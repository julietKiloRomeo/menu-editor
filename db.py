from tinydb import TinyDB, Query
from pydantic import BaseModel
from typing import Optional, Union
from enum import Enum, IntEnum


class DB:
    FILE = "db.json"
    TABLES = ["ingredient", "recipe", "menu"]

    def __init__(self):
        self._db = TinyDB(self.FILE)

    def _clear(self):
        self._db.drop_tables()

    def tables(self):
        return self._db.tables()

    def add_from_api(self, table_name, item):
        self._db.table(table_name).insert(item)

    def update_recipe(self, doc_id, recipe):
        recipes = self._db.table("recipe")
        recipes.update(recipe, doc_ids=[doc_id])


class IngredientCategory(str, Enum):
    bad = "bad"
    bryggers = "bryggers"
    brød = "brød"
    fisk = "fisk"
    frugt = "frugt"
    frys = "frys"
    kød = "kød"
    køl = "køl"
    krydderi = "krydderi"
    none = "none"
    tilbehør = "tilbehør"
    vin = "vin"
    øl = "øl"


class Unit(str, Enum):
    g = "g"
    kg = "kg"
    l = "l"
    ml = "ml"
    dl = "dl"
    tsk = "tsk"
    spsk = "spsk"
    stk = "stk"
    portioner = "portioner"


class Rating(IntEnum):
    one = 1
    two = 2
    three = 3
    four = 4
    five = 5


class APIBase(BaseModel):
    def _preprocess(self):
        pass

    def id_and_dict(self):
        self._preprocess()
        datadict = self.dict()
        doc_id = self.doc_id
        del datadict["doc_id"]
        return doc_id, datadict


class Ingredient(BaseModel):
    doc_id: int
    name: str
    category: IngredientCategory
    alii: str

    def id_and_dict(self):
        alii = [s.strip() for s in self.alii.split(",") if len(s.strip())]
        return self.doc_id, {"name": self.name, "category": self.category, "alii": alii}


class IngredientAmount(BaseModel):
    ingredient: str  # hopefully matches an ingredient
    amount: float
    unit: Unit


class RecipeAmount(BaseModel):
    ingredient: str  # hopefully matches a recipe
    amount: float
    unit: Unit


class Recipe(BaseModel):
    doc_id: int
    name: str
    placement: str
    rating: Rating
    ingredients: list[IngredientAmount]


class MenuEntry(BaseModel):
    recipe: list[Union[IngredientAmount, RecipeAmount]]
    days: list[str]


class Menu(BaseModel):
    name: str
    rating: Rating
    menus: list[MenuEntry]


class Plan(BaseModel):
    name: str
    year: int
    week: int
    menu: Menu
    from_freezer: list[str]
    shopping: list[IngredientAmount]
