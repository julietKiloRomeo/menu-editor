#!/usr/bin/env python3
"""Say what the newest kitchen walk is, and what is left of it.

Read-only. "I just walked this week's list, where is it?" used to mean hunting
for a ``shopping-<N>.pdf`` in ``~/Downloads`` that no longer gets produced, then
copying valhalla's WAL-mode database by hand to look inside it. This answers the
same question with the one safe read the ordering command already knows how to
take.

    uv run python scripts/latest_run.py

Nothing is started and nothing is written back: the live database is left
exactly as it was.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.order_latest import (  # noqa: E402
    DEFAULT_HOST,
    DEFAULT_REMOTE_DB,
    clear_database,
    snapshot_live_database,
)


def _need(quantities: str | None) -> str:
    """``{"stk": 2.0}`` as ``2 stk``, because a bare ingredient name hides the size."""
    try:
        wanted = json.loads(quantities or "{}")
    except ValueError:
        return ""
    parts = []
    for unit, amount in wanted.items():
        number = int(amount) if float(amount).is_integer() else amount
        parts.append(f"{number} {unit}")
    return ", ".join(parts)


def summarise(database: pathlib.Path) -> str:
    """The whole answer as text, so it can be tested without a live kitchen."""
    connection = sqlite3.connect(database, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute(
            "select id, menu_name, created_at from shoppingrun "
            "order by created_at desc, id desc limit 1"
        ).fetchone()
        if run is None:
            return "No kitchen run has ever been started."

        items = connection.execute(
            "select ingredient, quantities, zone_name, zone_order, checked "
            "from shoppingrunitem where run_id=? order by zone_order, position",
            (run["id"],),
        ).fetchall()

        order = connection.execute(
            "select id, created_at, recorded_at from nemligorder "
            "where run_id=? order by id desc limit 1",
            (run["id"],),
        ).fetchone()
    finally:
        connection.close()

    ticked = sum(1 for item in items if item["checked"])
    lines = [
        f"Newest run: #{run['id']} {run['menu_name']}  (started {run['created_at']})",
        f"Walk: {ticked} of {len(items)} ticked"
        + ("  (nothing walked yet)" if ticked == 0 else ""),
    ]

    if order is None:
        lines.append("Order: none started")
    elif order["recorded_at"]:
        lines.append(f"Order: #{order['id']} recorded {order['recorded_at']}")
    else:
        lines.append(f"Order: #{order['id']} in progress since {order['created_at']}")

    leftover: dict[str, list[sqlite3.Row]] = {}
    for item in items:
        if not item["checked"]:
            leftover.setdefault(item["zone_name"], []).append(item)

    if leftover:
        lines.append(f"Left to order: {sum(len(rows) for rows in leftover.values())}")
        for zone, rows in leftover.items():
            wanted = ", ".join(
                f"{row['ingredient']} ({_need(row['quantities'])})"
                if _need(row["quantities"])
                else row["ingredient"]
                for row in rows
            )
            lines.append(f"  {zone} ({len(rows)}): {wanted}")
    else:
        lines.append("Left to order: nothing -- the walk ticked everything off")

    return "\n".join(lines)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--remote-db", default=DEFAULT_REMOTE_DB)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    snapshot = pathlib.Path("/tmp/opencode/menu-editor/latest-run.db")
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    clear_database(snapshot)
    try:
        snapshot_live_database(args.host, args.remote_db, snapshot)
        print(summarise(snapshot))
    finally:
        clear_database(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
