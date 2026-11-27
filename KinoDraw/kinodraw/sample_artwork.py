"""Starter showcase documents & templates for KinoDraw (KinoSuite)."""
from __future__ import annotations

import math
from .models import (
    AnchorPoint,
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Artboard,
    Color,
    Document,
    FreeformPoint,
    GradientDef,
    GradientStop,
    Layer,
    LiveEffect,
    PatternDef,
    SubPath,
    TextStyle,
    VectorObject,
    WidthStation,
)


def create_showcase_document() -> Document:
    """Create a rich multi-artboard KinoSuite showcase demonstrating KinoDraw's capabilities."""
    doc = Document(
        name="KinoSuite_Brand_Showcase.kdrw",
        color_mode="RGB",
        bleed=14.0,
        show_crop_marks=True,
        artboards=[
            Artboard(name="Brand Poster", x=0, y=0, width=1080, height=740, bg_color=Color.from_hex("#0F131C")),
            Artboard(name="Infographic & Mockup", x=1160, y=0, width=960, height=740, bg_color=Color.from_hex("#F8FAFC")),
        ],
    )
    lyr_bg = doc.layers[0]
    lyr_bg.name = "Backdrop & Gradients"
    lyr_bg.color_tag = "#3B82F6"
    lyr_art = Layer(name="Vector Artwork & 3D", color_tag="#FF9A00")
    lyr_type = Layer(name="Typography & Charts", color_tag="#06D6A0")
    doc.layers.extend([lyr_art, lyr_type])
    doc.active_layer_id = lyr_art.id

    # --- Artboard 1: Brand Poster ---
    # 1. Freeform gradient hero glow card
    hero_card = VectorObject(
        name="Freeform Aurora Card", kind="shape", shape_type="rect",
        x=48, y=48, width=984, height=644, corner_radius=28,
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="gradient", gradient=GradientDef(
                kind="freeform",
                freeform_points=[
                    FreeformPoint(0.18, 0.22, Color.from_hex("#1B2440"), 0.55),
                    FreeformPoint(0.82, 0.24, Color.from_hex("#4C1D95"), 0.52),
                    FreeformPoint(0.74, 0.80, Color.from_hex("#B45309"), 0.50),
                    FreeformPoint(0.22, 0.82, Color.from_hex("#0F172A"), 0.55),
                ],
            ))],
            strokes=[AppearanceStroke(stroke_type="solid", color=Color(255, 255, 255, 48), width=1.5)],
        ),
    )
    doc.add_object(hero_card, lyr_bg.id)

    # 2. Pattern fill accent strip
    pat_strip = VectorObject(
        name="Art Deco Accent Strip", kind="shape", shape_type="rect",
        x=48, y=580, width=984, height=112, corner_radius=0,
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="pattern", pattern=PatternDef(
                name="Kino Art Deco", kind="art_deco", tile_size=40.0,
                bg_color=Color(15, 19, 28, 175), fg_color=Color.from_hex("#FF9A00"), accent_color=Color.from_hex("#00C2FF"),
            ))],
            strokes=[AppearanceStroke(stroke_type="none")],
            opacity=0.65,
        ),
    )
    doc.add_object(pat_strip, lyr_bg.id)

    # 3. 3D Extruded Hero Emblem
    emblem = VectorObject(
        name="3D Hex Emblem", kind="shape", shape_type="polygon", sides=6,
        x=720, y=155, width=220, height=220,
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="solid", color=Color.from_hex("#FF9A00"))],
            strokes=[AppearanceStroke(stroke_type="none")],
            effects=[LiveEffect(kind="extrude_3d", params={"depth": 34, "angle_x": -22, "angle_y": 26, "material": "glossy"})],
        ),
    )
    doc.add_object(emblem, lyr_art.id)

    # 4. Variable-width calligraphic wave ribbon
    wave_sp = SubPath(closed=False, anchors=[
        AnchorPoint(90, 470, 90, 470, 210, 385, "smooth"),
        AnchorPoint(340, 455, 270, 520, 420, 390, "smooth"),
        AnchorPoint(565, 445, 490, 515, 650, 420, "smooth"),
    ])
    wave_obj = VectorObject(
        name="Variable Width Ribbon", kind="path", subpaths=[wave_sp],
        appearance=Appearance(
            fills=[AppearanceFill(fill_type="none")],
            strokes=[AppearanceStroke(
                stroke_type="gradient",
                gradient=GradientDef(kind="linear", angle=0, stroke_mode="along", stops=[
                    GradientStop(0.0, Color.from_hex("#00C2FF")),
                    GradientStop(0.5, Color.from_hex("#FF9A00")),
                    GradientStop(1.0, Color.from_hex("#FF2E63")),
                ]),
                width=22.0,
                width_profile_name="Width Profile 1 (Elliptical)",
            )],
        ),
    )
    doc.add_object(wave_obj, lyr_art.id)

    # 5. Live Blend between two shapes
    b1 = VectorObject(
        name="Blend Start", kind="shape", shape_type="ellipse",
        x=95, y=500, width=48, height=48,
        appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#00C2FF"))], strokes=[AppearanceStroke(stroke_type="none")]),
    )
    b2 = VectorObject(
        name="Blend End", kind="shape", shape_type="star", sides=5, inner_radius_ratio=0.45,
        x=360, y=500, width=54, height=54,
        appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#FF9A00"))], strokes=[AppearanceStroke(stroke_type="none")]),
    )
    blend = VectorObject(name="Shape & Color Blend", kind="blend", blend_steps=6, children=[b1, b2])
    doc.add_object(blend, lyr_art.id)

    # 6. Radial Repeat ornament
    petal = VectorObject(
        name="Petal", kind="shape", shape_type="ellipse",
        x=0, y=0, width=22, height=42,
        appearance=Appearance(
            fills=[AppearanceFill(color=Color(0, 194, 255, 190))],
            strokes=[AppearanceStroke(color=Color(255, 255, 255, 180), width=1.2)],
        ),
    )
    radial = VectorObject(
        name="Radial Repeat Rosette", kind="repeat", repeat_mode="radial",
        x=835, y=515, repeat_count=10, repeat_radius=54.0, children=[petal],
    )
    doc.add_object(radial, lyr_art.id)

    # 7. Typography: Hero Headline + Subhead + Type on a Path
    title = VectorObject(
        name="Hero Title", kind="text", text_mode="point", text="KINODRAW",
        x=92, y=126,
        text_style=TextStyle(font_family="Segoe UI", font_size=68, font_weight=800, tracking=2.5),
        appearance=Appearance(
            fills=[AppearanceFill(color=Color.from_hex("#FFFFFF"))],
            strokes=[AppearanceStroke(stroke_type="none")],
            effects=[LiveEffect(kind="drop_shadow", params={"dx": 0, "dy": 8, "blur": 16, "color": "#000000", "opacity": 0.45})],
        ),
    )
    sub = VectorObject(
        name="Suite Subtitle", kind="text", text_mode="point",
        text="KINOSUITE VECTOR STUDIO  •  BEZIER, 3D, PRINT & SCREEN",
        x=94, y=214,
        text_style=TextStyle(font_family="Segoe UI", font_size=13.5, font_weight=700, tracking=1.4),
        appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#FF9A00"))], strokes=[AppearanceStroke(stroke_type="none")]),
    )
    area_copy = VectorObject(
        name="Editorial Body", kind="text", text_mode="area",
        text="Precision Bezier paths, Pathfinder & Shape Builder, Freeform & Mesh Gradients, Live Appearance stacks, CMYK Print Separations, Image Trace, and Studio Product Mockups — unified in the KinoSuite workspace.",
        x=94, y=258, width=520, height=130,
        text_style=TextStyle(font_family="Segoe UI", font_size=15, font_weight=400, leading=1.5),
        appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#CBD5E1"))], strokes=[AppearanceStroke(stroke_type="none")]),
    )
    # Type on a Path around top arc
    arc_pts = []
    for i in range(9):
        ang = math.radians(-160 + i * 17.5)
        arc_pts.append(AnchorPoint(830 + 132 * math.cos(ang), 265 + 132 * math.sin(ang)))
    top_text = VectorObject(
        name="Curved Badge Text", kind="text", text_mode="path",
        text="•  KINOSUITE EDITION  •  VECTOR STUDIO  •",
        subpaths=[SubPath(anchors=arc_pts, closed=False)],
        text_style=TextStyle(font_family="Segoe UI", font_size=14, font_weight=700, tracking=2.2),
        appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#00C2FF"))], strokes=[AppearanceStroke(stroke_type="none")]),
    )
    doc.add_object(title, lyr_type.id)
    doc.add_object(sub, lyr_type.id)
    doc.add_object(area_copy, lyr_type.id)
    doc.add_object(top_text, lyr_type.id)

    # --- Artboard 2: Infographic & Product Mockup ---
    chart = VectorObject(
        name="Studio Performance Chart", kind="graph", graph_type="bar",
        graph_title="KinoSuite Asset Pipeline (Q1–Q4)",
        x=1210, y=64, width=440, height=300,
    )
    pie = VectorObject(
        name="Deliverables Mix", kind="graph", graph_type="pie",
        graph_title="Export Formats Share",
        graph_headers=["SVG", "PDF", "PNG", "WebP"],
        graph_series=[{"name": "Share", "values": [40, 25, 22, 13], "color": "#FF9A00"}],
        x=1210, y=390, width=440, height=290,
    )
    # Product Mockup (Ceramic Mug with KinoDraw star emblem)
    mug_art = VectorObject(
        name="Mug Emblem", kind="shape", shape_type="star", sides=8, inner_radius_ratio=0.52,
        x=0, y=0, width=120, height=120,
        appearance=Appearance(
            fills=[AppearanceFill(color=Color.from_hex("#FF9A00"))],
            strokes=[AppearanceStroke(color=Color.from_hex("#181C24"), width=4.0)],
        ),
    )
    mockup = VectorObject(
        name="KinoSuite Mug Mockup", kind="mockup", mockup_preset="mug",
        mockup_color=Color.from_hex("#F4F4F6"),
        x=1690, y=130, width=380, height=440,
        mockup_art_scale=0.62,
        children=[mug_art],
    )
    doc.add_object(chart, lyr_type.id)
    doc.add_object(pie, lyr_type.id)
    doc.add_object(mockup, lyr_art.id)

    doc.save_version("Initial Showcase Snapshot")
    doc.dirty = False
    return doc


def create_blank_document(name: str = "Untitled-1", width: float = 1280.0, height: float = 800.0,
                          color_mode: str = "RGB", artboards: int = 1, bleed: float = 0.0) -> Document:
    abs_list = []
    for i in range(max(1, artboards)):
        abs_list.append(Artboard(name=f"Artboard {i + 1}", x=i * (width + 80), y=0, width=width, height=height))
    doc = Document(name=name, color_mode=color_mode, bleed=bleed, show_crop_marks=(bleed > 0), artboards=abs_list)
    doc.save_version("Created Document")
    doc.dirty = False
    return doc
