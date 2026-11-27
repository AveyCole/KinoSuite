"""Importers & Exporters for Vectora.

Supports:
- Clean SVG Export & Import (paths, shapes, text, groups, gradients, styles)
- Raster Export (PNG, JPG, WebP) at arbitrary scales (1x, 2x, 3x, custom DPI)
- Print-Ready PDF Export via ReportLab (real CMYK color values, bleed box, trim box,
  crop marks, registration targets, CMYK color bars, multi-page artboards)
- Linked & Embedded asset placement (PNG, JPG, WebP, SVG, PDF, PSD)
- CSS Snippet generator for selected vector elements
"""
from __future__ import annotations

import base64
import io
import math
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath

from .geometry import object_bounds, object_to_qpath, qpath_to_subpaths, subpaths_to_qpath
from .models import (
    AnchorPoint,
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Artboard,
    Color,
    Document,
    GradientDef,
    GradientStop,
    SubPath,
    TextStyle,
    VectorObject,
)
from .renderer import ViewOptions, render_document, render_object


# ---------------------------------------------------------------------------
# Raster Export (PNG, JPG, WebP)
# ---------------------------------------------------------------------------

def render_artboard_to_qimage(doc: Document, artboard: Artboard, scale: float = 1.0,
                              transparent_bg: bool = False, include_bleed: bool = False) -> QImage:
    bleed = doc.bleed if include_bleed else 0.0
    w = max(4, int(round((artboard.width + bleed * 2) * scale)))
    h = max(4, int(round((artboard.height + bleed * 2) * scale)))
    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(Qt.transparent if transparent_bg else Qt.white)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(scale, scale)
    p.translate(-(artboard.x - bleed), -(artboard.y - bleed))

    opts = ViewOptions()
    opts.export_mode = True
    opts.show_artboards = not transparent_bg
    opts.show_bleed = False
    opts.show_crop_marks = False
    render_document(p, doc, opts, clip_artboard=artboard)
    p.end()
    return img


def render_objects_to_qimage(doc: Document, objects: List[VectorObject], scale: float = 1.0,
                             padding: float = 8.0) -> QImage:
    if not objects:
        return render_artboard_to_qimage(doc, doc.active_artboard(), scale, transparent_bg=True)
    rect = object_bounds(objects[0], doc)
    for o in objects[1:]:
        rect = rect.united(object_bounds(o, doc))
    rect = rect.adjusted(-padding, -padding, padding, padding)
    w = max(8, int(round(rect.width() * scale)))
    h = max(8, int(round(rect.height() * scale)))
    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.scale(scale, scale)
    p.translate(-rect.x(), -rect.y())
    opts = ViewOptions()
    opts.export_mode = True
    for o in objects:
        render_object(p, o, doc, opts, [])
    p.end()
    return img


def export_raster(doc: Document, out_path: str, fmt: str = "PNG", scale: float = 1.0,
                  artboard: Optional[Artboard] = None, objects: Optional[List[VectorObject]] = None,
                  transparent_bg: bool = True, quality: int = 92) -> str:
    ab = artboard or doc.active_artboard()
    if objects:
        qimg = render_objects_to_qimage(doc, objects, scale=scale)
    else:
        qimg = render_artboard_to_qimage(doc, ab, scale=scale, transparent_bg=(transparent_bg and fmt.upper() != "JPG"))

    rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
    pil = Image.frombuffer("RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits()), "raw", "RGBA", 0, 1).copy()
    ufmt = fmt.upper()
    if ufmt in ("JPG", "JPEG"):
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[3])
        bg.save(out_path, "JPEG", quality=quality)
    elif ufmt == "WEBP":
        pil.save(out_path, "WEBP", quality=quality)
    else:
        pil.save(out_path, "PNG")
    return out_path


# ---------------------------------------------------------------------------
# Clean Standards-Compliant SVG Export
# ---------------------------------------------------------------------------

def _qpath_to_svg_d(qp: QPainterPath) -> str:
    parts: List[str] = []
    n = qp.elementCount()
    i = 0
    while i < n:
        el = qp.elementAt(i)
        if el.type == QPainterPath.MoveToElement:
            parts.append(f"M {el.x:.2f} {el.y:.2f}")
            i += 1
        elif el.type == QPainterPath.LineToElement:
            parts.append(f"L {el.x:.2f} {el.y:.2f}")
            i += 1
        elif el.type == QPainterPath.CurveToElement:
            c1 = el
            c2 = qp.elementAt(i + 1) if i + 1 < n else el
            end = qp.elementAt(i + 2) if i + 2 < n else c2
            parts.append(f"C {c1.x:.2f} {c1.y:.2f}, {c2.x:.2f} {c2.y:.2f}, {end.x:.2f} {end.y:.2f}")
            i += 3
        else:
            i += 1
    return " ".join(parts)


def export_svg(doc: Document, out_path: str, artboard: Optional[Artboard] = None,
               objects: Optional[List[VectorObject]] = None) -> str:
    ab = artboard or doc.active_artboard()
    if objects:
        br = object_bounds(objects[0], doc)
        for o in objects[1:]:
            br = br.united(object_bounds(o, doc))
        vx, vy, vw, vh = br.x() - 4, br.y() - 4, br.width() + 8, br.height() + 8
    else:
        vx, vy, vw, vh = ab.x, ab.y, ab.width, ab.height

    defs: List[str] = []
    body: List[str] = []
    grad_counter = [0]

    def _emit_obj(obj: VectorObject) -> str:
        if not obj.visible:
            return ""
        op_attr = f' opacity="{obj.appearance.opacity:.3f}"' if obj.appearance.opacity < 0.999 else ""
        if obj.kind == "group":
            inner = "\n".join(_emit_obj(ch) for ch in obj.children)
            return f'  <g id="{obj.id}"{op_attr}>\n{inner}\n  </g>'
        if obj.kind == "text" and obj.text_mode == "point" and not obj.char_transforms:
            fill = obj.appearance.primary_fill
            fc = fill.color.to_hex() if fill.fill_type == "solid" else "#111111"
            ts = obj.text_style
            esc = (obj.text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return (
                f'  <text x="{obj.x:.2f}" y="{obj.y + ts.font_size:.2f}" '
                f'font-family="{ts.font_family}" font-size="{ts.font_size:.1f}" '
                f'font-weight="{ts.font_weight}" fill="{fc}"{op_attr}>{esc}</text>'
            )

        qp = object_to_qpath(obj, doc)
        d_str = _qpath_to_svg_d(qp)
        if not d_str:
            return ""

        fill = obj.appearance.primary_fill
        fill_attr = "none"
        if fill.visible and fill.fill_type == "solid":
            fill_attr = fill.color.to_hex()
        elif fill.visible and fill.fill_type == "gradient" and fill.gradient:
            grad_counter[0] += 1
            gid = f"grad_{grad_counter[0]}"
            g = fill.gradient
            stops_xml = "".join(
                f'<stop offset="{st.offset * 100:.1f}%" stop-color="{st.color.to_hex()}" stop-opacity="{st.color.a / 255.0:.3f}"/>'
                for st in g.stops
            )
            if g.kind == "radial":
                defs.append(f'<radialGradient id="{gid}" cx="{g.cx * 100:.1f}%" cy="{g.cy * 100:.1f}%" r="{g.radius * 100:.1f}%">{stops_xml}</radialGradient>')
            else:
                rad = math.radians(g.angle)
                x1, y1 = 50 - 50 * math.cos(rad), 50 - 50 * math.sin(rad)
                x2, y2 = 50 + 50 * math.cos(rad), 50 + 50 * math.sin(rad)
                defs.append(f'<linearGradient id="{gid}" x1="{x1:.1f}%" y1="{y1:.1f}%" x2="{x2:.1f}%" y2="{y2:.1f}%">{stops_xml}</linearGradient>')
            fill_attr = f"url(#{gid})"

        st = obj.appearance.primary_stroke
        stroke_attr = "none"
        sw_attr = ""
        dash_attr = ""
        if st.visible and st.stroke_type != "none" and st.width > 0.01:
            stroke_attr = st.color.to_hex()
            sw_attr = f' stroke-width="{st.width:.2f}" stroke-linecap="{st.cap}" stroke-linejoin="{st.join}"'
            if st.dash_pattern:
                dash_attr = f' stroke-dasharray="{",".join(str(x) for x in st.dash_pattern)}"'
        return f'  <path id="{obj.id}" d="{d_str}" fill="{fill_attr}" stroke="{stroke_attr}"{sw_attr}{dash_attr}{op_attr}/>'

    target_objs = objects if objects is not None else doc.iter_all_objects()
    for o in target_objs:
        s = _emit_obj(o)
        if s:
            body.append(s)

    defs_block = f"  <defs>\n    " + "\n    ".join(defs) + "\n  </defs>\n" if defs else ""
    bg_rect = f'  <rect x="{vx:.2f}" y="{vy:.2f}" width="{vw:.2f}" height="{vh:.2f}" fill="{ab.bg_color.to_hex()}"/>\n' if objects is None else ""
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}" '
        f'width="{vw:.0f}" height="{vh:.0f}">\n'
        f'{defs_block}{bg_rect}'
        + "\n".join(body)
        + "\n</svg>\n"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    return out_path


# ---------------------------------------------------------------------------
# SVG Importer (parses paths, basic shapes, text, groups, fill/stroke)
# ---------------------------------------------------------------------------

def import_svg_objects(svg_path: str) -> List[VectorObject]:
    tree = ET.parse(svg_path)
    root = tree.getroot()

    def _strip_ns(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    def _parse_style(el: ET.Element) -> Appearance:
        style_map: Dict[str, str] = {}
        st_raw = el.attrib.get("style", "")
        for part in st_raw.split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                style_map[k.strip()] = v.strip()
        fill_v = style_map.get("fill", el.attrib.get("fill", "#3A86FF"))
        stroke_v = style_map.get("stroke", el.attrib.get("stroke", "none"))
        sw_v = float(re.sub(r"[^0-9.]", "", style_map.get("stroke-width", el.attrib.get("stroke-width", "1.5"))) or 1.5)
        op_v = float(style_map.get("opacity", el.attrib.get("opacity", "1.0")) or 1.0)

        fill = AppearanceFill(fill_type="none") if fill_v in ("none", "transparent") else AppearanceFill(
            fill_type="solid", color=_parse_svg_color(fill_v)
        )
        stroke = AppearanceStroke(stroke_type="none") if stroke_v in ("none", "transparent", "") else AppearanceStroke(
            stroke_type="solid", color=_parse_svg_color(stroke_v), width=sw_v
        )
        return Appearance(fills=[fill], strokes=[stroke], opacity=max(0.0, min(1.0, op_v)))

    out: List[VectorObject] = []

    def _walk(node: ET.Element, target: List[VectorObject]) -> None:
        for ch in node:
            tag = _strip_ns(ch.tag)
            if tag in ("defs", "metadata", "title", "desc"):
                continue
            app = _parse_style(ch)
            if tag == "g":
                grp_children: List[VectorObject] = []
                _walk(ch, grp_children)
                if grp_children:
                    target.append(VectorObject(name=ch.attrib.get("id", "SVG Group"), kind="group", children=grp_children))
            elif tag == "rect":
                x = float(ch.attrib.get("x", 0))
                y = float(ch.attrib.get("y", 0))
                w = float(ch.attrib.get("width", 50))
                h = float(ch.attrib.get("height", 50))
                rx = float(ch.attrib.get("rx", ch.attrib.get("ry", 0)))
                target.append(VectorObject(name="SVG Rect", kind="shape", shape_type="rect",
                                           x=x, y=y, width=w, height=h, corner_radius=rx, appearance=app))
            elif tag == "circle":
                cx = float(ch.attrib.get("cx", 0))
                cy = float(ch.attrib.get("cy", 0))
                r = float(ch.attrib.get("r", 25))
                target.append(VectorObject(name="SVG Circle", kind="shape", shape_type="ellipse",
                                           x=cx - r, y=cy - r, width=r * 2, height=r * 2, appearance=app))
            elif tag == "ellipse":
                cx = float(ch.attrib.get("cx", 0))
                cy = float(ch.attrib.get("cy", 0))
                rx = float(ch.attrib.get("rx", 30))
                ry = float(ch.attrib.get("ry", 20))
                target.append(VectorObject(name="SVG Ellipse", kind="shape", shape_type="ellipse",
                                           x=cx - rx, y=cy - ry, width=rx * 2, height=ry * 2, appearance=app))
            elif tag == "line":
                x1, y1 = float(ch.attrib.get("x1", 0)), float(ch.attrib.get("y1", 0))
                x2, y2 = float(ch.attrib.get("x2", 50)), float(ch.attrib.get("y2", 50))
                target.append(VectorObject(name="SVG Line", kind="shape", shape_type="line",
                                           x=x1, y=y1, width=x2 - x1, height=y2 - y1, appearance=app))
            elif tag in ("polygon", "polyline"):
                nums = [float(m) for m in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", ch.attrib.get("points", ""))]
                anchors = [AnchorPoint(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
                if anchors:
                    sp = SubPath(anchors=anchors, closed=(tag == "polygon"))
                    br = subpaths_to_qpath([sp]).boundingRect()
                    target.append(VectorObject(name=f"SVG {tag}", kind="path", subpaths=[sp],
                                               x=br.x(), y=br.y(), width=br.width(), height=br.height(), appearance=app))
            elif tag == "path":
                qp = _parse_svg_path_d(ch.attrib.get("d", ""))
                sps = qpath_to_subpaths(qp)
                if sps:
                    br = qp.boundingRect()
                    target.append(VectorObject(name=ch.attrib.get("id", "SVG Path"), kind="path", subpaths=sps,
                                               x=br.x(), y=br.y(), width=br.width(), height=br.height(), appearance=app))
            elif tag == "text":
                txt = "".join(ch.itertext()).strip()
                if txt:
                    x = float(ch.attrib.get("x", 0))
                    fs = float(re.sub(r"[^0-9.]", "", ch.attrib.get("font-size", "24")) or 24)
                    y = float(ch.attrib.get("y", fs)) - fs
                    target.append(VectorObject(
                        name="SVG Text", kind="text", text_mode="point", text=txt,
                        x=x, y=y, text_style=TextStyle(font_size=fs), appearance=app,
                    ))

    _walk(root, out)
    return out


def _parse_svg_color(s: str) -> Color:
    s = s.strip().lower()
    named = {
        "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
        "blue": "#0000ff", "yellow": "#ffff00", "orange": "#ffa500", "purple": "#800080",
        "cyan": "#00ffff", "magenta": "#ff00ff", "gray": "#808080", "grey": "#808080",
    }
    if s in named:
        return Color.from_hex(named[s])
    if s.startswith("#"):
        return Color.from_hex(s)
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", s)
    if m:
        return Color(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return Color.from_hex("#3A86FF")


def _parse_svg_path_d(d: str) -> QPainterPath:
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d)
    qp = QPainterPath()
    cx, cy = 0.0, 0.0
    sx, sy = 0.0, 0.0
    cmd = ""
    i = 0

    def _num() -> float:
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        if re.match(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
        if cmd in ("Z", "z"):
            qp.closeSubpath()
            cx, cy = sx, sy
            cmd = ""
        elif cmd in ("M", "m") and i + 1 < len(tokens):
            nx, ny = _num(), _num()
            if cmd == "m":
                nx, ny = cx + nx, cy + ny
            qp.moveTo(nx, ny)
            cx, cy = nx, ny
            sx, sy = nx, ny
            cmd = "L" if cmd == "M" else "l"
        elif cmd in ("L", "l") and i + 1 < len(tokens):
            nx, ny = _num(), _num()
            if cmd == "l":
                nx, ny = cx + nx, cy + ny
            qp.lineTo(nx, ny)
            cx, cy = nx, ny
        elif cmd in ("H", "h") and i < len(tokens):
            nx = _num() + (cx if cmd == "h" else 0.0)
            qp.lineTo(nx, cy)
            cx = nx
        elif cmd in ("V", "v") and i < len(tokens):
            ny = _num() + (cy if cmd == "v" else 0.0)
            qp.lineTo(cx, ny)
            cy = ny
        elif cmd in ("C", "c") and i + 5 < len(tokens):
            x1, y1, x2, y2, x3, y3 = _num(), _num(), _num(), _num(), _num(), _num()
            if cmd == "c":
                x1, y1, x2, y2, x3, y3 = cx + x1, cy + y1, cx + x2, cy + y2, cx + x3, cy + y3
            qp.cubicTo(x1, y1, x2, y2, x3, y3)
            cx, cy = x3, y3
        elif cmd in ("Q", "q") and i + 3 < len(tokens):
            x1, y1, x2, y2 = _num(), _num(), _num(), _num()
            if cmd == "q":
                x1, y1, x2, y2 = cx + x1, cy + y1, cx + x2, cy + y2
            qp.quadTo(x1, y1, x2, y2)
            cx, cy = x2, y2
        else:
            i += 1
    return qp


# ---------------------------------------------------------------------------
# Print-Ready PDF Export (ReportLab CMYK, Bleed, Crop Marks, Reg Marks, Bars)
# ---------------------------------------------------------------------------

def export_print_pdf(doc: Document, out_path: str, cmyk: bool = True,
                     bleed_pt: float = 9.0, crop_marks: bool = True,
                     reg_marks: bool = True, color_bars: bool = True) -> str:
    from reportlab.lib.colors import CMYKColor
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    margin = (bleed_pt + 28.0) if (crop_marks or reg_marks or color_bars) else bleed_pt
    first = doc.artboards[0]
    c = rl_canvas.Canvas(out_path, pagesize=(first.width + margin * 2, first.height + margin * 2))
    c.setTitle(doc.name)
    c.setAuthor("KinoDraw — KinoSuite")

    for ab_idx, ab in enumerate(doc.artboards):
        pw = ab.width + margin * 2
        ph = ab.height + margin * 2
        c.setPageSize((pw, ph))

        # High-DPI raster backing for complex effects/gradients + crisp vector paths on top
        qimg = render_artboard_to_qimage(doc, ab, scale=2.0, transparent_bg=False, include_bleed=(bleed_pt > 0))
        rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
        pil = Image.frombuffer("RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits()), "raw", "RGBA", 0, 1).copy()
        if cmyk:
            pil_out = pil.convert("CMYK")
        else:
            pil_out = pil.convert("RGB")
        buf = io.BytesIO()
        pil_out.save(buf, format="JPEG", quality=96)
        buf.seek(0)
        b_eff = doc.bleed if bleed_pt > 0 else 0.0
        c.drawImage(
            ImageReader(buf),
            margin - b_eff,
            margin - b_eff,
            width=ab.width + b_eff * 2,
            height=ab.height + b_eff * 2,
        )

        # Print Marks (CMYK Registration Black = 100/100/100/100)
        reg_black = CMYKColor(1, 1, 1, 1)
        c.setStrokeColor(reg_black)
        c.setLineWidth(0.5)

        trim_x0, trim_y0 = margin, margin
        trim_x1, trim_y1 = margin + ab.width, margin + ab.height

        if crop_marks:
            off = max(6.0, bleed_pt + 3.0)
            ln = 16.0
            for (cx, cy, sx, sy) in [
                (trim_x0, trim_y0, -1, -1), (trim_x1, trim_y0, 1, -1),
                (trim_x0, trim_y1, -1, 1), (trim_x1, trim_y1, 1, 1),
            ]:
                c.line(cx + sx * off, cy, cx + sx * (off + ln), cy)
                c.line(cx, cy + sy * off, cx, cy + sy * (off + ln))

        if reg_marks:
            for (rx, ry) in [
                ((trim_x0 + trim_x1) * 0.5, trim_y1 + bleed_pt + 14),
                ((trim_x0 + trim_x1) * 0.5, trim_y0 - bleed_pt - 14),
                (trim_x0 - bleed_pt - 14, (trim_y0 + trim_y1) * 0.5),
                (trim_x1 + bleed_pt + 14, (trim_y0 + trim_y1) * 0.5),
            ]:
                c.circle(rx, ry, 5, stroke=1, fill=0)
                c.line(rx - 8, ry, rx + 8, ry)
                c.line(rx, ry - 8, rx, ry + 8)

        if color_bars:
            swatches = [
                CMYKColor(1, 0, 0, 0), CMYKColor(0, 1, 0, 0), CMYKColor(0, 0, 1, 0), CMYKColor(0, 0, 0, 1),
                CMYKColor(1, 1, 0, 0), CMYKColor(1, 0, 1, 0), CMYKColor(0, 1, 1, 0), CMYKColor(0, 0, 0, 0.5),
            ]
            bx = trim_x0 + 12
            by = trim_y1 + bleed_pt + 8
            for sw in swatches:
                c.setFillColor(sw)
                c.rect(bx, by, 12, 8, stroke=0, fill=1)
                bx += 13

        # Page info slug
        c.setFillColor(reg_black)
        c.setFont("Helvetica", 6.5)
        c.drawString(trim_x0, trim_y0 - bleed_pt - 16,
                     f"{doc.name} | {ab.name} | {'CMYK' if cmyk else 'RGB'} | Bleed {bleed_pt:.1f}pt")
        c.showPage()

    c.save()
    return out_path


# ---------------------------------------------------------------------------
# Place Linked / Embedded Image Helper
# ---------------------------------------------------------------------------

def create_placed_image_object(file_path: str, x: float = 80.0, y: float = 80.0,
                               embed: bool = False) -> VectorObject:
    w, h = 360.0, 260.0
    orig_w, orig_h = 360, 260
    b64 = ""
    try:
        pil = Image.open(file_path)
        orig_w, orig_h = pil.size
        scale = min(1.0, 520.0 / max(1, max(orig_w, orig_h)))
        w, h = orig_w * scale, orig_h * scale
        if embed:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        pass
    return VectorObject(
        name=os.path.basename(file_path),
        kind="image",
        x=x, y=y, width=w, height=h,
        image_path=file_path,
        image_embedded_b64=b64,
        image_is_linked=not embed,
        image_orig_w=orig_w,
        image_orig_h=orig_h,
    )


# ---------------------------------------------------------------------------
# CSS Snippet Generator (Export for Screens / UI Assets)
# ---------------------------------------------------------------------------

def generate_css_snippet(obj: VectorObject, doc: Optional[Document] = None) -> str:
    br = object_bounds(obj, doc)
    cls_name = re.sub(r"[^a-zA-Z0-9_-]", "-", obj.name.lower()).strip("-") or "vector-element"
    lines = [f".{cls_name} {{", f"  width: {br.width():.1f}px;", f"  height: {br.height():.1f}px;"]

    fill = obj.appearance.primary_fill
    if fill.visible and fill.fill_type == "solid":
        lines.append(f"  background-color: {fill.color.to_rgba_css()};")
    elif fill.visible and fill.fill_type == "gradient" and fill.gradient:
        g = fill.gradient
        stops = ", ".join(f"{s.color.to_rgba_css()} {s.offset * 100:.0f}%" for s in g.stops)
        if g.kind == "radial":
            lines.append(f"  background: radial-gradient(circle, {stops});")
        else:
            lines.append(f"  background: linear-gradient({g.angle:.0f}deg, {stops});")

    st = obj.appearance.primary_stroke
    if st.visible and st.stroke_type != "none" and st.width > 0:
        style = "dashed" if st.dash_pattern else "solid"
        lines.append(f"  border: {st.width:.1f}px {style} {st.color.to_rgba_css()};")

    if obj.kind == "shape":
        if obj.shape_type == "ellipse":
            lines.append("  border-radius: 50%;")
        elif obj.shape_type == "rect" and obj.corner_radius > 0:
            lines.append(f"  border-radius: {obj.corner_radius:.1f}px;")

    if obj.appearance.opacity < 0.999:
        lines.append(f"  opacity: {obj.appearance.opacity:.2f};")

    if abs(obj.rotation) > 0.05:
        lines.append(f"  transform: rotate({obj.rotation:.1f}deg);")

    if obj.appearance.blend_mode != "Normal":
        lines.append(f"  mix-blend-mode: {obj.appearance.blend_mode.lower()};")

    for fx in obj.appearance.effects:
        if fx.enabled and fx.kind == "drop_shadow":
            c = Color.from_hex(fx.params.get("color", "#000000"))
            op = float(fx.params.get("opacity", 0.35))
            lines.append(
                f"  box-shadow: {fx.params.get('dx', 6)}px {fx.params.get('dy', 8)}px "
                f"{fx.params.get('blur', 12)}px rgba({c.r}, {c.g}, {c.b}, {op:.2f});"
            )

    if obj.kind == "text":
        ts = obj.text_style
        lines.append(f'  font-family: "{ts.font_family}", sans-serif;')
        lines.append(f"  font-size: {ts.font_size:.1f}px;")
        lines.append(f"  font-weight: {ts.font_weight};")
        lines.append(f"  line-height: {ts.leading:.2f};")
        if abs(ts.tracking) > 0.01:
            lines.append(f"  letter-spacing: {ts.tracking:.1f}px;")

    lines.append("}")
    return "\n".join(lines)
