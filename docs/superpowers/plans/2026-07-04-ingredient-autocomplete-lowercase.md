# Ingredient autocomplete + lowercase normalization — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw ingredient-name and unit `<input>`s on the Add and Edit recipe forms with a combobox backed by existing values, and normalize every ingredient key and unit string to lowercase (with a one-shot migration for existing data).

**Architecture:** Backend lowercases at the single write-time choke point (`coerce_ingredients` in `app.py`). A standalone migration script rewrites existing recipes, `IngredientConfig`, and `StapleItem` rows. Frontend gets a shared `ComboboxInput` component that filters an in-memory pool derived from already-loaded recipes plus the `configItems` state.

**Tech Stack:** Python 3 / Flask / SQLModel / SQLite (backend), pytest (backend tests), React 19 / TypeScript / Vite (frontend), Jest + React Testing Library (frontend tests), `uv` for Python runtime, `bun` for frontend scripts.

**Spec:** `docs/superpowers/specs/2026-07-04-ingredient-autocomplete-lowercase-design.md`

---

## File structure

**Backend:**
- Modify `app.py:534-593` (`coerce_ingredients`) — lowercase ingredient name and unit at the choke point.
- Modify `app.py:475` region (`_canonical_ingredient_cache`) — expose an invalidator.
- Modify `app.py:932-1029` (`ingredient_rename` endpoint) — lowercase the target key so renames don't reintroduce mixed-case data.
- Create `scripts/__init__.py` (empty, to make `scripts` importable in tests).
- Create `scripts/migrate_lowercase_ingredients.py` — one-shot migration, importable and CLI-runnable.
- Create `tests/test_ingredient_normalization.py` — coerce_ingredients unit tests.
- Create `tests/test_migrate_lowercase.py` — migration tests.
- Modify `tests/test_integration_endpoints.py:137-197` — adapt assertions to lowercased storage.

**Frontend:**
- Create `frontend/src/lib/text.ts` — `foldText` helper.
- Create `frontend/src/components/ComboboxInput.tsx` — the shared combobox.
- Modify `frontend/src/App.tsx` — add `allIngredientNames` / `allUnits` memos, replace four `<input>` pairs (ingredient name + unit in each of Add-ingredienser, Add-extras, Edit-ingredienser, Edit-extras).
- Create `frontend/src/__tests__/comboboxInput.test.tsx` — component tests.
- Create `frontend/src/__tests__/addRecipeAutocomplete.test.tsx` — integration test against `<App>` on `/add`.

**Testing commands (used throughout):**
- Backend: `uv run pytest tests/<file>::<test> -v` (single test), `uv run pytest -v` (all).
- Frontend: `bun --cwd frontend run test -- --testPathPattern=<file>` (single), `bun --cwd frontend run test` (all).
- Frontend typecheck+build: `bun --cwd frontend run build`.

---

## Task 1: Backend — lowercase ingredient name and unit in `coerce_ingredients`

**Files:**
- Modify: `app.py:534-593`
- Test: `tests/test_ingredient_normalization.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ingredient_normalization.py`:

```python
"""Ensure ingredient names and units are lowercased at the write choke point."""


def test_coerce_ingredients_lowercases_name(client):
    payload = {
        "navn": "Bolognese",
        "placering": "Notebook",
        "antal": 4,
        "ingredienser": {"Løg": {"amount": 1, "unit": "stk"}},
        "extras": {},
    }
    response = client.post("/api/recipes", json=payload)
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert "løg" in body["ingredienser"]
    assert "Løg" not in body["ingredienser"]


def test_coerce_ingredients_lowercases_unit(client):
    payload = {
        "navn": "Sauce",
        "placering": "Notebook",
        "antal": 2,
        "ingredienser": {"tomat": {"amount": 1, "unit": "DL"}},
        "extras": {},
    }
    response = client.post("/api/recipes", json=payload)
    assert response.status_code == 201
    assert response.get_json()["ingredienser"]["tomat"]["unit"] == "dl"


def test_coerce_ingredients_merges_case_variants_in_payload(client):
    """Same recipe posted with both 'Løg' and 'løg' collapses to a single key."""
    payload = {
        "navn": "Soup",
        "placering": "Notebook",
        "antal": 4,
        "ingredienser": {
            "Løg": {"amount": 1, "unit": "stk"},
            "løg": {"amount": 2, "unit": "stk"},
        },
        "extras": {},
    }
    response = client.post("/api/recipes", json=payload)
    assert response.status_code == 201
    ingredients = response.get_json()["ingredienser"]
    assert list(ingredients.keys()) == ["løg"]
    # Last-write-wins behavior in coerce_ingredients (dict iteration order):
    # value is whichever variant was processed last; either amount is acceptable
    # as long as only one key survives.
    assert ingredients["løg"]["amount"] in (1.0, 2.0)


def test_coerce_ingredients_preserves_recipe_title_case(client):
    payload = {
        "navn": "Bolognese",
        "placering": "Notebook",
        "antal": 4,
        "ingredienser": {"Tomat": {"amount": 2, "unit": "stk"}},
        "extras": {},
    }
    response = client.post("/api/recipes", json=payload)
    assert response.status_code == 201
    body = response.get_json()
    assert body["navn"] == "Bolognese"  # title untouched
    assert "tomat" in body["ingredienser"]  # ingredient key lowercased


def test_coerce_ingredients_extras_also_lowercased(client):
    payload = {
        "navn": "Salad",
        "placering": "Notebook",
        "antal": 2,
        "ingredienser": {"salat": {"amount": 1, "unit": "stk"}},
        "extras": {"Olie": {"amount": 1, "unit": "SPSK"}},
    }
    response = client.post("/api/recipes", json=payload)
    assert response.status_code == 201
    body = response.get_json()
    assert "olie" in body["extras"]
    assert body["extras"]["olie"]["unit"] == "spsk"
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_ingredient_normalization.py -v`
Expected: 5 tests fail. `test_coerce_ingredients_lowercases_name` fails asserting `"løg" in ingredienser` (actual key is `"Løg"`). The unit test fails on `"DL" != "dl"`. The merge test fails because both `"Løg"` and `"løg"` remain as separate keys. Title-preservation test fails on the ingredient key check. Extras test fails on `"Olie"` still being uppercase.

- [ ] **Step 3: Modify `coerce_ingredients` to lowercase name and unit**

In `app.py`, edit lines 551-556 (list-input branch) and 585-588 (final assembly):

At `app.py:551-556`, change:
```python
            name = (
                item.get("navn")
                or item.get("name")
                or item.get("ingredient")
                or ""
            ).strip()
```
to:
```python
            name = (
                item.get("navn")
                or item.get("name")
                or item.get("ingredient")
                or ""
            ).strip().lower()
```

At `app.py:569-588` (the shared loop), change the block:
```python
    for ingredient_name, value in iterable:
        if not ingredient_name:
            continue
        if isinstance(value, dict):
            amount = value.get("amount", 0)
            unit = value.get("unit", "")
        else:
            raise ValueError(f"{field_name.capitalize()} values must be dictionaries")

        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid amount for {field_name[:-1]} '{ingredient_name}'"
            ) from None

        ingredients[ingredient_name] = {
            "amount": amount_value,
            "unit": str(unit or "").strip(),
        }
```
to:
```python
    for ingredient_name, value in iterable:
        key = str(ingredient_name or "").strip().lower()
        if not key:
            continue
        if isinstance(value, dict):
            amount = value.get("amount", 0)
            unit = value.get("unit", "")
        else:
            raise ValueError(f"{field_name.capitalize()} values must be dictionaries")

        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid amount for {field_name[:-1]} '{key}'"
            ) from None

        ingredients[key] = {
            "amount": amount_value,
            "unit": str(unit or "").strip().lower(),
        }
```

Two things changed: `ingredient_name` → `key` (computed as stripped+lowered), and unit adds `.lower()`. The dict-input path (line 542-543) now feeds already-uppercase keys into the same loop, which the new `key` derivation handles.

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_ingredient_normalization.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Run the full backend test suite to spot regressions**

Run: `uv run pytest -v`
Expected: `test_ingredient_usage_and_rename_flow` and `test_ingredient_rename_conflict_detection` may still pass or may fail — we will handle those in Task 5. All other tests should pass. Note any unexpected failures for later triage.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_ingredient_normalization.py
git commit -m "feat(backend): lowercase ingredient name and unit in coerce_ingredients"
```

---

## Task 2: Backend — lowercase the rename target and invalidate canonical cache

**Rationale:** After Task 1, new writes are lowercased. But `/api/ingredients/rename` (`app.py:932-1029`) still writes the caller's `to_name` verbatim, which lets a rename re-introduce mixed-case keys (e.g., renaming to `"Gulerod Deluxe"` would store `"Gulerod Deluxe"`). Fix it there too. Also, `_canonical_ingredient_cache` (`app.py:475, 489-498`) never invalidates — after the migration in Task 4, cached names would be stale until process restart.

**Files:**
- Modify: `app.py:932-946` (rename endpoint input handling)
- Modify: `app.py:475-498` (add invalidator)
- Test: `tests/test_ingredient_normalization.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ingredient_normalization.py`:

```python
def test_ingredient_rename_lowercases_target(client):
    """Rename endpoint must store the target key as lowercased, not as passed."""
    seed = {
        "navn": "Carrot Soup",
        "placering": "Notebook",
        "antal": 2,
        "ingredienser": {"gulerod": {"amount": 2, "unit": "stk"}},
        "extras": {},
    }
    resp = client.post("/api/recipes", json=seed)
    assert resp.status_code == 201
    slug = resp.get_json()["slug"]

    rename = client.post(
        "/api/ingredients/rename",
        json={"from": "gulerod", "to": "Baby Carrot", "include_extras": True},
    )
    assert rename.status_code == 200
    assert rename.get_json()["updated_count"] == 1

    updated = client.get(f"/api/recipes/{slug}").get_json()
    assert "baby carrot" in updated["ingredienser"]
    assert "Baby Carrot" not in updated["ingredienser"]


def test_invalidate_canonical_ingredient_cache_exists(app_module):
    """The module must expose invalidate_canonical_ingredient_cache()."""
    assert hasattr(app_module, "invalidate_canonical_ingredient_cache")
    # First call populates the cache; invalidation clears it.
    app_module.get_canonical_ingredient_names()
    assert app_module._canonical_ingredient_cache is not None
    app_module.invalidate_canonical_ingredient_cache()
    assert app_module._canonical_ingredient_cache is None
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_ingredient_normalization.py::test_ingredient_rename_lowercases_target tests/test_ingredient_normalization.py::test_invalidate_canonical_ingredient_cache_exists -v`
Expected: rename test fails (stored key is `"Baby Carrot"`); cache test fails with `AttributeError` on `invalidate_canonical_ingredient_cache`.

- [ ] **Step 3: Lowercase the rename target**

In `app.py:932-946`, change:
```python
    from_name = (payload.get('from') or '').strip()
    to_name = (payload.get('to') or '').strip()
```
to:
```python
    from_name = (payload.get('from') or '').strip()
    to_name = (payload.get('to') or '').strip().lower()
```
(Only `to_name` gets `.lower()`. `from_name` stays unmodified because `_find_key` handles case-insensitive matching for lookup.)

- [ ] **Step 4: Add the cache invalidator**

In `app.py:475-498`, replace:
```python
_canonical_ingredient_cache: list[str] | None = None


def fetch_config() -> tuple[list[CategoryConfig], list[IngredientConfig]]:
    ...


def get_canonical_ingredient_names() -> list[str]:
    global _canonical_ingredient_cache
    if _canonical_ingredient_cache is not None:
        return _canonical_ingredient_cache

    _, items = fetch_config()
    names = [item.name for item in items if item.name]

    _canonical_ingredient_cache = names
    return names
```
with:
```python
_canonical_ingredient_cache: list[str] | None = None


def fetch_config() -> tuple[list[CategoryConfig], list[IngredientConfig]]:
    ...  # UNCHANGED - do not modify fetch_config


def invalidate_canonical_ingredient_cache() -> None:
    """Drop the memoized canonical ingredient list.

    Called after any mutation that could rename/add/remove an IngredientConfig
    row (rename endpoint, migration script, config CRUD).
    """
    global _canonical_ingredient_cache
    _canonical_ingredient_cache = None


def get_canonical_ingredient_names() -> list[str]:
    global _canonical_ingredient_cache
    if _canonical_ingredient_cache is not None:
        return _canonical_ingredient_cache

    _, items = fetch_config()
    names = [item.name for item in items if item.name]

    _canonical_ingredient_cache = names
    return names
```

(Do NOT paste-edit the `fetch_config` function — leave it exactly as-is. The `...` in this snippet is only for readability. Only insert the new `invalidate_canonical_ingredient_cache` function between `fetch_config` and `get_canonical_ingredient_names`.)

- [ ] **Step 5: Wire the invalidator into the rename endpoint**

In `app.py`, at the very end of `ingredient_rename` (`app.py:1025-1026`, right before the successful `return jsonify(...)`), add a call:
```python
            session.commit()
        invalidate_canonical_ingredient_cache()
        return jsonify({"updated_count": updated_count, "conflicts": conflicts})
```
(The `session.commit()` line is existing at 1025; the `invalidate_canonical_ingredient_cache()` line is new. Placement is outside the `with get_session()` block, before `return`.)

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_ingredient_normalization.py -v`
Expected: all 7 tests pass.

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_ingredient_normalization.py
git commit -m "feat(backend): lowercase rename target + expose canonical cache invalidator"
```

---

## Task 3: Backend — migration helpers (pure functions, no DB)

**Rationale:** The migration script has two responsibilities: iterate the DB and normalize each dict. Split the dict-normalization out as a pure function so it's unit-testable without a session.

**Files:**
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/migrate_lowercase_ingredients.py` (helper functions only in this task; CLI in Task 4)
- Create: `tests/test_migrate_lowercase.py`

- [ ] **Step 1: Create the `scripts` package**

Create empty `scripts/__init__.py`:
```python
```
(zero-byte file; needed so `from scripts.migrate_lowercase_ingredients import ...` works in pytest.)

- [ ] **Step 2: Write the failing tests**

Create `tests/test_migrate_lowercase.py`:

```python
"""Unit tests for the migration helper functions."""

from scripts.migrate_lowercase_ingredients import merge_lowercase


def test_merge_lowercase_lowercases_keys_and_units():
    result, warnings = merge_lowercase(
        {"Løg": {"amount": 1, "unit": "STK"}, "Tomat": {"amount": 2, "unit": "dl"}}
    )
    assert result == {
        "løg": {"amount": 1.0, "unit": "stk"},
        "tomat": {"amount": 2.0, "unit": "dl"},
    }
    assert warnings == []


def test_merge_lowercase_sums_amounts_when_units_match():
    result, warnings = merge_lowercase(
        {"Løg": {"amount": 1, "unit": "stk"}, "løg": {"amount": 2, "unit": "stk"}}
    )
    assert result == {"løg": {"amount": 3.0, "unit": "stk"}}
    assert warnings == []


def test_merge_lowercase_keeps_first_on_unit_mismatch_and_warns():
    result, warnings = merge_lowercase(
        {"Løg": {"amount": 1, "unit": "stk"}, "løg": {"amount": 200, "unit": "g"}}
    )
    assert result == {"løg": {"amount": 1.0, "unit": "stk"}}
    assert len(warnings) == 1
    assert "unit mismatch" in warnings[0]
    assert "løg" in warnings[0]


def test_merge_lowercase_skips_empty_keys():
    result, warnings = merge_lowercase(
        {"": {"amount": 1, "unit": "stk"}, "   ": {"amount": 2, "unit": "stk"}}
    )
    assert result == {}
    assert warnings == []


def test_merge_lowercase_handles_none_mapping():
    result, warnings = merge_lowercase(None)
    assert result == {}
    assert warnings == []


def test_merge_lowercase_handles_non_numeric_amount_gracefully():
    """If amount is a string like '2', it's normalized to float; if garbage, kept as-is."""
    result, _ = merge_lowercase({"tomat": {"amount": "2", "unit": "stk"}})
    assert result["tomat"]["amount"] == 2.0


def test_merge_lowercase_is_idempotent():
    already_normal = {"tomat": {"amount": 2.0, "unit": "stk"}}
    first, _ = merge_lowercase(already_normal)
    second, _ = merge_lowercase(first)
    assert first == second == already_normal
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_migrate_lowercase.py -v`
Expected: all 7 fail with `ModuleNotFoundError` on `scripts.migrate_lowercase_ingredients`.

- [ ] **Step 4: Implement `merge_lowercase`**

Create `scripts/migrate_lowercase_ingredients.py`:

```python
"""One-shot migration: lowercase all ingredient keys and unit strings.

Run:
    uv run python scripts/migrate_lowercase_ingredients.py           # commit
    uv run python scripts/migrate_lowercase_ingredients.py --dry-run # preview

Idempotent: re-running on already-lowercased data changes nothing.
"""

from __future__ import annotations

from typing import Any


def merge_lowercase(
    mapping: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Normalize a single ingredienser/extras mapping to lowercase.

    Rules:
      - Keys are stripped and lowercased.
      - Units are stripped and lowercased.
      - Amounts are coerced to float; non-numeric amounts fall back to the raw value.
      - Case-only key collisions merge: same unit → sum amounts; different unit →
        keep the first-seen entry, emit a warning.

    Returns:
        (new_mapping, warnings).
    """
    if not mapping:
        return {}, []

    out: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for raw_key, raw_val in mapping.items():
        key = str(raw_key or "").strip().lower()
        if not key:
            continue

        val = raw_val or {}
        raw_amount = val.get("amount", 0)
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            amount = raw_amount  # preserve for human inspection
        unit = str(val.get("unit") or "").strip().lower()

        if key not in out:
            out[key] = {"amount": amount, "unit": unit}
            continue

        # Collision. Three cases:
        #   - Units match AND both amounts numeric -> sum.
        #   - Units match BUT one amount is non-numeric -> keep first, warn (amount issue).
        #   - Units differ -> keep first, warn (unit mismatch).
        existing = out[key]
        amounts_are_numeric = isinstance(existing["amount"], (int, float)) and isinstance(amount, (int, float))
        if existing["unit"] == unit and amounts_are_numeric:
            existing["amount"] = float(existing["amount"]) + float(amount)
        elif existing["unit"] != unit:
            warnings.append(
                f"unit mismatch on '{key}': kept "
                f"{{amount:{existing['amount']}, unit:{existing['unit']!r}}}, "
                f"dropped {{amount:{amount}, unit:{unit!r}}}"
            )
        else:
            warnings.append(
                f"non-numeric amount on '{key}': kept "
                f"{{amount:{existing['amount']!r}, unit:{existing['unit']!r}}}, "
                f"dropped {{amount:{amount!r}, unit:{unit!r}}}"
            )

    return out, warnings
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_migrate_lowercase.py -v`
Expected: all 7 pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/migrate_lowercase_ingredients.py tests/test_migrate_lowercase.py
git commit -m "feat(backend): migration helper merge_lowercase (pure)"
```

---

## Task 4: Backend — migration script CLI + DB integration

**Files:**
- Modify: `scripts/migrate_lowercase_ingredients.py` (add `run_migration` + CLI)
- Modify: `tests/test_migrate_lowercase.py` (add DB integration tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_migrate_lowercase.py`:

```python
"""DB integration tests for the migration script."""

from sqlmodel import select

from scripts.migrate_lowercase_ingredients import run_migration


def test_run_migration_lowercases_recipe_keys(app_module, models):
    # Seed a recipe with mixed-case keys, bypassing coerce_ingredients so we
    # can plant the exact bad data we want to migrate.
    with app_module.get_session() as session:
        recipe = models.Recipe(
            slug="test-mix",
            navn="Test Mix",
            placering="Notebook",
            antal=4,
            ingredienser={
                "Løg": {"amount": 1, "unit": "stk"},
                "løg": {"amount": 2, "unit": "stk"},  # will merge with Løg
                "Tomat": {"amount": 3, "unit": "DL"},
            },
            extras={"Salt": {"amount": 1, "unit": "TSK"}},
        )
        session.add(recipe)
        session.commit()

    summary = run_migration(dry_run=False)

    assert summary["recipes_updated"] == 1
    with app_module.get_session() as session:
        r = session.exec(select(models.Recipe).where(models.Recipe.slug == "test-mix")).one()
        assert r.ingredienser == {
            "løg": {"amount": 3.0, "unit": "stk"},
            "tomat": {"amount": 3.0, "unit": "dl"},
        }
        assert r.extras == {"salt": {"amount": 1.0, "unit": "tsk"}}


def test_run_migration_is_idempotent(app_module, models):
    with app_module.get_session() as session:
        recipe = models.Recipe(
            slug="already-lc",
            navn="Already LC",
            placering="Notebook",
            antal=2,
            ingredienser={"tomat": {"amount": 1.0, "unit": "dl"}},
            extras={},
        )
        session.add(recipe)
        session.commit()

    first = run_migration(dry_run=False)
    second = run_migration(dry_run=False)

    assert first["recipes_updated"] == 0
    assert second["recipes_updated"] == 0


def test_run_migration_dry_run_leaves_db_unchanged(app_module, models):
    with app_module.get_session() as session:
        recipe = models.Recipe(
            slug="dry-mix",
            navn="Dry Mix",
            placering="Notebook",
            antal=2,
            ingredienser={"Løg": {"amount": 1, "unit": "stk"}},
            extras={},
        )
        session.add(recipe)
        session.commit()

    summary = run_migration(dry_run=True)
    assert summary["recipes_updated"] == 1  # would have updated

    with app_module.get_session() as session:
        r = session.exec(select(models.Recipe).where(models.Recipe.slug == "dry-mix")).one()
        assert "Løg" in r.ingredienser  # still uppercase


def test_run_migration_deduplicates_ingredient_config(app_module, models):
    with app_module.get_session() as session:
        cat = models.CategoryConfig(name="Produce", priority=0)
        session.add(cat)
        session.commit()
        session.refresh(cat)
        session.add(models.IngredientConfig(name="Løg", category_id=cat.id))
        session.add(models.IngredientConfig(name="løg", category_id=cat.id))
        session.commit()

    summary = run_migration(dry_run=False)
    assert summary["ingredient_config_dedupes"] == 1

    with app_module.get_session() as session:
        rows = session.exec(
            select(models.IngredientConfig).where(models.IngredientConfig.name == "løg")
        ).all()
        assert len(rows) == 1


def test_run_migration_deduplicates_staples(app_module, models):
    with app_module.get_session() as session:
        session.add(models.StapleItem(name="Salt"))
        session.add(models.StapleItem(name="salt"))
        session.commit()

    summary = run_migration(dry_run=False)
    assert summary["staple_dedupes"] == 1

    with app_module.get_session() as session:
        rows = session.exec(
            select(models.StapleItem).where(models.StapleItem.name == "salt")
        ).all()
        assert len(rows) == 1


def test_run_migration_returns_warnings_on_unit_mismatch(app_module, models):
    with app_module.get_session() as session:
        recipe = models.Recipe(
            slug="mismatch",
            navn="Mismatch",
            placering="Notebook",
            antal=2,
            ingredienser={
                "Løg": {"amount": 1, "unit": "stk"},
                "løg": {"amount": 200, "unit": "g"},
            },
            extras={},
        )
        session.add(recipe)
        session.commit()

    summary = run_migration(dry_run=False)
    assert len(summary["warnings"]) == 1
    assert "mismatch" in summary["warnings"][0]
    assert "unit mismatch" in summary["warnings"][0]


def test_run_migration_invalidates_canonical_cache(app_module, models):
    # Prime the cache
    app_module.get_canonical_ingredient_names()
    assert app_module._canonical_ingredient_cache is not None
    run_migration(dry_run=False)
    assert app_module._canonical_ingredient_cache is None
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/test_migrate_lowercase.py -v`
Expected: 7 new tests fail on `ImportError` for `run_migration`. Existing 7 helper tests still pass.

- [ ] **Step 3: Implement `run_migration` and the CLI**

Append to `scripts/migrate_lowercase_ingredients.py`:

```python
import argparse
import sys
from typing import Any


def run_migration(*, dry_run: bool = False) -> dict[str, Any]:
    """Iterate the DB, lowercase and merge ingredient data, dedupe config rows.

    Returns a summary dict:
      {
        "recipes_updated": int,
        "ingredient_config_dedupes": int,
        "staple_dedupes": int,
        "warnings": list[str],
      }

    Imports are inside the function so `merge_lowercase` remains importable
    without pulling in the whole Flask app (helper tests don't need it).
    """
    import app as app_module
    import src.models as models
    from sqlmodel import select

    recipes_updated = 0
    ingredient_config_dedupes = 0
    staple_dedupes = 0
    warnings: list[str] = []

    with app_module.get_session() as session:
        # --- recipes ---
        for recipe in session.exec(select(models.Recipe)).all():
            new_ing, warn1 = merge_lowercase(recipe.ingredienser)
            new_ext, warn2 = merge_lowercase(recipe.extras)
            for w in warn1 + warn2:
                warnings.append(f"recipe={recipe.slug}: {w}")
            if new_ing != (recipe.ingredienser or {}) or new_ext != (recipe.extras or {}):
                recipe.ingredienser = new_ing
                recipe.extras = new_ext
                session.add(recipe)
                recipes_updated += 1

        # --- IngredientConfig: lowercase + dedupe on lowercased name ---
        seen: dict[str, models.IngredientConfig] = {}
        for row in session.exec(select(models.IngredientConfig)).all():
            lc = (row.name or "").strip().lower()
            if not lc:
                session.delete(row)
                continue
            if lc in seen:
                session.delete(row)
                ingredient_config_dedupes += 1
            else:
                if row.name != lc:
                    row.name = lc
                    session.add(row)
                seen[lc] = row

        # --- StapleItem: lowercase + dedupe on lowercased name ---
        seen_staples: dict[str, models.StapleItem] = {}
        for row in session.exec(select(models.StapleItem)).all():
            lc = (row.name or "").strip().lower()
            if not lc:
                session.delete(row)
                continue
            if lc in seen_staples:
                session.delete(row)
                staple_dedupes += 1
            else:
                if row.name != lc:
                    row.name = lc
                    session.add(row)
                seen_staples[lc] = row

        if dry_run:
            session.rollback()
        else:
            session.commit()

    if not dry_run:
        app_module.invalidate_canonical_ingredient_cache()

    return {
        "recipes_updated": recipes_updated,
        "ingredient_config_dedupes": ingredient_config_dedupes,
        "staple_dedupes": staple_dedupes,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="Preview without committing.")
    args = parser.parse_args(argv)

    summary = run_migration(dry_run=args.dry_run)

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}Recipes updated:          {summary['recipes_updated']}")
    print(f"{prefix}IngredientConfig dedupes: {summary['ingredient_config_dedupes']}")
    print(f"{prefix}StapleItem dedupes:       {summary['staple_dedupes']}")
    if summary["warnings"]:
        print(f"{prefix}Warnings ({len(summary['warnings'])}):")
        for w in summary["warnings"]:
            print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/test_migrate_lowercase.py -v`
Expected: all 14 tests pass (7 helper + 7 integration).

- [ ] **Step 5: Dry-run the migration against the real DB**

Run: `uv run python scripts/migrate_lowercase_ingredients.py --dry-run`
Expected: output shows the counts of what would change, prints any warnings, but does not modify `recipes.db`. Verify by running twice — output should be identical.

- [ ] **Step 6: Take a backup and run the migration for real**

```bash
cp recipes.db recipes.db.pre-lowercase-migration.bak
uv run python scripts/migrate_lowercase_ingredients.py
```
Expected: same counts as the dry-run. Review any warnings — those are cases where a human might want to reconcile manually.

- [ ] **Step 7: Confirm idempotency on the real DB**

Run: `uv run python scripts/migrate_lowercase_ingredients.py`
Expected: `Recipes updated: 0`, `IngredientConfig dedupes: 0`, `StapleItem dedupes: 0`, no warnings.

- [ ] **Step 8: Commit**

```bash
git add scripts/migrate_lowercase_ingredients.py tests/test_migrate_lowercase.py
git commit -m "feat(backend): migration script for lowercase normalization"
```

Do NOT commit `recipes.db` or the `.bak` file (they should already be gitignored; verify with `git status`).

---

## Task 5: Backend — update existing integration test assertions

**Rationale:** After Tasks 1-4, `test_ingredient_usage_and_rename_flow` and `test_ingredient_rename_conflict_detection` need their premises updated because the DB no longer stores mixed-case keys. The behavior these tests exist to verify (case-insensitive lookup via `_find_key`, conflict detection, force merges) still holds — the fixtures just look different.

**Files:**
- Modify: `tests/test_integration_endpoints.py:137-197`

- [ ] **Step 1: Run the two tests to see current state**

Run: `uv run pytest tests/test_integration_endpoints.py::test_ingredient_usage_and_rename_flow tests/test_integration_endpoints.py::test_ingredient_rename_conflict_detection -v`
Expected: both may pass or fail. Passing means the assertions still hold with lowercased storage — good, we still want to tighten them. Failing means we need to update. Read the output carefully before proceeding.

- [ ] **Step 2: Replace `test_ingredient_usage_and_rename_flow`**

In `tests/test_integration_endpoints.py`, replace lines 137-165 with:

```python
def test_ingredient_usage_and_rename_flow(client):
    """Verifies case-insensitive matching still works even though storage is lowercase."""
    recipe_one = recipe_payload(
        navn="Carrot Soup",
        ingredienser={
            "Gulerod": {"amount": 2, "unit": "stk"},  # server stores as "gulerod"
            "Kartoffel": {"amount": 3, "unit": "stk"},
        },
        extras={},
    )
    recipe_two = recipe_payload(
        navn="Garden Salad",
        ingredienser={"gulerod": {"amount": 1, "unit": "stk"}},
        extras={"Gulerod": {"amount": 1, "unit": "bund"}},  # extras uses same key, different field
    )
    resp1 = client.post("/api/recipes", json=recipe_one)
    resp2 = client.post("/api/recipes", json=recipe_two)
    assert resp1.status_code == 201 and resp2.status_code == 201

    # Confirm storage is lowercased
    assert "gulerod" in resp1.get_json()["ingredienser"]
    assert "Gulerod" not in resp1.get_json()["ingredienser"]

    # Usage lookup works with mixed-case query (via _find_key)
    usage = client.get(
        "/api/ingredients/usage",
        query_string={"name": "Gulerod", "include_extras": "true"},
    )
    assert usage.status_code == 200
    usages = usage.get_json()["usages"]
    # 2 recipes in ingredienser + 1 in extras = 3
    assert len(usages) == 3

    # Rename target gets lowercased on write
    rename = client.post(
        "/api/ingredients/rename",
        json={"from": "gulerod", "to": "Gulerod Deluxe", "include_extras": True},
    )
    assert rename.status_code == 200
    body = rename.get_json()
    assert body["updated_count"] >= 1
    assert not body["conflicts"]

    # Confirm renamed key is lowercased on disk
    updated = client.get(f"/api/recipes/{resp1.get_json()['slug']}").get_json()
    assert "gulerod deluxe" in updated["ingredienser"]
    assert "Gulerod Deluxe" not in updated["ingredienser"]
```

- [ ] **Step 3: Replace `test_ingredient_rename_conflict_detection`**

Replace lines 168-197 with:

```python
def test_ingredient_rename_conflict_detection(client):
    """Conflict detection triggers on lowercased target key collisions."""
    payload = recipe_payload(
        navn="Carrot Mash",
        ingredienser={
            "Gulerod": {"amount": 200, "unit": "g"},              # stored as "gulerod"
            "Gulerod Deluxe": {"amount": 2, "unit": "stk"},       # stored as "gulerod deluxe"
        },
    )
    client.post("/api/recipes", json=payload)

    # Rename "gulerod" -> "Gulerod Deluxe" (target lowercases to "gulerod deluxe",
    # which already exists with a different unit — conflict.)
    conflict = client.post(
        "/api/ingredients/rename",
        json={"from": "Gulerod", "to": "Gulerod Deluxe", "include_extras": False},
    )
    assert conflict.status_code == 200
    conflict_payload = conflict.get_json()
    assert conflict_payload["conflicts"]

    forced = client.post(
        "/api/ingredients/rename",
        json={
            "from": "Gulerod",
            "to": "Gulerod Deluxe",
            "include_extras": False,
            "force": True,
        },
    )
    assert forced.status_code == 200
    forced_payload = forced.get_json()
    assert any("conflict" in entry["reason"] for entry in forced_payload["conflicts"])
```

- [ ] **Step 4: Run the two tests to confirm they pass**

Run: `uv run pytest tests/test_integration_endpoints.py::test_ingredient_usage_and_rename_flow tests/test_integration_endpoints.py::test_ingredient_rename_conflict_detection -v`
Expected: both pass.

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_integration_endpoints.py
git commit -m "test(backend): adapt ingredient rename tests to lowercase storage"
```

---

## Task 6: Frontend — `foldText` helper

**Files:**
- Create: `frontend/src/lib/text.ts`
- Create: `frontend/src/__tests__/foldText.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/__tests__/foldText.test.ts`:

```typescript
import { foldText } from '../lib/text'

describe('foldText', () => {
  test('lowercases ascii', () => {
    expect(foldText('Løg')).toBe('log')
  })

  test('strips diacritics', () => {
    expect(foldText('Café')).toBe('cafe')
    expect(foldText('Løg')).toBe('log')
    expect(foldText('Æble')).toBe('aeble')
    expect(foldText('Rødvin')).toBe('rodvin')
  })

  test('trims whitespace', () => {
    expect(foldText('  Tomat  ')).toBe('tomat')
  })

  test('handles empty string', () => {
    expect(foldText('')).toBe('')
  })

  test('is idempotent', () => {
    const once = foldText('Hakkede Tomater')
    expect(foldText(once)).toBe(once)
  })
})
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `bun --cwd frontend run test -- --testPathPattern=foldText`
Expected: fails with module-not-found on `../lib/text`.

- [ ] **Step 3: Implement `foldText`**

Create `frontend/src/lib/text.ts`:

```typescript
/**
 * Fold a string for case- and diacritic-insensitive matching.
 *
 * Mirrors backend `_norm_text` (app.py:834-842):
 *   NFKD-normalize, strip combining marks, lowercase, trim.
 *
 * Note: Danish 'æ' decomposes into 'ae' under NFKD, so 'Æble' → 'aeble'.
 * This is intentional and matches the backend behavior.
 */
export function foldText(s: string): string {
  return s
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
}
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `bun --cwd frontend run test -- --testPathPattern=foldText`
Expected: all 5 tests pass.

**Note:** The `Æ` → `aeble` assumption is a common gotcha. Verify empirically — some runtimes fold `Æ` as `ae`, others as `æ` (which then lowercases to itself). If the test fails on that specific line, the assertion is what needs to change to match observed behavior, NOT the implementation. Adjust the test to reflect whatever `'Æble'.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()` actually produces in the Jest environment (log it once, then update the assertion).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/text.ts frontend/src/__tests__/foldText.test.ts
git commit -m "feat(frontend): foldText helper for case/diacritic-insensitive matching"
```

---

## Task 7: Frontend — `ComboboxInput` component

**Files:**
- Create: `frontend/src/components/ComboboxInput.tsx`
- Create: `frontend/src/__tests__/comboboxInput.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/__tests__/comboboxInput.test.tsx`:

```typescript
import React, { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { ComboboxInput } from '../components/ComboboxInput'

function Harness({
  suggestions,
  initial = '',
  onChange,
}: {
  suggestions: string[]
  initial?: string
  onChange?: (v: string) => void
}) {
  const [value, setValue] = useState(initial)
  return (
    <ComboboxInput
      value={value}
      onChange={(v) => {
        setValue(v)
        onChange?.(v)
      }}
      suggestions={suggestions}
      ariaLabel="ingredient"
    />
  )
}

test('typing filters visible suggestions', () => {
  render(<Harness suggestions={['løg', 'hakkede tomater', 'kartoffel']} />)
  const input = screen.getByLabelText('ingredient') as HTMLInputElement
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'tom' } })
  expect(screen.getByText('hakkede tomater')).toBeInTheDocument()
  expect(screen.queryByText('løg')).not.toBeInTheDocument()
})

test('diacritic-insensitive matching', () => {
  render(<Harness suggestions={['løg', 'rødvin']} />)
  const input = screen.getByLabelText('ingredient') as HTMLInputElement
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'log' } })
  expect(screen.getByText('løg')).toBeInTheDocument()
})

test('arrow down + enter picks the highlighted suggestion', () => {
  const onChange = jest.fn()
  render(
    <Harness suggestions={['løg', 'hakkede tomater', 'kartoffel']} onChange={onChange} />,
  )
  const input = screen.getByLabelText('ingredient') as HTMLInputElement
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: '' } })
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  fireEvent.keyDown(input, { key: 'Enter' })
  // Third value (activeIndex 1 after two arrow-downs from -1) is 'kartoffel' if
  // suggestions are sorted alphabetically: ['hakkede tomater', 'kartoffel', 'løg'].
  // We assert on whatever the second alphabetical entry is.
  expect(onChange).toHaveBeenLastCalledWith('kartoffel')
})

test('Escape closes the dropdown without changing value', () => {
  render(<Harness suggestions={['løg']} initial="typing" />)
  const input = screen.getByLabelText('ingredient') as HTMLInputElement
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'lø' } })
  expect(screen.getByText('løg')).toBeInTheDocument()
  fireEvent.keyDown(input, { key: 'Escape' })
  expect(screen.queryByText('løg')).not.toBeInTheDocument()
  expect(input.value).toBe('lø')
})

test('free text with zero matches keeps the input value', () => {
  const onChange = jest.fn()
  render(<Harness suggestions={['løg']} onChange={onChange} />)
  const input = screen.getByLabelText('ingredient') as HTMLInputElement
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'totally-new-ingredient' } })
  expect(screen.queryByText('løg')).not.toBeInTheDocument()
  expect(onChange).toHaveBeenLastCalledWith('totally-new-ingredient')
})

test('clicking outside closes the dropdown', () => {
  render(
    <div>
      <Harness suggestions={['løg']} />
      <button>outside</button>
    </div>,
  )
  const input = screen.getByLabelText('ingredient') as HTMLInputElement
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'lø' } })
  expect(screen.getByText('løg')).toBeInTheDocument()
  fireEvent.mouseDown(screen.getByText('outside'))
  expect(screen.queryByText('løg')).not.toBeInTheDocument()
})

test('exact single-match keeps dropdown closed', () => {
  render(<Harness suggestions={['løg']} initial="løg" />)
  const input = screen.getByLabelText('ingredient') as HTMLInputElement
  fireEvent.focus(input)
  // Value already matches exactly — no dropdown row for a single exact match.
  expect(screen.queryByText('løg')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `bun --cwd frontend run test -- --testPathPattern=comboboxInput`
Expected: all 7 fail with module-not-found on `../components/ComboboxInput`.

- [ ] **Step 3: Implement `ComboboxInput`**

Create `frontend/src/components/ComboboxInput.tsx`:

```typescript
import { useEffect, useMemo, useRef, useState } from 'react'
import { foldText } from '../lib/text'

const MAX_SUGGESTIONS = 8

type Props = {
  value: string
  onChange: (next: string) => void
  suggestions: string[]
  placeholder?: string
  ariaLabel?: string
  className?: string
}

export function ComboboxInput({
  value,
  onChange,
  suggestions,
  placeholder,
  ariaLabel,
  className,
}: Props): JSX.Element {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const rootRef = useRef<HTMLDivElement | null>(null)

  const matches = useMemo(() => {
    const q = foldText(value)
    if (!q) return suggestions.slice(0, MAX_SUGGESTIONS)
    return suggestions.filter((s) => foldText(s).includes(q)).slice(0, MAX_SUGGESTIONS)
  }, [value, suggestions])

  const shouldShow =
    open &&
    matches.length > 0 &&
    // Suppress dropdown when the current input exactly matches the only suggestion.
    !(matches.length === 1 && foldText(matches[0]) === foldText(value))

  useEffect(() => {
    if (!shouldShow) return
    function handleMouseDown(event: MouseEvent) {
      if (!rootRef.current) return
      if (!rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [shouldShow])

  // Reset the highlighted row when the visible matches change.
  useEffect(() => {
    setActiveIndex(-1)
  }, [value, suggestions])

  function pick(suggestion: string) {
    onChange(suggestion)
    setOpen(false)
    setActiveIndex(-1)
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!shouldShow) {
      if (event.key === 'ArrowDown' && matches.length > 0) {
        setOpen(true)
        setActiveIndex(0)
        event.preventDefault()
      }
      return
    }
    if (event.key === 'ArrowDown') {
      setActiveIndex((i) => (i + 1) % matches.length)
      event.preventDefault()
    } else if (event.key === 'ArrowUp') {
      setActiveIndex((i) => (i <= 0 ? matches.length - 1 : i - 1))
      event.preventDefault()
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      pick(matches[activeIndex])
      event.preventDefault()
    } else if (event.key === 'Escape') {
      setOpen(false)
      event.preventDefault()
    } else if (event.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <input
        type="text"
        aria-label={ariaLabel}
        value={value}
        placeholder={placeholder}
        className={className}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value)
          setOpen(true)
        }}
        onKeyDown={handleKeyDown}
        autoComplete="off"
      />
      {shouldShow && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-lg border border-white/10 bg-brand-dark/95 shadow-lg backdrop-blur"
        >
          {matches.map((s, i) => (
            <li
              key={s}
              role="option"
              aria-selected={i === activeIndex}
              title={s}
              className={`cursor-pointer truncate px-3 py-2 text-sm ${
                i === activeIndex ? 'bg-brand-accent/20 text-white' : 'text-white/80 hover:bg-white/5'
              }`}
              // Use onMouseDown so the click fires before onBlur closes the dropdown.
              onMouseDown={(event) => {
                event.preventDefault()
                pick(s)
              }}
            >
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `bun --cwd frontend run test -- --testPathPattern=comboboxInput`
Expected: all 7 tests pass. If the "arrow down + enter picks the highlighted suggestion" test fails because sort order in the harness doesn't match your assumption, adjust the expected value in the test to the actual second alphabetical entry from `['løg', 'hakkede tomater', 'kartoffel'].sort()`. The component itself receives suggestions as-is — sorting is the caller's job.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ComboboxInput.tsx frontend/src/__tests__/comboboxInput.test.tsx
git commit -m "feat(frontend): ComboboxInput component with keyboard nav and diacritic-insensitive filter"
```

---

## Task 8: Frontend — wire ComboboxInput into Add-recipe form

**Files:**
- Modify: `frontend/src/App.tsx` (add memos + replace 4 inputs in the Add form)
- Create: `frontend/src/__tests__/addRecipeAutocomplete.test.tsx`

- [ ] **Step 1: Write the failing integration test**

Create `frontend/src/__tests__/addRecipeAutocomplete.test.tsx`:

```typescript
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

beforeEach(() => {
  ;(global.fetch as any) = jest.fn((url: string) => {
    if (typeof url === 'string' && url.endsWith('/api/recipes')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: async () => [
          {
            slug: 'test',
            navn: 'Test',
            placering: 'Notebook',
            antal: 4,
            ingredienser: { 'løg': { amount: 1, unit: 'stk' } },
            extras: {},
            is_blacklisted: false,
            is_whitelisted: false,
          },
        ],
      })
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({}),
    })
  })
})

test('typing in the ingredient field on /add shows an autocomplete suggestion', async () => {
  render(
    <MemoryRouter initialEntries={['/add']}>
      <App />
    </MemoryRouter>,
  )

  // Wait for recipes to load
  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/recipes$/))
  })

  // Find the first ingredient-name input (the Add form starts with one blank row).
  const inputs = screen.getAllByLabelText(/ingredient name/i)
  expect(inputs.length).toBeGreaterThan(0)
  const first = inputs[0] as HTMLInputElement

  fireEvent.focus(first)
  fireEvent.change(first, { target: { value: 'lø' } })

  // Suggestion appears.
  const suggestion = await screen.findByText('løg')
  expect(suggestion).toBeInTheDocument()

  // Pick with Enter after ArrowDown.
  fireEvent.keyDown(first, { key: 'ArrowDown' })
  fireEvent.keyDown(first, { key: 'Enter' })
  expect(first.value).toBe('løg')
})
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `bun --cwd frontend run test -- --testPathPattern=addRecipeAutocomplete`
Expected: fails because `getAllByLabelText(/ingredient name/i)` returns nothing — the current Add form's ingredient input has no such label.

- [ ] **Step 3: Add the suggestion-pool memos to `App.tsx`**

In `frontend/src/App.tsx`, near the existing `ingredientNames` memo at `~line 222-233`, add:

```typescript
  const allIngredientNames = useMemo<string[]>(() => {
    const set = new Set<string>()
    const push = (raw: string | undefined | null) => {
      if (!raw) return
      const v = raw.normalize('NFC').toLowerCase().trim()
      if (v) set.add(v)
    }
    for (const r of recipes) {
      for (const k of Object.keys(r.ingredienser ?? {})) push(k)
      for (const k of Object.keys(r.extras ?? {})) push(k)
    }
    for (const item of configItems) push(item.name)
    return Array.from(set).sort()
  }, [recipes, configItems])

  const allUnits = useMemo<string[]>(() => {
    const set = new Set<string>()
    const push = (raw: string | undefined | null) => {
      if (!raw) return
      const v = raw.toLowerCase().trim()
      if (v) set.add(v)
    }
    const collect = (m: Record<string, { unit: string }> | undefined) => {
      for (const v of Object.values(m ?? {})) push(v?.unit)
    }
    for (const r of recipes) {
      collect(r.ingredienser)
      collect(r.extras)
    }
    return Array.from(set).sort()
  }, [recipes])
```

Also add the import at the top of `App.tsx`:
```typescript
import { ComboboxInput } from './components/ComboboxInput'
```

- [ ] **Step 4: Replace the Add-form ingredient row inputs**

In `App.tsx` at the Add-form ingredient row (around lines 2081-2111), replace the name and unit `<input>` elements. The two amount input and the ✕ button stay unchanged. The current structure is:

```tsx
{ingredientRows.map((row) => (
  <div key={row.id} className="grid gap-2 ...">
    <input
      value={row.navn}
      onChange={(event) => updateIngredientRow(row.id, { navn: event.target.value })}
      placeholder="Ingredient"
      className="rounded-lg border border-white/10 bg-brand-surface/50 ..."
    />
    <input value={row.amount} onChange={... { amount: ... }} placeholder="Amount" />
    <input value={row.unit}   onChange={... { unit:   ... }} placeholder="Unit" />
    <button ... onClick={() => removeIngredientRow(row.id)}>✕</button>
  </div>
))}
```

Change it to:
```tsx
{ingredientRows.map((row) => (
  <div key={row.id} className="grid gap-2 ...">
    <ComboboxInput
      value={row.navn}
      onChange={(v) => updateIngredientRow(row.id, { navn: v })}
      suggestions={allIngredientNames}
      placeholder="Ingredient"
      ariaLabel="ingredient name"
      className="w-full rounded-lg border border-white/10 bg-brand-surface/50 ..."
    />
    <input value={row.amount} onChange={... { amount: ... }} placeholder="Amount" />
    <ComboboxInput
      value={row.unit}
      onChange={(v) => updateIngredientRow(row.id, { unit: v })}
      suggestions={allUnits}
      placeholder="Unit"
      ariaLabel="ingredient unit"
      className="w-full rounded-lg border border-white/10 bg-brand-surface/50 ..."
    />
    <button ... onClick={() => removeIngredientRow(row.id)}>✕</button>
  </div>
))}
```

Preserve the exact className string from the original raw `<input>` — copy-paste it into the `className` prop on `ComboboxInput`. The amount input and ✕ button are unchanged (do NOT touch them). The `...` in the amount/button lines above represent whatever exists in the current file; do not literally paste `...`.

- [ ] **Step 5: Replace the Add-form extras row inputs**

Same treatment at the Add-form extras row (around lines 2122-2152). Ingredient name field → `ComboboxInput` with `suggestions={allIngredientNames}` and `ariaLabel="extra name"`. Unit field → `ComboboxInput` with `suggestions={allUnits}` and `ariaLabel="extra unit"`. Amount and ✕ stay untouched. The `onChange` callbacks call `updateExtraRow(row.id, ...)` instead of `updateIngredientRow`.

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `bun --cwd frontend run test -- --testPathPattern=addRecipeAutocomplete`
Expected: pass.

Also run the full frontend suite: `bun --cwd frontend run test`
Expected: all tests pass. The existing `cameraModal.test.tsx` should be unaffected because it doesn't type into ingredient rows directly.

- [ ] **Step 7: Typecheck the build**

Run: `bun --cwd frontend run build`
Expected: TypeScript and Vite complete without errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/__tests__/addRecipeAutocomplete.test.tsx
git commit -m "feat(frontend): autocomplete ingredient name and unit on Add-recipe form"
```

---

## Task 9: Frontend — wire ComboboxInput into Edit-recipe form

**Rationale:** Duplicate the Task 8 work for the Edit form (around lines 2311-2343 for ingredients, 2351-2384 for extras). The edit-form rows use `updateEditIngredientRow` and `updateEditExtraRow` callbacks (see `App.tsx:395-417`).

**Files:**
- Modify: `frontend/src/App.tsx` (Edit-form ingredient + extras rows)

- [ ] **Step 1: Add an aria-labeled input test for the edit path**

Append to `frontend/src/__tests__/addRecipeAutocomplete.test.tsx`:

```typescript
test('edit form ingredient input also uses the combobox', async () => {
  render(
    <MemoryRouter initialEntries={['/edit/test']}>
      <App />
    </MemoryRouter>,
  )

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/recipes$/))
  })

  // Edit form should render pre-populated rows with aria-label="ingredient name".
  const inputs = await screen.findAllByLabelText(/ingredient name/i)
  expect(inputs.length).toBeGreaterThan(0)
})
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `bun --cwd frontend run test -- --testPathPattern=addRecipeAutocomplete`
Expected: the new test fails because the Edit form's ingredient inputs are still raw `<input>` elements without the `aria-label`.

- [ ] **Step 3: Replace the Edit-form ingredient row inputs**

Same treatment as Task 8 Step 4, but at lines 2311-2343 in `App.tsx`, using `updateEditIngredientRow(row.id, ...)` in the `onChange` callbacks. Preserve any drag-and-drop-related attributes on the row wrapper — only the two `<input>` elements (name, unit) become `ComboboxInput`. The amount input, delete button, and drag handles stay untouched.

- [ ] **Step 4: Replace the Edit-form extras row inputs**

Same as above for lines 2351-2384, calling `updateEditExtraRow(row.id, ...)`.

- [ ] **Step 5: Run the frontend suite**

Run: `bun --cwd frontend run test`
Expected: all tests pass.

Run: `bun --cwd frontend run build`
Expected: TypeScript + Vite build clean.

- [ ] **Step 6: Manual smoke test**

Start the app: `uv run python app.py` in one terminal.

Visit `http://127.0.0.1:5000/add`. Type "lø" in the first ingredient field — a dropdown with "løg" (or whatever exists in your DB) should appear. Arrow-down + Enter should fill the field. Save the recipe. Visit `http://127.0.0.1:5000/edit/<slug>` for the newly-saved recipe. Confirm the same autocomplete behavior on the edit form. Confirm the saved ingredient key is lowercase in the DB (open `recipes.db` with `sqlite3 recipes.db "SELECT slug, ingredienser FROM recipe WHERE slug='<slug>';"`).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/__tests__/addRecipeAutocomplete.test.tsx
git commit -m "feat(frontend): autocomplete ingredient name and unit on Edit-recipe form"
```

---

## Verification — end to end

- [ ] Full backend suite: `uv run pytest -v` — all pass.
- [ ] Full frontend suite: `bun --cwd frontend run test` — all pass.
- [ ] Frontend build: `bun --cwd frontend run build` — succeeds.
- [ ] Manual smoke test on `/add` and `/edit/<slug>` — autocomplete visible, keyboard navigation works, saved data is lowercased in DB.
- [ ] Idempotency of migration: `uv run python scripts/migrate_lowercase_ingredients.py` reports zero changes.
- [ ] Backup file `recipes.db.pre-lowercase-migration.bak` still exists locally (do NOT commit it).

If all checks pass, the feature is complete.
