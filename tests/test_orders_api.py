"""Tests for the nemlig order endpoints -- the desktop half of the workflow."""

from __future__ import annotations

import json

import pytest
import yaml


@pytest.fixture()
def order_app(app_bundle, make_recipe, tmp_path):
    """App with one menu and a product map of its own.

    The map path is redirected at a temp file on purpose: recording an order
    rewrites it in place, and the real one holds a year of learned choices.
    """
    app_module, models = app_bundle
    app_module.app.config["MENU_DATA_DIR"] = str(tmp_path / "menus")

    map_path = tmp_path / "product_map.json"
    map_path.write_text(
        json.dumps(
            {
                "mappings": {
                    "mælk": {
                        "query": "letmælk",
                        "product_id": "111",
                        "name": "Letmælk",
                        "pack": "1 l",
                        "price": 12,
                        "last_qty": 2,
                    }
                },
                "no_default_yet": {},
                "usually_in_the_kitchen": {"items": []},
            }
        ),
        encoding="utf-8",
    )
    app_module.app.config["NEMLIG_MAP_PATH"] = str(map_path)

    make_recipe(
        navn="Pandekager",
        ingredienser={
            "mælk": {"amount": 5, "unit": "dl"},
            "æble": {"amount": 2, "unit": "stk"},
        },
    )
    directory = app_module.data_dir()
    (directory / "uge_34_2026.yaml").write_text(
        yaml.dump({"Mandag": [{"Pandekager": {"amount": 4, "unit": "plates"}}]},
                  allow_unicode=True),
        encoding="utf-8",
    )
    return app_module, models, map_path


@pytest.fixture()
def order_client(order_app):
    return order_app[0].app.test_client()


@pytest.fixture()
def run_id(order_client):
    return order_client.post("/api/runs", json={"menu": "uge_34_2026"}).get_json()["id"]


def open_order(client, run_id, **kwargs):
    return client.post("/api/orders", json={"run_id": run_id, **kwargs})


def items_of(order):
    return {item["ingredient"]: item for item in order["items"]}


class TestCreateOrder:
    def test_opens_an_order_for_the_runs_items(self, order_client, run_id):
        response = open_order(order_client, run_id)

        assert response.status_code == 201
        order = response.get_json()
        assert set(items_of(order)) == {"mælk", "æble"}
        assert order["decided"] == 0

    def test_ticked_items_are_left_out(self, order_client, run_id):
        run = order_client.get(f"/api/runs/{run_id}").get_json()
        milk = next(
            item
            for zone in run["zones"]
            for item in zone["items"]
            if item["ingredient"] == "mælk"
        )
        order_client.patch(f"/api/runs/items/{milk['id']}", json={"checked": True})

        order = open_order(order_client, run_id).get_json()

        # Ticking meant "we already have it". Asking again would either waste
        # the kitchen walk or quietly overrule it.
        assert set(items_of(order)) == {"æble"}

    def test_the_whole_list_can_be_revisited_on_purpose(self, order_client, run_id):
        run = order_client.get(f"/api/runs/{run_id}").get_json()
        milk = next(
            item
            for zone in run["zones"]
            for item in zone["items"]
            if item["ingredient"] == "mælk"
        )
        order_client.patch(f"/api/runs/items/{milk['id']}", json={"checked": True})

        order = open_order(order_client, run_id, include_checked=True).get_json()

        assert set(items_of(order)) == {"mælk", "æble"}

    def test_what_the_map_already_knows_is_carried_in(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        milk = items_of(order)["mælk"]

        assert milk["status"] == "mapped"
        assert milk["query"] == "letmælk"  # recipe Danish is not shelf Danish
        assert milk["qty"] == 2

    def test_an_unknown_ingredient_searches_for_itself(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        assert items_of(order)["æble"]["status"] == "new"
        assert items_of(order)["æble"]["query"] == "æble"

    def test_the_need_is_rendered_for_a_human(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        assert items_of(order)["mælk"]["need"] == "5 dl"

    def test_a_missing_run_is_a_404(self, order_client):
        assert open_order(order_client, 999).status_code == 404

    def test_run_id_is_required(self, order_client):
        assert order_client.post("/api/orders", json={}).status_code == 400


class TestQueries:
    def test_lists_the_searches_to_run(self, order_client, run_id):
        order_id = open_order(order_client, run_id).get_json()["id"]

        queries = order_client.get(f"/api/orders/{order_id}/queries").get_json()["queries"]

        assert sorted(queries) == ["letmælk", "æble"]

    def test_answered_rows_drop_out(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "have_it"},
        )

        queries = order_client.get(
            f"/api/orders/{order['id']}/queries"
        ).get_json()["queries"]

        # Re-searching a decided row would churn its candidates underneath a
        # decision that has already been made.
        assert queries == ["letmælk"]


class TestSearchResults:
    def test_candidates_are_attached_and_ranked(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        response = order_client.post(
            f"/api/orders/{order['id']}/search-results",
            json={
                "results": {
                    "letmælk": [
                        {"Id": "999", "Name": "Anden mælk", "Price": 9},
                        {"Id": "111", "Name": "Letmælk", "Price": 12},
                    ]
                }
            },
        )

        assert response.status_code == 200
        milk = items_of(response.get_json()["order"])["mælk"]
        # Last week's product leads: the strongest signal about what someone
        # wants is what they chose the last time they were asked.
        assert milk["candidates"][0]["product_id"] == "111"
        assert milk["candidates"][0]["previous"] is True

    def test_nemligs_own_shape_is_accepted_unreshaped(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        order_client.post(
            f"/api/orders/{order['id']}/search-results",
            json={
                "results": {
                    "æble": [
                        {
                            "Id": "5",
                            "Name": "Æbler",
                            "Description": "1 kg / Danmark",
                            "Price": 25,
                            "PrimaryImage": "https://img/a.jpg",
                            "Favorite": True,
                        }
                    ]
                }
            },
        )

        apple = items_of(
            order_client.get(f"/api/orders/{order['id']}").get_json()
        )["æble"]
        assert apple["candidates"][0]["pack"] == "1 kg / Danmark"
        assert apple["candidates"][0]["fav"] is True

    def test_sold_out_hits_never_reach_the_picker(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        order_client.post(
            f"/api/orders/{order['id']}/search-results",
            json={
                "results": {
                    "æble": [
                        {
                            "Id": "5",
                            "Name": "Udsolgt",
                            "Availability": {"IsAvailableInStock": False},
                        }
                    ]
                }
            },
        )

        apple = items_of(
            order_client.get(f"/api/orders/{order['id']}").get_json()
        )["æble"]
        assert apple["candidates"] == []

    def test_rows_search_could_not_answer_are_named(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        response = order_client.post(
            f"/api/orders/{order['id']}/search-results",
            json={"results": {"æble": [], "letmælk": []}},
        )

        # Only the row with nothing to fall back on. Naming these is the prompt
        # to re-search with a different word: when results look unrelated,
        # suspect your word before you suspect the shelf.
        assert response.get_json()["without_candidates"] == ["æble"]

    def test_an_empty_search_still_offers_last_weeks_product(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        order_client.post(
            f"/api/orders/{order['id']}/search-results",
            json={"results": {"letmælk": []}},
        )

        # Sold out, renamed or gone from the index: the row should still offer
        # what was bought last time rather than look like a product never seen.
        milk = items_of(order_client.get(f"/api/orders/{order['id']}").get_json())["mælk"]
        assert milk["candidates"][0]["product_id"] == "111"
        assert milk["candidates"][0]["from_memory"] is True

    def test_a_decided_row_is_not_disturbed(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "have_it"},
        )

        order_client.post(
            f"/api/orders/{order['id']}/search-results",
            json={"results": {"æble": [{"Id": "5", "Name": "Æbler"}]}},
        )

        apple = items_of(
            order_client.get(f"/api/orders/{order['id']}").get_json()
        )["æble"]
        assert apple["candidates"] == []

    def test_results_must_be_an_object(self, order_client, run_id):
        order_id = open_order(order_client, run_id).get_json()["id"]

        response = order_client.post(
            f"/api/orders/{order_id}/search-results", json={"results": []}
        )

        assert response.status_code == 400


class TestChoices:
    def test_choosing_a_product_is_saved_immediately(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        item_id = items_of(order)["æble"]["id"]

        response = order_client.patch(
            f"/api/orders/items/{item_id}",
            json={
                "action": "buy",
                "product_id": "5",
                "qty": 3,
                "product": {"Id": "5", "Name": "Æbler", "Price": 25},
            },
        )

        assert response.status_code == 200
        apple = items_of(response.get_json())["æble"]
        assert apple["action"] == "buy"
        assert apple["qty"] == 3
        assert apple["product"]["name"] == "Æbler"

    def test_the_whole_order_comes_back_so_progress_stays_right(
        self, order_client, run_id
    ):
        order = open_order(order_client, run_id).get_json()

        updated = order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "have_it"},
        ).get_json()

        assert updated["decided"] == 1
        assert updated["total"] == 2

    def test_declining_clears_any_chosen_product(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        item_id = items_of(order)["æble"]["id"]
        order_client.patch(
            f"/api/orders/items/{item_id}",
            json={"action": "buy", "product_id": "5",
                  "product": {"Id": "5", "Name": "Æbler"}},
        )

        response = order_client.patch(
            f"/api/orders/items/{item_id}", json={"action": "not_this_week"}
        )

        # Otherwise the basket builder cheerfully buys what was just refused.
        apple = items_of(response.get_json())["æble"]
        assert apple["product_id"] is None
        assert apple["product"] is None

    def test_a_note_can_be_edited_without_disturbing_the_product(
        self, order_client, run_id
    ):
        order = open_order(order_client, run_id).get_json()
        item_id = items_of(order)["æble"]["id"]
        order_client.patch(
            f"/api/orders/items/{item_id}",
            json={"action": "buy", "product_id": "5",
                  "product": {"Id": "5", "Name": "Æbler"}},
        )

        response = order_client.patch(
            f"/api/orders/items/{item_id}", json={"note": "de små, ikke de store"}
        )

        apple = items_of(response.get_json())["æble"]
        assert apple["note"] == "de små, ikke de store"
        assert apple["product_id"] == "5"

    def test_a_decision_can_be_taken_back(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        item_id = items_of(order)["æble"]["id"]
        order_client.patch(f"/api/orders/items/{item_id}", json={"action": "have_it"})

        response = order_client.patch(f"/api/orders/items/{item_id}", json={"action": None})

        assert items_of(response.get_json())["æble"]["action"] is None

    def test_an_unknown_action_is_refused(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        response = order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "skip"},
        )

        # "skip" is exactly the conflated verb this design replaced.
        assert response.status_code == 400

    def test_an_empty_patch_is_refused(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        response = order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}", json={}
        )

        assert response.status_code == 400


class TestBasket:
    def test_quantities_are_summed_per_product(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        product = {"Id": "77", "Name": "Cheddar", "Price": 15}
        for name in ("mælk", "æble"):
            order_client.patch(
                f"/api/orders/items/{items_of(order)[name]['id']}",
                json={"action": "buy", "product_id": "77", "qty": 1, "product": product},
            )

        basket = order_client.get(f"/api/orders/{order['id']}/basket").get_json()

        assert len(basket["lines"]) == 1
        assert basket["lines"][0]["qty"] == 2
        assert sorted(basket["lines"][0]["covers"]) == ["mælk", "æble"]

    def test_undecided_rows_block_the_basket(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()

        basket = order_client.get(f"/api/orders/{order['id']}/basket").get_json()

        assert sorted(u["ingredient"] for u in basket["unresolved"]) == ["mælk", "æble"]


class TestReconcile:
    def test_a_sold_out_line_is_caught(self, order_client, run_id):
        order = open_order(order_client, run_id).get_json()
        order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "buy", "product_id": "5", "qty": 1,
                  "product": {"Id": "5", "Name": "Æbler"}},
        )

        response = order_client.post(
            f"/api/orders/{order['id']}/reconcile",
            json={"basket": {"Lines": [{"ProductId": "5", "Quantity": 0, "Name": "Æbler"}]}},
        )

        result = response.get_json()
        assert result["ok"] is False
        assert result["sold_out"][0]["product_id"] == "5"

    def test_a_basket_is_required(self, order_client, run_id):
        order_id = open_order(order_client, run_id).get_json()["id"]

        assert order_client.post(
            f"/api/orders/{order_id}/reconcile", json={}
        ).status_code == 400


class TestRecord:
    def test_buying_teaches_the_map_and_backs_it_up(self, order_app, order_client, run_id):
        _, _, map_path = order_app
        order = open_order(order_client, run_id).get_json()
        order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "buy", "product_id": "5", "qty": 3,
                  "product": {"Id": "5", "Name": "Æbler", "Description": "1 kg"}},
        )

        response = order_client.post(f"/api/orders/{order['id']}/record", json={})

        assert response.status_code == 200
        saved = json.loads(map_path.read_text(encoding="utf-8"))
        assert saved["mappings"]["æble"]["product_id"] == "5"
        assert saved["mappings"]["æble"]["last_qty"] == 3
        assert map_path.with_suffix(".json.bak").exists()

    def test_a_dry_run_changes_nothing_on_disk(self, order_app, order_client, run_id):
        _, _, map_path = order_app
        before = map_path.read_text(encoding="utf-8")
        order = open_order(order_client, run_id).get_json()
        order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "buy", "product_id": "5",
                  "product": {"Id": "5", "Name": "Æbler"}},
        )

        response = order_client.post(
            f"/api/orders/{order['id']}/record", json={"dry_run": True}
        )

        assert response.get_json()["added"] == 1
        assert map_path.read_text(encoding="utf-8") == before

    def test_we_already_have_it_reaches_the_phones_stocked_list(
        self, order_app, order_client, run_id
    ):
        order = open_order(order_client, run_id).get_json()
        order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "have_it"},
        )

        order_client.post(f"/api/orders/{order['id']}/record", json={})

        # The map alone is not enough: the next kitchen walk reads the database.
        names = [row["name"] for row in order_client.get("/api/stocked").get_json()["items"]]
        assert "æble" in names

    def test_a_sold_out_item_does_not_become_a_staple(
        self, order_app, order_client, run_id
    ):
        _, _, map_path = order_app
        order = open_order(order_client, run_id).get_json()
        order_client.patch(
            f"/api/orders/items/{items_of(order)['æble']['id']}",
            json={"action": "unavailable", "note": "udsolgt"},
        )

        order_client.post(f"/api/orders/{order['id']}/record", json={})

        saved = json.loads(map_path.read_text(encoding="utf-8"))
        assert "æble" not in saved["usually_in_the_kitchen"]["items"]
        assert saved["no_default_yet"]["æble"]["reason"] == "udsolgt"

    def test_recording_is_marked_so_it_is_not_done_twice_by_accident(
        self, order_client, run_id
    ):
        order = open_order(order_client, run_id).get_json()

        order_client.post(f"/api/orders/{order['id']}/record", json={})

        assert order_client.get(
            f"/api/orders/{order['id']}"
        ).get_json()["recorded_at"] is not None


class TestProductMapEndpoint:
    def test_exposes_what_the_app_remembers(self, order_client):
        response = order_client.get("/api/nemlig/map")

        payload = response.get_json()
        assert payload["summary"]["mappings"] == 1
        assert "mælk" in payload["mappings"]


class TestListOrders:
    def test_newest_first_with_progress(self, order_client, run_id):
        first = open_order(order_client, run_id).get_json()
        second = open_order(order_client, run_id).get_json()

        orders = order_client.get("/api/orders").get_json()["orders"]

        assert [o["id"] for o in orders] == [second["id"], first["id"]]
        assert orders[0]["total"] == 2
