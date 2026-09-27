import base64
import datetime
import functools
import json
import os
import pathlib
import re
import socket
import subprocess
import unicodedata
from enum import Enum
from typing import Any, Dict, Iterable, List

import parser
import yaml
from flask import Flask, jsonify, render_template, request, send_from_directory, abort
from flask_cors import CORS
from fuzzywuzzy import fuzz
from openai import OpenAI
from sqlalchemy import func, or_
from sqlmodel import select, Session
from pydantic import BaseModel, Field

from src.core.ingredients import load_alias_map
from src.core.ingredients import normalise as normalise_ingredient
from src.core.nemlig import (
    ACTIONS,
    DEFAULT_MAP_PATH as NEMLIG_MAP_PATH,
    adapt_product,
    adapt_search_results,
    check_coverage,
    find_collisions,
    load_product_map,
    merge_add_lines,
    reconcile_basket,
    record_run,
    save_product_map,
    summarise_map,
)
from src.browser import BrowserUnavailable, status as browser_status
from src.nemlig_tab import (
    add_line as tab_add_line,
    ensure_session as tab_ensure_session,
    read_basket as tab_read_basket,
    search as tab_search,
)
from src.core.orders import (
    attach_search_results,
    mark_recorded,
    order_items,
    pending_queries,
    progress as order_progress,
    recent_orders,
    set_choice,
    start_order,
)
from src.core.runs import (
    latest_run,
    progress,
    progress_by_run,
    recent_runs,
    run_items,
    seed_stocked,
    set_checked,
    start_run,
)
from src.core.zones import load_zone_config, seed_zones
from src.render.export import to_dict as menu_export
from src.render.markdown import render as render_markdown
from src.models import (
    CategoryConfig,
    IngredientAlias,
    IngredientConfig,
    NemligOrder,
    NemligOrderItem,
    Recipe,
    ShoppingRun,
    ShoppingRunItem,
    StapleItem,
    StockedItem,
    AppSetting,
    get_session,
    init_db,
    initialization_lock,
)


def load_env_file(path: str = ".env", override: bool = False) -> int:
    """Load environment variables from a dotenv-style file.

    - Lines starting with '#' are ignored
    - Only KEY=VALUE pairs are considered
    - If override=False, existing environment variables are not replaced
    Returns number of keys loaded.
    """
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if not key:
                    continue
                if override or key not in os.environ:
                    os.environ[key] = value
                    count += 1
    except FileNotFoundError:
        # .env is optional
        pass
    return count


# Load .env early so subsequent config/env reads can use it
load_env_file()


app = Flask(
    __name__,
    static_url_path='',
    static_folder='static',
    template_folder='templates',
)
app.config.setdefault("FRONTEND_DIST", os.getenv("FRONTEND_DIST", "frontend/dist"))
app.config.setdefault("FRONTEND_INDEX", os.getenv("FRONTEND_INDEX", "index.html"))
app.config.setdefault("FRONTEND_ORIGIN", os.getenv("FRONTEND_ORIGIN", "*"))
# Where the generated uge_<week>_<year>.yaml menu snapshots are written.
# Defaults to the process CWD, which is the historic behaviour; set
# MENU_DATA_DIR=data to keep them out of the repo root.
app.config.setdefault("MENU_DATA_DIR", os.getenv("MENU_DATA_DIR", "."))
CORS(app, resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGIN"]}})

init_db()
_config_seeded = False
_known_unit_cache: list[str] | None = None
_unit_enum_cache: type[Enum] | None = None
_staples_seeded = False
STAPLE_LABEL_OPTIONS = [
    "Weekly staples",
    "Pantry essentials",
    "Base kit",
    "Always buy list",
    "Household basics",
]
DEFAULT_STAPLE_LABEL = STAPLE_LABEL_OPTIONS[0]


def _frontend_build_root() -> pathlib.Path:
    configured = app.config.get("FRONTEND_DIST") or "frontend/dist"
    return pathlib.Path(configured)


def _safe_send_from_directory(root: pathlib.Path, relative_path: str):
    cleaned = (relative_path or "").lstrip("/")
    if not cleaned or not root.exists():
        return None
    base = root.resolve()
    target = (base / cleaned).resolve()
    try:
        rel = target.relative_to(base)
    except ValueError:
        return None
    if not target.exists() or not target.is_file():
        return None
    return send_from_directory(str(base), rel.as_posix())


def _serve_frontend_asset(relative_path: str):
    return _safe_send_from_directory(_frontend_build_root(), relative_path)


def _serve_frontend_index_response():
    index_asset = _serve_frontend_asset(app.config.get("FRONTEND_INDEX") or "index.html")
    if index_asset is not None:
        return index_asset
    return _render_legacy_index()


def _serve_legacy_asset(relative_path: str):
    return _safe_send_from_directory(pathlib.Path("assets"), relative_path)


def _normalise_unit_value(unit: str | None) -> str:
    cleaned = (unit or "").strip()
    if not cleaned:
        return ""
    return cleaned.split("#", 1)[0].strip()


def get_known_units() -> list[str]:
    global _known_unit_cache
    if _known_unit_cache is not None:
        return _known_unit_cache

    units: set[str] = set()
    with get_session() as session:
        for recipe in session.exec(select(Recipe)).all():
            for bucket in (recipe.ingredienser or {}).values():
                units.add(_normalise_unit_value((bucket or {}).get("unit")))
            for bucket in (recipe.extras or {}).values():
                units.add(_normalise_unit_value((bucket or {}).get("unit")))

    fallback_units = {"", "stk", "spsk", "tsk", "dl", "ml", "g", "kg", "l", "portion", "pk", "pose", "fed"}
    units.update(fallback_units)
    units.add("other")

    cleaned = sorted({unit for unit in units if unit is not None}, key=lambda s: s or "")
    _known_unit_cache = cleaned
    return cleaned


def _make_enum_key(value: str, index: int) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", value or "none").upper().strip("_")
    if not key:
        key = "NONE"
    if key[0].isdigit():
        key = f"U_{key}"
    if index:
        key = f"{key}_{index}"
    return key


def get_unit_enum() -> type[Enum]:
    global _unit_enum_cache
    if _unit_enum_cache is not None:
        return _unit_enum_cache

    members: dict[str, str] = {}
    for index, unit in enumerate(get_known_units()):
        attempt = 0
        key = _make_enum_key(unit or "none", attempt)
        while key in members:
            attempt += 1
            key = _make_enum_key(unit or "none", attempt)
        members[key] = unit

    _unit_enum_cache = Enum("UnitEnum", members, module=__name__)
    return _unit_enum_cache


UnitEnum = get_unit_enum()
_default_unit_member = UnitEnum.__members__.get("NONE") or next(iter(UnitEnum))

class IngredientLine(BaseModel):
    name: str = Field(..., description="Canonical ingredient name")
    amount: float = Field(..., ge=0)
    unit: UnitEnum = Field(default=_default_unit_member)


class GeneratedRecipe(BaseModel):
    navn: str = Field(..., description="Recipe name")
    placering: str = Field(default="", description="Book/page reference if present")
    antal: int = Field(..., ge=0, description="Servings")
    slug: str | None = Field(default=None, description="Optional slug suggestion")
    ingredienser: List[IngredientLine]
    extras: List[IngredientLine] | None = None


def _serialise_ingredient_lines(lines: List[IngredientLine] | None) -> List[Dict[str, Any]]:
    serialised: List[Dict[str, Any]] = []
    if not lines:
        return serialised
    for line in lines:
        name = (line.name or "").strip()
        if not name:
            continue
        unit_value = line.unit.value if isinstance(line.unit, Enum) else str(line.unit or "")
        serialised.append(
            {
                "navn": name,
                "amount": float(line.amount),
                "unit": unit_value.strip(),
            }
        )
    return serialised


def _generated_recipe_to_payload(model: GeneratedRecipe) -> Dict[str, Any]:
    return {
        "navn": model.navn,
        "placering": model.placering,
        "antal": model.antal,
        "slug": model.slug,
        "ingredienser": _serialise_ingredient_lines(model.ingredienser),
        "extras": _serialise_ingredient_lines(model.extras),
    }


def _payload_to_yaml(payload: Dict[str, Any]) -> str:
    data = {
        "navn": payload.get("navn", ""),
        "placering": payload.get("placering", ""),
        "antal": payload.get("antal", 0),
        "slug": payload.get("slug"),
        "ingredienser": {
            item["navn"]: {"amount": item["amount"], "unit": item["unit"]}
            for item in payload.get("ingredienser") or []
            if item.get("navn")
        },
    }
    extras_source = payload.get("extras") or []
    if extras_source:
        if isinstance(extras_source, dict):
            extras_items = extras_source.items()
        else:
            extras_items = [
                (item.get("navn"), {"amount": item.get("amount"), "unit": item.get("unit")})
                for item in extras_source
                if item.get("navn")
            ]
        data["extras"] = {
            name: {"amount": value.get("amount"), "unit": value.get("unit")}
            for name, value in extras_items
            if name
        }
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()


def serialise_staple(item: StapleItem) -> Dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "amount": float(item.amount),
        "unit": item.unit,
    }


def fetch_staples() -> list[StapleItem]:
    with get_session() as session:
        return session.exec(select(StapleItem).order_by(StapleItem.name)).all()


def staples_response() -> Dict[str, Any]:
    return {
        "items": [serialise_staple(item) for item in fetch_staples()],
        "label": get_staple_label(),
        "label_options": STAPLE_LABEL_OPTIONS,
    }


def get_staple_label(session: Session | None = None) -> str:
    if session is None:
        with get_session() as temp_session:
            return get_staple_label(temp_session)

    setting = session.exec(
        select(AppSetting).where(AppSetting.key == "staples_label")
    ).first()
    if setting and (setting.value or "").strip():
        return setting.value.strip()
    return DEFAULT_STAPLE_LABEL


def set_staple_label(label: str) -> str:
    cleaned = (label or DEFAULT_STAPLE_LABEL).strip() or DEFAULT_STAPLE_LABEL
    with get_session() as session:
        record = session.exec(
            select(AppSetting).where(AppSetting.key == "staples_label")
        ).first()
        if record:
            record.value = cleaned
            session.add(record)
        else:
            session.add(AppSetting(key="staples_label", value=cleaned))
        session.commit()
        return cleaned


def seed_config_from_yaml() -> None:
    """Give a brand-new database the default kitchen layout.

    Only ever runs against a genuinely empty config -- an existing
    installation keeps whatever zones its owner has set up. Use
    ``scripts/seed_zones.py --force`` to update one deliberately.
    """
    global _config_seeded
    if _config_seeded:
        return

    # Keyed on assignments, not categories: zones with nothing mapped into them
    # do nothing at all, so that state is indistinguishable from unconfigured.
    _categories, items = fetch_config()
    if not items:
        try:
            result = seed_zones(only_if_empty=True)
            if result.changed:
                app.logger.info(
                    "Seeded default kitchen zones: %s zones, %s ingredient assignments.",
                    result.zones_added,
                    result.assignments_added,
                )
        except Exception:  # pragma: no cover - seeding must never block start-up
            app.logger.exception(
                "Could not seed default kitchen zones; configure them via /api/config."
            )

    try:
        stock = seed_stocked(only_if_empty=True)
        if stock.added:
            app.logger.info(
                "Seeded %s usually-stocked ingredients.", stock.added
            )
    except Exception:  # pragma: no cover - seeding must never block start-up
        app.logger.exception(
            "Could not seed the usually-stocked list; manage it via /api/stocked."
        )

    _config_seeded = True


def seed_staples_from_legacy() -> None:
    global _staples_seeded
    if _staples_seeded:
        return

    recipe_path = pathlib.Path("recipes/standardvarer.yml")
    if not recipe_path.exists():
        _staples_seeded = True
        return

    try:
        data = yaml.safe_load(recipe_path.read_text(encoding="utf-8")) or {}
    except Exception:
        _staples_seeded = True
        return

    ingredienser = data.get("ingredienser") or {}
    if not ingredienser:
        _staples_seeded = True
        return

    # Reading the existing rows and inserting the missing ones is not atomic, so
    # concurrently booting gunicorn workers would otherwise all insert the same
    # staples and collide on stapleitem.name.
    with initialization_lock():
        with get_session() as session:
            existing = {
                (item.name or "").strip().lower(): item
                for item in session.exec(select(StapleItem)).all()
            }
            added = False
            for name, value in ingredienser.items():
                cleaned_name = (name or "").strip()
                if not cleaned_name:
                    continue
                key = cleaned_name.lower()
                if key in existing:
                    continue
                try:
                    amount_value = float(value.get("amount", 1))
                except (TypeError, ValueError):
                    amount_value = 1.0
                unit_value = _normalise_unit_value(value.get("unit"))
                session.add(
                    StapleItem(name=cleaned_name, amount=amount_value or 1.0, unit=unit_value)
                )
                added = True
            if added:
                session.commit()

    _staples_seeded = True

_openai_client: OpenAI | None = None


def normalise_slug(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "recipe"


def ensure_unique_slug(base_slug: str) -> str:
    with get_session() as session:
        slug = base_slug
        counter = 1
        while session.exec(select(Recipe).where(Recipe.slug == slug)).first():
            counter += 1
            slug = f"{base_slug}-{counter}"
    return slug


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set")
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            _openai_client = OpenAI(base_url=base_url)
        else:
            _openai_client = OpenAI()
    return _openai_client


def fetch_recipes(include_blacklisted: bool = False) -> List[Recipe]:
    with get_session() as session:
        statement = select(Recipe)
        if not include_blacklisted:
            statement = statement.where(
                or_(Recipe.is_blacklisted.is_(False), Recipe.is_whitelisted.is_(True))
            )
        statement = statement.order_by(Recipe.navn)
        return list(session.exec(statement).all())


def fetch_recipes_by_names(names: Iterable[str]) -> Dict[str, Recipe]:
    unique_names = list({name for name in names if name})
    if not unique_names:
        return {}
    with get_session() as session:
        statement = select(Recipe).where(Recipe.navn.in_(unique_names))
        results = session.exec(statement).all()
        return {recipe.navn: recipe for recipe in results}


def fetch_recipe_by_identifier(identifier: str) -> Recipe | None:
    if not identifier:
        return None
    with get_session() as session:
        statement = select(Recipe).where(
            or_(Recipe.slug == identifier, Recipe.navn == identifier)
        )
        return session.exec(statement).first()


def serialise_recipe(recipe: Recipe) -> Dict[str, Any]:
    return {
        "id": recipe.id,
        "slug": recipe.slug,
        "navn": recipe.navn,
        "placering": recipe.placering or "",
        "antal": recipe.antal,
        "ingredienser": recipe.ingredienser or {},
        "extras": recipe.extras or {},
        "is_blacklisted": recipe.is_blacklisted,
        "is_whitelisted": recipe.is_whitelisted,
    }


def serialise_category(category: CategoryConfig) -> Dict[str, Any]:
    return {
        "id": category.id,
        "name": category.name,
        "priority": category.priority,
    }


def serialise_ingredient_config(item: IngredientConfig, categories: Dict[int, CategoryConfig]) -> Dict[str, Any]:
    category = categories.get(item.category_id)
    return {
        "id": item.id,
        "name": item.name,
        "category_id": item.category_id,
        "category_name": category.name if category else None,
    }


_canonical_ingredient_cache: list[str] | None = None


def fetch_config() -> tuple[list[CategoryConfig], list[IngredientConfig]]:
    with get_session() as session:
        categories = session.exec(
            select(CategoryConfig).order_by(CategoryConfig.priority, CategoryConfig.name)
        ).all()
        items = session.exec(
            select(IngredientConfig).order_by(IngredientConfig.name)
        ).all()
    return categories, items


def get_canonical_ingredient_names() -> list[str]:
    global _canonical_ingredient_cache
    if _canonical_ingredient_cache is not None:
        return _canonical_ingredient_cache

    _, items = fetch_config()
    names = [item.name for item in items if item.name]

    _canonical_ingredient_cache = names
    return names


def fetch_aliases() -> List[IngredientAlias]:
    with get_session() as session:
        return list(session.exec(select(IngredientAlias)).all())


def serialise_alias(alias: IngredientAlias) -> Dict[str, Any]:
    return {"id": alias.id, "alias": alias.alias, "canonical": alias.canonical}


def build_config_payload() -> Dict[str, Any]:
    categories, items = fetch_config()
    category_map = {category.id: category for category in categories}
    staples = fetch_staples()
    return {
        "categories": [serialise_category(category) for category in categories],
        "items": [
            serialise_ingredient_config(item, category_map)
            for item in items
        ],
        "staples": [serialise_staple(item) for item in staples],
        "staple_label": get_staple_label(),
        "staple_label_options": STAPLE_LABEL_OPTIONS,
        "aliases": [serialise_alias(alias) for alias in fetch_aliases()],
    }


seed_config_from_yaml()
seed_staples_from_legacy()


def staple_api(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Staple API failed: %s", exc)
            return jsonify({"error": "Staple operation failed"}), 500
    return wrapper


def coerce_ingredients(raw_ingredients: Any, *, field_name: str = "ingredienser") -> Dict[str, Dict[str, Any]]:
    if raw_ingredients is None:
        if field_name == "ingredienser":
            raise ValueError("Missing ingredients")
        return {}

    ingredients: Dict[str, Dict[str, Any]] = {}

    if isinstance(raw_ingredients, dict):
        iterable = raw_ingredients.items()
    else:
        iterable = []
        for item in raw_ingredients:
            if not isinstance(item, dict):
                raise ValueError(
                    f"{field_name.capitalize()} items must be objects with name, amount and unit"
                )
            name = (
                item.get("navn")
                or item.get("name")
                or item.get("ingredient")
                or ""
            ).strip()
            if not name:
                continue
            iterable.append(
                (
                    name,
                    {
                        "amount": item.get("amount"),
                        "unit": item.get("unit"),
                    },
                )
            )

    for ingredient_name, value in iterable:
        if not ingredient_name:
            continue
        if isinstance(value, dict):
            amount = value.get("amount", 0)
            unit = value.get("unit", "")
        else:
            raise ValueError(f"{field_name.capitalize()} values must be dictionaries")

        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid amount for {field_name[:-1]} '{ingredient_name}'"
            ) from None

        ingredients[ingredient_name] = {
            "amount": amount_value,
            "unit": str(unit or "").strip(),
        }

    if field_name == "ingredienser" and not ingredients:
        raise ValueError("At least one ingredient is required")

    return ingredients


def build_recipe_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not payload or not isinstance(payload, dict):
        raise ValueError("Invalid payload")

    name = (payload.get("navn") or payload.get("name") or "").strip()
    placement = (payload.get("placering") or payload.get("placement") or "").strip()
    servings = payload.get("antal") or payload.get("servings")
    ingredients_payload = payload.get("ingredienser") or payload.get("ingredients")
    extras_payload = payload.get("extras")

    if not name:
        raise ValueError("'navn' is required")

    try:
        servings = int(servings)
        if servings < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("'antal' must be a non-negative integer")

    ingredients = coerce_ingredients(ingredients_payload, field_name="ingredienser")
    extras = coerce_ingredients(extras_payload, field_name="extras") if extras_payload else {}

    is_blacklisted = bool(payload.get("is_blacklisted", False))
    is_whitelisted = bool(payload.get("is_whitelisted", False))

    slug_hint = payload.get("slug") or payload.get("filename") or normalise_slug(name)
    slug = ensure_unique_slug(normalise_slug(slug_hint))

    return {
        "slug": slug,
        "navn": name,
        "placering": placement,
        "antal": servings,
        "ingredienser": ingredients,
        "extras": extras,
        "is_blacklisted": is_blacklisted,
        "is_whitelisted": is_whitelisted,
    }


def create_recipe_record(recipe_payload: Dict[str, Any]) -> Recipe:
    with get_session() as session:
        recipe = Recipe(**recipe_payload)
        session.add(recipe)
        session.commit()
        session.refresh(recipe)
        return recipe


def parse_recipe_yaml(yaml_text: str) -> Dict[str, Any]:
    try:
        loaded = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not parse YAML returned by model: {exc}") from exc
    payload = build_recipe_from_payload(loaded)
    # Use model-provided slug if present after normalisation without enforcing uniqueness again
    payload["slug"] = normalise_slug(loaded.get("slug") or payload["slug"])
    return payload


def generate_recipe_from_image(
    image_bytes: bytes,
    mimetype: str,
    extra_prompt: str = "",
) -> tuple[Dict[str, Any], str]:
    client = get_openai_client()
    base64_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mimetype};base64,{base64_image}"
    canonical_ingredients = get_canonical_ingredient_names()
    canonical_instruction = ""

    if canonical_ingredients:
        canonical_instruction = (
            "Use the canonical ingredient names listed below whenever they match the image. "
            "Always spell them exactly as provided. Only invent a new name when you cannot find a match.\n\n"
            "Canonical ingredient names:\n"
            + "\n".join(f"- {name}" for name in canonical_ingredients)
        )

    model_name = os.getenv("RECIPE_IMAGE_MODEL", "gpt-5-mini")
    user_instructions = (
        "Extract every detail from this recipe photo and produce structured data following the provided schema. "
        "Populate 'ingredienser' with every component of the recipe. Use 'extras' for fresh side items or toppings we still need to buy when reheating or serving a pre-made dish (e.g. bread, salad, garnish). "
        "Amounts must be numeric floats and units short text. Feel free to add '#' notes inside the unit when uncertain."
    )

    if canonical_instruction:
        user_instructions += f"\n\n{canonical_instruction}"

    known_units = get_known_units()
    if known_units:
        units_text = ", ".join(unit or "(none)" for unit in known_units)
        user_instructions += (
            "\n\nUse only these measurement units for 'unit' fields (choose 'other' if nothing fits): "
            f"{units_text}."
        )

    if extra_prompt:
        user_instructions += f"\n\nAdditional user notes: {extra_prompt.strip()}"

    try:
        response = client.beta.chat.completions.parse(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a culinary assistant that extracts recipes from photos and returns structured JSON.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_instructions},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format=GeneratedRecipe,
        )
    except Exception as exc:  # pragma: no cover - network failure/pass-through
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc

    choice = response.choices[0]
    parsed_recipe: GeneratedRecipe | None = getattr(choice.message, "parsed", None)
    if not parsed_recipe:
        raise RuntimeError("Model did not return structured recipe data")

    raw_payload = _generated_recipe_to_payload(parsed_recipe)
    recipe_payload = build_recipe_from_payload(raw_payload)
    raw_yaml = _payload_to_yaml(raw_payload)
    return recipe_payload, raw_yaml


def add_standard_items(menu_recipes: Dict[str, Any]) -> None:
    staples = fetch_staples()
    if not staples:
        return

    label = get_staple_label()
    entries: list[dict[str, dict[str, Any]]] = []
    for item in staples:
        if not item.name:
            continue
        entries.append(
            {
                item.name: {
                    "amount": float(item.amount or 0) or 1,
                    "unit": item.unit or "",
                }
            }
        )

    if entries:
        menu_recipes[label] = entries


def _render_legacy_index():
    recipe_names = [recipe.navn for recipe in fetch_recipes()]
    return render_template('index.html', recipes=json.dumps(recipe_names))


@app.route('/')
def index():
    spa_response = _serve_frontend_asset(app.config.get("FRONTEND_INDEX") or "index.html")
    if spa_response is not None:
        return spa_response
    return _render_legacy_index()


@app.route('/assets/<path:asset_path>')
def serve_asset(asset_path: str):
    spa_asset = _serve_frontend_asset(f"assets/{asset_path}")
    if spa_asset is not None:
        return spa_asset
    legacy_asset = _serve_legacy_asset(asset_path)
    if legacy_asset is not None:
        return legacy_asset
    abort(404)


@app.route('/favicon.ico')
def favicon():
    asset = (
        _serve_frontend_asset('favicon.ico')
        or _serve_frontend_asset('favicon.svg')
        or _serve_legacy_asset('favicon.ico')
    )
    if asset is not None:
        return asset
    abort(404)


@app.route('/favicon.svg')
def favicon_svg():
    asset = _serve_frontend_asset('favicon.svg') or _serve_legacy_asset('favicon.svg')
    if asset is not None:
        return asset
    abort(404)


@app.route('/search_recipes', methods=['GET'])
def search_recipes():
    try:
        query = (request.args.get('query') or '').lower().strip()
        recipes = fetch_recipes()

        if not query:
            return jsonify({'recipes': [recipe.navn for recipe in recipes[:6]]})

        scored_matches: List[Dict[str, Any]] = []

        for recipe in recipes:
            score = fuzz.partial_ratio(query, recipe.navn.lower())
            for ingredient_name in recipe.ingredienser.keys():
                ingredient_score = fuzz.partial_ratio(query, ingredient_name.lower())
                score = max(score, ingredient_score)

            if score > 80:
                scored_matches.append({'name': recipe.navn, 'score': score})

        sorted_matches = sorted(scored_matches, key=lambda x: -x['score'])
        matched_names = [match['name'] for match in sorted_matches[:6]]

        return jsonify({'recipes': matched_names, 'total_matches': len(scored_matches)})

    except Exception as exc:
        app.logger.error("Error in search_recipes: %s", exc)
        return jsonify({'error': 'An error occurred while searching recipes', 'recipes': []}), 500


app.add_url_rule(
    '/api/recipes/search',
    view_func=search_recipes,
    methods=['GET'],
    endpoint='api_search_recipes',
)


def _norm_text(s: str) -> str:
    s = s or ""
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


def _find_key(mapping: dict[str, Any], name: str, *, case_insensitive: bool = True) -> str | None:
    if mapping is None:
        return None
    if not case_insensitive:
        return name if name in mapping else None
    target = _norm_text(name)
    for key in mapping.keys():
        if _norm_text(key) == target:
            return key
    return None


def _collect_all_ingredient_names() -> list[str]:
    names: set[str] = set()
    with get_session() as session:
        # From config items
        for item in session.exec(select(IngredientConfig)).all():
            if item.name:
                names.add(item.name)
        # From recipes
        for recipe in session.exec(select(Recipe)).all():
            for key in (recipe.ingredienser or {}).keys():
                if key:
                    names.add(key)
            for key in (recipe.extras or {}).keys():
                if key:
                    names.add(key)
    return sorted(names)


@app.route('/api/ingredients/similar')
def similar_ingredients():
    name = (request.args.get('name') or '').strip()
    if not name:
        return jsonify({"names": []})
    try:
        limit = int(request.args.get('limit', 10))
    except ValueError:
        limit = 10

    try:
        pool = _collect_all_ingredient_names()
        scored = [
            (candidate, fuzz.ratio(name.lower(), (candidate or '').lower()))
            for candidate in pool
            if candidate and candidate.lower() != name.lower()
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        names = [n for n, score in scored[:limit] if score >= 70]
        return jsonify({"names": names})
    except Exception as exc:
        app.logger.exception("similar_ingredients failed: %s", exc)
        return jsonify({"error": "Failed to compute similar names"}), 500


@app.route('/api/ingredients/usage')
def ingredient_usage():
    name = (request.args.get('name') or '').strip()
    include_extras = (request.args.get('include_extras', 'true').lower() not in {'0', 'false', 'no'})
    if not name:
        return jsonify({"error": "name is required"}), 400

    usages: list[dict[str, Any]] = []
    try:
        with get_session() as session:
            for recipe in session.exec(select(Recipe)).all():
                key = _find_key(recipe.ingredienser or {}, name, case_insensitive=True)
                if key is not None:
                    usages.append({
                        "recipe_slug": recipe.slug,
                        "recipe_name": recipe.navn,
                        "field": "ingredienser",
                    })
                if include_extras:
                    key2 = _find_key(recipe.extras or {}, name, case_insensitive=True)
                    if key2 is not None:
                        usages.append({
                            "recipe_slug": recipe.slug,
                            "recipe_name": recipe.navn,
                            "field": "extras",
                        })
        return jsonify({"usages": usages})
    except Exception as exc:
        app.logger.exception("ingredient_usage failed: %s", exc)
        return jsonify({"error": "Failed to search usage"}), 500


@app.route('/api/ingredients/rename', methods=['POST'])
def ingredient_rename():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    from_name = (payload.get('from') or '').strip()
    to_name = (payload.get('to') or '').strip()
    include_extras = bool(payload.get('include_extras', True))
    force = bool(payload.get('force', False))
    case_insensitive = bool(payload.get('case_insensitive', True))

    if not from_name or not to_name:
        return jsonify({"error": "'from' and 'to' are required"}), 400

    updated_count = 0
    conflicts: list[dict[str, Any]] = []

    def process_mapping(mapping: dict[str, Any]) -> tuple[dict[str, Any], bool, dict | None]:
        if not mapping:
            return mapping or {}, False, None
        src_key = _find_key(mapping, from_name, case_insensitive=case_insensitive)
        if not src_key:
            return mapping, False, None
        dst_key = _find_key(mapping, to_name, case_insensitive=case_insensitive) or to_name
        if dst_key in mapping and dst_key != src_key:
            src_val = mapping.get(src_key) or {}
            dst_val = mapping.get(dst_key) or {}
            try:
                src_amt = float(src_val.get('amount', 0))
            except Exception:
                src_amt = None
            try:
                dst_amt = float(dst_val.get('amount', 0))
            except Exception:
                dst_amt = None
            src_unit = (src_val.get('unit') or '').strip()
            dst_unit = (dst_val.get('unit') or '').strip()
            if src_amt is not None and dst_amt is not None and src_unit == dst_unit:
                dst_val['amount'] = float(dst_amt) + float(src_amt)
                mapping = dict(mapping)
                mapping[dst_key] = dst_val
                mapping.pop(src_key, None)
                return mapping, True, None
            else:
                if force:
                    # Remove the source to avoid duplication, keep destination as-is
                    mapping = dict(mapping)
                    mapping.pop(src_key, None)
                    return mapping, True, {"reason": "conflict (unit/amount mismatch) - removed source, kept destination"}
                else:
                    return mapping, False, {"reason": "conflict (unit/amount mismatch)", "conflict_with": dst_key}
        else:
            mapping = dict(mapping)
            mapping[dst_key] = mapping.get(src_key) or {}
            if dst_key != src_key:
                mapping.pop(src_key, None)
            return mapping, True, None

    try:
        with get_session() as session:
            recipes = session.exec(select(Recipe)).all()
            for recipe in recipes:
                changed = False
                # ingredienser
                new_map, mutated, conflict = process_mapping(recipe.ingredienser or {})
                if mutated:
                    recipe.ingredienser = new_map
                    changed = True
                if conflict:
                    conflicts.append({
                        "slug": recipe.slug,
                        "name": recipe.navn,
                        "field": "ingredienser",
                        **conflict,
                    })
                # extras
                if include_extras:
                    new_extra_map, mutated2, conflict2 = process_mapping(recipe.extras or {})
                    if mutated2:
                        recipe.extras = new_extra_map
                        changed = True
                    if conflict2:
                        conflicts.append({
                            "slug": recipe.slug,
                            "name": recipe.navn,
                            "field": "extras",
                            **conflict2,
                        })
                if changed:
                    session.add(recipe)
                    updated_count += 1
            session.commit()
        return jsonify({"updated_count": updated_count, "conflicts": conflicts})
    except Exception as exc:
        app.logger.exception("ingredient_rename failed: %s", exc)
        return jsonify({"error": "Failed to rename ingredient"}), 500


@app.route('/generate_menu', methods=['POST'])
def generate_menu():
    chosen_recipes = request.json.get('menu_data', {})
    recipe_objects = fetch_recipes_by_names(chosen_recipes.keys())

    if not recipe_objects:
        return jsonify({"error": "No valid recipes supplied"}), 400

    menu_structure: Dict[str, Any] = {}
    for recipe_name, plates in chosen_recipes.items():
        recipe = recipe_objects.get(recipe_name)
        if not recipe:
            continue
        menu_structure[recipe.navn] = [
            {
                recipe.slug: {
                    "amount": plates,
                    "unit": "plates",
                }
            }
        ]

    add_standard_items(menu_structure)
    menu_path = save_menu(menu_structure)

    aggregated = parser.aggregate_menu_file(
        menu_path,
        silent_sections={get_staple_label()},
    )

    menu_text = MenuText()
    render_markdown(aggregated, printer=menu_text.add)

    # The markdown is the printable menu; the export is the machine-readable
    # hand-off that scripts/import_menu.py turns back into a shopping run.
    return jsonify({
        "markdown": str(menu_text),
        "export": menu_export(aggregated, name=menu_path.stem),
    })


app.add_url_rule(
    '/api/menu/generate',
    view_func=generate_menu,
    methods=['POST'],
    endpoint='api_generate_menu',
)


@app.route('/api/status', methods=['GET'])
def app_status():
    """Which database this process is actually serving.

    Two stale dev servers once sat on port 5000 holding a six-recipe demo
    database, and the app looked like it had lost the entire recipe collection
    and was showing last week's menu. Nothing on screen said which file was
    open, so the obvious reading was "the data is gone" rather than "this is a
    different database". The identity of the data is part of the data.
    """
    from src.models import DATABASE_URL

    path = DATABASE_URL
    resolved = ""
    if path.startswith("sqlite:///"):
        candidate = pathlib.Path(path[len("sqlite:///") :])
        resolved = str(candidate if candidate.is_absolute() else candidate.resolve())

    with get_session() as session:
        recipes = session.exec(select(func.count()).select_from(Recipe)).one()

    return jsonify(
        {
            "database_url": DATABASE_URL,
            "database_path": resolved,
            "recipes": recipes,
            "host": socket.gethostname(),
        }
    )


@app.route('/api/recipes', methods=['GET'])
def list_recipes():
    include_blacklisted = request.args.get('include_blacklisted', 'true').lower() not in {'0', 'false', 'no'}
    only_names = request.args.get('only_names', '').lower() in {'1', 'true', 'yes'}

    recipes = fetch_recipes(include_blacklisted=include_blacklisted)

    if only_names:
        payload = [recipe.navn for recipe in recipes]
    else:
        payload = [serialise_recipe(recipe) for recipe in recipes]

    return jsonify({"recipes": payload})


@app.route('/api/recipes/<string:identifier>', methods=['GET'])
def get_recipe(identifier: str):
    recipe = fetch_recipe_by_identifier(identifier)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404
    return jsonify({"recipe": serialise_recipe(recipe)})


@app.route('/api/recipes', methods=['POST'])
def create_recipe_api():
    try:
        payload = request.get_json(force=True)
    except Exception:
        payload = None

    if not payload:
        return jsonify({"error": "Invalid JSON payload"}), 400

    try:
        recipe_payload = build_recipe_from_payload(payload)
        recipe = create_recipe_record(recipe_payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        app.logger.exception("Failed to create recipe: %s", exc)
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        app.logger.exception("Unexpected failure while creating recipe: %s", exc)
        return jsonify({"error": "Failed to create recipe"}), 500

    recipes = fetch_recipes()
    return jsonify({
        "message": "Recipe created",
        "recipe": serialise_recipe(recipe),
        "recipes": [r.navn for r in recipes],
    }), 201


@app.route('/api/recipes/<string:identifier>', methods=['PATCH'])
def update_recipe(identifier: str):
    recipe = fetch_recipe_by_identifier(identifier)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404

    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    updates: Dict[str, Any] = {}

    if 'navn' in payload:
        new_name = (payload['navn'] or '').strip()
        if not new_name:
            return jsonify({"error": "'navn' cannot be empty"}), 400
        updates['navn'] = new_name

    if 'placering' in payload:
        updates['placering'] = (payload['placering'] or '').strip()

    if 'antal' in payload:
        try:
            updates['antal'] = max(0, int(payload['antal']))
        except (TypeError, ValueError):
            return jsonify({"error": "'antal' must be a non-negative integer"}), 400

    if 'ingredienser' in payload:
        updates['ingredienser'] = coerce_ingredients(payload['ingredienser'])

    if 'extras' in payload:
        updates['extras'] = coerce_ingredients(payload['extras'], field_name="extras")

    if 'is_blacklisted' in payload:
        updates['is_blacklisted'] = bool(payload['is_blacklisted'])

    if 'is_whitelisted' in payload:
        updates['is_whitelisted'] = bool(payload['is_whitelisted'])

    if 'slug' in payload:
        new_slug = normalise_slug(payload['slug'] or '')
        if not new_slug:
            return jsonify({"error": "'slug' cannot be empty"}), 400
        updates['slug'] = new_slug

    with get_session() as session:
        db_recipe = session.exec(
            select(Recipe).where(Recipe.id == recipe.id)
        ).one()

        if 'navn' in updates and updates['navn'] != db_recipe.navn:
            existing_name = session.exec(
                select(Recipe).where(Recipe.navn == updates['navn'], Recipe.id != db_recipe.id)
            ).first()
            if existing_name:
                return jsonify({"error": "Another recipe already uses that name"}), 400

        if 'slug' in updates and updates['slug'] != db_recipe.slug:
            existing_slug = session.exec(
                select(Recipe).where(Recipe.slug == updates['slug'], Recipe.id != db_recipe.id)
            ).first()
            if existing_slug:
                return jsonify({"error": "Another recipe already uses that slug"}), 400

        for key, value in updates.items():
            setattr(db_recipe, key, value)
        session.add(db_recipe)
        session.commit()
        session.refresh(db_recipe)

    refreshed_identifier = updates.get('slug', identifier)
    refreshed = fetch_recipe_by_identifier(refreshed_identifier)
    return jsonify({"recipe": serialise_recipe(refreshed)})


@app.route('/api/recipes/from-image', methods=['POST'])
def create_recipe_from_image():
    image = request.files.get('image')
    if image is None or image.filename == "":
        return jsonify({"error": "Image file is required"}), 400

    try:
        image_bytes = image.read()
    except Exception:
        return jsonify({"error": "Could not read uploaded file"}), 400

    if not image_bytes:
        return jsonify({"error": "Uploaded file was empty"}), 400

    prompt = request.form.get('prompt', '')
    mimetype = image.mimetype or 'image/jpeg'

    try:
        recipe_payload, raw_yaml = generate_recipe_from_image(image_bytes, mimetype, prompt)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502

    suggested_slug = ensure_unique_slug(recipe_payload["slug"])
    recipe_payload["slug"] = suggested_slug

    response_payload = {
        "navn": recipe_payload["navn"],
        "placering": recipe_payload.get("placering", ""),
        "antal": recipe_payload["antal"],
        "ingredienser": recipe_payload["ingredienser"],
        "extras": recipe_payload.get("extras", {}),
        "suggested_slug": suggested_slug,
        "raw_yaml": raw_yaml,
    }

    return jsonify({"recipe": response_payload})


@app.route('/api/config', methods=['GET'])
def get_config_api():
    return jsonify(build_config_payload())


@app.route('/api/config/categories', methods=['POST'])
def create_category_api():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    name = (payload.get('name') or '').strip()
    if not name:
        return jsonify({"error": "Category name is required"}), 400

    try:
        priority = int(payload.get('priority', 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Priority must be an integer"}), 400

    with get_session() as session:
        existing = session.exec(
            select(CategoryConfig).where(CategoryConfig.name == name)
        ).first()
        if existing:
            return jsonify({"error": "Category already exists"}), 400

        category = CategoryConfig(name=name, priority=priority)
        session.add(category)
        session.commit()

    return jsonify(build_config_payload()), 201


@app.route('/api/staples', methods=['GET'])
@staple_api
def get_staples_api():
    return jsonify(staples_response())


def _parse_staple_payload(payload: Dict[str, Any], *, require_name: bool = False) -> tuple[str | None, float | None, str | None]:
    name = (payload.get('name') or '').strip()
    if require_name and not name:
        raise ValueError("Name is required")

    amount_raw = payload.get('amount')
    amount_value: float | None = None
    if amount_raw is not None:
        try:
            amount_value = float(amount_raw)
        except (TypeError, ValueError):
            raise ValueError("Amount must be a number")
        if amount_value < 0:
            raise ValueError("Amount must be positive")

    unit = _normalise_unit_value(payload.get('unit'))
    return name or None, amount_value, unit


@app.route('/api/staples', methods=['POST'])
@staple_api
def create_staple_api():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    try:
        name, amount, unit = _parse_staple_payload(payload, require_name=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    amount_value = amount if amount is not None else 1.0
    with get_session() as session:
        existing = session.exec(select(StapleItem).where(StapleItem.name == name)).first()
        if existing:
            return jsonify({"error": "Staple already exists"}), 400
        staple = StapleItem(name=name, amount=amount_value, unit=unit)
        session.add(staple)
        session.commit()
        session.refresh(staple)

    response = staples_response()
    response["item"] = serialise_staple(staple)
    return jsonify(response), 201


@app.route('/api/staples/<int:item_id>', methods=['PATCH'])
@staple_api
def update_staple_api(item_id: int):
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    if not payload:
        return jsonify({"error": "No fields provided"}), 400

    try:
        name, amount, unit = _parse_staple_payload(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    with get_session() as session:
        staple = session.get(StapleItem, item_id)
        if not staple:
            return jsonify({"error": "Staple not found"}), 404

        if name:
            existing = session.exec(
                select(StapleItem).where(StapleItem.name == name, StapleItem.id != staple.id)
            ).first()
            if existing:
                return jsonify({"error": "Another staple already uses that name"}), 400
            staple.name = name
        if amount is not None:
            staple.amount = amount
        if unit is not None:
            staple.unit = unit
        session.add(staple)
        session.commit()
        session.refresh(staple)

    response = staples_response()
    response["item"] = serialise_staple(staple)
    return jsonify(response)


@app.route('/api/staples/<int:item_id>', methods=['DELETE'])
@staple_api
def delete_staple_api(item_id: int):
    with get_session() as session:
        staple = session.get(StapleItem, item_id)
        if not staple:
            return jsonify({"error": "Staple not found"}), 404
        session.delete(staple)
        session.commit()

    return jsonify(staples_response())


@app.route('/api/staples/label', methods=['POST'])
@staple_api
def update_staple_label_api():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    label_choice = (payload.get('label') or '').strip()
    custom_label = (payload.get('custom_label') or '').strip()
    use_custom = bool(payload.get('use_custom'))

    new_label = custom_label if use_custom and custom_label else label_choice
    if not new_label:
        return jsonify({"error": "Label cannot be empty"}), 400

    saved = set_staple_label(new_label)
    response = staples_response()
    response["label"] = saved
    return jsonify(response)

@app.route('/api/config/categories/<int:category_id>', methods=['PATCH'])
def update_category_api(category_id: int):
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    with get_session() as session:
        category = session.get(CategoryConfig, category_id)
        if not category:
            return jsonify({"error": "Category not found"}), 404

        if 'name' in payload:
            new_name = (payload['name'] or '').strip()
            if not new_name:
                return jsonify({"error": "Category name cannot be empty"}), 400
            existing = session.exec(
                select(CategoryConfig).where(
                    CategoryConfig.name == new_name,
                    CategoryConfig.id != category_id,
                )
            ).first()
            if existing:
                return jsonify({"error": "Another category already uses that name"}), 400
            category.name = new_name

        if 'priority' in payload:
            try:
                category.priority = int(payload['priority'])
            except (TypeError, ValueError):
                return jsonify({"error": "Priority must be an integer"}), 400

        session.add(category)
        session.commit()

    return jsonify(build_config_payload())


@app.route('/api/config/categories/<int:category_id>', methods=['DELETE'])
def delete_category_api(category_id: int):
    with get_session() as session:
        category = session.get(CategoryConfig, category_id)
        if not category:
            return jsonify({"error": "Category not found"}), 404

        in_use = session.exec(
            select(IngredientConfig).where(IngredientConfig.category_id == category_id)
        ).first()
        if in_use:
            return jsonify({"error": "Remove ingredient mappings before deleting this category"}), 400

        session.delete(category)
        session.commit()

    return jsonify(build_config_payload())


@app.route('/api/config/items', methods=['POST'])
def create_ingredient_config():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    name = (payload.get('name') or '').strip()
    category_id = payload.get('category_id')
    if not name:
        return jsonify({"error": "Ingredient name is required"}), 400

    try:
        category_id = int(category_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Valid category_id is required"}), 400

    with get_session() as session:
        category = session.get(CategoryConfig, category_id)
        if not category:
            return jsonify({"error": "Category not found"}), 404

        existing = session.exec(
            select(IngredientConfig).where(IngredientConfig.name == name)
        ).first()
        if existing:
            return jsonify({"error": "Ingredient mapping already exists"}), 400

        item = IngredientConfig(name=name, category_id=category_id)
        session.add(item)
        session.commit()

    return jsonify(build_config_payload()), 201


@app.route('/api/config/items/<int:item_id>', methods=['PATCH'])
def update_ingredient_config(item_id: int):
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    with get_session() as session:
        item = session.get(IngredientConfig, item_id)
        if not item:
            return jsonify({"error": "Ingredient mapping not found"}), 404

        if 'name' in payload:
            new_name = (payload['name'] or '').strip()
            if not new_name:
                return jsonify({"error": "Ingredient name cannot be empty"}), 400
            existing = session.exec(
                select(IngredientConfig).where(
                    IngredientConfig.name == new_name,
                    IngredientConfig.id != item_id,
                )
            ).first()
            if existing:
                return jsonify({"error": "Another mapping already uses that ingredient"}), 400
            item.name = new_name

        if 'category_id' in payload:
            try:
                new_category_id = int(payload['category_id'])
            except (TypeError, ValueError):
                return jsonify({"error": "Valid category_id is required"}), 400
            category = session.get(CategoryConfig, new_category_id)
            if not category:
                return jsonify({"error": "Category not found"}), 404
            item.category_id = new_category_id

        session.add(item)
        session.commit()

    return jsonify(build_config_payload())


@app.route('/api/config/items/<int:item_id>', methods=['DELETE'])
def delete_ingredient_config(item_id: int):
    with get_session() as session:
        item = session.get(IngredientConfig, item_id)
        if not item:
            return jsonify({"error": "Ingredient mapping not found"}), 404
        session.delete(item)
        session.commit()

    return jsonify(build_config_payload())


@app.route('/api/config/aliases', methods=['POST'])
@staple_api
def create_alias_api():
    payload = request.get_json(silent=True) or {}
    alias = (payload.get("alias") or "").strip()
    canonical = (payload.get("canonical") or "").strip()

    if not alias:
        raise ValueError("Alias is required")
    if not canonical:
        raise ValueError("Canonical name is required")
    if normalise_ingredient(alias) == normalise_ingredient(canonical):
        raise ValueError("An ingredient cannot be an alias of itself")

    with get_session() as session:
        existing = session.exec(
            select(IngredientAlias).where(IngredientAlias.alias == alias)
        ).first()
        if existing:
            existing.canonical = canonical
            session.add(existing)
        else:
            session.add(IngredientAlias(alias=alias, canonical=canonical))
        session.commit()

    return jsonify(build_config_payload()), 201


@app.route('/api/config/aliases/<int:alias_id>', methods=['DELETE'])
@staple_api
def delete_alias_api(alias_id: int):
    with get_session() as session:
        alias = session.get(IngredientAlias, alias_id)
        if not alias:
            return jsonify({"error": "Alias not found"}), 404
        session.delete(alias)
        session.commit()

    return jsonify(build_config_payload())


@app.route('/api/zones/unplaced', methods=['GET'])
def unplaced_ingredients():
    """Ingredients used by recipes that have no kitchen zone yet.

    Each comes with a suggested zone, borrowed from the closest already-placed
    ingredient, so assigning them is one click rather than a decision.
    """
    try:
        zone_config = load_zone_config()
    except LookupError:
        return jsonify({"unplaced": [], "zones": []})

    aliases = load_alias_map()
    known = _collect_all_ingredient_names()

    unplaced = []
    for name in sorted(known):
        canonical = aliases.canonical(name)
        if zone_config.is_mapped(canonical):
            continue
        unplaced.append(
            {
                "ingredient": name,
                "canonical": canonical if canonical != name else None,
                "suggested_zone": suggest_zone(canonical, zone_config),
            }
        )

    zones = sorted(
        ({"name": z.name, "order": z.order} for z in zone_config.zones.values()),
        key=lambda z: z["order"],
    )
    return jsonify({"unplaced": unplaced, "zones": zones})


def suggest_zone(ingredient: str, zone_config) -> Dict[str, Any] | None:
    """Guess a zone from the most similar ingredient already placed."""
    target = _norm_text(ingredient)
    if not target:
        return None

    best_name = None
    best_score = 0
    for candidate in zone_config.assignments:
        score = fuzz.ratio(target, _norm_text(candidate))
        if score > best_score:
            best_name, best_score = candidate, score

    if best_name is None or best_score < 70:
        return None
    return {
        "zone": zone_config.assignments[best_name],
        "because_of": best_name,
        "confidence": best_score,
    }


MENU_SUFFIXES = (".yaml", ".yml")


def looks_like_menu(path: pathlib.Path) -> bool:
    """True when a YAML file is a menu rather than some other config.

    The data directory is shared with configuration -- ``kitchen_zones.yml``
    lives there too -- so suffix alone is not enough. A menu maps a section
    name to a *list* of dishes; the zone config maps names to mappings, so the
    shape tells them apart without a filename denylist.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            parsed = yaml.load(handle, Loader=yaml.FullLoader)
    except (OSError, yaml.YAMLError):
        return False

    if not isinstance(parsed, dict) or not parsed:
        return False
    return all(isinstance(value, list) for value in parsed.values())


def list_menu_files() -> list[pathlib.Path]:
    """Menu files in the data directory, newest first."""
    directory = data_dir()
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix in MENU_SUFFIXES and looks_like_menu(path)
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def menu_path_for(name: str) -> pathlib.Path | None:
    """Resolve a menu name to a file, refusing to escape the data directory.

    The name arrives from the client, so it is treated as hostile: only a bare
    stem is accepted, and the resolved path must still sit inside the data
    directory.
    """
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None

    directory = data_dir().resolve()
    for suffix in MENU_SUFFIXES:
        candidate = (directory / f"{name}{suffix}").resolve()
        if candidate.parent != directory:
            return None
        if candidate.is_file() and looks_like_menu(candidate):
            return candidate
    return None


def serialise_run_item(item: ShoppingRunItem) -> Dict[str, Any]:
    return {
        "id": item.id,
        "ingredient": item.ingredient,
        "quantities": item.quantities,
        "recipes": item.recipes,
        "zone": item.zone_name,
        "checked": item.checked,
        "checked_at": item.checked_at.isoformat() if item.checked_at else None,
        # a hint that this is probably already in the cupboard; the item is
        # still unticked, because only the walk can confirm it
        "likely_stocked": item.likely_stocked,
    }


def serialise_run(run: ShoppingRun, items: List[ShoppingRunItem]) -> Dict[str, Any]:
    """Group items into zones so the phone can render sticky headers directly."""
    zones: List[Dict[str, Any]] = []
    for item in items:
        if not zones or zones[-1]["zone"] != item.zone_name:
            zones.append({"zone": item.zone_name, "items": []})
        zones[-1]["items"].append(serialise_run_item(item))

    checked, total = progress(items)
    return {
        "id": run.id,
        "menu": run.menu_name,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "checked": checked,
        "total": total,
        "zones": zones,
    }


@app.route('/api/menus', methods=['GET'])
def list_menus():
    """Menu files available to shop from, newest first."""
    return jsonify(
        {
            "menus": [
                {
                    "name": path.stem,
                    "modified": datetime.datetime.fromtimestamp(
                        path.stat().st_mtime
                    ).isoformat(),
                }
                for path in list_menu_files()
            ]
        }
    )


@app.route('/api/runs', methods=['GET'])
def list_runs():
    """Runs available to walk or resume, newest first."""
    with get_session() as session:
        runs = recent_runs(session)
        totals = progress_by_run(session)
        return jsonify(
            {
                "runs": [
                    {
                        "id": run.id,
                        "menu": run.menu_name,
                        "created_at": (
                            run.created_at.isoformat() if run.created_at else None
                        ),
                        "checked": totals.get(run.id, (0, 0))[0],
                        "total": totals.get(run.id, (0, 0))[1],
                    }
                    for run in runs
                ]
            }
        )


@app.route('/api/runs', methods=['POST'])
def create_run():
    """Freeze a menu's shopping list into a tickable run."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get("menu") or "").strip()

    menu_path = menu_path_for(name)
    if menu_path is None:
        return jsonify({"error": "Menu not found"}), 404

    try:
        aggregated = parser.aggregate_menu_file(
            menu_path, silent_sections={get_staple_label()}
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    with get_session() as session:
        run = start_run(name, aggregated.shopping, session)
        return jsonify(serialise_run(run, run_items(run.id, session))), 201


@app.route('/api/runs/latest', methods=['GET'])
def get_latest_run():
    """The run in progress for a menu, so phone and laptop meet on the same one."""
    name = (request.args.get("menu") or "").strip()
    if not name:
        return jsonify({"error": "menu is required"}), 400

    with get_session() as session:
        run = latest_run(name, session)
        if run is None:
            return jsonify({"run": None})
        return jsonify({"run": serialise_run(run, run_items(run.id, session))})


@app.route('/api/runs/<int:run_id>', methods=['GET'])
def get_run(run_id: int):
    with get_session() as session:
        run = session.get(ShoppingRun, run_id)
        if run is None:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(serialise_run(run, run_items(run.id, session)))


@app.route('/api/runs/items/<int:item_id>', methods=['PATCH'])
def update_run_item(item_id: int):
    """Tick or untick one item.

    Returns the whole run, not just the item: the phone and the laptop may both
    be looking at this list, so every reply carries the current totals.
    """
    payload = request.get_json(silent=True) or {}
    if "checked" not in payload:
        return jsonify({"error": "checked is required"}), 400

    with get_session() as session:
        item = set_checked(item_id, bool(payload["checked"]), session)
        if item is None:
            return jsonify({"error": "Item not found"}), 404

        run = session.get(ShoppingRun, item.run_id)
        return jsonify(serialise_run(run, run_items(run.id, session)))


def serialise_stocked(item: StockedItem) -> Dict[str, Any]:
    return {"id": item.id, "name": item.name}


@app.route('/api/stocked', methods=['GET'])
def get_stocked():
    """Ingredients normally already in the kitchen, so runs start them ticked."""
    with get_session() as session:
        rows = session.exec(select(StockedItem).order_by(StockedItem.name)).all()
        return jsonify({"items": [serialise_stocked(row) for row in rows]})


@app.route('/api/stocked', methods=['POST'])
def add_stocked():
    payload = request.get_json(silent=True) or {}
    name = normalise_ingredient(payload.get("name") or "")
    if not name:
        return jsonify({"error": "name is required"}), 400

    with get_session() as session:
        existing = session.exec(
            select(StockedItem).where(StockedItem.name == name)
        ).first()
        if existing is None:
            session.add(StockedItem(name=name))
            session.commit()

        rows = session.exec(select(StockedItem).order_by(StockedItem.name)).all()
        return jsonify({"items": [serialise_stocked(row) for row in rows]})


@app.route('/api/stocked/<int:item_id>', methods=['DELETE'])
def delete_stocked(item_id: int):
    with get_session() as session:
        item = session.get(StockedItem, item_id)
        if item is None:
            return jsonify({"error": "Item not found"}), 404
        session.delete(item)
        session.commit()

        rows = session.exec(select(StockedItem).order_by(StockedItem.name)).all()
        return jsonify({"items": [serialise_stocked(row) for row in rows]})


def product_map_path() -> pathlib.Path:
    """Where the nemlig memory lives.

    Configurable so tests never touch the real file. ``record`` rewrites it in
    place, and a test suite that clobbers a year of learned product choices is
    a bad afternoon.
    """
    configured = app.config.get("NEMLIG_MAP_PATH")
    return pathlib.Path(configured) if configured else NEMLIG_MAP_PATH


def serialise_order_item(item: NemligOrderItem) -> Dict[str, Any]:
    # Computed on read rather than stored: it is a function of the need and the
    # currently chosen product, both of which change while the picker is open.
    # A stored copy would go stale the moment someone changes the quantity.
    shortfall = None
    if item.action in ("buy", "link"):
        shortfall = check_coverage(item.need or "", (item.product or {}).get("pack", ""), item.qty)

    return {
        "id": item.id,
        "ingredient": item.ingredient,
        "need": item.need,
        "recipes": item.recipes,
        "zone": item.zone_name,
        "status": item.status,
        "query": item.query or None,
        "candidates": item.candidates or [],
        "warning": item.warning,
        "action": item.action,
        "product_id": item.product_id,
        "product": item.product,
        "qty": item.qty,
        "note": item.note,
        "url": item.url,
        "shortfall": shortfall,
    }


def serialise_order(order: NemligOrder, items: List[NemligOrderItem]) -> Dict[str, Any]:
    decided, total = order_progress(items)
    payload = [serialise_order_item(item) for item in items]
    collisions = find_collisions(
        [
            {
                "action": item.action,
                "product_id": item.product_id,
                "product": item.product,
                "ingredient": item.ingredient,
                "need": item.need,
                "qty": item.qty,
            }
            for item in items
        ]
    )
    return {
        "id": order.id,
        "run_id": order.run_id,
        "source": order.source,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "recorded_at": order.recorded_at.isoformat() if order.recorded_at else None,
        "decided": decided,
        "total": total,
        "items": payload,
        "collisions": collisions,
        "shortfalls": [
            {"ingredient": row["ingredient"], **row["shortfall"]}
            for row in payload
            if row.get("shortfall")
        ],
    }


@app.route('/api/orders', methods=['GET'])
def list_orders():
    """Baskets in progress, newest first."""
    with get_session() as session:
        orders = recent_orders(session)
        return jsonify(
            {
                "orders": [
                    serialise_order(order, order_items(order.id, session))
                    for order in orders
                ]
            }
        )


@app.route('/api/orders', methods=['POST'])
def create_order():
    """Open a basket for whatever the kitchen walk did not tick off."""
    payload = request.get_json(silent=True) or {}
    run_id = payload.get("run_id")
    if not isinstance(run_id, int):
        return jsonify({"error": "run_id is required"}), 400

    with get_session() as session:
        order = start_order(
            run_id,
            load_product_map(product_map_path()),
            session,
            source=(payload.get("source") or "").strip(),
            include_checked=bool(payload.get("include_checked")),
        )
        if order is None:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(serialise_order(order, order_items(order.id, session))), 201


@app.route('/api/orders/<int:order_id>', methods=['GET'])
def get_order(order_id: int):
    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        return jsonify(serialise_order(order, order_items(order.id, session)))


@app.route('/api/orders/<int:order_id>/queries', methods=['GET'])
def get_order_queries(order_id: int):
    """The searches still worth running, ready to paste into a logged-in tab.

    The app cannot run them itself: nemlig's search needs a bearer token and
    several session parameters that only exist inside a logged-in browser, and
    the basket authenticates on a rotating HttpOnly cookie set. So the queries
    go out and the results come back.
    """
    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        return jsonify({"queries": pending_queries(order_id, session)})


@app.route('/api/orders/<int:order_id>/search-results', methods=['POST'])
def post_order_search_results(order_id: int):
    """Attach a batch of search results, as ``{query: [product, ...]}``.

    Accepts nemlig's own product shape as well as the flattened one, because
    whoever ran the searches should not have to reshape them by hand.
    """
    payload = request.get_json(silent=True) or {}
    results = payload.get("results")
    if not isinstance(results, dict):
        return jsonify({"error": "results must be an object of query -> products"}), 400

    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404

        touched = attach_search_results(
            order_id, adapt_search_results(results), load_product_map(product_map_path()), session
        )
        items = order_items(order_id, session)
        return jsonify(
            {
                "updated": touched,
                "without_candidates": [
                    item.ingredient
                    for item in items
                    if not item.action and item.query and not item.candidates
                ],
                "order": serialise_order(order, items),
            }
        )


@app.route('/api/browser/status')
def get_browser_status():
    """Whether the Order screen can drive the browser, and why not if it can't."""
    return jsonify(browser_status())


@app.route('/api/orders/<int:order_id>/run-search', methods=['POST'])
def post_order_run_search(order_id: int):
    """Search nemlig for every undecided row, straight from the logged-in tab.

    The loop lives here rather than in the page: one long awaited evaluate
    exceeds the socket timeout and loses its results, while many short ones
    cannot.
    """
    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        queries = pending_queries(order_id, session)

    if not queries:
        return jsonify({"error": "Nothing left to search"}), 400

    try:
        tab_ensure_session()
        results = {query: tab_search(query) for query in queries}
    except BrowserUnavailable as exc:
        return jsonify({"error": str(exc)}), 503

    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        touched = attach_search_results(
            order_id, adapt_search_results(results), load_product_map(product_map_path()), session
        )
        items = order_items(order_id, session)
        return jsonify(
            {
                "searched": len(queries),
                "updated": touched,
                "without_candidates": [
                    item.ingredient
                    for item in items
                    if not item.action and item.query and not item.candidates
                ],
                "order": serialise_order(order, items),
            }
        )


@app.route('/api/orders/<int:order_id>/fill-basket', methods=['POST'])
def post_order_fill_basket(order_id: int):
    """Add every chosen line to the basket, then report what really landed.

    Reconciliation is not optional here: AddToBasket answers 200 for a
    sold-out product and quietly lands it at quantity zero.
    """
    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404
        choices = [serialise_order_item(item) for item in order_items(order_id, session)]

    merged = merge_add_lines(choices)
    lines = merged["lines"]
    if not lines:
        return jsonify({"error": "Nothing chosen to buy yet"}), 400

    try:
        statuses = [
            {
                "product_name": line["product_name"],
                "qty": line["qty"],
                "status": tab_add_line(line["product_id"], line["qty"]),
            }
            for line in lines
        ]
        basket = tab_read_basket()
    except BrowserUnavailable as exc:
        return jsonify({"error": str(exc)}), 503

    reconciliation = reconcile_basket(lines, basket)
    # Anything in the basket we did not ask for: the user's own extras, or a
    # surprise. Either way it should be visible rather than silently ignored.
    asked = {str(line["product_id"]) for line in lines}
    reconciliation["unexpected"] = [
        {"product_id": str(l.get("ProductId")), "name": l.get("Name"),
         "qty": l.get("Quantity"), "price": l.get("Price")}
        for l in basket.get("Lines") or []
        if str(l.get("ProductId")) not in asked and l.get("Quantity")
    ]
    return jsonify({
        "added": statuses,
        "failed": [s for s in statuses if s["status"] != 200],
        "merged": merged,
        "reconciliation": reconciliation,
    })


@app.route('/api/orders/items/<int:item_id>', methods=['PATCH'])
def update_order_item(item_id: int):
    """Record one decision. Saved immediately, never at a submit."""
    payload = request.get_json(silent=True) or {}
    fields: Dict[str, Any] = {}

    if "action" in payload:
        action = payload["action"]
        if action is not None and action not in ACTIONS:
            return jsonify({"error": f"unknown action {action!r}"}), 400
        fields["action"] = action
    for key in ("product_id", "qty", "note", "url"):
        if key in payload:
            fields[key] = payload[key]
    if "product" in payload:
        product = payload["product"]
        fields["product"] = adapt_product(product) if product else None
    if not fields:
        return jsonify({"error": "nothing to update"}), 400

    with get_session() as session:
        item = set_choice(item_id, session, **fields)
        if item is None:
            return jsonify({"error": "Item not found"}), 404

        order = session.get(NemligOrder, item.order_id)
        return jsonify(serialise_order(order, order_items(order.id, session)))


@app.route('/api/orders/<int:order_id>/basket', methods=['GET'])
def get_order_basket(order_id: int):
    """The basket lines to post, with quantities summed per product.

    Summing is not a nicety. ``AddToBasket`` is called with
    ``AffectPartialQuantity: true``, so the quantity is absolute: two rows
    resolving to the same product and posted separately leave one pack in the
    basket rather than two, silently.
    """
    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404

        choices = [serialise_order_item(item) for item in order_items(order_id, session)]
        return jsonify(merge_add_lines(choices))


@app.route('/api/orders/<int:order_id>/reconcile', methods=['POST'])
def post_order_reconcile(order_id: int):
    """Check a GetBasket response against what was asked for.

    A 200 from AddToBasket is not proof of purchase: a sold-out product is
    accepted, reports success, and lands as a line with ``Quantity: 0``.
    """
    payload = request.get_json(silent=True) or {}
    basket = payload.get("basket")
    if not isinstance(basket, dict):
        return jsonify({"error": "basket is required"}), 400

    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404

        choices = [serialise_order_item(item) for item in order_items(order_id, session)]
        lines = merge_add_lines(choices)["lines"]
        return jsonify(reconcile_basket(lines, basket))


@app.route('/api/orders/<int:order_id>/record', methods=['POST'])
def post_order_record(order_id: int):
    """Fold what this order learned back into the product map.

    ``dry_run`` returns the summary without writing, so the diff can be looked
    at first. Writing keeps one backup.
    """
    payload = request.get_json(silent=True) or {}
    dry_run = bool(payload.get("dry_run"))

    # Each substitution must carry the replacement's product_id; a bare reason
    # string cannot say what was bought instead. Caught here because
    # record_run would otherwise index into the string and raise a 500.
    replaced = payload.get("replaced") or {}
    if not isinstance(replaced, dict):
        return jsonify({"error": "'replaced' must be an object"}), 400
    for name, substitute in replaced.items():
        if not isinstance(substitute, dict) or not substitute.get("product_id"):
            return jsonify({
                "error": f"replaced[{name!r}] must be an object with a product_id",
            }), 400

    with get_session() as session:
        order = session.get(NemligOrder, order_id)
        if order is None:
            return jsonify({"error": "Order not found"}), 404

        items = order_items(order_id, session)
        choices = [serialise_order_item(item) for item in items]
        lines = merge_add_lines(choices)["lines"]

        result = record_run(
            load_product_map(product_map_path()),
            choices,
            lines,
            replaced=replaced,
            source=(payload.get("source") or order.source),
            on_date=payload.get("date") or datetime.date.today(),
        )

        updated_map = result.pop("map")
        if not dry_run:
            save_product_map(updated_map, product_map_path())
            # Staples learned here belong in the database too, or the phone's
            # next walk will not know about them.
            for name in result["learned_staples"]:
                normalised = normalise_ingredient(name)
                existing = session.exec(
                    select(StockedItem).where(StockedItem.name == normalised)
                ).first()
                if existing is None:
                    session.add(StockedItem(name=normalised))
            session.commit()
            mark_recorded(order_id, session)

        result["dry_run"] = dry_run
        result["summary"] = summarise_map(updated_map)
        return jsonify(result)


@app.route('/api/nemlig/map', methods=['GET'])
def get_product_map():
    """The durable memory, so what the app knows is visible rather than implied."""
    product_map = load_product_map(product_map_path())
    return jsonify(
        {
            "summary": summarise_map(product_map),
            "mappings": product_map.get("mappings", {}),
            "unresolved": product_map.get("no_default_yet", {}),
            "stocked": product_map.get("usually_in_the_kitchen", {}).get("items", []),
        }
    )


def data_dir() -> pathlib.Path:
    """Directory for generated artifacts; created on demand."""
    target = pathlib.Path(app.config.get("MENU_DATA_DIR", "."))
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_menu(menu_dict: Dict[str, Any]) -> pathlib.Path:
    s = yaml.dump(menu_dict, allow_unicode=True, sort_keys=False)
    isodate = datetime.date.today().isocalendar()
    directory = data_dir()
    recipe_file = directory / f"uge_{isodate.week+1}_{isodate.year}.yaml"
    i = 1
    while recipe_file.exists():
        recipe_file = directory / f"uge_{isodate.week+1}_{isodate.year}({i}).yaml"
        i += 1

    with recipe_file.open("w", encoding="utf-8") as f:
        f.write(s)

    return recipe_file


class MenuText:
    """Accumulates rendered lines.

    Deliberately does not touch the filesystem: it used to rewrite the whole
    output file once per printed line, which is O(n^2) in file writes.
    """

    def __init__(self, menu: str = "") -> None:
        self.text = menu

    def add(self, s: str) -> None:
        self.text += s + "\n"

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return self.__str__()


# SPA fallback: when a static file is not found for a top-level path, serve the
# frontend index so client-side routing (React Router) can take over.
@app.errorhandler(404)
def spa_fallback(_error):  # noqa: ANN001
    path = request.path or ''
    if path.startswith(('/api/', '/assets/', '/favicon')):
        return jsonify(error='not found'), 404
    response = _serve_frontend_index_response()
    if response is None:
        return jsonify(error='not found'), 404
    return response


if __name__ == "__main__":
    app.run(host="::", port=5000, debug=True)
