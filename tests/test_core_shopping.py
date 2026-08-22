"""Unit tests for the shopping aggregation core.

These use an injected recipe loader so they stay pure and fast -- no database,
no filesystem.
"""

from __future__ import annotations

from src.core.shopping import aggregate_menu
from src.core.zones import UNKNOWN_ZONE, Zone, ZoneConfig

ZONES = ZoneConfig(
    zones={
        "frugt": Zone("frugt", 2),
        "tilbehør": Zone("tilbehør", 3),
        "køl": Zone("køl", 9),
        UNKNOWN_ZONE: Zone(UNKNOWN_ZONE, 1000),
    },
    assignments={
        "æble": "frugt",
        "løg": "frugt",
        "ris": "tilbehør",
        "mælk": "køl",
    },
)

RECIPES = {
    "grød": {
        "navn": "Grød",
        "placering": "side 12",
        "antal": 4,
        "ingredienser": {
            "mælk": {"amount": 500, "unit": "ml"},
            "ris": {"amount": 200, "unit": "g"},
        },
        "extras": {},
    },
    "kage": {
        "navn": "Kage",
        "placering": "side 44",
        "antal": 8,
        "ingredienser": {"æble": {"amount": 4, "unit": "stk"}},
        "extras": {"glasur": {"amount": 1, "unit": "recipe"}},
    },
    "glasur": {
        "navn": "Glasur",
        "placering": "",
        "antal": 1,
        "ingredienser": {"mælk": {"amount": 1, "unit": "dl"}},
        "extras": {},
    },
}


def loader(identifier):
    if identifier not in RECIPES:
        raise FileNotFoundError(identifier)
    # Deep-ish copy so a test can never be polluted by in-place scaling.
    recipe = dict(RECIPES[identifier])
    recipe["ingredienser"] = {
        k: dict(v) for k, v in RECIPES[identifier]["ingredienser"].items()
    }
    recipe["extras"] = {k: dict(v) for k, v in RECIPES[identifier]["extras"].items()}
    return recipe


def aggregate(menu, **kwargs):
    return aggregate_menu(menu, ZONES, load_recipe=loader, **kwargs)


def lines_by_name(result):
    return {line.ingredient: line for line in result.shopping.lines}


class TestScaling:
    def test_plates_scale_against_recipe_yield(self):
        result = aggregate({"Mad": [{"grød": {"amount": 8, "unit": "plates"}}]})
        # 8 plates of a 4-serving recipe == double
        assert lines_by_name(result)["mælk"].quantities == {"ml": 1000.0}

    def test_unit_recipe_is_a_batch_count(self):
        result = aggregate({"Mad": [{"grød": {"amount": 3, "unit": "recipe"}}]})
        assert lines_by_name(result)["ris"].quantities == {"g": 600.0}

    def test_bare_string_entry_means_one_batch(self):
        result = aggregate({"Mad": ["grød"]})
        assert lines_by_name(result)["ris"].quantities == {"g": 200.0}

    def test_zero_plates_contributes_nothing(self):
        result = aggregate({"Mad": [{"grød": {"amount": 0, "unit": "plates"}}]})
        assert result.shopping.lines == []

    def test_zero_plates_still_appears_on_the_menu_as_freezer(self):
        result = aggregate({"Mad": [{"grød": {"amount": 0, "unit": "plates"}}]})
        entry = result.sections[0].entries[0]
        assert entry.multiplier == 0

    def test_recipe_with_zero_yield_does_not_divide_by_zero(self):
        recipe = {"navn": "X", "antal": 0, "ingredienser": {}, "extras": {}}
        result = aggregate_menu(
            {"Mad": [{"x": {"amount": 4, "unit": "plates"}}]},
            ZONES,
            load_recipe=lambda _: recipe,
        )
        assert result.sections[0].entries[0].multiplier == 0


class TestMerging:
    def test_same_ingredient_across_recipes_is_summed(self):
        result = aggregate(
            {
                "Mad": [
                    {"grød": {"amount": 4, "unit": "plates"}},
                    {"glasur": {"amount": 1, "unit": "recipe"}},
                ]
            }
        )
        # 500 ml from grød, 1 dl from glasur -- different units, not converted
        assert lines_by_name(result)["mælk"].quantities == {"ml": 500.0, "dl": 1.0}

    def test_unit_order_follows_first_appearance(self):
        result = aggregate(
            {
                "Mad": [
                    {"grød": {"amount": 4, "unit": "plates"}},
                    {"glasur": {"amount": 1, "unit": "recipe"}},
                ]
            }
        )
        assert list(lines_by_name(result)["mælk"].quantities) == ["ml", "dl"]

    def test_contributing_recipes_are_deduplicated(self):
        result = aggregate(
            {
                "Mad": [
                    {"grød": {"amount": 4, "unit": "plates"}},
                    {"grød": {"amount": 4, "unit": "plates"}},
                ]
            }
        )
        assert lines_by_name(result)["ris"].contributing_recipes() == ["Grød"]

    def test_self_reference_dropped_once_a_real_recipe_contributes(self):
        # 'mælk' bought in its own right, and also used by Grød
        result = aggregate(
            {
                "Mad": [{"grød": {"amount": 4, "unit": "plates"}}],
                "Andet": [{"mælk": {"amount": 1, "unit": "l"}}],
            }
        )
        assert lines_by_name(result)["mælk"].contributing_recipes() == ["Grød"]

    def test_self_reference_kept_when_it_is_the_only_source(self):
        result = aggregate({"Andet": [{"mælk": {"amount": 1, "unit": "l"}}]})
        assert lines_by_name(result)["mælk"].contributing_recipes() == ["mælk"]


class TestExtras:
    def test_extras_that_are_recipes_recurse(self):
        result = aggregate({"Mad": [{"kage": {"amount": 8, "unit": "plates"}}]})
        assert "mælk" in lines_by_name(result)

    def test_extras_that_are_recipes_appear_on_the_menu(self):
        result = aggregate({"Mad": [{"kage": {"amount": 8, "unit": "plates"}}]})
        assert [e.name for e in result.sections[0].entries] == ["Kage", "Glasur"]

    def test_unknown_extra_falls_back_to_a_plain_ingredient(self):
        recipe = {
            "navn": "Y",
            "antal": 1,
            "ingredienser": {},
            "extras": {"serviet": {"amount": 2, "unit": "pakke"}},
        }
        result = aggregate_menu(
            {"Mad": [{"y": {"amount": 1, "unit": "recipe"}}]},
            ZONES,
            load_recipe=lambda i: recipe if i == "y" else _raise(i),
        )
        assert lines_by_name(result)["serviet"].quantities == {"pakke": 2.0}

    def test_unknown_menu_entry_falls_back_to_a_plain_ingredient(self):
        result = aggregate({"Andet": [{"toiletpapir": {"amount": 1, "unit": "pakke"}}]})
        assert lines_by_name(result)["toiletpapir"].quantities == {"pakke": 1.0}


class TestZones:
    def test_lines_are_ordered_by_zone_then_name(self):
        result = aggregate(
            {
                "Mad": [
                    {"grød": {"amount": 4, "unit": "plates"}},
                    {"kage": {"amount": 8, "unit": "plates"}},
                ]
            }
        )
        # frugt(2) -> tilbehør(3) -> køl(9)
        assert [l.ingredient for l in result.shopping.lines] == [
            "æble",
            "ris",
            "mælk",
        ]

    def test_unmapped_ingredient_lands_in_the_unknown_zone(self):
        result = aggregate({"Andet": [{"halloumi": {"amount": 1, "unit": "stk"}}]})
        line = lines_by_name(result)["halloumi"]
        assert line.zone.name == UNKNOWN_ZONE
        assert line.is_unmapped

    def test_unmapped_helper_lists_only_unmapped_lines(self):
        result = aggregate(
            {
                "Andet": [
                    {"mælk": {"amount": 1, "unit": "l"}},
                    {"halloumi": {"amount": 1, "unit": "stk"}},
                ]
            }
        )
        assert [l.ingredient for l in result.shopping.unmapped()] == ["halloumi"]

    def test_by_zone_groups_in_walking_order(self):
        result = aggregate({"Mad": [{"grød": {"amount": 4, "unit": "plates"}}]})
        grouped = result.shopping.by_zone()
        assert [(z.name, [l.ingredient for l in ls]) for z, ls in grouped] == [
            ("tilbehør", ["ris"]),
            ("køl", ["mælk"]),
        ]

    def test_missing_unknown_zone_still_resolves(self):
        zones = ZoneConfig(zones={"frugt": Zone("frugt", 2)}, assignments={})
        result = aggregate_menu(
            {"Andet": [{"x": {"amount": 1, "unit": "stk"}}]},
            zones,
            load_recipe=_raise,
        )
        assert result.shopping.lines[0].zone.name == UNKNOWN_ZONE


class TestSilentSections:
    def test_silent_section_still_contributes_to_shopping(self):
        result = aggregate(
            {"Weekly staples": [{"mælk": {"amount": 2, "unit": "l"}}]},
            silent_sections={"Weekly staples"},
        )
        assert "mælk" in lines_by_name(result)

    def test_silent_section_is_marked_silent(self):
        result = aggregate(
            {"Weekly staples": [{"mælk": {"amount": 2, "unit": "l"}}]},
            silent_sections={"Weekly staples"},
        )
        assert result.sections[0].silent

    def test_andet_is_always_silent(self):
        result = aggregate({"Andet": [{"mælk": {"amount": 1, "unit": "l"}}]})
        assert result.sections[0].silent

    def test_silent_matching_is_case_insensitive(self):
        result = aggregate(
            {"WEEKLY STAPLES": [{"mælk": {"amount": 1, "unit": "l"}}]},
            silent_sections={"weekly staples"},
        )
        assert result.sections[0].silent


def _raise(identifier):
    raise FileNotFoundError(identifier)
