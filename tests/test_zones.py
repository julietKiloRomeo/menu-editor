"""Tests for kitchen zone loading and seeding."""

from __future__ import annotations

import pytest
from sqlmodel import select

from src.core.zones import (
    UNKNOWN_ZONE,
    Zone,
    ZoneConfig,
    load_default_zones,
    load_zone_config,
    seed_zones,
)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'zones.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    from src import models

    monkeypatch.setattr(
        models, "engine", models.create_engine(db_url, **models._sqlite_kwargs(db_url))
    )
    models.init_db()
    return models


class TestCaseInsensitiveMatching:
    """Recipes capitalise inconsistently; the mapping holds one spelling."""

    def config(self):
        return ZoneConfig(
            zones={"køl": Zone("køl", 9)}, assignments={"smør": "køl"}
        )

    def test_capitalised_ingredient_finds_its_zone(self):
        assert self.config().zone_for("Smør").name == "køl"

    def test_shouted_ingredient_finds_its_zone(self):
        assert self.config().zone_for("SMØR").name == "køl"

    def test_surrounding_whitespace_is_ignored(self):
        assert self.config().zone_for("  smør ").name == "køl"

    def test_is_mapped_agrees_with_zone_for(self):
        config = self.config()

        assert config.is_mapped("Smør") is True
        assert config.zone_for("Smør").name != UNKNOWN_ZONE

    def test_genuinely_unmapped_still_falls_back(self):
        assert self.config().zone_for("Halloumi").name == UNKNOWN_ZONE

    def test_configured_spelling_is_preserved_for_display(self):
        """Matching folds case; the configured spelling is not rewritten."""
        config = self.config()
        config.zone_for("SMØR")

        assert list(config.assignments) == ["smør"]


class TestZoneConfig:
    def test_zone_for_known_ingredient(self):
        config = ZoneConfig(
            zones={"frugt": Zone("frugt", 2)}, assignments={"æble": "frugt"}
        )
        assert config.zone_for("æble").name == "frugt"

    def test_unknown_ingredient_falls_back_to_the_unknown_zone(self):
        config = ZoneConfig(zones={"frugt": Zone("frugt", 2)}, assignments={})
        assert config.zone_for("halloumi").name == UNKNOWN_ZONE

    def test_fallback_uses_configured_unknown_zone_when_present(self):
        config = ZoneConfig(
            zones={UNKNOWN_ZONE: Zone(UNKNOWN_ZONE, 42)}, assignments={}
        )
        assert config.zone_for("x").order == 42

    def test_assignment_to_a_missing_zone_still_resolves(self):
        # An ingredient pointing at a zone that no longer exists must not crash
        config = ZoneConfig(zones={}, assignments={"æble": "deleted"})
        assert config.zone_for("æble").name == UNKNOWN_ZONE

    def test_is_mapped(self):
        config = ZoneConfig(zones={}, assignments={"æble": "frugt"})
        assert config.is_mapped("æble")
        assert not config.is_mapped("halloumi")

    def test_legacy_roundtrip(self):
        legacy = {"kategorier": {"frugt": 2}, "varer": {"æble": "frugt"}}
        assert ZoneConfig.from_legacy_dict(legacy).to_legacy_dict() == legacy


class TestDefaults:
    def test_shipped_defaults_are_loadable(self):
        config = load_default_zones()
        assert len(config.zones) == 13
        assert len(config.assignments) == 537

    def test_shipped_defaults_include_the_unknown_bucket(self):
        assert UNKNOWN_ZONE in load_default_zones().zones

    def test_every_assignment_points_at_a_real_zone(self):
        config = load_default_zones()
        dangling = {
            ingredient: zone
            for ingredient, zone in config.assignments.items()
            if zone not in config.zones
        }
        assert dangling == {}


class TestSeeding:
    def test_seeds_an_empty_database(self, db):
        result = seed_zones()
        assert result.zones_added == 13
        assert result.assignments_added == 537

        config = load_zone_config()
        assert config.zone_for("æble").name == "frugt"

    def test_is_idempotent(self, db):
        seed_zones()
        again = seed_zones(only_if_empty=False)
        assert not again.changed

    def test_refuses_to_touch_an_existing_configuration(self, db):
        seed_zones()
        with db.get_session() as session:
            zone = session.exec(select(db.CategoryConfig)).first()
            session.add(db.IngredientConfig(name="my-thing", category_id=zone.id))
            session.commit()

        result = seed_zones()
        assert result.skipped
        assert not result.changed

    def test_force_updates_without_deleting_custom_entries(self, db):
        seed_zones()
        with db.get_session() as session:
            zone = session.exec(select(db.CategoryConfig)).first()
            session.add(db.IngredientConfig(name="my-thing", category_id=zone.id))
            session.commit()

        seed_zones(only_if_empty=False)
        assert load_zone_config().is_mapped("my-thing")

    def test_load_zone_config_raises_when_nothing_is_configured(self, db):
        with pytest.raises(LookupError):
            load_zone_config()
