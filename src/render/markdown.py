"""Markdown rendering of a menu and its shopping list.

Column widths and truncation here are load-bearing: the output is printed and
taken to the shop, so it is locked by golden tests in
``tests/test_shopping_golden.py``.
"""

from __future__ import annotations

from typing import Callable

from src.core.shopping import AggregatedMenu, MenuEntry, ShoppingLine, ShoppingList

Printer = Callable[[str], None]

_RECIPE_NAME_WIDTH = 12
_RECIPE_COLUMN_WIDTH = 30

_NEW_TABLE = """

|          |          |       |
|----------|----------|------:|"""


def _format_amount(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def quantity_string(line: ShoppingLine) -> str:
    """e.g. ``6 fed    + 0.5 løg``  -- units are never converted or merged."""
    return " + ".join(
        f"{_format_amount(amount)} {unit:<6s}" for unit, amount in line.quantities.items()
    )


def recipes_string(line: ShoppingLine) -> str:
    names = [name[:_RECIPE_NAME_WIDTH] for name in line.contributing_recipes()]
    return " + ".join(names)


def render_menu_entry(entry: MenuEntry) -> str:
    if entry.multiplier == 1:
        amount_str = ""
    elif entry.multiplier:
        amount_str = f"(x{entry.multiplier:g})"
    else:
        amount_str = "(fryser)"
    return f" - {entry.name:35s}  {amount_str} : {entry.placering:25s}"


def render_shopping(shopping: ShoppingList, printer: Printer = print) -> None:
    """Emit the shopping table, starting a new table at each zone change."""
    previous_order = None
    for line in shopping.lines:
        if line.zone.order != previous_order:
            printer(_NEW_TABLE)
        previous_order = line.zone.order

        quantities = quantity_string(line)
        recipes = recipes_string(line)[:_RECIPE_COLUMN_WIDTH]
        printer(
            f"| {line.ingredient:40s} | {quantities:>10s} |  {recipes:30s}  | "
        )


def render(aggregated: AggregatedMenu, printer: Printer = print) -> None:
    """Render the full document: menu, then shopping list."""
    printer("# Menu")
    for section in aggregated.sections:
        if not section.silent:
            printer("## " + section.name)
        for entry in section.entries:
            if not entry.silent:
                printer(render_menu_entry(entry))

    printer("# Shopping")
    render_shopping(aggregated.shopping, printer=printer)
