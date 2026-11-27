"""Core KinoShop Document (.ksd) data models.

Supports:
- RGB / CMYK / Grayscale / Lab color modes & ICC profiles + Soft-Proofing
- Print Prep: Bleed, Slug, Crop/Registration/ColorBar marks
- Artboards, Slices, Guides, Measurement & Scientific Counting
- Unlimited Layers: Raster, Adjustment, Smart Object, Vector Shape, Text (normal/path/warped), Fill, Group
- Layer Masks, Clipping Masks, 23 Blend Modes, Layer Styles (fx), Smart Filters
- Color Channels, Custom Alpha Channels, Spot Color Channels
- History Stack, Snapshots, and History Brush Source
- Frame-by-frame GIF Animation & Basic Video Timeline
- Variables & CSV Data Sets
- KinoCloud Collaboration: Comments & Version History
"""
from __future__ import annotations

import copy
import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

BLEND_MODES = [
    "Normal",
    "Dissolve",
    "Darken",
    "Multiply",
    "Color Burn",
    "Linear Burn",
    "Lighten",
    "Screen",
    "Color Dodge",
    "Linear Dodge (Add)",
    "Overlay",
    "Soft Light",
    "Hard Light",
    "Vivid Light",
    "Linear Light",
    "Pin Light",
    "Difference",
    "Exclusion",
    "Subtract",
    "Divide",
    "Hue",
    "Saturation",
    "Color",
    "Luminosity",
]

COLOR_MODES = ["RGB", "CMYK", "Grayscale", "Lab"]

COLOR_PROFILES = [
    "sRGB IEC61966-2.1",
    "Adobe RGB (1998)",
    "Display P3",
    "ProPhoto RGB",
    "U.S. Web Coated (SWOP) v2 [CMYK]",
    "Coated FOGRA39 (ISO 12647-2) [CMYK]",
    "Japan Color 2001 Coated [CMYK]",
]

ADJUSTMENT_TYPES = [
    "Levels",
    "Curves",
    "Exposure",
    "Hue/Saturation",
    "Vibrance",
    "Color Balance",
    "Black & White",
    "Photo Filter",
    "Channel Mixer",
    "LUT / Color Lookup",
    "Posterize",
    "Threshold",
    "Invert",
]

TEXT_WARP_STYLES = [
    "None",
    "Arc",
    "Arch",
    "Bulge",
    "Flag",
    "Wave",
    "Rise",
    "Fish",
    "Twist",
]


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class LayerStyles:
    drop_shadow: bool = False
    drop_shadow_color: Tuple[int, int, int] = (0, 0, 0)
    drop_shadow_opacity: float = 0.65
    drop_shadow_distance: int = 8
    drop_shadow_angle: float = 135.0
    drop_shadow_blur: int = 12

    inner_shadow: bool = False
    inner_shadow_color: Tuple[int, int, int] = (0, 0, 0)
    inner_shadow_opacity: float = 0.55
    inner_shadow_distance: int = 4
    inner_shadow_blur: int = 8

    outer_glow: bool = False
    outer_glow_color: Tuple[int, int, int] = (49, 168, 255)
    outer_glow_opacity: float = 0.75
    outer_glow_radius: int = 14

    inner_glow: bool = False
    inner_glow_color: Tuple[int, int, int] = (255, 255, 200)
    inner_glow_opacity: float = 0.5
    inner_glow_radius: int = 10

    bevel_emboss: bool = False
    bevel_depth: int = 4
    bevel_opacity: float = 0.55

    color_overlay: bool = False
    color_overlay_color: Tuple[int, int, int] = (49, 168, 255)
    color_overlay_opacity: float = 0.5

    stroke: bool = False
    stroke_color: Tuple[int, int, int] = (255, 255, 255)
    stroke_size: int = 3
    stroke_position: str = "Outside"  # Outside | Inside | Center
    stroke_opacity: float = 1.0

    def has_any(self) -> bool:
        return any([
            self.drop_shadow, self.inner_shadow, self.outer_glow,
            self.inner_glow, self.bevel_emboss, self.color_overlay, self.stroke,
        ])

    def to_dict(self) -> Dict[str, Any]:
        return {k: list(v) if isinstance(v, tuple) else v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LayerStyles":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                if isinstance(getattr(obj, k), tuple) and isinstance(v, list):
                    setattr(obj, k, tuple(v))
                else:
                    setattr(obj, k, v)
        return obj


@dataclass
class SmartFilter:
    uid: str = field(default_factory=new_id)
    name: str = "Gaussian Blur"
    enabled: bool = True
    opacity: float = 1.0
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "enabled": self.enabled,
            "opacity": self.opacity,
            "params": copy.deepcopy(self.params),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SmartFilter":
        return cls(
            uid=d.get("uid", new_id()),
            name=d.get("name", "Gaussian Blur"),
            enabled=d.get("enabled", True),
            opacity=float(d.get("opacity", 1.0)),
            params=copy.deepcopy(d.get("params", {})),
        )


@dataclass
class VectorShapeData:
    shape_type: str = "rectangle"  # rectangle, rounded_rect, ellipse, polygon, star, line, path
    rect: Tuple[float, float, float, float] = (100.0, 100.0, 260.0, 180.0)
    points: List[Tuple[float, float]] = field(default_factory=list)
    closed: bool = True
    corner_radius: float = 18.0
    sides: int = 5
    inner_ratio: float = 0.45
    fill_enabled: bool = True
    fill_color: Tuple[int, int, int, int] = (49, 168, 255, 255)
    stroke_enabled: bool = True
    stroke_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
    stroke_width: float = 3.0
    dashed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shape_type": self.shape_type,
            "rect": list(self.rect),
            "points": [list(p) for p in self.points],
            "closed": self.closed,
            "corner_radius": self.corner_radius,
            "sides": self.sides,
            "inner_ratio": self.inner_ratio,
            "fill_enabled": self.fill_enabled,
            "fill_color": list(self.fill_color),
            "stroke_enabled": self.stroke_enabled,
            "stroke_color": list(self.stroke_color),
            "stroke_width": self.stroke_width,
            "dashed": self.dashed,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VectorShapeData":
        return cls(
            shape_type=d.get("shape_type", "rectangle"),
            rect=tuple(d.get("rect", [100.0, 100.0, 260.0, 180.0])),
            points=[tuple(p) for p in d.get("points", [])],
            closed=d.get("closed", True),
            corner_radius=float(d.get("corner_radius", 18.0)),
            sides=int(d.get("sides", 5)),
            inner_ratio=float(d.get("inner_ratio", 0.45)),
            fill_enabled=d.get("fill_enabled", True),
            fill_color=tuple(d.get("fill_color", [49, 168, 255, 255])),
            stroke_enabled=d.get("stroke_enabled", True),
            stroke_color=tuple(d.get("stroke_color", [255, 255, 255, 255])),
            stroke_width=float(d.get("stroke_width", 3.0)),
            dashed=d.get("dashed", False),
        )


@dataclass
class TextLayerData:
    text: str = "KinoShop Studio"
    x: float = 120.0
    y: float = 120.0
    font_family: str = "Segoe UI"
    font_size: int = 56
    bold: bool = True
    italic: bool = False
    color: Tuple[int, int, int, int] = (240, 245, 255, 255)
    letter_spacing: float = 0.0
    line_height: float = 1.2
    align: str = "left"  # left | center | right
    warp_style: str = "None"
    warp_bend: float = 0.35
    on_path: bool = False
    path_points: List[Tuple[float, float]] = field(default_factory=list)
    box_width: float = 0.0  # >0 means area text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "color": list(self.color),
            "letter_spacing": self.letter_spacing,
            "line_height": self.line_height,
            "align": self.align,
            "warp_style": self.warp_style,
            "warp_bend": self.warp_bend,
            "on_path": self.on_path,
            "path_points": [list(p) for p in self.path_points],
            "box_width": self.box_width,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TextLayerData":
        return cls(
            text=d.get("text", "KinoShop"),
            x=float(d.get("x", 120.0)),
            y=float(d.get("y", 120.0)),
            font_family=d.get("font_family", "Segoe UI"),
            font_size=int(d.get("font_size", 56)),
            bold=bool(d.get("bold", True)),
            italic=bool(d.get("italic", False)),
            color=tuple(d.get("color", [240, 245, 255, 255])),
            letter_spacing=float(d.get("letter_spacing", 0.0)),
            line_height=float(d.get("line_height", 1.2)),
            align=d.get("align", "left"),
            warp_style=d.get("warp_style", "None"),
            warp_bend=float(d.get("warp_bend", 0.35)),
            on_path=bool(d.get("on_path", False)),
            path_points=[tuple(p) for p in d.get("path_points", [])],
            box_width=float(d.get("box_width", 0.0)),
        )


def default_adjustment_params(adj_type: str) -> Dict[str, Any]:
    if adj_type == "Levels":
        return {"in_black": 0, "in_white": 255, "gamma": 1.0, "out_black": 0, "out_white": 255, "channel": "RGB"}
    if adj_type == "Curves":
        return {
            "channel": "RGB",
            "points_rgb": [[0, 0], [64, 64], [128, 128], [192, 192], [255, 255]],
            "points_r": [[0, 0], [255, 255]],
            "points_g": [[0, 0], [255, 255]],
            "points_b": [[0, 0], [255, 255]],
        }
    if adj_type == "Exposure":
        return {"exposure": 0.0, "offset": 0.0, "gamma": 1.0}
    if adj_type == "Hue/Saturation":
        return {"hue": 0, "saturation": 0, "lightness": 0, "colorize": False}
    if adj_type == "Vibrance":
        return {"vibrance": 0, "saturation": 0}
    if adj_type == "Color Balance":
        return {
            "shadows": [0, 0, 0],
            "midtones": [0, 0, 0],
            "highlights": [0, 0, 0],
            "preserve_luminosity": True,
        }
    if adj_type == "Black & White":
        return {"red": 40, "yellow": 60, "green": 40, "cyan": 60, "blue": 20, "magenta": 80, "tint": False}
    if adj_type == "Photo Filter":
        return {"color": [236, 138, 0], "density": 25, "preserve_luminosity": True}
    if adj_type == "Channel Mixer":
        return {"r": [100, 0, 0], "g": [0, 100, 0], "b": [0, 0, 100], "monochrome": False}
    if adj_type == "LUT / Color Lookup":
        return {"preset": "Cinema Teal & Orange", "intensity": 0.75, "lut_path": ""}
    if adj_type == "Posterize":
        return {"levels": 6}
    if adj_type == "Threshold":
        return {"level": 128}
    if adj_type == "Invert":
        return {}
    return {}


@dataclass
class Layer:
    uid: str = field(default_factory=new_id)
    name: str = "Layer"
    kind: str = "raster"  # raster | adjustment | smart_object | vector | text | group | fill
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    fill_opacity: float = 1.0
    blend_mode: str = "Normal"
    clipping_mask: bool = False
    offset_x: int = 0
    offset_y: int = 0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0

    # Pixel image (H, W, 4) uint8 RGBA (document-sized for raster, or original size for smart_object)
    image: Optional[np.ndarray] = None
    # Original immutable source for Smart Objects
    smart_source: Optional[np.ndarray] = None
    # Layer mask (H, W) uint8 [0..255]
    mask: Optional[np.ndarray] = None
    mask_enabled: bool = True

    # Kind-specific payloads
    adjustment_type: str = "Levels"
    adjustment_params: Dict[str, Any] = field(default_factory=dict)
    vector_data: Optional[VectorShapeData] = None
    text_data: Optional[TextLayerData] = None
    fill_data: Dict[str, Any] = field(default_factory=dict)
    children: List["Layer"] = field(default_factory=list)  # for group layers

    # Non-destructive effects
    styles: LayerStyles = field(default_factory=LayerStyles)
    smart_filters: List[SmartFilter] = field(default_factory=list)

    # Variable / Data Set binding name (optional)
    variable_name: str = ""

    # Linked Smart Object fields
    linked_path: str = ""
    linked_mtime: float = 0.0

    # Runtime-only render cache & mutation counter (not serialized)
    _version: int = field(default=0, repr=False, compare=False)
    _cache_key: Any = field(default=None, repr=False, compare=False)
    _cache_val: Any = field(default=None, repr=False, compare=False)

    def invalidate_cache(self) -> None:
        self._version += 1
        self._cache_key = None
        self._cache_val = None

    def clone(self) -> "Layer":
        return Layer(
            uid=self.uid,
            name=self.name,
            kind=self.kind,
            visible=self.visible,
            locked=self.locked,
            opacity=self.opacity,
            fill_opacity=self.fill_opacity,
            blend_mode=self.blend_mode,
            clipping_mask=self.clipping_mask,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            rotation=self.rotation,
            scale_x=self.scale_x,
            scale_y=self.scale_y,
            image=None if self.image is None else self.image.copy(),
            smart_source=None if self.smart_source is None else self.smart_source.copy(),
            mask=None if self.mask is None else self.mask.copy(),
            mask_enabled=self.mask_enabled,
            adjustment_type=self.adjustment_type,
            adjustment_params=copy.deepcopy(self.adjustment_params),
            vector_data=copy.deepcopy(self.vector_data),
            text_data=copy.deepcopy(self.text_data),
            fill_data=copy.deepcopy(self.fill_data),
            children=[c.clone() for c in self.children],
            styles=LayerStyles.from_dict(self.styles.to_dict()),
            smart_filters=[SmartFilter.from_dict(f.to_dict()) for f in self.smart_filters],
            variable_name=self.variable_name,
            linked_path=self.linked_path,
            linked_mtime=self.linked_mtime,
        )


@dataclass
class ExtraChannel:
    uid: str = field(default_factory=new_id)
    name: str = "Alpha 1"
    kind: str = "alpha"  # alpha | spot
    color: Tuple[int, int, int] = (255, 0, 85)
    solidity: float = 0.55
    visible: bool = False
    data: Optional[np.ndarray] = None  # (H, W) uint8

    def clone(self) -> "ExtraChannel":
        return ExtraChannel(
            uid=self.uid,
            name=self.name,
            kind=self.kind,
            color=self.color,
            solidity=self.solidity,
            visible=self.visible,
            data=None if self.data is None else self.data.copy(),
        )


@dataclass
class Artboard:
    uid: str = field(default_factory=new_id)
    name: str = "Artboard 1"
    x: int = 0
    y: int = 0
    width: int = 1280
    height: int = 800

    def to_dict(self) -> Dict[str, Any]:
        return {"uid": self.uid, "name": self.name, "x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Artboard":
        return cls(
            uid=d.get("uid", new_id()),
            name=d.get("name", "Artboard"),
            x=int(d.get("x", 0)),
            y=int(d.get("y", 0)),
            width=int(d.get("width", 1280)),
            height=int(d.get("height", 800)),
        )


@dataclass
class SliceRect:
    uid: str = field(default_factory=new_id)
    name: str = "slice_01"
    x: int = 0
    y: int = 0
    width: int = 256
    height: int = 256
    fmt: str = "PNG"
    scales: List[float] = field(default_factory=lambda: [1.0, 2.0])
    url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "fmt": self.fmt,
            "scales": list(self.scales),
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SliceRect":
        return cls(
            uid=d.get("uid", new_id()),
            name=d.get("name", "slice"),
            x=int(d.get("x", 0)),
            y=int(d.get("y", 0)),
            width=int(d.get("width", 256)),
            height=int(d.get("height", 256)),
            fmt=d.get("fmt", "PNG"),
            scales=list(d.get("scales", [1.0, 2.0])),
            url=d.get("url", ""),
        )


@dataclass
class PrintSettings:
    bleed_mm: float = 3.0
    crop_marks: bool = False
    bleed_marks: bool = False
    registration_marks: bool = False
    color_bars: bool = False
    page_info: bool = False
    soft_proof: bool = False
    soft_proof_profile: str = "U.S. Web Coated (SWOP) v2 [CMYK]"
    gamut_warning: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PrintSettings":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj


@dataclass
class AnimationFrame:
    uid: str = field(default_factory=new_id)
    name: str = "Frame 1"
    duration_ms: int = 120
    layer_visibility: Dict[str, bool] = field(default_factory=dict)
    layer_offsets: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    layer_opacities: Dict[str, float] = field(default_factory=dict)
    # Optional direct raster frame for imported video clips
    video_frame: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "duration_ms": self.duration_ms,
            "layer_visibility": dict(self.layer_visibility),
            "layer_offsets": {k: list(v) for k, v in self.layer_offsets.items()},
            "layer_opacities": dict(self.layer_opacities),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnimationFrame":
        return cls(
            uid=d.get("uid", new_id()),
            name=d.get("name", "Frame"),
            duration_ms=int(d.get("duration_ms", 120)),
            layer_visibility=dict(d.get("layer_visibility", {})),
            layer_offsets={k: tuple(v) for k, v in d.get("layer_offsets", {}).items()},
            layer_opacities={k: float(v) for k, v in d.get("layer_opacities", {}).items()},
        )


@dataclass
class CommentPin:
    uid: str = field(default_factory=new_id)
    author: str = "Studio Artist"
    text: str = ""
    x: float = 100.0
    y: float = 100.0
    resolved: bool = False
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CommentPin":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CountMarker:
    index: int
    x: float
    y: float
    group: str = "Group 1"
    area_px: float = 0.0


@dataclass
class LayerComp:
    """Saved layout variation (Visibility, Position, Appearance) inside one .ksd file."""
    uid: str = field(default_factory=new_id)
    name: str = "Comp 1"
    comment: str = ""
    capture_visibility: bool = True
    capture_position: bool = True
    capture_appearance: bool = True
    layer_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "comment": self.comment,
            "capture_visibility": self.capture_visibility,
            "capture_position": self.capture_position,
            "capture_appearance": self.capture_appearance,
            "layer_states": copy.deepcopy(self.layer_states),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LayerComp":
        return cls(
            uid=d.get("uid", new_id()),
            name=d.get("name", "Comp"),
            comment=d.get("comment", ""),
            capture_visibility=bool(d.get("capture_visibility", True)),
            capture_position=bool(d.get("capture_position", True)),
            capture_appearance=bool(d.get("capture_appearance", True)),
            layer_states=copy.deepcopy(d.get("layer_states", {})),
        )


@dataclass
class DocumentMetadata:
    title: str = ""
    author: str = "KinoSuite Artist"
    copyright_status: str = "Copyrighted"  # Copyrighted | Public Domain | Unknown
    copyright_notice: str = ""
    keywords: str = ""
    description: str = ""
    camera_make: str = ""
    camera_model: str = ""
    lens: str = ""
    iso: str = ""
    aperture: str = ""
    shutter_speed: str = ""
    focal_length: str = ""
    content_credentials_enabled: bool = True
    provenance_log: List[Dict[str, Any]] = field(default_factory=list)

    def record_provenance(self, action: str, tool: str = "KinoShop", ai_used: bool = False, details: str = "") -> None:
        if not self.content_credentials_enabled:
            return
        self.provenance_log.append({
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "tool": tool,
            "ai_generated": bool(ai_used),
            "details": details,
        })

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self.__dict__)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DocumentMetadata":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, copy.deepcopy(v))
        return obj


@dataclass
class HistoryEntry:
    uid: str = field(default_factory=new_id)
    label: str = "New Document"
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime("%H:%M:%S"))
    layers: List[Layer] = field(default_factory=list)
    width: int = 1280
    height: int = 800
    is_snapshot: bool = False
    composite_cache: Optional[np.ndarray] = None


class KinoDocument:
    """Complete KinoShop layered document state."""

    def __init__(
        self,
        width: int = 1280,
        height: int = 800,
        name: str = "Untitled-1.ksd",
        dpi: int = 300,
        color_mode: str = "RGB",
        color_profile: str = "sRGB IEC61966-2.1",
        background: Tuple[int, int, int, int] = (24, 28, 37, 255),
    ) -> None:
        self.uid: str = new_id()
        self.name: str = name
        self.file_path: Optional[str] = None
        self.cloud_id: Optional[str] = None
        self.width: int = int(width)
        self.height: int = int(height)
        self.dpi: int = int(dpi)
        self.color_mode: str = color_mode
        self.bit_depth: int = 8  # 8 or 16
        self.color_profile: str = color_profile
        self.dirty: bool = False

        # Layers (bottom-to-top order: index 0 is bottom, -1 is top)
        self.layers: List[Layer] = []
        self.active_layer_id: Optional[str] = None

        # Channels: R, G, B (or C, M, Y, K) visibility & edit targets
        self.channel_visible: Dict[str, bool] = {"R": True, "G": True, "B": True}
        self.active_channel: str = "Composite"  # Composite | R | G | B | C | M | Y | K | <extra uid>
        self.extra_channels: List[ExtraChannel] = []

        # Selection mask: (H, W) float32 in [0.0, 1.0] or None
        self.selection: Optional[np.ndarray] = None

        # Guides, Artboards, Slices, Print Prep
        self.guides_h: List[float] = []
        self.guides_v: List[float] = []
        self.artboards: List[Artboard] = [Artboard(name="Artboard 1", x=0, y=0, width=self.width, height=self.height)]
        self.slices: List[SliceRect] = []
        self.print_settings: PrintSettings = PrintSettings()

        # Pattern preview toggle
        self.pattern_preview: bool = False

        # Measurement & Scientific Count
        self.pixels_per_unit: float = 100.0
        self.measure_unit: str = "mm"
        self.count_markers: List[CountMarker] = []
        self.ruler_line: Optional[Tuple[float, float, float, float]] = None

        # Timeline / Animation
        self.frames: List[AnimationFrame] = []
        self.current_frame_idx: int = 0
        self.timeline_fps: float = 12.0

        # Variables & Data Sets
        self.variables_map: Dict[str, str] = {}  # layer_uid -> column_name
        self.data_sets: List[Dict[str, str]] = []

        # Collaboration / Comments
        self.comments: List[CommentPin] = []

        # Layer Comps (client layout variations inside one file)
        self.layer_comps: List[LayerComp] = []

        # Metadata & Content Credentials (C2PA-style provenance)
        self.metadata: DocumentMetadata = DocumentMetadata(title=name)
        self.metadata.record_provenance("Created document", details=f"{self.width}x{self.height} {self.color_mode}")

        # History & Snapshots & History Brush source
        self.history: List[HistoryEntry] = []
        self.history_index: int = -1
        self.snapshots: List[HistoryEntry] = []
        self.history_brush_source_id: Optional[str] = None

        # Initialize default Background layer
        bg = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        bg[:, :] = background
        bg_layer = Layer(name="Background", kind="raster", image=bg)
        self.layers.append(bg_layer)
        self.active_layer_id = bg_layer.uid
        self.push_history("New Document", is_snapshot=True)

    # ---- Layer helpers ----
    def iter_all_layers(self, layers: Optional[List[Layer]] = None) -> List[Layer]:
        out: List[Layer] = []
        for lyr in (self.layers if layers is None else layers):
            out.append(lyr)
            if lyr.kind == "group" and lyr.children:
                out.extend(self.iter_all_layers(lyr.children))
        return out

    def get_layer(self, uid: Optional[str]) -> Optional[Layer]:
        if not uid:
            return None
        for lyr in self.iter_all_layers():
            if lyr.uid == uid:
                return lyr
        return None

    def active_layer(self) -> Optional[Layer]:
        lyr = self.get_layer(self.active_layer_id)
        if lyr is None and self.layers:
            self.active_layer_id = self.layers[-1].uid
            return self.layers[-1]
        return lyr

    def ensure_raster_layer(self) -> Layer:
        lyr = self.active_layer()
        if lyr is not None and lyr.kind == "raster" and not lyr.locked:
            if lyr.image is None:
                lyr.image = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            return lyr
        new_img = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        nl = Layer(name=f"Layer {len(self.layers) + 1}", kind="raster", image=new_img)
        self.layers.append(nl)
        self.active_layer_id = nl.uid
        return nl

    def add_raster_layer(self, name: Optional[str] = None, image: Optional[np.ndarray] = None) -> Layer:
        if image is None:
            image = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        elif image.shape[0] != self.height or image.shape[1] != self.width:
            canvas = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            h = min(self.height, image.shape[0])
            w = min(self.width, image.shape[1])
            canvas[:h, :w] = image[:h, :w]
            image = canvas
        nl = Layer(name=name or f"Layer {len(self.layers) + 1}", kind="raster", image=image)
        self.layers.append(nl)
        self.active_layer_id = nl.uid
        self.dirty = True
        return nl

    def add_adjustment_layer(self, adj_type: str, params: Optional[Dict[str, Any]] = None) -> Layer:
        p = default_adjustment_params(adj_type)
        if params:
            p.update(params)
        nl = Layer(
            name=f"{adj_type} 1",
            kind="adjustment",
            adjustment_type=adj_type,
            adjustment_params=p,
        )
        self.layers.append(nl)
        self.active_layer_id = nl.uid
        self.dirty = True
        return nl

    def add_text_layer(self, text: str = "KinoShop", x: float = 120, y: float = 140, **kwargs: Any) -> Layer:
        td = TextLayerData(text=text, x=x, y=y, **kwargs)
        nl = Layer(name=text[:24] or "Type Layer", kind="text", text_data=td)
        self.layers.append(nl)
        self.active_layer_id = nl.uid
        self.dirty = True
        return nl

    def add_vector_layer(self, shape_type: str = "rectangle", **kwargs: Any) -> Layer:
        vd = VectorShapeData(shape_type=shape_type, **kwargs)
        nl = Layer(name=f"{shape_type.replace('_', ' ').title()} 1", kind="vector", vector_data=vd)
        self.layers.append(nl)
        self.active_layer_id = nl.uid
        self.dirty = True
        return nl

    def add_group_layer(self, name: str = "Group 1") -> Layer:
        nl = Layer(name=name, kind="group", children=[])
        self.layers.append(nl)
        self.active_layer_id = nl.uid
        self.dirty = True
        return nl

    def add_mask_to_active(self, fill: int = 255) -> Optional[Layer]:
        lyr = self.active_layer()
        if not lyr:
            return None
        if self.selection is not None:
            lyr.mask = np.clip(self.selection * 255.0, 0, 255).astype(np.uint8)
        else:
            lyr.mask = np.full((self.height, self.width), fill, dtype=np.uint8)
        lyr.mask_enabled = True
        self.dirty = True
        return lyr

    def remove_layer(self, uid: str) -> bool:
        def _rm(lst: List[Layer]) -> bool:
            for i, lyr in enumerate(lst):
                if lyr.uid == uid:
                    lst.pop(i)
                    return True
                if lyr.children and _rm(lyr.children):
                    return True
            return False

        if len(self.layers) <= 1 and self.layers[0].uid == uid:
            return False
        ok = _rm(self.layers)
        if ok:
            if self.active_layer_id == uid:
                self.active_layer_id = self.layers[-1].uid if self.layers else None
            self.dirty = True
        return ok

    # ---- History & Snapshots ----
    def push_history(self, label: str, is_snapshot: bool = False, max_states: int = 40) -> HistoryEntry:
        entry = HistoryEntry(
            label=label,
            layers=[l.clone() for l in self.layers],
            width=self.width,
            height=self.height,
            is_snapshot=is_snapshot,
        )
        if is_snapshot:
            self.snapshots.append(entry)
            if self.history_brush_source_id is None:
                self.history_brush_source_id = entry.uid
            if not self.history:
                self.history.append(entry)
                self.history_index = 0
            return entry

        # Truncate redo branch
        if self.history_index < len(self.history) - 1:
            self.history = self.history[: self.history_index + 1]
        self.history.append(entry)
        if len(self.history) > max_states:
            self.history.pop(0)
        self.history_index = len(self.history) - 1
        if self.history_brush_source_id is None:
            self.history_brush_source_id = self.history[0].uid
        self.dirty = True
        return entry

    def restore_history_entry(self, entry: HistoryEntry) -> None:
        self.layers = [l.clone() for l in entry.layers]
        self.width = entry.width
        self.height = entry.height
        if self.selection is not None and self.selection.shape != (self.height, self.width):
            self.selection = None
        if not self.get_layer(self.active_layer_id) and self.layers:
            self.active_layer_id = self.layers[-1].uid

    def undo(self) -> bool:
        if self.history_index > 0:
            self.history_index -= 1
            self.restore_history_entry(self.history[self.history_index])
            return True
        return False

    def redo(self) -> bool:
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.restore_history_entry(self.history[self.history_index])
            return True
        return False

    def get_history_brush_source(self) -> Optional[HistoryEntry]:
        for s in self.snapshots:
            if s.uid == self.history_brush_source_id:
                return s
        for h in self.history:
            if h.uid == self.history_brush_source_id:
                return h
        return self.snapshots[0] if self.snapshots else (self.history[0] if self.history else None)

    # ---- Channels ----
    def set_color_mode(self, mode: str) -> None:
        self.color_mode = mode
        if mode == "CMYK":
            self.channel_visible = {"C": True, "M": True, "Y": True, "K": True}
        elif mode == "Grayscale":
            self.channel_visible = {"Gray": True}
        elif mode == "Lab":
            self.channel_visible = {"L": True, "a": True, "b": True}
        else:
            self.channel_visible = {"R": True, "G": True, "B": True}
        self.active_channel = "Composite"

    def save_selection_as_alpha(self, name: Optional[str] = None) -> ExtraChannel:
        if self.selection is not None:
            data = np.clip(self.selection * 255.0, 0, 255).astype(np.uint8)
        else:
            data = np.zeros((self.height, self.width), dtype=np.uint8)
        ch = ExtraChannel(
            name=name or f"Alpha {len(self.extra_channels) + 1}",
            kind="alpha",
            color=(255, 45, 85),
            solidity=0.5,
            visible=False,
            data=data,
        )
        self.extra_channels.append(ch)
        return ch

    def add_spot_channel(self, name: str = "Spot Pantone Cyan", color: Tuple[int, int, int] = (0, 174, 239)) -> ExtraChannel:
        data = np.zeros((self.height, self.width), dtype=np.uint8)
        if self.selection is not None:
            data = np.clip(self.selection * 255.0, 0, 255).astype(np.uint8)
        ch = ExtraChannel(name=name, kind="spot", color=color, solidity=0.85, visible=True, data=data)
        self.extra_channels.append(ch)
        return ch

    # ---- Bleed conversion ----
    def bleed_px(self) -> int:
        return max(0, int(round(self.print_settings.bleed_mm / 25.4 * self.dpi)))

    # ---- Layer Comps ----
    def capture_layer_comp(
        self,
        name: str,
        comment: str = "",
        capture_visibility: bool = True,
        capture_position: bool = True,
        capture_appearance: bool = True,
    ) -> LayerComp:
        states: Dict[str, Dict[str, Any]] = {}
        for lyr in self.iter_all_layers():
            states[lyr.uid] = {
                "visible": lyr.visible,
                "offset_x": lyr.offset_x,
                "offset_y": lyr.offset_y,
                "opacity": lyr.opacity,
                "blend_mode": lyr.blend_mode,
                "styles": lyr.styles.to_dict(),
            }
        comp = LayerComp(
            name=name,
            comment=comment,
            capture_visibility=capture_visibility,
            capture_position=capture_position,
            capture_appearance=capture_appearance,
            layer_states=states,
        )
        self.layer_comps.append(comp)
        self.dirty = True
        return comp

    def apply_layer_comp(self, comp: LayerComp) -> None:
        for lyr in self.iter_all_layers():
            st = comp.layer_states.get(lyr.uid)
            if not st:
                continue
            if comp.capture_visibility and "visible" in st:
                lyr.visible = bool(st["visible"])
            if comp.capture_position:
                if "offset_x" in st:
                    lyr.offset_x = int(st["offset_x"])
                if "offset_y" in st:
                    lyr.offset_y = int(st["offset_y"])
            if comp.capture_appearance:
                if "opacity" in st:
                    lyr.opacity = float(st["opacity"])
                if "blend_mode" in st:
                    lyr.blend_mode = str(st["blend_mode"])
                if "styles" in st:
                    lyr.styles = LayerStyles.from_dict(st["styles"])
        self.dirty = True

