"""Turn a menu into a structured shopping list.

This module is deliberately free of any rendering concern. ``aggregate_menu``
returns data; ``src.render`` turns data into text. That separation is what
makes check-off, zone labels and store integration possible -- previously the
only consumer of the aggregate was a markdown printer, and the structure was
discarded immediately after being printed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from src.core.recipes import load_recipe_data
from src.core.zones import UNKNOWN_ZONE, Zone, ZoneConfig

RecipeLoader = Callable[[str], dict[str, Any]]


@dataclass
class ShoppingLine:
    """One row of the shopping list: an ingredient and everything known about it."""

    ingredient: str
    zone: Zone
    #: unit -> summed amount, in first-seen order. Units are never converted,
    #: so "100 g" and "1 kg" remain separate buckets (see story 3.4).
    quantities: dict[str, float] = field(default_factory=dict)
    #: every recipe that contributed, in contribution order, duplicates kept
    recipes: list[str] = field(default_factory=list)

    @property
    def is_unmapped(self) -> bool:
        return self.zone.name == UNKNOWN_ZONE

    def contributing_recipes(self) -> list[str]:
        """Unique contributing recipes, self-reference dropped when redundant.

        An ingredient bought in its own right (a staple, say) records itself as
        its own source. That is only noise once there is a real recipe too.
        """
        unique = sorted(set(self.recipes))
        if len(unique) > 1:
            unique = [name for name in unique if name != self.ingredient]
        return unique


@dataclass
class MenuEntry:
    """A dish as it appears on the printed menu."""

    name: str
    placering: str
    multiplier: float
    silent: bool


@dataclass
class MenuSection:
    name: str
    silent: bool
    entries: list[MenuEntry] = field(default_factory=list)


@dataclass
class ShoppingList:
    lines: list[ShoppingLine] = field(default_factory=list)

    def by_zone(self) -> list[tuple[Zone, list[ShoppingLine]]]:
        """Group lines by zone, in walking order."""
        grouped: list[tuple[Zone, list[ShoppingLine]]] = []
        for line in self.lines:
            if grouped and grouped[-1][0].order == line.zone.order:
                grouped[-1][1].append(line)
            else:
                grouped.append((line.zone, [line]))
        return grouped

    def unmapped(self) -> list[ShoppingLine]:
        """Lines whose ingredient has no kitchen zone assigned yet."""
        return [line for line in self.lines if line.is_unmapped]


@dataclass
class AggregatedMenu:
    """The full result of processing a menu file."""

    sections: list[MenuSection] = field(default_factory=list)
    shopping: ShoppingList = field(default_factory=ShoppingList)


class _Accumulator:
    """Collects ingredient contributions keyed by (zone order, ingredient).

    The key and its sort order reproduce the historic behaviour exactly:
    lines are ordered by zone walking order, then by ingredient name.
    """

    def __init__(self, zone_config: ZoneConfig) -> None:
        self._zones = zone_config
        self._lines: dict[tuple[int, str], ShoppingLine] = {}

    def add(self, ingredient: str, amount: float, unit: str, recipe_name: str) -> None:
        zone = self._zones.zone_for(ingredient)
        key = (zone.order, ingredient)

        line = self._lines.get(key)
        if line is None:
            line = ShoppingLine(ingredient=ingredient, zone=zone)
            self._lines[key] = line

        line.quantities[unit] = line.quantities.get(unit, 0.0) + amount
        line.recipes.append(recipe_name)

    def build(self) -> ShoppingList:
        return ShoppingList(
            lines=[self._lines[key] for key in sorted(self._lines)]
        )


def _multiplier_for(amount: dict[str, Any], recipe: dict[str, Any]) -> float:
    """How many times over to buy this recipe's ingredients.

    ``unit: recipe`` means "this many batches". Anything else (typically
    ``plates``) is read as a serving count and divided by the recipe's yield.
    """
    if amount.get("unit") == "recipe":
        return amount["amount"]

    base_servings = float(recipe.get("antal") or 0)
    if base_servings <= 0:
        return 0
    return amount["amount"] / base_servings


def _add_recipe(
    identifier: str,
    amount: dict[str, Any],
    acc: _Accumulator,
    section: MenuSection,
    load_recipe: RecipeLoader,
    silent: bool,
) -> None:
    recipe = load_recipe(identifier)
    multiplier = _multiplier_for(amount, recipe)

    section.entries.append(
        MenuEntry(
            name=recipe["navn"],
            placering=recipe.get("placering", "") or "",
            multiplier=multiplier,
            silent=silent,
        )
    )

    for ingredient, entry in (recipe.get("ingredienser") or {}).items():
        scaled = entry["amount"] * multiplier
        if scaled > 0:
            acc.add(ingredient, scaled, entry["unit"], recipe["navn"])

    for ingredient, entry in (recipe.get("extras") or {}).items():
        try:
            _add_recipe(ingredient, entry, acc, section, load_recipe, silent)
        except FileNotFoundError:
            # Not a recipe after all -- treat it as a plain ingredient.
            if entry["amount"] > 0:
                acc.add(ingredient, entry["amount"], entry["unit"], recipe["navn"])


def aggregate_menu(
    menu: dict[str, Any],
    zone_config: ZoneConfig,
    load_recipe: RecipeLoader | None = None,
    silent_sections: Iterable[str] | None = None,
) -> AggregatedMenu:
    """Expand a menu into its dishes and a consolidated shopping list.

    ``silent_sections`` are included in the shopping list but omitted from the
    printed menu -- that is how weekly staples stay off the fridge sheet while
    still being bought.
    """
    loader = load_recipe or load_recipe_data

    silent_set = {s.lower() for s in (silent_sections or set())}
    silent_set.add("andet")

    acc = _Accumulator(zone_config)
    result = AggregatedMenu()

    for section_name, recipes in menu.items():
        silent = section_name.lower() in silent_set
        section = MenuSection(name=section_name, silent=silent)
        result.sections.append(section)

        for recipe in recipes:
            if isinstance(recipe, str):
                recipe = {recipe: {"amount": 1, "unit": "recipe"}}

            (recipe_name,) = recipe.keys()
            amount = recipe[recipe_name]
            try:
                _add_recipe(recipe_name, amount, acc, section, loader, silent)
            except FileNotFoundError:
                if amount["amount"] > 0:
                    acc.add(
                        recipe_name, amount["amount"], amount["unit"], recipe_name
                    )

    result.shopping = acc.build()
    return result
