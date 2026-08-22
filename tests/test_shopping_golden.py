"""Golden tests locking the rendered shopping-list markdown.

These exist so the core extraction can be proven behaviour-preserving. If one
of these fails, the refactor changed user-visible output — investigate before
regenerating with `uv run python scripts/capture_golden.py`.
"""

from __future__ import annotations

import difflib
import importlib
import os
import sys

import pytest
from _shopping_fixtures import (
    GOLDEN_DIR,
    GOLDEN_MENUS,
    ROOT,
    render_menu_to_text,
    seed_legacy_config,
)


@pytest.fixture()
def shopping_env(tmp_path, monkeypatch):
    """Temp DB seeded with the real 13-zone legacy config, plus the parser module."""
    monkeypatch.chdir(ROOT)

    db_path = tmp_path / "shopping.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    import src.models as models

    monkeypatch.setattr(
        models, "engine", models.create_engine(db_url, **models._sqlite_kwargs(db_url))
    )
    models.init_db()
    seed_legacy_config(models)

    if "parser" in sys.modules:
        del sys.modules["parser"]
    return importlib.import_module("parser")


@pytest.mark.parametrize("menu_name", GOLDEN_MENUS)
def test_shopping_markdown_matches_golden(shopping_env, menu_name):
    golden_path = GOLDEN_DIR / f"{os.path.splitext(menu_name)[0]}.md"
    expected = golden_path.read_text(encoding="utf-8")
    actual = render_menu_to_text(shopping_env, menu_name)

    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile=f"golden/{golden_path.name}",
                tofile="rendered",
                lineterm="",
            )
        )
        pytest.fail(f"Rendered output drifted from golden:\n{diff}")
