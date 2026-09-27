"""Ingredient name canonicalisation.

Recipes disagree about what to call things. Aliases let a household decide
that "frisk koriander" and "koriander" are one line on the shopping list
without editing every recipe that mentions them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

from sqlmodel import select

from src.models import IngredientAlias, get_session


def normalise(name: str) -> str:
    """Key used for alias lookup: trimmed and case-folded."""
    return name.strip().casefold()


@dataclass
class AliasMap:
    """Alias -> canonical ingredient name."""

    #: keyed by :func:`normalise` of the alias
    aliases: dict[str, str] = field(default_factory=dict)

    def canonical(self, name: str) -> str:
        """Resolve a name, leaving unknown names untouched.

        Matching is case-insensitive, but the stored canonical spelling wins so
        the shopping list stays consistent.
        """
        return self.aliases.get(normalise(name), name)

    def is_alias(self, name: str) -> bool:
        return normalise(name) in self.aliases

    @classmethod
    def from_pairs(cls, pairs: dict[str, str]) -> "AliasMap":
        return cls(aliases={normalise(a): c for a, c in pairs.items()})


def load_alias_map() -> AliasMap:
    with get_session() as session:
        rows = session.exec(select(IngredientAlias)).all()
    return AliasMap.from_pairs({row.alias: row.canonical for row in rows})


#: How similar two names must be before they are worth querying.
#:
#: Tuned against the real ingredient table, not guessed. At 0.88 the only
#: false positive was "salat"/"salt" (0.889) -- lettuce and salt, which short
#: words make look alike because four of five characters agree. 0.90 drops it
#: and still catches every genuine pair found there:
#: grønsagsbouillon/grøntsagsbouillon (0.970), frisk mozarella/frisk mozzarella
#: (0.968), creme fraiche/cremefraiche (0.960), æggeblomme/æggeblommer (0.952).
SIMILARITY_THRESHOLD = 0.90


def near_duplicates(
    names: Iterable[str], *, threshold: float = SIMILARITY_THRESHOLD
) -> list[tuple[str, str, float]]:
    """Names so close together that they are probably one ingredient.

    A shopping list that contains both "grønsagsbouillon" and
    "grøntsagsbouillon" is not a list with two ingredients on it; it is a
    spelling difference between two recipes, and it survives the kitchen walk
    because ticking one says nothing about the other. That pair reached a real
    basket, where one had been ticked as already in the house and the other was
    about to be bought again.

    Aliases are the cure, but only once someone notices. This is the noticing.
    Returns ``(first, second, ratio)`` sorted most-similar first, and only for
    names that differ -- exact repeats are already handled by the list builder.
    """
    unique = list(dict.fromkeys(name for name in names if name and name.strip()))
    pairs: list[tuple[str, str, float]] = []

    for i, first in enumerate(unique):
        for second in unique[i + 1 :]:
            left, right = normalise(first), normalise(second)
            if left == right:
                continue
            ratio = SequenceMatcher(None, left, right).ratio()
            if ratio >= threshold:
                pairs.append((first, second, round(ratio, 3)))

    pairs.sort(key=lambda pair: pair[2], reverse=True)
    return pairs
