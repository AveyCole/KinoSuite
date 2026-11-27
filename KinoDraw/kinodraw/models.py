"""Core vector document data model for Vectora.

Supports multi-artboard documents, hierarchical layers/groups, clipping & opacity masks,
cubic Bezier paths, live parametric shapes, point/area/on-path text with Touch Type and
OpenType features, stackable Appearance (multiple fills/strokes/effects), gradients
(linear, radial, freeform, mesh), patterns, brushes, symbols, graphic styles, linked &
embedded images, charts, blends, repeats, mockups, perspective grids, actions, variables,
and version history.
"""
from __future__ import annotations

import copy
import json
import math
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


def new_id(prefix: str = "obj") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Color, Gradients, Patterns, Swatches
# ---------------------------------------------------------------------------

@dataclass
class Color:
    r: int = 255
    g: int = 255
    b: int = 255
    a: int = 255
    mode: str = "RGB"  # "RGB", "CMYK", "SPOT"
    c: float = 0.0     # 0..100
    m: float = 0.0
    y: float = 0.0
    k: float = 0.0
    spot_name: str = ""
    overprint: bool = False

    def __post_init__(self):
        self.r = max(0, min(255, int(self.r)))
        self.g = max(0, min(255, int(self.g)))
        self.b = max(0, min(255, int(self.b)))
        self.a = max(0, min(255, int(self.a)))
        if self.mode == "RGB" and (self.c == 0 and self.m == 0 and self.y == 0 and self.k == 0):
            self.sync_cmyk_from_rgb()

    def sync_cmyk_from_rgb(self) -> None:
        rf, gf, bf = self.r / 255.0, self.g / 255.0, self.b / 255.0
        k = 1.0 - max(rf, gf, bf)
        if k >= 0.999:
            self.c, self.m, self.y, self.k = 0.0, 0.0, 0.0, 100.0
        else:
            self.c = round(((1.0 - rf - k) / (1.0 - k)) * 100.0, 1)
            self.m = round(((1.0 - gf - k) / (1.0 - k)) * 100.0, 1)
            self.y = round(((1.0 - bf - k) / (1.0 - k)) * 100.0, 1)
            self.k = round(k * 100.0, 1)

    def sync_rgb_from_cmyk(self) -> None:
        cf, mf, yf, kf = self.c / 100.0, self.m / 100.0, self.y / 100.0, self.k / 100.0
        self.r = max(0, min(255, int(round(255.0 * (1.0 - cf) * (1.0 - kf)))))
        self.g = max(0, min(255, int(round(255.0 * (1.0 - mf) * (1.0 - kf)))))
        self.b = max(0, min(255, int(round(255.0 * (1.0 - yf) * (1.0 - kf)))))

    @classmethod
    def from_hex(cls, hex_str: str, alpha: int = 255) -> "Color":
        s = hex_str.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) == 8:
            alpha = int(s[6:8], 16)
            s = s[:6]
        if len(s) != 6:
            return cls(0, 0, 0, alpha)
        c = cls(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), alpha)
        c.sync_cmyk_from_rgb()
        return c

    @classmethod
    def from_cmyk(cls, c: float, m: float, y: float, k: float, spot_name: str = "") -> "Color":
        col = cls(0, 0, 0, 255, mode="SPOT" if spot_name else "CMYK", c=c, m=m, y=y, k=k, spot_name=spot_name)
        col.sync_rgb_from_cmyk()
        return col

    def to_hex(self, include_alpha: bool = False) -> str:
        if include_alpha:
            return f"#{self.r:02X}{self.g:02X}{self.b:02X}{self.a:02X}"
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    def to_rgba_css(self) -> str:
        if self.a >= 255:
            return self.to_hex()
        return f"rgba({self.r}, {self.g}, {self.b}, {self.a / 255.0:.3f})"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Color":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class GradientStop:
    offset: float = 0.0  # 0..1
    color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))
    midpoint: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {"offset": self.offset, "color": self.color.to_dict(), "midpoint": self.midpoint}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GradientStop":
        return cls(
            offset=float(d.get("offset", 0.0)),
            color=Color.from_dict(d.get("color", {})),
            midpoint=float(d.get("midpoint", 0.5)),
        )


@dataclass
class FreeformPoint:
    x: float = 0.5  # normalized 0..1 inside object bbox
    y: float = 0.5
    color: Color = field(default_factory=lambda: Color(255, 154, 0, 255))
    spread: float = 0.45

    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "color": self.color.to_dict(), "spread": self.spread}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FreeformPoint":
        return cls(
            x=float(d.get("x", 0.5)),
            y=float(d.get("y", 0.5)),
            color=Color.from_dict(d.get("color", {})),
            spread=float(d.get("spread", 0.45)),
        )


@dataclass
class GradientDef:
    kind: str = "linear"  # "linear", "radial", "freeform", "mesh"
    angle: float = 0.0    # degrees
    x1: float = 0.0       # normalized object bbox coords
    y1: float = 0.5
    x2: float = 1.0
    y2: float = 0.5
    cx: float = 0.5
    cy: float = 0.5
    fx: float = 0.5
    fy: float = 0.5
    radius: float = 0.5
    stops: List[GradientStop] = field(default_factory=lambda: [
        GradientStop(0.0, Color.from_hex("#FF9A00")),
        GradientStop(1.0, Color.from_hex("#6E2CF2")),
    ])
    freeform_points: List[FreeformPoint] = field(default_factory=list)
    mesh_rows: int = 3
    mesh_cols: int = 3
    # flat list of (mesh_rows * mesh_cols) Color dicts for mesh nodes
    mesh_colors: List[Color] = field(default_factory=list)
    stroke_mode: str = "within"  # "within", "along", "across"

    def ensure_mesh(self) -> None:
        needed = self.mesh_rows * self.mesh_cols
        if len(self.mesh_colors) != needed:
            defaults = [
                Color.from_hex("#FF9A00"), Color.from_hex("#FF3B6B"), Color.from_hex("#6E2CF2"),
                Color.from_hex("#FFD166"), Color.from_hex("#FFFFFF"), Color.from_hex("#00C2FF"),
                Color.from_hex("#06D6A0"), Color.from_hex("#118AB2"), Color.from_hex("#073B4C"),
            ]
            self.mesh_colors = [copy.deepcopy(defaults[i % len(defaults)]) for i in range(needed)]

    def ensure_freeform(self) -> None:
        if not self.freeform_points:
            self.freeform_points = [
                FreeformPoint(0.25, 0.25, Color.from_hex("#FF9A00"), 0.5),
                FreeformPoint(0.75, 0.30, Color.from_hex("#FF3B6B"), 0.5),
                FreeformPoint(0.50, 0.78, Color.from_hex("#3A86FF"), 0.55),
            ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "angle": self.angle,
            "x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2,
            "cx": self.cx, "cy": self.cy, "fx": self.fx, "fy": self.fy, "radius": self.radius,
            "stops": [s.to_dict() for s in self.stops],
            "freeform_points": [p.to_dict() for p in self.freeform_points],
            "mesh_rows": self.mesh_rows,
            "mesh_cols": self.mesh_cols,
            "mesh_colors": [c.to_dict() for c in self.mesh_colors],
            "stroke_mode": self.stroke_mode,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GradientDef":
        return cls(
            kind=d.get("kind", "linear"),
            angle=float(d.get("angle", 0.0)),
            x1=float(d.get("x1", 0.0)), y1=float(d.get("y1", 0.5)),
            x2=float(d.get("x2", 1.0)), y2=float(d.get("y2", 0.5)),
            cx=float(d.get("cx", 0.5)), cy=float(d.get("cy", 0.5)),
            fx=float(d.get("fx", 0.5)), fy=float(d.get("fy", 0.5)),
            radius=float(d.get("radius", 0.5)),
            stops=[GradientStop.from_dict(s) for s in d.get("stops", [])] or [
                GradientStop(0.0, Color.from_hex("#FF9A00")),
                GradientStop(1.0, Color.from_hex("#6E2CF2")),
            ],
            freeform_points=[FreeformPoint.from_dict(p) for p in d.get("freeform_points", [])],
            mesh_rows=int(d.get("mesh_rows", 3)),
            mesh_cols=int(d.get("mesh_cols", 3)),
            mesh_colors=[Color.from_dict(c) for c in d.get("mesh_colors", [])],
            stroke_mode=d.get("stroke_mode", "within"),
        )


@dataclass
class PatternDef:
    id: str = field(default_factory=lambda: new_id("pat"))
    name: str = "Geometric Dots"
    kind: str = "dots"  # "dots", "stripes", "grid", "chevron", "waves", "terrazzo", "botanical", "stars", "memphis", "art_deco"
    tile_size: float = 36.0
    bg_color: Color = field(default_factory=lambda: Color.from_hex("#1D2432"))
    fg_color: Color = field(default_factory=lambda: Color.from_hex("#FF9A00"))
    accent_color: Color = field(default_factory=lambda: Color.from_hex("#00C2FF"))
    rotation: float = 0.0
    scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "tile_size": self.tile_size,
            "bg_color": self.bg_color.to_dict(),
            "fg_color": self.fg_color.to_dict(),
            "accent_color": self.accent_color.to_dict(),
            "rotation": self.rotation, "scale": self.scale,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PatternDef":
        return cls(
            id=d.get("id", new_id("pat")),
            name=d.get("name", "Pattern"),
            kind=d.get("kind", "dots"),
            tile_size=float(d.get("tile_size", 36.0)),
            bg_color=Color.from_dict(d.get("bg_color", {})),
            fg_color=Color.from_dict(d.get("fg_color", {})),
            accent_color=Color.from_dict(d.get("accent_color", {})),
            rotation=float(d.get("rotation", 0.0)),
            scale=float(d.get("scale", 1.0)),
        )


@dataclass
class BrushDef:
    id: str = field(default_factory=lambda: new_id("br"))
    name: str = "Basic"
    kind: str = "basic"  # "basic", "calligraphic", "art", "scatter", "pattern", "bristle"
    angle: float = 35.0
    roundness: float = 0.35
    size: float = 12.0
    spacing: float = 18.0
    scatter: float = 0.35
    bristle_count: int = 9
    taper: float = 0.7
    art_style: str = "charcoal"  # "charcoal", "ink_taper", "marker", "ribbon"
    scatter_shape: str = "star"  # "star", "dot", "leaf", "diamond"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BrushDef":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Stackable Appearance: Fills, Strokes, Live Effects, Graphic Styles
# ---------------------------------------------------------------------------

@dataclass
class AppearanceFill:
    visible: bool = True
    fill_type: str = "solid"  # "none", "solid", "gradient", "pattern"
    color: Color = field(default_factory=lambda: Color.from_hex("#3A86FF"))
    gradient: Optional[GradientDef] = None
    pattern: Optional[PatternDef] = None
    opacity: float = 1.0
    blend_mode: str = "Normal"
    overprint: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "visible": self.visible,
            "fill_type": self.fill_type,
            "color": self.color.to_dict(),
            "gradient": self.gradient.to_dict() if self.gradient else None,
            "pattern": self.pattern.to_dict() if self.pattern else None,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode,
            "overprint": self.overprint,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AppearanceFill":
        return cls(
            visible=bool(d.get("visible", True)),
            fill_type=d.get("fill_type", "solid"),
            color=Color.from_dict(d.get("color", {})),
            gradient=GradientDef.from_dict(d["gradient"]) if d.get("gradient") else None,
            pattern=PatternDef.from_dict(d["pattern"]) if d.get("pattern") else None,
            opacity=float(d.get("opacity", 1.0)),
            blend_mode=d.get("blend_mode", "Normal"),
            overprint=bool(d.get("overprint", False)),
        )


@dataclass
class WidthStation:
    t: float = 0.5          # normalized position 0..1 along path
    left_scale: float = 1.0
    right_scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {"t": self.t, "left_scale": self.left_scale, "right_scale": self.right_scale}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WidthStation":
        return cls(float(d.get("t", 0.5)), float(d.get("left_scale", 1.0)), float(d.get("right_scale", 1.0)))


@dataclass
class AppearanceStroke:
    visible: bool = True
    stroke_type: str = "solid"  # "none", "solid", "gradient"
    color: Color = field(default_factory=lambda: Color.from_hex("#111111"))
    gradient: Optional[GradientDef] = None
    width: float = 2.0
    cap: str = "round"          # "butt", "round", "square"
    join: str = "round"         # "miter", "round", "bevel"
    miter_limit: float = 4.0
    align: str = "center"       # "center", "inside", "outside"
    dash_pattern: List[float] = field(default_factory=list)
    dash_align_corners: bool = True
    arrow_start: str = "none"   # "none", "arrow", "dot", "diamond"
    arrow_end: str = "none"
    width_profile_name: str = "Uniform"
    width_stations: List[WidthStation] = field(default_factory=list)
    brush_id: Optional[str] = None
    opacity: float = 1.0
    blend_mode: str = "Normal"
    overprint: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "visible": self.visible,
            "stroke_type": self.stroke_type,
            "color": self.color.to_dict(),
            "gradient": self.gradient.to_dict() if self.gradient else None,
            "width": self.width,
            "cap": self.cap,
            "join": self.join,
            "miter_limit": self.miter_limit,
            "align": self.align,
            "dash_pattern": list(self.dash_pattern),
            "dash_align_corners": self.dash_align_corners,
            "arrow_start": self.arrow_start,
            "arrow_end": self.arrow_end,
            "width_profile_name": self.width_profile_name,
            "width_stations": [w.to_dict() for w in self.width_stations],
            "brush_id": self.brush_id,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode,
            "overprint": self.overprint,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AppearanceStroke":
        return cls(
            visible=bool(d.get("visible", True)),
            stroke_type=d.get("stroke_type", "solid"),
            color=Color.from_dict(d.get("color", {})),
            gradient=GradientDef.from_dict(d["gradient"]) if d.get("gradient") else None,
            width=float(d.get("width", 2.0)),
            cap=d.get("cap", "round"),
            join=d.get("join", "round"),
            miter_limit=float(d.get("miter_limit", 4.0)),
            align=d.get("align", "center"),
            dash_pattern=[float(x) for x in d.get("dash_pattern", [])],
            dash_align_corners=bool(d.get("dash_align_corners", True)),
            arrow_start=d.get("arrow_start", "none"),
            arrow_end=d.get("arrow_end", "none"),
            width_profile_name=d.get("width_profile_name", "Uniform"),
            width_stations=[WidthStation.from_dict(w) for w in d.get("width_stations", [])],
            brush_id=d.get("brush_id"),
            opacity=float(d.get("opacity", 1.0)),
            blend_mode=d.get("blend_mode", "Normal"),
            overprint=bool(d.get("overprint", False)),
        )


@dataclass
class LiveEffect:
    id: str = field(default_factory=lambda: new_id("fx"))
    kind: str = "drop_shadow"
    # Kinds: "drop_shadow", "outer_glow", "inner_glow", "gaussian_blur",
    #        "warp", "roughen", "offset_path", "extrude_3d", "transform"
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "enabled": self.enabled, "params": copy.deepcopy(self.params)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LiveEffect":
        return cls(
            id=d.get("id", new_id("fx")),
            kind=d.get("kind", "drop_shadow"),
            enabled=bool(d.get("enabled", True)),
            params=copy.deepcopy(d.get("params", {})),
        )


@dataclass
class Appearance:
    fills: List[AppearanceFill] = field(default_factory=lambda: [AppearanceFill()])
    strokes: List[AppearanceStroke] = field(default_factory=lambda: [AppearanceStroke()])
    effects: List[LiveEffect] = field(default_factory=list)
    opacity: float = 1.0
    blend_mode: str = "Normal"

    @property
    def primary_fill(self) -> AppearanceFill:
        if not self.fills:
            self.fills.append(AppearanceFill(fill_type="none"))
        return self.fills[0]

    @property
    def primary_stroke(self) -> AppearanceStroke:
        if not self.strokes:
            self.strokes.append(AppearanceStroke(stroke_type="none"))
        return self.strokes[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fills": [f.to_dict() for f in self.fills],
            "strokes": [s.to_dict() for s in self.strokes],
            "effects": [e.to_dict() for e in self.effects],
            "opacity": self.opacity,
            "blend_mode": self.blend_mode,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Appearance":
        return cls(
            fills=[AppearanceFill.from_dict(f) for f in d.get("fills", [])] or [AppearanceFill(fill_type="none")],
            strokes=[AppearanceStroke.from_dict(s) for s in d.get("strokes", [])] or [AppearanceStroke(stroke_type="none")],
            effects=[LiveEffect.from_dict(e) for e in d.get("effects", [])],
            opacity=float(d.get("opacity", 1.0)),
            blend_mode=d.get("blend_mode", "Normal"),
        )


@dataclass
class GraphicStyle:
    id: str = field(default_factory=lambda: new_id("sty"))
    name: str = "Style"
    appearance: Appearance = field(default_factory=Appearance)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "appearance": self.appearance.to_dict()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GraphicStyle":
        return cls(
            id=d.get("id", new_id("sty")),
            name=d.get("name", "Style"),
            appearance=Appearance.from_dict(d.get("appearance", {})),
        )


# ---------------------------------------------------------------------------
# Bezier Geometry Data Structures
# ---------------------------------------------------------------------------

@dataclass
class AnchorPoint:
    x: float
    y: float
    in_x: Optional[float] = None
    in_y: Optional[float] = None
    out_x: Optional[float] = None
    out_y: Optional[float] = None
    point_type: str = "corner"  # "corner", "smooth", "symmetric"

    def __post_init__(self):
        if self.in_x is None:
            self.in_x = self.x
        if self.in_y is None:
            self.in_y = self.y
        if self.out_x is None:
            self.out_x = self.x
        if self.out_y is None:
            self.out_y = self.y

    def translate(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy
        self.in_x += dx
        self.in_y += dy
        self.out_x += dx
        self.out_y += dy

    def transform_affine(self, m11: float, m12: float, m21: float, m22: float, tx: float, ty: float) -> None:
        def _t(px: float, py: float) -> Tuple[float, float]:
            return (m11 * px + m21 * py + tx, m12 * px + m22 * py + ty)
        self.x, self.y = _t(self.x, self.y)
        self.in_x, self.in_y = _t(self.in_x, self.in_y)
        self.out_x, self.out_y = _t(self.out_x, self.out_y)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": round(self.x, 4), "y": round(self.y, 4),
            "in_x": round(self.in_x, 4), "in_y": round(self.in_y, 4),
            "out_x": round(self.out_x, 4), "out_y": round(self.out_y, 4),
            "point_type": self.point_type,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnchorPoint":
        return cls(
            x=float(d["x"]), y=float(d["y"]),
            in_x=float(d.get("in_x", d["x"])), in_y=float(d.get("in_y", d["y"])),
            out_x=float(d.get("out_x", d["x"])), out_y=float(d.get("out_y", d["y"])),
            point_type=d.get("point_type", "corner"),
        )


@dataclass
class SubPath:
    anchors: List[AnchorPoint] = field(default_factory=list)
    closed: bool = False

    def translate(self, dx: float, dy: float) -> None:
        for a in self.anchors:
            a.translate(dx, dy)

    def to_dict(self) -> Dict[str, Any]:
        return {"anchors": [a.to_dict() for a in self.anchors], "closed": self.closed}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SubPath":
        return cls(
            anchors=[AnchorPoint.from_dict(a) for a in d.get("anchors", [])],
            closed=bool(d.get("closed", False)),
        )


# ---------------------------------------------------------------------------
# Typography (Point, Area, On-Path, OpenType, Touch Type, Threading, Wrap)
# ---------------------------------------------------------------------------

@dataclass
class CharTransform:
    dx: float = 0.0
    dy: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CharTransform":
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TextStyle:
    font_family: str = "Segoe UI"
    font_size: float = 36.0
    font_weight: int = 500       # 100..900 variable weight axis
    font_width: float = 100.0    # variable stretch % (50..200)
    italic: bool = False
    leading: float = 1.25        # line height multiplier
    tracking: float = 0.0        # extra letter spacing in px
    kerning: bool = True
    align: str = "left"          # "left", "center", "right", "justify"
    space_before: float = 0.0
    space_after: float = 6.0
    first_indent: float = 0.0
    # OpenType features
    ot_ligatures: bool = True
    ot_small_caps: bool = False
    ot_tabular_nums: bool = False
    ot_fractions: bool = False
    ot_stylistic_alt: bool = False
    underline: bool = False
    strikethrough: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TextStyle":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PuppetPin:
    x: float
    y: float
    orig_x: float
    orig_y: float
    rotation: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PuppetPin":
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Vector Objects
# ---------------------------------------------------------------------------

@dataclass
class VectorObject:
    id: str = field(default_factory=lambda: new_id("obj"))
    name: str = "Object"
    kind: str = "path"
    # Kinds: "path", "shape", "text", "group", "image", "symbol_instance",
    #        "graph", "blend", "repeat", "mockup", "live_paint"
    visible: bool = True
    locked: bool = False
    layer_id: str = ""
    appearance: Appearance = field(default_factory=Appearance)
    # Transform metadata (stored primarily for non-path objects or extra rotation tracking)
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 100.0
    rotation: float = 0.0
    shear_x: float = 0.0
    shear_y: float = 0.0
    # Text wrap around this object
    text_wrap: bool = False
    text_wrap_offset: float = 10.0
    # Global Edit signature tag (optional)
    global_tag: str = ""
    # Variable data binding name (for CSV/JSON data-driven graphics)
    variable_name: str = ""

    # --- Path data (used by kind == "path", and cached/base for puppet warp) ---
    subpaths: List[SubPath] = field(default_factory=list)
    puppet_pins: List[PuppetPin] = field(default_factory=list)
    puppet_base_subpaths: List[SubPath] = field(default_factory=list)

    # --- Live parametric shape data (kind == "shape") ---
    shape_type: str = "rect"  # "rect", "ellipse", "polygon", "star", "line", "arc", "spiral", "polar_grid"
    corner_radius: float = 0.0
    sides: int = 6
    inner_radius_ratio: float = 0.45
    spiral_turns: float = 3.0
    arc_sweep: float = 120.0

    # --- Text data (kind == "text") ---
    text_mode: str = "point"  # "point", "area", "path"
    text: str = "KinoDraw"
    text_style: TextStyle = field(default_factory=TextStyle)
    char_transforms: Dict[str, CharTransform] = field(default_factory=dict)  # str(index) -> CharTransform
    thread_next_id: Optional[str] = None
    path_text_offset: float = 0.0

    # --- Group data (kind == "group") ---
    children: List["VectorObject"] = field(default_factory=list)
    is_clipping_group: bool = False  # top-most (last) or first child acts as clipping path
    opacity_mask_enabled: bool = False

    # --- Image data (kind == "image") ---
    image_path: str = ""
    image_embedded_b64: str = ""
    image_is_linked: bool = True
    image_orig_w: int = 0
    image_orig_h: int = 0
    crop_rect: Optional[List[float]] = None  # [nx, ny, nw, nh] normalized 0..1

    # --- Symbol instance (kind == "symbol_instance") ---
    symbol_id: str = ""

    # --- Data Graphics / Chart (kind == "graph") ---
    graph_type: str = "bar"  # "bar", "stacked_bar", "line", "pie", "scatter"
    graph_title: str = "Quarterly Growth"
    graph_headers: List[str] = field(default_factory=lambda: ["Q1", "Q2", "Q3", "Q4"])
    graph_series: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "Design", "values": [42, 68, 55, 91], "color": "#FF9A00"},
        {"name": "Print", "values": [28, 45, 62, 74], "color": "#00C2FF"},
        {"name": "Web", "values": [35, 52, 78, 86], "color": "#6E2CF2"},
    ])

    # --- Blend object (kind == "blend") ---
    blend_steps: int = 6
    # children[0] and children[1] are the start/end objects

    # --- Repeat object (kind == "repeat") ---
    repeat_mode: str = "radial"  # "radial", "grid", "mirror"
    repeat_count: int = 8
    repeat_radius: float = 120.0
    repeat_rows: int = 3
    repeat_cols: int = 4
    repeat_spacing_x: float = 90.0
    repeat_spacing_y: float = 90.0
    # children[0] is the source artwork

    # --- Mockup object (kind == "mockup") ---
    mockup_preset: str = "mug"  # "mug", "tshirt", "tote", "cup", "box", "phone"
    mockup_color: Color = field(default_factory=lambda: Color.from_hex("#F4F4F6"))
    mockup_art_scale: float = 0.55
    mockup_art_offset_x: float = 0.0
    mockup_art_offset_y: float = 0.0
    # children[0] is the placed artwork

    # --- Live Paint regions (kind == "live_paint") ---
    live_paint_fills: Dict[str, str] = field(default_factory=dict)  # region_key -> hex color

    def clone(self, new_ids: bool = True) -> "VectorObject":
        c = copy.deepcopy(self)
        if new_ids:
            self._reassign_ids(c)
        return c

    @staticmethod
    def _reassign_ids(obj: "VectorObject") -> None:
        obj.id = new_id(obj.kind[:3])
        for ch in obj.children:
            VectorObject._reassign_ids(ch)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "visible": self.visible, "locked": self.locked, "layer_id": self.layer_id,
            "appearance": self.appearance.to_dict(),
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "rotation": self.rotation, "shear_x": self.shear_x, "shear_y": self.shear_y,
            "text_wrap": self.text_wrap, "text_wrap_offset": self.text_wrap_offset,
            "global_tag": self.global_tag, "variable_name": self.variable_name,
            "subpaths": [sp.to_dict() for sp in self.subpaths],
            "puppet_pins": [p.to_dict() for p in self.puppet_pins],
            "puppet_base_subpaths": [sp.to_dict() for sp in self.puppet_base_subpaths],
            "shape_type": self.shape_type, "corner_radius": self.corner_radius,
            "sides": self.sides, "inner_radius_ratio": self.inner_radius_ratio,
            "spiral_turns": self.spiral_turns, "arc_sweep": self.arc_sweep,
            "text_mode": self.text_mode, "text": self.text,
            "text_style": self.text_style.to_dict(),
            "char_transforms": {k: v.to_dict() for k, v in self.char_transforms.items()},
            "thread_next_id": self.thread_next_id, "path_text_offset": self.path_text_offset,
            "children": [ch.to_dict() for ch in self.children],
            "is_clipping_group": self.is_clipping_group,
            "opacity_mask_enabled": self.opacity_mask_enabled,
            "image_path": self.image_path, "image_embedded_b64": self.image_embedded_b64,
            "image_is_linked": self.image_is_linked,
            "image_orig_w": self.image_orig_w, "image_orig_h": self.image_orig_h,
            "crop_rect": self.crop_rect,
            "symbol_id": self.symbol_id,
            "graph_type": self.graph_type, "graph_title": self.graph_title,
            "graph_headers": list(self.graph_headers),
            "graph_series": copy.deepcopy(self.graph_series),
            "blend_steps": self.blend_steps,
            "repeat_mode": self.repeat_mode, "repeat_count": self.repeat_count,
            "repeat_radius": self.repeat_radius, "repeat_rows": self.repeat_rows,
            "repeat_cols": self.repeat_cols, "repeat_spacing_x": self.repeat_spacing_x,
            "repeat_spacing_y": self.repeat_spacing_y,
            "mockup_preset": self.mockup_preset, "mockup_color": self.mockup_color.to_dict(),
            "mockup_art_scale": self.mockup_art_scale,
            "mockup_art_offset_x": self.mockup_art_offset_x,
            "mockup_art_offset_y": self.mockup_art_offset_y,
            "live_paint_fills": dict(self.live_paint_fills),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VectorObject":
        return cls(
            id=d.get("id", new_id("obj")),
            name=d.get("name", "Object"),
            kind=d.get("kind", "path"),
            visible=bool(d.get("visible", True)),
            locked=bool(d.get("locked", False)),
            layer_id=d.get("layer_id", ""),
            appearance=Appearance.from_dict(d.get("appearance", {})),
            x=float(d.get("x", 0.0)), y=float(d.get("y", 0.0)),
            width=float(d.get("width", 100.0)), height=float(d.get("height", 100.0)),
            rotation=float(d.get("rotation", 0.0)),
            shear_x=float(d.get("shear_x", 0.0)), shear_y=float(d.get("shear_y", 0.0)),
            text_wrap=bool(d.get("text_wrap", False)),
            text_wrap_offset=float(d.get("text_wrap_offset", 10.0)),
            global_tag=d.get("global_tag", ""),
            variable_name=d.get("variable_name", ""),
            subpaths=[SubPath.from_dict(sp) for sp in d.get("subpaths", [])],
            puppet_pins=[PuppetPin.from_dict(p) for p in d.get("puppet_pins", [])],
            puppet_base_subpaths=[SubPath.from_dict(sp) for sp in d.get("puppet_base_subpaths", [])],
            shape_type=d.get("shape_type", "rect"),
            corner_radius=float(d.get("corner_radius", 0.0)),
            sides=int(d.get("sides", 6)),
            inner_radius_ratio=float(d.get("inner_radius_ratio", 0.45)),
            spiral_turns=float(d.get("spiral_turns", 3.0)),
            arc_sweep=float(d.get("arc_sweep", 120.0)),
            text_mode=d.get("text_mode", "point"),
            text=d.get("text", "KinoDraw"),
            text_style=TextStyle.from_dict(d.get("text_style", {})),
            char_transforms={k: CharTransform.from_dict(v) for k, v in d.get("char_transforms", {}).items()},
            thread_next_id=d.get("thread_next_id"),
            path_text_offset=float(d.get("path_text_offset", 0.0)),
            children=[VectorObject.from_dict(ch) for ch in d.get("children", [])],
            is_clipping_group=bool(d.get("is_clipping_group", False)),
            opacity_mask_enabled=bool(d.get("opacity_mask_enabled", False)),
            image_path=d.get("image_path", ""),
            image_embedded_b64=d.get("image_embedded_b64", ""),
            image_is_linked=bool(d.get("image_is_linked", True)),
            image_orig_w=int(d.get("image_orig_w", 0)),
            image_orig_h=int(d.get("image_orig_h", 0)),
            crop_rect=d.get("crop_rect"),
            symbol_id=d.get("symbol_id", ""),
            graph_type=d.get("graph_type", "bar"),
            graph_title=d.get("graph_title", "Chart"),
            graph_headers=list(d.get("graph_headers", ["Q1", "Q2", "Q3", "Q4"])),
            graph_series=copy.deepcopy(d.get("graph_series", [])),
            blend_steps=int(d.get("blend_steps", 6)),
            repeat_mode=d.get("repeat_mode", "radial"),
            repeat_count=int(d.get("repeat_count", 8)),
            repeat_radius=float(d.get("repeat_radius", 120.0)),
            repeat_rows=int(d.get("repeat_rows", 3)),
            repeat_cols=int(d.get("repeat_cols", 4)),
            repeat_spacing_x=float(d.get("repeat_spacing_x", 90.0)),
            repeat_spacing_y=float(d.get("repeat_spacing_y", 90.0)),
            mockup_preset=d.get("mockup_preset", "mug"),
            mockup_color=Color.from_dict(d.get("mockup_color", {})),
            mockup_art_scale=float(d.get("mockup_art_scale", 0.55)),
            mockup_art_offset_x=float(d.get("mockup_art_offset_x", 0.0)),
            mockup_art_offset_y=float(d.get("mockup_art_offset_y", 0.0)),
            live_paint_fills=dict(d.get("live_paint_fills", {})),
        )


# ---------------------------------------------------------------------------
# Symbols, Artboards, Layers, Guides, Perspective, Assets, Versions
# ---------------------------------------------------------------------------

@dataclass
class SymbolDef:
    id: str = field(default_factory=lambda: new_id("sym"))
    name: str = "Symbol"
    artwork: VectorObject = field(default_factory=VectorObject)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "artwork": self.artwork.to_dict()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SymbolDef":
        return cls(
            id=d.get("id", new_id("sym")),
            name=d.get("name", "Symbol"),
            artwork=VectorObject.from_dict(d.get("artwork", {})),
        )


@dataclass
class SwatchGroup:
    name: str = "Default"
    colors: List[Color] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "colors": [c.to_dict() for c in self.colors]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SwatchGroup":
        return cls(name=d.get("name", "Group"), colors=[Color.from_dict(c) for c in d.get("colors", [])])


@dataclass
class Artboard:
    id: str = field(default_factory=lambda: new_id("ab"))
    name: str = "Artboard 1"
    x: float = 0.0
    y: float = 0.0
    width: float = 1280.0
    height: float = 800.0
    bg_color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name,
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "bg_color": self.bg_color.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Artboard":
        return cls(
            id=d.get("id", new_id("ab")), name=d.get("name", "Artboard"),
            x=float(d.get("x", 0.0)), y=float(d.get("y", 0.0)),
            width=float(d.get("width", 1280.0)), height=float(d.get("height", 800.0)),
            bg_color=Color.from_dict(d.get("bg_color", {"r": 255, "g": 255, "b": 255, "a": 255})),
        )


@dataclass
class Layer:
    id: str = field(default_factory=lambda: new_id("lyr"))
    name: str = "Layer 1"
    visible: bool = True
    locked: bool = False
    color_tag: str = "#4A9EFF"
    opacity: float = 1.0
    blend_mode: str = "Normal"
    objects: List[VectorObject] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "visible": self.visible,
            "locked": self.locked, "color_tag": self.color_tag,
            "opacity": self.opacity, "blend_mode": self.blend_mode,
            "objects": [o.to_dict() for o in self.objects],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Layer":
        return cls(
            id=d.get("id", new_id("lyr")), name=d.get("name", "Layer"),
            visible=bool(d.get("visible", True)), locked=bool(d.get("locked", False)),
            color_tag=d.get("color_tag", "#4A9EFF"),
            opacity=float(d.get("opacity", 1.0)), blend_mode=d.get("blend_mode", "Normal"),
            objects=[VectorObject.from_dict(o) for o in d.get("objects", [])],
        )


@dataclass
class Guide:
    orientation: str = "v"  # "v" or "h"
    position: float = 0.0
    locked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Guide":
        return cls(d.get("orientation", "v"), float(d.get("position", 0.0)), bool(d.get("locked", False)))


@dataclass
class PerspectiveGridState:
    visible: bool = False
    points: int = 2         # 1, 2, or 3 point perspective
    active_plane: str = "left"  # "none", "left", "right", "horizontal"
    horizon_y: float = 280.0
    ground_y: float = 650.0
    vp_left_x: float = 140.0
    vp_right_x: float = 1140.0
    vp_center_x: float = 640.0
    vp_third_y: float = 1180.0
    grid_divisions: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerspectiveGridState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AssetExportItem:
    id: str = field(default_factory=lambda: new_id("ast"))
    name: str = "Asset"
    object_ids: List[str] = field(default_factory=list)
    scales: List[float] = field(default_factory=lambda: [1.0, 2.0])
    formats: List[str] = field(default_factory=lambda: ["PNG", "SVG"])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AssetExportItem":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class VersionSnapshot:
    id: str = field(default_factory=lambda: new_id("ver"))
    label: str = "Auto Snapshot"
    timestamp: float = field(default_factory=time.time)
    data_json: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "label": self.label, "timestamp": self.timestamp, "data_json": self.data_json}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VersionSnapshot":
        return cls(
            id=d.get("id", new_id("ver")),
            label=d.get("label", "Snapshot"),
            timestamp=float(d.get("timestamp", time.time())),
            data_json=d.get("data_json", ""),
        )


def default_swatch_groups() -> List[SwatchGroup]:
    return [
        SwatchGroup("Adobe Studio", [
            Color.from_hex("#000000"), Color.from_hex("#FFFFFF"),
            Color.from_hex("#FF9A00"), Color.from_hex("#FF3B6B"),
            Color.from_hex("#3A86FF"), Color.from_hex("#6E2CF2"),
            Color.from_hex("#06D6A0"), Color.from_hex("#FFD166"),
            Color.from_hex("#EF476F"), Color.from_hex("#118AB2"),
            Color.from_hex("#073B4C"), Color.from_hex("#2B2D42"),
        ]),
        SwatchGroup("CMYK Process & Spot", [
            Color.from_cmyk(100, 0, 0, 0),
            Color.from_cmyk(0, 100, 0, 0),
            Color.from_cmyk(0, 0, 100, 0),
            Color.from_cmyk(0, 0, 0, 100),
            Color.from_cmyk(0, 48, 100, 0, spot_name="PANTONE 1375 C"),
            Color.from_cmyk(88, 22, 0, 0, spot_name="PANTONE 2995 C"),
            Color.from_cmyk(0, 92, 65, 0, spot_name="PANTONE Warm Red C"),
            Color.from_cmyk(62, 0, 48, 0, spot_name="PANTONE 339 C"),
        ]),
        SwatchGroup("Pastel Editorial", [
            Color.from_hex("#FDE2E4"), Color.from_hex("#FAD2E1"),
            Color.from_hex("#E2ECE9"), Color.from_hex("#BEE1E6"),
            Color.from_hex("#DFE7FD"), Color.from_hex("#CDDAFD"),
            Color.from_hex("#FFF1E6"), Color.from_hex("#C5DEDD"),
        ]),
    ]


def default_brushes() -> List[BrushDef]:
    return [
        BrushDef(id="br_basic", name="Basic Uniform", kind="basic", size=4.0),
        BrushDef(id="br_callig_flat", name="Calligraphic 35° Flat", kind="calligraphic", angle=35.0, roundness=0.25, size=14.0),
        BrushDef(id="br_callig_oval", name="Calligraphic Oval 60°", kind="calligraphic", angle=60.0, roundness=0.45, size=10.0),
        BrushDef(id="br_art_taper", name="Art Ink Taper", kind="art", art_style="ink_taper", size=12.0, taper=0.85),
        BrushDef(id="br_art_charcoal", name="Art Charcoal Feather", kind="art", art_style="charcoal", size=16.0, taper=0.5),
        BrushDef(id="br_scatter_star", name="Scatter Stars", kind="scatter", scatter_shape="star", size=12.0, spacing=24.0, scatter=0.6),
        BrushDef(id="br_scatter_leaf", name="Scatter Leaves", kind="scatter", scatter_shape="leaf", size=14.0, spacing=22.0, scatter=0.45),
        BrushDef(id="br_pattern_chain", name="Pattern Rope / Chain", kind="pattern", size=10.0, spacing=14.0),
        BrushDef(id="br_bristle_mop", name="Bristle Mop Brush", kind="bristle", bristle_count=11, size=18.0),
    ]


def default_graphic_styles() -> List[GraphicStyle]:
    neon_app = Appearance(
        fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#141824"))],
        strokes=[AppearanceStroke(stroke_type="solid", color=Color.from_hex("#00F5D4"), width=3.5)],
        effects=[LiveEffect(kind="outer_glow", params={"color": "#00F5D4", "blur": 14, "opacity": 0.8})],
    )
    amber_grad = Appearance(
        fills=[AppearanceFill(fill_type="gradient", gradient=GradientDef(
            kind="linear", angle=35, stops=[
                GradientStop(0.0, Color.from_hex("#FF9A00")),
                GradientStop(1.0, Color.from_hex("#FF2E63")),
            ]
        ))],
        strokes=[AppearanceStroke(stroke_type="solid", color=Color.from_hex("#FFFFFF"), width=2.0)],
        effects=[LiveEffect(kind="drop_shadow", params={"dx": 6, "dy": 8, "blur": 12, "color": "#000000", "opacity": 0.35})],
    )
    extrude_3d = Appearance(
        fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#3A86FF"))],
        strokes=[AppearanceStroke(stroke_type="none")],
        effects=[LiveEffect(kind="extrude_3d", params={"depth": 28, "angle_x": -22, "angle_y": 28, "material": "glossy", "light_angle": 45})],
    )
    vintage_double = Appearance(
        fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#F4E4C1"))],
        strokes=[
            AppearanceStroke(stroke_type="solid", color=Color.from_hex("#2B2D42"), width=5.0),
            AppearanceStroke(stroke_type="solid", color=Color.from_hex("#D95D39"), width=2.0, dash_pattern=[6.0, 4.0]),
        ],
    )
    glass_card = Appearance(
        fills=[AppearanceFill(fill_type="gradient", gradient=GradientDef(
            kind="linear", angle=135, stops=[
                GradientStop(0.0, Color(255, 255, 255, 210)),
                GradientStop(1.0, Color(220, 235, 255, 140)),
            ]
        ))],
        strokes=[AppearanceStroke(stroke_type="solid", color=Color(255, 255, 255, 220), width=1.5)],
        effects=[LiveEffect(kind="drop_shadow", params={"dx": 0, "dy": 10, "blur": 18, "color": "#0F172A", "opacity": 0.22})],
    )
    return [
        GraphicStyle(id="sty_neon", name="Cyber Neon Glow", appearance=neon_app),
        GraphicStyle(id="sty_amber", name="Sunset Gradient Card", appearance=amber_grad),
        GraphicStyle(id="sty_3d", name="3D Extruded Gloss", appearance=extrude_3d),
        GraphicStyle(id="sty_vintage", name="Double-Stroke Badge", appearance=vintage_double),
        GraphicStyle(id="sty_glass", name="Frosted UI Glass", appearance=glass_card),
    ]


def default_symbols() -> List[SymbolDef]:
    # Starburst badge, Leaf, Sparkle, Location Pin
    star = VectorObject(
        id="sym_art_star", name="Star Emblem", kind="shape", shape_type="star",
        x=0, y=0, width=72, height=72, sides=8, inner_radius_ratio=0.52,
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#FF9A00"))],
            strokes=[AppearanceStroke(stroke_type="solid", color=Color.from_hex("#331800"), width=2.0)],
        ),
    )
    pin = VectorObject(
        id="sym_art_pin", name="Map Pin", kind="path",
        subpaths=[SubPath(closed=True, anchors=[
            AnchorPoint(30, 72, 16, 52, 44, 52, "corner"),
            AnchorPoint(56, 28, 56, 44, 56, 12, "smooth"),
            AnchorPoint(30, 2, 46, 2, 14, 2, "smooth"),
            AnchorPoint(4, 28, 4, 12, 4, 44, "smooth"),
        ])],
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#EF476F"))],
            strokes=[AppearanceStroke(stroke_type="solid", color=Color.from_hex("#FFFFFF"), width=2.5)],
        ),
    )
    sparkle = VectorObject(
        id="sym_art_sparkle", name="4-Point Sparkle", kind="shape", shape_type="star",
        x=0, y=0, width=64, height=64, sides=4, inner_radius_ratio=0.22,
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#00C2FF"))],
            strokes=[AppearanceStroke(stroke_type="none")],
        ),
    )
    hex_logo = VectorObject(
        id="sym_art_hex", name="Hex Badge", kind="shape", shape_type="polygon",
        x=0, y=0, width=70, height=70, sides=6,
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#6E2CF2"))],
            strokes=[AppearanceStroke(stroke_type="solid", color=Color.from_hex("#FFD166"), width=3.0)],
        ),
    )
    return [
        SymbolDef(id="sym_star", name="Starburst Badge", artwork=star),
        SymbolDef(id="sym_pin", name="Map Location Pin", artwork=pin),
        SymbolDef(id="sym_sparkle", name="AI Sparkle", artwork=sparkle),
        SymbolDef(id="sym_hex", name="Hex Emblem", artwork=hex_logo),
    ]


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

@dataclass
class Document:
    id: str = field(default_factory=lambda: new_id("doc"))
    name: str = "Untitled-1"
    file_path: str = ""
    is_cloud_doc: bool = False
    color_mode: str = "RGB"   # "RGB" or "CMYK"
    units: str = "px"         # "px", "pt", "mm", "in"
    bleed: float = 0.0        # print bleed in document units (e.g., 18px / 9pt / 3mm)
    show_crop_marks: bool = False
    grid_visible: bool = False
    grid_spacing: float = 40.0
    snap_to_grid: bool = False
    snap_to_pixel: bool = False
    smart_guides: bool = True
    guides_visible: bool = True
    guides: List[Guide] = field(default_factory=list)
    perspective: PerspectiveGridState = field(default_factory=PerspectiveGridState)
    artboards: List[Artboard] = field(default_factory=lambda: [Artboard()])
    active_artboard_index: int = 0
    layers: List[Layer] = field(default_factory=lambda: [Layer()])
    active_layer_id: str = ""
    swatch_groups: List[SwatchGroup] = field(default_factory=default_swatch_groups)
    brushes: List[BrushDef] = field(default_factory=default_brushes)
    symbols: List[SymbolDef] = field(default_factory=default_symbols)
    graphic_styles: List[GraphicStyle] = field(default_factory=default_graphic_styles)
    assets: List[AssetExportItem] = field(default_factory=list)
    char_styles: Dict[str, TextStyle] = field(default_factory=lambda: {
        "Headline": TextStyle(font_family="Segoe UI", font_size=54, font_weight=700, tracking=-1.0),
        "Subhead": TextStyle(font_family="Segoe UI", font_size=26, font_weight=600, tracking=0.5),
        "Body Copy": TextStyle(font_family="Segoe UI", font_size=15, font_weight=400, leading=1.45),
        "Display Caps": TextStyle(font_family="Segoe UI", font_size=22, font_weight=700, tracking=4.0, ot_small_caps=True),
    })
    variables_datasets: List[Dict[str, str]] = field(default_factory=list)
    active_dataset_index: int = -1
    versions: List[VersionSnapshot] = field(default_factory=list)
    dirty: bool = False

    def __post_init__(self):
        if not self.layers:
            self.layers = [Layer()]
        if not self.active_layer_id or not self.get_layer(self.active_layer_id):
            self.active_layer_id = self.layers[0].id

    def get_layer(self, layer_id: str) -> Optional[Layer]:
        for lyr in self.layers:
            if lyr.id == layer_id:
                return lyr
        return None

    def active_layer(self) -> Layer:
        lyr = self.get_layer(self.active_layer_id)
        if lyr is None:
            lyr = self.layers[0]
            self.active_layer_id = lyr.id
        return lyr

    def active_artboard(self) -> Artboard:
        idx = max(0, min(len(self.artboards) - 1, self.active_artboard_index))
        return self.artboards[idx]

    def iter_all_objects(self, include_hidden: bool = False) -> List[VectorObject]:
        result: List[VectorObject] = []
        for lyr in self.layers:
            if not include_hidden and not lyr.visible:
                continue
            for obj in lyr.objects:
                if include_hidden or obj.visible:
                    result.append(obj)
        return result

    def find_object(self, obj_id: str) -> Optional[VectorObject]:
        def _search(items: List[VectorObject]) -> Optional[VectorObject]:
            for o in items:
                if o.id == obj_id:
                    return o
                if o.children:
                    found = _search(o.children)
                    if found:
                        return found
            return None
        for lyr in self.layers:
            found = _search(lyr.objects)
            if found:
                return found
        return None

    def find_object_layer(self, obj_id: str) -> Optional[Layer]:
        for lyr in self.layers:
            for o in lyr.objects:
                if o.id == obj_id:
                    return lyr
        return None

    def add_object(self, obj: VectorObject, layer_id: Optional[str] = None) -> VectorObject:
        lyr = self.get_layer(layer_id) if layer_id else self.active_layer()
        if lyr is None:
            lyr = self.active_layer()
        obj.layer_id = lyr.id
        lyr.objects.append(obj)
        self.dirty = True
        return obj

    def remove_object(self, obj_id: str) -> bool:
        for lyr in self.layers:
            for i, o in enumerate(lyr.objects):
                if o.id == obj_id:
                    lyr.objects.pop(i)
                    self.dirty = True
                    return True
        return False

    def get_symbol(self, sym_id: str) -> Optional[SymbolDef]:
        for s in self.symbols:
            if s.id == sym_id:
                return s
        return None

    def get_brush(self, brush_id: Optional[str]) -> Optional[BrushDef]:
        if not brush_id:
            return None
        for b in self.brushes:
            if b.id == brush_id:
                return b
        return None

    def snapshot_json(self) -> str:
        return json.dumps(self.to_dict(include_versions=False))

    def save_version(self, label: str = "") -> VersionSnapshot:
        snap = VersionSnapshot(
            label=label or f"Version {len(self.versions) + 1}",
            timestamp=time.time(),
            data_json=self.snapshot_json(),
        )
        self.versions.append(snap)
        return snap

    def restore_version(self, version_id: str) -> bool:
        for v in self.versions:
            if v.id == version_id and v.data_json:
                restored = Document.from_dict(json.loads(v.data_json))
                self.artboards = restored.artboards
                self.layers = restored.layers
                self.guides = restored.guides
                self.symbols = restored.symbols
                self.swatch_groups = restored.swatch_groups
                self.graphic_styles = restored.graphic_styles
                self.brushes = restored.brushes
                self.perspective = restored.perspective
                self.bleed = restored.bleed
                self.color_mode = restored.color_mode
                self.active_layer_id = restored.active_layer_id
                self.dirty = True
                return True
        return False

    def to_dict(self, include_versions: bool = True) -> Dict[str, Any]:
        return {
            "format": "kinodraw_doc_v1",
            "id": self.id, "name": self.name, "is_cloud_doc": self.is_cloud_doc,
            "color_mode": self.color_mode, "units": self.units,
            "bleed": self.bleed, "show_crop_marks": self.show_crop_marks,
            "grid_visible": self.grid_visible, "grid_spacing": self.grid_spacing,
            "snap_to_grid": self.snap_to_grid, "snap_to_pixel": self.snap_to_pixel,
            "smart_guides": self.smart_guides, "guides_visible": self.guides_visible,
            "guides": [g.to_dict() for g in self.guides],
            "perspective": self.perspective.to_dict(),
            "artboards": [ab.to_dict() for ab in self.artboards],
            "active_artboard_index": self.active_artboard_index,
            "layers": [l.to_dict() for l in self.layers],
            "active_layer_id": self.active_layer_id,
            "swatch_groups": [sg.to_dict() for sg in self.swatch_groups],
            "brushes": [b.to_dict() for b in self.brushes],
            "symbols": [s.to_dict() for s in self.symbols],
            "graphic_styles": [gs.to_dict() for gs in self.graphic_styles],
            "assets": [a.to_dict() for a in self.assets],
            "char_styles": {k: v.to_dict() for k, v in self.char_styles.items()},
            "variables_datasets": copy.deepcopy(self.variables_datasets),
            "active_dataset_index": self.active_dataset_index,
            "versions": [v.to_dict() for v in self.versions] if include_versions else [],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Document":
        doc = cls(
            id=d.get("id", new_id("doc")),
            name=d.get("name", "Untitled"),
            is_cloud_doc=bool(d.get("is_cloud_doc", False)),
            color_mode=d.get("color_mode", "RGB"),
            units=d.get("units", "px"),
            bleed=float(d.get("bleed", 0.0)),
            show_crop_marks=bool(d.get("show_crop_marks", False)),
            grid_visible=bool(d.get("grid_visible", False)),
            grid_spacing=float(d.get("grid_spacing", 40.0)),
            snap_to_grid=bool(d.get("snap_to_grid", False)),
            snap_to_pixel=bool(d.get("snap_to_pixel", False)),
            smart_guides=bool(d.get("smart_guides", True)),
            guides_visible=bool(d.get("guides_visible", True)),
            guides=[Guide.from_dict(g) for g in d.get("guides", [])],
            perspective=PerspectiveGridState.from_dict(d.get("perspective", {})),
            artboards=[Artboard.from_dict(ab) for ab in d.get("artboards", [])] or [Artboard()],
            active_artboard_index=int(d.get("active_artboard_index", 0)),
            layers=[Layer.from_dict(l) for l in d.get("layers", [])] or [Layer()],
            active_layer_id=d.get("active_layer_id", ""),
            swatch_groups=[SwatchGroup.from_dict(sg) for sg in d.get("swatch_groups", [])] or default_swatch_groups(),
            brushes=[BrushDef.from_dict(b) for b in d.get("brushes", [])] or default_brushes(),
            symbols=[SymbolDef.from_dict(s) for s in d.get("symbols", [])] or default_symbols(),
            graphic_styles=[GraphicStyle.from_dict(gs) for gs in d.get("graphic_styles", [])] or default_graphic_styles(),
            assets=[AssetExportItem.from_dict(a) for a in d.get("assets", [])],
            char_styles={k: TextStyle.from_dict(v) for k, v in d.get("char_styles", {}).items()} or {
                "Headline": TextStyle(font_family="Segoe UI", font_size=54, font_weight=700),
            },
            variables_datasets=copy.deepcopy(d.get("variables_datasets", [])),
            active_dataset_index=int(d.get("active_dataset_index", -1)),
            versions=[VersionSnapshot.from_dict(v) for v in d.get("versions", [])],
        )
        return doc

    def save_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(include_versions=True), f, indent=2)
        self.file_path = path
        self.dirty = False

    @classmethod
    def load_from_file(cls, path: str) -> "Document":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        doc = cls.from_dict(data)
        doc.file_path = path
        doc.dirty = False
        return doc
