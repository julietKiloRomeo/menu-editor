import datetime
import subprocess
import parser
import pathlib
import yaml
import json
import os

from flask import Flask, render_template, jsonify, request, send_file
from fuzzywuzzy import fuzz

#from dotenv import load_dotenv

# Load environment variables
#load_dotenv()

app = Flask(__name__, 
    static_url_path='', 
    static_folder='static',
    template_folder='templates')


# Add this configuration
app.config['APPLICATION_ROOT'] = os.environ.get('APP_PREFIX', '/')


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


@app.route('/search_recipes', methods=['GET'])
def search_recipes():
    try:
        query = request.args.get('query', '').lower()
        
        if not query:
            return jsonify({'recipes': list(recipes.keys())[:5]})
        
        # Store matches with their scores
        scored_matches = []
        
        for recipe_name, recipe_data in recipes.items():
            
            # Score recipe name using fuzzy matching
            score = fuzz.partial_ratio(query, recipe_name.lower())
            # Score each ingredient
            for ingredient_text in recipe_data["ingredienser"]:
                ingredient_score = fuzz.partial_ratio(query, ingredient_text.lower())
                score = max(score, ingredient_score)
            
            # Add to matches if score is above threshold
            if score > 80:  # Adjust threshold as needed
                scored_matches.append({
                    'name': recipe_name,
                    'score': score,
                })
        
        # Sort matches by:
        # 1. Name matches before ingredient matches
        # 2. Higher scores before lower scores
        sorted_matches = sorted( scored_matches, key=lambda x: -x['score'] )
        # Extract just the recipe names for the top 5 matches
        matched_recipes = [
            match['name'] 
            for match in sorted_matches[:5]
        ]
        
        return jsonify({
            'recipes': matched_recipes,
            'total_matches': len(scored_matches)  # Optional: include total count
        })
        
    except Exception as e:
        app.logger.error(f"Error in search_recipes: {str(e)}")
        return jsonify({
            'error': 'An error occurred while searching recipes',
            'recipes': []
        }), 500
    


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

