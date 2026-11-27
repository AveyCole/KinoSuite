"""Build standalone Windows single-file (.exe) release binaries for the entire KinoSuite."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from typing import List, Tuple

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "release_assets")
WORK_DIR = os.path.join(ROOT, "_pyi_work")

COMMON_EXCLUDES = [
    "tkinter", "_tkinter", "matplotlib", "pandas", "scipy", "sympy", "onnxruntime",
    "folium", "branca", "beautifulsoup4", "bs4", "jinja2", "Jinja2", "requests", "urllib3",
    "PyAutoGUI", "pyautogui", "pyscreeze", "pytweening", "pygetwindow", "pymsgbox", "mouseinfo",
    "vlc", "unicorn", "pefile", "uiautomation", "pedalboard",
    "PySide6.QtWebEngine", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DExtras", "PySide6.Qt3DAnimation", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtNetwork", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtXml", "PySide6.QtGraphs", "PySide6.QtHttpServer",
]


def build_one(
    name: str,
    entry_script: str,
    ico_path: str,
    extra_args: List[str],
    extra_excludes: List[str],
) -> str:
    t0 = time.perf_counter()
    print(f"\n=== Building standalone {name}.exe ===")
    work = os.path.join(WORK_DIR, name)
    spec = os.path.join(WORK_DIR, "specs")
    os.makedirs(work, exist_ok=True)
    os.makedirs(spec, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", name,
        "--icon", ico_path,
        "--distpath", OUT_DIR,
        "--workpath", work,
        "--specpath", spec,
    ]
    cmd.extend(extra_args)
    for ex in COMMON_EXCLUDES + extra_excludes:
        cmd.extend(["--exclude-module", ex])
    cmd.append(entry_script)

    res = subprocess.run(cmd, cwd=os.path.dirname(entry_script))
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller failed for {name} (exit {res.returncode})")
    out_exe = os.path.join(OUT_DIR, f"{name}.exe")
    mb = os.path.getsize(out_exe) / (1024 * 1024)
    print(f"[OK] Built {name}.exe ({mb:.1f} MB) in {time.perf_counter() - t0:.1f}s")
    return out_exe


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)

    specs: List[Tuple[str, str, str, List[str], List[str]]] = [
        (
            "KinoSuite",
            os.path.join(ROOT, "main.py"),
            os.path.join(ROOT, "KinoSuite.ico"),
            [],
            ["numpy", "cv2", "PIL", "reportlab", "pypdf", "sounddevice", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSvg", "PySide6.QtPrintSupport"],
        ),
        (
            "KinoPixel",
            os.path.join(ROOT, "KinoPixel", "main.py"),
            os.path.join(ROOT, "KinoPixel", "KinoPixel.ico"),
            [
                "--collect-data", "_sounddevice_data",
                "--collect-binaries", "_sounddevice_data",
                "--hidden-import", "sounddevice",
                "--hidden-import", "_sounddevice_data",
            ],
            ["cv2", "PIL", "reportlab", "pypdf", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSvg", "PySide6.QtPrintSupport"],
        ),
        (
            "KinoShop",
            os.path.join(ROOT, "KinoShop", "main.py"),
            os.path.join(ROOT, "KinoShop", "KinoShop.ico"),
            [
                "--add-data", f"{os.path.join(ROOT, 'KinoShop', 'plugins')};plugins",
            ],
            ["pypdf", "sounddevice", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSvg", "PySide6.QtPrintSupport"],
        ),
        (
            "KinoDraw",
            os.path.join(ROOT, "KinoDraw", "main.py"),
            os.path.join(ROOT, "KinoDraw", "KinoDraw.ico"),
            [
                "--hidden-import", "PySide6.QtSvg",
                "--hidden-import", "PySide6.QtPrintSupport",
            ],
            ["pypdf", "sounddevice", "PySide6.QtPdf", "PySide6.QtPdfWidgets"],
        ),
        (
            "KinoFill",
            os.path.join(ROOT, "KinoFill", "main.py"),
            os.path.join(ROOT, "KinoFill", "KinoFill.ico"),
            [
                "--hidden-import", "PySide6.QtPdf",
                "--hidden-import", "PySide6.QtPrintSupport",
            ],
            ["cv2", "numpy", "sounddevice", "PySide6.QtSvg"],
        ),
    ]

    only = set(a.lower() for a in sys.argv[1:])
    for name, entry, ico, args, excl in specs:
        if only and name.lower() not in only:
            continue
        build_one(name, entry, ico, args, excl)

    # Copy already-standalone KinoWave.exe & KinoCut.exe + starter GBA ROM
    for src, dst_name in [
        (os.path.join(ROOT, "KinoWave", "KinoWave.exe"), "KinoWave.exe"),
        (os.path.join(ROOT, "KinoCut.exe"), "KinoCut.exe"),
        (os.path.join(ROOT, "KinoPixel", "examples", "starbit_quest.gba"), "starbit_quest.gba"),
    ]:
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT_DIR, dst_name))
            mb = os.path.getsize(src) / (1024 * 1024)
            print(f"[COPY] {dst_name} ({mb:.2f} MB)")

    # Write SHA256SUMS.txt
    sums_lines = []
    for fn in sorted(os.listdir(OUT_DIR)):
        fp = os.path.join(OUT_DIR, fn)
        if os.path.isfile(fp) and fn != "SHA256SUMS.txt":
            sums_lines.append(f"{sha256_file(fp)}  {fn}")
    with open(os.path.join(OUT_DIR, "SHA256SUMS.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sums_lines) + "\n")

    print("\n=== All Release Assets Ready ===")
    for fn in sorted(os.listdir(OUT_DIR)):
        fp = os.path.join(OUT_DIR, fn)
        print(f"  {fn:24s} {os.path.getsize(fp) / (1024 * 1024):7.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
