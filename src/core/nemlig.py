"""Turning a walked shopping run into a nemlig.com basket.

This is the second half of the weekly workflow. The first half happens on a
phone in the kitchen: :mod:`src.core.runs` freezes a menu into a tickable list
and you walk it, ticking what you already have. Whatever is left is what has to
be bought, and this module turns that remainder into basket lines.

**Why none of this talks to nemlig.** Search needs a bearer token *and* five
session/delivery parameters that only exist once the site itself has searched;
the basket endpoints authenticate on a large, rotating, ``HttpOnly`` cookie set.
Replicating that in Python means storing someone's grocery session on disk, and
it breaks the moment nemlig rotates anything. So the network calls stay in a
logged-in browser tab and this module handles everything either side of them:
what to search for, what the choices mean, and what the week taught us. Search
results come in as JSON and basket lines go out as JSON.

Two behaviours here are load-bearing, both learned by getting them wrong:

* :func:`merge_add_lines` sums quantities per product id. ``AddToBasket`` is
  called with ``AffectPartialQuantity: true``, which makes ``quantity``
  *absolute* -- retries are safe, but two list rows resolving to the same
  product will overwrite rather than accumulate. Un-merged duplicates silently
  under-buy.
* :func:`record_run` treats "we already have it" as the *only* route into the
  staples list. See the note on :data:`ACTIONS` for why that matters.
"""

from __future__ import annotations

import json
import pathlib
import shutil
from datetime import date as _date
from typing import Any, Iterable, Mapping, Sequence

#: Where the durable memory lives. Not in the database: it is edited by hand
#: between runs, diffed in review, and read by agents working from a checkout
#: without the app running.
DEFAULT_MAP_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "nemlig_product_map.json"
)

#: What a picker row can resolve to.
#:
#: The skill this replaces had a single ``skip`` button labelled "har vi / drop",
#: and its recorder inferred a durable cupboard fact from it: anything skipped
#: that was not brand new got appended to the staples list, permanently and with
#: no removal path. But one button was carrying at least four different
#: intentions -- "we have it", "not cooking that this week", "it was sold out",
#: "ask me later" -- and three of them are not statements about the cupboard.
#: Skipping a sold-out item taught the map that the kitchen always has it.
#:
#: So the intentions are separate here, and only ``have_it`` writes to staples.
ACTIONS = ("buy", "link", "have_it", "not_this_week", "unavailable", "undecided")

#: Actions that put something in the basket.
BUYING = ("buy", "link")

#: Actions that mean "do not buy, and here is why", mapped to whether the reason
#: is a durable fact about the kitchen or a fact about this week only.
DECLINED = {
    "have_it": "staple",
    "not_this_week": "transient",
    "unavailable": "unresolved",
    "undecided": "unresolved",
}


# --------------------------------------------------------------------------
# the product map
# --------------------------------------------------------------------------


def load_product_map(path: pathlib.Path | None = None) -> dict:
    """Read the product map, tolerating its absence.

    A missing file is a first run, not an error: the map is memory, and memory
    starts empty.
    """
    path = pathlib.Path(path or DEFAULT_MAP_PATH)
    if not path.exists():
        return empty_product_map()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    # Older maps predate one section or another; normalise on read so every
    # caller can assume the shape.
    payload.setdefault("mappings", {})
    payload.setdefault("no_default_yet", {})
    payload.setdefault("usually_in_the_kitchen", {}).setdefault("items", [])
    return payload


def empty_product_map() -> dict:
    return {
        "_comment": "Learned ingredient -> nemlig.com product defaults.",
        "_source_menu": "",
        "mappings": {},
        "no_default_yet": {},
        "usually_in_the_kitchen": {"items": []},
    }


def save_product_map(payload: Mapping, path: pathlib.Path | None = None) -> pathlib.Path:
    """Write the map, keeping one backup.

    The backup is taken before the write rather than after a successful one,
    because the failure worth protecting against is a half-written file, and by
    then the original is already gone.
    """
    path = pathlib.Path(path or DEFAULT_MAP_PATH)
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        shutil.copy(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return backup


# --------------------------------------------------------------------------
# shaping the list
# --------------------------------------------------------------------------


def format_need(quantities: Mapping[str, float]) -> str:
    """Render ``{"dl": 3, "g": 300}`` as ``"3 dl + 300 g"``.

    Units are never converted -- deliberately, upstream in
    :class:`~src.core.shopping.ShoppingLine` -- so they are joined rather than
    summed. Whole numbers lose the decimal point because "1 stk" reads as a
    count and "1.0 stk" reads as a measurement.
    """
    parts = []
    for unit, amount in quantities.items():
        rounded = round(float(amount), 2)
        number = int(rounded) if rounded == int(rounded) else rounded
        parts.append(f"{number} {unit}".strip())
    return " + ".join(parts)


def adapt_product(raw: Mapping) -> dict | None:
    """Normalise one search hit into the shape the picker uses.

    Accepts nemlig's own ``Products.Products[]`` objects as well as the already
    flattened shape, because search results arrive by copy-paste from whatever
    ran them and demanding one exact schema would just move the adapter into the
    browser where it cannot be tested.

    Returns ``None`` for anything not both deliverable and in stock: an
    undeliverable product in the picker is a choice that cannot be honoured.
    """
    if "Id" in raw or "Name" in raw:
        availability = raw.get("Availability") or {}
        if availability:
            deliverable = availability.get("IsDeliveryAvailable", True)
            in_stock = availability.get("IsAvailableInStock", True)
            if not (deliverable and in_stock):
                return None
        unit_price = ""
        if raw.get("UnitPriceCalc") is not None:
            unit_price = f"{raw['UnitPriceCalc']} {raw.get('UnitPriceLabel', '')}".strip()
        return {
            "product_id": str(raw.get("Id", "")),
            "name": raw.get("Name", ""),
            "pack": raw.get("Description", ""),
            "price": raw.get("Price"),
            "image": raw.get("PrimaryImage", ""),
            "unit_price": unit_price,
            "fav": bool(raw.get("Favorite")),
        }

    if not raw.get("product_id"):
        return None
    return {
        "product_id": str(raw["product_id"]),
        "name": raw.get("name", ""),
        "pack": raw.get("pack", ""),
        "price": raw.get("price"),
        "image": raw.get("image", ""),
        "unit_price": raw.get("unit_price", ""),
        "fav": bool(raw.get("fav")),
    }


def adapt_search_results(payload: Mapping[str, Sequence[Mapping]]) -> dict[str, list[dict]]:
    """Normalise ``{query: [hit, ...]}``, dropping unbuyable hits."""
    out: dict[str, list[dict]] = {}
    for query, hits in payload.items():
        adapted = [adapt_product(hit) for hit in hits or []]
        out[query] = [hit for hit in adapted if hit]
    return out


def plan_item(
    ingredient: str,
    quantities: Mapping[str, float],
    recipes: Sequence[str],
    zone: str,
    product_map: Mapping,
) -> dict:
    """Decide what to search for and what to default to, for one row."""
    mappings = product_map.get("mappings", {})
    stocked = set(product_map.get("usually_in_the_kitchen", {}).get("items", []))
    entry = mappings.get(ingredient)

    if entry:
        status = "mapped"
    elif ingredient in stocked:
        status = "stocked"
    else:
        status = "new"

    # A stored query beats the ingredient name: recipe Danish and shelf Danish
    # differ, and the map is where that difference is remembered. `query: null`
    # means search cannot reach the product at all, so there is nothing to run.
    if entry and "query" in entry:
        query = entry["query"]
    else:
        query = ingredient

    unresolved = product_map.get("no_default_yet", {}).get(ingredient)

    return {
        "ingredient": ingredient,
        "need": format_need(quantities),
        "recipes": list(recipes),
        "zone": zone,
        "status": status,
        "query": query,
        "qty": (entry.get("last_qty") or 1) if entry else 1,
        "previous_id": entry.get("product_id") if entry else None,
        "warning": unresolved.get("reason", "") if unresolved else "",
    }


def queries_for(items: Iterable[Mapping]) -> list[str]:
    """The distinct searches to run, in first-seen order.

    ``None`` queries are omitted rather than searched: they mark products
    nemlig's own search cannot reach, where the answer is a pasted link.
    """
    seen: dict[str, None] = {}
    for item in items:
        query = item.get("query")
        if query:
            seen.setdefault(query, None)
    return list(seen)


def rank_candidates(
    candidates: Sequence[Mapping],
    previous_id: str | None,
    product_map: Mapping | None = None,
) -> list[dict]:
    """Order the shelf so the likely answer is first.

    Last week's product leads, because the strongest signal about what someone
    wants is what they chose the last time they were asked. Then favourites,
    which are nemlig's record of everything ever bought and so know more than a
    local map does. Everything else keeps nemlig's own relevance order.
    """
    ranked = [dict(candidate) for candidate in candidates]
    head: list[dict] = []

    if previous_id:
        found = next((c for c in ranked if c["product_id"] == previous_id), None)
        if found:
            ranked.remove(found)
        elif product_map:
            # The product is in the map but not in this week's results -- sold
            # out, renamed, or unsearchable. Reconstruct it from memory so the
            # row still offers last week's answer instead of looking new.
            source = next(
                (
                    entry
                    for entry in product_map.get("mappings", {}).values()
                    if entry.get("product_id") == previous_id
                ),
                None,
            )
            if source:
                found = {
                    "product_id": previous_id,
                    "name": source.get("name", ""),
                    "pack": source.get("pack", ""),
                    "price": source.get("price"),
                    "image": source.get("image", ""),
                    "unit_price": "",
                    "fav": True,
                    "from_memory": True,
                }
        if found:
            found["previous"] = True
            head = [found]

    rest = [c for c in ranked if not c.get("previous")]
    rest.sort(key=lambda c: not c.get("fav"))
    for candidate in head + rest:
        candidate.setdefault("previous", False)
        candidate.setdefault("from_memory", False)
    return head + rest


# --------------------------------------------------------------------------
# the basket
# --------------------------------------------------------------------------


def merge_add_lines(choices: Sequence[Mapping]) -> dict:
    """Turn resolved choices into basket lines, summed per product.

    The summing is the entire point. ``AffectPartialQuantity: true`` makes the
    posted quantity absolute, so adding the same product from two rows as "1"
    and "1" leaves one pack in the basket, not two. That failure is silent until
    delivery day.

    Returns the lines plus everything worth a second look before committing:
    which rows were merged, and which are not yet answerable.
    """
    lines: dict[str, dict] = {}
    merged: list[dict] = []
    unresolved: list[dict] = []
    declined = 0

    for choice in choices:
        action = choice.get("action")
        name = choice.get("ingredient", "")

        if not action:
            unresolved.append({"ingredient": name, "reason": "no decision yet"})
            continue
        if action in DECLINED:
            declined += 1
            continue

        product = choice.get("product") or {}
        product_id = choice.get("product_id")
        if not product_id:
            unresolved.append({"ingredient": name, "reason": "no product chosen"})
            continue
        if not product.get("name"):
            # A pasted link yields an id but no product details, and details are
            # what make the basket reviewable before it is committed.
            unresolved.append(
                {
                    "ingredient": name,
                    "reason": f"link not resolved yet ({choice.get('url', '')})".strip(),
                }
            )
            continue

        quantity = int(choice.get("qty") or 1)
        if product_id in lines:
            line = lines[product_id]
            line["qty"] += quantity
            line["covers"].append(name)
            if line not in merged:
                merged.append(line)
        else:
            lines[product_id] = {
                "product_id": product_id,
                "product_name": product.get("name", ""),
                "pack": product.get("pack", ""),
                "price": product.get("price") or 0,
                "qty": quantity,
                "covers": [name],
                "zone": choice.get("zone", ""),
            }

    return {
        "lines": list(lines.values()),
        "merged": merged,
        "unresolved": unresolved,
        "declined": declined,
    }


def reconcile_basket(add_lines: Sequence[Mapping], basket: Mapping) -> dict:
    """Compare what we asked for against what the basket actually holds.

    A ``200`` from ``AddToBasket`` is not proof of purchase. A sold-out product
    is accepted, returns success, and lands as a line with ``Quantity: 0``;
    nothing in the response says so. Two items vanished this way on an earlier
    run and were noticed at delivery.
    """
    actual = {}
    for line in basket.get("Lines") or []:
        product_id = str(line.get("ProductId") or line.get("Id") or "")
        if product_id:
            actual[product_id] = line

    sold_out, missing, mismatched = [], [], []
    for line in add_lines:
        product_id = str(line["product_id"])
        found = actual.get(product_id)
        if found is None:
            missing.append(line)
            continue
        quantity = found.get("Quantity") or 0
        if not quantity:
            sold_out.append({**line, "basket_name": found.get("Name", "")})
        elif quantity != line["qty"]:
            mismatched.append({**line, "basket_qty": quantity})

    return {
        "sold_out": sold_out,
        "missing": missing,
        "mismatched": mismatched,
        "ok": not (sold_out or missing or mismatched),
        "total": basket.get("TotalProductsPrice"),
        "product_count": basket.get("NumberOfProducts"),
    }


# --------------------------------------------------------------------------
# what the week taught us
# --------------------------------------------------------------------------


def record_run(
    product_map: Mapping,
    choices: Sequence[Mapping],
    add_lines: Sequence[Mapping],
    *,
    replaced: Mapping[str, Mapping] | None = None,
    source: str = "",
    on_date: str | _date | None = None,
) -> dict:
    """Fold a finished run back into the product map.

    This is the step that makes next week cheaper than this week, so it runs
    even when the basket already looks finished.

    ``replaced`` is ``{ingredient: {product_id, name, pack, price, reason}}`` for
    items that were out of stock and got a substitute. Recording the
    substitution *and its reason* is what stops the dead product being re-picked
    next week; without the reason, a future reader only sees an unexplained
    change and is liable to revert it.

    Returns the updated map and a summary. The caller decides whether to persist
    it, so a dry run is possible.
    """
    payload = json.loads(json.dumps(product_map))  # deep copy; never edit in place
    mappings = payload.setdefault("mappings", {})
    unresolved = payload.setdefault("no_default_yet", {})
    stocked = payload.setdefault("usually_in_the_kitchen", {}).setdefault("items", [])
    replaced = replaced or {}

    by_product = {str(line["product_id"]): line for line in add_lines}

    added, updated, learned_staples, cleared = 0, 0, [], []

    for choice in choices:
        name = choice.get("ingredient", "")
        action = choice.get("action")
        note = (choice.get("note") or "").strip()

        if action in DECLINED:
            kind = DECLINED[action]
            if kind == "staple":
                # The one durable claim about the kitchen, and the only thing
                # allowed to write here.
                if name not in stocked:
                    stocked.append(name)
                    learned_staples.append(name)
            elif kind == "unresolved":
                reason = note or (
                    "out of stock" if action == "unavailable" else "not decided yet"
                )
                unresolved[name] = {"reason": reason}
            # "not this week" is a fact about this week. It teaches nothing.
            continue

        if action not in BUYING:
            continue

        line = by_product.get(str(choice.get("product_id") or ""))
        if not line:
            continue

        entry = dict(mappings.get(name) or {})
        existed = name in mappings
        entry.update(
            product_id=line["product_id"],
            name=line["product_name"],
            pack=line["pack"],
            price=line["price"],
            # The line quantity may cover several rows; this row's own default
            # is what it asked for, not the merged total.
            last_qty=int(choice.get("qty") or 1),
        )

        if name in replaced:
            substitute = replaced[name]
            entry.update(
                product_id=substitute["product_id"],
                name=substitute.get("name", ""),
                pack=substitute.get("pack", ""),
                price=substitute.get("price"),
            )
            if substitute.get("reason"):
                entry["note"] = substitute["reason"]
        if note:
            entry["note"] = note
        entry.setdefault("query", name)

        mappings[name] = entry
        added += not existed
        updated += existed

        # Buying it resolves it. Left alone, no_default_yet only ever grew, so
        # items stayed listed as open questions years after being answered.
        if name in unresolved:
            del unresolved[name]
            cleared.append(name)

    payload["usually_in_the_kitchen"]["items"] = sorted(set(stocked))

    if source:
        payload["_source_menu"] = source
    if on_date:
        stamp = on_date.isoformat() if hasattr(on_date, "isoformat") else str(on_date)
        payload["_comment"] = (
            "Learned ingredient -> nemlig.com product defaults. "
            f"Updated {stamp}" + (f" from {source}." if source else ".")
        )

    return {
        "map": payload,
        "added": added,
        "updated": updated,
        "mappings": len(mappings),
        "learned_staples": learned_staples,
        "cleared_unresolved": cleared,
        "still_unresolved": sorted(unresolved),
        "without_product_id": sorted(
            key for key, value in mappings.items() if not value.get("product_id")
        ),
    }


def summarise_map(product_map: Mapping) -> dict[str, Any]:
    """Counts for the desktop header, so the memory is visible not implicit."""
    return {
        "mappings": len(product_map.get("mappings", {})),
        "stocked": len(product_map.get("usually_in_the_kitchen", {}).get("items", [])),
        "unresolved": len(product_map.get("no_default_yet", {})),
        "source": product_map.get("_source_menu", ""),
    }
