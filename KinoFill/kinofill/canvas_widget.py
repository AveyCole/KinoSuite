"""Interactive multi-page PDF canvas and editing tools for KinoFill (KinoSuite)."""

from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
from datetime import datetime
import math
import os
import tempfile
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QBuffer, QByteArray, QEvent, QIODevice, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetricsF,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QInputDialog,
    QLineEdit,
    QMenu,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import (
    BaseItem,
    DocumentState,
    EditableTextBlock,
    FormFieldItem,
    HighlightItem,
    ImageItem,
    InkItem,
    NoteItem,
    RedactItem,
    ShapeItem,
    StampItem,
    TextItem,
    WhiteoutItem,
    item_from_dict,
    new_id,
)
from .pdf_engine import build_stripped_single_page_pdf, extract_editable_text_blocks, parse_page_range, resolve_rl_font
from reportlab.pdfbase import pdfmetrics


@dataclass
class ToolSettings:
    tool: str = "edit_text"
    show_text_boxes: bool = True
    # Text
    font_family: str = "Arial"
    font_size: float = 12.0
    bold: bool = False
    italic: bool = False
    text_color: str = "#111827"
    text_bg_color: str = ""
    text_align: str = "left"
    # Highlight / Pen / Shape
    highlight_color: str = "#FDE047"
    highlight_style: str = "highlight"  # highlight | underline | strikeout
    highlight_opacity: float = 0.42
    stroke_color: str = "#1D4ED8"
    fill_color: str = ""
    stroke_width: float = 2.2
    opacity: float = 1.0
    shape_type: str = "rect"  # rect | roundrect | ellipse | line | arrow
    # Whiteout
    whiteout_auto_sample: bool = True
    whiteout_color: str = "#FFFFFF"
    # Stamps & Date
    stamp_text: str = "APPROVED"
    stamp_color: str = "#DC2626"
    stamp_rotation: float = -12.0
    date_format: str = "%m/%d/%Y"
    check_color: str = "#111827"
    # Active signature / image payload
    pending_signature_b64: str = ""
    pending_signature_ratio: float = 2.6
    pending_image_b64: str = ""
    pending_image_ratio: float = 1.5
    # Forms
    highlight_forms: bool = True


HANDLE_SIZE = 8.0


def _decode_pixmap(b64: str) -> QPixmap:
    px = QPixmap()
    if b64:
        px.loadFromData(base64.b64decode(b64), "PNG")
    return px


class InlineTextEditor(QTextEdit):
    """Floating inline text editor placed directly over a TextItem or multiline FormFieldItem."""

    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._done = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._done = True
            self.cancelled.emit()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._commit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if not self._done:
            self._commit()

    def _commit(self) -> None:
        if self._done:
            return
        self._done = True
        self.committed.emit(self.toPlainText())


class PdfPageCanvas(QWidget):
    """Interactive vector canvas for a single PDF page."""

    def __init__(self, doc_view: "PdfDocumentView", page_index: int) -> None:
        super().__init__(doc_view.container)
        self.doc_view = doc_view
        self.page_index = page_index
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self._rendered_pixmap: Optional[QPixmap] = None
        self._rendered_image: Optional[QImage] = None
        self._rendered_zoom: float = -1.0
        self._rendered_stripped_key: Tuple[Tuple[str, Tuple[float, ...]], ...] = ()
        self._stream_stripped_ids: set[str] = set()
        self._pixmap_cache: Dict[str, QPixmap] = {}

        # Interaction state
        self._dragging_mode: str = ""  # move | resize | create | ink | line_p1 | line_p2 | replace_text
        self._resize_handle: str = ""
        self._drag_start_pt: QPointF = QPointF()
        self._drag_cur_pt: QPointF = QPointF()
        self._orig_item_geom: Tuple[float, float, float, float, float, float] = (0, 0, 0, 0, 0, 0)
        self._active_ink_points: List[List[float]] = []
        self._undo_pushed_for_drag: bool = False

        # Inline editors
        self._inline_editor: Optional[QWidget] = None
        self._editing_item_id: Optional[str] = None
        self._hovered_block_id: Optional[str] = None
        self._hovered_text_item_id: Optional[str] = None

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(shadow)

    @property
    def state(self) -> DocumentState:
        return self.doc_view.state

    @property
    def zoom(self) -> float:
        return self.doc_view.zoom

    @property
    def settings(self) -> ToolSettings:
        return self.doc_view.settings

    def page_point_size(self) -> Tuple[float, float]:
        sz = self.doc_view.pdf_doc.pagePointSize(self.page_index)
        return max(10.0, sz.width()), max(10.0, sz.height())

    def update_page_size(self) -> None:
        pw, ph = self.page_point_size()
        w = max(20, int(round(pw * self.zoom)))
        h = max(20, int(round(ph * self.zoom)))
        self.setFixedSize(w, h)
        self._rendered_zoom = -1.0
        self.update()

    def invalidate_render(self) -> None:
        self._rendered_pixmap = None
        self._rendered_image = None
        self._rendered_zoom = -1.0
        self._rendered_stripped_key = ()
        self.update()

    def _replaced_text_items_on_page(self) -> List[TextItem]:
        return [
            it
            for it in self.state.items_on_page(self.page_index)
            if isinstance(it, TextItem) and it.mask_rect and len(it.mask_rect) == 4
        ]

    def _ensure_rendered(self) -> None:
        replaced_items = self._replaced_text_items_on_page()
        cur_key = tuple((it.id, tuple(round(float(v), 2) for v in it.mask_rect)) for it in replaced_items)
        if (
            self._rendered_pixmap is not None
            and abs(self._rendered_zoom - self.zoom) < 1e-4
            and cur_key == self._rendered_stripped_key
        ):
            return
        pdf_doc = self.doc_view.pdf_doc
        if pdf_doc.status() != QPdfDocument.Status.Ready or self.page_index >= pdf_doc.pageCount():
            return
        dpr = max(1.0, self.devicePixelRatioF())
        pw, ph = self.page_point_size()
        px_w = max(1, int(round(pw * self.zoom * dpr)))
        px_h = max(1, int(round(ph * self.zoom * dpr)))

        img: Optional[QImage] = None
        stripped_ids: set[str] = set()

        if replaced_items:
            pdf_bytes, stripped_ids = build_stripped_single_page_pdf(
                self.state.working_pdf_path,
                self.state.password,
                self.page_index,
                replaced_items,
            )
            if pdf_bytes:
                fd, tmp_preview = tempfile.mkstemp(prefix="kinofill_prev_", suffix=".pdf")
                os.close(fd)
                tmp_doc = QPdfDocument()
                try:
                    with open(tmp_preview, "wb") as f:
                        f.write(pdf_bytes)
                    if tmp_doc.load(tmp_preview) == QPdfDocument.Error.None_ and tmp_doc.pageCount() > 0:
                        img = tmp_doc.render(0, QSize(px_w, px_h))
                except Exception:
                    img = None
                finally:
                    tmp_doc.close()
                    try:
                        os.remove(tmp_preview)
                    except OSError:
                        pass

        if img is None or img.isNull():
            img = pdf_doc.render(self.page_index, QSize(px_w, px_h))
            stripped_ids = set()

        if img.isNull():
            return
        # Composite onto white paper so transparent PDFs look clean
        paper = QImage(px_w, px_h, QImage.Format.Format_RGB32)
        paper.fill(QColor("#FFFFFF"))
        p = QPainter(paper)
        p.drawImage(0, 0, img)
        p.end()
        self._rendered_image = paper
        px = QPixmap.fromImage(paper)
        px.setDevicePixelRatio(dpr)
        self._rendered_pixmap = px
        self._rendered_zoom = self.zoom
        self._rendered_stripped_key = cur_key
        self._stream_stripped_ids = stripped_ids

    def _to_pdf_pt(self, pos: QPointF) -> QPointF:
        return QPointF(pos.x() / self.zoom, pos.y() / self.zoom)

    def _to_widget_rect(self, x: float, y: float, w: float, h: float) -> QRectF:
        z = self.zoom
        return QRectF(x * z, y * z, w * z, h * z)

    def _sample_page_bg_color(self, rect_pt: QRectF) -> str:
        """Sample border pixels around rect_pt on the rendered PDF to match background."""
        self._ensure_rendered()
        if self._rendered_image is None or self._rendered_image.isNull():
            return "#FFFFFF"
        img = self._rendered_image
        dpr = max(1.0, self.devicePixelRatioF())
        scale = self.zoom * dpr
        x0 = max(0, min(img.width() - 1, int(rect_pt.left() * scale)))
        y0 = max(0, min(img.height() - 1, int(rect_pt.top() * scale)))
        x1 = max(0, min(img.width() - 1, int(rect_pt.right() * scale)))
        y1 = max(0, min(img.height() - 1, int(rect_pt.bottom() * scale)))

        samples: List[Tuple[int, int, int]] = []
        for sx, sy in [
            (max(0, x0 - 2), max(0, y0 - 2)),
            (min(img.width() - 1, x1 + 2), max(0, y0 - 2)),
            (max(0, x0 - 2), min(img.height() - 1, y1 + 2)),
            (min(img.width() - 1, x1 + 2), min(img.height() - 1, y1 + 2)),
            ((x0 + x1) // 2, max(0, y0 - 2)),
            ((x0 + x1) // 2, min(img.height() - 1, y1 + 2)),
        ]:
            c = img.pixelColor(sx, sy)
            samples.append((c.red(), c.green(), c.blue()))

        if not samples:
            return "#FFFFFF"
        # Pick the lightest median sample (avoids hitting dark text ink)
        samples.sort(key=lambda rgb: rgb[0] + rgb[1] + rgb[2])
        r, g, b = samples[len(samples) * 2 // 3]
        return f"#{r:02X}{g:02X}{b:02X}"

    def _get_image_pixmap(self, item: ImageItem) -> QPixmap:
        if item.id not in self._pixmap_cache:
            self._pixmap_cache[item.id] = _decode_pixmap(item.image_b64)
        return self._pixmap_cache[item.id]

    def _item_bounds_pt(self, item: BaseItem) -> QRectF:
        if isinstance(item, InkItem) and item.points:
            xs = [p[0] for p in item.points]
            ys = [p[1] for p in item.points]
            pad = max(4.0, item.stroke_width)
            return QRectF(min(xs) - pad, min(ys) - pad, (max(xs) - min(xs)) + pad * 2, (max(ys) - min(ys)) + pad * 2)
        if isinstance(item, ShapeItem) and item.shape_type in ("line", "arrow"):
            x0, x1 = min(item.x, item.x2), max(item.x, item.x2)
            y0, y1 = min(item.y, item.y2), max(item.y, item.y2)
            return QRectF(x0 - 4, y0 - 4, max(8.0, x1 - x0 + 8), max(8.0, y1 - y0 + 8))
        return QRectF(item.x, item.y, max(8.0, item.w), max(8.0, item.h))

    def _handle_rects(self, rect_w: QRectF) -> Dict[str, QRectF]:
        hs = HANDLE_SIZE
        h2 = hs / 2.0
        cx = rect_w.center().x()
        cy = rect_w.center().y()
        return {
            "tl": QRectF(rect_w.left() - h2, rect_w.top() - h2, hs, hs),
            "t": QRectF(cx - h2, rect_w.top() - h2, hs, hs),
            "tr": QRectF(rect_w.right() - h2, rect_w.top() - h2, hs, hs),
            "r": QRectF(rect_w.right() - h2, cy - h2, hs, hs),
            "br": QRectF(rect_w.right() - h2, rect_w.bottom() - h2, hs, hs),
            "b": QRectF(cx - h2, rect_w.bottom() - h2, hs, hs),
            "bl": QRectF(rect_w.left() - h2, rect_w.bottom() - h2, hs, hs),
            "l": QRectF(rect_w.left() - h2, cy - h2, hs, hs),
        }

    def _hit_test_text_block(self, pt_pdf: QPointF) -> Optional[EditableTextBlock]:
        replaced = self.state.replaced_block_ids(self.page_index)
        for blk in self.state.text_blocks.get(self.page_index, []):
            if blk.id in replaced:
                continue
            if QRectF(blk.x, blk.y, blk.w, blk.h).adjusted(-2, -2, 2, 2).contains(pt_pdf):
                return blk
        return None

    def _hit_test_item(self, pt_pdf: QPointF) -> Optional[BaseItem]:
        items = self.state.items_on_page(self.page_index)
        for it in reversed(items):
            if isinstance(it, ShapeItem) and it.shape_type in ("line", "arrow"):
                # Point-to-segment distance
                ax, ay, bx, by = it.x, it.y, it.x2, it.y2
                dx, dy = bx - ax, by - ay
                l2 = dx * dx + dy * dy
                if l2 < 1e-3:
                    dist = math.hypot(pt_pdf.x() - ax, pt_pdf.y() - ay)
                else:
                    t = max(0.0, min(1.0, ((pt_pdf.x() - ax) * dx + (pt_pdf.y() - ay) * dy) / l2))
                    dist = math.hypot(pt_pdf.x() - (ax + t * dx), pt_pdf.y() - (ay + t * dy))
                if dist <= max(7.0, it.stroke_width + 4.0):
                    return it
            else:
                if self._item_bounds_pt(it).adjusted(-2, -2, 2, 2).contains(pt_pdf):
                    return it
        return None

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        self._ensure_rendered()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._rendered_pixmap is not None:
            painter.drawPixmap(0, 0, self._rendered_pixmap)
        else:
            painter.fillRect(self.rect(), QColor("#FFFFFF"))

        z = self.zoom
        pw, ph = self.page_point_size()

        # Search highlights
        self._paint_search_highlights(painter)

        # Watermark preview
        wm = self.state.watermark
        if wm.enabled and wm.text:
            total = self.doc_view.pdf_doc.pageCount()
            if self.page_index in set(parse_page_range(wm.page_range, total)):
                painter.save()
                painter.translate(pw * z / 2.0, ph * z / 2.0)
                painter.rotate(-wm.angle)
                col = QColor(wm.color)
                col.setAlphaF(max(0.03, min(1.0, wm.opacity)))
                painter.setPen(col)
                f = QFont("Arial")
                f.setPixelSize(max(8, int(round(wm.font_size * z))))
                f.setBold(True)
                painter.setFont(f)
                painter.drawText(QRectF(-pw * z, -ph * z * 0.25, pw * z * 2, ph * z * 0.5), Qt.AlignmentFlag.AlignCenter, wm.text)
                painter.restore()

        # Header / Footer preview
        hf = self.state.header_footer
        if hf.enabled and (self.page_index + 1) >= hf.start_page:
            total = self.doc_view.pdf_doc.pageCount()
            painter.save()
            f = QFont("Arial")
            f.setPixelSize(max(7, int(round(hf.font_size * z))))
            painter.setFont(f)
            painter.setPen(QColor(hf.color))
            m = hf.margin * z

            def fmt(tpl: str) -> str:
                return (tpl or "").replace("{page}", str(self.page_index + 1)).replace("{total}", str(total))

            top_rect = QRectF(m, m * 0.35, pw * z - 2 * m, m)
            bot_rect = QRectF(m, ph * z - m * 1.15, pw * z - 2 * m, m)
            if hf.header_left:
                painter.drawText(top_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, fmt(hf.header_left))
            if hf.header_center:
                painter.drawText(top_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, fmt(hf.header_center))
            if hf.header_right:
                painter.drawText(top_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt(hf.header_right))
            if hf.footer_left:
                painter.drawText(bot_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, fmt(hf.footer_left))
            if hf.footer_center:
                painter.drawText(bot_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, fmt(hf.footer_center))
            if hf.footer_right:
                painter.drawText(bot_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt(hf.footer_right))
            painter.restore()

        # In "Edit All Text" mode, show crisp subtle boxes around every editable existing text block
        if self.settings.tool == "edit_text":
            replaced = self.state.replaced_block_ids(self.page_index)
            for blk in self.state.text_blocks.get(self.page_index, []):
                if blk.id in replaced:
                    continue
                is_hov = blk.id == self._hovered_block_id
                if not self.settings.show_text_boxes and not is_hov:
                    continue
                br = self._to_widget_rect(blk.x, blk.y, blk.w, blk.h)
                if is_hov:
                    painter.fillRect(br, QColor(0, 194, 255, 28))
                    painter.setPen(QPen(QColor("#00A8E8"), 1.35, Qt.PenStyle.SolidLine))
                else:
                    painter.setPen(QPen(QColor(47, 140, 255, 95), 0.95, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(br, 2.0, 2.0)

        # Draw all overlay items
        selected_id = self.doc_view.selected_item_id
        for it in self.state.items_on_page(self.page_index):
            if it.id == self._editing_item_id and isinstance(it, TextItem):
                # Only draw tight fallback mask if original text wasn't stripped from PDF stream (e.g., scanned PDF)
                if it.id not in self._stream_stripped_ids and it.mask_rect and len(it.mask_rect) == 4:
                    mx, my, mw, mh = it.mask_rect
                    mr = self._to_widget_rect(mx, my, mw, mh)
                    painter.fillRect(mr, QColor(it.mask_color or "#FFFFFF"))
                if it.bg_color:
                    c = QColor(it.bg_color)
                    c.setAlphaF(it.bg_opacity)
                    painter.fillRect(self._to_widget_rect(it.x, it.y, it.w, it.h), c)
                continue
            self._paint_item(painter, it)
            # In Edit All Text mode, also outline edited/added text items gently so they remain obviously editable
            if self.settings.tool == "edit_text" and isinstance(it, TextItem) and it.id != selected_id:
                is_hov = it.id == self._hovered_text_item_id
                if self.settings.show_text_boxes or is_hov:
                    tr = self._to_widget_rect(it.x, it.y, it.w, it.h)
                    if is_hov:
                        painter.fillRect(tr, QColor(0, 194, 255, 24))
                        painter.setPen(QPen(QColor("#00A8E8"), 1.25, Qt.PenStyle.SolidLine))
                    else:
                        painter.setPen(QPen(QColor(34, 197, 94, 115), 0.95, Qt.PenStyle.DashLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(tr, 2.0, 2.0)

        # Draw selection handles
        if selected_id:
            sel = self.state.find_item(selected_id)
            if sel is not None and sel.page == self.page_index:
                self._paint_selection(painter, sel)

        # Draw live creation drag preview
        if self._dragging_mode in ("create", "replace_text"):
            self._paint_create_preview(painter)
        elif self._dragging_mode == "ink" and len(self._active_ink_points) >= 2:
            painter.save()
            c = QColor(self.settings.stroke_color)
            c.setAlphaF(self.settings.opacity)
            pen = QPen(c, max(1.0, self.settings.stroke_width * z), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(self._active_ink_points[0][0] * z, self._active_ink_points[0][1] * z)
            for pt in self._active_ink_points[1:]:
                path.lineTo(pt[0] * z, pt[1] * z)
            painter.drawPath(path)
            painter.restore()

        painter.end()

    def _paint_search_highlights(self, painter: QPainter) -> None:
        sm = self.doc_view.search_model
        if not sm.searchString():
            return
        results = sm.resultsOnPage(self.page_index)
        if not results:
            return
        z = self.zoom
        cur_idx = self.doc_view.current_search_index
        cur_link = sm.resultAtIndex(cur_idx) if 0 <= cur_idx < sm.count() else None

        for link in results:
            is_cur = (
                cur_link is not None
                and cur_link.page() == link.page()
                and cur_link.location() == link.location()
            )
            fill = QColor(249, 115, 22, 115) if is_cur else QColor(250, 204, 21, 95)
            border = QColor(234, 88, 12, 220) if is_cur else QColor(202, 138, 4, 150)
            for r in link.rectangles():
                wr = QRectF(r.x() * z, r.y() * z, r.width() * z, r.height() * z)
                painter.fillRect(wr, fill)
                painter.setPen(QPen(border, 1.5 if is_cur else 1.0))
                painter.drawRect(wr)

    def _paint_item(self, painter: QPainter, item: BaseItem) -> None:
        z = self.zoom
        painter.save()
        try:
            if isinstance(item, WhiteoutItem):
                rect = self._to_widget_rect(item.x, item.y, item.w, item.h)
                c = QColor(item.fill_color or "#FFFFFF")
                c.setAlphaF(item.opacity)
                painter.fillRect(rect, c)
                if item.border_color:
                    painter.setPen(QPen(QColor(item.border_color), 1.0))
                    painter.drawRect(rect)
                else:
                    # Very subtle dashed guide only on screen so user knows whiteout exists
                    painter.setPen(QPen(QColor(180, 190, 205, 95), 0.8, Qt.PenStyle.DashLine))
                    painter.drawRect(rect)

            elif isinstance(item, RedactItem):
                rect = self._to_widget_rect(item.x, item.y, item.w, item.h)
                painter.fillRect(rect, QColor(item.fill_color or "#000000"))
                if item.label:
                    painter.setPen(QColor("#FFFFFF"))
                    f = QFont("Arial")
                    f.setBold(True)
                    f.setPixelSize(max(8, int(round(min(11.0, item.h * 0.55) * z))))
                    painter.setFont(f)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, item.label)

            elif isinstance(item, HighlightItem):
                rect = self._to_widget_rect(item.x, item.y, item.w, item.h)
                c = QColor(item.color)
                if item.style == "highlight":
                    c.setAlphaF(item.opacity)
                    painter.fillRect(rect, c)
                elif item.style == "underline":
                    c.setAlphaF(min(1.0, max(0.75, item.opacity)))
                    painter.setPen(QPen(c, max(1.5, item.h * 0.12 * z)))
                    y_l = rect.bottom() - 1.5 * z
                    painter.drawLine(QPointF(rect.left(), y_l), QPointF(rect.right(), y_l))
                elif item.style == "strikeout":
                    c.setAlphaF(min(1.0, max(0.75, item.opacity)))
                    painter.setPen(QPen(c, max(1.5, item.h * 0.12 * z)))
                    y_l = rect.center().y()
                    painter.drawLine(QPointF(rect.left(), y_l), QPointF(rect.right(), y_l))

            elif isinstance(item, ShapeItem):
                stroke = QColor(item.stroke_color) if item.stroke_color else QColor(0, 0, 0, 0)
                stroke.setAlphaF(item.opacity if item.stroke_color else 0.0)
                fill = QColor(item.fill_color) if item.fill_color else QColor(0, 0, 0, 0)
                fill.setAlphaF(item.opacity if item.fill_color else 0.0)
                painter.setPen(
                    QPen(stroke, max(1.0, item.stroke_width * z), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    if item.stroke_color and item.stroke_width > 0
                    else Qt.PenStyle.NoPen
                )
                painter.setBrush(QBrush(fill) if item.fill_color else Qt.BrushStyle.NoBrush)

                if item.shape_type == "rect":
                    painter.drawRect(self._to_widget_rect(item.x, item.y, item.w, item.h))
                elif item.shape_type == "roundrect":
                    r = min(10.0, item.w * 0.2, item.h * 0.2) * z
                    painter.drawRoundedRect(self._to_widget_rect(item.x, item.y, item.w, item.h), r, r)
                elif item.shape_type == "ellipse":
                    painter.drawEllipse(self._to_widget_rect(item.x, item.y, item.w, item.h))
                elif item.shape_type in ("line", "arrow"):
                    p1 = QPointF(item.x * z, item.y * z)
                    p2 = QPointF(item.x2 * z, item.y2 * z)
                    painter.drawLine(p1, p2)
                    if item.shape_type == "arrow":
                        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
                        hl = max(9.0, item.stroke_width * 4.2) * z
                        a1 = angle + math.radians(152)
                        a2 = angle - math.radians(152)
                        painter.drawLine(p2, QPointF(p2.x() + hl * math.cos(a1), p2.y() + hl * math.sin(a1)))
                        painter.drawLine(p2, QPointF(p2.x() + hl * math.cos(a2), p2.y() + hl * math.sin(a2)))

            elif isinstance(item, InkItem):
                if len(item.points) >= 2:
                    c = QColor(item.color)
                    c.setAlphaF(item.opacity)
                    painter.setPen(
                        QPen(c, max(1.0, item.stroke_width * z), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    )
                    path = QPainterPath()
                    path.moveTo(item.points[0][0] * z, item.points[0][1] * z)
                    for pt in item.points[1:]:
                        path.lineTo(pt[0] * z, pt[1] * z)
                    painter.drawPath(path)

            elif isinstance(item, ImageItem):
                px = self._get_image_pixmap(item)
                if not px.isNull():
                    painter.setOpacity(item.opacity)
                    painter.drawPixmap(self._to_widget_rect(item.x, item.y, item.w, item.h).toRect(), px)

            elif isinstance(item, StampItem):
                rect = self._to_widget_rect(item.x, item.y, item.w, item.h)
                painter.translate(rect.center())
                if item.rotation:
                    painter.rotate(item.rotation)
                c = QColor(item.color)
                c.setAlphaF(item.opacity)
                hw, hh = rect.width() / 2.0, rect.height() / 2.0
                if item.stamp_type == "check":
                    painter.setPen(
                        QPen(c, max(2.0, min(rect.width(), rect.height()) * 0.13), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    )
                    painter.drawLine(QPointF(-hw * 0.72, 0), QPointF(-hw * 0.15, hh * 0.62))
                    painter.drawLine(QPointF(-hw * 0.15, hh * 0.62), QPointF(hw * 0.76, -hh * 0.62))
                elif item.stamp_type == "cross":
                    painter.setPen(QPen(c, max(2.0, min(rect.width(), rect.height()) * 0.13), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    painter.drawLine(QPointF(-hw * 0.65, -hh * 0.65), QPointF(hw * 0.65, hh * 0.65))
                    painter.drawLine(QPointF(-hw * 0.65, hh * 0.65), QPointF(hw * 0.65, -hh * 0.65))
                elif item.stamp_type == "dot":
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(c)
                    r = min(hw, hh) * 0.55
                    painter.drawEllipse(QPointF(0, 0), r, r)
                elif item.stamp_type == "circle":
                    painter.setPen(QPen(c, max(1.6, min(rect.width(), rect.height()) * 0.1)))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QRectF(-hw * 0.85, -hh * 0.85, rect.width() * 0.85, rect.height() * 0.85))
                elif item.stamp_type == "date":
                    painter.setPen(c)
                    f = QFont("Arial")
                    f.setPixelSize(max(8, int(round(min(18.0, item.h * 0.65) * z))))
                    painter.setFont(f)
                    painter.drawText(QRectF(-hw, -hh, rect.width(), rect.height()), Qt.AlignmentFlag.AlignCenter, item.text)
                elif item.stamp_type == "rubber":
                    if item.border:
                        painter.setPen(QPen(c, max(2.0, 2.2 * z)))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawRoundedRect(QRectF(-hw + 2, -hh + 2, rect.width() - 4, rect.height() - 4), 4 * z, 4 * z)
                    painter.setPen(c)
                    f = QFont("Arial")
                    f.setBold(True)
                    px_fs = max(9, int(round(min(28.0, item.h * 0.52) * z)))
                    f.setPixelSize(px_fs)
                    fm = QFontMetricsF(f)
                    tw = fm.horizontalAdvance(item.text)
                    if tw > rect.width() - 12 * z and tw > 0:
                        f.setPixelSize(max(7, int(px_fs * ((rect.width() - 12 * z) / tw))))
                    painter.setFont(f)
                    painter.drawText(QRectF(-hw, -hh, rect.width(), rect.height()), Qt.AlignmentFlag.AlignCenter, item.text)

            elif isinstance(item, TextItem):
                # Only paint fallback mask if the text wasn't already stripped directly from the PDF stream!
                if item.id not in self._stream_stripped_ids and item.mask_rect and len(item.mask_rect) == 4:
                    mx, my, mw, mh = item.mask_rect
                    mr = self._to_widget_rect(mx, my, mw, mh)
                    painter.fillRect(mr, QColor(item.mask_color or "#FFFFFF"))
                rect = self._to_widget_rect(item.x, item.y, item.w, item.h)
                if item.bg_color:
                    bg = QColor(item.bg_color)
                    bg.setAlphaF(item.bg_opacity)
                    painter.fillRect(rect, bg)
                if item.text:
                    f = QFont(item.font_family)
                    f.setPixelSize(max(6, int(round(item.font_size * z))))
                    f.setBold(item.bold)
                    f.setItalic(item.italic)
                    painter.setFont(f)
                    c = QColor(item.color)
                    c.setAlphaF(item.opacity)
                    painter.setPen(c)
                    align_flag = Qt.AlignmentFlag.AlignLeft
                    if item.align == "center":
                        align_flag = Qt.AlignmentFlag.AlignHCenter
                    elif item.align == "right":
                        align_flag = Qt.AlignmentFlag.AlignRight
                    text_rect = rect.adjusted(
                        (0.5 if item.source_block_id else 2.0) * z,
                        (0.0 if item.source_block_id else 2.0) * z,
                        -2 * z,
                        0.0,
                    )
                    painter.drawText(text_rect, int(align_flag | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), item.text)

            elif isinstance(item, NoteItem):
                rect = self._to_widget_rect(item.x, item.y, item.w, item.h)
                painter.setBrush(QColor(item.color or "#FEF08A"))
                painter.setPen(QPen(QColor("#CA8A04"), 1.3))
                painter.drawRoundedRect(rect, 3.5 * z, 3.5 * z)
                painter.setPen(QPen(QColor("#854D0E"), max(1.0, 1.0 * z)))
                for frac in (0.35, 0.55, 0.72):
                    ly = rect.top() + rect.height() * frac
                    painter.drawLine(QPointF(rect.left() + 4 * z, ly), QPointF(rect.right() - 4 * z, ly))

            elif isinstance(item, FormFieldItem):
                rect = self._to_widget_rect(item.x, item.y, item.w, item.h)
                if self.settings.highlight_forms or not item.is_existing:
                    bg = QColor(219, 234, 254, 130) if item.is_existing else QColor(220, 252, 231, 145)
                    border = QColor("#3B82F6") if item.is_existing else QColor("#16A34A")
                    painter.fillRect(rect, bg)
                    painter.setPen(QPen(border, 1.1, Qt.PenStyle.SolidLine if item.is_existing else Qt.PenStyle.DashLine))
                    painter.drawRect(rect)

                if item.id == self._editing_item_id:
                    return

                if item.field_type in ("text", "dropdown"):
                    if item.value:
                        f = QFont("Arial")
                        f.setPixelSize(max(7, int(round(item.font_size * z))))
                        painter.setFont(f)
                        painter.setPen(QColor("#111827"))
                        flags = (
                            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)
                            if item.multiline
                            else int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                        )
                        painter.drawText(rect.adjusted(3 * z, 1 * z, -3 * z, -1 * z), flags, item.value)
                    elif not item.is_existing:
                        f = QFont("Segoe UI")
                        f.setPixelSize(max(7, int(round(8.5 * z))))
                        painter.setFont(f)
                        painter.setPen(QColor("#15803D"))
                        painter.drawText(rect.adjusted(4 * z, 0, -4 * z, 0), Qt.AlignmentFlag.AlignVCenter, item.field_name)
                    if item.field_type == "dropdown":
                        # Tiny dropdown chevron
                        cx = rect.right() - 7 * z
                        cy = rect.center().y()
                        painter.setPen(QPen(QColor("#374151"), 1.3))
                        painter.drawLine(QPointF(cx - 3 * z, cy - 1.5 * z), QPointF(cx, cy + 2 * z))
                        painter.drawLine(QPointF(cx, cy + 2 * z), QPointF(cx + 3 * z, cy - 1.5 * z))

                elif item.field_type in ("checkbox", "radio"):
                    if item.checked:
                        painter.setPen(QPen(QColor("#111827"), max(1.8, min(rect.width(), rect.height()) * 0.14), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                        if item.field_type == "radio":
                            painter.setBrush(QColor("#111827"))
                            r = min(rect.width(), rect.height()) * 0.28
                            painter.drawEllipse(rect.center(), r, r)
                        else:
                            cx, cy = rect.center().x(), rect.center().y()
                            hw, hh = rect.width() * 0.30, rect.height() * 0.30
                            painter.drawLine(QPointF(cx - hw, cy), QPointF(cx - hw * 0.2, cy + hh * 0.8))
                            painter.drawLine(QPointF(cx - hw * 0.2, cy + hh * 0.8), QPointF(cx + hw, cy - hh * 0.8))
        finally:
            painter.restore()

    def _paint_selection(self, painter: QPainter, item: BaseItem) -> None:
        z = self.zoom
        painter.save()
        if isinstance(item, ShapeItem) and item.shape_type in ("line", "arrow"):
            p1 = QPointF(item.x * z, item.y * z)
            p2 = QPointF(item.x2 * z, item.y2 * z)
            painter.setPen(QPen(QColor("#00A8E8"), 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(p1, p2)
            painter.setBrush(QColor("#FFFFFF"))
            painter.setPen(QPen(QColor("#00A8E8"), 1.6))
            for pt in (p1, p2):
                painter.drawEllipse(pt, HANDLE_SIZE / 2.0, HANDLE_SIZE / 2.0)
        else:
            b = self._item_bounds_pt(item)
            wr = self._to_widget_rect(b.x(), b.y(), b.width(), b.height())
            painter.setPen(QPen(QColor("#00A8E8"), 1.4, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(wr)
            if not isinstance(item, InkItem):
                painter.setBrush(QColor("#FFFFFF"))
                painter.setPen(QPen(QColor("#00A8E8"), 1.5))
                for hr in self._handle_rects(wr).values():
                    painter.drawRect(hr)
        painter.restore()

    def _paint_create_preview(self, painter: QPainter) -> None:
        z = self.zoom
        p1 = QPointF(self._drag_start_pt.x() * z, self._drag_start_pt.y() * z)
        p2 = QPointF(self._drag_cur_pt.x() * z, self._drag_cur_pt.y() * z)
        rect = QRectF(p1, p2).normalized()
        tool = self.settings.tool
        painter.save()
        if tool == "replace_text":
            painter.fillRect(rect, QColor(37, 99, 235, 35))
            painter.setPen(QPen(QColor("#2563EB"), 1.4, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
        elif tool == "whiteout":
            painter.fillRect(rect, QColor(255, 255, 255, 220))
            painter.setPen(QPen(QColor("#2563EB"), 1.2, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
        elif tool == "redact":
            painter.fillRect(rect, QColor(0, 0, 0, 210))
            painter.setPen(QPen(QColor("#EF4444"), 1.4))
            painter.drawRect(rect)
        elif tool == "highlight":
            c = QColor(self.settings.highlight_color)
            c.setAlphaF(self.settings.highlight_opacity)
            painter.fillRect(rect, c)
        elif tool == "shape" and self.settings.shape_type in ("line", "arrow"):
            painter.setPen(QPen(QColor(self.settings.stroke_color), max(1.5, self.settings.stroke_width * z)))
            painter.drawLine(p1, p2)
        elif tool == "shape" and self.settings.shape_type == "ellipse":
            painter.setPen(QPen(QColor(self.settings.stroke_color), max(1.5, self.settings.stroke_width * z)))
            painter.drawEllipse(rect)
        elif tool in ("form_text", "form_check", "form_dropdown"):
            painter.fillRect(rect, QColor(220, 252, 231, 140))
            painter.setPen(QPen(QColor("#16A34A"), 1.4, Qt.PenStyle.DashLine))
            painter.drawRect(rect)
        else:
            painter.setPen(QPen(QColor(self.settings.stroke_color), max(1.5, self.settings.stroke_width * z)))
            painter.drawRect(rect)
        painter.restore()

    # ------------------------------------------------------------------
    # Inline Editors
    # ------------------------------------------------------------------
    def close_inline_editor(self, commit: bool = True) -> None:
        if self._inline_editor is None:
            return
        ed = self._inline_editor
        self._inline_editor = None
        self._editing_item_id = None
        if isinstance(ed, InlineTextEditor):
            if commit:
                ed._commit()
            else:
                ed._done = True
        ed.hide()
        ed.deleteLater()
        self.update()

    def open_inline_text_editor(
        self,
        item: TextItem,
        is_existing_block: bool = False,
        original_text: Optional[str] = None,
        is_new_replacement: bool = False,
    ) -> None:
        self.close_inline_editor(commit=True)
        self._editing_item_id = item.id
        ed = InlineTextEditor(self)
        self._inline_editor = ed
        z = self.zoom
        pw_pt, _ = self.page_point_size()

        f = QFont(item.font_family)
        f.setPixelSize(max(8, int(round(item.font_size * z))))
        f.setBold(item.bold)
        f.setItalic(item.italic)
        ed.setFont(f)
        ed.document().setDocumentMargin(2)

        # Ensure stripped background is computed immediately so inline editor is 100% transparent over form lines!
        self._ensure_rendered()
        is_stream_clean = item.id in self._stream_stripped_ids
        bg = item.bg_color if item.bg_color else ("transparent" if is_stream_clean else (item.mask_color or "#FFFFFF"))
        ed.setStyleSheet(
            f"QTextEdit {{ background: {bg}; color: {item.color}; "
            f"border: 1.5px solid #00A8E8; border-radius: 3px; padding: 0px 2px; }}"
        )
        ed.setPlainText(item.text)

        def fit_editor_geometry() -> None:
            fm = QFontMetricsF(f)
            rl_font = resolve_rl_font(item.font_family, item.bold, item.italic)
            txt = ed.toPlainText()
            lines = txt.splitlines() or [""]
            max_line_w_pt = max(
                max(
                    fm.horizontalAdvance(ln) / z,
                    pdfmetrics.stringWidth(ln, rl_font, item.font_size),
                )
                for ln in lines
            )
            needed_w_pt = max(item.w, max_line_w_pt + 24.0, 72.0)
            max_w_pt = max(80.0, pw_pt - item.x - 12.0)
            w_pt = min(needed_w_pt, max_w_pt)
            item.w = w_pt
            # Compute wrapped height
            ed.setFixedWidth(max(40, int(round(w_pt * z)) + 6))
            doc_h = ed.document().size().height()
            h_pt = max(item.h, (doc_h / z) + 4.0, item.font_size * 1.55)
            item.h = h_pt
            rect = self._to_widget_rect(item.x, item.y, w_pt, h_pt).toRect()
            ed.setGeometry(rect.adjusted(-2, -2, 6, 4))

        fit_editor_geometry()
        ed.textChanged.connect(fit_editor_geometry)

        # Put cursor at end (or select all for brand-new empty/short text)
        if not is_existing_block:
            ed.selectAll()
        else:
            cur = ed.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            ed.setTextCursor(cur)

        orig_cmp = item.text if original_text is None else original_text

        def on_commit(new_text: str) -> None:
            if is_new_replacement and new_text == orig_cmp:
                # User clicked an existing PDF text block and didn't alter it: leave original untouched!
                self.state.remove_item(item.id, record_undo=False)
                self.doc_view.select_item(None)
            elif not is_existing_block and not item.mask_rect and new_text.strip() == "":
                self.state.remove_item(item.id, record_undo=False)
                self.doc_view.select_item(None)
            else:
                if is_new_replacement:
                    # Record an undo state WITHOUT this new item first, so Ctrl+Z restores original PDF text cleanly
                    self.state.items.remove(item)
                    self.state.push_undo()
                    item.text = new_text
                    self.state.items.append(item)
                elif new_text != item.text:
                    self.state.push_undo()
                    item.text = new_text
            self._editing_item_id = None
            self._inline_editor = None
            ed.deleteLater()
            self.update()
            self.doc_view.itemsChanged.emit()

        def on_cancel() -> None:
            if is_new_replacement:
                self.state.remove_item(item.id, record_undo=False)
                self.doc_view.select_item(None)
            self._editing_item_id = None
            self._inline_editor = None
            ed.deleteLater()
            self.update()

        ed.committed.connect(on_commit)
        ed.cancelled.connect(on_cancel)
        ed.show()
        ed.setFocus()
        self.update()

    def start_editing_text_block(self, blk: EditableTextBlock) -> TextItem:
        """Convert a clicked native PDF text block into an inline editable TextItem right in place."""
        bg_col = self._sample_page_bg_color(QRectF(blk.x, blk.y, blk.w, blk.h))
        # Align replacement text baseline precisely with original PDF glyph baseline!
        # PDFium's tight rect starts near cap-top, while Qt/ReportLab add font ascender/leading above cap-top.
        baseline_lift = blk.font_size * 0.24
        item = TextItem(
            page=self.page_index,
            x=blk.x,
            y=max(0.0, blk.y - baseline_lift),
            w=max(blk.w + 14.0, 72.0),
            h=max(blk.h + baseline_lift, blk.font_size * 1.35),
            text=blk.text,
            font_family=blk.font_family,
            font_size=blk.font_size,
            bold=blk.bold,
            italic=blk.italic,
            color=blk.color,
            bg_color="",
            mask_rect=[blk.x, blk.y, blk.w, blk.h],
            mask_color=bg_col,
            source_block_id=blk.id,
            source_orig_text=blk.text,
        )
        self.state.items.append(item)
        self.doc_view.select_item(item.id)
        self.open_inline_text_editor(
            item,
            is_existing_block=True,
            original_text=blk.text,
            is_new_replacement=True,
        )
        return item

    def open_inline_form_editor(self, field: FormFieldItem) -> None:
        self.close_inline_editor(commit=True)
        z = self.zoom
        rect = self._to_widget_rect(field.x, field.y, field.w, field.h).toRect()

        if field.field_type == "checkbox":
            self.state.push_undo()
            field.checked = not field.checked
            field.value = field.checked_value if field.checked else "/Off"
            self.update()
            self.doc_view.itemsChanged.emit()
            return

        if field.field_type == "radio":
            self.state.push_undo()
            for other in self.state.items:
                if isinstance(other, FormFieldItem) and other.field_type == "radio" and other.radio_group == field.radio_group:
                    other.checked = False
                    other.value = "/Off"
            field.checked = True
            field.value = field.checked_value
            self.doc_view.refresh_all_pages()
            self.doc_view.itemsChanged.emit()
            return

        self._editing_item_id = field.id
        if field.field_type == "dropdown":
            cb = QComboBox(self)
            cb.setEditable(True)
            cb.addItems(field.options or [""])
            if field.value:
                cb.setCurrentText(field.value)
            cb.setGeometry(rect.adjusted(-1, -1, 1, 2))
            self._inline_editor = cb

            def commit_cb() -> None:
                val = cb.currentText()
                if val != field.value:
                    self.state.push_undo()
                    field.value = val
                self._editing_item_id = None
                self._inline_editor = None
                cb.deleteLater()
                self.update()
                self.doc_view.itemsChanged.emit()

            cb.activated.connect(lambda _: commit_cb())
            cb.lineEdit().editingFinished.connect(commit_cb)
            cb.show()
            cb.setFocus()
            cb.showPopup()
            return

        # Text form field
        if field.multiline:
            ed = InlineTextEditor(self)
            ed.setGeometry(rect.adjusted(-1, -1, 2, 2))
            f = QFont("Arial")
            f.setPixelSize(max(8, int(round(field.font_size * z))))
            ed.setFont(f)
            ed.setPlainText(field.value)
            self._inline_editor = ed

            def on_commit_ml(val: str) -> None:
                if val != field.value:
                    self.state.push_undo()
                    field.value = val
                self._editing_item_id = None
                self._inline_editor = None
                ed.deleteLater()
                self.update()
                self.doc_view.itemsChanged.emit()

            ed.committed.connect(on_commit_ml)
            ed.cancelled.connect(lambda: self.close_inline_editor(False))
            ed.show()
            ed.setFocus()
        else:
            le = QLineEdit(self)
            le.setGeometry(rect.adjusted(-1, -1, 1, 1))
            f = QFont("Arial")
            f.setPixelSize(max(8, int(round(field.font_size * z))))
            le.setFont(f)
            le.setText(field.value)
            le.setStyleSheet("QLineEdit { background: #E0F2FE; color: #111827; border: 1.5px solid #00A8E8; padding: 0 3px; }")
            self._inline_editor = le

            def commit_le() -> None:
                if self._inline_editor is not le:
                    return
                val = le.text()
                if val != field.value:
                    self.state.push_undo()
                    field.value = val
                self._editing_item_id = None
                self._inline_editor = None
                le.deleteLater()
                self.update()
                self.doc_view.itemsChanged.emit()

            le.editingFinished.connect(commit_le)
            le.returnPressed.connect(commit_le)
            le.show()
            le.setFocus()
            le.selectAll()

    def open_note_dialog(self, note: NoteItem) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self,
            f"Sticky Note ({note.timestamp})",
            "Comment:",
            note.text,
        )
        if ok:
            self.state.push_undo()
            note.text = text
            self.update()
            self.doc_view.itemsChanged.emit()

    # ------------------------------------------------------------------
    # Mouse Events
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.doc_view.set_current_page(self.page_index, scroll=False)
        self.close_inline_editor(commit=True)

        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.position())
            return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos_w = event.position()
        pt_pdf = self._to_pdf_pt(pos_w)
        tool = self.settings.tool

        # Check resize handles on currently selected item first when in select tool
        if tool == "select" and self.doc_view.selected_item_id:
            sel = self.state.find_item(self.doc_view.selected_item_id)
            if sel is not None and sel.page == self.page_index and not sel.locked:
                if isinstance(sel, ShapeItem) and sel.shape_type in ("line", "arrow"):
                    z = self.zoom
                    if (QPointF(sel.x * z, sel.y * z) - pos_w).manhattanLength() <= 10:
                        self._dragging_mode = "line_p1"
                        self._drag_start_pt = pt_pdf
                        self._orig_item_geom = (sel.x, sel.y, sel.w, sel.h, sel.x2, sel.y2)
                        self._undo_pushed_for_drag = False
                        return
                    if (QPointF(sel.x2 * z, sel.y2 * z) - pos_w).manhattanLength() <= 10:
                        self._dragging_mode = "line_p2"
                        self._drag_start_pt = pt_pdf
                        self._orig_item_geom = (sel.x, sel.y, sel.w, sel.h, sel.x2, sel.y2)
                        self._undo_pushed_for_drag = False
                        return
                elif not isinstance(sel, InkItem):
                    b = self._item_bounds_pt(sel)
                    wr = self._to_widget_rect(b.x(), b.y(), b.width(), b.height())
                    for hname, hrect in self._handle_rects(wr).items():
                        if hrect.adjusted(-3, -3, 3, 3).contains(pos_w):
                            self._dragging_mode = "resize"
                            self._resize_handle = hname
                            self._drag_start_pt = pt_pdf
                            self._orig_item_geom = (sel.x, sel.y, sel.w, sel.h, 0, 0)
                            self._undo_pushed_for_drag = False
                            return

        if tool == "edit_text":
            # 1. Existing fillable form fields remain directly clickable!
            hit = self._hit_test_item(pt_pdf)
            if isinstance(hit, FormFieldItem):
                self.doc_view.select_item(hit.id)
                self.open_inline_form_editor(hit)
                return
            # 2. Already-edited / added TextItem: single-click immediately opens inline editor!
            if isinstance(hit, TextItem):
                self.doc_view.select_item(hit.id)
                self.open_inline_text_editor(hit, is_existing_block=bool(hit.source_block_id))
                return
            # 3. Native PDF text block: single-click pops up editable box right over the text!
            blk = self._hit_test_text_block(pt_pdf)
            if blk is not None:
                self.start_editing_text_block(blk)
                return
            # 4. Other annotation object: select/move it
            if hit is not None:
                self.doc_view.select_item(hit.id)
                if not hit.locked:
                    self._dragging_mode = "move"
                    self._drag_start_pt = pt_pdf
                    x2 = hit.x2 if isinstance(hit, ShapeItem) else 0.0
                    y2 = hit.y2 if isinstance(hit, ShapeItem) else 0.0
                    self._orig_item_geom = (hit.x, hit.y, hit.w, hit.h, x2, y2)
                    self._undo_pushed_for_drag = False
                self.update()
                return
            self.doc_view.select_item(None)
            self.update()
            return

        if tool == "select":
            hit = self._hit_test_item(pt_pdf)
            if hit is not None:
                self.doc_view.select_item(hit.id)
                if isinstance(hit, FormFieldItem) and hit.is_existing:
                    # Clicking an existing AcroForm field fills it immediately!
                    self.open_inline_form_editor(hit)
                    return
                if not hit.locked:
                    self._dragging_mode = "move"
                    self._drag_start_pt = pt_pdf
                    x2 = hit.x2 if isinstance(hit, ShapeItem) else 0.0
                    y2 = hit.y2 if isinstance(hit, ShapeItem) else 0.0
                    self._orig_item_geom = (hit.x, hit.y, hit.w, hit.h, x2, y2)
                    self._undo_pushed_for_drag = False
            else:
                self.doc_view.select_item(None)
            self.update()
            return

        # One-click placement tools
        if tool == "text":
            item = TextItem(
                page=self.page_index,
                x=pt_pdf.x(),
                y=pt_pdf.y() - self.settings.font_size * 0.4,
                w=190.0,
                h=max(24.0, self.settings.font_size * 1.7),
                text="",
                font_family=self.settings.font_family,
                font_size=self.settings.font_size,
                bold=self.settings.bold,
                italic=self.settings.italic,
                color=self.settings.text_color,
                bg_color=self.settings.text_bg_color,
                align=self.settings.text_align,
            )
            self.state.add_item(item)
            self.doc_view.select_item(item.id)
            self.open_inline_text_editor(item)
            self.doc_view.itemsChanged.emit()
            return

        if tool in ("check", "cross", "dot", "circle"):
            sz = 20.0
            item = StampItem(
                page=self.page_index,
                x=pt_pdf.x() - sz / 2.0,
                y=pt_pdf.y() - sz / 2.0,
                w=sz,
                h=sz,
                stamp_type=tool,
                color=self.settings.check_color,
            )
            self.state.add_item(item)
            self.doc_view.select_item(item.id)
            self.update()
            self.doc_view.itemsChanged.emit()
            return

        if tool == "date":
            date_str = datetime.now().strftime(self.settings.date_format or "%m/%d/%Y")
            item = StampItem(
                page=self.page_index,
                x=pt_pdf.x() - 48.0,
                y=pt_pdf.y() - 10.0,
                w=96.0,
                h=20.0,
                stamp_type="date",
                text=date_str,
                color=self.settings.text_color,
            )
            self.state.add_item(item)
            self.doc_view.select_item(item.id)
            self.update()
            self.doc_view.itemsChanged.emit()
            return

        if tool == "stamp":
            w, h = 155.0, 44.0
            item = StampItem(
                page=self.page_index,
                x=pt_pdf.x() - w / 2.0,
                y=pt_pdf.y() - h / 2.0,
                w=w,
                h=h,
                stamp_type="rubber",
                text=self.settings.stamp_text or "APPROVED",
                color=self.settings.stamp_color,
                rotation=self.settings.stamp_rotation,
                border=True,
                opacity=0.88,
            )
            self.state.add_item(item)
            self.doc_view.select_item(item.id)
            self.update()
            self.doc_view.itemsChanged.emit()
            return

        if tool == "sign":
            if not self.settings.pending_signature_b64:
                self.doc_view.signatureRequested.emit(self.page_index, pt_pdf.x(), pt_pdf.y())
                return
            w = 155.0
            h = max(28.0, w / max(0.3, self.settings.pending_signature_ratio))
            item = ImageItem(
                page=self.page_index,
                x=pt_pdf.x() - w / 2.0,
                y=pt_pdf.y() - h / 2.0,
                w=w,
                h=h,
                image_b64=self.settings.pending_signature_b64,
                is_signature=True,
            )
            self.state.add_item(item)
            self.doc_view.select_item(item.id)
            self.doc_view.toolFinishedAutoSelect.emit()
            self.update()
            self.doc_view.itemsChanged.emit()
            return

        if tool == "image":
            if not self.settings.pending_image_b64:
                self.doc_view.imageRequested.emit(self.page_index, pt_pdf.x(), pt_pdf.y())
                return
            w = 180.0
            h = max(36.0, w / max(0.25, self.settings.pending_image_ratio))
            item = ImageItem(
                page=self.page_index,
                x=pt_pdf.x() - w / 2.0,
                y=pt_pdf.y() - h / 2.0,
                w=w,
                h=h,
                image_b64=self.settings.pending_image_b64,
                is_signature=False,
            )
            self.state.add_item(item)
            self.doc_view.select_item(item.id)
            self.doc_view.toolFinishedAutoSelect.emit()
            self.update()
            self.doc_view.itemsChanged.emit()
            return

        if tool == "note":
            note = NoteItem(page=self.page_index, x=pt_pdf.x() - 12, y=pt_pdf.y() - 12, w=24.0, h=24.0)
            self.state.add_item(note)
            self.doc_view.select_item(note.id)
            self.update()
            self.open_note_dialog(note)
            return

        if tool == "pen":
            self._dragging_mode = "ink"
            self._active_ink_points = [[pt_pdf.x(), pt_pdf.y()]]
            return

        if tool == "replace_text":
            self._dragging_mode = "replace_text"
            self._drag_start_pt = pt_pdf
            self._drag_cur_pt = pt_pdf
            return

        # Drag-to-create tools: whiteout, redact, highlight, shape, form_text, form_check, form_dropdown
        if tool in ("whiteout", "redact", "highlight", "shape", "form_text", "form_check", "form_dropdown"):
            self._dragging_mode = "create"
            self._drag_start_pt = pt_pdf
            self._drag_cur_pt = pt_pdf
            return

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos_w = event.position()
        pt_pdf = self._to_pdf_pt(pos_w)

        if not self._dragging_mode:
            self._update_hover_cursor(pos_w, pt_pdf)
            return

        if self._dragging_mode in ("create", "replace_text"):
            self._drag_cur_pt = pt_pdf
            self.update()
            return

        if self._dragging_mode == "ink":
            if not self._active_ink_points or math.hypot(
                pt_pdf.x() - self._active_ink_points[-1][0],
                pt_pdf.y() - self._active_ink_points[-1][1],
            ) >= 1.5:
                self._active_ink_points.append([pt_pdf.x(), pt_pdf.y()])
                self.update()
            return

        sel = self.state.find_item(self.doc_view.selected_item_id or "")
        if sel is None or sel.page != self.page_index:
            return

        dx = pt_pdf.x() - self._drag_start_pt.x()
        dy = pt_pdf.y() - self._drag_start_pt.y()

        if not self._undo_pushed_for_drag and (abs(dx) > 0.5 or abs(dy) > 0.5):
            self.state.push_undo()
            self._undo_pushed_for_drag = True

        ox, oy, ow, oh, ox2, oy2 = self._orig_item_geom

        if self._dragging_mode == "move":
            if isinstance(sel, InkItem):
                # Shift all points relative to original offset
                sel.points = [[p[0] + dx, p[1] + dy] for p in sel.points]
                self._drag_start_pt = pt_pdf
            elif isinstance(sel, ShapeItem) and sel.shape_type in ("line", "arrow"):
                sel.x = ox + dx
                sel.y = oy + dy
                sel.x2 = ox2 + dx
                sel.y2 = oy2 + dy
            else:
                sel.x = ox + dx
                sel.y = oy + dy
            self.update()
        elif self._dragging_mode == "line_p1" and isinstance(sel, ShapeItem):
            sel.x = pt_pdf.x()
            sel.y = pt_pdf.y()
            self.update()
        elif self._dragging_mode == "line_p2" and isinstance(sel, ShapeItem):
            sel.x2 = pt_pdf.x()
            sel.y2 = pt_pdf.y()
            self.update()
        elif self._dragging_mode == "resize":
            nx, ny, nw, nh = ox, oy, ow, oh
            h = self._resize_handle
            if "l" in h:
                nx = min(ox + ow - 10.0, ox + dx)
                nw = (ox + ow) - nx
            if "r" in h:
                nw = max(10.0, ow + dx)
            if "t" in h:
                ny = min(oy + oh - 10.0, oy + dy)
                nh = (oy + oh) - ny
            if "b" in h:
                nh = max(10.0, oh + dy)
            # Aspect lock for signatures / images when Shift not held on corner drag
            if isinstance(sel, ImageItem) and sel.aspect_lock and len(h) == 2 and oh > 0:
                ratio = ow / oh
                nh = max(10.0, nw / ratio)
            sel.x, sel.y, sel.w, sel.h = nx, ny, nw, nh
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging_mode:
            return
        mode = self._dragging_mode
        self._dragging_mode = ""

        if mode == "ink":
            if len(self._active_ink_points) >= 2:
                item = InkItem(
                    page=self.page_index,
                    points=self._active_ink_points,
                    color=self.settings.stroke_color,
                    stroke_width=self.settings.stroke_width,
                    opacity=self.settings.opacity,
                )
                self.state.add_item(item)
                self.doc_view.select_item(item.id)
                self.doc_view.itemsChanged.emit()
            self._active_ink_points = []
            self.update()
            return

        if mode == "replace_text":
            rect = QRectF(self._drag_start_pt, self._drag_cur_pt).normalized()
            if rect.width() >= 8 and rect.height() >= 6:
                sel_obj = self.doc_view.pdf_doc.getSelection(
                    self.page_index,
                    QPointF(rect.left(), rect.top()),
                    QPointF(rect.right(), rect.bottom()),
                )
                extracted = sel_obj.text().strip() if sel_obj else ""
                bg_col = self._sample_page_bg_color(rect)
                self.state.push_undo()
                wo = WhiteoutItem(
                    page=self.page_index,
                    x=rect.x() - 1.5,
                    y=rect.y() - 1.5,
                    w=rect.width() + 3.0,
                    h=rect.height() + 3.0,
                    fill_color=bg_col,
                )
                self.state.items.append(wo)
                est_fs = max(8.0, min(28.0, rect.height() * 0.72))
                txt = TextItem(
                    page=self.page_index,
                    x=rect.x(),
                    y=rect.y(),
                    w=max(rect.width() + 18.0, 90.0),
                    h=max(rect.height() + 6.0, est_fs * 1.6),
                    text=extracted,
                    font_family=self.settings.font_family,
                    font_size=round(est_fs, 1),
                    bold=self.settings.bold,
                    italic=self.settings.italic,
                    color=self.settings.text_color,
                    bg_color="",
                )
                self.state.items.append(txt)
                self.doc_view.select_item(txt.id)
                self.open_inline_text_editor(txt)
                self.doc_view.itemsChanged.emit()
            self.update()
            return

        if mode == "create":
            rect = QRectF(self._drag_start_pt, self._drag_cur_pt).normalized()
            tool = self.settings.tool
            if tool == "shape" and self.settings.shape_type in ("line", "arrow"):
                if math.hypot(
                    self._drag_cur_pt.x() - self._drag_start_pt.x(),
                    self._drag_cur_pt.y() - self._drag_start_pt.y(),
                ) >= 6.0:
                    item = ShapeItem(
                        page=self.page_index,
                        shape_type=self.settings.shape_type,
                        x=self._drag_start_pt.x(),
                        y=self._drag_start_pt.y(),
                        x2=self._drag_cur_pt.x(),
                        y2=self._drag_cur_pt.y(),
                        stroke_color=self.settings.stroke_color,
                        stroke_width=self.settings.stroke_width,
                        opacity=self.settings.opacity,
                    )
                    self.state.add_item(item)
                    self.doc_view.select_item(item.id)
                    self.doc_view.itemsChanged.emit()
                self.update()
                return

            if rect.width() < 6 and rect.height() < 6:
                # Default click size for quick placement
                if tool == "form_check":
                    rect = QRectF(self._drag_start_pt.x() - 8, self._drag_start_pt.y() - 8, 16, 16)
                elif tool in ("form_text", "form_dropdown"):
                    rect = QRectF(self._drag_start_pt.x(), self._drag_start_pt.y() - 10, 150, 22)
                else:
                    self.update()
                    return

            item: Optional[BaseItem] = None
            if tool == "whiteout":
                col = self._sample_page_bg_color(rect) if self.settings.whiteout_auto_sample else self.settings.whiteout_color
                item = WhiteoutItem(page=self.page_index, x=rect.x(), y=rect.y(), w=rect.width(), h=rect.height(), fill_color=col)
            elif tool == "redact":
                item = RedactItem(page=self.page_index, x=rect.x(), y=rect.y(), w=rect.width(), h=rect.height())
            elif tool == "highlight":
                item = HighlightItem(
                    page=self.page_index,
                    x=rect.x(),
                    y=rect.y(),
                    w=rect.width(),
                    h=rect.height(),
                    style=self.settings.highlight_style,
                    color=self.settings.highlight_color,
                    opacity=self.settings.highlight_opacity,
                )
            elif tool == "shape":
                item = ShapeItem(
                    page=self.page_index,
                    shape_type=self.settings.shape_type,
                    x=rect.x(),
                    y=rect.y(),
                    w=rect.width(),
                    h=rect.height(),
                    stroke_color=self.settings.stroke_color,
                    fill_color=self.settings.fill_color,
                    stroke_width=self.settings.stroke_width,
                    opacity=self.settings.opacity,
                )
            elif tool == "form_text":
                n = sum(1 for i in self.state.items if isinstance(i, FormFieldItem)) + 1
                item = FormFieldItem(
                    page=self.page_index,
                    x=rect.x(),
                    y=rect.y(),
                    w=max(40.0, rect.width()),
                    h=max(18.0, rect.height()),
                    field_name=f"TextField_{n}",
                    field_type="text",
                    multiline=rect.height() > 36.0,
                    is_existing=False,
                )
            elif tool == "form_check":
                n = sum(1 for i in self.state.items if isinstance(i, FormFieldItem)) + 1
                s = max(14.0, min(rect.width(), rect.height()))
                item = FormFieldItem(
                    page=self.page_index,
                    x=rect.x(),
                    y=rect.y(),
                    w=s,
                    h=s,
                    field_name=f"Checkbox_{n}",
                    field_type="checkbox",
                    checked=False,
                    is_existing=False,
                )
            elif tool == "form_dropdown":
                n = sum(1 for i in self.state.items if isinstance(i, FormFieldItem)) + 1
                opts_str, ok = QInputDialog.getText(
                    self,
                    "Dropdown Options",
                    "Enter comma-separated options:",
                    text="Option 1, Option 2, Option 3",
                )
                opts = [o.strip() for o in opts_str.split(",") if o.strip()] if ok else ["Option 1", "Option 2"]
                item = FormFieldItem(
                    page=self.page_index,
                    x=rect.x(),
                    y=rect.y(),
                    w=max(60.0, rect.width()),
                    h=max(20.0, rect.height()),
                    field_name=f"Dropdown_{n}",
                    field_type="dropdown",
                    options=opts,
                    value=opts[0] if opts else "",
                    is_existing=False,
                )

            if item is not None:
                self.state.add_item(item)
                self.doc_view.select_item(item.id)
                self.doc_view.itemsChanged.emit()
            self.update()
            return

        if mode in ("move", "resize", "line_p1", "line_p2") and self._undo_pushed_for_drag:
            self.doc_view.itemsChanged.emit()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        pt_pdf = self._to_pdf_pt(event.position())
        hit = self._hit_test_item(pt_pdf)
        if isinstance(hit, TextItem):
            self.doc_view.select_item(hit.id)
            self.open_inline_text_editor(hit, is_existing_block=bool(hit.source_block_id))
        elif isinstance(hit, NoteItem):
            self.doc_view.select_item(hit.id)
            self.open_note_dialog(hit)
        elif isinstance(hit, FormFieldItem):
            self.doc_view.select_item(hit.id)
            self.open_inline_form_editor(hit)
        elif isinstance(hit, StampItem) and hit.stamp_type in ("rubber", "date"):
            txt, ok = QInputDialog.getText(self, "Edit Stamp Text", "Text:", text=hit.text)
            if ok and txt.strip():
                self.state.push_undo()
                hit.text = txt.strip()
                self.update()
                self.doc_view.itemsChanged.emit()
        elif isinstance(hit, RedactItem):
            txt, ok = QInputDialog.getText(self, "Redaction Label", "Optional label (e.g. REDACTED):", text=hit.label)
            if ok:
                self.state.push_undo()
                hit.label = txt.strip()
                self.update()
                self.doc_view.itemsChanged.emit()
        elif self.settings.tool in ("edit_text", "select"):
            blk = self._hit_test_text_block(pt_pdf)
            if blk is not None:
                self.start_editing_text_block(blk)
            elif self.settings.tool == "edit_text":
                item = TextItem(
                    page=self.page_index,
                    x=pt_pdf.x(),
                    y=pt_pdf.y() - self.settings.font_size * 0.4,
                    w=180.0,
                    h=max(24.0, self.settings.font_size * 1.6),
                    text="",
                    font_family=self.settings.font_family,
                    font_size=self.settings.font_size,
                    bold=self.settings.bold,
                    italic=self.settings.italic,
                    color=self.settings.text_color,
                    bg_color=self.settings.text_bg_color,
                    align=self.settings.text_align,
                )
                self.state.add_item(item)
                self.doc_view.select_item(item.id)
                self.open_inline_text_editor(item)
                self.doc_view.itemsChanged.emit()

    def leaveEvent(self, event) -> None:
        if self._hovered_block_id is not None or self._hovered_text_item_id is not None:
            self._hovered_block_id = None
            self._hovered_text_item_id = None
            self.update()
        super().leaveEvent(event)

    def _update_hover_cursor(self, pos_w: QPointF, pt_pdf: QPointF) -> None:
        tool = self.settings.tool
        if tool == "edit_text":
            prev_b = self._hovered_block_id
            prev_t = self._hovered_text_item_id
            self._hovered_block_id = None
            self._hovered_text_item_id = None

            hit = self._hit_test_item(pt_pdf)
            if isinstance(hit, FormFieldItem):
                self.setCursor(Qt.CursorShape.PointingHandCursor if hit.field_type in ("checkbox", "radio", "dropdown") else Qt.CursorShape.IBeamCursor)
            elif isinstance(hit, TextItem):
                self._hovered_text_item_id = hit.id
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                blk = self._hit_test_text_block(pt_pdf)
                if blk is not None:
                    self._hovered_block_id = blk.id
                    self.setCursor(Qt.CursorShape.IBeamCursor)
                elif hit is not None:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

            if prev_b != self._hovered_block_id or prev_t != self._hovered_text_item_id:
                self.update()
            return

        if self._hovered_block_id is not None or self._hovered_text_item_id is not None:
            self._hovered_block_id = None
            self._hovered_text_item_id = None
            self.update()

        if tool == "select":
            if self.doc_view.selected_item_id:
                sel = self.state.find_item(self.doc_view.selected_item_id)
                if sel is not None and sel.page == self.page_index and not isinstance(sel, InkItem):
                    b = self._item_bounds_pt(sel)
                    wr = self._to_widget_rect(b.x(), b.y(), b.width(), b.height())
                    for hname, hrect in self._handle_rects(wr).items():
                        if hrect.adjusted(-3, -3, 3, 3).contains(pos_w):
                            if hname in ("tl", "br"):
                                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                            elif hname in ("tr", "bl"):
                                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                            elif hname in ("t", "b"):
                                self.setCursor(Qt.CursorShape.SizeVerCursor)
                            else:
                                self.setCursor(Qt.CursorShape.SizeHorCursor)
                            return
            hit = self._hit_test_item(pt_pdf)
            if isinstance(hit, FormFieldItem) and hit.is_existing:
                self.setCursor(Qt.CursorShape.PointingHandCursor if hit.field_type in ("checkbox", "radio", "dropdown") else Qt.CursorShape.IBeamCursor)
            elif hit is not None:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        elif tool == "text":
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def _show_context_menu(self, pos_w: QPointF) -> None:
        pt_pdf = self._to_pdf_pt(pos_w)
        hit = self._hit_test_item(pt_pdf)
        menu = QMenu(self)

        if hit is not None:
            self.doc_view.select_item(hit.id)
            if isinstance(hit, TextItem):
                menu.addAction("Edit Text", lambda: self.open_inline_text_editor(hit))
            elif isinstance(hit, NoteItem):
                menu.addAction("Edit Comment", lambda: self.open_note_dialog(hit))
            elif isinstance(hit, FormFieldItem):
                menu.addAction("Fill / Edit Value", lambda: self.open_inline_form_editor(hit))
                if not hit.is_existing:
                    def rename_field() -> None:
                        name, ok = QInputDialog.getText(self, "Rename Field", "Field Name:", text=hit.field_name)
                        if ok and name.strip():
                            self.state.push_undo()
                            hit.field_name = name.strip()
                            self.update()
                            self.doc_view.itemsChanged.emit()
                    menu.addAction("Rename Field...", rename_field)
            menu.addSeparator()
            menu.addAction("Duplicate (Ctrl+D)", self.doc_view.duplicate_selected)
            menu.addAction("Bring to Front", lambda: (self.state.bring_to_front(hit.id), self.update(), self.doc_view.itemsChanged.emit()))
            menu.addAction("Send to Back", lambda: (self.state.send_to_back(hit.id), self.update(), self.doc_view.itemsChanged.emit()))
            menu.addSeparator()
            menu.addAction("Delete (Del)", self.doc_view.delete_selected)
        else:
            menu.addAction("Add Text Here", lambda: (self.doc_view.requestToolChange.emit("text"),))
            if self.doc_view.clipboard_item is not None:
                menu.addAction("Paste Here (Ctrl+V)", lambda: self.doc_view.paste_at(self.page_index, pt_pdf.x(), pt_pdf.y()))
            menu.addSeparator()
            menu.addAction("Copy Page Text", self._copy_page_text)

        menu.exec(self.mapToGlobal(pos_w.toPoint()))

    def _copy_page_text(self) -> None:
        txt = self.doc_view.pdf_doc.getAllText(self.page_index).text()
        if txt:
            QApplication.clipboard().setText(txt)


class PdfDocumentView(QScrollArea):
    """Scrollable multi-page PDF editor view with zoom, search, selection & undo/redo."""

    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)
    selectionChanged = Signal(object)  # BaseItem or None
    itemsChanged = Signal()
    requestToolChange = Signal(str)
    toolFinishedAutoSelect = Signal()
    signatureRequested = Signal(int, float, float)
    imageRequested = Signal(int, float, float)

    def __init__(self, state: DocumentState, settings: ToolSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.settings = settings
        self.pdf_doc = QPdfDocument(self)
        self.search_model = QPdfSearchModel(self)
        self.search_model.setDocument(self.pdf_doc)
        self.current_search_index: int = -1

        self.zoom: float = 1.15
        self.current_page: int = 0
        self.selected_item_id: Optional[str] = None
        self.clipboard_item: Optional[dict] = None
        self.page_widgets: List[PdfPageCanvas] = []

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.vbox.setSpacing(18)
        self.vbox.setContentsMargins(24, 20, 24, 30)
        self.setWidget(self.container)

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.viewport().installEventFilter(self)

    def load_working_pdf(self) -> bool:
        if self.state.password:
            self.pdf_doc.setPassword(self.state.password)
        err = self.pdf_doc.load(self.state.working_pdf_path)
        if err != QPdfDocument.Error.None_:
            return False
        existing_forms = [it for it in self.state.items if isinstance(it, FormFieldItem)]
        self.state.text_blocks = extract_editable_text_blocks(
            self.state.working_pdf_path,
            self.state.password,
            self.pdf_doc,
            existing_form_fields=existing_forms,
        )
        self._rebuild_pages()
        return True

    def _rebuild_pages(self) -> None:
        for pw in self.page_widgets:
            pw.close_inline_editor(commit=False)
            self.vbox.removeWidget(pw)
            pw.deleteLater()
        self.page_widgets.clear()

        count = self.pdf_doc.pageCount()
        for i in range(count):
            canvas = PdfPageCanvas(self, i)
            canvas.update_page_size()
            self.vbox.addWidget(canvas, 0, Qt.AlignmentFlag.AlignHCenter)
            self.page_widgets.append(canvas)

        if self.current_page >= count:
            self.current_page = max(0, count - 1)
        self.currentPageChanged.emit(self.current_page)

    def page_count(self) -> int:
        return self.pdf_doc.pageCount()

    def set_zoom(self, new_zoom: float) -> None:
        new_zoom = max(0.25, min(4.0, round(new_zoom, 3)))
        if abs(new_zoom - self.zoom) < 1e-4:
            return
        self.zoom = new_zoom
        for pw in self.page_widgets:
            pw.close_inline_editor(commit=True)
            pw.update_page_size()
        self.zoomChanged.emit(self.zoom)

    def fit_width(self) -> None:
        if not self.page_widgets:
            return
        pt_w, _ = self.page_widgets[self.current_page].page_point_size()
        avail = max(200, self.viewport().width() - 64)
        self.set_zoom(avail / pt_w)

    def fit_page(self) -> None:
        if not self.page_widgets:
            return
        pt_w, pt_h = self.page_widgets[self.current_page].page_point_size()
        avail_w = max(200, self.viewport().width() - 64)
        avail_h = max(200, self.viewport().height() - 48)
        self.set_zoom(min(avail_w / pt_w, avail_h / pt_h))

    def set_current_page(self, idx: int, scroll: bool = True) -> None:
        if not self.page_widgets:
            return
        idx = max(0, min(len(self.page_widgets) - 1, idx))
        if scroll:
            target = self.page_widgets[idx]
            self.verticalScrollBar().setValue(max(0, target.y() - 16))
        if idx != self.current_page:
            self.current_page = idx
            self.currentPageChanged.emit(idx)

    def _on_scroll(self) -> None:
        if not self.page_widgets:
            return
        vp_mid = self.verticalScrollBar().value() + self.viewport().height() * 0.35
        best_idx = 0
        for i, pw in enumerate(self.page_widgets):
            if pw.y() <= vp_mid:
                best_idx = i
            else:
                break
        if best_idx != self.current_page:
            self.current_page = best_idx
            self.currentPageChanged.emit(best_idx)

    def select_item(self, item_id: Optional[str]) -> None:
        if self.selected_item_id == item_id:
            return
        self.selected_item_id = item_id
        self.refresh_all_pages()
        self.selectionChanged.emit(self.state.find_item(item_id) if item_id else None)

    def refresh_all_pages(self) -> None:
        for pw in self.page_widgets:
            pw.update()

    def close_all_inline_editors(self) -> None:
        for pw in self.page_widgets:
            pw.close_inline_editor(commit=True)

    def delete_selected(self) -> None:
        if not self.selected_item_id:
            return
        self.close_all_inline_editors()
        if self.state.remove_item(self.selected_item_id):
            self.selected_item_id = None
            self.refresh_all_pages()
            self.selectionChanged.emit(None)
            self.itemsChanged.emit()

    def copy_selected(self) -> None:
        if not self.selected_item_id:
            return
        it = self.state.find_item(self.selected_item_id)
        if it is not None:
            self.clipboard_item = copy.deepcopy(it.to_dict())

    def paste_at(self, page_idx: Optional[int] = None, x: Optional[float] = None, y: Optional[float] = None) -> None:
        if not self.clipboard_item:
            return
        d = copy.deepcopy(self.clipboard_item)
        d["id"] = new_id()
        d["page"] = self.current_page if page_idx is None else page_idx
        if x is not None and y is not None:
            dx = x - d.get("x", 0)
            dy = y - d.get("y", 0)
            d["x"] = x
            d["y"] = y
            if "x2" in d:
                d["x2"] += dx
                d["y2"] += dy
            if "points" in d and d["points"]:
                d["points"] = [[p[0] + dx, p[1] + dy] for p in d["points"]]
        else:
            d["x"] = d.get("x", 72) + 16
            d["y"] = d.get("y", 72) + 16
            if "x2" in d:
                d["x2"] += 16
                d["y2"] += 16
            if "points" in d and d["points"]:
                d["points"] = [[p[0] + 16, p[1] + 16] for p in d["points"]]
        if d.get("kind") == "form_field":
            d["is_existing"] = False
            d["field_name"] = f"{d.get('field_name', 'Field')}_copy"
        new_it = item_from_dict(d)
        self.state.add_item(new_it)
        self.select_item(new_it.id)
        self.itemsChanged.emit()

    def duplicate_selected(self) -> None:
        self.copy_selected()
        if self.selected_item_id:
            it = self.state.find_item(self.selected_item_id)
            if it:
                self.paste_at(it.page)

    def nudge_selected(self, dx: float, dy: float) -> None:
        if not self.selected_item_id:
            return
        it = self.state.find_item(self.selected_item_id)
        if it is None or it.locked:
            return
        self.state.push_undo()
        if isinstance(it, InkItem):
            it.points = [[p[0] + dx, p[1] + dy] for p in it.points]
        elif isinstance(it, ShapeItem) and it.shape_type in ("line", "arrow"):
            it.x += dx
            it.y += dy
            it.x2 += dx
            it.y2 += dy
        else:
            it.x += dx
            it.y += dy
        self.refresh_all_pages()
        self.itemsChanged.emit()

    def set_search_query(self, query: str) -> int:
        self.search_model.setSearchString(query)
        # Ensure all pages are scanned synchronously for immediate match count
        if query:
            for p in range(self.pdf_doc.pageCount()):
                self.search_model.resultsOnPage(p)
        count = self.search_model.count()
        self.current_search_index = 0 if count > 0 else -1
        if count > 0:
            self._jump_to_search_result(0)
        self.refresh_all_pages()
        return count

    def next_search_result(self, step: int = 1) -> Tuple[int, int]:
        count = self.search_model.count()
        if count <= 0:
            return 0, 0
        self.current_search_index = (self.current_search_index + step) % count
        self._jump_to_search_result(self.current_search_index)
        self.refresh_all_pages()
        return self.current_search_index + 1, count

    def _jump_to_search_result(self, idx: int) -> None:
        link = self.search_model.resultAtIndex(idx)
        if link is not None and 0 <= link.page() < len(self.page_widgets):
            pw = self.page_widgets[link.page()]
            y_off = pw.y() + int(link.location().y() * self.zoom) - 120
            self.verticalScrollBar().setValue(max(0, y_off))
            self.current_page = link.page()
            self.currentPageChanged.emit(self.current_page)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.viewport() and event.type() == QEvent.Type.Wheel:
            we: QWheelEvent = event
            if we.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = we.angleDelta().y()
                factor = 1.12 if delta > 0 else (1.0 / 1.12)
                self.set_zoom(self.zoom * factor)
                return True
        return super().eventFilter(obj, event)
