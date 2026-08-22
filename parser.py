"""Back-compat shim over ``src.core`` plus the menu CLI.

The aggregation logic that used to live here now lives in
``src.core.shopping``, and the markdown rendering in ``src.render.markdown``.
This module keeps the historic entry points working.
"""

import datetime
import pathlib

import click
import yaml

from src.core.ingredients import load_alias_map
from src.core.recipes import load_recipe_data
from src.core.shopping import aggregate_menu
from src.core.zones import ZoneConfig, load_zone_config
from src.render.markdown import render

__all__ = [
    "aggregate_menu_file",
    "load_config",
    "load_config_from_db",
    "load_recipe_data",
    "write_menu",
]


def load_config_from_db():
    """Legacy ``{"kategorier": ..., "varer": ...}`` view of the zone config."""
    return load_zone_config().to_legacy_dict()


def load_config():
    try:
        return load_config_from_db()
    except LookupError:
        raise RuntimeError(
            "No categories found in the database. Seed data via the /api/config endpoints before generating menus."
        ) from None


def _load_zone_config() -> ZoneConfig:
    try:
        return load_zone_config()
    except LookupError:
        raise RuntimeError(
            "No categories found in the database. Seed data via the /api/config endpoints before generating menus."
        ) from None


def aggregate_menu_file(menu_path, silent_sections=None):
    """Read a menu file and return the structured :class:`AggregatedMenu`."""
    with pathlib.Path(menu_path).open("r") as f:
        menu = yaml.load(f, Loader=yaml.FullLoader)

    return aggregate_menu(
        menu,
        _load_zone_config(),
        load_recipe=load_recipe_data,
        silent_sections=silent_sections,
        aliases=load_alias_map(),
    )


def write_menu(menu_path, printer=print, silent_sections=None):
    """Aggregate a menu file and render it as markdown through ``printer``."""
    render(aggregate_menu_file(menu_path, silent_sections), printer=printer)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("week", type=int)
@click.argument("year", default=datetime.date.today().year, type=int)
def menu(week, year):
    menu_path = pathlib.Path.cwd() / f"menus/uge_{week:02d}_{year}.yaml"
    write_menu(menu_path)


if __name__ == "__main__":
    cli()
