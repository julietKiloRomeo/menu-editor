"""The second search an empty first one deserves.

nemlig's shelf and the recipe list disagree about words. The list asks for
``købepitabrød``, which the search returns nothing for; the shelf calls them
``pitabrød``. The row then has no candidates at all, which reads exactly like
"this cannot be bought" and sends someone off to find a product link by hand.

One retry in the row's own words is cheap and closes that gap. It is
deliberately not a guess at synonyms: the ingredient name is the only other
word we already have, and if that also returns nothing the honest answer is
still "no choices", so the picker can say so.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence


def retry_queries(
    items: Iterable[Mapping],
    results: Mapping[str, Sequence],
) -> dict[str, str]:
    """Queries that found nothing, mapped to the row's ingredient name.

    ``items`` are undecided rows as ``{"query": ..., "ingredient": ...}``;
    ``results`` is what each query returned. The returned mapping is keyed by
    the *original* query so the hits can be attached under the name the row
    already stores, rather than rewriting the row to match the search.

    A row whose ingredient is its own query has no second word to try, and is
    left out instead of being searched twice for the same string. First-seen
    order is kept, so two rows sharing a dead query retry once between them.
    """
    retry: dict[str, str] = {}
    for item in items:
        query = item.get("query") or ""
        ingredient = item.get("ingredient") or ""
        if not query or query in retry:
            continue
        if query not in results:
            # Never searched yet is not the same fact as searched and empty.
            continue
        if results[query]:
            continue
        if not ingredient or ingredient == query:
            continue
        retry[query] = ingredient
    return retry
