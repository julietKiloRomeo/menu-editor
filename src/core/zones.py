"""Kitchen zones: where things live, and the order you walk past them.

A "zone" is what the database still calls a ``CategoryConfig``. The name is
kept at the persistence layer to avoid a migration, but the domain speaks in
zones because that is what the ordering actually means: the sequence in which
the shopper walks their kitchen and, later, the shop.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import yaml
from sqlmodel import select

from src.models import CategoryConfig, IngredientConfig, get_session

UNKNOWN_ZONE = "unknown"
UNKNOWN_ORDER = 1000

#: Default kitchen layout shipped with the app, used to seed a fresh database.
DEFAULT_ZONES_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "kitchen_zones.yml"
)


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


@dataclass
class SeedResult:
    zones_added: int = 0
    zones_updated: int = 0
    assignments_added: int = 0
    assignments_updated: int = 0
    skipped: bool = False
    reason: str = ""

    @property
    def changed(self) -> bool:
        return bool(
            self.zones_added
            or self.zones_updated
            or self.assignments_added
            or self.assignments_updated
        )


def load_default_zones(path: pathlib.Path | None = None) -> ZoneConfig:
    source = path or DEFAULT_ZONES_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return ZoneConfig.from_legacy_dict(data)


def seed_zones(
    path: pathlib.Path | None = None,
    *,
    only_if_empty: bool = True,
) -> SeedResult:
    """Load the default kitchen layout into the database.

    Idempotent: existing zones keep their configured walking order unless it
    differs, and existing ingredient assignments are re-pointed rather than
    duplicated.

    ``only_if_empty`` guards against clobbering a real configuration -- with it
    set, seeding is skipped whenever any ingredient assignment already exists.
    """
    config = load_default_zones(path)
    result = SeedResult()

    with get_session() as session:
        existing_assignments = session.exec(select(IngredientConfig)).all()
        if only_if_empty and existing_assignments:
            result.skipped = True
            result.reason = (
                f"{len(existing_assignments)} ingredient assignments already exist"
            )
            return result

        by_name = {c.name: c for c in session.exec(select(CategoryConfig)).all()}

        for zone in config.zones.values():
            current = by_name.get(zone.name)
            if current is None:
                current = CategoryConfig(name=zone.name, priority=zone.order)
                session.add(current)
                by_name[zone.name] = current
                result.zones_added += 1
            elif current.priority != zone.order:
                current.priority = zone.order
                session.add(current)
                result.zones_updated += 1
        session.commit()

        for zone_name in list(by_name):
            session.refresh(by_name[zone_name])
        zone_ids = {name: c.id for name, c in by_name.items()}

        existing_items = {
            item.name: item for item in session.exec(select(IngredientConfig)).all()
        }

        for ingredient, zone_name in config.assignments.items():
            zone_id = zone_ids.get(zone_name)
            if zone_id is None:
                continue
            item = existing_items.get(ingredient)
            if item is None:
                session.add(
                    IngredientConfig(name=ingredient, category_id=zone_id)
                )
                result.assignments_added += 1
            elif item.category_id != zone_id:
                item.category_id = zone_id
                session.add(item)
                result.assignments_updated += 1
        session.commit()

    return result
