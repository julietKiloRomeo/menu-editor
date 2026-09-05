"""Import a rendered menu markdown file as a tickable shopping run.

Normally a run is frozen from a menu YAML via ``POST /api/runs``. That path
needs the menu's recipes to be resolvable, which is not true for menus that
were produced elsewhere -- the weekly ``menu-<date>.md`` files land in
``~/Downloads`` already aggregated, and some of their dishes have no recipe
file in this repo at all.

This importer takes the *rendered* list instead. The markdown already contains
the finished aggregate (ingredient, summed quantities, contributing dishes), so
there is nothing to recompute. Zones are the one thing the markdown does not
carry -- its table headers are blank -- so they are looked up in the live zone
config rather than inferred from the table grouping. That keeps the imported
run consistent with runs frozen the normal way.

Usage::

    uv run python scripts/import_menu_markdown.py ~/Downloads/menu-2026-09-05.md
    uv run python scripts/import_menu_markdown.py <path> --dry-run
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.runs import latest_run, run_items, start_run
from src.core.shopping import ShoppingLine, ShoppingList
from src.core.zones import load_zone_config
from src.models import get_session

#: ``| ingredient | 300 g | Jambalaya + Lun pastasal |``
_ROW = re.compile(r"^\s*\|(?P<cells>.*)\|\s*$")
#: A quantity bucket: a number then an optional unit ("0.5 tsk", "2", "300 g").
_QUANTITY = re.compile(r"^(?P<amount>-?\d+(?:[.,]\d+)?)\s*(?P<unit>.*)$")


def _split_row(line: str) -> list[str] | None:
    """Cells of a markdown table row, or ``None`` if this is not one."""
    match = _ROW.match(line)
    if match is None:
        return None
    return [cell.strip() for cell in match.group("cells").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return all(not cell or set(cell) <= set("-: ") for cell in cells)


def parse_quantities(raw: str) -> dict[str, float]:
    """``"3 dl + 300 g"`` -> ``{"dl": 3.0, "g": 300.0}``.

    Units are never converted or merged, matching the aggregator: separate
    units stay separate buckets so "100 g" and "1 kg" remain distinguishable.
    """
    quantities: dict[str, float] = {}
    for chunk in raw.split("+"):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = _QUANTITY.match(chunk)
        if match is None:
            # Unparseable, but losing it silently would lose an instruction to
            # the shopper. Keep it as a unit with no amount.
            quantities.setdefault(chunk, 0.0)
            continue
        unit = " ".join(match.group("unit").split())
        amount = float(match.group("amount").replace(",", "."))
        quantities[unit] = quantities.get(unit, 0.0) + amount
    return quantities


def parse_recipes(raw: str) -> list[str]:
    """Contributing dishes from the third column.

    The renderer truncates this column to a fixed width, so entries arrive
    clipped ("Gnocchi somm") and the trailing "+" of an overflowing list is
    kept. Both are preserved verbatim: the column is a "why is this on my
    list?" hint, and inventing the missing characters would be worse.
    """
    return [part.strip() for part in raw.split("+") if part.strip()]


def parse_markdown(text: str) -> list[tuple[str, dict[str, float], list[str]]]:
    """Every shopping row in the document, in file order."""
    rows: list[tuple[str, dict[str, float], list[str]]] = []
    in_shopping = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # The document is "# Menu" then "# Shopping"; only the latter has
            # the tables we want.
            in_shopping = stripped.lstrip("#").strip().lower().startswith("shopping")
            continue
        if not in_shopping:
            continue

        cells = _split_row(line)
        if cells is None or _is_separator(cells):
            continue

        ingredient = cells[0]
        if not ingredient:
            continue

        quantities = parse_quantities(cells[1] if len(cells) > 1 else "")
        recipes = parse_recipes(cells[2] if len(cells) > 2 else "")
        rows.append((ingredient, quantities, recipes))

    return rows


def build_shopping_list(
    rows: list[tuple[str, dict[str, float], list[str]]],
) -> ShoppingList:
    """Turn parsed rows into a ShoppingList, zoned from the live config."""
    zone_config = load_zone_config()

    lines = [
        ShoppingLine(
            ingredient=ingredient,
            zone=zone_config.zone_for(ingredient),
            quantities=quantities,
            recipes=recipes or [ingredient],
        )
        for ingredient, quantities, recipes in rows
    ]

    # Walking order, matching _Accumulator.build().
    lines.sort(key=lambda line: (line.zone.order, line.ingredient.casefold()))
    return ShoppingList(lines=lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=pathlib.Path, help="rendered menu markdown")
    parser.add_argument(
        "--name",
        help="run name (defaults to the file stem, e.g. menu-2026-09-05)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report, without writing to the database",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="start another run even if this menu already has one",
    )
    args = parser.parse_args()

    text = args.path.read_text(encoding="utf-8")
    rows = parse_markdown(text)
    if not rows:
        print(f"No shopping rows found in {args.path}", file=sys.stderr)
        return 1

    menu_name = args.name or args.path.stem
    shopping = build_shopping_list(rows)

    print(f"{args.path.name}: {len(shopping.lines)} items")
    for zone, zone_lines in shopping.by_zone():
        print(f"  {zone.name} ({len(zone_lines)})")
        for line in zone_lines:
            amounts = " + ".join(
                f"{amount:g} {unit}".strip() for unit, amount in line.quantities.items()
            )
            print(f"    {line.ingredient:<28} {amounts}")

    unmapped = shopping.unmapped()
    if unmapped:
        print(f"\n{len(unmapped)} unzoned (they land in the 'unknown' zone):")
        for line in unmapped:
            print(f"    {line.ingredient}")

    if args.dry_run:
        print("\nDry run: nothing written.")
        return 0

    with get_session() as session:
        if not args.force and latest_run(menu_name, session) is not None:
            print(
                f"\nA run for {menu_name!r} already exists. "
                "Re-run with --force to start a second one.",
                file=sys.stderr,
            )
            return 1

        run = start_run(menu_name, shopping, session)
        items = run_items(run.id, session)
        stocked = sum(1 for item in items if item.likely_stocked)

    print(f"\nRun {run.id} started for {menu_name!r}: {len(items)} items")
    print(f"{stocked} flagged as usually stocked (flagged, not ticked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
