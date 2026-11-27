"""KinoPixel Sequence Genie — Authentic Generative Chiptune Sequencer, Chord Genie & Euclidean Drum Engine.

Ported and adapted from 404 Sequence Genie (Supermodel REDUX V963 19-scale library,
per-step Lock/Chance/Repeat/Gate, Swing 50-75%, 8 Phrase Slots, Chord Genie 4/8-bar
progressions with strum/arp/bass, and Bjorklund Euclidean drum lanes) for GB/GBC/GBA PSG audio.
"""
from __future__ import annotations

import copy
import math
import random
import threading
import wave
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import sounddevice as _sd
except Exception:
    _sd = None


# ---------------------------------------------------------------------------
# All 19 Authentic Sequence Genie Scales (from genie_scales.inc / REDUX V963)
# Bit i (0..11) set => semitone i above root is in the scale.
# ---------------------------------------------------------------------------
GENIE_SCALES: List[Tuple[str, int]] = [
    ("CHROM", 0xFFF),
    ("MAJ", 0xAB5),
    ("MIN", 0x5AD),
    ("DOR", 0x6AD),
    ("PENTA", 0x295),
    ("PHRYG", 0x5AB),
    ("LYD", 0xAD5),
    ("MIXO", 0x6B5),
    ("LOCR", 0x56B),
    ("BLUES MAJ", 0x699),
    ("BLUES MIN", 0x4E9),
    ("PENTA MIN", 0x4A9),
    ("FOLK", 0x5BB),
    ("JAPAN", 0x1A3),
    ("GAMELAN", 0x18B),
    ("GYPSY", 0x9CD),
    ("ARABIAN", 0x9B3),
    ("FLAMENCO", 0x5B3),
    ("WHOLE", 0x555),
]
SCALE_MASK_BY_NAME: Dict[str, int] = dict(GENIE_SCALES)
NOTE_NAMES: List[str] = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CHORD_STYLES: List[str] = ["Off", "Triad Arp", "7th Arp", "Power 5th", "Block Strum", "Chiptune Fast Arp"]
CHORD_DIRS: List[str] = ["Up", "Down", "Ping-Pong"]
GRID_MODES: List[str] = ["16th Straight", "16th Triplets"]


def scale_intervals(scale_name: str) -> List[int]:
    mask = SCALE_MASK_BY_NAME.get(scale_name, 0xAB5)
    return [i for i in range(12) if (mask >> i) & 1] or [0]


def midi_to_hz(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def midi_to_name(midi_note: int) -> str:
    return f"{NOTE_NAMES[midi_note % 12]}{(midi_note // 12) - 1}"


def midi_to_gba_rate(midi_note: int) -> int:
    """Convert MIDI note to exact GBA/GB 11-bit PSG frequency register value."""
    hz = max(65.0, min(4000.0, midi_to_hz(midi_note)))
    return max(0, min(2047, int(round(2048.0 - 131072.0 / hz))))


def euclidean_pattern(steps: int, hits: int, rotate: int = 0) -> List[bool]:
    """Bjorklund Euclidean rhythm generator (used for Sequence Genie Drum Lanes)."""
    steps = max(1, int(steps))
    hits = max(0, min(steps, int(hits)))
    if hits == 0:
        return [False] * steps
    if hits == steps:
        return [True] * steps
    pat = [((i * hits) % steps) < hits for i in range(steps)]
    rot = int(rotate) % steps
    if rot:
        pat = pat[-rot:] + pat[:-rot]
    return pat


# ---------------------------------------------------------------------------
# Sequence Genie Data Models (serializable inside .kpx)
# ---------------------------------------------------------------------------
@dataclass
class GenieStep:
    active: bool = False
    note: int = 60          # MIDI note (C4=60)
    locked: bool = False    # Retains step across Rerolls & Mutations
    chance: int = 100       # 0..100 % probability
    repeat: int = 1         # 1..4 ratchet triggers per step
    gate: int = 75          # 15..100 % gate length

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": bool(self.active),
            "note": int(self.note),
            "locked": bool(self.locked),
            "chance": int(self.chance),
            "repeat": int(self.repeat),
            "gate": int(self.gate),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GenieStep":
        return cls(
            active=bool(d.get("active", False)),
            note=int(d.get("note", 60)),
            locked=bool(d.get("locked", False)),
            chance=max(0, min(100, int(d.get("chance", 100)))),
            repeat=max(1, min(4, int(d.get("repeat", 1)))),
            gate=max(15, min(100, int(d.get("gate", 75)))),
        )


@dataclass
class DrumLane:
    name: str = "Kick"
    kind: str = "kick"      # kick | snare | hihat | rim
    enabled: bool = True
    hits: int = 4
    rotate: int = 0
    volume: int = 12

    def pattern(self, length: int = 16) -> List[bool]:
        return euclidean_pattern(length, self.hits if self.enabled else 0, self.rotate)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "enabled": bool(self.enabled),
            "hits": int(self.hits),
            "rotate": int(self.rotate),
            "volume": int(self.volume),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DrumLane":
        return cls(
            name=str(d.get("name", "Drum")),
            kind=str(d.get("kind", "kick")),
            enabled=bool(d.get("enabled", True)),
            hits=int(d.get("hits", 4)),
            rotate=int(d.get("rotate", 0)),
            volume=int(d.get("volume", 12)),
        )


@dataclass
class SequenceGenieData:
    enabled_in_rom: bool = True
    bpm: int = 132
    swing: int = 54                 # 50..75% (authentic Sequence Genie range)
    grid_mode: str = "16th Straight"
    root: int = 0                   # 0=C .. 11=B
    scale: str = "PENTA MIN"
    octave: int = 4                 # base octave 3..6
    octave_span: int = 2            # 1..3 octaves
    density: int = 68               # 10..100% step density for rerolls
    lead_duty: int = 1              # 0=12.5%, 1=25%, 2=50%, 3=75%
    chord_style: str = "Triad Arp"
    chord_dir: str = "Up"
    chord_strum_ms: int = 25        # 0..120ms authentic Chord Genie range
    chord_bars: int = 4             # 4 or 8 bar progression
    chord_degrees: List[int] = field(default_factory=lambda: [0, 3, 4, 2])
    bass_enabled: bool = True
    steps: List[GenieStep] = field(default_factory=list)
    drum_lanes: List[DrumLane] = field(default_factory=list)
    phrase_slots: List[Optional[Dict[str, Any]]] = field(default_factory=lambda: [None] * 8)

    def ensure_initialized(self) -> None:
        if len(self.steps) != 16:
            self.steps = [GenieStep() for _ in range(16)]
            reroll_phrase(self, seed=404)
        if not self.drum_lanes:
            self.drum_lanes = [
                DrumLane("Kick", "kick", True, hits=4, rotate=0, volume=13),
                DrumLane("Snare", "snare", True, hits=2, rotate=4, volume=11),
                DrumLane("Hi-Hat", "hihat", True, hits=8, rotate=0, volume=8),
                DrumLane("Perc / Rim", "rim", True, hits=3, rotate=2, volume=9),
            ]
        while len(self.phrase_slots) < 8:
            self.phrase_slots.append(None)

    def save_slot(self, slot_idx: int) -> None:
        if 0 <= slot_idx < 8:
            self.phrase_slots[slot_idx] = {
                "root": self.root,
                "scale": self.scale,
                "bpm": self.bpm,
                "swing": self.swing,
                "chord_degrees": list(self.chord_degrees),
                "steps": [s.to_dict() for s in self.steps],
                "drum_lanes": [d.to_dict() for d in self.drum_lanes],
            }

    def recall_slot(self, slot_idx: int) -> bool:
        if 0 <= slot_idx < 8 and self.phrase_slots[slot_idx]:
            sl = self.phrase_slots[slot_idx]
            self.root = int(sl.get("root", self.root))
            self.scale = str(sl.get("scale", self.scale))
            self.bpm = int(sl.get("bpm", self.bpm))
            self.swing = int(sl.get("swing", self.swing))
            self.chord_degrees = [int(x) for x in sl.get("chord_degrees", self.chord_degrees)]
            self.steps = [GenieStep.from_dict(s) for s in sl.get("steps", [])]
            if sl.get("drum_lanes"):
                self.drum_lanes = [DrumLane.from_dict(d) for d in sl["drum_lanes"]]
            self.ensure_initialized()
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        self.ensure_initialized()
        return {
            "enabled_in_rom": bool(self.enabled_in_rom),
            "bpm": int(self.bpm),
            "swing": int(self.swing),
            "grid_mode": self.grid_mode,
            "root": int(self.root),
            "scale": self.scale,
            "octave": int(self.octave),
            "octave_span": int(self.octave_span),
            "density": int(self.density),
            "lead_duty": int(self.lead_duty),
            "chord_style": self.chord_style,
            "chord_dir": self.chord_dir,
            "chord_strum_ms": int(self.chord_strum_ms),
            "chord_bars": int(self.chord_bars),
            "chord_degrees": list(self.chord_degrees),
            "bass_enabled": bool(self.bass_enabled),
            "steps": [s.to_dict() for s in self.steps],
            "drum_lanes": [d.to_dict() for d in self.drum_lanes],
            "phrase_slots": copy.deepcopy(self.phrase_slots[:8]),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SequenceGenieData":
        obj = cls(
            enabled_in_rom=bool(d.get("enabled_in_rom", True)),
            bpm=max(60, min(220, int(d.get("bpm", 132)))),
            swing=max(50, min(75, int(d.get("swing", 54)))),
            grid_mode=str(d.get("grid_mode", "16th Straight")),
            root=int(d.get("root", 0)) % 12,
            scale=str(d.get("scale", "PENTA MIN")),
            octave=max(2, min(6, int(d.get("octave", 4)))),
            octave_span=max(1, min(3, int(d.get("octave_span", 2)))),
            density=max(10, min(100, int(d.get("density", 68)))),
            lead_duty=int(d.get("lead_duty", 1)) & 3,
            chord_style=str(d.get("chord_style", "Triad Arp")),
            chord_dir=str(d.get("chord_dir", "Up")),
            chord_strum_ms=max(0, min(120, int(d.get("chord_strum_ms", 25)))),
            chord_bars=8 if int(d.get("chord_bars", 4)) == 8 else 4,
            chord_degrees=[int(x) for x in d.get("chord_degrees", [0, 3, 4, 2])],
            bass_enabled=bool(d.get("bass_enabled", True)),
            steps=[GenieStep.from_dict(s) for s in d.get("steps", [])],
            drum_lanes=[DrumLane.from_dict(dl) for dl in d.get("drum_lanes", [])],
            phrase_slots=list(d.get("phrase_slots", [None] * 8)),
        )
        obj.ensure_initialized()
        return obj


# ---------------------------------------------------------------------------
# Generative Sequence Genie Operations (Reroll, Mutate, Prog Reroll)
# ---------------------------------------------------------------------------
def build_scale_pool(root: int, scale_name: str, octave: int, span: int) -> List[int]:
    intervals = scale_intervals(scale_name)
    base_midi = (octave + 1) * 12 + (root % 12)
    notes: List[int] = []
    for oct_off in range(max(1, span)):
        for iv in intervals:
            m = base_midi + oct_off * 12 + iv
            if 36 <= m <= 96:
                notes.append(m)
    return notes or [60]


def reroll_phrase(genie: SequenceGenieData, seed: Optional[int] = None) -> None:
    """Generate a fresh musical retro chiptune phrase, preserving LOCKED steps!"""
    rng = random.Random(seed)
    pool = build_scale_pool(genie.root, genie.scale, genie.octave, genie.octave_span)
    dens = genie.density / 100.0
    cur_idx = 0
    if len(genie.steps) != 16:
        genie.steps = [GenieStep() for _ in range(16)]

    # Melodic contour with strong downbeat anchor + stepwise motion + retro octave leaps
    for i in range(16):
        st = genie.steps[i]
        if st.locked:
            continue
        is_strong = (i % 4 == 0)
        is_offbeat = (i % 2 == 0)
        prob = dens * (1.25 if is_strong else (1.0 if is_offbeat else 0.72))
        st.active = (i == 0) or (rng.random() < min(0.96, prob))
        if st.active:
            if i == 0:
                cur_idx = rng.choice([0, min(2, len(pool) - 1)])
            else:
                jump = rng.choices([-2, -1, 0, 1, 2, 3, -3], weights=[12, 24, 14, 24, 14, 6, 6])[0]
                cur_idx = max(0, min(len(pool) - 1, cur_idx + jump))
            st.note = pool[cur_idx]
            st.chance = 100 if is_strong else rng.choices([100, 85, 70], weights=[72, 18, 10])[0]
            st.repeat = 1 if rng.random() < 0.84 else rng.choice([2, 3])
            st.gate = rng.choice([55, 75, 90])


def mutate_phrase(genie: SequenceGenieData, seed: Optional[int] = None) -> None:
    """Apply a musical Sequence Genie mutation (tweaks 3-5 unlocked steps while preserving hook)."""
    rng = random.Random(seed)
    pool = build_scale_pool(genie.root, genie.scale, genie.octave, genie.octave_span)
    unlocked = [i for i, s in enumerate(genie.steps) if not s.locked]
    if not unlocked:
        return
    k = min(len(unlocked), rng.randint(3, 5))
    for i in rng.sample(unlocked, k):
        st = genie.steps[i]
        r = rng.random()
        if r < 0.28:
            st.active = not st.active
            if st.active and st.note not in pool:
                st.note = rng.choice(pool)
        elif r < 0.78:
            st.active = True
            # Move 1-2 scale degrees from current note
            nearest = min(range(len(pool)), key=lambda idx: abs(pool[idx] - st.note))
            nxt = max(0, min(len(pool) - 1, nearest + rng.choice([-2, -1, 1, 2])))
            st.note = pool[nxt]
        else:
            st.repeat = rng.choice([1, 2, 3])
            st.chance = rng.choice([100, 85, 75])


def reroll_chord_progression(genie: SequenceGenieData, seed: Optional[int] = None) -> None:
    """Chord Genie Prog Reroll — chooses a fresh 4- or 8-bar retro game chord progression."""
    rng = random.Random(seed)
    classic_4 = [
        [0, 3, 4, 0],
        [0, 5, 3, 4],
        [0, 4, 5, 3],
        [0, 2, 3, 4],
        [0, 6, 5, 4],
        [0, 3, 6, 4],
        [0, 5, 2, 4],
    ]
    if genie.chord_bars == 8:
        a = rng.choice(classic_4)
        b = rng.choice(classic_4)
        genie.chord_degrees = a + b
    else:
        genie.chord_degrees = list(rng.choice(classic_4))


def chord_tones_for_bar(genie: SequenceGenieData, bar_idx: int) -> List[int]:
    """Build diatonic chord tones (root, 3rd, 5th, [7th]) for a given bar index."""
    iv = scale_intervals(genie.scale)
    deg = genie.chord_degrees[bar_idx % max(1, len(genie.chord_degrees))] if genie.chord_degrees else 0
    base = (genie.octave) * 12 + (genie.root % 12)  # One octave below lead
    n = len(iv)
    if genie.chord_style == "Power 5th":
        offsets = [0, min(4, n - 1)]
    elif genie.chord_style == "7th Arp":
        offsets = [0, 2, 4, 6]
    else:
        offsets = [0, 2, 4]
    tones = []
    for off in offsets:
        idx = deg + off
        oct_add = (idx // n) * 12
        tones.append(max(36, min(84, base + oct_add + iv[idx % n])))
    return tones


# ---------------------------------------------------------------------------
# Multi-Channel GB/GBA PSG Chiptune Loop Renderer & Live Preview Player
# ---------------------------------------------------------------------------
DUTIES = (0.125, 0.25, 0.50, 0.75)


def _synth_square_note(freq: float, dur_s: float, sr: int, duty: float, vol: float) -> np.ndarray:
    n = max(1, int(dur_s * sr))
    t = np.arange(n, dtype=np.float64) / sr
    wave_sq = np.where(((t * freq) % 1.0) < duty, 1.0, -1.0)
    env = np.exp(-t * 4.5) * vol
    fade = min(40, n // 4)
    if fade > 0:
        env[-fade:] *= np.linspace(1.0, 0.0, fade)
    return (wave_sq * env).astype(np.float32)


def _synth_tri_bass(freq: float, dur_s: float, sr: int, vol: float) -> np.ndarray:
    """GBC/GBA Wave Channel (4-bit quantized triangle bass)."""
    n = max(1, int(dur_s * sr))
    t = np.arange(n, dtype=np.float64) / sr
    ph = (t * freq) % 1.0
    tri = 4.0 * np.abs(ph - 0.5) - 1.0
    # 4-bit hardware wave-RAM quantization!
    tri = np.round(tri * 7.0) / 7.0
    env = np.exp(-t * 3.0) * vol
    return (tri * env).astype(np.float32)


def _synth_drum_hit(kind: str, sr: int, vol: float) -> np.ndarray:
    if kind == "kick":
        dur = 0.095
        n = int(dur * sr)
        t = np.arange(n, dtype=np.float64) / sr
        freq = 165.0 * np.exp(-t * 32.0) + 45.0
        ph = np.cumsum(freq / sr)
        sq = np.where((ph % 1.0) < 0.5, 1.0, -1.0)
        return (sq * np.exp(-t * 28.0) * vol).astype(np.float32)
    elif kind == "snare":
        dur = 0.11
        n = int(dur * sr)
        t = np.arange(n, dtype=np.float64) / sr
        rng = np.random.default_rng(1337)
        noise = rng.choice([-1.0, 1.0], size=n)
        body = np.sin(2.0 * math.pi * 195.0 * t) * np.exp(-t * 35.0)
        return ((noise * 0.7 + body * 0.4) * np.exp(-t * 22.0) * vol).astype(np.float32)
    elif kind == "hihat":
        dur = 0.042
        n = int(dur * sr)
        t = np.arange(n, dtype=np.float64) / sr
        rng = np.random.default_rng(777)
        noise = rng.choice([-1.0, 1.0], size=n)
        return (noise * np.exp(-t * 65.0) * vol * 0.65).astype(np.float32)
    else:  # rim / perc
        dur = 0.05
        n = int(dur * sr)
        t = np.arange(n, dtype=np.float64) / sr
        sq = np.where(((t * 880.0) % 1.0) < 0.25, 1.0, -1.0)
        return (sq * np.exp(-t * 50.0) * vol * 0.75).astype(np.float32)


def render_genie_loop(genie: SequenceGenieData, bars: int = 2, sample_rate: int = 44100, seed: Optional[int] = 42) -> np.ndarray:
    """Render Sequence Genie Lead + Chord Genie + Wave Bass + Euclidean Drums to float32 PCM."""
    genie.ensure_initialized()
    rng = random.Random(seed)
    step_unit = (60.0 / max(60, genie.bpm)) / (6.0 if "Triplet" in genie.grid_mode else 4.0)
    swing_ratio = max(0.50, min(0.75, genie.swing / 100.0))
    pair_s = step_unit * 2.0
    even_dur = pair_s * swing_ratio
    odd_dur = pair_s * (1.0 - swing_ratio)

    # Precompute exact start times & durations for 16 steps per bar
    step_starts = []
    step_durs = []
    cur = 0.0
    for i in range(16):
        step_starts.append(cur)
        d = even_dur if (i % 2 == 0) else odd_dur
        step_durs.append(d)
        cur += d
    bar_s = cur
    total_samples = int(math.ceil(bar_s * bars * sample_rate)) + int(0.15 * sample_rate)
    mix = np.zeros(total_samples, dtype=np.float32)

    def add_at(buf: np.ndarray, start_s: float) -> None:
        i0 = int(start_s * sample_rate)
        if i0 < 0 or i0 >= total_samples:
            return
        end = min(total_samples, i0 + len(buf))
        mix[i0:end] += buf[: end - i0]

    lead_duty = DUTIES[genie.lead_duty & 3]
    drum_pats = [(dl, dl.pattern(16)) for dl in genie.drum_lanes]

    for b in range(bars):
        bar_t0 = b * bar_s
        tones = chord_tones_for_bar(genie, b)
        if genie.chord_dir == "Down":
            arp_seq = list(reversed(tones))
        elif genie.chord_dir == "Ping-Pong" and len(tones) > 2:
            arp_seq = tones + list(reversed(tones[1:-1]))
        else:
            arp_seq = list(tones)

        # 1. Lead Phrase (with Chance, Repeat ratchets, Gate)
        for i, st in enumerate(genie.steps):
            if not st.active:
                continue
            if st.chance < 100 and rng.randint(1, 100) > st.chance:
                continue
            t0 = bar_t0 + step_starts[i]
            sd = step_durs[i]
            reps = max(1, min(4, st.repeat))
            sub_d = sd / reps
            gate_s = max(0.025, sub_d * (st.gate / 100.0))
            hz = midi_to_hz(st.note)
            for r in range(reps):
                add_at(_synth_square_note(hz, gate_s, sample_rate, lead_duty, 0.24), t0 + r * sub_d)

        # 2. Chord Genie Harmony / Arp / Strum
        if genie.chord_style != "Off" and tones:
            if genie.chord_style == "Block Strum":
                strum_s = genie.chord_strum_ms / 1000.0
                for hit_step in (0, 8):
                    ht = bar_t0 + step_starts[hit_step]
                    for ti, mn in enumerate(arp_seq):
                        add_at(_synth_square_note(midi_to_hz(mn), step_unit * 4.5, sample_rate, 0.5, 0.10), ht + ti * strum_s)
            elif genie.chord_style == "Chiptune Fast Arp":
                # Iconic 8-bit rapid 1/32 arpeggio shimmer!
                sub_len = step_unit * 0.5
                total_subs = int(bar_s / sub_len)
                for si in range(total_subs):
                    mn = arp_seq[si % len(arp_seq)]
                    add_at(_synth_square_note(midi_to_hz(mn), sub_len * 0.9, sample_rate, 0.125, 0.11), bar_t0 + si * sub_len)
            else:
                for i in range(0, 16, 2):
                    mn = arp_seq[(i // 2) % len(arp_seq)]
                    add_at(_synth_square_note(midi_to_hz(mn), step_unit * 1.4, sample_rate, 0.25, 0.13), bar_t0 + step_starts[i])

        # 3. Wave Channel Triangle Bass (tracks Chord Genie root!)
        if genie.bass_enabled and tones:
            bass_midi = max(36, tones[0] - 12)
            for i in (0, 4, 6, 8, 12, 14):
                mn = bass_midi + (7 if i in (6, 14) else 0)
                add_at(_synth_tri_bass(midi_to_hz(mn), step_unit * 1.7, sample_rate, 0.24), bar_t0 + step_starts[i])

        # 4. Euclidean Drum Lanes
        for dl, pat in drum_pats:
            if not dl.enabled:
                continue
            v = (dl.volume / 15.0) * 0.26
            hit_buf = _synth_drum_hit(dl.kind, sample_rate, v)
            for i, hit in enumerate(pat):
                if hit:
                    add_at(hit_buf, bar_t0 + step_starts[i])

    # Trim to exact loop length so playback loops seamlessly
    loop_len = int(round(bar_s * bars * sample_rate))
    out = np.tanh(mix[:loop_len] * 1.15).astype(np.float32) * 0.72
    return out


def export_genie_wav(genie: SequenceGenieData, out_path: str, bars: int = 4, sample_rate: int = 44100) -> str:
    """Bounce Sequence Genie chiptune soundtrack directly to a crisp 16-bit WAV (great for KinoWave!)."""
    pcm = render_genie_loop(genie, bars=bars, sample_rate=sample_rate)
    int16 = np.clip(pcm * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16.tobytes())
    return out_path


def compile_genie_to_gba_bgm(genie: SequenceGenieData) -> Tuple[int, List[Tuple[int, int, int, int]]]:
    """Compile Sequence Genie pattern to 3-voice GBA PSG hardware step table!

    Returns:
        (frames_per_step, [(ch2_cnt_l, ch2_cnt_h, ch3_bass_cnt_x, ch4_drum_flag), ...]) for 16 steps.
        - Channel 2: Lead Pulse melody (0x04000068 / 0x6C)
        - Channel 3: 4-bit Wave RAM Bassline (0x04000074, f = 65536 / (2048 - x))
        - Channel 4: Euclidean Drums (0x04000078 / 0x7C)
    """
    genie.ensure_initialized()
    frames_per_step = max(4, min(20, int(round(900.0 / max(60, genie.bpm)))))
    duty_bits = (genie.lead_duty & 3) << 6
    kick_pat = genie.drum_lanes[0].pattern(16) if len(genie.drum_lanes) > 0 else [False] * 16
    snare_pat = genie.drum_lanes[1].pattern(16) if len(genie.drum_lanes) > 1 else [False] * 16
    hat_pat = genie.drum_lanes[2].pattern(16) if len(genie.drum_lanes) > 2 else [False] * 16

    tones = chord_tones_for_bar(genie, 0)
    bass_root = max(36, (tones[0] - 12) if tones else 48)

    steps_out: List[Tuple[int, int, int, int]] = []
    for i in range(16):
        st = genie.steps[i]
        if st.active and st.chance >= 40:
            rate = midi_to_gba_rate(st.note)
            c2_l = (9 << 12) | (2 << 8) | duty_bits
            c2_h = 0x8000 | rate
        else:
            c2_l = 0
            c2_h = 0

        # Channel 3 Wave RAM Bass on classic driving retro steps (0, 4, 6, 8, 12, 14)
        c3_x = 0
        if genie.bass_enabled and i in (0, 4, 6, 8, 12, 14):
            b_midi = bass_root + (7 if i in (6, 14) else (5 if i == 12 else 0))
            b_hz = max(45.0, min(1200.0, midi_to_hz(b_midi)))
            # GBA Wave Channel 3 formula: f = 65536 / (2048 - x) => x = 2048 - 65536 / f
            b_rate = max(0, min(2047, int(round(2048.0 - 65536.0 / b_hz))))
            c3_x = 0x8000 | b_rate

        drum = 2 if (snare_pat[i] or kick_pat[i]) else (1 if hat_pat[i] else 0)
        steps_out.append((c2_l, c2_h, c3_x, drum))
    return frames_per_step, steps_out


class GenieLoopPlayer:
    """Background looping audio player for live Sequence Genie studio preview."""

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self.playing = False
        self._stop_ev = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self, genie: SequenceGenieData) -> None:
        self.stop()
        if _sd is None:
            return
        self.playing = True
        self._stop_ev.clear()
        pcm = render_genie_loop(genie, bars=max(2, min(4, genie.chord_bars)), sample_rate=self.sample_rate, seed=None)

        def _run() -> None:
            try:
                while not self._stop_ev.is_set():
                    _sd.play(pcm, samplerate=self.sample_rate, blocking=False)
                    dur = len(pcm) / float(self.sample_rate)
                    if self._stop_ev.wait(timeout=dur):
                        _sd.stop()
                        break
            except Exception:
                pass
            finally:
                self.playing = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_ev.set()
        self.playing = False
        if _sd is not None:
            try:
                _sd.stop()
            except Exception:
                pass
