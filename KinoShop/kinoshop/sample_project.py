"""Rich built-in multi-layered KinoShop studio showcase document."""
from __future__ import annotations

import math
import cv2
import numpy as np

from .models import (
    CommentPin,
    KinoDocument,
    Layer,
    LayerStyles,
    SliceRect,
    SmartFilter,
    TextLayerData,
    VectorShapeData,
)
from .photo_ops import generate_procedural_sky


def create_sample_studio_document() -> KinoDocument:
    """Create a rich, realistic layered showcase document demonstrating KinoShop capabilities."""
    w, h = 1280, 800
    doc = KinoDocument(width=w, height=h, name="KinoShop_Alpine_Poster.ksd", dpi=300, color_mode="RGB")
    doc.layers.clear()

    # 1. Atmospheric Sky & Mountain Photo Layer
    sky = generate_procedural_sky(w, h, "Golden Hour Sunset", seed=21)
    photo = np.dstack([sky, np.full((h, w), 255, dtype=np.uint8)])

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # Distant misty alpine range
    ridge1 = h * 0.56 - 95 * np.exp(-((xx - w * 0.28) / 210.0) ** 2) - 130 * np.exp(-((xx - w * 0.72) / 240.0) ** 2) - 35 * np.sin(xx * 0.012)
    mask_r1 = yy >= ridge1
    photo[mask_r1, :3] = np.clip(
        np.stack([
            42 + (yy[mask_r1] - ridge1[mask_r1]) * 0.06,
            50 + (yy[mask_r1] - ridge1[mask_r1]) * 0.07,
            78 + (yy[mask_r1] - ridge1[mask_r1]) * 0.09,
        ], axis=-1),
        0,
        255,
    ).astype(np.uint8)

    # Foreground dark slate mountain & reflective lake
    ridge2 = h * 0.68 - 70 * np.exp(-((xx - w * 0.16) / 170.0) ** 2) - 85 * np.exp(-((xx - w * 0.85) / 190.0) ** 2) - 18 * np.cos(xx * 0.025)
    mask_r2 = (yy >= ridge2) & (yy < h * 0.76)
    photo[mask_r2, :3] = (20, 26, 38)

    # Reflective alpine lake
    lake_y = int(h * 0.76)
    refl = photo[lake_y - (h - lake_y) : lake_y, :, :3][::-1].astype(np.float32)
    rip = (np.sin(yy[lake_y:] * 0.65 + xx[lake_y:] * 0.03) * 8.0)[..., None]
    lake = np.clip(refl * 0.55 + np.array([14, 28, 48], np.float32) * 0.45 + rip, 0, 255).astype(np.uint8)
    photo[lake_y:, :, :3] = lake

    bg_layer = Layer(name="Alpine Landscape Photo", kind="raster", image=photo)
    doc.layers.append(bg_layer)

    # 2. Smart Object Subject Emblem (Glowing geometric prism in center-right)
    prism = np.zeros((h, w, 4), dtype=np.uint8)
    cx, cy = int(w * 0.68), int(h * 0.44)
    pts_outer = np.array([[cx, cy - 130], [cx + 125, cy + 85], [cx - 125, cy + 85]], np.int32)
    pts_inner = np.array([[cx, cy - 72], [cx + 72, cy + 52], [cx - 72, cy + 52]], np.int32)
    cv2.fillConvexPoly(prism, pts_outer, (32, 168, 255, 220), cv2.LINE_AA)
    cv2.fillConvexPoly(prism, pts_inner, (255, 232, 175, 235), cv2.LINE_AA)
    cv2.polylines(prism, [pts_outer], True, (255, 255, 255, 255), 4, cv2.LINE_AA)
    so_layer = Layer(
        name="Prism Smart Object",
        kind="smart_object",
        smart_source=prism,
        blend_mode="Screen",
        opacity=0.88,
        styles=LayerStyles(outer_glow=True, outer_glow_color=(49, 168, 255), outer_glow_radius=18, outer_glow_opacity=0.8),
        smart_filters=[SmartFilter(name="Gaussian Blur", enabled=False, params={"radius": 3.0})],
    )
    doc.layers.append(so_layer)

    # 3. Vector Accent Card
    card_layer = Layer(
        name="Accent Frame",
        kind="vector",
        vector_data=VectorShapeData(
            shape_type="rounded_rect",
            rect=(74.0, 96.0, 470.0, 220.0),
            corner_radius=18.0,
            fill_enabled=True,
            fill_color=(16, 22, 34, 175),
            stroke_enabled=True,
            stroke_color=(49, 168, 255, 225),
            stroke_width=2.5,
        ),
        styles=LayerStyles(drop_shadow=True, drop_shadow_blur=18, drop_shadow_distance=10, drop_shadow_opacity=0.55),
    )
    doc.layers.append(card_layer)

    # 4. Styled Typography Layers
    title_layer = Layer(
        name="KINOSHOP Title",
        kind="text",
        text_data=TextLayerData(
            text="KINOSHOP",
            x=108.0,
            y=188.0,
            font_family="Segoe UI",
            font_size=64,
            bold=True,
            color=(244, 248, 255, 255),
            letter_spacing=4.0,
        ),
        styles=LayerStyles(drop_shadow=True, drop_shadow_blur=10, drop_shadow_distance=4, drop_shadow_opacity=0.7),
        variable_name="Headline",
    )
    doc.layers.append(title_layer)

    sub_layer = Layer(
        name="Subtitle",
        kind="text",
        text_data=TextLayerData(
            text="KinoSuite Photo & Design Studio\nNon-Destructive Layers · AI · Print Prep",
            x=110.0,
            y=238.0,
            font_family="Segoe UI",
            font_size=18,
            bold=False,
            color=(140, 210, 255, 255),
            line_height=1.35,
        ),
        variable_name="Subtitle",
    )
    doc.layers.append(sub_layer)

    # 5. Non-Destructive Adjustment Layer (Subtle Cinema LUT)
    lut_layer = Layer(
        name="Cinema Grade LUT",
        kind="adjustment",
        adjustment_type="LUT / Color Lookup",
        adjustment_params={"preset": "Cinema Teal & Orange", "intensity": 0.32, "lut_path": ""},
        opacity=0.85,
    )
    doc.layers.append(lut_layer)

    doc.active_layer_id = bg_layer.uid

    # Add sample Slices, Layer Comps & Review Comment
    doc.slices = [
        SliceRect(name="hero_banner", x=0, y=0, width=1280, height=400, fmt="PNG", scales=[1.0, 2.0]),
        SliceRect(name="title_card", x=70, y=90, width=480, height=235, fmt="PNG", scales=[1.0, 2.0]),
    ]
    doc.comments = [
        CommentPin(author="Art Director", text="Try Sky Replacement or Harmonize on the Alpine photo!", x=870, y=260),
    ]
    doc.capture_layer_comp("Default Poster", "Full editorial layout with Cinema LUT")
    lut_layer.visible = False
    card_layer.visible = False
    doc.capture_layer_comp("Clean Photo Only", "Without title card or LUT grade")
    lut_layer.visible = True
    card_layer.visible = True

    doc.history.clear()
    doc.snapshots.clear()
    doc.history_index = -1
    doc.push_history("Opened Sample Project", is_snapshot=True)
    doc.dirty = False
    return doc
