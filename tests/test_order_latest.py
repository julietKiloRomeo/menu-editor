from __future__ import annotations

import sqlite3
import subprocess
import sys

from scripts import order_latest


def make_database(path, *, run_id=3, order_id=9, recorded_at=None):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        create table shoppingrun (id integer primary key, created_at text);
        create table nemligorder (
            id integer primary key,
            run_id integer,
            recorded_at text
        );
        """
    )
    connection.execute(
        "insert into shoppingrun(id, created_at) values (?, '2026-10-10T08:00:00')",
        (run_id,),
    )
    connection.execute(
        "insert into nemligorder(id, run_id, recorded_at) values (?, ?, ?)",
        (order_id, run_id, recorded_at),
    )
    connection.commit()
    connection.close()


def test_saved_order_state_survives_a_restart(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    database = tmp_path / "order.db"
    make_database(database)
    monkeypatch.setattr(order_latest, "STATE", state_path)

    order_latest.write_state(
        host="valhalla",
        remote_db="/live/recipes.db",
        order={"id": 9, "run_id": 3},
    )

    assert order_latest.read_state() == {
        "host": "valhalla",
        "remote_db": "/live/recipes.db",
        "order_id": 9,
        "run_id": 3,
    }
    assert order_latest.local_order_state(database, 9) == {
        "id": 9,
        "run_id": 3,
        "recorded_at": None,
    }


def test_completed_local_order_can_be_detected_for_recovery(tmp_path):
    database = tmp_path / "order.db"
    make_database(database, recorded_at="2026-10-10T09:00:00")

    assert order_latest.local_order_state(database, 9)["recorded_at"] is not None
    assert order_latest.latest_run_id(database) == 3


def test_corrupt_state_is_ignored(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(order_latest, "STATE", state_path)

    assert order_latest.read_state() is None


def test_remote_sync_replaces_only_the_matching_unfinished_order(tmp_path):
    live_path = tmp_path / "live.db"
    snapshot_path = tmp_path / "snapshot.db"

    schema = """
        create table nemligorder (
            id integer primary key,
            run_id integer,
            created_at text,
            source text,
            recorded_at text
        );
        create table nemligorderitem (
            id integer primary key,
            order_id integer,
            position integer,
            ingredient text,
            qty integer,
            qty_manual integer
        );
        create table stockeditem (
            id integer primary key,
            name text unique
        );
    """
    live = sqlite3.connect(live_path)
    live.executescript(schema)
    live.execute(
        "insert into nemligorder values (9, 3, 'old', 'uge_42_2026', null)"
    )
    live.execute(
        "insert into nemligorderitem values (1, 9, 0, 'old row', 1, 1)"
    )
    live.execute("insert into stockeditem(name) values ('salt')")
    live.commit()
    live.close()

    snapshot = sqlite3.connect(snapshot_path)
    snapshot.executescript(schema)
    snapshot.execute(
        "insert into nemligorder values (9, 3, 'new', 'uge_42_2026', 'done')"
    )
    snapshot.execute(
        "insert into nemligorderitem values (2, 9, 0, 'mælk', 2, 0)"
    )
    snapshot.execute("insert into stockeditem(name) values ('peber')")
    snapshot.commit()
    snapshot.close()

    completed = None
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-", str(live_path), str(snapshot_path), "9"],
            input=order_latest.REMOTE_SYNC,
            text=True,
            capture_output=True,
            check=True,
        )

    result = sqlite3.connect(live_path)
    assert result.execute(
        "select recorded_at from nemligorder where id=9"
    ).fetchone() == ("done",)
    assert result.execute(
        "select ingredient, qty, qty_manual from nemligorderitem where order_id=9"
    ).fetchall() == [("mælk", 2, 0)]
    assert result.execute(
        "select count(*) from nemligorder where run_id=3"
    ).fetchone() == (1,)
    assert result.execute("select name from stockeditem order by name").fetchall() == [
        ("peber",),
        ("salt",),
    ]
    result.close()
    assert completed is not None
    assert '"items": 1' in completed.stdout
