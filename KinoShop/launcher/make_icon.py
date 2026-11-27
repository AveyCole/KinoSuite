"""Generate multi-resolution KinoShop.ico ('Ks' KinoSuite electric sapphire badge)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PIL import Image
from PySide6.QtGui import QGuiApplication

from kinoshop.icons import make_app_pixmap


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = []
    for sz in sizes:
        pm = make_app_pixmap(sz)
        qimg = pm.toImage().convertToFormat(pm.toImage().Format.Format_RGBA8888)
        raw = bytes(qimg.constBits())
        imgs.append(Image.frombytes("RGBA", (sz, sz), raw))
    out_ico = os.path.join(ROOT, "KinoShop.ico")
    imgs[-1].save(out_ico, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    print(f"Generated {out_ico}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
