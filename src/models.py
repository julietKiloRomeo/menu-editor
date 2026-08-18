from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional, Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None

from sqlalchemy import Column
from sqlalchemy.dialects.sqlite import JSON
from sqlmodel import Field, Session, SQLModel, create_engine


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///recipes.db")


def _sqlite_kwargs(url: str) -> Dict[str, Dict[str, bool]]:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


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


class StapleItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    amount: float = Field(default=1.0)
    unit: str = Field(default="stk")


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
    "StapleItem",
    "AppSetting",
    "Recipe",
    "RecipeBase",
    "engine",
    "init_db",
    "initialization_lock",
    "get_session",
]
