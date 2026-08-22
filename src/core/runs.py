"""Shopping runs: a list you can walk around and tick off.

A :class:`~src.models.ShoppingRun` is a snapshot of a menu's shopping list
taken at a moment in time. Snapshotting rather than recomputing is the whole
point: the list is walked physically, on a phone, in a kitchen and then a shop.
If it re-derived itself from the menu on every request, editing a recipe
mid-walk would reshuffle the rows under your thumb and could drop something you
had already ticked.

Deliberately free of Flask, so the MCP server can drive the same behaviour.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from src.core.ingredients import normalise
from src.core.shopping import ShoppingList
from src.models import ShoppingRun, ShoppingRunItem, StockedItem, get_session

#: JSON rather than YAML on purpose: the data directory also holds menus, and a
#: YAML file shaped ``items: [...]`` is indistinguishable from a menu section.
DEFAULT_STOCKED_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "usually_stocked.json"
)


@dataclass
class StockSeedResult:
    added: int = 0
    skipped: bool = False
    reason: str = ""


def load_default_stocked(path: pathlib.Path | None = None) -> list[str]:
    """The shipped list of things the kitchen usually has in."""
    target = path or DEFAULT_STOCKED_PATH
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    seen: dict[str, None] = {}
    for raw in payload.get("items", []):
        name = normalise(raw)
        if name:
            seen.setdefault(name, None)
    return list(seen)


def seed_stocked(
    path: pathlib.Path | None = None,
    *,
    only_if_empty: bool = True,
) -> StockSeedResult:
    """Load the default stock list into the database.

    Idempotent and additive: it never deletes, so an item removed by hand
    stays removed only until the next forced seed -- which is why the default
    is to skip entirely once the table has anything in it.
    """
    names = load_default_stocked(path)
    result = StockSeedResult()

    with get_session() as session:
        existing = session.exec(select(StockedItem)).all()
        if only_if_empty and existing:
            result.skipped = True
            result.reason = f"{len(existing)} stocked items already exist"
            return result

        known = {row.name for row in existing}
        for name in names:
            if name in known:
                continue
            session.add(StockedItem(name=name))
            known.add(name)
            result.added += 1
        session.commit()

    return result


def load_stocked_names(session: Session | None = None) -> set[str]:
    """Normalised names of everything the household usually already has."""
    if session is not None:
        rows = session.exec(select(StockedItem)).all()
        return {normalise(row.name) for row in rows}
    with get_session() as own:
        rows = own.exec(select(StockedItem)).all()
        return {normalise(row.name) for row in rows}


def start_run(
    menu_name: str,
    shopping: ShoppingList,
    session: Session,
    stocked: set[str] | None = None,
) -> ShoppingRun:
    """Freeze ``shopping`` into a tickable run.

    Everything starts unticked, including things the kitchen usually has in.
    Those are only *flagged* (``likely_stocked``): the walk exists to check
    reality, and a list that pre-ticks salt on your behalf is the list that
    sends you home without any.
    """
    if stocked is None:
        stocked = load_stocked_names(session)

    run = ShoppingRun(menu_name=menu_name)
    session.add(run)
    # Flush rather than commit: the run and its items become visible together,
    # so a concurrent reader never sees an empty list.
    session.flush()

    for position, line in enumerate(shopping.lines):
        session.add(
            ShoppingRunItem(
                run_id=run.id,
                position=position,
                ingredient=line.ingredient,
                quantities=dict(line.quantities),
                recipes=line.contributing_recipes(),
                zone_name=line.zone.name,
                zone_order=line.zone.order,
                likely_stocked=normalise(line.ingredient) in stocked,
            )
        )

    session.commit()
    session.refresh(run)
    return run


def run_items(run_id: int, session: Session) -> list[ShoppingRunItem]:
    """Items in walking order: zone order first, then original list position."""
    return list(
        session.exec(
            select(ShoppingRunItem)
            .where(ShoppingRunItem.run_id == run_id)
            .order_by(ShoppingRunItem.zone_order, ShoppingRunItem.position)
        ).all()
    )


def latest_run(menu_name: str, session: Session) -> ShoppingRun | None:
    """The most recent run for a menu, or ``None`` if it has never been walked."""
    return session.exec(
        select(ShoppingRun)
        .where(ShoppingRun.menu_name == menu_name)
        .order_by(ShoppingRun.created_at.desc(), ShoppingRun.id.desc())
    ).first()


def set_checked(
    item_id: int, checked: bool, session: Session
) -> ShoppingRunItem | None:
    """Tick or untick one item. Returns ``None`` if it does not exist."""
    item = session.get(ShoppingRunItem, item_id)
    if item is None:
        return None

    item.checked = checked
    item.checked_at = datetime.now(timezone.utc) if checked else None
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def progress(items: list[ShoppingRunItem]) -> tuple[int, int]:
    """``(checked, total)`` -- what the phone shows at the top of the screen."""
    return sum(1 for item in items if item.checked), len(items)
