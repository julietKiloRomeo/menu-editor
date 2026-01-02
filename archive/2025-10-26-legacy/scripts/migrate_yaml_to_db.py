#!/usr/bin/env python3
"""Migrate existing YAML recipes into the SQLite database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import yaml
from sqlalchemy import or_
from sqlmodel import Session, select

from src.models import (
    CategoryConfig,
    IngredientConfig,
    Recipe,
    engine,
    init_db,
)

DEFAULT_BLACKLIST = {
    "Chokoladetærte med saltkaramel",
    "Peberkager",
    "Coleslaw",
    "Dilddressing",
    "Pitabrød",
    "Knuste Kartofler",
    "Flødekartofler",
    "Blomkålssalat med æbler og mandler",
    "Kartoffelmos",
    "Broccolisalat",
    "Anders Ands kanelsnegle",
    "Hvidkålssalat",
    "Rucolasalat med bagte tomater",
    "Raita",
    "Pirogger med oksekød",
    "Pita brød",
    "Mango lassi",
    "TikTok baked oats",
    "Spinatsalat med feta og granatæble",
    "Spinat Pandekager",
    "Pizzadej",
    "Raw muslibar",
    "Mettes Æblekage",
    "Rugboller",
    "Naan",
    "Bedstemor ands chokoladekage",
    "Verdens bedste burger",
    "Kyllinge Nuggets med Corn Flakes",
    "Calzoneboller",
    "Bananbrød",
    "standard",
    "Hindbær Brülee",
    "Panna Cotta med Havtorn",
    "Tunmousse",
    "Syltede rødløg",
}

DEFAULT_WHITELIST: set[str] = set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "recipes_dir",
        type=Path,
        nargs="?",
        default=Path("recipes"),
        help="Path to the directory containing recipe YAML files (default: recipes/).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yml"),
        help="Path to the YAML config file to migrate (default: config.yml).",
    )
    parser.add_argument(
        "--blacklist",
        type=Path,
        help="Optional path to a JSON or newline-delimited file listing recipes (name or slug) to blacklist.",
    )
    parser.add_argument(
        "--whitelist",
        type=Path,
        help="Optional path to a JSON or newline-delimited file listing recipes (name or slug) to whitelist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended actions without modifying the database.",
    )
    return parser.parse_args()


def load_list_from_file(path: Path | None) -> set[str]:
    if not path:
        return set()
    if not path.exists():
        raise FileNotFoundError(f"List file not found: {path}")

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return set()

    try:
        loaded = json.loads(content)
        if isinstance(loaded, list):
            return {str(item).strip() for item in loaded if str(item).strip()}
    except json.JSONDecodeError:
        pass

    return {line.strip() for line in content.splitlines() if line.strip()}


def load_recipe_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Recipe file {path} did not contain a mapping")
    return data


def normalise_mapping(mapping: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalised: Dict[str, Dict[str, Any]] = {}
    for name, value in (mapping or {}).items():
        if not isinstance(value, dict):
            continue
        amount = value.get("amount", 0)
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            continue
        unit = str(value.get("unit", "")).strip()
        normalised[name] = {"amount": amount_value, "unit": unit}
    return normalised


def upsert_recipe(path: Path, blacklist: set[str], whitelist: set[str], dry_run: bool = False) -> None:
    data = load_recipe_yaml(path)
    slug = path.stem
    name = data.get("navn") or slug
    placering = data.get("placering")
    antal = data.get("antal") or 4

    try:
        antal = int(antal)
    except (TypeError, ValueError):
        antal = 4

    ingredienser = normalise_mapping(data.get("ingredienser", {}))
    extras = normalise_mapping(data.get("extras", {}))

    blacklist_hit = slug in blacklist or name in blacklist
    whitelist_hit = slug in whitelist or name in whitelist

    with Session(engine) as session:
        existing = session.exec(
            select(Recipe).where(or_(Recipe.slug == slug, Recipe.navn == name))
        ).first()

        if dry_run:
            action = "UPDATE" if existing else "CREATE"
            print(f"{action}: {name} ({slug})")
            return

        if existing:
            existing.slug = slug
            existing.navn = name
            existing.placering = placering
            existing.antal = antal
            existing.ingredienser = ingredienser
            existing.extras = extras
            existing.is_blacklisted = blacklist_hit
            existing.is_whitelisted = whitelist_hit
            session.add(existing)
        else:
            recipe = Recipe(
                slug=slug,
                navn=name,
                placering=placering,
                antal=antal,
                ingredienser=ingredienser,
                extras=extras,
                is_blacklisted=blacklist_hit,
                is_whitelisted=whitelist_hit,
            )
            session.add(recipe)

        session.commit()


def migrate_config(config_path: Path, dry_run: bool = False) -> None:
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    categories_data = data.get("kategorier", {}) or {}
    items_data = data.get("varer", {}) or {}

    if dry_run:
        print(f"Would migrate {len(categories_data)} categories and {len(items_data)} ingredient mappings from {config_path}")
        return

    with Session(engine) as session:
        # categories
        for name, priority in categories_data.items():
            try:
                priority_value = int(priority)
            except (TypeError, ValueError):
                priority_value = 0

            existing = session.exec(
                select(CategoryConfig).where(CategoryConfig.name == name)
            ).first()

            if existing:
                existing.priority = priority_value
                category = existing
            else:
                category = CategoryConfig(name=name, priority=priority_value)
            session.add(category)

        session.commit()

        categories = session.exec(select(CategoryConfig)).all()
        category_lookup = {category.name: category.id for category in categories}

        for ingredient, category_name in items_data.items():
            category_id = category_lookup.get(category_name)
            if not category_id:
                continue

            existing_item = session.exec(
                select(IngredientConfig).where(IngredientConfig.name == ingredient)
            ).first()

            if existing_item:
                existing_item.category_id = category_id
                session.add(existing_item)
            else:
                session.add(IngredientConfig(name=ingredient, category_id=category_id))

        session.commit()


def main() -> None:
    args = parse_args()
    init_db()

    blacklist = set(DEFAULT_BLACKLIST)
    whitelist = set(DEFAULT_WHITELIST)

    blacklist.update(load_list_from_file(args.blacklist))
    whitelist.update(load_list_from_file(args.whitelist))

    if not args.recipes_dir.exists():
        raise FileNotFoundError(f"Recipes directory not found: {args.recipes_dir}")

    recipe_files = sorted(args.recipes_dir.glob('*.yml'))

    if not recipe_files:
        print("No recipe YAML files found.")
    else:
        for recipe_file in recipe_files:
            upsert_recipe(recipe_file, blacklist, whitelist, dry_run=args.dry_run)

    migrate_config(args.config, dry_run=args.dry_run)

    if args.dry_run:
        print("Dry run complete.")
    else:
        print(f"Migrated {len(recipe_files)} recipes and configuration into the database.")


if __name__ == "__main__":
    main()
