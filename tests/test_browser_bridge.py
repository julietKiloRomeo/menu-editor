"""The browser bridge, especially its failure messages.

Every failure here is something only the user can fix -- start Chrome, log in,
add a flag -- so the message matters as much as the status code.
"""

from __future__ import annotations

import httpx
import pytest

from src import browser
from src.browser import BrowserUnavailable


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


NEMLIG_TAB = {
    "type": "page",
    "url": "https://www.nemlig.com/?search=agurk",
    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/ABC",
}


class TestFindingTheTab:
    def test_it_finds_the_nemlig_tab_among_others(self, monkeypatch):
        monkeypatch.setattr(browser.httpx, "get", lambda *a, **k: FakeResponse([
            {"type": "page", "url": "https://disctree.dk/search?q=flx"},
            NEMLIG_TAB,
        ]))

        assert browser.find_tab()["url"].startswith("https://www.nemlig.com")

    def test_it_ignores_non_page_targets(self, monkeypatch):
        """Service workers carry the site's URL but cannot be driven."""
        monkeypatch.setattr(browser.httpx, "get", lambda *a, **k: FakeResponse([
            {"type": "service_worker", "url": "https://www.nemlig.com/sw.js"},
        ]))

        assert browser.find_tab() is None

    def test_no_nemlig_tab_is_reported_as_reachable_but_empty(self, monkeypatch):
        monkeypatch.setattr(browser.httpx, "get", lambda *a, **k: FakeResponse([
            {"type": "page", "url": "https://disctree.dk/"},
        ]))

        result = browser.status()

        assert result["reachable"] is True
        assert result["tab"] is None
        assert "nemlig.com" in result["detail"]


class TestWhenChromeIsNotSetUp:
    def test_a_dead_port_explains_the_flag(self, monkeypatch):
        def refuse(*a, **k):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(browser.httpx, "get", refuse)

        result = browser.status()

        assert result["reachable"] is False
        assert "--remote-debugging-port" in result["detail"]

    def test_the_chrome_inspect_toggle_is_called_out(self, monkeypatch):
        """Port open but /json 404s: the toggle, not the flag.

        This is the state the user's machine was actually in, and it is
        indistinguishable from a working setup until tabs are requested.
        """
        monkeypatch.setattr(
            browser.httpx, "get", lambda *a, **k: FakeResponse(None, status_code=404)
        )

        result = browser.status()

        assert result["reachable"] is False
        assert "chrome://inspect" in result["detail"]

    def test_evaluating_without_a_tab_raises(self, monkeypatch):
        monkeypatch.setattr(browser.httpx, "get", lambda *a, **k: FakeResponse([]))

        with pytest.raises(BrowserUnavailable):
            browser.evaluate("1 + 1")


class TestEndpoints:
    def test_status_endpoint_reports_trouble_without_failing(self, client, monkeypatch):
        def refuse(*a, **k):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(browser.httpx, "get", refuse)

        response = client.get("/api/browser/status")

        # A missing browser is a state to render, not a server error.
        assert response.status_code == 200
        assert response.get_json()["reachable"] is False
