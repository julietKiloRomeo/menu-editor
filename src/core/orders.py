"""Persisting the nemlig picker, so half an hour of judgement survives a reload.

:mod:`src.core.nemlig` holds the pure transforms. This module is the part that
touches the database: it turns a walked :class:`~src.models.ShoppingRun` into a
:class:`~src.models.NemligOrder` and keeps every decision as it is made.

Saving each choice as it happens, rather than at a submit, is the whole design.
Choosing forty products takes long enough to be interrupted, and losing that
work is far worse than losing the basket -- the basket can be refilled in a
minute, the decisions cannot. It also means the list is readable while it is
being filled in, so progress is visible without anyone pressing anything.

Deliberately free of Flask, like :mod:`src.core.runs`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

from sqlmodel import Session, select

from src.core.nemlig import ACTIONS, plan_item, queries_for, rank_candidates
from src.models import NemligOrder, NemligOrderItem, ShoppingRun, ShoppingRunItem


def start_order(
    run_id: int,
    product_map: Mapping,
    session: Session,
    *,
    source: str = "",
    include_checked: bool = False,
) -> NemligOrder | None:
    """Open an order for everything the kitchen walk did not tick off.

    Ticked items are excluded because that is what ticking meant: the walk was
    the decision about what is already in the house, and asking again on the
    desktop would either waste the walk or quietly overrule it.

    ``include_checked`` exists for the case where the walk was done carelessly
    or belongs to someone else, and the whole list needs revisiting.
    """
    run = session.get(ShoppingRun, run_id)
    if run is None:
        return None

    rows = session.exec(
        select(ShoppingRunItem)
        .where(ShoppingRunItem.run_id == run_id)
        .order_by(ShoppingRunItem.zone_order, ShoppingRunItem.position)
    ).all()
    if not include_checked:
        rows = [row for row in rows if not row.checked]

    order = NemligOrder(run_id=run_id, source=source or run.menu_name)
    session.add(order)
    session.flush()  # so the items can reference it, and both land together

    for position, row in enumerate(rows):
        plan = plan_item(
            row.ingredient, row.quantities or {}, row.recipes or [], row.zone_name, product_map
        )
        session.add(
            NemligOrderItem(
                order_id=order.id,
                position=position,
                ingredient=plan["ingredient"],
                need=plan["need"],
                recipes=plan["recipes"],
                zone_name=plan["zone"],
                status=plan["status"],
                query=plan["query"] or "",
                qty=plan["qty"],
                warning=plan["warning"],
            )
        )

    session.commit()
    session.refresh(order)
    return order


def order_items(order_id: int, session: Session) -> list[NemligOrderItem]:
    """Rows in walked order, matching the list the user has beside them."""
    return session.exec(
        select(NemligOrderItem)
        .where(NemligOrderItem.order_id == order_id)
        .order_by(NemligOrderItem.position)
    ).all()


def recent_orders(session: Session, limit: int = 25) -> list[NemligOrder]:
    return session.exec(
        select(NemligOrder)
        .order_by(NemligOrder.created_at.desc(), NemligOrder.id.desc())
        .limit(limit)
    ).all()


def pending_queries(order_id: int, session: Session) -> list[str]:
    """Searches still worth running for this order.

    Rows already answered are left out: re-searching them would churn the
    candidate lists under decisions that have already been made.
    """
    items = [
        {"query": item.query}
        for item in order_items(order_id, session)
        if not item.action
    ]
    return queries_for(items)


def attach_search_results(
    order_id: int,
    results: Mapping[str, Sequence[Mapping]],
    product_map: Mapping,
    session: Session,
) -> int:
    """Fill in candidate products from a batch of search results.

    Only undecided rows are touched. Someone who has already picked a product
    should not have it swapped out because a later search returned a different
    order.
    """
    mappings = product_map.get("mappings", {})
    touched = 0

    for item in order_items(order_id, session):
        if item.action:
            continue
        hits = results.get(item.query)
        if hits is None:
            continue
        previous_id = (mappings.get(item.ingredient) or {}).get("product_id")
        item.candidates = rank_candidates(hits, previous_id, product_map)
        session.add(item)
        touched += 1

    session.commit()
    return touched


def set_choice(
    item_id: int,
    session: Session,
    *,
    action: str | None = ...,
    product_id: str | None = ...,
    product: dict | None = ...,
    qty: int | None = ...,
    note: str | None = ...,
    url: str | None = ...,
) -> NemligOrderItem | None:
    """Record one decision.

    Every field is optional and ``...`` means "not supplied", so a note can be
    edited without disturbing a chosen product, and vice versa. ``None`` is a
    real value here -- it is how a decision is taken back.
    """
    item = session.get(NemligOrderItem, item_id)
    if item is None:
        return None

    if action is not ...:
        if action is not None and action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        item.action = action
        # Declining something must not leave a product attached to it, or the
        # basket builder will happily buy what was just refused.
        if action is not None and action not in ("buy", "link"):
            item.product_id = None
            item.product = None

    if product_id is not ...:
        item.product_id = product_id
    if product is not ...:
        item.product = product
    if qty is not ...:
        item.qty = max(1, int(qty or 1))
    if note is not ...:
        item.note = note or ""
    if url is not ...:
        item.url = url or ""

    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def mark_recorded(order_id: int, session: Session) -> NemligOrder | None:
    order = session.get(NemligOrder, order_id)
    if order is None:
        return None
    order.recorded_at = datetime.now(timezone.utc)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def progress(items: Sequence[NemligOrderItem]) -> tuple[int, int]:
    """(decided, total) -- what the picker's progress bar shows."""
    return sum(1 for item in items if item.action), len(items)
