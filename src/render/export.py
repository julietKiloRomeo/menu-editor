"""Serialise an aggregated menu to a structured document, and read it back.

The weekly menu crosses a machine boundary: it is planned and generated on
one instance (which has the recipes) and ordered from another (which may not).
That hand-off used to travel as *rendered markdown*, which the importer then
re-parsed -- reconstructing sums from a right-aligned column and dish names
from a column the renderer had already truncated to twelve characters.

This module is the hand-off instead. It carries the aggregate as data, so
nothing has to be recovered from a layout, and the printed menu is free to
change without breaking the import.

Both directions live here on purpose: ``to_dict`` and ``shopping_from_dict``
are one contract, and a round-trip test over the pair is what keeps them
honest.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable

from src.core.shopping import AggregatedMenu, ShoppingLine, ShoppingList
from src.core.zones import UNKNOWN_ORDER, UNKNOWN_ZONE, Zone, ZoneConfig

#: Bumped when the shape changes incompatibly. Readers reject what they do not
#: know rather than guessing at a field that moved.
SCHEMA_VERSION = 1


class UnsupportedSchema(ValueError):
    """Raised when a document's schema version is not one we can read."""


def _entry_to_dict(entry: Any) -> dict[str, Any]:
    return {
        "name": entry.name,
        "placering": entry.placering,
        "multiplier": entry.multiplier,
        "silent": entry.silent,
    }


def _line_to_dict(line: ShoppingLine) -> dict[str, Any]:
    return {
        "ingredient": line.ingredient,
        # Units are never converted, so this stays a mapping of separate
        # buckets rather than a single amount.
        "quantities": dict(line.quantities),
        # The full list, untruncated -- the markdown column was clipped to 12
        # characters and the importer had to keep the clipped text verbatim.
        "recipes": line.contributing_recipes(),
        "zone": line.zone.name,
        "zone_order": line.zone.order,
    }


def shopping_to_dict(shopping: ShoppingList) -> list[dict[str, Any]]:
    """The shopping list as plain data, in walking order."""
    return [_line_to_dict(line) for line in shopping.lines]


def to_dict(
    aggregated: AggregatedMenu,
    *,
    name: str,
    generated: datetime.date | None = None,
) -> dict[str, Any]:
    """The whole document: what to cook, and what to buy for it."""
    return {
        "schema": SCHEMA_VERSION,
        "name": name,
        "generated": (generated or datetime.date.today()).isoformat(),
        "menu": [
            {
                "section": section.name,
                "silent": section.silent,
                "entries": [_entry_to_dict(entry) for entry in section.entries],
            }
            for section in aggregated.sections
        ],
        "shopping": shopping_to_dict(aggregated.shopping),
    }


def _coerce_quantities(raw: Any) -> dict[str, float]:
    """Quantities as unit -> amount, skipping anything not a number.

    A unit that arrives with an unreadable amount is kept with a zero amount:
    dropping it would silently lose an instruction to the shopper.
    """
    if not isinstance(raw, dict):
        return {}
    quantities: dict[str, float] = {}
    for unit, amount in raw.items():
        try:
            quantities[str(unit)] = float(amount)
        except (TypeError, ValueError):
            quantities[str(unit)] = 0.0
    return quantities


def shopping_from_dict(
    payload: Any,
    *,
    zone_config: ZoneConfig | None = None,
) -> ShoppingList:
    """Rebuild a shopping list from an exported document.

    Accepts either the whole document or just its ``shopping`` array.

    Zones are resolved against ``zone_config`` when one is given, so an
    imported run is ordered by *this* kitchen rather than the exporting one.
    The exported zone is the fallback for ingredients this kitchen has never
    seen, which is strictly better than dropping them into 'unknown'.
    """
    if isinstance(payload, dict):
        schema = payload.get("schema")
        if schema is not None and schema != SCHEMA_VERSION:
            raise UnsupportedSchema(
                f"unsupported schema {schema!r}; this reader speaks {SCHEMA_VERSION}"
            )
        rows: Iterable[Any] = payload.get("shopping") or []
    else:
        rows = payload or []

    lines: list[ShoppingLine] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ingredient = str(row.get("ingredient") or "").strip()
        if not ingredient:
            continue

        exported = Zone(
            name=str(row.get("zone") or UNKNOWN_ZONE),
            order=int(row.get("zone_order") or UNKNOWN_ORDER),
        )
        zone = exported
        if zone_config is not None:
            local = zone_config.zone_for(ingredient)
            # Keep the exporter's zone only when we have nothing better.
            if local.name != UNKNOWN_ZONE or exported.name == UNKNOWN_ZONE:
                zone = local

        recipes = [
            str(name).strip()
            for name in (row.get("recipes") or [])
            if str(name).strip()
        ]
        lines.append(
            ShoppingLine(
                ingredient=ingredient,
                zone=zone,
                quantities=_coerce_quantities(row.get("quantities")),
                recipes=recipes or [ingredient],
            )
        )

    # Walking order, matching _Accumulator.build().
    lines.sort(key=lambda line: (line.zone.order, line.ingredient.casefold()))
    return ShoppingList(lines=lines)
