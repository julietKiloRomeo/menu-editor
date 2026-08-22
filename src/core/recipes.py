"""Recipe loading."""

from __future__ import annotations

import pathlib
from typing import Any

import yaml
from sqlalchemy import or_
from sqlmodel import select

from src.models import Recipe, get_session


def load_recipe_data(identifier: str) -> dict[str, Any]:
    """Load a recipe by slug or name, falling back to the legacy YAML files.

    Raises FileNotFoundError when the identifier is not a recipe at all --
    callers rely on that to treat the identifier as a bare ingredient.
    """
    with get_session() as session:
        statement = select(Recipe).where(
            or_(Recipe.slug == identifier, Recipe.navn == identifier)
        )
        db_recipe = session.exec(statement).first()

    if db_recipe:
        return {
            "navn": db_recipe.navn,
            "placering": db_recipe.placering,
            "antal": db_recipe.antal,
            "ingredienser": db_recipe.ingredienser or {},
            "extras": db_recipe.extras or {},
        }

    recipe_pth = pathlib.Path.cwd() / f"recipes/{identifier}.yml"
    with recipe_pth.open("r") as f:
        return yaml.load(f, Loader=yaml.FullLoader)
