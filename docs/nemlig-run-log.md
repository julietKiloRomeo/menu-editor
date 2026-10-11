# Nemlig run log

One entry per weekly ordering run. The point is to capture what had to be
decided by hand, so the next run can decide less. Append newest at the top.

---

## Run 42 postmortem — 2026-10-10

The basket was ultimately correct (33 lines, 50 items, 1,012.06 kr), but the
workflow was not: an agent manually bridged the live and local databases,
revived the old standalone picker, lost time to an expired cached token, and
made the user wait while state moved between several temporary files. The app
already contained most of the finished workflow, but there was no single safe
entry point that joined valhalla's database to local Chrome.

Changes made from this run:

- `scripts/order_latest.py` is the only kitchen-run entry point. It takes a
  SQLite backup over SSH (safe for WAL), chooses/resumes the newest run, builds
  and opens the app picker, searches live products, and syncs the completed
  order back without replacing the live database.
- Interrupted picks are kept locally and resumed. A clean fill that could not
  sync is retried idempotently on the next invocation.
- Search now refreshes an expired bearer token once and aborts visibly on any
  remaining API error instead of presenting stale memory as live results.
- Direct product links resolve inside the logged-in tab immediately.
- Automatic pack quantities come from this week's need; duplicate rows are
  calculated from their combined need. User-edited quantities always win,
  including values saved before the new quantity-origin flag existed.
- Basket fill is blocked until every row is decided. A clean reconciliation
  records product memory automatically; the premature manual Record action was
  removed from the picker.

---

## Bridge verified live — 2026-09-12, after run 4

The Order screen now drives the browser itself; no snippets, no pasting. Live
results against nemlig, with the flag set and Chrome restarted:

- `/api/browser/status` → reports the tab correctly, and reported the
  chrome://inspect misconfiguration correctly beforehand.
- `/api/orders/<id>/run-search` → 31 queries in **13,7 s**.
- **Preselect: 28 of 32 rows chosen automatically.** Only 4 needed a human.
- `/api/orders/<id>/fill-basket` → added, reconciled, reported clean.
- Idempotency confirmed by accident: `fill-basket` ran three times and the
  basket still held exactly one citron. `AffectPartialQuantity` works.

### Two things the live run caught that tests could not

1. **Chrome rejects the CDP websocket over `Origin`.** `websocket-client`
   sends one by default and Chrome answers `403`. Fixed with
   `suppress_origin=True` rather than `--remote-allow-origins`, which would
   let any page that can reach the port attach to the browser.
2. **The `from_memory` exclusion earned its place immediately.** `agurk` and
   `butterdej` both had `previous=True, from_memory=True` — their mapped
   products were not in this week's results at all. Auto-buying them would
   have put two more sold-out items in the basket at quantity zero, the exact
   Cosmic Crisp failure. Both were correctly left for a human.

### Corrected from below

The unexplained empty basket after the Chrome restart was **not** a lapsed
timeslot, as first guessed here. The user had simply checked out. Recorded
because the wrong theory was written down first.

---

## Run 4 — menu-2026-09-12 (shopping-29), ordered 2026-09-12

- Shopping run: **6** (52 items, imported from `~/Downloads/menu-2026-09-12.md`)
- Kitchen walk: 20 ticked, **32 went to the order**
- Nemlig order: **3** — 30 bought, 2 declined, 27 merged basket lines
- Basket result: **39 products, 814,39 kr**
- Map after recording: 90 mappings, 26 stocked, 4 unresolved

### How it was driven

Not the console-snippet path in `OrderPicker.tsx`. The whole run went through
`browser-use` over CDP against the user's own logged-in Chrome, with the app
used as the state/planning/recording store via its HTTP API. That hybrid is
what should be automated — see `docs/nemlig-automation-plan.md`.

### Decisions a human had to make

| Item | Why the ranking could not decide it |
|---|---|
| `hakket okse` | Top-ranked hit was minced **pork** (a favourite). The correct 400 g øko beef was 3rd. Favourites outrank correctness. |
| `tomat` (4 stk) | Nemlig sells no small loose pack; only 1,5 kg boxes. Resolved by buying a 2nd pack of cherry tomatoes instead. |
| `soltørrede tomater` | Correct product was **8th** of 8; the first seven were fresh/chopped tomatoes. |
| `sød sennep` | Query returned sweet potatoes, sweet paprika and tykmælk. Declined — 37,50 kr jar for 1 spsk, dijon already in the house. |
| `cheddar` | Ambiguous against the separate `revet cheddar` row; user chose to merge into an extra bag of grated. |

### Quantity corrections (the important one)

`qty` in the product map is a **stored default from a previous week**, not
derived from the current week's need. Merging then compounds it:

- `revet cheddar` (2) + `revet ost` (2) + `cheddar` (1) = **5 bags / 700 g**,
  against a real need of ~1 pose + 200 g. Corrected to 3.
- `fløde` (1) + `piskefløde` (2) = **3 bottles / 1,5 L**, against a real need
  of 6,5 dl. Corrected to 2.

Both were caught only by reading the merged basket by eye. This is the single
biggest source of silent over-buying and the highest-value thing to fix.

### Substitution

`Æbler Cosmic Crisp` returned **HTTP 200 but landed at quantity 0** — sold out.
`reconcile_basket` caught it correctly. Replaced with `Æbler Joya` (5604123,
same pack, same price) and recorded via the `replaced` payload.

### Unexplained

One basket line appeared that was not added by this run:
`Agurk/spinatjuice m. æble øko.` (5065461, 1 stk, 24,09 kr). The basket was
verified empty (0 lines, 0 products) before the run started. Cause not
established. User chose to keep it. **Watch for this next run** — if it recurs,
suspect a nemlig-side upsell or a bundle attached to one of the added products.

### Bugs found and fixed

1. **`basketSnippet` read the wrong field.** `GetBasket` returns the product id
   as `Id`; only the *search* endpoint calls it `ProductId`. The snippet mapped
   `l.ProductId`, which is `undefined`, which `JSON.stringify` drops — so every
   line arrived id-less and `reconcile` reported the entire basket as missing.
   Fixed in `frontend/src/OrderPicker.tsx`. This means **in-app reconciliation
   has never actually worked**; it silently reported everything missing.

2. **`replaced` with a string 500s.** `record_run` indexes the substitute for
   `product_id`. The frontend has no substitutions UI, so the path was never
   exercised. Now validated with a 400 in `app.py`, with two regression tests
   in `tests/test_orders_api.py`.

### Environment gotchas hit

- `js()` awaits promises by default, so the 31-search loop blew the
  `Runtime.evaluate` IPC timeout. The page work continued regardless — park
  progress on `window` and poll, exactly as `references/browser.md` says.
- The active CDP tab silently became `disctree.dk` mid-run (user browsing), so
  `fetch('/webapi/...')` hit the wrong origin and returned HTML. **Always
  re-resolve the nemlig tab by URL and `switch_tab` before each batch.**
