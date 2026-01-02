import reflex as rx
import pathlib
import yaml
import json
import random
import datetime
import subprocess
from fuzzywuzzy import fuzz

# ======== Data Loading ========

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

def load_all_recipes():
    # Set up a way to mock the recipes for testing environments
    try:
        paths = pathlib.Path("recipes").glob("*.yml")
        recipes = {p.stem: load_recipe(p) for p in paths}
        recipes = {
            rec["navn"]: {**rec, "path": p} 
            for p, rec in recipes.items() 
            if rec["navn"] not in blacklist
        }
        return recipes
    except:
        # Mock data for testing when recipe files aren't available
        return {f"Recipe {i}": {"navn": f"Recipe {i}", "path": f"recipe_{i}"} for i in range(1, 20)}

# ======== State Management ========

class State(rx.State):
    """The app state."""
    
    # Recipe data
    all_recipes: dict = {}
    recipe_names: list = []
    
    # UI state
    available_recipes: list = []
    chosen_recipes: dict = {}  # recipe_name -> quantity
    search_results: list = []
    recipe_buttons: list = []
    
    # Toast notification
    toast_message: str = ""
    toast_visible: bool = False
    
    # Loading states
    is_spinning: bool = False
    
    def initialize(self):
        """Initialize the app state."""
        self.all_recipes = load_all_recipes()
        self.recipe_names = list(self.all_recipes.keys())
        self.available_recipes = self.recipe_names.copy()
        self.recipe_buttons = self.get_random_recipes(5)
    
    def get_random_recipes(self, count: int) -> list:
        """Get a list of random recipes."""
        if len(self.available_recipes) == 0:
            return ["No recipe available"] * count
            
        result = []
        temp_available = self.available_recipes.copy()
        
        for i in range(min(count, len(temp_available))):
            random_index = random.randint(0, len(temp_available) - 1)
            result.append(temp_available.pop(random_index))
        
        # Fill remaining slots if needed
        result += ["No recipe available"] * (count - len(result))
        return result
    
    def spin_recipes(self):
        """Randomize the recipe buttons."""
        self.is_spinning = True
        self.recipe_buttons = [""] * 5
        yield rx.set_timeout(
            self._finish_spin,
            timeout=1,
        )
    
    def _finish_spin(self):
        """Complete the spinning animation and update recipes."""
        self.recipe_buttons = self.get_random_recipes(5)
        self.is_spinning = False
    
    def search_recipes(self, query: str):
        """Search for recipes matching the query."""
        if not query:
            self.spin_recipes()
            return
        
        # Store matches with their scores
        scored_matches = []
        
        for recipe_name, recipe_data in self.all_recipes.items():
            # Skip recipes that are already chosen
            if recipe_name in self.chosen_recipes:
                continue
                
            # Score recipe name using fuzzy matching
            score = fuzz.partial_ratio(query.lower(), recipe_name.lower())
            
            # Score each ingredient if available
            if "ingredienser" in recipe_data:
                for ingredient_text in recipe_data["ingredienser"]:
                    ingredient_score = fuzz.partial_ratio(query.lower(), ingredient_text.lower())
                    score = max(score, ingredient_score)
            
            # Add to matches if score is above threshold
            if score > 80:  # Adjust threshold as needed
                scored_matches.append({
                    'name': recipe_name,
                    'score': score,
                })
        
        # Sort matches by score (highest first)
        sorted_matches = sorted(scored_matches, key=lambda x: -x['score'])
        
        # Update recipe buttons with search results
        result_names = [match['name'] for match in sorted_matches[:5]]
        
        # Fill remaining slots if needed
        result_names += ["No recipe available"] * (5 - len(result_names))
        self.recipe_buttons = result_names
    
    def add_recipe(self, recipe: str):
        """Add a recipe to the chosen list."""
        if recipe != "No recipe available" and recipe not in self.chosen_recipes:
            self.chosen_recipes[recipe] = 4  # Default to 4 portions
            # Remove from available recipes
            if recipe in self.available_recipes:
                self.available_recipes.remove(recipe)
            self.show_toast(f"Added {recipe} to your menu!")
    
    def update_recipe_quantity(self, recipe: str, quantity: int):
        """Update the quantity for a recipe."""
        if recipe in self.chosen_recipes:
            self.chosen_recipes[recipe] = quantity
    
    def remove_recipe(self, recipe: str):
        """Remove a recipe from the chosen list."""
        if recipe in self.chosen_recipes:
            del self.chosen_recipes[recipe]
            # Add back to available recipes
            if recipe not in self.available_recipes:
                self.available_recipes.append(recipe)
            self.show_toast(f"Removed {recipe} from your menu!")
    
    def show_toast(self, message: str):
        """Show a toast notification."""
        self.toast_message = message
        self.toast_visible = True
        yield rx.set_timeout(
            self._hide_toast,
            timeout=3,
        )
    
    def _hide_toast(self):
        """Hide the toast notification."""
        self.toast_visible = False
    
    def generate_menu(self):
        """Generate a PDF menu from chosen recipes."""
        if not self.chosen_recipes:
            self.show_toast("Please select at least one recipe first!")
            return
            
        self.show_toast("This would generate a PDF in a full implementation")
        # In a complete implementation, you would:
        # 1. Format chosen_recipes as needed
        # 2. Call your parser functions
        # 3. Create the PDF
        # 4. Trigger a download

# ======== UI Components ========

def recipe_button(recipe: str, index: int):
    """Create a recipe button component."""
    is_disabled = recipe == "No recipe available" or recipe == ""
    
    return rx.button(
        recipe if recipe else "",
        on_click=lambda: State.add_recipe(recipe) if not is_disabled else None,
        disabled=is_disabled,
        height="100px",
        border="1px solid #ddd",
        border_radius="8px",
        padding="1em",
        margin="0.5em",
        bg="white",
        color="black",
        cursor="pointer" if not is_disabled else "not-allowed",
        opacity="1" if not is_disabled else "0.5",
        font_size="1em",
        width="100%",
        text_align="center",
        transition="all 0.3s ease",
        _hover={"bg": "#f0f0f0", "transform": "translateY(-2px)"} if not is_disabled else {},
    )

def quantity_select(recipe: str, current_quantity: int):
    """Create a quantity select component."""
    return rx.select(
        options=[
            ("Fryser", 0),
            ("4 portioner", 4),
            ("8 portioner", 8),
        ],
        value=current_quantity,
        on_change=lambda value: State.update_recipe_quantity(recipe, int(value)),
        width="120px",
    )

def delete_button(recipe: str):
    """Create a delete button component."""
    return rx.button(
        "🗑️",
        on_click=lambda: State.remove_recipe(recipe),
        aria_label=f"Delete {recipe}",
        bg="transparent",
        border="none",
        cursor="pointer",
        font_size="1.2em",
        _hover={"color": "red"},
    )

def chosen_recipe_item(recipe: str, quantity: int):
    """Create a list item for a chosen recipe."""
    return rx.list_item(
        rx.hstack(
            rx.text(recipe, flex="1"),
            rx.hstack(
                quantity_select(recipe, quantity),
                delete_button(recipe),
                spacing="2",
            ),
            width="100%",
            justify="space-between",
        ),
        padding="0.5em",
        border_bottom="1px solid #eee",
    )

def toast_notification():
    """Create a toast notification component."""
    return rx.cond(
        State.toast_visible,
        rx.box(
            State.toast_message,
            position="fixed",
            bottom="20px",
            right="20px",
            bg="rgba(0, 0, 0, 0.7)",
            color="white",
            padding="1em",
            border_radius="8px",
            z_index="1000",
            transition="all 0.3s ease",
        ),
    )

# ======== Main App ========

def index():
    """The main page of the app."""
    return rx.container(
        # Header
        rx.heading("Recipe Randomizer", font_size="2em", margin_bottom="1em"),
        
        # Controls
        rx.hstack(
            rx.input(
                placeholder="Search recipes...",
                on_change=lambda value: State.search_recipes(value),
                width="100%",
                padding="0.5em",
                border="1px solid #ddd",
                border_radius="4px",
            ),
            rx.button(
                "Spin!",
                on_click=State.spin_recipes,
                disabled=State.is_spinning,
                padding="0.5em 1em",
                bg="#4CAF50",
                color="white",
                border="none",
                border_radius="4px",
                cursor="pointer",
                font_weight="bold",
                _hover={"bg": "#45a049"},
                _disabled={"bg": "#cccccc", "cursor": "not-allowed"},
                class_name=rx.cond(State.is_spinning, "spinning", ""),
            ),
            spacing="4",
            width="100%",
            margin_bottom="1em",
        ),
        
        # Recipe Grid
        rx.vstack(
            rx.grid(
                rx.foreach(
                    rx.range(5),
                    lambda i: recipe_button(
                        State.recipe_buttons[i] if i < len(State.recipe_buttons) else "No recipe available",
                        i
                    ),
                ),
                columns="1",
                spacing="4",
                width="100%",
                margin_bottom="2em",
                template_columns="repeat(auto-fit, minmax(200px, 1fr))",
                sx={
                    "@media (min-width: 768px)": {
                        "grid-template-columns": "repeat(3, 1fr)",
                    }
                },
            ),
            align_items="stretch",
            width="100%",
        ),
        
        # Chosen Recipes
        rx.vstack(
            rx.heading("Chosen Recipes", font_size="1.5em", margin_bottom="0.5em"),
            rx.cond(
                rx.len(State.chosen_recipes) > 0,
                rx.list(
                    rx.foreach(
                        State.chosen_recipes.items(),
                        lambda item: chosen_recipe_item(item[0], item[1])
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.text("No recipes chosen yet", color="gray"),
            ),
            width="100%",
            align_items="stretch",
            margin_bottom="2em",
            padding="1em",
            border="1px solid #eee",
            border_radius="8px",
        ),
        
        # Generate Menu Button
        rx.button(
            "Make Menu",
            on_click=State.generate_menu,
            width="100%",
            padding="0.75em",
            bg="#007BFF",
            color="white",
            border="none",
            border_radius="4px",
            cursor="pointer",
            font_weight="bold",
            _hover={"bg": "#0056b3"},
        ),
        
        # Toast Notification
        toast_notification(),
        
        # Container styling
        width="100%",
        max_width="800px",
        margin="0 auto",
        padding="2em",
    )

# ======== CSS Styles ========

style = {
    "@keyframes spin": {
        "0%": {"transform": "rotate(0deg)"},
        "100%": {"transform": "rotate(360deg)"},
    },
    ".spinning": {
        "animation": "spin 2s linear infinite",
    },
}

# Create app
app = rx.App(state=State, style=style)
app.add_page(index, title="Recipe Randomizer")