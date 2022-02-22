from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from tinydb import Query
import db as database
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import pathlib

import logging
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# allow connecting from other local ips than the fastapi server
origins = [
    "http://localhost",
    "http://localhost:8080",
]


STATIC_DIR = pathlib.Path(__file__).parent / "static"
print(STATIC_DIR)
menu_db = database.DB()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logging.error(f"{request}: {exc_str}")
    content = {"status_code": 10422, "message": exc_str, "data": None}
    return JSONResponse(
        content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


def get_sorted_rows_w_id(table, sort_by_func = lambda rec: rec["name"]);
    rows = menu_db._db.table(table).all()
    rows = sorted(rows, key=sort_by_func)
    return [{**row, "doc_id": row.doc_id} for row in rows]







@app.get("/api/ingredient")
def get_ingredients():
    return [
        {
            **ingredient,
            "alii": ", ".join(ingredient["alii"]),
        }
        for ingredient in get_sorted_rows_w_id("ingredient")
    ]


@app.post("/api/ingredient")
def add_ingredient(ingredients: list[database.Ingredient]):
    table = menu_db._db.table("ingredient")
    for ingredient in ingredients:
        doc_id, ingredient = ingredient.id_and_dict()

        print(doc_id, ingredient)

        is_new = doc_id < 0
        if is_new:
            table.insert(ingredient)
        else:
            table.update(ingredient, doc_ids=[doc_id])

    return [
        {
            **ingredient,
            "alii": ", ".join(ingredient["alii"]),
        }
        for ingredient in get_sorted_rows_w_id("ingredient")
    ]


@app.post("/api/ingredient/delete")
def delete_ingredient(to_delete: list[int]):
    table = menu_db._db.table("ingredient")
    table.remove(doc_ids=to_delete)

    return [
        {
            **ingredient,
            "alii": ", ".join(ingredient["alii"]),
        }
        for ingredient in get_sorted_rows_w_id("ingredient")
    ]


@app.get("/api/recipe")
def list_recipies():
    return get_sorted_rows_w_id("recipe")


@app.post("/api/recipe")
def upsert_recipe(recipes: list[database.Recipe]):
    print(recipes)
    return "done"

    table = menu_db._db.table("plan")

    for plan in plans:
        doc_id = plan["doc_id"]
        del plan["doc_id"]

        print(doc_id, plan)

        is_new = doc_id < 0
        if is_new:
            table.insert(plan)
        else:
            table.update(plan, doc_ids=[doc_id])

    menus = menu_db._db.table("plan").all()
    return [{**menu, "doc_id": menu.doc_id} for menu in menus]


@app.get("/api/plan")
def get_plans():
    return get_sorted_rows_w_id("plan")


@app.post("/api/plan")
def upsert_plans(plans: list):
    print(plans)

    table = menu_db._db.table("plan")

    for plan in plans:
        doc_id = plan["doc_id"]
        del plan["doc_id"]

        print(doc_id, plan)

        is_new = doc_id < 0
        if is_new:
            table.insert(plan)
        else:
            table.update(plan, doc_ids=[doc_id])

    return get_sorted_rows_w_id("plan")

