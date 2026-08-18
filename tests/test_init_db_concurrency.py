"""Schema creation must be safe when several processes start at once.

Gunicorn runs the app with `-w 4`. Each worker imports `app`, and `app` calls
`init_db()` at import time, so four processes race to create the schema against
the same SQLite file. On a fresh database this used to crash every worker but
the one that won the race, taking the whole container down.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

WORKERS = 4


def _init_db_in_child(root: str, db_url: str, barrier, results) -> None:
    """Import the models module fresh and create the schema, as a worker would."""
    import os

    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ["DATABASE_URL"] = db_url

    try:
        import src.models as models

        # Release all children simultaneously to maximise contention.
        barrier.wait(timeout=30)
        models.init_db()
    except Exception as exc:  # noqa: BLE001 - the failure mode is what we assert on
        results.put(f"{type(exc).__name__}: {exc}")
    else:
        results.put("ok")


def test_init_db_is_safe_across_concurrent_processes(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'race.db'}"

    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(WORKERS)
    results = ctx.Queue()

    procs = [
        ctx.Process(
            target=_init_db_in_child,
            args=(str(ROOT), db_url, barrier, results),
        )
        for _ in range(WORKERS)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=60)

    outcomes = [results.get(timeout=10) for _ in range(WORKERS)]
    failures = [outcome for outcome in outcomes if outcome != "ok"]

    assert not failures, f"{len(failures)}/{WORKERS} workers failed to initialise: {failures}"
    assert all(proc.exitcode == 0 for proc in procs), (
        f"worker exit codes: {[proc.exitcode for proc in procs]}"
    )


def _import_app_in_child(root: str, db_url: str, barrier, results) -> None:
    """Import the whole app, exactly as a gunicorn worker does at boot."""
    import os

    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ["DATABASE_URL"] = db_url

    try:
        barrier.wait(timeout=30)
        import app  # noqa: F401 - importing is the operation under test
    except Exception as exc:  # noqa: BLE001
        results.put(f"{type(exc).__name__}: {exc}")
    else:
        results.put("ok")


def test_app_import_is_safe_across_concurrent_workers(tmp_path):
    """Importing `app` runs init_db() and the staples seeding.

    Both are check-then-act sequences, so concurrent workers must not collide.
    """
    db_url = f"sqlite:///{tmp_path / 'boot.db'}"

    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(WORKERS)
    results = ctx.Queue()

    procs = [
        ctx.Process(
            target=_import_app_in_child,
            args=(str(ROOT), db_url, barrier, results),
        )
        for _ in range(WORKERS)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=60)

    outcomes = [results.get(timeout=10) for _ in range(WORKERS)]
    failures = [outcome for outcome in outcomes if outcome != "ok"]

    assert not failures, f"{len(failures)}/{WORKERS} workers failed to boot: {failures}"


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    """Calling init_db twice in one process must not raise."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'twice.db'}")

    import src.models as models

    db_url = f"sqlite:///{tmp_path / 'twice.db'}"
    monkeypatch.setattr(
        models, "engine", models.create_engine(db_url, **models._sqlite_kwargs(db_url))
    )

    models.init_db()
    models.init_db()
