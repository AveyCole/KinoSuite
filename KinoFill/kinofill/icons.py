"""Crisp procedural QPainter vector icons in the KinoSuite studio style for KinoFill."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


def make_app_pixmap(size: int = 64) -> QPixmap:
    """KinoSuite 'Kf' badge: deep slate rounded square + electric blue frame + KinoSuite cyan bar."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pad = size * 0.06
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    rad = size * 0.22
    p.setBrush(QColor("#111824"))
    p.setPen(QPen(QColor("#2F8CFF"), max(2.0, size * 0.065)))
    p.drawRoundedRect(rect, rad, rad)

    # Signature KinoSuite cyan top accent bar (shared across KinoSuite apps)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#00C2FF"))
    p.drawRoundedRect(
        QRectF(size * 0.22, size * 0.16, size * 0.56, max(2.0, size * 0.055)),
        2,
        2,
    )

    f = QFont("Segoe UI", max(7, int(size * 0.40)), QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor("#38BDF8"))
    p.drawText(rect.adjusted(0, size * 0.05, 0, 0), Qt.AlignmentFlag.AlignCenter, "Kf")
    p.end()
    return pm


def make_icon(
    name: str,
    color: str = "#DCE2EE",
    size: int = 24,
    accent_color: str = "#00C2FF",
) -> QIcon:
    if name == "app":
        return QIcon(make_app_pixmap(max(32, size * 2)))

    px = QPixmap(size * 2, size * 2)
    px.setDevicePixelRatio(2.0)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QColor(color)
    accent = QColor(accent_color)
    pen = QPen(c, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    if name == "select":
        path = QPainterPath()
        path.moveTo(6, 4)
        path.lineTo(6, 19)
        path.lineTo(10.2, 15.2)
        path.lineTo(13.2, 20.5)
        path.lineTo(15.6, 19.2)
        path.lineTo(12.6, 14)
        path.lineTo(18, 14)
        path.closeSubpath()
        p.fillPath(path, c)

    elif name == "text":
        f = QFont("Georgia", 15, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(0, 1, size, size), Qt.AlignmentFlag.AlignCenter, "T")

    elif name in ("edit_text", "replace_text"):
        p.setPen(QPen(accent, 1.8))
        p.drawRoundedRect(QRectF(2.5, 4, 19, 16), 3, 3)
        f = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(2.5, 4, 19, 16), Qt.AlignmentFlag.AlignCenter, "Ab")

    elif name == "check":
        p.setPen(QPen(QColor("#22C55E"), 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(4.5, 12.5), QPointF(9.5, 17.5))
        p.drawLine(QPointF(9.5, 17.5), QPointF(19.5, 6.5))

    elif name == "cross":
        p.setPen(QPen(QColor("#EF4444"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))

    elif name == "date":
        p.drawRoundedRect(QRectF(3.5, 5.5, 17, 15), 2.5, 2.5)
        p.drawLine(QPointF(3.5, 10), QPointF(20.5, 10))
        p.drawLine(QPointF(8, 3.5), QPointF(8, 7))
        p.drawLine(QPointF(16, 3.5), QPointF(16, 7))
        f = QFont("Segoe UI", 7, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(4, 10, 16, 10), Qt.AlignmentFlag.AlignCenter, "26")

    elif name == "sign":
        p.setPen(QPen(accent, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.moveTo(4, 16)
        path.cubicTo(7, 6, 10, 18, 13, 10)
        path.cubicTo(15, 6, 16, 16, 20, 13)
        p.drawPath(path)
        p.setPen(QPen(c, 1.4))
        p.drawLine(QPointF(4, 19.5), QPointF(20, 19.5))

    elif name == "highlight":
        p.fillRect(QRectF(3, 13, 18, 6), QColor("#FDE047"))
        p.setPen(QPen(c, 1.7))
        path = QPainterPath()
        path.moveTo(8, 14)
        path.lineTo(15, 5)
        path.lineTo(19, 8.5)
        path.lineTo(12, 17)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "pen":
        path = QPainterPath()
        path.moveTo(5, 19)
        path.lineTo(7.5, 13.5)
        path.lineTo(16.5, 4.5)
        path.lineTo(19.5, 7.5)
        path.lineTo(10.5, 16.5)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(14.2, 6.8), QPointF(17.2, 9.8))

    elif name == "whiteout":
        p.drawRoundedRect(QRectF(4, 7, 16, 11), 2.5, 2.5)
        p.fillRect(QRectF(5.5, 8.5, 8, 8), QColor("#F1F5F9"))
        p.drawLine(QPointF(13.5, 7), QPointF(13.5, 18))

    elif name == "redact":
        p.fillRect(QRectF(3.5, 6.5, 17, 11), QColor("#0B0E14"))
        p.setPen(QPen(QColor("#EF4444"), 1.7))
        p.drawRect(QRectF(3.5, 6.5, 17, 11))

    elif name == "shape":
        p.drawRect(QRectF(3.5, 4.5, 11, 10))
        p.setPen(QPen(accent, 1.8))
        p.drawEllipse(QRectF(10, 10, 10.5, 10.5))

    elif name == "image":
        p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2, 2)
        p.drawEllipse(QRectF(7, 7.5, 3, 3))
        p.drawLine(QPointF(5, 17), QPointF(10, 12))
        p.drawLine(QPointF(10, 12), QPointF(13.5, 15.5))
        p.drawLine(QPointF(13.5, 15.5), QPointF(16.5, 12.5))
        p.drawLine(QPointF(16.5, 12.5), QPointF(19, 17))

    elif name == "stamp":
        p.drawLine(QPointF(4, 19), QPointF(20, 19))
        p.drawRoundedRect(QRectF(5, 14, 14, 4), 1.5, 1.5)
        p.drawLine(QPointF(12, 14), QPointF(12, 9.5))
        p.drawEllipse(QRectF(9, 4.5, 6, 5.5))

    elif name == "note":
        p.setBrush(QColor("#FDE047"))
        p.setPen(QPen(QColor("#D97706"), 1.6))
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 2.5, 2.5)
        p.drawLine(QPointF(7, 9), QPointF(17, 9))
        p.drawLine(QPointF(7, 13), QPointF(14, 13))

    elif name == "form":
        p.setPen(QPen(accent, 1.7))
        p.drawRoundedRect(QRectF(3.5, 5, 17, 6), 2, 2)
        p.drawRoundedRect(QRectF(3.5, 14, 6, 6), 1.5, 1.5)
        p.drawLine(QPointF(5, 17), QPointF(6.5, 18.5))
        p.drawLine(QPointF(6.5, 18.5), QPointF(8.5, 15.5))
        p.setPen(QPen(c, 1.6))
        p.drawLine(QPointF(12, 17), QPointF(20, 17))

    elif name == "open":
        path = QPainterPath()
        path.moveTo(3.5, 7)
        path.lineTo(9.5, 7)
        path.lineTo(11.5, 9)
        path.lineTo(20.5, 9)
        path.lineTo(20.5, 18.5)
        path.lineTo(3.5, 18.5)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "save":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2)
        p.drawRect(QRectF(7.5, 4, 8, 5.5))
        p.drawRect(QRectF(7, 13, 10, 7))

    elif name == "undo":
        p.drawArc(QRectF(7, 7, 12, 11), 0 * 16, 180 * 16)
        p.drawLine(QPointF(7, 12), QPointF(4.5, 9.5))
        p.drawLine(QPointF(7, 12), QPointF(10, 9.5))

    elif name == "redo":
        p.drawArc(QRectF(5, 7, 12, 11), 0 * 16, 180 * 16)
        p.drawLine(QPointF(17, 12), QPointF(19.5, 9.5))
        p.drawLine(QPointF(17, 12), QPointF(14, 9.5))

    elif name == "search":
        p.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        p.drawLine(QPointF(14, 14), QPointF(19.5, 19.5))

    elif name == "print":
        p.drawRect(QRectF(7, 4, 10, 5))
        p.drawRoundedRect(QRectF(4, 9, 16, 7), 2, 2)
        p.drawRect(QRectF(7, 14, 10, 6))

    elif name == "lock":
        p.drawRoundedRect(QRectF(5.5, 11, 13, 9), 2, 2)
        p.drawArc(QRectF(8, 5, 8, 9), 0 * 16, 180 * 16)

    elif name == "theme":
        p.drawEllipse(QRectF(5, 5, 14, 14))
        path = QPainterPath()
        path.moveTo(12, 5)
        path.arcTo(QRectF(5, 5, 14, 14), 90, 180)
        path.closeSubpath()
        p.fillPath(path, accent)

    elif name == "zoom_in":
        p.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        p.drawLine(QPointF(14, 14), QPointF(19.5, 19.5))
        p.drawLine(QPointF(10, 7.5), QPointF(10, 12.5))
        p.drawLine(QPointF(7.5, 10), QPointF(12.5, 10))

    elif name == "zoom_out":
        p.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        p.drawLine(QPointF(14, 14), QPointF(19.5, 19.5))
        p.drawLine(QPointF(7.5, 10), QPointF(12.5, 10))

    elif name == "merge":
        p.drawRect(QRectF(4, 4, 9, 11))
        p.setPen(QPen(accent, 1.8))
        p.drawRect(QRectF(11, 9, 9, 11))

    p.end()
    return QIcon(px)
