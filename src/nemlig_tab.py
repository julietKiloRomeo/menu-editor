"""Nemlig operations performed inside the user's logged-in tab.

Every function here is one short ``Runtime.evaluate``. Loops live in the
caller, not in the page: awaiting a 31-query loop inside a single evaluate
exceeds the socket timeout and loses the results even though the page happily
carries on working.

The access token is cached on ``window`` and deliberately never returned. This
process learns product names and prices; it never learns how to authenticate
as the user.
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlparse

from src.browser import DEFAULT_DEBUG_URL, BrowserUnavailable, evaluate

SEARCH_HOST = "https://webapi.prod.knl.nemlig.it/searchgateway/api/search"

#: A query that exists purely to make nemlig reveal its session parameters.
WARMUP_URL = "https://www.nemlig.com/?search=agurk"

#: Prelude shared by every call: cache the token in the page, and find the
#: session/delivery parameters that only exist once the site has searched.
_PRELUDE = """
  if (!window.__meTok) {
    window.__meTok = (await (await fetch('/webapi/Token', { credentials: 'include' })).json()).access_token;
  }
  const ref = performance.getEntriesByType('resource').map(e => e.name)
    .find(n => n.includes('searchgateway/api/search'));
"""


def _run(body: str, *, debug_url: str = DEFAULT_DEBUG_URL):
    """Evaluate an async body that returns a JSON string, and parse it."""
    raw = evaluate("(async () => {%s})()" % body, debug_url=debug_url)
    if raw is None:
        raise BrowserUnavailable("The page returned nothing; try reloading the tab.")
    return json.loads(raw)


def has_session(*, debug_url: str = DEFAULT_DEBUG_URL) -> bool:
    """Whether nemlig has already searched once in this tab."""
    return bool(evaluate(
        "!!performance.getEntriesByType('resource').map(e=>e.name)"
        ".find(n=>n.includes('searchgateway/api/search'))",
        debug_url=debug_url,
    ))


def ensure_session(*, debug_url: str = DEFAULT_DEBUG_URL, timeout: float = 20.0) -> None:
    """Make the session parameters available, navigating the tab if needed.

    The search endpoint needs delivery and timeslot parameters that are
    invisible until nemlig itself has searched; without them a query returns
    HTTP 500 with an empty body, which reads exactly like an auth failure.
    """
    if has_session(debug_url=debug_url):
        return

    evaluate(f"location.href = {json.dumps(WARMUP_URL)}", debug_url=debug_url)

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            if has_session(debug_url=debug_url):
                return
        except BrowserUnavailable:
            continue  # mid-navigation; the tab is briefly unattachable
    raise BrowserUnavailable(
        "Could not get nemlig to reveal its search parameters. Search for "
        "something on nemlig.com once, then try again."
    )


def search(query: str, *, take: int = 8, debug_url: str = DEFAULT_DEBUG_URL) -> list[dict]:
    """Products matching one query, as nemlig's search returns them."""
    body = _PRELUDE + """
      if (!ref) return JSON.stringify({error: 'no-session'});
      const params = new URL(ref).searchParams;
      const url = new URL(%s);
      params.forEach((v, k) => url.searchParams.set(k, v));
      url.searchParams.set('query', %s);
      url.searchParams.set('take', %s);
      url.searchParams.set('skip', '0');
      let r = await fetch(url, { headers: { Authorization: 'Bearer ' + window.__meTok } });
      if (r.status === 401) {
        window.__meTok = (await (await fetch('/webapi/Token', { credentials: 'include' })).json()).access_token;
        r = await fetch(url, { headers: { Authorization: 'Bearer ' + window.__meTok } });
      }
      if (!r.ok) return JSON.stringify({error: 'http-' + r.status});
      const j = await r.json();
      return JSON.stringify({products: j.Products?.Products ?? []});
    """ % (json.dumps(SEARCH_HOST), json.dumps(query), json.dumps(str(take)))

    result = _run(body, debug_url=debug_url)
    if result.get("error") == "no-session":
        raise BrowserUnavailable("Nemlig has not searched yet in this tab.")
    if result.get("error"):
        # Never turn an authentication/API failure into an empty shelf. The
        # caller would reconstruct stale products from memory and the picker
        # would look valid while containing no live results at all.
        raise BrowserUnavailable(
            f"Nemlig search failed for {query!r} ({result['error']}). "
            "No choices were changed; try Search again."
        )
    return result.get("products") or []


def resolve_product_url(url: str, *, debug_url: str = DEFAULT_DEBUG_URL) -> dict:
    """Resolve a pasted nemlig product link without navigating the user's tab."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "nemlig.com",
        "www.nemlig.com",
    ):
        raise ValueError("Paste a nemlig.com product link")
    if parsed.port not in (None, 443):
        raise ValueError("Paste a nemlig.com product link")

    # Rebuild rather than fetching the user's literal string: credentials,
    # fragments and surprising ports have no place in a product lookup.
    safe_url = f"https://www.nemlig.com{parsed.path or '/'}"
    if parsed.query:
        safe_url += f"?{parsed.query}"

    body = """
      const input = %s;
      const r = await fetch(input, { credentials: 'include' });
      if (!r.ok) return JSON.stringify({error: 'http-' + r.status});
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      let product = null;
      for (const node of doc.querySelectorAll('script[type="application/ld+json"]')) {
        try {
          const parsed = JSON.parse(node.textContent || 'null');
          const values = Array.isArray(parsed) ? parsed : [parsed];
          product = values.find(value => value && value['@type'] === 'Product') || product;
        } catch (_) {}
      }
      if (!product) return JSON.stringify({error: 'not-a-product'});
      const id = new URL(input).pathname.match(/(\\d{5,})\\/?$/)?.[1];
      if (!id) return JSON.stringify({error: 'missing-product-id'});
      const offer = Array.isArray(product.offers) ? product.offers[0] : (product.offers || {});
      return JSON.stringify({product: {
        Id: id,
        Name: product.name || '',
        Description: product.description || '',
        // JSON-LD prices have been observed to be wrong. The basket is the
        // authority; keep this unknown rather than persisting a false price.
        Price: null,
        PrimaryImage: Array.isArray(product.image) ? product.image[0] : (product.image || ''),
        Favorite: false,
        Availability: {
          IsDeliveryAvailable: true,
          IsAvailableInStock: !String(offer.availability || '').endsWith('OutOfStock'),
        },
      }});
    """ % json.dumps(safe_url)
    result = _run(body, debug_url=debug_url)
    if result.get("error"):
        raise ValueError(f"Could not resolve that nemlig link ({result['error']})")
    if not isinstance(result.get("product"), dict):
        raise ValueError("Could not resolve that nemlig link (invalid product data)")
    return result["product"]


def add_line(product_id: str, qty: int, *, debug_url: str = DEFAULT_DEBUG_URL) -> int:
    """Put one product in the basket; returns the HTTP status.

    ``AffectPartialQuantity`` makes the quantity absolute rather than additive,
    so re-running after a failure corrects the basket instead of doubling it.
    """
    body = """
      const r = await fetch('/webapi/basket/AddToBasket', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ProductId: %s, quantity: %d,
          AffectPartialQuantity: true, disableQuantityValidation: false }),
      });
      return JSON.stringify({status: r.status});
    """ % (json.dumps(str(product_id)), int(qty))
    return _run(body, debug_url=debug_url)["status"]


def read_basket(*, debug_url: str = DEFAULT_DEBUG_URL) -> dict:
    """The basket, shaped the way ``reconcile_basket`` expects.

    GetBasket calls the product id ``Id``; only the search endpoint calls it
    ``ProductId``. Reading the wrong one yields undefined, JSON.stringify drops
    it, and every line then looks missing.
    """
    body = """
      const b = await (await fetch('/webapi/basket/GetBasket', { credentials: 'include' })).json();
      return JSON.stringify({basket: {
        Lines: (b.Lines || []).map(l => ({ ProductId: l.Id, Quantity: l.Quantity,
                                           Name: l.Name, Price: l.ItemPrice })),
        TotalProductsPrice: b.TotalProductsPrice,
        NumberOfProducts: b.NumberOfProducts,
      }});
    """
    return _run(body, debug_url=debug_url)["basket"]
