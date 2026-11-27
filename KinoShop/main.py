"""KinoShop — KinoSuite Photo & Raster Design Studio entry point."""
from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kinoshop.icons import make_app_pixmap
from kinoshop.mainwindow import KinoShopWindow
from kinoshop.theme import KINOSUITE_DARK_THEME

APP_USER_MODEL_ID = "KinoSuite.KinoShop.Desktop.1"


def _set_windows_app_id() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass


def _load_app_icon() -> QIcon:
    root = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(root, "KinoShop.ico")
    if os.path.isfile(ico_path):
        ic = QIcon(ico_path)
        if not ic.isNull():
            return ic
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(make_app_pixmap(sz))
    return ic


def main() -> int:
    _set_windows_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("KinoShop")
    app.setOrganizationName("KinoSuite")
    app.setStyleSheet(KINOSUITE_DARK_THEME)

    icon = _load_app_icon()
    app.setWindowIcon(icon)

    initial_files = [a for a in sys.argv[1:] if not a.startswith("-")]
    win = KinoShopWindow(initial_files=initial_files)
    win.setWindowIcon(icon)
    win.show()
    win.apply_native_taskbar_icon()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
