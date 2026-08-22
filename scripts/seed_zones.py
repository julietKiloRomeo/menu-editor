#!/usr/bin/env python
"""Seed the kitchen zones and ingredient assignments.

    uv run python scripts/seed_zones.py --dry-run
    uv run python scripts/seed_zones.py
    uv run python scripts/seed_zones.py --force   # update an existing config

By default this refuses to touch a database that already has ingredient
assignments, so it is safe to run against a live installation.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.zones import (  # noqa: E402
    DEFAULT_ZONES_PATH,
    load_default_zones,
    load_zone_config,
    seed_zones,
)
from src.models import init_db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument(
        "--force",
        action="store_true",
        help="seed even when assignments already exist (upserts, never deletes)",
    )
    ap.add_argument("--path", type=pathlib.Path, default=DEFAULT_ZONES_PATH)
    args = ap.parse_args()

    defaults = load_default_zones(args.path)
    print(
        f"source: {args.path.relative_to(ROOT) if args.path.is_relative_to(ROOT) else args.path}"
    )
    print(
        f"  {len(defaults.zones)} zones, {len(defaults.assignments)} ingredient assignments"
    )

    init_db()

    try:
        current = load_zone_config()
        print(
            f"database: {len(current.zones)} zones, {len(current.assignments)} assignments"
        )
    except LookupError:
        print("database: no zones configured yet")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    result = seed_zones(args.path, only_if_empty=not args.force)

    if result.skipped:
        print(f"\nskipped: {result.reason}")
        print("re-run with --force to update an existing configuration")
        return 0

    print(
        f"\nzones:       +{result.zones_added} added, {result.zones_updated} reordered"
        f"\nassignments: +{result.assignments_added} added, {result.assignments_updated} moved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
