#!/usr/bin/env python3
"""
Headful Playwright exploration script for BilkaToGo.

Goals:
- Open BilkaToGo, dismiss cookies, and help you log in
- Optionally set store context (via zip)
- Optionally search and click "add to basket" for a sample product
- Log relevant network traffic so we can learn hidden cart endpoints

Run:
  uv run python scripts/bilkatogo_explore.py --headful --zip 8000 --sample "mælk"

Environment:
  BILKA_EMAIL, BILKA_PASSWORD (optional if you already have storage state)

Notes:
- This script is intentionally verbose and defensive; selectors are best-effort
- You can press Ctrl+C to stop; artifacts/logs are written under playwright/
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARTIFACTS = ROOT / "playwright"
AUTH_STATE = ARTIFACTS / ".auth" / "bilka.json"
LOG_DIR = ARTIFACTS / "logs"


def ensure_dirs() -> None:
    (ARTIFACTS / ".auth").mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def save_storage_state(context: BrowserContext, path: Path = AUTH_STATE) -> None:
    context.storage_state(path=str(path))
    print(f"Saved storage state → {path}")


def attach_logging(page: Page) -> None:
    log_path = LOG_DIR / "bilka-network.log"
    f = log_path.open("a", encoding="utf-8")

    SENSITIVE = re.compile(r"authorization|cookie|set-cookie|token|x-.*auth|bearer", re.I)

    def strip_query(u: str) -> str:
        try:
            return u.split("?", 1)[0]
        except Exception:
            return u

    def sanitized_headers(hdrs: dict) -> dict:
        return {k: ("<redacted>" if SENSITIVE.search(k) else v) for k, v in hdrs.items()}

    def on_request(req):
        url = req.url
        if re.search(r"cart|basket|checkout|bag", url, re.I):
            safe_url = strip_query(url)
            f.write(f"REQ {req.method} {safe_url}\n")
            headers = dict(req.headers)
            f.write(f"  headers: {sanitized_headers(headers)}\n")
            # Do not log bodies to avoid leaking tokens
            f.flush()

    def on_response(res):
        url = res.url
        if re.search(r"cart|basket|checkout|bag", url, re.I):
            safe_url = strip_query(url)
            f.write(f"RES {res.status} {safe_url}\n")
            # Do not log response bodies by default
            f.flush()

    page.on("request", on_request)
    page.on("response", on_response)
    print(f"Logging network (redacted) to {log_path}")


def dismiss_cookie_banner(page: Page) -> None:
    candidates = [
        re.compile(r"accept|accepter|tillad|ok", re.I),
        re.compile(r"accept all|accepter alle", re.I),
    ]
    for pattern in candidates:
        try:
            btn = page.get_by_role("button", name=pattern)
            if btn and btn.is_visible():
                btn.click(timeout=2000)
                return
        except Exception:
            continue


def try_login(page: Page, email: Optional[str], password: Optional[str]) -> bool:
    """Attempt a basic login flow if credentials are present.

    Returns True if we're likely logged in, False otherwise.
    """
    if not email or not password:
        print("No credentials provided; skipping login.")
        return False

    try:
        # Common entry points: a user icon or a 'Log ind' link/button.
        login_triggers = [
            page.get_by_role("button", name=re.compile("log ind|login|konto|account", re.I)),
            page.get_by_role("link", name=re.compile("log ind|login|konto|account", re.I)),
        ]
        for trig in login_triggers:
            try:
                if trig.is_visible():
                    trig.click(timeout=1500)
                    break
            except Exception:
                pass

        # Fill forms (best-effort; adjust selectors as we learn the site)
        email_input = page.get_by_role("textbox", name=re.compile("e(-)?mail|email", re.I))
        if not email_input or not email_input.is_visible():
            # fallback to input[type=email]
            email_input = page.locator("input[type=email]").first
        if email_input:
            email_input.fill(email)

        password_input = page.get_by_role("textbox", name=re.compile("adgangskode|password|kodeord", re.I))
        if not password_input or not password_input.is_visible():
            password_input = page.locator("input[type=password]").first
        if password_input:
            password_input.fill(password)

        submit_btn = page.get_by_role("button", name=re.compile("log ind|login|fortsæt|continue", re.I))
        if submit_btn:
            submit_btn.click()
            page.wait_for_timeout(2000)
            print("Submitted login form; complete any 2FA if prompted.")
            return True
    except Exception as exc:
        print(f"Login attempt failed: {exc}")
    return False


def ensure_store(page: Page, zip_code: Optional[str]) -> None:
    if not zip_code:
        return
    try:
        # Try an element that opens store/location modal
        store_btn = page.get_by_role("button", name=re.compile("levering|butik|udlevering|postnr|postnummer|vælg", re.I))
        if store_btn and store_btn.is_visible():
            store_btn.click()
            # Find a postal code input
            zip_input = page.get_by_role("textbox", name=re.compile("postnr|postnummer|zip", re.I))
            if not zip_input or not zip_input.is_visible():
                zip_input = page.locator("input").filter(has_text=re.compile("post|zip", re.I)).first
            if zip_input:
                zip_input.fill(zip_code)
                page.keyboard.press("Enter")
                page.wait_for_timeout(1500)
            # Try to choose a first suggestion if presented
            try:
                first_option = page.get_by_role("button", name=re.compile("vælg|choose|select", re.I)).first
                if first_option:
                    first_option.click()
            except Exception:
                pass
            page.wait_for_timeout(1000)
    except Exception:
        pass


def search_and_try_add(page: Page, query: str, clicks: int = 1) -> None:
    print(f"Searching for: {query}")
    # Try to focus a search box
    try:
        search_input = page.get_by_role("textbox", name=re.compile("søg|search", re.I))
        if not search_input or not search_input.is_visible():
            search_input = page.locator("input[type=search]").first
        if not search_input:
            print("Could not find a search input.")
            return
        search_input.fill(query)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)
    except Exception:
        print("Search input interaction failed.")
        return

    # Try to click the first visible “add to basket” for result
    for i in range(clicks):
        try:
            add_btn = page.get_by_role("button", name=re.compile("læg i kurv|add|kurv|basket|læg i indkøbskurv", re.I)).first
            if add_btn and add_btn.is_enabled():
                add_btn.click()
                page.wait_for_timeout(600)
                print(f"Clicked add to basket ({i+1}/{clicks}).")
        except Exception:
            print("Add button not found or not clickable.")
            break


def load_env_defaults() -> None:
    """Load .env (if present) without an external dependency.

    Only sets variables that are not already present in the environment.
    """
    env_path = ROOT / ".env"
    try:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)
    except Exception:
        # best-effort; ignore parsing issues silently
        pass


def run(headless: bool, zip_code: Optional[str], sample: Optional[str]) -> None:
    load_env_defaults()
    email = os.getenv("BILKA_EMAIL")
    password = os.getenv("BILKA_PASSWORD")

    ensure_dirs()
    with sync_playwright() as pw:
        browser: Browser
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(AUTH_STATE) if AUTH_STATE.exists() else None)
        page = context.new_page()

        attach_logging(page)

        # Go to homepage
        url = "https://www.bilkatogo.dk/"  # adjust if redirected
        print(f"Opening {url}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)

        dismiss_cookie_banner(page)
        ensure_store(page, zip_code)

        # If not authenticated, attempt login
        logged_in = try_login(page, email, password)
        if logged_in:
            page.wait_for_timeout(2000)
            save_storage_state(context)

        # Optional sample search/add
        if sample:
            search_and_try_add(page, sample, clicks=1)

        if not headless:
            print("Headful mode: pausing so you can explore. Close the window to exit.")
            page.pause()

        context.close()
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headful", action="store_true", help="Launch Chromium headful for exploration")
    parser.add_argument("--zip", help="Preferred pickup ZIP/store context (optional)")
    parser.add_argument("--sample", help="Sample product name to search and try to add")
    args = parser.parse_args()

    try:
        run(headless=not args.headful, zip_code=args.zip, sample=args.sample)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
