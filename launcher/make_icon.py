"""Generate multi-resolution KinoSuite.ico from the KS architectural badge."""
from __future__ import annotations

import io
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from kinosuite.icons import make_suite_pixmap


def main() -> None:
    app = QApplication.instance() or QApplication([])
    imgs = []
    for sz in (256, 128, 64, 48, 32, 16):
        pm = make_suite_pixmap(sz)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        imgs.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
    out = os.path.join(ROOT, "KinoSuite.ico")
    imgs[0].save(out, format="ICO", sizes=[(im.width, im.height) for im in imgs])
    print(f"Generated: {out}")


if __name__ == "__main__":
    main()
