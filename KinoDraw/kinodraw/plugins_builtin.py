"""Plugin & Extension Architecture for KinoDraw (KinoSuite).

Provides built-in studio extensions and discovers external Python plugins placed in
`KinoDraw/plugins/*.py`.
"""
from __future__ import annotations

import importlib.util
import math
import os
from typing import Callable, Dict, List

from .models import (
    AnchorPoint,
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Color,
    Document,
    SubPath,
    TextStyle,
    VectorObject,
)


class KinoPlugin:
    def __init__(self, plugin_id: str, name: str, version: str, description: str,
                 author: str, action: Callable[[Document], str], enabled: bool = True):
        self.id = plugin_id
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.action = action
        self.enabled = enabled


def _plugin_isometric_grid(doc: Document) -> str:
    ab = doc.active_artboard()
    children: List[VectorObject] = []
    step = 48.0
    ang = math.radians(30)
    dx, dy = math.cos(ang) * ab.width * 1.2, math.sin(ang) * ab.width * 1.2
    stroke_app = Appearance(
        fills=[AppearanceFill(fill_type="none")],
        strokes=[AppearanceStroke(stroke_type="solid", color=Color(0, 194, 255, 110), width=1.0)],
    )
    for i in range(-8, 18):
        y0 = ab.y + i * step
        children.append(VectorObject(
            name=f"Iso Line A{i}", kind="shape", shape_type="line",
            x=ab.x, y=y0, width=dx, height=dy, appearance=stroke_app,
        ))
        children.append(VectorObject(
            name=f"Iso Line B{i}", kind="shape", shape_type="line",
            x=ab.x, y=y0, width=dx, height=-dy, appearance=stroke_app,
        ))
    grp = VectorObject(name="Isometric Guide Grid", kind="group", x=ab.x, y=ab.y,
                       width=ab.width, height=ab.height, children=children)
    doc.add_object(grp)
    return "Added Isometric Guide Grid to active layer."


def _plugin_qr_badge(doc: Document) -> str:
    ab = doc.active_artboard()
    ox, oy = ab.x + ab.width * 0.5 - 84, ab.y + ab.height * 0.5 - 84
    cell = 12.0
    n = 14
    children: List[VectorObject] = [
        VectorObject(name="QR Quiet Zone", kind="shape", shape_type="rect",
                     x=ox - 12, y=oy - 12, width=n * cell + 24, height=n * cell + 24, corner_radius=8,
                     appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#FFFFFF"))],
                                           strokes=[AppearanceStroke(color=Color.from_hex("#111111"), width=2.0)]))
    ]
    dark = Appearance(fills=[AppearanceFill(color=Color.from_hex("#111111"))], strokes=[AppearanceStroke(stroke_type="none")])
    for r in range(n):
        for c in range(n):
            in_finder = (r < 4 and c < 4) or (r < 4 and c >= n - 4) or (r >= n - 4 and c < 4)
            bit = in_finder or (((r * 7 + c * 13 + r * c) % 5) in (0, 2))
            if bit:
                children.append(VectorObject(
                    name=f"M{r}_{c}", kind="shape", shape_type="rect",
                    x=ox + c * cell, y=oy + r * cell, width=cell - 0.5, height=cell - 0.5,
                    appearance=dark,
                ))
    doc.add_object(VectorObject(name="Vector QR Matrix", kind="group", x=ox - 12, y=oy - 12,
                                width=n * cell + 24, height=n * cell + 24, children=children))
    return "Generated scalable Vector QR Matrix."


def _plugin_golden_spiral(doc: Document) -> str:
    ab = doc.active_artboard()
    cx, cy = ab.x + ab.width * 0.5, ab.y + ab.height * 0.5
    pts: List[AnchorPoint] = []
    phi = 1.61803398875
    for i in range(60):
        t = i / 14.0
        r = 6.0 * (phi ** (t * 0.85))
        ang = t * math.pi * 0.5
        pts.append(AnchorPoint(cx + r * math.cos(ang), cy + r * math.sin(ang)))
    obj = VectorObject(
        name="Golden Ratio Spiral", kind="path",
        subpaths=[SubPath(anchors=pts, closed=False)],
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="none")],
            strokes=[AppearanceStroke(stroke_type="solid", color=Color.from_hex("#FF9A00"), width=3.0)],
        ),
    )
    doc.add_object(obj)
    return "Inserted Golden Ratio Fibonacci Spiral."


def _plugin_brand_badge(doc: Document) -> str:
    ab = doc.active_artboard()
    cx, cy = ab.x + ab.width * 0.5, ab.y + ab.height * 0.5
    r = 95.0
    children = [
        VectorObject(name="Seal Star", kind="shape", shape_type="star", sides=18, inner_radius_ratio=0.86,
                     x=cx - r, y=cy - r, width=r * 2, height=r * 2,
                     appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#181C24"))],
                                           strokes=[AppearanceStroke(color=Color.from_hex("#FF9A00"), width=3.0)])),
        VectorObject(name="Inner Ring", kind="shape", shape_type="ellipse",
                     x=cx - r * 0.72, y=cy - r * 0.72, width=r * 1.44, height=r * 1.44,
                     appearance=Appearance(fills=[AppearanceFill(fill_type="none")],
                                           strokes=[AppearanceStroke(color=Color.from_hex("#00C2FF"), width=2.0, dash_pattern=[5, 4])])),
        VectorObject(name="Seal Title", kind="text", text_mode="point", text="KINOSUITE",
                     x=cx, y=cy - 14,
                     text_style=TextStyle(font_family="Segoe UI", font_size=22, font_weight=800, align="center", tracking=2.5),
                     appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#FF9A00"))],
                                           strokes=[AppearanceStroke(stroke_type="none")])),
    ]
    doc.add_object(VectorObject(name="Typographic Seal Badge", kind="group",
                                x=cx - r, y=cy - r, width=r * 2, height=r * 2, children=children))
    return "Inserted Typographic Seal Badge."


def load_all_plugins(plugins_dir: str) -> List[KinoPlugin]:
    plugins: List[KinoPlugin] = [
        KinoPlugin("kinodraw.iso_grid", "Isometric Grid Builder", "1.0", "Generates a 30° isometric vector guide grid.", "KinoSuite", _plugin_isometric_grid),
        KinoPlugin("kinodraw.qr_matrix", "Vector QR Code Builder", "1.0", "Creates a crisp scalable vector QR matrix.", "KinoSuite", _plugin_qr_badge),
        KinoPlugin("kinodraw.golden_spiral", "Golden Ratio Spiral", "1.0", "Plots a parametric Fibonacci golden spiral guide.", "KinoSuite", _plugin_golden_spiral),
        KinoPlugin("kinodraw.seal_badge", "Typographic Seal Badge", "1.0", "Generates a vintage scalloped typographic stamp.", "KinoSuite", _plugin_brand_badge),
    ]
    if os.path.isdir(plugins_dir):
        for fname in sorted(os.listdir(plugins_dir)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            fpath = os.path.join(plugins_dir, fname)
            try:
                spec = importlib.util.spec_from_file_location(f"kinodraw_ext_{fname[:-3]}", fpath)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "register_plugin"):
                        ext = mod.register_plugin()
                        if isinstance(ext, KinoPlugin):
                            plugins.append(ext)
            except Exception:
                pass
    return plugins
