"""Vector geometry engine for Vectora.

Provides cubic Bezier evaluation/fitting/simplification, parametric shape conversion to
SubPaths/QPainterPath, Pathfinder Boolean operations, Shape Builder & Live Paint region
splitting, Variable Width stroke polygonization, corner-aligned dash generation,
Offset Path, Shaper gesture recognition, Envelope Warp, Puppet Warp (MLS), Perspective
Grid projection, Blend interpolation, and Brush stroke synthesis.
"""
from __future__ import annotations

import copy
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath, QPainterPathStroker, QTransform

from .models import (
    AnchorPoint,
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    BrushDef,
    Color,
    Document,
    PerspectiveGridState,
    PuppetPin,
    SubPath,
    VectorObject,
    WidthStation,
)

# ---------------------------------------------------------------------------
# Width Profile Presets (Illustrator-style Variable Width Profiles)
# ---------------------------------------------------------------------------

WIDTH_PROFILES: Dict[str, List[Tuple[float, float, float]]] = {
    "Uniform": [(0.0, 1.0, 1.0), (1.0, 1.0, 1.0)],
    "Width Profile 1 (Elliptical)": [
        (0.0, 0.08, 0.08), (0.25, 0.72, 0.72), (0.5, 1.25, 1.25), (0.75, 0.72, 0.72), (1.0, 0.08, 0.08),
    ],
    "Width Profile 2 (Double Wave)": [
        (0.0, 0.15, 0.15), (0.25, 1.2, 1.2), (0.5, 0.45, 0.45), (0.75, 1.2, 1.2), (1.0, 0.15, 0.15),
    ],
    "Width Profile 3 (Asymmetric Flare)": [
        (0.0, 0.15, 0.15), (0.35, 1.35, 0.55), (0.7, 0.85, 1.25), (1.0, 0.12, 0.12),
    ],
    "Width Profile 4 (Triangular Taper)": [
        (0.0, 1.4, 1.4), (0.5, 0.72, 0.72), (1.0, 0.05, 0.05),
    ],
    "Width Profile 5 (Reverse Taper)": [
        (0.0, 0.05, 0.05), (0.5, 0.72, 0.72), (1.0, 1.4, 1.4),
    ],
    "Width Profile 6 (Calligraphic Ribbon)": [
        (0.0, 0.9, 0.25), (0.33, 0.35, 1.15), (0.66, 1.15, 0.35), (1.0, 0.25, 0.9),
    ],
}


def get_width_stations(stroke: AppearanceStroke) -> List[WidthStation]:
    if stroke.width_stations:
        return sorted(stroke.width_stations, key=lambda s: s.t)
    prof = WIDTH_PROFILES.get(stroke.width_profile_name)
    if prof and stroke.width_profile_name != "Uniform":
        return [WidthStation(t, l, r) for t, l, r in prof]
    return []


# ---------------------------------------------------------------------------
# Cubic Bezier & Path Conversions
# ---------------------------------------------------------------------------

def eval_cubic(p0: Tuple[float, float], p1: Tuple[float, float],
               p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t
    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return (x, y)


def eval_cubic_deriv(p0: Tuple[float, float], p1: Tuple[float, float],
                     p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    u = 1.0 - t
    dx = 3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0])
    dy = 3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1])
    return (dx, dy)


def subpaths_to_qpath(subpaths: Sequence[SubPath]) -> QPainterPath:
    qp = QPainterPath()
    qp.setFillRule(Qt.WindingFill)
    for sp in subpaths:
        if not sp.anchors:
            continue
        a0 = sp.anchors[0]
        qp.moveTo(a0.x, a0.y)
        n = len(sp.anchors)
        seg_count = n if sp.closed else n - 1
        for i in range(seg_count):
            a = sp.anchors[i]
            b = sp.anchors[(i + 1) % n]
            is_line = (
                abs(a.out_x - a.x) < 1e-4 and abs(a.out_y - a.y) < 1e-4
                and abs(b.in_x - b.x) < 1e-4 and abs(b.in_y - b.y) < 1e-4
            )
            if is_line:
                qp.lineTo(b.x, b.y)
            else:
                qp.cubicTo(a.out_x, a.out_y, b.in_x, b.in_y, b.x, b.y)
        if sp.closed:
            qp.closeSubpath()
    return qp


def qpath_to_subpaths(qp: QPainterPath) -> List[SubPath]:
    """Convert a QPainterPath (including lines & cubics) back into exact SubPaths."""
    subpaths: List[SubPath] = []
    cur: Optional[SubPath] = None
    n = qp.elementCount()
    i = 0
    while i < n:
        el = qp.elementAt(i)
        if el.type == QPainterPath.MoveToElement:
            if cur and cur.anchors:
                _finalize_subpath(cur)
                subpaths.append(cur)
            cur = SubPath(anchors=[AnchorPoint(el.x, el.y)], closed=False)
            i += 1
        elif el.type == QPainterPath.LineToElement:
            if cur is None:
                cur = SubPath(anchors=[AnchorPoint(el.x, el.y)], closed=False)
            else:
                cur.anchors.append(AnchorPoint(el.x, el.y))
            i += 1
        elif el.type == QPainterPath.CurveToElement:
            if cur is None or not cur.anchors:
                i += 1
                continue
            c1 = el
            c2 = qp.elementAt(i + 1) if i + 1 < n else el
            end = qp.elementAt(i + 2) if i + 2 < n else c2
            prev = cur.anchors[-1]
            prev.out_x, prev.out_y = c1.x, c1.y
            nxt = AnchorPoint(end.x, end.y, in_x=c2.x, in_y=c2.y, out_x=end.x, out_y=end.y, point_type="smooth")
            cur.anchors.append(nxt)
            i += 3
        else:
            i += 1
    if cur and cur.anchors:
        _finalize_subpath(cur)
        subpaths.append(cur)
    return subpaths


def _finalize_subpath(sp: SubPath) -> None:
    if len(sp.anchors) >= 2:
        first = sp.anchors[0]
        last = sp.anchors[-1]
        if math.hypot(first.x - last.x, first.y - last.y) < 1e-2:
            first.in_x = last.in_x
            first.in_y = last.in_y
            sp.anchors.pop()
            sp.closed = True


# ---------------------------------------------------------------------------
# Parametric Shape Generators -> SubPaths / QPainterPath
# ---------------------------------------------------------------------------

def shape_to_qpath(obj: VectorObject) -> QPainterPath:
    qp = QPainterPath()
    x, y, w, h = obj.x, obj.y, obj.width, obj.height
    cx, cy = x + w * 0.5, y + h * 0.5
    rx, ry = max(1e-3, abs(w) * 0.5), max(1e-3, abs(h) * 0.5)
    st = obj.shape_type

    if st == "rect":
        r = max(0.0, min(obj.corner_radius, rx, ry))
        if r > 0.1:
            qp.addRoundedRect(QRectF(x, y, w, h), r, r)
        else:
            qp.addRect(QRectF(x, y, w, h))
    elif st == "ellipse":
        qp.addEllipse(QRectF(x, y, w, h))
    elif st == "polygon":
        sides = max(3, int(obj.sides))
        for i in range(sides):
            ang = -math.pi / 2 + 2 * math.pi * i / sides
            px = cx + rx * math.cos(ang)
            py = cy + ry * math.sin(ang)
            if i == 0:
                qp.moveTo(px, py)
            else:
                qp.lineTo(px, py)
        qp.closeSubpath()
    elif st == "star":
        pts = max(3, int(obj.sides))
        ratio = max(0.1, min(0.95, float(obj.inner_radius_ratio)))
        for i in range(pts * 2):
            ang = -math.pi / 2 + math.pi * i / pts
            rr_x = rx if i % 2 == 0 else rx * ratio
            rr_y = ry if i % 2 == 0 else ry * ratio
            px = cx + rr_x * math.cos(ang)
            py = cy + rr_y * math.sin(ang)
            if i == 0:
                qp.moveTo(px, py)
            else:
                qp.lineTo(px, py)
        qp.closeSubpath()
    elif st == "line":
        qp.moveTo(x, y)
        qp.lineTo(x + w, y + h)
    elif st == "arc":
        rect = QRectF(x, y, w, h)
        qp.arcMoveTo(rect, 0)
        qp.arcTo(rect, 0, obj.arc_sweep)
    elif st == "spiral":
        turns = max(1.0, float(obj.spiral_turns))
        steps = int(turns * 40)
        max_r = min(rx, ry)
        for i in range(steps + 1):
            t = i / steps
            ang = t * turns * 2 * math.pi
            rad = t * max_r
            px = cx + rad * math.cos(ang)
            py = cy + rad * math.sin(ang)
            if i == 0:
                qp.moveTo(px, py)
            else:
                qp.lineTo(px, py)
    elif st == "polar_grid":
        rings = 4
        spokes = max(4, int(obj.sides))
        for r_i in range(1, rings + 1):
            f = r_i / rings
            qp.addEllipse(QRectF(cx - rx * f, cy - ry * f, w * f, h * f))
        for i in range(spokes):
            ang = 2 * math.pi * i / spokes
            qp.moveTo(cx, cy)
            qp.lineTo(cx + rx * math.cos(ang), cy + ry * math.sin(ang))
    else:
        qp.addRect(QRectF(x, y, w, h))

    if abs(obj.rotation) > 1e-4 or abs(obj.shear_x) > 1e-4 or abs(obj.shear_y) > 1e-4:
        tr = QTransform()
        tr.translate(cx, cy)
        if abs(obj.rotation) > 1e-4:
            tr.rotate(obj.rotation)
        if abs(obj.shear_x) > 1e-4 or abs(obj.shear_y) > 1e-4:
            tr.shear(obj.shear_x, obj.shear_y)
        tr.translate(-cx, -cy)
        qp = tr.map(qp)
    return qp


def object_to_qpath(obj: VectorObject, doc: Optional[Document] = None) -> QPainterPath:
    """Return the primary vector QPainterPath of any VectorObject."""
    if obj.kind == "path" or obj.kind == "live_paint":
        qp = subpaths_to_qpath(obj.subpaths)
        return qp
    if obj.kind == "shape":
        return shape_to_qpath(obj)
    if obj.kind == "text":
        return text_to_outline_qpath(obj)
    if obj.kind == "group":
        combined = QPainterPath()
        for ch in obj.children:
            combined.addPath(object_to_qpath(ch, doc))
        return combined
    if obj.kind == "symbol_instance" and doc is not None:
        sym = doc.get_symbol(obj.symbol_id)
        if sym:
            base = object_to_qpath(sym.artwork, doc)
            br = base.boundingRect()
            if br.width() > 1e-4 and br.height() > 1e-4:
                tr = QTransform()
                tr.translate(obj.x, obj.y)
                tr.scale(obj.width / br.width(), obj.height / br.height())
                tr.translate(-br.x(), -br.y())
                return tr.map(base)
    qp = QPainterPath()
    qp.addRect(QRectF(obj.x, obj.y, max(1.0, obj.width), max(1.0, obj.height)))
    return qp


def object_bounds(obj: VectorObject, doc: Optional[Document] = None) -> QRectF:
    if obj.kind in ("image", "graph", "mockup"):
        return QRectF(obj.x, obj.y, max(1.0, obj.width), max(1.0, obj.height))
    if obj.kind == "text":
        if obj.text_mode == "area":
            return QRectF(obj.x, obj.y, max(20.0, obj.width), max(20.0, obj.height))
        if obj.text_mode == "path" and obj.subpaths:
            br = subpaths_to_qpath(obj.subpaths).boundingRect()
            pad = obj.text_style.font_size * 1.2
            return br.adjusted(-pad, -pad, pad, pad)
        qp = text_to_outline_qpath(obj)
        br = qp.boundingRect()
        if br.isEmpty():
            return QRectF(obj.x, obj.y, max(40.0, obj.text_style.font_size * 2), max(20.0, obj.text_style.font_size))
        return br
    if obj.kind == "group":
        if not obj.children:
            return QRectF(obj.x, obj.y, max(1.0, obj.width), max(1.0, obj.height))
        rect = object_bounds(obj.children[0], doc)
        for ch in obj.children[1:]:
            rect = rect.united(object_bounds(ch, doc))
        return rect
    if obj.kind == "repeat" and obj.children:
        br = object_bounds(obj.children[0], doc)
        if obj.repeat_mode == "radial":
            r = obj.repeat_radius + max(br.width(), br.height()) * 0.6
            return QRectF(obj.x - r, obj.y - r, r * 2, r * 2)
        elif obj.repeat_mode == "grid":
            return QRectF(
                br.x(), br.y(),
                max(br.width(), (obj.repeat_cols - 1) * obj.repeat_spacing_x + br.width()),
                max(br.height(), (obj.repeat_rows - 1) * obj.repeat_spacing_y + br.height()),
            )
        elif obj.repeat_mode == "mirror":
            return QRectF(br.x(), br.y(), br.width() * 2 + 20, br.height())
    if obj.kind == "blend" and len(obj.children) >= 2:
        return object_bounds(obj.children[0], doc).united(object_bounds(obj.children[1], doc))
    if obj.kind == "symbol_instance":
        return QRectF(obj.x, obj.y, max(10.0, obj.width), max(10.0, obj.height))
    qp = object_to_qpath(obj, doc)
    br = qp.boundingRect()
    if br.isEmpty():
        return QRectF(obj.x, obj.y, max(1.0, obj.width), max(1.0, obj.height))
    return br


def translate_object(obj: VectorObject, dx: float, dy: float) -> None:
    obj.x += dx
    obj.y += dy
    for sp in obj.subpaths:
        sp.translate(dx, dy)
    for sp in obj.puppet_base_subpaths:
        sp.translate(dx, dy)
    for pin in obj.puppet_pins:
        pin.x += dx
        pin.y += dy
        pin.orig_x += dx
        pin.orig_y += dy
    for ch in obj.children:
        translate_object(ch, dx, dy)


def transform_object_affine(obj: VectorObject, tr: QTransform, doc: Optional[Document] = None) -> None:
    """Apply an affine QTransform (scale, rotate, reflect, shear) to any object."""
    if obj.kind in ("path", "live_paint"):
        m11, m12, m21, m22, tx, ty = tr.m11(), tr.m12(), tr.m21(), tr.m22(), tr.dx(), tr.dy()
        for sp in obj.subpaths:
            for a in sp.anchors:
                a.transform_affine(m11, m12, m21, m22, tx, ty)
        br = subpaths_to_qpath(obj.subpaths).boundingRect()
        obj.x, obj.y, obj.width, obj.height = br.x(), br.y(), br.width(), br.height()
    elif obj.kind == "group" or obj.kind == "blend":
        for ch in obj.children:
            transform_object_affine(ch, tr, doc)
        br = object_bounds(obj, doc)
        obj.x, obj.y, obj.width, obj.height = br.x(), br.y(), br.width(), br.height()
    else:
        # Map bounding box corners for shapes/images/text/graphs/mockups/symbols
        br = object_bounds(obj, doc)
        tl = tr.map(QPointF(br.x(), br.y()))
        tr_pt = tr.map(QPointF(br.right(), br.y()))
        bl = tr.map(QPointF(br.x(), br.bottom()))
        new_w = max(2.0, math.hypot(tr_pt.x() - tl.x(), tr_pt.y() - tl.y()))
        new_h = max(2.0, math.hypot(bl.x() - tl.x(), bl.y() - tl.y()))
        angle_rad = math.atan2(tr_pt.y() - tl.y(), tr_pt.x() - tl.x())
        center = tr.map(br.center())
        obj.width = new_w
        obj.height = new_h
        obj.x = center.x() - new_w * 0.5
        obj.y = center.y() - new_h * 0.5
        if abs(angle_rad) > 1e-4:
            obj.rotation = (obj.rotation + math.degrees(angle_rad)) % 360.0
        if obj.kind == "text" and br.height() > 1e-3 and obj.text_mode == "point":
            scale_y = new_h / br.height()
            obj.text_style.font_size = max(4.0, min(400.0, obj.text_style.font_size * scale_y))
        if obj.subpaths:
            m11, m12, m21, m22, tx, ty = tr.m11(), tr.m12(), tr.m21(), tr.m22(), tr.dx(), tr.dy()
            for sp in obj.subpaths:
                for a in sp.anchors:
                    a.transform_affine(m11, m12, m21, m22, tx, ty)


def convert_object_to_path(obj: VectorObject, doc: Optional[Document] = None) -> VectorObject:
    """Convert live shapes or text into editable Bezier PathObject."""
    qp = object_to_qpath(obj, doc)
    sps = qpath_to_subpaths(qp)
    br = qp.boundingRect()
    out = VectorObject(
        name=f"{obj.name} (Path)",
        kind="path",
        layer_id=obj.layer_id,
        appearance=copy.deepcopy(obj.appearance),
        x=br.x(), y=br.y(), width=br.width(), height=br.height(),
        subpaths=sps,
    )
    return out


# ---------------------------------------------------------------------------
# Text to Outlines (supports Point, Area, On-Path, Touch Type, OpenType)
# ---------------------------------------------------------------------------

def build_qfont(style) -> QFont:
    font = QFont(style.font_family)
    font.setPixelSize(max(4, int(round(style.font_size))))
    # Map 100..900 weight to Qt QFont.Weight
    w_val = max(100, min(900, int(style.font_weight)))
    font.setWeight(QFont.Weight(w_val))
    font.setStretch(max(50, min(200, int(round(style.font_width)))))
    font.setItalic(bool(style.italic))
    font.setKerning(bool(style.kerning))
    font.setUnderline(bool(style.underline))
    font.setStrikeOut(bool(style.strikethrough))
    if abs(style.tracking) > 1e-3:
        font.setLetterSpacing(QFont.AbsoluteSpacing, style.tracking)
    if style.ot_small_caps:
        font.setCapitalization(QFont.SmallCaps)
    # Apply OpenType feature tags via Qt 6.7+ QFont.setFeature if available
    if hasattr(font, "setFeature"):
        try:
            font.setFeature(QFont.Tag(b"liga"), 1 if style.ot_ligatures else 0)
            font.setFeature(QFont.Tag(b"smcp"), 1 if style.ot_small_caps else 0)
            font.setFeature(QFont.Tag(b"tnum"), 1 if style.ot_tabular_nums else 0)
            font.setFeature(QFont.Tag(b"frac"), 1 if style.ot_fractions else 0)
            font.setFeature(QFont.Tag(b"salt"), 1 if style.ot_stylistic_alt else 0)
        except Exception:
            pass
    return font


def text_to_outline_qpath(obj: VectorObject) -> QPainterPath:
    """Convert any TextObject (Point, Area, On-Path, with Touch Type) to a QPainterPath."""
    font = build_qfont(obj.text_style)
    fm = QFontMetricsF(font)
    result = QPainterPath()
    text = obj.text or ""
    if not text:
        return result

    if obj.text_mode == "path" and obj.subpaths:
        base_path = subpaths_to_qpath(obj.subpaths)
        total_len = base_path.length()
        if total_len < 1e-2:
            return result
        dist = obj.path_text_offset * total_len
        for idx, ch in enumerate(text):
            adv = fm.horizontalAdvance(ch) + obj.text_style.tracking
            mid_d = dist + adv * 0.5
            if mid_d > total_len:
                break
            pct = max(0.0, min(1.0, base_path.percentAtLength(mid_d)))
            pt = base_path.pointAtPercent(pct)
            ang = -base_path.angleAtPercent(pct)
            ct = obj.char_transforms.get(str(idx))
            ch_path = QPainterPath()
            ch_path.addText(-adv * 0.5, 0, font, ch)
            tr = QTransform()
            tr.translate(pt.x(), pt.y())
            tr.rotate(ang + (ct.rotation if ct else 0.0))
            if ct:
                tr.translate(ct.dx, ct.dy)
                tr.scale(ct.scale_x, ct.scale_y)
            result.addPath(tr.map(ch_path))
            dist += adv
        return result

    # Point or Area text (supports Touch Type per-char transforms!)
    lines = _layout_text_lines(obj, fm)
    line_h = obj.text_style.font_size * obj.text_style.leading
    ascent = fm.ascent()
    char_global_idx = 0
    for line_i, (line_str, line_x) in enumerate(lines):
        baseline_y = obj.y + ascent + line_i * line_h
        cur_x = line_x
        for ch in line_str:
            adv = fm.horizontalAdvance(ch) + obj.text_style.tracking
            ct = obj.char_transforms.get(str(char_global_idx))
            if ct and (ct.dx != 0 or ct.dy != 0 or ct.scale_x != 1 or ct.scale_y != 1 or ct.rotation != 0):
                cp = QPainterPath()
                cp.addText(0, 0, font, ch)
                tr = QTransform()
                tr.translate(cur_x + ct.dx + adv * 0.5, baseline_y + ct.dy)
                tr.rotate(ct.rotation)
                tr.scale(ct.scale_x, ct.scale_y)
                tr.translate(-adv * 0.5, 0)
                result.addPath(tr.map(cp))
            else:
                result.addText(cur_x, baseline_y, font, ch)
            cur_x += adv
            char_global_idx += 1
        char_global_idx += 1  # newline offset

    if abs(obj.rotation) > 1e-4:
        br = result.boundingRect()
        tr = QTransform()
        tr.translate(br.center().x(), br.center().y())
        tr.rotate(obj.rotation)
        tr.translate(-br.center().x(), -br.center().y())
        result = tr.map(result)
    return result


def _layout_text_lines(obj: VectorObject, fm: QFontMetricsF,
                       wrap_obstacles: Optional[List[QRectF]] = None) -> List[Tuple[str, float]]:
    """Lay out point or area text into (line_string, start_x) pairs."""
    raw_paras = (obj.text or "").split("\n")
    lines: List[Tuple[str, float]] = []
    max_w = max(24.0, obj.width) if obj.text_mode == "area" else 1e9
    line_h = obj.text_style.font_size * obj.text_style.leading

    for p_idx, para in enumerate(raw_paras):
        if obj.text_mode != "area":
            w = fm.horizontalAdvance(para)
            lx = obj.x
            if obj.text_style.align == "center":
                lx = obj.x - w * 0.5
            elif obj.text_style.align == "right":
                lx = obj.x - w
            lines.append((para, lx))
            continue

        words = para.split(" ") if para else [""]
        cur = ""
        first_in_para = True
        for word in words:
            y_cur = obj.y + len(lines) * line_h
            avail_x = obj.x + (obj.text_style.first_indent if first_in_para else 0.0)
            avail_w = max_w - (obj.text_style.first_indent if first_in_para else 0.0)
            # Check text wrap around objects!
            if wrap_obstacles:
                line_rect = QRectF(avail_x, y_cur, avail_w, line_h)
                for obs in wrap_obstacles:
                    if line_rect.intersects(obs):
                        if obs.center().x() < obj.x + max_w * 0.5:
                            shift = max(0.0, obs.right() - avail_x)
                            avail_x += shift
                            avail_w = max(24.0, avail_w - shift)
                        else:
                            avail_w = max(24.0, obs.left() - avail_x)

            candidate = (cur + " " + word).strip() if cur else word
            if fm.horizontalAdvance(candidate) <= avail_w or not cur:
                cur = candidate
            else:
                lines.append((cur, _align_line_x(cur, fm, avail_x, avail_w, obj.text_style.align)))
                cur = word
                first_in_para = False
        avail_x = obj.x + (obj.text_style.first_indent if first_in_para else 0.0)
        avail_w = max_w - (obj.text_style.first_indent if first_in_para else 0.0)
        lines.append((cur, _align_line_x(cur, fm, avail_x, avail_w, obj.text_style.align)))
    return lines


def _align_line_x(line: str, fm: QFontMetricsF, x0: float, box_w: float, align: str) -> float:
    lw = fm.horizontalAdvance(line)
    if align == "center":
        return x0 + (box_w - lw) * 0.5
    if align == "right":
        return x0 + (box_w - lw)
    return x0


# ---------------------------------------------------------------------------
# Pathfinder Boolean Operations & Shape Builder / Live Paint Regions
# ---------------------------------------------------------------------------

def pathfinder_op(objects: List[VectorObject], op: str, doc: Optional[Document] = None) -> List[VectorObject]:
    """Execute Illustrator Pathfinder operations on >= 2 objects.

    Supported ops: 'unite', 'minus_front', 'intersect', 'exclude', 'minus_back',
                   'divide', 'trim', 'merge', 'crop', 'outline'.
    """
    if len(objects) < 2:
        return []
    paths = [object_to_qpath(o, doc) for o in objects]
    base_app = copy.deepcopy(objects[0].appearance)
    top_app = copy.deepcopy(objects[-1].appearance)
    layer_id = objects[0].layer_id

    def _make_obj(qp: QPainterPath, app: Appearance, name: str) -> Optional[VectorObject]:
        sps = qpath_to_subpaths(qp)
        if not sps:
            return None
        br = qp.boundingRect()
        if br.width() < 0.2 and br.height() < 0.2:
            return None
        return VectorObject(
            name=name, kind="path", layer_id=layer_id,
            appearance=copy.deepcopy(app),
            x=br.x(), y=br.y(), width=br.width(), height=br.height(),
            subpaths=sps,
        )

    if op == "unite":
        res = paths[0]
        for p in paths[1:]:
            res = res.united(p)
        o = _make_obj(res.simplified(), top_app, "United Path")
        return [o] if o else []

    if op == "minus_front":
        res = paths[0]
        for p in paths[1:]:
            res = res.subtracted(p)
        o = _make_obj(res.simplified(), base_app, "Minus Front")
        return [o] if o else []

    if op == "minus_back":
        res = paths[-1]
        for p in paths[:-1]:
            res = res.subtracted(p)
        o = _make_obj(res.simplified(), top_app, "Minus Back")
        return [o] if o else []

    if op == "intersect":
        res = paths[0]
        for p in paths[1:]:
            res = res.intersected(p)
        o = _make_obj(res.simplified(), top_app, "Intersection")
        return [o] if o else []

    if op == "exclude":
        res = paths[0]
        for p in paths[1:]:
            u = res.united(p)
            inter = res.intersected(p)
            res = u.subtracted(inter)
        o = _make_obj(res.simplified(), top_app, "Excluded Path")
        return [o] if o else []

    if op == "crop":
        clip = paths[-1]
        out: List[VectorObject] = []
        for idx, p in enumerate(paths[:-1]):
            inter = p.intersected(clip).simplified()
            o = _make_obj(inter, objects[idx].appearance, f"Cropped {idx + 1}")
            if o:
                out.append(o)
        return out

    if op == "outline":
        out = []
        for idx, p in enumerate(paths):
            app = copy.deepcopy(objects[idx].appearance)
            fill_col = app.primary_fill.color if app.primary_fill.fill_type == "solid" else Color.from_hex("#111111")
            app.fills = [AppearanceFill(fill_type="none")]
            app.strokes = [AppearanceStroke(stroke_type="solid", color=fill_col, width=1.5)]
            o = _make_obj(p, app, f"Outline {idx + 1}")
            if o:
                out.append(o)
        return out

    if op == "trim" or op == "merge":
        # Each shape gets higher shapes subtracted from it
        out = []
        acc = QPainterPath()
        for idx in range(len(paths) - 1, -1, -1):
            piece = paths[idx].subtracted(acc).simplified()
            acc = acc.united(paths[idx])
            o = _make_obj(piece, objects[idx].appearance, f"Trimmed {idx + 1}")
            if o:
                out.insert(0, o)
        return out

    if op == "divide":
        # Planar Venn decomposition into disjoint non-empty regions!
        regions = compute_planar_regions(objects, doc)
        out = []
        for i, (rpath, color_app) in enumerate(regions):
            o = _make_obj(rpath, color_app, f"Divided Region {i + 1}")
            if o:
                out.append(o)
        return out

    return []


def compute_planar_regions(objects: List[VectorObject], doc: Optional[Document] = None) -> List[Tuple[QPainterPath, Appearance]]:
    """Decompose overlapping vector objects into disjoint atomic planar regions.

    Powers Pathfinder Divide, interactive Shape Builder, and Live Paint Bucket!
    """
    if not objects:
        return []
    # Cap combinatorics cleanly if huge selection
    objs = objects[:12]
    # Incremental cell refinement: each new path splits existing cells into (cell ∩ P) and (cell \ P)
    # plus the remainder (P \ union_so_far).
    cells: List[Tuple[QPainterPath, Appearance]] = []
    union_all = QPainterPath()
    for obj in objs:
        p = object_to_qpath(obj, doc)
        if p.isEmpty():
            continue
        new_cells: List[Tuple[QPainterPath, Appearance]] = []
        for cpath, capp in cells:
            inter = cpath.intersected(p).simplified()
            if not inter.isEmpty() and inter.boundingRect().width() > 0.5 and inter.boundingRect().height() > 0.5:
                new_cells.append((inter, copy.deepcopy(obj.appearance)))
            diff = cpath.subtracted(p).simplified()
            if not diff.isEmpty() and diff.boundingRect().width() > 0.5 and diff.boundingRect().height() > 0.5:
                new_cells.append((diff, capp))
        rem = p.subtracted(union_all).simplified()
        if not rem.isEmpty() and rem.boundingRect().width() > 0.5 and rem.boundingRect().height() > 0.5:
            new_cells.append((rem, copy.deepcopy(obj.appearance)))
        union_all = union_all.united(p)
        cells = new_cells
    return cells


# ---------------------------------------------------------------------------
# Path Editing: Simplify, Offset, Outline Stroke, Join, Cut, Variable Width
# ---------------------------------------------------------------------------

def rdp_simplify(pts: List[Tuple[float, float]], eps: float) -> List[Tuple[float, float]]:
    """Ramer-Douglas-Peucker polyline simplification."""
    if len(pts) <= 2:
        return list(pts)
    x1, y1 = pts[0]
    x2, y2 = pts[-1]
    dx, dy = x2 - x1, y2 - y1
    denom = math.hypot(dx, dy)
    max_d = -1.0
    max_i = 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        if denom < 1e-6:
            d = math.hypot(px - x1, py - y1)
        else:
            d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / denom
        if d > max_d:
            max_d = d
            max_i = i
    if max_d > eps:
        left = rdp_simplify(pts[:max_i + 1], eps)
        right = rdp_simplify(pts[max_i:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def fit_catmull_rom_subpath(pts: List[Tuple[float, float]], closed: bool = False, tension: float = 0.5) -> SubPath:
    """Convert a sequence of through-points into a smooth cubic Bezier SubPath."""
    n = len(pts)
    if n == 0:
        return SubPath()
    if n == 1:
        return SubPath([AnchorPoint(pts[0][0], pts[0][1])], closed=False)
    anchors: List[AnchorPoint] = []
    for i in range(n):
        p_prev = pts[(i - 1) % n] if closed else pts[max(0, i - 1)]
        p_curr = pts[i]
        p_next = pts[(i + 1) % n] if closed else pts[min(n - 1, i + 1)]
        tx = (p_next[0] - p_prev[0]) * (tension / 3.0)
        ty = (p_next[1] - p_prev[1]) * (tension / 3.0)
        a = AnchorPoint(
            p_curr[0], p_curr[1],
            in_x=p_curr[0] - tx, in_y=p_curr[1] - ty,
            out_x=p_curr[0] + tx, out_y=p_curr[1] + ty,
            point_type="smooth",
        )
        anchors.append(a)
    if not closed:
        anchors[0].in_x, anchors[0].in_y = anchors[0].x, anchors[0].y
        anchors[-1].out_x, anchors[-1].out_y = anchors[-1].x, anchors[-1].y
    return SubPath(anchors=anchors, closed=closed)


def simplify_subpaths(subpaths: List[SubPath], tolerance: float = 3.0, smooth: bool = True) -> List[SubPath]:
    out: List[SubPath] = []
    for sp in subpaths:
        qp = subpaths_to_qpath([sp])
        total = qp.length()
        if total < 1.0:
            out.append(copy.deepcopy(sp))
            continue
        samples = max(12, min(400, int(total / 3.0)))
        pts = [(qp.pointAtPercent(i / samples).x(), qp.pointAtPercent(i / samples).y()) for i in range(samples + 1)]
        reduced = rdp_simplify(pts, max(0.4, tolerance))
        if sp.closed and len(reduced) > 2 and math.hypot(reduced[0][0] - reduced[-1][0], reduced[0][1] - reduced[-1][1]) < tolerance * 2:
            reduced.pop()
        if smooth:
            out.append(fit_catmull_rom_subpath(reduced, closed=sp.closed, tension=0.45))
        else:
            out.append(SubPath([AnchorPoint(x, y) for x, y in reduced], closed=sp.closed))
    return out


def offset_qpath(qp: QPainterPath, offset: float, join: str = "round") -> QPainterPath:
    """Offset a path outward (offset > 0) or inward (offset < 0)."""
    if abs(offset) < 0.05:
        return QPainterPath(qp)
    stroker = QPainterPathStroker()
    stroker.setWidth(abs(offset) * 2.0)
    join_map = {"miter": Qt.MiterJoin, "bevel": Qt.BevelJoin, "round": Qt.RoundJoin}
    stroker.setJoinStyle(join_map.get(join, Qt.RoundJoin))
    stroker.setCapStyle(Qt.RoundCap)
    band = stroker.createStroke(qp)
    if offset > 0:
        return qp.united(band).simplified()
    return qp.subtracted(band).simplified()


def outline_stroke_qpath(qp: QPainterPath, stroke: AppearanceStroke) -> QPainterPath:
    """Expand a stroke (including variable width!) into a filled closed outline QPainterPath."""
    stations = get_width_stations(stroke)
    if stations:
        return build_variable_width_path(qp, stroke.width, stations)
    stroker = QPainterPathStroker()
    stroker.setWidth(max(0.2, stroke.width))
    cap_map = {"butt": Qt.FlatCap, "square": Qt.SquareCap, "round": Qt.RoundCap}
    join_map = {"miter": Qt.MiterJoin, "bevel": Qt.BevelJoin, "round": Qt.RoundJoin}
    stroker.setCapStyle(cap_map.get(stroke.cap, Qt.RoundCap))
    stroker.setJoinStyle(join_map.get(stroke.join, Qt.RoundJoin))
    stroker.setMiterLimit(stroke.miter_limit)
    if stroke.dash_pattern:
        stroker.setDashPattern(stroke.dash_pattern)
    return stroker.createStroke(qp).simplified()


def build_variable_width_path(qp: QPainterPath, base_width: float,
                              stations: Sequence[WidthStation], samples: int = 96) -> QPainterPath:
    """Generate a smooth closed vector ribbon with varying left/right thickness along a path."""
    total_len = qp.length()
    if total_len < 1e-2:
        return QPainterPath()
    st_sorted = sorted(stations, key=lambda s: s.t)

    def _interp_width(t: float) -> Tuple[float, float]:
        if not st_sorted:
            return (base_width * 0.5, base_width * 0.5)
        if t <= st_sorted[0].t:
            return (base_width * 0.5 * st_sorted[0].left_scale, base_width * 0.5 * st_sorted[0].right_scale)
        if t >= st_sorted[-1].t:
            return (base_width * 0.5 * st_sorted[-1].left_scale, base_width * 0.5 * st_sorted[-1].right_scale)
        for i in range(len(st_sorted) - 1):
            a, b = st_sorted[i], st_sorted[i + 1]
            if a.t <= t <= b.t:
                u = (t - a.t) / max(1e-6, b.t - a.t)
                # Smoothstep cosine interpolation for Illustrator-grade organic taper
                u = 0.5 - 0.5 * math.cos(u * math.pi)
                ls = a.left_scale + (b.left_scale - a.left_scale) * u
                rs = a.right_scale + (b.right_scale - a.right_scale) * u
                return (base_width * 0.5 * ls, base_width * 0.5 * rs)
        return (base_width * 0.5, base_width * 0.5)

    left_pts: List[QPointF] = []
    right_pts: List[QPointF] = []
    n = max(24, min(200, int(total_len / 4.0)))
    for i in range(n + 1):
        t = i / n
        pct = max(0.0, min(1.0, qp.percentAtLength(t * total_len)))
        pt = qp.pointAtPercent(pct)
        ang_rad = math.radians(-qp.angleAtPercent(pct))
        nx, ny = -math.sin(ang_rad), math.cos(ang_rad)
        lw, rw = _interp_width(t)
        left_pts.append(QPointF(pt.x() + nx * lw, pt.y() + ny * lw))
        right_pts.append(QPointF(pt.x() - nx * rw, pt.y() - ny * rw))

    out = QPainterPath()
    if not left_pts:
        return out
    out.moveTo(left_pts[0])
    for p in left_pts[1:]:
        out.lineTo(p)
    for p in reversed(right_pts):
        out.lineTo(p)
    out.closeSubpath()
    return out


def build_corner_aligned_dash_path(qp: QPainterPath, dash_pattern: List[float],
                                   stroke_width: float) -> QPainterPath:
    """Adjust dash spacing per segment so dashes land symmetrically on path ends & corners."""
    if not dash_pattern or len(dash_pattern) < 1:
        return qp
    dash = max(1.0, dash_pattern[0] * max(1.0, stroke_width * 0.5))
    gap = max(1.0, (dash_pattern[1] if len(dash_pattern) > 1 else dash_pattern[0]) * max(1.0, stroke_width * 0.5))
    total = qp.length()
    if total < dash * 1.5:
        return qp
    # Compute integer number of dashes so path starts AND ends on a full dash
    cycle = dash + gap
    num_gaps = max(1, int(round((total - dash) / cycle)))
    adj_gap = max(0.5, (total - (num_gaps + 1) * dash) / num_gaps)
    adj_dash = dash
    if adj_gap < 0.5:
        scale = total / ((num_gaps + 1) * dash + num_gaps * gap)
        adj_dash = dash * scale
        adj_gap = gap * scale

    out = QPainterPath()
    pos = 0.0
    for k in range(num_gaps + 1):
        d0 = min(total, pos)
        d1 = min(total, pos + adj_dash)
        if d1 > d0 + 0.1:
            segs = max(2, int((d1 - d0) / 4.0))
            for s in range(segs + 1):
                dd = d0 + (d1 - d0) * (s / segs)
                pt = qp.pointAtPercent(max(0.0, min(1.0, qp.percentAtLength(dd))))
                if s == 0:
                    out.moveTo(pt)
                else:
                    out.lineTo(pt)
        pos += adj_dash + adj_gap
    return out


def split_subpath_at_point(sp: SubPath, px: float, py: float) -> List[SubPath]:
    """Scissors tool: split a SubPath at the closest point to (px, py)."""
    if len(sp.anchors) < 2:
        return [sp]
    best_i = 0
    best_d = 1e18
    for i, a in enumerate(sp.anchors):
        d = math.hypot(a.x - px, a.y - py)
        if d < best_d:
            best_d = d
            best_i = i
    if sp.closed:
        # Open closed path at best_i
        reordered = sp.anchors[best_i:] + sp.anchors[:best_i]
        reordered.append(copy.deepcopy(reordered[0]))
        return [SubPath(anchors=reordered, closed=False)]
    if best_i <= 0 or best_i >= len(sp.anchors) - 1:
        mid = len(sp.anchors) // 2
        best_i = max(1, min(len(sp.anchors) - 1, mid))
    a_left = copy.deepcopy(sp.anchors[:best_i + 1])
    a_right = copy.deepcopy(sp.anchors[best_i:])
    return [SubPath(anchors=a_left, closed=False), SubPath(anchors=a_right, closed=False)]


def knife_slice_object(obj: VectorObject, cut_pts: List[Tuple[float, float]],
                       doc: Optional[Document] = None) -> List[VectorObject]:
    """Knife tool: slice a closed shape along a freeform polyline into two closed VectorObjects."""
    if len(cut_pts) < 2:
        return []
    base_qp = object_to_qpath(obj, doc)
    br = base_qp.boundingRect().adjusted(-120, -120, 120, 120)
    # Build two giant half-plane polygons on left and right side of cut_pts
    p0 = cut_pts[0]
    p1 = cut_pts[-1]
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = max(1e-3, math.hypot(dx, dy))
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    ext = max(br.width(), br.height()) * 2.5

    ext_pts = [(p0[0] - ux * ext, p0[1] - uy * ext)] + list(cut_pts) + [(p1[0] + ux * ext, p1[1] + uy * ext)]
    left_poly = QPainterPath()
    left_poly.moveTo(ext_pts[0][0], ext_pts[0][1])
    for x, y in ext_pts[1:]:
        left_poly.lineTo(x, y)
    left_poly.lineTo(ext_pts[-1][0] + nx * ext, ext_pts[-1][1] + ny * ext)
    left_poly.lineTo(ext_pts[0][0] + nx * ext, ext_pts[0][1] + ny * ext)
    left_poly.closeSubpath()

    right_poly = QPainterPath()
    right_poly.moveTo(ext_pts[0][0], ext_pts[0][1])
    for x, y in ext_pts[1:]:
        right_poly.lineTo(x, y)
    right_poly.lineTo(ext_pts[-1][0] - nx * ext, ext_pts[-1][1] - ny * ext)
    right_poly.lineTo(ext_pts[0][0] - nx * ext, ext_pts[0][1] - ny * ext)
    right_poly.closeSubpath()

    out: List[VectorObject] = []
    for idx, half in enumerate((left_poly, right_poly)):
        piece = base_qp.intersected(half).simplified()
        sps = qpath_to_subpaths(piece)
        if sps and piece.boundingRect().width() > 1.0 and piece.boundingRect().height() > 1.0:
            pbr = piece.boundingRect()
            out.append(VectorObject(
                name=f"{obj.name} Slice {idx + 1}",
                kind="path", layer_id=obj.layer_id,
                appearance=copy.deepcopy(obj.appearance),
                x=pbr.x(), y=pbr.y(), width=pbr.width(), height=pbr.height(),
                subpaths=sps,
            ))
    return out


# ---------------------------------------------------------------------------
# Shaper Tool Gesture Recognition
# ---------------------------------------------------------------------------

def recognize_shaper_gesture(pts: List[Tuple[float, float]]) -> Tuple[str, Dict[str, float]]:
    """Classify a rough freehand stroke into 'line', 'ellipse', 'rect', 'triangle', 'polygon', or 'scribble'."""
    if len(pts) < 4:
        return ("none", {})
    arr = np.array(pts, dtype=np.float64)
    xmin, ymin = arr[:, 0].min(), arr[:, 1].min()
    xmax, ymax = arr[:, 0].max(), arr[:, 1].max()
    w, h = xmax - xmin, ymax - ymin
    diag = math.hypot(w, h)
    if diag < 12.0:
        return ("none", {})

    # Compute total arc length & endpoint distance
    diffs = np.diff(arr, axis=0)
    seg_lens = np.hypot(diffs[:, 0], diffs[:, 1])
    path_len = float(seg_lens.sum())
    end_dist = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])

    # Straight line check
    if end_dist > diag * 0.78 and path_len < end_dist * 1.18:
        return ("line", {"x": pts[0][0], "y": pts[0][1], "w": pts[-1][0] - pts[0][0], "h": pts[-1][1] - pts[0][1]})

    # Scribble check: many direction reversals (for Shaper erase gesture!)
    if len(diffs) >= 6:
        angles = np.arctan2(diffs[:, 1], diffs[:, 0])
        da = np.abs(np.diff(np.unwrap(angles)))
        sharp_turns = int((da > 1.8).sum())
        if sharp_turns >= 3 and end_dist > diag * 0.25 and path_len > (w + h) * 2.2:
            return ("scribble", {"x": xmin, "y": ymin, "w": w, "h": h})

    # Closed shape checks
    cx, cy = (xmin + xmax) * 0.5, (ymin + ymax) * 0.5
    rx, ry = max(1.0, w * 0.5), max(1.0, h * 0.5)
    # Normalized radial distance to ellipse
    ell_r = np.hypot((arr[:, 0] - cx) / rx, (arr[:, 1] - cy) / ry)
    ell_err = float(np.std(ell_r))

    # Simplified polygon vertices
    simp = rdp_simplify(pts, eps=max(6.0, diag * 0.08))
    if len(simp) > 1 and math.hypot(simp[0][0] - simp[-1][0], simp[0][1] - simp[-1][1]) < diag * 0.25:
        simp = simp[:-1]

    if ell_err < 0.145 and len(simp) >= 5:
        return ("ellipse", {"x": xmin, "y": ymin, "w": w, "h": h})
    if len(simp) == 3:
        return ("triangle", {"x": xmin, "y": ymin, "w": w, "h": h})
    if len(simp) == 4:
        return ("rect", {"x": xmin, "y": ymin, "w": w, "h": h})
    if 5 <= len(simp) <= 8:
        return ("polygon", {"x": xmin, "y": ymin, "w": w, "h": h, "sides": len(simp)})
    return ("ellipse" if ell_err < 0.22 else "rect", {"x": xmin, "y": ymin, "w": w, "h": h})


# ---------------------------------------------------------------------------
# Envelope Distort (Warp Presets) & Puppet Warp (Moving Least Squares)
# ---------------------------------------------------------------------------

def apply_warp_to_qpath(qp: QPainterPath, style: str, bend: float = 0.35,
                        h_distort: float = 0.0, v_distort: float = 0.0) -> QPainterPath:
    """Apply Illustrator-style Envelope Warp to a QPainterPath."""
    br = qp.boundingRect()
    if br.width() < 1e-3 or br.height() < 1e-3:
        return qp
    sps = qpath_to_subpaths(qp)
    # Subdivide long straight lines slightly for smooth warp curvature
    fine_sps: List[SubPath] = []
    for sp in sps:
        fine_sps.append(_subdivide_subpath(sp, passes=2))

    cx, cy = br.center().x(), br.center().y()
    hw, hh = br.width() * 0.5, br.height() * 0.5

    def _warp_pt(x: float, y: float) -> Tuple[float, float]:
        u = (x - cx) / max(1e-3, hw)  # -1..1
        v = (y - cy) / max(1e-3, hh)  # -1..1
        nx, ny = u, v
        if style == "arc":
            ny = v - bend * (1.0 - u * u)
        elif style == "arch":
            ny = v - bend * math.cos(u * math.pi * 0.5)
        elif style == "bulge":
            factor = 1.0 + bend * (1.0 - u * u) * (1.0 - v * v)
            nx = u * factor
            ny = v * factor
        elif style == "flag":
            ny = v + bend * math.sin(u * math.pi)
        elif style == "wave":
            ny = v + bend * 0.7 * math.sin(u * math.pi * 2.0)
            nx = u + bend * 0.2 * math.cos(v * math.pi)
        elif style == "fish":
            ny = v * (1.0 + bend * 0.6 * math.cos(u * math.pi * 0.5))
        elif style == "rise":
            ny = v - bend * 0.65 * u
        elif style == "twist":
            r = math.hypot(u, v)
            ang = bend * 1.4 * max(0.0, 1.3 - r)
            ca, sa = math.cos(ang), math.sin(ang)
            nx = u * ca - v * sa
            ny = u * sa + v * ca
        elif style == "squeeze":
            nx = u * (1.0 - bend * 0.5 * (1.0 - v * v))
            ny = v * (1.0 + bend * 0.35 * (1.0 - u * u))
        # Apply horizontal/vertical perspective distortion
        nx *= (1.0 + v_distort * 0.45 * v)
        ny *= (1.0 + h_distort * 0.45 * u)
        return (cx + nx * hw, cy + ny * hh)

    for sp in fine_sps:
        for a in sp.anchors:
            a.x, a.y = _warp_pt(a.x, a.y)
            a.in_x, a.in_y = _warp_pt(a.in_x, a.in_y)
            a.out_x, a.out_y = _warp_pt(a.out_x, a.out_y)
    return subpaths_to_qpath(fine_sps)


def _subdivide_subpath(sp: SubPath, passes: int = 1) -> SubPath:
    cur = copy.deepcopy(sp)
    for _ in range(passes):
        if not cur.anchors or len(cur.anchors) < 2:
            break
        new_anchors: List[AnchorPoint] = []
        n = len(cur.anchors)
        seg_count = n if cur.closed else n - 1
        for i in range(seg_count):
            a = cur.anchors[i]
            b = cur.anchors[(i + 1) % n]
            p0 = (a.x, a.y)
            p1 = (a.out_x, a.out_y)
            p2 = (b.in_x, b.in_y)
            p3 = (b.x, b.y)
            # De Casteljau split at t=0.5
            q0 = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)
            q1 = ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
            q2 = ((p2[0] + p3[0]) * 0.5, (p2[1] + p3[1]) * 0.5)
            r0 = ((q0[0] + q1[0]) * 0.5, (q0[1] + q1[1]) * 0.5)
            r1 = ((q1[0] + q2[0]) * 0.5, (q1[1] + q2[1]) * 0.5)
            mid = ((r0[0] + r1[0]) * 0.5, (r0[1] + r1[1]) * 0.5)
            if not new_anchors:
                a_copy = copy.deepcopy(a)
                a_copy.out_x, a_copy.out_y = q0[0], q0[1]
                new_anchors.append(a_copy)
            else:
                new_anchors[-1].out_x, new_anchors[-1].out_y = q0[0], q0[1]
            new_anchors.append(AnchorPoint(mid[0], mid[1], r0[0], r0[1], r1[0], r1[1], "smooth"))
            if i < seg_count - 1 or not cur.closed:
                b_copy = copy.deepcopy(b)
                b_copy.in_x, b_copy.in_y = q2[0], q2[1]
                new_anchors.append(b_copy)
            else:
                new_anchors[0].in_x, new_anchors[0].in_y = q2[0], q2[1]
        cur = SubPath(anchors=new_anchors, closed=cur.closed)
    return cur


def apply_puppet_warp(base_subpaths: List[SubPath], pins: List[PuppetPin]) -> List[SubPath]:
    """Deform base_subpaths smoothly using Moving Least Squares (inverse-distance weighted) puppet pins."""
    if not pins or not base_subpaths:
        return copy.deepcopy(base_subpaths)
    p_orig = np.array([[p.orig_x, p.orig_y] for p in pins], dtype=np.float64)
    p_curr = np.array([[p.x, p.y] for p in pins], dtype=np.float64)
    deltas = p_curr - p_orig

    def _deform(x: float, y: float) -> Tuple[float, float]:
        if len(pins) == 1:
            dx, dy = deltas[0]
            ang = math.radians(pins[0].rotation)
            rx, ry = x - pins[0].orig_x, y - pins[0].orig_y
            ca, sa = math.cos(ang), math.sin(ang)
            return (pins[0].x + rx * ca - ry * sa, pins[0].y + rx * sa + ry * ca)
        v = np.array([x, y], dtype=np.float64)
        d2 = np.sum((p_orig - v) ** 2, axis=1) + 400.0
        w = 1.0 / (d2 ** 1.15)
        w /= w.sum()
        # Similarity MLS approximation
        p_star = np.sum(w[:, None] * p_orig, axis=0)
        q_star = np.sum(w[:, None] * p_curr, axis=0)
        p_hat = p_orig - p_star
        q_hat = p_curr - q_star
        mu = float(np.sum(w * np.sum(p_hat ** 2, axis=1))) + 1e-6
        vp = v - p_star
        # Accumulate similarity transform
        a = float(np.sum(w * (p_hat[:, 0] * q_hat[:, 0] + p_hat[:, 1] * q_hat[:, 1]))) / mu
        b = float(np.sum(w * (p_hat[:, 0] * q_hat[:, 1] - p_hat[:, 1] * q_hat[:, 0]))) / mu
        # Normalize slight scale explosion for cleaner vector shapes
        s = math.hypot(a, b)
        if s > 1.8:
            a *= 1.8 / s
            b *= 1.8 / s
        nx = q_star[0] + a * vp[0] - b * vp[1]
        ny = q_star[1] + b * vp[0] + a * vp[1]
        return (float(nx), float(ny))

    out = copy.deepcopy(base_subpaths)
    for sp in out:
        for a in sp.anchors:
            a.x, a.y = _deform(a.x, a.y)
            a.in_x, a.in_y = _deform(a.in_x, a.in_y)
            a.out_x, a.out_y = _deform(a.out_x, a.out_y)
    return out


# ---------------------------------------------------------------------------
# Perspective Grid 1 / 2 / 3-Point Projection
# ---------------------------------------------------------------------------

def project_rect_to_perspective(rect: QRectF, persp: PerspectiveGridState) -> SubPath:
    """Project a dragged 2D rectangle onto the active 1-, 2-, or 3-point perspective plane."""
    plane = persp.active_plane
    if not persp.visible or plane == "none":
        return qpath_to_subpaths(_rect_qpath(rect))[0]

    x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    hy = persp.horizon_y

    if plane == "left":
        vp_x = persp.vp_left_x if persp.points >= 2 else persp.vp_center_x
        vp = (vp_x, hy)
        # Right vertical edge is near edge (x1, y0)-(x1, y1); left edge converges to vp
        t = max(0.05, min(0.85, (x1 - x0) / max(40.0, abs(x1 - vp[0]))))
        tl = (x1 + (vp[0] - x1) * t, y0 + (vp[1] - y0) * t)
        bl = (x1 + (vp[0] - x1) * t, y1 + (vp[1] - y1) * t)
        tr_p = (x1, y0)
        br_p = (x1, y1)
        if persp.points == 3:
            # Vertical edges also converge slightly toward 3rd VP below
            vp3 = (persp.vp_center_x, persp.vp_third_y)
            f = 0.14
            bl = (bl[0] + (vp3[0] - bl[0]) * f, bl[1] + (vp3[1] - bl[1]) * f)
            br_p = (br_p[0] + (vp3[0] - br_p[0]) * f, br_p[1] + (vp3[1] - br_p[1]) * f)
        pts = [tl, tr_p, br_p, bl]
    elif plane == "right":
        vp_x = persp.vp_right_x if persp.points >= 2 else persp.vp_center_x
        vp = (vp_x, hy)
        t = max(0.05, min(0.85, (x1 - x0) / max(40.0, abs(vp[0] - x0))))
        tl = (x0, y0)
        bl = (x0, y1)
        tr_p = (x0 + (vp[0] - x0) * t, y0 + (vp[1] - y0) * t)
        br_p = (x0 + (vp[0] - x0) * t, y1 + (vp[1] - y1) * t)
        if persp.points == 3:
            vp3 = (persp.vp_center_x, persp.vp_third_y)
            f = 0.14
            bl = (bl[0] + (vp3[0] - bl[0]) * f, bl[1] + (vp3[1] - bl[1]) * f)
            br_p = (br_p[0] + (vp3[0] - br_p[0]) * f, br_p[1] + (vp3[1] - br_p[1]) * f)
        pts = [tl, tr_p, br_p, bl]
    else:  # horizontal ground plane
        vpl = (persp.vp_left_x if persp.points >= 2 else persp.vp_center_x, hy)
        vpr = (persp.vp_right_x if persp.points >= 2 else persp.vp_center_x, hy)
        cx = (x0 + x1) * 0.5
        t_l = max(0.08, min(0.55, (x1 - x0) / max(60.0, abs(cx - vpl[0])) * 0.6))
        t_r = max(0.08, min(0.55, (x1 - x0) / max(60.0, abs(vpr[0] - cx)) * 0.6))
        front = (cx, y1)
        left_c = (front[0] + (vpl[0] - front[0]) * t_l, front[1] + (vpl[1] - front[1]) * t_l)
        right_c = (front[0] + (vpr[0] - front[0]) * t_r, front[1] + (vpr[1] - front[1]) * t_r)
        back = (left_c[0] + (right_c[0] - front[0]) * 0.78, left_c[1] + (right_c[1] - front[1]) * 0.78)
        pts = [front, right_c, back, left_c]

    return SubPath(anchors=[AnchorPoint(p[0], p[1]) for p in pts], closed=True)


def _rect_qpath(r: QRectF) -> QPainterPath:
    qp = QPainterPath()
    qp.addRect(r)
    return qp


# ---------------------------------------------------------------------------
# Blend Tool Interpolation
# ---------------------------------------------------------------------------

def interpolate_color(c1: Color, c2: Color, t: float) -> Color:
    return Color(
        r=int(round(c1.r + (c2.r - c1.r) * t)),
        g=int(round(c1.g + (c2.g - c1.g) * t)),
        b=int(round(c1.b + (c2.b - c1.b) * t)),
        a=int(round(c1.a + (c2.a - c1.a) * t)),
    )


def generate_blend_steps(obj_a: VectorObject, obj_b: VectorObject, steps: int,
                         doc: Optional[Document] = None) -> List[Tuple[QPainterPath, Appearance]]:
    """Interpolate both geometry (resampled contour) and appearance between two objects."""
    pa = object_to_qpath(obj_a, doc)
    pb = object_to_qpath(obj_b, doc)
    n_pts = 64
    pts_a = [pa.pointAtPercent(i / n_pts) for i in range(n_pts)] if not pa.isEmpty() else []
    pts_b = [pb.pointAtPercent(i / n_pts) for i in range(n_pts)] if not pb.isEmpty() else []
    if not pts_a or not pts_b:
        return []

    out: List[Tuple[QPainterPath, Appearance]] = []
    total = max(1, steps)
    for s in range(1, total + 1):
        t = s / (total + 1)
        qp = QPainterPath()
        for i in range(n_pts):
            x = pts_a[i].x() + (pts_b[i].x() - pts_a[i].x()) * t
            y = pts_a[i].y() + (pts_b[i].y() - pts_a[i].y()) * t
            if i == 0:
                qp.moveTo(x, y)
            else:
                qp.lineTo(x, y)
        qp.closeSubpath()
        app = copy.deepcopy(obj_a.appearance)
        app.opacity = obj_a.appearance.opacity + (obj_b.appearance.opacity - obj_a.appearance.opacity) * t
        if app.primary_fill.fill_type == "solid" and obj_b.appearance.primary_fill.fill_type == "solid":
            app.primary_fill.color = interpolate_color(
                obj_a.appearance.primary_fill.color, obj_b.appearance.primary_fill.color, t
            )
        if app.primary_stroke.stroke_type == "solid" and obj_b.appearance.primary_stroke.stroke_type == "solid":
            app.primary_stroke.color = interpolate_color(
                obj_a.appearance.primary_stroke.color, obj_b.appearance.primary_stroke.color, t
            )
            app.primary_stroke.width = (
                obj_a.appearance.primary_stroke.width
                + (obj_b.appearance.primary_stroke.width - obj_a.appearance.primary_stroke.width) * t
            )
        out.append((qp, app))
    return out


# ---------------------------------------------------------------------------
# Roughen / ZigZag Live Effect
# ---------------------------------------------------------------------------

def apply_roughen_to_qpath(qp: QPainterPath, amount: float = 6.0, detail: int = 24, seed: int = 42) -> QPainterPath:
    total = qp.length()
    if total < 2.0:
        return qp
    rng = np.random.default_rng(seed)
    steps = max(8, min(220, int(detail * max(1.0, total / 180.0))))
    out = QPainterPath()
    for i in range(steps + 1):
        t = i / steps
        pct = max(0.0, min(1.0, qp.percentAtLength(t * total)))
        pt = qp.pointAtPercent(pct)
        ang = math.radians(-qp.angleAtPercent(pct))
        nx, ny = -math.sin(ang), math.cos(ang)
        jitter = float(rng.uniform(-amount, amount))
        px, py = pt.x() + nx * jitter, pt.y() + ny * jitter
        if i == 0:
            out.moveTo(px, py)
        else:
            out.lineTo(px, py)
    return out
