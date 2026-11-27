"""Programmatic crisp vector icons in Adobe Illustrator's dark studio style."""
from __future__ import annotations

import math
from typing import Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

_ICON_CACHE: Dict[str, QIcon] = {}


def make_app_pixmap(size: int = 64) -> QPixmap:
    """KinoSuite 'Kd' badge: Kino slate + Illustrator-amber rounded square with pen accent."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pad = size * 0.06
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    rad = size * 0.22
    p.setBrush(QColor("#1A1310"))
    p.setPen(QPen(QColor("#FF9A00"), max(2.0, size * 0.065)))
    p.drawRoundedRect(rect, rad, rad)
    # Subtle KinoSuite corner accent bar
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#00C2FF"))
    p.drawRoundedRect(QRectF(size * 0.22, size * 0.16, size * 0.56, max(2.0, size * 0.055)), 2, 2)

    f = QFont("Segoe UI", int(size * 0.42), QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("#FF9A00"))
    p.drawText(rect.adjusted(0, size * 0.04, 0, 0), Qt.AlignCenter, "Kd")
    p.end()
    return pm


def get_tool_icon(name: str, active: bool = False, size: int = 24) -> QIcon:
    key = f"{name}_{active}_{size}"
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    fg = QColor("#FF9A00") if active else QColor("#E2E4E9")
    sub = QColor("#FFB74D") if active else QColor("#8F96A3")
    pen = QPen(fg, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    s = float(size)
    if name == "select":
        path = QPainterPath()
        path.moveTo(s * 0.25, s * 0.14)
        path.lineTo(s * 0.25, s * 0.80)
        path.lineTo(s * 0.44, s * 0.62)
        path.lineTo(s * 0.62, s * 0.86)
        path.lineTo(s * 0.72, s * 0.80)
        path.lineTo(s * 0.54, s * 0.57)
        path.lineTo(s * 0.78, s * 0.56)
        path.closeSubpath()
        p.setBrush(fg)
        p.drawPath(path)
    elif name == "direct_select":
        path = QPainterPath()
        path.moveTo(s * 0.25, s * 0.14)
        path.lineTo(s * 0.25, s * 0.80)
        path.lineTo(s * 0.44, s * 0.62)
        path.lineTo(s * 0.78, s * 0.56)
        path.closeSubpath()
        p.setBrush(QColor("#262626"))
        p.drawPath(path)
    elif name == "pen":
        path = QPainterPath()
        path.moveTo(s * 0.5, s * 0.14)
        path.lineTo(s * 0.74, s * 0.52)
        path.lineTo(s * 0.62, s * 0.78)
        path.lineTo(s * 0.38, s * 0.78)
        path.lineTo(s * 0.26, s * 0.52)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.5, s * 0.14), QPointF(s * 0.5, s * 0.48))
        p.setBrush(fg)
        p.drawEllipse(QPointF(s * 0.5, s * 0.52), 2.0, 2.0)
        p.drawRect(QRectF(s * 0.34, s * 0.78, s * 0.32, s * 0.10))
    elif name == "curvature":
        path = QPainterPath()
        path.moveTo(s * 0.18, s * 0.76)
        path.cubicTo(s * 0.25, s * 0.18, s * 0.75, s * 0.18, s * 0.82, s * 0.76)
        p.drawPath(path)
        p.setBrush(QColor("#262626"))
        p.drawEllipse(QPointF(s * 0.5, s * 0.32), 2.6, 2.6)
        p.drawEllipse(QPointF(s * 0.18, s * 0.76), 2.2, 2.2)
        p.drawEllipse(QPointF(s * 0.82, s * 0.76), 2.2, 2.2)
    elif name == "pencil":
        p.drawLine(QPointF(s * 0.24, s * 0.76), QPointF(s * 0.72, s * 0.28))
        p.drawLine(QPointF(s * 0.32, s * 0.82), QPointF(s * 0.78, s * 0.36))
        p.drawLine(QPointF(s * 0.24, s * 0.76), QPointF(s * 0.18, s * 0.86))
        p.drawLine(QPointF(s * 0.32, s * 0.82), QPointF(s * 0.18, s * 0.86))
        p.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.78, s * 0.36))
    elif name == "blob_brush":
        p.setBrush(fg)
        p.drawEllipse(QPointF(s * 0.36, s * 0.68), s * 0.16, s * 0.14)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(s * 0.44, s * 0.58), QPointF(s * 0.78, s * 0.20))
    elif name == "shaper":
        p.drawEllipse(QRectF(s * 0.18, s * 0.22, s * 0.42, s * 0.42))
        p.drawRect(QRectF(s * 0.44, s * 0.44, s * 0.38, s * 0.34))
    elif name == "rect":
        p.drawRect(QRectF(s * 0.18, s * 0.24, s * 0.64, s * 0.52))
    elif name == "ellipse":
        p.drawEllipse(QRectF(s * 0.16, s * 0.24, s * 0.68, s * 0.52))
    elif name == "polygon":
        poly = QPainterPath()
        for i in range(6):
            ang = -math.pi / 2 + i * math.pi / 3
            px = s * 0.5 + s * 0.34 * math.cos(ang)
            py = s * 0.5 + s * 0.34 * math.sin(ang)
            poly.moveTo(px, py) if i == 0 else poly.lineTo(px, py)
        poly.closeSubpath()
        p.drawPath(poly)
    elif name == "star":
        poly = QPainterPath()
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = s * 0.36 if i % 2 == 0 else s * 0.15
            px, py = s * 0.5 + r * math.cos(ang), s * 0.5 + r * math.sin(ang)
            poly.moveTo(px, py) if i == 0 else poly.lineTo(px, py)
        poly.closeSubpath()
        p.drawPath(poly)
    elif name == "line":
        p.drawLine(QPointF(s * 0.18, s * 0.80), QPointF(s * 0.82, s * 0.20))
    elif name == "type":
        f = QFont("Georgia", int(s * 0.62), QFont.Bold)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "T")
    elif name == "touch_type":
        f = QFont("Segoe UI", int(s * 0.52), QFont.Bold)
        p.setFont(f)
        p.setPen(fg)
        p.drawText(QRectF(s * 0.1, s * 0.05, s * 0.6, s * 0.7), Qt.AlignCenter, "T")
        p.setPen(QPen(sub, 1.2, Qt.DashLine))
        p.drawRect(QRectF(s * 0.44, s * 0.42, s * 0.42, s * 0.42))
    elif name == "shape_builder":
        p.drawEllipse(QRectF(s * 0.16, s * 0.28, s * 0.44, s * 0.44))
        p.drawEllipse(QRectF(s * 0.40, s * 0.28, s * 0.44, s * 0.44))
        p.setPen(QPen(QColor("#FF9A00"), 1.8))
        p.drawLine(QPointF(s * 0.50, s * 0.42), QPointF(s * 0.50, s * 0.58))
        p.drawLine(QPointF(s * 0.42, s * 0.50), QPointF(s * 0.58, s * 0.50))
    elif name == "live_paint":
        p.drawRect(QRectF(s * 0.22, s * 0.36, s * 0.36, s * 0.36))
        p.setBrush(fg)
        p.drawEllipse(QPointF(s * 0.72, s * 0.70), 3.0, 4.0)
        p.drawLine(QPointF(s * 0.42, s * 0.36), QPointF(s * 0.68, s * 0.56))
    elif name == "width":
        path = QPainterPath()
        path.moveTo(s * 0.20, s * 0.78)
        path.cubicTo(s * 0.32, s * 0.20, s * 0.68, s * 0.20, s * 0.80, s * 0.78)
        p.drawPath(path)
        p.setPen(QPen(QColor("#FF9A00"), 1.6))
        p.drawLine(QPointF(s * 0.5, s * 0.16), QPointF(s * 0.5, s * 0.56))
        p.setBrush(fg)
        p.drawEllipse(QPointF(s * 0.5, s * 0.16), 2.2, 2.2)
        p.drawEllipse(QPointF(s * 0.5, s * 0.56), 2.2, 2.2)
    elif name == "scissors":
        p.drawEllipse(QRectF(s * 0.18, s * 0.56, s * 0.22, s * 0.22))
        p.drawEllipse(QRectF(s * 0.56, s * 0.56, s * 0.22, s * 0.22))
        p.drawLine(QPointF(s * 0.36, s * 0.62), QPointF(s * 0.74, s * 0.20))
        p.drawLine(QPointF(s * 0.60, s * 0.62), QPointF(s * 0.24, s * 0.20))
    elif name == "knife":
        path = QPainterPath()
        path.moveTo(s * 0.20, s * 0.80)
        path.lineTo(s * 0.76, s * 0.20)
        path.lineTo(s * 0.82, s * 0.34)
        path.lineTo(s * 0.42, s * 0.78)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "rotate":
        p.drawArc(QRectF(s * 0.20, s * 0.20, s * 0.60, s * 0.60), 30 * 16, 280 * 16)
        p.drawLine(QPointF(s * 0.74, s * 0.34), QPointF(s * 0.84, s * 0.20))
        p.drawLine(QPointF(s * 0.74, s * 0.34), QPointF(s * 0.60, s * 0.30))
    elif name == "scale":
        p.drawRect(QRectF(s * 0.18, s * 0.44, s * 0.38, s * 0.38))
        p.setPen(QPen(sub, 1.3, Qt.DashLine))
        p.drawRect(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64))
        p.setPen(pen)
        p.drawLine(QPointF(s * 0.56, s * 0.44), QPointF(s * 0.80, s * 0.20))
    elif name == "puppet_warp":
        p.setBrush(fg)
        p.drawEllipse(QPointF(s * 0.5, s * 0.28), 3.6, 3.6)
        p.drawLine(QPointF(s * 0.5, s * 0.36), QPointF(s * 0.5, s * 0.82))
        p.drawEllipse(QPointF(s * 0.25, s * 0.65), 2.2, 2.2)
        p.drawEllipse(QPointF(s * 0.75, s * 0.65), 2.2, 2.2)
    elif name == "blend":
        p.drawRect(QRectF(s * 0.16, s * 0.18, s * 0.26, s * 0.26))
        p.drawEllipse(QRectF(s * 0.54, s * 0.54, s * 0.28, s * 0.28))
        p.setPen(QPen(sub, 1.2))
        p.drawRoundedRect(QRectF(s * 0.34, s * 0.36, s * 0.28, s * 0.28), 4, 4)
    elif name == "gradient":
        for i in range(6):
            c = int(40 + i * 38)
            p.fillRect(QRectF(s * 0.18 + i * s * 0.105, s * 0.24, s * 0.11, s * 0.52), QColor(c, c, c))
        p.drawRect(QRectF(s * 0.18, s * 0.24, s * 0.64, s * 0.52))
    elif name == "eyedropper":
        p.drawLine(QPointF(s * 0.22, s * 0.78), QPointF(s * 0.66, s * 0.34))
        p.drawLine(QPointF(s * 0.56, s * 0.24), QPointF(s * 0.76, s * 0.44))
        p.setBrush(fg)
        p.drawEllipse(QPointF(s * 0.74, s * 0.26), 3.5, 3.5)
    elif name == "perspective":
        p.drawLine(QPointF(s * 0.14, s * 0.34), QPointF(s * 0.50, s * 0.20))
        p.drawLine(QPointF(s * 0.86, s * 0.34), QPointF(s * 0.50, s * 0.20))
        p.drawLine(QPointF(s * 0.14, s * 0.70), QPointF(s * 0.50, s * 0.84))
        p.drawLine(QPointF(s * 0.86, s * 0.70), QPointF(s * 0.50, s * 0.84))
        p.drawLine(QPointF(s * 0.50, s * 0.20), QPointF(s * 0.50, s * 0.84))
        p.drawLine(QPointF(s * 0.14, s * 0.34), QPointF(s * 0.14, s * 0.70))
        p.drawLine(QPointF(s * 0.86, s * 0.34), QPointF(s * 0.86, s * 0.70))
    elif name == "graph":
        p.setBrush(fg)
        p.drawRect(QRectF(s * 0.18, s * 0.52, s * 0.14, s * 0.30))
        p.drawRect(QRectF(s * 0.42, s * 0.26, s * 0.14, s * 0.56))
        p.drawRect(QRectF(s * 0.66, s * 0.40, s * 0.14, s * 0.42))
    elif name == "artboard":
        p.drawRect(QRectF(s * 0.24, s * 0.24, s * 0.56, s * 0.56))
        p.drawLine(QPointF(s * 0.14, s * 0.24), QPointF(s * 0.22, s * 0.24))
        p.drawLine(QPointF(s * 0.24, s * 0.14), QPointF(s * 0.24, s * 0.22))
    elif name == "symbol_sprayer":
        p.setBrush(fg)
        for px, py in [(0.3, 0.3), (0.65, 0.28), (0.5, 0.52), (0.28, 0.72), (0.72, 0.70)]:
            p.drawEllipse(QPointF(s * px, s * py), 2.2, 2.2)
    elif name == "hand":
        p.drawRoundedRect(QRectF(s * 0.28, s * 0.40, s * 0.44, s * 0.40), 4, 4)
        for dx in (0.34, 0.44, 0.54, 0.64):
            p.drawLine(QPointF(s * dx, s * 0.40), QPointF(s * dx, s * 0.18))
    elif name == "zoom":
        p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.46, s * 0.46))
        p.drawLine(QPointF(s * 0.58, s * 0.58), QPointF(s * 0.84, s * 0.84))
    else:
        p.drawRect(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56))

    p.end()
    icon = QIcon(pm)
    _ICON_CACHE[key] = icon
    return icon
