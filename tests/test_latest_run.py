"""What the newest kitchen walk contains, answered without starting anything."""

from __future__ import annotations

import sqlite3

from scripts.latest_run import summarise

SCHEMA = """
    create table shoppingrun (
        id integer primary key,
        menu_name text,
        created_at text
    );
    create table shoppingrunitem (
        id integer primary key,
        run_id integer,
        position integer,
        ingredient text,
        quantities text,
        zone_name text,
        zone_order integer,
        checked integer
    );
    create table nemligorder (
        id integer primary key,
        run_id integer,
        created_at text,
        recorded_at text
    );
"""


def make_run(path, *, rows, order=None):
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.execute(
        "insert into shoppingrun values (9, 'uge_44_2026(3)', '2026-10-24 07:05:58')"
    )
    connection.executemany(
        "insert into shoppingrunitem(run_id, position, ingredient, quantities, "
        "zone_name, zone_order, checked) values (9, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    if order:
        connection.execute(
            "insert into nemligorder values (?, 9, ?, ?)", (5, order[0], order[1])
        )
    connection.commit()
    connection.close()


def test_a_walked_run_reports_what_is_left_by_zone(tmp_path):
    database = tmp_path / "recipes.db"
    make_run(
        path=database,
        rows=[
            (0, "citron", '{"stk": 2.0}', "frugt", 2, 1),
            (1, "mandler", '{"g": 100.0}', "tilbehør", 3, 0),
            (2, "æg", '{"stk": 1.0}', "køl", 9, 0),
        ],
        order=("2026-10-24 07:21:36", "2026-10-24 07:29:20"),
    )

    summary = summarise(database)

    assert "Newest run: #9 uge_44_2026(3)" in summary
    assert "Walk: 1 of 3 ticked" in summary
    assert "Order: #5 recorded 2026-10-24 07:29:20" in summary
    assert "Left to order: 2" in summary
    assert "tilbehør (1): mandler (100 g)" in summary
    assert "køl (1): æg (1 stk)" in summary
    assert "citron" not in summary  # already in the house


def test_an_unwalked_run_says_so(tmp_path):
    database = tmp_path / "recipes.db"
    make_run(path=database, rows=[(0, "citron", '{"stk": 2.0}', "frugt", 2, 0)])

    summary = summarise(database)

    assert "Walk: 0 of 1 ticked  (nothing walked yet)" in summary
    assert "Order: none started" in summary


def test_a_fully_ticked_walk_leaves_nothing_to_order(tmp_path):
    database = tmp_path / "recipes.db"
    make_run(path=database, rows=[(0, "citron", '{"stk": 2.0}', "frugt", 2, 1)])

    assert "the walk ticked everything off" in summarise(database)


def test_an_empty_database_is_not_an_error(tmp_path):
    database = tmp_path / "recipes.db"
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    connection.close()

    assert summarise(database) == "No kitchen run has ever been started."
