"""KinoSuite Hub — Unified Creative Suite entry point.

Launch directly for the KinoSuite Hub window, or pass any creative file path
(e.g. `KinoSuite.exe track.wav` or `photo.png`) to route and open it in the
matching KinoSuite app automatically.
"""
from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kinosuite.icons import make_suite_pixmap
from kinosuite.mainwindow import KinoSuiteHubWindow
from kinosuite.registry import SuiteConfig, discover_suite_apps, launch_kino_app, route_file_to_app
from kinosuite.theme import KINOSUITE_HUB_DARK

APP_USER_MODEL_ID = "KinoSuite.Hub.Desktop.1"


def _set_windows_app_id() -> None:
    if sys.platform == "win32":
        try:
            shell32 = ctypes.windll.shell32
            shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
            shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass


def _load_suite_icon(suite_root: str) -> QIcon:
    ico_path = os.path.join(suite_root, "KinoSuite.ico")
    if os.path.isfile(ico_path):
        ic = QIcon(ico_path)
        if not ic.isNull():
            return ic
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(make_suite_pixmap(sz))
    return ic


def main() -> int:
    suite_root = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    file_args = [a for a in sys.argv[1:] if not a.startswith("-") and os.path.isfile(a)]

    # Fast universal file-router CLI mode when invoked with file arguments
    if file_args and "--hub" not in sys.argv:
        cfg = SuiteConfig(suite_root)
        apps = discover_suite_apps(suite_root, cfg)
        routed_any = False
        for fp in file_args:
            target = route_file_to_app(fp, apps)
            if target:
                launch_kino_app(target, [fp])
                cfg.add_recent(fp, target.app_id)
                routed_any = True
        if routed_any:
            return 0

    _set_windows_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("KinoSuite")
    app.setOrganizationName("KinoSuite")
    app.setStyleSheet(KINOSUITE_HUB_DARK)

    icon = _load_suite_icon(suite_root)
    app.setWindowIcon(icon)

    win = KinoSuiteHubWindow(suite_root=suite_root)
    win.setWindowIcon(icon)
    win.show()
    win.apply_native_taskbar_icon()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
