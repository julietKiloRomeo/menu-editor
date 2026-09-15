"""Markdown rendering of a menu.

Only the menu. The shopping list used to be rendered here too, as zone-grouped
tables, and that output had quietly become an interchange format: the weekly
importer re-parsed it to rebuild the aggregate. It now travels as data instead
(see ``src.render.export``), and the list itself is ticked off on a phone.

So what this produces is what goes on the fridge, and column widths are no
longer load-bearing for anything but the eye.
"""

from __future__ import annotations

from typing import Callable

from src.core.shopping import AggregatedMenu, MenuEntry

Printer = Callable[[str], None]


def render_menu_entry(entry: MenuEntry) -> str:
    if entry.multiplier == 1:
        amount_str = ""
    elif entry.multiplier:
        amount_str = f"(x{entry.multiplier:g})"
    else:
        amount_str = "(fryser)"
    return f" - {entry.name:35s}  {amount_str} : {entry.placering:25s}"


def render(aggregated: AggregatedMenu, printer: Printer = print) -> None:
    """Render the menu: what is being cooked, and where to find it."""
    printer("# Menu")
    for section in aggregated.sections:
        if not section.silent:
            printer("## " + section.name)
        for entry in section.entries:
            if not entry.silent:
                printer(render_menu_entry(entry))
