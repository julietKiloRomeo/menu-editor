# Menu Planner React/Tailwind Migration & Repo Cleanup

## 1. Inventory & Archival Prep ✅ (2025-10-26)
- Root now contains only the live Flask app + config tables: `app.py`, `assets/`, `src/`, `templates/`, `static/`, `menus/`, `recipes/`, `pyproject.toml`, `uv.lock`, `Dockerfile`, `playwright/`, and supporting docs (`README.md`, `MIGRATION_PLAN.md`). The legacy `config.yml` now lives in `archive/2025-10-26-legacy/` for reference only.
- Archived experiments + notebooks + scripts live under `archive/2025-10-26-legacy/` (see its README for the exact files: notebooks, automation docs, helper CLIs, YAML exports, etc.).
- `.gitignore` now anticipates the upcoming frontend toolchain (`frontend/dist`, `frontend/node_modules`, Vite cache) plus coverage artefacts so the repo stays clean once React/Tailwind bootstraps.
- Continue to drop any additional legacy artefacts into a dated folder under `archive/` to keep the root tidy.

## 2. Backend/API Hardening ✅ (2025-10-26)
- Added `docs/api.md` with a full inventory of search helpers, recipe CRUD, staples/config, and OpenAI ingestion endpoints plus error semantics and SPA-hosting notes.
- Created `tests/test_api.py` (pytest) covering recipe list/create/update flows and staple CRUD against an isolated SQLite database to protect against regressions while the UI is replaced.
- Flask now enables configurable CORS for `/api/*`, exposes `/api` aliases for legacy routes (`/search_recipes`, `/generate_menu`), and can stream `frontend/dist` assets whenever the React build exists (falling back to the legacy templates otherwise).

## 3. Front-End Stack Bootstrapping ✅ (2025-10-26)
- Vite React+TS app lives in `frontend/` (Bun-powered) with build output streaming from Flask automatically when `frontend/dist/` exists.
- Tailwind + PostCSS configured with our legacy colour palette + rounded card aesthetic so gradients/panels match the Flask UI.
- `src/App.tsx` already renders the shell (spinner/search, chosen list, API status footer) and consumes `/api/recipes?only_names=1`, proving end-to-end wiring ahead of deeper feature parity work.

## 4. Feature Parity Migration
1. **Menu Planner** ✅ (React UI now mirrors the legacy planner: spinner suggestions, searchable grid, weekly selection with serving controls, ingredient rename tooling, and `/api/menu/generate` export/copy/download flow.)
2. **Add Recipe** ✅ (React view handles drag/drop uploads, AI photo parsing with prompt hints, camera capture, YAML preview, manual ingredient/extras editing, and saves via `/api/recipes`.)
3. **Edit Recipes** ✅ (React edit view matches legacy editor: search/filter by name/slug/ingredient, update fields/servings/slug/flags, tweak ingredients/extras, and save via `/api/recipes/<slug>` with live toast feedback.)
4. **Config** ✅ (React view covers categories, ingredient mappings, staples + label editor, and wires bulk-rename shortcuts back into the ingredient tools.)
   - Each sub-step ships behind a flag or dedicated branch; verify parity before moving on.

## 5. Routing & Deployment Integration ⏳
- Status: React Router scaffolding landed (`BrowserRouter` in `frontend/src/main.tsx`, initial route helpers, and `goToView` wrappers), but legacy conditional rendering still drives view switching.
- TODO
  - Finish swapping the remaining `view === '...'` blocks in `frontend/src/App.tsx` for `<Routes>`/`<Route>` config and ensure `goToView` keeps planner/shared state in sync (`renameCandidate`, `configLoaded`, search query, etc.).
  - Replace the few lingering `setView('...')` calls with router navigation helpers (search for `setView(` to confirm none remain).
  - Update navigation controls to use `<Link>/<NavLink>` and verify rename/tool flows still bridge the routes correctly.
  - Extend Flask's SPA fallback so `/planner`, `/add`, `/edit`, `/config`, `/shopping`, and `/tools` all return the React index while preserving API routes.
  - Consolidate the new `[tool.uv.scripts]` entries for frontend dev/build (`frontend-dev`, `frontend-build`) and surface the commands in `README.md`.
  - Run `bun run build` once routing is wired; note any large-chunk warnings (html2pdf) for later optimisation.

## 6. Cleanup & Documentation
- After React parity, remove legacy templates/CSS/JS (archive the final snapshot in `/archive/<date>-legacy` before deletion).
- Refresh README with new dev instructions (backend via `uv run python app.py`, frontend via Vite commands).
- Document repo layout so future experiments land under `/archive` instead of root.

---
Tracking status of each step here; update this file as milestones complete.
