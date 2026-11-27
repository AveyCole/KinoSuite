"""Programmatic crisp KinoSuite master badge ('KS') and authentic sibling app badges
(KinoCut Kc, KinoShop Ks, KinoDraw Kd, KinoWave Kw, KinoFill Kf, KinoPixel Kp)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)


def make_suite_pixmap(size: int = 64) -> QPixmap:
    """Create the master KinoSuite 'KS' multi-spectrum architectural badge."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    pad = size * 0.06
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    rad = size * 0.22

    bg = QLinearGradient(0, 0, size, size)
    bg.setColorAt(0.0, QColor("#0B1624"))
    bg.setColorAt(0.55, QColor("#121D2E"))
    bg.setColorAt(1.0, QColor("#09111A"))

    border_grad = QLinearGradient(0, 0, size, size)
    border_grad.setColorAt(0.0, QColor("#00C2FF"))
    border_grad.setColorAt(0.25, QColor("#10D9A0"))
    border_grad.setColorAt(0.50, QColor("#8B5CF6"))
    border_grad.setColorAt(0.75, QColor("#FF9A00"))
    border_grad.setColorAt(1.0, QColor("#FF4D6D"))

    p.setBrush(QBrush(bg))
    p.setPen(QPen(QBrush(border_grad), max(2.0, size * 0.065)))
    p.drawRoundedRect(rect, rad, rad)

    # Top spectrum accent bar representing all 5 KinoSuite creative studios
    bar_w = size * 0.56
    bar_x = size * 0.22
    bar_y = size * 0.16
    bar_h = max(2.2, size * 0.055)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(border_grad))
    p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

    # KS monogram
    font = QFont("Segoe UI", max(8, int(size * 0.37)), QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 95)
    p.setFont(font)
    p.setPen(QColor("#F1F5F9"))
    p.drawText(rect.adjusted(0, size * 0.06, 0, 0), Qt.AlignmentFlag.AlignCenter, "KS")
    p.end()
    return pm


def make_app_badge(monogram: str, accent: str, bg_hex: str, size: int = 56, wave_bars: bool = False, pixel_blocks: bool = False) -> QPixmap:
    """Create a matching KinoSuite rounded-square monogram badge for any Kino app."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    pad = size * 0.06
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    rad = size * 0.22

    p.setBrush(QColor(bg_hex))
    p.setPen(QPen(QColor(accent), max(2.0, size * 0.06)))
    p.drawRoundedRect(rect, rad, rad)

    # Shared KinoSuite cyan top bar
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#00C2FF"))
    p.drawRoundedRect(QRectF(size * 0.22, size * 0.16, size * 0.56, max(2.0, size * 0.05)), 2, 2)

    if wave_bars:
        p.setBrush(QColor(16, 217, 160, 48))
        bars = [0.20, 0.38, 0.54, 0.30, 0.58, 0.42]
        bw = (size * 0.62) / len(bars)
        sx = size * 0.19
        for i, r in enumerate(bars):
            bh = size * r * 0.48
            p.drawRoundedRect(QRectF(sx + i * bw + 1, size * 0.55 - bh / 2, bw * 0.65, bh), 1.5, 1.5)

    if pixel_blocks:
        cell = size * 0.11
        for rx, ry, col in (
            (0.16, 0.28, QColor(167, 139, 250, 45)),
            (0.73, 0.28, QColor(245, 158, 11, 45)),
            (0.16, 0.72, QColor(52, 211, 153, 42)),
            (0.73, 0.72, QColor(139, 92, 246, 52)),
        ):
            p.setBrush(col)
            p.drawRoundedRect(QRectF(size * rx, size * ry, cell, cell), 1.5, 1.5)

    font = QFont("Segoe UI", max(8, int(size * 0.38)), QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 93)
    p.setFont(font)
    p.setPen(QColor(accent))
    p.drawText(rect.adjusted(0, size * 0.06, 0, 0), Qt.AlignmentFlag.AlignCenter, monogram)
    p.end()
    return pm


def make_suite_icon(size: int = 64) -> QIcon:
    return QIcon(make_suite_pixmap(size))
