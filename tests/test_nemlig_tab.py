import json

import pytest

from src import nemlig_tab
from src.browser import BrowserUnavailable


def test_search_refreshes_an_expired_token_once(monkeypatch):
    evaluated = {}

    def fake_evaluate(expression, *, debug_url):
        evaluated["expression"] = expression
        evaluated["debug_url"] = debug_url
        return json.dumps({"products": []})

    monkeypatch.setattr(nemlig_tab, "evaluate", fake_evaluate)

    assert nemlig_tab.search("agurk", debug_url="http://chrome.test") == []

    expression = evaluated["expression"]
    assert evaluated["debug_url"] == "http://chrome.test"
    assert "if (r.status === 401)" in expression
    assert expression.count("fetch('/webapi/Token'") == 2
    assert expression.count("r = await fetch(url") == 2


def test_search_failure_does_not_masquerade_as_an_empty_shelf(monkeypatch):
    monkeypatch.setattr(
        nemlig_tab,
        "evaluate",
        lambda expression, *, debug_url: json.dumps({"error": "http-500"}),
    )

    with pytest.raises(BrowserUnavailable, match="No choices were changed"):
        nemlig_tab.search("agurk")


def test_product_links_are_limited_to_nemlig():
    with pytest.raises(ValueError, match="nemlig.com"):
        nemlig_tab.resolve_product_url("https://example.com/product-12345")


def test_product_link_is_resolved_without_navigating(monkeypatch):
    captured = {}

    def fake_evaluate(expression, *, debug_url):
        captured["expression"] = expression
        return json.dumps({"product": {"Id": "5053401", "Name": "Sorte bønner"}})

    monkeypatch.setattr(nemlig_tab, "evaluate", fake_evaluate)

    product = nemlig_tab.resolve_product_url(
        "https://www.nemlig.com/sorte-boenner-oeko-5053401"
    )

    assert product["Id"] == "5053401"
    assert "location.href" not in captured["expression"]


def test_product_link_is_normalised_and_json_ld_price_is_not_trusted(monkeypatch):
    captured = {}

    def fake_evaluate(expression, *, debug_url):
        captured["expression"] = expression
        return json.dumps({"product": {"Id": "5053401", "Name": "Sorte bønner"}})

    monkeypatch.setattr(nemlig_tab, "evaluate", fake_evaluate)
    nemlig_tab.resolve_product_url(
        "https://user:secret@nemlig.com/sorte-boenner-5053401?ref=picker#fragment"
    )

    assert "user:secret" not in captured["expression"]
    assert "#fragment" not in captured["expression"]
    assert 'Price: null' in captured["expression"]
