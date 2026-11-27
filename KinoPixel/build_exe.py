"""Build script to generate kinopixel.ico and package KinoPixel.exe via PyInstaller."""
from __future__ import annotations

import io
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

from kinopixel.icons import make_app_pixmap


def build_ico(ico_path: str) -> None:
    app = QApplication.instance() or QApplication([])
    imgs = []
    for sz in (256, 128, 64, 48, 32, 16):
        pm = make_app_pixmap(sz)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        im = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")
        imgs.append(im)
    imgs[0].save(ico_path, format="ICO", sizes=[(im.width, im.height) for im in imgs])
    print(f"Generated icon: {ico_path}")


def main() -> int:
    ico_path = os.path.join(ROOT, "kinopixel.ico")
    build_ico(ico_path)

    if "--icon-only" in sys.argv:
        return 0

    excludes = [
        "tkinter", "_tkinter", "matplotlib", "pandas", "cv2", "scipy",
        "sympy", "onnxruntime", "reportlab", "pypdf", "folium", "branca",
        "beautifulsoup4", "bs4", "jinja2", "Jinja2", "requests", "urllib3",
        "PySide6.QtWebEngine", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
        "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtSvg",
        "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtPrintSupport", "PySide6.QtSql",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "KinoPixel",
        "--icon", ico_path,
        "--collect-data", "_sounddevice_data",
        "--collect-binaries", "_sounddevice_data",
        "--hidden-import", "sounddevice",
        "--hidden-import", "_sounddevice_data",
        "--hidden-import", "PIL.Image",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build"),
        "--specpath", ROOT,
    ]
    for ex in excludes:
        cmd.extend(["--exclude-module", ex])
    cmd.append(os.path.join(ROOT, "main.py"))

    print("Running PyInstaller for KinoPixel...")
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode != 0:
        return res.returncode

    src_exe = os.path.join(ROOT, "dist", "KinoPixel.exe")
    dst_exe = os.path.join(ROOT, "KinoPixel.exe")
    shutil.copy2(src_exe, dst_exe)
    size_mb = os.path.getsize(dst_exe) / (1024 * 1024)
    print(f"Built standalone executable: {dst_exe} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
