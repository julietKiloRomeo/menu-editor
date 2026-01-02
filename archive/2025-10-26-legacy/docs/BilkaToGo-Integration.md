# BilkaToGo Integration Plan (Step‑by‑Step)

Goal: Add a “Send to BilkaToGo” flow that takes our computed shopping list and adds items to a BilkaToGo basket via Playwright browser automation. We will rely on UI automation (and optionally authenticated fetch) instead of a product/cart API.

This document is a living checklist. We’ll progress milestone by milestone. Check items off as we complete them and capture notes/decisions here.

## Milestone 0 — Prep (Playwright exploration)

- [x] Install Playwright in the project
  - `uv add playwright`
  - `uv run playwright install chromium`
- [x] Configure secrets
  - Env vars: `BILKA_EMAIL`, `BILKA_PASSWORD` (and optionally `BILKA_ZIP` or `BILKA_STORE`)
- [x] Run the exploration script (headful) to learn the flow
  - `uv run python scripts/bilkatogo_explore.py --headful`
  - Accept cookies, log in, set store, try searching for a product and adding to basket
  - The script logs network requests that look relevant (e.g., cart/basket endpoints) to `playwright/logs/bilka-network.log`
- [ ] Save a persistent session (storage state) for later headless runs
  - The exploration script saves to `playwright/.auth/bilka.json` once logged in
- [ ] Capture notes
  - URLs used to log in, set store, search, add to cart
  - Any anti-bot or 2FA prompts we need to handle
  - Reliable selectors for cookie banner, login, search box, result cards, add button

Outcome: We prove we can launch a browser, sign in, search, and add at least one item. We also identify the most reliable selectors and any underlying JSON endpoints (optional future optimization).

### Milestone 0 — Findings (from logs)

What we’ve observed so far in `playwright/logs/bilka-network.log`:

- Cart endpoints (all under `https://api.bilkatogo.dk/api/shop/v6/`)
  - `GET Cart` — retrieves the current cart. Used after add/remove to refresh state.
  - `GET ChangeLineCount` — invoked when adjusting quantities (add/remove). The site passes query parameters (line id and target count) that we’ll capture during a live click.
- Auth and headers
  - Requests include a `jwt_token` header (value present at runtime; redacted in logs).
  - Datadog tracing headers are present but nonessential for us.
- Practical implication
  - We can automate via UI clicks OR by authenticated fetch using `page.request.get()` to these endpoints. The fetch approach is faster and more reliable once we know the parameter names.

Next: capture a single `ChangeLineCount` request (with query) at runtime to learn parameter names (e.g., `lineId`, `quantity`/`count`). We will not log the full URL; just parse the keys internally.

## Milestone 1 — Minimal service + dry‑run

- [ ] Add a `BilkaToGoService` class with: `start()`, `stop()`, `login()`, `ensure_store()`, `search_add(product_name, packs)`
- [ ] Reuse `playwright/.auth/bilka.json` when available; otherwise use credentials to log in
- [ ] Implement cookie‑banner dismissal and simple store selection helper
- [ ] Add request logging and screenshots for failures (saved under `playwright/artifacts/`)
- [ ] Create a backend endpoint: `POST /api/basket/bilka` (dry_run only)
  - Accepts a list of `{product_name, packs}`
  - Returns intended actions (no real clicks yet)

Outcome: We can simulate a run end‑to‑end and display what the automation would do, without actually touching a cart.

## Milestone 2 — Real add flow (UI automation)

- [ ] Implement `search_add()` to:
  - Open the site, ensure store selection, focus search box, enter query
  - Click the first (or mapped) product’s “Add to basket” button `packs` times
  - Confirm via cart badge/toast or another reliable signal
- [ ] Backend endpoint now performs real add when `dry_run=false`
- [ ] Add retries/backoff + graceful fallback if the first product is unavailable

Outcome: We can programmatically add several product lines to the basket.

## Milestone 3 — Ingredient → product mapping + pack math

- [ ] DB: `StoreProductMapping` table (store, ingredient_name, product_id|url|name, pack_amount, pack_unit, priority, active)
- [ ] CRUD endpoints `/api/mappings`
- [ ] Pack computation utilities (g/kg, ml/dl/l, stk) with round‑up to pack count
- [ ] `POST /api/basket/preview` to compute cart plan from aggregated ingredients
- [ ] SPA: “Send to BilkaToGo” button → preview modal (shows packs, missing mappings), proceed when zero missing

Outcome: One‑click push from planned menu to BilkaToGo cart with clear preview.

## Milestone 4 — Hardening and polish

- [ ] Persistent storage state and periodic refresh
- [ ] Better OOS handling (report lines we couldn’t add)
- [ ] Logs + artifacts per run for debugging
- [ ] Optional optimization: replace UI clicks with authenticated `page.request.fetch()` to the cart endpoint if stable

Outcome: Robust, maintainable automation ready for daily use.

---

## Quickstart (Exploration)

1) Install Playwright (one‑time):

```bash
uv add playwright
uv run playwright install chromium
```

2) Set credentials (or export them in your shell profile):

```bash
export BILKA_EMAIL="you@example.com"
export BILKA_PASSWORD="••••••••"
# optional store context
export BILKA_ZIP="8000"
```

3) Run the exploration script headful and follow on‑screen guidance:

```bash
uv run python scripts/bilkatogo_explore.py --headful
```

The script:
- launches Chromium, opens BilkaToGo
- tries to dismiss cookie banner
- helps you log in (then saves session to `playwright/.auth/bilka.json`)
- sets store (if `BILKA_ZIP` is provided)
- optionally performs a test search and attempts to click “Add to basket”
- logs network events to `playwright/logs/bilka-network.log`

4) Record findings right here under Milestone 0 as we discover reliable selectors and flows.

---

## Notes & Decisions

- We will prefer UI automation first; if a clean cart endpoint is discovered and stable, we can switch to authenticated requests for speed.
- We won’t rely on a product/cart API in the first iteration. Search is automated in the browser.
