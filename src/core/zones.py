"""Kitchen zones: where things live, and the order you walk past them.

A "zone" is what the database still calls a ``CategoryConfig``. The name is
kept at the persistence layer to avoid a migration, but the domain speaks in
zones because that is what the ordering actually means: the sequence in which
the shopper walks their kitchen and, later, the shop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import select

from src.models import CategoryConfig, IngredientConfig, get_session

UNKNOWN_ZONE = "unknown"
UNKNOWN_ORDER = 1000


@dataclass(frozen=True)
class Zone:
    """A named area of the kitchen, ordered by walking sequence."""

    name: str
    order: int


@dataclass
class ZoneConfig:
    """Zone definitions plus the ingredient -> zone assignment."""

    zones: dict[str, Zone] = field(default_factory=dict)
    assignments: dict[str, str] = field(default_factory=dict)

    def zone_for(self, ingredient: str) -> Zone:
        """Resolve an ingredient's zone, falling back to the unknown bucket.

        The fallback is deliberately a real Zone rather than a raised error so
        an unmapped ingredient can never drop off a shopping list silently.
        """
        name = self.assignments.get(ingredient, UNKNOWN_ZONE)
        zone = self.zones.get(name)
        if zone is not None:
            return zone
        # 'unknown' is not guaranteed to exist as a configured row.
        return self.zones.get(UNKNOWN_ZONE, Zone(UNKNOWN_ZONE, UNKNOWN_ORDER))

    def is_mapped(self, ingredient: str) -> bool:
        return ingredient in self.assignments

    # -- legacy interop -------------------------------------------------
    @classmethod
    def from_legacy_dict(cls, config: dict) -> ZoneConfig:
        """Build from the historic ``{"kategorier": ..., "varer": ...}`` shape."""
        zones = {
            name: Zone(name=name, order=order)
            for name, order in (config.get("kategorier") or {}).items()
        }
        return cls(zones=zones, assignments=dict(config.get("varer") or {}))

    def to_legacy_dict(self) -> dict:
        return {
            "kategorier": {z.name: z.order for z in self.zones.values()},
            "varer": dict(self.assignments),
        }


def load_zone_config() -> ZoneConfig:
    """Load zones and ingredient assignments from the database."""
    with get_session() as session:
        categories = session.exec(select(CategoryConfig)).all()
        if not categories:
            raise LookupError("no zones configured")
        items = session.exec(select(IngredientConfig)).all()

        zones = {c.name: Zone(name=c.name, order=c.priority) for c in categories}
        by_id = {c.id: c.name for c in categories}

        assignments: dict[str, str] = {}
        for item in items:
            zone_name = by_id.get(item.category_id)
            if zone_name:
                assignments[item.name] = zone_name

    return ZoneConfig(zones=zones, assignments=assignments)
