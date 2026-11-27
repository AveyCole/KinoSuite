"""Advanced Computational Photography, AI Selection, Sky Replacement, Warping,
Camera Raw, Photomerge, HDR Pro, Focus Stack, Vanishing Point, Scanner Deskew/Split,
Contact Sheets, Harmonize, Neural Filters, Texture Synthesis, Light 3D,
and Scientific Measurement & Counting."""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Retouching: Spot Healing, Remove Tool, Content-Aware Fill
# ---------------------------------------------------------------------------
def spot_heal_stroke(rgba: np.ndarray, mask_u8: np.ndarray, radius: int = 5, method: str = "telea") -> np.ndarray:
    """Inpaint masked region cleanly while preserving alpha."""
    if mask_u8.max() == 0:
        return rgba
    flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    bgr = rgba[..., :3][..., ::-1]
    healed = cv2.inpaint(bgr, (mask_u8 > 20).astype(np.uint8) * 255, max(3, radius), flag)
    out = rgba.copy()
    m = (cv2.GaussianBlur(mask_u8.astype(np.float32), (5, 5), 1.2) / 255.0)[..., None]
    out[..., :3] = np.clip(rgba[..., :3] * (1.0 - m) + healed[..., ::-1] * m, 0, 255).astype(np.uint8)
    return out


def content_aware_fill(rgba: np.ndarray, selection: np.ndarray) -> np.ndarray:
    """Content-Aware Fill combining Navier-Stokes & Telea multi-scale inpainting + local grain matching."""
    mask_u8 = (selection > 0.2).astype(np.uint8) * 255
    if mask_u8.max() == 0:
        return rgba
    bgr = rgba[..., :3][..., ::-1]
    in1 = cv2.inpaint(bgr, mask_u8, 7, cv2.INPAINT_TELEA).astype(np.float32)
    in2 = cv2.inpaint(bgr, mask_u8, 11, cv2.INPAINT_NS).astype(np.float32)
    blended = (in1 * 0.6 + in2 * 0.4)

    # Match surrounding micro-texture variance so fill doesn't look plastic
    dil = cv2.dilate(mask_u8, np.ones((25, 25), np.uint8))
    ring = (dil > 0) & (mask_u8 == 0)
    if np.any(ring):
        ring_std = float(np.std(bgr[ring].astype(np.float32) - cv2.GaussianBlur(bgr, (5, 5), 1.0)[ring].astype(np.float32)))
        rng = np.random.default_rng(19)
        grain = rng.normal(0.0, min(ring_std * 0.45, 9.0), blended.shape).astype(np.float32)
        blended = np.clip(blended + grain, 0, 255)

    soft = cv2.GaussianBlur(selection.astype(np.float32), (7, 7), 2.0)[..., None]
    out = rgba.copy()
    out[..., :3] = np.clip(rgba[..., :3].astype(np.float32) * (1.0 - soft) + blended[..., ::-1] * soft, 0, 255).astype(np.uint8)
    out[..., 3] = np.maximum(out[..., 3], (selection > 0.2).astype(np.uint8) * 255)
    return out


# ---------------------------------------------------------------------------
# AI Selections & Select and Mask
# ---------------------------------------------------------------------------
def magic_wand_select(rgba: np.ndarray, x: int, y: int, tolerance: int = 32, contiguous: bool = True) -> np.ndarray:
    h, w = rgba.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return np.zeros((h, w), dtype=np.float32)
    seed = rgba[y, x, :3].astype(np.int32)
    diff = np.max(np.abs(rgba[..., :3].astype(np.int32) - seed), axis=-1)
    within = (diff <= tolerance).astype(np.uint8)
    if contiguous:
        _, labels = cv2.connectedComponents(within, connectivity=4)
        return (labels == labels[y, x]).astype(np.float32)
    return within.astype(np.float32)


def quick_select_grow(rgba: np.ndarray, seed_points: List[Tuple[int, int]], radius: int = 18) -> np.ndarray:
    """Grow a smart edge-aware selection from user brush strokes using GrabCut."""
    h, w = rgba.shape[:2]
    if not seed_points:
        return np.zeros((h, w), dtype=np.float32)
    bgr = rgba[..., :3][..., ::-1].copy()
    mask = np.full((h, w), cv2.GC_PR_BGD, dtype=np.uint8)
    # Border ring as probable background
    mask[:3, :] = cv2.GC_BGD
    mask[-3:, :] = cv2.GC_BGD
    mask[:, :3] = cv2.GC_BGD
    mask[:, -3:] = cv2.GC_BGD
    for sx, sy in seed_points:
        cv2.circle(mask, (int(sx), int(sy)), max(4, radius), cv2.GC_FGD, -1)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, mask, None, bgd, fgd, 2, cv2.GC_INIT_WITH_MASK)
        sel = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
        return cv2.GaussianBlur(sel, (3, 3), 0.7)
    except Exception:
        return (mask == cv2.GC_FGD).astype(np.float32)


def ai_select_subject(rgba: np.ndarray) -> np.ndarray:
    """AI-assisted Select Subject via border color modeling + GrabCut foreground segmentation."""
    h, w = rgba.shape[:2]
    bgr = rgba[..., :3][..., ::-1].copy()
    # Downscale for speed on large images
    scale = min(1.0, 480.0 / max(h, w))
    sw, sh = max(32, int(w * scale)), max(32, int(h * scale))
    small = cv2.resize(bgr, (sw, sh), interpolation=cv2.INTER_AREA)

    # Estimate saliency map vs border color
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    border = np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]], axis=0)
    bg_med = np.median(border, axis=0)
    dist = np.linalg.norm(lab - bg_med, axis=-1)
    dist_norm = dist / max(float(dist.max()), 1.0)

    # Build GrabCut initial rect from salient region
    sal_mask = (dist_norm > np.percentile(dist_norm, 62)).astype(np.uint8)
    ys, xs = np.nonzero(sal_mask)
    if len(xs) > 40:
        x0, x1 = max(2, int(xs.min())), min(sw - 3, int(xs.max()))
        y0, y1 = max(2, int(ys.min())), min(sh - 3, int(ys.max()))
        rect = (x0, y0, max(10, x1 - x0), max(10, y1 - y0))
    else:
        rect = (int(sw * 0.12), int(sh * 0.12), int(sw * 0.76), int(sh * 0.76))

    gc_mask = np.zeros((sh, sw), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(small, gc_mask, rect, bgd, fgd, 4, cv2.GC_INIT_WITH_RECT)
        fg = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
    except Exception:
        fg = sal_mask.astype(np.float32)

    if fg.mean() < 0.02 or fg.mean() > 0.96:
        fg = (dist_norm > 0.32).astype(np.float32)

    full = cv2.resize(fg, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(full, (5, 5), 1.2)


def ai_select_object(rgba: np.ndarray, rect_xywh: Tuple[int, int, int, int]) -> np.ndarray:
    """AI Select Object inside a user-dragged bounding box via GrabCut."""
    h, w = rgba.shape[:2]
    x, y, rw, rh = rect_xywh
    x = max(1, min(w - 4, int(x)))
    y = max(1, min(h - 4, int(y)))
    rw = max(4, min(w - x - 1, int(rw)))
    rh = max(4, min(h - y - 1, int(rh)))
    bgr = rgba[..., :3][..., ::-1].copy()
    mask = np.zeros((h, w), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, mask, (x, y, rw, rh), bgd, fgd, 4, cv2.GC_INIT_WITH_RECT)
        sel = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
        return cv2.GaussianBlur(sel, (3, 3), 0.9)
    except Exception:
        out = np.zeros((h, w), dtype=np.float32)
        out[y:y + rh, x:x + rw] = 1.0
        return out


def ai_select_sky(rgba: np.ndarray) -> np.ndarray:
    """AI Select Sky: upper-region color/brightness/gradient horizon segmentation."""
    h, w = rgba.shape[:2]
    rgb = rgba[..., :3].astype(np.float32)
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV).astype(np.float32)

    # Sample top band as sky reference
    top_band = rgb[: max(6, int(h * 0.15)), :, :].reshape(-1, 3)
    sky_col = np.median(top_band, axis=0)
    sky_std = np.maximum(np.std(top_band, axis=0), 18.0)

    # Color similarity to top sky + smoothness (low texture) + vertical prior
    dist = np.sqrt(np.mean(((rgb - sky_col) / (sky_std * 2.4)) ** 2, axis=-1))
    gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY)
    grad = cv2.Laplacian(gray, cv2.CV_32F)
    smooth = np.exp(-np.abs(grad) / 28.0)

    yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    v_prior = np.clip(1.25 - yy * 1.45, 0.0, 1.0)

    # Also boost bright/blue-ish upper pixels
    bright = hsv[..., 2] / 255.0
    score = np.exp(-dist * 0.85) * 0.65 + smooth * 0.20 + bright * 0.15
    prob = score * v_prior

    raw = (prob > 0.42).astype(np.uint8)
    # Keep only components connected to the top 15% edge
    num, labels = cv2.connectedComponents(raw, connectivity=8)
    top_labels = set(np.unique(labels[: max(4, int(h * 0.12)), :])) - {0}
    sky = np.isin(labels, list(top_labels)).astype(np.float32)

    if sky.mean() < 0.02:
        # Graceful fallback gradient in upper 38%
        sky = np.clip((0.38 - yy) / 0.12, 0.0, 1.0) * np.ones((h, w), dtype=np.float32)
    else:
        sky = cv2.GaussianBlur(sky, (9, 9), 2.2)
    return np.clip(sky, 0.0, 1.0).astype(np.float32)


def refine_select_and_mask(
    rgba: np.ndarray,
    mask: np.ndarray,
    smooth: float = 2.0,
    feather: float = 1.5,
    contrast: float = 0.2,
    shift_edge: float = 0.0,
    decontaminate: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """Select and Mask: edge-guided matte refinement for hair & fine edges + optional color decontamination."""
    m = np.clip(mask.astype(np.float32), 0.0, 1.0)

    # Shift edge (dilate / erode)
    if abs(shift_edge) >= 0.5:
        k = max(3, int(abs(shift_edge) * 2) | 1)
        kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        if shift_edge > 0:
            m = cv2.dilate(m, kern)
        else:
            m = cv2.erode(m, kern)

    # Smooth edges
    if smooth > 0.2:
        k = max(3, int(smooth * 2) | 1)
        m = cv2.GaussianBlur(m, (k, k), smooth * 0.5)

    # Edge-aware guided-like refinement using image luminance
    gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    m_bil = cv2.bilateralFilter(m, 7, 0.25, 5.0)
    edge_band = (m > 0.05) & (m < 0.95)
    m = np.where(edge_band, m_bil * 0.7 + m * 0.3, m)

    # Contrast boost
    if contrast > 0.01:
        gain = 1.0 + contrast * 5.0
        m = np.clip((m - 0.5) * gain + 0.5, 0.0, 1.0)

    # Feather
    if feather > 0.2:
        k = max(3, int(feather * 3) | 1)
        m = cv2.GaussianBlur(m, (k, k), feather)

    out_rgba = rgba.copy()
    if decontaminate:
        # Replace fringe colors near semi-transparent edge with nearby solid foreground color
        fg_solid = m > 0.85
        fringe = (m > 0.05) & (m < 0.85)
        if np.any(fg_solid) and np.any(fringe):
            blurred_fg = cv2.GaussianBlur(rgba[..., :3], (15, 15), 5.0)
            out_rgba[..., :3][fringe] = (
                rgba[..., :3][fringe].astype(np.float32) * 0.45
                + blurred_fg[fringe].astype(np.float32) * 0.55
            ).astype(np.uint8)

    return np.clip(m, 0.0, 1.0).astype(np.float32), out_rgba


# ---------------------------------------------------------------------------
# Sky Replacement (One-Step + Built-in Procedural Studio Skies)
# ---------------------------------------------------------------------------
SKY_PRESETS = [
    "Golden Hour Sunset",
    "Crisp Blue Cumulus",
    "Dramatic Twilight Aurora",
    "Moody Storm Clouds",
    "Starry Milky Way Night",
    "Pastel Cotton Candy",
]


def generate_procedural_sky(width: int, height: int, preset: str = "Golden Hour Sunset", seed: int = 11) -> np.ndarray:
    """Synthesize a high-resolution photorealistic gradient + multi-octave cloud sky (H,W,3) uint8."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    u = xx / max(width - 1, 1)
    v = yy / max(height - 1, 1)

    palettes = {
        "Golden Hour Sunset": ((28, 42, 92), (218, 108, 76), (255, 214, 128), (255, 224, 180)),
        "Crisp Blue Cumulus": ((26, 92, 198), (92, 166, 238), (195, 226, 250), (252, 254, 255)),
        "Dramatic Twilight Aurora": ((10, 18, 42), (28, 62, 112), (48, 188, 164), (110, 255, 198)),
        "Moody Storm Clouds": ((24, 30, 44), (58, 68, 86), (112, 124, 142), (175, 185, 200)),
        "Starry Milky Way Night": ((6, 10, 24), (16, 24, 52), (38, 48, 88), (185, 212, 255)),
        "Pastel Cotton Candy": ((118, 152, 232), (222, 158, 210), (255, 208, 196), (255, 240, 246)),
    }
    top_c, mid_c, hor_c, cloud_c = palettes.get(preset, palettes["Golden Hour Sunset"])
    top_c = np.array(top_c, dtype=np.float32)
    mid_c = np.array(mid_c, dtype=np.float32)
    hor_c = np.array(hor_c, dtype=np.float32)
    cloud_c = np.array(cloud_c, dtype=np.float32)

    sky = np.where(
        v[..., None] < 0.55,
        top_c * (1.0 - v[..., None] / 0.55) + mid_c * (v[..., None] / 0.55),
        mid_c * (1.0 - (v[..., None] - 0.55) / 0.45) + hor_c * ((v[..., None] - 0.55) / 0.45),
    )

    # Multi-octave smooth fBm clouds
    rng = np.random.default_rng(seed)
    clouds = np.zeros((height, width), dtype=np.float32)
    amp = 0.55
    for grid in (8, 16, 32, 64):
        noise = rng.random((max(4, grid // 2), grid), dtype=np.float32)
        up = cv2.resize(noise, (width, height), interpolation=cv2.INTER_CUBIC)
        clouds += up * amp
        amp *= 0.52
    clouds = (clouds - clouds.min()) / max(float(clouds.max() - clouds.min()), 1e-5)

    if preset == "Starry Milky Way Night":
        # Stars + subtle nebula band
        nebula = np.exp(-((v - (0.35 + 0.25 * u)) ** 2) / 0.04) * clouds * 0.55
        sky = sky + nebula[..., None] * np.array([115, 130, 215], dtype=np.float32)
        stars = (rng.random((height, width)) > 0.9965).astype(np.float32) * rng.uniform(150, 255, (height, width))
        sky = sky + stars[..., None]
    elif preset == "Dramatic Twilight Aurora":
        curtain = np.sin(u * 14.0 + clouds * 4.5) * 0.5 + 0.5
        band = np.exp(-((v - 0.34 - 0.08 * np.sin(u * 6.0)) ** 2) / 0.03) * curtain
        sky = sky + band[..., None] * np.array([50, 230, 175], dtype=np.float32) * 0.72
    else:
        c_mask = np.clip((clouds - 0.44) * 2.4, 0.0, 1.0) * (1.0 - v * 0.35)
        sky = sky * (1.0 - c_mask[..., None] * 0.72) + cloud_c * (c_mask[..., None] * 0.72)
        if preset == "Golden Hour Sunset":
            sun = np.exp(-((u - 0.68) ** 2 + ((v - 0.62) * (height / max(width, 1))) ** 2) / 0.015)
            sky += sun[..., None] * np.array([255, 220, 145], dtype=np.float32) * 0.85

    return np.clip(sky, 0, 255).astype(np.uint8)


def replace_sky(
    rgba: np.ndarray,
    sky_preset: str = "Golden Hour Sunset",
    custom_sky: Optional[np.ndarray] = None,
    shift_edge: float = 0.0,
    relight_fg: float = 0.35,
    temperature: float = 0.0,
) -> np.ndarray:
    """One-step Sky Replacement with horizon edge refinement and foreground color relighting."""
    h, w = rgba.shape[:2]
    sky_mask = ai_select_sky(rgba)
    if abs(shift_edge) >= 0.5:
        sky_mask, _ = refine_select_and_mask(rgba, sky_mask, smooth=2.0, feather=3.0, shift_edge=shift_edge)

    if custom_sky is not None:
        sky_rgb = cv2.resize(custom_sky[..., :3], (w, h), interpolation=cv2.INTER_CUBIC)
    else:
        sky_rgb = generate_procedural_sky(w, h, sky_preset)

    if abs(temperature) > 0.01:
        sf = sky_rgb.astype(np.float32)
        sf[..., 0] = np.clip(sf[..., 0] + temperature * 38.0, 0, 255)
        sf[..., 2] = np.clip(sf[..., 2] - temperature * 38.0, 0, 255)
        sky_rgb = sf.astype(np.uint8)

    fg = rgba[..., :3].astype(np.float32)
    if relight_fg > 0.01:
        # Match foreground ambient tint gently to new sky's average hue
        sky_tint = sky_rgb.astype(np.float32).mean(axis=(0, 1))
        fg_mean = np.maximum(fg.mean(axis=(0, 1)), 1.0)
        ratio = np.clip(sky_tint / fg_mean, 0.72, 1.32)
        relight = np.clip(fg * (1.0 - relight_fg * 0.45 + ratio * relight_fg * 0.45), 0, 255)
    else:
        relight = fg

    m = sky_mask[..., None]
    comp = relight * (1.0 - m) + sky_rgb.astype(np.float32) * m
    return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), rgba[..., 3]])


# ---------------------------------------------------------------------------
# Camera Raw Studio Pipeline
# ---------------------------------------------------------------------------
def apply_camera_raw(rgba: np.ndarray, params: Dict[str, float]) -> np.ndarray:
    """Full float32 Camera Raw develop pipeline."""
    rgb = rgba[..., :3].astype(np.float32) / 255.0

    # White Balance (Temperature & Tint)
    temp = params.get("temperature", 0.0) / 100.0
    tint = params.get("tint", 0.0) / 100.0
    rgb[..., 0] *= 1.0 + temp * 0.35 + tint * 0.12
    rgb[..., 1] *= 1.0 - tint * 0.22
    rgb[..., 2] *= 1.0 - temp * 0.35 + tint * 0.12
    rgb = np.clip(rgb, 0.0, 2.0)

    # Exposure
    exp = params.get("exposure", 0.0)
    rgb = rgb * (2.0 ** exp)

    # Contrast
    contrast = params.get("contrast", 0.0) / 100.0
    rgb = (rgb - 0.5) * (1.0 + contrast * 0.85) + 0.5
    rgb = np.clip(rgb, 0.0, 1.0)

    # Highlights / Shadows / Whites / Blacks
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    hi_w = np.clip((luma - 0.5) * 2.0, 0.0, 1.0)[..., None]
    sh_w = np.clip((0.5 - luma) * 2.0, 0.0, 1.0)[..., None]
    wh_w = np.clip((luma - 0.78) * 4.5, 0.0, 1.0)[..., None]
    bl_w = np.clip((0.22 - luma) * 4.5, 0.0, 1.0)[..., None]

    rgb += hi_w * (params.get("highlights", 0.0) / 100.0) * 0.35
    rgb += sh_w * (params.get("shadows", 0.0) / 100.0) * 0.38
    rgb += wh_w * (params.get("whites", 0.0) / 100.0) * 0.25
    rgb += bl_w * (params.get("blacks", 0.0) / 100.0) * 0.25
    rgb = np.clip(rgb, 0.0, 1.0)

    # Clarity & Texture (local midtone micro-contrast)
    clarity = params.get("clarity", 0.0) / 100.0
    if abs(clarity) > 0.01:
        blur = cv2.GaussianBlur(rgb, (0, 0), 9.0)
        rgb = np.clip(rgb + (rgb - blur) * clarity * 0.75, 0.0, 1.0)

    # Dehaze
    dehaze = params.get("dehaze", 0.0) / 100.0
    if abs(dehaze) > 0.01:
        dark = np.min(rgb, axis=-1, keepdims=True)
        rgb = np.clip((rgb - dark * dehaze * 0.35) / max(1.0 - dehaze * 0.28, 0.35), 0.0, 1.0)

    # Vibrance & Saturation
    vib = params.get("vibrance", 0.0) / 100.0
    sat = params.get("saturation", 0.0) / 100.0
    if abs(vib) > 0.01 or abs(sat) > 0.01:
        mx = np.max(rgb, axis=-1, keepdims=True)
        mn = np.min(rgb, axis=-1, keepdims=True)
        avg = rgb.mean(axis=-1, keepdims=True)
        rgb = np.clip(avg + (rgb - avg) * (1.0 + vib * (1.0 - (mx - mn)) + sat), 0.0, 1.0)

    # Sharpening
    sharp = params.get("sharpen", 0.0) / 100.0
    if sharp > 0.01:
        blur = cv2.GaussianBlur(rgb, (0, 0), 1.4)
        rgb = np.clip(rgb + (rgb - blur) * sharp * 1.4, 0.0, 1.0)

    # Noise Reduction
    denoise = params.get("denoise", 0.0)
    u8 = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    if denoise > 1.0:
        u8 = cv2.bilateralFilter(u8, 7, denoise * 1.4, denoise * 0.8)

    # Vignette
    vig = params.get("vignette", 0.0) / 100.0
    if abs(vig) > 0.01:
        h, w = u8.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = ((xx - w * 0.5) / max(w * 0.5, 1)) ** 2 + ((yy - h * 0.5) / max(h * 0.5, 1)) ** 2
        fac = np.clip(1.0 - vig * 0.55 * d, 0.15, 1.6)[..., None]
        u8 = np.clip(u8.astype(np.float32) * fac, 0, 255).astype(np.uint8)

    return np.dstack([u8, rgba[..., 3]])


# ---------------------------------------------------------------------------
# Color Match between Images & Harmonize (Generative AI Lighting Blend)
# ---------------------------------------------------------------------------
def match_color_reinhard(target_rgba: np.ndarray, ref_rgba: np.ndarray, strength: float = 0.85) -> np.ndarray:
    """Reinhard Lab color transfer to match color & tone between two images."""
    tgt_lab = cv2.cvtColor(target_rgba[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    ref_lab = cv2.cvtColor(ref_rgba[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    t_mean, t_std = tgt_lab.mean(axis=(0, 1)), np.maximum(tgt_lab.std(axis=(0, 1)), 1e-4)
    r_mean, r_std = ref_lab.mean(axis=(0, 1)), np.maximum(ref_lab.std(axis=(0, 1)), 1e-4)
    matched = (tgt_lab - t_mean) * (r_std / t_std) + r_mean
    blended = tgt_lab * (1.0 - strength) + matched * strength
    rgb_out = cv2.cvtColor(np.clip(blended, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    return np.dstack([rgb_out, target_rgba[..., 3]])


def harmonize_layer_to_scene(fg_rgba: np.ndarray, bg_rgba: np.ndarray, strength: float = 0.8) -> np.ndarray:
    """Harmonize: blends an added foreground object layer into the scene's ambient color, contrast & directional light."""
    alpha = fg_rgba[..., 3] > 20
    if not np.any(alpha):
        return fg_rgba

    fg_lab = cv2.cvtColor(fg_rgba[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(bg_rgba[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)

    # Sample background around the object's bounding box for local lighting context
    ys, xs = np.nonzero(alpha)
    y0, y1 = max(0, int(ys.min()) - 60), min(bg_rgba.shape[0], int(ys.max()) + 60)
    x0, x1 = max(0, int(xs.min()) - 60), min(bg_rgba.shape[1], int(xs.max()) + 60)
    bg_local = bg_lab[y0:y1, x0:x1]

    f_mean = fg_lab[alpha].mean(axis=0)
    f_std = np.maximum(fg_lab[alpha].std(axis=0), 6.0)
    b_mean = bg_local.mean(axis=(0, 1))
    b_std = np.maximum(bg_local.std(axis=(0, 1)), 6.0)

    # Match chromaticity strongly and luminance gently so object keeps natural form
    res_lab = fg_lab.copy()
    res_lab[..., 0] = (fg_lab[..., 0] - f_mean[0]) * (0.65 + 0.35 * (b_std[0] / f_std[0])) + (f_mean[0] * 0.55 + b_mean[0] * 0.45)
    res_lab[..., 1] = (fg_lab[..., 1] - f_mean[1]) * (b_std[1] / f_std[1]) * 0.65 + b_mean[1] * 0.55 + f_mean[1] * 0.45
    res_lab[..., 2] = (fg_lab[..., 2] - f_mean[2]) * (b_std[2] / f_std[2]) * 0.65 + b_mean[2] * 0.55 + f_mean[2] * 0.45

    # Directional lighting gradient matching left-to-right luminance slope of background
    h, w = fg_rgba.shape[:2]
    bg_left = float(bg_local[:, : max(1, bg_local.shape[1] // 2), 0].mean())
    bg_right = float(bg_local[:, max(1, bg_local.shape[1] // 2):, 0].mean())
    slope = np.clip((bg_right - bg_left) / 255.0, -0.25, 0.25)
    xx = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    res_lab[..., 0] = np.clip(res_lab[..., 0] + xx * slope * 65.0 * strength, 0, 255)

    blended_lab = fg_lab * (1.0 - strength) + res_lab * strength
    out_rgb = cv2.cvtColor(np.clip(blended_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    return np.dstack([out_rgb, fg_rgba[..., 3]])


# ---------------------------------------------------------------------------
# Warping: Liquify, Puppet Warp (MLS), Perspective Warp, Lens Correction,
#          Vanishing Point, and Content-Aware Scale (Seam Carving)
# ---------------------------------------------------------------------------
def liquify_brush_step(
    disp_x: np.ndarray,
    disp_y: np.ndarray,
    cx: float,
    cy: float,
    dx: float,
    dy: float,
    radius: float,
    pressure: float = 0.5,
    tool: str = "Forward Warp",  # Forward Warp | Twirl CW | Twirl CCW | Pucker | Bloat | Reconstruct
) -> None:
    """Accumulate Liquify displacement field in-place."""
    h, w = disp_x.shape
    r = max(4.0, float(radius))
    x0, x1 = max(0, int(cx - r)), min(w, int(cx + r) + 1)
    y0, y1 = max(0, int(cy - r)), min(h, int(cy + r) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    rx, ry = xx - cx, yy - cy
    dist2 = rx * rx + ry * ry
    inside = dist2 < (r * r)
    falloff = np.where(inside, (1.0 - dist2 / (r * r)) ** 2, 0.0).astype(np.float32) * pressure

    if tool == "Forward Warp":
        disp_x[y0:y1, x0:x1] -= dx * falloff
        disp_y[y0:y1, x0:x1] -= dy * falloff
    elif tool in ("Twirl CW", "Twirl CCW"):
        ang = (0.35 if tool == "Twirl CW" else -0.35) * falloff
        ca, sa = np.cos(ang), np.sin(ang)
        nx = rx * ca - ry * sa - rx
        ny = rx * sa + ry * ca - ry
        disp_x[y0:y1, x0:x1] += nx
        disp_y[y0:y1, x0:x1] += ny
    elif tool == "Pucker":
        disp_x[y0:y1, x0:x1] += rx * falloff * 0.25
        disp_y[y0:y1, x0:x1] += ry * falloff * 0.25
    elif tool == "Bloat":
        disp_x[y0:y1, x0:x1] -= rx * falloff * 0.25
        disp_y[y0:y1, x0:x1] -= ry * falloff * 0.25
    elif tool == "Reconstruct":
        disp_x[y0:y1, x0:x1] *= (1.0 - falloff)
        disp_y[y0:y1, x0:x1] *= (1.0 - falloff)


def apply_liquify_field(rgba: np.ndarray, disp_x: np.ndarray, disp_y: np.ndarray) -> np.ndarray:
    h, w = rgba.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return cv2.remap(
        rgba,
        (xx + disp_x).astype(np.float32),
        (yy + disp_y).astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )


def apply_puppet_warp(
    rgba: np.ndarray,
    orig_pins: List[Tuple[float, float]],
    moved_pins: List[Tuple[float, float]],
) -> np.ndarray:
    """Inverse-distance / Shepard Moving-Least-Squares Puppet Warp on a coarse grid remapped smoothly."""
    if len(orig_pins) < 2 or len(orig_pins) != len(moved_pins):
        return rgba
    h, w = rgba.shape[:2]
    # Compute smooth warp on coarse 64x64 grid then upsample with cubic interpolation
    gh, gw = min(64, h), min(64, w)
    gy, gx = np.mgrid[0:gh, 0:gw].astype(np.float32)
    px_grid = gx * (w / float(gw))
    py_grid = gy * (h / float(gh))

    p = np.array(moved_pins, dtype=np.float32)  # destination pins
    q = np.array(orig_pins, dtype=np.float32)   # source pins
    deltas = q - p  # displacement back to source

    map_x = px_grid.copy()
    map_y = py_grid.copy()
    w_sum = np.zeros((gh, gw), dtype=np.float32)
    dx_acc = np.zeros((gh, gw), dtype=np.float32)
    dy_acc = np.zeros((gh, gw), dtype=np.float32)

    for i in range(len(p)):
        dist2 = (px_grid - p[i, 0]) ** 2 + (py_grid - p[i, 1]) ** 2 + 180.0
        wt = 1.0 / (dist2 ** 1.35)
        w_sum += wt
        dx_acc += wt * deltas[i, 0]
        dy_acc += wt * deltas[i, 1]

    map_x += dx_acc / np.maximum(w_sum, 1e-8)
    map_y += dy_acc / np.maximum(w_sum, 1e-8)

    full_mx = cv2.resize(map_x, (w, h), interpolation=cv2.INTER_CUBIC)
    full_my = cv2.resize(map_y, (w, h), interpolation=cv2.INTER_CUBIC)
    return cv2.remap(rgba, full_mx, full_my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def apply_perspective_warp(
    rgba: np.ndarray,
    src_quad: List[Tuple[float, float]],
    dst_quad: List[Tuple[float, float]],
) -> np.ndarray:
    """4-point homography Perspective Warp."""
    h, w = rgba.shape[:2]
    src = np.array(src_quad, dtype=np.float32)
    dst = np.array(dst_quad, dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(rgba, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def apply_lens_correction(
    rgba: np.ndarray,
    k1: float = 0.0,
    vertical_tilt: float = 0.0,
    horizontal_tilt: float = 0.0,
    rotate_deg: float = 0.0,
    vignette_fix: float = 0.0,
) -> np.ndarray:
    """Fix barrel/pincushion lens distortion, keystone tilt, horizon rotation & lens vignette."""
    h, w = rgba.shape[:2]
    out = rgba.copy()

    if abs(k1) > 1e-4:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = w * 0.5, h * 0.5
        nx = (xx - cx) / max(cx, 1.0)
        ny = (yy - cy) / max(cy, 1.0)
        r2 = nx * nx + ny * ny
        scale = 1.0 + k1 * r2
        map_x = (cx + nx * scale * cx).astype(np.float32)
        map_y = (cy + ny * scale * cy).astype(np.float32)
        out = cv2.remap(out, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    if abs(vertical_tilt) > 1e-3 or abs(horizontal_tilt) > 1e-3:
        dx = w * 0.18 * vertical_tilt
        dy = h * 0.18 * horizontal_tilt
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32([
            [max(0, dx), max(0, dy)],
            [w - max(0, dx), max(0, -dy)],
            [w - max(0, -dx), h - max(0, -dy)],
            [max(0, -dx), h - max(0, dy)],
        ])
        M = cv2.getPerspectiveTransform(src, dst)
        out = cv2.warpPerspective(out, M, (w, h), borderMode=cv2.BORDER_REFLECT)

    if abs(rotate_deg) > 1e-3:
        M = cv2.getRotationMatrix2D((w * 0.5, h * 0.5), rotate_deg, 1.0)
        out = cv2.warpAffine(out, M, (w, h), borderMode=cv2.BORDER_REFLECT)

    if abs(vignette_fix) > 1e-3:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r2 = ((xx - w * 0.5) / max(w * 0.5, 1)) ** 2 + ((yy - h * 0.5) / max(h * 0.5, 1)) ** 2
        gain = np.clip(1.0 + vignette_fix * 0.45 * r2, 0.4, 1.8)[..., None]
        out[..., :3] = np.clip(out[..., :3].astype(np.float32) * gain, 0, 255).astype(np.uint8)

    return out


def vanishing_point_tile_or_paste(
    base_rgba: np.ndarray,
    plane_quad: List[Tuple[float, float]],
    tile_rgba: np.ndarray,
    repeat_x: int = 3,
    repeat_y: int = 3,
    opacity: float = 0.88,
) -> np.ndarray:
    """Vanishing Point: tile/clone/paint a texture or patch in true perspective onto a 4-point wall/floor plane."""
    h, w = base_rgba.shape[:2]
    tw, th = 512, 512
    # Build tiled plane texture
    cell_w = max(8, tw // max(1, repeat_x))
    cell_h = max(8, th // max(1, repeat_y))
    cell = cv2.resize(tile_rgba, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
    tiled = np.tile(cell, (repeat_y + 1, repeat_x + 1, 1))[:th, :tw]

    src = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])
    dst = np.float32(plane_quad)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(tiled, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

    # Soft mask inside quad
    quad_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(quad_mask, dst.astype(np.int32), 255)
    soft = (cv2.GaussianBlur(quad_mask.astype(np.float32), (5, 5), 1.0) / 255.0) * (warped[..., 3].astype(np.float32) / 255.0) * opacity
    out = base_rgba.copy()
    m = soft[..., None]
    out[..., :3] = np.clip(base_rgba[..., :3].astype(np.float32) * (1.0 - m) + warped[..., :3].astype(np.float32) * m, 0, 255).astype(np.uint8)
    return out


def content_aware_scale(
    rgba: np.ndarray,
    new_width: int,
    new_height: int,
    protect_mask: Optional[np.ndarray] = None,
    protect_skin: bool = True,
) -> np.ndarray:
    """Real DP Seam Carving Content-Aware Scale with skin-tone & mask protection."""
    cur = rgba.copy()
    pm = protect_mask.copy() if protect_mask is not None else None

    def _carve_width(img: np.ndarray, pmask: Optional[np.ndarray], target_w: int) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        h, w = img.shape[:2]
        if target_w == w:
            return img, pmask
        if target_w > w:
            # Expand by inserting low-energy seams or gentle hybrid resize
            return cv2.resize(img, (target_w, h), interpolation=cv2.INTER_CUBIC), (
                cv2.resize(pmask, (target_w, h)) if pmask is not None else None
            )
        # Work at reasonable speed: limit carved seams to <= 160, finish remaining with bicubic if huge jump
        steps = min(w - target_w, 140)
        for _ in range(steps):
            hh, ww = img.shape[:2]
            gray = cv2.cvtColor(img[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
            gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            energy = np.abs(gx) + np.abs(gy)
            if protect_skin:
                hsv = cv2.cvtColor(img[..., :3], cv2.COLOR_RGB2HSV)
                skin = (hsv[..., 0] < 24) & (hsv[..., 1] > 35) & (hsv[..., 1] < 185) & (hsv[..., 2] > 60)
                energy += skin.astype(np.float32) * 800.0
            if pmask is not None and pmask.shape == (hh, ww):
                energy += pmask * 1200.0

            M = energy.copy()
            back = np.zeros((hh, ww), dtype=np.int32)
            for r in range(1, hh):
                prev = M[r - 1]
                left = np.concatenate([[1e12], prev[:-1]])
                right = np.concatenate([prev[1:], [1e12]])
                stacked = np.stack([left, prev, right], axis=0)
                idx = np.argmin(stacked, axis=0)
                M[r] += stacked[idx, np.arange(ww)]
                back[r] = np.arange(ww) + (idx - 1)

            seam = np.zeros(hh, dtype=np.int32)
            seam[-1] = int(np.argmin(M[-1]))
            for r in range(hh - 2, -1, -1):
                seam[r] = back[r + 1, seam[r + 1]]

            keep = np.ones((hh, ww), dtype=bool)
            keep[np.arange(hh), seam] = False
            img = img[keep].reshape((hh, ww - 1, 4))
            if pmask is not None:
                pmask = pmask[keep].reshape((hh, ww - 1))

        if img.shape[1] != target_w:
            img = cv2.resize(img, (target_w, img.shape[0]), interpolation=cv2.INTER_AREA)
            if pmask is not None:
                pmask = cv2.resize(pmask, (target_w, img.shape[0]))
        return img, pmask

    cur, pm = _carve_width(cur, pm, max(16, int(new_width)))
    if int(new_height) != cur.shape[0]:
        # Transpose, carve width, transpose back
        cur_t = np.transpose(cur, (1, 0, 2)).copy()
        pm_t = pm.T.copy() if pm is not None else None
        cur_t, _ = _carve_width(cur_t, pm_t, max(16, int(new_height)))
        cur = np.transpose(cur_t, (1, 0, 2)).copy()
    return cur


# ---------------------------------------------------------------------------
# Photo Merging: Photomerge Panorama, Auto-Align, Auto-Blend, HDR Pro, Focus Stack
# ---------------------------------------------------------------------------
def photomerge_panorama(images: List[np.ndarray]) -> np.ndarray:
    """Stitch multiple overlapping photos into a seamless panorama."""
    if not images:
        raise ValueError("No images provided")
    if len(images) == 1:
        return images[0]
    bgrs = [img[..., :3][..., ::-1].copy() for img in images]
    try:
        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
        status, pano = stitcher.stitch(bgrs)
        if status == cv2.Stitcher_OK and pano is not None and pano.size > 0:
            rgb = pano[..., ::-1]
            return np.dstack([rgb, np.full(rgb.shape[:2], 255, dtype=np.uint8)])
    except Exception:
        pass

    # Fallback: feature-aligned feather blend horizontally
    base_h = min(im.shape[0] for im in images)
    resized = [cv2.resize(im, (int(im.shape[1] * base_h / im.shape[0]), base_h)) for im in images]
    overlap = min(80, min(im.shape[1] for im in resized) // 4)
    total_w = sum(im.shape[1] for im in resized) - overlap * (len(resized) - 1)
    canvas = np.zeros((base_h, total_w, 4), dtype=np.float32)
    x = 0
    for idx, im in enumerate(resized):
        iw = im.shape[1]
        if idx == 0:
            canvas[:, :iw] = im.astype(np.float32)
        else:
            ramp = np.linspace(0.0, 1.0, overlap, dtype=np.float32)[None, :, None]
            canvas[:, x:x + overlap] = canvas[:, x:x + overlap] * (1.0 - ramp) + im[:, :overlap].astype(np.float32) * ramp
            canvas[:, x + overlap:x + iw] = im[:, overlap:].astype(np.float32)
        x += iw - overlap
    return np.clip(canvas, 0, 255).astype(np.uint8)


def auto_align_layers(layers_rgba: List[np.ndarray]) -> List[np.ndarray]:
    """ORB feature + RANSAC homography Auto-Align for handheld group shots & stacks."""
    if len(layers_rgba) < 2:
        return layers_rgba
    ref = layers_rgba[0]
    h, w = ref.shape[:2]
    ref_gray = cv2.cvtColor(ref[..., :3], cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(1200)
    kp0, des0 = orb.detectAndCompute(ref_gray, None)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    aligned = [ref.copy()]
    for img in layers_rgba[1:]:
        cur = cv2.resize(img, (w, h)) if img.shape[:2] != (h, w) else img
        g = cv2.cvtColor(cur[..., :3], cv2.COLOR_RGB2GRAY)
        kp1, des1 = orb.detectAndCompute(g, None)
        if des0 is not None and des1 is not None and len(kp0) >= 8 and len(kp1) >= 8:
            matches = sorted(bf.match(des1, des0), key=lambda m: m.distance)[:80]
            if len(matches) >= 8:
                pts1 = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
                pts0 = np.float32([kp0[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
                H, _ = cv2.findHomography(pts1, pts0, cv2.RANSAC, 5.0)
                if H is not None:
                    warped = cv2.warpPerspective(cur, H, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
                    aligned.append(warped)
                    continue
        aligned.append(cur.copy())
    return aligned


def auto_blend_layers(layers_rgba: List[np.ndarray]) -> np.ndarray:
    """Seamless multi-band / feather Auto-Blend for combining group shots or composites."""
    if not layers_rgba:
        raise ValueError("No layers")
    if len(layers_rgba) == 1:
        return layers_rgba[0].copy()
    h, w = layers_rgba[0].shape[:2]
    acc = np.zeros((h, w, 3), dtype=np.float32)
    w_sum = np.zeros((h, w, 1), dtype=np.float32)
    for img in layers_rgba:
        cur = cv2.resize(img, (w, h)) if img.shape[:2] != (h, w) else img
        alpha = (cur[..., 3:4].astype(np.float32) / 255.0)
        # Prefer sharper & well-exposed regions in overlap
        gray = cv2.cvtColor(cur[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        sharp = np.abs(cv2.Laplacian(gray, cv2.CV_32F)) + 0.1
        wt = alpha * cv2.GaussianBlur(sharp, (15, 15), 4.0)[..., None]
        acc += cur[..., :3].astype(np.float32) * wt
        w_sum += wt
    rgb = np.where(w_sum > 1e-5, acc / np.maximum(w_sum, 1e-5), layers_rgba[0][..., :3].astype(np.float32))
    return np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), np.full((h, w), 255, dtype=np.uint8)])


def merge_to_hdr_pro(
    images: List[np.ndarray],
    exposure: float = 0.0,
    gamma: float = 1.0,
    detail: float = 0.35,
    vibrance: float = 0.25,
    align: bool = True,
) -> np.ndarray:
    """Merge to HDR Pro: bracket alignment + Mertens Exposure Fusion + detail/tone mapping."""
    if not images:
        raise ValueError("No bracketed images")
    h, w = images[0].shape[:2]
    bgrs = [cv2.resize(im[..., :3], (w, h))[..., ::-1].copy() for im in images]
    if align and len(bgrs) >= 2:
        try:
            align_mtb = cv2.createAlignMTB()
            align_mtb.process(bgrs, bgrs)
        except Exception:
            pass
    merge_mertens = cv2.createMergeMertens()
    hdr = merge_mertens.process(bgrs)  # float32 ~ [0..1]
    hdr = np.clip(hdr * (2.0 ** exposure), 0.0, 2.0)
    # Local detail boost
    if abs(detail) > 0.01:
        blur = cv2.GaussianBlur(hdr, (0, 0), 7.0)
        hdr = np.clip(hdr + (hdr - blur) * detail, 0.0, 1.5)
    hdr = np.power(np.clip(hdr, 0.0, 1.0), 1.0 / max(0.2, gamma))
    # Vibrance
    if abs(vibrance) > 0.01:
        avg = hdr.mean(axis=-1, keepdims=True)
        hdr = np.clip(avg + (hdr - avg) * (1.0 + vibrance), 0.0, 1.0)
    rgb = np.clip(hdr[..., ::-1] * 255.0, 0, 255).astype(np.uint8)
    return np.dstack([rgb, np.full((h, w), 255, dtype=np.uint8)])


def focus_stack_images(images: List[np.ndarray]) -> np.ndarray:
    """Focus Stacking: select sharpest pixels across focus slices via Laplacian energy maps."""
    if not images:
        raise ValueError("No images")
    if len(images) == 1:
        return images[0].copy()
    aligned = auto_align_layers(images)
    h, w = aligned[0].shape[:2]
    scores = []
    for im in aligned:
        g = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2GRAY)
        g_blur = cv2.GaussianBlur(g, (3, 3), 0.8)
        lap = np.abs(cv2.Laplacian(g_blur, cv2.CV_32F, ksize=5))
        scores.append(cv2.GaussianBlur(lap, (9, 9), 2.5))
    stack_scores = np.stack(scores, axis=0)
    best = np.argmax(stack_scores, axis=0)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for idx, im in enumerate(aligned):
        mask = best == idx
        out[mask] = im[mask]
    return out


# ---------------------------------------------------------------------------
# Patterns & Texture Synthesis
# ---------------------------------------------------------------------------
def make_seamless_pattern(rgba: np.ndarray, blend_width: int = 36, mode: str = "Offset Blend") -> np.ndarray:
    """Pattern Maker: convert any image into a seamless tileable texture (Offset Blend / Mirror / Brick)."""
    h, w = rgba.shape[:2]
    if mode == "Mirror Tile":
        half_w, half_h = max(4, w // 2), max(4, h // 2)
        q = cv2.resize(rgba, (half_w, half_h), interpolation=cv2.INTER_AREA)
        top = np.concatenate([q, q[:, ::-1]], axis=1)
        full = np.concatenate([top, top[::-1, :]], axis=0)
        return cv2.resize(full, (w, h), interpolation=cv2.INTER_LINEAR)

    # Offset by half width/height and heal the center cross seam!
    shifted = np.roll(np.roll(rgba, h // 2, axis=0), w // 2, axis=1)
    seam_mask = np.zeros((h, w), dtype=np.uint8)
    bw = max(6, min(blend_width, min(h, w) // 4))
    seam_mask[h // 2 - bw // 2 : h // 2 + bw // 2, :] = 255
    seam_mask[:, w // 2 - bw // 2 : w // 2 + bw // 2] = 255
    healed = spot_heal_stroke(shifted, seam_mask, radius=max(5, bw // 3), method="telea")
    if mode == "Brick":
        half = h // 2
        healed[half:, :] = np.roll(healed[half:, :], w // 2, axis=1)
    return healed


def synthesize_procedural_texture(width: int, height: int, kind: str = "Brushed Metal", seed: int = 42) -> np.ndarray:
    """Texture Synthesis: generate seamless tileable studio textures."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)

    if kind == "Brushed Metal":
        noise = rng.normal(158, 28, (height, max(8, width // 16))).astype(np.float32)
        streaks = cv2.resize(noise, (width, height), interpolation=cv2.INTER_LINEAR)
        streaks = cv2.GaussianBlur(streaks, (31, 3), 8.0)
        sheen = 18.0 * np.sin((xx / max(width, 1)) * math.pi * 2.0)
        v = np.clip(streaks + sheen, 0, 255).astype(np.uint8)
        rgb = np.stack([np.clip(v * 0.94, 0, 255), np.clip(v * 0.97, 0, 255), np.clip(v * 1.03, 0, 255)], axis=-1).astype(np.uint8)
    elif kind == "Marble Veins":
        base = np.zeros((height, width), dtype=np.float32)
        for g, a in [(8, 0.5), (16, 0.25), (32, 0.15), (64, 0.1)]:
            n = rng.random((g, g), dtype=np.float32)
            base += cv2.resize(n, (width, height), interpolation=cv2.INTER_CUBIC) * a
        vein = np.abs(np.sin((xx / max(width, 1) * 5.0 + yy / max(height, 1) * 3.0 + base * 8.5) * math.pi))
        vein = np.power(vein, 0.35)
        r = np.clip(195 + vein * 55, 0, 255)
        g_c = np.clip(198 + vein * 52, 0, 255)
        b = np.clip(206 + vein * 47, 0, 255)
        rgb = np.stack([r, g_c, b], axis=-1).astype(np.uint8)
    elif kind == "Wood Grain":
        turb = cv2.resize(rng.random((12, 12), dtype=np.float32), (width, height), interpolation=cv2.INTER_CUBIC)
        rings = np.sin((xx / max(width, 1) * 22.0 + turb * 5.0) * math.pi) * 0.5 + 0.5
        r = np.clip(110 + rings * 78, 0, 255)
        g_c = np.clip(68 + rings * 54, 0, 255)
        b = np.clip(38 + rings * 32, 0, 255)
        rgb = np.stack([r, g_c, b], axis=-1).astype(np.uint8)
    elif kind == "Canvas Fabric":
        h_wave = (np.sin(yy * 1.1) * 0.5 + 0.5) * 18.0
        v_wave = (np.sin(xx * 1.1) * 0.5 + 0.5) * 18.0
        grain = rng.normal(216, 7, (height, width)).astype(np.float32)
        val = np.clip(grain + (h_wave + v_wave) * 0.6 - 10, 0, 255)
        rgb = np.stack([val, val * 0.98, val * 0.93], axis=-1).astype(np.uint8)
    elif kind == "Carbon Fiber":
        px = (xx.astype(np.int32) // 6)
        py = (yy.astype(np.int32) // 6)
        weave = ((px + py) % 2 == 0).astype(np.float32)
        sub_x = (xx % 6) / 6.0
        sub_y = (yy % 6) / 6.0
        val = np.where(weave > 0.5, 28 + 46 * np.sin(sub_x * math.pi), 22 + 36 * np.sin(sub_y * math.pi))
        u = np.clip(val, 0, 255).astype(np.uint8)
        rgb = np.stack([u, u, np.clip(u.astype(np.int32) + 6, 0, 255).astype(np.uint8)], axis=-1)
    else:  # Paper Grain
        grain = rng.normal(238, 9, (height, width)).astype(np.float32)
        rgb = np.stack([np.clip(grain, 0, 255), np.clip(grain - 3, 0, 255), np.clip(grain - 10, 0, 255)], axis=-1).astype(np.uint8)

    return np.dstack([rgb, np.full((height, width), 255, dtype=np.uint8)])


# ---------------------------------------------------------------------------
# Neural Filters: Colorize, Style Transfer, Smart Portrait, Depth Blur, Super Zoom
# ---------------------------------------------------------------------------
def neural_filter_colorize(rgba: np.ndarray, warmth: float = 0.15, saturation: float = 0.65) -> np.ndarray:
    """Neural Colorize: intelligent tonal & regional colorization for grayscale / vintage photos."""
    h, w = rgba.shape[:2]
    gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]

    # Regional semantic priors: upper bright -> cool sky blue, mid -> warm skin/earth, lower -> rich foliage/ground
    sky_w = np.clip((0.45 - yy) * 2.5, 0.0, 1.0) * np.clip((gray - 0.35) * 2.2, 0.0, 1.0)
    earth_w = np.clip((yy - 0.50) * 2.2, 0.0, 1.0)
    mid_w = np.clip(1.0 - sky_w - earth_w, 0.0, 1.0)

    r = gray * (1.0 + mid_w * (0.22 + warmth * 0.4) - sky_w * 0.18 - earth_w * 0.06)
    g = gray * (1.0 + mid_w * 0.06 + sky_w * 0.04 + earth_w * 0.14)
    b = gray * (1.0 - mid_w * (0.14 + warmth * 0.25) + sky_w * 0.32 - earth_w * 0.12)
    col = np.clip(np.stack([r, g, b], axis=-1), 0.0, 1.0)

    # Blend saturation strength
    g3 = gray[..., None]
    out = np.clip(g3 + (col - g3) * (saturation * 1.45), 0.0, 1.0)
    return np.dstack([(out * 255.0).astype(np.uint8), rgba[..., 3]])


def neural_filter_style_transfer(rgba: np.ndarray, style: str = "Watercolor", strength: float = 0.85) -> np.ndarray:
    """Neural Style Transfer presets powered by edge-preserving OpenCV & artistic shaders."""
    bgr = rgba[..., :3][..., ::-1].copy()
    if style == "Watercolor":
        res = cv2.stylization(bgr, sigma_s=60, sigma_r=0.45)
    elif style == "Pencil Sketch":
        _, res = cv2.pencilSketch(bgr, sigma_s=60, sigma_r=0.07, shade_factor=0.05)
    elif style == "Ink Comic":
        smooth = cv2.bilateralFilter(bgr, 9, 75, 75)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.adaptiveThreshold(cv2.medianBlur(gray, 5), 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 7)
        res = cv2.bitwise_and(smooth, smooth, mask=edges)
    elif style == "Impressionist Oil":
        q = (cv2.pyrMeanShiftFiltering(bgr, 14, 32) // 16) * 16 + 8
        res = cv2.detailEnhance(q, sigma_s=12, sigma_r=0.2)
    elif style == "Cyberpunk Neon":
        edges = cv2.Canny(bgr, 60, 160)
        glow = cv2.GaussianBlur(edges, (7, 7), 2.0)
        res = bgr.astype(np.float32) * 0.72
        res[..., 0] = np.clip(res[..., 0] + glow * 1.4, 0, 255)
        res[..., 2] = np.clip(res[..., 2] + glow * 0.9, 0, 255)
        res = res.astype(np.uint8)
    else:  # Vintage Film
        res = bgr.astype(np.float32)
        res[..., 2] = np.clip(res[..., 2] * 1.08 + 10, 0, 255)
        res[..., 0] = np.clip(res[..., 0] * 0.86 + 14, 0, 255)
        res = res.astype(np.uint8)

    out_rgb = np.clip(rgba[..., :3].astype(np.float32) * (1.0 - strength) + res[..., ::-1].astype(np.float32) * strength, 0, 255).astype(np.uint8)
    return np.dstack([out_rgb, rgba[..., 3]])


def neural_filter_smart_portrait(
    rgba: np.ndarray,
    skin_smooth: float = 0.55,
    light_angle: float = 0.0,
    glow: float = 0.2,
    eye_pop: float = 0.35,
) -> np.ndarray:
    """Smart Portrait Neural Filter: frequency-separation skin smoothing, directional relight & detail pop."""
    rgb = rgba[..., :3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    skin = ((hsv[..., 0] <= 26) & (hsv[..., 1] >= 28) & (hsv[..., 1] <= 190) & (hsv[..., 2] >= 55)).astype(np.float32)
    skin = cv2.GaussianBlur(skin, (15, 15), 4.0)[..., None]

    # Frequency separation smoothing on skin
    smooth = cv2.bilateralFilter(rgb, 11, 55, 55).astype(np.float32)
    base = rgb.astype(np.float32)
    out = base * (1.0 - skin * skin_smooth) + smooth * (skin * skin_smooth)

    # Micro detail pop on non-skin / eyes
    if eye_pop > 0.01:
        hi = base - cv2.GaussianBlur(base, (0, 0), 2.0)
        out = np.clip(out + hi * (1.0 - skin * 0.6) * eye_pop * 1.2, 0, 255)

    # Soft directional studio relighting
    if abs(light_angle) > 1.0:
        h, w = rgb.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        rad = math.radians(light_angle)
        nx = (xx - w * 0.5) / max(w * 0.5, 1)
        ny = (yy - h * 0.5) / max(h * 0.5, 1)
        shade = 1.0 + (nx * math.cos(rad) + ny * math.sin(rad)) * 0.22
        out = np.clip(out * shade[..., None], 0, 255)

    # Dreamy studio glow
    if glow > 0.01:
        bloom = cv2.GaussianBlur(out, (0, 0), 12.0)
        out = np.clip(out * (1.0 - glow * 0.35) + bloom * (glow * 0.35), 0, 255)

    return np.dstack([out.astype(np.uint8), rgba[..., 3]])


def neural_filter_depth_blur(rgba: np.ndarray, focal_y: float = 0.5, blur_strength: float = 12.0, haze: float = 0.08) -> np.ndarray:
    """Depth Blur Neural Filter: synthetic depth-of-field bokeh with adjustable focal plane & atmospheric haze."""
    h, w = rgba.shape[:2]
    yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    depth = np.clip(np.abs(yy - focal_y) * 2.2, 0.0, 1.0)
    k = max(3, int(blur_strength * 2) | 1)
    far = cv2.GaussianBlur(rgba[..., :3], (k, k), blur_strength * 0.6).astype(np.float32)
    near = rgba[..., :3].astype(np.float32)
    m = depth[..., None]
    comp = near * (1.0 - m) + far * m
    if haze > 0.005:
        comp = comp * (1.0 - m * haze) + 235.0 * (m * haze)
    return np.dstack([np.clip(comp, 0, 255).astype(np.uint8), rgba[..., 3]])


def neural_filter_super_zoom(rgba: np.ndarray, scale: int = 2) -> np.ndarray:
    """Super Zoom AI-style upscaler: Lanczos + edge-preserving detail restoration."""
    h, w = rgba.shape[:2]
    up = cv2.resize(rgba, (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(up[..., :3], (0, 0), 1.2)
    sharp = np.clip(up[..., :3].astype(np.float32) * 1.45 - blur.astype(np.float32) * 0.45, 0, 255).astype(np.uint8)
    sharp = cv2.bilateralFilter(sharp, 5, 22, 22)
    return np.dstack([sharp, up[..., 3]])


# ---------------------------------------------------------------------------
# Light 3D & Texturing Studio Renderer
# ---------------------------------------------------------------------------
def render_3d_object(
    width: int,
    height: int,
    shape: str = "Sphere",  # Sphere | Cube | Cylinder | Torus | Extruded Plate
    texture_rgba: Optional[np.ndarray] = None,
    rot_x: float = 20.0,
    rot_y: float = -30.0,
    light_x: float = 0.6,
    light_y: float = -0.6,
    metallic: float = 0.35,
    base_color: Tuple[int, int, int] = (49, 168, 255),
) -> np.ndarray:
    """Fast analytical ray-cast / rasterized 3D primitive renderer with texture mapping & Phong shading."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    cx, cy = width * 0.5, height * 0.5
    rad = min(width, height) * 0.36
    nx = (xx - cx) / max(rad, 1.0)
    ny = (yy - cy) / max(rad, 1.0)

    out = np.zeros((height, width, 4), dtype=np.float32)
    lvec = np.array([light_x, light_y, 0.85], dtype=np.float32)
    lvec /= max(np.linalg.norm(lvec), 1e-6)
    col_base = np.array(base_color, dtype=np.float32) / 255.0

    ry_r = math.radians(rot_y)
    rx_r = math.radians(rot_x)

    if shape == "Sphere":
        r2 = nx * nx + ny * ny
        hit = r2 <= 1.0
        nz = np.sqrt(np.maximum(0.0, 1.0 - r2))
        u = ((np.arctan2(nx, nz) + ry_r) / (2.0 * math.pi)) % 1.0
        v = (np.arcsin(np.clip(ny, -1.0, 1.0)) / math.pi + 0.5 + rx_r / math.pi) % 1.0
        norm_x, norm_y, norm_z = nx, ny, nz
    elif shape == "Cylinder":
        hit = (np.abs(nx) <= 0.72) & (np.abs(ny) <= 0.92)
        ux = np.clip(nx / 0.72, -1.0, 1.0)
        nz = np.sqrt(np.maximum(0.0, 1.0 - ux * ux))
        u = ((np.arctan2(ux, nz) + ry_r) / (2.0 * math.pi)) % 1.0
        v = (ny / 1.84 + 0.5) % 1.0
        norm_x, norm_y, norm_z = ux, np.zeros_like(ux), nz
    elif shape == "Torus":
        R, r_t = 0.66, 0.28
        rho = np.sqrt(nx * nx + ny * ny)
        d = rho - R
        hit = np.abs(d) <= r_t
        nz = np.sqrt(np.maximum(0.0, r_t * r_t - d * d)) / r_t
        dn = np.clip(d / r_t, -1.0, 1.0)
        ang = np.arctan2(ny, nx)
        norm_x = dn * np.cos(ang)
        norm_y = dn * np.sin(ang)
        norm_z = nz
        u = ((ang + ry_r) / (2.0 * math.pi)) % 1.0
        v = (np.arctan2(dn, nz) / (2.0 * math.pi) + 0.5) % 1.0
    else:  # Cube / Extruded Plate (projected isometric 3-face box)
        img = np.zeros((height, width, 4), dtype=np.uint8)
        verts = np.array([
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1],
        ], dtype=np.float32)
        if shape == "Extruded Plate":
            verts[:, 2] *= 0.25
        cy_c, sy_c = math.cos(ry_r), math.sin(ry_r)
        cx_c, sx_c = math.cos(rx_r), math.sin(rx_r)
        Ry = np.array([[cy_c, 0, sy_c], [0, 1, 0], [-sy_c, 0, cy_c]], np.float32)
        Rx = np.array([[1, 0, 0], [0, cx_c, -sx_c], [0, sx_c, cx_c]], np.float32)
        rv = (verts @ Ry.T) @ Rx.T
        proj = np.zeros((8, 2), dtype=np.float32)
        for i in range(8):
            persp = 3.2 / (3.8 - rv[i, 2])
            proj[i, 0] = cx + rv[i, 0] * rad * 0.65 * persp
            proj[i, 1] = cy + rv[i, 1] * rad * 0.65 * persp
        faces = [
            ([4, 5, 6, 7], 1.0),
            ([0, 1, 2, 3], 0.55),
            ([0, 4, 7, 3], 0.72),
            ([1, 5, 6, 2], 0.84),
            ([0, 1, 5, 4], 0.94),
            ([3, 2, 6, 7], 0.62),
        ]
        # Painter's algorithm sort by average Z
        faces.sort(key=lambda f: float(np.mean([rv[idx, 2] for idx in f[0]])))
        for idxs, shade in faces:
            poly = proj[idxs].astype(np.float32)
            if texture_rgba is not None and idxs == [4, 5, 6, 7]:
                th, tw = texture_rgba.shape[:2]
                src_q = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])
                M = cv2.getPerspectiveTransform(src_q, poly)
                warped = cv2.warpPerspective(texture_rgba, M, (width, height))
                m = warped[..., 3] > 10
                img[m] = warped[m]
            else:
                c = tuple(int(np.clip(base_color[k] * shade, 0, 255)) for k in range(3)) + (255,)
                cv2.fillConvexPoly(img, poly.astype(np.int32), c, cv2.LINE_AA)
                cv2.polylines(img, [poly.astype(np.int32)], True, (220, 235, 255, 255), 1, cv2.LINE_AA)
        return img

    # Texture sampling for Sphere / Cylinder / Torus
    if texture_rgba is not None:
        th, tw = texture_rgba.shape[:2]
        tx = np.clip((u * (tw - 1)).astype(np.int32), 0, tw - 1)
        ty = np.clip((v * (th - 1)).astype(np.int32), 0, th - 1)
        albedo = texture_rgba[ty, tx, :3].astype(np.float32) / 255.0
    else:
        albedo = np.broadcast_to(col_base, (height, width, 3)).copy()

    ndotl = np.clip(norm_x * lvec[0] + norm_y * lvec[1] + norm_z * lvec[2], 0.0, 1.0)
    # Specular highlight
    hx, hy, hz = lvec[0], lvec[1], lvec[2] + 1.0
    hlen = math.sqrt(hx * hx + hy * hy + hz * hz)
    ndoth = np.clip((norm_x * hx + norm_y * hy + norm_z * hz) / max(hlen, 1e-6), 0.0, 1.0)
    spec = np.power(ndoth, 24.0 + metallic * 64.0) * (0.35 + metallic * 0.75)

    shaded = albedo * (0.20 + 0.85 * ndotl[..., None]) + spec[..., None]
    out[..., :3] = np.where(hit[..., None], np.clip(shaded, 0.0, 1.0), 0.0)
    out[..., 3] = np.where(hit, 1.0, 0.0)
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Scanning & Documents: WIA Scanner, Auto-Straighten, Split Multiple Scanned Photos
# ---------------------------------------------------------------------------
def scan_from_wia_windows() -> Optional[np.ndarray]:
    """Attempt to acquire an image from a Windows WIA 2.0 scanner via COM."""
    try:
        import comtypes.client  # type: ignore

        dlg = comtypes.client.CreateObject("WIA.CommonDialog")
        img = dlg.ShowAcquireImage()
        if img is None:
            return None
        tmp = os.path.join(os.environ.get("TEMP", "."), "kinoshop_wia_scan.png")
        if os.path.exists(tmp):
            os.remove(tmp)
        img.SaveFile(tmp)
        pil = Image.open(tmp).convert("RGBA")
        return np.array(pil)
    except Exception:
        return None


def auto_straighten_scan(rgba: np.ndarray) -> Tuple[np.ndarray, float]:
    """Automatically detect dominant skew angle of a scanned document/photo and deskew it."""
    gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, math.pi / 180.0, threshold=80, minLineLength=min(rgba.shape[:2]) // 6, maxLineGap=20)
    angles: List[float] = []
    if lines is not None:
        for line in lines[:200]:
            x1, y1, x2, y2 = line[0]
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            # Normalize near horizontal (-45..45)
            while ang < -45.0:
                ang += 90.0
            while ang > 45.0:
                ang -= 90.0
            if abs(ang) < 25.0:
                angles.append(ang)
    skew = float(np.median(angles)) if angles else 0.0
    if abs(skew) < 0.15:
        return rgba.copy(), 0.0
    h, w = rgba.shape[:2]
    M = cv2.getRotationMatrix2D((w * 0.5, h * 0.5), skew, 1.0)
    deskewed = cv2.warpAffine(rgba, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return deskewed, skew


def split_scanned_photos(rgba: np.ndarray, min_area_ratio: float = 0.025) -> List[np.ndarray]:
    """Crop and Straighten Photos: detect multiple photos on a flatbed scan and split each straight & cropped."""
    h, w = rgba.shape[:2]
    rgb = rgba[..., :3]
    # Estimate flatbed background from corners
    corners = np.concatenate([
        rgb[:12, :12].reshape(-1, 3),
        rgb[:12, -12:].reshape(-1, 3),
        rgb[-12:, :12].reshape(-1, 3),
        rgb[-12:, -12:].reshape(-1, 3),
    ], axis=0)
    bg_med = np.median(corners, axis=0).astype(np.float32)
    diff = np.linalg.norm(rgb.astype(np.float32) - bg_med, axis=-1)
    mask = (diff > 24.0).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = h * w * min_area_ratio
    results: List[np.ndarray] = []

    for cnt in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(cnt) < min_area:
            continue
        rect = cv2.minAreaRect(cnt)
        (cx, cy), (rw, rh), angle = rect
        if rw < 24 or rh < 24:
            continue
        box = cv2.boxPoints(rect).astype(np.float32)
        # Order box points TL, TR, BR, BL
        s = box.sum(axis=1)
        d = np.diff(box, axis=1).ravel()
        ordered = np.array([box[np.argmin(s)], box[np.argmin(d)], box[np.argmax(s)], box[np.argmax(d)]], dtype=np.float32)
        out_w = int(round(max(np.linalg.norm(ordered[1] - ordered[0]), np.linalg.norm(ordered[2] - ordered[3]))))
        out_h = int(round(max(np.linalg.norm(ordered[3] - ordered[0]), np.linalg.norm(ordered[2] - ordered[1]))))
        if out_w < 20 or out_h < 20:
            continue
        dst = np.float32([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]])
        M = cv2.getPerspectiveTransform(ordered, dst)
        cropped = cv2.warpPerspective(rgba, M, (out_w, out_h), flags=cv2.INTER_CUBIC)
        results.append(cropped)
    return results


# ---------------------------------------------------------------------------
# Contact Sheet II & Picture Package
# ---------------------------------------------------------------------------
def build_contact_sheet(
    images: List[Tuple[str, np.ndarray]],
    page_w: int = 1600,
    page_h: int = 2000,
    cols: int = 4,
    rows: int = 5,
    margin: int = 48,
    gutter: int = 24,
    show_captions: bool = True,
    bg_color: Tuple[int, int, int] = (245, 247, 250),
) -> np.ndarray:
    """Create a gridded Contact Sheet page with optional filename captions."""
    canvas = Image.new("RGBA", (page_w, page_h), bg_color + (255,))
    draw = ImageDraw.Draw(canvas)
    cap_h = 24 if show_captions else 0
    cell_w = max(20, (page_w - 2 * margin - gutter * (cols - 1)) // max(1, cols))
    cell_h = max(20, (page_h - 2 * margin - gutter * (rows - 1)) // max(1, rows))
    img_h = max(16, cell_h - cap_h)

    for idx, (label, arr) in enumerate(images[: cols * rows]):
        r, c = divmod(idx, cols)
        x0 = margin + c * (cell_w + gutter)
        y0 = margin + r * (cell_h + gutter)
        pil = Image.fromarray(arr).convert("RGBA")
        pil.thumbnail((cell_w, img_h), Image.Resampling.LANCZOS)
        px = x0 + (cell_w - pil.width) // 2
        py = y0 + (img_h - pil.height) // 2
        canvas.alpha_composite(pil, (px, py))
        draw.rectangle([px, py, px + pil.width, py + pil.height], outline=(180, 188, 200, 255), width=1)
        if show_captions:
            draw.text((x0 + 2, y0 + img_h + 4), os.path.basename(label)[:28], fill=(35, 42, 56, 255))
    return np.array(canvas)


def build_picture_package(
    photo_rgba: np.ndarray,
    layout: str = "1x(5x7) + 2x(3.5x5) + 4x(Wallet)",
    page_w: int = 1600,
    page_h: int = 2000,
) -> np.ndarray:
    """Arrange one photo into classic multi-size print Picture Package slots."""
    canvas = Image.new("RGBA", (page_w, page_h), (255, 255, 255, 255))
    pil = Image.fromarray(photo_rgba).convert("RGBA")

    if layout == "2x(5x7)":
        slots = [(0.05, 0.04, 0.90, 0.44), (0.05, 0.52, 0.90, 0.44)]
    elif layout == "4x(4x5)":
        slots = [
            (0.05, 0.05, 0.43, 0.43), (0.52, 0.05, 0.43, 0.43),
            (0.05, 0.52, 0.43, 0.43), (0.52, 0.52, 0.43, 0.43),
        ]
    elif layout == "9x(Wallet)":
        slots = [
            (0.04 + c * 0.315, 0.04 + r * 0.315, 0.29, 0.29)
            for r in range(3) for c in range(3)
        ]
    else:  # 1x(5x7) + 2x(3.5x5) + 4x(Wallet)
        slots = [
            (0.04, 0.04, 0.58, 0.54),
            (0.65, 0.04, 0.31, 0.255),
            (0.65, 0.325, 0.31, 0.255),
            (0.04, 0.62, 0.215, 0.34),
            (0.275, 0.62, 0.215, 0.34),
            (0.51, 0.62, 0.215, 0.34),
            (0.745, 0.62, 0.215, 0.34),
        ]

    draw = ImageDraw.Draw(canvas)
    for fx, fy, fw, fh in slots:
        x, y, sw, sh = int(fx * page_w), int(fy * page_h), int(fw * page_w), int(fh * page_h)
        # Cover-fit crop
        src_ar = pil.width / max(1, pil.height)
        dst_ar = sw / max(1, sh)
        if src_ar > dst_ar:
            nh = sh
            nw = int(round(sh * src_ar))
        else:
            nw = sw
            nh = int(round(sw / src_ar))
        res = pil.resize((max(1, nw), max(1, nh)), Image.Resampling.LANCZOS)
        cx, cy = (res.width - sw) // 2, (res.height - sh) // 2
        crop = res.crop((cx, cy, cx + sw, cy + sh))
        canvas.alpha_composite(crop, (x, y))
        draw.rectangle([x, y, x + sw, y + sh], outline=(210, 215, 224, 255), width=2)
    return np.array(canvas)


# ---------------------------------------------------------------------------
# Scientific Measurement & Auto-Count
# ---------------------------------------------------------------------------
def auto_count_objects(rgba: np.ndarray, threshold: int = 128, invert: bool = False, min_area: int = 35) -> List[Tuple[float, float, float]]:
    """Detect and count distinct objects/cells in scientific images. Returns [(cx, cy, area_px), ...]."""
    gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 1.0)
    mode = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    _, bw = cv2.threshold(blur, threshold, 255, mode)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(bw, connectivity=8)
    out: List[Tuple[float, float, float]] = []
    for i in range(1, num):
        area = float(stats[i, cv2.CC_STAT_AREA])
        if area >= min_area:
            out.append((float(centroids[i][0]), float(centroids[i][1]), area))
    return out
