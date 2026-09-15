"""The structured menu export, and reading one back.

This pair is the hand-off between the instance that plans the menu and the one
that orders it, so the round-trip is the thing worth pinning: anything the
exporter drops, the importer cannot invent.
"""

from __future__ import annotations

import datetime
import json

import pytest

from src.core.shopping import (
    AggregatedMenu,
    MenuEntry,
    MenuSection,
    ShoppingLine,
    ShoppingList,
)
from src.core.zones import UNKNOWN_ORDER, UNKNOWN_ZONE, Zone, ZoneConfig
from src.render.export import (
    SCHEMA_VERSION,
    UnsupportedSchema,
    shopping_from_dict,
    to_dict,
)

FRUGT = Zone("frugt", 2)
KØL = Zone("køl", 9)
UNKNOWN = Zone(UNKNOWN_ZONE, UNKNOWN_ORDER)


def line(ingredient, zone=FRUGT, quantities=None, recipes=None):
    return ShoppingLine(
        ingredient=ingredient,
        zone=zone,
        quantities=quantities if quantities is not None else {"stk": 1.0},
        recipes=recipes if recipes is not None else [ingredient],
    )


def menu(*lines, sections=None):
    return AggregatedMenu(
        sections=sections or [],
        shopping=ShoppingList(list(lines)),
    )


class _StubZones(ZoneConfig):
    """A zone config that only knows what it is told."""

    def __init__(self, mapping):
        self._mapping = mapping

    def zone_for(self, ingredient):
        return self._mapping.get(ingredient.casefold(), UNKNOWN)


class TestDocumentShape:
    def test_carries_a_schema_version(self):
        document = to_dict(menu(line("Æbler")), name="uge_38_2026")
        assert document["schema"] == SCHEMA_VERSION

    def test_carries_the_name_and_date(self):
        document = to_dict(
            menu(line("Æbler")),
            name="uge_38_2026",
            generated=datetime.date(2026, 9, 12),
        )
        assert document["name"] == "uge_38_2026"
        assert document["generated"] == "2026-09-12"

    def test_is_json_serialisable(self):
        """It is written to a file and read on another machine."""
        document = to_dict(menu(line("Æbler", quantities={"kg": 1.5})), name="m")
        assert json.loads(json.dumps(document)) == document

    def test_menu_entries_are_included(self):
        sections = [
            MenuSection(
                "Mandag", silent=False, entries=[MenuEntry("Grød", "side 12", 2, False)]
            )
        ]
        document = to_dict(menu(line("Havregryn"), sections=sections), name="m")
        section = document["menu"][0]
        assert section["section"] == "Mandag"
        assert section["entries"][0] == {
            "name": "Grød",
            "placering": "side 12",
            "multiplier": 2,
            "silent": False,
        }


class TestShoppingRows:
    def test_units_stay_separate_buckets(self):
        """Matching the aggregator: 100 g and 1 kg are not merged."""
        document = to_dict(menu(line("Mel", quantities={"g": 100.0, "kg": 1.0})), name="m")
        assert document["shopping"][0]["quantities"] == {"g": 100.0, "kg": 1.0}

    def test_contributing_recipes_are_not_truncated(self):
        """The markdown column was clipped to 12 characters; this is not."""
        document = to_dict(
            menu(line("Fløde", recipes=["Gnocchi sommersalat", "Broccolitærte"])),
            name="m",
        )
        assert document["shopping"][0]["recipes"] == [
            "Broccolitærte",
            "Gnocchi sommersalat",
        ]

    def test_self_referencing_staple_keeps_itself_as_its_source(self):
        document = to_dict(menu(line("Salt", recipes=["Salt"])), name="m")
        assert document["shopping"][0]["recipes"] == ["Salt"]

    def test_zone_travels_with_the_row(self):
        document = to_dict(menu(line("Mælk", zone=KØL)), name="m")
        row = document["shopping"][0]
        assert row["zone"] == "køl"
        assert row["zone_order"] == 9


class TestRoundTrip:
    def test_survives_a_round_trip(self):
        original = menu(
            line("Æbler", zone=FRUGT, quantities={"stk": 6.0}, recipes=["Koldskål"]),
            line("Mælk", zone=KØL, quantities={"l": 1.5}, recipes=["Koldskål"]),
        )
        document = json.loads(json.dumps(to_dict(original, name="m")))
        restored = shopping_from_dict(document)

        assert [l.ingredient for l in restored.lines] == ["Æbler", "Mælk"]
        assert [l.quantities for l in restored.lines] == [{"stk": 6.0}, {"l": 1.5}]
        assert [l.zone for l in restored.lines] == [FRUGT, KØL]

    def test_accepts_a_bare_shopping_array(self):
        document = to_dict(menu(line("Æbler")), name="m")
        restored = shopping_from_dict(document["shopping"])
        assert [l.ingredient for l in restored.lines] == ["Æbler"]

    def test_rows_come_back_in_walking_order(self):
        document = to_dict(menu(line("Mælk", zone=KØL), line("Æbler", zone=FRUGT)), name="m")
        # Shuffle the wire order; the reader must re-sort by zone then name.
        document["shopping"].reverse()
        restored = shopping_from_dict(document)
        assert [l.ingredient for l in restored.lines] == ["Æbler", "Mælk"]


class TestZoneResolution:
    def test_local_zone_wins_over_the_exported_one(self):
        """An imported run should walk this kitchen, not the exporting one."""
        document = to_dict(menu(line("Mælk", zone=Zone("andet", 50))), name="m")
        restored = shopping_from_dict(document, zone_config=_StubZones({"mælk": KØL}))
        assert restored.lines[0].zone == KØL

    def test_exported_zone_is_kept_when_this_kitchen_does_not_know_it(self):
        """Better than dropping a known-good zone into 'unknown'."""
        document = to_dict(menu(line("Yuzu", zone=FRUGT)), name="m")
        restored = shopping_from_dict(document, zone_config=_StubZones({}))
        assert restored.lines[0].zone == FRUGT

    def test_unknown_on_both_sides_stays_unknown(self):
        document = to_dict(menu(line("Yuzu", zone=UNKNOWN)), name="m")
        restored = shopping_from_dict(document, zone_config=_StubZones({}))
        assert restored.lines[0].is_unmapped


class TestTolerance:
    def test_rejects_a_schema_it_does_not_speak(self):
        with pytest.raises(UnsupportedSchema):
            shopping_from_dict({"schema": SCHEMA_VERSION + 1, "shopping": []})

    def test_rows_without_an_ingredient_are_dropped(self):
        restored = shopping_from_dict({"shopping": [{"ingredient": "  "}, "nonsense"]})
        assert restored.lines == []

    def test_an_unreadable_amount_keeps_the_unit(self):
        """Losing the row would lose an instruction to the shopper."""
        restored = shopping_from_dict(
            {"shopping": [{"ingredient": "Persille", "quantities": {"bundt": "en del"}}]}
        )
        assert restored.lines[0].quantities == {"bundt": 0.0}

    def test_a_row_with_no_recipes_records_itself(self):
        restored = shopping_from_dict({"shopping": [{"ingredient": "Salt"}]})
        assert restored.lines[0].recipes == ["Salt"]

    def test_missing_shopping_key_is_empty_not_an_error(self):
        assert shopping_from_dict({"schema": SCHEMA_VERSION}).lines == []
