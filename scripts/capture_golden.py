#!/usr/bin/env python
"""Regenerate the shopping-list golden fixtures.

Run from the repo root:

    uv run python scripts/capture_golden.py

The goldens lock the rendered markdown of the shopping-list pipeline. Only
regenerate them when an output change is *intentional*, and review the diff.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def main() -> int:
    os.chdir(ROOT)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "golden.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

        import src.models as models

        db_url = f"sqlite:///{db_path}"
        models.engine = models.create_engine(db_url, **models._sqlite_kwargs(db_url))
        models.init_db()

        from _shopping_fixtures import (
            GOLDEN_DIR,
            GOLDEN_MENUS,
            render_menu_to_text,
            seed_legacy_config,
        )

        seed_legacy_config(models)

        import parser as parser_module

        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        for menu_name in GOLDEN_MENUS:
            text = render_menu_to_text(parser_module, menu_name)
            target = GOLDEN_DIR / f"{pathlib.Path(menu_name).stem}.md"
            target.write_text(text, encoding="utf-8")
            print(f"wrote {target.relative_to(ROOT)}  ({len(text)} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
