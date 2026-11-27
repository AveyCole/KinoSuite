"""Programmatic crisp vector icons for KinoPixel (KinoSuite style)."""
from __future__ import annotations

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
    QPolygonF,
)

ACCENT = QColor("#8B5CF6")
ACCENT_BRIGHT = QColor("#A78BFA")
MINT = QColor("#34D399")
GOLD = QColor("#F59E0B")
CRIMSON = QColor("#F43F5E")
INK = QColor("#DCE2EE")


def make_app_pixmap(size: int = 64) -> QPixmap:
    """Create the KinoPixel 'Kp' KinoSuite badge icon with subtle pixel-grid & D-pad motif."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    pad = size * 0.06
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    rad = size * 0.22

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#140D28"))
    grad.setColorAt(0.55, QColor("#221647"))
    grad.setColorAt(1.0, QColor("#0E0C1E"))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(ACCENT_BRIGHT, max(1.5, size * 0.055)))
    p.drawRoundedRect(rect, rad, rad)

    # Shared KinoSuite cyan top bar (matching Kc, Ks, Kd, Kw, Kf)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#00C2FF"))
    p.drawRoundedRect(QRectF(size * 0.22, size * 0.16, size * 0.56, max(2.0, size * 0.05)), 2, 2)

    # Subtle pixel-art blocks in background (echoing KinoWave's subtle wave bars)
    cell = size * 0.11
    pixels = [
        (0.16, 0.28, QColor(167, 139, 250, 42)),
        (0.73, 0.28, QColor(245, 158, 11, 44)),
        (0.16, 0.72, QColor(52, 211, 153, 40)),
        (0.73, 0.72, QColor(139, 92, 246, 52)),
        (0.60, 0.72, QColor(167, 139, 250, 34)),
    ]
    for rx, ry, col in pixels:
        p.setBrush(col)
        p.drawRoundedRect(QRectF(size * rx, size * ry, cell, cell), max(1.0, size * 0.02), max(1.0, size * 0.02))

    # Subtle top-left KinoSuite gleam
    gleam = QLinearGradient(0, 0, size * 0.55, size * 0.55)
    gleam.setColorAt(0.0, QColor(167, 139, 250, 58))
    gleam.setColorAt(1.0, QColor(167, 139, 250, 0))
    p.setBrush(QBrush(gleam))
    p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), rad * 0.85, rad * 0.85)

    # Crisp Kp monogram
    font = QFont("Segoe UI", max(8, int(size * 0.38)), QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 92)
    p.setFont(font)
    p.setPen(ACCENT_BRIGHT)
    p.drawText(rect.adjusted(0, size * 0.06, 0, 0), Qt.AlignmentFlag.AlignCenter, "Kp")
    p.end()
    return pm


def make_icon(name: str, size: int = 22, active: bool = False, color: str | None = None) -> QIcon:
    """Generate crisp vector icons for pixel tools, level editing, wiring, audio, and ROM building."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    fg = QColor(color) if color else (ACCENT_BRIGHT if active else INK)
    pen = QPen(fg, 1.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    m = s * 0.18

    if name == "pencil":
        p.drawLine(QPointF(s * 0.24, s * 0.78), QPointF(s * 0.74, s * 0.24))
        p.drawLine(QPointF(s * 0.62, s * 0.18), QPointF(s * 0.80, s * 0.36))
        p.drawLine(QPointF(s * 0.24, s * 0.78), QPointF(s * 0.18, s * 0.84))
        p.setBrush(QBrush(MINT if active else ACCENT_BRIGHT))
        p.drawEllipse(QPointF(s * 0.20, s * 0.82), 1.8, 1.8)

    elif name == "eraser":
        poly = QPolygonF([
            QPointF(s * 0.36, s * 0.78),
            QPointF(s * 0.78, s * 0.36),
            QPointF(s * 0.60, s * 0.18),
            QPointF(s * 0.18, s * 0.60),
        ])
        p.drawPolygon(poly)
        p.drawLine(QPointF(s * 0.34, s * 0.44), QPointF(s * 0.52, s * 0.62))
        p.drawLine(QPointF(s * 0.36, s * 0.78), QPointF(s * 0.80, s * 0.78))

    elif name == "fill":
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.24, s * 0.48),
            QPointF(s * 0.54, s * 0.20),
            QPointF(s * 0.78, s * 0.44),
            QPointF(s * 0.48, s * 0.74),
        ]))
        p.setBrush(QBrush(ACCENT_BRIGHT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(s * 0.68, s * 0.62, s * 0.18, s * 0.24))

    elif name == "eyedropper":
        p.drawLine(QPointF(s * 0.22, s * 0.78), QPointF(s * 0.66, s * 0.34))
        p.drawEllipse(QRectF(s * 0.60, s * 0.18, s * 0.22, s * 0.22))
        p.drawLine(QPointF(s * 0.50, s * 0.28), QPointF(s * 0.72, s * 0.50))

    elif name == "line":
        p.drawLine(QPointF(s * 0.20, s * 0.80), QPointF(s * 0.80, s * 0.20))
        p.setBrush(QBrush(ACCENT_BRIGHT))
        p.drawEllipse(QPointF(s * 0.20, s * 0.80), 2.0, 2.0)
        p.drawEllipse(QPointF(s * 0.80, s * 0.20), 2.0, 2.0)

    elif name == "rect":
        p.drawRoundedRect(QRectF(s * 0.20, s * 0.24, s * 0.60, s * 0.52), 1.5, 1.5)

    elif name == "mirror":
        p.setPen(QPen(ACCENT_BRIGHT if active else fg, 1.6, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(s * 0.50, s * 0.16), QPointF(s * 0.50, s * 0.84))
        p.setPen(pen)
        p.drawPolygon(QPolygonF([QPointF(s * 0.20, s * 0.30), QPointF(s * 0.42, s * 0.50), QPointF(s * 0.20, s * 0.70)]))
        p.drawPolygon(QPolygonF([QPointF(s * 0.80, s * 0.30), QPointF(s * 0.58, s * 0.50), QPointF(s * 0.80, s * 0.70)]))

    elif name == "onion":
        p.setPen(QPen(QColor(167, 139, 250, 110), 1.6))
        p.drawEllipse(QRectF(s * 0.16, s * 0.24, s * 0.46, s * 0.46))
        p.setPen(QPen(MINT if active else fg, 1.8))
        p.drawEllipse(QRectF(s * 0.38, s * 0.28, s * 0.46, s * 0.46))

    elif name == "grid":
        for i in (0.22, 0.50, 0.78):
            p.drawLine(QPointF(s * i, s * 0.18), QPointF(s * i, s * 0.82))
            p.drawLine(QPointF(s * 0.18, s * i), QPointF(s * 0.82, s * i))

    elif name == "flip_h":
        p.drawLine(QPointF(s * 0.18, s * 0.50), QPointF(s * 0.82, s * 0.50))
        p.drawLine(QPointF(s * 0.30, s * 0.34), QPointF(s * 0.18, s * 0.50))
        p.drawLine(QPointF(s * 0.30, s * 0.66), QPointF(s * 0.18, s * 0.50))
        p.drawLine(QPointF(s * 0.70, s * 0.34), QPointF(s * 0.82, s * 0.50))
        p.drawLine(QPointF(s * 0.70, s * 0.66), QPointF(s * 0.82, s * 0.50))

    elif name == "flip_v":
        p.drawLine(QPointF(s * 0.50, s * 0.18), QPointF(s * 0.50, s * 0.82))
        p.drawLine(QPointF(s * 0.34, s * 0.30), QPointF(s * 0.50, s * 0.18))
        p.drawLine(QPointF(s * 0.66, s * 0.30), QPointF(s * 0.50, s * 0.18))
        p.drawLine(QPointF(s * 0.34, s * 0.70), QPointF(s * 0.50, s * 0.82))
        p.drawLine(QPointF(s * 0.66, s * 0.70), QPointF(s * 0.50, s * 0.82))

    elif name == "rotate":
        p.drawArc(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56), 30 * 16, 260 * 16)
        p.drawLine(QPointF(s * 0.72, s * 0.36), QPointF(s * 0.82, s * 0.24))
        p.drawLine(QPointF(s * 0.72, s * 0.36), QPointF(s * 0.60, s * 0.28))

    elif name == "play":
        p.setBrush(QBrush(MINT if not color else fg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(s * 0.28, s * 0.18), QPointF(s * 0.82, s * 0.50), QPointF(s * 0.28, s * 0.82)]))

    elif name == "pause":
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(s * 0.24, s * 0.20, s * 0.18, s * 0.60), 1.5, 1.5)
        p.drawRoundedRect(QRectF(s * 0.58, s * 0.20, s * 0.18, s * 0.60), 1.5, 1.5)

    elif name == "stop":
        p.setBrush(QBrush(CRIMSON if active else fg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(s * 0.24, s * 0.24, s * 0.52, s * 0.52), 2.5, 2.5)

    elif name == "undo":
        p.drawArc(QRectF(s * 0.24, s * 0.30, s * 0.54, s * 0.50), 0, 180 * 16)
        p.drawLine(QPointF(s * 0.24, s * 0.54), QPointF(s * 0.16, s * 0.40))
        p.drawLine(QPointF(s * 0.24, s * 0.54), QPointF(s * 0.38, s * 0.48))

    elif name == "redo":
        p.drawArc(QRectF(s * 0.22, s * 0.30, s * 0.54, s * 0.50), 0, 180 * 16)
        p.drawLine(QPointF(s * 0.76, s * 0.54), QPointF(s * 0.84, s * 0.40))
        p.drawLine(QPointF(s * 0.76, s * 0.54), QPointF(s * 0.62, s * 0.48))

    elif name == "sprite":
        p.drawRoundedRect(QRectF(s * 0.22, s * 0.18, s * 0.56, s * 0.42), 3, 3)
        p.setBrush(QBrush(ACCENT_BRIGHT))
        p.drawRect(QRectF(s * 0.32, s * 0.30, s * 0.10, s * 0.10))
        p.drawRect(QRectF(s * 0.58, s * 0.30, s * 0.10, s * 0.10))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(s * 0.36, s * 0.60), QPointF(s * 0.30, s * 0.82))
        p.drawLine(QPointF(s * 0.64, s * 0.60), QPointF(s * 0.70, s * 0.82))

    elif name == "map":
        p.drawRect(QRectF(s * 0.18, s * 0.20, s * 0.64, s * 0.60))
        p.drawLine(QPointF(s * 0.18, s * 0.50), QPointF(s * 0.82, s * 0.50))
        p.drawLine(QPointF(s * 0.50, s * 0.20), QPointF(s * 0.50, s * 0.80))
        p.setBrush(QBrush(MINT))
        p.drawRect(QRectF(s * 0.24, s * 0.56, s * 0.20, s * 0.18))

    elif name == "gamepad":
        p.drawRoundedRect(QRectF(s * 0.14, s * 0.26, s * 0.72, s * 0.48), 6, 6)
        p.drawLine(QPointF(s * 0.32, s * 0.40), QPointF(s * 0.32, s * 0.60))
        p.drawLine(QPointF(s * 0.22, s * 0.50), QPointF(s * 0.42, s * 0.50))
        p.setBrush(QBrush(ACCENT_BRIGHT))
        p.drawEllipse(QPointF(s * 0.66, s * 0.56), 2.3, 2.3)
        p.setBrush(QBrush(MINT))
        p.drawEllipse(QPointF(s * 0.76, s * 0.44), 2.3, 2.3)

    elif name == "sfx":
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.18, s * 0.40),
            QPointF(s * 0.34, s * 0.40),
            QPointF(s * 0.52, s * 0.22),
            QPointF(s * 0.52, s * 0.78),
            QPointF(s * 0.34, s * 0.60),
            QPointF(s * 0.18, s * 0.60),
        ]))
        p.drawArc(QRectF(s * 0.52, s * 0.32, s * 0.20, s * 0.36), -60 * 16, 120 * 16)
        p.drawArc(QRectF(s * 0.58, s * 0.22, s * 0.28, s * 0.56), -60 * 16, 120 * 16)

    elif name == "cartridge":
        path = QPainterPath()
        path.moveTo(s * 0.20, s * 0.18)
        path.lineTo(s * 0.72, s * 0.18)
        path.lineTo(s * 0.82, s * 0.28)
        path.lineTo(s * 0.82, s * 0.82)
        path.lineTo(s * 0.20, s * 0.82)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(QBrush(GOLD))
        p.drawRect(QRectF(s * 0.30, s * 0.34, s * 0.40, s * 0.26))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(s * 0.34, s * 0.72), QPointF(s * 0.66, s * 0.72))

    elif name == "save":
        p.drawRoundedRect(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64), 2, 2)
        p.drawRect(QRectF(s * 0.30, s * 0.18, s * 0.36, s * 0.24))
        p.drawRect(QRectF(s * 0.28, s * 0.54, s * 0.44, s * 0.28))

    elif name == "open":
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.16, s * 0.26),
            QPointF(s * 0.42, s * 0.26),
            QPointF(s * 0.50, s * 0.36),
            QPointF(s * 0.84, s * 0.36),
            QPointF(s * 0.84, s * 0.78),
            QPointF(s * 0.16, s * 0.78),
        ]))

    elif name == "new":
        p.drawRect(QRectF(s * 0.24, s * 0.16, s * 0.52, s * 0.68))
        p.drawLine(QPointF(s * 0.50, s * 0.38), QPointF(s * 0.50, s * 0.62))
        p.drawLine(QPointF(s * 0.38, s * 0.50), QPointF(s * 0.62, s * 0.50))

    else:
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))

    p.end()
    return QIcon(pm)
