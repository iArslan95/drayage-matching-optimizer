"""Keep a public Streamlit Community Cloud app awake with a real browser session.

A plain HTTP GET returns 200 (the static shell) but does NOT reset Streamlit's
inactivity timer, which tracks real viewer sessions (the WebSocket the JS opens).
This script loads the app in headless Chromium; if it finds the app asleep (a
wake prompt instead of the app), it clicks the wake button, then waits for the
app to actually render. It stays on the page briefly so the session registers,
and exits non-zero (with diagnostics) if the app never rendered.
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL")
if not URL:
    sys.exit("APP_URL not set")

DEADLINE_S = 180
APP = '[data-testid="stApp"]'


def snapshot(page):
    labels = []
    for b in page.query_selector_all("button")[:6]:
        try:
            tx = (b.inner_text() or "").strip().replace("\n", " ")
            if tx:
                labels.append(tx[:40])
        except Exception:
            pass
    body = ""
    try:
        body = (page.inner_text("body") or "").strip().replace("\n", " ")[:200]
    except Exception:
        pass
    return labels, body


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        print(f"Visiting {URL}", flush=True)
        page.goto(URL, wait_until="load", timeout=90000)

        clicked = False
        loaded = False
        start = time.time()
        while time.time() - start < DEADLINE_S:
            if page.query_selector(APP):
                loaded = True
                break
            labels, body = snapshot(page)
            elapsed = int(time.time() - start)
            print(f"t={elapsed}s no app yet | buttons={labels} | body='{body}'",
                  flush=True)
            if not clicked:
                btn = page.query_selector("button")
                if btn:
                    try:
                        btn.click()
                        clicked = True
                        print("  clicked a button (assumed wake control)", flush=True)
                    except Exception as exc:
                        print(f"  click failed: {exc}", flush=True)
            time.sleep(6)

        if loaded:
            print("Streamlit app rendered — session established", flush=True)
            time.sleep(20)  # keep the session open so it counts as activity
            browser.close()
            return 0

        labels, body = snapshot(page)
        print(f"FAILED to render within {DEADLINE_S}s | buttons={labels} | "
              f"body='{body}'", flush=True)
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
