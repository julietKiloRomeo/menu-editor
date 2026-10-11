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

**Use `uv run python scripts/order_latest.py` for a kitchen-run order.** It is
the single entry point: it snapshots the real valhalla database safely, chooses
the newest run, performs fresh searches, opens the app's Order screen, and syncs
the recorded order back. Do not manually copy databases, parse a shopping PDF,
create a temporary run, or launch the skill's standalone picker when a kitchen
run exists.

**The app's Order screen is the picker**, not the skill's scripts. The
`nemlig-shopping` skill at `~/.config/opencode/skills/nemlig-shopping/`
predates it and drives the same workflow through standalone scripts
(`prepare.py`, `picker.py`, `basket.py`, `record.py`). Its *judgement* notes are
still the best writeup of why each step exists — read `SKILL.md` for that — but
the mechanics now live in `app.py` and `src/core/nemlig.py`.

Note the skill may not appear in the skills list. Descriptions over roughly
500 characters seem not to load (every skill at <= 319 chars loads; the two at
>= 587 do not), which fails silently — the skill looks absent rather than
malformed. `nemlig-shopping`'s description was shortened on 2026-09-27; if it
still does not appear, read `SKILL.md` directly instead of re-deriving.

Prerequisites, in order — the whole workflow is blocked without them:

1. **The app must run locally, on the same machine as Chrome.**
   `src/browser.py` pins CDP to `127.0.0.1:9222` deliberately, so nemlig
   tokens never leave the machine. The container on valhalla therefore cannot
   drive a basket, and never will.
2. Chrome needs `--remote-debugging-port=9222` (already in
   `~/.config/chromium-flags.conf` on loke). `chrome://inspect` is **not**
   equivalent: the port listens but `/json` 404s, which shows up as
   `{"reachable": true, "tab": null}`.
3. **The user logs in themselves.** Never handle the password; never persist a
   session.

- `data/nemlig_product_map.json` is the durable memory: ingredient -> product
  defaults, quantities, preference notes, likely-stocked staples, and unresolved
  items. `POST /api/orders/<id>/record` folds a finished order back into it and
  takes a `.bak` first.
- Weekly menus and lists are **not** kept in this repo. They land in
  `~/Downloads/` as `shopping-<N>.pdf` (image-based, so `pdftotext` returns
  nothing — render with `pdftoppm` and read the pages) and sometimes
  `menu-<YYYY-MM-DD>.md`. The `<N>` is the user's own counter, not the ISO week.
  A run can also be built in the app directly via `POST /api/runs`.

Known data discrepancies, so they are not mistaken for bugs:

- There are two different databases called `recipes.db`, and confusing them
  looks exactly like data loss:
  - **`./recipes.db` in this repo holds 6 English demo recipes.** It is the
    fallback `DATABASE_URL` and is what you get by running the app with no
    environment set.
  - **valhalla's `menu/data/recipes.db` is the real one** (144 recipes, the
    live runs and orders), at
    `valhalla:/home/jikr/projects/kastaniebakken-automation/menu/data/recipes.db`.
    It is in **WAL mode**: never plain-`cp` it, use `sqlite3.connect(...).backup()`
    or you will silently miss recent writes.
  - `GET /api/status` reports which file the running process actually has open,
    and the app header shows it. Check it before concluding anything is missing.
- `recipes/` holds 136 `.yml` files. That corpus and the databases are not kept
  in sync automatically.

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
