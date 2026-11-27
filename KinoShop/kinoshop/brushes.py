"""Pressure-sensitive Painting, Mixer Brush, Eraser, Retouching, Clone, Gradient & Symmetry engine."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class BrushSettings:
    preset: str = "Soft Round"  # Soft Round | Hard Round | Chalk | Calligraphy | Spatter | Mixer | Custom
    size: float = 36.0
    hardness: float = 0.65
    opacity: float = 1.0
    flow: float = 0.85
    spacing: float = 0.22
    scatter: float = 0.0
    angle: float = 0.0
    pressure_size: bool = True
    pressure_opacity: bool = False
    # Mixer brush dynamics
    wetness: float = 0.55
    load: float = 0.45
    mix: float = 0.60
    # Symmetry: None | Vertical | Horizontal | Dual | Radial4 | Radial8
    symmetry: str = "None"
    # Custom captured brush tip (float32 0..1 mask)
    custom_tip: Optional[np.ndarray] = None
    # Active mixer reservoir color (float32 RGB 0..1)
    mixer_reservoir: Optional[np.ndarray] = None


def make_brush_dab(
    radius: float,
    hardness: float,
    preset: str = "Soft Round",
    angle: float = 0.0,
    custom_tip: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Generate a (D, D) float32 brush dab mask in [0, 1]."""
    r = max(1.0, float(radius))
    dim = max(3, int(math.ceil(r * 2.0)) | 1)
    if preset == "Custom" and custom_tip is not None and custom_tip.size > 0:
        dab = cv2.resize(custom_tip.astype(np.float32), (dim, dim), interpolation=cv2.INTER_AREA)
        return np.clip(dab, 0.0, 1.0)

    yy, xx = np.mgrid[0:dim, 0:dim].astype(np.float32)
    c = (dim - 1) * 0.5
    dx = (xx - c) / max(r, 1.0)
    dy = (yy - c) / max(r, 1.0)

    if preset == "Calligraphy":
        rad = math.radians(angle + 35.0)
        rx = dx * math.cos(rad) + dy * math.sin(rad)
        ry = (-dx * math.sin(rad) + dy * math.cos(rad)) * 3.6
        dist = np.sqrt(rx * rx + ry * ry)
        dab = np.clip((1.0 - dist) * 5.0, 0.0, 1.0)
        return dab.astype(np.float32)

    dist = np.sqrt(dx * dx + dy * dy)
    if preset == "Hard Round":
        h_eff = max(0.88, hardness)
    else:
        h_eff = np.clip(hardness, 0.0, 0.99)

    if h_eff >= 0.98:
        dab = (dist <= 1.0).astype(np.float32)
    else:
        t = np.clip((dist - h_eff) / max(1.0 - h_eff, 1e-4), 0.0, 1.0)
        # Smooth Hermite falloff
        dab = 1.0 - (t * t * (3.0 - 2.0 * t))
        dab = np.where(dist <= 1.0, dab, 0.0)

    if preset == "Chalk":
        rng = np.random.default_rng(dim * 13 + 7)
        grain = rng.uniform(0.35, 1.0, (dim, dim)).astype(np.float32)
        dab = dab * grain
    elif preset == "Spatter":
        rng = np.random.default_rng(dim * 31 + 3)
        speck = (rng.random((dim, dim)) > 0.62).astype(np.float32)
        dab = dab * speck

    return np.clip(dab, 0.0, 1.0).astype(np.float32)


def symmetry_points(x: float, y: float, width: int, height: int, mode: str) -> List[Tuple[float, float]]:
    pts = [(x, y)]
    if mode == "None":
        return pts
    cx, cy = width * 0.5, height * 0.5
    if mode == "Vertical":
        pts.append((width - x, y))
    elif mode == "Horizontal":
        pts.append((x, height - y))
    elif mode == "Dual":
        pts.extend([(width - x, y), (x, height - y), (width - x, height - y)])
    elif mode in ("Radial4", "Radial8"):
        n = 4 if mode == "Radial4" else 8
        dx, dy = x - cx, y - cy
        for k in range(1, n):
            a = 2.0 * math.pi * k / n
            pts.append((cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)))
    return pts


def _roi_slices(cx: int, cy: int, dim: int, w: int, h: int):
    half = dim // 2
    x0, y0 = cx - half, cy - half
    x1, y1 = x0 + dim, y0 + dim
    ix0, iy0 = max(0, x0), max(0, y0)
    ix1, iy1 = min(w, x1), min(h, y1)
    if ix0 >= ix1 or iy0 >= iy1:
        return None
    dx0, dy0 = ix0 - x0, iy0 - y0
    dx1, dy1 = dx0 + (ix1 - ix0), dy0 + (iy1 - iy0)
    return (iy0, iy1, ix0, ix1, dy0, dy1, dx0, dx1)


def stamp_paint_dab(
    target: np.ndarray,
    x: float,
    y: float,
    color_rgb: Tuple[int, int, int],
    settings: BrushSettings,
    pressure: float = 1.0,
    mode: str = "brush",  # brush | eraser | mixer | dodge | burn | blur | smudge | clone | history | mask_paint
    selection: Optional[np.ndarray] = None,
    clone_source: Optional[np.ndarray] = None,
    clone_offset: Tuple[int, int] = (0, 0),
    history_source: Optional[np.ndarray] = None,
    prev_pos: Optional[Tuple[float, float]] = None,
) -> None:
    """Apply a single brush dab (with symmetry and selection clipping) directly onto target RGBA or grayscale mask."""
    h, w = target.shape[:2]
    is_mask = target.ndim == 2

    eff_size = settings.size * (0.25 + 0.75 * pressure if settings.pressure_size else 1.0)
    eff_op = settings.opacity * settings.flow * (pressure if settings.pressure_opacity else 1.0)
    radius = max(1.0, eff_size * 0.5)
    dab = make_brush_dab(radius, settings.hardness, settings.preset, settings.angle, settings.custom_tip)
    dim = dab.shape[0]
    col_f = np.array(color_rgb, dtype=np.float32) / 255.0

    for px, py in symmetry_points(x, y, w, h, settings.symmetry):
        if settings.scatter > 0.01:
            rng = np.random.default_rng()
            px += rng.normal(0, settings.scatter * radius)
            py += rng.normal(0, settings.scatter * radius)

        roi = _roi_slices(int(round(px)), int(round(py)), dim, w, h)
        if roi is None:
            continue
        iy0, iy1, ix0, ix1, dy0, dy1, dx0, dx1 = roi
        m = dab[dy0:dy1, dx0:dx1] * eff_op
        if selection is not None and selection.shape == (h, w):
            m = m * selection[iy0:iy1, ix0:ix1]
        if float(m.max()) < 1e-4:
            continue

        if is_mask:
            val = float(color_rgb[0])
            dst = target[iy0:iy1, ix0:ix1].astype(np.float32)
            target[iy0:iy1, ix0:ix1] = np.clip(dst * (1.0 - m) + val * m, 0, 255).astype(np.uint8)
            continue

        patch = target[iy0:iy1, ix0:ix1].astype(np.float32) / 255.0

        if mode == "eraser":
            patch[..., 3] = np.clip(patch[..., 3] * (1.0 - m), 0.0, 1.0)
        elif mode == "brush":
            sa = m[..., None]
            da = patch[..., 3:4]
            out_a = sa + da * (1.0 - sa)
            out_rgb = (col_f * sa + patch[..., :3] * da * (1.0 - sa)) / np.maximum(out_a, 1e-6)
            patch[..., :3] = np.clip(out_rgb, 0.0, 1.0)
            patch[..., 3:4] = np.clip(out_a, 0.0, 1.0)
        elif mode == "mixer":
            # Wet Mixer Brush: picks up paint from canvas & blends with reservoir!
            valid = patch[..., 3] > 0.05
            if np.any(valid):
                picked = patch[..., :3][valid].mean(axis=0)
            else:
                picked = col_f
            if settings.mixer_reservoir is None:
                settings.mixer_reservoir = col_f.copy()
            # Mix reservoir with picked canvas paint
            settings.mixer_reservoir = (
                settings.mixer_reservoir * (1.0 - settings.wetness * 0.45)
                + picked * (settings.wetness * 0.45)
            )
            paint_col = settings.mixer_reservoir * (1.0 - settings.load * 0.35) + col_f * (settings.load * 0.35)
            sa = (m * settings.mix)[..., None]
            da = patch[..., 3:4]
            out_a = sa + da * (1.0 - sa)
            out_rgb = (paint_col * sa + patch[..., :3] * da * (1.0 - sa)) / np.maximum(out_a, 1e-6)
            patch[..., :3] = np.clip(out_rgb, 0.0, 1.0)
            patch[..., 3:4] = np.clip(out_a, 0.0, 1.0)
        elif mode == "dodge":
            patch[..., :3] = np.clip(patch[..., :3] + m[..., None] * 0.22 * (1.0 - patch[..., :3] * 0.3), 0.0, 1.0)
        elif mode == "burn":
            patch[..., :3] = np.clip(patch[..., :3] * (1.0 - m[..., None] * 0.22), 0.0, 1.0)
        elif mode == "blur":
            blurred = cv2.GaussianBlur(patch[..., :3], (9, 9), 2.5)
            patch[..., :3] = patch[..., :3] * (1.0 - m[..., None]) + blurred * m[..., None]
        elif mode == "smudge" and prev_pos is not None:
            sx = int(round(prev_pos[0]))
            sy = int(round(prev_pos[1]))
            sroi = _roi_slices(sx, sy, dim, w, h)
            if sroi is not None:
                sy0, sy1, sx0, sx1, sdy0, sdy1, sdx0, sdx1 = sroi
                if (sy1 - sy0) == (iy1 - iy0) and (sx1 - sx0) == (ix1 - ix0):
                    sp = target[sy0:sy1, sx0:sx1].astype(np.float32) / 255.0
                    sm = (m * 0.65)[..., None]
                    patch = patch * (1.0 - sm) + sp * sm
        elif mode == "clone" and clone_source is not None:
            ox, oy = clone_offset
            sroi = _roi_slices(int(round(px + ox)), int(round(py + oy)), dim, clone_source.shape[1], clone_source.shape[0])
            if sroi is not None:
                sy0, sy1, sx0, sx1, _, _, _, _ = sroi
                sh_p, sw_p = min(iy1 - iy0, sy1 - sy0), min(ix1 - ix0, sx1 - sx0)
                if sh_p > 0 and sw_p > 0:
                    sp = clone_source[sy0:sy0 + sh_p, sx0:sx0 + sw_p].astype(np.float32) / 255.0
                    mm = m[:sh_p, :sw_p, None]
                    patch[:sh_p, :sw_p] = patch[:sh_p, :sw_p] * (1.0 - mm) + sp * mm
        elif mode == "history" and history_source is not None:
            if history_source.shape[:2] == (h, w):
                hp = history_source[iy0:iy1, ix0:ix1].astype(np.float32) / 255.0
                mm = m[..., None]
                patch = patch * (1.0 - mm) + hp * mm

        target[iy0:iy1, ix0:ix1] = np.clip(patch * 255.0, 0, 255).astype(np.uint8)


def paint_stroke_segment(
    target: np.ndarray,
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    color_rgb: Tuple[int, int, int],
    settings: BrushSettings,
    pressure: float = 1.0,
    mode: str = "brush",
    selection: Optional[np.ndarray] = None,
    clone_source: Optional[np.ndarray] = None,
    clone_offset: Tuple[int, int] = (0, 0),
    history_source: Optional[np.ndarray] = None,
) -> None:
    """Interpolate brush dabs smoothly along a segment p0 -> p1."""
    dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    step = max(1.0, settings.size * max(0.08, settings.spacing))
    n = max(1, int(math.ceil(dist / step)))
    prev = p0
    for i in range(n + 1):
        t = i / float(n)
        x = p0[0] + (p1[0] - p0[0]) * t
        y = p0[1] + (p1[1] - p0[1]) * t
        stamp_paint_dab(
            target,
            x,
            y,
            color_rgb,
            settings,
            pressure=pressure,
            mode=mode,
            selection=selection,
            clone_source=clone_source,
            clone_offset=clone_offset,
            history_source=history_source,
            prev_pos=prev,
        )
        prev = (x, y)


def render_gradient(
    width: int,
    height: int,
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    color0: Tuple[int, int, int, int],
    color1: Tuple[int, int, int, int],
    style: str = "Linear",  # Linear | Radial | Angle | Reflected | Diamond
    selection: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Render a smooth RGBA gradient."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = max(1.0, math.hypot(dx, dy))
    rx, ry = xx - p0[0], yy - p0[1]

    if style == "Radial":
        t = np.sqrt(rx * rx + ry * ry) / length
    elif style == "Angle":
        base_a = math.atan2(dy, dx)
        t = ((np.arctan2(ry, rx) - base_a) % (2.0 * math.pi)) / (2.0 * math.pi)
    elif style == "Reflected":
        proj = (rx * dx + ry * dy) / (length * length)
        t = np.abs(proj)
    elif style == "Diamond":
        ang = -math.atan2(dy, dx)
        u = rx * math.cos(ang) - ry * math.sin(ang)
        v = rx * math.sin(ang) + ry * math.cos(ang)
        t = (np.abs(u) + np.abs(v)) / length
    else:
        t = (rx * dx + ry * dy) / (length * length)

    t = np.clip(t, 0.0, 1.0)[..., None]
    c0 = np.array(color0, dtype=np.float32)
    c1 = np.array(color1, dtype=np.float32)
    rgba = c0 * (1.0 - t) + c1 * t
    if selection is not None and selection.shape == (height, width):
        rgba[..., 3] *= selection
    return np.clip(rgba, 0, 255).astype(np.uint8)


def flood_fill_layer(
    target: np.ndarray,
    x: int,
    y: int,
    color_rgba: Tuple[int, int, int, int],
    tolerance: int = 32,
    contiguous: bool = True,
    selection: Optional[np.ndarray] = None,
) -> None:
    """Paint Bucket flood fill onto RGBA layer."""
    h, w = target.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return
    seed = target[y, x].astype(np.int32)
    diff = np.max(np.abs(target.astype(np.int32) - seed), axis=-1)
    within = (diff <= tolerance).astype(np.uint8)

    if contiguous:
        num, labels = cv2.connectedComponents(within, connectivity=4)
        mask = (labels == labels[y, x]).astype(np.float32)
    else:
        mask = within.astype(np.float32)

    if selection is not None and selection.shape == (h, w):
        mask *= selection

    m = mask[..., None]
    col = np.array(color_rgba, dtype=np.float32)
    out = target.astype(np.float32) * (1.0 - m) + col * m
    target[:] = np.clip(out, 0, 255).astype(np.uint8)
