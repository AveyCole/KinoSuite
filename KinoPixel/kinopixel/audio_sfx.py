"""Hardware-accurate GB/GBC/GBA PSG Chiptune SFX Synthesizer for KinoPixel.

Synthesizes authentic GBA/GB Channel 1 (Square + Pitch Sweep + Volume Envelope)
and Channel 4 (LFSR Noise) waveforms for instant studio preview via numpy + sounddevice.
"""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from .models import SfxPatch

try:
    import sounddevice as _sd
except Exception:
    _sd = None


DUTY_RATIOS = (0.125, 0.25, 0.50, 0.75)


def synthesize_sfx_waveform(patch: SfxPatch, sample_rate: int = 44100) -> np.ndarray:
    """Render an SfxPatch to a mono float32 waveform in [-1.0, 1.0]."""
    dur_s = max(0.04, min(1.5, patch.duration_ms / 1000.0))
    n = int(sample_rate * dur_s)
    t = np.linspace(0.0, dur_s, n, endpoint=False, dtype=np.float64)

    # Hardware-style stepped volume envelope (0..15 fading down at env_step ticks/64Hz)
    vol0 = max(0, min(15, patch.volume)) / 15.0
    if patch.env_step > 0:
        steps_per_sec = 64.0 / patch.env_step
        env = np.clip(vol0 - np.floor(t * steps_per_sec) / 15.0, 0.0, 1.0)
    else:
        env = np.full(n, vol0, dtype=np.float64)

    if patch.channel == 4:
        # Authentic LFSR noise approximation
        div = max(0.5, float(patch.noise_div) if patch.noise_div > 0 else 0.5)
        clock_hz = 524288.0 / div / (2.0 ** (patch.noise_shift + 1))
        step_samples = max(1, int(sample_rate / max(80.0, min(sample_rate, clock_hz))))
        num_steps = (n + step_samples - 1) // step_samples
        lfsr = 0x7FFF
        bits = np.empty(num_steps, dtype=np.float64)
        for i in range(num_steps):
            xor = (lfsr & 1) ^ ((lfsr >> 1) & 1)
            lfsr = (lfsr >> 1) | (xor << 14)
            if patch.noise_short:
                lfsr = (lfsr & ~(1 << 6)) | (xor << 6)
            bits[i] = 1.0 if (lfsr & 1) == 0 else -1.0
        raw = np.repeat(bits, step_samples)[:n]
    else:
        # Channel 1 Square wave + Pitch Sweep
        duty = DUTY_RATIOS[patch.duty & 0x3]
        f0 = float(max(65, min(3500, patch.freq_hz)))
        if patch.sweep_time > 0 and patch.sweep_shift > 0:
            # Sweep rate at 128 Hz / sweep_time
            sw_rate = 128.0 / patch.sweep_time
            sw_steps = np.floor(t * sw_rate)
            # GBA/GB changes period T <- T +/- (T >> shift)
            factor = 1.0 + (2.0 ** (-patch.sweep_shift)) * (1.0 if patch.sweep_dir == 1 else -1.0)
            factor = max(0.5, factor)
            # Frequency is inverse of period
            freq = np.clip(f0 / (factor ** sw_steps), 65.0, 5000.0)
        else:
            freq = np.full(n, f0, dtype=np.float64)
        phase = np.cumsum(freq / sample_rate) % 1.0
        raw = np.where(phase < duty, 1.0, -1.0)

    # Gentle anti-click tail fade
    tail = min(200, n // 4)
    if tail > 0:
        env[-tail:] *= np.linspace(1.0, 0.0, tail)
    return (raw * env * 0.35).astype(np.float32)


class ChiptuneAudioPlayer:
    """Non-blocking fire-and-forget chiptune SFX previewer."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self.muted = False
        self._lock = threading.Lock()

    def play_patch(self, patch: SfxPatch) -> None:
        if self.muted or _sd is None:
            return
        wave = synthesize_sfx_waveform(patch, self.sample_rate)

        def _worker() -> None:
            try:
                with self._lock:
                    _sd.play(wave, samplerate=self.sample_rate, blocking=False)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()
