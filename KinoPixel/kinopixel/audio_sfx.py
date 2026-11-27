"""Hardware-accurate GB/GBC/GBA PSG Chiptune SFX & GBA Direct Sound DMA PCM Synthesizer.

Synthesizes authentic GBA/GB Channel 1 (Square + Pitch Sweep + Volume Envelope),
Channel 4 (LFSR Noise), and GBA Direct Sound Channel A 8-bit signed PCM samples
for instant studio preview AND direct ROM DMA playback!
"""
from __future__ import annotations

import math
import threading
from typing import List

import numpy as np

from .models import DirectSoundConfig, SfxPatch

try:
    import sounddevice as _sd
except Exception:
    _sd = None


DUTY_RATIOS = (0.125, 0.25, 0.50, 0.75)
DIRECT_SOUND_PRESETS: List[str] = ["Boss Explosion", "BSL Alarm", "Item Fanfare", "Laser Charge"]


def synthesize_sfx_waveform(patch: SfxPatch, sample_rate: int = 44100) -> np.ndarray:
    """Render an SfxPatch to a mono float32 waveform in [-1.0, 1.0]."""
    dur_s = max(0.04, min(1.5, patch.duration_ms / 1000.0))
    n = int(sample_rate * dur_s)
    t = np.linspace(0.0, dur_s, n, endpoint=False, dtype=np.float64)

    vol0 = max(0, min(15, patch.volume)) / 15.0
    if patch.env_step > 0:
        steps_per_sec = 64.0 / patch.env_step
        env = np.clip(vol0 - np.floor(t * steps_per_sec) / 15.0, 0.0, 1.0)
    else:
        env = np.full(n, vol0, dtype=np.float64)

    if patch.channel == 4:
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
        duty = DUTY_RATIOS[patch.duty & 0x3]
        f0 = float(max(65, min(3500, patch.freq_hz)))
        if patch.sweep_time > 0 and patch.sweep_shift > 0:
            sw_rate = 128.0 / patch.sweep_time
            sw_steps = np.floor(t * sw_rate)
            factor = 1.0 + (2.0 ** (-patch.sweep_shift)) * (1.0 if patch.sweep_dir == 1 else -1.0)
            factor = max(0.5, factor)
            freq = np.clip(f0 / (factor ** sw_steps), 65.0, 5000.0)
        else:
            freq = np.full(n, f0, dtype=np.float64)
        phase = np.cumsum(freq / sample_rate) % 1.0
        raw = np.where(phase < duty, 1.0, -1.0)

    tail = min(200, n // 4)
    if tail > 0:
        env[-tail:] *= np.linspace(1.0, 0.0, tail)
    return (raw * env * 0.35).astype(np.float32)


def generate_direct_sound_pcm(cfg: DirectSoundConfig) -> bytes:
    """Generate authentic 8-bit signed PCM bytes for GBA Direct Sound DMA Channel A (FIFO_A)."""
    sr = max(4096, min(16384, int(cfg.sample_rate)))
    dur_s = 0.45
    # Align length to 16 bytes for clean GBA DMA1 32-bit word transfers
    n = ((int(sr * dur_s) + 15) // 16) * 16
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(2002)

    if cfg.preset == "BSL Alarm":
        # Sci-fi Metroid Fusion bio-station two-tone klaxon
        freq = np.where(((t * 6.0) % 1.0) < 0.5, 660.0, 494.0)
        sig = np.sin(2.0 * math.pi * np.cumsum(freq / sr)) * 0.65 + np.sin(4.0 * math.pi * np.cumsum(freq / sr)) * 0.25
        env = np.exp(-t * 2.5)
    elif cfg.preset == "Item Fanfare":
        # Classic 4-note sci-fi upgrade chime (C5 -> E5 -> G5 -> C6)
        notes = np.select([t < 0.10, t < 0.20, t < 0.30], [523.25, 659.25, 783.99], default=1046.50)
        ph = np.cumsum(notes / sr)
        sig = np.sin(2.0 * math.pi * ph) * 0.6 + np.where((ph % 1.0) < 0.25, 0.35, -0.35)
        env = np.exp(-t * 2.2)
    elif cfg.preset == "Laser Charge":
        freq = 180.0 + 1400.0 * (t / dur_s) ** 2
        ph = np.cumsum(freq / sr)
        sig = np.sin(2.0 * math.pi * ph) * 0.7 + rng.uniform(-0.2, 0.2, size=n)
        env = np.minimum(1.0, t * 8.0) * np.exp(-np.maximum(0.0, t - 0.30) * 10.0)
    else:  # Boss Explosion
        noise = rng.uniform(-1.0, 1.0, size=n)
        # Low-pass rumble + sub-bass drop
        kernel = np.ones(5) / 5.0
        rumble = np.convolve(noise, kernel, mode="same")
        sub = np.sin(2.0 * math.pi * np.cumsum((95.0 * np.exp(-t * 5.0) + 32.0) / sr))
        sig = rumble * 0.75 + sub * 0.65
        env = np.exp(-t * 4.5)

    pcm_f = np.clip(sig * env, -1.0, 1.0)
    pcm_i8 = np.clip(np.round(pcm_f * 118.0), -128, 127).astype(np.int8)
    return pcm_i8.tobytes()


class ChiptuneAudioPlayer:
    """Non-blocking fire-and-forget chiptune PSG & Direct Sound PCM previewer."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self.muted = False
        self._lock = threading.Lock()

    def play_patch(self, patch: SfxPatch) -> None:
        if self.muted or _sd is None:
            return
        wave = synthesize_sfx_waveform(patch, self.sample_rate)
        self._play_array(wave, self.sample_rate)

    def play_direct_sound(self, cfg: DirectSoundConfig) -> None:
        if self.muted or _sd is None or not cfg.enabled:
            return
        raw = np.frombuffer(generate_direct_sound_pcm(cfg), dtype=np.int8).astype(np.float32) / 128.0
        self._play_array(raw * 0.5, cfg.sample_rate)

    def _play_array(self, arr: np.ndarray, sr: int) -> None:
        def _worker() -> None:
            try:
                with self._lock:
                    _sd.play(arr, samplerate=sr, blocking=False)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()
