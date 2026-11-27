"""Programmatic crisp vector icons for KinoShop (KinoSuite style)."""
from __future__ import annotations

import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

ACCENT = QColor("#31A8FF")
ACCENT_CYAN = QColor("#00D4FF")
INK = QColor("#DCE2EE")
MUTED = QColor("#8D99AE")


def make_app_pixmap(size: int = 64) -> QPixmap:
    """Create the KinoShop 'Ks' KinoSuite badge icon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    pad = size * 0.06
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    rad = size * 0.22

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#0B1A2E"))
    grad.setColorAt(0.6, QColor("#0F2440"))
    grad.setColorAt(1.0, QColor("#091322"))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor("#31A8FF"), max(1.5, size * 0.055)))
    p.drawRoundedRect(rect, rad, rad)

    # Subtle cyan corner gleam
    gleam = QLinearGradient(0, 0, size * 0.55, size * 0.55)
    gleam.setColorAt(0.0, QColor(49, 168, 255, 55))
    gleam.setColorAt(1.0, QColor(49, 168, 255, 0))
    p.setBrush(QBrush(gleam))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), rad * 0.85, rad * 0.85)

    # Ks monogram
    font = QFont("Segoe UI", int(size * 0.42), QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 94)
    p.setFont(font)
    p.setPen(QColor("#31A8FF"))
    p.drawText(rect.adjusted(0, -size * 0.02, 0, 0), Qt.AlignmentFlag.AlignCenter, "Ks")
    p.end()
    return pm


def make_tool_icon(name: str, size: int = 24, active: bool = False) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    fg = ACCENT if active else INK
    pen = QPen(fg, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    m = s * 0.16

    if name == "move":
        # Four-way move arrow
        cx, cy = s / 2, s / 2
        r = s * 0.34
        p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            tx, ty = cx + dx * r, cy + dy * r
            if dx:
                p.drawLine(QPointF(tx, ty), QPointF(tx - dx * 3.5, ty - 3))
                p.drawLine(QPointF(tx, ty), QPointF(tx - dx * 3.5, ty + 3))
            else:
                p.drawLine(QPointF(tx, ty), QPointF(tx - 3, ty - dy * 3.5))
                p.drawLine(QPointF(tx, ty), QPointF(tx + 3, ty - dy * 3.5))

    elif name == "marquee_rect":
        dash = QPen(fg, 1.5, Qt.PenStyle.DashLine)
        p.setPen(dash)
        p.drawRect(QRectF(m, m + 1.5, s - 2 * m, s - 2 * m - 3))

    elif name == "marquee_ellipse":
        dash = QPen(fg, 1.5, Qt.PenStyle.DashLine)
        p.setPen(dash)
        p.drawEllipse(QRectF(m, m + 1.5, s - 2 * m, s - 2 * m - 3))

    elif name == "lasso":
        path = QPainterPath()
        path.moveTo(s * 0.3, s * 0.72)
        path.cubicTo(s * 0.12, s * 0.45, s * 0.28, s * 0.15, s * 0.62, s * 0.22)
        path.cubicTo(s * 0.88, s * 0.28, s * 0.86, s * 0.68, s * 0.52, s * 0.72)
        path.cubicTo(s * 0.38, s * 0.74, s * 0.32, s * 0.82, s * 0.24, s * 0.88)
        p.drawPath(path)

    elif name == "poly_lasso":
        pts = [QPointF(s * 0.2, s * 0.78), QPointF(s * 0.26, s * 0.24), QPointF(s * 0.78, s * 0.28),
               QPointF(s * 0.82, s * 0.72), QPointF(s * 0.46, s * 0.64), QPointF(s * 0.2, s * 0.78)]
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])

    elif name == "quick_select":
        p.drawLine(QPointF(s * 0.2, s * 0.82), QPointF(s * 0.56, s * 0.46))
        p.setPen(QPen(ACCENT_CYAN, 1.6))
        p.drawEllipse(QRectF(s * 0.46, s * 0.16, s * 0.38, s * 0.38))
        p.drawLine(QPointF(s * 0.65, s * 0.25), QPointF(s * 0.65, s * 0.45))
        p.drawLine(QPointF(s * 0.55, s * 0.35), QPointF(s * 0.75, s * 0.35))

    elif name == "magic_wand":
        p.drawLine(QPointF(s * 0.2, s * 0.82), QPointF(s * 0.68, s * 0.34))
        p.setPen(QPen(ACCENT_CYAN, 1.5))
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            p.drawLine(
                QPointF(s * 0.72 + math.cos(rad) * 2.5, s * 0.30 + math.sin(rad) * 2.5),
                QPointF(s * 0.72 + math.cos(rad) * 5.2, s * 0.30 + math.sin(rad) * 5.2),
            )

    elif name == "crop":
        p.drawLine(QPointF(s * 0.28, s * 0.16), QPointF(s * 0.28, s * 0.72))
        p.drawLine(QPointF(s * 0.28, s * 0.72), QPointF(s * 0.84, s * 0.72))
        p.drawLine(QPointF(s * 0.16, s * 0.28), QPointF(s * 0.72, s * 0.28))
        p.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.72, s * 0.84))

    elif name == "slice":
        # Knife / slice grid
        p.drawLine(QPointF(s * 0.22, s * 0.82), QPointF(s * 0.78, s * 0.2))
        p.drawLine(QPointF(s * 0.52, s * 0.5), QPointF(s * 0.82, s * 0.5))
        p.setPen(QPen(ACCENT_CYAN, 1.3, Qt.PenStyle.DashLine))
        p.drawRect(QRectF(s * 0.2, s * 0.2, s * 0.6, s * 0.6))

    elif name == "eyedropper":
        p.drawLine(QPointF(s * 0.22, s * 0.78), QPointF(s * 0.62, s * 0.38))
        p.drawLine(QPointF(s * 0.52, s * 0.28), QPointF(s * 0.72, s * 0.48))
        p.setBrush(QBrush(fg))
        p.drawEllipse(QPointF(s * 0.72, s * 0.28), 3.0, 3.0)

    elif name == "spot_heal":
        # Bandage icon
        p.save()
        p.translate(s / 2, s / 2)
        p.rotate(-45)
        p.drawRoundedRect(QRectF(-8, -3.6, 16, 7.2), 3.5, 3.5)
        p.drawPoint(QPointF(-2, -1))
        p.drawPoint(QPointF(2, 1))
        p.drawPoint(QPointF(-2, 1))
        p.drawPoint(QPointF(2, -1))
        p.restore()

    elif name == "remove":
        # Sparkle eraser / AI remove
        p.setPen(QPen(ACCENT_CYAN, 1.6))
        p.drawEllipse(QRectF(s * 0.24, s * 0.26, s * 0.52, s * 0.52))
        p.drawLine(QPointF(s * 0.36, s * 0.38), QPointF(s * 0.64, s * 0.66))
        p.drawLine(QPointF(s * 0.64, s * 0.38), QPointF(s * 0.36, s * 0.66))

    elif name == "clone":
        # Rubber stamp
        p.drawLine(QPointF(s * 0.22, s * 0.8), QPointF(s * 0.78, s * 0.8))
        p.drawRoundedRect(QRectF(s * 0.26, s * 0.58, s * 0.48, s * 0.16), 2, 2)
        p.drawEllipse(QRectF(s * 0.38, s * 0.2, s * 0.24, s * 0.24))
        p.drawLine(QPointF(s * 0.5, s * 0.44), QPointF(s * 0.5, s * 0.58))

    elif name == "brush":
        path = QPainterPath()
        path.moveTo(s * 0.78, s * 0.2)
        path.lineTo(s * 0.44, s * 0.56)
        p.drawPath(path)
        tip = QPainterPath()
        tip.moveTo(s * 0.44, s * 0.56)
        tip.cubicTo(s * 0.26, s * 0.58, s * 0.22, s * 0.76, s * 0.2, s * 0.82)
        tip.cubicTo(s * 0.38, s * 0.82, s * 0.5, s * 0.72, s * 0.48, s * 0.6)
        p.setBrush(QBrush(fg))
        p.drawPath(tip)

    elif name == "mixer_brush":
        p.drawLine(QPointF(s * 0.76, s * 0.22), QPointF(s * 0.42, s * 0.56))
        p.setBrush(QBrush(ACCENT_CYAN))
        p.drawEllipse(QPointF(s * 0.32, s * 0.72), 4.0, 4.0)
        p.setPen(QPen(ACCENT, 1.4))
        p.drawArc(QRectF(s * 0.18, s * 0.18, s * 0.35, s * 0.35), 30 * 16, 200 * 16)

    elif name == "history_brush":
        p.drawArc(QRectF(s * 0.2, s * 0.2, s * 0.58, s * 0.58), 40 * 16, 250 * 16)
        p.drawLine(QPointF(s * 0.26, s * 0.22), QPointF(s * 0.26, s * 0.38))
        p.drawLine(QPointF(s * 0.26, s * 0.38), QPointF(s * 0.42, s * 0.34))
        p.setBrush(QBrush(ACCENT))
        p.drawEllipse(QPointF(s * 0.66, s * 0.72), 3.0, 3.0)

    elif name == "eraser":
        p.save()
        p.translate(s / 2, s / 2)
        p.rotate(-35)
        p.drawRoundedRect(QRectF(-7.5, -4, 15, 8), 2, 2)
        p.drawLine(QPointF(0, -4), QPointF(0, 4))
        p.restore()

    elif name == "gradient":
        grad = QLinearGradient(m, m, s - m, s - m)
        grad.setColorAt(0.0, ACCENT)
        grad.setColorAt(1.0, QColor("#182030"))
        p.setBrush(QBrush(grad))
        p.drawRect(QRectF(m, m, s - 2 * m, s - 2 * m))

    elif name == "bucket":
        p.drawPolygon([QPointF(s * 0.24, s * 0.52), QPointF(s * 0.52, s * 0.24),
                       QPointF(s * 0.78, s * 0.5), QPointF(s * 0.5, s * 0.78)])
        p.setBrush(QBrush(ACCENT_CYAN))
        p.drawEllipse(QPointF(s * 0.76, s * 0.74), 2.6, 3.4)

    elif name == "dodge_burn":
        p.drawEllipse(QRectF(s * 0.26, s * 0.2, s * 0.36, s * 0.36))
        p.drawLine(QPointF(s * 0.56, s * 0.5), QPointF(s * 0.78, s * 0.8))

    elif name == "blur_smudge":
        path = QPainterPath()
        path.moveTo(s * 0.5, s * 0.18)
        path.cubicTo(s * 0.78, s * 0.54, s * 0.74, s * 0.82, s * 0.5, s * 0.82)
        path.cubicTo(s * 0.26, s * 0.82, s * 0.22, s * 0.54, s * 0.5, s * 0.18)
        p.drawPath(path)

    elif name == "pen":
        path = QPainterPath()
        path.moveTo(s * 0.5, s * 0.16)
        path.lineTo(s * 0.74, s * 0.56)
        path.lineTo(s * 0.6, s * 0.8)
        path.lineTo(s * 0.4, s * 0.8)
        path.lineTo(s * 0.26, s * 0.56)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.5, s * 0.16), QPointF(s * 0.5, s * 0.52))
        p.drawEllipse(QPointF(s * 0.5, s * 0.54), 1.8, 1.8)

    elif name == "text":
        f = QFont("Georgia", int(s * 0.58), QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "T")

    elif name == "shape":
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.24, s * 0.48, s * 0.44), 3, 3)
        p.setPen(QPen(ACCENT_CYAN, 1.5))
        p.drawEllipse(QRectF(s * 0.42, s * 0.4, s * 0.4, s * 0.4))

    elif name == "puppet_warp":
        # Pin icon
        p.setPen(QPen(ACCENT_CYAN, 1.7))
        p.drawEllipse(QPointF(s * 0.5, s * 0.34), 4.0, 4.0)
        p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.5, s * 0.84))

    elif name == "perspective_warp":
        pts = [QPointF(s * 0.2, s * 0.32), QPointF(s * 0.8, s * 0.18),
               QPointF(s * 0.84, s * 0.78), QPointF(s * 0.18, s * 0.72), QPointF(s * 0.2, s * 0.32)]
        for i in range(4):
            p.drawLine(pts[i], pts[i + 1])
        p.drawLine(QPointF(s * 0.5, s * 0.25), QPointF(s * 0.51, s * 0.75))

    elif name == "ruler_count":
        p.drawLine(QPointF(s * 0.18, s * 0.76), QPointF(s * 0.82, s * 0.24))
        p.drawLine(QPointF(s * 0.34, s * 0.63), QPointF(s * 0.4, s * 0.7))
        p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.56, s * 0.57))
        p.drawLine(QPointF(s * 0.66, s * 0.37), QPointF(s * 0.72, s * 0.44))

    elif name == "artboard":
        p.drawRect(QRectF(s * 0.26, s * 0.26, s * 0.48, s * 0.48))
        p.drawLine(QPointF(s * 0.26, s * 0.14), QPointF(s * 0.26, s * 0.22))
        p.drawLine(QPointF(s * 0.14, s * 0.26), QPointF(s * 0.22, s * 0.26))
        p.drawLine(QPointF(s * 0.74, s * 0.78), QPointF(s * 0.74, s * 0.86))
        p.drawLine(QPointF(s * 0.78, s * 0.74), QPointF(s * 0.86, s * 0.74))

    elif name == "hand":
        p.drawRoundedRect(QRectF(s * 0.3, s * 0.44, s * 0.42, s * 0.38), 5, 5)
        for x in (0.34, 0.46, 0.58, 0.68):
            p.drawLine(QPointF(s * x, s * 0.24), QPointF(s * x, s * 0.46))

    elif name == "zoom":
        p.drawEllipse(QRectF(s * 0.2, s * 0.2, s * 0.44, s * 0.44))
        p.drawLine(QPointF(s * 0.58, s * 0.58), QPointF(s * 0.82, s * 0.82))

    elif name == "comment":
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.22, s * 0.6, s * 0.44), 4, 4)
        p.drawLine(QPointF(s * 0.34, s * 0.66), QPointF(s * 0.28, s * 0.82))
        p.drawLine(QPointF(s * 0.28, s * 0.82), QPointF(s * 0.48, s * 0.66))

    else:
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))

    p.end()
    return QIcon(pm)
