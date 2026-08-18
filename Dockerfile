# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build the React SPA.
#
# frontend/dist is gitignored, so it does not exist in a clean checkout (CI).
# The image must therefore build the frontend itself; relying on a host-built
# dist/ silently degrades the app to the legacy Jinja templates.
# ---------------------------------------------------------------------------
FROM docker.io/oven/bun:1 AS frontend

WORKDIR /src

# Install dependencies first so this layer caches independently of source edits.
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY frontend/ ./
RUN bun run build

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime.
# glibc-based (not Alpine) so dependencies resolve to prebuilt manylinux wheels
# rather than being compiled from source.
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm

WORKDIR /app

# Resolve dependencies from the lockfile before copying source, so dependency
# layers are reused across application changes.
COPY pyproject.toml uv.lock /app/
RUN uv sync --no-dev --frozen --no-install-project

COPY . /app

# Overwrite anything that slipped through with the artifact built in stage 1.
COPY --from=frontend /src/dist /app/frontend/dist

# Default to a mounted volume so data survives container replacement. Deployments
# should mount a host directory at /data; override DATABASE_URL for other stores.
ENV DATABASE_URL="sqlite:////data/recipes.db"
ENV PYTHONUNBUFFERED=1
VOLUME ["/data"]

EXPOSE 5000

CMD ["uv", "run", "--no-dev", "gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app", \
     "--log-level", "info", "--error-logfile", "-", "--access-logfile", "-"]
