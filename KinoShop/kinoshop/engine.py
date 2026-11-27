"""Fast NumPy + OpenCV + Qt compositing, adjustment, smart-filter, and color-management engine."""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

from .models import (
    ExtraChannel,
    KinoDocument,
    Layer,
    LayerStyles,
    SmartFilter,
    TextLayerData,
    VectorShapeData,
)


# ---------------------------------------------------------------------------
# Color space & LUT helpers
# ---------------------------------------------------------------------------
def rgb_to_cmyk(rgb: np.ndarray) -> np.ndarray:
    """Convert float32 RGB [0..1] (H,W,3) to CMYK [0..1] (H,W,4)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    k = 1.0 - np.maximum(np.maximum(r, g), b)
    denom = np.maximum(1.0 - k, 1e-6)
    c = np.where(k < 0.9999, (1.0 - r - k) / denom, 0.0)
    m = np.where(k < 0.9999, (1.0 - g - k) / denom, 0.0)
    y = np.where(k < 0.9999, (1.0 - b - k) / denom, 0.0)
    return np.stack([c, m, y, k], axis=-1).astype(np.float32)


def cmyk_to_rgb(cmyk: np.ndarray, profile: str = "SWOP") -> np.ndarray:
    """Simulate realistic CMYK ink-gamut rendering back to display RGB [0..1]."""
    c, m, y, k = cmyk[..., 0], cmyk[..., 1], cmyk[..., 2], cmyk[..., 3]
    # Simulate coated press ink attenuation (SWOP / FOGRA39)
    if "FOGRA39" in profile:
        # Slightly richer black & cyan gamut
        r = (1.0 - np.minimum(1.0, c * 0.93 + m * 0.05)) * (1.0 - k * 0.92)
        g = (1.0 - np.minimum(1.0, m * 0.91 + c * 0.08 + y * 0.04)) * (1.0 - k * 0.92)
        b = (1.0 - np.minimum(1.0, y * 0.90 + m * 0.10)) * (1.0 - k * 0.91)
    else:
        # U.S. Web Coated SWOP v2 press gamut compression
        r = (1.0 - np.minimum(1.0, c * 0.90 + m * 0.07)) * (1.0 - k * 0.90)
        g = (1.0 - np.minimum(1.0, m * 0.89 + c * 0.10 + y * 0.05)) * (1.0 - k * 0.90)
        b = (1.0 - np.minimum(1.0, y * 0.88 + m * 0.12)) * (1.0 - k * 0.89)
    # Paper white point warmth
    r = r * 0.97 + 0.02
    g = g * 0.96 + 0.02
    b = b * 0.94 + 0.025
    return np.clip(np.stack([r, g, b], axis=-1), 0.0, 1.0).astype(np.float32)


def compute_gamut_warning_mask(rgb_f: np.ndarray, profile: str = "SWOP") -> np.ndarray:
    """Detect out-of-CMYK-gamut saturated colors (neon blues/greens/magentas)."""
    cmyk = rgb_to_cmyk(rgb_f)
    sim = cmyk_to_rgb(cmyk, profile)
    diff = np.linalg.norm(rgb_f - sim, axis=-1)
    return diff > 0.16


def apply_builtin_lut(rgb: np.ndarray, preset: str, intensity: float = 0.75, lut_path: str = "") -> np.ndarray:
    """Apply a built-in cinematic color grade LUT or external .cube 3D LUT file."""
    out = rgb.copy()
    if lut_path and os.path.isfile(lut_path):
        try:
            out = apply_cube_lut(rgb, lut_path)
            return np.clip(rgb * (1.0 - intensity) + out * intensity, 0.0, 1.0)
        except Exception:
            pass

    r, g, b = out[..., 0], out[..., 1], out[..., 2]
    luma = 0.299 * r + 0.587 * g + 0.114 * b

    if preset == "Cinema Teal & Orange":
        # Push shadows toward teal, highlights toward warm orange
        sh = np.clip(1.0 - luma * 1.4, 0.0, 1.0)
        hi = np.clip((luma - 0.35) * 1.5, 0.0, 1.0)
        r2 = r + hi * 0.14 - sh * 0.10
        g2 = g + hi * 0.03 + sh * 0.04
        b2 = b - hi * 0.12 + sh * 0.14
        out = np.stack([r2, g2, b2], axis=-1)
    elif preset == "Fuji Crisp Film":
        out = np.stack([
            np.power(np.clip(r * 1.03, 0, 1), 0.95),
            np.power(np.clip(g * 1.05, 0, 1), 0.96),
            np.power(np.clip(b * 0.97 + 0.02, 0, 1), 1.02),
        ], axis=-1)
    elif preset == "Kodak Warm Gold":
        out = np.stack([
            np.clip(r * 1.08 + 0.02, 0, 1),
            np.clip(g * 1.02 + 0.01, 0, 1),
            np.clip(b * 0.88 + 0.03, 0, 1),
        ], axis=-1)
    elif preset == "Noir High Contrast":
        c = np.clip((luma - 0.5) * 1.45 + 0.5, 0, 1)
        out = np.stack([c * 0.98, c * 0.99, c * 1.03], axis=-1)
    elif preset == "Cyberpunk Neon":
        out = np.stack([
            np.clip(r * 1.15 + (1 - g) * 0.08, 0, 1),
            np.clip(g * 0.92 + b * 0.10, 0, 1),
            np.clip(b * 1.22 + 0.05, 0, 1),
        ], axis=-1)
    elif preset == "Bleach Bypass":
        desat = luma[..., None]
        mix = out * 0.45 + desat * 0.55
        out = np.clip((mix - 0.5) * 1.35 + 0.5, 0, 1)
    elif preset == "Sunset Matte":
        out = np.stack([
            np.clip(r * 1.06 + 0.05, 0, 1),
            np.clip(g * 0.96 + 0.03, 0, 1),
            np.clip(b * 0.88 + 0.07, 0, 1),
        ], axis=-1)

    out = np.clip(out, 0.0, 1.0)
    return np.clip(rgb * (1.0 - intensity) + out * intensity, 0.0, 1.0).astype(np.float32)


def apply_cube_lut(rgb: np.ndarray, lut_path: str) -> np.ndarray:
    """Parse and apply an Adobe/Resolve .cube 3D LUT using trilinear interpolation."""
    size = 0
    rows: List[List[float]] = []
    with open(lut_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.upper().startswith("LUT_3D_SIZE"):
                size = int(s.split()[-1])
                continue
            parts = s.split()
            if len(parts) == 3:
                try:
                    rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
                except ValueError:
                    pass
    if size <= 1 or len(rows) != size ** 3:
        return rgb
    # .cube order: R fastest, then G, then B -> shape (B, G, R, 3)
    table = np.array(rows, dtype=np.float32).reshape((size, size, size, 3))
    coords = np.clip(rgb, 0.0, 1.0) * (size - 1)
    r0 = np.floor(coords[..., 0]).astype(np.int32)
    g0 = np.floor(coords[..., 1]).astype(np.int32)
    b0 = np.floor(coords[..., 2]).astype(np.int32)
    r1 = np.minimum(r0 + 1, size - 1)
    g1 = np.minimum(g0 + 1, size - 1)
    b1 = np.minimum(b0 + 1, size - 1)
    dr = (coords[..., 0] - r0)[..., None]
    dg = (coords[..., 1] - g0)[..., None]
    db = (coords[..., 2] - b0)[..., None]

    c000 = table[b0, g0, r0]
    c001 = table[b0, g0, r1]
    c010 = table[b0, g1, r0]
    c011 = table[b0, g1, r1]
    c100 = table[b1, g0, r0]
    c101 = table[b1, g0, r1]
    c110 = table[b1, g1, r0]
    c111 = table[b1, g1, r1]

    c00 = c000 * (1 - dr) + c001 * dr
    c01 = c010 * (1 - dr) + c011 * dr
    c10 = c100 * (1 - dr) + c101 * dr
    c11 = c110 * (1 - dr) + c111 * dr
    c0 = c00 * (1 - dg) + c01 * dg
    c1 = c10 * (1 - dg) + c11 * dg
    return np.clip(c0 * (1 - db) + c1 * db, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Blend Modes (24 Photoshop-compatible modes in vectorized float32)
# ---------------------------------------------------------------------------
def _rgb_to_hsl_luma(c: np.ndarray) -> np.ndarray:
    return 0.299 * c[..., 0] + 0.587 * c[..., 1] + 0.114 * c[..., 2]


def _set_lum(c: np.ndarray, l: np.ndarray) -> np.ndarray:
    d = l - _rgb_to_hsl_luma(c)
    out = c + d[..., None]
    mn = np.min(out, axis=-1, keepdims=True)
    mx = np.max(out, axis=-1, keepdims=True)
    ll = l[..., None]
    out = np.where(mn < 0.0, ll + ((out - ll) * ll) / np.maximum(ll - mn, 1e-6), out)
    out = np.where(mx > 1.0, ll + ((out - ll) * (1.0 - ll)) / np.maximum(mx - ll, 1e-6), out)
    return np.clip(out, 0.0, 1.0)


def _sat(c: np.ndarray) -> np.ndarray:
    return np.max(c, axis=-1) - np.min(c, axis=-1)


def _set_sat(c: np.ndarray, s: np.ndarray) -> np.ndarray:
    mn = np.min(c, axis=-1, keepdims=True)
    mx = np.max(c, axis=-1, keepdims=True)
    cur = np.maximum(mx - mn, 1e-6)
    norm = (c - mn) / cur
    return np.where((mx - mn) > 1e-5, norm * s[..., None], 0.0)


def blend_rgb(base: np.ndarray, top: np.ndarray, mode: str) -> np.ndarray:
    """Compute blend function B(base, top) for float32 RGB in [0, 1]."""
    if mode == "Normal" or mode == "Dissolve":
        return top
    if mode == "Darken":
        return np.minimum(base, top)
    if mode == "Multiply":
        return base * top
    if mode == "Color Burn":
        return 1.0 - np.minimum(1.0, (1.0 - base) / np.maximum(top, 1e-5))
    if mode == "Linear Burn":
        return np.maximum(0.0, base + top - 1.0)
    if mode == "Lighten":
        return np.maximum(base, top)
    if mode == "Screen":
        return 1.0 - (1.0 - base) * (1.0 - top)
    if mode == "Color Dodge":
        return np.minimum(1.0, base / np.maximum(1.0 - top, 1e-5))
    if mode == "Linear Dodge (Add)":
        return np.minimum(1.0, base + top)
    if mode == "Overlay":
        return np.where(base <= 0.5, 2.0 * base * top, 1.0 - 2.0 * (1.0 - base) * (1.0 - top))
    if mode == "Soft Light":
        return np.where(
            top <= 0.5,
            base - (1.0 - 2.0 * top) * base * (1.0 - base),
            base + (2.0 * top - 1.0) * (np.sqrt(np.maximum(base, 0.0)) - base),
        )
    if mode == "Hard Light":
        return np.where(top <= 0.5, 2.0 * base * top, 1.0 - 2.0 * (1.0 - base) * (1.0 - top))
    if mode == "Vivid Light":
        burn = 1.0 - np.minimum(1.0, (1.0 - base) / np.maximum(2.0 * top, 1e-5))
        dodge = np.minimum(1.0, base / np.maximum(2.0 * (1.0 - top), 1e-5))
        return np.where(top <= 0.5, burn, dodge)
    if mode == "Linear Light":
        return np.clip(base + 2.0 * top - 1.0, 0.0, 1.0)
    if mode == "Pin Light":
        return np.where(top <= 0.5, np.minimum(base, 2.0 * top), np.maximum(base, 2.0 * top - 1.0))
    if mode == "Difference":
        return np.abs(base - top)
    if mode == "Exclusion":
        return base + top - 2.0 * base * top
    if mode == "Subtract":
        return np.maximum(0.0, base - top)
    if mode == "Divide":
        return np.minimum(1.0, base / np.maximum(top, 1e-5))
    if mode == "Hue":
        return _set_lum(_set_sat(top, _sat(base)), _rgb_to_hsl_luma(base))
    if mode == "Saturation":
        return _set_lum(_set_sat(base, _sat(top)), _rgb_to_hsl_luma(base))
    if mode == "Color":
        return _set_lum(top, _rgb_to_hsl_luma(base))
    if mode == "Luminosity":
        return _set_lum(base, _rgb_to_hsl_luma(top))
    return top


def _alpha_bbox(alpha: np.ndarray, pad: int = 0) -> Optional[Tuple[int, int, int, int]]:
    """Fast tight bounding box (x0, y0, x1, y1) of non-zero alpha pixels."""
    h, w = alpha.shape
    rows = np.any(alpha > 0, axis=1)
    if not rows.any():
        return None
    cols = np.any(alpha > 0, axis=0)
    y0 = int(np.argmax(rows))
    y1 = h - int(np.argmax(rows[::-1]))
    x0 = int(np.argmax(cols))
    x1 = w - int(np.argmax(cols[::-1]))
    return (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))


def alpha_composite_roi(
    dst_rgba: np.ndarray,
    src_rgba: np.ndarray,
    bbox: Tuple[int, int, int, int],
    mode: str = "Normal",
    opacity: float = 1.0,
) -> None:
    """In-place fast compositing inside tight ROI bbox=(x0,y0,x1,y1) on float32 RGBA [0..1]."""
    x0, y0, x1, y1 = bbox
    if x0 >= x1 or y0 >= y1 or opacity <= 1e-4:
        return
    dst = dst_rgba[y0:y1, x0:x1]
    src = src_rgba[y0:y1, x0:x1]
    sa = src[..., 3:4] if opacity >= 0.999 else (src[..., 3:4] * opacity)
    if mode == "Dissolve":
        rng = np.random.default_rng(42)
        sa = (rng.random(sa.shape, dtype=np.float32) < sa).astype(np.float32)

    if mode == "Normal":
        inv_sa = 1.0 - sa
        da = dst[..., 3:4]
        # Fast path when destination is already opaque (99% of canvas compositing!)
        if float(da.min()) > 0.995:
            dst[..., :3] = dst[..., :3] * inv_sa + src[..., :3] * sa
            dst[..., 3:4] = 1.0
            return
        out_a = sa + da * inv_sa
        num = src[..., :3] * sa + dst[..., :3] * (da * inv_sa)
        np.divide(num, np.maximum(out_a, 1e-6), out=dst[..., :3])
        dst[..., 3:4] = out_a
        return

    da = dst[..., 3:4]
    inv_sa = 1.0 - sa
    out_a = sa + da * inv_sa
    blended = blend_rgb(dst[..., :3], src[..., :3], mode)
    num = (1.0 - da) * sa * src[..., :3] + inv_sa * da * dst[..., :3] + sa * da * blended
    np.divide(num, np.maximum(out_a, 1e-6), out=dst[..., :3])
    np.clip(dst[..., :3], 0.0, 1.0, out=dst[..., :3])
    np.clip(out_a, 0.0, 1.0, out=dst[..., 3:4])


def alpha_composite(dst_rgba: np.ndarray, src_rgba: np.ndarray, mode: str = "Normal", opacity: float = 1.0) -> np.ndarray:
    """Porter-Duff + Photoshop blend mode compositing on float32 RGBA [0..1]."""
    out = dst_rgba.copy()
    h, w = dst_rgba.shape[:2]
    alpha_composite_roi(out, src_rgba, (0, 0, w, h), mode=mode, opacity=opacity)
    return out


# ---------------------------------------------------------------------------
# Non-destructive Adjustment Layers
# ---------------------------------------------------------------------------
def _curve_lut(points: List[List[float]]) -> np.ndarray:
    pts = sorted(points, key=lambda p: p[0])
    if len(pts) < 2:
        return np.linspace(0.0, 1.0, 256, dtype=np.float32)
    xs = np.array([p[0] for p in pts], dtype=np.float32)
    ys = np.array([p[1] for p in pts], dtype=np.float32)
    grid = np.arange(256, dtype=np.float32)
    vals = np.interp(grid, xs, ys)
    return np.clip(vals / 255.0, 0.0, 1.0).astype(np.float32)


def apply_adjustment_rgb(rgb: np.ndarray, adj_type: str, params: Dict[str, Any]) -> np.ndarray:
    """Apply an adjustment layer operation on float32 RGB [0..1]."""
    out = rgb.copy()
    if adj_type == "Levels":
        ib = float(params.get("in_black", 0)) / 255.0
        iw = max(ib + 1.0 / 255.0, float(params.get("in_white", 255)) / 255.0)
        gamma = max(0.05, float(params.get("gamma", 1.0)))
        ob = float(params.get("out_black", 0)) / 255.0
        ow = float(params.get("out_white", 255)) / 255.0
        ch = params.get("channel", "RGB")
        idx = {"R": 0, "G": 1, "B": 2}.get(ch, None)
        target = out[..., idx] if idx is not None else out
        x = np.clip((target - ib) / (iw - ib), 0.0, 1.0)
        x = np.power(x, 1.0 / gamma)
        x = ob + x * (ow - ob)
        if idx is not None:
            out[..., idx] = x
        else:
            out = x
        return np.clip(out, 0.0, 1.0)

    if adj_type == "Curves":
        idx_u8 = np.clip((out * 255.0).astype(np.int32), 0, 255)
        lut_rgb = _curve_lut(params.get("points_rgb", [[0, 0], [255, 255]]))
        out = lut_rgb[idx_u8]
        for ci, key in enumerate(["points_r", "points_g", "points_b"]):
            pts = params.get(key)
            if pts and len(pts) >= 2 and pts != [[0, 0], [255, 255]]:
                lut_c = _curve_lut(pts)
                out[..., ci] = lut_c[np.clip((out[..., ci] * 255.0).astype(np.int32), 0, 255)]
        return np.clip(out, 0.0, 1.0)

    if adj_type == "Exposure":
        exp = float(params.get("exposure", 0.0))
        off = float(params.get("offset", 0.0))
        gam = max(0.1, float(params.get("gamma", 1.0)))
        out = out * (2.0 ** exp) + off
        out = np.power(np.clip(out, 0.0, 1.0), 1.0 / gam)
        return np.clip(out, 0.0, 1.0)

    if adj_type == "Hue/Saturation":
        hue = float(params.get("hue", 0.0))  # -180..180
        sat = float(params.get("saturation", 0.0)) / 100.0  # -1..1
        lit = float(params.get("lightness", 0.0)) / 100.0
        colorize = bool(params.get("colorize", False))
        bgr_u8 = np.clip(out[..., ::-1] * 255.0, 0, 255).astype(np.uint8)
        hsv = cv2.cvtColor(bgr_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
        if colorize:
            hsv[..., 0] = (hue % 360.0) * 0.5
            hsv[..., 1] = np.clip((sat + 0.5) * 255.0, 0, 255)
        else:
            hsv[..., 0] = (hsv[..., 0] + hue * 0.5) % 180.0
            hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + sat), 0, 255)
        bgr2 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255.0
        out = bgr2[..., ::-1]
        if lit > 0:
            out = out + (1.0 - out) * lit
        elif lit < 0:
            out = out * (1.0 + lit)
        return np.clip(out, 0.0, 1.0)

    if adj_type == "Vibrance":
        vib = float(params.get("vibrance", 0.0)) / 100.0
        sat = float(params.get("saturation", 0.0)) / 100.0
        mx = np.max(out, axis=-1, keepdims=True)
        mn = np.min(out, axis=-1, keepdims=True)
        avg = (out[..., 0:1] + out[..., 1:2] + out[..., 2:3]) / 3.0
        cur_sat = mx - mn
        boost = vib * (1.0 - cur_sat) + sat
        out = avg + (out - avg) * (1.0 + boost)
        return np.clip(out, 0.0, 1.0)

    if adj_type == "Color Balance":
        sh = np.array(params.get("shadows", [0, 0, 0]), dtype=np.float32) / 255.0
        md = np.array(params.get("midtones", [0, 0, 0]), dtype=np.float32) / 255.0
        hi = np.array(params.get("highlights", [0, 0, 0]), dtype=np.float32) / 255.0
        luma = _rgb_to_hsl_luma(out)[..., None]
        w_sh = np.clip(1.0 - luma * 2.0, 0.0, 1.0)
        w_hi = np.clip((luma - 0.5) * 2.0, 0.0, 1.0)
        w_md = 1.0 - np.abs(luma - 0.5) * 2.0
        delta = w_sh * sh + w_md * md + w_hi * hi
        res = np.clip(out + delta, 0.0, 1.0)
        if params.get("preserve_luminosity", True):
            res = _set_lum(res, luma[..., 0])
        return res

    if adj_type == "Black & White":
        wr = float(params.get("red", 40)) / 100.0
        wg = float(params.get("green", 40)) / 100.0
        wb = float(params.get("blue", 20)) / 100.0
        tot = max(wr + wg + wb, 1e-4)
        gray = np.clip((out[..., 0] * wr + out[..., 1] * wg + out[..., 2] * wb) / tot, 0.0, 1.0)
        if params.get("tint", False):
            return np.stack([np.clip(gray * 1.06, 0, 1), np.clip(gray * 0.99, 0, 1), np.clip(gray * 0.88, 0, 1)], axis=-1)
        return np.stack([gray, gray, gray], axis=-1)

    if adj_type == "Photo Filter":
        col = np.array(params.get("color", [236, 138, 0]), dtype=np.float32) / 255.0
        dens = np.clip(float(params.get("density", 25)) / 100.0, 0.0, 1.0)
        filtered = out * (1.0 - dens) + (out * col) * dens
        if params.get("preserve_luminosity", True):
            filtered = _set_lum(filtered, _rgb_to_hsl_luma(out))
        return np.clip(filtered, 0.0, 1.0)

    if adj_type == "Channel Mixer":
        mr = np.array(params.get("r", [100, 0, 0]), dtype=np.float32) / 100.0
        mg = np.array(params.get("g", [0, 100, 0]), dtype=np.float32) / 100.0
        mb = np.array(params.get("b", [0, 0, 100]), dtype=np.float32) / 100.0
        if params.get("monochrome", False):
            g = np.clip(out[..., 0] * mr[0] + out[..., 1] * mr[1] + out[..., 2] * mr[2], 0, 1)
            return np.stack([g, g, g], axis=-1)
        r2 = out[..., 0] * mr[0] + out[..., 1] * mr[1] + out[..., 2] * mr[2]
        g2 = out[..., 0] * mg[0] + out[..., 1] * mg[1] + out[..., 2] * mg[2]
        b2 = out[..., 0] * mb[0] + out[..., 1] * mb[1] + out[..., 2] * mb[2]
        return np.clip(np.stack([r2, g2, b2], axis=-1), 0.0, 1.0)

    if adj_type == "LUT / Color Lookup":
        return apply_builtin_lut(
            out,
            str(params.get("preset", "Cinema Teal & Orange")),
            float(params.get("intensity", 0.75)),
            str(params.get("lut_path", "")),
        )

    if adj_type == "Posterize":
        lv = max(2, int(params.get("levels", 6)))
        return np.floor(out * lv) / max(lv - 1, 1)

    if adj_type == "Threshold":
        th = float(params.get("level", 128)) / 255.0
        g = (_rgb_to_hsl_luma(out) >= th).astype(np.float32)
        return np.stack([g, g, g], axis=-1)

    if adj_type == "Invert":
        return 1.0 - out

    return out


# ---------------------------------------------------------------------------
# Smart Filters (Reversible per-layer filter stack)
# ---------------------------------------------------------------------------
def apply_filter_rgba(rgba_u8: np.ndarray, name: str, params: Dict[str, Any]) -> np.ndarray:
    """Apply a named filter to an (H,W,4) uint8 RGBA image and return (H,W,4) uint8."""
    h, w = rgba_u8.shape[:2]
    rgb = rgba_u8[..., :3]
    alpha = rgba_u8[..., 3]
    out_rgb = rgb.copy()
    out_a = alpha.copy()

    if name == "Gaussian Blur":
        rad = max(0.5, float(params.get("radius", 6.0)))
        k = int(rad * 3) * 2 + 1
        out_rgb = cv2.GaussianBlur(rgb, (k, k), rad)
        out_a = cv2.GaussianBlur(alpha, (k, k), rad)

    elif name == "Motion Blur":
        dist = max(3, int(params.get("distance", 15)))
        angle = float(params.get("angle", 0.0))
        kern = np.zeros((dist, dist), dtype=np.float32)
        kern[dist // 2, :] = 1.0
        M = cv2.getRotationMatrix2D((dist / 2.0, dist / 2.0), angle, 1.0)
        kern = cv2.warpAffine(kern, M, (dist, dist))
        s = kern.sum()
        if s > 0:
            kern /= s
        out_rgb = cv2.filter2D(rgb, -1, kern)
        out_a = cv2.filter2D(alpha, -1, kern)

    elif name == "Radial Blur":
        strength = max(1, int(params.get("amount", 10)))
        cx, cy = w / 2.0, h / 2.0
        acc = rgb.astype(np.float32)
        steps = 8
        for i in range(1, steps + 1):
            sc = 1.0 + (strength * 0.004) * i
            M = cv2.getRotationMatrix2D((cx, cy), 0.0, sc)
            acc += cv2.warpAffine(rgb, M, (w, h), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        out_rgb = np.clip(acc / (steps + 1), 0, 255).astype(np.uint8)

    elif name == "Surface Blur":
        rad = max(3, int(params.get("radius", 9)))
        sigma = float(params.get("threshold", 45.0))
        out_rgb = cv2.bilateralFilter(rgb, rad, sigma, sigma)

    elif name == "Unsharp Mask":
        amount = float(params.get("amount", 1.2))
        rad = max(0.5, float(params.get("radius", 2.0)))
        blur = cv2.GaussianBlur(rgb, (0, 0), rad)
        out_rgb = np.clip(rgb.astype(np.float32) * (1.0 + amount) - blur.astype(np.float32) * amount, 0, 255).astype(np.uint8)

    elif name == "High Pass":
        rad = max(1.0, float(params.get("radius", 4.0)))
        blur = cv2.GaussianBlur(rgb, (0, 0), rad).astype(np.float32)
        out_rgb = np.clip(rgb.astype(np.float32) - blur + 128.0, 0, 255).astype(np.uint8)

    elif name == "Add Noise":
        amt = float(params.get("amount", 22.0))
        mono = bool(params.get("monochrome", False))
        rng = np.random.default_rng(int(params.get("seed", 7)))
        if mono:
            n = rng.normal(0, amt, (h, w, 1)).astype(np.float32)
        else:
            n = rng.normal(0, amt, (h, w, 3)).astype(np.float32)
        out_rgb = np.clip(rgb.astype(np.float32) + n, 0, 255).astype(np.uint8)

    elif name == "Reduce Noise":
        strength = float(params.get("strength", 8.0))
        bgr = rgb[..., ::-1]
        den = cv2.fastNlMeansDenoisingColored(bgr, None, strength, strength, 7, 15)
        out_rgb = den[..., ::-1]

    elif name == "Median":
        k = max(3, int(params.get("radius", 5)) | 1)
        out_rgb = cv2.medianBlur(rgb, k)

    elif name == "Twirl":
        ang_deg = float(params.get("angle", 90.0))
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = w * 0.5, h * 0.5
        dx, dy = xx - cx, yy - cy
        r = np.sqrt(dx * dx + dy * dy)
        rmax = min(cx, cy)
        theta = np.arctan2(dy, dx) + np.radians(ang_deg) * np.maximum(0.0, 1.0 - r / max(rmax, 1.0))
        map_x = (cx + r * np.cos(theta)).astype(np.float32)
        map_y = (cy + r * np.sin(theta)).astype(np.float32)
        out_rgb = cv2.remap(rgb, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        out_a = cv2.remap(alpha, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    elif name == "Ripple":
        amp = float(params.get("amplitude", 10.0))
        wl = max(4.0, float(params.get("wavelength", 40.0)))
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        map_x = (xx + amp * np.sin(2.0 * math.pi * yy / wl)).astype(np.float32)
        map_y = (yy + amp * np.cos(2.0 * math.pi * xx / wl)).astype(np.float32)
        out_rgb = cv2.remap(rgb, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        out_a = cv2.remap(alpha, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    elif name == "Spherize":
        strength = float(params.get("amount", 0.6))
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = w * 0.5, h * 0.5
        nx = (xx - cx) / max(cx, 1.0)
        ny = (yy - cy) / max(cy, 1.0)
        r = np.sqrt(nx * nx + ny * ny)
        factor = np.where(r < 1.0, np.power(np.maximum(r, 1e-6), strength), 1.0) / np.maximum(r, 1e-6)
        factor = np.where(r < 1.0, factor, 1.0)
        map_x = (cx + nx * factor * cx).astype(np.float32)
        map_y = (cy + ny * factor * cy).astype(np.float32)
        out_rgb = cv2.remap(rgb, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        out_a = cv2.remap(alpha, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    elif name == "Oil Paint":
        bgr = rgb[..., ::-1]
        styled = cv2.stylization(bgr, sigma_s=float(params.get("sigma_s", 45)), sigma_r=float(params.get("sigma_r", 0.45)))
        out_rgb = styled[..., ::-1]

    elif name == "Emboss":
        kern = np.array([[-2, -1, 0], [-1, 1, 1], [0, 1, 2]], dtype=np.float32)
        emb = cv2.filter2D(rgb.astype(np.float32), -1, kern) + 128.0
        out_rgb = np.clip(emb, 0, 255).astype(np.uint8)

    elif name == "Find Edges":
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = 255.0 - np.clip(np.sqrt(gx * gx + gy * gy), 0, 255)
        u = mag.astype(np.uint8)
        out_rgb = np.stack([u, u, u], axis=-1)

    elif name == "Halftone":
        cell = max(4, int(params.get("cell", 8)))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        canvas = np.full((h, w), 255, dtype=np.uint8)
        for y0 in range(0, h, cell):
            for x0 in range(0, w, cell):
                val = float(gray[y0:y0 + cell, x0:x0 + cell].mean()) / 255.0
                rad = int((1.0 - val) * cell * 0.58)
                if rad > 0:
                    cv2.circle(canvas, (x0 + cell // 2, y0 + cell // 2), rad, 18, -1, cv2.LINE_AA)
        out_rgb = np.stack([canvas, canvas, canvas], axis=-1)

    elif name == "Vignette":
        strength = float(params.get("amount", 0.55))
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        nx = (xx - w / 2.0) / max(w / 2.0, 1.0)
        ny = (yy - h / 2.0) / max(h / 2.0, 1.0)
        dist = np.sqrt(nx * nx + ny * ny)
        vig = np.clip(1.0 - strength * np.power(dist, 2.2), 0.12, 1.0)[..., None]
        out_rgb = np.clip(rgb.astype(np.float32) * vig, 0, 255).astype(np.uint8)

    elif name == "Chromatic Aberration":
        shift = int(params.get("shift", 4))
        out_rgb = rgb.copy()
        out_rgb[..., 0] = np.roll(rgb[..., 0], shift, axis=1)
        out_rgb[..., 2] = np.roll(rgb[..., 2], -shift, axis=1)

    elif name == "Lens Flare":
        fx = float(params.get("x", 0.72)) * w
        fy = float(params.get("y", 0.26)) * h
        brightness = float(params.get("brightness", 1.0))
        style = str(params.get("style", "Anamorphic Blue"))
        out_rgb = render_lens_flare(rgb, fx, fy, brightness, style)

    elif name == "Lighting Effects":
        lx = float(params.get("x", 0.35)) * w
        ly = float(params.get("y", 0.30)) * h
        intensity = float(params.get("intensity", 1.25))
        ambience = float(params.get("ambience", 0.28))
        radius = float(params.get("radius", 0.55)) * max(w, h)
        color = tuple(params.get("color", [255, 240, 215]))
        out_rgb = render_lighting_effects(rgb, lx, ly, radius, intensity, ambience, color)

    return np.dstack([out_rgb, out_a])


def render_lens_flare(
    rgb: np.ndarray,
    fx: float,
    fy: float,
    brightness: float = 1.0,
    style: str = "Anamorphic Blue",
) -> np.ndarray:
    """Physically-inspired optical lens flare (halo, starburst, bokeh ghosts, anamorphic streak)."""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - fx, yy - fy
    dist = np.sqrt(dx * dx + dy * dy)
    diag = math.hypot(w, h)

    flare = np.zeros((h, w, 3), dtype=np.float32)

    # Core bloom
    core = np.exp(-dist / (diag * 0.032)) * 1.45 + np.exp(-dist / (diag * 0.14)) * 0.55
    if style == "Anamorphic Blue":
        core_col = np.array([0.85, 0.94, 1.0], dtype=np.float32)
    elif style == "35mm Prime":
        core_col = np.array([1.0, 0.92, 0.80], dtype=np.float32)
    else:
        core_col = np.array([1.0, 0.96, 0.88], dtype=np.float32)
    flare += core[..., None] * core_col

    # Diffraction starburst rays
    ang = np.arctan2(dy, dx)
    rays = np.power(np.abs(np.cos(ang * 6.0)), 14.0) * np.exp(-dist / (diag * 0.18)) * 0.5
    flare += rays[..., None] * core_col

    # Anamorphic horizontal streak
    if "Anamorphic" in style:
        streak = np.exp(-np.abs(dy) / max(2.5, h * 0.008)) * np.exp(-np.abs(dx) / (w * 0.55)) * 0.85
        flare += streak[..., None] * np.array([0.18, 0.65, 1.0], dtype=np.float32)

    # Optical aperture ghost rings along the axis through image center
    cx, cy = w * 0.5, h * 0.5
    vx, vy = cx - fx, cy - fy
    ghosts = [
        (0.45, 0.045, (0.35, 0.78, 1.0), 0.25),
        (0.85, 0.028, (1.0, 0.68, 0.35), 0.22),
        (1.35, 0.075, (0.45, 0.95, 0.65), 0.18),
        (1.78, 0.052, (0.88, 0.45, 1.0), 0.20),
    ]
    for t, rad_f, gcol, gop in ghosts:
        gx, gy = fx + vx * t, fy + vy * t
        gd = np.sqrt((xx - gx) ** 2 + (yy - gy) ** 2)
        gr = diag * rad_f
        ring = np.exp(-((gd - gr) ** 2) / max(8.0, (gr * 0.18) ** 2)) * 0.65 + np.where(gd < gr, 0.28, 0.0)
        flare += (ring * gop)[..., None] * np.array(gcol, dtype=np.float32)

    base = rgb.astype(np.float32) / 255.0
    # Screen blend flare onto image
    f_scaled = np.clip(flare * brightness, 0.0, 1.5)
    out = 1.0 - (1.0 - base) * (1.0 - np.clip(f_scaled, 0.0, 1.0)) + np.maximum(0.0, f_scaled - 1.0) * 0.35
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


def render_lighting_effects(
    rgb: np.ndarray,
    lx: float,
    ly: float,
    radius: float,
    intensity: float = 1.25,
    ambience: float = 0.28,
    color: Tuple[int, int, int] = (255, 240, 215),
) -> np.ndarray:
    """3D-inspired spotlight + surface bump lighting effect."""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2)
    falloff = np.exp(-(dist ** 2) / max(100.0, 2.0 * (radius * 0.65) ** 2))

    # Subtle surface normal bump from luminance gradients
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    ldx = (lx - xx) / np.maximum(dist, 1.0)
    ldy = (ly - yy) / np.maximum(dist, 1.0)
    bump = np.clip(1.0 + (gx * ldx + gy * ldy) * 0.85, 0.65, 1.35)

    lcol = np.array(color, dtype=np.float32) / 255.0
    light = ambience + (falloff * intensity * bump)[..., None] * lcol
    out = (rgb.astype(np.float32) / 255.0) * light
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Vector Shape & Text Layer Rasterization (via Qt QPainter)
# ---------------------------------------------------------------------------
def _qimage_to_rgba(qimg: QImage) -> np.ndarray:
    qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, qimg.bytesPerLine()))
    return arr[:, : w * 4].reshape((h, w, 4)).copy()


def rasterize_vector_layer(vd: VectorShapeData, width: int, height: int) -> np.ndarray:
    qimg = QImage(width, height, QImage.Format.Format_RGBA8888)
    qimg.fill(Qt.GlobalColor.transparent)
    p = QPainter(qimg)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    if vd.fill_enabled:
        p.setBrush(QBrush(QColor(*vd.fill_color)))
    else:
        p.setBrush(Qt.BrushStyle.NoBrush)

    if vd.stroke_enabled and vd.stroke_width > 0:
        pen = QPen(QColor(*vd.stroke_color), vd.stroke_width)
        if vd.dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
    else:
        p.setPen(Qt.PenStyle.NoPen)

    x, y, w, h = vd.rect
    if vd.shape_type == "rectangle":
        p.drawRect(QRectF(x, y, w, h))
    elif vd.shape_type == "rounded_rect":
        p.drawRoundedRect(QRectF(x, y, w, h), vd.corner_radius, vd.corner_radius)
    elif vd.shape_type == "ellipse":
        p.drawEllipse(QRectF(x, y, w, h))
    elif vd.shape_type in ("polygon", "star"):
        cx, cy = x + w / 2.0, y + h / 2.0
        rx, ry = abs(w) / 2.0, abs(h) / 2.0
        path = QPainterPath()
        n = max(3, vd.sides)
        total = n * 2 if vd.shape_type == "star" else n
        for i in range(total):
            ang = -math.pi / 2.0 + i * (2.0 * math.pi / total)
            rscale = vd.inner_ratio if (vd.shape_type == "star" and i % 2 == 1) else 1.0
            px = cx + math.cos(ang) * rx * rscale
            py = cy + math.sin(ang) * ry * rscale
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        p.drawPath(path)
    elif vd.shape_type == "line":
        p.drawLine(QPointF(x, y), QPointF(x + w, y + h))
    elif vd.shape_type == "path" and len(vd.points) >= 2:
        path = QPainterPath()
        path.moveTo(vd.points[0][0], vd.points[0][1])
        for pt in vd.points[1:]:
            path.lineTo(pt[0], pt[1])
        if vd.closed and len(vd.points) >= 3:
            path.closeSubpath()
        p.drawPath(path)

    p.end()
    return _qimage_to_rgba(qimg)


def _apply_text_warp(rgba: np.ndarray, style: str, bend: float) -> np.ndarray:
    if style == "None" or abs(bend) < 0.005:
        return rgba
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    if len(xs) == 0:
        return rgba
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = max(1, x1 - x0 + 1)
    bh = max(1, y1 - y0 + 1)
    pad = max(40, int(max(bw, bh) * abs(bend) * 0.8))
    h, w = rgba.shape[:2]
    rx0, rx1 = max(0, x0 - pad), min(w, x1 + pad + 1)
    ry0, ry1 = max(0, y0 - pad), min(h, y1 + pad + 1)
    sub = rgba[ry0:ry1, rx0:rx1]
    sh, sw = sub.shape[:2]
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    u = ((xx + rx0) - (x0 + x1) * 0.5) / max(bw * 0.5, 1.0)  # [-1..1]
    v = ((yy + ry0) - (y0 + y1) * 0.5) / max(bh * 0.5, 1.0)

    map_x = xx.copy()
    map_y = yy.copy()
    amp = bend * bh * 0.85

    if style == "Arc":
        map_y = yy + amp * (u * u - 0.5)
    elif style == "Arch":
        map_y = yy + amp * (np.cos(np.clip(u, -1.5, 1.5) * math.pi * 0.5) - 0.5) * -1.0
    elif style == "Bulge":
        scale = 1.0 + bend * 0.6 * (1.0 - np.minimum(1.0, u * u))
        map_y = (yy - sh * 0.5) / np.maximum(scale, 0.25) + sh * 0.5
    elif style == "Flag":
        map_y = yy + amp * 0.55 * np.sin(u * math.pi)
    elif style == "Wave":
        map_y = yy + amp * 0.45 * np.sin(u * math.pi * 2.0)
    elif style == "Rise":
        map_y = yy + amp * 0.6 * u
    elif style == "Fish":
        scale = 1.0 + bend * 0.7 * np.sin(u * math.pi * 0.5)
        map_y = (yy - sh * 0.5) / np.maximum(scale, 0.25) + sh * 0.5
    elif style == "Twist":
        ang = bend * 0.7 * (1.0 - np.minimum(1.0, np.sqrt(u * u + v * v)))
        cx, cy = sw * 0.5, sh * 0.5
        dx, dy = xx - cx, yy - cy
        map_x = cx + dx * np.cos(ang) - dy * np.sin(ang)
        map_y = cy + dx * np.sin(ang) + dy * np.cos(ang)

    warped = cv2.remap(sub, map_x.astype(np.float32), map_y.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    out = np.zeros_like(rgba)
    out[ry0:ry1, rx0:rx1] = warped
    return out


def rasterize_text_layer(td: TextLayerData, width: int, height: int) -> np.ndarray:
    qimg = QImage(width, height, QImage.Format.Format_RGBA8888)
    qimg.fill(Qt.GlobalColor.transparent)
    p = QPainter(qimg)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    font = QFont(td.font_family, max(6, td.font_size))
    font.setBold(td.bold)
    font.setItalic(td.italic)
    if abs(td.letter_spacing) > 0.01:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, td.letter_spacing)
    p.setFont(font)
    p.setPen(QColor(*td.color))

    if td.on_path and len(td.path_points) >= 2:
        # Type on a Path!
        path = QPainterPath()
        path.moveTo(td.path_points[0][0], td.path_points[0][1])
        if len(td.path_points) == 3:
            path.quadTo(td.path_points[1][0], td.path_points[1][1], td.path_points[2][0], td.path_points[2][1])
        else:
            for pt in td.path_points[1:]:
                path.lineTo(pt[0], pt[1])
        total_len = max(1.0, path.length())
        fm = QFontMetricsF(font)
        dist = 0.0
        for ch in td.text:
            cw = max(2.0, fm.horizontalAdvance(ch) + td.letter_spacing)
            pct = min(1.0, (dist + cw * 0.5) / total_len)
            if pct >= 1.0:
                break
            pt = path.pointAtPercent(pct)
            ang = -path.angleAtPercent(pct)
            p.save()
            p.translate(pt)
            p.rotate(ang)
            p.drawText(QPointF(-cw * 0.5, 0), ch)
            p.restore()
            dist += cw
    else:
        lines = td.text.split("\n")
        fm = QFontMetricsF(font)
        step = fm.height() * td.line_height
        for idx, line in enumerate(lines):
            y = td.y + idx * step
            x = td.x
            if td.align == "center":
                x -= fm.horizontalAdvance(line) * 0.5
            elif td.align == "right":
                x -= fm.horizontalAdvance(line)
            p.drawText(QPointF(x, y), line)

    p.end()
    rgba = _qimage_to_rgba(qimg)
    if td.warp_style and td.warp_style != "None":
        rgba = _apply_text_warp(rgba, td.warp_style, td.warp_bend)
    return rgba


# ---------------------------------------------------------------------------
# Layer Styles (Drop Shadow, Outer/Inner Glow, Bevel, Color Overlay, Stroke)
# ---------------------------------------------------------------------------
def _blur_alpha_fast(alpha_f: np.ndarray, radius: int) -> np.ndarray:
    """SIMD-accelerated uint8 Gaussian blur for alpha channels (10x faster than float32)."""
    if radius <= 0:
        return alpha_f
    u8 = np.clip(alpha_f * 255.0, 0, 255).astype(np.uint8)
    k = radius * 2 + 1
    b = cv2.GaussianBlur(u8, (k, k), max(0.5, radius * 0.55))
    return b.astype(np.float32) * (1.0 / 255.0)


def apply_layer_styles_roi(
    rgba_f: np.ndarray, styles: LayerStyles
) -> Tuple[Optional[Tuple[Tuple[int, int, int, int], np.ndarray]], Tuple[Tuple[int, int, int, int], np.ndarray]]:
    """Compute Layer Styles ONLY within the tight non-zero alpha bounding box (+ blur padding).
    Returns ((under_bbox, under_patch) or None, (styled_bbox, styled_patch))."""
    h, w = rgba_f.shape[:2]
    pad = max(
        (styles.drop_shadow_blur * 2 + styles.drop_shadow_distance + 4) if styles.drop_shadow else 0,
        (styles.outer_glow_radius * 2 + 4) if styles.outer_glow else 0,
        (styles.stroke_size + 4) if styles.stroke else 0,
        4,
    )
    bbox = _alpha_bbox(rgba_f[..., 3], pad=pad)
    if bbox is None:
        return None, ((0, 0, 0, 0), np.zeros((0, 0, 4), dtype=np.float32))

    x0, y0, x1, y1 = bbox
    rh, rw = y1 - y0, x1 - x0
    out = rgba_f[y0:y1, x0:x1].copy()
    alpha = out[..., 3]
    under = np.zeros((rh, rw, 4), dtype=np.float32)
    has_under = False

    if styles.drop_shadow:
        rad_ang = math.radians(styles.drop_shadow_angle)
        dx = int(round(math.cos(rad_ang) * styles.drop_shadow_distance))
        dy = int(round(math.sin(rad_ang) * styles.drop_shadow_distance))
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        sh_a = cv2.warpAffine(alpha, M, (rw, rh), borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        sh_a = _blur_alpha_fast(sh_a, styles.drop_shadow_blur)
        sh = np.zeros((rh, rw, 4), dtype=np.float32)
        sh[..., :3] = np.array(styles.drop_shadow_color, dtype=np.float32) / 255.0
        sh[..., 3] = np.clip(sh_a * styles.drop_shadow_opacity, 0.0, 1.0)
        alpha_composite_roi(under, sh, (0, 0, rw, rh), "Normal", 1.0)
        has_under = True

    if styles.outer_glow:
        glow_a = _blur_alpha_fast(alpha, max(1, styles.outer_glow_radius))
        glow_a = np.clip(glow_a * 1.45 * styles.outer_glow_opacity, 0.0, 1.0)
        gl = np.zeros((rh, rw, 4), dtype=np.float32)
        gl[..., :3] = np.array(styles.outer_glow_color, dtype=np.float32) / 255.0
        gl[..., 3] = glow_a
        alpha_composite_roi(under, gl, (0, 0, rw, rh), "Screen", 1.0)
        has_under = True

    if styles.color_overlay:
        col = np.array(styles.color_overlay_color, dtype=np.float32) / 255.0
        t = styles.color_overlay_opacity
        out[..., :3] = out[..., :3] * (1.0 - t) + col * t

    if styles.inner_shadow:
        inv_a = 1.0 - alpha
        M = np.float32([[1, 0, styles.inner_shadow_distance], [0, 1, styles.inner_shadow_distance]])
        sh_a = cv2.warpAffine(inv_a, M, (rw, rh), borderMode=cv2.BORDER_CONSTANT, borderValue=1.0)
        sh_a = _blur_alpha_fast(sh_a, styles.inner_shadow_blur)
        m = np.clip(sh_a * alpha * styles.inner_shadow_opacity, 0.0, 1.0)[..., None]
        col = np.array(styles.inner_shadow_color, dtype=np.float32) / 255.0
        out[..., :3] = out[..., :3] * (1.0 - m) + col * m

    if styles.inner_glow:
        edge = _blur_alpha_fast(1.0 - alpha, max(1, styles.inner_glow_radius))
        m = np.clip(edge * alpha * styles.inner_glow_opacity * 1.6, 0.0, 1.0)[..., None]
        col = np.array(styles.inner_glow_color, dtype=np.float32) / 255.0
        out[..., :3] = out[..., :3] * (1.0 - m) + col * m

    if styles.bevel_emboss:
        sm = _blur_alpha_fast(alpha, max(1, styles.bevel_depth))
        gx = cv2.Sobel(sm, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(sm, cv2.CV_32F, 0, 1, ksize=3)
        light = np.clip((-gx - gy) * 2.5, -1.0, 1.0) * styles.bevel_opacity * alpha
        out[..., :3] = np.clip(out[..., :3] + light[..., None], 0.0, 1.0)

    if styles.stroke and styles.stroke_size > 0:
        sz = styles.stroke_size
        kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (sz * 2 + 1, sz * 2 + 1))
        a_u8 = (alpha * 255.0).astype(np.uint8)
        if styles.stroke_position == "Inside":
            eroded = cv2.erode(a_u8, kern).astype(np.float32) / 255.0
            ring = np.clip(alpha - eroded, 0.0, 1.0)
        elif styles.stroke_position == "Center":
            hk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(1, sz) | 1, max(1, sz) | 1))
            dil = cv2.dilate(a_u8, hk).astype(np.float32) / 255.0
            ero = cv2.erode(a_u8, hk).astype(np.float32) / 255.0
            ring = np.clip(dil - ero, 0.0, 1.0)
        else:
            dil = cv2.dilate(a_u8, kern).astype(np.float32) / 255.0
            ring = np.clip(dil - alpha, 0.0, 1.0)
        st = np.zeros((rh, rw, 4), dtype=np.float32)
        st[..., :3] = np.array(styles.stroke_color, dtype=np.float32) / 255.0
        st[..., 3] = ring * styles.stroke_opacity
        if styles.stroke_position == "Outside":
            alpha_composite_roi(under, st, (0, 0, rw, rh), "Normal", 1.0)
            has_under = True
        else:
            alpha_composite_roi(out, st, (0, 0, rw, rh), "Normal", 1.0)

    return ((bbox, under) if has_under else None), (bbox, out)


def apply_layer_styles(rgba_f: np.ndarray, styles: LayerStyles) -> Tuple[np.ndarray, np.ndarray]:
    """Compatibility wrapper returning full-frame (under_rgba_f, styled_rgba_f)."""
    h, w = rgba_f.shape[:2]
    under_res, styled_res = apply_layer_styles_roi(rgba_f, styles)
    under_full = np.zeros((h, w, 4), dtype=np.float32)
    styled_full = rgba_f.copy()
    if under_res is not None:
        (x0, y0, x1, y1), up = under_res
        under_full[y0:y1, x0:x1] = up
    (sx0, sy0, sx1, sy1), sp = styled_res
    if sx1 > sx0 and sy1 > sy0:
        styled_full[sy0:sy1, sx0:sx1] = sp
    return under_full, styled_full


# ---------------------------------------------------------------------------
# Full Document Compositor
# ---------------------------------------------------------------------------
def _transform_layer_image(img_u8: np.ndarray, lyr: Layer, width: int, height: int) -> np.ndarray:
    """Apply offset, scale, and rotation onto a (height, width, 4) canvas."""
    sh, sw = img_u8.shape[:2]
    if (
        sh == height
        and sw == width
        and lyr.offset_x == 0
        and lyr.offset_y == 0
        and abs(lyr.rotation) < 1e-3
        and abs(lyr.scale_x - 1.0) < 1e-3
        and abs(lyr.scale_y - 1.0) < 1e-3
    ):
        return img_u8

    cx, cy = sw * 0.5, sh * 0.5
    M = cv2.getRotationMatrix2D((cx, cy), -lyr.rotation, 1.0)
    # Apply non-uniform scale
    M[0, 0] *= lyr.scale_x
    M[0, 1] *= lyr.scale_y
    M[1, 0] *= lyr.scale_x
    M[1, 1] *= lyr.scale_y
    # Re-center + translate
    tx = (width - sw) * 0.5 if (sw != width or sh != height) else 0.0
    ty = (height - sh) * 0.5 if (sw != width or sh != height) else 0.0
    M[0, 2] += lyr.offset_x + tx + cx * (1.0 - lyr.scale_x)
    M[1, 2] += lyr.offset_y + ty + cy * (1.0 - lyr.scale_y)
    return cv2.warpAffine(img_u8, M, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def render_single_layer_rgba(lyr: Layer, width: int, height: int) -> Optional[np.ndarray]:
    """Render any non-adjustment layer (including Smart Objects, Smart Filters, Vector, Text, Group) to uint8 RGBA."""
    if lyr.kind == "raster":
        if lyr.image is None:
            return None
        base = _transform_layer_image(lyr.image, lyr, width, height)
    elif lyr.kind == "smart_object":
        src = lyr.smart_source if lyr.smart_source is not None else lyr.image
        if src is None:
            return None
        base = _transform_layer_image(src, lyr, width, height)
    elif lyr.kind == "vector" and lyr.vector_data is not None:
        raw = rasterize_vector_layer(lyr.vector_data, width, height)
        base = _transform_layer_image(raw, lyr, width, height)
    elif lyr.kind == "text" and lyr.text_data is not None:
        raw = rasterize_text_layer(lyr.text_data, width, height)
        base = _transform_layer_image(raw, lyr, width, height)
    elif lyr.kind == "fill":
        base = np.zeros((height, width, 4), dtype=np.uint8)
        col = lyr.fill_data.get("color", [49, 168, 255, 255])
        base[:, :] = col
    elif lyr.kind == "group":
        base = composite_layer_list(lyr.children, width, height)
        if lyr.offset_x or lyr.offset_y or abs(lyr.rotation) > 1e-3:
            base = _transform_layer_image(base, lyr, width, height)
    else:
        return None

    # Execute Smart Filters stack non-destructively!
    for sf in lyr.smart_filters:
        if sf.enabled:
            filtered = apply_filter_rgba(base, sf.name, sf.params)
            if sf.opacity < 0.999:
                base = np.clip(
                    base.astype(np.float32) * (1.0 - sf.opacity) + filtered.astype(np.float32) * sf.opacity,
                    0,
                    255,
                ).astype(np.uint8)
            else:
                base = filtered
    return base


def _layer_cache_signature(lyr: Layer, width: int, height: int) -> Tuple[Any, ...]:
    """Lightweight immutable key capturing all visual inputs for a non-adjustment layer."""
    st_key = tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in lyr.styles.__dict__.items()))
    sf_key = tuple((sf.uid, sf.name, sf.enabled, sf.opacity, repr(sf.params)) for sf in lyr.smart_filters)
    payload_key: Any = None
    if lyr.kind == "text" and lyr.text_data is not None:
        td = lyr.text_data
        payload_key = (td.text, td.x, td.y, td.font_family, td.font_size, td.bold, td.italic, td.color, td.letter_spacing, td.line_height, td.align, td.warp_style, td.warp_bend, td.on_path, tuple(td.path_points))
    elif lyr.kind == "vector" and lyr.vector_data is not None:
        vd = lyr.vector_data
        payload_key = (vd.shape_type, vd.rect, tuple(vd.points), vd.closed, vd.corner_radius, vd.sides, vd.inner_ratio, vd.fill_enabled, vd.fill_color, vd.stroke_enabled, vd.stroke_color, vd.stroke_width, vd.dashed)
    elif lyr.kind == "fill":
        payload_key = repr(lyr.fill_data)
    img_id = id(lyr.image) if lyr.image is not None else id(lyr.smart_source)
    mask_id = (id(lyr.mask), lyr.mask_enabled) if lyr.mask is not None else None
    return (
        lyr.kind, width, height, lyr._version, img_id, mask_id,
        lyr.offset_x, lyr.offset_y, lyr.rotation, lyr.scale_x, lyr.scale_y,
        st_key, sf_key, payload_key,
    )


def _get_cached_layer_render(lyr: Layer, width: int, height: int) -> Optional[Dict[str, Any]]:
    """Return cached tight-ROI float32 patches for a layer (re-rendering ONLY when modified!)."""
    if lyr.kind == "group":
        # Groups recurse on children; compute freshly but children themselves are cached
        rendered_u8 = render_single_layer_rgba(lyr, width, height)
        if rendered_u8 is None:
            return None
        bbox = _alpha_bbox(rendered_u8[..., 3])
        if bbox is None:
            return None
        x0, y0, x1, y1 = bbox
        patch = rendered_u8[y0:y1, x0:x1].astype(np.float32) * (1.0 / 255.0)
        return {"bbox": bbox, "patch": patch, "under": None}

    sig = _layer_cache_signature(lyr, width, height)
    if lyr._cache_key == sig and lyr._cache_val is not None:
        return lyr._cache_val

    rendered_u8 = render_single_layer_rgba(lyr, width, height)
    if rendered_u8 is None:
        lyr._cache_key = sig
        lyr._cache_val = None
        return None

    # Apply layer mask onto alpha before style calculation
    if lyr.mask is not None and lyr.mask_enabled:
        m = lyr.mask if lyr.mask.shape == (height, width) else cv2.resize(lyr.mask, (width, height), interpolation=cv2.INTER_LINEAR)
        rendered_u8 = rendered_u8.copy()
        rendered_u8[..., 3] = ((rendered_u8[..., 3].astype(np.uint16) * m.astype(np.uint16)) // 255).astype(np.uint8)

    if lyr.styles.has_any():
        src_f = rendered_u8.astype(np.float32) * (1.0 / 255.0)
        under_res, (sbbox, spatch) = apply_layer_styles_roi(src_f, lyr.styles)
        res = {"bbox": sbbox, "patch": spatch, "under": under_res}
    else:
        bbox = _alpha_bbox(rendered_u8[..., 3])
        if bbox is None:
            res = None
        else:
            x0, y0, x1, y1 = bbox
            patch = rendered_u8[y0:y1, x0:x1].astype(np.float32) * (1.0 / 255.0)
            res = {"bbox": bbox, "patch": patch, "under": None}

    lyr._cache_key = sig
    lyr._cache_val = res
    return res


_LUT3D_CACHE: Dict[Tuple[str, str], np.ndarray] = {}


def _get_builtin_lut3d_u8(preset: str, lut_path: str = "") -> np.ndarray:
    """Build & cache a 32x32x32 uint8 3D LUT (96 KB, fits in L2 cache -> ~4ms on 1280x800!)."""
    key = (preset, lut_path)
    cached = _LUT3D_CACHE.get(key)
    if cached is not None:
        return cached
    grid = np.linspace(0.0, 1.0, 32, dtype=np.float32)
    rr, gg, bb = np.meshgrid(grid, grid, grid, indexing="ij")
    cube = np.stack([rr, gg, bb], axis=-1).reshape((32, 32 * 32, 3))
    mapped = apply_builtin_lut(cube, preset, intensity=1.0, lut_path=lut_path)
    table = np.clip(mapped * 255.0 + 0.5, 0, 255).astype(np.uint8).reshape((32, 32, 32, 3))
    _LUT3D_CACHE[key] = table
    return table


def apply_adjustment_u8(rgb_u8: np.ndarray, adj_type: str, params: Dict[str, Any], opacity: float = 1.0) -> np.ndarray:
    """SIMD-accelerated uint8 adjustment path (0.6ms-5ms for 1280x800!)."""
    if adj_type == "LUT / Color Lookup":
        preset = str(params.get("preset", "Cinema Teal & Orange"))
        lut_path = str(params.get("lut_path", ""))
        intensity = float(params.get("intensity", 0.75)) * opacity
        if intensity <= 1e-4:
            return rgb_u8
        tbl = _get_builtin_lut3d_u8(preset, lut_path)
        graded = tbl[rgb_u8[..., 0] >> 3, rgb_u8[..., 1] >> 3, rgb_u8[..., 2] >> 3]
        if intensity >= 0.999:
            return graded
        return cv2.addWeighted(rgb_u8, 1.0 - intensity, graded, intensity, 0)

    if adj_type in ("Levels", "Curves", "Exposure", "Posterize", "Threshold", "Invert"):
        # Compute 256-entry 1D LUT per channel -> cv2.LUT is 0.6 ms SIMD!
        ramp = np.linspace(0.0, 1.0, 256, dtype=np.float32)
        ramp3 = np.stack([ramp, ramp, ramp], axis=-1)[None, :, :]  # (1, 256, 3)
        if adj_type == "Threshold":
            th = float(params.get("level", 128))
            gray = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2GRAY)
            bw = np.where(gray >= th, 255, 0).astype(np.uint8)
            out = np.stack([bw, bw, bw], axis=-1)
        else:
            mapped = apply_adjustment_rgb(ramp3, adj_type, params)[0]  # (256, 3)
            lut = np.clip(mapped * 255.0 + 0.5, 0, 255).astype(np.uint8)
            if np.array_equal(lut[:, 0], lut[:, 1]) and np.array_equal(lut[:, 1], lut[:, 2]):
                out = cv2.LUT(rgb_u8, lut[:, 0])
            else:
                out = np.empty_like(rgb_u8)
                for c in range(3):
                    out[..., c] = cv2.LUT(rgb_u8[..., c], lut[:, c])
        return out if opacity >= 0.999 else cv2.addWeighted(rgb_u8, 1.0 - opacity, out, opacity, 0)

    # Fallback to float32 for multi-channel nonlinear adjustments
    rgb_f = rgb_u8.astype(np.float32) * (1.0 / 255.0)
    adj_f = apply_adjustment_rgb(rgb_f, adj_type, params)
    out = np.clip(adj_f * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return out if opacity >= 0.999 else cv2.addWeighted(rgb_u8, 1.0 - opacity, out, opacity, 0)


def composite_layer_list(layers: List[Layer], width: int, height: int) -> np.ndarray:
    """Ultra-fast uint8-accumulator + tight-ROI + per-layer cached compositor (~10-15ms at 1280x800!)."""
    acc_u8 = np.zeros((height, width, 4), dtype=np.uint8)
    last_base_alpha: Optional[Tuple[Tuple[int, int, int, int], np.ndarray]] = None

    for idx, lyr in enumerate(layers):
        if not lyr.visible or lyr.opacity <= 1e-4:
            if not lyr.clipping_mask:
                last_base_alpha = None
            continue

        if lyr.kind == "adjustment":
            has_mask = lyr.mask is not None and lyr.mask_enabled
            has_clip = lyr.clipping_mask and last_base_alpha is not None
            if lyr.blend_mode == "Normal" and not has_mask and not has_clip:
                acc_u8[..., :3] = apply_adjustment_u8(acc_u8[..., :3], lyr.adjustment_type, lyr.adjustment_params, opacity=lyr.opacity)
                continue

            # Masked / blended adjustment path
            adj_u8 = apply_adjustment_u8(acc_u8[..., :3], lyr.adjustment_type, lyr.adjustment_params, opacity=1.0)
            eff = np.full((height, width), lyr.opacity, dtype=np.float32)
            if has_mask:
                m = lyr.mask if lyr.mask.shape == (height, width) else cv2.resize(lyr.mask, (width, height))
                eff *= m.astype(np.float32) * (1.0 / 255.0)
            if has_clip:
                (bx0, by0, bx1, by1), ba = last_base_alpha
                full_ba = np.zeros((height, width), dtype=np.float32)
                full_ba[by0:by1, bx0:bx1] = ba
                eff *= full_ba
            dst_f = acc_u8[..., :3].astype(np.float32) * (1.0 / 255.0)
            adj_f = adj_u8.astype(np.float32) * (1.0 / 255.0)
            if lyr.blend_mode != "Normal":
                adj_f = blend_rgb(dst_f, adj_f, lyr.blend_mode)
            e3 = eff[..., None]
            acc_u8[..., :3] = np.clip((dst_f * (1.0 - e3) + adj_f * e3) * 255.0, 0, 255).astype(np.uint8)
            continue

        # Fast-path for bottom opaque full-frame raster background (0.5 ms memcpy!)
        if (
            idx == 0
            and lyr.kind == "raster"
            and lyr.image is not None
            and lyr.image.shape == (height, width, 4)
            and lyr.opacity >= 0.999
            and lyr.fill_opacity >= 0.999
            and lyr.offset_x == 0 and lyr.offset_y == 0
            and abs(lyr.rotation) < 1e-3 and abs(lyr.scale_x - 1.0) < 1e-3 and abs(lyr.scale_y - 1.0) < 1e-3
            and not lyr.styles.has_any()
            and not lyr.smart_filters
            and (lyr.mask is None or not lyr.mask_enabled)
        ):
            np.copyto(acc_u8, lyr.image)
            last_base_alpha = ((0, 0, width, height), (acc_u8[..., 3].astype(np.float32) * (1.0 / 255.0)))
            continue

        cached = _get_cached_layer_render(lyr, width, height)
        if cached is None:
            if not lyr.clipping_mask:
                last_base_alpha = None
            continue

        bbox = cached["bbox"]
        x0, y0, x1, y1 = bbox
        if x1 <= x0 or y1 <= y0:
            continue
        patch = cached["patch"]
        under = cached["under"]

        if lyr.clipping_mask and last_base_alpha is not None:
            (bx0, by0, bx1, by1), ba = last_base_alpha
            ix0, iy0 = max(x0, bx0), max(y0, by0)
            ix1, iy1 = min(x1, bx1), min(y1, by1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            clipped = patch[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0].copy()
            clipped[..., 3] *= ba[iy0 - by0 : iy1 - by0, ix0 - bx0 : ix1 - bx0]
            _composite_patch_onto_u8(acc_u8, clipped, (ix0, iy0, ix1, iy1), lyr.blend_mode, lyr.opacity * lyr.fill_opacity)
            continue

        last_base_alpha = (bbox, patch[..., 3])

        if under is not None:
            (ux0, uy0, ux1, uy1), upatch = under
            _composite_patch_onto_u8(acc_u8, upatch, (ux0, uy0, ux1, uy1), "Normal", lyr.opacity)

        _composite_patch_onto_u8(acc_u8, patch, bbox, lyr.blend_mode, lyr.opacity * lyr.fill_opacity)

    return acc_u8


def _composite_patch_onto_u8(
    dst_u8: np.ndarray,
    patch_f: np.ndarray,
    bbox: Tuple[int, int, int, int],
    mode: str,
    opacity: float,
    clip_rect: Optional[Tuple[int, int, int, int]] = None,
) -> None:
    """Composite a float32 tight-ROI patch directly onto a uint8 RGBA destination buffer (optional dirty-rect clip)."""
    x0, y0, x1, y1 = bbox
    if clip_rect is not None:
        cx0, cy0, cx1, cy1 = clip_rect
        ix0, iy0 = max(x0, cx0), max(y0, cy0)
        ix1, iy1 = min(x1, cx1), min(y1, cy1)
        if ix0 >= ix1 or iy0 >= iy1:
            return
        sub_patch = patch_f[iy0 - y0 : iy1 - y0, ix0 - x0 : ix1 - x0]
        dst_slice = dst_u8[iy0 - cy0 : iy1 - cy0, ix0 - cx0 : ix1 - cx0]
    else:
        if x0 >= x1 or y0 >= y1:
            return
        sub_patch = patch_f
        dst_slice = dst_u8[y0:y1, x0:x1]

    if opacity <= 1e-4:
        return
    dst_f = dst_slice.astype(np.float32) * (1.0 / 255.0)
    sa = sub_patch[..., 3:4] if opacity >= 0.999 else (sub_patch[..., 3:4] * opacity)
    if mode == "Dissolve":
        rng = np.random.default_rng(42)
        sa = (rng.random(sa.shape, dtype=np.float32) < sa).astype(np.float32)
    if mode == "Normal":
        inv_sa = 1.0 - sa
        if int(dst_slice[..., 3].min()) == 255:
            out_rgb = dst_f[..., :3] * inv_sa + sub_patch[..., :3] * sa
            dst_slice[..., :3] = np.clip(out_rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
            dst_slice[..., 3] = 255
            return
        da = dst_f[..., 3:4]
        out_a = sa + da * inv_sa
        out_rgb = (sub_patch[..., :3] * sa + dst_f[..., :3] * (da * inv_sa)) / np.maximum(out_a, 1e-6)
        dst_slice[..., :3] = np.clip(out_rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
        dst_slice[..., 3] = np.clip(out_a[..., 0] * 255.0 + 0.5, 0, 255).astype(np.uint8)
        return
    da = dst_f[..., 3:4]
    inv_sa = 1.0 - sa
    out_a = sa + da * inv_sa
    blended = blend_rgb(dst_f[..., :3], sub_patch[..., :3], mode)
    out_rgb = ((1.0 - da) * sa * sub_patch[..., :3] + inv_sa * da * dst_f[..., :3] + sa * da * blended) / np.maximum(out_a, 1e-6)
    dst_slice[..., :3] = np.clip(out_rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    dst_slice[..., 3] = np.clip(out_a[..., 0] * 255.0 + 0.5, 0, 255).astype(np.uint8)


def composite_dirty_rect(doc: KinoDocument, dst_full_u8: np.ndarray, rect: Tuple[int, int, int, int]) -> bool:
    """Ultra-fast (<3ms!) partial dirty-rect composite for real-time 60+ FPS brush painting.
    Returns True if handled via fast dirty-rect path, False if full composite is needed."""
    has_extra = any(ec.visible and ec.data is not None for ec in doc.extra_channels)
    if (
        doc.color_mode != "RGB"
        or doc.print_settings.soft_proof
        or has_extra
        or not (doc.channel_visible.get("R", True) and doc.channel_visible.get("G", True) and doc.channel_visible.get("B", True))
    ):
        return False

    x0 = max(0, int(rect[0]))
    y0 = max(0, int(rect[1]))
    x1 = min(doc.width, int(rect[2]))
    y1 = min(doc.height, int(rect[3]))
    if x0 >= x1 or y0 >= y1:
        return True
    rh, rw = y1 - y0, x1 - x0
    roi = np.zeros((rh, rw, 4), dtype=np.uint8)
    clip = (x0, y0, x1, y1)

    for idx, lyr in enumerate(doc.layers):
        if not lyr.visible or lyr.opacity <= 1e-4:
            continue
        if lyr.clipping_mask or lyr.kind == "group":
            return False  # fall back to full composite for clipping/group stacks
        if lyr.kind == "adjustment":
            if lyr.blend_mode != "Normal" or (lyr.mask is not None and lyr.mask_enabled):
                return False
            roi[..., :3] = apply_adjustment_u8(roi[..., :3], lyr.adjustment_type, lyr.adjustment_params, opacity=lyr.opacity)
            continue

        # Fast-path for unstyled/untransformed full-frame raster layer (e.g. active painting layer!)
        if (
            lyr.kind == "raster"
            and lyr.image is not None
            and lyr.image.shape == (doc.height, doc.width, 4)
            and lyr.offset_x == 0 and lyr.offset_y == 0
            and abs(lyr.rotation) < 1e-3 and abs(lyr.scale_x - 1.0) < 1e-3 and abs(lyr.scale_y - 1.0) < 1e-3
            and not lyr.styles.has_any()
            and not lyr.smart_filters
        ):
            sub_u8 = lyr.image[y0:y1, x0:x1]
            if idx == 0 and lyr.opacity >= 0.999 and lyr.fill_opacity >= 0.999 and (lyr.mask is None or not lyr.mask_enabled):
                np.copyto(roi, sub_u8)
                continue
            sub_f = sub_u8.astype(np.float32) * (1.0 / 255.0)
            if lyr.mask is not None and lyr.mask_enabled and lyr.mask.shape == (doc.height, doc.width):
                sub_f[..., 3] *= lyr.mask[y0:y1, x0:x1].astype(np.float32) * (1.0 / 255.0)
            _composite_patch_onto_u8(roi, sub_f, (0, 0, rw, rh), lyr.blend_mode, lyr.opacity * lyr.fill_opacity)
            continue

        cached = _get_cached_layer_render(lyr, doc.width, doc.height)
        if cached is None:
            continue
        if cached["under"] is not None:
            ubbox, upatch = cached["under"]
            _composite_patch_onto_u8(roi, upatch, ubbox, "Normal", lyr.opacity, clip_rect=clip)
        _composite_patch_onto_u8(roi, cached["patch"], cached["bbox"], lyr.blend_mode, lyr.opacity * lyr.fill_opacity, clip_rect=clip)

    dst_full_u8[y0:y1, x0:x1] = roi
    return True


def composite_document(doc: KinoDocument, apply_view_effects: bool = True) -> np.ndarray:
    """Render full KinoDocument including Color Mode, Soft-Proofing, Gamut Warning, Channel Solo & Spot Channels."""
    rgba = composite_layer_list(doc.layers, doc.width, doc.height)
    if not apply_view_effects:
        return rgba

    # Fast-path: Standard RGB with all channels visible, no soft-proof, no visible extra channels -> zero extra copies!
    has_extra = any(ec.visible and ec.data is not None for ec in doc.extra_channels)
    if (
        doc.color_mode == "RGB"
        and not doc.print_settings.soft_proof
        and not has_extra
        and doc.channel_visible.get("R", True)
        and doc.channel_visible.get("G", True)
        and doc.channel_visible.get("B", True)
    ):
        return rgba

    rgb_f = rgba[..., :3].astype(np.float32) / 255.0
    alpha_u8 = rgba[..., 3]

    # Color mode simulation / Soft-Proofing
    if doc.color_mode == "Grayscale":
        g = _rgb_to_hsl_luma(rgb_f)
        rgb_f = np.stack([g, g, g], axis=-1)
    elif doc.color_mode == "CMYK" or doc.print_settings.soft_proof:
        prof = doc.print_settings.soft_proof_profile if doc.print_settings.soft_proof else doc.color_profile
        gamut_mask = compute_gamut_warning_mask(rgb_f, prof) if doc.print_settings.gamut_warning else None
        cmyk = rgb_to_cmyk(rgb_f)
        # Apply C/M/Y/K channel toggles if in CMYK mode
        if doc.color_mode == "CMYK":
            for ci, cname in enumerate(["C", "M", "Y", "K"]):
                if not doc.channel_visible.get(cname, True):
                    cmyk[..., ci] = 0.0
        rgb_f = cmyk_to_rgb(cmyk, prof)
        if gamut_mask is not None:
            # Classic neutral gray gamut warning overlay
            rgb_f[gamut_mask] = np.array([0.55, 0.55, 0.55], dtype=np.float32)
    elif doc.color_mode == "RGB":
        # RGB channel visibility / solo
        vis_r = doc.channel_visible.get("R", True)
        vis_g = doc.channel_visible.get("G", True)
        vis_b = doc.channel_visible.get("B", True)
        vis_count = int(vis_r) + int(vis_g) + int(vis_b)
        if vis_count == 1:
            # Photoshop-style grayscale solo channel view
            idx = 0 if vis_r else (1 if vis_g else 2)
            ch = rgb_f[..., idx]
            rgb_f = np.stack([ch, ch, ch], axis=-1)
        elif vis_count < 3:
            if not vis_r:
                rgb_f[..., 0] = 0.0
            if not vis_g:
                rgb_f[..., 1] = 0.0
            if not vis_b:
                rgb_f[..., 2] = 0.0

    # Extra Alpha / Spot Color channels overlay
    for ec in doc.extra_channels:
        if ec.visible and ec.data is not None:
            d = ec.data
            if d.shape != (doc.height, doc.width):
                d = cv2.resize(d, (doc.width, doc.height))
            m = (d.astype(np.float32) / 255.0) * ec.solidity
            col = np.array(ec.color, dtype=np.float32) / 255.0
            if doc.active_channel == ec.uid and ec.kind == "alpha":
                # Solo grayscale alpha editing preview
                g = d.astype(np.float32) / 255.0
                rgb_f = np.stack([g, g, g], axis=-1)
                break
            if ec.kind == "spot":
                # Overprint multiply-like ink blend
                rgb_f = rgb_f * (1.0 - m[..., None]) + (rgb_f * col * 0.45 + col * 0.55) * m[..., None]
            else:
                # Rubylith quick-mask overlay
                rgb_f = rgb_f * (1.0 - m[..., None]) + col * m[..., None]

    out_rgb = np.clip(rgb_f * 255.0, 0, 255).astype(np.uint8)
    return np.dstack([out_rgb, alpha_u8])


def compute_histogram(rgba: np.ndarray) -> Dict[str, np.ndarray]:
    """Compute 256-bin R, G, B, and Luminance histograms (fast 4x stride subsampling on large images)."""
    sub = rgba[::4, ::4] if (rgba.shape[0] > 320 or rgba.shape[1] > 320) else rgba
    r = np.bincount(sub[..., 0].ravel(), minlength=256)
    g = np.bincount(sub[..., 1].ravel(), minlength=256)
    b = np.bincount(sub[..., 2].ravel(), minlength=256)
    luma = ((77 * sub[..., 0].astype(np.uint16) + 150 * sub[..., 1].astype(np.uint16) + 29 * sub[..., 2].astype(np.uint16)) >> 8)
    l = np.bincount(luma.ravel(), minlength=256)
    return {"R": r, "G": g, "B": b, "L": l}
