from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None

from sqlalchemy import Column, event, inspect
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///recipes.db")


def _sqlite_kwargs(url: str) -> Dict[str, Dict[str, bool]]:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    """Enable WAL so several processes can share one SQLite file.

    The web app and the MCP server are separate processes reading and writing
    the same database; without WAL a reader blocks a writer and vice versa.
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


engine = create_engine(DATABASE_URL, **_sqlite_kwargs(DATABASE_URL))


class RecipeBase(SQLModel):
    slug: str = Field(index=True, unique=True)
    navn: str = Field(index=True, unique=True)
    placering: Optional[str] = None
    antal: int = Field(default=4, ge=0)
    ingredienser: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    extras: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )


class Recipe(RecipeBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    is_blacklisted: bool = Field(default=False, index=True)
    is_whitelisted: bool = Field(default=False, index=True)


class CategoryConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    priority: int = Field(default=0)


class IngredientConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category_id: Optional[int] = Field(default=None, foreign_key="categoryconfig.id")


class IngredientAlias(SQLModel, table=True):
    """Maps a writing of an ingredient onto the name the shopping list uses.

    Recipes spell things differently -- "frisk koriander" and "koriander" are
    the same bunch of herbs -- and without this they aggregate into two rows
    and get bought twice.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    alias: str = Field(index=True, unique=True)
    canonical: str = Field(index=True)


class StapleItem(SQLModel, table=True):
    """Something bought *every* week, injected into every menu.

    Not to be confused with :class:`StockedItem`, which is the opposite idea:
    something already in the kitchen that therefore should *not* be bought.
    One of this table's display labels is "Pantry essentials", so the two are
    easy to mix up -- the test is whether the item ends up in the basket.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    amount: float = Field(default=1.0)
    unit: str = Field(default="stk")


class StockedItem(SQLModel, table=True):
    """An ingredient the household normally already has in.

    Salt, oil, most spices: they turn up in recipe after recipe and are usually
    already in the cupboard. Recording them lets the list say so (story 5.3).

    They are flagged, *not* ticked and *not* hidden. "Usually" is not "always",
    and a list that quietly assumes you still have salt is the list that sends
    you home without any. The hint saves you a decision; it does not make it
    for you.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    #: stored :func:`src.core.ingredients.normalise`-d, so matching is
    #: case-insensitive without every caller remembering to fold case
    name: str = Field(index=True, unique=True)


class ShoppingRun(SQLModel, table=True):
    """One trip's shopping list, frozen at the moment it was started.

    A run is a *snapshot*, not a live view of the menu. Editing a recipe while
    halfway around the kitchen must not reorder the list underneath you, nor
    silently drop an item you have already ticked. That means the zone name and
    order are copied onto each item rather than joined at read time.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    menu_name: str = Field(index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )


class ShoppingRunItem(SQLModel, table=True):
    """One tickable row of a :class:`ShoppingRun`."""

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[int] = Field(
        default=None, foreign_key="shoppingrun.id", index=True
    )
    #: position in the original list, so display order survives any re-sorting
    position: int = Field(default=0)
    ingredient: str = Field(index=True)
    #: unit -> amount, mirroring ShoppingLine.quantities. Units are never
    #: converted, so "100 g" and "1 kg" stay separate buckets.
    quantities: Dict[str, float] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    #: contributing recipe names, to answer "why is this on my list?"
    recipes: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )
    zone_name: str = Field(default="")
    zone_order: int = Field(default=0)
    checked: bool = Field(default=False)
    checked_at: Optional[datetime] = Field(default=None)
    #: matched a :class:`StockedItem` when the run started -- a hint that this
    #: is probably already in the cupboard, never an assumption that it is
    likely_stocked: bool = Field(default=False)


class NemligOrder(SQLModel, table=True):
    """One attempt at turning a walked run into a nemlig.com basket.

    Separate from :class:`ShoppingRun` because they answer different questions
    and have different lifetimes. A run is "what does the kitchen still need",
    settled once you have walked it. An order is "which product, how many" --
    thirty to sixty judgement calls that take half an hour, get interrupted, and
    must survive a closed tab. It is also legitimately one-to-many: a basket can
    be abandoned and restarted against the same run.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[int] = Field(default=None, foreign_key="shoppingrun.id", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    #: free text naming where the list came from, copied into the product map
    source: str = Field(default="")
    #: set when the learnings have been folded back into the product map, so a
    #: half-finished order is never mistaken for a finished one
    recorded_at: Optional[datetime] = Field(default=None)


class NemligOrderItem(SQLModel, table=True):
    """One row of the picker: an ingredient and what was decided about it."""

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="nemligorder.id", index=True)
    #: preserves the walked list's zone-then-position order, because the picker
    #: is compared line by line against the list it came from
    position: int = Field(default=0)
    ingredient: str = Field(index=True)
    #: the quantity as the recipes asked for it, pre-rendered ("3 dl + 300 g").
    #: Kept as text: it is shown to a human deciding how many packs to buy, and
    #: is never arithmetic again.
    need: str = Field(default="")
    recipes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    zone_name: str = Field(default="")
    #: mapped / stocked / new -- what the product map knew before this run
    status: str = Field(default="new")
    #: what to search nemlig for; empty when the product is unreachable by
    #: search and only a pasted link will do
    query: str = Field(default="")
    candidates: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    #: why this row was unresolved last time, carried from the product map's
    #: no_default_yet. Kept apart from ``note`` so the map's own warning is
    #: never mistaken for something the user typed and written back as one.
    warning: str = Field(default="")
    #: one of src.core.nemlig.ACTIONS, or None while undecided
    action: Optional[str] = Field(default=None)
    product_id: Optional[str] = Field(default=None)
    #: the chosen candidate, copied so the basket stays reviewable even if the
    #: candidate list is later rebuilt from a fresh search
    product: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    qty: int = Field(default=1)
    #: True only after the user edits the quantity. The database default is
    #: deliberately true so quantities saved before this flag existed are
    #: protected during migration. New picker rows explicitly set it false.
    qty_manual: bool = Field(default=True)
    note: str = Field(default="")
    url: str = Field(default="")


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: Optional[str] = None


_lock_depth = 0


@contextmanager
def initialization_lock():
    """Serialise start-up work that reads state and then writes it.

    ``create_all(checkfirst=True)`` reflects the existing tables and then emits
    the ``CREATE TABLE`` statements for whatever is missing. Those two steps are
    not atomic, so when several processes start together -- gunicorn runs the app
    with multiple workers, and each worker imports ``app``, which calls
    ``init_db()`` -- they can all observe an empty database and all try to create
    the same tables. Every process but the winner then dies with
    "table recipe already exists".

    Seeding reference data has the same shape: it reads the rows that already
    exist and inserts the missing ones, so concurrent workers otherwise collide
    on a UNIQUE constraint.

    An exclusive file lock makes those read-then-write sequences atomic. The lock
    lives in the temp directory, which serialises the workers inside a single
    container; concurrent writers from separate hosts are not supported by SQLite
    anyway.
    """
    global _lock_depth

    # flock is tied to the open file description, so a second exclusive
    # acquisition from the same process would deadlock. Track depth and let
    # nested callers through.
    if fcntl is None or _lock_depth > 0:  # pragma: no cover - non-POSIX platforms
        _lock_depth += 1
        try:
            yield
        finally:
            _lock_depth -= 1
        return

    digest = hashlib.sha256(str(engine.url).encode()).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"menu-editor-init-{digest}.lock"

    with open(lock_path, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        _lock_depth += 1
        try:
            yield
        finally:
            _lock_depth -= 1
            fcntl.flock(handle, fcntl.LOCK_UN)


def add_missing_columns(connection) -> list[str]:
    """Bring existing tables up to date with the models, additively.

    ``create_all`` only ever creates missing *tables*. A column added to a
    model that already has a table is silently ignored, and the failure then
    surfaces much later as "table X has no column named Y" on the first insert
    -- in production, against real data, long after the tests passed on their
    freshly created schemas.

    Only additions are performed. Dropping, renaming or retyping a column is
    never guessed at: those need a real migration, and are reported instead.

    Returns a description of each column added.
    """
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []

    for table in SQLModel.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all will make it in full

        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue

            # A NOT NULL column with no default cannot be added to a table that
            # already has rows; SQLite rejects it outright.
            if not column.nullable and column.default is None:
                raise RuntimeError(
                    f"Cannot add required column {table.name}.{column.name} "
                    "automatically: it is NOT NULL with no default. "
                    "This needs a hand-written migration."
                )

            spec = column.type.compile(connection.dialect)
            clause = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {spec}'
            if column.default is not None and column.default.is_scalar:
                clause += f" DEFAULT {_sql_literal(column.default.arg)}"

            connection.exec_driver_sql(clause)
            added.append(f"{table.name}.{column.name}")

    return added


def _sql_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "NULL"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def init_db() -> None:
    with initialization_lock():
        SQLModel.metadata.create_all(engine)
        with engine.begin() as connection:
            add_missing_columns(connection)


@contextmanager
def get_session() -> Session:
    with Session(engine) as session:
        yield session


__all__ = [
    "CategoryConfig",
    "IngredientConfig",
    "IngredientAlias",
    "StapleItem",
    "StockedItem",
    "ShoppingRun",
    "ShoppingRunItem",
    "AppSetting",
    "Recipe",
    "RecipeBase",
    "add_missing_columns",
    "engine",
    "init_db",
    "initialization_lock",
    "get_session",
]
