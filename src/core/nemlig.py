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
import re
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


# --------------------------------------------------------------------------
# does the chosen product actually cover what the week needs?
# --------------------------------------------------------------------------

#: unit -> (family, multiplier into the family's base unit)
#:
#: Families never convert into each other. "2 pakker" and "150 g" are both
#: real answers to how much pålæg is wanted, but nothing here knows how many
#: grams a pakke is, and guessing is how you buy a third of what you needed.
_UNITS: dict[str, tuple[str, float]] = {
    "ml": ("volume", 1.0),
    "cl": ("volume", 10.0),
    "dl": ("volume", 100.0),
    "l": ("volume", 1000.0),
    "liter": ("volume", 1000.0),
    "g": ("mass", 1.0),
    "gram": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "stk": ("count", 1.0),
    "styk": ("count", 1.0),
    "bundt": ("count", 1.0),
    "fed": ("count", 1.0),
    "pakke": ("pack", 1.0),
    "pakker": ("pack", 1.0),
    "pk": ("pack", 1.0),
    "pose": ("pack", 1.0),
    "poser": ("pack", 1.0),
    "dåse": ("pack", 1.0),
    "dåser": ("pack", 1.0),
    "slags": ("kinds", 1.0),
    "sorter": ("kinds", 1.0),
}

#: How far short a purchase may fall before it is worth mentioning.
#:
#: Shelf sizes rarely match a recipe exactly -- 140 g of cheddar against a
#: 150 g need is the shop's fault, not a mistake, and warning about it would
#: train people to ignore the warnings. A fifth short is a different thing.
COVERAGE_TOLERANCE = 0.10

_QUANTITY_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*([a-zA-ZæøåÆØÅ]+\.?)",
)


def _unit(token: str) -> tuple[str, float] | None:
    return _UNITS.get(token.strip().rstrip(".").casefold())


def parse_quantity(text: str) -> dict[str, float]:
    """Sum a free-text amount into ``{family: total_in_base_unit}``.

    ``"5 dl + 2 l"`` becomes ``{"volume": 2500.0}``. Unrecognised units are
    dropped rather than guessed at, so an unparseable need reads as "nothing
    known" and produces no warning, instead of a confident wrong one.

    Accepts both the decimal comma nemlig writes and the decimal point
    :func:`format_need` produces.
    """
    totals: dict[str, float] = {}
    for amount, token in _QUANTITY_RE.findall(text or ""):
        unit = _unit(token)
        if unit is None:
            continue
        family, multiplier = unit
        totals[family] = totals.get(family, 0.0) + float(amount.replace(",", ".")) * multiplier
    return totals


def parse_pack(pack: str) -> tuple[str, float] | None:
    """Read one product's pack size as ``(family, amount_in_base_unit)``.

    Pack strings carry provenance after a slash -- ``"0,50 l / Arla Karolines
    Køkken"``, ``"200 g / Danmark / Tvedemose  ★ købt før"`` -- and only the
    first field is a size, so the rest is discarded before parsing. Returns
    ``None`` when there is no size to read.
    """
    head = (pack or "").split("/")[0]
    for amount, token in _QUANTITY_RE.findall(head):
        unit = _unit(token)
        if unit is not None:
            family, multiplier = unit
            return family, float(amount.replace(",", ".")) * multiplier
    return None


def check_coverage(need: str, pack: str, qty: int) -> dict | None:
    """Warn when the chosen product does not add up to what the week needs.

    The app has always known both halves of this and never compared them. Six
    rows in one real order were short -- a squash, half a litre of milk, a pack
    of pålæg, 50 g of mushrooms, and a second kind of fruit that never got
    bought at all -- and every one of them was visible on screen at the time.

    Returns ``None`` when the purchase covers the need, when the need is
    unparseable, or when the two cannot honestly be compared. Warning only on
    what can be shown is the point: a false alarm costs more than a silent pass,
    because it is the thing that makes people stop reading warnings.
    """
    qty = max(1, int(qty or 1))
    needs = parse_quantity(need)
    if not needs:
        return None

    parsed_pack = parse_pack(pack)

    for family, required in needs.items():
        # "2 slags" is a request for variety, not volume: one product cannot
        # satisfy it however many are bought.
        if family == "kinds":
            if required > 1:
                return {
                    "kind": "kinds",
                    "need": need,
                    "required": required,
                    "bought": 1,
                    "message": (
                        f"{_number(required)} kinds wanted, but one product is "
                        f"chosen -- pick another row for the second kind"
                    ),
                }
            continue

        if parsed_pack is None:
            continue
        pack_family, pack_amount = parsed_pack

        if family == pack_family:
            bought = pack_amount * qty
        elif family == "pack" and pack_family in ("mass", "volume"):
            # The need counts packages ("2 pakker") while the product is sold by
            # weight. How many grams a pakke holds is unknowable here, but one
            # pakke is one of whatever is on the shelf, so the count still maps
            # directly onto how many to buy.
            bought = float(qty)
        else:
            # No honest comparison exists. This deliberately includes a count
            # against a weight -- "12 stk" cherrytomater against a 200 g box,
            # or "2 stk" kyllingebryst against a 280 g pack. Treating the count
            # as a pack count warns that two boxes of cherry tomatoes are ten
            # short, which is nonsense, and a warning that cries wolf is worse
            # than no warning: it is what teaches people to skip reading them.
            continue

        if bought >= required * (1 - COVERAGE_TOLERANCE):
            continue

        return {
            "kind": "short",
            "need": need,
            "required": required,
            "bought": bought,
            "family": family,
            "message": (
                f"needs {need}, but {qty} x {pack.split('/')[0].strip() or 'this'} "
                f"is {_shortfall(required, bought, family)} short"
            ),
        }

    return None


def _number(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"


_BASE_UNIT = {"volume": "ml", "mass": "g", "count": "stk", "pack": "pakker"}


def _shortfall(required: float, bought: float, family: str) -> str:
    missing = required - bought
    unit = _BASE_UNIT.get(family, "")
    if family == "volume" and missing >= 1000:
        return f"{_number(missing / 1000)} l"
    if family == "mass" and missing >= 1000:
        return f"{_number(missing / 1000)} kg"
    if family == "pack" and missing == 1:
        unit = "pakke"
    return f"{_number(missing)} {unit}".strip()


def find_collisions(choices: Sequence[Mapping]) -> list[dict]:
    """Rows that resolve to the same product, before anything is bought.

    :func:`merge_add_lines` already sums these so the basket is correct, but it
    does so silently and only at fill time. That is too late to ask the question
    that matters: *should* both rows be this product? ``fløde`` and
    ``piskefløde`` both defaulted to the same 0,5 l carton in one order, which
    merged to two cartons for a combined need of 0,35 l.
    """
    by_product: dict[str, list[Mapping]] = {}
    for choice in choices:
        if choice.get("action") not in BUYING:
            continue
        product_id = str(choice.get("product_id") or "")
        if product_id:
            by_product.setdefault(product_id, []).append(choice)

    collisions = []
    for product_id, rows in by_product.items():
        if len(rows) < 2:
            continue
        product = rows[0].get("product") or {}
        collisions.append(
            {
                "product_id": product_id,
                "product_name": product.get("name", ""),
                "pack": product.get("pack", ""),
                "ingredients": [row.get("ingredient", "") for row in rows],
                "combined_need": " + ".join(
                    row.get("need", "") for row in rows if row.get("need")
                ),
                "total_qty": sum(int(row.get("qty") or 1) for row in rows),
                "message": (
                    f"{len(rows)} rows both resolve to {product.get('name', product_id)} "
                    f"-- they will be merged into "
                    f"{sum(int(row.get('qty') or 1) for row in rows)}"
                ),
            }
        )
    return collisions


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
