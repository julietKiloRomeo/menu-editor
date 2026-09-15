# Automating the weekly run

Goal: next week is one command plus a short confirmation list, instead of the
~20 manual steps in `docs/nemlig-run-log.md` run 4.

## What the run actually is

There are three implementations of this workflow now, and that is the first
problem to resolve:

1. `~/.config/opencode/skills/nemlig-shopping/` — the original file-passing
   pipeline (`prepare.py` → `picker.py` → `basket.py` → `record.py`).
   `AGENTS.md` still points agents here.
2. `frontend/src/OrderPicker.tsx` — the in-app console-snippet flow.
3. The CDP/`browser-use` hybrid actually used in run 4: the app's HTTP API for
   state, the browser for execution.

(3) is the one worth keeping. It needs no copy-paste, and it keeps every
network call inside the user's logged-in tab, which was the design constraint
that ruled out a Python HTTP client in the first place
(`src/core/nemlig.py:8-15`).

## Target flow

```
uv run python scripts/weekly_run.py ~/Downloads/uge_38_2026.json
```

1. Import the export → shopping run. *(exists: `import_menu.py`)*
2. Print the phone URL, wait for the kitchen walk. *(exists)*
3. On resume: open the order from the unticked rows. *(exists: `POST /api/orders`)*
4. Drive the browser: search every query, attach results. *(scripted in run 4)*
5. Auto-accept every row that is mapped, in stock, and quantity-sane.
6. Ask about **only** the exceptions.
7. Add to basket, reconcile, report sold-out. *(scripted in run 4)*
8. Record to the map. *(exists: `POST /api/orders/<id>/record`)*

Steps 1–4, 7 and 8 are already automated or trivially scriptable. **The value
is entirely in steps 5 and 6**, and they depend on the fixes below.

## Blockers, in priority order

### 1. Quantity must come from this week's need, not last week's default

The highest-value fix. Today `qty` is a stored per-ingredient default, so a
week needing 100 g of cheddar orders the same 2 bags as a week needing 400 g,
and merging compounds it (run 4: 5 bags instead of 3, 3 bottles instead of 2).

Wanted: derive quantity from `need` against the product's pack size —
`need 6,5 dl` ÷ `pack 0,5 l` = 2. Store the *pack size* in the map rather than
a `last_qty`, and keep `last_qty` only as a fallback for packs that cannot be
parsed (`1 bundt`, `1 klase`). Anything the calculation cannot decide should be
escalated to the human, not guessed.

Until this lands, no run can be fully unattended without risking silent
over-buying.

### 2. Ranking must not let favourites outrank correctness

`rank_candidates` puts favourites first. In run 4 that surfaced minced **pork**
as the top hit for `hakket okse`, and sweet potatoes for `sød sennep`. A
favourite whose name does not plausibly match the ingredient should be demoted,
not promoted. Cheap first cut: require a token overlap between the ingredient
(or its mapped query) and the product name before the favourite bonus applies.

### 3. Bad queries need to be recorded as such

`soltørrede tomater` ranked its correct product 8th of 8; `sød sennep` never
found mustard at all. The map already has a `query` field per ingredient — when
a human picks a product that the query ranked poorly, write a better query back
so the next run's search is aimed correctly. Run 4 did not do this.

### 4. One source of truth for the workflow

Pick (3), delete or clearly deprecate the other two, and update `AGENTS.md`,
which currently sends agents to the skill with "Do not re-derive the workflow".

## Smaller follow-ups

- `scripts/import_menu.py` has **zero tests** of its own; the format it reads
  is covered by `tests/test_render_export.py`, the CLI around it is not.
- `GET /api/orders/<id>/queries` exists and is tested, but `OrderPicker.tsx`
  re-derives the query list client-side. Two places to drift.
- `GET /api/nemlig/map` and `summarise_map()` are never called by any UI, so
  the map's contents are invisible.
- `MENU_DATA_DIR` defaults to `"."`, so the Shop tab's "start a new walk" list
  shows 13 stale `uge_26_2026*.yaml` files from the repo root. Either point it
  at `menus/` or drop the menu-YAML entry point in favour of the importer.
- `docs/api.md` documents none of `/api/orders/*` or `/api/nemlig/map`.
- No frontend tests cover `OrderPicker.tsx` — including the snippet generation
  where the `ProductId`/`Id` bug lived undetected.

## Reusable scripts from run 4

Kept under `scripts/nemlig/` rather than `/tmp`, since they are the working
parts of the target flow: search-and-attach, add-to-basket, and the
poll-instead-of-await pattern that avoids the `Runtime.evaluate` timeout.
