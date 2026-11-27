"""KinoWave 32-bit Float DSP, Effects, Generators & Analysis Engine (Pure NumPy).

Supports sample rates up to 384 kHz, non-destructive real-time & destructive
effects, 2-step spectral noise reduction, 31-band Graphic EQ, Filter Curve EQ,
LUFS/RMS loudness normalization, phase-vocoder pitch/tempo/Paulstretch,
physical-modeling generators, STFT spectrogram, WCAG loudness contrast, beat &
silence/sound finding, and preset persistence.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Helpers: Windows, Resampling, Dithering, Zero Crossings, Biquads
# ---------------------------------------------------------------------------
def make_window(name: str, n: int) -> np.ndarray:
    if n <= 1:
        return np.ones(max(1, n), dtype=np.float32)
    k = np.arange(n, dtype=np.float64)
    if name == "Hamming":
        w = 0.54 - 0.46 * np.cos(2.0 * np.pi * k / (n - 1))
    elif name == "Blackman":
        w = 0.42 - 0.5 * np.cos(2.0 * np.pi * k / (n - 1)) + 0.08 * np.cos(4.0 * np.pi * k / (n - 1))
    elif name == "Blackman-Harris":
        a0, a1, a2, a3 = 0.35875, 0.48829, 0.14128, 0.01168
        w = a0 - a1 * np.cos(2 * np.pi * k / (n - 1)) + a2 * np.cos(4 * np.pi * k / (n - 1)) - a3 * np.cos(6 * np.pi * k / (n - 1))
    elif name == "Bartlett":
        w = 1.0 - np.abs((k - (n - 1) / 2.0) / ((n - 1) / 2.0))
    elif name == "Rectangular":
        w = np.ones(n, dtype=np.float64)
    else:  # Hann
        w = 0.5 * (1.0 - np.cos(2.0 * np.pi * k / (n - 1)))
    return w.astype(np.float32)


def ensure_2d(audio: np.ndarray) -> np.ndarray:
    a = np.asarray(audio, dtype=np.float32)
    return a[None, :] if a.ndim == 1 else a


def db_to_lin(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def lin_to_db(val: float, floor_db: float = -120.0) -> float:
    if val <= 1e-12:
        return floor_db
    return max(floor_db, float(20.0 * math.log10(val)))


def find_zero_crossing(audio: np.ndarray, sample_idx: int, search_radius: int = 512) -> int:
    """Find nearest upward zero-crossing near sample_idx to avoid edit clicks."""
    a = ensure_2d(audio)
    mono = np.mean(a, axis=0)
    n = len(mono)
    if n < 2:
        return 0
    idx = max(0, min(n - 1, sample_idx))
    lo = max(1, idx - search_radius)
    hi = min(n - 1, idx + search_radius)
    seg = mono[lo - 1 : hi + 1]
    # Upward zero crossings
    crossings = np.where((seg[:-1] <= 0.0) & (seg[1:] > 0.0))[0] + lo
    if len(crossings) == 0:
        crossings = np.where(np.sign(seg[:-1]) != np.sign(seg[1:]))[0] + lo
    if len(crossings) == 0:
        return idx
    best = int(crossings[np.argmin(np.abs(crossings - idx))])
    return best


def resample_audio(audio: np.ndarray, src_sr: int, dst_sr: int, quality: str = "High") -> np.ndarray:
    """High-quality FFT / Sinc-windowed resampling supporting up to 384 kHz."""
    a = ensure_2d(audio)
    if src_sr == dst_sr or a.shape[1] == 0:
        return a.astype(np.float32, copy=True)
    n_in = a.shape[1]
    n_out = max(1, int(round(n_in * (dst_sr / float(src_sr)))))
    if quality == "Fast" or n_in < 16:
        x_old = np.arange(n_in, dtype=np.float64)
        x_new = np.linspace(0.0, n_in - 1, n_out, dtype=np.float64)
        out = np.empty((a.shape[0], n_out), dtype=np.float32)
        for ch in range(a.shape[0]):
            out[ch] = np.interp(x_new, x_old, a[ch]).astype(np.float32)
        return out

    # Band-limited FFT resampling (zero phase, anti-aliased)
    out = np.empty((a.shape[0], n_out), dtype=np.float32)
    scale = n_out / float(n_in)
    for ch in range(a.shape[0]):
        spec = np.fft.rfft(a[ch].astype(np.float64))
        new_bins = n_out // 2 + 1
        new_spec = np.zeros(new_bins, dtype=np.complex128)
        m = min(len(spec), new_bins)
        new_spec[:m] = spec[:m]
        out[ch] = (np.fft.irfft(new_spec, n=n_out) * scale).astype(np.float32)
    return out


def apply_dither(audio: np.ndarray, target_bits: int = 16, mode: str = "Triangle") -> np.ndarray:
    """Apply TPDF (Triangle), Rectangle, or Shaped dither when quantizing from 32-bit float."""
    a = ensure_2d(audio).astype(np.float32, copy=True)
    if mode == "None" or target_bits >= 32:
        return a
    lsb = 1.0 / (2.0 ** (target_bits - 1))
    rng = np.random.default_rng()
    if mode == "Rectangle":
        noise = rng.uniform(-0.5, 0.5, size=a.shape) * lsb
    elif mode == "Shaped":
        raw = (rng.uniform(-0.5, 0.5, size=a.shape) + rng.uniform(-0.5, 0.5, size=a.shape)) * lsb
        # High-pass noise shaping (1st-order diff)
        noise = raw.copy()
        noise[:, 1:] = raw[:, 1:] - 0.5 * raw[:, :-1]
    else:  # Triangle (TPDF)
        noise = (rng.uniform(-0.5, 0.5, size=a.shape) + rng.uniform(-0.5, 0.5, size=a.shape)) * lsb
    return np.clip(a + noise.astype(np.float32), -1.0, 1.0)


def _fft_filter(audio: np.ndarray, sr: int, mag_fn: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """Zero-phase FFT frequency-domain filter (fast, exact, handles arbitrary curves & slopes)."""
    a = ensure_2d(audio)
    n = a.shape[1]
    if n == 0:
        return a.copy()
    nfft = 1 << (n - 1).bit_length()
    if nfft < 256:
        nfft = 256
    freqs = np.fft.rfftfreq(nfft, d=1.0 / max(1, sr))
    resp = np.asarray(mag_fn(freqs), dtype=np.float64)
    out = np.empty_like(a, dtype=np.float32)
    for ch in range(a.shape[0]):
        spec = np.fft.rfft(a[ch].astype(np.float64), n=nfft)
        out[ch] = np.fft.irfft(spec * resp, n=nfft)[:n].astype(np.float32)
    return out


def _stft(x: np.ndarray, n_fft: int = 1024, hop: int = 256, window: str = "Hann") -> np.ndarray:
    win = make_window(window, n_fft)
    pad = n_fft // 2
    xp = np.pad(x.astype(np.float32), (pad, pad), mode="reflect" if len(x) > pad else "constant")
    n_frames = 1 + max(0, (len(xp) - n_fft) // hop)
    if n_frames <= 0:
        return np.zeros((n_fft // 2 + 1, 1), dtype=np.complex64)
    strides = (xp.strides[0] * hop, xp.strides[0])
    frames = np.lib.stride_tricks.as_strided(xp, shape=(n_frames, n_fft), strides=strides)
    spec = np.fft.rfft(frames * win[None, :], axis=1)
    return spec.T.astype(np.complex64)


def _istft(spec: np.ndarray, n_fft: int = 1024, hop: int = 256, window: str = "Hann", length: Optional[int] = None) -> np.ndarray:
    win = make_window(window, n_fft).astype(np.float64)
    n_frames = spec.shape[1]
    out_len = n_fft + hop * (n_frames - 1)
    y = np.zeros(out_len, dtype=np.float64)
    wsum = np.zeros(out_len, dtype=np.float64)
    frames = np.fft.irfft(spec.T, n=n_fft, axis=1)
    win2 = win * win
    for i in range(n_frames):
        pos = i * hop
        y[pos : pos + n_fft] += frames[i] * win
        wsum[pos : pos + n_fft] += win2
    y /= np.maximum(wsum, 1e-8)
    pad = n_fft // 2
    y = y[pad : len(y) - pad]
    if length is not None:
        if len(y) < length:
            y = np.pad(y, (0, length - len(y)))
        else:
            y = y[:length]
    return y.astype(np.float32)


# ---------------------------------------------------------------------------
# 1. VOLUME & DYNAMICS EFFECTS
# ---------------------------------------------------------------------------
def fx_amplify(audio: np.ndarray, sr: int, gain_db: float = 0.0, allow_clipping: bool = False) -> np.ndarray:
    a = ensure_2d(audio) * db_to_lin(gain_db)
    return a.astype(np.float32) if allow_clipping else np.clip(a, -1.0, 1.0).astype(np.float32)


def fx_normalize(audio: np.ndarray, sr: int, target_db: float = -1.0, remove_dc: bool = True, stereo_independent: bool = False) -> np.ndarray:
    a = ensure_2d(audio).astype(np.float32, copy=True)
    if a.shape[1] == 0:
        return a
    if remove_dc:
        a -= np.mean(a, axis=1, keepdims=True)
    target = db_to_lin(target_db)
    if stereo_independent:
        for ch in range(a.shape[0]):
            pk = float(np.max(np.abs(a[ch])))
            if pk > 1e-9:
                a[ch] *= target / pk
    else:
        pk = float(np.max(np.abs(a)))
        if pk > 1e-9:
            a *= target / pk
    return a


def measure_lufs(audio: np.ndarray, sr: int) -> float:
    """ITU-R BS.1770 K-weighted integrated loudness approximation in LUFS."""
    a = ensure_2d(audio)
    if a.shape[1] == 0:
        return -70.0
    # K-weighting frequency response: +4 dB high-shelf above 1500 Hz + 60 Hz high-pass
    def k_weight(f: np.ndarray) -> np.ndarray:
        hp = (f ** 2) / (f ** 2 + 60.0 ** 2 + 1e-12)
        hs = 1.0 + 0.585 * ((f ** 2) / (f ** 2 + 1500.0 ** 2 + 1e-12))
        return hp * hs

    kw = _fft_filter(a, sr, k_weight)
    mean_sq = float(np.sum(np.mean(kw.astype(np.float64) ** 2, axis=1)))
    if mean_sq <= 1e-12:
        return -70.0
    return float(-0.691 + 10.0 * math.log10(mean_sq))


def fx_loudness_normalize(audio: np.ndarray, sr: int, mode: str = "LUFS", target_db: float = -14.0) -> np.ndarray:
    a = ensure_2d(audio).astype(np.float32, copy=True)
    if a.shape[1] == 0:
        return a
    if mode == "RMS":
        rms = float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))
        cur = lin_to_db(rms)
    else:
        cur = measure_lufs(a, sr)
    if cur <= -69.5:
        return a
    gain = db_to_lin(target_db - cur)
    return (a * gain).astype(np.float32)


def _envelope_follower(x_abs: np.ndarray, sr: int, attack_ms: float, release_ms: float) -> np.ndarray:
    """Fast block-vectorized attack/release envelope follower."""
    n = len(x_abs)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    block = max(1, min(64, int(sr * 0.001)))
    nb = (n + block - 1) // block
    padded = np.pad(x_abs, (0, nb * block - n))
    peaks = np.max(padded.reshape(nb, block), axis=1).astype(np.float64)
    dt = block / float(max(1, sr))
    a_att = math.exp(-dt / max(1e-4, attack_ms * 0.001))
    a_rel = math.exp(-dt / max(1e-4, release_ms * 0.001))
    env = np.empty(nb, dtype=np.float64)
    cur = 0.0
    for i in range(nb):
        v = peaks[i]
        cur = a_att * cur + (1.0 - a_att) * v if v > cur else a_rel * cur + (1.0 - a_rel) * v
        env[i] = cur
    return np.repeat(env, block)[:n].astype(np.float32)


def fx_compressor(
    audio: np.ndarray,
    sr: int,
    threshold_db: float = -18.0,
    noise_floor_db: float = -50.0,
    ratio: float = 4.0,
    attack_ms: float = 20.0,
    release_ms: float = 250.0,
    makeup_gain: bool = True,
) -> np.ndarray:
    a = ensure_2d(audio)
    if a.shape[1] == 0:
        return a.copy()
    det = np.max(np.abs(a), axis=0)
    env = _envelope_follower(det, sr, attack_ms, release_ms)
    env_db = 20.0 * np.log10(np.maximum(env, 1e-7))
    over = np.maximum(0.0, env_db - threshold_db)
    above_floor = env_db > noise_floor_db
    gain_red_db = np.where(above_floor, -over * (1.0 - 1.0 / max(1.0, ratio)), 0.0)
    out = a * (10.0 ** (gain_red_db / 20.0))[None, :]
    if makeup_gain:
        pk = float(np.max(np.abs(out)))
        if pk > 1e-6:
            out *= db_to_lin(-1.0) / pk
    return out.astype(np.float32)


def fx_limiter(
    audio: np.ndarray,
    sr: int,
    limit_type: str = "Soft Limit",
    input_gain_left_db: float = 0.0,
    input_gain_right_db: float = 0.0,
    limit_db: float = -3.0,
    hold_ms: float = 10.0,
    makeup: bool = False,
) -> np.ndarray:
    a = ensure_2d(audio).astype(np.float32, copy=True)
    a[0] *= db_to_lin(input_gain_left_db)
    if a.shape[0] > 1:
        a[1] *= db_to_lin(input_gain_right_db)
    lim = db_to_lin(limit_db)
    if limit_type == "Hard Clip":
        out = np.clip(a, -lim, lim)
    elif limit_type == "Soft Clip":
        out = lim * np.tanh(a / max(lim, 1e-6))
    elif limit_type == "Hard Limit":
        env = _envelope_follower(np.max(np.abs(a), axis=0), sr, 1.0, max(5.0, hold_ms))
        gain = np.where(env > lim, lim / np.maximum(env, 1e-9), 1.0)
        out = np.clip(a * gain[None, :], -lim, lim)
    else:  # Soft Limit
        env = _envelope_follower(np.max(np.abs(a), axis=0), sr, 2.0, max(8.0, hold_ms))
        gain = np.where(env > lim, (lim / np.maximum(env, 1e-9)) ** 0.92, 1.0)
        out = lim * np.tanh((a * gain[None, :]) / max(lim, 1e-6))
    if makeup:
        out *= 1.0 / max(lim, 1e-6) * db_to_lin(-0.3)
    return out.astype(np.float32)


def fx_noise_gate(
    audio: np.ndarray,
    sr: int,
    mode: str = "Gate",
    stereo_link: bool = True,
    gate_freq_khz: float = 0.0,
    threshold_db: float = -48.0,
    level_reduction_db: float = -12.0,
    attack_ms: float = 10.0,
    hold_ms: float = 50.0,
    decay_ms: float = 250.0,
) -> np.ndarray:
    a = ensure_2d(audio)
    if a.shape[1] == 0 or mode == "Analyze Noise Level":
        return a.copy()
    det_sig = fx_high_pass(a, sr, cutoff_hz=gate_freq_khz * 1000.0, rolloff_db=12) if gate_freq_khz > 0.02 else a
    min_gain = db_to_lin(level_reduction_db)
    if stereo_link or a.shape[0] == 1:
        env = _envelope_follower(np.max(np.abs(det_sig), axis=0), sr, attack_ms, hold_ms + decay_ms)
        env_db = 20.0 * np.log10(np.maximum(env, 1e-7))
        gate = np.clip((env_db - (threshold_db - 6.0)) / 6.0, 0.0, 1.0)
        gain = min_gain + (1.0 - min_gain) * gate
        return (a * gain[None, :]).astype(np.float32)
    out = np.empty_like(a, dtype=np.float32)
    for ch in range(a.shape[0]):
        env = _envelope_follower(np.abs(det_sig[ch]), sr, attack_ms, hold_ms + decay_ms)
        env_db = 20.0 * np.log10(np.maximum(env, 1e-7))
        gate = np.clip((env_db - (threshold_db - 6.0)) / 6.0, 0.0, 1.0)
        out[ch] = a[ch] * (min_gain + (1.0 - min_gain) * gate)
    return out


def fx_auto_duck(
    audio: np.ndarray,
    sr: int,
    duck_db: float = -12.0,
    threshold_db: float = -30.0,
    fade_down_s: float = 0.25,
    fade_up_s: float = 0.5,
    control_audio: Optional[np.ndarray] = None,
) -> np.ndarray:
    a = ensure_2d(audio)
    if a.shape[1] == 0:
        return a.copy()
    ctrl = ensure_2d(control_audio) if control_audio is not None else a
    n = a.shape[1]
    ctrl_mono = np.max(np.abs(ctrl), axis=0)
    if len(ctrl_mono) < n:
        ctrl_mono = np.pad(ctrl_mono, (0, n - len(ctrl_mono)))
    else:
        ctrl_mono = ctrl_mono[:n]
    env = _envelope_follower(ctrl_mono, sr, max(10.0, fade_down_s * 500.0), max(20.0, fade_up_s * 500.0))
    env_db = 20.0 * np.log10(np.maximum(env, 1e-7))
    duck_lin = db_to_lin(duck_db)
    amount = np.clip((env_db - threshold_db) / 6.0, 0.0, 1.0)
    gain = 1.0 - amount * (1.0 - duck_lin)
    return (a * gain[None, :]).astype(np.float32)


def fx_fade_in(audio: np.ndarray, sr: int) -> np.ndarray:
    a = ensure_2d(audio)
    ramp = np.linspace(0.0, 1.0, a.shape[1], dtype=np.float32)
    return (a * ramp[None, :]).astype(np.float32)


def fx_fade_out(audio: np.ndarray, sr: int) -> np.ndarray:
    a = ensure_2d(audio)
    ramp = np.linspace(1.0, 0.0, a.shape[1], dtype=np.float32)
    return (a * ramp[None, :]).astype(np.float32)


def fx_studio_fade_out(audio: np.ndarray, sr: int) -> np.ndarray:
    a = ensure_2d(audio)
    t = np.linspace(0.0, 1.0, a.shape[1], dtype=np.float32)
    # Raised cosine + exponential tail for musical studio fade
    curve = (0.5 * (1.0 + np.cos(np.pi * t))) ** 1.65
    return (a * curve[None, :]).astype(np.float32)


def fx_adjustable_fade(
    audio: np.ndarray,
    sr: int,
    fade_type: str = "Fade Down",
    start_gain_pct: float = 100.0,
    end_gain_pct: float = 0.0,
    mid_cut: float = 0.0,
) -> np.ndarray:
    a = ensure_2d(audio)
    t = np.linspace(0.0, 1.0, a.shape[1], dtype=np.float32)
    g0, g1 = start_gain_pct / 100.0, end_gain_pct / 100.0
    if "S-Curve" in fade_type:
        u = 0.5 * (1.0 - np.cos(np.pi * t))
    else:
        exp = 2.0 ** (-mid_cut / 50.0)
        u = np.power(t, exp)
    if "Up" in fade_type and g0 > g1:
        g0, g1 = g1, g0
    curve = g0 + (g1 - g0) * u
    return (a * curve[None, :]).astype(np.float32)


def fx_crossfade_clips(audio: np.ndarray, sr: int) -> np.ndarray:
    """Crossfade first half into second half smoothly."""
    a = ensure_2d(audio)
    n = a.shape[1]
    if n < 8:
        return a.copy()
    half = n // 2
    t = np.linspace(0.0, 1.0, half, dtype=np.float32)
    fade_out = np.cos(t * np.pi * 0.5)
    fade_in = np.sin(t * np.pi * 0.5)
    out = a[:, :half] * fade_out[None, :] + a[:, half : half * 2] * fade_in[None, :]
    return out.astype(np.float32)


def fx_crossfade_tracks(audio: np.ndarray, sr: int, curve: str = "Constant Power", direction: str = "Fade Out") -> np.ndarray:
    a = ensure_2d(audio)
    t = np.linspace(0.0, 1.0, a.shape[1], dtype=np.float32)
    if direction == "Fade Out":
        g = np.cos(t * np.pi * 0.5) if curve == "Constant Power" else (1.0 - t)
    else:
        g = np.sin(t * np.pi * 0.5) if curve == "Constant Power" else t
    return (a * g[None, :]).astype(np.float32)


# ---------------------------------------------------------------------------
# 2. EQ & FILTERS
# ---------------------------------------------------------------------------
ISO_31_BANDS = [
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630,
    800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000,
]


def fx_bass_treble(audio: np.ndarray, sr: int, bass_db: float = 0.0, treble_db: float = 0.0, volume_db: float = 0.0) -> np.ndarray:
    def resp(f: np.ndarray) -> np.ndarray:
        low_shelf = 1.0 / (1.0 + (f / 250.0) ** 4)
        high_shelf = 1.0 / (1.0 + (4000.0 / np.maximum(f, 1.0)) ** 4)
        db = bass_db * low_shelf + treble_db * high_shelf + volume_db
        return 10.0 ** (db / 20.0)
    return _fft_filter(audio, sr, resp)


def fx_graphic_eq(audio: np.ndarray, sr: int, band_gains_db: Optional[List[float]] = None) -> np.ndarray:
    gains = list(band_gains_db) if band_gains_db else [0.0] * len(ISO_31_BANDS)
    if len(gains) < len(ISO_31_BANDS):
        gains += [0.0] * (len(ISO_31_BANDS) - len(gains))
    log_bands = np.log10(np.array(ISO_31_BANDS, dtype=np.float64))
    g_arr = np.array(gains[: len(ISO_31_BANDS)], dtype=np.float64)

    def resp(f: np.ndarray) -> np.ndarray:
        lf = np.log10(np.maximum(f, 10.0))
        db = np.interp(lf, log_bands, g_arr)
        return 10.0 ** (db / 20.0)
    return _fft_filter(audio, sr, resp)


def fx_filter_curve_eq(audio: np.ndarray, sr: int, points: Optional[List[Tuple[float, float]]] = None) -> np.ndarray:
    pts = sorted(points or [(20.0, 0.0), (1000.0, 0.0), (20000.0, 0.0)], key=lambda p: p[0])
    xs = np.log10(np.maximum(np.array([p[0] for p in pts], dtype=np.float64), 1.0))
    ys = np.array([p[1] for p in pts], dtype=np.float64)

    def resp(f: np.ndarray) -> np.ndarray:
        lf = np.log10(np.maximum(f, 1.0))
        db = np.interp(lf, xs, ys)
        return 10.0 ** (db / 20.0)
    return _fft_filter(audio, sr, resp)


def fx_high_pass(audio: np.ndarray, sr: int, cutoff_hz: float = 100.0, rolloff_db: int = 12) -> np.ndarray:
    order = max(1, rolloff_db // 6)
    fc = max(1.0, cutoff_hz)
    return _fft_filter(audio, sr, lambda f: 1.0 / np.sqrt(1.0 + (fc / np.maximum(f, 1e-6)) ** (2 * order)))


def fx_low_pass(audio: np.ndarray, sr: int, cutoff_hz: float = 4000.0, rolloff_db: int = 12) -> np.ndarray:
    order = max(1, rolloff_db // 6)
    fc = max(1.0, cutoff_hz)
    return _fft_filter(audio, sr, lambda f: 1.0 / np.sqrt(1.0 + (f / fc) ** (2 * order)))


def fx_notch(audio: np.ndarray, sr: int, freq_hz: float = 60.0, q: float = 5.0) -> np.ndarray:
    f0 = max(1.0, freq_hz)
    bw = f0 / max(0.2, q)

    def resp(f: np.ndarray) -> np.ndarray:
        d = ((f - f0) / max(bw * 0.5, 1e-4)) ** 2
        return d / (1.0 + d)
    return _fft_filter(audio, sr, resp)


def fx_classic_filters(
    audio: np.ndarray,
    sr: int,
    filter_type: str = "Butterworth",
    subtype: str = "Lowpass",
    order: int = 4,
    cutoff_hz: float = 1000.0,
    passband_ripple_db: float = 1.0,
    stopband_atten_db: float = 40.0,
) -> np.ndarray:
    """Audacity Classic Filters: Butterworth, Chebyshev Type I, Chebyshev Type II (Lowpass / Highpass, Order 1-10)."""
    n_ord = max(1, min(10, int(order)))
    fc = max(10.0, cutoff_hz)

    def cheb_poly(n: int, x: np.ndarray) -> np.ndarray:
        out = np.empty_like(x, dtype=np.float64)
        inside = np.abs(x) <= 1.0
        out[inside] = np.cos(n * np.arccos(np.clip(x[inside], -1.0, 1.0)))
        out[~inside] = np.cosh(n * np.arccosh(np.maximum(1.0, np.abs(x[~inside]))))
        return out

    def resp(f: np.ndarray) -> np.ndarray:
        w = (f / fc) if subtype == "Lowpass" else (fc / np.maximum(f, 1e-6))
        if filter_type == "Chebyshev Type I":
            eps = math.sqrt(max(1e-6, 10.0 ** (max(0.05, passband_ripple_db) / 10.0) - 1.0))
            tn = cheb_poly(n_ord, np.minimum(w, 50.0))
            return 1.0 / np.sqrt(1.0 + (eps * tn) ** 2)
        if filter_type == "Chebyshev Type II":
            eps = 1.0 / math.sqrt(max(1e-6, 10.0 ** (max(6.0, stopband_atten_db) / 10.0) - 1.0))
            inv_w = 1.0 / np.maximum(w, 1e-4)
            tn = cheb_poly(n_ord, np.minimum(inv_w, 50.0))
            return 1.0 / np.sqrt(1.0 + 1.0 / np.maximum((eps * tn) ** 2, 1e-12))
        # Butterworth
        return 1.0 / np.sqrt(1.0 + np.minimum(w, 100.0) ** (2 * n_ord))

    return _fft_filter(audio, sr, resp)


def fx_spectral_edit_multi(audio: np.ndarray, sr: int, freq_low: float = 300.0, freq_high: float = 3000.0) -> np.ndarray:
    fl, fh = sorted([max(1.0, freq_low), max(2.0, freq_high)])
    if fl <= 25.0:
        return fx_high_pass(audio, sr, cutoff_hz=fh, rolloff_db=24)
    if fh >= sr * 0.48:
        return fx_low_pass(audio, sr, cutoff_hz=fl, rolloff_db=24)
    fc = math.sqrt(fl * fh)
    q = fc / max(1.0, fh - fl)
    return fx_notch(audio, sr, freq_hz=fc, q=q)


def fx_spectral_parametric_eq(audio: np.ndarray, sr: int, gain_db: float = -12.0, freq_low: float = 400.0, freq_high: float = 2000.0) -> np.ndarray:
    fl, fh = sorted([max(1.0, freq_low), max(2.0, freq_high)])
    fc = math.sqrt(fl * fh)
    bw = max(10.0, fh - fl)

    def resp(f: np.ndarray) -> np.ndarray:
        bell = np.exp(-0.5 * ((f - fc) / (bw * 0.45)) ** 2)
        return 10.0 ** ((gain_db * bell) / 20.0)
    return _fft_filter(audio, sr, resp)


def fx_spectral_shelves(audio: np.ndarray, sr: int, gain_db: float = -6.0, freq_low: float = 400.0, freq_high: float = 4000.0, shelf_type: str = "High Shelf") -> np.ndarray:
    fl, fh = sorted([max(1.0, freq_low), max(2.0, freq_high)])

    def resp(f: np.ndarray) -> np.ndarray:
        if shelf_type == "Low Shelf":
            w = 1.0 / (1.0 + (f / fl) ** 4)
        else:
            w = 1.0 / (1.0 + (fh / np.maximum(f, 1.0)) ** 4)
        return 10.0 ** ((gain_db * w) / 20.0)
    return _fft_filter(audio, sr, resp)


# ---------------------------------------------------------------------------
# 3. NOISE & REPAIR
# ---------------------------------------------------------------------------
def capture_noise_profile(audio: np.ndarray, sr: int, n_fft: int = 2048) -> np.ndarray:
    """Compute average magnitude spectrum of a noise-only selection."""
    a = ensure_2d(audio)
    mono = np.mean(a, axis=0)
    spec = _stft(mono, n_fft=n_fft, hop=n_fft // 4, window="Hann")
    return np.mean(np.abs(spec), axis=1).astype(np.float32)


def fx_noise_reduction(
    audio: np.ndarray,
    sr: int,
    noise_profile: Optional[np.ndarray] = None,
    reduction_db: float = 12.0,
    sensitivity: float = 6.0,
    freq_smoothing_bands: int = 3,
) -> np.ndarray:
    a = ensure_2d(audio)
    if a.shape[1] == 0:
        return a.copy()
    n_fft = 2048
    hop = 512
    if noise_profile is None or len(noise_profile) != n_fft // 2 + 1:
        # Auto-estimate from quietest 10% frames if user didn't pre-capture profile
        mono_s = np.abs(_stft(np.mean(a, axis=0), n_fft=n_fft, hop=hop))
        energies = np.mean(mono_s ** 2, axis=0)
        k = max(1, len(energies) // 10)
        quiet_idx = np.argsort(energies)[:k]
        prof = np.mean(mono_s[:, quiet_idx], axis=1)
    else:
        prof = noise_profile.astype(np.float32)

    thresh = prof[:, None] * (1.0 + sensitivity * 0.35)
    floor_gain = db_to_lin(-abs(reduction_db))
    out = np.empty_like(a, dtype=np.float32)
    for ch in range(a.shape[0]):
        st = _stft(a[ch], n_fft=n_fft, hop=hop)
        mag = np.abs(st)
        ratio = np.clip((mag - thresh) / np.maximum(thresh, 1e-8), 0.0, 1.0)
        gain = floor_gain + (1.0 - floor_gain) * ratio
        if freq_smoothing_bands > 0:
            ksize = 2 * freq_smoothing_bands + 1
            kernel = np.ones(ksize, dtype=np.float32) / ksize
            for f_idx in range(gain.shape[1]):
                gain[:, f_idx] = np.convolve(gain[:, f_idx], kernel, mode="same")
        out[ch] = _istft(st * gain, n_fft=n_fft, hop=hop, length=a.shape[1])
    return out


def fx_click_removal(audio: np.ndarray, sr: int, threshold: float = 200.0, max_spike_width: int = 20) -> np.ndarray:
    a = ensure_2d(audio).astype(np.float32, copy=True)
    n = a.shape[1]
    if n < 64:
        return a
    sens = max(1.5, 10.0 - (threshold / 100.0))
    win = max(5, min(64, max_spike_width))
    for ch in range(a.shape[0]):
        x = a[ch]
        # High-pass derivative energy
        diff = np.abs(np.diff(x, prepend=x[0]))
        med = np.maximum(1e-5, np.convolve(diff, np.ones(win * 4) / (win * 4), mode="same"))
        spikes = np.where(diff > med * sens)[0]
        for idx in spikes:
            lo = max(0, idx - win // 2)
            hi = min(n - 1, idx + win // 2)
            if hi > lo + 1:
                x[lo:hi + 1] = np.linspace(x[lo], x[hi], hi - lo + 1, dtype=np.float32)
    return a


def fx_clip_fix(audio: np.ndarray, sr: int, threshold_pct: float = 95.0, reduce_amplitude_db: float = -9.0) -> np.ndarray:
    a = ensure_2d(audio).astype(np.float32, copy=True)
    thr = np.clip(threshold_pct / 100.0, 0.5, 0.999)
    for ch in range(a.shape[0]):
        x = a[ch]
        clipped = np.abs(x) >= thr
        if not np.any(clipped):
            continue
        idx = np.where(clipped)[0]
        # Group contiguous clipped runs and reconstruct parabolic/cubic crest
        splits = np.where(np.diff(idx) > 1)[0] + 1
        for run in np.split(idx, splits):
            i0, i1 = int(run[0]), int(run[-1])
            if i0 < 2 or i1 >= len(x) - 2:
                continue
            slope_l = x[i0] - x[i0 - 1]
            slope_r = x[i1 + 1] - x[i1]
            t = np.linspace(0.0, 1.0, i1 - i0 + 1, dtype=np.float32)
            # Hermite spline across clipped flat top
            h00 = 2 * t ** 3 - 3 * t ** 2 + 1
            h10 = t ** 3 - 2 * t ** 2 + t
            h01 = -2 * t ** 3 + 3 * t ** 2
            h11 = t ** 3 - t ** 2
            span = float(i1 - i0 + 1)
            x[i0 : i1 + 1] = h00 * x[i0] + h10 * (slope_l * span * 0.65) + h01 * x[i1] + h11 * (slope_r * span * 0.65)
    return (a * db_to_lin(reduce_amplitude_db)).astype(np.float32)


def fx_repair(audio: np.ndarray, sr: int) -> np.ndarray:
    """Interpolate a short damaged selection smoothly from boundary samples & derivatives."""
    a = ensure_2d(audio).astype(np.float32, copy=True)
    n = a.shape[1]
    if n < 4:
        return a
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    for ch in range(a.shape[0]):
        m0 = (a[ch, 1] - a[ch, 0]) * n * 0.25
        m1 = (a[ch, -1] - a[ch, -2]) * n * 0.25
        a[ch] = h00 * a[ch, 0] + h10 * m0 + h01 * a[ch, -1] + h11 * m1
    return a


def fx_spectral_delete(audio: np.ndarray, sr: int, freq_low: float = 500.0, freq_high: float = 2000.0) -> np.ndarray:
    fl, fh = sorted([max(0.0, freq_low), max(1.0, freq_high)])
    a = ensure_2d(audio)
    n_fft = 2048
    hop = 512
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / max(1, sr))
    mask = np.ones_like(freqs, dtype=np.float32)
    mask[(freqs >= fl) & (freqs <= fh)] = 0.0
    out = np.empty_like(a, dtype=np.float32)
    for ch in range(a.shape[0]):
        st = _stft(a[ch], n_fft=n_fft, hop=hop)
        out[ch] = _istft(st * mask[:, None], n_fft=n_fft, hop=hop, length=a.shape[1])
    return out


# ---------------------------------------------------------------------------
# 4. DELAY & REVERB
# ---------------------------------------------------------------------------
def fx_echo(audio: np.ndarray, sr: int, delay_s: float = 0.35, decay: float = 0.45) -> np.ndarray:
    a = ensure_2d(audio)
    d = max(1, int(round(delay_s * sr)))
    out = a.copy()
    gain = float(np.clip(decay, 0.0, 0.95))
    cur = a.copy()
    for _ in range(12):
        if gain < 1e-3:
            break
        shifted = np.zeros_like(a)
        if d < a.shape[1]:
            shifted[:, d:] = cur[:, :-d] * gain
        out += shifted
        cur = shifted
        if np.max(np.abs(cur)) < 1e-4:
            break
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def fx_delay(
    audio: np.ndarray,
    sr: int,
    delay_type: str = "Regular",
    level_db: float = -6.0,
    delay_s: float = 0.3,
    pitch_change: float = 0.0,
    num_echoes: int = 5,
) -> np.ndarray:
    a = ensure_2d(audio)
    out = a.copy()
    g = db_to_lin(level_db)
    cur_t = 0.0
    step = delay_s
    cur_sig = a.copy()
    for i in range(1, max(1, num_echoes) + 1):
        if delay_type == "Bouncing Ball":
            step = delay_s * (0.72 ** (i - 1))
        elif delay_type == "Reverse Bouncing Ball":
            step = delay_s * (0.72 ** (num_echoes - i))
        cur_t += step
        d = int(round(cur_t * sr))
        if d >= a.shape[1]:
            break
        if abs(pitch_change) > 0.05:
            cur_sig = change_pitch(cur_sig, sr, pitch_change)
        amp = g ** i
        n_copy = min(a.shape[1] - d, cur_sig.shape[1])
        if n_copy > 0:
            out[:, d : d + n_copy] += cur_sig[:, :n_copy] * amp
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def fx_reverb(
    audio: np.ndarray,
    sr: int,
    room_size: float = 65.0,
    pre_delay_ms: float = 15.0,
    reverberance: float = 55.0,
    damping: float = 50.0,
    tone_low: float = 100.0,
    tone_high: float = 100.0,
    wet_db: float = -6.0,
    dry_db: float = 0.0,
    stereo_width: float = 100.0,
) -> np.ndarray:
    """Rich algorithmic convolution reverb generated from damped stereo room IR."""
    a = ensure_2d(audio)
    n = a.shape[1]
    if n == 0:
        return a.copy()
    rt60 = 0.25 + (room_size / 100.0) * 2.2 * (0.4 + reverberance / 100.0)
    ir_len = min(int(sr * min(4.0, rt60)), max(2048, sr * 2))
    rng = np.random.default_rng(42)
    t = np.arange(ir_len, dtype=np.float64) / sr
    decay = np.exp(-6.9077 * t / max(0.15, rt60))
    pre_s = int(round(pre_delay_ms * 0.001 * sr))

    wet = np.zeros_like(a, dtype=np.float32)
    for ch in range(a.shape[0]):
        noise = rng.standard_normal(ir_len) * decay
        # Early reflections
        for er_ms, er_g in [(7, 0.5), (14, 0.35), (23, 0.28), (37, 0.2)]:
            idx = int(er_ms * 0.001 * sr) + ch * 19
            if idx < ir_len:
                noise[idx] += er_g
        if pre_s > 0 and pre_s < ir_len:
            noise = np.concatenate([np.zeros(pre_s), noise[:-pre_s]])
        # High-frequency damping on IR
        cutoff = 16000.0 * (1.0 - 0.78 * (damping / 100.0)) * (tone_high / 100.0)
        ir = fx_low_pass(noise[None, :].astype(np.float32), sr, cutoff_hz=max(500.0, cutoff), rolloff_db=12)[0]
        if tone_low < 99.0:
            ir = fx_high_pass(ir[None, :], sr, cutoff_hz=max(30.0, (100.0 - tone_low) * 4.0), rolloff_db=12)[0]
        ir /= max(1e-6, float(np.sqrt(np.sum(ir.astype(np.float64) ** 2))))
        # Fast FFT convolution
        nfft = 1 << (n + ir_len - 2).bit_length()
        conv = np.fft.irfft(np.fft.rfft(a[ch].astype(np.float64), nfft) * np.fft.rfft(ir.astype(np.float64), nfft), nfft)
        wet[ch] = conv[:n].astype(np.float32)

    if a.shape[0] == 2 and stereo_width < 100.0:
        w = stereo_width / 100.0
        mid = 0.5 * (wet[0] + wet[1])
        side = 0.5 * (wet[0] - wet[1]) * w
        wet[0], wet[1] = mid + side, mid - side

    out = a * db_to_lin(dry_db) + wet * db_to_lin(wet_db)
    return np.clip(out, -1.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 5. DISTORTION & MODULATION
# ---------------------------------------------------------------------------
def fx_distortion(
    audio: np.ndarray,
    sr: int,
    dist_type: str = "Soft Overdrive",
    drive: float = 50.0,
    threshold_db: float = -6.0,
    makeup_db: float = 0.0,
) -> np.ndarray:
    a = ensure_2d(audio)
    g = 1.0 + (drive / 100.0) * 14.0
    thr = db_to_lin(threshold_db)
    x = a * g
    if dist_type == "Hard Clipping":
        y = np.clip(x, -thr, thr)
    elif dist_type == "Soft Clipping":
        y = thr * np.tanh(x / max(thr, 1e-4))
    elif dist_type in ("Soft Overdrive", "Medium Overdrive", "Hard Overdrive"):
        k = {"Soft Overdrive": 1.5, "Medium Overdrive": 3.5, "Hard Overdrive": 7.0}[dist_type]
        y = (2.0 / np.pi) * np.arctan(x * k * 0.5)
    elif dist_type in ("Cubic Curve", "Cubic Curve (odd harmonics)"):
        xc = np.clip(x * 0.5, -1.0, 1.0)
        y = 1.5 * xc - 0.5 * (xc ** 3)
    elif dist_type == "Even Harmonics":
        y = np.tanh(x + 0.35 * (x ** 2))
    elif dist_type == "Expand and Compress":
        y = np.sign(a) * np.tanh((np.abs(a) ** 1.35) * (1.0 + drive / 30.0))
    elif dist_type == "Leveller":
        y = np.sign(a) * np.power(np.abs(a), 0.55)
    elif dist_type in ("Rectifier", "Rectifier Distortion"):
        y = np.abs(a) * 2.0 - 0.5
    elif dist_type == "Hard Limiter 1413":
        y = np.clip(a * (1.0 + drive / 50.0), -thr, thr)
    else:
        y = np.tanh(x)
    return np.clip(y * db_to_lin(makeup_db), -1.0, 1.0).astype(np.float32)


def fx_tremolo(audio: np.ndarray, sr: int, waveform: str = "Sine", start_phase: float = 0.0, wet_pct: float = 40.0, lfo_freq_hz: float = 4.0) -> np.ndarray:
    a = ensure_2d(audio)
    t = np.arange(a.shape[1], dtype=np.float32) / max(1, sr)
    ph = 2.0 * np.pi * lfo_freq_hz * t + math.radians(start_phase)
    if waveform == "Triangle":
        lfo = 2.0 / np.pi * np.arcsin(np.sin(ph))
    elif waveform == "Sawtooth":
        lfo = 2.0 * ((lfo_freq_hz * t + start_phase / 360.0) % 1.0) - 1.0
    elif waveform == "Square":
        lfo = np.sign(np.sin(ph))
    else:
        lfo = np.sin(ph)
    depth = np.clip(wet_pct / 100.0, 0.0, 1.0)
    mod = 1.0 - depth * 0.5 * (1.0 - lfo)
    return (a * mod[None, :]).astype(np.float32)


def fx_phaser(audio: np.ndarray, sr: int, stages: int = 4, dry_wet: int = 128, lfo_freq_hz: float = 0.4, start_phase: float = 0.0, depth: int = 100, feedback: float = 0.0) -> np.ndarray:
    a = ensure_2d(audio)
    n = a.shape[1]
    if n == 0:
        return a.copy()
    t = np.arange(n, dtype=np.float64) / max(1, sr)
    lfo = 0.5 * (1.0 + np.sin(2.0 * np.pi * lfo_freq_hz * t + math.radians(start_phase)))
    wet_mix = np.clip(dry_wet / 255.0, 0.0, 1.0)
    # Modulated variable delay comb approximation (fast vectorized allpass-like sweep)
    max_d = max(4.0, (depth / 255.0) * (sr * 0.004))
    delay_samples = 2.0 + lfo * max_d
    idx = np.arange(n, dtype=np.float64)
    src = np.clip(idx - delay_samples, 0.0, n - 1)
    out = np.empty_like(a, dtype=np.float32)
    fb = np.clip(feedback / 100.0, -0.8, 0.8)
    for ch in range(a.shape[0]):
        w = np.interp(src, idx, a[ch].astype(np.float64))
        for stg in range(1, max(1, stages // 2)):
            s2 = np.clip(idx - delay_samples * (1.0 + 0.35 * stg), 0.0, n - 1)
            w = 0.5 * (w + np.interp(s2, idx, w))
        out[ch] = np.clip((1.0 - wet_mix) * a[ch] + wet_mix * (a[ch] - w * (0.8 + 0.2 * fb)), -1.0, 1.0).astype(np.float32)
    return out


def fx_wahwah(audio: np.ndarray, sr: int, lfo_freq_hz: float = 1.5, start_phase: float = 0.0, depth: float = 70.0, resonance: float = 2.5, freq_offset_pct: float = 30.0, output_gain_db: float = -3.0) -> np.ndarray:
    a = ensure_2d(audio)
    n = a.shape[1]
    if n == 0:
        return a.copy()
    n_fft = 1024
    hop = 256
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / max(1, sr))
    out = np.empty_like(a, dtype=np.float32)
    for ch in range(a.shape[0]):
        st = _stft(a[ch], n_fft=n_fft, hop=hop)
        t_fr = np.arange(st.shape[1], dtype=np.float64) * (hop / max(1, sr))
        lfo = 0.5 * (1.0 + np.sin(2.0 * np.pi * lfo_freq_hz * t_fr + math.radians(start_phase)))
        base_f = 200.0 + (freq_offset_pct / 100.0) * 1400.0
        sweep_f = base_f + lfo * (depth / 100.0) * 2600.0
        bw = np.maximum(120.0, sweep_f / max(0.5, resonance))
        resp = 1.0 / np.sqrt(1.0 + ((freqs[:, None] - sweep_f[None, :]) / bw[None, :]) ** 2)
        out[ch] = _istft(st * (0.25 + 1.35 * resp), n_fft=n_fft, hop=hop, length=n)
    return np.clip(out * db_to_lin(output_gain_db), -1.0, 1.0).astype(np.float32)


def fx_vocoder(
    audio: np.ndarray,
    sr: int,
    distance: float = 20.0,
    output_choice: str = "Both Channels",
    bands: int = 40,
    track_vl_pct: float = 100.0,
    noise_vl_pct: float = 0.0,
    radar_vl_pct: float = 100.0,
    radar_freq_hz: float = 30.0,
) -> np.ndarray:
    """Audacity-compatible channel vocoder (modulates right-channel carrier + white noise + radar needles by left-channel envelope)."""
    a = ensure_2d(audio)
    n = a.shape[1]
    if n == 0:
        return a.copy()
    mod_mono = a[0] if a.shape[0] >= 2 else np.mean(a, axis=0)
    t = np.arange(n, dtype=np.float32) / max(1, sr)
    # Build composite carrier matching Audacity vocoder.ny (Right channel / synth + White Noise + Radar Needles)
    carrier = np.zeros(n, dtype=np.float32)
    if track_vl_pct > 0.0:
        if a.shape[0] >= 2:
            carrier += a[1] * (track_vl_pct / 100.0)
        else:
            for mult in (1.0, 1.5, 2.0):
                carrier += (2.0 * ((130.0 * mult * t) % 1.0) - 1.0) * 0.3 * (track_vl_pct / 100.0)
    if noise_vl_pct > 0.0:
        rng = np.random.default_rng(7)
        carrier += rng.standard_normal(n).astype(np.float32) * 0.45 * (noise_vl_pct / 100.0)
    if radar_vl_pct > 0.0:
        # Sharp pulse train ("Radar Needles") at radar_freq_hz
        phase = (radar_freq_hz * t) % 1.0
        needles = np.where(phase < 0.04, 1.0, 0.0).astype(np.float32) - 0.04
        carrier += needles * (radar_vl_pct / 100.0)
    if np.max(np.abs(carrier)) < 1e-6:
        carrier = (2.0 * ((130.0 * t) % 1.0) - 1.0).astype(np.float32)

    n_fft = 1024
    hop = max(64, int(round(128 * (distance / 20.0))))
    hop = min(512, hop)
    st_m = _stft(mod_mono, n_fft=n_fft, hop=hop)
    st_c = _stft(carrier, n_fft=n_fft, hop=hop)
    mag_m = np.abs(st_m)
    n_bins = st_m.shape[0]
    edges = np.unique(np.geomspace(1, n_bins, max(4, min(240, int(bands))) + 1).astype(int))
    env_spec = np.zeros_like(mag_m)
    for i in range(len(edges) - 1):
        b0, b1 = edges[i], edges[i + 1]
        if b1 > b0:
            env_spec[b0:b1, :] = np.mean(mag_m[b0:b1, :], axis=0, keepdims=True)
    voc = _istft(st_c * (env_spec / (np.abs(st_c) + 1e-4)), n_fft=n_fft, hop=hop, length=n)
    pk = float(np.max(np.abs(voc)))
    if pk > 1e-6:
        voc *= 0.85 / pk
    if output_choice == "Right Only" and a.shape[0] >= 2:
        return np.vstack([a[0], voc]).astype(np.float32)
    return np.vstack([voc] * a.shape[0]).astype(np.float32)


# ---------------------------------------------------------------------------
# 6. PITCH & TEMPO
# ---------------------------------------------------------------------------
def _phase_vocoder(x: np.ndarray, stretch_ratio: float, n_fft: int = 2048, hop: int = 512) -> np.ndarray:
    """STFT phase vocoder: stretch_ratio > 1 slows down (longer), < 1 speeds up (shorter)."""
    if len(x) < n_fft:
        n_fft = max(128, 1 << max(7, (len(x) // 2).bit_length()))
        hop = n_fft // 4
    st = _stft(x, n_fft=n_fft, hop=hop)
    n_bins, n_frames = st.shape
    if n_frames < 2:
        return x.copy()
    time_steps = np.arange(0.0, n_frames - 1, 1.0 / max(0.05, stretch_ratio))
    omega = 2.0 * np.pi * hop * np.arange(n_bins) / n_fft
    phase_acc = np.angle(st[:, 0]).astype(np.float64)
    out_spec = np.empty((n_bins, len(time_steps)), dtype=np.complex64)
    for idx, step in enumerate(time_steps):
        i0 = int(math.floor(step))
        i1 = min(n_frames - 1, i0 + 1)
        frac = step - i0
        mag = (1.0 - frac) * np.abs(st[:, i0]) + frac * np.abs(st[:, i1])
        dp = np.angle(st[:, i1]) - np.angle(st[:, i0]) - omega
        dp = dp - 2.0 * np.pi * np.round(dp / (2.0 * np.pi))
        phase_acc += omega + dp
        out_spec[:, idx] = (mag * np.exp(1j * phase_acc)).astype(np.complex64)
    target_len = max(1, int(round(len(x) * stretch_ratio)))
    return _istft(out_spec, n_fft=n_fft, hop=hop, length=target_len)


def change_tempo(audio: np.ndarray, sr: int, percent_change: float = 0.0) -> np.ndarray:
    """Change tempo without changing pitch. +100% = 2x faster (half length), -50% = half speed (2x length)."""
    a = ensure_2d(audio)
    factor = max(0.1, 1.0 + percent_change / 100.0)
    if abs(factor - 1.0) < 1e-4 or a.shape[1] == 0:
        return a.copy()
    stretch = 1.0 / factor
    chans = [_phase_vocoder(a[ch], stretch) for ch in range(a.shape[0])]
    min_l = min(len(c) for c in chans)
    return np.vstack([c[:min_l] for c in chans]).astype(np.float32)


def change_pitch(audio: np.ndarray, sr: int, semitones: float = 0.0) -> np.ndarray:
    """Change pitch without changing duration via phase vocoder + resampling."""
    a = ensure_2d(audio)
    if abs(semitones) < 1e-3 or a.shape[1] == 0:
        return a.copy()
    pitch_ratio = 2.0 ** (semitones / 12.0)
    orig_len = a.shape[1]
    stretched = np.vstack([_phase_vocoder(a[ch], pitch_ratio) for ch in range(a.shape[0])])
    # Resample back to orig_len
    x_old = np.arange(stretched.shape[1], dtype=np.float64)
    x_new = np.linspace(0.0, stretched.shape[1] - 1, orig_len, dtype=np.float64)
    out = np.empty((a.shape[0], orig_len), dtype=np.float32)
    for ch in range(a.shape[0]):
        out[ch] = np.interp(x_new, x_old, stretched[ch]).astype(np.float32)
    return out


def fx_change_speed(audio: np.ndarray, sr: int, percent_change: float = 0.0) -> np.ndarray:
    a = ensure_2d(audio)
    factor = max(0.1, 1.0 + percent_change / 100.0)
    if abs(factor - 1.0) < 1e-4 or a.shape[1] == 0:
        return a.copy()
    new_len = max(1, int(round(a.shape[1] / factor)))
    x_old = np.arange(a.shape[1], dtype=np.float64)
    x_new = np.linspace(0.0, a.shape[1] - 1, new_len, dtype=np.float64)
    out = np.empty((a.shape[0], new_len), dtype=np.float32)
    for ch in range(a.shape[0]):
        out[ch] = np.interp(x_new, x_old, a[ch]).astype(np.float32)
    return out


def fx_sliding_stretch(
    audio: np.ndarray,
    sr: int,
    initial_tempo_pct: float = 0.0,
    final_tempo_pct: float = 25.0,
    initial_pitch_semi: float = 0.0,
    final_pitch_semi: float = 0.0,
) -> np.ndarray:
    """Smoothly ramp tempo & pitch from initial to final values across the selection."""
    a = ensure_2d(audio)
    n = a.shape[1]
    if n < 256:
        return a.copy()
    chunks = 8
    step = max(128, n // chunks)
    pieces: List[np.ndarray] = []
    for i in range(chunks):
        s0 = i * step
        s1 = n if i == chunks - 1 else (i + 1) * step
        frac = i / max(1, chunks - 1)
        tp = initial_tempo_pct + (final_tempo_pct - initial_tempo_pct) * frac
        ps = initial_pitch_semi + (final_pitch_semi - initial_pitch_semi) * frac
        seg = a[:, s0:s1]
        if abs(tp) > 0.1:
            seg = change_tempo(seg, sr, tp)
        if abs(ps) > 0.02:
            seg = change_pitch(seg, sr, ps)
        pieces.append(seg)
    return np.concatenate(pieces, axis=1).astype(np.float32)


def fx_paulstretch(audio: np.ndarray, sr: int, stretch_factor: float = 4.0, time_resolution_s: float = 0.25) -> np.ndarray:
    """Iconic Paulstretch extreme ambient time-stretching via randomized STFT phases."""
    a = ensure_2d(audio)
    if a.shape[1] == 0:
        return a.copy()
    win_size = max(512, min(32768, 1 << int(round(math.log2(max(512, sr * time_resolution_s))))))
    hop_out = win_size // 2
    hop_in = max(1, int(round(hop_out / max(1.0, stretch_factor))))
    rng = np.random.default_rng(123)
    win = make_window("Hann", win_size).astype(np.float64)
    chans = []
    for ch in range(a.shape[0]):
        x = a[ch].astype(np.float64)
        n_frames = max(1, int((len(x) - win_size) // max(1, hop_in)) + 1) if len(x) >= win_size else 1
        if len(x) < win_size:
            x = np.pad(x, (0, win_size - len(x)))
        out_len = win_size + hop_out * n_frames
        y = np.zeros(out_len, dtype=np.float64)
        for i in range(n_frames):
            pos_in = min(len(x) - win_size, i * hop_in)
            frame = x[pos_in : pos_in + win_size] * win
            spec = np.fft.rfft(frame)
            rand_phase = np.exp(1j * rng.uniform(0.0, 2.0 * np.pi, size=len(spec)))
            grain = np.fft.irfft(np.abs(spec) * rand_phase, n=win_size) * win
            pos_out = i * hop_out
            y[pos_out : pos_out + win_size] += grain
        pk = float(np.max(np.abs(y)))
        if pk > 1e-6:
            y *= 0.85 / pk
        chans.append(y.astype(np.float32))
    return np.vstack(chans)


# ---------------------------------------------------------------------------
# 7. SPECIAL EFFECTS
# ---------------------------------------------------------------------------
def fx_invert(audio: np.ndarray, sr: int) -> np.ndarray:
    return (-ensure_2d(audio)).astype(np.float32)


def fx_reverse(audio: np.ndarray, sr: int) -> np.ndarray:
    return np.ascontiguousarray(ensure_2d(audio)[:, ::-1], dtype=np.float32)


def fx_repeat(audio: np.ndarray, sr: int, count: int = 2) -> np.ndarray:
    a = ensure_2d(audio)
    return np.tile(a, (1, max(1, int(count) + 1))).astype(np.float32)


def fx_truncate_silence(
    audio: np.ndarray,
    sr: int,
    threshold_db: float = -30.0,
    min_duration_s: float = 0.5,
    action: str = "Truncate",
    truncate_to_s: float = 0.15,
    compress_pct: float = 50.0,
) -> np.ndarray:
    a = ensure_2d(audio)
    n = a.shape[1]
    if n == 0:
        return a.copy()
    thr = db_to_lin(threshold_db)
    step = max(1, sr // 100)  # 10ms frames
    mono = np.max(np.abs(a), axis=0)
    min_frames = max(1, int(round(min_duration_s * sr / step)))
    trunc_samples = int(round(truncate_to_s * sr))

    keep_parts: List[np.ndarray] = []
    i = 0
    while i < n:
        if float(np.max(mono[i : min(n, i + step)])) >= thr:
            j = i + step
            while j < n and float(np.max(mono[j : min(n, j + step)])) >= thr:
                j += step
            keep_parts.append(a[:, i : min(n, j)])
            i = j
        else:
            j = i + step
            while j < n and float(np.max(mono[j : min(n, j + step)])) < thr:
                j += step
            sil_len = min(n, j) - i
            if sil_len >= min_frames * step:
                target = trunc_samples if action == "Truncate" else int(sil_len * (compress_pct / 100.0))
                if target > 0:
                    keep_parts.append(a[:, i : i + min(sil_len, target)])
            else:
                keep_parts.append(a[:, i : min(n, j)])
            i = j
    return np.concatenate(keep_parts, axis=1).astype(np.float32) if keep_parts else np.zeros((a.shape[0], 0), dtype=np.float32)


def fx_vocal_reduction_isolation(
    audio: np.ndarray,
    sr: int,
    action: str = "Remove Vocals",
    strength: float = 1.0,
    low_cut_hz: float = 120.0,
    high_cut_hz: float = 9000.0,
) -> np.ndarray:
    a = ensure_2d(audio)
    if a.shape[0] < 2:
        return a.copy()
    L, R = a[0], a[1]
    mid = 0.5 * (L + R)
    side = 0.5 * (L - R)
    if action == "Remove Center":
        return np.vstack([side, -side]).astype(np.float32)
    if action == "Isolate Center":
        return np.vstack([mid, mid]).astype(np.float32)

    # Band-limited center extraction for vocal frequencies
    n_fft = 2048
    hop = 512
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / max(1, sr))
    vocal_band = ((freqs >= low_cut_hz) & (freqs <= high_cut_hz)).astype(np.float32)
    st_l = _stft(L, n_fft=n_fft, hop=hop)
    st_r = _stft(R, n_fft=n_fft, hop=hop)
    st_m = 0.5 * (st_l + st_r)
    st_s = 0.5 * (st_l - st_r)
    # Center correlation mask
    center_weight = np.clip((np.abs(st_m) - np.abs(st_s)) / (np.abs(st_m) + np.abs(st_s) + 1e-6), 0.0, 1.0)
    mask = np.clip(center_weight * strength * vocal_band[:, None], 0.0, 1.0)
    if action == "Isolate Vocals":
        out_l = _istft(st_m * mask, n_fft=n_fft, hop=hop, length=a.shape[1])
        out_r = out_l.copy()
    else:  # Remove Vocals (preserves bass & highs outside vocal band!)
        out_l = _istft(st_l - st_m * mask, n_fft=n_fft, hop=hop, length=a.shape[1])
        out_r = _istft(st_r - st_m * mask, n_fft=n_fft, hop=hop, length=a.shape[1])
    return np.vstack([out_l, out_r]).astype(np.float32)


# ---------------------------------------------------------------------------
# GENERATORS
# ---------------------------------------------------------------------------
def gen_tone(sr: int, duration_s: float = 5.0, waveform: str = "Sine", freq_hz: float = 440.0, amplitude: float = 0.8, channels: int = 1) -> np.ndarray:
    n = max(1, int(round(duration_s * sr)))
    t = np.arange(n, dtype=np.float64) / max(1, sr)
    ph = 2.0 * np.pi * freq_hz * t
    if waveform == "Square":
        y = np.sign(np.sin(ph))
    elif waveform == "Square (No Alias)":
        y = np.zeros(n, dtype=np.float64)
        k = 1
        while k * freq_hz < sr * 0.45 and k < 60:
            y += np.sin(k * ph) / k
            k += 2
        y *= 4.0 / np.pi
    elif waveform == "Sawtooth":
        y = 2.0 * ((freq_hz * t) % 1.0) - 1.0
    elif waveform == "Triangle":
        y = (2.0 / np.pi) * np.arcsin(np.sin(ph))
    else:
        y = np.sin(ph)
    y = (y * amplitude).astype(np.float32)
    return np.vstack([y] * max(1, channels))


def gen_chirp(sr: int, duration_s: float = 5.0, waveform: str = "Sine", f_start: float = 220.0, f_end: float = 1760.0, amp_start: float = 0.8, amp_end: float = 0.8, interp: str = "Logarithmic", channels: int = 1) -> np.ndarray:
    n = max(1, int(round(duration_s * sr)))
    t = np.arange(n, dtype=np.float64) / max(1, sr)
    if interp == "Logarithmic" and f_start > 0 and f_end > 0 and abs(f_end - f_start) > 1e-3:
        k = (f_end / f_start) ** (1.0 / max(1e-6, duration_s))
        phase = 2.0 * np.pi * f_start * (k ** t - 1.0) / math.log(k)
    else:
        phase = 2.0 * np.pi * (f_start * t + 0.5 * (f_end - f_start) / max(1e-6, duration_s) * t ** 2)
    if waveform == "Square":
        y = np.sign(np.sin(phase))
    elif waveform == "Sawtooth":
        y = 2.0 * ((phase / (2.0 * np.pi)) % 1.0) - 1.0
    else:
        y = np.sin(phase)
    amp = np.linspace(amp_start, amp_end, n)
    y = (y * amp).astype(np.float32)
    return np.vstack([y] * max(1, channels))


def gen_noise(sr: int, duration_s: float = 5.0, noise_type: str = "White", amplitude: float = 0.4, channels: int = 1) -> np.ndarray:
    n = max(1, int(round(duration_s * sr)))
    rng = np.random.default_rng()
    out = np.empty((max(1, channels), n), dtype=np.float32)
    for ch in range(out.shape[0]):
        w = rng.standard_normal(n)
        if noise_type == "Pink":
            spec = np.fft.rfft(w)
            f = np.fft.rfftfreq(n, 1.0 / sr)
            spec /= np.sqrt(np.maximum(f, 1.0))
            y = np.fft.irfft(spec, n=n)
        elif noise_type == "Brown":
            y = np.cumsum(w)
            y -= np.mean(y)
        else:
            y = w
        pk = float(np.max(np.abs(y)))
        if pk > 1e-9:
            y = y / pk * amplitude
        out[ch] = y.astype(np.float32)
    return out


DTMF_MAP = {
    "1": (697, 1209), "2": (697, 1336), "3": (697, 1477), "A": (697, 1633),
    "4": (770, 1209), "5": (770, 1336), "6": (770, 1477), "B": (770, 1633),
    "7": (852, 1209), "8": (852, 1336), "9": (852, 1477), "C": (852, 1633),
    "*": (941, 1209), "0": (941, 1336), "#": (941, 1477), "D": (941, 1633),
}


def gen_dtmf(sr: int, sequence: str = "555-1234", duration_s: float = 3.0, duty_cycle_pct: float = 55.0, amplitude: float = 0.7, channels: int = 1) -> np.ndarray:
    chars = [c for c in sequence.upper() if c in DTMF_MAP]
    if not chars:
        return gen_silence(sr, duration_s, channels)
    slot_s = duration_s / len(chars)
    tone_s = slot_s * np.clip(duty_cycle_pct / 100.0, 0.1, 0.95)
    parts = []
    for ch in chars:
        f1, f2 = DTMF_MAP[ch]
        n_slot = max(1, int(round(slot_s * sr)))
        n_tone = max(1, int(round(tone_s * sr)))
        buf = np.zeros(n_slot, dtype=np.float32)
        t = np.arange(n_tone, dtype=np.float64) / sr
        env = np.minimum(1.0, t / 0.005) * np.minimum(1.0, (tone_s - t) / 0.005)
        buf[:n_tone] = (0.5 * (np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)) * env * amplitude).astype(np.float32)
        parts.append(buf)
    y = np.concatenate(parts)
    return np.vstack([y] * max(1, channels))


def gen_silence(sr: int, duration_s: float = 5.0, channels: int = 1) -> np.ndarray:
    return np.zeros((max(1, channels), max(1, int(round(duration_s * sr)))), dtype=np.float32)


def gen_rhythm_track(sr: int, bpm: float = 120.0, beats_per_bar: int = 4, num_bars: int = 8, swing: float = 0.0, click_sound: str = "Metronome", channels: int = 1) -> np.ndarray:
    beat_s = 60.0 / max(20.0, bpm)
    total_beats = max(1, beats_per_bar * num_bars)
    total_n = int(round(total_beats * beat_s * sr)) + sr // 4
    y = np.zeros(total_n, dtype=np.float32)
    rng = np.random.default_rng(11)
    for b in range(total_beats):
        is_accent = (b % max(1, beats_per_bar)) == 0
        sw = (swing / 100.0) * beat_s * 0.25 if (b % 2 == 1) else 0.0
        pos = int(round((b * beat_s + sw) * sr))
        clen = min(int(sr * 0.045), total_n - pos)
        if clen <= 0:
            continue
        t = np.arange(clen, dtype=np.float64) / sr
        if click_sound == "Ping":
            f = 1320.0 if is_accent else 880.0
            tick = np.sin(2 * np.pi * f * t) * np.exp(-t * 55.0)
        elif click_sound == "Woodblock":
            f = 1050.0 if is_accent else 720.0
            tick = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.7 * t)) * np.exp(-t * 110.0)
        else:  # Crisp Metronome / Studio Click
            f = 1600.0 if is_accent else 950.0
            tick = (0.7 * np.sin(2 * np.pi * f * t) + 0.3 * rng.standard_normal(clen) * np.exp(-t * 240.0)) * np.exp(-t * 95.0)
        y[pos : pos + clen] += (tick * (0.85 if is_accent else 0.55)).astype(np.float32)
    return np.vstack([np.clip(y, -1.0, 1.0)] * max(1, channels))


def gen_plucked(sr: int, midi_pitch: int = 60, duration_s: float = 2.0, decay_type: str = "Gradual", amplitude: float = 0.85, channels: int = 1) -> np.ndarray:
    """Karplus-Strong physical-modeling plucked string synthesizer."""
    freq = 440.0 * (2.0 ** ((midi_pitch - 69) / 12.0))
    period = max(2, int(round(sr / max(20.0, freq))))
    n = max(period * 2, int(round(duration_s * sr)))
    rng = np.random.default_rng()
    buf = rng.uniform(-1.0, 1.0, size=period).astype(np.float64)
    buf -= np.mean(buf)
    y = np.zeros(n, dtype=np.float64)
    damp = 0.996 if decay_type == "Gradual" else 0.985
    for i in range(n):
        idx = i % period
        nxt = (idx + 1) % period
        y[i] = buf[idx]
        buf[idx] = damp * 0.5 * (buf[idx] + buf[nxt])
    pk = float(np.max(np.abs(y)))
    if pk > 1e-9:
        y = y / pk * amplitude
    return np.vstack([y.astype(np.float32)] * max(1, channels))


def gen_risset_drum(
    sr: int,
    freq_hz: float = 100.0,
    decay_s: float = 2.0,
    noise_cf_hz: float = 500.0,
    noise_bw_hz: float = 400.0,
    noise_pct: float = 25.0,
    amplitude: float = 0.8,
    channels: int = 1,
) -> np.ndarray:
    """Jean-Claude Risset percussion drum generator (exact parity with Audacity rissetdrum.ny)."""
    dur = max(0.1, float(decay_s))
    n = max(64, int(round(dur * sr)))
    t = np.arange(n, dtype=np.float64) / sr
    half_life = dur / 8.0
    env_full = np.power(0.5, t / max(1e-4, half_life))
    env_half = np.where(t <= dur * 0.5, np.power(0.5, t / max(1e-4, half_life * 0.5)), 0.0)

    noise_g = np.clip(noise_pct / 100.0, 0.0, 1.0)
    tone_g = 1.0 - noise_g
    # Inharmonic Risset modal table: harmonics 10, 16, 22, 23 of (freq * 0.1)
    base_f = max(5.0, freq_hz * 0.1)
    modal = 0.17 * (
        1.00 * np.sin(2.0 * np.pi * base_f * 10.0 * t)
        + 1.50 * np.sin(2.0 * np.pi * base_f * 16.0 * t)
        + 2.00 * np.sin(2.0 * np.pi * base_f * 22.0 * t)
        + 1.50 * np.sin(2.0 * np.pi * base_f * 23.0 * t)
    )
    rng = np.random.default_rng()
    raw_noise = rng.standard_normal(n).astype(np.float32)
    lp_noise = fx_low_pass(raw_noise[None, :], sr, cutoff_hz=max(10.0, noise_bw_hz), rolloff_db=36)[0].astype(np.float64)
    noise_band = noise_g * np.sin(2.0 * np.pi * noise_cf_hz * t) * lp_noise

    out = env_half * (noise_band + tone_g * modal) + tone_g * env_full * np.sin(2.0 * np.pi * freq_hz * t)
    pk = float(np.max(np.abs(out)))
    if pk > 1e-9:
        out = out / pk * amplitude
    return np.vstack([out.astype(np.float32)] * max(1, channels))


def measure_rms(audio: np.ndarray) -> Dict[str, Any]:
    """Measure Left, Right, and Combined RMS levels in dB (parity with Audacity rms.ny)."""
    a = ensure_2d(audio)
    if a.shape[1] == 0:
        return {"channels": a.shape[0], "summary": "No audio selected."}
    if a.shape[0] == 1:
        r = float(np.sqrt(np.mean(a[0].astype(np.float64) ** 2)))
        db = lin_to_db(r)
        return {"channels": 1, "mono_db": round(db, 2), "summary": f"Mono: {db:.2f} dB"}
    rl = float(np.sqrt(np.mean(a[0].astype(np.float64) ** 2)))
    rr = float(np.sqrt(np.mean(a[1].astype(np.float64) ** 2)))
    rst = math.sqrt((rl * rl + rr * rr) / 2.0)
    dbl, dbr, dbst = lin_to_db(rl), lin_to_db(rr), lin_to_db(rst)
    return {
        "channels": 2,
        "left_db": round(dbl, 2),
        "right_db": round(dbr, 2),
        "stereo_db": round(dbst, 2),
        "summary": f"Left:   {dbl:.2f} dB\nRight:  {dbr:.2f} dB\nStereo: {dbst:.2f} dB",
    }


# ---------------------------------------------------------------------------
# ANALYSIS TOOLS
# ---------------------------------------------------------------------------
def compute_spectrum(audio: np.ndarray, sr: int, n_fft: int = 4096, window: str = "Hann", algorithm: str = "Spectrum") -> Tuple[np.ndarray, np.ndarray]:
    """Compute frequency spectrum (Hz, dB), cepstrum, or autocorrelation."""
    a = ensure_2d(audio)
    mono = np.mean(a, axis=0)
    if len(mono) == 0:
        return np.array([20.0, 20000.0]), np.array([-90.0, -90.0])
    if algorithm == "Autocorrelation":
        n = min(len(mono), n_fft)
        x = mono[:n].astype(np.float64) * make_window(window, n)
        ac = np.fft.irfft(np.abs(np.fft.rfft(x, n=2 * n)) ** 2, n=2 * n)[:n]
        ac /= max(1e-9, ac[0])
        lags = np.arange(n) / max(1, sr)
        return lags, ac
    st = _stft(mono, n_fft=n_fft, hop=max(64, n_fft // 4), window=window)
    mag = np.mean(np.abs(st), axis=1)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / max(1, sr))
    db = 20.0 * np.log10(np.maximum(mag / (n_fft * 0.25), 1e-6))
    return freqs, db


def compute_spectrogram_db(audio: np.ndarray, sr: int, window_size: int = 1024, window_type: str = "Hann", max_cols: int = 1200) -> Tuple[np.ndarray, np.ndarray]:
    """Compute STFT magnitude in dB shaped (freq_bins, time_frames) for fast display."""
    a = ensure_2d(audio)
    mono = np.mean(a, axis=0)
    n = len(mono)
    if n < 32:
        return np.full((64, 4), -80.0, dtype=np.float32), np.linspace(0, sr / 2, 64)
    n_fft = max(64, min(window_size, 1 << max(6, int(math.log2(max(64, n))))))
    hop = max(32, max(n_fft // 4, n // max(1, max_cols)))
    st = _stft(mono, n_fft=n_fft, hop=hop, window=window_type)
    db = 20.0 * np.log10(np.maximum(np.abs(st) / (n_fft * 0.25), 1e-6)).astype(np.float32)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / max(1, sr))
    return db, freqs


def wcag_contrast(fg_audio: np.ndarray, bg_audio: np.ndarray) -> Dict[str, Any]:
    """WCAG 2.0 Audio Contrast Analysis (speech foreground >= 20 dB above background)."""
    fg = ensure_2d(fg_audio)
    bg = ensure_2d(bg_audio)
    fg_rms = lin_to_db(float(np.sqrt(np.mean(fg.astype(np.float64) ** 2)))) if fg.size else -96.0
    bg_rms = lin_to_db(float(np.sqrt(np.mean(bg.astype(np.float64) ** 2)))) if bg.size else -96.0
    diff = fg_rms - bg_rms
    return {
        "foreground_db": round(fg_rms, 2),
        "background_db": round(bg_rms, 2),
        "difference_db": round(diff, 2),
        "wcag_pass": diff >= 20.0,
        "result": "WCAG 2.0 Pass (>= 20 dB)" if diff >= 20.0 else "WCAG 2.0 Fail (< 20 dB)",
    }


def find_clipping(audio: np.ndarray, sr: int, start_threshold: int = 3, stop_threshold: int = 3, clip_level: float = 0.999) -> List[Tuple[float, float, str]]:
    a = ensure_2d(audio)
    clipped = np.max(np.abs(a), axis=0) >= clip_level
    labels: List[Tuple[float, float, str]] = []
    n = len(clipped)
    i = 0
    while i < n:
        if clipped[i]:
            j = i
            while j < n and clipped[j]:
                j += 1
            if (j - i) >= start_threshold:
                labels.append((i / sr, j / sr, f"{j - i} of {j - i} clipped"))
            i = j + stop_threshold
        else:
            i += 1
    return labels


def find_beats(audio: np.ndarray, sr: int, threshold_pct: float = 65.0) -> List[Tuple[float, float, str]]:
    """Energy onset flux beat finder returning point labels."""
    a = ensure_2d(audio)
    mono = np.mean(a, axis=0)
    if len(mono) < 1024:
        return []
    hop = max(128, int(sr * 0.01))
    nb = len(mono) // hop
    frames = mono[: nb * hop].reshape(nb, hop)
    energy = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    flux = np.maximum(0.0, np.diff(energy, prepend=energy[0]))
    mx = float(np.max(flux))
    if mx <= 1e-9:
        return []
    thr = mx * (1.0 - np.clip(threshold_pct, 5.0, 95.0) / 100.0)
    min_gap = max(1, int(0.18 * sr / hop))
    labels: List[Tuple[float, float, str]] = []
    last = -min_gap
    for idx in range(1, len(flux) - 1):
        if flux[idx] >= thr and flux[idx] >= flux[idx - 1] and flux[idx] >= flux[idx + 1] and (idx - last) >= min_gap:
            t = (idx * hop) / sr
            labels.append((t, t, "B"))
            last = idx
    return labels


def find_sounds_or_silences(audio: np.ndarray, sr: int, mode: str = "Sounds", threshold_db: float = -30.0, min_duration_s: float = 0.5) -> List[Tuple[float, float, str]]:
    a = ensure_2d(audio)
    mono = np.max(np.abs(a), axis=0)
    if len(mono) == 0:
        return []
    thr = db_to_lin(threshold_db)
    hop = max(64, int(sr * 0.02))
    nb = len(mono) // hop
    if nb == 0:
        return []
    peaks = np.max(mono[: nb * hop].reshape(nb, hop), axis=1)
    cond = (peaks >= thr) if mode == "Sounds" else (peaks < thr)
    min_b = max(1, int(round(min_duration_s * sr / hop)))
    labels: List[Tuple[float, float, str]] = []
    i = 0
    cnt = 1
    while i < nb:
        if cond[i]:
            j = i
            while j < nb and cond[j]:
                j += 1
            if (j - i) >= min_b:
                prefix = "Sound" if mode == "Sounds" else "Silence"
                labels.append(((i * hop) / sr, (j * hop) / sr, f"{prefix} {cnt}"))
                cnt += 1
            i = j
        else:
            i += 1
    return labels


def generate_regular_interval_labels(start_s: float, end_s: float, interval_s: float = 5.0, prefix: str = "Marker ") -> List[Tuple[float, float, str]]:
    step = max(0.05, interval_s)
    labels: List[Tuple[float, float, str]] = []
    t = start_s
    idx = 1
    while t <= end_s + 1e-6 and idx <= 2000:
        labels.append((t, t, f"{prefix}{idx}"))
        t += step
        idx += 1
    return labels


def export_sample_data_text(audio: np.ndarray, sr: int, max_samples: int = 5000, fmt: str = "Plain Text") -> str:
    a = ensure_2d(audio)
    n = min(a.shape[1], max_samples)
    lines = [f"# KinoWave Sample Data Export | SR={sr} Hz | Channels={a.shape[0]} | Samples={n}"]
    if fmt == "CSV":
        header = "Index,Time_s," + ",".join(f"Ch{c + 1}" for c in range(a.shape[0]))
        lines.append(header)
        for i in range(n):
            vals = ",".join(f"{a[c, i]:.6f}" for c in range(a.shape[0]))
            lines.append(f"{i},{i / sr:.6f},{vals}")
    else:
        for i in range(n):
            vals = "\t".join(f"{a[c, i]:.6f}" for c in range(a.shape[0]))
            lines.append(vals)
    return "\n".join(lines) + "\n"


def import_sample_data_text(text: str) -> np.ndarray:
    rows: List[List[float]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.lower().startswith("index"):
            continue
        sep = "," if "," in s else None
        parts = [p.strip() for p in (s.split(sep) if sep else s.split()) if p.strip()]
        try:
            nums = [float(p) for p in parts]
            # If CSV exported with Index,Time,Ch1,... skip first two cols if >2 cols
            if sep == "," and len(nums) >= 3:
                nums = nums[2:]
            rows.append(nums)
        except ValueError:
            continue
    if not rows:
        return np.zeros((1, 0), dtype=np.float32)
    ch = min(2, min(len(r) for r in rows))
    arr = np.array([r[:ch] for r in rows], dtype=np.float32).T
    return np.ascontiguousarray(arr)


# ---------------------------------------------------------------------------
# UNIFIED EFFECT REGISTRY & PRESET MANAGER
# ---------------------------------------------------------------------------
# Parameter spec: (key, label, widget_type, default, min_val, max_val, step_or_choices)
EFFECT_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Volume & Dynamics
    "Amplify": {
        "category": "Volume and Compression",
        "fn": fx_amplify,
        "params": [
            ("gain_db", "Amplification (dB)", "float", 3.0, -50.0, 50.0, 0.5),
            ("allow_clipping", "Allow Clipping", "bool", False, None, None, None),
        ],
    },
    "Normalize": {
        "category": "Volume and Compression",
        "fn": fx_normalize,
        "params": [
            ("target_db", "Peak Amplitude (dB)", "float", -1.0, -60.0, 0.0, 0.5),
            ("remove_dc", "Remove DC Offset", "bool", True, None, None, None),
            ("stereo_independent", "Normalize Stereo Channels Independently", "bool", False, None, None, None),
        ],
    },
    "Loudness Normalization": {
        "category": "Volume and Compression",
        "fn": fx_loudness_normalize,
        "params": [
            ("mode", "Normalize Mode", "choice", "LUFS", None, None, ["LUFS", "RMS"]),
            ("target_db", "Target Loudness (LUFS / dB)", "float", -14.0, -40.0, -1.0, 0.5),
        ],
    },
    "Compressor": {
        "category": "Volume and Compression",
        "fn": fx_compressor,
        "params": [
            ("threshold_db", "Threshold (dB)", "float", -18.0, -60.0, 0.0, 1.0),
            ("noise_floor_db", "Noise Floor (dB)", "float", -50.0, -80.0, -20.0, 1.0),
            ("ratio", "Ratio (:1)", "float", 4.0, 1.0, 20.0, 0.5),
            ("attack_ms", "Attack (ms)", "float", 20.0, 1.0, 500.0, 5.0),
            ("release_ms", "Release (ms)", "float", 250.0, 20.0, 2000.0, 10.0),
            ("makeup_gain", "Make-up Gain to -1 dB", "bool", True, None, None, None),
        ],
    },
    "Limiter": {
        "category": "Volume and Compression",
        "fn": fx_limiter,
        "params": [
            ("limit_type", "Type", "choice", "Soft Limit", None, None, ["Soft Limit", "Hard Limit", "Soft Clip", "Hard Clip"]),
            ("input_gain_left_db", "Input Gain Left / Mono (dB)", "float", 0.0, 0.0, 24.0, 0.5),
            ("input_gain_right_db", "Input Gain Right (dB)", "float", 0.0, 0.0, 24.0, 0.5),
            ("limit_db", "Limit to (dB)", "float", -3.0, -20.0, 0.0, 0.2),
            ("hold_ms", "Hold (ms)", "float", 10.0, 1.0, 50.0, 1.0),
            ("makeup", "Apply Make-up Gain", "bool", False, None, None, None),
        ],
    },
    "Noise Gate": {
        "category": "Volume and Compression",
        "fn": fx_noise_gate,
        "params": [
            ("mode", "Function", "choice", "Gate", None, None, ["Gate", "Analyze Noise Level"]),
            ("stereo_link", "Link Stereo Tracks", "bool", True, None, None, None),
            ("gate_freq_khz", "Gate Frequencies Above (kHz, 0=All)", "float", 0.0, 0.0, 10.0, 0.2),
            ("threshold_db", "Gate Threshold (dB)", "float", -48.0, -96.0, -6.0, 1.0),
            ("level_reduction_db", "Level Reduction (dB)", "float", -12.0, -100.0, 0.0, 1.0),
            ("attack_ms", "Attack (ms)", "float", 10.0, 1.0, 250.0, 1.0),
            ("hold_ms", "Hold (ms)", "float", 50.0, 0.0, 1000.0, 10.0),
            ("decay_ms", "Decay (ms)", "float", 250.0, 10.0, 2000.0, 10.0),
        ],
    },
    "Auto Duck": {
        "category": "Volume and Compression",
        "fn": fx_auto_duck,
        "params": [
            ("duck_db", "Duck Amount (dB)", "float", -12.0, -36.0, 0.0, 1.0),
            ("threshold_db", "Control Threshold (dB)", "float", -30.0, -70.0, 0.0, 1.0),
            ("fade_down_s", "Fade Down Length (s)", "float", 0.25, 0.02, 3.0, 0.05),
            ("fade_up_s", "Fade Up Length (s)", "float", 0.5, 0.02, 3.0, 0.05),
        ],
    },
    "Fade In": {"category": "Fading", "fn": fx_fade_in, "params": []},
    "Fade Out": {"category": "Fading", "fn": fx_fade_out, "params": []},
    "Studio Fade Out": {"category": "Fading", "fn": fx_studio_fade_out, "params": []},
    "Adjustable Fade": {
        "category": "Fading",
        "fn": fx_adjustable_fade,
        "params": [
            ("fade_type", "Fade Type", "choice", "Fade Down", None, None, ["Fade Up", "Fade Down", "S-Curve Up", "S-Curve Down"]),
            ("start_gain_pct", "Start Gain (%)", "float", 100.0, 0.0, 200.0, 5.0),
            ("end_gain_pct", "End Gain (%)", "float", 0.0, 0.0, 200.0, 5.0),
            ("mid_cut", "Mid-Fade Adjust (%)", "float", 0.0, -100.0, 100.0, 5.0),
        ],
    },
    "Crossfade Clips": {"category": "Fading", "fn": fx_crossfade_clips, "params": []},
    "Crossfade Tracks": {
        "category": "Fading",
        "fn": fx_crossfade_tracks,
        "params": [
            ("curve", "Fade Curve", "choice", "Constant Power", None, None, ["Constant Power", "Constant Gain"]),
            ("direction", "Direction", "choice", "Fade Out", None, None, ["Fade Out", "Fade In"]),
        ],
    },
    # EQ & Filters
    "Bass and Treble": {
        "category": "EQ and Filters",
        "fn": fx_bass_treble,
        "params": [
            ("bass_db", "Bass (dB)", "float", 0.0, -30.0, 30.0, 0.5),
            ("treble_db", "Treble (dB)", "float", 0.0, -30.0, 30.0, 0.5),
            ("volume_db", "Volume (dB)", "float", 0.0, -30.0, 30.0, 0.5),
        ],
    },
    "Graphic EQ": {
        "category": "EQ and Filters",
        "fn": fx_graphic_eq,
        "params": [("band_gains_db", "31-Band Gains", "graphic_eq", [0.0] * 31, -20.0, 20.0, 0.5)],
    },
    "Filter Curve EQ": {
        "category": "EQ and Filters",
        "fn": fx_filter_curve_eq,
        "params": [("points", "Curve Points", "filter_curve", [(20.0, 0.0), (250.0, 0.0), (1000.0, 0.0), (4000.0, 0.0), (20000.0, 0.0)], None, None, None)],
    },
    "High-Pass Filter": {
        "category": "EQ and Filters",
        "fn": fx_high_pass,
        "params": [
            ("cutoff_hz", "Frequency (Hz)", "float", 100.0, 10.0, 20000.0, 10.0),
            ("rolloff_db", "Roll-off (dB/oct)", "choice", 12, None, None, [6, 12, 24, 36, 48]),
        ],
    },
    "Low-Pass Filter": {
        "category": "EQ and Filters",
        "fn": fx_low_pass,
        "params": [
            ("cutoff_hz", "Frequency (Hz)", "float", 4000.0, 50.0, 24000.0, 50.0),
            ("rolloff_db", "Roll-off (dB/oct)", "choice", 12, None, None, [6, 12, 24, 36, 48]),
        ],
    },
    "Notch Filter": {
        "category": "EQ and Filters",
        "fn": fx_notch,
        "params": [
            ("freq_hz", "Frequency (Hz)", "float", 60.0, 10.0, 20000.0, 1.0),
            ("q", "Quality Factor (Q)", "float", 5.0, 0.1, 1000.0, 0.5),
        ],
    },
    "Classic Filters": {
        "category": "EQ and Filters",
        "fn": fx_classic_filters,
        "params": [
            ("filter_type", "Filter Type", "choice", "Butterworth", None, None, ["Butterworth", "Chebyshev Type I", "Chebyshev Type II"]),
            ("subtype", "Subtype", "choice", "Lowpass", None, None, ["Lowpass", "Highpass"]),
            ("order", "Order (1-10)", "int", 4, 1, 10, 1),
            ("cutoff_hz", "Cutoff Frequency (Hz)", "float", 1000.0, 10.0, 24000.0, 25.0),
            ("passband_ripple_db", "Passband Ripple (Cheb I, dB)", "float", 1.0, 0.05, 20.0, 0.25),
            ("stopband_atten_db", "Stopband Atten (Cheb II, dB)", "float", 40.0, 10.0, 100.0, 2.0),
        ],
    },
    "Spectral Edit Multi-Tool": {
        "category": "Spectral",
        "fn": fx_spectral_edit_multi,
        "params": [
            ("freq_low", "Low Frequency (Hz)", "float", 300.0, 10.0, 24000.0, 20.0),
            ("freq_high", "High Frequency (Hz)", "float", 3000.0, 20.0, 24000.0, 20.0),
        ],
    },
    "Spectral Edit Parametric EQ": {
        "category": "Spectral",
        "fn": fx_spectral_parametric_eq,
        "params": [
            ("gain_db", "Gain (dB)", "float", -12.0, -30.0, 30.0, 1.0),
            ("freq_low", "Low Frequency (Hz)", "float", 400.0, 10.0, 24000.0, 20.0),
            ("freq_high", "High Frequency (Hz)", "float", 2000.0, 20.0, 24000.0, 20.0),
        ],
    },
    "Spectral Edit Shelves": {
        "category": "Spectral",
        "fn": fx_spectral_shelves,
        "params": [
            ("gain_db", "Gain (dB)", "float", -6.0, -30.0, 30.0, 1.0),
            ("freq_low", "Low Frequency (Hz)", "float", 400.0, 10.0, 24000.0, 20.0),
            ("freq_high", "High Frequency (Hz)", "float", 4000.0, 20.0, 24000.0, 20.0),
            ("shelf_type", "Shelf", "choice", "High Shelf", None, None, ["High Shelf", "Low Shelf"]),
        ],
    },
    # Noise & Repair
    "Noise Reduction": {
        "category": "Noise Removal and Repair",
        "fn": fx_noise_reduction,
        "params": [
            ("reduction_db", "Noise Reduction (dB)", "float", 12.0, 0.0, 48.0, 1.0),
            ("sensitivity", "Sensitivity", "float", 6.0, 0.0, 24.0, 0.5),
            ("freq_smoothing_bands", "Frequency Smoothing (bands)", "int", 3, 0, 12, 1),
        ],
    },
    "Click Removal": {
        "category": "Noise Removal and Repair",
        "fn": fx_click_removal,
        "params": [
            ("threshold", "Threshold", "float", 200.0, 0.0, 900.0, 10.0),
            ("max_spike_width", "Max Spike Width (samples)", "int", 20, 2, 60, 2),
        ],
    },
    "Clip Fix": {
        "category": "Noise Removal and Repair",
        "fn": fx_clip_fix,
        "params": [
            ("threshold_pct", "Threshold of Clipping (%)", "float", 95.0, 50.0, 99.9, 0.5),
            ("reduce_amplitude_db", "Reduce Amplitude to Allow Peaks (dB)", "float", -9.0, -30.0, 0.0, 0.5),
        ],
    },
    "Repair": {"category": "Noise Removal and Repair", "fn": fx_repair, "params": []},
    "Spectral Delete": {
        "category": "Noise Removal and Repair",
        "fn": fx_spectral_delete,
        "params": [
            ("freq_low", "Low Frequency (Hz)", "float", 500.0, 10.0, 24000.0, 20.0),
            ("freq_high", "High Frequency (Hz)", "float", 2000.0, 20.0, 24000.0, 20.0),
        ],
    },
    # Delay & Reverb
    "Echo": {
        "category": "Delay and Reverb",
        "fn": fx_echo,
        "params": [
            ("delay_s", "Delay Time (seconds)", "float", 0.35, 0.01, 5.0, 0.05),
            ("decay", "Decay Factor", "float", 0.45, 0.0, 0.95, 0.05),
        ],
    },
    "Delay": {
        "category": "Delay and Reverb",
        "fn": fx_delay,
        "params": [
            ("delay_type", "Delay Type", "choice", "Regular", None, None, ["Regular", "Bouncing Ball", "Reverse Bouncing Ball"]),
            ("level_db", "Delay Level per Echo (dB)", "float", -6.0, -30.0, 0.0, 1.0),
            ("delay_s", "Delay Time (seconds)", "float", 0.3, 0.02, 5.0, 0.05),
            ("pitch_change", "Pitch Change per Echo (semitones)", "float", 0.0, -12.0, 12.0, 0.5),
            ("num_echoes", "Number of Echoes", "int", 5, 1, 20, 1),
        ],
    },
    "Reverb": {
        "category": "Delay and Reverb",
        "fn": fx_reverb,
        "params": [
            ("room_size", "Room Size (%)", "float", 65.0, 0.0, 100.0, 5.0),
            ("pre_delay_ms", "Pre-delay (ms)", "float", 15.0, 0.0, 200.0, 5.0),
            ("reverberance", "Reverberance (%)", "float", 55.0, 0.0, 100.0, 5.0),
            ("damping", "Damping (%)", "float", 50.0, 0.0, 100.0, 5.0),
            ("tone_low", "Tone Low (%)", "float", 100.0, 0.0, 100.0, 5.0),
            ("tone_high", "Tone High (%)", "float", 100.0, 0.0, 100.0, 5.0),
            ("wet_db", "Wet Gain (dB)", "float", -6.0, -40.0, 12.0, 1.0),
            ("dry_db", "Dry Gain (dB)", "float", 0.0, -40.0, 12.0, 1.0),
            ("stereo_width", "Stereo Width (%)", "float", 100.0, 0.0, 100.0, 5.0),
        ],
    },
    # Distortion & Modulation
    "Distortion": {
        "category": "Distortion and Modulation",
        "fn": fx_distortion,
        "params": [
            ("dist_type", "Distortion Type", "choice", "Soft Overdrive", None, None, ["Hard Clipping", "Soft Clipping", "Soft Overdrive", "Medium Overdrive", "Hard Overdrive", "Cubic Curve (odd harmonics)", "Even Harmonics", "Expand and Compress", "Leveller", "Rectifier Distortion", "Hard Limiter 1413"]),
            ("drive", "Drive / Distortion (%)", "float", 50.0, 0.0, 100.0, 5.0),
            ("threshold_db", "Clipping Threshold (dB)", "float", -6.0, -30.0, 0.0, 1.0),
            ("makeup_db", "Make-up Gain (dB)", "float", 0.0, -18.0, 18.0, 1.0),
        ],
    },
    "Phaser": {
        "category": "Distortion and Modulation",
        "fn": fx_phaser,
        "params": [
            ("stages", "Stages", "int", 4, 2, 24, 2),
            ("dry_wet", "Dry/Wet (0-255)", "int", 128, 0, 255, 8),
            ("lfo_freq_hz", "LFO Frequency (Hz)", "float", 0.4, 0.05, 10.0, 0.1),
            ("start_phase", "LFO Start Phase (deg)", "float", 0.0, 0.0, 360.0, 15.0),
            ("depth", "Depth (0-255)", "int", 100, 0, 255, 10),
            ("feedback", "Feedback (%)", "float", 0.0, -100.0, 100.0, 5.0),
        ],
    },
    "Tremolo": {
        "category": "Distortion and Modulation",
        "fn": fx_tremolo,
        "params": [
            ("waveform", "Waveform", "choice", "Sine", None, None, ["Sine", "Triangle", "Sawtooth", "Square"]),
            ("start_phase", "Start Phase (deg)", "float", 0.0, 0.0, 360.0, 15.0),
            ("wet_pct", "Wet Level (%)", "float", 40.0, 0.0, 100.0, 5.0),
            ("lfo_freq_hz", "Frequency (Hz)", "float", 4.0, 0.1, 40.0, 0.2),
        ],
    },
    "Wahwah": {
        "category": "Distortion and Modulation",
        "fn": fx_wahwah,
        "params": [
            ("lfo_freq_hz", "LFO Frequency (Hz)", "float", 1.5, 0.1, 10.0, 0.1),
            ("start_phase", "LFO Start Phase (deg)", "float", 0.0, 0.0, 360.0, 15.0),
            ("depth", "Depth (%)", "float", 70.0, 0.0, 100.0, 5.0),
            ("resonance", "Resonance", "float", 2.5, 0.5, 10.0, 0.2),
            ("freq_offset_pct", "Wah Freq Offset (%)", "float", 30.0, 0.0, 100.0, 5.0),
            ("output_gain_db", "Output Gain (dB)", "float", -3.0, -24.0, 12.0, 1.0),
        ],
    },
    "Vocoder": {
        "category": "Distortion and Modulation",
        "fn": fx_vocoder,
        "params": [
            ("distance", "Distance (1-120)", "float", 20.0, 1.0, 120.0, 1.0),
            ("output_choice", "Output Choice", "choice", "Both Channels", None, None, ["Both Channels", "Right Only"]),
            ("bands", "Number of Vocoder Bands", "int", 40, 10, 240, 4),
            ("track_vl_pct", "Original Audio Amplitude (%)", "float", 100.0, 0.0, 100.0, 5.0),
            ("noise_vl_pct", "White Noise Amplitude (%)", "float", 0.0, 0.0, 100.0, 5.0),
            ("radar_vl_pct", "Radar Needles Amplitude (%)", "float", 100.0, 0.0, 100.0, 5.0),
            ("radar_freq_hz", "Radar Needles Frequency (Hz)", "float", 30.0, 1.0, 100.0, 1.0),
        ],
    },
    # Pitch & Tempo
    "Change Pitch": {
        "category": "Pitch and Tempo",
        "fn": change_pitch,
        "params": [("semitones", "Semitones (half-steps)", "float", 0.0, -24.0, 24.0, 0.5)],
    },
    "Change Speed and Pitch": {
        "category": "Pitch and Tempo",
        "fn": fx_change_speed,
        "params": [("percent_change", "Percent Change (%)", "float", 0.0, -75.0, 300.0, 5.0)],
    },
    "Change Tempo": {
        "category": "Pitch and Tempo",
        "fn": change_tempo,
        "params": [("percent_change", "Percent Change (%)", "float", 0.0, -75.0, 300.0, 5.0)],
    },
    "Sliding Stretch": {
        "category": "Pitch and Tempo",
        "fn": fx_sliding_stretch,
        "params": [
            ("initial_tempo_pct", "Initial Tempo Change (%)", "float", 0.0, -60.0, 150.0, 5.0),
            ("final_tempo_pct", "Final Tempo Change (%)", "float", 25.0, -60.0, 150.0, 5.0),
            ("initial_pitch_semi", "Initial Pitch Shift (semitones)", "float", 0.0, -12.0, 12.0, 0.5),
            ("final_pitch_semi", "Final Pitch Shift (semitones)", "float", 0.0, -12.0, 12.0, 0.5),
        ],
    },
    "Paulstretch": {
        "category": "Pitch and Tempo",
        "fn": fx_paulstretch,
        "params": [
            ("stretch_factor", "Stretch Factor", "float", 4.0, 1.0, 50.0, 0.5),
            ("time_resolution_s", "Time Resolution (s)", "float", 0.25, 0.05, 2.0, 0.05),
        ],
    },
    # Special
    "Invert": {"category": "Special", "fn": fx_invert, "params": []},
    "Reverse": {"category": "Special", "fn": fx_reverse, "params": []},
    "Repeat": {
        "category": "Special",
        "fn": fx_repeat,
        "params": [("count", "Number of Repeats to Add", "int", 2, 1, 100, 1)],
    },
    "Truncate Silence": {
        "category": "Special",
        "fn": fx_truncate_silence,
        "params": [
            ("threshold_db", "Threshold (dB)", "float", -30.0, -80.0, -6.0, 1.0),
            ("min_duration_s", "Duration (s)", "float", 0.5, 0.05, 10.0, 0.05),
            ("action", "Action", "choice", "Truncate", None, None, ["Truncate", "Compress"]),
            ("truncate_to_s", "Truncate To (s)", "float", 0.15, 0.0, 5.0, 0.05),
            ("compress_pct", "Compress To (%)", "float", 50.0, 5.0, 95.0, 5.0),
        ],
    },
    "Vocal Reduction and Isolation": {
        "category": "Special",
        "fn": fx_vocal_reduction_isolation,
        "params": [
            ("action", "Action", "choice", "Remove Vocals", None, None, ["Remove Vocals", "Isolate Vocals", "Remove Center", "Isolate Center"]),
            ("strength", "Strength", "float", 1.0, 0.1, 3.0, 0.1),
            ("low_cut_hz", "Low Cut for Vocals (Hz)", "float", 120.0, 20.0, 1000.0, 10.0),
            ("high_cut_hz", "High Cut for Vocals (Hz)", "float", 9000.0, 2000.0, 20000.0, 250.0),
        ],
    },
}


def default_effect_params(effect_name: str) -> Dict[str, Any]:
    spec = EFFECT_REGISTRY.get(effect_name)
    if not spec:
        return {}
    return {p[0]: (list(p[3]) if isinstance(p[3], list) else p[3]) for p in spec["params"]}


def run_effect(effect_name: str, audio: np.ndarray, sr: int, params: Optional[Dict[str, Any]] = None, extra_ctx: Optional[Dict[str, Any]] = None) -> np.ndarray:
    # Support external VST3 / VST2 / Audio Unit / LADSPA plugins transparently inside FX racks & pipelines
    if params and "__plugin_path__" in params:
        from .vst_host import process_external_plugin
        return process_external_plugin(
            path=str(params["__plugin_path__"]),
            plugin_type=str(params.get("__plugin_type__", "VST3")),
            audio=audio,
            sr=sr,
            params=params,
            plugin_name=params.get("__plugin_subname__"),
        )
    spec = EFFECT_REGISTRY.get(effect_name)
    if not spec:
        return ensure_2d(audio)
    merged = default_effect_params(effect_name)
    if params:
        merged.update(params)
    if effect_name == "Noise Reduction" and extra_ctx and "noise_profile" in extra_ctx:
        merged["noise_profile"] = extra_ctx["noise_profile"]
    if effect_name == "Auto Duck" and extra_ctx and "control_audio" in extra_ctx:
        merged["control_audio"] = extra_ctx["control_audio"]
    return spec["fn"](audio, sr, **merged)


def apply_effect_chain(audio: np.ndarray, sr: int, slots: List[Any], extra_ctx: Optional[Dict[str, Any]] = None) -> np.ndarray:
    out = ensure_2d(audio)
    for slot in slots:
        if getattr(slot, "enabled", True):
            out = run_effect(slot.effect_name, out, sr, slot.params, extra_ctx=extra_ctx)
    return out


class PresetManager:
    """Save and load named effect presets + factory presets."""

    FACTORY_PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
        "Reverb": {
            "Vocal I": {"room_size": 70.0, "pre_delay_ms": 20.0, "reverberance": 40.0, "damping": 99.0, "tone_low": 100.0, "tone_high": 50.0, "wet_db": -12.0, "dry_db": 0.0, "stereo_width": 70.0},
            "Vocal II": {"room_size": 50.0, "pre_delay_ms": 0.0, "reverberance": 50.0, "damping": 99.0, "tone_low": 50.0, "tone_high": 100.0, "wet_db": -1.0, "dry_db": -1.0, "stereo_width": 70.0},
            "Bathroom": {"room_size": 16.0, "pre_delay_ms": 8.0, "reverberance": 80.0, "damping": 0.0, "tone_low": 0.0, "tone_high": 100.0, "wet_db": -6.0, "dry_db": 0.0, "stereo_width": 100.0},
            "Small Room Bright": {"room_size": 30.0, "pre_delay_ms": 10.0, "reverberance": 50.0, "damping": 50.0, "tone_low": 50.0, "tone_high": 100.0, "wet_db": -1.0, "dry_db": -1.0, "stereo_width": 100.0},
            "Small Room Dark": {"room_size": 30.0, "pre_delay_ms": 10.0, "reverberance": 50.0, "damping": 50.0, "tone_low": 100.0, "tone_high": 0.0, "wet_db": -1.0, "dry_db": -1.0, "stereo_width": 100.0},
            "Medium Room": {"room_size": 75.0, "pre_delay_ms": 10.0, "reverberance": 40.0, "damping": 50.0, "tone_low": 100.0, "tone_high": 70.0, "wet_db": -1.0, "dry_db": -1.0, "stereo_width": 70.0},
            "Large Room": {"room_size": 85.0, "pre_delay_ms": 10.0, "reverberance": 40.0, "damping": 50.0, "tone_low": 100.0, "tone_high": 80.0, "wet_db": 0.0, "dry_db": -6.0, "stereo_width": 90.0},
            "Church Hall": {"room_size": 90.0, "pre_delay_ms": 32.0, "reverberance": 60.0, "damping": 50.0, "tone_low": 100.0, "tone_high": 50.0, "wet_db": 0.0, "dry_db": -12.0, "stereo_width": 100.0},
            "Cathedral": {"room_size": 90.0, "pre_delay_ms": 16.0, "reverberance": 90.0, "damping": 50.0, "tone_low": 100.0, "tone_high": 0.0, "wet_db": 0.0, "dry_db": -20.0, "stereo_width": 100.0},
        },
        "Filter Curve EQ": {
            "AM Radio": {"points": [(20.0, -20.0), (31.0, -20.0), (50.0, -3.0), (100.0, 0.0), (2500.0, 0.0), (4000.0, -0.6), (5000.0, -8.1), (8000.0, -20.0), (20000.0, -20.0)]},
            "Telephone": {"points": [(20.0, -20.0), (200.0, -14.3), (250.0, -7.2), (315.0, -2.2), (500.0, 0.0), (2500.0, 0.0), (4000.0, -4.0), (5000.0, -10.0), (20000.0, -20.0)]},
            "Walkie-talkie": {"points": [(20.0, -20.0), (100.0, -20.0), (101.0, 0.0), (2000.0, 0.0), (2001.0, -20.0), (20000.0, -20.0)]},
            "100Hz Rumble": {"points": [(20.0, -20.0), (50.0, -20.0), (88.0, -6.9), (96.0, -4.5), (109.0, -1.9), (150.0, 0.0), (20000.0, 0.0)]},
            "RIAA": {"points": [(20.0, 19.3), (50.0, 16.9), (100.0, 13.1), (250.0, 6.7), (500.0, 2.6), (1000.0, 0.0), (2500.0, -3.7), (5000.0, -8.2), (10000.0, -13.7), (20000.0, -19.6)]},
            "Bass Boost": {"points": [(20.0, 9.0), (100.0, 9.0), (500.0, 0.0), (20000.0, 0.0)]},
            "Bass Cut": {"points": [(20.0, -20.0), (150.0, -20.0), (300.0, 0.0), (20000.0, 0.0)]},
            "Treble Boost": {"points": [(20.0, 0.0), (4000.0, 0.0), (5000.0, 9.0), (20000.0, 9.0)]},
            "Treble Cut": {"points": [(20.0, 0.0), (6000.0, 0.0), (10000.0, -20.0), (20000.0, -20.0)]},
            "Low rolloff for speech": {"points": [(20.0, -20.0), (60.0, -20.0), (65.0, -20.0), (70.0, -12.0), (80.0, -4.0), (90.0, -1.0), (100.0, 0.0), (20000.0, 0.0)]},
        },
        "Compressor": {
            "Podcast Voice": {"threshold_db": -20.0, "ratio": 3.5, "attack_ms": 12.0, "release_ms": 180.0, "makeup_gain": True},
            "Master Glue": {"threshold_db": -12.0, "ratio": 2.0, "attack_ms": 30.0, "release_ms": 250.0, "makeup_gain": False},
        },
        "Bass and Treble": {
            "Warm Broadcast": {"bass_db": 4.0, "treble_db": 2.5, "volume_db": 0.0},
            "Crisp Air": {"bass_db": -1.0, "treble_db": 5.0, "volume_db": 0.0},
        },
        "Loudness Normalization": {
            "Streaming (-14 LUFS)": {"mode": "LUFS", "target_db": -14.0},
            "Podcast (-16 LUFS)": {"mode": "LUFS", "target_db": -16.0},
            "Broadcast EBU R128 (-23 LUFS)": {"mode": "LUFS", "target_db": -23.0},
        },
    }

    def __init__(self, config_dir: str) -> None:
        self.path = os.path.join(config_dir, "effect_presets.json")
        self.user_presets: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.load()

    def load(self) -> None:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.user_presets = json.load(f)
            except Exception:
                self.user_presets = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.user_presets, f, indent=2)

    def list_presets(self, effect_name: str) -> List[str]:
        names = ["Factory Default"]
        for k in self.FACTORY_PRESETS.get(effect_name, {}):
            names.append(f"Factory: {k}")
        for k in self.user_presets.get(effect_name, {}):
            names.append(k)
        return names

    def get_preset(self, effect_name: str, preset_name: str) -> Dict[str, Any]:
        if preset_name == "Factory Default":
            return default_effect_params(effect_name)
        if preset_name.startswith("Factory: "):
            key = preset_name[len("Factory: "):]
            base = default_effect_params(effect_name)
            base.update(self.FACTORY_PRESETS.get(effect_name, {}).get(key, {}))
            return base
        base = default_effect_params(effect_name)
        base.update(self.user_presets.get(effect_name, {}).get(preset_name, {}))
        return base

    def save_preset(self, effect_name: str, preset_name: str, params: Dict[str, Any]) -> None:
        self.user_presets.setdefault(effect_name, {})[preset_name] = params
        self.save()
