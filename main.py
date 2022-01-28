from fastapi import FastAPI, Request, Form, status, Depends
from tinydb import TinyDB, Query
import json
import db as database
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import pathlib

STATIC_DIR = pathlib.Path(__file__).parent / "static"
print(STATIC_DIR)
menu_db = database.DB()
app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="templates")


def paginated_search(table, page, pagination, search):
    paginate = page >= 0
    subset = slice(page*pagination, (page+1)*pagination, None) if paginate else slice(None, None, None)
    
    if search:
        query = Query()
        data = table.search( Query().name.matches(".*" + search) )
    else:
        data = table.all()
    
    return {
        "data": data[subset],
        "page": page
    }

    
    
@app.get("/api/ingredient")
def list_ingredients(page: int = -1, search: str = None):
    return paginated_search(
        table=menu_db._db.table("ingredient"),
        page=page,
        search=search,
        pagination = 20,
    )

@app.post("/api/ingredient")
def add_ingredient(ingredients: list[database.IngredientData]):
    table = menu_db._db.table("ingredient")
    for ingredient in ingredients:
        doc_id, ingredient = ingredient.id_and_dict()

        is_new = doc_id == -1
        if is_new:
            table.insert(ingredient)
        else:
            table.update(ingredient, doc_ids=[doc_id])
        
    return "ingredients updated"


@app.post("/api/ingredient/delete")
def delete_ingredient(to_delete: list[int]):
    table = menu_db._db.table("ingredient")
    table.remove(doc_ids=to_delete)
    return "ingredients deleted"


@app.get("/api/recipe")
def list_recipies(page: int = -1, search: str = None):
    return paginated_search(
        table=menu_db._db.table("recipe"),
        page=page,
        search=search,
        pagination = 20,
    )

@app.post("/api/recipe/{doc_id}")
def upsert_recipe(doc_id: int, item: database.Recipe):
    make_new = doc_id == -1
    if make_new:
        menu_db.add_from_api("recipe", item.dict())
        return "recipe created"
    menu_db.update_recipe(doc_id=doc_id, recipe=item.dict())
    return "recipe updated"


@app.post("/api/menu/delete")
def delete_ingredient(to_delete: dict):
    table = menu_db._db.table("menu")
    table.remove(doc_ids=[to_delete["doc_id"]])
    return "menu deleted"

@app.post("/api/menu/{doc_id}")
def upsert_menu(doc_id: int, item: dict):
    menu_db._db.table("menu").update(item, doc_ids=[doc_id])
    return "menu updated"



#-----------------------------------------------------
# HTML
#-----------------------------------------------------


# ingredient
@app.get("/ingredient", response_class=HTMLResponse)
def ingredient_list(request: Request):
    ingredients = menu_db._db.table("ingredient").all()
    ingredients = [{**ing, "doc_id":ing.doc_id} for ing in ingredients]
    categories = [e.name for e in database.IngredientCategory]
    return templates.TemplateResponse("ingredient_list.html", {"request": request, "ingredients": ingredients, "categories": categories})

# recipe
@app.get("/recipe", response_class=HTMLResponse)
def recipe_list(request: Request):
    recipes = menu_db._db.table("recipe").all()
    return templates.TemplateResponse("recipe_list.html", {"request": request, "recipes": recipes})


@app.get("/recipe/{doc_id}", response_class=HTMLResponse)
def recipe_details(request: Request, doc_id: int):
    recipe_or_none = menu_db._db.table("recipe").get(doc_id=doc_id)
    recipe = recipe_or_none if recipe_or_none else {"name":"", "placement":"", "rating":0, "ingredients":[]}
    ratings = [e.value for e in database.Rating]
    return templates.TemplateResponse(
        "recipe_detail.html",
        {
            "request": request,
            "recipe": recipe,
            "ratings": ratings
        }
    )

# menu
@app.get("/menu", response_class=HTMLResponse)
def recipe_list(request: Request):
    menus = menu_db._db.table("menu").all()
    return templates.TemplateResponse(
        "menu_list.html",
        {
            "request": request,
            "menus": menus,
        }
    )

@app.get("/menu/{doc_id}", response_class=HTMLResponse)
def recipe_list(request: Request, doc_id: int):
    menu = menu_db._db.table("menu").get(doc_id=doc_id)
    ratings = [e.value for e in database.Rating]
    return templates.TemplateResponse(
        "menu_detail.html",
        {
            "request": request,
            "menu": menu,
            "ratings": ratings,
        }
    )
