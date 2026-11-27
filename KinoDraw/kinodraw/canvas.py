"""Interactive Illustrator-style Vector Canvas with Rulers, Smart Guides,
all 25+ drawing/editing tools, and a floating Contextual Task Bar.
"""
from __future__ import annotations

import copy
import math
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
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
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QWidget,
)

from .geometry import (
    apply_puppet_warp,
    compute_planar_regions,
    convert_object_to_path,
    fit_catmull_rom_subpath,
    knife_slice_object,
    object_bounds,
    object_to_qpath,
    project_rect_to_perspective,
    qpath_to_subpaths,
    rdp_simplify,
    recognize_shaper_gesture,
    split_subpath_at_point,
    subpaths_to_qpath,
    transform_object_affine,
    translate_object,
)
from .models import (
    AnchorPoint,
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Artboard,
    CharTransform,
    Color,
    Document,
    GradientDef,
    Guide,
    PuppetPin,
    SubPath,
    TextStyle,
    VectorObject,
    WidthStation,
)
from .renderer import ViewOptions, apply_separations_filter, render_document

RULER_SIZE = 22


class ContextualTaskBar(QWidget):
    """Floating Illustrator-style contextual pill anchored below the current selection."""
    action_triggered = Signal(str)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("ContextualBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(5)
        self.hide()

    def set_actions(self, items: List[Tuple[str, str]]) -> None:
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        for label, cmd in items:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("padding: 3px 9px; font-size: 8.5pt;")
            if cmd in ("ai_generate", "recolor"):
                btn.setObjectName("PrimaryButton")
            btn.clicked.connect(lambda _=False, c=cmd: self.action_triggered.emit(c))
            self._layout.addWidget(btn)
        self.adjustSize()


class VectorCanvas(QWidget):
    """Core interactive vector artboard viewport for KinoDraw."""

    selection_changed = Signal()
    document_modified = Signal(str)
    cursor_moved = Signal(float, float)
    zoom_changed = Signal(float)
    tool_requested = Signal(str)
    context_action = Signal(str)

    def __init__(self, doc: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = doc
        self.view_opts = ViewOptions()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Viewport transform
        self.zoom: float = 0.72
        self.pan_x: float = 90.0
        self.pan_y: float = 70.0
        self.show_rulers: bool = True

        # Active tool & default creation style
        self.tool: str = "select"
        self.active_fill_color: Color = Color.from_hex("#FF9A00")
        self.active_stroke_color: Color = Color.from_hex("#141821")
        self.active_stroke_width: float = 2.0
        self.active_fill_enabled: bool = True
        self.active_stroke_enabled: bool = True
        self.active_symbol_id: str = "sym_star"
        self.active_brush_id: Optional[str] = None
        self.global_edit_mode: bool = False

        # Selection state
        self.selected_ids: List[str] = []
        self.selected_anchor: Optional[Tuple[str, int, int, str]] = None  # (obj_id, sp_i, a_i, part: 'anchor'|'in'|'out')
        self.touch_type_char_idx: int = -1
        self.crop_target_id: Optional[str] = None

        # Undo / Redo JSON history
        self._undo_stack: List[str] = [self.doc.snapshot_json()]
        self._redo_stack: List[str] = []

        # Interaction state
        self._space_pan: bool = False
        self._dragging: bool = False
        self._drag_mode: str = ""
        self._drag_start_doc: QPointF = QPointF()
        self._drag_last_doc: QPointF = QPointF()
        self._drag_start_screen: QPointF = QPointF()
        self._cursor_doc: QPointF = QPointF()
        self._marquee_rect: Optional[QRectF] = None
        self._active_handle: str = ""
        self._orig_bounds: Optional[QRectF] = None
        self._orig_snapshot_before_drag: Optional[str] = None

        # Multi-click tool builders (Pen, Curvature, Pencil, Blob, Shaper, Knife, ShapeBuilder)
        self._pen_anchors: List[AnchorPoint] = []
        self._pen_dragging_handle: bool = False
        self._curv_points: List[Tuple[float, float]] = []
        self._freehand_pts: List[Tuple[float, float]] = []
        self._preview_shape: Optional[VectorObject] = None
        self._sb_regions: List[Tuple[QPainterPath, Appearance]] = []
        self._sb_hover_idx: int = -1
        self._sb_merged_indices: List[int] = []
        self._blend_first_id: Optional[str] = None
        self._active_puppet_pin_idx: int = -1
        self._smart_guide_lines: List[Tuple[QPointF, QPointF]] = []
        self._ruler_drag_orient: Optional[str] = None

        # Floating Contextual Task Bar
        self.ctx_bar = ContextualTaskBar(self)
        self.ctx_bar.action_triggered.connect(self.context_action.emit)

    # ------------------------------------------------------------------
    # Coordinate Transforms & Helpers
    # ------------------------------------------------------------------

    def screen_to_doc(self, pt: QPointF) -> QPointF:
        ox = RULER_SIZE if self.show_rulers else 0
        oy = RULER_SIZE if self.show_rulers else 0
        return QPointF((pt.x() - ox - self.pan_x) / self.zoom, (pt.y() - oy - self.pan_y) / self.zoom)

    def doc_to_screen(self, pt: QPointF) -> QPointF:
        ox = RULER_SIZE if self.show_rulers else 0
        oy = RULER_SIZE if self.show_rulers else 0
        return QPointF(pt.x() * self.zoom + self.pan_x + ox, pt.y() * self.zoom + self.pan_y + oy)

    def snap_point(self, pt: QPointF) -> QPointF:
        x, y = pt.x(), pt.y()
        if self.doc.snap_to_pixel:
            x, y = round(x), round(y)
        elif self.doc.snap_to_grid and self.doc.grid_spacing > 1.0:
            s = self.doc.grid_spacing
            x = round(x / s) * s
            y = round(y / s) * s
        # Snap to guides
        if self.doc.guides_visible:
            tol = 6.0 / self.zoom
            for g in self.doc.guides:
                if g.orientation == "v" and abs(x - g.position) < tol:
                    x = g.position
                elif g.orientation == "h" and abs(y - g.position) < tol:
                    y = g.position
        return QPointF(x, y)

    def fit_artboard(self, ab: Optional[Artboard] = None) -> None:
        ab = ab or self.doc.active_artboard()
        avail_w = max(100, self.width() - (RULER_SIZE if self.show_rulers else 0) - 60)
        avail_h = max(100, self.height() - (RULER_SIZE if self.show_rulers else 0) - 80)
        self.zoom = max(0.08, min(4.0, min(avail_w / max(1.0, ab.width), avail_h / max(1.0, ab.height))))
        self.pan_x = (avail_w - ab.width * self.zoom) * 0.5 + 30 - ab.x * self.zoom
        self.pan_y = (avail_h - ab.height * self.zoom) * 0.5 + 30 - ab.y * self.zoom
        self.zoom_changed.emit(self.zoom)
        self.update_contextual_bar()
        self.update()

    def set_zoom(self, new_zoom: float, anchor_screen: Optional[QPointF] = None) -> None:
        new_zoom = max(0.05, min(32.0, new_zoom))
        if anchor_screen is None:
            anchor_screen = QPointF(self.width() * 0.5, self.height() * 0.5)
        before = self.screen_to_doc(anchor_screen)
        self.zoom = new_zoom
        after_s = self.doc_to_screen(before)
        self.pan_x += anchor_screen.x() - after_s.x()
        self.pan_y += anchor_screen.y() - after_s.y()
        self.zoom_changed.emit(self.zoom)
        self.update_contextual_bar()
        self.update()

    def set_tool(self, tool_name: str) -> None:
        self._commit_open_builders()
        self.tool = tool_name
        self._sb_regions = []
        self._sb_hover_idx = -1
        self._blend_first_id = None
        if tool_name in ("shape_builder", "live_paint"):
            objs = self.selected_objects() if tool_name == "shape_builder" else self.doc.iter_all_objects()
            if objs:
                self._sb_regions = compute_planar_regions(objs, self.doc)
        if tool_name == "hand":
            self.setCursor(Qt.OpenHandCursor)
        elif tool_name in ("select", "direct_select"):
            self.setCursor(Qt.ArrowCursor)
        elif tool_name in ("type", "area_type", "type_on_path"):
            self.setCursor(Qt.IBeamCursor)
        else:
            self.setCursor(Qt.CrossCursor)
        self.update()

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def push_undo(self, label: str = "Edit") -> None:
        snap = self.doc.snapshot_json()
        if not self._undo_stack or self._undo_stack[-1] != snap:
            self._undo_stack.append(snap)
            if len(self._undo_stack) > 80:
                self._undo_stack.pop(0)
            self._redo_stack.clear()
        self.doc.dirty = True
        self.document_modified.emit(label)
        self.update_contextual_bar()
        self.update()

    def undo(self) -> bool:
        if len(self._undo_stack) <= 1:
            return False
        cur = self._undo_stack.pop()
        self._redo_stack.append(cur)
        self._restore_json(self._undo_stack[-1])
        self.document_modified.emit("Undo")
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        nxt = self._redo_stack.pop()
        self._undo_stack.append(nxt)
        self._restore_json(nxt)
        self.document_modified.emit("Redo")
        return True

    def _restore_json(self, raw_json: str) -> None:
        import json
        restored = Document.from_dict(json.loads(raw_json))
        self.doc.artboards = restored.artboards
        self.doc.layers = restored.layers
        self.doc.guides = restored.guides
        self.doc.symbols = restored.symbols
        self.doc.swatch_groups = restored.swatch_groups
        self.doc.graphic_styles = restored.graphic_styles
        self.doc.brushes = restored.brushes
        self.doc.perspective = restored.perspective
        self.doc.active_layer_id = restored.active_layer_id
        self.selected_ids = [oid for oid in self.selected_ids if self.doc.find_object(oid)]
        self.selection_changed.emit()
        self.update_contextual_bar()
        self.update()

    # ------------------------------------------------------------------
    # Selection Helpers & Global Edit
    # ------------------------------------------------------------------

    def selected_objects(self) -> List[VectorObject]:
        out = []
        for oid in self.selected_ids:
            o = self.doc.find_object(oid)
            if o:
                out.append(o)
        return out

    def selection_bounds(self) -> Optional[QRectF]:
        objs = self.selected_objects()
        if not objs:
            return None
        r = object_bounds(objs[0], self.doc)
        for o in objs[1:]:
            r = r.united(object_bounds(o, self.doc))
        return r

    def global_edit_matches(self) -> List[VectorObject]:
        """Find all objects across all artboards sharing shape/fill signature for Global Edit."""
        sel = self.selected_objects()
        if not self.global_edit_mode or not sel:
            return []
        ref = sel[0]
        ref_hex = ref.appearance.primary_fill.color.to_hex() if ref.appearance.primary_fill.fill_type == "solid" else ""
        matches = []
        for o in self.doc.iter_all_objects():
            if o.id in self.selected_ids:
                continue
            o_hex = o.appearance.primary_fill.color.to_hex() if o.appearance.primary_fill.fill_type == "solid" else ""
            if o.kind == ref.kind and o.shape_type == ref.shape_type and o_hex == ref_hex:
                matches.append(o)
        return matches

    def hit_test(self, doc_pt: QPointF) -> Optional[VectorObject]:
        tol = max(6.0, 8.0 / self.zoom)
        for lyr in reversed(self.doc.layers):
            if not lyr.visible or lyr.locked:
                continue
            for obj in reversed(lyr.objects):
                if not obj.visible or obj.locked:
                    continue
                br = object_bounds(obj, self.doc).adjusted(-tol, -tol, tol, tol)
                if not br.contains(doc_pt):
                    continue
                if obj.kind in ("image", "graph", "mockup", "text", "symbol_instance", "group", "repeat", "blend"):
                    return obj
                qp = object_to_qpath(obj, self.doc)
                if qp.contains(doc_pt):
                    return obj
                # Also hit-test near stroked outline
                probe = QPainterPath()
                probe.addEllipse(doc_pt, tol, tol)
                if qp.intersects(probe):
                    return obj
        return None

    def make_default_appearance(self) -> Appearance:
        fill = AppearanceFill(
            fill_type="solid" if self.active_fill_enabled else "none",
            color=copy.deepcopy(self.active_fill_color),
        )
        stroke = AppearanceStroke(
            stroke_type="solid" if self.active_stroke_enabled else "none",
            color=copy.deepcopy(self.active_stroke_color),
            width=self.active_stroke_width,
            brush_id=self.active_brush_id,
        )
        return Appearance(fills=[fill], strokes=[stroke])

    def update_contextual_bar(self) -> None:
        sel = self.selected_objects()
        if not sel:
            self.ctx_bar.hide()
            return
        actions: List[Tuple[str, str]] = []
        if len(sel) == 1:
            o = sel[0]
            if o.kind == "image":
                actions = [("Image Trace", "image_trace"), ("Crop Image", "crop_image"), ("Embed", "embed_image"), ("Duplicate", "duplicate"), ("Delete", "delete")]
            elif o.kind == "text":
                actions = [("Edit Text", "edit_text"), ("Create Outlines", "create_outlines"), ("Touch Type", "tool_touch_type"), ("Recolor", "recolor"), ("Duplicate", "duplicate")]
            elif o.kind == "group":
                actions = [("Ungroup", "ungroup"), ("Recolor", "recolor"), ("3D Extrude", "effect_3d"), ("Mockup", "create_mockup"), ("Duplicate", "duplicate")]
            elif o.kind == "graph":
                actions = [("Edit Data", "edit_graph"), ("Duplicate", "duplicate"), ("Delete", "delete")]
            else:
                actions = [("Recolor", "recolor"), ("Warp", "effect_warp"), ("3D Extrude", "effect_3d"), ("Mockup", "create_mockup"), ("Global Edit", "toggle_global_edit"), ("Duplicate", "duplicate")]
        else:
            actions = [("Group", "group"), ("Unite", "pf_unite"), ("Minus Front", "pf_minus"), ("Clip Mask", "clip_mask"), ("Blend", "make_blend"), ("Recolor", "recolor")]
        actions.append(("✦ Generate", "ai_generate"))
        self.ctx_bar.set_actions(actions)

        br = self.selection_bounds()
        if br is None:
            self.ctx_bar.hide()
            return
        bot = self.doc_to_screen(QPointF(br.center().x(), br.bottom()))
        bx = int(max(30, min(self.width() - self.ctx_bar.width() - 12, bot.x() - self.ctx_bar.width() * 0.5)))
        by = int(max(30, min(self.height() - self.ctx_bar.height() - 12, bot.y() + 18)))
        self.ctx_bar.move(bx, by)
        self.ctx_bar.show()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, not self.view_opts.pixel_preview)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, not self.view_opts.pixel_preview)

        # Deep KinoSuite pasteboard background
        p.fillRect(self.rect(), QColor("#12151C"))

        ox = RULER_SIZE if self.show_rulers else 0
        oy = RULER_SIZE if self.show_rulers else 0

        # If Separations Preview is active with a plate turned off, render via offscreen QImage filter
        if self.view_opts.separations_preview and not all(self.view_opts.sep_plates.values()):
            img = QImage(self.width(), self.height(), QImage.Format_RGBA8888)
            img.fill(QColor("#12151C"))
            ip = QPainter(img)
            ip.setRenderHint(QPainter.Antialiasing, True)
            ip.translate(ox + self.pan_x, oy + self.pan_y)
            ip.scale(self.zoom, self.zoom)
            render_document(ip, self.doc, self.view_opts)
            ip.end()
            sep_img = apply_separations_filter(img, self.view_opts.sep_plates)
            p.drawImage(0, 0, sep_img)
        else:
            p.save()
            p.setClipRect(ox, oy, self.width() - ox, self.height() - oy)
            p.translate(ox + self.pan_x, oy + self.pan_y)
            p.scale(self.zoom, self.zoom)
            render_document(p, self.doc, self.view_opts)

            # Pixel grid overlay when zoomed >= 6x in Pixel Preview
            if self.view_opts.pixel_preview and self.zoom >= 6.0:
                self._draw_pixel_grid(p)

            # Live creation previews
            self._draw_active_tool_overlays(p)
            p.restore()

        # Selection gizmos in crisp 1px screen-space
        p.save()
        p.setClipRect(ox, oy, self.width() - ox, self.height() - oy)
        self._draw_selection_overlays(p)
        p.restore()

        # Rulers
        if self.show_rulers:
            self._draw_rulers(p)

        # Perspective Plane Widget (top-left of viewport when Perspective Grid is visible)
        if self.doc.perspective.visible:
            self._draw_perspective_widget(p)

        p.end()

    def _draw_pixel_grid(self, p: QPainter) -> None:
        tl = self.screen_to_doc(QPointF(RULER_SIZE, RULER_SIZE))
        br = self.screen_to_doc(QPointF(self.width(), self.height()))
        p.setPen(QPen(QColor(120, 140, 160, 70), 1.0 / self.zoom))
        for x in range(int(tl.x()), int(br.x()) + 1):
            p.drawLine(QPointF(x, tl.y()), QPointF(x, br.y()))
        for y in range(int(tl.y()), int(br.y()) + 1):
            p.drawLine(QPointF(tl.x(), y), QPointF(br.x(), y))

    def _draw_active_tool_overlays(self, p: QPainter) -> None:
        # Shape Builder / Live Paint region mesh highlight
        if self.tool in ("shape_builder", "live_paint") and self._sb_regions:
            for idx, (rpath, _) in enumerate(self._sb_regions):
                if idx == self._sb_hover_idx or idx in self._sb_merged_indices:
                    p.setBrush(QBrush(QColor(255, 154, 0, 115), Qt.Dense4Pattern))
                    p.setPen(QPen(QColor("#FF9A00"), 1.8 / self.zoom))
                    p.drawPath(rpath)

        # Preview shape while dragging
        if self._preview_shape is not None:
            from .renderer import render_object
            render_object(p, self._preview_shape, self.doc, self.view_opts, [])

        # Pen tool in-progress path
        if self.tool == "pen" and self._pen_anchors:
            sp = SubPath(anchors=self._pen_anchors, closed=False)
            qp = subpaths_to_qpath([sp])
            p.setPen(QPen(QColor("#00C2FF"), 1.6 / self.zoom))
            p.setBrush(Qt.NoBrush)
            p.drawPath(qp)
            last = self._pen_anchors[-1]
            p.setPen(QPen(QColor("#FF9A00"), 1.1 / self.zoom, Qt.DashLine))
            p.drawLine(QPointF(last.x, last.y), self._cursor_doc)
            for a in self._pen_anchors:
                p.setPen(QPen(QColor("#00C2FF"), 1.0 / self.zoom))
                p.drawLine(QPointF(a.in_x, a.in_y), QPointF(a.out_x, a.out_y))
                p.setBrush(QColor("#FFFFFF"))
                r = 3.5 / self.zoom
                p.drawRect(QRectF(a.x - r, a.y - r, r * 2, r * 2))

        # Curvature tool in-progress
        if self.tool == "curvature" and self._curv_points:
            sp = fit_catmull_rom_subpath(self._curv_points + [(self._cursor_doc.x(), self._cursor_doc.y())], closed=False)
            p.setPen(QPen(QColor("#00C2FF"), 1.6 / self.zoom))
            p.setBrush(Qt.NoBrush)
            p.drawPath(subpaths_to_qpath([sp]))
            for px, py in self._curv_points:
                p.setBrush(QColor("#FF9A00"))
                p.drawEllipse(QPointF(px, py), 4.0 / self.zoom, 4.0 / self.zoom)

        # Freehand preview (Pencil / Blob Brush / Shaper / Knife)
        if self._freehand_pts and len(self._freehand_pts) >= 2:
            fp = QPainterPath()
            fp.moveTo(self._freehand_pts[0][0], self._freehand_pts[0][1])
            for x, y in self._freehand_pts[1:]:
                fp.lineTo(x, y)
            col = QColor("#EF4444") if self.tool == "knife" else QColor("#FF9A00")
            w = (self.active_stroke_width if self.tool == "blob_brush" else 1.8 / self.zoom)
            p.setPen(QPen(col, w, Qt.DashLine if self.tool == "knife" else Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(fp)

        # Smart guides magenta hairlines
        if self._smart_guide_lines:
            p.setPen(QPen(QColor("#FF2E93"), 1.0 / self.zoom))
            for a, b in self._smart_guide_lines:
                p.drawLine(a, b)

    def _draw_selection_overlays(self, p: QPainter) -> None:
        # Marquee selection box
        if self._marquee_rect:
            tl = self.doc_to_screen(self._marquee_rect.topLeft())
            br = self.doc_to_screen(self._marquee_rect.bottomRight())
            r = QRectF(tl, br).normalized()
            p.setPen(QPen(QColor("#00C2FF"), 1.0, Qt.DashLine))
            p.setBrush(QColor(0, 194, 255, 35))
            p.drawRect(r)

        sel = self.selected_objects()
        if not sel:
            return

        # Global Edit peer highlights
        for peer in self.global_edit_matches():
            pbr = object_bounds(peer, self.doc)
            stl, sbr = self.doc_to_screen(pbr.topLeft()), self.doc_to_screen(pbr.bottomRight())
            p.setPen(QPen(QColor("#00C2FF"), 1.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(stl, sbr))

        # Direct Selection anchor & Bezier handle display
        if self.tool == "direct_select":
            for o in sel:
                if o.kind == "path":
                    for sp_i, sp in enumerate(o.subpaths):
                        for a_i, a in enumerate(sp.anchors):
                            sa = self.doc_to_screen(QPointF(a.x, a.y))
                            sin = self.doc_to_screen(QPointF(a.in_x, a.in_y))
                            sout = self.doc_to_screen(QPointF(a.out_x, a.out_y))
                            p.setPen(QPen(QColor("#00C2FF"), 1.0))
                            if math.hypot(sin.x() - sa.x(), sin.y() - sa.y()) > 2:
                                p.drawLine(sa, sin)
                                p.setBrush(QColor("#00C2FF"))
                                p.drawEllipse(sin, 3.5, 3.5)
                            if math.hypot(sout.x() - sa.x(), sout.y() - sa.y()) > 2:
                                p.drawLine(sa, sout)
                                p.setBrush(QColor("#00C2FF"))
                                p.drawEllipse(sout, 3.5, 3.5)
                            is_sel = (self.selected_anchor == (o.id, sp_i, a_i, "anchor"))
                            p.setBrush(QColor("#FF9A00") if is_sel else QColor("#FFFFFF"))
                            p.setPen(QPen(QColor("#0077CC"), 1.3))
                            p.drawRect(QRectF(sa.x() - 4, sa.y() - 4, 8, 8))
            return

        # Puppet Warp Pins overlay
        if self.tool == "puppet_warp" and len(sel) == 1:
            o = sel[0]
            for idx, pin in enumerate(o.puppet_pins):
                sp = self.doc_to_screen(QPointF(pin.x, pin.y))
                p.setBrush(QColor("#FF9A00") if idx == self._active_puppet_pin_idx else QColor("#FFFFFF"))
                p.setPen(QPen(QColor("#111111"), 2.0))
                p.drawEllipse(sp, 6.5, 6.5)
                p.setPen(QPen(QColor("#FF9A00"), 1.0, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(sp, 14.0, 14.0)
            return

        # Standard Selection Transform Bounding Box + 8 Handles + Rotate Knob + Live Corner Widget
        br = self.selection_bounds()
        if br is None:
            return
        stl = self.doc_to_screen(br.topLeft())
        sbr = self.doc_to_screen(br.bottomRight())
        sr = QRectF(stl, sbr).normalized()
        p.setPen(QPen(QColor("#00C2FF"), 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawRect(sr)

        # Rotate knob above top center
        rot_pt = QPointF(sr.center().x(), sr.top() - 22)
        p.drawLine(QPointF(sr.center().x(), sr.top()), rot_pt)
        p.setBrush(QColor("#FF9A00"))
        p.setPen(QPen(QColor("#12151C"), 1.3))
        p.drawEllipse(rot_pt, 5.0, 5.0)

        # 8 resize handles
        for hx, hy in self._handle_positions(sr).values():
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#0077CC"), 1.3))
            p.drawRect(QRectF(hx - 4, hy - 4, 8, 8))

        # Live Corner Widget for single rectangle
        if len(sel) == 1 and sel[0].kind == "shape" and sel[0].shape_type == "rect":
            cw = QPointF(sr.left() + 14 + sel[0].corner_radius * self.zoom * 0.4, sr.top() + 14 + sel[0].corner_radius * self.zoom * 0.4)
            if sr.contains(cw):
                p.setBrush(QColor("#FFFFFF"))
                p.setPen(QPen(QColor("#FF9A00"), 1.5))
                p.drawEllipse(cw, 4.5, 4.5)

        # Gradient Annotator bar if Gradient tool active
        if self.tool == "gradient" and len(sel) == 1:
            fill = sel[0].appearance.primary_fill
            if fill.fill_type == "gradient" and fill.gradient:
                g = fill.gradient
                if g.kind == "freeform":
                    g.ensure_freeform()
                    for pt in g.freeform_points:
                        sp = self.doc_to_screen(QPointF(br.x() + pt.x * br.width(), br.y() + pt.y * br.height()))
                        p.setBrush(QColor(pt.color.to_hex()))
                        p.setPen(QPen(QColor("#FFFFFF"), 2.0))
                        p.drawEllipse(sp, 7.0, 7.0)
                else:
                    ang = math.radians(g.angle)
                    c = br.center()
                    half = max(br.width(), br.height()) * 0.45
                    p1 = self.doc_to_screen(QPointF(c.x() - math.cos(ang) * half, c.y() - math.sin(ang) * half))
                    p2 = self.doc_to_screen(QPointF(c.x() + math.cos(ang) * half, c.y() + math.sin(ang) * half))
                    p.setPen(QPen(QColor("#FF9A00"), 2.2))
                    p.drawLine(p1, p2)
                    p.setBrush(QColor("#FFFFFF"))
                    p.drawEllipse(p1, 5.5, 5.5)
                    p.drawEllipse(p2, 5.5, 5.5)

    def _handle_positions(self, sr: QRectF) -> Dict[str, Tuple[float, float]]:
        return {
            "tl": (sr.left(), sr.top()),
            "tm": (sr.center().x(), sr.top()),
            "tr": (sr.right(), sr.top()),
            "mr": (sr.right(), sr.center().y()),
            "br": (sr.right(), sr.bottom()),
            "bm": (sr.center().x(), sr.bottom()),
            "bl": (sr.left(), sr.bottom()),
            "ml": (sr.left(), sr.center().y()),
        }

    def _draw_rulers(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, RULER_SIZE, QColor("#181C25"))
        p.fillRect(0, 0, RULER_SIZE, h, QColor("#181C25"))
        p.fillRect(0, 0, RULER_SIZE, RULER_SIZE, QColor("#1D222E"))
        p.setPen(QColor("#2E3545"))
        p.drawLine(0, RULER_SIZE, w, RULER_SIZE)
        p.drawLine(RULER_SIZE, 0, RULER_SIZE, h)

        # Choose nice ruler tick step
        raw_step = 80.0 / max(0.05, self.zoom)
        step = 10.0
        for cand in (10, 20, 50, 100, 200, 500, 1000):
            if cand >= raw_step:
                step = float(cand)
                break

        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor("#8C96AA"))
        # Horizontal ticks
        doc_l = self.screen_to_doc(QPointF(RULER_SIZE, 0)).x()
        doc_r = self.screen_to_doc(QPointF(w, 0)).x()
        x = math.floor(doc_l / step) * step
        while x <= doc_r:
            sx = self.doc_to_screen(QPointF(x, 0)).x()
            if sx >= RULER_SIZE:
                p.drawLine(QPointF(sx, RULER_SIZE - 8), QPointF(sx, RULER_SIZE))
                p.drawText(QPointF(sx + 2, 10), f"{int(x)}")
            x += step

        # Vertical ticks
        doc_t = self.screen_to_doc(QPointF(0, RULER_SIZE)).y()
        doc_b = self.screen_to_doc(QPointF(0, h)).y()
        y = math.floor(doc_t / step) * step
        while y <= doc_b:
            sy = self.doc_to_screen(QPointF(0, y)).y()
            if sy >= RULER_SIZE:
                p.drawLine(QPointF(RULER_SIZE - 8, sy), QPointF(RULER_SIZE, sy))
                p.save()
                p.translate(10, sy + 14)
                p.rotate(-90)
                p.drawText(0, 0, f"{int(y)}")
                p.restore()
            y += step

        # Live amber cursor ticks on both rulers
        cs = self.doc_to_screen(self._cursor_doc)
        p.setPen(QPen(QColor("#FF9A00"), 1.5))
        if cs.x() >= RULER_SIZE:
            p.drawLine(QPointF(cs.x(), 0), QPointF(cs.x(), RULER_SIZE))
        if cs.y() >= RULER_SIZE:
            p.drawLine(QPointF(0, cs.y()), QPointF(RULER_SIZE, cs.y()))

    def _draw_perspective_widget(self, p: QPainter) -> None:
        ox, oy = (RULER_SIZE + 14), (RULER_SIZE + 14)
        p.save()
        p.setBrush(QColor(24, 28, 37, 230))
        p.setPen(QPen(QColor("#39445B"), 1.2))
        p.drawRoundedRect(QRectF(ox, oy, 74, 78), 8, 8)
        cx, cy = ox + 37, oy + 38
        # Left face (Blue), Right face (Orange), Bottom face (Green)
        ap = self.doc.perspective.active_plane
        l_poly = [QPointF(cx, cy - 18), QPointF(cx - 22, cy - 6), QPointF(cx - 22, cy + 16), QPointF(cx, cy + 26)]
        r_poly = [QPointF(cx, cy - 18), QPointF(cx + 22, cy - 6), QPointF(cx + 22, cy + 16), QPointF(cx, cy + 26)]
        b_poly = [QPointF(cx, cy - 18), QPointF(cx - 22, cy - 6), QPointF(cx, cy + 5), QPointF(cx + 22, cy - 6)]
        p.setPen(QPen(QColor("#FFFFFF"), 1.0))
        p.setBrush(QColor("#3B82F6") if ap == "left" else QColor(59, 130, 246, 80))
        p.drawPolygon(l_poly)
        p.setBrush(QColor("#FF9A00") if ap == "right" else QColor(255, 154, 0, 80))
        p.drawPolygon(r_poly)
        p.setBrush(QColor("#22C55E") if ap == "horizontal" else QColor(34, 197, 94, 80))
        p.drawPolygon(b_poly)
        p.setPen(QColor("#E2E8F0"))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.drawText(QRectF(ox, oy + 61, 74, 15), Qt.AlignCenter, f"{self.doc.perspective.points}P: {ap.upper()}")
        p.restore()

    # ------------------------------------------------------------------
    # Mouse & Keyboard Events
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier or True:
            factor = 1.15 if delta > 0 else 1.0 / 1.15
            self.set_zoom(self.zoom * factor, event.position())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        doc_pt = self.snap_point(self.screen_to_doc(pos))
        self._drag_start_screen = pos
        self._drag_start_doc = doc_pt
        self._drag_last_doc = doc_pt
        self._cursor_doc = doc_pt

        # Click inside Perspective Plane selector cube
        if self.doc.perspective.visible and self.show_rulers:
            ox, oy = RULER_SIZE + 14, RULER_SIZE + 14
            if QRectF(ox, oy, 74, 78).contains(pos):
                order = ["left", "right", "horizontal", "none"]
                nxt = order[(order.index(self.doc.perspective.active_plane) + 1) % len(order)]
                self.doc.perspective.active_plane = nxt
                self.update()
                return

        # Drag from rulers to create a Guide!
        if self.show_rulers and event.button() == Qt.LeftButton:
            if pos.y() < RULER_SIZE and pos.x() > RULER_SIZE:
                self._ruler_drag_orient = "h"
                self._dragging = True
                return
            if pos.x() < RULER_SIZE and pos.y() > RULER_SIZE:
                self._ruler_drag_orient = "v"
                self._dragging = True
                return

        # Pan with Middle button, Spacebar, or Hand tool
        if event.button() == Qt.MiddleButton or self._space_pan or self.tool == "hand":
            self._dragging = True
            self._drag_mode = "pan"
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() != Qt.LeftButton:
            return

        # Zoom tool
        if self.tool == "zoom":
            factor = 0.7 if (event.modifiers() & Qt.AltModifier) else 1.45
            self.set_zoom(self.zoom * factor, pos)
            return

        # Eyedropper tool
        if self.tool == "eyedropper":
            hit = self.hit_test(doc_pt)
            if hit:
                if hit.appearance.primary_fill.fill_type == "solid":
                    self.active_fill_color = copy.deepcopy(hit.appearance.primary_fill.color)
                    self.active_fill_enabled = True
                if hit.appearance.primary_stroke.stroke_type == "solid":
                    self.active_stroke_color = copy.deepcopy(hit.appearance.primary_stroke.color)
                    self.active_stroke_width = hit.appearance.primary_stroke.width
                    self.active_stroke_enabled = True
                for o in self.selected_objects():
                    if o.id != hit.id:
                        o.appearance = copy.deepcopy(hit.appearance)
                self.push_undo("Eyedropper Sample")
            return

        # Selection tool
        if self.tool == "select":
            self._press_select(pos, doc_pt, event.modifiers())
            return

        # Direct Selection tool (anchors & handles)
        if self.tool == "direct_select":
            self._press_direct_select(pos, doc_pt)
            return

        # Pen Tool
        if self.tool == "pen":
            if self._pen_anchors and math.hypot(doc_pt.x() - self._pen_anchors[0].x, doc_pt.y() - self._pen_anchors[0].y) < 10.0 / self.zoom and len(self._pen_anchors) >= 3:
                self._finish_pen_path(closed=True)
                return
            self._pen_anchors.append(AnchorPoint(doc_pt.x(), doc_pt.y()))
            self._pen_dragging_handle = True
            self._dragging = True
            self._drag_mode = "pen_handle"
            self.update()
            return

        # Curvature Tool
        if self.tool == "curvature":
            self._curv_points.append((doc_pt.x(), doc_pt.y()))
            self.update()
            return

        # Freehand tools (Pencil, Blob Brush, Shaper, Knife)
        if self.tool in ("pencil", "blob_brush", "shaper", "knife"):
            self._freehand_pts = [(doc_pt.x(), doc_pt.y())]
            self._dragging = True
            self._drag_mode = self.tool
            return

        # Shape creation tools & Graph & Artboard
        if self.tool in ("rect", "ellipse", "polygon", "star", "line", "arc", "spiral", "graph", "artboard"):
            self._dragging = True
            self._drag_mode = "create_" + self.tool
            return

        # Shape Builder
        if self.tool == "shape_builder":
            if not self._sb_regions:
                sel = self.selected_objects() or self.doc.iter_all_objects()
                self._sb_regions = compute_planar_regions(sel, self.doc)
            idx = self._hit_sb_region(doc_pt)
            if idx >= 0:
                if event.modifiers() & Qt.AltModifier:
                    self._sb_regions.pop(idx)
                    self._commit_shape_builder_regions()
                else:
                    self._sb_merged_indices = [idx]
                    self._dragging = True
                    self._drag_mode = "shape_builder"
            self.update()
            return

        # Live Paint Bucket
        if self.tool == "live_paint":
            objs = self.selected_objects() or self.doc.iter_all_objects()
            self._sb_regions = compute_planar_regions(objs, self.doc)
            idx = self._hit_sb_region(doc_pt)
            if idx >= 0:
                rpath, _ = self._sb_regions[idx]
                sps = qpath_to_subpaths(rpath)
                if sps:
                    br = rpath.boundingRect()
                    app = Appearance(
                        fills=[AppearanceFill(fill_type="solid", color=copy.deepcopy(self.active_fill_color))],
                        strokes=[AppearanceStroke(stroke_type="none")],
                    )
                    painted = VectorObject(name="Live Paint Fill", kind="path", subpaths=sps,
                                           x=br.x(), y=br.y(), width=br.width(), height=br.height(), appearance=app)
                    self.doc.add_object(painted)
                    self.push_undo("Live Paint Fill")
            return

        # Variable Width Tool
        if self.tool == "width":
            hit = self.hit_test(doc_pt) or (self.selected_objects()[0] if self.selected_objects() else None)
            if hit:
                if hit.id not in self.selected_ids:
                    self.selected_ids = [hit.id]
                    self.selection_changed.emit()
                self._dragging = True
                self._drag_mode = "width_drag"
                self._orig_snapshot_before_drag = self.doc.snapshot_json()
            return

        # Scissors Tool
        if self.tool == "scissors":
            hit = self.hit_test(doc_pt)
            if hit:
                if hit.kind != "path":
                    path_obj = convert_object_to_path(hit, self.doc)
                    self.doc.remove_object(hit.id)
                    self.doc.add_object(path_obj)
                    hit = path_obj
                new_sps = []
                for sp in hit.subpaths:
                    new_sps.extend(split_subpath_at_point(sp, doc_pt.x(), doc_pt.y()))
                if len(new_sps) >= 2:
                    self.doc.remove_object(hit.id)
                    for idx, sp in enumerate(new_sps):
                        br = subpaths_to_qpath([sp]).boundingRect()
                        piece = VectorObject(name=f"{hit.name} Cut {idx + 1}", kind="path", subpaths=[sp],
                                             x=br.x(), y=br.y(), width=br.width(), height=br.height(),
                                             appearance=copy.deepcopy(hit.appearance))
                        self.doc.add_object(piece)
                    self.push_undo("Scissors Cut")
            return

        # Type Tools (Point, Area, Type on Path, Touch Type)
        if self.tool == "type":
            txt, ok = QInputDialog.getText(self, "Point Type", "Enter text:", text="KinoDraw")
            if ok and txt:
                obj = VectorObject(
                    name=f"Text: {txt[:16]}", kind="text", text_mode="point", text=txt,
                    x=doc_pt.x(), y=doc_pt.y() - 24,
                    text_style=TextStyle(font_family="Segoe UI", font_size=42, font_weight=700),
                    appearance=Appearance(fills=[AppearanceFill(color=copy.deepcopy(self.active_fill_color))],
                                          strokes=[AppearanceStroke(stroke_type="none")]),
                )
                self.doc.add_object(obj)
                self.selected_ids = [obj.id]
                self.selection_changed.emit()
                self.push_undo("Add Point Type")
            return

        if self.tool == "area_type":
            self._dragging = True
            self._drag_mode = "create_area_type"
            return

        if self.tool == "type_on_path":
            hit = self.hit_test(doc_pt)
            if hit:
                txt, ok = QInputDialog.getText(self, "Type on a Path", "Text along path:", text="KINODRAW  •  CURVED VECTOR TYPE")
                if ok and txt:
                    qp = object_to_qpath(hit, self.doc)
                    sps = qpath_to_subpaths(qp)
                    obj = VectorObject(
                        name=f"Path Type: {txt[:14]}", kind="text", text_mode="path", text=txt,
                        subpaths=sps,
                        text_style=TextStyle(font_family="Segoe UI", font_size=20, font_weight=700, tracking=1.5),
                        appearance=Appearance(fills=[AppearanceFill(color=copy.deepcopy(self.active_fill_color))],
                                              strokes=[AppearanceStroke(stroke_type="none")]),
                    )
                    self.doc.add_object(obj)
                    self.selected_ids = [obj.id]
                    self.selection_changed.emit()
                    self.push_undo("Type on a Path")
            return

        if self.tool == "touch_type":
            hit = self.hit_test(doc_pt)
            if hit and hit.kind == "text" and hit.text:
                self.selected_ids = [hit.id]
                self.selection_changed.emit()
                # Pick closest character index along text width
                br = object_bounds(hit, self.doc)
                frac = max(0.0, min(0.99, (doc_pt.x() - br.x()) / max(1.0, br.width())))
                self.touch_type_char_idx = int(frac * len(hit.text))
                self._dragging = True
                self._drag_mode = "touch_type_drag"
                self._orig_snapshot_before_drag = self.doc.snapshot_json()
            return

        # Rotate / Scale / Gradient / Blend / Puppet Warp / Symbol Sprayer / Perspective
        if self.tool in ("rotate", "scale"):
            if self.selected_ids:
                self._dragging = True
                self._drag_mode = self.tool
                self._orig_bounds = self.selection_bounds()
                self._orig_snapshot_before_drag = self.doc.snapshot_json()
            return

        if self.tool == "gradient":
            if self.selected_ids:
                self._dragging = True
                self._drag_mode = "gradient_drag"
            return

        if self.tool == "blend":
            hit = self.hit_test(doc_pt)
            if hit:
                if self._blend_first_id is None:
                    self._blend_first_id = hit.id
                    self.selected_ids = [hit.id]
                    self.selection_changed.emit()
                elif hit.id != self._blend_first_id:
                    a = self.doc.find_object(self._blend_first_id)
                    b = hit
                    if a and b:
                        self.doc.remove_object(a.id)
                        self.doc.remove_object(b.id)
                        bl = VectorObject(name="Blend Object", kind="blend", blend_steps=6, children=[a, b])
                        self.doc.add_object(bl)
                        self.selected_ids = [bl.id]
                        self._blend_first_id = None
                        self.selection_changed.emit()
                        self.push_undo("Create Blend")
            return

        if self.tool == "puppet_warp":
            sel = self.selected_objects()
            if not sel:
                hit = self.hit_test(doc_pt)
                if hit:
                    self.selected_ids = [hit.id]
                    sel = [hit]
                    self.selection_changed.emit()
            if sel:
                o = sel[0]
                if o.kind != "path":
                    po = convert_object_to_path(o, self.doc)
                    self.doc.remove_object(o.id)
                    self.doc.add_object(po)
                    self.selected_ids = [po.id]
                    o = po
                if not o.puppet_base_subpaths:
                    o.puppet_base_subpaths = copy.deepcopy(o.subpaths)
                # Hit existing pin?
                pin_idx = -1
                for i, pin in enumerate(o.puppet_pins):
                    if math.hypot(pin.x - doc_pt.x(), pin.y - doc_pt.y()) < 14.0 / self.zoom:
                        pin_idx = i
                        break
                if pin_idx < 0:
                    o.puppet_pins.append(PuppetPin(doc_pt.x(), doc_pt.y(), doc_pt.x(), doc_pt.y()))
                    pin_idx = len(o.puppet_pins) - 1
                self._active_puppet_pin_idx = pin_idx
                self._dragging = True
                self._drag_mode = "puppet_pin"
                self.update()
            return

        if self.tool == "symbol_sprayer":
            sym = self.doc.get_symbol(self.active_symbol_id) or (self.doc.symbols[0] if self.doc.symbols else None)
            if sym:
                inst = VectorObject(
                    name=f"{sym.name} Instance", kind="symbol_instance", symbol_id=sym.id,
                    x=doc_pt.x() - 36, y=doc_pt.y() - 36, width=72, height=72,
                )
                self.doc.add_object(inst)
                self.selected_ids = [inst.id]
                self.selection_changed.emit()
                self.push_undo("Place Symbol")
            return

        if self.tool == "perspective":
            self.doc.perspective.visible = True
            self._dragging = True
            self._drag_mode = "perspective_vp"
            self.update()

    def _press_select(self, pos: QPointF, doc_pt: QPointF, mods) -> None:
        # Check handles on existing selection first
        br = self.selection_bounds()
        if br is not None:
            sr = QRectF(self.doc_to_screen(br.topLeft()), self.doc_to_screen(br.bottomRight())).normalized()
            # Rotate knob
            rot_pt = QPointF(sr.center().x(), sr.top() - 22)
            if math.hypot(pos.x() - rot_pt.x(), pos.y() - rot_pt.y()) <= 9:
                self._dragging = True
                self._drag_mode = "rotate"
                self._orig_bounds = br
                self._orig_snapshot_before_drag = self.doc.snapshot_json()
                return
            # Live corner widget on rect
            sel = self.selected_objects()
            if len(sel) == 1 and sel[0].kind == "shape" and sel[0].shape_type == "rect":
                cw = QPointF(sr.left() + 14 + sel[0].corner_radius * self.zoom * 0.4, sr.top() + 14 + sel[0].corner_radius * self.zoom * 0.4)
                if math.hypot(pos.x() - cw.x(), pos.y() - cw.y()) <= 8:
                    self._dragging = True
                    self._drag_mode = "corner_radius"
                    return
            # 8 resize handles
            for hname, (hx, hy) in self._handle_positions(sr).items():
                if abs(pos.x() - hx) <= 7 and abs(pos.y() - hy) <= 7:
                    self._dragging = True
                    self._drag_mode = "resize"
                    self._active_handle = hname
                    self._orig_bounds = br
                    self._orig_snapshot_before_drag = self.doc.snapshot_json()
                    return

        hit = self.hit_test(doc_pt)
        if hit:
            if mods & Qt.ShiftModifier:
                if hit.id in self.selected_ids:
                    self.selected_ids.remove(hit.id)
                else:
                    self.selected_ids.append(hit.id)
            elif hit.id not in self.selected_ids:
                self.selected_ids = [hit.id]
            self.selection_changed.emit()
            self.update_contextual_bar()
            self._dragging = True
            self._drag_mode = "move"
            self._orig_snapshot_before_drag = self.doc.snapshot_json()
        else:
            if not (mods & Qt.ShiftModifier):
                self.selected_ids = []
                self.selection_changed.emit()
                self.update_contextual_bar()
            self._dragging = True
            self._drag_mode = "marquee"
            self._marquee_rect = QRectF(doc_pt, doc_pt)
        self.update()

    def _press_direct_select(self, pos: QPointF, doc_pt: QPointF) -> None:
        # Check anchors & handles of selected paths
        for o in self.selected_objects():
            if o.kind != "path":
                continue
            for sp_i, sp in enumerate(o.subpaths):
                for a_i, a in enumerate(sp.anchors):
                    for part, (px, py) in [("in", (a.in_x, a.in_y)), ("out", (a.out_x, a.out_y)), ("anchor", (a.x, a.y))]:
                        sp_scr = self.doc_to_screen(QPointF(px, py))
                        if math.hypot(pos.x() - sp_scr.x(), pos.y() - sp_scr.y()) <= 8:
                            self.selected_anchor = (o.id, sp_i, a_i, part)
                            self._dragging = True
                            self._drag_mode = "drag_anchor"
                            self.update()
                            return
        hit = self.hit_test(doc_pt)
        if hit:
            if hit.kind == "shape":
                # Auto-convert live shape to editable Bezier path on direct selection!
                po = convert_object_to_path(hit, self.doc)
                self.doc.remove_object(hit.id)
                self.doc.add_object(po)
                self.selected_ids = [po.id]
                self.push_undo("Convert to Editable Path")
            else:
                self.selected_ids = [hit.id]
            self.selection_changed.emit()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        doc_pt = self.snap_point(self.screen_to_doc(pos))
        self._cursor_doc = doc_pt
        self.cursor_moved.emit(doc_pt.x(), doc_pt.y())

        if not self._dragging:
            if self.tool in ("shape_builder", "live_paint") and self._sb_regions:
                self._sb_hover_idx = self._hit_sb_region(doc_pt)
                self.update()
            elif self.tool in ("pen", "curvature") and (self._pen_anchors or self._curv_points):
                self.update()
            elif self.show_rulers:
                self.update()
            return

        if self._ruler_drag_orient:
            self.update()
            return

        if self._drag_mode == "pan":
            delta = pos - self._drag_start_screen
            self._drag_start_screen = pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self.update_contextual_bar()
            self.update()
            return

        dx = doc_pt.x() - self._drag_last_doc.x()
        dy = doc_pt.y() - self._drag_last_doc.y()

        if self._drag_mode == "move":
            targets = self.selected_objects() + self.global_edit_matches()
            for o in targets:
                translate_object(o, dx, dy)
            # Smart Guides alignment lines against artboard center
            self._smart_guide_lines = []
            br = self.selection_bounds()
            if br and self.doc.smart_guides:
                ab = self.doc.active_artboard()
                ab_cx, ab_cy = ab.x + ab.width * 0.5, ab.y + ab.height * 0.5
                if abs(br.center().x() - ab_cx) < 6.0 / self.zoom:
                    self._smart_guide_lines.append((QPointF(ab_cx, ab.y), QPointF(ab_cx, ab.y + ab.height)))
                if abs(br.center().y() - ab_cy) < 6.0 / self.zoom:
                    self._smart_guide_lines.append((QPointF(ab.x, ab_cy), QPointF(ab.x + ab.width, ab_cy)))
            self._drag_last_doc = doc_pt
            self.update_contextual_bar()
            self.update()
            return

        if self._drag_mode == "marquee":
            self._marquee_rect = QRectF(self._drag_start_doc, doc_pt).normalized()
            self.update()
            return

        if self._drag_mode == "resize" and self._orig_bounds:
            ob = self._orig_bounds
            sx, sy = 1.0, 1.0
            cx, cy = ob.center().x(), ob.center().y()
            if "r" in self._active_handle:
                sx = max(0.05, (doc_pt.x() - ob.left()) / max(1.0, ob.width()))
                cx = ob.left()
            elif "l" in self._active_handle:
                sx = max(0.05, (ob.right() - doc_pt.x()) / max(1.0, ob.width()))
                cx = ob.right()
            if "b" in self._active_handle:
                sy = max(0.05, (doc_pt.y() - ob.top()) / max(1.0, ob.height()))
                cy = ob.top()
            elif "t" in self._active_handle:
                sy = max(0.05, (ob.bottom() - doc_pt.y()) / max(1.0, ob.height()))
                cy = ob.bottom()
            if event.modifiers() & Qt.ShiftModifier:
                s = max(sx, sy)
                sx = sy = s
            # Incremental step from last frame using original snapshot would be exact; use clean delta transform
            if self._orig_snapshot_before_drag:
                self._restore_json_quiet(self._orig_snapshot_before_drag)
                tr = QTransform()
                tr.translate(cx, cy)
                tr.scale(sx, sy)
                tr.translate(-cx, -cy)
                for o in self.selected_objects() + self.global_edit_matches():
                    transform_object_affine(o, tr, self.doc)
            self.update_contextual_bar()
            self.update()
            return

        if self._drag_mode == "rotate" and self._orig_bounds and self._orig_snapshot_before_drag:
            c = self._orig_bounds.center()
            a0 = math.atan2(self._drag_start_doc.y() - c.y(), self._drag_start_doc.x() - c.x())
            a1 = math.atan2(doc_pt.y() - c.y(), doc_pt.x() - c.x())
            deg = math.degrees(a1 - a0)
            if event.modifiers() & Qt.ShiftModifier:
                deg = round(deg / 15.0) * 15.0
            self._restore_json_quiet(self._orig_snapshot_before_drag)
            tr = QTransform()
            tr.translate(c.x(), c.y())
            tr.rotate(deg)
            tr.translate(-c.x(), -c.y())
            for o in self.selected_objects() + self.global_edit_matches():
                transform_object_affine(o, tr, self.doc)
            self.update_contextual_bar()
            self.update()
            return

        if self._drag_mode == "scale" and self._orig_bounds and self._orig_snapshot_before_drag:
            c = self._orig_bounds.center()
            d0 = max(10.0, math.hypot(self._drag_start_doc.x() - c.x(), self._drag_start_doc.y() - c.y()))
            d1 = max(5.0, math.hypot(doc_pt.x() - c.x(), doc_pt.y() - c.y()))
            s = max(0.08, min(10.0, d1 / d0))
            self._restore_json_quiet(self._orig_snapshot_before_drag)
            tr = QTransform()
            tr.translate(c.x(), c.y())
            tr.scale(s, s)
            tr.translate(-c.x(), -c.y())
            for o in self.selected_objects():
                transform_object_affine(o, tr, self.doc)
            self.update()
            return

        if self._drag_mode == "corner_radius":
            sel = self.selected_objects()
            if len(sel) == 1 and sel[0].kind == "shape":
                d = max(0.0, doc_pt.x() - sel[0].x)
                sel[0].corner_radius = min(min(sel[0].width, sel[0].height) * 0.5, d)
                self.update()
            return

        if self._drag_mode == "drag_anchor" and self.selected_anchor:
            oid, sp_i, a_i, part = self.selected_anchor
            o = self.doc.find_object(oid)
            if o and sp_i < len(o.subpaths) and a_i < len(o.subpaths[sp_i].anchors):
                a = o.subpaths[sp_i].anchors[a_i]
                if part == "anchor":
                    a.translate(dx, dy)
                elif part == "in":
                    a.in_x, a.in_y = doc_pt.x(), doc_pt.y()
                elif part == "out":
                    a.out_x, a.out_y = doc_pt.x(), doc_pt.y()
            self._drag_last_doc = doc_pt
            self.update()
            return

        if self._drag_mode == "pen_handle" and self._pen_anchors:
            a = self._pen_anchors[-1]
            a.out_x, a.out_y = doc_pt.x(), doc_pt.y()
            a.in_x = 2 * a.x - doc_pt.x()
            a.in_y = 2 * a.y - doc_pt.y()
            a.point_type = "smooth"
            self.update()
            return

        if self._drag_mode in ("pencil", "blob_brush", "shaper", "knife"):
            if not self._freehand_pts or math.hypot(doc_pt.x() - self._freehand_pts[-1][0], doc_pt.y() - self._freehand_pts[-1][1]) >= 2.5:
                self._freehand_pts.append((doc_pt.x(), doc_pt.y()))
            self.update()
            return

        if self._drag_mode.startswith("create_"):
            kind = self._drag_mode[7:]
            r = QRectF(self._drag_start_doc, doc_pt).normalized()
            if event.modifiers() & Qt.ShiftModifier:
                s = max(r.width(), r.height())
                r.setWidth(s)
                r.setHeight(s)
            if kind == "line":
                self._preview_shape = VectorObject(
                    name="Line", kind="shape", shape_type="line",
                    x=self._drag_start_doc.x(), y=self._drag_start_doc.y(),
                    width=doc_pt.x() - self._drag_start_doc.x(), height=doc_pt.y() - self._drag_start_doc.y(),
                    appearance=Appearance(fills=[AppearanceFill(fill_type="none")],
                                          strokes=[AppearanceStroke(color=copy.deepcopy(self.active_stroke_color), width=max(1.5, self.active_stroke_width), brush_id=self.active_brush_id)]),
                )
            elif kind == "graph":
                self._preview_shape = VectorObject(name="Data Graph", kind="graph", graph_type="bar",
                                                   x=r.x(), y=r.y(), width=max(120, r.width()), height=max(90, r.height()))
            elif kind == "area_type":
                self._preview_shape = VectorObject(
                    name="Area Text", kind="text", text_mode="area",
                    text="KinoDraw Area Typography wraps smoothly inside this frame and supports threading & wrap around objects.",
                    x=r.x(), y=r.y(), width=max(80, r.width()), height=max(50, r.height()),
                    text_style=TextStyle(font_size=16),
                    appearance=Appearance(fills=[AppearanceFill(color=copy.deepcopy(self.active_fill_color))], strokes=[AppearanceStroke(stroke_type="none")]),
                )
            elif kind == "artboard":
                self._preview_shape = VectorObject(
                    name="New Artboard Preview", kind="shape", shape_type="rect",
                    x=r.x(), y=r.y(), width=r.width(), height=r.height(),
                    appearance=Appearance(fills=[AppearanceFill(color=Color(255, 255, 255, 50))],
                                          strokes=[AppearanceStroke(color=Color.from_hex("#FF9A00"), width=1.5, dash_pattern=[6, 4])]),
                )
            else:
                if self.doc.perspective.visible and self.doc.perspective.active_plane != "none" and kind == "rect":
                    sp = project_rect_to_perspective(r, self.doc.perspective)
                    self._preview_shape = VectorObject(name="Perspective Plane Shape", kind="path", subpaths=[sp],
                                                       x=r.x(), y=r.y(), width=r.width(), height=r.height(),
                                                       appearance=self.make_default_appearance())
                else:
                    self._preview_shape = VectorObject(
                        name=kind.title(), kind="shape", shape_type=kind,
                        x=r.x(), y=r.y(), width=max(2.0, r.width()), height=max(2.0, r.height()),
                        appearance=self.make_default_appearance(),
                    )
            self.update()
            return

        if self._drag_mode == "shape_builder":
            idx = self._hit_sb_region(doc_pt)
            if idx >= 0 and idx not in self._sb_merged_indices:
                self._sb_merged_indices.append(idx)
                self.update()
            return

        if self._drag_mode == "width_drag":
            sel = self.selected_objects()
            if sel:
                o = sel[0]
                st = o.appearance.primary_stroke
                if st.stroke_type == "none":
                    st.stroke_type = "solid"
                    st.width = max(4.0, st.width)
                qp = object_to_qpath(o, self.doc)
                # Find nearest t on path to drag start
                best_t, best_d = 0.5, 1e18
                for k in range(33):
                    t = k / 32.0
                    pt = qp.pointAtPercent(t)
                    d = math.hypot(pt.x() - self._drag_start_doc.x(), pt.y() - self._drag_start_doc.y())
                    if d < best_d:
                        best_d = d
                        best_t = t
                dist = math.hypot(doc_pt.x() - self._drag_start_doc.x(), doc_pt.y() - self._drag_start_doc.y())
                scale_w = max(0.1, min(6.0, dist / max(2.0, st.width * 0.5)))
                if not st.width_stations:
                    st.width_stations = [WidthStation(0.0, 1.0, 1.0), WidthStation(1.0, 1.0, 1.0)]
                # Update or insert station near best_t
                updated = False
                for ws in st.width_stations:
                    if abs(ws.t - best_t) < 0.08:
                        ws.left_scale = scale_w
                        ws.right_scale = scale_w
                        updated = True
                        break
                if not updated:
                    st.width_stations.append(WidthStation(best_t, scale_w, scale_w))
                    st.width_stations.sort(key=lambda w: w.t)
                st.width_profile_name = "Custom"
                self.update()
            return

        if self._drag_mode == "touch_type_drag" and self.touch_type_char_idx >= 0:
            sel = self.selected_objects()
            if sel and sel[0].kind == "text":
                o = sel[0]
                key = str(self.touch_type_char_idx)
                ct = o.char_transforms.setdefault(key, CharTransform())
                if event.modifiers() & Qt.ShiftModifier:
                    ct.scale_x = max(0.3, min(3.5, ct.scale_x + dx * 0.01))
                    ct.scale_y = max(0.3, min(3.5, ct.scale_y - dy * 0.01))
                elif event.modifiers() & Qt.AltModifier:
                    ct.rotation = (ct.rotation + dx * 0.8) % 360.0
                else:
                    ct.dx += dx
                    ct.dy += dy
                self._drag_last_doc = doc_pt
                self.update()
            return

        if self._drag_mode == "gradient_drag":
            sel = self.selected_objects()
            if sel:
                o = sel[0]
                f = o.appearance.primary_fill
                if f.fill_type != "gradient" or not f.gradient:
                    f.fill_type = "gradient"
                    f.gradient = GradientDef()
                ang = math.degrees(math.atan2(doc_pt.y() - self._drag_start_doc.y(), doc_pt.x() - self._drag_start_doc.x()))
                f.gradient.angle = ang
                self.update()
            return

        if self._drag_mode == "puppet_pin" and self._active_puppet_pin_idx >= 0:
            sel = self.selected_objects()
            if sel:
                o = sel[0]
                if self._active_puppet_pin_idx < len(o.puppet_pins):
                    o.puppet_pins[self._active_puppet_pin_idx].x = doc_pt.x()
                    o.puppet_pins[self._active_puppet_pin_idx].y = doc_pt.y()
                    o.subpaths = apply_puppet_warp(o.puppet_base_subpaths, o.puppet_pins)
                    self.update()
            return

        if self._drag_mode == "perspective_vp":
            pg = self.doc.perspective
            if abs(doc_pt.x() - pg.vp_left_x) < abs(doc_pt.x() - pg.vp_right_x):
                pg.vp_left_x = doc_pt.x()
            else:
                pg.vp_right_x = doc_pt.x()
            pg.horizon_y = doc_pt.y()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            return
        pos = event.position()
        doc_pt = self.snap_point(self.screen_to_doc(pos))
        self._dragging = False
        self._smart_guide_lines = []

        if self._ruler_drag_orient:
            g = Guide(orientation=self._ruler_drag_orient,
                      position=doc_pt.y() if self._ruler_drag_orient == "h" else doc_pt.x())
            self.doc.guides.append(g)
            self._ruler_drag_orient = None
            self.push_undo("Add Guide")
            return

        if self._drag_mode == "pan":
            self.setCursor(Qt.OpenHandCursor if self.tool == "hand" else Qt.ArrowCursor)
            self._drag_mode = ""
            return

        if self._drag_mode == "marquee" and self._marquee_rect:
            r = self._marquee_rect
            self.selected_ids = [o.id for o in self.doc.iter_all_objects() if not o.locked and object_bounds(o, self.doc).intersects(r)]
            self._marquee_rect = None
            self.selection_changed.emit()
            self.update_contextual_bar()
            self.update()
            return

        if self._drag_mode in ("move", "resize", "rotate", "scale", "corner_radius", "drag_anchor", "width_drag", "touch_type_drag", "gradient_drag", "puppet_pin", "perspective_vp"):
            self._orig_snapshot_before_drag = None
            self.push_undo(self._drag_mode.replace("_", " ").title())
            self._drag_mode = ""
            return

        if self._drag_mode == "pencil" and len(self._freehand_pts) >= 2:
            simp = rdp_simplify(self._freehand_pts, max(2.0, 3.0 / self.zoom))
            sp = fit_catmull_rom_subpath(simp, closed=False, tension=0.45)
            br = subpaths_to_qpath([sp]).boundingRect()
            obj = VectorObject(
                name="Pencil Path", kind="path", subpaths=[sp],
                x=br.x(), y=br.y(), width=br.width(), height=br.height(),
                appearance=Appearance(fills=[AppearanceFill(fill_type="none")],
                                      strokes=[AppearanceStroke(color=copy.deepcopy(self.active_stroke_color), width=max(1.5, self.active_stroke_width), brush_id=self.active_brush_id)]),
            )
            self.doc.add_object(obj)
            self.selected_ids = [obj.id]
            self._freehand_pts = []
            self.selection_changed.emit()
            self.push_undo("Pencil Draw")
            return

        if self._drag_mode == "blob_brush" and len(self._freehand_pts) >= 2:
            from .geometry import outline_stroke_qpath
            simp = rdp_simplify(self._freehand_pts, 2.5)
            sp = fit_catmull_rom_subpath(simp, closed=False)
            raw_qp = subpaths_to_qpath([sp])
            st = AppearanceStroke(width=max(10.0, self.active_stroke_width * 4.0), cap="round", join="round")
            blob_qp = outline_stroke_qpath(raw_qp, st)
            fill_hex = self.active_fill_color.to_hex()
            # Merge with overlapping same-color paths!
            merged_any = False
            for existing in list(self.doc.active_layer().objects):
                if existing.kind == "path" and existing.appearance.primary_fill.fill_type == "solid" and existing.appearance.primary_fill.color.to_hex() == fill_hex:
                    eqp = object_to_qpath(existing, self.doc)
                    if eqp.intersects(blob_qp):
                        blob_qp = eqp.united(blob_qp).simplified()
                        self.doc.remove_object(existing.id)
                        merged_any = True
            sps = qpath_to_subpaths(blob_qp)
            if sps:
                br = blob_qp.boundingRect()
                obj = VectorObject(
                    name="Blob Brush Shape", kind="path", subpaths=sps,
                    x=br.x(), y=br.y(), width=br.width(), height=br.height(),
                    appearance=Appearance(fills=[AppearanceFill(color=copy.deepcopy(self.active_fill_color))],
                                          strokes=[AppearanceStroke(stroke_type="none")]),
                )
                self.doc.add_object(obj)
                self.selected_ids = [obj.id]
                self.selection_changed.emit()
                self.push_undo("Blob Brush Merge" if merged_any else "Blob Brush")
            self._freehand_pts = []
            return

        if self._drag_mode == "shaper" and len(self._freehand_pts) >= 4:
            kind, info = recognize_shaper_gesture(self._freehand_pts)
            self._freehand_pts = []
            if kind == "scribble":
                # Erase overlapped shapes in scribble bounding box
                sr = QRectF(info["x"], info["y"], info["w"], info["h"])
                removed = False
                for o in list(self.doc.active_layer().objects):
                    if object_bounds(o, self.doc).intersects(sr):
                        self.doc.remove_object(o.id)
                        removed = True
                if removed:
                    self.selected_ids = []
                    self.selection_changed.emit()
                    self.push_undo("Shaper Scribble Erase")
            elif kind != "none":
                st_type = "polygon" if kind in ("triangle", "polygon") else kind
                sides = 3 if kind == "triangle" else int(info.get("sides", 6))
                obj = VectorObject(
                    name=f"Shaper {kind.title()}", kind="shape", shape_type=st_type,
                    x=info["x"], y=info["y"], width=info["w"], height=info["h"], sides=sides,
                    appearance=self.make_default_appearance(),
                )
                self.doc.add_object(obj)
                self.selected_ids = [obj.id]
                self.selection_changed.emit()
                self.push_undo(f"Shaper {kind.title()}")
            self.update()
            return

        if self._drag_mode == "knife" and len(self._freehand_pts) >= 2:
            cut_pts = list(self._freehand_pts)
            self._freehand_pts = []
            targets = self.selected_objects() or self.doc.active_layer().objects
            sliced_any = False
            for o in list(targets):
                pieces = knife_slice_object(o, cut_pts, self.doc)
                if len(pieces) >= 2:
                    self.doc.remove_object(o.id)
                    for pc in pieces:
                        self.doc.add_object(pc)
                    sliced_any = True
            if sliced_any:
                self.selected_ids = []
                self.selection_changed.emit()
                self.push_undo("Knife Slice")
            self.update()
            return

        if self._drag_mode == "shape_builder":
            if len(self._sb_merged_indices) >= 2:
                merged_qp = QPainterPath()
                app = copy.deepcopy(self._sb_regions[self._sb_merged_indices[0]][1])
                for idx in self._sb_merged_indices:
                    merged_qp = merged_qp.united(self._sb_regions[idx][0])
                remaining = [r for i, r in enumerate(self._sb_regions) if i not in self._sb_merged_indices]
                remaining.append((merged_qp.simplified(), app))
                self._sb_regions = remaining
                self._commit_shape_builder_regions()
            self._sb_merged_indices = []
            self.update()
            return

        if self._drag_mode.startswith("create_") and self._preview_shape is not None:
            obj = self._preview_shape
            self._preview_shape = None
            if self._drag_mode == "create_artboard":
                if obj.width > 20 and obj.height > 20:
                    ab = Artboard(name=f"Artboard {len(self.doc.artboards) + 1}",
                                  x=obj.x, y=obj.y, width=obj.width, height=obj.height)
                    self.doc.artboards.append(ab)
                    self.doc.active_artboard_index = len(self.doc.artboards) - 1
                    self.push_undo("Create Artboard")
            else:
                self.doc.add_object(obj)
                self.selected_ids = [obj.id]
                self.selection_changed.emit()
                self.push_undo(f"Create {obj.name}")
            self._drag_mode = ""
            return

        self._drag_mode = ""
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.tool == "pen" and len(self._pen_anchors) >= 2:
            self._finish_pen_path(closed=False)
            return
        if self.tool == "curvature" and len(self._curv_points) >= 2:
            self._finish_curvature_path()
            return
        if self.tool == "select":
            doc_pt = self.screen_to_doc(event.position())
            hit = self.hit_test(doc_pt)
            if hit and hit.kind == "text":
                self.context_action.emit("edit_text")
            elif hit and hit.kind == "graph":
                self.context_action.emit("edit_graph")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        k = event.key()
        if k == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = True
            self.setCursor(Qt.OpenHandCursor)
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self._commit_open_builders()
            return
        if k == Qt.Key_Escape:
            self._pen_anchors = []
            self._curv_points = []
            self._freehand_pts = []
            self.selected_ids = []
            self.selection_changed.emit()
            self.update_contextual_bar()
            self.update()
            return
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.selected_ids:
                for oid in list(self.selected_ids):
                    self.doc.remove_object(oid)
                self.selected_ids = []
                self.selection_changed.emit()
                self.push_undo("Delete")
            return
        # Arrow nudge
        step = 10.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0
        nudge = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}
        if k in nudge and self.selected_ids:
            dx, dy = nudge[k]
            for o in self.selected_objects() + self.global_edit_matches():
                translate_object(o, dx, dy)
            self.push_undo("Nudge")
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_pan = False
            self.setCursor(Qt.OpenHandCursor if self.tool == "hand" else Qt.ArrowCursor)
        super().keyReleaseEvent(event)

    # ------------------------------------------------------------------
    # Internal Builder Helpers
    # ------------------------------------------------------------------

    def _restore_json_quiet(self, raw_json: str) -> None:
        import json
        restored = Document.from_dict(json.loads(raw_json))
        self.doc.layers = restored.layers

    def _hit_sb_region(self, doc_pt: QPointF) -> int:
        for i, (rpath, _) in enumerate(self._sb_regions):
            if rpath.contains(doc_pt):
                return i
        return -1

    def _commit_shape_builder_regions(self) -> None:
        for oid in list(self.selected_ids):
            self.doc.remove_object(oid)
        new_ids: List[str] = []
        for idx, (rpath, rapp) in enumerate(self._sb_regions):
            sps = qpath_to_subpaths(rpath)
            if sps:
                br = rpath.boundingRect()
                o = VectorObject(name=f"Built Shape {idx + 1}", kind="path", subpaths=sps,
                                 x=br.x(), y=br.y(), width=br.width(), height=br.height(), appearance=copy.deepcopy(rapp))
                self.doc.add_object(o)
                new_ids.append(o.id)
        self.selected_ids = new_ids
        self.selection_changed.emit()
        self.push_undo("Shape Builder")

    def _finish_pen_path(self, closed: bool) -> None:
        if len(self._pen_anchors) < 2:
            self._pen_anchors = []
            return
        sp = SubPath(anchors=list(self._pen_anchors), closed=closed)
        br = subpaths_to_qpath([sp]).boundingRect()
        app = self.make_default_appearance()
        if not closed:
            app.fills = [AppearanceFill(fill_type="none")]
        obj = VectorObject(name="Pen Path", kind="path", subpaths=[sp],
                           x=br.x(), y=br.y(), width=br.width(), height=br.height(), appearance=app)
        self.doc.add_object(obj)
        self._pen_anchors = []
        self.selected_ids = [obj.id]
        self.selection_changed.emit()
        self.push_undo("Pen Path")

    def _finish_curvature_path(self) -> None:
        if len(self._curv_points) < 2:
            self._curv_points = []
            return
        closed = math.hypot(self._curv_points[0][0] - self._curv_points[-1][0], self._curv_points[0][1] - self._curv_points[-1][1]) < 24.0
        pts = self._curv_points[:-1] if closed and len(self._curv_points) > 3 else self._curv_points
        sp = fit_catmull_rom_subpath(pts, closed=closed, tension=0.55)
        br = subpaths_to_qpath([sp]).boundingRect()
        app = self.make_default_appearance()
        if not closed:
            app.fills = [AppearanceFill(fill_type="none")]
        obj = VectorObject(name="Curvature Path", kind="path", subpaths=[sp],
                           x=br.x(), y=br.y(), width=br.width(), height=br.height(), appearance=app)
        self.doc.add_object(obj)
        self._curv_points = []
        self.selected_ids = [obj.id]
        self.selection_changed.emit()
        self.push_undo("Curvature Path")

    def _commit_open_builders(self) -> None:
        if self._pen_anchors:
            self._finish_pen_path(closed=False)
        if self._curv_points:
            self._finish_curvature_path()
