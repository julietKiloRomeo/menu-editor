"""Import an exported menu as a tickable shopping run.

Normally a run is frozen from a menu YAML via ``POST /api/runs``. That path
needs the menu's recipes to be resolvable, which is not true for menus planned
on another instance -- some of their dishes have no recipe file here at all.

So the menu crosses as an export: the finished aggregate as data, written by
``POST /api/menu/generate`` and saved from the app's "Download .json" button.
There is nothing to recompute, and nothing to recover from a layout.

Zones are resolved against *this* kitchen's config where it knows the
ingredient, so an imported run walks in the same order as one frozen the
normal way. The exported zone is kept only for ingredients this kitchen has
never seen.

Usage::

    uv run python scripts/import_menu.py ~/Downloads/menu-2026-09-19.json
    uv run python scripts/import_menu.py <path> --dry-run
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.runs import latest_run, run_items, start_run
from src.core.zones import load_zone_config
from src.models import get_session
from src.render.export import UnsupportedSchema, shopping_from_dict


def load_export(path: pathlib.Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}")
    if not isinstance(document, dict):
        raise SystemExit(f"{path} is not a menu export (expected an object)")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=pathlib.Path, help="exported menu JSON")
    parser.add_argument(
        "--name",
        help="run name (defaults to the export's name, else the file stem)",
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

    if not args.path.exists():
        print(f"No such file: {args.path}", file=sys.stderr)
        return 1

    document = load_export(args.path)
    try:
        shopping = shopping_from_dict(document, zone_config=load_zone_config())
    except UnsupportedSchema as exc:
        print(f"{args.path}: {exc}", file=sys.stderr)
        return 1

    if not shopping.lines:
        print(f"No shopping rows found in {args.path}", file=sys.stderr)
        return 1

    menu_name = args.name or document.get("name") or args.path.stem

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
