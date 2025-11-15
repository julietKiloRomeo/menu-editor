import base64
import datetime
import functools
import json
import os
import pathlib
import re
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
from sqlalchemy import or_
from sqlmodel import select, Session
from pydantic import BaseModel, Field

from src.models import (
    CategoryConfig,
    IngredientConfig,
    Recipe,
    StapleItem,
    AppSetting,
    get_session,
    init_db,
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
    global _config_seeded
    if _config_seeded:
        return

    categories, _items = fetch_config()
    if not categories:
        app.logger.info(
            "No category config found in the database yet; seed via /api/config before using the planner."
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
            session.add(StapleItem(name=cleaned_name, amount=amount_value or 1.0, unit=unit_value))
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

    menu_text = MenuText()
    parser.write_menu(menu_path, printer=menu_text.add)

    return jsonify({"markdown": str(menu_text)})


app.add_url_rule(
    '/api/menu/generate',
    view_func=generate_menu,
    methods=['POST'],
    endpoint='api_generate_menu',
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


def save_menu(menu_dict: Dict[str, Any]) -> pathlib.Path:
    s = yaml.dump(menu_dict, allow_unicode=True, sort_keys=False)
    isodate = datetime.date.today().isocalendar()
    recipe_file = pathlib.Path(f"uge_{isodate.week+1}_{isodate.year}.yaml")
    i = 1
    while recipe_file.exists():
        recipe_file = pathlib.Path(f"uge_{isodate.week+1}_{isodate.year}({i}).yaml")
        i += 1

    with recipe_file.open("w", encoding="utf-8") as f:
        f.write(s)

    return recipe_file


class MenuText:

    def __init__(self, menu: str = "") -> None:
        self.text = menu

    def add(self, s: str) -> None:
        self.text += s + "\n"
        with open("shopping.md", "w", encoding="utf-8") as f:
            f.write(self.text)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return self.__str__()


if __name__ == "__main__":
    app.run(host="::", port=5000, debug=True)
