"""Shared fixtures for shopping-list golden tests.

The golden tests lock the rendered markdown output of the shopping-list
pipeline so the Phase 1 core extraction can be proven behaviour-preserving.
"""

from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEGACY_CONFIG = ROOT / "archive" / "2025-10-26-legacy" / "config.yml"
GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"

# A deliberately diverse spread: different eras of the file format, menus with
# zero-amount (freezer) entries, bare ingredients that are not recipes, silent
# "Andet" sections, and recipes that recurse through `extras`.
GOLDEN_MENUS = [
    "uge_01_2021.yaml",
    "uge_07_2023.yaml",
    "uge_13_2023.yaml",
    "uge_21_2021.yaml",
    "uge_27_2023.yaml",
    "uge_36_2022.yaml",
    "uge_43_2022.yaml",
    "uge_48_2020.yaml",
]


def seed_legacy_config(models) -> None:
    """Seed the temp DB with the real 13-zone / 501-mapping legacy config.

    Uses the archived config.yml so the golden output exercises real category
    priorities rather than the 6-row test seed shipped in recipes.db.
    """
    config = yaml.safe_load(LEGACY_CONFIG.read_text(encoding="utf-8"))

    with models.get_session() as session:
        by_name = {}
        for name, priority in config["kategorier"].items():
            category = models.CategoryConfig(name=name, priority=priority)
            session.add(category)
            by_name[name] = category
        session.commit()

        for category in by_name.values():
            session.refresh(category)

        for ingredient, category_name in config["varer"].items():
            category = by_name.get(category_name)
            if category is None:
                continue
            session.add(
                models.IngredientConfig(name=ingredient, category_id=category.id)
            )
        session.commit()


def render_menu_to_text(parser_module, menu_name: str) -> str:
    """Run the shopping pipeline for one menu and return the rendered markdown."""
    lines: list[str] = []
    parser_module.write_menu(
        ROOT / "menus" / menu_name,
        printer=lines.append,
        silent_sections={"Weekly staples"},
    )
    return "\n".join(lines) + "\n"
