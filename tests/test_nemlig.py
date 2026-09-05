"""The pure half of the nemlig workflow: list in, basket out, memory updated."""

import json

import pytest

from src.core.nemlig import (
    adapt_product,
    adapt_search_results,
    format_need,
    load_product_map,
    merge_add_lines,
    plan_item,
    queries_for,
    rank_candidates,
    reconcile_basket,
    record_run,
    save_product_map,
)


@pytest.fixture()
def product_map():
    return {
        "mappings": {
            "gulerod": {
                "query": "gulerødder",
                "product_id": "111",
                "name": "Gulerødder",
                "pack": "1 kg",
                "price": 12.0,
                "last_qty": 2,
            },
            "frisk pasta": {
                "query": None,
                "product_id": "222",
                "name": "Fettuccine (frisk)",
                "pack": "250 g",
                "price": 25.0,
                "last_qty": 2,
                "note": "ikke søgbar, kun direkte link",
            },
        },
        "no_default_yet": {"pålæg": {"reason": "to slags, aldrig valgt"}},
        "usually_in_the_kitchen": {"items": ["salt", "olivenolie"]},
    }


class TestFormatNeed:
    def test_joins_units_without_converting_them(self):
        assert format_need({"dl": 3, "g": 300}) == "3 dl + 300 g"

    def test_drops_the_decimal_point_on_whole_counts(self):
        # "1.0 stk" reads as a measurement; "1 stk" reads as a count.
        assert format_need({"stk": 1.0}) == "1 stk"

    def test_keeps_real_fractions(self):
        assert format_need({"stk": 0.3}) == "0.3 stk"

    def test_empty_is_empty(self):
        assert format_need({}) == ""


class TestAdaptProduct:
    def test_reads_nemligs_own_shape(self):
        adapted = adapt_product(
            {
                "Id": "5004143",
                "Name": "Avocado formodnet",
                "Description": "2 stk.",
                "Price": 20,
                "PrimaryImage": "https://img/avocado.jpg",
                "UnitPriceCalc": 10,
                "UnitPriceLabel": "kr/stk",
                "Favorite": True,
                "Availability": {
                    "IsDeliveryAvailable": True,
                    "IsAvailableInStock": True,
                },
            }
        )
        assert adapted == {
            "product_id": "5004143",
            "name": "Avocado formodnet",
            "pack": "2 stk.",
            "price": 20,
            "image": "https://img/avocado.jpg",
            "unit_price": "10 kr/stk",
            "fav": True,
        }

    def test_drops_what_cannot_be_delivered(self):
        # Offering a choice that cannot be honoured wastes the only expensive
        # resource here, which is the user's attention.
        assert (
            adapt_product(
                {
                    "Id": "1",
                    "Name": "Udsolgt",
                    "Availability": {
                        "IsDeliveryAvailable": True,
                        "IsAvailableInStock": False,
                    },
                }
            )
            is None
        )

    def test_accepts_the_already_flattened_shape(self):
        adapted = adapt_product({"product_id": "9", "name": "Løg", "fav": False})
        assert adapted["product_id"] == "9"
        assert adapted["name"] == "Løg"

    def test_coerces_numeric_ids_to_strings(self):
        # nemlig sends strings, hand-written JSON tends to send numbers, and a
        # product id compared with == must not depend on which arrived.
        assert adapt_product({"Id": 5004143, "Name": "x"})["product_id"] == "5004143"

    def test_search_results_filter_out_the_unbuyable(self):
        results = adapt_search_results(
            {
                "løg": [
                    {"Id": "1", "Name": "Løg", "Availability": {"IsAvailableInStock": True}},
                    {"Id": "2", "Name": "Væk", "Availability": {"IsAvailableInStock": False}},
                ]
            }
        )
        assert [hit["product_id"] for hit in results["løg"]] == ["1"]


class TestPlanItem:
    def test_a_mapped_ingredient_carries_its_stored_query_and_quantity(self, product_map):
        plan = plan_item("gulerod", {"stk": 4}, ["Suppe"], "frugt", product_map)
        assert plan["status"] == "mapped"
        assert plan["query"] == "gulerødder"  # recipe Danish is not shelf Danish
        assert plan["qty"] == 2
        assert plan["previous_id"] == "111"

    def test_a_stocked_ingredient_is_flagged_but_still_planned(self, product_map):
        plan = plan_item("salt", {"g": 5}, ["Suppe"], "krydderi", product_map)
        assert plan["status"] == "stocked"
        assert plan["query"] == "salt"

    def test_an_unknown_ingredient_searches_for_itself(self, product_map):
        plan = plan_item("pastinak", {"stk": 2}, ["Suppe"], "frugt", product_map)
        assert plan["status"] == "new"
        assert plan["query"] == "pastinak"
        assert plan["previous_id"] is None

    def test_a_null_query_survives_as_null(self, product_map):
        # The map records that search cannot reach this product at all. Falling
        # back to the ingredient name would run a search already known to fail
        # and present its wrong answers as candidates.
        plan = plan_item("frisk pasta", {"g": 250}, ["Pasta"], "køl", product_map)
        assert plan["query"] is None

    def test_a_known_open_question_is_carried_into_the_row(self, product_map):
        plan = plan_item("pålæg", {"stk": 1}, ["Madpakke"], "køl", product_map)
        assert plan["warning"] == "to slags, aldrig valgt"


class TestQueriesFor:
    def test_deduplicates_and_keeps_first_seen_order(self):
        items = [{"query": "løg"}, {"query": "salt"}, {"query": "løg"}]
        assert queries_for(items) == ["løg", "salt"]

    def test_omits_unsearchable_rows(self):
        assert queries_for([{"query": None}, {"query": ""}, {"query": "løg"}]) == ["løg"]


class TestRankCandidates:
    def test_last_weeks_product_leads(self):
        ranked = rank_candidates(
            [
                {"product_id": "1", "name": "A", "fav": False},
                {"product_id": "2", "name": "B", "fav": False},
            ],
            previous_id="2",
        )
        assert [c["product_id"] for c in ranked] == ["2", "1"]
        assert ranked[0]["previous"] is True

    def test_favourites_come_before_strangers(self):
        ranked = rank_candidates(
            [
                {"product_id": "1", "name": "A", "fav": False},
                {"product_id": "2", "name": "B", "fav": True},
            ],
            previous_id=None,
        )
        assert [c["product_id"] for c in ranked] == ["2", "1"]

    def test_relevance_order_survives_within_each_group(self):
        ranked = rank_candidates(
            [
                {"product_id": "1", "name": "A", "fav": True},
                {"product_id": "2", "name": "B", "fav": True},
            ],
            previous_id=None,
        )
        assert [c["product_id"] for c in ranked] == ["1", "2"]

    def test_a_vanished_favourite_is_rebuilt_from_memory(self, product_map):
        # Sold out, renamed or unsearchable: the row should still offer last
        # week's answer rather than looking like a product never bought.
        ranked = rank_candidates(
            [{"product_id": "999", "name": "Andet", "fav": False}],
            previous_id="111",
            product_map=product_map,
        )
        assert ranked[0]["product_id"] == "111"
        assert ranked[0]["from_memory"] is True
        assert ranked[0]["name"] == "Gulerødder"

    def test_does_not_invent_a_product_it_has_never_seen(self):
        ranked = rank_candidates(
            [{"product_id": "1", "name": "A"}], previous_id="404", product_map={}
        )
        assert [c["product_id"] for c in ranked] == ["1"]

    def test_leaves_the_input_alone(self):
        original = [{"product_id": "1", "name": "A", "fav": True}]
        rank_candidates(original, previous_id="1")
        assert "previous" not in original[0]


class TestMergeAddLines:
    def test_two_rows_of_one_product_are_summed_not_overwritten(self):
        # The expensive bug. AffectPartialQuantity makes quantity absolute, so
        # posting 1 and then 1 leaves one pack in the basket, not two, and
        # nobody finds out until delivery.
        result = merge_add_lines(
            [
                {
                    "ingredient": "revet ost",
                    "action": "buy",
                    "product_id": "77",
                    "qty": 1,
                    "product": {"name": "Cheddar revet", "pack": "140 g", "price": 15},
                },
                {
                    "ingredient": "revet cheddar",
                    "action": "buy",
                    "product_id": "77",
                    "qty": 1,
                    "product": {"name": "Cheddar revet", "pack": "140 g", "price": 15},
                },
            ]
        )
        assert len(result["lines"]) == 1
        assert result["lines"][0]["qty"] == 2
        assert result["lines"][0]["covers"] == ["revet ost", "revet cheddar"]

    def test_a_merge_is_reported_so_it_can_be_checked(self):
        result = merge_add_lines(
            [
                {"ingredient": "a", "action": "buy", "product_id": "7", "qty": 1,
                 "product": {"name": "P"}},
                {"ingredient": "b", "action": "buy", "product_id": "7", "qty": 3,
                 "product": {"name": "P"}},
            ]
        )
        assert len(result["merged"]) == 1
        assert result["merged"][0]["qty"] == 4

    def test_an_undecided_row_blocks_rather_than_vanishes(self):
        result = merge_add_lines([{"ingredient": "pålæg", "action": None}])
        assert result["lines"] == []
        assert result["unresolved"][0]["ingredient"] == "pålæg"

    def test_an_unresolved_link_is_not_added_blind(self):
        # A pasted link yields an id but no name or price, and an unreviewable
        # line is exactly what should not reach a basket.
        result = merge_add_lines(
            [
                {
                    "ingredient": "frisk pasta",
                    "action": "link",
                    "product_id": "222",
                    "url": "https://www.nemlig.com/x-222",
                    "product": None,
                }
            ]
        )
        assert result["lines"] == []
        assert "link not resolved" in result["unresolved"][0]["reason"]

    def test_a_resolved_link_buys_normally(self):
        result = merge_add_lines(
            [
                {
                    "ingredient": "frisk pasta",
                    "action": "link",
                    "product_id": "222",
                    "qty": 2,
                    "product": {"name": "Fettuccine", "pack": "250 g", "price": 25},
                }
            ]
        )
        assert result["lines"][0]["product_id"] == "222"
        assert result["lines"][0]["qty"] == 2

    def test_declined_rows_are_counted_not_bought(self):
        result = merge_add_lines(
            [
                {"ingredient": "salt", "action": "have_it"},
                {"ingredient": "vin", "action": "not_this_week"},
            ]
        )
        assert result["lines"] == []
        assert result["declined"] == 2
        assert result["unresolved"] == []


class TestReconcileBasket:
    def test_a_sold_out_line_is_caught_despite_the_success(self):
        # AddToBasket returns 200 for a sold-out product and sets the line to
        # zero. The response says nothing; only the basket does.
        result = reconcile_basket(
            [{"product_id": "1", "qty": 2, "product_name": "Æbler"}],
            {"Lines": [{"ProductId": "1", "Quantity": 0, "Name": "Æbler"}]},
        )
        assert result["ok"] is False
        assert result["sold_out"][0]["product_name"] == "Æbler"

    def test_a_line_that_never_arrived_is_reported(self):
        result = reconcile_basket(
            [{"product_id": "1", "qty": 1, "product_name": "Løg"}], {"Lines": []}
        )
        assert [line["product_name"] for line in result["missing"]] == ["Løg"]

    def test_a_short_line_is_reported(self):
        result = reconcile_basket(
            [{"product_id": "1", "qty": 3, "product_name": "Løg"}],
            {"Lines": [{"ProductId": "1", "Quantity": 1}]},
        )
        assert result["mismatched"][0]["basket_qty"] == 1

    def test_a_clean_basket_reports_its_own_total(self):
        result = reconcile_basket(
            [{"product_id": "1", "qty": 1, "product_name": "Løg"}],
            {
                "Lines": [{"ProductId": "1", "Quantity": 1}],
                "TotalProductsPrice": 1056.87,
                "NumberOfProducts": 53,
            },
        )
        assert result["ok"] is True
        assert result["total"] == 1056.87


class TestRecordRun:
    """The step that makes next week cheaper -- and the one that used to lie."""

    def test_buying_something_new_teaches_the_map(self, product_map):
        result = record_run(
            product_map,
            [{"ingredient": "pastinak", "action": "buy", "product_id": "5", "qty": 2}],
            [{"product_id": "5", "product_name": "Pastinak", "pack": "500 g", "price": 9}],
        )
        entry = result["map"]["mappings"]["pastinak"]
        assert entry["product_id"] == "5"
        assert entry["last_qty"] == 2
        assert entry["query"] == "pastinak"
        assert result["added"] == 1

    def test_only_we_already_have_it_creates_a_staple(self, product_map):
        result = record_run(
            product_map, [{"ingredient": "mel", "action": "have_it"}], []
        )
        assert "mel" in result["map"]["usually_in_the_kitchen"]["items"]
        assert result["learned_staples"] == ["mel"]

    def test_a_sold_out_item_does_not_become_a_staple(self, product_map):
        # The bug this replaces: one undifferentiated "skip" button meant every
        # reason for not buying was recorded as "the kitchen always has this",
        # permanently and with no way to take it back.
        result = record_run(
            product_map,
            [{"ingredient": "tyttebær", "action": "unavailable", "note": "udsolgt"}],
            [],
        )
        assert "tyttebær" not in result["map"]["usually_in_the_kitchen"]["items"]
        assert result["map"]["no_default_yet"]["tyttebær"]["reason"] == "udsolgt"

    def test_not_cooking_that_this_week_teaches_nothing(self, product_map):
        before = json.dumps(product_map, sort_keys=True)
        result = record_run(
            product_map, [{"ingredient": "laks", "action": "not_this_week"}], []
        )
        assert "laks" not in result["map"]["usually_in_the_kitchen"]["items"]
        assert "laks" not in result["map"]["no_default_yet"]
        assert json.dumps(product_map, sort_keys=True) == before  # nothing in place

    def test_an_undecided_row_is_remembered_as_an_open_question(self, product_map):
        result = record_run(
            product_map,
            [{"ingredient": "pålæg", "action": "undecided", "note": "spørg igen"}],
            [],
        )
        assert result["map"]["no_default_yet"]["pålæg"]["reason"] == "spørg igen"

    def test_buying_an_open_question_closes_it(self, product_map):
        # Left alone, no_default_yet only ever grew: items stayed listed as
        # unanswered long after they had been answered.
        result = record_run(
            product_map,
            [{"ingredient": "pålæg", "action": "buy", "product_id": "8", "qty": 1}],
            [{"product_id": "8", "product_name": "Leverpostej", "pack": "200 g", "price": 12}],
        )
        assert "pålæg" not in result["map"]["no_default_yet"]
        assert result["cleared_unresolved"] == ["pålæg"]

    def test_a_substitution_records_both_the_product_and_the_reason(self, product_map):
        result = record_run(
            product_map,
            [{"ingredient": "gulerod", "action": "buy", "product_id": "111", "qty": 1}],
            [{"product_id": "111", "product_name": "Gulerødder", "pack": "1 kg", "price": 12}],
            replaced={
                "gulerod": {
                    "product_id": "333",
                    "name": "Gulerødder øko",
                    "pack": "1 kg",
                    "price": 15,
                    "reason": "den sædvanlige var udsolgt",
                }
            },
        )
        entry = result["map"]["mappings"]["gulerod"]
        assert entry["product_id"] == "333"
        assert entry["note"] == "den sædvanlige var udsolgt"

    def test_a_null_query_is_never_overwritten(self, product_map):
        # `query: null` is hard-won knowledge that search cannot find this
        # product. Replacing it with the ingredient name resurrects a search
        # already proven to fail.
        result = record_run(
            product_map,
            [{"ingredient": "frisk pasta", "action": "buy", "product_id": "222", "qty": 2}],
            [{"product_id": "222", "product_name": "Fettuccine", "pack": "250 g", "price": 25}],
        )
        assert result["map"]["mappings"]["frisk pasta"]["query"] is None

    def test_the_row_quantity_wins_over_the_merged_line(self, product_map):
        # A merged line's qty covers several rows; storing it as this row's
        # default would double the order a week later.
        result = record_run(
            product_map,
            [
                {"ingredient": "revet ost", "action": "buy", "product_id": "77", "qty": 1},
                {"ingredient": "revet cheddar", "action": "buy", "product_id": "77", "qty": 1},
            ],
            [{"product_id": "77", "product_name": "Cheddar", "pack": "140 g", "price": 15,
              "qty": 2}],
        )
        assert result["map"]["mappings"]["revet ost"]["last_qty"] == 1

    def test_the_staple_list_stays_sorted_and_unique(self, product_map):
        result = record_run(
            product_map,
            [
                {"ingredient": "salt", "action": "have_it"},
                {"ingredient": "mel", "action": "have_it"},
            ],
            [],
        )
        items = result["map"]["usually_in_the_kitchen"]["items"]
        assert items == sorted(set(items))

    def test_provenance_is_stamped(self, product_map):
        result = record_run(
            product_map, [], [], source="menu-2026-09-05", on_date="2026-09-05"
        )
        assert result["map"]["_source_menu"] == "menu-2026-09-05"
        assert "2026-09-05" in result["map"]["_comment"]


class TestProductMapFile:
    def test_a_missing_file_is_a_first_run_not_a_crash(self, tmp_path):
        loaded = load_product_map(tmp_path / "nothing.json")
        assert loaded["mappings"] == {}

    def test_saving_keeps_the_previous_version(self, tmp_path, product_map):
        path = tmp_path / "map.json"
        save_product_map(product_map, path)
        save_product_map({"mappings": {}}, path)

        backup = json.loads((tmp_path / "map.json.bak").read_text(encoding="utf-8"))
        assert "gulerod" in backup["mappings"]

    def test_danish_survives_the_round_trip(self, tmp_path):
        path = tmp_path / "map.json"
        save_product_map({"mappings": {"gulerødder": {"name": "Gulerødder øko."}}}, path)
        assert "gulerødder" in path.read_text(encoding="utf-8")  # not \u-escaped
        assert load_product_map(path)["mappings"]["gulerødder"]["name"] == "Gulerødder øko."

    def test_missing_sections_are_filled_in_on_read(self, tmp_path):
        path = tmp_path / "map.json"
        path.write_text(json.dumps({"mappings": {}}), encoding="utf-8")
        loaded = load_product_map(path)
        assert loaded["no_default_yet"] == {}
        assert loaded["usually_in_the_kitchen"]["items"] == []
