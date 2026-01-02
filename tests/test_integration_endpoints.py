import io
from typing import Dict

import pytest
import yaml


def recipe_payload(**overrides) -> Dict:
    payload = {
        "navn": "Everyday Chili",
        "placering": "Red book",
        "antal": 4,
        "ingredienser": {
            "Kidneybønner": {"amount": 2, "unit": "dåse"},
            "Løg": {"amount": 1, "unit": "stk"},
        },
        "extras": {
            "Brød": {"amount": 1, "unit": "stk"},
        },
    }
    payload.update(overrides)
    return payload


def test_recipe_lifecycle_and_slug_uniqueness(client):
    first = client.post("/api/recipes", json=recipe_payload(navn="Veggie Delight"))
    assert first.status_code == 201
    first_slug = first.get_json()["recipe"]["slug"]

    second_payload = recipe_payload(navn="Veggie Encore")
    second_payload["slug"] = first_slug
    second = client.post("/api/recipes", json=second_payload)
    assert second.status_code == 201
    second_slug = second.get_json()["recipe"]["slug"]
    assert second_slug != first_slug
    assert second_slug.startswith(first_slug)

    listing = client.get("/api/recipes")
    assert listing.status_code == 200
    names = {entry["navn"] for entry in listing.get_json()["recipes"]}
    assert names >= {"Veggie Delight"}

    update = client.patch(
        f"/api/recipes/{first_slug}",
        json={"navn": "Veggie Deluxe", "is_blacklisted": True},
    )
    assert update.status_code == 200
    updated_recipe = update.get_json()["recipe"]
    assert updated_recipe["navn"] == "Veggie Deluxe"
    assert updated_recipe["is_blacklisted"] is True

    detail = client.get(f"/api/recipes/{first_slug}")
    assert detail.status_code == 200
    assert detail.get_json()["recipe"]["navn"] == "Veggie Deluxe"


def test_recipe_creation_validation(client):
    resp = client.post("/api/recipes", json={"navn": "", "ingredienser": {}, "antal": -1})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_staples_label_and_update_flow(client):
    create = client.post("/api/staples", json={"name": "Havregryn", "amount": 1, "unit": "pk"})
    assert create.status_code == 201
    item_id = create.get_json()["item"]["id"]

    update = client.patch(
        f"/api/staples/{item_id}",
        json={"amount": 2.5, "unit": "pose", "name": "Øko Havregryn"},
    )
    assert update.status_code == 200
    updated_item = update.get_json()["item"]
    assert updated_item["amount"] == pytest.approx(2.5)
    assert updated_item["unit"] == "pose"

    duplicate = client.post("/api/staples", json={"name": "Øko Havregryn", "amount": 1})
    assert duplicate.status_code == 400

    label_resp = client.post(
        "/api/staples/label",
        json={"label": "Pantry essentials"},
    )
    assert label_resp.status_code == 200
    assert label_resp.get_json()["label"] == "Pantry essentials"

    delete = client.delete(f"/api/staples/{item_id}")
    assert delete.status_code == 200
    remaining_names = [item["name"] for item in delete.get_json()["items"]]
    assert "Øko Havregryn" not in remaining_names


def test_config_category_and_ingredient_management(client):
    cat_resp = client.post("/api/config/categories", json={"name": "Produce", "priority": 1})
    assert cat_resp.status_code == 201
    data = cat_resp.get_json()
    produce = next(c for c in data["categories"] if c["name"] == "Produce")

    another = client.post("/api/config/categories", json={"name": "Pantry", "priority": 2})
    assert another.status_code == 201
    pantry = next(c for c in another.get_json()["categories"] if c["name"] == "Pantry")

    duplicate = client.post("/api/config/categories", json={"name": "Produce", "priority": 3})
    assert duplicate.status_code == 400

    item_resp = client.post(
        "/api/config/items",
        json={"name": "Tomato", "category_id": produce["id"]},
    )
    assert item_resp.status_code == 201
    tomato = next(i for i in item_resp.get_json()["items"] if i["name"] == "Tomato")

    blocked_delete = client.delete(f"/api/config/categories/{produce['id']}")
    assert blocked_delete.status_code == 400

    cat_update = client.patch(
        f"/api/config/categories/{produce['id']}",
        json={"name": "Fresh Produce", "priority": 5},
    )
    assert cat_update.status_code == 200
    assert any(c["name"] == "Fresh Produce" for c in cat_update.get_json()["categories"])

    item_update = client.patch(
        f"/api/config/items/{tomato['id']}",
        json={"name": "Roma Tomato", "category_id": pantry["id"]},
    )
    assert item_update.status_code == 200
    assert any(i["name"] == "Roma Tomato" for i in item_update.get_json()["items"])

    delete_item = client.delete(f"/api/config/items/{tomato['id']}")
    assert delete_item.status_code == 200

    delete_cat = client.delete(f"/api/config/categories/{produce['id']}")
    assert delete_cat.status_code == 200


def test_ingredient_usage_and_rename_flow(client):
    recipe_one = recipe_payload(
        navn="Carrot Soup",
        ingredienser={
            "Gulerod": {"amount": 2, "unit": "stk"},
            "Kartoffel": {"amount": 3, "unit": "stk"},
        },
        extras={},
    )
    recipe_two = recipe_payload(
        navn="Garden Salad",
        ingredienser={"gulerod": {"amount": 1, "unit": "stk"}},
        extras={"Gulerod": {"amount": 1, "unit": "bund"}},
    )
    client.post("/api/recipes", json=recipe_one)
    client.post("/api/recipes", json=recipe_two)

    usage = client.get("/api/ingredients/usage", query_string={"name": "gulerod", "include_extras": "true"})
    assert usage.status_code == 200
    usage_payload = usage.get_json()["usages"]
    assert len(usage_payload) == 3  # 2 recipes ingredients + 1 extra

    rename = client.post(
        "/api/ingredients/rename",
        json={"from": "gulerod", "to": "Gulerod Deluxe", "include_extras": True},
    )
    assert rename.status_code == 200
    assert rename.get_json()["updated_count"] >= 1
    assert not rename.get_json()["conflicts"]


def test_ingredient_rename_conflict_detection(client):
    payload = recipe_payload(
        navn="Carrot Mash",
        ingredienser={
            "Gulerod": {"amount": 200, "unit": "g"},
            "Gulerod Deluxe": {"amount": 2, "unit": "stk"},
        },
    )
    client.post("/api/recipes", json=payload)

    conflict = client.post(
        "/api/ingredients/rename",
        json={"from": "Gulerod", "to": "Gulerod Deluxe", "include_extras": False},
    )
    assert conflict.status_code == 200
    conflict_payload = conflict.get_json()
    assert conflict_payload["conflicts"]

    forced = client.post(
        "/api/ingredients/rename",
        json={
            "from": "Gulerod",
            "to": "Gulerod Deluxe",
            "include_extras": False,
            "force": True,
        },
    )
    assert forced.status_code == 200
    forced_payload = forced.get_json()
    assert any("conflict" in entry["reason"] for entry in forced_payload["conflicts"])


def test_menu_generation_includes_staples(client, app_module, add_category, monkeypatch, tmp_path):
    add_category(name="unknown", priority=999)
    client.post("/api/staples", json={"name": "Salt", "amount": 1, "unit": "stk"})

    recipe_name = "Roast Veg"
    client.post(
        "/api/recipes",
        json=recipe_payload(
            navn=recipe_name,
            ingredienser={"Kartoffel": {"amount": 4, "unit": "stk"}},
            extras={},
        ),
    )

    def fake_save(menu_dict):
        path = tmp_path / "menu.yml"
        path.write_text(yaml.safe_dump(menu_dict), encoding="utf-8")
        return path

    monkeypatch.setattr(app_module, "save_menu", fake_save)

    original_add = app_module.MenuText.add

    def noop_add(self, s):
        self.text += s + "\n"

    monkeypatch.setattr(app_module.MenuText, "add", noop_add)

    response = client.post("/api/menu/generate", json={"menu_data": {recipe_name: 4}})
    assert response.status_code == 200
    markdown = response.get_json()["markdown"]
    assert "# Menu" in markdown
    assert recipe_name in markdown
    assert "Salt" in markdown

    monkeypatch.setattr(app_module.MenuText, "add", original_add)


def test_menu_generation_requires_known_recipes(client):
    response = client.post("/api/menu/generate", json={"menu_data": {"Ghost": 2}})
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_recipe_search_and_similar_endpoints(client, add_category, add_ingredient_mapping):
    veg = add_category(name="Vegetables", priority=1)
    add_ingredient_mapping("Gulerod", veg.id)

    client.post("/api/recipes", json=recipe_payload(navn="Veg Curry"))
    client.post("/api/recipes", json=recipe_payload(navn="Chicken Curry"))

    search = client.get("/api/recipes/search", query_string={"query": "veg"})
    assert search.status_code == 200
    payload = search.get_json()
    assert payload["recipes"]
    assert payload["total_matches"] >= 1

    similar = client.get("/api/ingredients/similar", query_string={"name": "gulerod"})
    assert similar.status_code == 200
    assert "gulerod" not in similar.get_json()["names"]  # should propose other names


def test_create_recipe_from_image_uses_stub(client, app_module, monkeypatch, make_recipe):
    existing = make_recipe(navn="Photo Recipe")

    def fake_generate(image_bytes, mimetype, prompt):
        assert isinstance(image_bytes, (bytes, bytearray))
        assert mimetype == "image/png"
        return (
            {
                "navn": "Photo Recipe",
                "placering": "Scan",
                "antal": 2,
                "ingredienser": {"Flour": {"amount": 100, "unit": "g"}},
                "extras": {},
                "slug": "photo-recipe",
            },
            "navn: Photo Recipe",
        )

    monkeypatch.setattr(app_module, "generate_recipe_from_image", fake_generate)

    data = {
        "prompt": "pls",
        "image": (io.BytesIO(b"fake-bytes"), "recipe.png"),
    }
    response = client.post(
        "/api/recipes/from-image",
        data=data,
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()["recipe"]
    assert payload["navn"] == "Photo Recipe"
    assert payload["suggested_slug"].startswith(existing.slug)
    assert "raw_yaml" in payload
