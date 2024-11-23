from flask import Flask, render_template, jsonify, request, send_file
import pathlib
import yaml
import json

app = Flask(__name__)

blacklist = [
    "Chokoladetærte med saltkaramel",
    "Peberkager",
    "Coleslaw",
    "Dilddressing",
    'Pitabrød',
    'Knuste Kartofler',
    'Flødekartofler',
    'Blomkålssalat med æbler og mandler',
    'Kartoffelmos',
    'Broccolisalat',
    'Anders Ands kanelsnegle',
    'Hvidkålssalat',
    'Rucolasalat med bagte tomater',
    'Raita',
    'Pirogger med oksekød',
    'Pita brød',
    'Mango lassi',
    'TikTok baked oats',
    'Spinatsalat med feta og granatæble',
    'Spinat Pandekager',
    'Pizzadej',
    'Raw muslibar',
    'Mettes Æblekage',
    'Rugboller',
    'Naan',
    'Bedstemor ands chokoladekage',
    "Verdens bedste burger",
    "Kyllinge Nuggets med Corn Flakes",
    "Calzoneboller",
    "Bananbrød",
    "standard",
    "Hindbær Brülee",
    "Panna Cotta med Havtorn",
]

def load_recipe(path):
    with path.open("r") as f:
        return yaml.load(f, Loader=yaml.FullLoader)           
             
paths = pathlib.Path("recipes").glob("*.yml")
recipes = {p.stem:load_recipe(p) for p in paths}
recipes = {rec["navn"]: {**rec, "path":p} for p,rec in recipes.items() if not rec["navn"] in blacklist}

def add_standard_items(menu_recipes):
    menu_recipes["Andet"] = [dict(standardvarer=dict(amount=1, unit="plates"))]

@app.route('/')
def index():
    return render_template('index.html', recipes=json.dumps(list(recipes.keys())))


@app.route('/generate_menu', methods=['POST'])
def generate_menu():
    chosen_recipes = request.json['menu_data']
    menu_recipes = {}
    for recipe, plates in chosen_recipes.items():
        path = recipes[recipe]["path"]
        menu_recipes[path] = [{path:dict(amount=plates, unit="plates")}]

    add_standard_items(menu_recipes)
    menu_path = save_menu(menu_recipes)
    write_pdf(menu_path)

    return send_file("shopping.pdf", as_attachment=True)


import datetime

def save_menu(menu_dict):
    s = yaml.dump(menu_dict)
    isodate = datetime.date.today().isocalendar()
    recipe_file = pathlib.Path(f"uge_{isodate.week+1}_{isodate.year}.yaml")
    i=1
    while recipe_file.exists():
        recipe_file = pathlib.Path(f"uge_{isodate.week+1}_{isodate.year}({i}).yaml")
        i+=1

    with recipe_file.open("w") as f:
        f.write(s)

    return recipe_file


class MenuText():
    
    def __init__(self, menu=""):
        self.text=menu

    def add(self, s):
        self.text += s+"\n"
        
        with open("shopping.md", "w") as f:
            f.write(self.text)
        
    def __str__(self):
        return self.text

    def __repr__(self):
        return self.__str__()

import subprocess
import parser

def write_pdf(recipe_file):
    menu_text = MenuText()
    parser.write_menu(recipe_file, printer=menu_text.add)

    # Run pandoc to convert shopping.md to shopping.pdf
    subprocess.run([
        'pandoc', 'shopping.md', '-f', 'gfm', '-H', 'chapter_break.tex',
        '-V', 'geometry:a4paper', '-V', 'geometry:margin=4cm',
        '-V', 'mainfont=Montserrat', '-V', 'monofont=DejaVu Sans Mono',
        '--pdf-engine=xelatex', '-o', 'shopping.pdf'
    ])





if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)