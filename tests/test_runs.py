"""Tests for shopping runs -- the tickable snapshot of a shopping list."""

from __future__ import annotations

import pytest
from sqlmodel import Session

import json

from src.core.runs import (
    DEFAULT_STOCKED_PATH,
    latest_run,
    load_default_stocked,
    load_stocked_names,
    progress,
    run_items,
    seed_stocked,
    set_checked,
    start_run,
)
from src.core.shopping import ShoppingLine, ShoppingList
from src.core.zones import Zone


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'runs.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    from src import models

    monkeypatch.setattr(
        models, "engine", models.create_engine(db_url, **models._sqlite_kwargs(db_url))
    )
    models.init_db()
    return models


@pytest.fixture()
def session(db):
    with Session(db.engine) as session:
        yield session


def make_list() -> ShoppingList:
    """Two zones, deliberately out of walking order in the source list."""
    frugt = Zone("frugt", 2)
    mejeri = Zone("mejeri", 1)
    return ShoppingList(
        lines=[
            ShoppingLine(
                ingredient="æble",
                zone=frugt,
                quantities={"stk": 4.0},
                recipes=["Æblekage"],
            ),
            ShoppingLine(
                ingredient="mælk",
                zone=mejeri,
                quantities={"l": 1.0, "dl": 2.0},
                recipes=["Pandekager", "Æblekage"],
            ),
        ]
    )


class TestStartRun:
    def test_snapshots_every_line(self, session):
        run = start_run("uge_34", make_list(), session)
        items = run_items(run.id, session)

        assert run.menu_name == "uge_34"
        assert [item.ingredient for item in items] == ["mælk", "æble"]

    def test_orders_items_by_zone_walking_order(self, session):
        run = start_run("uge_34", make_list(), session)
        items = run_items(run.id, session)

        # mælk is second in the source list but its zone comes first
        assert [item.zone_name for item in items] == ["mejeri", "frugt"]

    def test_preserves_units_without_converting_them(self, session):
        run = start_run("uge_34", make_list(), session)
        milk = run_items(run.id, session)[0]

        assert milk.quantities == {"l": 1.0, "dl": 2.0}

    def test_records_contributing_recipes(self, session):
        run = start_run("uge_34", make_list(), session)
        milk = run_items(run.id, session)[0]

        assert milk.recipes == ["Pandekager", "Æblekage"]

    def test_items_start_unchecked(self, session):
        run = start_run("uge_34", make_list(), session)

        assert all(not item.checked for item in run_items(run.id, session))

    def test_copies_the_zone_rather_than_referencing_it(self, session, db):
        """A run must not reshuffle when zones are edited mid-walk."""
        run = start_run("uge_34", make_list(), session)
        items = run_items(run.id, session)
        assert items[0].zone_name == "mejeri"

        # Nothing about the zone tables can reach back into a frozen run.
        assert not hasattr(items[0], "zone_id")


class TestStockedItems:
    def test_known_stock_is_flagged(self, session, db):
        session.add(db.StockedItem(name="mælk"))
        session.commit()

        run = start_run("uge_34", make_list(), session)
        by_name = {item.ingredient: item for item in run_items(run.id, session)}

        assert by_name["mælk"].likely_stocked is True
        assert by_name["æble"].likely_stocked is False

    def test_known_stock_is_not_ticked(self, session, db):
        """A list that pre-ticks salt is the list that sends you home without."""
        session.add(db.StockedItem(name="mælk"))
        session.commit()

        run = start_run("uge_34", make_list(), session)
        by_name = {item.ingredient: item for item in run_items(run.id, session)}

        assert by_name["mælk"].checked is False
        assert by_name["mælk"].checked_at is None

    def test_stock_matching_ignores_case(self, session, db):
        session.add(db.StockedItem(name="MÆLK"))
        session.commit()

        run = start_run("uge_34", make_list(), session)
        by_name = {item.ingredient: item for item in run_items(run.id, session)}

        assert by_name["mælk"].likely_stocked is True

    def test_stocked_items_are_shown_not_hidden(self, session, db):
        session.add(db.StockedItem(name="mælk"))
        session.commit()

        run = start_run("uge_34", make_list(), session)

        assert len(run_items(run.id, session)) == 2

    def test_flagging_does_not_affect_progress(self, session, db):
        session.add(db.StockedItem(name="mælk"))
        session.commit()

        run = start_run("uge_34", make_list(), session)

        assert progress(run_items(run.id, session)) == (0, 2)

    def test_load_stocked_names_normalises(self, session, db):
        session.add(db.StockedItem(name="  Salt "))
        session.commit()

        assert load_stocked_names(session) == {"salt"}


class TestSeedingStock:
    def test_shipped_list_is_the_one_checked_by_hand(self):
        """The 23 cupboard items recorded on 2026-08-22."""
        assert len(load_default_stocked()) == 23

    def test_shipped_list_is_normalised(self):
        names = load_default_stocked()

        assert names == [n.strip().casefold() for n in names]

    def test_shipped_file_is_not_yaml(self):
        """A YAML ``items: [...]`` file would be mistaken for a menu."""
        assert DEFAULT_STOCKED_PATH.suffix == ".json"

    def test_seeds_an_empty_database(self, db, session):
        result = seed_stocked()

        assert result.added == 23
        assert load_stocked_names(session) == set(load_default_stocked())

    def test_skips_a_populated_database(self, db, session):
        session.add(db.StockedItem(name="noget helt andet"))
        session.commit()

        result = seed_stocked()

        assert result.skipped is True
        assert result.added == 0

    def test_force_is_additive_and_never_deletes(self, db, session):
        session.add(db.StockedItem(name="noget helt andet"))
        session.commit()

        seed_stocked(only_if_empty=False)

        assert "noget helt andet" in load_stocked_names(session)
        assert "salt" in load_stocked_names(session)

    def test_seeding_twice_adds_nothing_the_second_time(self, db):
        seed_stocked()
        again = seed_stocked(only_if_empty=False)

        assert again.added == 0

    def test_duplicates_in_the_source_are_collapsed(self, db, tmp_path):
        path = tmp_path / "stocked.json"
        path.write_text(
            json.dumps({"items": ["Salt", "salt", " SALT "]}), encoding="utf-8"
        )

        assert load_default_stocked(path) == ["salt"]


class TestChecking:
    def test_tick_an_item(self, session):
        run = start_run("uge_34", make_list(), session)
        item = run_items(run.id, session)[0]

        updated = set_checked(item.id, True, session)

        assert updated.checked is True
        assert updated.checked_at is not None

    def test_untick_clears_the_timestamp(self, session):
        run = start_run("uge_34", make_list(), session)
        item = run_items(run.id, session)[0]
        set_checked(item.id, True, session)

        updated = set_checked(item.id, False, session)

        assert updated.checked is False
        assert updated.checked_at is None

    def test_ticking_is_idempotent(self, session):
        run = start_run("uge_34", make_list(), session)
        item = run_items(run.id, session)[0]

        set_checked(item.id, True, session)
        again = set_checked(item.id, True, session)

        assert again.checked is True

    def test_unknown_item_returns_none(self, session):
        assert set_checked(9999, True, session) is None

    def test_ticking_one_item_leaves_the_others_alone(self, session):
        run = start_run("uge_34", make_list(), session)
        items = run_items(run.id, session)
        set_checked(items[0].id, True, session)

        after = run_items(run.id, session)

        assert [item.checked for item in after] == [True, False]


class TestLatestRun:
    def test_returns_none_when_never_walked(self, session):
        assert latest_run("uge_34", session) is None

    def test_returns_the_newest_run(self, session):
        first = start_run("uge_34", make_list(), session)
        second = start_run("uge_34", make_list(), session)

        assert latest_run("uge_34", session).id == second.id
        assert first.id != second.id

    def test_runs_are_scoped_to_their_menu(self, session):
        start_run("uge_34", make_list(), session)
        other = start_run("uge_35", make_list(), session)

        assert latest_run("uge_35", session).id == other.id

    def test_starting_a_new_run_does_not_disturb_the_old_one(self, session):
        first = start_run("uge_34", make_list(), session)
        item = run_items(first.id, session)[0]
        set_checked(item.id, True, session)

        start_run("uge_34", make_list(), session)

        assert run_items(first.id, session)[0].checked is True


class TestProgress:
    def test_counts_checked_against_total(self, session):
        run = start_run("uge_34", make_list(), session)
        items = run_items(run.id, session)
        set_checked(items[0].id, True, session)

        assert progress(run_items(run.id, session)) == (1, 2)

    def test_empty_list(self, session):
        run = start_run("tom", ShoppingList(lines=[]), session)

        assert progress(run_items(run.id, session)) == (0, 0)
