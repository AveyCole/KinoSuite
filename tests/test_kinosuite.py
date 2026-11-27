"""Verification & UI smoke test for KinoSuite Hub."""
from __future__ import annotations

import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

from kinosuite.mainwindow import KinoSuiteHubWindow
from kinosuite.registry import SuiteConfig, discover_suite_apps, route_file_to_app


def main() -> None:
    cfg = SuiteConfig(ROOT)
    apps = discover_suite_apps(ROOT, cfg)
    installed = [a.name for a in apps if a.installed]
    print("Discovered Installed KinoSuite Apps:", installed)
    for expected in ("KinoCut", "KinoShop", "KinoDraw", "KinoWave", "KinoFill", "KinoPixel"):
        assert expected in installed, f"Missing {expected}"

    # Verify Universal File Router
    assert route_file_to_app("clip.mp4", apps).app_id == "kinocut"
    assert route_file_to_app("poster.ksd", apps).app_id == "kinoshop"
    assert route_file_to_app("logo.svg", apps).app_id == "kinodraw"
    assert route_file_to_app("mix.wav", apps).app_id == "kinowave"
    assert route_file_to_app("form.pdf", apps).app_id == "kinofill"
    assert route_file_to_app("starbit.kpx", apps).app_id == "kinopixel"
    assert route_file_to_app("starbit.gba", apps).app_id == "kinopixel"

    app = QApplication.instance() or QApplication([])
    t0 = time.perf_counter()
    win = KinoSuiteHubWindow(ROOT)
    win.show()
    app.processEvents()
    t_ms = (time.perf_counter() - t0) * 1000.0

    # Visit all 5 pages & toggle Light/Dark cleanly
    for idx in range(5):
        win._switch_page(idx)
        app.processEvents()
    win._apply_theme("Light")
    app.processEvents()
    win._apply_theme("Dark")
    win._switch_page(0)
    app.processEvents()

    shot = os.path.join(ROOT, "tests", "kinosuite_hub_smoke.png")
    os.makedirs(os.path.dirname(shot), exist_ok=True)
    win.grab().save(shot)
    assert os.path.isfile(shot) and os.path.getsize(shot) > 10000
    win.cfg.data["minimize_to_tray"] = False
    win.close()
    print(f"[PASS] KinoSuite Hub verified! Startup: {t_ms:.0f} ms | Apps: {len(installed)}/6 | Cloud/Recent: {len(win._all_projects)} | Plugins: {len(win._all_plugins)}")


if __name__ == "__main__":
    main()
