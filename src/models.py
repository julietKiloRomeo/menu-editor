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

from sqlalchemy import Column, event
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

    Salt, oil, most spices: they appear in recipe after recipe and are ticked
    off unread every single week. Recording them lets a new run start with them
    already ticked, so the list shows what actually needs attention (story 5.3).

    They are *pre-ticked rather than hidden*, because "usually" is not "always"
    -- when the oil finally runs out it must be possible to untick it.
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


def init_db() -> None:
    with initialization_lock():
        SQLModel.metadata.create_all(engine)


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
    "engine",
    "init_db",
    "initialization_lock",
    "get_session",
]
