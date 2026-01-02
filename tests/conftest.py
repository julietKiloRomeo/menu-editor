import importlib
import sys
from pathlib import Path

import pytest
from sqlmodel import select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app_bundle(tmp_path, monkeypatch):
    """Provide the freshly imported app module and bound models against a temp DB."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import src.models as models

    db_url = f"sqlite:///{db_path}"
    models.engine = models.create_engine(db_url, **models._sqlite_kwargs(db_url))
    models.init_db()

    if "app" in sys.modules:
        del sys.modules["app"]
    app_module = importlib.import_module("app")
    return app_module, models


@pytest.fixture()
def app_module(app_bundle):
    return app_bundle[0]


@pytest.fixture()
def models(app_bundle):
    return app_bundle[1]


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture()
def make_recipe(app_module):
    def _create(**overrides):
        payload = {
            "navn": "Test Opskrift",
            "placering": "Notebook",
            "antal": 4,
            "ingredienser": {
                "Tomat": {"amount": 2, "unit": "stk"},
            },
            "extras": {},
        }
        payload.update(overrides)
        recipe_payload = app_module.build_recipe_from_payload(payload)
        return app_module.create_recipe_record(recipe_payload)

    return _create


@pytest.fixture()
def add_category(app_module, models):
    def _add(name: str = "Produce", priority: int = 0):
        with app_module.get_session() as session:
            existing = session.exec(
                select(models.CategoryConfig).where(models.CategoryConfig.name == name)
            ).first()
            if existing:
                return existing
            category = models.CategoryConfig(name=name, priority=priority)
            session.add(category)
            session.commit()
            session.refresh(category)
            return category

    return _add


@pytest.fixture()
def add_ingredient_mapping(app_module, models):
    def _add(name: str, category_id: int):
        with app_module.get_session() as session:
            mapping = models.IngredientConfig(name=name, category_id=category_id)
            session.add(mapping)
            session.commit()
            session.refresh(mapping)
            return mapping

    return _add
