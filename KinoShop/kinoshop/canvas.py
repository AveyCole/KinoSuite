"""Interactive High-FPS KinoShop Canvas with Tablet Pressure, Marching Ants,
Pattern Preview, Print Marks, Puppet/Perspective Warp, Slicing, Rulers, Count & Contextual Taskbar."""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTabletEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QPushButton, QWidget

from .brushes import (
    BrushSettings,
    flood_fill_layer,
    paint_stroke_segment,
    render_gradient,
)
from .engine import composite_dirty_rect, composite_document, composite_layer_list
from .models import Artboard, CommentPin, CountMarker, KinoDocument, Layer, SliceRect
from .photo_ops import (
    apply_perspective_warp,
    apply_puppet_warp,
    magic_wand_select,
    quick_select_grow,
    spot_heal_stroke,
)


def rgba_to_qimage(rgba: np.ndarray, copy: bool = True) -> QImage:
    h, w = rgba.shape[:2]
    arr = np.ascontiguousarray(rgba)
    qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return qimg.copy() if copy else qimg


class ContextualTaskbar(QWidget):
    """Floating Photoshop / KinoSuite Contextual Taskbar anchored over the canvas."""

    actionRequested = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("ContextualBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 6, 10, 6)
        self._layout.setSpacing(6)
        self._buttons: List[QPushButton] = []
        self._current_mode: str = ""
        self.set_mode("idle")

    def set_mode(self, mode: str) -> None:
        if mode == self._current_mode:
            return
        self._current_mode = mode
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._buttons.clear()

        if mode == "selection":
            specs = [
                ("Content-Aware Fill", "caf", "PrimaryButton"),
                ("Select & Mask", "select_mask", ""),
                ("Add Mask", "add_mask", ""),
                ("Invert", "invert_sel", ""),
                ("Deselect", "deselect", ""),
            ]
        elif mode in ("crop", "puppet_warp", "perspective_warp"):
            label = {"crop": "Crop", "puppet_warp": "Puppet Warp", "perspective_warp": "Perspective Warp"}[mode]
            specs = [
                (f"Commit {label}", "commit_mode", "PrimaryButton"),
                ("Cancel", "cancel_mode", "DangerButton"),
            ]
        elif mode == "text":
            specs = [
                ("Edit Text", "edit_text", "PrimaryButton"),
                ("Warp Text", "warp_text", ""),
                ("Type on Path", "type_on_path", ""),
                ("Layer Styles (fx)", "layer_styles", ""),
            ]
        else:
            specs = [
                ("Select Subject", "select_subject", "PrimaryButton"),
                ("Select Sky", "select_sky", ""),
                ("Remove BG", "remove_bg", ""),
                ("Sky Replace", "sky_replace", ""),
                ("Harmonize", "harmonize", ""),
                ("Camera Raw", "camera_raw", ""),
            ]

        for title, cmd, obj_name in specs:
            btn = QPushButton(title, self)
            if obj_name:
                btn.setObjectName(obj_name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _=False, c=cmd: self.actionRequested.emit(c))
            self._layout.addWidget(btn)
            self._buttons.append(btn)
        self.adjustSize()


class KinoCanvas(QWidget):
    """Main interactive image editing viewport for a single KinoDocument."""

    documentChanged = Signal()
    selectionChanged = Signal()
    colorPicked = Signal(tuple)
    cursorMoved = Signal(int, int, str)
    statusMessage = Signal(str)
    contextAction = Signal(str)

    def __init__(self, doc: KinoDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TabletTracking, True)

        # Viewport transform
        self.zoom: float = 0.85
        self.pan: QPointF = QPointF(0.0, 0.0)
        self.view_rotation: float = 0.0
        self.show_rulers: bool = True
        self.show_guides: bool = True
        self.show_grid: bool = False
        self.show_slices: bool = False
        self.show_comments: bool = True
        self.show_contextual_bar: bool = True

        # Active tool state
        self.tool: str = "move"
        self.fg_color: Tuple[int, int, int] = (49, 168, 255)
        self.bg_color: Tuple[int, int, int] = (18, 21, 28)
        self.brush_settings: BrushSettings = BrushSettings()
        self.editing_mask: bool = False
        self.shape_subtool: str = "rounded_rect"
        self.gradient_style: str = "Linear"
        self.dodge_burn_mode: str = "dodge"  # dodge | burn
        self.blur_smudge_mode: str = "blur"  # blur | smudge
        self.wand_tolerance: int = 32
        self.count_mode: bool = False  # False=Ruler, True=Count tool

        # Cached composite QImage/QPixmap & dirty-rect coalescing
        self._comp_rgba: Optional[np.ndarray] = None
        self._comp_qimg: Optional[QImage] = None
        self._comp_pixmap: Optional[QPixmap] = None
        self._checker_pm: QPixmap = self._make_checker()
        self._last_sel_id: int = -1
        self._pending_composite: bool = False
        self._dirty_rect: Optional[Tuple[int, int, int, int]] = None
        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.setInterval(12)  # ~80 FPS cap during continuous drag/brush
        self._frame_timer.timeout.connect(self._flush_composite)

        # Interaction transient states
        self._dragging: bool = False
        self._space_pan: bool = False
        self._last_screen: QPointF = QPointF()
        self._start_doc: QPointF = QPointF()
        self._last_doc: QPointF = QPointF()
        self._cur_doc: QPointF = QPointF()
        self._tablet_pressure: float = 1.0
        self._move_orig_offset: Tuple[int, int] = (0, 0)

        # Tool-specific temp state
        self._lasso_pts: List[Tuple[float, float]] = []
        self._poly_pts: List[Tuple[float, float]] = []
        self._pen_pts: List[Tuple[float, float]] = []
        self._quick_pts: List[Tuple[int, int]] = []
        self._heal_mask: Optional[np.ndarray] = None
        self._clone_origin: Optional[Tuple[int, int]] = None
        self._clone_offset: Tuple[int, int] = (0, 0)
        self._clone_snapshot: Optional[np.ndarray] = None
        self._history_source_rgba: Optional[np.ndarray] = None

        # Crop / Puppet Warp / Perspective Warp active modes
        self._crop_rect: Optional[QRectF] = None
        self._puppet_orig_pins: List[Tuple[float, float]] = []
        self._puppet_moved_pins: List[Tuple[float, float]] = []
        self._puppet_base_img: Optional[np.ndarray] = None
        self._puppet_drag_idx: int = -1

        self._persp_src_quad: List[Tuple[float, float]] = []
        self._persp_dst_quad: List[Tuple[float, float]] = []
        self._persp_base_img: Optional[np.ndarray] = None
        self._persp_drag_idx: int = -1

        # Marching ants animation
        self._ants_phase: int = 0
        self._ants_contours: List[np.ndarray] = []
        self._ants_timer = QTimer(self)
        self._ants_timer.timeout.connect(self._tick_ants)
        self._ants_timer.start(140)

        # Contextual Taskbar
        self.context_bar = ContextualTaskbar(self)
        self.context_bar.actionRequested.connect(self._on_context_action)

        self.refresh_composite()

    def _make_checker(self) -> QPixmap:
        pm = QPixmap(16, 16)
        p = QPainter(pm)
        p.fillRect(0, 0, 16, 16, QColor("#252A34"))
        p.fillRect(0, 0, 8, 8, QColor("#303644"))
        p.fillRect(8, 8, 8, 8, QColor("#303644"))
        p.end()
        return pm

    def _tick_ants(self) -> None:
        if self.doc.selection is not None:
            self._ants_phase = (self._ants_phase + 2) % 16
            self.update()

    def set_document(self, doc: KinoDocument) -> None:
        self.doc = doc
        self._reset_modes()
        self.refresh_composite()
        self.fit_to_view()

    def set_tool(self, tool_name: str) -> None:
        if self.tool in ("crop", "puppet_warp", "perspective_warp") and tool_name != self.tool:
            self.cancel_active_mode()
        self.tool = tool_name
        self._poly_pts.clear()
        self._pen_pts.clear()
        if tool_name == "crop":
            self._crop_rect = QRectF(0, 0, self.doc.width, self.doc.height)
        elif tool_name == "puppet_warp":
            lyr = self.doc.ensure_raster_layer()
            self._puppet_base_img = lyr.image.copy()
            self._puppet_orig_pins.clear()
            self._puppet_moved_pins.clear()
            self.statusMessage.emit("Puppet Warp: Click to add pins, drag pins to deform, Enter to commit.")
        elif tool_name == "perspective_warp":
            lyr = self.doc.ensure_raster_layer()
            self._persp_base_img = lyr.image.copy()
            m_x, m_y = self.doc.width * 0.12, self.doc.height * 0.12
            quad = [
                (m_x, m_y),
                (self.doc.width - m_x, m_y),
                (self.doc.width - m_x, self.doc.height - m_y),
                (m_x, self.doc.height - m_y),
            ]
            self._persp_src_quad = list(quad)
            self._persp_dst_quad = list(quad)
            self.statusMessage.emit("Perspective Warp: Drag the 4 corner pins and press Enter to commit.")
        self._update_context_bar_mode()
        self.update()

    def _reset_modes(self) -> None:
        self._crop_rect = None
        self._puppet_orig_pins.clear()
        self._puppet_moved_pins.clear()
        self._puppet_base_img = None
        self._persp_src_quad.clear()
        self._persp_dst_quad.clear()
        self._persp_base_img = None
        self._poly_pts.clear()
        self._pen_pts.clear()

    def _update_context_bar_mode(self) -> None:
        if self.tool in ("crop", "puppet_warp", "perspective_warp"):
            self.context_bar.set_mode(self.tool)
        elif self.doc.selection is not None and float(self.doc.selection.max()) > 0.05:
            self.context_bar.set_mode("selection")
        elif self.doc.active_layer() and self.doc.active_layer().kind == "text":
            self.context_bar.set_mode("text")
        else:
            self.context_bar.set_mode("idle")
        self._reposition_context_bar()

    def _reposition_context_bar(self) -> None:
        self.context_bar.setVisible(self.show_contextual_bar)
        if not self.show_contextual_bar:
            return
        bw = self.context_bar.sizeHint().width()
        bh = self.context_bar.sizeHint().height()
        x = max(24, (self.width() - bw) // 2)
        y = max(28, self.height() - bh - 16)
        self.context_bar.move(x, y)

    def _on_context_action(self, cmd: str) -> None:
        if cmd == "commit_mode":
            self.commit_active_mode()
        elif cmd == "cancel_mode":
            self.cancel_active_mode()
        else:
            self.contextAction.emit(cmd)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_context_bar()

    def fit_to_view(self) -> None:
        avail_w = max(100, self.width() - 60)
        avail_h = max(100, self.height() - 90)
        self.zoom = min(avail_w / max(1, self.doc.width), avail_h / max(1, self.doc.height), 1.5)
        self.pan = QPointF(0.0, 0.0)
        self.update()

    def schedule_composite(self, dirty_rect: Optional[Tuple[int, int, int, int]] = None) -> None:
        """Coalesce rapid mouseMove updates into smooth 60+ FPS frames with optional dirty-rect fast-path."""
        if dirty_rect is None:
            self._dirty_rect = None
        elif not self._pending_composite:
            self._dirty_rect = dirty_rect
        elif self._dirty_rect is not None:
            self._dirty_rect = (
                min(self._dirty_rect[0], dirty_rect[0]),
                min(self._dirty_rect[1], dirty_rect[1]),
                max(self._dirty_rect[2], dirty_rect[2]),
                max(self._dirty_rect[3], dirty_rect[3]),
            )
        if not self._pending_composite:
            self._pending_composite = True
            self._frame_timer.start()

    def _flush_composite(self) -> None:
        self._pending_composite = False
        dr = self._dirty_rect
        self._dirty_rect = None
        if (
            dr is not None
            and self._comp_rgba is not None
            and self._comp_rgba.shape[:2] == (self.doc.height, self.doc.width)
            and self.brush_settings.symmetry == "None"
            and composite_dirty_rect(self.doc, self._comp_rgba, dr)
        ):
            self._comp_qimg = rgba_to_qimage(self._comp_rgba, copy=False)
            if self._comp_pixmap is not None and self._comp_pixmap.size() == self._comp_qimg.size():
                # Fast partial QPixmap blit of ONLY the dirty rectangle!
                x0, y0, x1, y1 = max(0, dr[0]), max(0, dr[1]), min(self.doc.width, dr[2]), min(self.doc.height, dr[3])
                pm_p = QPainter(self._comp_pixmap)
                pm_p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                pm_p.drawImage(x0, y0, self._comp_qimg, x0, y0, x1 - x0, y1 - y0)
                pm_p.end()
            else:
                self._comp_pixmap = QPixmap.fromImage(self._comp_qimg)
            self.update()
            return
        self.refresh_composite()

    def refresh_composite(self) -> None:
        self._pending_composite = False
        self._dirty_rect = None
        self._comp_rgba = np.ascontiguousarray(composite_document(self.doc, apply_view_effects=True))
        self._comp_qimg = rgba_to_qimage(self._comp_rgba, copy=False)
        self._comp_pixmap = QPixmap.fromImage(self._comp_qimg)
        sel_id = id(self.doc.selection) if self.doc.selection is not None else 0
        if sel_id != self._last_sel_id:
            self._last_sel_id = sel_id
            self.rebuild_selection_contours()
        self._update_context_bar_mode()
        self.update()

    def rebuild_selection_contours(self) -> None:
        self._ants_contours = []
        if self.doc.selection is not None and float(self.doc.selection.max()) > 0.05:
            bw = (self.doc.selection > 0.25).astype(np.uint8) * 255
            cnts, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            self._ants_contours = list(cnts)

    # ---- Coordinate conversion ----
    def doc_rect_on_screen(self) -> QRectF:
        dw = self.doc.width * self.zoom
        dh = self.doc.height * self.zoom
        cx = self.width() * 0.5 + self.pan.x()
        cy = self.height() * 0.5 + self.pan.y()
        return QRectF(cx - dw * 0.5, cy - dh * 0.5, dw, dh)

    def screen_to_doc(self, pt: QPointF) -> QPointF:
        r = self.doc_rect_on_screen()
        return QPointF((pt.x() - r.left()) / max(self.zoom, 1e-4), (pt.y() - r.top()) / max(self.zoom, 1e-4))

    def doc_to_screen(self, pt: QPointF) -> QPointF:
        r = self.doc_rect_on_screen()
        return QPointF(r.left() + pt.x() * self.zoom, r.top() + pt.y() * self.zoom)

    # ---- Commit / Cancel interactive warp or crop modes ----
    def commit_active_mode(self) -> None:
        if self.tool == "crop" and self._crop_rect is not None:
            r = self._crop_rect.normalized()
            x0 = max(0, int(round(r.left())))
            y0 = max(0, int(round(r.top())))
            x1 = min(self.doc.width, int(round(r.right())))
            y1 = min(self.doc.height, int(round(r.bottom())))
            if x1 - x0 >= 8 and y1 - y0 >= 8:
                nw, nh = x1 - x0, y1 - y0
                for lyr in self.doc.iter_all_layers():
                    if lyr.image is not None and lyr.image.shape[:2] == (self.doc.height, self.doc.width):
                        lyr.image = lyr.image[y0:y1, x0:x1].copy()
                    elif lyr.kind == "text" and lyr.text_data is not None:
                        lyr.text_data.x -= x0
                        lyr.text_data.y -= y0
                    elif lyr.kind == "vector" and lyr.vector_data is not None:
                        vx, vy, vw, vh = lyr.vector_data.rect
                        lyr.vector_data.rect = (vx - x0, vy - y0, vw, vh)
                    else:
                        lyr.offset_x -= x0
                        lyr.offset_y -= y0
                    if lyr.mask is not None and lyr.mask.shape == (self.doc.height, self.doc.width):
                        lyr.mask = lyr.mask[y0:y1, x0:x1].copy()
                self.doc.width, self.doc.height = nw, nh
                self.doc.selection = None
                self.doc.artboards = [Artboard(name="Artboard 1", x=0, y=0, width=nw, height=nh)]
                self.doc.push_history("Crop Image")
                self.doc.metadata.record_provenance("Cropped Image", details=f"{nw}x{nh}")
                self.refresh_composite()
                self.documentChanged.emit()
                self.statusMessage.emit(f"Cropped to {nw} × {nh} px.")
            self.set_tool("move")

        elif self.tool == "puppet_warp":
            self.doc.push_history("Puppet Warp")
            self.doc.metadata.record_provenance("Applied Puppet Warp")
            self._puppet_base_img = None
            self.set_tool("move")
            self.documentChanged.emit()
            self.statusMessage.emit("Puppet Warp committed.")

        elif self.tool == "perspective_warp":
            self.doc.push_history("Perspective Warp")
            self.doc.metadata.record_provenance("Applied Perspective Warp")
            self._persp_base_img = None
            self.set_tool("move")
            self.documentChanged.emit()
            self.statusMessage.emit("Perspective Warp committed.")

    def cancel_active_mode(self) -> None:
        if self.tool == "puppet_warp" and self._puppet_base_img is not None:
            lyr = self.doc.active_layer()
            if lyr and lyr.image is not None:
                lyr.image = self._puppet_base_img.copy()
                self.refresh_composite()
        elif self.tool == "perspective_warp" and self._persp_base_img is not None:
            lyr = self.doc.active_layer()
            if lyr and lyr.image is not None:
                lyr.image = self._persp_base_img.copy()
                self.refresh_composite()
        self._reset_modes()
        self.tool = "move"
        self._update_context_bar_mode()
        self.update()

    # ---- Painting helper ----
    def _paint_segment_active(self, p0: Tuple[float, float], p1: Tuple[float, float], pressure: float) -> None:
        # Check if editing an Extra Channel (Alpha / Spot)
        for ec in self.doc.extra_channels:
            if self.doc.active_channel == ec.uid and ec.data is not None:
                paint_stroke_segment(
                    ec.data, p0, p1, self.fg_color, self.brush_settings, pressure=pressure,
                    mode="mask_paint", selection=self.doc.selection,
                )
                return

        lyr = self.doc.active_layer()
        if self.editing_mask and lyr is not None:
            if lyr.mask is None:
                lyr.mask = np.full((self.doc.height, self.doc.width), 255, dtype=np.uint8)
            paint_stroke_segment(
                lyr.mask, p0, p1, self.fg_color, self.brush_settings, pressure=pressure,
                mode="mask_paint", selection=self.doc.selection,
            )
            lyr.invalidate_cache()
            return

        lyr = self.doc.ensure_raster_layer()
        if lyr.locked or lyr.image is None:
            return
        mode_map = {
            "brush": "brush",
            "mixer_brush": "mixer",
            "eraser": "eraser",
            "dodge_burn": self.dodge_burn_mode,
            "blur_smudge": self.blur_smudge_mode,
            "clone": "clone",
            "history_brush": "history",
        }
        mode = mode_map.get(self.tool, "brush")
        # Translate doc coords to layer local coords
        lp0 = (p0[0] - lyr.offset_x, p0[1] - lyr.offset_y)
        lp1 = (p1[0] - lyr.offset_x, p1[1] - lyr.offset_y)
        paint_stroke_segment(
            lyr.image,
            lp0,
            lp1,
            self.fg_color,
            self.brush_settings,
            pressure=pressure,
            mode=mode,
            selection=self.doc.selection,
            clone_source=self._clone_snapshot,
            clone_offset=self._clone_offset,
            history_source=self._history_source_rgba,
        )
        lyr.invalidate_cache()

    # ---- Events ----
    def tabletEvent(self, event: QTabletEvent) -> None:
        self._tablet_pressure = max(0.05, min(1.0, float(event.pressure())))
        # Let Qt synthesize standard mouse events with our updated pressure
        event.ignore()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        old_doc = self.screen_to_doc(event.position())
        self.zoom = max(0.08, min(24.0, self.zoom * factor))
        new_scr = self.doc_to_screen(old_doc)
        self.pan += event.position() - new_scr
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_pan = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.tool in ("crop", "puppet_warp", "perspective_warp"):
                self.commit_active_mode()
                return
            if self.tool == "poly_lasso" and len(self._poly_pts) >= 3:
                self._commit_poly_lasso()
                return
            if self.tool == "pen" and len(self._pen_pts) >= 2:
                self._commit_pen_path()
                return
        if event.key() == Qt.Key.Key_Escape:
            if self.tool in ("crop", "puppet_warp", "perspective_warp"):
                self.cancel_active_mode()
                return
            self._poly_pts.clear()
            self._pen_pts.clear()
            self.update()
            return
        if event.key() == Qt.Key.Key_BracketLeft:
            self.brush_settings.size = max(2.0, self.brush_settings.size * 0.82)
            self.statusMessage.emit(f"Brush Size: {int(self.brush_settings.size)} px")
            self.update()
            return
        if event.key() == Qt.Key.Key_BracketRight:
            self.brush_settings.size = min(400.0, self.brush_settings.size * 1.2)
            self.statusMessage.emit(f"Brush Size: {int(self.brush_settings.size)} px")
            self.update()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_pan = False
            self.unsetCursor()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        pos = event.position()
        dpt = self.screen_to_doc(pos)
        self._last_screen = pos
        self._start_doc = dpt
        self._last_doc = dpt
        self._cur_doc = dpt

        if event.button() == Qt.MouseButton.MiddleButton or self._space_pan or self.tool == "hand":
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.tool == "zoom":
            factor = (1.0 / 1.35) if (event.modifiers() & Qt.KeyboardModifier.AltModifier) else 1.35
            self.zoom = max(0.08, min(24.0, self.zoom * factor))
            self.update()
            return

        if self.tool == "eyedropper":
            self._pick_color_at(dpt)
            self._dragging = True
            return

        if self.tool == "move":
            lyr = self.doc.active_layer()
            if lyr and not lyr.locked:
                self._move_orig_offset = (lyr.offset_x, lyr.offset_y)
                self._dragging = True
            return

        if self.tool == "magic_wand":
            comp = self._comp_rgba if self._comp_rgba is not None else composite_document(self.doc)
            mask = magic_wand_select(comp, int(dpt.x()), int(dpt.y()), tolerance=self.wand_tolerance)
            self._apply_new_selection(mask, event.modifiers())
            return

        if self.tool == "quick_select":
            self._quick_pts = [(int(dpt.x()), int(dpt.y()))]
            self._dragging = True
            return

        if self.tool == "lasso":
            self._lasso_pts = [(dpt.x(), dpt.y())]
            self._dragging = True
            return

        if self.tool == "poly_lasso":
            self._poly_pts.append((dpt.x(), dpt.y()))
            self.update()
            return

        if self.tool == "pen":
            self._pen_pts.append((dpt.x(), dpt.y()))
            self.statusMessage.emit(f"Pen Tool: {len(self._pen_pts)} points placed (Enter to finish path).")
            self.update()
            return

        if self.tool in ("marquee_rect", "marquee_ellipse", "crop", "slice", "shape", "gradient", "artboard"):
            self._dragging = True
            return

        if self.tool == "bucket":
            lyr = self.doc.ensure_raster_layer()
            if lyr.image is not None:
                flood_fill_layer(
                    lyr.image,
                    int(dpt.x() - lyr.offset_x),
                    int(dpt.y() - lyr.offset_y),
                    self.fg_color + (255,),
                    tolerance=self.wand_tolerance,
                    selection=self.doc.selection,
                )
                lyr.invalidate_cache()
                self.doc.push_history("Paint Bucket Fill")
                self.refresh_composite()
                self.documentChanged.emit()
            return

        if self.tool in ("spot_heal", "remove"):
            self._heal_mask = np.zeros((self.doc.height, self.doc.width), dtype=np.uint8)
            cv2.circle(self._heal_mask, (int(dpt.x()), int(dpt.y())), max(4, int(self.brush_settings.size * 0.5)), 255, -1)
            self._dragging = True
            self.update()
            return

        if self.tool == "clone":
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self._clone_origin = (int(dpt.x()), int(dpt.y()))
                self.statusMessage.emit(f"Clone Stamp source set to ({int(dpt.x())}, {int(dpt.y())}).")
                self.update()
                return
            if self._clone_origin is None:
                self._clone_origin = (max(0, int(dpt.x()) - 40), max(0, int(dpt.y()) - 40))
            self._clone_offset = (self._clone_origin[0] - int(dpt.x()), self._clone_origin[1] - int(dpt.y()))
            lyr = self.doc.ensure_raster_layer()
            self._clone_snapshot = lyr.image.copy()
            self._dragging = True
            self._paint_segment_active((dpt.x(), dpt.y()), (dpt.x(), dpt.y()), self._tablet_pressure)
            self.refresh_composite()
            return

        if self.tool == "history_brush":
            src_entry = self.doc.get_history_brush_source()
            if src_entry is not None:
                if src_entry.composite_cache is None:
                    src_entry.composite_cache = composite_layer_list(src_entry.layers, src_entry.width, src_entry.height)
                self._history_source_rgba = src_entry.composite_cache
            self._dragging = True
            self._paint_segment_active((dpt.x(), dpt.y()), (dpt.x(), dpt.y()), self._tablet_pressure)
            self.refresh_composite()
            return

        if self.tool in ("brush", "mixer_brush", "eraser", "dodge_burn", "blur_smudge"):
            if self.tool == "mixer_brush":
                self.brush_settings.mixer_reservoir = None
            self._dragging = True
            self._paint_segment_active((dpt.x(), dpt.y()), (dpt.x(), dpt.y()), self._tablet_pressure)
            pad = int(self.brush_settings.size * 0.75) + 8
            self.schedule_composite((int(dpt.x()) - pad, int(dpt.y()) - pad, int(dpt.x()) + pad, int(dpt.y()) + pad))
            return

        if self.tool == "text":
            txt, ok = QInputDialog.getText(self, "Add Type Layer", "Enter text:", text="KinoShop Studio")
            if ok and txt.strip():
                self.doc.add_text_layer(txt.strip(), x=dpt.x(), y=dpt.y(), color=self.fg_color + (255,))
                self.doc.push_history("Add Type Layer")
                self.refresh_composite()
                self.documentChanged.emit()
            return

        if self.tool == "puppet_warp":
            # Check if clicking near an existing pin
            self._puppet_drag_idx = -1
            for i, (px, py) in enumerate(self._puppet_moved_pins):
                if math.hypot(px - dpt.x(), py - dpt.y()) < 14.0 / max(self.zoom, 0.2):
                    self._puppet_drag_idx = i
                    self._dragging = True
                    return
            self._puppet_orig_pins.append((dpt.x(), dpt.y()))
            self._puppet_moved_pins.append((dpt.x(), dpt.y()))
            self._puppet_drag_idx = len(self._puppet_moved_pins) - 1
            self._dragging = True
            self.update()
            return

        if self.tool == "perspective_warp":
            self._persp_drag_idx = -1
            for i, (px, py) in enumerate(self._persp_dst_quad):
                if math.hypot(px - dpt.x(), py - dpt.y()) < 18.0 / max(self.zoom, 0.2):
                    self._persp_drag_idx = i
                    self._dragging = True
                    return
            return

        if self.tool == "ruler_count":
            if self.count_mode or (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                idx = len(self.doc.count_markers) + 1
                self.doc.count_markers.append(CountMarker(index=idx, x=dpt.x(), y=dpt.y()))
                self.statusMessage.emit(f"Count Marker #{idx} placed at ({int(dpt.x())}, {int(dpt.y())}).")
                self.update()
            else:
                self.doc.ruler_line = (dpt.x(), dpt.y(), dpt.x(), dpt.y())
                self._dragging = True
            return

        if self.tool == "comment":
            txt, ok = QInputDialog.getText(self, "Add Review Comment", "Comment note:")
            if ok and txt.strip():
                self.doc.comments.append(CommentPin(author=self.doc.metadata.author or "Artist", text=txt.strip(), x=dpt.x(), y=dpt.y()))
                self.documentChanged.emit()
                self.update()
            return

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        dpt = self.screen_to_doc(pos)
        self._cur_doc = dpt
        ix, iy = int(dpt.x()), int(dpt.y())
        col_str = ""
        if self._comp_rgba is not None and 0 <= ix < self.doc.width and 0 <= iy < self.doc.height:
            r, g, b, a = [int(v) for v in self._comp_rgba[iy, ix]]
            col_str = f"RGB({r},{g},{b}) A:{a}"
        self.cursorMoved.emit(ix, iy, col_str)

        if not self._dragging:
            if self.tool in ("brush", "mixer_brush", "eraser", "spot_heal", "remove", "clone", "history_brush", "dodge_burn", "blur_smudge"):
                self.update()
            return

        if self._space_pan or self.tool == "hand" or (event.buttons() & Qt.MouseButton.MiddleButton):
            self.pan += pos - self._last_screen
            self._last_screen = pos
            self.update()
            return

        if self.tool == "eyedropper":
            self._pick_color_at(dpt)
            return

        if self.tool == "move":
            lyr = self.doc.active_layer()
            if lyr and not lyr.locked:
                dx = int(round(dpt.x() - self._start_doc.x()))
                dy = int(round(dpt.y() - self._start_doc.y()))
                lyr.offset_x = self._move_orig_offset[0] + dx
                lyr.offset_y = self._move_orig_offset[1] + dy
                self.schedule_composite()
            return

        if self.tool == "lasso":
            self._lasso_pts.append((dpt.x(), dpt.y()))
            self.update()
            return

        if self.tool == "quick_select":
            self._quick_pts.append((int(dpt.x()), int(dpt.y())))
            self.update()
            return

        if self.tool in ("spot_heal", "remove") and self._heal_mask is not None:
            cv2.line(
                self._heal_mask,
                (int(self._last_doc.x()), int(self._last_doc.y())),
                (int(dpt.x()), int(dpt.y())),
                255,
                max(4, int(self.brush_settings.size)),
            )
            self._last_doc = dpt
            self.update()
            return

        if self.tool in ("brush", "mixer_brush", "eraser", "dodge_burn", "blur_smudge", "clone", "history_brush"):
            p0 = (self._last_doc.x(), self._last_doc.y())
            p1 = (dpt.x(), dpt.y())
            self._paint_segment_active(p0, p1, self._tablet_pressure)
            self._last_doc = dpt
            pad = int(self.brush_settings.size * 0.75) + 8
            dr = (
                int(min(p0[0], p1[0])) - pad,
                int(min(p0[1], p1[1])) - pad,
                int(max(p0[0], p1[0])) + pad,
                int(max(p0[1], p1[1])) + pad,
            )
            self.schedule_composite(dr)
            return

        if self.tool == "crop":
            self._crop_rect = QRectF(self._start_doc, dpt).normalized()
            self.update()
            return

        if self.tool == "puppet_warp" and self._puppet_drag_idx >= 0 and self._puppet_base_img is not None:
            self._puppet_moved_pins[self._puppet_drag_idx] = (dpt.x(), dpt.y())
            lyr = self.doc.active_layer()
            if lyr and lyr.image is not None and len(self._puppet_orig_pins) >= 2:
                lyr.image = apply_puppet_warp(self._puppet_base_img, self._puppet_orig_pins, self._puppet_moved_pins)
                self.refresh_composite()
            else:
                self.update()
            return

        if self.tool == "perspective_warp" and self._persp_drag_idx >= 0 and self._persp_base_img is not None:
            self._persp_dst_quad[self._persp_drag_idx] = (dpt.x(), dpt.y())
            lyr = self.doc.active_layer()
            if lyr and lyr.image is not None:
                lyr.image = apply_perspective_warp(self._persp_base_img, self._persp_src_quad, self._persp_dst_quad)
                self.refresh_composite()
            return

        if self.tool == "ruler_count" and self.doc.ruler_line is not None:
            x0, y0, _, _ = self.doc.ruler_line
            self.doc.ruler_line = (x0, y0, dpt.x(), dpt.y())
            dist_px = math.hypot(dpt.x() - x0, dpt.y() - y0)
            dist_u = dist_px / max(self.doc.pixels_per_unit, 1e-4)
            ang = math.degrees(math.atan2(dpt.y() - y0, dpt.x() - x0))
            self.statusMessage.emit(f"Measure: {dist_px:.1f} px ({dist_u:.2f} {self.doc.measure_unit}) · Angle: {ang:.1f}°")
            self.update()
            return

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        if self._space_pan or self.tool == "hand":
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._space_pan else Qt.CursorShape.ArrowCursor)
            return

        dpt = self.screen_to_doc(event.position())
        self._tablet_pressure = 1.0

        if self.tool == "move":
            self.doc.push_history("Move Layer")
            self.documentChanged.emit()

        elif self.tool in ("brush", "mixer_brush", "eraser", "dodge_burn", "blur_smudge", "clone", "history_brush"):
            self.doc.push_history(self.tool.replace("_", " ").title())
            self.documentChanged.emit()

        elif self.tool in ("spot_heal", "remove") and self._heal_mask is not None:
            lyr = self.doc.ensure_raster_layer()
            if lyr.image is not None:
                method = "ns" if self.tool == "remove" else "telea"
                lyr.image = spot_heal_stroke(lyr.image, self._heal_mask, radius=max(5, int(self.brush_settings.size * 0.3)), method=method)
                self.doc.push_history("Remove Tool" if self.tool == "remove" else "Spot Healing")
                self.refresh_composite()
                self.documentChanged.emit()
            self._heal_mask = None
            self.update()

        elif self.tool in ("marquee_rect", "marquee_ellipse"):
            r = QRectF(self._start_doc, dpt).normalized()
            if r.width() >= 2 and r.height() >= 2:
                mask = np.zeros((self.doc.height, self.doc.width), dtype=np.float32)
                x0, y0 = max(0, int(r.left())), max(0, int(r.top()))
                x1, y1 = min(self.doc.width, int(r.right())), min(self.doc.height, int(r.bottom()))
                if self.tool == "marquee_rect":
                    mask[y0:y1, x0:x1] = 1.0
                else:
                    cx, cy = int((x0 + x1) * 0.5), int((y0 + y1) * 0.5)
                    ax, ay = max(1, (x1 - x0) // 2), max(1, (y1 - y0) // 2)
                    cv2.ellipse(mask, (cx, cy), (ax, ay), 0, 0, 360, 1.0, -1)
                self._apply_new_selection(mask, event.modifiers())

        elif self.tool == "lasso" and len(self._lasso_pts) >= 3:
            mask = np.zeros((self.doc.height, self.doc.width), dtype=np.float32)
            pts = np.array(self._lasso_pts, dtype=np.int32)
            cv2.fillPoly(mask, [pts], 1.0)
            self._lasso_pts.clear()
            self._apply_new_selection(mask, event.modifiers())

        elif self.tool == "quick_select" and self._quick_pts:
            comp = self._comp_rgba if self._comp_rgba is not None else composite_document(self.doc)
            mask = quick_select_grow(comp, self._quick_pts, radius=max(10, int(self.brush_settings.size * 0.5)))
            self._quick_pts.clear()
            self._apply_new_selection(mask, event.modifiers())

        elif self.tool == "gradient":
            lyr = self.doc.ensure_raster_layer()
            if lyr.image is not None:
                grad = render_gradient(
                    self.doc.width,
                    self.doc.height,
                    (self._start_doc.x(), self._start_doc.y()),
                    (dpt.x(), dpt.y()),
                    self.fg_color + (255,),
                    self.bg_color + (255,),
                    style=self.gradient_style,
                    selection=self.doc.selection,
                )
                a = (grad[..., 3:4].astype(np.float32) / 255.0)
                lyr.image[..., :3] = np.clip(lyr.image[..., :3] * (1.0 - a) + grad[..., :3] * a, 0, 255).astype(np.uint8)
                lyr.image[..., 3] = np.maximum(lyr.image[..., 3], grad[..., 3])
                lyr.invalidate_cache()
                self.doc.push_history("Gradient Fill")
                self.refresh_composite()
                self.documentChanged.emit()

        elif self.tool == "shape":
            r = QRectF(self._start_doc, dpt).normalized()
            if r.width() >= 4 and r.height() >= 4:
                self.doc.add_vector_layer(
                    self.shape_subtool,
                    rect=(r.left(), r.top(), r.width(), r.height()),
                    fill_color=self.fg_color + (235,),
                    stroke_color=(255, 255, 255, 255),
                )
                self.doc.push_history(f"Add {self.shape_subtool.title()}")
                self.refresh_composite()
                self.documentChanged.emit()

        elif self.tool == "slice":
            r = QRectF(self._start_doc, dpt).normalized()
            if r.width() >= 8 and r.height() >= 8:
                idx = len(self.doc.slices) + 1
                self.doc.slices.append(
                    SliceRect(name=f"slice_{idx:02d}", x=int(r.left()), y=int(r.top()), width=int(r.width()), height=int(r.height()))
                )
                self.documentChanged.emit()
                self.statusMessage.emit(f"Added Slice #{idx} ({int(r.width())}×{int(r.height())}).")

        elif self.tool == "artboard":
            r = QRectF(self._start_doc, dpt).normalized()
            if r.width() >= 20 and r.height() >= 20:
                idx = len(self.doc.artboards) + 1
                self.doc.artboards.append(
                    Artboard(name=f"Artboard {idx}", x=int(r.left()), y=int(r.top()), width=int(r.width()), height=int(r.height()))
                )
                self.documentChanged.emit()
                self.statusMessage.emit(f"Added Artboard {idx}.")

        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.tool == "crop":
            self.commit_active_mode()
        elif self.tool == "poly_lasso" and len(self._poly_pts) >= 3:
            self._commit_poly_lasso()
        elif self.tool == "pen" and len(self._pen_pts) >= 2:
            self._commit_pen_path()

    def _commit_poly_lasso(self) -> None:
        mask = np.zeros((self.doc.height, self.doc.width), dtype=np.float32)
        cv2.fillPoly(mask, [np.array(self._poly_pts, dtype=np.int32)], 1.0)
        self._poly_pts.clear()
        self._apply_new_selection(mask, Qt.KeyboardModifier.NoModifier)

    def _commit_pen_path(self) -> None:
        self.doc.add_vector_layer(
            "path",
            points=list(self._pen_pts),
            closed=len(self._pen_pts) >= 3,
            fill_enabled=False,
            stroke_enabled=True,
            stroke_color=self.fg_color + (255,),
            stroke_width=3.5,
        )
        self._pen_pts.clear()
        self.doc.push_history("Add Pen Path")
        self.refresh_composite()
        self.documentChanged.emit()

    def _apply_new_selection(self, mask: np.ndarray, mods: Qt.KeyboardModifier) -> None:
        if self.doc.selection is not None and (mods & Qt.KeyboardModifier.ShiftModifier):
            self.doc.selection = np.clip(np.maximum(self.doc.selection, mask), 0.0, 1.0)
        elif self.doc.selection is not None and (mods & Qt.KeyboardModifier.AltModifier):
            self.doc.selection = np.clip(self.doc.selection - mask, 0.0, 1.0)
        else:
            self.doc.selection = mask
        self.rebuild_selection_contours()
        self._update_context_bar_mode()
        self.selectionChanged.emit()
        self.update()

    def _pick_color_at(self, dpt: QPointF) -> None:
        ix, iy = int(dpt.x()), int(dpt.y())
        if self._comp_rgba is not None and 0 <= ix < self.doc.width and 0 <= iy < self.doc.height:
            c = tuple(int(v) for v in self._comp_rgba[iy, ix, :3])
            self.fg_color = c
            self.colorPicked.emit(c)

    # ---- Paint Event ----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0E1117"))

        dr = self.doc_rect_on_screen()

        # Subtle workspace drop shadow around document
        p.fillRect(dr.adjusted(6, 6, 6, 6), QColor(0, 0, 0, 110))

        # Pattern Preview: render infinite seamless 3x3 tiled view around document!
        if self.doc.pattern_preview and self._comp_pixmap is not None:
            for tx in (-1, 0, 1):
                for ty in (-1, 0, 1):
                    if tx == 0 and ty == 0:
                        continue
                    tr = QRectF(dr.left() + tx * dr.width(), dr.top() + ty * dr.height(), dr.width(), dr.height())
                    p.setOpacity(0.72)
                    p.drawPixmap(tr, self._comp_pixmap, QRectF(self._comp_pixmap.rect()))
            p.setOpacity(1.0)

        # Checkerboard + Composite Document Image (hardware-accelerated QPixmap blit!)
        p.drawTiledPixmap(dr, self._checker_pm)
        if self._comp_pixmap is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.zoom < 4.0)
            p.drawPixmap(dr, self._comp_pixmap, QRectF(self._comp_pixmap.rect()))

        # Print Bleed & Printer Marks overlay
        if self.doc.print_settings.bleed_mm > 0 and (
            self.doc.print_settings.bleed_marks or self.doc.print_settings.crop_marks or self.doc.print_settings.soft_proof
        ):
            bp = self.doc.bleed_px() * self.zoom
            bleed_r = dr.adjusted(-bp, -bp, bp, bp)
            p.setPen(QPen(QColor("#FF4D6D"), 1.2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(bleed_r)
            if self.doc.print_settings.crop_marks:
                p.setPen(QPen(QColor("#E2E8F0"), 1.0))
                ml = 14
                for cx, cy, sx, sy in [
                    (dr.left(), dr.top(), -1, -1), (dr.right(), dr.top(), 1, -1),
                    (dr.left(), dr.bottom(), -1, 1), (dr.right(), dr.bottom(), 1, 1),
                ]:
                    p.drawLine(QPointF(cx + sx * 4, cy), QPointF(cx + sx * (4 + ml), cy))
                    p.drawLine(QPointF(cx, cy + sy * 4), QPointF(cx, cy + sy * (4 + ml)))

        # Document border
        p.setPen(QPen(QColor("#31A8FF" if self.doc.pattern_preview else "#354056"), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(dr)

        # Artboards overlay (when >1 artboard)
        if len(self.doc.artboards) > 1:
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            for ab in self.doc.artboards:
                ar = QRectF(
                    dr.left() + ab.x * self.zoom,
                    dr.top() + ab.y * self.zoom,
                    ab.width * self.zoom,
                    ab.height * self.zoom,
                )
                p.setPen(QPen(QColor("#38BDF8"), 1.2, Qt.PenStyle.DashLine))
                p.drawRect(ar)
                p.setPen(QColor("#38BDF8"))
                p.drawText(QPointF(ar.left() + 4, ar.top() - 5), ab.name)

        # Guides & Grid
        if self.show_guides:
            p.setPen(QPen(QColor("#00D4FF"), 1.0))
            for gy in self.doc.guides_h:
                sy = dr.top() + gy * self.zoom
                p.drawLine(QPointF(0, sy), QPointF(self.width(), sy))
            for gx in self.doc.guides_v:
                sx = dr.left() + gx * self.zoom
                p.drawLine(QPointF(sx, 0), QPointF(sx, self.height()))

        if self.show_grid:
            p.setPen(QPen(QColor(255, 255, 255, 32), 1.0))
            step = 64
            for x in range(step, self.doc.width, step):
                sx = dr.left() + x * self.zoom
                p.drawLine(QPointF(sx, dr.top()), QPointF(sx, dr.bottom()))
            for y in range(step, self.doc.height, step):
                sy = dr.top() + y * self.zoom
                p.drawLine(QPointF(dr.left(), sy), QPointF(dr.right(), sy))

        # Pixel grid at high zoom (>= 8x)
        if self.zoom >= 8.0:
            p.setPen(QPen(QColor(255, 255, 255, 28), 0.7))
            for x in range(1, self.doc.width):
                sx = dr.left() + x * self.zoom
                if 0 <= sx <= self.width():
                    p.drawLine(QPointF(sx, dr.top()), QPointF(sx, dr.bottom()))
            for y in range(1, self.doc.height):
                sy = dr.top() + y * self.zoom
                if 0 <= sy <= self.height():
                    p.drawLine(QPointF(dr.left(), sy), QPointF(dr.right(), sy))

        # Slices overlay (shown when Slice tool active or View -> Show Slices)
        if (self.show_slices or self.tool == "slice") and self.doc.slices:
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            for idx, sl in enumerate(self.doc.slices, start=1):
                sr = QRectF(dr.left() + sl.x * self.zoom, dr.top() + sl.y * self.zoom, sl.width * self.zoom, sl.height * self.zoom)
                p.setPen(QPen(QColor("#F59E0B"), 1.3, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(sr)
                p.fillRect(QRectF(sr.left(), sr.top(), 66, 16), QColor("#F59E0B"))
                p.setPen(QColor("#11151C"))
                p.drawText(QPointF(sr.left() + 4, sr.top() + 12), f"{idx:02d} {sl.name[:8]}")

        # Animated Marching Ants Selection
        if self._ants_contours:
            pen_w = QPen(QColor("#FFFFFF"), 1.2)
            pen_b = QPen(QColor("#0B0E14"), 1.2)
            pen_b.setDashPattern([4, 4])
            pen_b.setDashOffset(float(self._ants_phase))
            for cnt in self._ants_contours:
                if len(cnt) < 2:
                    continue
                path = QPainterPath()
                p0 = cnt[0][0]
                path.moveTo(dr.left() + p0[0] * self.zoom, dr.top() + p0[1] * self.zoom)
                for pt in cnt[1:]:
                    q = pt[0]
                    path.lineTo(dr.left() + q[0] * self.zoom, dr.top() + q[1] * self.zoom)
                path.closeSubpath()
                p.setPen(pen_w)
                p.drawPath(path)
                p.setPen(pen_b)
                p.drawPath(path)

        # Transient overlays (Crop, Puppet Pins, Perspective Quad, Heal mask, Lasso, Shape, Gradient, Ruler, Count, Comments)
        self._paint_tool_overlays(p, dr)

        # Rulers along top & left
        if self.show_rulers:
            self._paint_rulers(p, dr)

        p.end()

    def _paint_tool_overlays(self, p: QPainter, dr: QRectF) -> None:
        # Dragging preview for marquee/slice/shape/artboard/gradient
        if self._dragging and self.tool in ("marquee_rect", "marquee_ellipse", "slice", "shape", "artboard"):
            r = QRectF(self.doc_to_screen(self._start_doc), self.doc_to_screen(self._cur_doc)).normalized()
            p.setPen(QPen(QColor("#31A8FF"), 1.4, Qt.PenStyle.DashLine))
            p.setBrush(QColor(49, 168, 255, 32))
            if self.tool == "marquee_ellipse":
                p.drawEllipse(r)
            else:
                p.drawRect(r)

        if self._dragging and self.tool == "gradient":
            p.setPen(QPen(QColor("#31A8FF"), 2.0))
            p.drawLine(self.doc_to_screen(self._start_doc), self.doc_to_screen(self._cur_doc))

        # Lasso / Poly Lasso / Pen preview
        pts_src = self._lasso_pts or self._poly_pts or self._pen_pts
        if pts_src:
            p.setPen(QPen(QColor("#31A8FF"), 1.6))
            for i in range(len(pts_src) - 1):
                p.drawLine(self.doc_to_screen(QPointF(*pts_src[i])), self.doc_to_screen(QPointF(*pts_src[i + 1])))
            for pt in pts_src:
                p.setBrush(QColor("#31A8FF"))
                p.drawEllipse(self.doc_to_screen(QPointF(*pt)), 3, 3)

        # Spot Heal / Remove translucent red stroke overlay
        if self._heal_mask is not None:
            h, w = self._heal_mask.shape
            ov = np.zeros((h, w, 4), dtype=np.uint8)
            ov[self._heal_mask > 0] = (255, 70, 110, 120)
            p.drawImage(dr, rgba_to_qimage(ov))

        # Crop box with rule-of-thirds grid
        if self.tool == "crop" and self._crop_rect is not None:
            cr = QRectF(
                self.doc_to_screen(self._crop_rect.topLeft()),
                self.doc_to_screen(self._crop_rect.bottomRight()),
            ).normalized()
            p.setPen(QPen(QColor("#FFFFFF"), 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(cr)
            p.setPen(QPen(QColor(255, 255, 255, 120), 1.0))
            for f in (1 / 3.0, 2 / 3.0):
                p.drawLine(QPointF(cr.left() + cr.width() * f, cr.top()), QPointF(cr.left() + cr.width() * f, cr.bottom()))
                p.drawLine(QPointF(cr.left(), cr.top() + cr.height() * f), QPointF(cr.right(), cr.top() + cr.height() * f))

        # Puppet Warp Pins
        if self.tool == "puppet_warp":
            for i, (px, py) in enumerate(self._puppet_moved_pins):
                sp = self.doc_to_screen(QPointF(px, py))
                p.setPen(QPen(QColor("#FFFFFF"), 2.0))
                p.setBrush(QColor("#31A8FF" if i != self._puppet_drag_idx else "#FF9A00"))
                p.drawEllipse(sp, 6.5, 6.5)

        # Perspective Warp Quad
        if self.tool == "perspective_warp" and len(self._persp_dst_quad) == 4:
            spts = [self.doc_to_screen(QPointF(x, y)) for x, y in self._persp_dst_quad]
            p.setPen(QPen(QColor("#31A8FF"), 2.0))
            for i in range(4):
                p.drawLine(spts[i], spts[(i + 1) % 4])
            for sp in spts:
                p.setBrush(QColor("#FFFFFF"))
                p.drawEllipse(sp, 6.5, 6.5)

        # Clone Stamp Origin Crosshair
        if self.tool == "clone" and self._clone_origin is not None:
            sp = self.doc_to_screen(QPointF(*self._clone_origin))
            p.setPen(QPen(QColor("#00D4FF"), 1.5))
            p.drawEllipse(sp, 7, 7)
            p.drawLine(QPointF(sp.x() - 10, sp.y()), QPointF(sp.x() + 10, sp.y()))
            p.drawLine(QPointF(sp.x(), sp.y() - 10), QPointF(sp.x(), sp.y() + 10))

        # Ruler Measurement Line
        if self.doc.ruler_line is not None and self.tool == "ruler_count":
            x0, y0, x1, y1 = self.doc.ruler_line
            p.setPen(QPen(QColor("#38BDF8"), 2.0))
            p.drawLine(self.doc_to_screen(QPointF(x0, y0)), self.doc_to_screen(QPointF(x1, y1)))

        # Scientific Count Markers
        if self.doc.count_markers:
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            for cm in self.doc.count_markers:
                sp = self.doc_to_screen(QPointF(cm.x, cm.y))
                p.setPen(QPen(QColor("#11151C"), 1.5))
                p.setBrush(QColor("#22D3EE"))
                p.drawEllipse(sp, 9, 9)
                p.setPen(QColor("#0B111A"))
                p.drawText(QRectF(sp.x() - 9, sp.y() - 9, 18, 18), Qt.AlignmentFlag.AlignCenter, str(cm.index))

        # Collaboration Comment Pins
        if self.show_comments and self.doc.comments:
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            for idx, cp in enumerate(self.doc.comments, start=1):
                sp = self.doc_to_screen(QPointF(cp.x, cp.y))
                p.setPen(QPen(QColor("#FFFFFF"), 1.6))
                p.setBrush(QColor("#10B981" if cp.resolved else "#31A8FF"))
                p.drawEllipse(sp, 10, 10)
                p.setPen(QColor("#0B1220"))
                p.drawText(QRectF(sp.x() - 10, sp.y() - 10, 20, 20), Qt.AlignmentFlag.AlignCenter, str(idx))

        # Brush Cursor Circle
        if self.tool in ("brush", "mixer_brush", "eraser", "spot_heal", "remove", "clone", "history_brush", "dodge_burn", "blur_smudge"):
            sp = self.doc_to_screen(self._cur_doc)
            rad = max(2.0, self.brush_settings.size * 0.5 * self.zoom)
            p.setPen(QPen(QColor(255, 255, 255, 195), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(sp, rad, rad)

    def _paint_rulers(self, p: QPainter, dr: QRectF) -> None:
        rw = 20
        p.fillRect(0, 0, self.width(), rw, QColor("#171B24"))
        p.fillRect(0, 0, rw, self.height(), QColor("#171B24"))
        p.setPen(QPen(QColor("#2A3242"), 1))
        p.drawLine(0, rw, self.width(), rw)
        p.drawLine(rw, 0, rw, self.height())
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor("#8D99AE"))

        step = 100 if self.zoom >= 0.5 else 200
        if self.zoom >= 2.0:
            step = 50
        for x in range(0, self.doc.width + 1, step):
            sx = dr.left() + x * self.zoom
            if rw <= sx <= self.width():
                p.drawLine(QPointF(sx, rw - 6), QPointF(sx, rw))
                p.drawText(QPointF(sx + 2, 11), str(x))
        for y in range(0, self.doc.height + 1, step):
            sy = dr.top() + y * self.zoom
            if rw <= sy <= self.height():
                p.drawLine(QPointF(rw - 6, sy), QPointF(rw, sy))
                p.drawText(QPointF(2, sy - 2), str(y))
