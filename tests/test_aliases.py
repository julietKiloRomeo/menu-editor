"""Tests for ingredient aliases."""

from __future__ import annotations

from src.core.ingredients import AliasMap, normalise
from src.core.shopping import aggregate_menu
from src.core.zones import Zone, ZoneConfig

ZONES = ZoneConfig(
    zones={"frugt": Zone("frugt", 2)},
    assignments={"koriander": "frugt"},
)

RECIPE = {
    "navn": "Karry",
    "placering": "",
    "antal": 4,
    "ingredienser": {
        "frisk koriander": {"amount": 1, "unit": "bdt"},
        "koriander": {"amount": 1, "unit": "bdt"},
    },
    "extras": {},
}


def aggregate(aliases=None):
    return aggregate_menu(
        {"Mad": [{"karry": {"amount": 4, "unit": "plates"}}]},
        ZONES,
        load_recipe=lambda _: {
            **RECIPE,
            "ingredienser": {k: dict(v) for k, v in RECIPE["ingredienser"].items()},
        },
        aliases=aliases,
    )


class TestNormalise:
    def test_trims_and_casefolds(self):
        assert normalise("  Frisk Koriander ") == "frisk koriander"

    def test_handles_danish_characters(self):
        assert normalise("RØDLØG") == "rødløg"


class TestAliasMap:
    def test_unknown_names_pass_through_untouched(self):
        assert AliasMap().canonical("koriander") == "koriander"

    def test_alias_resolves_to_canonical(self):
        m = AliasMap.from_pairs({"frisk koriander": "koriander"})
        assert m.canonical("frisk koriander") == "koriander"

    def test_lookup_is_case_insensitive(self):
        m = AliasMap.from_pairs({"frisk koriander": "koriander"})
        assert m.canonical("Frisk Koriander") == "koriander"

    def test_canonical_spelling_wins_over_input_casing(self):
        m = AliasMap.from_pairs({"MÆLK": "mælk"})
        assert m.canonical("mælk ") == "mælk"

    def test_is_alias(self):
        m = AliasMap.from_pairs({"frisk koriander": "koriander"})
        assert m.is_alias("FRISK KORIANDER")
        assert not m.is_alias("koriander")


class TestAggregationWithAliases:
    def test_without_aliases_the_two_spellings_are_separate_lines(self):
        names = [line.ingredient for line in aggregate().shopping.lines]
        assert sorted(names) == ["frisk koriander", "koriander"]

    def test_alias_merges_them_into_one_line(self):
        aliases = AliasMap.from_pairs({"frisk koriander": "koriander"})
        lines = aggregate(aliases).shopping.lines
        assert [line.ingredient for line in lines] == ["koriander"]

    def test_merged_amounts_are_summed(self):
        aliases = AliasMap.from_pairs({"frisk koriander": "koriander"})
        line = aggregate(aliases).shopping.lines[0]
        assert line.quantities == {"bdt": 2.0}

    def test_alias_inherits_the_canonical_ingredients_zone(self):
        aliases = AliasMap.from_pairs({"frisk koriander": "koriander"})
        line = aggregate(aliases).shopping.lines[0]
        assert line.zone.name == "frugt"
        assert not line.is_unmapped

    def test_alias_of_an_unplaced_ingredient_stays_unplaced(self):
        aliases = AliasMap.from_pairs({"koriander": "cilantro"})
        lines = {line.ingredient: line for line in aggregate(aliases).shopping.lines}
        assert lines["cilantro"].is_unmapped
