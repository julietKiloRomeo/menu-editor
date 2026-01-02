import pathlib
from collections import defaultdict

import click
import yaml
from sqlalchemy import or_
from sqlmodel import select

from src.models import (
    CategoryConfig,
    IngredientConfig,
    Recipe,
    get_session,
)


def add_ingredient(ingrediens, amount, shopping, config, recipe_name):
        category = config["varer"].get(ingrediens, "unknown")
        priority = config["kategorier"][category]
        shopping[priority, ingrediens][amount["unit"]] += amount["amount"]

        if not "recipes" in shopping[priority, ingrediens]:
            shopping[priority, ingrediens]["recipes"] = []

        shopping[priority, ingrediens]["recipes"].append(recipe_name)

def load_recipe_data(identifier):
    with get_session() as session:
        statement = select(Recipe).where(
            or_(Recipe.slug == identifier, Recipe.navn == identifier)
        )
        db_recipe = session.exec(statement).first()

    if db_recipe:
        return {
            "navn": db_recipe.navn,
            "placering": db_recipe.placering,
            "antal": db_recipe.antal,
            "ingredienser": db_recipe.ingredienser or {},
            "extras": db_recipe.extras or {},
        }

    recipe_pth = pathlib.Path.cwd() / f"recipes/{identifier}.yml"
    with recipe_pth.open("r") as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_config_from_db():
    with get_session() as session:
        categories = session.exec(select(CategoryConfig)).all()
        if not categories:
            raise LookupError
        items = session.exec(select(IngredientConfig)).all()

    config = {
        "kategorier": {category.name: category.priority for category in categories},
        "varer": {},
    }

    category_lookup = {category.id: category.name for category in categories}
    for item in items:
        category_name = category_lookup.get(item.category_id)
        if category_name:
            config["varer"][item.name] = category_name

    return config


def load_config():
    try:
        return load_config_from_db()
    except LookupError:
        raise RuntimeError(
            "No categories found in the database. Seed data via the /api/config endpoints before generating menus."
        ) from None


def add_recipe(recipe_identifier, amount, shopping, config, silent=False, printer=print):
    recipe = load_recipe_data(recipe_identifier)

    if amount["unit"] == "recipe":
        multiplier = amount["amount"]
    else:
        base_servings = float(recipe.get("antal") or 0)
        multiplier = amount["amount"]/base_servings if base_servings > 0 else 0

    if not silent:
        if multiplier == 1:
            amount_str = ""
        else:
            amount_str = f"(x{multiplier:g})" if multiplier else "(fryser)"
            
        printer( f" - {recipe['navn']:35s}  {amount_str} : {recipe.get('placering', ''):25s}" )

    for ingrediens, amount in recipe["ingredienser"].items():
        amount["amount"] *= multiplier
        if amount["amount"]>0:
            add_ingredient(ingrediens, amount, shopping, config, recipe['navn'])

    for ingrediens, amount in (recipe.get("extras") or {}).items():
        try:
            add_recipe(ingrediens, amount, shopping, config, silent=silent, printer=printer)
        except FileNotFoundError:
            if amount["amount"] > 0:
                add_ingredient(ingrediens, amount, shopping, config, recipe['navn'])



def amount_string(amounts, ingrediens):
    to_str = lambda v: f"{v:.2f}".rstrip('0').rstrip('.')
    a = [f"{to_str(amount)} {unit:<6s}" for unit, amount in amounts.items() if not unit=="recipes"]

    amounts_str = " + ".join(a)

    max_len = 12
    included_in = sorted(set(amounts.get('recipes', [])))

    included_in_more_than_self = len(included_in)>1
    if included_in_more_than_self:
        # eg ingredient == apple : [apple, dish-w-apple, other-dish-w-apple] -> [dish-w-apple, other-dish-w-apple]
        # then don't include self
        included_in = [s for s in included_in if not s == ingrediens]
    
    # [dish-w-apple, other-dish-w-apple] -> [dish-w-app, other-dish]
    included_in = [s[:max_len] for s in included_in]
    
    recs_str = f"{' + '.join(included_in)}"

    return amounts_str, recs_str


def print_shopping(shopping, printer=print):
    """

    |          |          |       |
    |----------|----------|------:|
    | **agurk**    | 1 stk    | agurk |


    """
    prev_priority = None
    new_table = """

|          |          |       |
|----------|----------|------:|"""
    for (priority, ingrediens), amount in sorted(shopping.items()):
        if not (priority == prev_priority):
            printer(new_table)
        prev_priority = priority
        amounts_str, recs_str = amount_string(amount, ingrediens)
        max_recs_len = 30
        printer(f"| {ingrediens:40s} | {amounts_str:>10s} |  {recs_str[:max_recs_len]:30s}  | ")


def write_menu(menu_path, printer=print):
    config = load_config()

    shopping = defaultdict(lambda: defaultdict(float) )

    with menu_path.open("r") as f: 
        menu = yaml.load(f, Loader=yaml.FullLoader)

    printer("# Menu")
    for name, recipes in menu.items():
        silent = name.lower() == "andet"
        if not silent:
            printer("## " + name)
        for recipe in recipes:
            if isinstance(recipe, str):
                recipe = {recipe: {"amount": 1, "unit": "recipe"}}

            recipe_name, = recipe.keys()
            amount = recipe[recipe_name]
            try:
                add_recipe(recipe_name, amount, shopping, config, silent=silent, printer=printer)
            except FileNotFoundError:
                if amount["amount"] > 0:
                    add_ingredient(recipe_name, amount, shopping, config, recipe_name)


    printer("# Shopping")
    print_shopping(shopping, printer=printer)




class ShoppingListItem:
    def __init__(self, name, category, recipe):
        self.name = name
        self.category = category
        self.recipe = recipe
        self.value = value
        self.unit = unit

    def __add__(self, other):
        if not self.name == other.name:
            raise Exception


        self.name = name
        self.category = category
        self.recipe = recipe
        self.value = value
        self.unit = unit


@click.group()
def cli():
    pass

import datetime

@cli.command()
@click.argument('week', type=int)
@click.argument('year', default = datetime.date.today().year , type=int)
def menu(week, year):
    menu_path = pathlib.Path.cwd() / f"menus/uge_{week:02d}_{year}.yaml"
    write_menu(menu_path)

if __name__ == '__main__':
    cli()
