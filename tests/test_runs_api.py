"""Tests for the shopping run and stocked-item endpoints."""

from __future__ import annotations

import pytest
import yaml


@pytest.fixture()
def menu_app(app_bundle, make_recipe, tmp_path):
    """App wired to a temp data dir holding one real menu file.

    Relies on the zone config the app seeds for itself from
    ``data/kitchen_zones.yml``: there ``æble`` is in ``frugt`` (order 2) and
    ``mælk`` in ``køl`` (order 9), so the two land in different zones and in a
    known walking order.
    """
    app_module, models = app_bundle
    app_module.app.config["MENU_DATA_DIR"] = str(tmp_path / "menus")

    make_recipe(
        navn="Pandekager",
        ingredienser={
            "mælk": {"amount": 5, "unit": "dl"},
            "æble": {"amount": 2, "unit": "stk"},
        },
    )

    directory = app_module.data_dir()
    menu = {
        "Mandag": [{"Pandekager": {"amount": 4, "unit": "plates"}}],
    }
    (directory / "uge_34_2026.yaml").write_text(
        yaml.dump(menu, allow_unicode=True), encoding="utf-8"
    )
    return app_module, models


@pytest.fixture()
def menu_client(menu_app):
    return menu_app[0].app.test_client()


def create_run(client, menu="uge_34_2026"):
    return client.post("/api/runs", json={"menu": menu})


class TestListMenus:
    def test_lists_menu_files(self, menu_client):
        response = menu_client.get("/api/menus")

        assert response.status_code == 200
        assert [m["name"] for m in response.get_json()["menus"]] == ["uge_34_2026"]

    def test_ignores_non_menu_files(self, menu_app, menu_client):
        app_module, _ = menu_app
        (app_module.data_dir() / "shopping.md").write_text("# not a menu")

        names = [m["name"] for m in menu_client.get("/api/menus").get_json()["menus"]]

        assert names == ["uge_34_2026"]

    def test_ignores_config_yaml_sharing_the_directory(self, menu_app, menu_client):
        """kitchen_zones.yml lives alongside menus and must not look like one."""
        app_module, _ = menu_app
        (app_module.data_dir() / "kitchen_zones.yml").write_text(
            yaml.dump({"kategorier": {"frugt": 2}, "varer": {"æble": "frugt"}}),
            encoding="utf-8",
        )

        names = [m["name"] for m in menu_client.get("/api/menus").get_json()["menus"]]

        assert names == ["uge_34_2026"]

    def test_ignores_unparseable_yaml(self, menu_app, menu_client):
        app_module, _ = menu_app
        (app_module.data_dir() / "broken.yaml").write_text("{[not yaml", encoding="utf-8")

        names = [m["name"] for m in menu_client.get("/api/menus").get_json()["menus"]]

        assert names == ["uge_34_2026"]

    def test_cannot_start_a_run_from_config(self, menu_app, menu_client):
        app_module, _ = menu_app
        (app_module.data_dir() / "kitchen_zones.yml").write_text(
            yaml.dump({"kategorier": {"frugt": 2}}), encoding="utf-8"
        )

        assert create_run(menu_client, "kitchen_zones").status_code == 404


class TestCreateRun:
    def test_creates_a_run_from_a_menu(self, menu_client):
        response = create_run(menu_client)

        assert response.status_code == 201
        body = response.get_json()
        assert body["menu"] == "uge_34_2026"
        assert body["total"] > 0

    def test_groups_items_by_zone_in_walking_order(self, menu_client):
        body = create_run(menu_client).get_json()

        assert [zone["zone"] for zone in body["zones"]] == ["frugt", "køl"]

    def test_reports_progress(self, menu_client):
        body = create_run(menu_client).get_json()

        assert body["checked"] == 0
        assert body["total"] == 2

    def test_unknown_menu_is_404(self, menu_client):
        assert create_run(menu_client, "nope").status_code == 404

    def test_missing_menu_name_is_404(self, menu_client):
        assert menu_client.post("/api/runs", json={}).status_code == 404

    @pytest.mark.parametrize(
        "name",
        [
            "../../etc/passwd",
            "..%2f..%2fetc%2fpasswd",
            "/etc/passwd",
            "..",
            ".hidden",
            "sub/uge_34_2026",
        ],
    )
    def test_refuses_to_escape_the_data_directory(self, menu_client, name):
        assert create_run(menu_client, name).status_code == 404


class TestReadRun:
    def test_fetch_by_id(self, menu_client):
        run_id = create_run(menu_client).get_json()["id"]

        response = menu_client.get(f"/api/runs/{run_id}")

        assert response.status_code == 200
        assert response.get_json()["id"] == run_id

    def test_unknown_run_is_404(self, menu_client):
        assert menu_client.get("/api/runs/9999").status_code == 404

    def test_latest_run_for_a_menu(self, menu_client):
        create_run(menu_client)
        second = create_run(menu_client).get_json()["id"]

        body = menu_client.get("/api/runs/latest?menu=uge_34_2026").get_json()

        assert body["run"]["id"] == second

    def test_latest_is_null_when_never_walked(self, menu_client):
        body = menu_client.get("/api/runs/latest?menu=uge_34_2026").get_json()

        assert body["run"] is None

    def test_latest_requires_a_menu(self, menu_client):
        assert menu_client.get("/api/runs/latest").status_code == 400


class TestListRuns:
    """The phone picks a run from here, so it must not depend on menu files."""

    def test_empty_before_any_run(self, menu_client):
        assert menu_client.get("/api/runs").get_json()["runs"] == []

    def test_lists_runs_newest_first(self, menu_client):
        first = create_run(menu_client).get_json()["id"]
        second = create_run(menu_client).get_json()["id"]

        runs = menu_client.get("/api/runs").get_json()["runs"]

        assert [run["id"] for run in runs] == [second, first]

    def test_reports_progress(self, menu_client):
        body = create_run(menu_client).get_json()
        item_id = body["zones"][0]["items"][0]["id"]
        menu_client.patch(f"/api/runs/items/{item_id}", json={"checked": True})

        run = menu_client.get("/api/runs").get_json()["runs"][0]

        assert (run["checked"], run["total"]) == (1, body["total"])

    def test_survives_the_menu_file_disappearing(self, menu_app, menu_client):
        """A half-ticked run stays reachable even once its menu is gone."""
        app_module, _ = menu_app
        run_id = create_run(menu_client).get_json()["id"]
        (app_module.data_dir() / "uge_34_2026.yaml").unlink()

        runs = menu_client.get("/api/runs").get_json()["runs"]

        assert [run["id"] for run in runs] == [run_id]
        assert menu_client.get("/api/menus").get_json()["menus"] == []


class TestChecking:
    def first_item_id(self, body):
        return body["zones"][0]["items"][0]["id"]

    def test_tick_an_item(self, menu_client):
        body = create_run(menu_client).get_json()
        item_id = self.first_item_id(body)

        response = menu_client.patch(f"/api/runs/items/{item_id}", json={"checked": True})

        assert response.status_code == 200
        assert response.get_json()["checked"] == 1

    def test_reply_carries_the_whole_run(self, menu_client):
        """Phone and laptop both need current totals on every reply."""
        body = create_run(menu_client).get_json()
        item_id = self.first_item_id(body)

        updated = menu_client.patch(
            f"/api/runs/items/{item_id}", json={"checked": True}
        ).get_json()

        assert updated["total"] == body["total"]
        assert "zones" in updated

    def test_untick(self, menu_client):
        body = create_run(menu_client).get_json()
        item_id = self.first_item_id(body)
        menu_client.patch(f"/api/runs/items/{item_id}", json={"checked": True})

        updated = menu_client.patch(
            f"/api/runs/items/{item_id}", json={"checked": False}
        ).get_json()

        assert updated["checked"] == 0

    def test_checked_is_required(self, menu_client):
        body = create_run(menu_client).get_json()
        item_id = self.first_item_id(body)

        assert menu_client.patch(f"/api/runs/items/{item_id}", json={}).status_code == 400

    def test_unknown_item_is_404(self, menu_client):
        response = menu_client.patch("/api/runs/items/9999", json={"checked": True})

        assert response.status_code == 404

    def test_a_second_client_sees_the_tick(self, menu_app, menu_client):
        """Story 5.4: check-off on the phone is visible on the laptop."""
        body = create_run(menu_client).get_json()
        item_id = self.first_item_id(body)
        menu_client.patch(f"/api/runs/items/{item_id}", json={"checked": True})

        other = menu_app[0].app.test_client()
        seen = other.get(f"/api/runs/{body['id']}").get_json()

        assert seen["checked"] == 1


class TestStockedItems:
    def names(self, client):
        return [i["name"] for i in client.get("/api/stocked").get_json()["items"]]

    def test_ships_seeded_with_the_cupboard_list(self, menu_client):
        """A fresh database starts with the 23 items checked by hand."""
        names = self.names(menu_client)

        assert len(names) == 23
        assert "salt" in names

    def test_add_an_item(self, menu_client):
        before = len(self.names(menu_client))

        response = menu_client.post("/api/stocked", json={"name": "kanelstang"})

        assert response.status_code == 200
        assert "kanelstang" in [i["name"] for i in response.get_json()["items"]]
        assert len(response.get_json()["items"]) == before + 1

    def test_names_are_normalised(self, menu_client):
        menu_client.post("/api/stocked", json={"name": "  KANELSTANG "})

        assert "kanelstang" in self.names(menu_client)

    def test_adding_twice_is_idempotent(self, menu_client):
        menu_client.post("/api/stocked", json={"name": "kanelstang"})
        before = len(self.names(menu_client))

        menu_client.post("/api/stocked", json={"name": "Kanelstang"})

        assert len(self.names(menu_client)) == before

    def test_name_is_required(self, menu_client):
        assert menu_client.post("/api/stocked", json={}).status_code == 400

    def test_delete_an_item(self, menu_client):
        added = menu_client.post("/api/stocked", json={"name": "kanelstang"}).get_json()
        item_id = next(i["id"] for i in added["items"] if i["name"] == "kanelstang")

        response = menu_client.delete(f"/api/stocked/{item_id}")

        assert response.status_code == 200
        assert "kanelstang" not in [i["name"] for i in response.get_json()["items"]]

    def test_delete_unknown_is_404(self, menu_client):
        assert menu_client.delete("/api/stocked/9999").status_code == 404

    def test_seeded_items_are_flagged_on_a_run(self, menu_client):
        """mælk is not on the cupboard list; smør would be."""
        body = create_run(menu_client).get_json()
        flagged = {
            item["ingredient"]: item["likely_stocked"]
            for zone in body["zones"]
            for item in zone["items"]
        }

        assert flagged["mælk"] is False
        assert body["checked"] == 0

    def test_stocked_items_are_flagged_but_not_ticked(self, menu_client):
        menu_client.post("/api/stocked", json={"name": "mælk"})

        body = create_run(menu_client).get_json()
        flagged = {
            item["ingredient"]: item["likely_stocked"]
            for zone in body["zones"]
            for item in zone["items"]
        }

        assert flagged == {"mælk": True, "æble": False}
        assert body["checked"] == 0
