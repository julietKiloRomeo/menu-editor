
def test_list_recipes_only_names(client, make_recipe):
    make_recipe(navn="Pasta Primavera")
    make_recipe(navn="Tofu Curry")

    response = client.get("/api/recipes?only_names=1")

    assert response.status_code == 200
    data = response.get_json()
    assert set(data["recipes"]) == {"Pasta Primavera", "Tofu Curry"}


def test_create_recipe_api_persists_and_returns_names(client):
    payload = {
        "navn": "Chili sin Carne",
        "placering": "Blue binder",
        "antal": 6,
        "ingredienser": {
            "Bønner": {"amount": 2, "unit": "dåse"},
        },
        "extras": {
            "Brød": {"amount": 1, "unit": "stk"},
        },
    }

    response = client.post("/api/recipes", json=payload)

    assert response.status_code == 201
    data = response.get_json()
    assert data["recipe"]["navn"] == payload["navn"]
    assert payload["navn"] in data["recipes"]


def test_update_recipe_flags_and_name(client, make_recipe):
    recipe = make_recipe(navn="Everyday Soup")

    response = client.patch(
        f"/api/recipes/{recipe.slug}",
        json={"navn": "Cozy Soup", "is_blacklisted": True},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["recipe"]["navn"] == "Cozy Soup"
    assert data["recipe"]["is_blacklisted"] is True


def test_staples_crud_flow(client):
    create_resp = client.post(
        "/api/staples",
        json={"name": "Havregryn", "amount": 1, "unit": "pk"},
    )
    assert create_resp.status_code == 201

    listing = client.get("/api/staples")
    assert listing.status_code == 200
    items = listing.get_json()["items"]
    assert any(item["name"] == "Havregryn" for item in items)
