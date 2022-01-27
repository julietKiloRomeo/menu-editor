from tinydb import TinyDB, Query
from pydantic import BaseModel
from typing import Optional, Union
from enum import Enum


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
    køl = "køl"
    frys = "frys"
    frugt = "frugt"
    vin = "vin"
    tilbehør = "tilbehør"
    brød = "brød"
    øl = "øl"

class Unit(str, Enum):
    g = "g"
    l = "l"
    kg = "kg"
    stk = "stk"
    portioner = "portioner"

class Rating(int, Enum):
    one=1
    two=2
    three=3
    four=4
    five=5
        
class Ingredient(BaseModel):
    name: str
    category: IngredientCategory
    alii: list[str]

class IngredientAmount(BaseModel):
    ingredient: str # hopefully matches an ingredient
    amount: float
    unit: Unit

class RecipeAmount(BaseModel):
    ingredient: str # hopefully matches a recipe
    amount: float
    unit: Unit


class Recipe(BaseModel):
    name: str
    placement: str
    rating: Rating
    ingredients: list[IngredientAmount]


class MenuEntry(BaseModel):
    recipe: Union[IngredientAmount, RecipeAmount]
    day: str

class Menu(BaseModel):
    name: str
    rating: Rating
    recipies: list[MenuEntry]
        
class Plan(BaseModel):
    name: str
    year: int
    week: int
    menu: Menu
    from_freezer: list[str]
    shopping: list[IngredientAmount]
        
