Use uv for projects.

- New packages are added with `uv add <pkg>`.
- Run the app with `uv run python app.py`.

Secrets and local state (do not read or print):
- Never open or quote the contents of `.env` in prompts, logs, or output.
- Treat it as sensitive; only load into the process environment if needed.

Operational notes for agents:
- Keep network logs redacted (no Authorization/Cookie headers, no tokens).
- nemlig.com bearer tokens and session cookies are secrets: never print them,
  and never persist a logged-in session to disk.

## Grocery ordering (nemlig.com)

Use the `nemlig-shopping` skill. Do not re-derive the workflow.

- `data/nemlig_product_map.json` is the durable memory: ingredient -> product
  defaults, quantities, preference notes, likely-stocked staples, and unresolved
  items. Back it up before writing (the skill's `record.py` does).
- Weekly menus and lists are **not** kept in this repo. They land in
  `~/Downloads/` as `shopping-<N>.pdf` (image-based, so `pdftotext` returns
  nothing — render with `pdftoppm` and read the pages) and sometimes
  `menu-<YYYY-MM-DD>.md`. The `<N>` is the user's own counter, not the ISO week.
- Ordering is driven through a logged-in browser tab, not a Python HTTP client;
  the user logs in themselves.

Known data discrepancies, so they are not mistaken for bugs:

- `recipes.db` currently holds 6 English demo recipes. The real corpus is the
  135 `.yml` files in `recipes/`.
- `shopping.md` in the repo root is stale relative to both.

Frontend build/run tips:
- Dev server: `bun --cwd frontend run dev` (expects API at `http://localhost:5000` unless `VITE_API_BASE` is set)
- Build for Flask to serve: run from inside the folder: `cd frontend && bun run build`
- Flask automatically serves the built SPA from `frontend/dist/` when present.


## Python Environment Policy

Use `uv` for all Python dependency and environment management.
- Prefer `uv sync`, `uv run`, and `uv pip` commands.
- Do NOT manually create or activate virtual environments (`python -m venv`, `source .venv/bin/activate`) unless explicitly requested.
- Treat manual venv creation/activation as discouraged and avoid suggesting it in guidance.


## 1) Secrets scan (trufflehog via podman)

```bash
podman run --rm -v "$PWD:/repo" -v "$PWD/.trufflehog:/tmp" docker.io/trufflesecurity/trufflehog:latest filesystem /repo
```

## 2) Tests

Backend (pytest, matches CI):

```bash
uv run --frozen pytest -q
```

Frontend (Jest + React Testing Library):

```bash
bun --cwd frontend run test
```

## Tooling Requirements

- `gh` (GitHub CLI) for issue workflows.
- `podman` to run the trufflehog secrets scan.
- `uv` for Python dependency management and running `ruff`.
- `node` + `npm` for frontend lint/test tasks.
