"""Endpoint tests for aliases and unplaced-ingredient reporting."""

from __future__ import annotations


def make_recipe_with(client, name, ingredients):
    return client.post(
        "/api/recipes",
        json={
            "navn": name,
            "placering": "",
            "antal": 4,
            "ingredienser": {
                key: {"amount": 1, "unit": "stk"} for key in ingredients
            },
            "extras": {},
        },
    )


class TestAliasEndpoints:
    def test_config_payload_exposes_aliases(self, client):
        assert client.get("/api/config").get_json()["aliases"] == []

    def test_create_alias(self, client):
        response = client.post(
            "/api/config/aliases",
            json={"alias": "frisk koriander", "canonical": "koriander"},
        )
        assert response.status_code == 201
        aliases = response.get_json()["aliases"]
        assert aliases[0]["alias"] == "frisk koriander"
        assert aliases[0]["canonical"] == "koriander"

    def test_creating_the_same_alias_twice_updates_it(self, client):
        client.post(
            "/api/config/aliases",
            json={"alias": "frisk koriander", "canonical": "koriander"},
        )
        response = client.post(
            "/api/config/aliases",
            json={"alias": "frisk koriander", "canonical": "cilantro"},
        )
        aliases = response.get_json()["aliases"]
        assert len(aliases) == 1
        assert aliases[0]["canonical"] == "cilantro"

    def test_alias_is_required(self, client):
        response = client.post("/api/config/aliases", json={"canonical": "koriander"})
        assert response.status_code == 400

    def test_canonical_is_required(self, client):
        response = client.post("/api/config/aliases", json={"alias": "x"})
        assert response.status_code == 400

    def test_self_alias_is_rejected(self, client):
        response = client.post(
            "/api/config/aliases", json={"alias": "salt", "canonical": " SALT "}
        )
        assert response.status_code == 400
        assert "itself" in response.get_json()["error"]

    def test_delete_alias(self, client):
        created = client.post(
            "/api/config/aliases",
            json={"alias": "frisk koriander", "canonical": "koriander"},
        ).get_json()
        alias_id = created["aliases"][0]["id"]

        response = client.delete(f"/api/config/aliases/{alias_id}")
        assert response.status_code == 200
        assert response.get_json()["aliases"] == []

    def test_deleting_a_missing_alias_is_404(self, client):
        assert client.delete("/api/config/aliases/999").status_code == 404


class TestUnplacedEndpoint:
    """A fresh database is seeded with the default 13-zone kitchen layout,
    so these exercise the real shipped mappings."""

    def test_reports_an_ingredient_with_no_zone(self, client):
        make_recipe_with(client, "Test", ["halloumi"])
        payload = client.get("/api/zones/unplaced").get_json()
        assert "halloumi" in [item["ingredient"] for item in payload["unplaced"]]

    def test_placed_ingredients_are_not_reported(self, client):
        make_recipe_with(client, "Test", ["koriander"])
        payload = client.get("/api/zones/unplaced").get_json()
        assert "koriander" not in [i["ingredient"] for i in payload["unplaced"]]

    def test_lists_zones_in_walking_order(self, client):
        zones = client.get("/api/zones/unplaced").get_json()["zones"]
        assert [z["name"] for z in zones][:4] == ["bad", "vin", "frugt", "tilbehør"]
        assert zones == sorted(zones, key=lambda z: z["order"])

    def test_suggests_a_zone_from_a_similar_placed_ingredient(self, client):
        make_recipe_with(client, "Test", ["rødløgg"])  # near-miss of seeded "rødløg"
        payload = client.get("/api/zones/unplaced").get_json()
        entry = next(i for i in payload["unplaced"] if i["ingredient"] == "rødløgg")
        assert entry["suggested_zone"]["zone"] == "frugt"
        assert entry["suggested_zone"]["because_of"] == "rødløg"

    def test_no_suggestion_when_nothing_is_similar(self, client):
        make_recipe_with(client, "Test", ["zzqqxx"])
        payload = client.get("/api/zones/unplaced").get_json()
        entry = next(i for i in payload["unplaced"] if i["ingredient"] == "zzqqxx")
        assert entry["suggested_zone"] is None

    def test_alias_is_resolved_before_checking_placement(self, client):
        client.post(
            "/api/config/aliases",
            json={"alias": "cilantro", "canonical": "koriander"},
        )
        make_recipe_with(client, "Test", ["cilantro"])

        payload = client.get("/api/zones/unplaced").get_json()
        assert "cilantro" not in [i["ingredient"] for i in payload["unplaced"]]

    def test_alias_target_is_reported_when_it_too_is_unplaced(self, client):
        client.post(
            "/api/config/aliases",
            json={"alias": "cilantro", "canonical": "coriander-leaf"},
        )
        make_recipe_with(client, "Test", ["cilantro"])

        payload = client.get("/api/zones/unplaced").get_json()
        entry = next(i for i in payload["unplaced"] if i["ingredient"] == "cilantro")
        assert entry["canonical"] == "coriander-leaf"
