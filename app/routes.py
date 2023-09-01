from flask import render_template, jsonify
from app import application, mongo
from flask import request, redirect, send_file

@application.route('/')
@application.route('/index')
def index():
    user = {'username': 'Alvilde T'}
    return render_template('index.html', title='Opskrifter', user=user)


@application.route('/ingredients')
def ingredient_list():
    ingredients = list(mongo.db.ingredients.find())
    return render_template('ingredient_list.html', ingredients=ingredients)

@application.route('/ingredient/<name>', methods=["POST", "GET"])
def ingredient_detail(name):
    if request.method == "POST":

        req = request.form

        mongo.db.ingredients.update(
            {"name":req["name"]},
            {
                "name":req["name"],
                "placement":req["category"],
            },
        )

        return redirect(request.url)
    
    try:
        item, = list(mongo.db.ingredients.find(dict(name={"$regex":f"{name}"})))
    except:
        item = None

    return render_template('ingredient_detail.html', ingredient=item)

@application.route('/recipes')
def recipe_list():
    recipes = list(mongo.db.recipes.find())
    return render_template('recipe_list.html', recipes=recipes)

from collections import defaultdict
def parse_recipe_form(req):
    req = dict(request.form)

    scalars = ["navn", "placering", "antal", ]
    data = {
        key : req[key] for key in scalars
    }
    data["ingredienser"] = {}

    ingredients = defaultdict(dict)
    for key_index, value in req.items():
        if key_index in scalars:
            continue
        key, index_str = key_index.split("-")
        ingredients[index_str][key] = value

    for key, ingredient in ingredients.items():
        if ingredient["name"] == "":
            continue

        data[
            "ingredienser"
        ][
            ingredient["name"]
        ] = {
            "amount": float(ingredient["amount"]),
            "unit": ingredient["unit"],
        }
    return data


@application.route('/recipe/<name>', methods=["POST", "GET"])
def recipe_detail(name):
    if request.method == "POST":
        data = parse_recipe_form(request)

        mongo.db.recipes.update(
            {"navn":data["navn"]},
            { "$set":data },
        )

        return redirect(request.url)

    try:
        item, = list(mongo.db.recipes.find(dict(navn={"$regex":f"{name}"})))
    except:
        item = None

    return render_template('recipe_detail.html', recipe=item)

@application.route('/menus')
def menu_list():
    menus = list(mongo.db.menus.find())
    return render_template('menu_list.html', menus=menus)

@application.route('/menu/<year>/<week>', methods=["POST", "GET"])
def menu_detail(year, week):
    if request.method == "POST":
        print(request.form)
        # data = parse_menu_form(request)

        # mongo.db.recipes.update(
        #     {"navn":data["navn"]},
        #     { "$set":data },
        # )
        return send_file("../shopping.pdf")
        return redirect(request.url)

    try:
        item, = list(mongo.db.menus.find(dict(week=int(week), year=int(year), )))
    except:
        item = None

    return render_template('menu_detail.html', menu=item)
