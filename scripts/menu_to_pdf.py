"""Render just the menu half of a menu markdown file to a printable PDF.

The weekly markdown produced by the app (and downloaded as ``menu-<date>.md``)
holds two documents: ``# Menu`` and then ``# Shopping``. The shopping list goes
to the phone now, so what gets printed for the fridge is the menu alone.

This script stops at the ``# Shopping`` heading, so the shopping table never
reaches the page.

Usage::

    uv run python scripts/menu_to_pdf.py ~/Downloads/menu-2026-09-12.md
    uv run python scripts/menu_to_pdf.py <input.md> -o <output.pdf>

PDF generation shells out to headless Chromium, which is the same engine the
in-app Print button uses, so the output matches what the browser would produce.
A throwaway profile directory is used so this never touches the logged-in
browser session.
"""

from __future__ import annotations

import argparse
import datetime
import html
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

#: Everything from this heading onwards is the shopping list, which we drop.
SHOPPING_HEADING = re.compile(r"^#\s+Shopping\s*$", re.IGNORECASE)
MENU_HEADING = re.compile(r"^#\s+Menu\s*$", re.IGNORECASE)
SECTION_HEADING = re.compile(r"^##\s+(?P<name>.+?)\s*$")
#: Matches ``render_menu_entry``: " - <name> <(xN)|(fryser)> : <placering>".
ENTRY = re.compile(r"^\s*-\s+(?P<body>.*?)\s*:\s*(?P<placering>.*?)\s*$")
NOTE = re.compile(r"^\s*\((?P<note>x[\d.]+|fryser)\)\s*$")


@dataclass
class Entry:
    name: str
    note: str
    placering: str


def parse_menu(text: str) -> tuple[list[Entry], list[str]]:
    """Return the menu entries and any section names that carried no entry.

    Sections whose name merely repeats their single dish are collapsed, since
    the app emits one section per dish for imported menus.
    """
    entries: list[Entry] = []
    in_menu = False
    current_section: str | None = None
    empty_sections: list[str] = []

    for line in text.splitlines():
        if SHOPPING_HEADING.match(line):
            break
        if MENU_HEADING.match(line):
            in_menu = True
            continue
        if not in_menu:
            continue

        section = SECTION_HEADING.match(line)
        if section:
            if current_section and not any(
                e.name.casefold() == current_section.casefold() for e in entries
            ):
                empty_sections.append(current_section)
            current_section = section.group("name")
            continue

        match = ENTRY.match(line)
        if not match:
            continue

        body = match.group("body").strip()
        note = ""
        # The amount marker, when present, is the trailing parenthesised token.
        if body.endswith(")") and "(" in body:
            head, _, tail = body.rpartition("(")
            candidate = NOTE.match("(" + tail)
            if candidate:
                note = candidate.group("note")
                body = head.strip()

        entries.append(
            Entry(name=body, note=note, placering=match.group("placering").strip())
        )

    return entries, empty_sections


def week_label(source: Path) -> str:
    """Derive 'uge N' from a ``menu-YYYY-MM-DD.md`` filename.

    The app names a menu for the week it is shopped, which is the week *after*
    the Saturday it was generated (see ``save_menu`` in app.py).
    """
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", source.stem)
    if not match:
        return ""
    made = datetime.date(*(int(part) for part in match.groups()))
    shopped = made + datetime.timedelta(days=7)
    return f"Uge {shopped.isocalendar()[1]}"


def render_html(entries: list[Entry], subtitle: str) -> str:
    rows = []
    for entry in entries:
        note = (
            f'<span class="note">{html.escape(entry.note)}</span>' if entry.note else ""
        )
        placering = (
            f'<p class="placering">{html.escape(entry.placering)}</p>'
            if entry.placering
            else ""
        )
        rows.append(
            f'<li><div class="dish"><h2>{html.escape(entry.name)}</h2>{note}</div>'
            f"{placering}</li>"
        )
    items = "\n".join(rows)
    heading = html.escape(subtitle)

    return f"""<!doctype html>
<html lang="da">
<meta charset="utf-8">
<title>Menu</title>
<style>
  @page {{ size: A4; margin: 22mm 20mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
    color: #16130f;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  header {{ border-bottom: 2px solid #16130f; padding-bottom: 10mm; }}
  h1 {{
    margin: 0;
    font-size: 40pt;
    font-weight: 600;
    letter-spacing: -0.02em;
  }}
  .subtitle {{
    margin: 3mm 0 0;
    font-size: 11pt;
    letter-spacing: 0.32em;
    text-transform: uppercase;
    color: #8a7f70;
  }}
  ol {{ list-style: none; margin: 0; padding: 0; counter-reset: dish; }}
  li {{
    counter-increment: dish;
    padding: 7mm 0 7mm 16mm;
    border-bottom: 1px solid #e0d9cd;
    position: relative;
    break-inside: avoid;
  }}
  li::before {{
    content: counter(dish, decimal-leading-zero);
    position: absolute;
    left: 0;
    top: 8.5mm;
    font-size: 10pt;
    letter-spacing: 0.1em;
    color: #b8ab98;
  }}
  li:last-child {{ border-bottom: none; }}
  .dish {{ display: flex; align-items: baseline; gap: 4mm; }}
  h2 {{ margin: 0; font-size: 21pt; font-weight: 500; letter-spacing: -0.01em; }}
  .note {{
    font-size: 10pt;
    letter-spacing: 0.08em;
    color: #8a7f70;
    white-space: nowrap;
  }}
  .placering {{
    margin: 2mm 0 0;
    font-size: 11pt;
    font-style: italic;
    color: #6d6255;
  }}
</style>
<body>
  <header>
    <h1>Menu</h1>
    <p class="subtitle">{heading}</p>
  </header>
  <ol>
{items}
  </ol>
</body>
</html>
"""


def find_chromium() -> str:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit(
        "No Chromium/Chrome binary found; install one or render the HTML by hand."
    )


def html_to_pdf(document: str, destination: Path, timeout: float = 60.0) -> None:
    """Print ``document`` to ``destination`` using headless Chromium.

    Chromium is not expected to exit on its own: a ``--remote-debugging-port``
    in the user's global ``chromium-flags.conf`` is injected into every launch,
    including this one, and the resulting listener keeps the browser alive long
    after the PDF is on disk. So we wait for the *file* and then terminate the
    process, rather than waiting for the process.
    """
    binary = find_chromium()
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "menu.html"
        source.write_text(document, encoding="utf-8")
        # A scratch profile keeps this away from the real, logged-in browser.
        profile = Path(tmp) / "profile"
        process = subprocess.Popen(
            [
                binary,
                "--headless=new",
                "--disable-gpu",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-component-update",
                # Do not contend for the debugging port the real browser holds.
                "--remote-debugging-port=0",
                "--no-pdf-header-footer",
                f"--print-to-pdf={destination}",
                source.as_uri(),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if destination.exists() and destination.stat().st_size > 0:
                    # Give the write a moment to flush before we kill the process.
                    time.sleep(0.4)
                    return
                if process.poll() is not None:
                    break
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

        stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""

    if not destination.exists() or destination.stat().st_size == 0:
        sys.stderr.write(stderr)
        raise SystemExit(f"Chromium failed to produce {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="menu markdown file")
    parser.add_argument(
        "-o", "--output", type=Path, default=None, help="destination PDF"
    )
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"No such file: {args.source}")

    text = args.source.read_text(encoding="utf-8")
    entries, empty_sections = parse_menu(text)
    if not entries:
        raise SystemExit(f"No menu entries found in {args.source}")

    destination = args.output or args.source.with_suffix(".pdf")
    html_to_pdf(render_html(entries, week_label(args.source)), destination)

    print(f"{destination}  ({len(entries)} dishes)")
    for entry in entries:
        suffix = f" ({entry.note})" if entry.note else ""
        print(f"  - {entry.name}{suffix} : {entry.placering}")
    if empty_sections:
        print(f"  note: sections with no entries skipped: {', '.join(empty_sections)}")


if __name__ == "__main__":
    main()
