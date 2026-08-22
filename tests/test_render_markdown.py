"""Unit tests for markdown rendering.

The golden tests lock whole documents; these pin the individual formatting
decisions that are easy to break and hard to spot in a big diff.
"""

from __future__ import annotations

from src.core.shopping import (
    AggregatedMenu,
    MenuEntry,
    MenuSection,
    ShoppingLine,
    ShoppingList,
)
from src.core.zones import UNKNOWN_ZONE, Zone
from src.render.markdown import (
    UNMAPPED_LABEL,
    quantity_string,
    recipes_string,
    render,
    render_menu_entry,
    render_shopping,
    zone_label,
)

FRUGT = Zone("frugt", 2)
KØL = Zone("køl", 9)
UNKNOWN = Zone(UNKNOWN_ZONE, 1000)


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


class TestQuantities:
    def test_trailing_zeros_are_trimmed(self):
        assert quantity_string(line("x", quantities={"g": 500.0})).strip() == "500 g"

    def test_fractions_are_kept(self):
        assert quantity_string(line("x", quantities={"stk": 0.5})).strip() == "0.5 stk"

    def test_multiple_units_are_joined_not_converted(self):
        text = quantity_string(line("x", quantities={"fed": 6.0, "løg": 0.5}))
        assert "6 fed" in text and "0.5 løg" in text and "+" in text


class TestRecipeColumn:
    def test_recipe_names_are_truncated_to_twelve_chars(self):
        text = recipes_string(line("x", recipes=["Boller i karry med ris"]))
        assert text == "Boller i kar"

    def test_duplicates_collapse(self):
        text = recipes_string(line("x", recipes=["Grød", "Grød"]))
        assert text == "Grød"

    def test_self_reference_dropped_when_a_recipe_also_contributes(self):
        text = recipes_string(line("mælk", recipes=["mælk", "Grød"]))
        assert text == "Grød"


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


class TestZoneHeadings:
    def test_zone_name_is_rendered_as_the_table_heading(self):
        text = collect(render_shopping, ShoppingList([line("æble")]))
        assert "| **frugt** |" in text

    def test_each_zone_starts_a_new_table(self):
        shopping = ShoppingList([line("æble", FRUGT), line("mælk", KØL)])
        text = collect(render_shopping, shopping)
        assert "| **frugt** |" in text and "| **køl** |" in text

    def test_one_table_per_zone_not_per_line(self):
        shopping = ShoppingList([line("æble", FRUGT), line("banan", FRUGT)])
        text = collect(render_shopping, shopping)
        assert text.count("| **frugt** |") == 1

    def test_unknown_zone_gets_a_human_label(self):
        assert zone_label(UNKNOWN) == UNMAPPED_LABEL
        text = collect(render_shopping, ShoppingList([line("AA", UNKNOWN)]))
        assert f"| **{UNMAPPED_LABEL}** |" in text
        assert "unknown" not in text


class TestUnmappedFooter:
    def test_no_footer_when_everything_is_placed(self):
        text = collect(render_shopping, ShoppingList([line("æble")]))
        assert "mangler en zone" not in text

    def test_singular_footer(self):
        text = collect(render_shopping, ShoppingList([line("AA", UNKNOWN)]))
        assert "1 vare mangler en zone: AA." in text
        assert "Tildel den " in text

    def test_plural_footer_lists_every_item(self):
        shopping = ShoppingList(
            [line("halloumi", UNKNOWN), line("smoothies", UNKNOWN)]
        )
        text = collect(render_shopping, shopping)
        assert "2 varer mangler en zone: halloumi, smoothies." in text
        assert "Tildel dem " in text


class TestDocument:
    def test_silent_sections_are_omitted_from_the_menu(self):
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
        # ...but the ingredient is still bought
        assert "kaffe" in text

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

    def test_document_order_is_menu_then_shopping(self):
        aggregated = AggregatedMenu(
            sections=[MenuSection("Mandag", False, [MenuEntry("Grød", "", 1, False)])],
            shopping=ShoppingList([line("ris")]),
        )
        text = collect(render, aggregated)
        assert text.index("# Menu") < text.index("# Shopping")
