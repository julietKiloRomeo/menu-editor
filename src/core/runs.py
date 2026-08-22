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

from datetime import datetime, timezone

from sqlmodel import Session, select

from src.core.ingredients import normalise
from src.core.shopping import ShoppingList
from src.models import ShoppingRun, ShoppingRunItem, StockedItem, get_session


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

    Items already known to be in the kitchen start ticked rather than hidden:
    "usually" is not "always", and when the oil finally runs out you need to be
    able to untick it.
    """
    if stocked is None:
        stocked = load_stocked_names(session)

    run = ShoppingRun(menu_name=menu_name)
    session.add(run)
    # Flush rather than commit: the run and its items become visible together,
    # so a concurrent reader never sees an empty list.
    session.flush()

    now = datetime.now(timezone.utc)
    for position, line in enumerate(shopping.lines):
        pre_checked = normalise(line.ingredient) in stocked
        session.add(
            ShoppingRunItem(
                run_id=run.id,
                position=position,
                ingredient=line.ingredient,
                quantities=dict(line.quantities),
                recipes=line.contributing_recipes(),
                zone_name=line.zone.name,
                zone_order=line.zone.order,
                checked=pre_checked,
                checked_at=now if pre_checked else None,
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
