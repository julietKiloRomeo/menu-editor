# Backend API Reference

Last updated: 2025-10-26.

## Overview
- Base URL: the Flask server default `http://localhost:5000`.
- Auth: none. All routes assume trusted LAN access; add a proxy/auth middleware before internet exposure.
- Content types: JSON for every `/api/*` route except `/api/recipes/from-image` (multipart file upload). Responses use UTF-8.
- Error model: every endpoint returns `{"error": "message"}` alongside an HTTP 4xx/5xx status when something fails.
- CORS: requests hitting `/api/*` are allowed from the origin configured via `FRONTEND_ORIGIN` (default `*`). Set this env var before starting Flask when the React dev server runs on another port.
- SPA hosting: when `frontend/dist/index.html` exists, `GET /` and `/assets/*` stream the static React build. Without the build, Flask falls back to the legacy Jinja templates so both stacks can coexist during the migration.

## Search & Menu Helpers
### `GET /api/recipes/search` (also exposed as `/search_recipes`)
Query params:
- `query`: string to fuzzy match against recipe names + ingredient keys. Empty query returns the first six recipes alphabetically.

Response: `{"recipes": ["name", ...], "total_matches": N}`.

### `POST /api/menu/generate` (also exposed as `/generate_menu`)
Body:
```json
{
  "menu_data": {
    "Recipe name": 4,
    "Another recipe": 2
  }
}
```
Values represent requested plate counts. Unknown recipe names are silently ignored.

Response: `{"markdown": "..."}` containing the rendered grocery list plus auto-appended staple items. The endpoint also writes `shopping.md` and the YAML snapshot under `uge_<week>_<year>.yaml` for downstream tooling.

## Recipes
### `GET /api/recipes`
Query params:
- `only_names` (`1/true/yes`): return `{"recipes": ["navn", ...]}` instead of full objects.
- `include_blacklisted` (`0/false/no` to hide blacklisted recipes unless they are explicitly whitelisted).

Full recipe objects look like:
```json
{
  "id": 1,
  "slug": "lasagne",
  "navn": "Lasagne",
  "placering": "Page 12",
  "antal": 4,
  "ingredienser": {"Pasta": {"amount": 1, "unit": "pk"}},
  "extras": {"Salat": {"amount": 1, "unit": "stk"}},
  "is_blacklisted": false,
  "is_whitelisted": false
}
```

### `GET /api/recipes/<identifier>`
`identifier` can be either `slug` or `navn`. Returns `{ "recipe": <object> }` or 404.

### `POST /api/recipes`
Body: JSON produced either by the existing UI or a React form. Required keys: `navn`, `antal`, and `ingredienser`. Optional: `placering`, `extras`, `slug`, `is_blacklisted`, `is_whitelisted`.

Response: `201 Created` with `{"message": "Recipe created", "recipe": <object>, "recipes": ["..." ]}` so the UI can refresh its dropdowns in one round-trip.

### `PATCH /api/recipes/<identifier>`
Allows partial updates for any of the recipe fields listed above. Validation rules:
- `navn`/`slug`: non-empty + unique.
- `antal`: positive integer.
- `ingredienser`/`extras`: dictionary or list entries with `name + amount + unit`.
- Boolean flags accept any truthy/falsy JSON value.

Response: `{ "recipe": <updated object> }` (200) or `{"error": ...}` for validation failures.

### `POST /api/recipes/from-image`
`multipart/form-data` upload with:
- `image`: required file (jpg/png/etc.).
- `prompt`: optional user instructions passed verbatim to the OpenAI Vision call.

Response: `{ "recipe": { "navn": ..., "ingredienser": {...}, "extras": {...}, "suggested_slug": "...", "raw_yaml": "..." } }`. HTTP 502 is returned when model parsing fails.

## Ingredient Utilities
### `GET /api/ingredients/similar`
Query params: `name` (required) and optional `limit` (default 10). Returns the closest ingredient names detected across recipes and config mappings: `{"names": ["Tomat", ...]}`.

### `GET /api/ingredients/usage`
Query params: `name` (required) and `include_extras` (default true). Response: `{"usages": [{"recipe_slug": "...", "recipe_name": "...", "field": "ingredienser"|"extras"}, ...]}`.

### `POST /api/ingredients/rename`
Body:
```json
{
  "from": "Tomat",
  "to": "Tomat, hakket",
  "include_extras": true,
  "case_insensitive": true,
  "force": false
}
```
`force=true` removes conflicting duplicates when units/amounts disagree. Response: `{"updated_count": N, "conflicts": [...]}`.

## Staples & Config
### `GET /api/staples`
Returns `{ "items": [...], "label": "Weekly staples", "label_options": [...] }`.

### `POST /api/staples`
Body: `{ "name": "Brød", "amount": 1, "unit": "stk" }`. `amount` defaults to `1.0` if omitted. Response: `201` with the refreshed list plus `item` containing the created staple.

### `PATCH /api/staples/<id>` / `DELETE /api/staples/<id>`
- `PATCH` accepts any combination of `name`, `amount`, `unit`.
- `DELETE` removes the staple and returns the refreshed list.

### `POST /api/staples/label`
Body: `{ "label": "Weekly staples" }` or `{ "use_custom": true, "custom_label": "Picnic" }`. Response echoes the saved label + items list.

### `GET /api/config`
Returns categories, ingredient mappings, staples, and the active staple label. Useful for bootstrapping React context.

### `POST /api/config/categories`
Body: `{ "name": "Grønt", "priority": 10 }`. Response `201` with the full config snapshot. `PATCH` / `DELETE /api/config/categories/<id>` follow the same envelope.

### `POST /api/config/items`
Body: `{ "name": "Tomat", "category_id": 1 }`. Response `201` with full config. `PATCH` / `DELETE /api/config/items/<id>` mirror this behavior.

## Legacy helpers (still available during the migration)
- `GET /` → serves the React bundle when it exists, otherwise renders the Flask/Jinja UI with preloaded recipe names.
- `GET /assets/*` and `GET /favicon.ico` transparently read from `frontend/dist` when present or fall back to the legacy `assets/` directory.

Use `/api/*` whenever possible—non `/api` routes remain only for backwards compatibility with the legacy UI and will disappear once the React app ships.
