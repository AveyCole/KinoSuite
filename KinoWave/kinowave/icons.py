"""Programmatic crisp vector icons for KinoWave (KinoSuite style + Audacity workflow)."""
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
    QPolygonF,
)

ACCENT = QColor("#10D9A0")
ACCENT_CYAN = QColor("#22D3EE")
RECORD_RED = QColor("#F43F5E")
AMBER = QColor("#F59E0B")
INK = QColor("#DCE2EE")


def make_app_pixmap(size: int = 64) -> QPixmap:
    """Create the KinoWave 'Kw' KinoSuite badge icon with subtle acoustic waveform."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    pad = size * 0.06
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    rad = size * 0.22

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#081C1B"))
    grad.setColorAt(0.55, QColor("#0D2B2A"))
    grad.setColorAt(1.0, QColor("#071419"))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(ACCENT, max(1.5, size * 0.055)))
    p.drawRoundedRect(rect, rad, rad)

    # Subtle acoustic wave bars in background
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(34, 211, 238, 45))
    bars = [0.18, 0.34, 0.52, 0.28, 0.62, 0.44, 0.24]
    bw = (size * 0.66) / len(bars)
    start_x = size * 0.17
    for idx, bh_ratio in enumerate(bars):
        bh = size * bh_ratio * 0.55
        bx = start_x + idx * bw + bw * 0.18
        p.drawRoundedRect(QRectF(bx, size * 0.5 - bh / 2, bw * 0.64, bh), 2, 2)

    # Subtle top-left gleam
    gleam = QLinearGradient(0, 0, size * 0.55, size * 0.55)
    gleam.setColorAt(0.0, QColor(16, 217, 160, 58))
    gleam.setColorAt(1.0, QColor(16, 217, 160, 0))
    p.setBrush(QBrush(gleam))
    p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), rad * 0.85, rad * 0.85)

    # Kw monogram
    font = QFont("Segoe UI", max(8, int(size * 0.38)), QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 92)
    p.setFont(font)
    p.setPen(ACCENT)
    p.drawText(rect.adjusted(0, -size * 0.02, 0, 0), Qt.AlignmentFlag.AlignCenter, "Kw")
    p.end()
    return pm


def make_icon(name: str, size: int = 22, active: bool = False, color: str | None = None) -> QIcon:
    """Generate crisp vector toolbar icons for transport, editing, tools, zoom, and track actions."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    fg = QColor(color) if color else (ACCENT if active else INK)
    pen = QPen(fg, 1.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    m = s * 0.18

    if name == "play":
        p.setBrush(QBrush(ACCENT if not color else fg))
        p.setPen(Qt.PenStyle.NoPen)
        poly = QPolygonF([QPointF(s * 0.28, s * 0.18), QPointF(s * 0.82, s * 0.5), QPointF(s * 0.28, s * 0.82)])
        p.drawPolygon(poly)

    elif name == "pause":
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(s * 0.24, s * 0.2, s * 0.18, s * 0.6), 1.5, 1.5)
        p.drawRoundedRect(QRectF(s * 0.58, s * 0.2, s * 0.18, s * 0.6), 1.5, 1.5)

    elif name == "stop":
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(s * 0.24, s * 0.24, s * 0.52, s * 0.52), 2.5, 2.5)

    elif name == "record":
        p.setBrush(QBrush(RECORD_RED))
        p.setPen(QPen(QColor("#FDA4AF"), 1.2))
        p.drawEllipse(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56))

    elif name == "skip_start":
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(s * 0.2, s * 0.22, s * 0.11, s * 0.56))
        p.drawPolygon(QPolygonF([QPointF(s * 0.78, s * 0.22), QPointF(s * 0.35, s * 0.5), QPointF(s * 0.78, s * 0.78)]))

    elif name == "skip_end":
        p.setBrush(QBrush(fg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(s * 0.69, s * 0.22, s * 0.11, s * 0.56))
        p.drawPolygon(QPolygonF([QPointF(s * 0.22, s * 0.22), QPointF(s * 0.65, s * 0.5), QPointF(s * 0.22, s * 0.78)]))

    elif name == "loop":
        p.setPen(QPen(AMBER if active else fg, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.moveTo(s * 0.24, s * 0.45)
        path.lineTo(s * 0.24, s * 0.32)
        path.lineTo(s * 0.76, s * 0.32)
        path.moveTo(s * 0.76, s * 0.55)
        path.lineTo(s * 0.76, s * 0.68)
        path.lineTo(s * 0.24, s * 0.68)
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.66, s * 0.22), QPointF(s * 0.78, s * 0.32))
        p.drawLine(QPointF(s * 0.66, s * 0.42), QPointF(s * 0.78, s * 0.32))
        p.drawLine(QPointF(s * 0.34, s * 0.58), QPointF(s * 0.22, s * 0.68))
        p.drawLine(QPointF(s * 0.34, s * 0.78), QPointF(s * 0.22, s * 0.68))

    elif name == "tool_select":
        # Classic Audacity I-beam selection cursor
        p.drawLine(QPointF(s * 0.5, s * 0.18), QPointF(s * 0.5, s * 0.82))
        p.drawLine(QPointF(s * 0.34, s * 0.18), QPointF(s * 0.66, s * 0.18))
        p.drawLine(QPointF(s * 0.34, s * 0.82), QPointF(s * 0.66, s * 0.82))

    elif name == "tool_envelope":
        # Two inward triangles + amplitude curve
        p.setPen(QPen(QColor("#A78BFA") if active else fg, 1.6))
        p.drawLine(QPointF(s * 0.18, s * 0.28), QPointF(s * 0.5, s * 0.42))
        p.drawLine(QPointF(s * 0.5, s * 0.42), QPointF(s * 0.82, s * 0.24))
        p.drawLine(QPointF(s * 0.18, s * 0.72), QPointF(s * 0.5, s * 0.58))
        p.drawLine(QPointF(s * 0.5, s * 0.58), QPointF(s * 0.82, s * 0.76))
        p.setBrush(QBrush(ACCENT))
        p.drawEllipse(QPointF(s * 0.5, s * 0.42), 2.3, 2.3)
        p.drawEllipse(QPointF(s * 0.5, s * 0.58), 2.3, 2.3)

    elif name == "tool_draw":
        # Pencil / sample draw
        p.drawLine(QPointF(s * 0.24, s * 0.78), QPointF(s * 0.72, s * 0.24))
        p.drawLine(QPointF(s * 0.62, s * 0.20), QPointF(s * 0.78, s * 0.34))
        p.drawLine(QPointF(s * 0.24, s * 0.78), QPointF(s * 0.20, s * 0.84))
        p.setBrush(QBrush(ACCENT_CYAN))
        p.drawEllipse(QPointF(s * 0.22, s * 0.80), 2.0, 2.0)

    elif name == "tool_multi":
        # Star / Multi-tool emblem
        cx, cy = s * 0.5, s * 0.5
        for ang in range(0, 360, 60):
            r = math.radians(ang)
            p.drawLine(QPointF(cx, cy), QPointF(cx + math.cos(r) * s * 0.32, cy + math.sin(r) * s * 0.32))
        p.setBrush(QBrush(ACCENT))
        p.drawEllipse(QPointF(cx, cy), 2.6, 2.6)

    elif name == "tool_zoom":
        p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.46, s * 0.46))
        p.drawLine(QPointF(s * 0.58, s * 0.58), QPointF(s * 0.82, s * 0.82))

    elif name == "tool_shift":
        # Horizontal double-headed clip move arrow
        p.drawLine(QPointF(s * 0.2, s * 0.5), QPointF(s * 0.8, s * 0.5))
        p.drawLine(QPointF(s * 0.32, s * 0.36), QPointF(s * 0.2, s * 0.5))
        p.drawLine(QPointF(s * 0.32, s * 0.64), QPointF(s * 0.2, s * 0.5))
        p.drawLine(QPointF(s * 0.68, s * 0.36), QPointF(s * 0.8, s * 0.5))
        p.drawLine(QPointF(s * 0.68, s * 0.64), QPointF(s * 0.8, s * 0.5))

    elif name == "cut":
        p.drawEllipse(QRectF(s * 0.18, s * 0.6, s * 0.22, s * 0.22))
        p.drawEllipse(QRectF(s * 0.58, s * 0.6, s * 0.22, s * 0.22))
        p.drawLine(QPointF(s * 0.35, s * 0.62), QPointF(s * 0.72, s * 0.2))
        p.drawLine(QPointF(s * 0.63, s * 0.62), QPointF(s * 0.28, s * 0.2))

    elif name == "copy":
        p.drawRoundedRect(QRectF(s * 0.34, s * 0.18, s * 0.46, s * 0.52), 2, 2)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.32, s * 0.46, s * 0.52), 2, 2)

    elif name == "paste":
        p.drawRoundedRect(QRectF(s * 0.24, s * 0.26, s * 0.52, s * 0.58), 2, 2)
        p.drawRoundedRect(QRectF(s * 0.36, s * 0.16, s * 0.28, s * 0.14), 2, 2)

    elif name == "trim":
        p.drawLine(QPointF(s * 0.28, s * 0.2), QPointF(s * 0.28, s * 0.8))
        p.drawLine(QPointF(s * 0.72, s * 0.2), QPointF(s * 0.72, s * 0.8))
        p.setPen(QPen(ACCENT, 2.0))
        p.drawLine(QPointF(s * 0.36, s * 0.5), QPointF(s * 0.64, s * 0.5))
        p.drawLine(QPointF(s * 0.44, s * 0.34), QPointF(s * 0.44, s * 0.66))
        p.drawLine(QPointF(s * 0.56, s * 0.34), QPointF(s * 0.56, s * 0.66))

    elif name == "silence":
        p.drawLine(QPointF(s * 0.18, s * 0.5), QPointF(s * 0.34, s * 0.5))
        p.drawLine(QPointF(s * 0.26, s * 0.3), QPointF(s * 0.26, s * 0.7))
        p.drawLine(QPointF(s * 0.66, s * 0.5), QPointF(s * 0.82, s * 0.5))
        p.drawLine(QPointF(s * 0.74, s * 0.3), QPointF(s * 0.74, s * 0.7))
        p.setPen(QPen(ACCENT_CYAN, 1.5, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(s * 0.36, s * 0.5), QPointF(s * 0.64, s * 0.5))

    elif name == "undo":
        p.drawArc(QRectF(s * 0.24, s * 0.3, s * 0.54, s * 0.5), 0, 180 * 16)
        p.drawLine(QPointF(s * 0.24, s * 0.54), QPointF(s * 0.16, s * 0.4))
        p.drawLine(QPointF(s * 0.24, s * 0.54), QPointF(s * 0.38, s * 0.48))

    elif name == "redo":
        p.drawArc(QRectF(s * 0.22, s * 0.3, s * 0.54, s * 0.5), 0, 180 * 16)
        p.drawLine(QPointF(s * 0.76, s * 0.54), QPointF(s * 0.84, s * 0.4))
        p.drawLine(QPointF(s * 0.76, s * 0.54), QPointF(s * 0.62, s * 0.48))

    elif name == "zoom_in":
        p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.46, s * 0.46))
        p.drawLine(QPointF(s * 0.58, s * 0.58), QPointF(s * 0.82, s * 0.82))
        p.drawLine(QPointF(s * 0.41, s * 0.29), QPointF(s * 0.41, s * 0.53))
        p.drawLine(QPointF(s * 0.29, s * 0.41), QPointF(s * 0.53, s * 0.41))

    elif name == "zoom_out":
        p.drawEllipse(QRectF(s * 0.18, s * 0.18, s * 0.46, s * 0.46))
        p.drawLine(QPointF(s * 0.58, s * 0.58), QPointF(s * 0.82, s * 0.82))
        p.drawLine(QPointF(s * 0.29, s * 0.41), QPointF(s * 0.53, s * 0.41))

    elif name == "fit_sel":
        p.drawLine(QPointF(s * 0.18, s * 0.24), QPointF(s * 0.18, s * 0.76))
        p.drawLine(QPointF(s * 0.82, s * 0.24), QPointF(s * 0.82, s * 0.76))
        p.drawLine(QPointF(s * 0.26, s * 0.5), QPointF(s * 0.74, s * 0.5))
        p.drawLine(QPointF(s * 0.35, s * 0.38), QPointF(s * 0.26, s * 0.5))
        p.drawLine(QPointF(s * 0.35, s * 0.62), QPointF(s * 0.26, s * 0.5))
        p.drawLine(QPointF(s * 0.65, s * 0.38), QPointF(s * 0.74, s * 0.5))
        p.drawLine(QPointF(s * 0.65, s * 0.62), QPointF(s * 0.74, s * 0.5))

    elif name == "fit_proj":
        p.drawRect(QRectF(s * 0.18, s * 0.24, s * 0.64, s * 0.52))
        p.setPen(QPen(ACCENT, 1.5))
        p.drawLine(QPointF(s * 0.26, s * 0.5), QPointF(s * 0.74, s * 0.5))

    elif name == "sync_lock":
        # Clock / chain lock icon
        p.drawEllipse(QRectF(s * 0.2, s * 0.2, s * 0.6, s * 0.6))
        p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.5, s * 0.3))
        p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.66, s * 0.56))

    elif name == "fx":
        font = QFont("Segoe UI", max(7, int(s * 0.42)), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "FX")

    elif name == "cloud":
        p.drawRoundedRect(QRectF(s * 0.18, s * 0.46, s * 0.64, s * 0.28), 6, 6)
        p.drawArc(QRectF(s * 0.28, s * 0.26, s * 0.38, s * 0.36), 0, 180 * 16)

    elif name == "split":
        p.drawLine(QPointF(s * 0.5, s * 0.16), QPointF(s * 0.5, s * 0.84))
        p.drawRect(QRectF(s * 0.18, s * 0.34, s * 0.22, s * 0.32))
        p.drawRect(QRectF(s * 0.6, s * 0.34, s * 0.22, s * 0.32))

    elif name == "scrub":
        p.drawLine(QPointF(s * 0.18, s * 0.5), QPointF(s * 0.82, s * 0.5))
        p.setBrush(QBrush(ACCENT_CYAN))
        p.drawPolygon(QPolygonF([QPointF(s * 0.5, s * 0.22), QPointF(s * 0.64, s * 0.5), QPointF(s * 0.5, s * 0.78), QPointF(s * 0.36, s * 0.5)]))

    elif name == "spectral":
        # Vertical frequency bars
        cols = [QColor("#6366F1"), QColor("#22D3EE"), ACCENT, AMBER]
        for i, c in enumerate(cols):
            p.setPen(QPen(c, 2.2))
            x = s * (0.24 + i * 0.17)
            h = s * (0.35 + (i % 2) * 0.25)
            p.drawLine(QPointF(x, s * 0.8), QPointF(x, s * 0.8 - h))

    else:
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))

    p.end()
    return QIcon(pm)
