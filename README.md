```bash
  uv run python app.py 
```

## React/Tailwind frontend

```bash
cd frontend
bun install          # first time only
VITE_API_BASE="http://localhost:5000" bun run dev
```

- Build: recommended to run from inside the `frontend/` folder:

```bash
cd frontend
bun run build
```

This emits the production bundle to `frontend/dist/` (served automatically by Flask when present).
If you only run `uv run python app.py`, make sure to rebuild after frontend changes so Flask serves the latest UI:

```bash
cd frontend && bun run build
```

Then reload the browser. The camera modal and capture flow will be available on the “Add” view.

### Camera capture UX
- Full-screen camera modal for preview and capture.
- Visible spinner overlay while parsing the image.
- Manual focus slider appears when supported by the device; otherwise a hint is shown.
- Ingredient order is preserved exactly as parsed (no alphabetic sort).
- Adding a new ingredient/extra row prepends at the top for quick entry.

## OpenAI API configuration

The backend auto-loads `.env` at startup and uses these variables:

- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (optional for custom endpoints)
- `RECIPE_IMAGE_MODEL` (optional; defaults to `gpt-5-mini`)

Setup
- Copy `./.env.example` to `./.env` and fill values:
  - `cp .env.example .env`
- Start the app: `uv run python app.py`

Notes
- Do not commit keys to source control. Prefer a password manager or OS keychain for storage.

- Menu Planner parity lives in the React shell: spinner suggestions, search, serving adjustments, menu export, and ingredient rename tooling all run off the existing `/api/*` routes.
- Add Recipe lives in the same UI: drag/drop or camera capture, optional AI prompt, YAML preview, and manual form edits before posting to `/api/recipes`.
- Edit Recipes is React-native too: search/filter, adjust name/slug/servings/flags, tweak ingredients/extras, and PATCH via `/api/recipes/<slug>`.
- Config dashboard (categories, ingredient mappings, staples + label) is now in React with shortcuts into the rename tools.
- If the frontend dev server runs on another port, keep the Flask API running via `uv run python app.py` and point `VITE_API_BASE` to that origin.

## Running the container locally

```bash
podman build -t menu-editor .
podman run -p 8080:5000 -v menu-data:/data menu-editor
```

The image builds the React frontend itself (stage 1) and serves it from Flask,
so a clean checkout is all that is needed — `frontend/dist` is gitignored and is
deliberately not used from the host.

The database lives at `/data/recipes.db` (`DATABASE_URL` overrides this). Mount
something at `/data` or the data disappears with the container.

## Deployment

The app runs on **valhalla**, in the Ansible-managed compose stack in the
[`homelab`](https://github.com/julietKiloRomeo/homelab) repo, behind Traefik at
`menu.valhalla`. valhalla's `docker-compose.yml` is *generated* from
`roles/home_automation_stack/templates/docker-compose.yml.j2` — editing it on the
host is pointless, the next deploy overwrites it.

Releasing a new version:

```bash
git tag v1.2.0 && git push --tags   # Actions builds + pushes to GHCR
./scripts/pin-image.sh 1.2.0        # pins the digest in the homelab inventory

cd ../homelab/ansible
bin/deploy valhalla --check --diff -K   # review
bin/deploy valhalla -K                  # apply
```

`-K` is needed because the AdGuard task in that stack requires sudo. Commit the
inventory bump in the homelab repo afterwards.

### Persistent data

`recipes.db` is bind-mounted from `menu/data/` inside the compose project
directory on valhalla, so it survives image pulls and is included in
`bin/backup-valhalla`. The weekly `uge_*.yaml` files and `shopping.md` are *not*
persisted — they are regenerated on demand.

### Secrets

`OPENAI_API_KEY` (for recipe-from-photo parsing) comes from Ansible Vault and is
rendered to `menu/menu-app.env` with mode 0600. Add it with:

```bash
cd ../homelab/ansible && bin/vault-edit valhalla   # vault_menu_app_openai_api_key
```

Locally, put it in `.env` (see `.env.example`); that file is excluded from the
image by `.dockerignore`.
