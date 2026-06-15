"""Keep a Streamlit Community Cloud app awake with a real browser session.

A plain HTTP GET returns 200 but does NOT reset Streamlit's inactivity timer:
that timer tracks real viewer sessions (the WebSocket to /_stcore/stream), not
page-shell requests. This script loads the app in headless Chromium, wakes it
if it is asleep, waits for the app to render, and stays on the page briefly so
the session registers. It exits non-zero if the app never rendered, so a green
run means the app is genuinely up.
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL")
if not URL:
    sys.exit("APP_URL not set")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        print(f"Visiting {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        time.sleep(5)

        if any(s in page.content().lower()
               for s in ("get this app back up", "gone to sleep", "is sleeping")):
            print("App is asleep — clicking the wake button")
            try:
                page.locator("button").first.click(timeout=20000)
            except Exception as exc:
                print(f"Could not click wake button: {exc}")
            time.sleep(60)  # allow the app to reboot

        loaded = False
        try:
            page.wait_for_selector('[data-testid="stApp"]', timeout=90000)
            loaded = True
            print("Streamlit app rendered")
        except Exception as exc:
            print(f"App did not render: {exc}")

        time.sleep(30)  # keep the session open so it counts as activity
        browser.close()
    return 0 if loaded else 1


if __name__ == "__main__":
    sys.exit(main())
