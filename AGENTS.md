Use uv for projects.

- New packages are added with `uv add <pkg>`.
- Run the app with `uv run python app.py`.

Secrets and local state (do not read or print):
- Never open or quote the contents of `.env` in prompts, logs, or output.
- Never open or quote the contents of `playwright/.auth/*` (session data).
- Treat both as sensitive; only load into the process environment if needed.

Operational notes for agents:
- Prefer Playwright + persisted auth for BilkaToGo automation.
- Keep network logs redacted (no Authorization/Cookie headers, no tokens).

Frontend build/run tips:
- Dev server: `bun --cwd frontend run dev` (expects API at `http://localhost:5000` unless `VITE_API_BASE` is set)
- Build for Flask to serve: run from inside the folder: `cd frontend && bun run build`
- Flask automatically serves the built SPA from `frontend/dist/` when present.
