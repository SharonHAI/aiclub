#!/usr/bin/env python3
"""Checks the class registration page for an open spot and notifies by email
and push (ntfy) on the transition into "open". Never touches the
registration form itself — detection and notification only."""

import datetime
import json
import os
import re
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

TARGET_URL = os.environ["TARGET_URL"]
FULL_TEXT_PATTERNS = [
    p.strip()
    for p in os.environ.get("FULL_TEXT_PATTERNS", "full group,complet,sold out,no places").split(",")
    if p.strip()
]
REGISTER_BUTTON_PATTERN = os.environ.get("REGISTER_BUTTON_PATTERN", r"regist|sign up|inscri")
STATE_PATH = Path(os.environ.get("STATE_PATH", "state/status.json"))
EMAIL_TO = os.environ["EMAIL_TO"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
DEBUG_DIR = Path(os.environ.get("DEBUG_DIR", "debug-output"))


def fetch_page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(TARGET_URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2000)  # let any post-load rendering settle

        text = page.inner_text("body")
        button_info = []
        for button in page.query_selector_all("button"):
            try:
                label = (button.inner_text() or "").strip()
            except Exception:
                label = ""
            button_info.append({"label": label, "disabled": button.is_disabled()})

        if DEBUG:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            (DEBUG_DIR / "page-text.txt").write_text(text, encoding="utf-8")
            (DEBUG_DIR / "buttons.json").write_text(json.dumps(button_info, indent=2), encoding="utf-8")
            page.screenshot(path=str(DEBUG_DIR / "screenshot.png"), full_page=True)

        browser.close()
        return text, button_info


def is_full_by_text(text):
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in FULL_TEXT_PATTERNS)


def register_button_enabled(button_info):
    """Returns True/False, or None if no register-like button was found at all
    (page structure changed — inconclusive, caller should not act on it)."""
    pattern = re.compile(REGISTER_BUTTON_PATTERN, re.IGNORECASE)
    matches = [b for b in button_info if pattern.search(b["label"])]
    if not matches:
        return None
    return any(not b["disabled"] for b in matches)


def send_email(message, subject):
    payload = json.dumps({"_subject": subject, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        f"https://formsubmit.co/ajax/{EMAIL_TO}",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


def send_ntfy(message, title):
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "urgent", "Tags": "rotating_light"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


def load_previous_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"open": False, "checked_at": None}


def main():
    text, button_info = fetch_page()
    full_by_text = is_full_by_text(text)
    enabled = register_button_enabled(button_info)

    if enabled is None:
        print("WARNING: no register-like button found on the page — structure may have "
              "changed. Skipping this run without touching state or sending a notification.")
        print(f"Buttons seen: {button_info}")
        return

    is_open = (not full_by_text) and enabled
    print(f"full_by_text={full_by_text} register_button_enabled={enabled} -> is_open={is_open}")

    previous = load_previous_state()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"open": is_open, "checked_at": now}, indent=2) + "\n")

    if is_open:
        subject = "Class spot just opened!" if not previous.get("open") else "Still open — go register"
        body = f"A spot is open for the class. Register now:\n{TARGET_URL}"

        for channel, send in (("email", lambda: send_email(body, subject)), ("ntfy", lambda: send_ntfy(body, subject))):
            try:
                send()
                print(f"Notification sent via {channel}.")
            except Exception as exc:
                print(f"WARNING: {channel} notification failed: {exc}")
    else:
        print("Still full — no notification.")


if __name__ == "__main__":
    main()
