import db

dummy_data = {
    "menu" : [
                {
                    "name":"bolo uge",
                    "rating":4,
                    "recipes":[
                        {
                            "recipe": {"ingredient":"bolognese", "amount":4, "unit": "plates"},
                            "day": ["tue", "wed"],
                        },
                        {
                            "recipe": {"ingredient":"fettuccine", "amount":4, "unit": "plates"},
                            "day": ["tue", "wed"],
                        }
                    ],
                },
                {
                    "name":"grød uge",
                    "rating":4,
                    "recipes":[
                        {
                            "recipe": {"ingredient":"havregrød", "amount":4, "unit": "plates"},
                            "day": ["mon", "thur"],
                        },
                        {
                            "recipe": {"ingredient":"risengrød", "amount":4, "unit": "plates"},
                            "day": ["tue", "wed"],
                        }
                    ],
                },
            ],
    "recipe": [
        {
            "name": "mælkesuppe",
            "placement":"let mad",
            "rating":3,
            "ingredients": [{"ingredient":"mælk", "amount":2, "unit":"dl"},],
        }
    ],
    "ingredient":[
        {
            "name": "gulerod",
            "category": "frugt",
            "alii": ["gulerødder"],
        },
    ],
}

database = db.DB()

for tablename, dummies in dummy_data.items():
    table = database._db.table(tablename)
    
    for dummy in dummies:
        table.insert(dummy)


