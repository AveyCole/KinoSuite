"""Build script to generate kinowave.ico and package KinoWave.exe via PyInstaller."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from kinowave.icons import make_app_pixmap


def build_ico(ico_path: str) -> None:
    app = QApplication.instance() or QApplication([])
    imgs = []
    for sz in (256, 128, 64, 48, 32, 16):
        pm = make_app_pixmap(sz)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        import io
        im = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")
        imgs.append(im)
    imgs[0].save(ico_path, format="ICO", sizes=[(im.width, im.height) for im in imgs])
    print(f"Generated icon: {ico_path}")


def main() -> int:
    ico_path = os.path.join(ROOT, "kinowave.ico")
    build_ico(ico_path)

    excludes = [
        "tkinter", "_tkinter", "matplotlib", "pandas", "cv2", "PIL", "scipy",
        "sympy", "onnxruntime", "reportlab", "pypdf", "folium", "branca",
        "beautifulsoup4", "bs4", "jinja2", "Jinja2", "requests", "urllib3",
        "PyAutoGUI", "pyautogui", "pyscreeze", "pytweening", "pygetwindow",
        "pymsgbox", "mouseinfo", "vlc", "unicorn", "pefile", "uiautomation",
        "PySide6.QtWebEngine", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
        "PySide6.Qt3DExtras", "PySide6.Qt3DAnimation", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
        "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql", "PySide6.QtSvg",
        "PySide6.QtTest", "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
        "PySide6.QtPrintSupport", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
        "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtWebChannel",
        "PySide6.QtWebSockets", "PySide6.QtXml", "PySide6.QtGraphs", "PySide6.QtHttpServer",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "KinoWave",
        "--icon", ico_path,
        "--collect-data", "_sounddevice_data",
        "--collect-binaries", "_sounddevice_data",
        "--collect-all", "pedalboard",
        "--hidden-import", "sounddevice",
        "--hidden-import", "_sounddevice_data",
        "--hidden-import", "pedalboard",
        "--hidden-import", "kinowave.vst_host",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", ROOT,
    ]
    for ex in excludes:
        cmd.extend(["--exclude-module", ex])
    cmd.append(os.path.join(ROOT, "main.py"))

    print("Running PyInstaller...")
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode != 0:
        return res.returncode

    src_exe = os.path.join(ROOT, "dist", "KinoWave.exe")
    dst_exe = os.path.join(ROOT, "KinoWave.exe")
    shutil.copy2(src_exe, dst_exe)
    size_mb = os.path.getsize(dst_exe) / (1024 * 1024)
    print(f"Built standalone executable: {dst_exe} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
