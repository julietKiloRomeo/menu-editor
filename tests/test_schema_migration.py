"""Tests for additive schema catch-up.

``create_all`` only creates missing *tables*. A column added to a model whose
table already exists is silently ignored, and then fails on the first insert
against a real database -- exactly what happened when ``likely_stocked`` was
added to ``ShoppingRunItem``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine

from src.models import ShoppingRunItem, _sql_literal, add_missing_columns


def columns(engine, table: str) -> set[str]:
    with engine.connect() as connection:
        return {col["name"] for col in inspect(connection).get_columns(table)}


def make_stale_run_item_table(engine, omit: str) -> None:
    """Create ``shoppingrunitem`` as it looked before ``omit`` was added."""
    kept = [c for c in ShoppingRunItem.__table__.columns if c.name != omit]
    defs = ", ".join(
        "id INTEGER PRIMARY KEY" if c.name == "id" else f'"{c.name}" TEXT'
        for c in kept
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE TABLE shoppingrunitem ({defs})")


class TestAddMissingColumns:
    def test_adds_a_column_the_model_gained(self, tmp_path):
        """Reproduces the likely_stocked failure exactly."""
        engine = create_engine(f"sqlite:///{tmp_path / 'stale.db'}")
        make_stale_run_item_table(engine, omit="likely_stocked")
        assert "likely_stocked" not in columns(engine, "shoppingrunitem")

        with engine.begin() as connection:
            added = add_missing_columns(connection)

        assert "shoppingrunitem.likely_stocked" in added
        assert "likely_stocked" in columns(engine, "shoppingrunitem")

    def test_existing_rows_survive_and_take_the_default(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'rows.db'}")
        make_stale_run_item_table(engine, omit="likely_stocked")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO shoppingrunitem (id, ingredient) VALUES (1, 'salt')"
            )

        with engine.begin() as connection:
            add_missing_columns(connection)

        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT ingredient, likely_stocked FROM shoppingrunitem")
            ).one()

        assert row[0] == "salt"
        assert not row[1]

    def test_is_idempotent_on_an_up_to_date_database(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
        SQLModel.metadata.create_all(engine)

        with engine.begin() as connection:
            assert add_missing_columns(connection) == []

    def test_running_twice_adds_nothing_the_second_time(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'twice.db'}")
        make_stale_run_item_table(engine, omit="likely_stocked")

        with engine.begin() as connection:
            add_missing_columns(connection)
        with engine.begin() as connection:
            assert add_missing_columns(connection) == []

    def test_leaves_tables_that_do_not_exist_to_create_all(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")

        with engine.begin() as connection:
            assert add_missing_columns(connection) == []

    def test_never_drops_a_column_the_model_no_longer_has(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'extra.db'}")
        SQLModel.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'ALTER TABLE shoppingrunitem ADD COLUMN "legacy" TEXT'
            )

        with engine.begin() as connection:
            add_missing_columns(connection)

        assert "legacy" in columns(engine, "shoppingrunitem")


class TestSqlLiteral:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (True, "1"),
            (False, "0"),
            (3, "3"),
            (1.5, "1.5"),
            (None, "NULL"),
            ("salt", "'salt'"),
            ("it's", "'it''s'"),
        ],
    )
    def test_renders_defaults_safely(self, value, expected):
        assert _sql_literal(value) == expected
