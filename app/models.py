from app import db

class Ingredient(db.Document):
    name = db.StringField()
    placement = db.IntegerField()

class Recipe(db.Document):
    name = db.StringField()
    location = db.StringField()
    ingredients = db.IntegerField()

class Menu(db.Document):
    name = db.StringField()
    recipes = db.IntegerField()

