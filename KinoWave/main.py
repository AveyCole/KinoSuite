"""KinoWave — KinoSuite Multitrack Audio Editing Platform entry point."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kinowave.icons import make_app_pixmap
from kinowave.mainwindow import KinoWaveWindow
from kinowave.theme import KINOWAVE_DARK_THEME


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("KinoWave")
    app.setOrganizationName("KinoSuite")
    app.setStyleSheet(KINOWAVE_DARK_THEME)
    app.setWindowIcon(QIcon(make_app_pixmap(64)))

    initial_files = [a for a in sys.argv[1:] if not a.startswith("-")]
    win = KinoWaveWindow(initial_files=initial_files)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
