# Menu Editor Modernization Plan

This plan translates the recent code-review findings into a concrete sequence of changes that steer the project toward a modular, maintainable architecture with trustworthy test coverage. Line references point to the current implementation for clarity (for example, `app.py:69`).

## Objectives
- Align the backend with the FastAPI-first charter while separating HTTP, business logic, and persistence.
- Decompose the monolithic React entry point into routed, testable components with shared data utilities.
- Provide comprehensive tests (unit, integration, E2E) so future refactors are low-risk.

## Backend Modernization

1. **Adopt a FastAPI Application Shell**
   - Introduce `app/main.py` that configures FastAPI, mounts routers, and serves the SPA. Move Flask-specific logic out of `app.py:69-1580`.
   - Split endpoints into modules (`app/api/recipes.py`, `app/api/config.py`, `app/api/staples.py`, `app/api/ingredients.py`, `app/api/menus.py`) so each domain’s dependencies are explicit.
   - Replace `flask_cors.CORS` usage with FastAPI middleware and document the migration steps in `README.md`.

2. **Create Service & Repository Layers**
   - Extract database access currently inlined throughout `app.py:500-1115` into repositories (e.g., `RecipeRepository`, `CategoryRepository`) that accept a SQLModel session.
   - Wrap domain behavior (slug handling, rename flows, staples label logic) into service classes/functions, enabling dependency injection for tests.
   - Update HTTP handlers to call services instead of `get_session()` directly.

3. **Fix Unit & Config Data Management**
   - Persist allowed measurement units (or a `unit_aliases` table) instead of computing once at import (`app.py:137-189`).
   - Provide CRUD endpoints/admin UI for units so new entries do not require restarts; invalidate caches via event hooks when recipes/staples change.

4. **Rebuild the Menu Generation Pipeline**
   - Move the YAML/menu shopping logic out of `parser.py:17-205` and the `/api/menu/generate` handler (`app.py:1040-1065`) into a pure `menu_builder` module.
   - Ensure the API returns JSON/markdown without writing `shopping.md` or `recipes/uge_*.yaml` unless explicitly requested. Keep the CLI as a thin wrapper that writes to disk when invoked manually.
   - Add cycle detection and safe YAML loading (`yaml.safe_load`) to avoid recursion bugs and unsafe parsing.

5. **Isolate the OpenAI Integration**
   - Create `app/integrations/recipe_extractor.py` responsible for prompt construction, request/response handling, validation, and error mapping (currently in `app.py:657-736`).
   - Add timeouts, payload size guards, and a protocol interface that tests can stub.
   - Consider background job support (e.g., task queue) if photo parsing becomes slow or rate-limited.

6. **Make Initialization Explicit**
   - Remove import-time side effects like `seed_config_from_yaml()` and `seed_staples_from_legacy()` (`app.py:517-555`). Replace them with CLI commands (`uv run python -m app.manage seed-config`) or startup hooks that run exactly once under controlled conditions.
   - Centralize settings in a `settings.py` module backed by Pydantic’s `BaseSettings` for clearer configuration handling.

## Frontend Modernization

1. **Introduce Route-Level Components**
   - Break the 2.7k-line `App` component (`frontend/src/App.tsx:80-2715`) into routed views (`PlannerView`, `AddRecipeView`, `EditRecipeView`, `ConfigView`, `ShoppingToolsView`), each with its own state/effects.
   - Use `react-router` element routes instead of manual pathname switching (`frontend/src/App.tsx:157-195`) so navigation is declarative and code-splitting-friendly.

2. **Build a Typed API Layer**
   - Create `frontend/src/api/client.ts` with a typed `fetchJson` helper and domain-specific functions (recipes, config, staples, menu, rename). Replace the repeated `fetch` blocks scattered through `App.tsx` (`lines 251, 650, 709, 1108, 1331, 1419, etc.).
   - Consider React Query/SWR for caching and loading-state management, which also simplifies testing.

3. **Componentize Ingredient Forms & Tables**
   - Extract reusable components/hooks for ingredient rows (currently repeated for add/edit/config flows around `frontend/src/App.tsx:323-360`, `347-358`, `640-688`).
   - Adopt a form library (React Hook Form + Zod/Yup) to handle validation and reduce the sprawl of `useState` setters.

4. **Isolate Camera & Media Logic**
   - Move camera handling (`frontend/src/App.tsx:197-320`, `286-298`, `518-587`) into a dedicated `CameraModal` module with a context/provider. Encapsulate media-stream lifecycles, focus controls, and capture logic for easier mocking.
   - Provide a non-camera upload path component so automated tests can cover parsing without WebRTC dependencies.

5. **Modularize Export & Tooling Features**
   - Lazy-load heavy utilities like `html2pdf` (`frontend/src/App.tsx:1360-1405`) and markdown export helpers into a `useExportTools` hook or separate component to shrink the default bundle.
   - Relocate rename tools, staples config, and planner utilities into their own panels to keep each view focused.

6. **Establish Shared State & Toast Providers**
   - Replace manual toast bookkeeping (`frontend/src/App.tsx:232-239`) and selection state with context providers so child components can subscribe without prop drilling.
   - Ensure cleanup (timeouts, media streams, object URLs) happens inside the respective components, not the root.

## Testing & Tooling Roadmap

1. **Backend Test Suite Expansion**
   - Port existing Flask tests to FastAPI’s `TestClient`.
   - Add coverage for config CRUD, staples label changes, ingredient renames (including conflict scenarios), menu generation, and error paths (invalid payloads, DB failures).

2. **Menu Builder & Parser Tests**
   - Once the menu logic is extracted, write unit tests for recursion, freezer entries, staple injection, rounding, and markdown rendering.
   - Add property tests or table-driven tests for `coerce_ingredients` and unit handling to protect parsing edge cases.

3. **Integration & Contract Tests**
   - Stub the OpenAI client to verify prompt construction and payload validation without live calls.
   - Add tests ensuring caching invalidation (units, staples) works when new data is inserted.

4. **Frontend Unit & Component Tests**
   - Update `frontend/package.json` devDependencies to include `jest`, `ts-jest`, `@testing-library/react`, `@testing-library/user-event`, and `msw`.
   - Write component tests per view (planner interactions, add/edit form validation, config CRUD, rename modal, export tools) with coverage thresholds ≥80 % for critical components.

5. **End-to-End Coverage**
   - Use the existing Playwright setup to script core user journeys: planner selection, recipe capture (with mocked parser response), config changes, menu export download.
   - Persist auth as required by the operational notes and gate these tests behind optional CI flags if they rely on browser APIs.

## Suggested Implementation Order
1. Stand up the FastAPI skeleton alongside the Flask app, add parity tests, then switch the entry point.
2. Extract repositories/services and rewrite the menu builder; update tests to cover the new modules.
3. Modularize the frontend by introducing routes and the API client, migrating one view at a time while growing the component test suite.
4. Finish by adding the remaining frontend features (camera module, export helpers) and Playwright flows, ensuring CI runs backend + frontend + E2E tests.

Following this sequence keeps the system deployable after each milestone while continuously increasing automated coverage and modularity.
