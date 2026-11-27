"""High-precision Qt6 vector rendering engine for Vectora.

Renders multi-artboard documents, stackable Appearance (solid/gradient/freeform/mesh/pattern
fills; uniform/variable-width/gradient-along/dashed/brush strokes), live effects (drop shadow,
glow, blur, warp, roughen, 3D extrusion & materials), clipping & opacity masks, rich text
(point, area, on-path, Touch Type, threading, text wrap), data charts, blends, repeats,
studio product mockups, and Illustrator view modes (Outline, Pixel, Overprint, Separations,
Flattener Preview).
"""
from __future__ import annotations

import base64
import copy
import math
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTransform,
)

from .geometry import (
    _layout_text_lines,
    apply_roughen_to_qpath,
    apply_warp_to_qpath,
    build_corner_aligned_dash_path,
    build_qfont,
    build_variable_width_path,
    generate_blend_steps,
    get_width_stations,
    object_bounds,
    object_to_qpath,
    offset_qpath,
    subpaths_to_qpath,
)
from .models import (
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Artboard,
    BrushDef,
    Color,
    Document,
    GradientDef,
    Layer,
    LiveEffect,
    PatternDef,
    PerspectiveGridState,
    VectorObject,
)

BLEND_MODES = {
    "Normal": QPainter.CompositionMode_SourceOver,
    "Multiply": QPainter.CompositionMode_Multiply,
    "Screen": QPainter.CompositionMode_Screen,
    "Overlay": QPainter.CompositionMode_Overlay,
    "Darken": QPainter.CompositionMode_Darken,
    "Lighten": QPainter.CompositionMode_Lighten,
    "ColorDodge": QPainter.CompositionMode_ColorDodge,
    "ColorBurn": QPainter.CompositionMode_ColorBurn,
    "HardLight": QPainter.CompositionMode_HardLight,
    "SoftLight": QPainter.CompositionMode_SoftLight,
    "Difference": QPainter.CompositionMode_Difference,
    "Exclusion": QPainter.CompositionMode_Exclusion,
}

_IMAGE_CACHE: Dict[str, QImage] = {}


class ViewOptions:
    def __init__(self):
        self.outline_mode: bool = False
        self.pixel_preview: bool = False
        self.overprint_preview: bool = False
        self.separations_preview: bool = False
        self.sep_plates: Dict[str, bool] = {"C": True, "M": True, "Y": True, "K": True, "SPOT": True}
        self.flattener_preview: bool = False
        self.show_artboards: bool = True
        self.show_guides: bool = True
        self.show_grid: bool = True
        self.show_bleed: bool = True
        self.show_crop_marks: bool = True
        self.export_mode: bool = False


def to_qcolor(c: Color, opacity: float = 1.0, overprint_sim: bool = False) -> QColor:
    r, g, b = c.r, c.g, c.b
    if overprint_sim:
        # Simulate CMYK print gamut slightly softer vibrant blues/greens
        cf, mf, yf, kf = c.c / 100.0, c.m / 100.0, c.y / 100.0, c.k / 100.0
        r = int(round(255 * (1.0 - cf * 0.96) * (1.0 - kf * 0.94)))
        g = int(round(255 * (1.0 - mf * 0.94) * (1.0 - kf * 0.94)))
        b = int(round(255 * (1.0 - yf * 0.92) * (1.0 - kf * 0.94)))
    a = max(0, min(255, int(round(c.a * max(0.0, min(1.0, opacity))))))
    return QColor(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), a)


def load_object_qimage(obj: VectorObject) -> Optional[QImage]:
    key = f"{obj.id}:{obj.image_path}:{len(obj.image_embedded_b64)}"
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]
    img: Optional[QImage] = None
    if obj.image_embedded_b64:
        try:
            raw = base64.b64decode(obj.image_embedded_b64)
            qimg = QImage()
            if qimg.loadFromData(raw):
                img = qimg
        except Exception:
            img = None
    if img is None and obj.image_path and os.path.exists(obj.image_path):
        ext = os.path.splitext(obj.image_path)[1].lower()
        if ext == ".psd":
            img = _load_psd_preview(obj.image_path)
        else:
            qimg = QImage(obj.image_path)
            if not qimg.isNull():
                img = qimg
            else:
                try:
                    pil = Image.open(obj.image_path).convert("RGBA")
                    data = pil.tobytes("raw", "RGBA")
                    img = QImage(data, pil.width, pil.height, QImage.Format_RGBA8888).copy()
                except Exception:
                    img = None
    if img is not None:
        _IMAGE_CACHE[key] = img
    return img


def _load_psd_preview(path: str) -> Optional[QImage]:
    try:
        pil = Image.open(path).convert("RGBA")
        data = pil.tobytes("raw", "RGBA")
        return QImage(data, pil.width, pil.height, QImage.Format_RGBA8888).copy()
    except Exception:
        # Render a crisp placeholder card for unreadable PSD/PDF files
        img = QImage(400, 300, QImage.Format_RGBA8888)
        img.fill(QColor("#2D3340"))
        p = QPainter(img)
        p.setPen(QColor("#FF9A00"))
        p.setFont(QFont("Segoe UI", 18, QFont.Bold))
        p.drawText(QRectF(0, 0, 400, 300), Qt.AlignCenter, f"Placed File\n{os.path.basename(path)}")
        p.end()
        return img


# ---------------------------------------------------------------------------
# Pattern, Freeform Gradient, and Gradient Mesh Synthesizers
# ---------------------------------------------------------------------------

def render_pattern_tile(pat: PatternDef) -> QPixmap:
    s = max(12, int(round(pat.tile_size * pat.scale)))
    pm = QPixmap(s, s)
    pm.fill(to_qcolor(pat.bg_color))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    fg = to_qcolor(pat.fg_color)
    ac = to_qcolor(pat.accent_color)

    if pat.kind == "dots":
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        p.drawEllipse(QPointF(s * 0.25, s * 0.25), s * 0.14, s * 0.14)
        p.setBrush(ac)
        p.drawEllipse(QPointF(s * 0.75, s * 0.75), s * 0.14, s * 0.14)
    elif pat.kind == "stripes":
        p.setPen(QPen(fg, max(2.0, s * 0.22)))
        p.drawLine(0, s, s, 0)
        p.drawLine(-s // 2, s // 2, s // 2, -s // 2)
        p.drawLine(s // 2, s + s // 2, s + s // 2, s // 2)
    elif pat.kind == "grid":
        p.setPen(QPen(fg, max(1.0, s * 0.06)))
        p.drawLine(0, 0, s, 0)
        p.drawLine(0, 0, 0, s)
        p.setPen(QPen(ac, max(1.0, s * 0.04)))
        p.drawLine(0, s // 2, s, s // 2)
        p.drawLine(s // 2, 0, s // 2, s)
    elif pat.kind == "chevron":
        p.setPen(QPen(fg, max(2.0, s * 0.12), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(0, int(s * 0.65), s // 2, int(s * 0.25))
        p.drawLine(s // 2, int(s * 0.25), s, int(s * 0.65))
        p.setPen(QPen(ac, max(1.5, s * 0.08)))
        p.drawLine(0, int(s * 0.95), s // 2, int(s * 0.55))
        p.drawLine(s // 2, int(s * 0.55), s, int(s * 0.95))
    elif pat.kind == "waves":
        path = QPainterPath()
        path.moveTo(0, s * 0.5)
        path.cubicTo(s * 0.25, s * 0.15, s * 0.25, s * 0.85, s * 0.5, s * 0.5)
        path.cubicTo(s * 0.75, s * 0.15, s * 0.75, s * 0.85, s, s * 0.5)
        p.setPen(QPen(fg, max(1.5, s * 0.1)))
        p.drawPath(path)
    elif pat.kind == "terrazzo":
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        p.drawPolygon([QPointF(s * 0.1, s * 0.2), QPointF(s * 0.45, s * 0.12), QPointF(s * 0.35, s * 0.45)])
        p.setBrush(ac)
        p.drawPolygon([QPointF(s * 0.55, s * 0.55), QPointF(s * 0.9, s * 0.48), QPointF(s * 0.82, s * 0.88), QPointF(s * 0.52, s * 0.80)])
        p.setBrush(QColor(255, 255, 255, 180))
        p.drawEllipse(QPointF(s * 0.75, s * 0.22), s * 0.09, s * 0.06)
    elif pat.kind == "botanical":
        p.setPen(QPen(fg, max(1.2, s * 0.05)))
        p.setBrush(ac)
        leaf = QPainterPath()
        leaf.moveTo(s * 0.2, s * 0.8)
        leaf.quadTo(s * 0.25, s * 0.2, s * 0.8, s * 0.2)
        leaf.quadTo(s * 0.75, s * 0.75, s * 0.2, s * 0.8)
        p.drawPath(leaf)
        p.drawLine(QPointF(s * 0.2, s * 0.8), QPointF(s * 0.8, s * 0.2))
    elif pat.kind == "stars":
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        star = QPainterPath()
        cx, cy = s * 0.5, s * 0.5
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = s * 0.32 if i % 2 == 0 else s * 0.13
            pt = QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang))
            star.moveTo(pt) if i == 0 else star.lineTo(pt)
        star.closeSubpath()
        p.drawPath(star)
    elif pat.kind == "memphis":
        p.setPen(QPen(fg, max(1.6, s * 0.07)))
        p.drawLine(QPointF(s * 0.12, s * 0.25), QPointF(s * 0.38, s * 0.12))
        p.setBrush(ac)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(s * 0.72, s * 0.30), s * 0.12, s * 0.12)
        p.setBrush(fg)
        p.drawRect(QRectF(s * 0.18, s * 0.62, s * 0.24, s * 0.24))
    elif pat.kind == "art_deco":
        p.setPen(QPen(fg, max(1.2, s * 0.06)))
        p.setBrush(Qt.NoBrush)
        for rad in (0.48, 0.34, 0.20):
            p.drawArc(QRectF(s * (0.5 - rad), s * (1.0 - rad), s * rad * 2, s * rad * 2), 0, 180 * 16)
    p.end()
    return pm


def render_freeform_or_mesh_image(grad: GradientDef, w: int, h: int, opacity: float = 1.0) -> QImage:
    """Fast vectorized NumPy Freeform Gradient and Gradient Mesh rasterizer."""
    rw = max(16, min(240, w))
    rh = max(16, min(240, h))
    yy, xx = np.mgrid[0:rh, 0:rw].astype(np.float32)
    u = xx / max(1.0, rw - 1)
    v = yy / max(1.0, rh - 1)

    if grad.kind == "freeform":
        grad.ensure_freeform()
        pts = grad.freeform_points
        num = np.zeros((rh, rw, 4), dtype=np.float32)
        den = np.zeros((rh, rw, 1), dtype=np.float32) + 1e-6
        for pt in pts:
            dist2 = (u - pt.x) ** 2 + (v - pt.y) ** 2 + (0.04 + pt.spread * 0.12) ** 2
            wt = 1.0 / (dist2 ** 1.35)
            col = np.array([pt.color.r, pt.color.g, pt.color.b, pt.color.a * opacity], dtype=np.float32)
            num += wt[:, :, None] * col[None, None, :]
            den += wt[:, :, None]
        rgba = np.clip(num / den, 0, 255).astype(np.uint8)
    else:  # mesh gradient
        grad.ensure_mesh()
        rows, cols = max(2, grad.mesh_rows), max(2, grad.mesh_cols)
        grid = np.zeros((rows, cols, 4), dtype=np.float32)
        for r_i in range(rows):
            for c_i in range(cols):
                c = grad.mesh_colors[r_i * cols + c_i]
                grid[r_i, c_i] = [c.r, c.g, c.b, c.a * opacity]
        # Smooth bicubic-like cosine-interpolated bilinear sampling
        gu = u * (cols - 1)
        gv = v * (rows - 1)
        c0 = np.clip(np.floor(gu).astype(np.int32), 0, cols - 2)
        r0 = np.clip(np.floor(gv).astype(np.int32), 0, rows - 2)
        fu = 0.5 - 0.5 * np.cos((gu - c0) * np.pi)
        fv = 0.5 - 0.5 * np.cos((gv - r0) * np.pi)
        c00 = grid[r0, c0]
        c10 = grid[r0, c0 + 1]
        c01 = grid[r0 + 1, c0]
        c11 = grid[r0 + 1, c0 + 1]
        top = c00 * (1 - fu[:, :, None]) + c10 * fu[:, :, None]
        bot = c01 * (1 - fu[:, :, None]) + c11 * fu[:, :, None]
        rgba = np.clip(top * (1 - fv[:, :, None]) + bot * fv[:, :, None], 0, 255).astype(np.uint8)

    qimg = QImage(rgba.data, rw, rh, rw * 4, QImage.Format_RGBA8888).copy()
    return qimg


def build_qbrush_for_fill(fill: AppearanceFill, rect: QRectF, opacity: float = 1.0,
                          overprint_sim: bool = False) -> Optional[QBrush]:
    if not fill.visible or fill.fill_type == "none":
        return None
    eff_op = fill.opacity * opacity
    if fill.fill_type == "solid":
        return QBrush(to_qcolor(fill.color, eff_op, overprint_sim))
    if fill.fill_type == "gradient" and fill.gradient:
        g = fill.gradient
        if g.kind in ("freeform", "mesh"):
            return None  # handled via direct clipped QImage draw
        if g.kind == "radial":
            cx = rect.x() + g.cx * rect.width()
            cy = rect.y() + g.cy * rect.height()
            fx = rect.x() + g.fx * rect.width()
            fy = rect.y() + g.fy * rect.height()
            rad = max(1.0, g.radius * max(rect.width(), rect.height()))
            rg = QRadialGradient(cx, cy, rad, fx, fy)
            for st in g.stops:
                rg.setColorAt(max(0.0, min(1.0, st.offset)), to_qcolor(st.color, eff_op, overprint_sim))
            return QBrush(rg)
        else:
            ang = math.radians(g.angle)
            cx, cy = rect.center().x(), rect.center().y()
            half = max(1.0, math.hypot(rect.width(), rect.height()) * 0.5)
            dx, dy = math.cos(ang) * half, math.sin(ang) * half
            lg = QLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy)
            for st in g.stops:
                lg.setColorAt(max(0.0, min(1.0, st.offset)), to_qcolor(st.color, eff_op, overprint_sim))
            return QBrush(lg)
    if fill.fill_type == "pattern" and fill.pattern:
        pm = render_pattern_tile(fill.pattern)
        br = QBrush(pm)
        if abs(fill.pattern.rotation) > 1e-3:
            tr = QTransform()
            tr.rotate(fill.pattern.rotation)
            br.setTransform(tr)
        return br
    return None


# ---------------------------------------------------------------------------
# Brush Stroke Renderer (Calligraphic, Art, Scatter, Pattern, Bristle)
# ---------------------------------------------------------------------------

def render_brush_stroke(p: QPainter, qp: QPainterPath, stroke: AppearanceStroke,
                        brush: BrushDef, opacity: float, overprint_sim: bool) -> None:
    total_len = qp.length()
    if total_len < 1.0:
        return
    col = to_qcolor(stroke.color, stroke.opacity * opacity, overprint_sim)
    size = max(1.0, stroke.width * (brush.size / 10.0))

    if brush.kind == "calligraphic":
        # Angled elliptical nib stamped along path
        ang_nib = math.radians(brush.angle)
        nx, ny = math.cos(ang_nib), math.sin(ang_nib)
        steps = max(16, min(300, int(total_len / 2.5)))
        left_pts, right_pts = [], []
        for i in range(steps + 1):
            pct = max(0.0, min(1.0, qp.percentAtLength((i / steps) * total_len)))
            pt = qp.pointAtPercent(pct)
            tangent = math.radians(-qp.angleAtPercent(pct))
            # Projected nib thickness depends on angle between nib and tangent
            sin_diff = abs(math.sin(tangent - ang_nib))
            hw = size * 0.5 * max(brush.roundness, sin_diff)
            tnx, tny = -math.sin(tangent), math.cos(tangent)
            left_pts.append(QPointF(pt.x() + tnx * hw, pt.y() + tny * hw))
            right_pts.append(QPointF(pt.x() - tnx * hw, pt.y() - tny * hw))
        ribbon = QPainterPath()
        ribbon.moveTo(left_pts[0])
        for pt in left_pts[1:]:
            ribbon.lineTo(pt)
        for pt in reversed(right_pts):
            ribbon.lineTo(pt)
        ribbon.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(ribbon)

    elif brush.kind == "art":
        # Tapered artistic stroke (or charcoal feathered edges)
        stations = [
            WidthStation(0.0, 0.08, 0.08),
            WidthStation(0.18, 1.05, 1.05),
            WidthStation(0.82, 0.95, 0.95),
            WidthStation(1.0, 0.06, 0.06),
        ]
        rib = build_variable_width_path(qp, size, stations)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(rib)
        if brush.art_style == "charcoal":
            p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), int(col.alpha() * 0.35)), max(1.0, size * 0.12)))
            p.setBrush(Qt.NoBrush)
            p.drawPath(apply_roughen_to_qpath(qp, amount=size * 0.3, detail=36, seed=17))

    elif brush.kind == "scatter":
        step = max(6.0, brush.spacing * (stroke.width / 4.0 + 0.5))
        count = max(2, min(180, int(total_len / step)))
        rng = np.random.default_rng(101)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        for i in range(count + 1):
            d = min(total_len, i * step)
            pct = max(0.0, min(1.0, qp.percentAtLength(d)))
            pt = qp.pointAtPercent(pct)
            ang = math.radians(-qp.angleAtPercent(pct))
            nx, ny = -math.sin(ang), math.cos(ang)
            off = float(rng.uniform(-1.0, 1.0)) * size * brush.scatter * 1.4
            sc = float(rng.uniform(0.65, 1.3)) * size * 0.45
            cx, cy = pt.x() + nx * off, pt.y() + ny * off
            p.save()
            p.translate(cx, cy)
            p.rotate(float(rng.uniform(0, 360)))
            if brush.scatter_shape == "star":
                st = QPainterPath()
                for k in range(10):
                    a = k * math.pi / 5
                    r = sc if k % 2 == 0 else sc * 0.42
                    st.moveTo(r * math.cos(a), r * math.sin(a)) if k == 0 else st.lineTo(r * math.cos(a), r * math.sin(a))
                st.closeSubpath()
                p.drawPath(st)
            elif brush.scatter_shape == "leaf":
                lf = QPainterPath()
                lf.moveTo(-sc, 0)
                lf.quadTo(0, -sc * 0.75, sc, 0)
                lf.quadTo(0, sc * 0.75, -sc, 0)
                p.drawPath(lf)
            else:
                p.drawEllipse(QPointF(0, 0), sc * 0.6, sc * 0.6)
            p.restore()

    elif brush.kind == "pattern":
        step = max(6.0, brush.spacing)
        count = max(2, min(200, int(total_len / step)))
        p.setPen(QPen(col, max(1.2, stroke.width * 0.45)))
        p.setBrush(Qt.NoBrush)
        for i in range(count):
            d = min(total_len, (i + 0.5) * step)
            pct = max(0.0, min(1.0, qp.percentAtLength(d)))
            pt = qp.pointAtPercent(pct)
            ang = -qp.angleAtPercent(pct)
            p.save()
            p.translate(pt)
            p.rotate(ang)
            p.drawRoundedRect(QRectF(-step * 0.42, -size * 0.28, step * 0.84, size * 0.56), size * 0.25, size * 0.25)
            p.restore()

    elif brush.kind == "bristle":
        hairs = max(3, min(19, brush.bristle_count))
        steps = max(16, min(160, int(total_len / 5.0)))
        for h_i in range(hairs):
            frac = (h_i / max(1, hairs - 1)) - 0.5
            off = frac * size
            alpha_f = 1.0 - abs(frac) * 0.75
            h_col = QColor(col.red(), col.green(), col.blue(), int(col.alpha() * alpha_f * 0.75))
            hp = QPainterPath()
            for s_i in range(steps + 1):
                pct = max(0.0, min(1.0, qp.percentAtLength((s_i / steps) * total_len)))
                pt = qp.pointAtPercent(pct)
                ang = math.radians(-qp.angleAtPercent(pct))
                nx, ny = -math.sin(ang), math.cos(ang)
                wob = math.sin(s_i * 0.45 + h_i * 1.7) * size * 0.04
                px, py = pt.x() + nx * (off + wob), pt.y() + ny * (off + wob)
                hp.moveTo(px, py) if s_i == 0 else hp.lineTo(px, py)
            p.setPen(QPen(h_col, max(0.8, size / hairs * 1.1), Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(hp)


# ---------------------------------------------------------------------------
# 3D Extrusion & Materials Renderer
# ---------------------------------------------------------------------------

def render_extrude_3d(p: QPainter, qp: QPainterPath, app: Appearance, params: Dict,
                      opacity: float, overprint_sim: bool) -> None:
    depth = max(4, min(90, int(params.get("depth", 26))))
    ang_x = math.radians(float(params.get("angle_x", -22)))
    ang_y = math.radians(float(params.get("angle_y", 28)))
    material = params.get("material", "glossy")  # "matte", "glossy", "metallic"
    dx = math.sin(ang_y) * 1.15
    dy = -math.sin(ang_x) * 1.15
    base_col = app.primary_fill.color if app.primary_fill.fill_type == "solid" else Color.from_hex("#3A86FF")
    steps = max(8, min(48, depth))

    # Draw extruded side wall slices from back to front with directional material shading
    for i in range(steps, 0, -1):
        frac = i / steps  # 1 = back, 0 = front
        tx = dx * i * (depth / steps)
        ty = dy * i * (depth / steps)
        # Shade factor
        if material == "metallic":
            shade = 0.32 + 0.58 * abs(math.sin(frac * math.pi * 1.6))
        elif material == "glossy":
            shade = 0.40 + 0.35 * (1.0 - frac)
        else:
            shade = 0.52 + 0.22 * (1.0 - frac)
        sc = QColor(
            max(0, min(255, int(base_col.r * shade))),
            max(0, min(255, int(base_col.g * shade))),
            max(0, min(255, int(base_col.b * shade))),
            int(255 * opacity),
        )
        p.save()
        p.translate(tx, ty)
        p.setPen(Qt.NoPen)
        p.setBrush(sc)
        p.drawPath(qp)
        p.restore()

    # Front lit face + optional specular rim highlight
    br = qp.boundingRect()
    p.save()
    if material in ("glossy", "metallic"):
        lg = QLinearGradient(br.topLeft(), br.bottomRight())
        hi = QColor(min(255, base_col.r + 75), min(255, base_col.g + 75), min(255, base_col.b + 75), int(255 * opacity))
        mid = to_qcolor(base_col, opacity, overprint_sim)
        lo = QColor(max(0, base_col.r - 35), max(0, base_col.g - 35), max(0, base_col.b - 35), int(255 * opacity))
        lg.setColorAt(0.0, hi)
        lg.setColorAt(0.45, mid)
        lg.setColorAt(1.0, lo)
        p.setBrush(QBrush(lg))
        p.setPen(QPen(QColor(255, 255, 255, int(110 * opacity)), 1.4))
    else:
        p.setBrush(to_qcolor(base_col, opacity, overprint_sim))
        p.setPen(Qt.NoPen)
    p.drawPath(qp)
    p.restore()


# ---------------------------------------------------------------------------
# Soft Blur / Shadow / Glow Offscreen Filter
# ---------------------------------------------------------------------------

def render_blurred_path(p: QPainter, qp: QPainterPath, color: QColor, blur_radius: float,
                        dx: float = 0.0, dy: float = 0.0) -> None:
    br = qp.boundingRect()
    if br.width() < 0.5 and br.height() < 0.5:
        return
    pad = int(math.ceil(blur_radius * 2.5)) + 4
    w = min(1400, max(8, int(math.ceil(br.width())) + pad * 2))
    h = min(1400, max(8, int(math.ceil(br.height())) + pad * 2))
    scale_x = (w - pad * 2) / max(1.0, br.width())
    scale_y = (h - pad * 2) / max(1.0, br.height())
    scale = min(1.0, scale_x, scale_y)

    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(Qt.transparent)
    ip = QPainter(img)
    ip.setRenderHint(QPainter.Antialiasing, True)
    ip.translate(pad - br.x() * scale, pad - br.y() * scale)
    ip.scale(scale, scale)
    ip.setPen(Qt.NoPen)
    ip.setBrush(color)
    ip.drawPath(qp)
    ip.end()

    # Gaussian blur via Pillow
    ptr = img.constBits()
    pil = Image.frombuffer("RGBA", (w, h), bytes(ptr), "raw", "RGBA", 0, 1).copy()
    pil = pil.filter(ImageFilter.GaussianBlur(radius=max(0.5, blur_radius * scale)))
    out_bytes = pil.tobytes("raw", "RGBA")
    blurred = QImage(out_bytes, w, h, w * 4, QImage.Format_RGBA8888).copy()

    target_rect = QRectF(
        br.x() - pad / scale + dx,
        br.y() - pad / scale + dy,
        w / scale,
        h / scale,
    )
    p.drawImage(target_rect, blurred)


# ---------------------------------------------------------------------------
# Data Graphics / Charts Renderer
# ---------------------------------------------------------------------------

def render_graph_object(p: QPainter, obj: VectorObject, opts: ViewOptions) -> None:
    rect = QRectF(obj.x, obj.y, max(80.0, obj.width), max(60.0, obj.height))
    p.save()
    if opts.outline_mode:
        p.setPen(QPen(QColor("#222222"), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRect(rect)
        p.restore()
        return

    # Card background
    p.setBrush(QColor("#FFFFFF"))
    p.setPen(QPen(QColor("#D0D7DE"), 1.2))
    p.drawRoundedRect(rect, 8, 8)

    pad_l, pad_r, pad_t, pad_b = 48.0, 22.0, 46.0, 42.0
    plot = QRectF(rect.x() + pad_l, rect.y() + pad_t, max(20.0, rect.width() - pad_l - pad_r),
                  max(20.0, rect.height() - pad_t - pad_b))

    # Title
    p.setPen(QColor("#1E2430"))
    p.setFont(QFont("Segoe UI", 13, QFont.Bold))
    p.drawText(QRectF(rect.x() + 16, rect.y() + 8, rect.width() - 32, 26), Qt.AlignLeft | Qt.AlignVCenter, obj.graph_title)

    series = obj.graph_series or []
    headers = obj.graph_headers or ["A", "B", "C", "D"]
    if not series:
        p.restore()
        return

    # Legend top-right
    lx = rect.right() - 16
    p.setFont(QFont("Segoe UI", 9))
    for s in reversed(series):
        nm = s.get("name", "Series")
        tw = QFontMetricsF(p.font()).horizontalAdvance(nm) + 18
        lx -= tw
        p.setBrush(QColor(s.get("color", "#FF9A00")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(lx, rect.y() + 15, 10, 10), 2, 2)
        p.setPen(QColor("#4A5568"))
        p.drawText(QRectF(lx + 14, rect.y() + 10, tw - 12, 20), Qt.AlignLeft | Qt.AlignVCenter, nm)

    if obj.graph_type == "pie":
        vals = [max(0.0, float(v)) for v in series[0].get("values", [25, 25, 25, 25])]
        total = sum(vals) or 1.0
        palette = ["#FF9A00", "#00C2FF", "#6E2CF2", "#06D6A0", "#EF476F", "#FFD166"]
        rad = min(plot.width(), plot.height()) * 0.45
        pie_rect = QRectF(plot.center().x() - rad, plot.center().y() - rad, rad * 2, rad * 2)
        start_ang = 90 * 16
        for i, v in enumerate(vals):
            span = -int(round((v / total) * 360 * 16))
            p.setBrush(QColor(palette[i % len(palette)]))
            p.setPen(QPen(QColor("#FFFFFF"), 2.0))
            p.drawPie(pie_rect, start_ang, span)
            mid_rad = math.radians((start_ang + span * 0.5) / 16.0)
            lbl = headers[i] if i < len(headers) else f"#{i + 1}"
            tx = plot.center().x() + math.cos(mid_rad) * (rad * 0.68)
            ty = plot.center().y() - math.sin(mid_rad) * (rad * 0.68)
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            p.drawText(QRectF(tx - 24, ty - 10, 48, 20), Qt.AlignCenter, f"{lbl}\n{int(round(v / total * 100))}%")
            start_ang += span
        p.restore()
        return

    # Cartesian axes + gridlines
    all_vals = [float(v) for s in series for v in s.get("values", [])]
    if obj.graph_type == "stacked_bar":
        n_cats = max(1, len(headers))
        max_v = max([sum(float(s["values"][i]) for s in series if i < len(s.get("values", []))) for i in range(n_cats)] + [10.0])
    else:
        max_v = max(all_vals + [10.0])
    max_v = math.ceil(max_v / 10.0) * 10.0

    p.setFont(QFont("Segoe UI", 8))
    for g in range(5):
        frac = g / 4.0
        gy = plot.bottom() - frac * plot.height()
        p.setPen(QPen(QColor("#E5E9F0"), 1.0, Qt.DashLine))
        p.drawLine(QPointF(plot.left(), gy), QPointF(plot.right(), gy))
        p.setPen(QColor("#6B7280"))
        p.drawText(QRectF(rect.x() + 4, gy - 8, pad_l - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{int(max_v * frac)}")

    p.setPen(QPen(QColor("#94A3B8"), 1.2))
    p.drawLine(plot.bottomLeft(), plot.bottomRight())
    p.drawLine(plot.topLeft(), plot.bottomLeft())

    n_cats = max(1, len(headers))
    cat_w = plot.width() / n_cats
    for i, h_lbl in enumerate(headers):
        cx = plot.left() + (i + 0.5) * cat_w
        p.setPen(QColor("#475569"))
        p.drawText(QRectF(cx - cat_w * 0.5, plot.bottom() + 6, cat_w, 20), Qt.AlignCenter, str(h_lbl))

    if obj.graph_type == "bar":
        n_ser = max(1, len(series))
        bw = (cat_w * 0.72) / n_ser
        for s_i, s in enumerate(series):
            p.setBrush(QColor(s.get("color", "#FF9A00")))
            p.setPen(Qt.NoPen)
            for c_i, v in enumerate(s.get("values", [])[:n_cats]):
                bh = (float(v) / max_v) * plot.height()
                bx = plot.left() + c_i * cat_w + cat_w * 0.14 + s_i * bw
                p.drawRoundedRect(QRectF(bx, plot.bottom() - bh, max(2.0, bw - 2.0), bh), 3, 3)

    elif obj.graph_type == "stacked_bar":
        bw = cat_w * 0.56
        for c_i in range(n_cats):
            y_bot = plot.bottom()
            for s in series:
                vals = s.get("values", [])
                if c_i >= len(vals):
                    continue
                bh = (float(vals[c_i]) / max_v) * plot.height()
                p.setBrush(QColor(s.get("color", "#FF9A00")))
                p.setPen(Qt.NoPen)
                bx = plot.left() + c_i * cat_w + (cat_w - bw) * 0.5
                p.drawRect(QRectF(bx, y_bot - bh, bw, bh))
                y_bot -= bh

    elif obj.graph_type == "line":
        for s in series:
            col = QColor(s.get("color", "#FF9A00"))
            pts = []
            for c_i, v in enumerate(s.get("values", [])[:n_cats]):
                px = plot.left() + (c_i + 0.5) * cat_w
                py = plot.bottom() - (float(v) / max_v) * plot.height()
                pts.append(QPointF(px, py))
            p.setPen(QPen(col, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for k in range(len(pts) - 1):
                p.drawLine(pts[k], pts[k + 1])
            p.setBrush(QColor("#FFFFFF"))
            for pt in pts:
                p.drawEllipse(pt, 4.2, 4.2)

    elif obj.graph_type == "scatter":
        for s_i, s in enumerate(series):
            col = QColor(s.get("color", "#FF9A00"))
            p.setBrush(col)
            p.setPen(QPen(QColor("#FFFFFF"), 1.2))
            for c_i, v in enumerate(s.get("values", [])[:n_cats]):
                px = plot.left() + (c_i + 0.35 + s_i * 0.14) * cat_w
                py = plot.bottom() - (float(v) / max_v) * plot.height()
                p.drawEllipse(QPointF(px, py), 6.0, 6.0)

    p.restore()


# ---------------------------------------------------------------------------
# Studio Product Mockup Renderer (Mug, T-Shirt, Tote, Cup, Box, Phone)
# ---------------------------------------------------------------------------

def render_mockup_object(p: QPainter, obj: VectorObject, doc: Document, opts: ViewOptions) -> None:
    rect = QRectF(obj.x, obj.y, max(120.0, obj.width), max(120.0, obj.height))
    p.save()
    cx, cy = rect.center().x(), rect.center().y()
    w, h = rect.width(), rect.height()
    base = to_qcolor(obj.mockup_color)
    preset = obj.mockup_preset

    # Soft studio backdrop shadow
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 32))
    p.drawEllipse(QPointF(cx, rect.bottom() - h * 0.06), w * 0.36, h * 0.055)

    art_rect = QRectF(cx - w * 0.22, cy - h * 0.20, w * 0.44, h * 0.40)
    clip_path = QPainterPath()

    if preset == "mug":
        # Mug handle
        p.setPen(QPen(base.darker(112), max(8.0, w * 0.055), Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx + w * 0.16, cy - h * 0.18, w * 0.24, h * 0.38), -90 * 16, 180 * 16)
        # Mug cylinder body
        body = QRectF(cx - w * 0.28, cy - h * 0.30, w * 0.54, h * 0.62)
        clip_path.addRoundedRect(body, w * 0.06, h * 0.05)
        lg = QLinearGradient(body.left(), body.center().y(), body.right(), body.center().y())
        lg.setColorAt(0.0, base.darker(122))
        lg.setColorAt(0.28, base.lighter(108))
        lg.setColorAt(0.70, base)
        lg.setColorAt(1.0, base.darker(132))
        p.setPen(QPen(base.darker(140), 1.2))
        p.setBrush(QBrush(lg))
        p.drawPath(clip_path)
        # Mug rim
        p.setBrush(base.darker(108))
        p.drawEllipse(QRectF(body.x(), body.y() - h * 0.04, body.width(), h * 0.09))
        art_rect = QRectF(body.x() + body.width() * 0.12, body.y() + body.height() * 0.16,
                          body.width() * 0.76, body.height() * 0.68)

    elif preset == "tshirt":
        shirt = QPainterPath()
        shirt.moveTo(cx - w * 0.14, rect.y() + h * 0.10)
        shirt.quadTo(cx, rect.y() + h * 0.18, cx + w * 0.14, rect.y() + h * 0.10)
        shirt.lineTo(cx + w * 0.32, rect.y() + h * 0.16)
        shirt.lineTo(cx + w * 0.45, rect.y() + h * 0.36)
        shirt.lineTo(cx + w * 0.34, rect.y() + h * 0.44)
        shirt.lineTo(cx + w * 0.28, rect.y() + h * 0.35)
        shirt.lineTo(cx + w * 0.28, rect.y() + h * 0.88)
        shirt.lineTo(cx - w * 0.28, rect.y() + h * 0.88)
        shirt.lineTo(cx - w * 0.28, rect.y() + h * 0.35)
        shirt.lineTo(cx - w * 0.34, rect.y() + h * 0.44)
        shirt.lineTo(cx - w * 0.45, rect.y() + h * 0.36)
        shirt.lineTo(cx - w * 0.32, rect.y() + h * 0.16)
        shirt.closeSubpath()
        clip_path = shirt
        lg = QLinearGradient(rect.left(), cy, rect.right(), cy)
        lg.setColorAt(0.0, base.darker(118))
        lg.setColorAt(0.35, base.lighter(104))
        lg.setColorAt(0.65, base)
        lg.setColorAt(1.0, base.darker(120))
        p.setBrush(QBrush(lg))
        p.setPen(QPen(base.darker(138), 1.4))
        p.drawPath(shirt)
        art_rect = QRectF(cx - w * 0.20, rect.y() + h * 0.28, w * 0.40, h * 0.42)

    elif preset == "tote":
        p.setPen(QPen(base.darker(125), max(6.0, w * 0.032), Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - w * 0.14, rect.y() + h * 0.06, w * 0.28, h * 0.36), 0, 180 * 16)
        bag = QRectF(cx - w * 0.28, rect.y() + h * 0.26, w * 0.56, h * 0.62)
        clip_path.addRoundedRect(bag, 8, 8)
        p.setBrush(base)
        p.setPen(QPen(base.darker(135), 1.4))
        p.drawPath(clip_path)
        art_rect = bag.adjusted(w * 0.08, h * 0.10, -w * 0.08, -h * 0.10)

    elif preset == "box":
        # Isometric packaging box
        front = QPainterPath()
        front.moveTo(cx - w * 0.26, cy - h * 0.18)
        front.lineTo(cx + w * 0.08, cy - h * 0.08)
        front.lineTo(cx + w * 0.08, cy + h * 0.36)
        front.lineTo(cx - w * 0.26, cy + h * 0.24)
        front.closeSubpath()
        side = QPainterPath()
        side.moveTo(cx + w * 0.08, cy - h * 0.08)
        side.lineTo(cx + w * 0.32, cy - h * 0.20)
        side.lineTo(cx + w * 0.32, cy + h * 0.22)
        side.lineTo(cx + w * 0.08, cy + h * 0.36)
        side.closeSubpath()
        top = QPainterPath()
        top.moveTo(cx - w * 0.26, cy - h * 0.18)
        top.lineTo(cx - w * 0.02, cy - h * 0.30)
        top.lineTo(cx + w * 0.32, cy - h * 0.20)
        top.lineTo(cx + w * 0.08, cy - h * 0.08)
        top.closeSubpath()
        p.setPen(QPen(base.darker(145), 1.2))
        p.setBrush(base.lighter(106))
        p.drawPath(top)
        p.setBrush(base.darker(124))
        p.drawPath(side)
        p.setBrush(base)
        p.drawPath(front)
        clip_path = front
        art_rect = QRectF(cx - w * 0.23, cy - h * 0.08, w * 0.28, h * 0.34)

    elif preset == "phone":
        case = QRectF(cx - w * 0.22, rect.y() + h * 0.08, w * 0.44, h * 0.82)
        clip_path.addRoundedRect(case, w * 0.08, w * 0.08)
        p.setBrush(base)
        p.setPen(QPen(QColor("#1E2430"), 3.0))
        p.drawPath(clip_path)
        # Camera bump
        p.setBrush(QColor("#1B1F29"))
        p.drawRoundedRect(QRectF(case.x() + 14, case.y() + 14, case.width() * 0.34, case.width() * 0.34), 8, 8)
        art_rect = QRectF(case.x() + 12, case.y() + case.height() * 0.32, case.width() - 24, case.height() * 0.56)

    else:  # coffee cup
        cup = QPainterPath()
        cup.moveTo(cx - w * 0.24, rect.y() + h * 0.22)
        cup.lineTo(cx + w * 0.24, rect.y() + h * 0.22)
        cup.lineTo(cx + w * 0.17, rect.y() + h * 0.86)
        cup.lineTo(cx - w * 0.17, rect.y() + h * 0.86)
        cup.closeSubpath()
        clip_path = cup
        p.setBrush(base)
        p.setPen(QPen(base.darker(130), 1.3))
        p.drawPath(cup)
        p.setBrush(QColor("#232328"))
        p.drawRoundedRect(QRectF(cx - w * 0.26, rect.y() + h * 0.14, w * 0.52, h * 0.09), 6, 6)
        art_rect = QRectF(cx - w * 0.17, rect.y() + h * 0.34, w * 0.34, h * 0.38)

    # Composite child artwork onto the product surface with realistic specular/shadow multiply overlay
    if obj.children:
        art = obj.children[0]
        abr = object_bounds(art, doc)
        if abr.width() > 1.0 and abr.height() > 1.0:
            p.save()
            p.setClipPath(clip_path)
            sc = min(art_rect.width() / abr.width(), art_rect.height() / abr.height()) * max(0.15, obj.mockup_art_scale)
            tx = art_rect.center().x() + obj.mockup_art_offset_x - abr.center().x() * sc
            ty = art_rect.center().y() + obj.mockup_art_offset_y - abr.center().y() * sc
            p.translate(tx, ty)
            if preset == "box":
                p.shear(0.0, 0.26)
            p.scale(sc, sc)
            p.setCompositionMode(QPainter.CompositionMode_Multiply)
            render_object(p, art, doc, opts, [])
            p.restore()

            # Cylindrical highlight sheen over mug/cup
            if preset in ("mug", "cup"):
                p.save()
                p.setClipPath(clip_path)
                sheen = QLinearGradient(art_rect.left(), 0, art_rect.right(), 0)
                sheen.setColorAt(0.0, QColor(0, 0, 0, 55))
                sheen.setColorAt(0.26, QColor(255, 255, 255, 65))
                sheen.setColorAt(0.65, QColor(255, 255, 255, 0))
                sheen.setColorAt(1.0, QColor(0, 0, 0, 75))
                p.fillRect(rect, QBrush(sheen))
                p.restore()
    p.restore()


# ---------------------------------------------------------------------------
# Core Object & Document Renderer
# ---------------------------------------------------------------------------

def render_object(p: QPainter, obj: VectorObject, doc: Document, opts: ViewOptions,
                  wrap_obstacles: List[QRectF], thread_override_text: Optional[str] = None) -> None:
    if not obj.visible:
        return

    # Flattener Preview: highlight objects with transparency, blend modes, or raster effects
    has_transparency = (
        obj.appearance.opacity < 0.99
        or obj.appearance.blend_mode != "Normal"
        or any(e.enabled and e.kind in ("drop_shadow", "outer_glow", "inner_glow", "gaussian_blur") for e in obj.appearance.effects)
        or obj.opacity_mask_enabled
    )

    p.save()
    mode = BLEND_MODES.get(obj.appearance.blend_mode, QPainter.CompositionMode_SourceOver)
    p.setCompositionMode(mode)
    eff_op = obj.appearance.opacity

    if obj.kind == "group":
        if obj.is_clipping_group and len(obj.children) >= 2:
            # Top-most (last) child defines clipping path (Illustrator convention)
            clip_obj = obj.children[-1]
            clip_qp = object_to_qpath(clip_obj, doc)
            p.save()
            p.setClipPath(clip_qp)
            for ch in obj.children[:-1]:
                render_object(p, ch, doc, opts, wrap_obstacles)
            p.restore()
            if opts.outline_mode:
                p.setPen(QPen(QColor("#0078D7"), 1.0, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawPath(clip_qp)
        elif obj.opacity_mask_enabled and len(obj.children) >= 2:
            # Render group content modulated by luminance of top child
            br = object_bounds(obj, doc)
            w = max(8, min(1400, int(math.ceil(br.width())) + 4))
            h = max(8, min(1400, int(math.ceil(br.height())) + 4))
            content_img = QImage(w, h, QImage.Format_RGBA8888)
            content_img.fill(Qt.transparent)
            cp = QPainter(content_img)
            cp.setRenderHint(QPainter.Antialiasing, True)
            cp.translate(-br.x() + 2, -br.y() + 2)
            for ch in obj.children[:-1]:
                render_object(cp, ch, doc, opts, wrap_obstacles)
            cp.end()
            mask_img = QImage(w, h, QImage.Format_RGBA8888)
            mask_img.fill(Qt.black)
            mp = QPainter(mask_img)
            mp.setRenderHint(QPainter.Antialiasing, True)
            mp.translate(-br.x() + 2, -br.y() + 2)
            render_object(mp, obj.children[-1], doc, opts, [])
            mp.end()
            # Apply luminance as alpha multiplier
            c_arr = np.frombuffer(bytes(content_img.constBits()), dtype=np.uint8).reshape((h, w, 4)).copy()
            m_arr = np.frombuffer(bytes(mask_img.constBits()), dtype=np.uint8).reshape((h, w, 4))
            lum = (0.299 * m_arr[:, :, 0] + 0.587 * m_arr[:, :, 1] + 0.114 * m_arr[:, :, 2]) / 255.0
            c_arr[:, :, 3] = np.clip(c_arr[:, :, 3].astype(np.float32) * lum, 0, 255).astype(np.uint8)
            out_img = QImage(c_arr.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
            p.drawImage(QRectF(br.x() - 2, br.y() - 2, w, h), out_img)
        else:
            for ch in obj.children:
                render_object(p, ch, doc, opts, wrap_obstacles)
        p.restore()
        return

    if obj.kind == "symbol_instance":
        sym = doc.get_symbol(obj.symbol_id)
        if sym:
            abr = object_bounds(sym.artwork, doc)
            if abr.width() > 1e-3 and abr.height() > 1e-3:
                p.save()
                p.setOpacity(eff_op)
                p.translate(obj.x, obj.y)
                if abs(obj.rotation) > 1e-3:
                    p.translate(obj.width * 0.5, obj.height * 0.5)
                    p.rotate(obj.rotation)
                    p.translate(-obj.width * 0.5, -obj.height * 0.5)
                p.scale(obj.width / abr.width(), obj.height / abr.height())
                p.translate(-abr.x(), -abr.y())
                render_object(p, sym.artwork, doc, opts, [])
                p.restore()
        p.restore()
        return

    if obj.kind == "image":
        img = load_object_qimage(obj)
        rect = QRectF(obj.x, obj.y, max(1.0, obj.width), max(1.0, obj.height))
        if opts.outline_mode or img is None:
            p.setPen(QPen(QColor("#555555"), 1.0))
            p.setBrush(Qt.NoBrush)
            p.drawRect(rect)
            p.drawLine(rect.topLeft(), rect.bottomRight())
            p.drawLine(rect.topRight(), rect.bottomLeft())
        else:
            p.setOpacity(eff_op)
            if abs(obj.rotation) > 1e-3:
                p.translate(rect.center())
                p.rotate(obj.rotation)
                p.translate(-rect.center())
            if obj.crop_rect and len(obj.crop_rect) == 4:
                nx, ny, nw, nh = obj.crop_rect
                src = QRectF(nx * img.width(), ny * img.height(), nw * img.width(), nh * img.height())
                p.drawImage(rect, img, src)
            else:
                p.drawImage(rect, img)
        p.restore()
        return

    if obj.kind == "graph":
        p.setOpacity(eff_op)
        render_graph_object(p, obj, opts)
        p.restore()
        return

    if obj.kind == "mockup":
        p.setOpacity(eff_op)
        render_mockup_object(p, obj, doc, opts)
        p.restore()
        return

    if obj.kind == "blend" and len(obj.children) >= 2:
        render_object(p, obj.children[0], doc, opts, [])
        for step_qp, step_app in generate_blend_steps(obj.children[0], obj.children[1], obj.blend_steps, doc):
            _render_styled_path(p, step_qp, step_app, doc, opts)
        render_object(p, obj.children[1], doc, opts, [])
        p.restore()
        return

    if obj.kind == "repeat" and obj.children:
        src = obj.children[0]
        sbr = object_bounds(src, doc)
        if obj.repeat_mode == "radial":
            cnt = max(2, obj.repeat_count)
            for i in range(cnt):
                ang = (360.0 * i) / cnt
                p.save()
                p.translate(obj.x, obj.y)
                p.rotate(ang)
                p.translate(-sbr.center().x(), -obj.repeat_radius - sbr.center().y())
                render_object(p, src, doc, opts, [])
                p.restore()
        elif obj.repeat_mode == "grid":
            for r in range(max(1, obj.repeat_rows)):
                for c in range(max(1, obj.repeat_cols)):
                    p.save()
                    p.translate(c * obj.repeat_spacing_x, r * obj.repeat_spacing_y)
                    render_object(p, src, doc, opts, [])
                    p.restore()
        elif obj.repeat_mode == "mirror":
            render_object(p, src, doc, opts, [])
            axis_x = sbr.right() + 10.0
            p.save()
            p.translate(axis_x * 2, 0)
            p.scale(-1.0, 1.0)
            render_object(p, src, doc, opts, [])
            p.restore()
        p.restore()
        return

    if obj.kind == "text":
        _render_text_object(p, obj, doc, opts, wrap_obstacles, thread_override_text)
        p.restore()
        return

    # Standard path / live_paint / shape object
    qp = object_to_qpath(obj, doc)
    if obj.kind == "live_paint" and obj.live_paint_fills:
        # Render painted faces if stored
        pass
    _render_styled_path(p, qp, obj.appearance, doc, opts)

    if opts.flattener_preview and has_transparency:
        p.setPen(QPen(QColor("#FF007F"), 1.5))
        p.setBrush(QColor(255, 0, 127, 90))
        p.drawPath(qp)

    p.restore()


def _render_text_object(p: QPainter, obj: VectorObject, doc: Document, opts: ViewOptions,
                        wrap_obstacles: List[QRectF], override_text: Optional[str] = None) -> None:
    if obj.text_mode == "path" or obj.char_transforms or any(e.enabled for e in obj.appearance.effects):
        qp = object_to_qpath(obj, doc)
        if obj.text_mode == "path" and not opts.export_mode and opts.outline_mode:
            p.setPen(QPen(QColor("#888888"), 0.8, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawPath(subpaths_to_qpath(obj.subpaths))
        _render_styled_path(p, qp, obj.appearance, doc, opts)
        return

    # Crisp native text rendering for Point / Area text (with Text Wrap & Threading support!)
    if opts.outline_mode:
        qp = object_to_qpath(obj, doc)
        p.setPen(QPen(QColor("#111111"), 0.9))
        p.setBrush(Qt.NoBrush)
        p.drawPath(qp)
        return

    text_obj = obj
    if override_text is not None:
        text_obj = copy.copy(obj)
        text_obj.text = override_text

    font = build_qfont(text_obj.text_style)
    fm = QFontMetricsF(font)
    lines = _layout_text_lines(text_obj, fm, wrap_obstacles if text_obj.text_mode == "area" else None)
    line_h = text_obj.text_style.font_size * text_obj.text_style.leading
    ascent = fm.ascent()

    max_lines = int(max(1, text_obj.height // max(4.0, line_h))) if text_obj.text_mode == "area" else len(lines)
    visible_lines = lines[:max_lines]
    overflow_lines = lines[max_lines:]

    p.save()
    p.setFont(font)
    if abs(obj.rotation) > 1e-3:
        br = object_bounds(obj, doc)
        p.translate(br.center())
        p.rotate(obj.rotation)
        p.translate(-br.center())

    fill = obj.appearance.primary_fill
    col = to_qcolor(fill.color, fill.opacity * obj.appearance.opacity, opts.overprint_preview) if fill.fill_type == "solid" else QColor("#111111")
    p.setPen(col)
    for i, (line_str, lx) in enumerate(visible_lines):
        by = obj.y + ascent + i * line_h
        p.drawText(QPointF(lx, by), line_str)
    p.restore()

    # If threaded to another area text frame, flow overflow text into it!
    if overflow_lines and obj.thread_next_id:
        nxt = doc.find_object(obj.thread_next_id)
        if nxt and nxt.kind == "text":
            rem = " ".join(l for l, _ in overflow_lines)
            _render_text_object(p, nxt, doc, opts, wrap_obstacles, override_text=rem)


def _render_styled_path(p: QPainter, base_qp: QPainterPath, app: Appearance,
                        doc: Document, opts: ViewOptions) -> None:
    if base_qp.isEmpty():
        return
    if opts.outline_mode:
        p.setPen(QPen(QColor("#1A1A1A"), 0.9))
        p.setBrush(Qt.NoBrush)
        p.drawPath(base_qp)
        return

    # 1. Geometry-modifying live effects (Offset Path, Warp, Roughen)
    qp = QPainterPath(base_qp)
    extrude_fx: Optional[LiveEffect] = None
    blur_fx: Optional[LiveEffect] = None
    for fx in app.effects:
        if not fx.enabled:
            continue
        if fx.kind == "offset_path":
            qp = offset_qpath(qp, float(fx.params.get("offset", 8.0)), fx.params.get("join", "round"))
        elif fx.kind == "warp":
            qp = apply_warp_to_qpath(
                qp,
                fx.params.get("style", "arc"),
                float(fx.params.get("bend", 0.35)),
                float(fx.params.get("h_distort", 0.0)),
                float(fx.params.get("v_distort", 0.0)),
            )
        elif fx.kind == "roughen":
            qp = apply_roughen_to_qpath(
                qp,
                float(fx.params.get("amount", 5.0)),
                int(fx.params.get("detail", 24)),
            )
        elif fx.kind == "extrude_3d":
            extrude_fx = fx
        elif fx.kind == "gaussian_blur":
            blur_fx = fx

    # 2. Pre-pass Live Effects (Drop Shadow, Outer Glow)
    for fx in app.effects:
        if not fx.enabled:
            continue
        if fx.kind == "drop_shadow":
            sc = Color.from_hex(fx.params.get("color", "#000000"))
            sh_op = float(fx.params.get("opacity", 0.38)) * app.opacity
            render_blurred_path(
                p, qp, to_qcolor(sc, sh_op),
                float(fx.params.get("blur", 10.0)),
                float(fx.params.get("dx", 6.0)),
                float(fx.params.get("dy", 8.0)),
            )
        elif fx.kind == "outer_glow":
            gc = Color.from_hex(fx.params.get("color", "#00F5D4"))
            gl_op = float(fx.params.get("opacity", 0.75)) * app.opacity
            render_blurred_path(p, qp, to_qcolor(gc, gl_op), float(fx.params.get("blur", 14.0)), 0.0, 0.0)

    # If 3D Extrusion is enabled, delegate full lit 3D rendering
    if extrude_fx is not None:
        render_extrude_3d(p, qp, app, extrude_fx.params, app.opacity, opts.overprint_preview)
        return

    # If Gaussian blur is enabled on the object itself
    if blur_fx is not None and app.primary_fill.fill_type == "solid":
        render_blurred_path(
            p, qp, to_qcolor(app.primary_fill.color, app.opacity, opts.overprint_preview),
            float(blur_fx.params.get("blur", 8.0)), 0.0, 0.0,
        )
        return

    rect = qp.boundingRect()

    # 3. Stackable Fills (drawn bottom-to-top)
    for fill in reversed(app.fills):
        if not fill.visible or fill.fill_type == "none":
            continue
        p.save()
        p.setCompositionMode(BLEND_MODES.get(fill.blend_mode, QPainter.CompositionMode_SourceOver))
        if fill.overprint and opts.overprint_preview:
            p.setCompositionMode(QPainter.CompositionMode_Multiply)
        if fill.fill_type == "gradient" and fill.gradient and fill.gradient.kind in ("freeform", "mesh"):
            gimg = render_freeform_or_mesh_image(
                fill.gradient,
                int(max(16, rect.width())), int(max(16, rect.height())),
                fill.opacity * app.opacity,
            )
            p.setClipPath(qp)
            p.drawImage(rect, gimg)
        else:
            qbrush = build_qbrush_for_fill(fill, rect, app.opacity, opts.overprint_preview)
            if qbrush is not None:
                p.setPen(Qt.NoPen)
                p.setBrush(qbrush)
                p.drawPath(qp)
        p.restore()

    # 4. Inner Glow (clipped to path)
    for fx in app.effects:
        if fx.enabled and fx.kind == "inner_glow":
            gc = Color.from_hex(fx.params.get("color", "#FFFFFF"))
            p.save()
            p.setClipPath(qp)
            p.setPen(QPen(to_qcolor(gc, float(fx.params.get("opacity", 0.55)) * app.opacity), float(fx.params.get("blur", 12.0))))
            p.setBrush(Qt.NoBrush)
            p.drawPath(qp)
            p.restore()

    # 5. Stackable Strokes (drawn bottom-to-top)
    for st in reversed(app.strokes):
        if not st.visible or st.stroke_type == "none" or st.width <= 0.01:
            continue
        p.save()
        p.setCompositionMode(BLEND_MODES.get(st.blend_mode, QPainter.CompositionMode_SourceOver))
        if st.overprint and opts.overprint_preview:
            p.setCompositionMode(QPainter.CompositionMode_Multiply)

        brush_def = doc.get_brush(st.brush_id)
        if brush_def and brush_def.kind != "basic":
            render_brush_stroke(p, qp, st, brush_def, app.opacity, opts.overprint_preview)
            p.restore()
            continue

        stations = get_width_stations(st)
        if stations:
            rib = build_variable_width_path(qp, st.width, stations)
            p.setPen(Qt.NoPen)
            if st.stroke_type == "gradient" and st.gradient:
                dummy_fill = AppearanceFill(fill_type="gradient", gradient=st.gradient, opacity=st.opacity)
                p.setBrush(build_qbrush_for_fill(dummy_fill, rect, app.opacity, opts.overprint_preview) or Qt.black)
            else:
                p.setBrush(to_qcolor(st.color, st.opacity * app.opacity, opts.overprint_preview))
            p.drawPath(rib)
            p.restore()
            continue

        # Gradient along stroke!
        if st.stroke_type == "gradient" and st.gradient and st.gradient.stroke_mode == "along":
            _render_gradient_along_stroke(p, qp, st, app.opacity, opts.overprint_preview)
            p.restore()
            continue

        cap_map = {"butt": Qt.FlatCap, "square": Qt.SquareCap, "round": Qt.RoundCap}
        join_map = {"miter": Qt.MiterJoin, "bevel": Qt.BevelJoin, "round": Qt.RoundJoin}

        if st.stroke_type == "gradient" and st.gradient:
            dummy_fill = AppearanceFill(fill_type="gradient", gradient=st.gradient, opacity=st.opacity)
            sb = build_qbrush_for_fill(dummy_fill, rect, app.opacity, opts.overprint_preview)
            pen = QPen(sb if sb else to_qcolor(st.color, st.opacity * app.opacity), st.width)
        else:
            pen = QPen(to_qcolor(st.color, st.opacity * app.opacity, opts.overprint_preview), st.width)
        pen.setCapStyle(cap_map.get(st.cap, Qt.RoundCap))
        pen.setJoinStyle(join_map.get(st.join, Qt.RoundJoin))
        pen.setMiterLimit(st.miter_limit)

        draw_qp = qp
        if st.dash_pattern:
            if st.dash_align_corners:
                draw_qp = build_corner_aligned_dash_path(qp, st.dash_pattern, st.width)
            else:
                pen.setDashPattern([max(0.5, d) for d in st.dash_pattern])

        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(draw_qp)

        # Arrowheads
        if st.arrow_start != "none" or st.arrow_end != "none":
            _draw_arrowheads(p, qp, st, app.opacity, opts.overprint_preview)
        p.restore()


def _render_gradient_along_stroke(p: QPainter, qp: QPainterPath, st: AppearanceStroke,
                                  opacity: float, overprint_sim: bool) -> None:
    total = qp.length()
    if total < 1.0 or not st.gradient or not st.gradient.stops:
        return
    stops = sorted(st.gradient.stops, key=lambda s: s.offset)
    segs = max(24, min(140, int(total / 6.0)))

    def _sample_grad(t: float) -> QColor:
        if t <= stops[0].offset:
            return to_qcolor(stops[0].color, st.opacity * opacity, overprint_sim)
        if t >= stops[-1].offset:
            return to_qcolor(stops[-1].color, st.opacity * opacity, overprint_sim)
        for i in range(len(stops) - 1):
            a, b = stops[i], stops[i + 1]
            if a.offset <= t <= b.offset:
                u = (t - a.offset) / max(1e-6, b.offset - a.offset)
                c = Color(
                    int(a.color.r + (b.color.r - a.color.r) * u),
                    int(a.color.g + (b.color.g - a.color.g) * u),
                    int(a.color.b + (b.color.b - a.color.b) * u),
                    int(a.color.a + (b.color.a - a.color.a) * u),
                )
                return to_qcolor(c, st.opacity * opacity, overprint_sim)
        return to_qcolor(st.color, st.opacity * opacity, overprint_sim)

    prev = qp.pointAtPercent(0.0)
    for i in range(1, segs + 1):
        t = i / segs
        pct = max(0.0, min(1.0, qp.percentAtLength(t * total)))
        cur = qp.pointAtPercent(pct)
        p.setPen(QPen(_sample_grad(t), st.width, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(prev, cur)
        prev = cur


def _draw_arrowheads(p: QPainter, qp: QPainterPath, st: AppearanceStroke,
                     opacity: float, overprint_sim: bool) -> None:
    if qp.length() < 2.0:
        return
    col = to_qcolor(st.color, st.opacity * opacity, overprint_sim)
    sz = max(6.0, st.width * 3.4)
    for which, kind in ((0.0, st.arrow_start), (1.0, st.arrow_end)):
        if kind == "none":
            continue
        pt = qp.pointAtPercent(which)
        ang = -qp.angleAtPercent(which) + (180.0 if which == 0.0 else 0.0)
        p.save()
        p.translate(pt)
        p.rotate(ang)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        if kind == "arrow":
            tri = QPainterPath()
            tri.moveTo(sz * 0.4, 0)
            tri.lineTo(-sz * 0.8, -sz * 0.45)
            tri.lineTo(-sz * 0.55, 0)
            tri.lineTo(-sz * 0.8, sz * 0.45)
            tri.closeSubpath()
            p.drawPath(tri)
        elif kind == "dot":
            p.drawEllipse(QPointF(0, 0), sz * 0.35, sz * 0.35)
        elif kind == "diamond":
            dm = QPainterPath()
            dm.moveTo(sz * 0.5, 0)
            dm.lineTo(0, -sz * 0.35)
            dm.lineTo(-sz * 0.5, 0)
            dm.lineTo(0, sz * 0.35)
            dm.closeSubpath()
            p.drawPath(dm)
        p.restore()


# ---------------------------------------------------------------------------
# Perspective Grid, Bleeds, Crop Marks, Guides, Grid, Separations
# ---------------------------------------------------------------------------

def render_perspective_grid(p: QPainter, persp: PerspectiveGridState, doc: Document) -> None:
    if not persp.visible:
        return
    p.save()
    hy = persp.horizon_y
    gy = persp.ground_y
    vpl = QPointF(persp.vp_left_x if persp.points >= 2 else persp.vp_center_x, hy)
    vpr = QPointF(persp.vp_right_x if persp.points >= 2 else persp.vp_center_x, hy)
    cx = persp.vp_center_x
    top_y = hy - 220.0
    divs = max(4, persp.grid_divisions)

    # Horizon line
    p.setPen(QPen(QColor("#00D1FF"), 1.3, Qt.DashLine))
    p.drawLine(QPointF(vpl.x() - 200, hy), QPointF(vpr.x() + 200, hy))

    # Left Plane (Blue)
    l_alpha = 155 if persp.active_plane == "left" else 65
    p.setPen(QPen(QColor(66, 153, 255, l_alpha), 1.0))
    for i in range(divs + 1):
        t = i / divs
        y_edge = top_y + (gy - top_y) * t
        p.drawLine(QPointF(cx, y_edge), vpl)
        vx = cx + (vpl.x() - cx) * (t * 0.78)
        yt = top_y + (hy - top_y) * (t * 0.78)
        yb = gy + (hy - gy) * (t * 0.78)
        p.drawLine(QPointF(vx, yt), QPointF(vx, yb))

    # Right Plane (Orange)
    r_alpha = 155 if persp.active_plane == "right" else 65
    p.setPen(QPen(QColor(255, 154, 0, r_alpha), 1.0))
    for i in range(divs + 1):
        t = i / divs
        y_edge = top_y + (gy - top_y) * t
        p.drawLine(QPointF(cx, y_edge), vpr)
        vx = cx + (vpr.x() - cx) * (t * 0.78)
        yt = top_y + (hy - top_y) * (t * 0.78)
        yb = gy + (hy - gy) * (t * 0.78)
        p.drawLine(QPointF(vx, yt), QPointF(vx, yb))

    # Horizontal Ground Plane (Green)
    h_alpha = 145 if persp.active_plane == "horizontal" else 55
    p.setPen(QPen(QColor(46, 213, 115, h_alpha), 1.0))
    for i in range(1, divs):
        t = (i / divs) * 0.65
        pt_l = QPointF(cx + (vpl.x() - cx) * t, gy + (hy - gy) * t)
        pt_r = QPointF(cx + (vpr.x() - cx) * t, gy + (hy - gy) * t)
        p.drawLine(pt_l, QPointF(pt_l.x() + (vpr.x() - cx) * 0.55, pt_l.y() + (hy - gy) * 0.55))
        p.drawLine(pt_r, QPointF(pt_r.x() + (vpl.x() - cx) * 0.55, pt_r.y() + (hy - gy) * 0.55))

    # 3rd vanishing point rays
    if persp.points == 3:
        vp3 = QPointF(cx, persp.vp_third_y)
        p.setPen(QPen(QColor(180, 120, 255, 110), 1.0, Qt.DotLine))
        for dx in (-260, -130, 0, 130, 260):
            p.drawLine(QPointF(cx + dx, top_y), vp3)
        p.setBrush(QColor("#B478FF"))
        p.drawEllipse(vp3, 6, 6)

    # Vanishing Point Handles
    for vp, lbl in ((vpl, "VP-L"), (vpr, "VP-R")):
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#2680EB"), 2.0))
        p.drawEllipse(vp, 6.0, 6.0)
        p.setPen(QColor("#E2E4E9"))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.drawText(QPointF(vp.x() - 14, vp.y() - 10), lbl)
    p.restore()


def render_document(p: QPainter, doc: Document, opts: ViewOptions,
                    clip_artboard: Optional[Artboard] = None) -> None:
    """Render all artboards, layers, objects, guides, grids, and perspective overlays."""
    # Collect text-wrap obstacles once
    wrap_obstacles: List[QRectF] = []
    for o in doc.iter_all_objects():
        if o.text_wrap:
            b = object_bounds(o, doc)
            pad = o.text_wrap_offset
            wrap_obstacles.append(b.adjusted(-pad, -pad, pad, pad))

    artboards = [clip_artboard] if clip_artboard else doc.artboards

    # 1. Artboards, drop shadows, bleed & crop marks
    if opts.show_artboards:
        for idx, ab in enumerate(artboards):
            r = QRectF(ab.x, ab.y, ab.width, ab.height)
            if not opts.export_mode:
                p.fillRect(r.translated(4, 5), QColor(0, 0, 0, 85))
            p.fillRect(r, to_qcolor(ab.bg_color))
            if not opts.export_mode:
                border_col = QColor("#FF9A00") if idx == doc.active_artboard_index else QColor("#555555")
                p.setPen(QPen(border_col, 1.0))
                p.setBrush(Qt.NoBrush)
                p.drawRect(r)
                p.setPen(QColor("#9AA0AA"))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(QPointF(ab.x, ab.y - 6), f"{idx + 1:02d}  {ab.name} ({int(ab.width)}×{int(ab.height)})")

            # Print Bleed Guide (red box outside artboard)
            if opts.show_bleed and doc.bleed > 0.1:
                br = r.adjusted(-doc.bleed, -doc.bleed, doc.bleed, doc.bleed)
                p.setPen(QPen(QColor("#E53935"), 1.0, Qt.SolidLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(br)

            # Crop Marks
            if opts.show_crop_marks and doc.show_crop_marks:
                _draw_crop_marks(p, r, doc.bleed)

    # 2. Layers & Vector Objects
    for lyr in doc.layers:
        if not lyr.visible:
            continue
        p.save()
        p.setOpacity(lyr.opacity)
        for obj in lyr.objects:
            render_object(p, obj, doc, opts, wrap_obstacles)
        p.restore()

    if opts.export_mode:
        return

    # 3. Document Grid
    if opts.show_grid and doc.grid_visible:
        ab = doc.active_artboard()
        step = max(8.0, doc.grid_spacing)
        p.save()
        p.setPen(QPen(QColor(130, 145, 165, 55), 1.0))
        x = ab.x
        while x <= ab.x + ab.width:
            p.drawLine(QPointF(x, ab.y), QPointF(x, ab.y + ab.height))
            x += step
        y = ab.y
        while y <= ab.y + ab.height:
            p.drawLine(QPointF(ab.x, y), QPointF(ab.x + ab.width, y))
            y += step
        p.restore()

    # 4. Guides
    if opts.show_guides and doc.guides_visible:
        p.save()
        p.setPen(QPen(QColor("#00D1FF"), 1.0))
        for g in doc.guides:
            if g.orientation == "v":
                p.drawLine(QPointF(g.position, -5000), QPointF(g.position, 5000))
            else:
                p.drawLine(QPointF(-5000, g.position), QPointF(5000, g.position))
        p.restore()

    # 5. Perspective Grid
    render_perspective_grid(p, doc.perspective, doc)


def _draw_crop_marks(p: QPainter, r: QRectF, bleed: float) -> None:
    p.save()
    p.setPen(QPen(QColor("#111111"), 0.8))
    off = max(6.0, bleed + 4.0)
    ln = 18.0
    corners = [
        (r.left(), r.top(), -1, -1),
        (r.right(), r.top(), 1, -1),
        (r.left(), r.bottom(), -1, 1),
        (r.right(), r.bottom(), 1, 1),
    ]
    for cx, cy, sx, sy in corners:
        p.drawLine(QPointF(cx + sx * off, cy), QPointF(cx + sx * (off + ln), cy))
        p.drawLine(QPointF(cx, cy + sy * off), QPointF(cx, cy + sy * (off + ln)))
    p.restore()


def apply_separations_filter(qimg: QImage, plates: Dict[str, bool]) -> QImage:
    """Apply real-time CMYK ink plate separation preview to a rendered QImage."""
    if all(plates.get(k, True) for k in ("C", "M", "Y", "K")):
        return qimg
    rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
    w, h = rgba.width(), rgba.height()
    arr = np.frombuffer(bytes(rgba.constBits()), dtype=np.uint8).reshape((h, w, 4)).astype(np.float32) / 255.0
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    k = 1.0 - np.maximum(np.maximum(r, g), b)
    denom = np.maximum(1e-4, 1.0 - k)
    c = (1.0 - r - k) / denom
    m = (1.0 - g - k) / denom
    y = (1.0 - b - k) / denom

    if not plates.get("C", True):
        c *= 0.0
    if not plates.get("M", True):
        m *= 0.0
    if not plates.get("Y", True):
        y *= 0.0
    if not plates.get("K", True):
        k *= 0.0

    nr = (1.0 - c) * (1.0 - k)
    ng = (1.0 - m) * (1.0 - k)
    nb = (1.0 - y) * (1.0 - k)
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[:, :, 0] = np.clip(nr * 255.0, 0, 255).astype(np.uint8)
    out[:, :, 1] = np.clip(ng * 255.0, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(nb * 255.0, 0, 255).astype(np.uint8)
    out[:, :, 3] = 255
    return QImage(out.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
