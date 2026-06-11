"""Headless UI test via streamlit.testing: load the app, check the KPI row,
chat panel and the map-view toggle render without exceptions.

    python scripts/ui_test.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    assert not at.exception, f"app raised on default run: {at.exception}"
    assert len(at.metric) == 3, f"expected 3 KPI metrics, got {len(at.metric)}"
    assert len(at.chat_input) == 1, "Plan Assistant chat input should render"

    at.radio[0].set_value("Fragmented dispatch (today's practice)")
    at.run()
    assert not at.exception, f"app raised on baseline map view: {at.exception}"

    print("metrics:", " | ".join(f"{m.label}={m.value}" for m in at.metric))
    print("UI TEST OK")


if __name__ == "__main__":
    main()
