"""KinoFill — KinoSuite Local PDF & Form Studio entry point."""

from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kinofill import APP_NAME, SUITE_NAME
from kinofill.icons import make_app_pixmap
from kinofill.main_window import MainWindow


def _apply_win32_icon(win, ico_path: str) -> None:
    if sys.platform != "win32" or not os.path.isfile(ico_path):
        return
    try:
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
        user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        hwnd = ctypes.c_void_p(int(win.winId()))
        h_small = user32.LoadImageW(None, ico_path, 1, 16, 16, 0x0010)
        h_big = user32.LoadImageW(None, ico_path, 1, 48, 48, 0x0010)
        win._h_icons = (h_small, h_big)
        if h_small:
            user32.SendMessageW(hwnd, 0x0080, 0, h_small)
            user32.SetClassLongPtrW(hwnd, -34, h_small)
        if h_big:
            user32.SendMessageW(hwnd, 0x0080, 1, h_big)
            user32.SetClassLongPtrW(hwnd, -14, h_big)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    args = sys.argv if argv is None else argv
    if sys.platform == "win32":
        try:
            sh = ctypes.windll.shell32
            sh.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
            sh.SetCurrentProcessExplicitAppUserModelID("KinoSuite.KinoFill.Desktop.1")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(args)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(SUITE_NAME)
    ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "KinoFill.ico")
    icon = QIcon(ico_path) if os.path.isfile(ico_path) else QIcon(make_app_pixmap(64))
    app.setWindowIcon(icon)

    win = MainWindow()
    win.setWindowIcon(icon)
    win.show()
    _apply_win32_icon(win, ico_path)

    # Open any PDF / .kinofill (or legacy .freefill / .lfill) passed on command line
    for path in args[1:]:
        if os.path.exists(path):
            if path.lower().endswith((".kinofill", ".freefill", ".lfill")):
                win.open_project_file(path)
            elif path.lower().endswith(".pdf"):
                win.open_pdf(path)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
