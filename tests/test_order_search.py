"""Tests for the second look at a query that found nothing.

The behaviour under test is small but load-bearing: a stored query that the
shelf does not answer used to leave a row with no candidates at all, which
looks like "this cannot be bought" rather than "wrong word" -- and that is
what sends someone off to hunt for a product link during a live order.
"""

from __future__ import annotations

import json

import pytest
import yaml

from src.core.order_search import retry_queries


class TestRetryQueries:
    def test_a_dead_query_is_retried_in_the_lists_own_words(self):
        items = [{"query": "købepitabrød", "ingredient": "købepitabrød"}]
        # The row's own name is the same dead word, so there is nothing to try.
        assert retry_queries(items, {"købepitabrød": []}) == {}

        items = [{"query": "købepitabrød", "ingredient": "pitabrød"}]
        assert retry_queries(items, {"købepitabrød": []}) == {"købepitabrød": "pitabrød"}

    def test_a_query_that_found_something_is_left_alone(self):
        items = [{"query": "mælk", "ingredient": "sødmælk"}]
        assert retry_queries(items, {"mælk": [{"product_id": "1"}]}) == {}

    def test_a_query_that_was_never_run_is_not_a_miss(self):
        # A row can have no search yet; that is not evidence the shelf is empty.
        assert retry_queries([{"query": "mælk", "ingredient": "sødmælk"}], {}) == {}

    def test_rows_sharing_a_dead_query_retry_once_between_them(self):
        items = [
            {"query": "pitabrød", "ingredient": "pitabrød"},
            {"query": "pitabrød", "ingredient": "fladbrød"},
        ]
        assert retry_queries(items, {"pitabrød": []}) == {"pitabrød": "fladbrød"}

    def test_rows_without_a_query_are_skipped(self):
        items = [{"query": "", "ingredient": "pitabrød"}, {"ingredient": "pitabrød"}]
        assert retry_queries(items, {"": []}) == {}


@pytest.fixture()
def search_app(app_bundle, make_recipe, tmp_path, monkeypatch):
    """An app with one order open, and a searching tab that can be faked."""
    app_module, _models = app_bundle
    app_module.app.config["MENU_DATA_DIR"] = str(tmp_path / "menus")
    map_path = tmp_path / "product_map.json"
    map_path.write_text(
        json.dumps(
            {
                "mappings": {},
                "no_default_yet": {},
                "usually_in_the_kitchen": {"items": []},
            }
        ),
        encoding="utf-8",
    )
    app_module.app.config["NEMLIG_MAP_PATH"] = str(map_path)
    make_recipe(navn="Pandekager", ingredienser={"pitabrød": {"amount": 4, "unit": "stk"}})
    (app_module.data_dir() / "uge_34_2026.yaml").write_text(
        yaml.dump({"Mandag": [{"Pandekager": {"amount": 4, "unit": "plates"}}]},
                  allow_unicode=True),
        encoding="utf-8",
    )
    return app_module


def test_run_search_files_the_retry_under_the_rows_original_query(
    search_app, monkeypatch
):
    client = search_app.app.test_client()
    run_id = client.post("/api/runs", json={"menu": "uge_34_2026"}).get_json()["id"]
    order = client.post("/api/orders", json={"run_id": run_id}).get_json()
    item = order["items"][0]

    # The list's word is the one the shelf cannot find, so the row would open
    # with no choices at all without the retry.
    with search_app.get_session() as session:
        row = session.get(search_app.NemligOrderItem, item["id"])
        row.query = "købepitabrød"
        row.ingredient = "pitabrød"
        session.add(row)
        session.commit()

    searched = []

    def fake_search(query, **kwargs):
        searched.append(query)
        if query == "pitabrød":
            return [
                {
                    "Id": "5501616",
                    "Name": "Soft pitabrød",
                    "Description": "5 stk. / 375 g / frost",
                    "Price": 12.95,
                }
            ]
        return []

    monkeypatch.setattr(search_app, "tab_search", fake_search)
    monkeypatch.setattr(search_app, "tab_ensure_session", lambda: None)

    response = client.post(f"/api/orders/{order['id']}/run-search", json={})

    assert response.status_code == 200
    assert searched == ["købepitabrød", "pitabrød"]
    payload = response.get_json()["order"]
    retried = next(i for i in payload["items"] if i["id"] == item["id"])
    # Still the row's query, so the decision is stored against the right name.
    assert retried["query"] == "købepitabrød"
    assert [c["product_id"] for c in retried["candidates"]] == ["5501616"]
