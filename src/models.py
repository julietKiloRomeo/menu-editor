import peewee

db = peewee.SqliteDatabase('recipes.db')

class Recipe(peewee.Model):
    """
    A recipe for a dish, including its name, source, and number of servings.

    Relationships:
    - One Recipe has many RecipeIngredients.
    - One Recipe can be part of many MenuItems in different Menus.
    """
    name = peewee.CharField(unique=True)
    source = peewee.CharField()

    class Meta:
        database = db


class Category(peewee.Model):
    """
    A category that groups similar ingredients together.

    Relationships:
    - One Category has many Ingredients.
    """
    name = peewee.CharField(unique=True)

    class Meta:
        database = db



class Ingredient(peewee.Model):
    """
    An item that can be bought at a grocery store and used as an ingredient in recipes.
    Includes its name, and metadata like placement in the supermarket and in our kitchen.

    Relationships:
    - One Ingredient is referred to by many RecipeIngredients.
    - One Ingredient belongs to one Category.
    """
    name = peewee.CharField(unique=True)
    category = peewee.ForeignKeyField(Category, backref='ingredients')
    supermarket_placement = peewee.CharField()
    kitchen_placement = peewee.CharField()

    class Meta:
        database = db



class RecipeIngredient(peewee.Model):
    """
    An ingredient used in a recipe, including its quantity and unit.

    Relationships:
    - One RecipeIngredient belongs to one Recipe.
    - One RecipeIngredient refers to one Ingredient.
    """
    recipe = peewee.ForeignKeyField(Recipe, backref='recipe_ingredients')
    ingredient = peewee.ForeignKeyField(Ingredient)
    quantity = peewee.FloatField()
    unit = peewee.CharField()

    class Meta:
        database = db






class Menu(peewee.Model):
    """
    A menu consisting of several MenuItems (recipes with a specified number of servings).

    Relationships:
    - One Menu has many MenuItems.
    """
    name = peewee.CharField(unique=True)

    class Meta:
        database = db


class MenuItem(peewee.Model):
    """
    A recipe with a specified number of servings that is part of a menu.

    Relationships:
    - One MenuItem belongs to one Menu.
    - One MenuItem refers to one Recipe.
    """
    menu = peewee.ForeignKeyField(Menu, backref='menu_items')
    recipe = peewee.ForeignKeyField(Recipe)
    servings = peewee.IntegerField()

    class Meta:
        database = db


if __name__ == "__main__":
    db.create_tables([Recipe, Category, Ingredient, RecipeIngredient, Menu, MenuItem])
