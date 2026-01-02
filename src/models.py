from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Dict, Optional, Any

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


def init_db() -> None:
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
    "get_session",
]
