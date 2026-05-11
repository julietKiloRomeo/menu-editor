## Overview
Create a standalone Playwright demo under `menu-editor/playwright-demo` that opens a visible browser to nemlig.com, lets the user log in manually, and loops through user-provided search terms. After each search, the script pauses for the user to pick a product and add it to the basket, then resumes on Enter.

## Goals
- Fast iteration demo for shopping assistance.
- Manual login and manual product selection for accuracy.
- Terminal-driven loop for entering the next item.

## Non-Goals
- Full automation of product selection or checkout.
- Persistent auth or stored credentials in this first demo.
- Integration into the menu-editor app flow.

## User Flow
1. Launch script.
2. Browser opens to nemlig.com.
3. User logs in manually.
4. Terminal prompts for item name.
5. Script performs search on site.
6. Script pauses; user clicks the desired product and adds it to basket.
7. User presses Enter in terminal to continue.
8. Loop repeats until user exits.

## Components
- `menu-editor/playwright-demo/`
  - `run_demo.py`: main script.
  - `README.md`: quick start notes and usage.

## Data Flow
- Input: item names typed into terminal.
- Actions: script fills search field and submits.
- No persistence; no local files written beyond the script and README.

## Error Handling
- Missing or changed selectors: log an error and exit with a clear message.
- Navigation or search timeouts: prompt user to retry the same item or skip.

## Security and Privacy
- No secrets read from disk.
- Manual login only; no session storage in this demo.

## Testing
- No automated tests for the demo script.
- Manual validation: search, pause, add item, and repeat.

## Open Questions
- None for demo scope.
