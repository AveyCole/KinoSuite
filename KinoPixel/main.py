"""KinoPixel — KinoSuite Retro Handheld Game Creation Studio entry point."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kinopixel.icons import make_app_pixmap
from kinopixel.mainwindow import KinoPixelWindow
from kinopixel.theme import KINOPIXEL_DARK_THEME


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("KinoPixel")
    app.setOrganizationName("KinoSuite")
    app.setStyleSheet(KINOPIXEL_DARK_THEME)
    app.setWindowIcon(QIcon(make_app_pixmap(64)))

    initial_files = [a for a in sys.argv[1:] if not a.startswith("-")]
    win = KinoPixelWindow(initial_files=initial_files)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
