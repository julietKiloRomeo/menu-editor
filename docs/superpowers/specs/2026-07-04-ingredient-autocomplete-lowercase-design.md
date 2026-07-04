# Ingredient autocomplete + lowercase normalization

Status: approved design (2026-07-04)
Author: brainstorming session

## Summary

Two coupled changes to the recipe forms:

1. Replace the plain `<input>` for ingredient name and unit in the Add and Edit recipe forms with a combobox: type freely, get a dropdown of matching existing values, pick with mouse or keyboard, or keep the free text you typed.
2. Normalize every ingredient key and unit string to lowercase at write time, and run a one-shot migration to lowercase and merge existing data.

Goals: make it easy for the user to reuse existing spellings ("hakkede tomater") instead of inventing variants ("hakket tomat"), and eliminate case-only duplicates (`"Løg"` vs `"løg"`) that currently coexist in the database.

Recipe titles (`navn`) are unchanged.

## Motivation

The database contains mixed-case ingredient keys today (`tests/test_integration_endpoints.py:137-165` explicitly seeds `"Gulerod"` and `"gulerod"` in different recipes to test case-insensitive matching). A `_norm_text`/`_find_key` helper (`app.py:834-854`) papers over this at lookup time, but the underlying data drift makes autocomplete suggestions noisy and complicates any future analytics (shopping list dedup, category assignment, etc.).

Additionally, users typing ingredient names have no visibility into what names already exist, so Danish inflection ("hakkede tomater" vs "hakket tomat") produces near-duplicates that only a human can reconcile.

## Non-goals

- Fuzzy matching that bridges Danish inflection (`hakket` ↔ `hakkede`). Substring + diacritic-insensitive is sufficient for v1. `/api/ingredients/similar` remains available for future use.
- Renaming existing ingredients as a side-effect of autocompleting. The "Bulk rename" tool at `/tools` already does that.
- Category assignment during ingredient entry.
- Preserving brand-name capitalization (user chose full lowercase for consistency).
- Lowercasing recipe titles (`navn`).

## Architecture

Three layers, applied in order:

### 1. Backend normalization (write-time choke point)

Every recipe write already passes through `coerce_ingredients` in `app.py:534-593` — that includes `POST /api/recipes`, `PATCH /api/recipes/<slug>`, and image-based recipe import via `parse_recipe_yaml`. Lowercase both the ingredient key and the unit string there.

Change points in `coerce_ingredients`:
- The dict-input branch (`app.py:551-556`): after `.strip()`, add `.lower()` on the name.
- The final dict assembly (`app.py:585-588`): compute `key = ingredient_name.strip().lower()` and `unit_str = str(unit or "").strip().lower()`, then write `ingredients[key] = {"amount": amount_value, "unit": unit_str}`.

Empty names are still skipped. `_norm_text` / `_find_key` are unchanged and continue to guarantee that API callers can still pass `"Løg"` and hit the (now lowercased) `"løg"` key.

### 2. One-shot data migration

New script: `scripts/migrate_lowercase_ingredients.py`, invoked via `uv run python scripts/migrate_lowercase_ingredients.py [--dry-run]`.

Algorithm:

```
open a single session/transaction

for each Recipe row:
    new_ingredienser, warnings1 = _merge_lowercase(recipe.ingredienser)
    new_extras,       warnings2 = _merge_lowercase(recipe.extras)
    if changed:
        recipe.ingredienser = new_ingredienser
        recipe.extras       = new_extras
        session.add(recipe)
    accumulate warnings (recipe.slug + before/after keys)

for each IngredientConfig row:
    new_name = name.strip().lower()
    if another IngredientConfig row already has that lowercased name:
        delete this row (keep the first surviving row)
    else: update .name in place

for each StapleItem row:
    same dedup treatment against staple's own name column

commit (or rollback on exception; on --dry-run always rollback)

print summary: recipes updated, keys merged, warnings, config/staple dedups
```

`_merge_lowercase(mapping)` returns a new dict:

- Iterate items in insertion order (dicts preserve it).
- For each `(key, {amount, unit})`: `k = key.strip().lower()`, `u = str(unit or '').strip().lower()`.
- If `k` not yet in output → insert.
- If `k` already in output (case-only collision within this recipe):
  - Units match → sum amounts.
  - Units differ → keep the first entry, emit `WARN: recipe=<slug> ingredient=<k> unit mismatch: kept {amount:X, unit:Y}, dropped {amount:X2, unit:Y2}`.

Idempotent: rerunning on already-lowercase data produces zero changes and exits 0.

### 3. Frontend combobox

New shared component: `frontend/src/components/ComboboxInput.tsx`.

Props:

```ts
type Props = {
  value: string
  onChange: (next: string) => void
  suggestions: string[]      // pre-computed, sorted, lowercased pool
  placeholder?: string
  ariaLabel?: string
}
```

Internal state: `open: boolean`, `activeIndex: number`.

Behavior:
- On focus or on type: filter `suggestions` by `foldText(value)` substring; open dropdown if there are matches AND the current typed value isn't already an exact match of a single suggestion.
- Show up to 8 matches.
- `↓` / `↑` cycle `activeIndex`; `Enter` calls `onChange(suggestion)` and closes; `Esc` closes without changing; `Tab` closes and lets normal focus flow continue.
- Mouse click on a row picks it; a `mousedown` document listener closes on outside clicks.
- Free text always accepted — parent `onChange` fires on every keystroke; picking from the list replaces the current value.
- Dropdown is an absolutely-positioned `<div>` beneath the input, styled to match existing dark panels in the app; `z-20`.
- No debouncing (in-memory filter of a few hundred strings is instant).

Used for both ingredient name and unit — one component, two suggestion pools.

Support module: `frontend/src/lib/text.ts` with:

```ts
export function foldText(s: string): string {
  return s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim()
}
```

Mirrors `app.py:_norm_text` semantics. Kept in a shared module so any future feature (duplicate detection, search) can reuse it.

Suggestion pools computed in `App.tsx` alongside the existing `ingredientNames` memo. The exact path into `config` for the canonical name list should be confirmed against the `build_config_payload` shape (`app.py:501-514`) during implementation — the intent is the union of every recipe's ingredienser/extras keys with the canonical `IngredientConfig.name` list:

```ts
const allIngredientNames = useMemo(() => {
  const set = new Set<string>()
  const push = (raw: string | undefined | null) => {
    if (!raw) return
    const v = raw.normalize('NFC').toLowerCase().trim()
    if (v) set.add(v)
  }
  for (const r of recipes) {
    for (const k of Object.keys(r.ingredienser ?? {})) push(k)
    for (const k of Object.keys(r.extras       ?? {})) push(k)
  }
  // canonical names from /api/config — exact path TBD during implementation
  for (const name of canonicalIngredientNames(config)) push(name)
  return Array.from(set).sort()
}, [recipes, config])

const allUnits = useMemo(() => {
  const set = new Set<string>()
  const push = (raw: string | undefined | null) => {
    if (!raw) return
    const v = raw.toLowerCase().trim()
    if (v) set.add(v)
  }
  const collect = (m: Record<string, {unit: string}> | undefined) => {
    for (const v of Object.values(m ?? {})) push(v.unit)
  }
  for (const r of recipes) { collect(r.ingredienser); collect(r.extras) }
  return Array.from(set).sort()
}, [recipes])
```

`canonicalIngredientNames(config)` is a small helper that extracts the canonical `IngredientConfig.name` list from whichever shape `config` actually uses; centralizing it in one place keeps the memo body readable.

Call sites (four in `App.tsx`) replace the raw name and unit `<input>`s with `<ComboboxInput>`:
- Add form ingredients row (~2081-2111)
- Add form extras row (~2122-2152)
- Edit form ingredients row (~2311-2343)
- Edit form extras row (~2351-2384)

The amount field and delete button are unchanged.

## Data model

No schema changes. The `Recipe.ingredienser` / `Recipe.extras` JSON columns keep their existing shape (`{name: {amount, unit}}`) — only the values written to them change.

## Error handling / edge cases

- Empty `suggestions` array → dropdown never opens; component behaves as a plain text input.
- Typed value equals a single exact match → dropdown stays closed (no single-row "you already have this" dropdown).
- Very long names → row uses `truncate` class; full text in `title` attribute.
- Two form rows with the same ingredient name in a single recipe → allowed at the form layer. The frontend payload builder already emits both, and server-side `coerce_ingredients` assembles the final dict key-by-key so the last row overwrites earlier ones with the same lowercased key. This matches today's behavior — no regression.
- Migration on empty DB → prints `0 recipes updated, 0 merges, 0 warnings`, exits 0.
- Migration exception mid-run → single transaction, rollback, print the failing recipe slug and the exception, exit non-zero.
- `--dry-run` → same output, no commit.

## Testing

### Backend

New — `tests/test_ingredient_normalization.py`:
- `test_coerce_ingredients_lowercases_name_and_unit` — POST `/api/recipes` with `"Løg"` / unit `"DL"`; assert stored as `"løg"` / `"dl"`.
- `test_coerce_ingredients_merges_case_variants_in_payload` — POST payload containing both `"Løg"` and `"løg"` in one recipe; assert single lowercased key.
- `test_coerce_ingredients_preserves_recipe_title_case` — POST `navn="Bolognese"`; assert title stays `"Bolognese"`, only ingredient keys are lowered.

New — `tests/test_migrate_lowercase.py`:
- Seed mixed-case keys via direct DB insert (bypassing `coerce_ingredients`) → run migration → assert lowercased and merged.
- Second run is a no-op (idempotency).
- Unit-mismatch collision → warning emitted to stdout, first-wins in output.
- `IngredientConfig` and `StapleItem` dedup on lowercased name.
- `--dry-run` leaves DB unchanged.

Update — `tests/test_integration_endpoints.py:137-165` (`test_ingredient_usage_and_rename_flow`):

Current premise: seed `"Gulerod"` in recipe A and `"gulerod"` in recipe B, then verify usage and rename bridge the case-insensitivity gap via `_find_key`.

New premise: because `coerce_ingredients` now lowercases at write time, both recipes end up with `"gulerod"`. Update assertions to reflect this. The case-insensitive behavior on `/api/ingredients/rename` and `/api/ingredients/usage` still holds (a caller passing `"Gulerod"` finds the `"gulerod"` key via `_find_key`); test that explicitly.

### Frontend

New — `frontend/src/__tests__/comboboxInput.test.tsx`:
- Renders with a suggestions array; typing filters visible items.
- Diacritic-insensitive: typing `"log"` shows `"løg"`; typing `"løg"` shows `"løg"`.
- Keyboard: `↓↓ Enter` picks the second suggestion and closes.
- `Esc` closes without changing the value.
- Free text with zero matches → dropdown hides, `value` retained, `onChange` fires on every keystroke.
- Outside click closes the dropdown.

New — `frontend/src/__tests__/addRecipeAutocomplete.test.tsx`:
- Mount `<App>` on `/add`, mock `GET /api/recipes` to return a recipe with `ingredienser: {"løg": {...}}`.
- Type `"lø"` into the first ingredient row → assert `"løg"` appears in the dropdown → press `Enter` → assert input value becomes `"løg"`.

## File-touch summary

Backend:
- `app.py` — modify `coerce_ingredients` (~lines 551-588) to lowercase name and unit
- `scripts/migrate_lowercase_ingredients.py` — new
- `tests/test_ingredient_normalization.py` — new
- `tests/test_migrate_lowercase.py` — new
- `tests/test_integration_endpoints.py:137-165` — update assertions

Frontend:
- `frontend/src/lib/text.ts` — new (`foldText`)
- `frontend/src/components/ComboboxInput.tsx` — new
- `frontend/src/App.tsx` — replace 4 ingredient-name inputs + 4 unit inputs with `<ComboboxInput>`; add `allIngredientNames` and `allUnits` memos
- `frontend/src/__tests__/comboboxInput.test.tsx` — new
- `frontend/src/__tests__/addRecipeAutocomplete.test.tsx` — new

## Rollout order

1. Backend: `coerce_ingredients` change + normalization tests.
2. Migration script + tests.
3. Run migration on `recipes.db`.
4. Update the affected integration test.
5. Frontend: `foldText` + `ComboboxInput` + tests.
6. Wire `ComboboxInput` into the four call sites in `App.tsx`.

Each step is independently reviewable and revertible.
