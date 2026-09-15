"""Unit tests for markdown rendering.

Only the menu is rendered now; the shopping list travels as structured data
(see ``tests/test_render_export.py``). These pin the formatting decisions that
are easy to break and hard to spot in a big diff.
"""

from __future__ import annotations

from src.core.shopping import (
    AggregatedMenu,
    MenuEntry,
    MenuSection,
    ShoppingLine,
    ShoppingList,
)
from src.core.zones import Zone
from src.render.markdown import render, render_menu_entry

FRUGT = Zone("frugt", 2)


def line(ingredient, zone=FRUGT, quantities=None, recipes=None):
    return ShoppingLine(
        ingredient=ingredient,
        zone=zone,
        quantities=quantities or {"stk": 1.0},
        recipes=recipes or [ingredient],
    )


def collect(fn, *args):
    out: list[str] = []
    fn(*args, printer=out.append)
    return "\n".join(out)


class TestMenuEntries:
    def test_single_batch_shows_no_multiplier(self):
        entry = MenuEntry("Grød", "side 12", 1, silent=False)
        assert "(x" not in render_menu_entry(entry)

    def test_multiplier_is_shown(self):
        entry = MenuEntry("Grød", "side 12", 2, silent=False)
        assert "(x2)" in render_menu_entry(entry)

    def test_zero_multiplier_reads_as_freezer(self):
        entry = MenuEntry("Grød", "side 12", 0, silent=False)
        assert "(fryser)" in render_menu_entry(entry)

    def test_placering_is_included(self):
        entry = MenuEntry("Grød", "side 12", 1, silent=False)
        assert "side 12" in render_menu_entry(entry)


class TestDocument:
    def test_silent_sections_are_omitted(self):
        aggregated = AggregatedMenu(
            sections=[
                MenuSection(
                    "Weekly staples",
                    silent=True,
                    entries=[MenuEntry("Kaffe", "", 1, silent=True)],
                )
            ],
            shopping=ShoppingList([line("kaffe")]),
        )
        text = collect(render, aggregated)
        assert "Weekly staples" not in text
        assert "Kaffe" not in text

    def test_visible_sections_are_rendered(self):
        aggregated = AggregatedMenu(
            sections=[
                MenuSection(
                    "Mandag",
                    silent=False,
                    entries=[MenuEntry("Grød", "side 12", 1, silent=False)],
                )
            ],
            shopping=ShoppingList([line("ris")]),
        )
        text = collect(render, aggregated)
        assert "## Mandag" in text
        assert " - Grød" in text

    def test_the_shopping_list_is_not_printed(self):
        """What goes on the fridge is the menu. The list is ticked on a phone."""
        aggregated = AggregatedMenu(
            sections=[MenuSection("Mandag", False, [MenuEntry("Grød", "", 1, False)])],
            shopping=ShoppingList([line("rødbeder")]),
        )
        text = collect(render, aggregated)
        assert text.startswith("# Menu")
        assert "# Shopping" not in text
        assert "rødbeder" not in text
