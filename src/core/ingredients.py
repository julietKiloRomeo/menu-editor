"""Ingredient name canonicalisation.

Recipes disagree about what to call things. Aliases let a household decide
that "frisk koriander" and "koriander" are one line on the shopping list
without editing every recipe that mentions them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
