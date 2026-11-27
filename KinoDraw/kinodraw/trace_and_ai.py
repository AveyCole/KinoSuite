"""Image Trace (OpenCV + Bezier fitting) and Generative Vector / Pattern / Recolor engine for KinoDraw."""
from __future__ import annotations

import copy
import math
import random
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtGui import QImage

from .geometry import fit_catmull_rom_subpath, rdp_simplify, subpaths_to_qpath
from .models import (
    AnchorPoint,
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Color,
    Document,
    GradientDef,
    GradientStop,
    PatternDef,
    SubPath,
    TextStyle,
    VectorObject,
)
from .renderer import load_object_qimage


# ---------------------------------------------------------------------------
# Image Trace & AI-Assisted Sketch Tracing (OpenCV K-Means + Contours + Bezier)
# ---------------------------------------------------------------------------

TRACE_PRESETS: Dict[str, Dict] = {
    "High Fidelity Photo": {"mode": "color", "colors": 14, "threshold": 128, "simplify": 1.6, "min_area": 18, "ignore_white": False, "sketch_ai": False},
    "16 Colors": {"mode": "color", "colors": 16, "threshold": 128, "simplify": 2.0, "min_area": 24, "ignore_white": True, "sketch_ai": False},
    "6 Colors": {"mode": "color", "colors": 6, "threshold": 128, "simplify": 2.4, "min_area": 30, "ignore_white": True, "sketch_ai": False},
    "3 Colors": {"mode": "color", "colors": 3, "threshold": 128, "simplify": 2.8, "min_area": 35, "ignore_white": True, "sketch_ai": False},
    "Shades of Gray": {"mode": "gray", "colors": 6, "threshold": 128, "simplify": 2.2, "min_area": 28, "ignore_white": True, "sketch_ai": False},
    "Black & White Logo": {"mode": "bw", "colors": 2, "threshold": 135, "simplify": 2.0, "min_area": 22, "ignore_white": True, "sketch_ai": False},
    "Sketched Art (AI-Assisted)": {"mode": "sketch", "colors": 2, "threshold": 160, "simplify": 1.8, "min_area": 14, "ignore_white": True, "sketch_ai": True},
    "Line Art": {"mode": "line", "colors": 2, "threshold": 140, "simplify": 1.5, "min_area": 10, "ignore_white": True, "sketch_ai": True},
    "Silhouettes": {"mode": "bw", "colors": 2, "threshold": 165, "simplify": 3.0, "min_area": 45, "ignore_white": True, "sketch_ai": False},
}


def trace_image_object(
    img_obj: VectorObject,
    mode: str = "color",
    colors: int = 6,
    threshold: int = 128,
    simplify: float = 2.2,
    min_area: int = 24,
    ignore_white: bool = True,
    smooth_curves: bool = True,
    sketch_ai: bool = False,
) -> Optional[VectorObject]:
    """Vectorize a placed raster ImageObject into a grouped editable VectorObject."""
    qimg = load_object_qimage(img_obj)
    if qimg is None or qimg.isNull():
        return None

    rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
    w, h = rgba.width(), rgba.height()
    arr = np.frombuffer(bytes(rgba.constBits()), dtype=np.uint8).reshape((h, w, 4)).copy()

    # Composite transparent pixels onto white for tracing
    alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
    rgb = (arr[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)

    # Downscale very large images for responsive tracing
    max_dim = 512
    scale_down = min(1.0, max_dim / max(w, h))
    if scale_down < 1.0:
        tw, th = max(16, int(w * scale_down)), max(16, int(h * scale_down))
        rgb_work = cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_AREA)
    else:
        tw, th = w, h
        rgb_work = rgb

    sx = img_obj.width / max(1.0, tw)
    sy = img_obj.height / max(1.0, th)
    ox, oy = img_obj.x, img_obj.y

    traced_children: List[VectorObject] = []

    if mode in ("bw", "sketch", "line"):
        gray = cv2.cvtColor(rgb_work, cv2.COLOR_RGB2GRAY)
        if sketch_ai or mode == "sketch":
            # AI-assisted sketch cleanup: bilateral denoise + adaptive local ink threshold + morphological bridge
            clean = cv2.bilateralFilter(gray, 7, 45, 45)
            mask = cv2.adaptiveThreshold(
                clean, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 7
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        elif mode == "line":
            blur = cv2.GaussianBlur(gray, (3, 3), 0)
            mask = cv2.Canny(blur, max(20, threshold // 2), min(250, threshold + 60))
            mask = cv2.dilate(mask, np.ones((2, 2), np.uint8), iterations=1)
        else:
            _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        sps: List[SubPath] = []
        for cnt in contours:
            if cv2.contourArea(cnt) < min_area:
                continue
            pts = [(ox + float(pt[0][0]) * sx, oy + float(pt[0][1]) * sy) for pt in cnt]
            simp = rdp_simplify(pts, max(0.8, simplify * max(sx, sy)))
            if len(simp) < 3:
                continue
            if smooth_curves:
                sps.append(fit_catmull_rom_subpath(simp, closed=True, tension=0.42))
            else:
                sps.append(SubPath([AnchorPoint(px, py) for px, py in simp], closed=True))
        if sps:
            br = subpaths_to_qpath(sps).boundingRect()
            traced_children.append(VectorObject(
                name="Traced Ink Path", kind="path", subpaths=sps,
                x=br.x(), y=br.y(), width=br.width(), height=br.height(),
                appearance=Appearance(
                    fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#14171F"))],
                    strokes=[AppearanceStroke(stroke_type="none")],
                ),
            ))
    else:
        # Color or Grayscale K-Means Quantization
        if mode == "gray":
            g = cv2.cvtColor(rgb_work, cv2.COLOR_RGB2GRAY)
            work = cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)
        else:
            work = cv2.bilateralFilter(rgb_work, 5, 35, 35)

        k = max(2, min(24, int(colors)))
        pixels = work.reshape((-1, 3)).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 16, 1.0)
        _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        labels_2d = labels.reshape((th, tw))
        centers_u8 = np.clip(centers, 0, 255).astype(np.uint8)

        # Sort clusters from largest area (background) to smallest (foreground detail)
        cluster_order = sorted(range(k), key=lambda idx: int(np.sum(labels_2d == idx)), reverse=True)
        for ci in cluster_order:
            r, g, b = int(centers_u8[ci][0]), int(centers_u8[ci][1]), int(centers_u8[ci][2])
            if ignore_white and r > 240 and g > 240 and b > 240:
                continue
            mask = (labels_2d == ci).astype(np.uint8) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            sps: List[SubPath] = []
            for cnt in contours:
                if cv2.contourArea(cnt) < min_area:
                    continue
                pts = [(ox + float(pt[0][0]) * sx, oy + float(pt[0][1]) * sy) for pt in cnt]
                simp = rdp_simplify(pts, max(0.8, simplify * max(sx, sy)))
                if len(simp) < 3:
                    continue
                if smooth_curves:
                    sps.append(fit_catmull_rom_subpath(simp, closed=True, tension=0.45))
                else:
                    sps.append(SubPath([AnchorPoint(px, py) for px, py in simp], closed=True))
            if sps:
                br = subpaths_to_qpath(sps).boundingRect()
                traced_children.append(VectorObject(
                    name=f"Color Region #{r:02X}{g:02X}{b:02X}",
                    kind="path", subpaths=sps,
                    x=br.x(), y=br.y(), width=br.width(), height=br.height(),
                    appearance=Appearance(
                        fills=[AppearanceFill(fill_type="solid", color=Color(r, g, b, 255))],
                        strokes=[AppearanceStroke(stroke_type="none")],
                    ),
                ))

    if not traced_children:
        return None
    return VectorObject(
        name=f"Image Trace ({img_obj.name})",
        kind="group",
        layer_id=img_obj.layer_id,
        x=img_obj.x, y=img_obj.y, width=img_obj.width, height=img_obj.height,
        children=traced_children,
    )


# ---------------------------------------------------------------------------
# Generative Recolor Palettes
# ---------------------------------------------------------------------------

GENERATIVE_PALETTES: Dict[str, List[str]] = {
    "cyberpunk neon": ["#0B0E1A", "#FF2A85", "#00F5D4", "#7B2CBF", "#FFE600", "#1C2541"],
    "sunset retro": ["#2B193D", "#FF595E", "#FF924C", "#FFCA3A", "#8AC926", "#F7EDE2"],
    "oceanic calm": ["#03045E", "#0077B6", "#00B4D8", "#90E0EF", "#CAF0F8", "#023E8A"],
    "autumn forest": ["#283618", "#606C38", "#DDA15E", "#BC6C25", "#FEFAE0", "#9B2226"],
    "pastel bakery": ["#FFF1E6", "#FDE2E4", "#FAD2E1", "#BEE1E6", "#CDDAFD", "#A5A58D"],
    "swiss modernist": ["#111111", "#F5F5F0", "#E63946", "#1D3557", "#FFB703", "#457B9D"],
    "kinosuite dark": ["#12151C", "#1F242E", "#FF9A00", "#00C2FF", "#6E2CF2", "#E2E8F0"],
    "botanical sage": ["#1B4332", "#2D6A4F", "#52B788", "#95D5B2", "#D8F3DC", "#E9C46A"],
    "luxury gold": ["#0D0D0D", "#1E1E24", "#D4AF37", "#F6E27F", "#8C6D1F", "#F4F1DE"],
    "pop art comic": ["#FF006E", "#FFBE0B", "#3A86FF", "#8338EC", "#FB5607", "#141414"],
}


def generate_palette_from_prompt(prompt: str) -> List[Color]:
    p = prompt.lower().strip()
    for k, hexes in GENERATIVE_PALETTES.items():
        if any(w in p for w in k.split()):
            return [Color.from_hex(h) for h in hexes]
    # Deterministic harmonic palette seeded from prompt text
    seed = sum(ord(c) * (i + 1) for i, c in enumerate(p or "kinodraw"))
    rng = random.Random(seed)
    base_h = rng.random()
    cols: List[Color] = []
    for i in range(6):
        h = (base_h + i * 0.14) % 1.0
        s = 0.55 + (i % 3) * 0.15
        v = 0.25 + (i / 6.0) * 0.7
        cols.append(_hsv_to_color(h, s, v))
    return cols


def _hsv_to_color(h: float, s: float, v: float) -> Color:
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i %= 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return Color(int(r * 255), int(g * 255), int(b * 255), 255)


def recolor_objects(objects: List[VectorObject], palette: List[Color], hue_shift: float = 0.0) -> None:
    """Remap all solid & gradient colors across selected objects to a new palette or hue shift."""
    if not objects:
        return
    # Collect unique source hex colors to keep semantic mapping consistent
    color_map: Dict[str, Color] = {}
    idx_counter = [0]

    def _map_color(c: Color) -> Color:
        if palette:
            key = c.to_hex()
            if key not in color_map:
                color_map[key] = copy.deepcopy(palette[idx_counter[0] % len(palette)])
                idx_counter[0] += 1
            mapped = copy.deepcopy(color_map[key])
            mapped.a = c.a
            return mapped
        if abs(hue_shift) > 0.5:
            # Shift hue by degrees
            rf, gf, bf = c.r / 255.0, c.g / 255.0, c.b / 255.0
            mx, mn = max(rf, gf, bf), min(rf, gf, bf)
            d = mx - mn
            if d < 1e-4:
                return c
            if mx == rf:
                h = ((gf - bf) / d) % 6.0
            elif mx == gf:
                h = (bf - rf) / d + 2.0
            else:
                h = (rf - gf) / d + 4.0
            h = ((h / 6.0) + hue_shift / 360.0) % 1.0
            s = d / mx if mx > 1e-4 else 0.0
            nc = _hsv_to_color(h, s, mx)
            nc.a = c.a
            return nc
        return c

    def _walk(o: VectorObject) -> None:
        for f in o.appearance.fills:
            if f.fill_type == "solid":
                f.color = _map_color(f.color)
            elif f.fill_type == "gradient" and f.gradient:
                for st in f.gradient.stops:
                    st.color = _map_color(st.color)
                for fp in f.gradient.freeform_points:
                    fp.color = _map_color(fp.color)
                f.gradient.mesh_colors = [_map_color(mc) for mc in f.gradient.mesh_colors]
        for s in o.appearance.strokes:
            if s.stroke_type == "solid":
                s.color = _map_color(s.color)
        for ch in o.children:
            _walk(ch)

    for obj in objects:
        _walk(obj)


# ---------------------------------------------------------------------------
# Text-to-Vector Graphic & Generative Pattern Synthesizer (Works 100% Offline)
# ---------------------------------------------------------------------------

def generate_vector_from_prompt(prompt: str, style: str = "Subject",
                                x: float = 200.0, y: float = 160.0, size: float = 280.0) -> VectorObject:
    """Synthesize clean multi-layer editable vector artwork from a text prompt."""
    p = (prompt or "geometric emblem").lower().strip()
    palette = generate_palette_from_prompt(p)
    seed = sum(ord(ch) * (i + 3) for i, ch in enumerate(p))
    rng = random.Random(seed)
    children: List[VectorObject] = []

    def _solid(hex_or_col, stroke_col=None, sw=0.0) -> Appearance:
        col = hex_or_col if isinstance(hex_or_col, Color) else Color.from_hex(hex_or_col)
        st = AppearanceStroke(stroke_type="solid", color=stroke_col if isinstance(stroke_col, Color) else Color.from_hex(stroke_col), width=sw) if stroke_col else AppearanceStroke(stroke_type="none")
        return Appearance(fills=[AppearanceFill(fill_type="solid", color=col)], strokes=[st])

    if any(k in p for k in ("mountain", "landscape", "sunset", "scene", "nature", "hill", "desert")):
        # Layered vector sunset landscape badge
        sky = VectorObject(
            name="Sky Backdrop", kind="shape", shape_type="rect",
            x=x, y=y, width=size, height=size * 0.78, corner_radius=18,
            appearance=Appearance(
                fills=[AppearanceFill(fill_type="gradient", gradient=GradientDef(
                    kind="linear", angle=90, stops=[
                        GradientStop(0.0, Color.from_hex("#1D1B38")),
                        GradientStop(0.55, Color.from_hex("#FF595E")),
                        GradientStop(1.0, Color.from_hex("#FFCA3A")),
                    ]
                ))],
                strokes=[AppearanceStroke(stroke_type="none")],
            ),
        )
        sun = VectorObject(
            name="Sun", kind="shape", shape_type="ellipse",
            x=x + size * 0.56, y=y + size * 0.14, width=size * 0.24, height=size * 0.24,
            appearance=_solid("#FFF3B0"),
        )
        m_back = VectorObject(
            name="Far Ridge", kind="path",
            subpaths=[SubPath([
                AnchorPoint(x, y + size * 0.78),
                AnchorPoint(x, y + size * 0.52),
                AnchorPoint(x + size * 0.28, y + size * 0.26),
                AnchorPoint(x + size * 0.54, y + size * 0.48),
                AnchorPoint(x + size * 0.78, y + size * 0.30),
                AnchorPoint(x + size, y + size * 0.50),
                AnchorPoint(x + size, y + size * 0.78),
            ], closed=True)],
            appearance=_solid("#3D2C5E"),
        )
        m_front = VectorObject(
            name="Near Peak", kind="path",
            subpaths=[SubPath([
                AnchorPoint(x, y + size * 0.78),
                AnchorPoint(x + size * 0.15, y + size * 0.50),
                AnchorPoint(x + size * 0.42, y + size * 0.64),
                AnchorPoint(x + size * 0.72, y + size * 0.44),
                AnchorPoint(x + size, y + size * 0.66),
                AnchorPoint(x + size, y + size * 0.78),
            ], closed=True)],
            appearance=_solid("#19172E"),
        )
        children = [sky, sun, m_back, m_front]

    elif any(k in p for k in ("rocket", "space", "planet", "astronaut", "ufo", "launch")):
        bg = VectorObject(
            name="Space Disc", kind="shape", shape_type="ellipse",
            x=x, y=y, width=size, height=size,
            appearance=_solid("#12182B", "#FF9A00", 4.0),
        )
        body = VectorObject(
            name="Rocket Fuselage", kind="path",
            subpaths=[SubPath([
                AnchorPoint(x + size * 0.50, y + size * 0.14, x + size * 0.42, y + size * 0.24, x + size * 0.58, y + size * 0.24, "smooth"),
                AnchorPoint(x + size * 0.64, y + size * 0.56),
                AnchorPoint(x + size * 0.58, y + size * 0.72),
                AnchorPoint(x + size * 0.42, y + size * 0.72),
                AnchorPoint(x + size * 0.36, y + size * 0.56),
            ], closed=True)],
            appearance=_solid("#F8FAFC", "#1E293B", 3.0),
        )
        fin_l = VectorObject(
            name="Left Fin", kind="path",
            subpaths=[SubPath([
                AnchorPoint(x + size * 0.37, y + size * 0.52),
                AnchorPoint(x + size * 0.23, y + size * 0.72),
                AnchorPoint(x + size * 0.40, y + size * 0.68),
            ], closed=True)],
            appearance=_solid("#FF3B6B"),
        )
        fin_r = VectorObject(
            name="Right Fin", kind="path",
            subpaths=[SubPath([
                AnchorPoint(x + size * 0.63, y + size * 0.52),
                AnchorPoint(x + size * 0.77, y + size * 0.72),
                AnchorPoint(x + size * 0.60, y + size * 0.68),
            ], closed=True)],
            appearance=_solid("#FF3B6B"),
        )
        window = VectorObject(
            name="Porthole", kind="shape", shape_type="ellipse",
            x=x + size * 0.43, y=y + size * 0.36, width=size * 0.14, height=size * 0.14,
            appearance=_solid("#00C2FF", "#1E293B", 3.0),
        )
        flame = VectorObject(
            name="Exhaust Flame", kind="path",
            subpaths=[SubPath([
                AnchorPoint(x + size * 0.44, y + size * 0.73),
                AnchorPoint(x + size * 0.50, y + size * 0.90),
                AnchorPoint(x + size * 0.56, y + size * 0.73),
            ], closed=True)],
            appearance=_solid("#FF9A00"),
        )
        children = [bg, fin_l, fin_r, flame, body, window]

    elif any(k in p for k in ("plant", "leaf", "botanical", "flower", "tree", "coffee")):
        pot = VectorObject(
            name="Ceramic Vessel", kind="path",
            subpaths=[SubPath([
                AnchorPoint(x + size * 0.28, y + size * 0.62),
                AnchorPoint(x + size * 0.72, y + size * 0.62),
                AnchorPoint(x + size * 0.64, y + size * 0.92),
                AnchorPoint(x + size * 0.36, y + size * 0.92),
            ], closed=True)],
            appearance=_solid("#D96B43", "#2A1E17", 2.5),
        )
        children.append(pot)
        for idx, (ang, col_hex) in enumerate([(-38, "#2D6A4F"), (0, "#40916C"), (38, "#52B788")]):
            rad = math.radians(ang - 90)
            cx0, cy0 = x + size * 0.50, y + size * 0.62
            tip_x = cx0 + math.cos(rad) * size * 0.46
            tip_y = cy0 + math.sin(rad) * size * 0.46
            px, py = -math.sin(rad) * size * 0.14, math.cos(rad) * size * 0.14
            mx, my = (cx0 + tip_x) * 0.5, (cy0 + tip_y) * 0.5
            leaf = VectorObject(
                name=f"Leaf {idx + 1}", kind="path",
                subpaths=[SubPath([
                    AnchorPoint(cx0, cy0, cx0, cy0, mx - px, my - py, "corner"),
                    AnchorPoint(tip_x, tip_y, mx - px, my - py, mx + px, my + py, "corner"),
                ], closed=True)],
                appearance=_solid(col_hex, "#1B4332", 2.0),
            )
            children.append(leaf)

    elif any(k in p for k in ("logo", "badge", "emblem", "crest", "brand", "cinema", "kino", "film")):
        outer = VectorObject(
            name="Outer Shield", kind="shape", shape_type="polygon", sides=6,
            x=x, y=y, width=size, height=size,
            appearance=Appearance(
                fills=[AppearanceFill(fill_type="gradient", gradient=GradientDef(
                    kind="linear", angle=45, stops=[
                        GradientStop(0.0, palette[0]), GradientStop(1.0, palette[2]),
                    ]
                ))],
                strokes=[AppearanceStroke(stroke_type="solid", color=palette[3], width=5.0)],
            ),
        )
        inner = VectorObject(
            name="Inner Star", kind="shape", shape_type="star", sides=6, inner_radius_ratio=0.45,
            x=x + size * 0.22, y=y + size * 0.22, width=size * 0.56, height=size * 0.56,
            appearance=_solid(palette[4], "#FFFFFF", 2.5),
        )
        word = prompt.split()[0].upper()[:8] if prompt.strip() else "KINO"
        lbl = VectorObject(
            name="Emblem Title", kind="text", text_mode="point", text=word,
            x=x + size * 0.5, y=y + size * 0.42,
            text_style=TextStyle(font_family="Segoe UI", font_size=size * 0.13, font_weight=800, align="center", tracking=2.0),
            appearance=_solid("#FFFFFF"),
        )
        children = [outer, inner, lbl]

    else:
        # Abstract geometric Bauhaus / Swiss vector composition seeded from prompt
        card = VectorObject(
            name="Art Frame", kind="shape", shape_type="rect",
            x=x, y=y, width=size, height=size, corner_radius=16,
            appearance=_solid(palette[0]),
        )
        children.append(card)
        for i in range(6):
            st = rng.choice(["ellipse", "rect", "polygon", "star"])
            w = rng.uniform(size * 0.18, size * 0.48)
            h = w if st in ("polygon", "star") else rng.uniform(size * 0.16, size * 0.46)
            ox = x + rng.uniform(size * 0.08, size - w - size * 0.08)
            oy = y + rng.uniform(size * 0.08, size - h - size * 0.08)
            col = palette[(i + 1) % len(palette)]
            children.append(VectorObject(
                name=f"Gen Shape {i + 1}", kind="shape", shape_type=st,
                x=ox, y=oy, width=w, height=h, sides=rng.choice([3, 5, 6, 8]),
                corner_radius=rng.choice([0, 8, 16]),
                rotation=rng.choice([0, 15, 30, 45]),
                appearance=Appearance(
                    fills=[AppearanceFill(fill_type="solid", color=col)],
                    strokes=[AppearanceStroke(stroke_type="solid", color=Color(255, 255, 255, 160), width=1.8)],
                    opacity=rng.uniform(0.78, 1.0),
                ),
            ))

    return VectorObject(
        name=f"AI Vector: {prompt[:26]}",
        kind="group",
        x=x, y=y, width=size, height=size,
        children=children,
    )


def generate_pattern_from_prompt(prompt: str) -> PatternDef:
    p = (prompt or "geometric").lower()
    palette = generate_palette_from_prompt(p)
    kind = "dots"
    for candidate, keys in [
        ("botanical", ("leaf", "floral", "botanical", "plant", "jungle", "nature")),
        ("waves", ("wave", "ocean", "water", "sea", "ripple")),
        ("stars", ("star", "space", "night", "galaxy", "sparkle")),
        ("memphis", ("memphis", "80s", "90s", "retro", "pop", "confetti")),
        ("terrazzo", ("terrazzo", "stone", "speckle", "marble")),
        ("art_deco", ("deco", "gold", "luxury", "gatsby", "fan")),
        ("chevron", ("chevron", "zigzag", "herringbone")),
        ("stripes", ("stripe", "diagonal", "candy")),
        ("grid", ("grid", "plaid", "check", "blueprint", "circuit")),
    ]:
        if any(k in p for k in keys):
            kind = candidate
            break
    return PatternDef(
        name=f"AI Pattern: {prompt[:22]}",
        kind=kind,
        tile_size=44.0,
        bg_color=palette[0],
        fg_color=palette[2],
        accent_color=palette[3],
    )
