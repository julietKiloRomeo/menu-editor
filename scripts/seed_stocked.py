#!/usr/bin/env python
"""Seed the list of ingredients the kitchen usually already has in.

    uv run python scripts/seed_stocked.py --dry-run
    uv run python scripts/seed_stocked.py
    uv run python scripts/seed_stocked.py --force   # add to an existing list

Items on this list are *flagged* on a shopping run -- never pre-ticked and
never hidden. By default this refuses to touch a database that already has
stocked items, so it is safe to run against a live installation.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.runs import (  # noqa: E402
    DEFAULT_STOCKED_PATH,
    load_default_stocked,
    load_stocked_names,
    seed_stocked,
)
from src.models import init_db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument(
        "--force",
        action="store_true",
        help="seed even when items already exist (adds, never deletes)",
    )
    ap.add_argument("--path", type=pathlib.Path, default=DEFAULT_STOCKED_PATH)
    args = ap.parse_args()

    defaults = load_default_stocked(args.path)
    source = (
        args.path.relative_to(ROOT) if args.path.is_relative_to(ROOT) else args.path
    )
    print(f"source: {source}")
    print(f"  {len(defaults)} ingredients")

    init_db()
    current = load_stocked_names()
    print(f"database: {len(current)} stocked ingredients")

    missing = [name for name in defaults if name not in current]
    if missing:
        print(f"  would add: {', '.join(missing)}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    result = seed_stocked(args.path, only_if_empty=not args.force)

    if result.skipped:
        print(f"\nskipped: {result.reason}")
        print("re-run with --force to add the missing ones")
        return 0

    print(f"\nstocked: +{result.added} added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
