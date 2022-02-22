import db

dummy_data = {
    "plan": [
        {
            "name": "bolo uge",
            "rating": 4,
            "menus": [
                {
                    "title": "Bolo",
                    "days": ["tue", "wed"],
                    "parts": [
                        {"ingredient": "bolognese", "amount": 4, "unit": "plates",},
                        {"ingredient": "fettuccine", "amount": 400, "unit": "g",},
                    ],
                },
            ],
        },
    ],
    "recipe": [
        {
            "name": "mælkesuppe",
            "placement": "let mad",
            "rating": 3,
            "ingredients": [{"ingredient": "mælk", "amount": 2, "unit": "dl"},],
        }
    ],
    "ingredient": [
        {"name": "gulerod", "category": "frugt", "alii": ["gulerødder", "rødder"],},
        {"name": "havregryn", "category": "tilbehør", "alii": ["gryn"],},
        {"name": "fettuccine", "category": "tilbehør", "alii": [],},
    ],
}

database = db.DB()
database._clear()
for tablename, dummies in dummy_data.items():
    table = database._db.table(tablename)

    for dummy in dummies:
        table.insert(dummy)

