"""Talk to the user's own Chrome, so ordering needs no copy-pasted snippets.

This speaks the Chrome DevTools Protocol to a browser the user started and
logged into themselves. That is the whole point: nemlig's search needs a bearer
token and five session parameters, and its basket endpoints authenticate on a
large rotating cookie set. Rather than copy those into a Python HTTP client --
which would mean this process holding the user's grocery-shop credentials -- we
ask the already-authenticated tab to make the call and hand back only the
result. No token, cookie or session ever reaches this process or the disk.

Requires Chrome to be listening on a debug port::

    # ~/.config/chromium-flags.conf   (Arch/chromium)
    --remote-debugging-port=9222

The ``chrome://inspect`` toggle is *not* equivalent: it leaves the port
listening but returns 404 for ``/json``, so tabs cannot be discovered. If
``status()`` reports ``reachable`` but ``tab`` is ``None``, that is usually
what happened.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import websocket

#: Where Chrome's DevTools endpoint lives. Localhost only, never a remote host.
DEFAULT_DEBUG_URL = "http://127.0.0.1:9222"

#: Only tabs on this host are ever touched. A bug that picked the wrong tab
#: would run fetches against someone else's site with their cookies, so the
#: match is explicit rather than "whatever tab is in front".
NEMLIG_HOST = "nemlig.com"

#: A single evaluate must stay well under the socket timeout. Long work is
#: split into many short calls by the caller instead of one awaited loop.
EVALUATE_TIMEOUT = 30.0


class BrowserUnavailable(RuntimeError):
    """Chrome is not reachable, or has no usable nemlig tab.

    Carries a message aimed at the person reading it in the UI, because the
    fix is always something only they can do: start Chrome, log in, add the
    flag.
    """


def _targets(debug_url: str) -> list[dict]:
    try:
        response = httpx.get(f"{debug_url}/json", timeout=3.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise BrowserUnavailable(
                "Chrome is listening but not exposing its tabs. It was most "
                "likely enabled through chrome://inspect. Add "
                "--remote-debugging-port=9222 to ~/.config/chromium-flags.conf "
                "and restart Chrome."
            ) from exc
        raise BrowserUnavailable(f"Chrome refused the request: {exc}") from exc
    except httpx.HTTPError as exc:
        raise BrowserUnavailable(
            "Chrome is not reachable on 127.0.0.1:9222. Start Chrome with "
            "--remote-debugging-port=9222 (see ~/.config/chromium-flags.conf)."
        ) from exc

    payload = response.json()
    return [t for t in payload if isinstance(t, dict)]


def find_tab(debug_url: str = DEFAULT_DEBUG_URL) -> dict | None:
    """The nemlig tab, or ``None``.

    Tab ids change on every reload, so this is re-resolved before each batch
    rather than cached.
    """
    for target in _targets(debug_url):
        if target.get("type") != "page":
            continue
        if NEMLIG_HOST in (target.get("url") or ""):
            return target
    return None


def status(debug_url: str = DEFAULT_DEBUG_URL) -> dict:
    """Whether the browser is ready, in terms the Order screen can render."""
    try:
        tab = find_tab(debug_url)
    except BrowserUnavailable as exc:
        return {"reachable": False, "tab": None, "detail": str(exc)}

    if tab is None:
        return {
            "reachable": True,
            "tab": None,
            "detail": (
                "No nemlig.com tab is open. Open nemlig.com, log in, and "
                "search for anything once."
            ),
        }
    return {"reachable": True, "tab": tab.get("url"), "detail": ""}


def evaluate(expression: str, *, debug_url: str = DEFAULT_DEBUG_URL) -> Any:
    """Run one short piece of JavaScript in the nemlig tab and return its value.

    Deliberately one *short* call. Awaiting a long-running promise here would
    exceed the socket timeout and lose the result even though the page carried
    on working, so callers loop over many small evaluates instead.
    """
    tab = find_tab(debug_url)
    if tab is None:
        raise BrowserUnavailable(status(debug_url)["detail"])

    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise BrowserUnavailable("That tab cannot be attached to; reload it.")

    # suppress_origin is load-bearing. websocket-client sends an Origin header
    # by default; Chrome rejects the handshake with 403 unless that origin is
    # explicitly allowed. The alternative is starting Chrome with
    # --remote-allow-origins, which is a wider hole than sending no origin at
    # all -- a browser page that reached the port could then attach too.
    connection = websocket.create_connection(
        ws_url, timeout=EVALUATE_TIMEOUT, suppress_origin=True
    )
    try:
        connection.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }))
        while True:
            message = json.loads(connection.recv())
            if message.get("id") != 1:
                continue  # an unsolicited event; keep waiting for our reply
            break
    except websocket.WebSocketTimeoutException as exc:
        raise BrowserUnavailable(
            "Chrome did not answer in time. Is the tab busy or asleep?"
        ) from exc
    finally:
        connection.close()

    if "error" in message:
        raise BrowserUnavailable(f"Chrome rejected the request: {message['error']}")

    result = (message.get("result") or {}).get("result") or {}
    thrown = (message.get("result") or {}).get("exceptionDetails")
    if thrown:
        text = (thrown.get("exception") or {}).get("description") or thrown.get("text")
        raise BrowserUnavailable(f"The page raised an error: {text}")
    return result.get("value")
