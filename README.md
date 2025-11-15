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

```bash
docker build -t menu-app .
docker run -p 80:5000 menu-app
```

# Docker GitHub Container Registry (GHCR) Guide

## Creating a Personal Access Token (PAT)
1. Go to GitHub Settings → Developer Settings → Personal Access Tokens
2. Choose "Tokens (classic)" or "Fine-grained tokens"
3. Generate new token with required permissions:
   - `write:packages`
   - `read:packages`
   - `delete:packages` (optional)
4. Save the token securely (e.g., in 1Password)
5. Note the token name shown in GitHub settings (this will be your username for docker login)

## Pushing Images to GHCR

1. Login to GitHub Container Registry:
```bash
# Replace TOKEN_NAME with the name of your token from GitHub settings
# Replace YOUR_PAT with your actual PAT
echo YOUR_PAT | docker login ghcr.io -u TOKEN_NAME --password-stdin
```

2. Tag your local image:
```bash
docker tag menu-app:latest ghcr.io/julietkiloromeo/menu-app:latest
```

3. Push the image:
```bash
docker push ghcr.io/julietkiloromeo/menu-app:latest
```

## Pulling Images on a New Machine

1. Login to GHCR:
```bash
# Replace TOKEN_NAME and YOUR_PAT as before
echo YOUR_PAT | docker login ghcr.io -u TOKEN_NAME --password-stdin
```

2. Pull the image:
```bash
docker pull ghcr.io/julietkiloromeo/menu-app:latest
```

## Troubleshooting

- If login fails, verify:
  - Token name is correct (from GitHub settings, not your GitHub username)
  - PAT hasn't expired
  - PAT has correct permissions
- If push fails, ensure:
  - Repository exists and is properly configured for packages
  - You have appropriate permissions on the repository
  - Image is tagged correctly with the ghcr.io prefix

## Security Notes

- Never commit your PAT to version control
- Use environment variables or secure secret management (like 1Password) to store PATs
- Consider using fine-grained tokens with minimal necessary permissions
- Regularly rotate your PATs
