# User stories

Reference for the menu-editor roadmap. One persona: **the household cook-shopper**.

Status: ✅ works today · ⚠️ partly works · ❌ not built

Deployment model: single user, desktop-only, Flask bound to `0.0.0.0` so the
phone can reach it over the LAN. No auth, no multi-tenancy.

---

## E1 — Build up the recipe collection

| # | Story | Status |
|---|---|---|
| 1.1 | As a cook, I want to add a recipe by photographing a cookbook page, so I don't have to retype it | ✅ |
| 1.2 | As a cook, I want to add a recipe by typing it in, so I can record family recipes | ✅ |
| 1.3 | As a cook, I want to add a recipe from a web URL, so I can capture recipes I find online | ❌ |
| 1.4 | As a cook, I want to correct a recipe after adding it, because OCR and typing both make mistakes | ✅ |
| 1.5 | As a cook, I want to retire a recipe without deleting it, so it stops being suggested but history stays intact | ✅ |
| 1.6 | As a cook, I want to find a recipe by name *or* by an ingredient, so I can use up what I have | ✅ |
| 1.7 | As a cook, I want duplicate ingredient names merged, so "frisk koriander" and "koriander" stop being two rows | ⚠️ |

> 1.7 is exact-match only (`parser.py` ingredient lookup), which is why a single
> menu can produce two coriander lines.

## E2 — Plan the week

| # | Story | Status |
|---|---|---|
| 2.1 | As a cook, I want to pick recipes and set servings per meal, so quantities scale correctly | ✅ |
| 2.2 | As a cook, I want recipe suggestions when I have no inspiration | ✅ |
| 2.3 | As a cook, I want to mark a meal as "from the freezer", so it shows on the menu but not the shopping list | ✅ |
| 2.4 | As a cook, I want to avoid meals we ate recently, so we don't repeat ourselves | ❌ |
| 2.5 | As a cook, I want to plan by constraint ("4 veggie dinners, one fish"), so planning is faster | ❌ |
| 2.6 | As a cook, I want a printable weekly menu for the fridge | ✅ |

> 2.4 is cheap: 136 historical menus already sit in `menus/`, unread by the app.

## E3 — Turn the menu into a shopping list

| # | Story | Status |
|---|---|---|
| 3.1 | As a shopper, I want ingredients aggregated across all meals and scaled by servings | ✅ |
| 3.2 | As a shopper, I want to see which meal each item is for, so I can drop items when I drop a meal | ✅ |
| 3.3 | As a shopper, I want weekly staples added automatically, so I never forget coffee | ✅ |
| 3.4 | As a shopper, I want quantities in one sensible unit, not "100 g + 1 kg" | ❌ |

## E4 — Order the list by my kitchen

| # | Story | Status |
|---|---|---|
| 4.1 | As a shopper, I want the list grouped by kitchen zone in the order I walk, so I clear one area at a time | ⚠️ |
| 4.2 | As a shopper, I want to define my own zones and reorder them, because my kitchen isn't anyone else's | ✅ |
| 4.3 | As a shopper, I want to assign an ingredient to a zone | ✅ |
| 4.4 | As a shopper, I want to be told when an ingredient has no zone yet, so it stops silently landing in a mystery group | ❌ |
| 4.5 | As a shopper, I want a suggested zone for new ingredients, so I'm not doing data entry | ❌ |

> 4.1 is ⚠️ because grouping works but zone *names* are never rendered — the
> output is a series of anonymous tables.

## E5 — Check off what I already have

| # | Story | Status |
|---|---|---|
| 5.1 | As a shopper, I want to walk through my kitchen ticking off what I already have, so I don't buy duplicates | ❌ |
| 5.2 | As a shopper, I want to say in bulk "I have X, Y, Z" and have them all drop off the list | ❌ |
| 5.3 | As a shopper, I want the app to remember what I *usually* have, so the same items aren't proposed every week | ❌ |
| 5.4 | As a shopper, I want check-off done on my phone to be visible on my laptop | ❌ |

## E6 — Order it online

| # | Story | Status |
|---|---|---|
| 6.1 | As a shopper, I want to search my store's catalogue from inside the app | ❌ |
| 6.2 | As a shopper, I want to pick a product per ingredient seeing its picture, size and price, so I pick the right thing | ❌ |
| 6.3 | As a shopper, I want my usual product per ingredient remembered, so next week is one click | ❌ |
| 6.4 | As a shopper, I want the whole list pushed to my store basket in one go | ❌ |
| 6.5 | As a shopper, I want to do delivery slot and payment myself, because the app should not hold my card | ❌ |
| 6.6 | As a shopper, I don't want to be locked to one store | ❌ |

## E7 — Use it from wherever I am

| # | Story | Status |
|---|---|---|
| 7.1 | As a shopper, I want the list on my phone in the kitchen and in the shop | ❌ |
| 7.2 | As a cook, I want to drive the app from a chat client, so I can say what I want in words | ❌ |
| 7.3 | As a shopper, I want to print the list on paper | ✅ |

---

## Interface split

Not every story suits every interface.

| Task shape | Interface | Why |
|---|---|---|
| Capture a recipe, plan a week, state what you have, push a basket | **MCP** (chat) | Language-shaped. Bulk statements beat repeated tapping. |
| Tick a list while walking, choose between eight tubs of yoghurt | **Web UI** (phone) | Needs a persistent, glanceable screen and product images. |
| Delivery slot, payment | **The store's own site** | The app should never hold payment details. |

## Roadmap

| Phase | Delivers | Stories |
|---|---|---|
| 1 | Core extraction — structured shopping list, no behaviour change | foundation |
| 2 | Kitchen zones made real: seed mappings, render names, surface unmapped | 4.1, 4.4, 4.5, 1.7, 3.4 |
| 3 | Phone check-off | 5.1, 5.3, 5.4, 7.1 |
| 4 | MCP server | 7.2, 5.2, 2.4, 2.5, 1.3 |
| 5 | Provider abstraction + product search | 6.1, 6.2, 6.3, 6.6 |
| 6 | Basket push via Playwright | 6.4, 6.5 |
| 7 | Second provider to validate the abstraction | 6.6 |
