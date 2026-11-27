"""Example third-party KinoShop Extension plugin: Analog Film Halation."""
from __future__ import annotations

import cv2
import numpy as np
from kinoshop.plugins_builtin import KinoPlugin


def _apply_halation(rgba: np.ndarray, params: dict) -> np.ndarray:
    thresh = int(params.get("threshold", 205))
    strength = float(params.get("strength", 0.45))
    rgb = rgba[..., :3].astype(np.float32)
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    bright = np.where(luma > thresh, luma - thresh, 0.0)
    glow = cv2.GaussianBlur(bright, (0, 0), 14.0)
    out = rgb.copy()
    out[..., 0] = np.clip(out[..., 0] + glow * strength * 2.2, 0, 255)
    out[..., 1] = np.clip(out[..., 1] + glow * strength * 0.65, 0, 255)
    return np.dstack([out.astype(np.uint8), rgba[..., 3]])


def register_plugin() -> KinoPlugin:
    return KinoPlugin(
        plugin_id="community.film_halation",
        name="Film Halation Glow",
        category="Artistic / Film",
        version="1.0",
        author="Community SDK",
        description="Adds realistic warm red-orange 35mm film halation bloom around bright highlights.",
        run=_apply_halation,
        default_params={"threshold": 205, "strength": 0.45},
    )
