"""KinoWave Core Multitrack Project & Track Data Models (32-bit float, up to 384 kHz).

Supports Audio Tracks (mono/stereo, non-destructive clips, trim edges, volume
envelopes, pitch/speed/stretch, real-time FX chains), Label Tracks, Time Tracks,
MIDI Note Tracks, Spectral Selections, Sync-Lock, Snap-To Grid, and Unlimited
Undo/Redo History.
"""
from __future__ import annotations

import copy
import datetime
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

SAMPLE_RATES = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000]
SAMPLE_FORMATS = ["32-bit float", "24-bit PCM", "16-bit PCM"]

CLIP_PALETTE = [
    "#10D9A0",  # KinoWave Emerald
    "#22D3EE",  # Electric Cyan
    "#38BDF8",  # KinoShop Sapphire
    "#818CF8",  # Indigo
    "#A78BFA",  # Violet
    "#F472B6",  # Rose
    "#FB923C",  # Warm Amber
    "#FACC15",  # Gold
]

SPECTROGRAM_COLORMAPS = ["KinoWave", "Magma", "Inferno", "Viridis", "Roseus", "Grayscale"]
SPECTROGRAM_WINDOWS = ["Hann", "Hamming", "Blackman", "Blackman-Harris", "Bartlett", "Rectangular"]
SPECTROGRAM_SCALES = ["Linear", "Logarithmic", "Mel", "Bark", "ERB", "Period"]
SNAP_UNITS = [
    "Seconds",
    "Milliseconds",
    "Samples",
    "Frames (24 fps)",
    "Frames (25 fps)",
    "Frames (30 fps)",
    "Frames (60 fps)",
    "Beats",
    "Bars",
]
TIME_FORMATS = [
    "hh:mm:ss + ms",
    "hh:mm:ss",
    "Seconds",
    "Samples",
    "hh:mm:ss + frames (24)",
    "hh:mm:ss + frames (25)",
    "hh:mm:ss + frames (30)",
    "hh:mm:ss + frames (60)",
    "bars:beats:ticks",
]


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def format_time(
    seconds: float,
    fmt: str = "hh:mm:ss + ms",
    sample_rate: int = 48000,
    bpm: float = 120.0,
    time_sig_num: int = 4,
) -> str:
    """Format a time value (seconds) into any Audacity/DAW precision time format."""
    neg = seconds < 0
    s = abs(float(seconds))
    sign = "-" if neg else ""

    if fmt == "Samples":
        return f"{sign}{int(round(s * sample_rate)):,} smpl"
    if fmt == "Seconds":
        return f"{sign}{s:.4f} s"
    if fmt == "bars:beats:ticks":
        beats_total = s * (bpm / 60.0)
        bar = int(beats_total // max(1, time_sig_num)) + 1
        rem_beats = beats_total - (bar - 1) * max(1, time_sig_num)
        beat = int(rem_beats) + 1
        ticks = int(round((rem_beats - int(rem_beats)) * 480))
        if ticks >= 480:
            ticks = 0
            beat += 1
        return f"{sign}{bar:03d}:{beat:02d}:{ticks:03d}"

    hrs = int(s // 3600)
    mins = int((s % 3600) // 60)
    secs = int(s % 60)
    frac = s - math.floor(s)

    if fmt == "hh:mm:ss":
        return f"{sign}{hrs:02d}:{mins:02d}:{secs:02d}"
    if fmt.startswith("hh:mm:ss + frames"):
        fps = 30
        if "(24)" in fmt:
            fps = 24
        elif "(25)" in fmt:
            fps = 25
        elif "(60)" in fmt:
            fps = 60
        fr = int(round(frac * fps)) % fps
        return f"{sign}{hrs:02d}:{mins:02d}:{secs:02d}:{fr:02d}"
    ms = int(round(frac * 1000))
    if ms >= 1000:
        ms = 0
        secs += 1
    return f"{sign}{hrs:02d}:{mins:02d}:{secs:02d}.{ms:03d}"


def parse_time(
    text: str,
    fmt: str = "hh:mm:ss + ms",
    sample_rate: int = 48000,
    bpm: float = 120.0,
    time_sig_num: int = 4,
) -> float:
    """Parse a user-entered time string back to seconds."""
    raw = text.strip().replace(",", "").replace("smpl", "").replace("s", "").strip()
    if not raw:
        return 0.0
    try:
        if fmt == "Samples":
            return max(0.0, float(raw) / max(1, sample_rate))
        if fmt == "Seconds" or (":" not in raw):
            return max(0.0, float(raw))
        if fmt == "bars:beats:ticks":
            parts = raw.split(":")
            bar = max(1, int(parts[0]))
            beat = max(1, int(parts[1])) if len(parts) > 1 else 1
            tick = int(parts[2]) if len(parts) > 2 else 0
            total_beats = (bar - 1) * max(1, time_sig_num) + (beat - 1) + tick / 480.0
            return max(0.0, total_beats * (60.0 / max(1.0, bpm)))
        parts = raw.split(":")
        if len(parts) == 4:
            fps = 30
            if "(24)" in fmt:
                fps = 24
            elif "(25)" in fmt:
                fps = 25
            elif "(60)" in fmt:
                fps = 60
            return max(0.0, int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) + int(parts[3]) / fps)
        if len(parts) == 3:
            return max(0.0, int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2]))
        if len(parts) == 2:
            return max(0.0, int(parts[0]) * 60 + float(parts[1]))
    except Exception:
        return 0.0
    return 0.0


def snap_time_value(
    t: float,
    snap_mode: str,
    snap_unit: str,
    sample_rate: int = 48000,
    bpm: float = 120.0,
    time_sig_num: int = 4,
) -> float:
    """Snap a timestamp in seconds according to current snap mode and unit."""
    if snap_mode == "Off" or t <= 0:
        return max(0.0, t)
    step = 1.0
    if snap_unit == "Seconds":
        step = 1.0
    elif snap_unit == "Milliseconds":
        step = 0.001
    elif snap_unit == "Samples":
        step = 1.0 / max(1, sample_rate)
    elif snap_unit == "Frames (24 fps)":
        step = 1.0 / 24.0
    elif snap_unit == "Frames (25 fps)":
        step = 1.0 / 25.0
    elif snap_unit == "Frames (30 fps)":
        step = 1.0 / 30.0
    elif snap_unit == "Frames (60 fps)":
        step = 1.0 / 60.0
    elif snap_unit == "Beats":
        step = 60.0 / max(1.0, bpm)
    elif snap_unit == "Bars":
        step = (60.0 / max(1.0, bpm)) * max(1, time_sig_num)

    if snap_mode == "Prior":
        return max(0.0, math.floor(t / step) * step)
    return max(0.0, round(t / step) * step)


@dataclass
class EffectSlot:
    """Non-destructive real-time effect slot (stackable per track or on master bus)."""
    effect_name: str
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    preset_name: str = "Default"
    uid: str = field(default_factory=_uid)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "effect_name": self.effect_name,
            "enabled": self.enabled,
            "params": copy.deepcopy(self.params),
            "preset_name": self.preset_name,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EffectSlot":
        return cls(
            uid=d.get("uid", _uid()),
            effect_name=d["effect_name"],
            enabled=bool(d.get("enabled", True)),
            params=copy.deepcopy(d.get("params", {})),
            preset_name=d.get("preset_name", "Default"),
        )


@dataclass
class SpectrogramConfig:
    window_type: str = "Hann"
    window_size: int = 1024
    color_scheme: str = "KinoWave"
    freq_scale: str = "Linear"
    min_freq: float = 20.0
    max_freq: float = 20000.0
    gain_db: float = 20.0
    range_db: float = 80.0
    zero_padding: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SpectrogramConfig":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class AudioClip:
    """Non-destructive audio clip with backing 32-bit float samples, edge trims,
    stretch/pitch/speed properties, color, and volume envelope control points."""
    samples: np.ndarray  # shape (channels, N), dtype float32
    sample_rate: int = 48000
    start_time: float = 0.0
    name: str = "Audio Clip"
    color: str = "#10D9A0"
    trim_start: int = 0  # non-destructive sample offset from backing start
    trim_end: int = 0    # non-destructive sample offset trimmed from backing end
    pitch_semitones: float = 0.0
    speed_ratio: float = 1.0
    stretch_ratio: float = 1.0
    envelope_points: List[Tuple[float, float]] = field(default_factory=list)  # (rel_sec, gain 0..2)
    uid: str = field(default_factory=_uid)

    def __post_init__(self) -> None:
        arr = np.asarray(self.samples, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr[None, :]
        self.samples = np.ascontiguousarray(arr, dtype=np.float32)
        self.trim_start = max(0, min(self.trim_start, max(0, self.samples.shape[1] - 1)))
        self.trim_end = max(0, min(self.trim_end, max(0, self.samples.shape[1] - self.trim_start - 1)))

    @property
    def channels(self) -> int:
        return int(self.samples.shape[0])

    @property
    def raw_length(self) -> int:
        return int(self.samples.shape[1])

    @property
    def visible_sample_count(self) -> int:
        return max(0, self.samples.shape[1] - self.trim_start - self.trim_end)

    @property
    def duration(self) -> float:
        base = self.visible_sample_count / max(1, self.sample_rate)
        return base * max(0.05, self.stretch_ratio) / max(0.05, self.speed_ratio)

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    def visible_samples(self) -> np.ndarray:
        end_idx = self.samples.shape[1] - self.trim_end
        if end_idx <= self.trim_start:
            return np.zeros((self.channels, 0), dtype=np.float32)
        return self.samples[:, self.trim_start:end_idx]

    def envelope_gain_curve(self, num_samples: int) -> np.ndarray:
        """Return per-sample linear gain curve from envelope control points."""
        if not self.envelope_points or num_samples <= 0:
            return np.ones(num_samples, dtype=np.float32)
        pts = sorted(self.envelope_points, key=lambda p: p[0])
        xs = np.array([p[0] for p in pts], dtype=np.float64)
        ys = np.array([np.clip(p[1], 0.0, 2.0) for p in pts], dtype=np.float64)
        t = np.linspace(0.0, max(1e-9, self.duration), num_samples, dtype=np.float64)
        return np.interp(t, xs, ys).astype(np.float32)

    def render_audio(self, target_sr: Optional[int] = None) -> np.ndarray:
        """Render clip samples with trim, stretch/speed/pitch, and volume envelope applied."""
        from .dsp import change_pitch, change_tempo, resample_audio

        vis = self.visible_samples().copy()
        if vis.shape[1] == 0:
            return vis

        sr = self.sample_rate
        if abs(self.speed_ratio - 1.0) > 1e-4:
            new_len = max(1, int(round(vis.shape[1] / max(0.05, self.speed_ratio))))
            idx = np.linspace(0, vis.shape[1] - 1, new_len, dtype=np.float64)
            out = np.empty((vis.shape[0], new_len), dtype=np.float32)
            x_old = np.arange(vis.shape[1], dtype=np.float64)
            for c in range(vis.shape[0]):
                out[c] = np.interp(idx, x_old, vis[c]).astype(np.float32)
            vis = out

        if abs(self.stretch_ratio - 1.0) > 1e-4:
            pct = (1.0 / max(0.05, self.stretch_ratio) - 1.0) * 100.0
            vis = change_tempo(vis, sr, pct)

        if abs(self.pitch_semitones) > 1e-3:
            vis = change_pitch(vis, sr, self.pitch_semitones)

        if self.envelope_points:
            env = self.envelope_gain_curve(vis.shape[1])
            vis = vis * env[None, :]

        if target_sr is not None and target_sr != sr:
            vis = resample_audio(vis, sr, target_sr)

        return np.ascontiguousarray(vis, dtype=np.float32)

    def clone(self) -> "AudioClip":
        return AudioClip(
            samples=self.samples.copy(),
            sample_rate=self.sample_rate,
            start_time=self.start_time,
            name=self.name,
            color=self.color,
            trim_start=self.trim_start,
            trim_end=self.trim_end,
            pitch_semitones=self.pitch_semitones,
            speed_ratio=self.speed_ratio,
            stretch_ratio=self.stretch_ratio,
            envelope_points=list(self.envelope_points),
        )


@dataclass
class BaseTrack:
    name: str
    kind: str = "audio"  # audio | label | time | note
    height: int = 136
    collapsed: bool = False
    selected: bool = False
    sync_lock: bool = True
    uid: str = field(default_factory=_uid)

    @property
    def display_height(self) -> int:
        return 42 if self.collapsed else self.height


@dataclass
class AudioTrack(BaseTrack):
    kind: str = "audio"
    channels: int = 2  # 1=mono, 2=stereo
    sample_rate: int = 48000
    sample_format: str = "32-bit float"
    gain_db: float = 0.0
    pan: float = 0.0  # -1.0 (L) to +1.0 (R)
    mute: bool = False
    solo: bool = False
    view_mode: str = "Waveform"  # Waveform | Waveform (dB) | Spectrogram | Split View
    show_clipping: bool = True
    spectrogram: SpectrogramConfig = field(default_factory=SpectrogramConfig)
    clips: List[AudioClip] = field(default_factory=list)
    realtime_effects: List[EffectSlot] = field(default_factory=list)
    color: str = "#10D9A0"

    def duration(self) -> float:
        if not self.clips:
            return 0.0
        return max(c.end_time for c in self.clips)

    def start_time(self) -> float:
        if not self.clips:
            return 0.0
        return min(c.start_time for c in self.clips)

    def ensure_channels(self, arr: np.ndarray) -> np.ndarray:
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr[None, :]
        if arr.shape[0] == self.channels:
            return arr
        if self.channels == 1:
            return np.mean(arr, axis=0, keepdims=True).astype(np.float32)
        if arr.shape[0] == 1 and self.channels == 2:
            return np.vstack([arr, arr]).astype(np.float32)
        return arr[: self.channels]

    def render_range(
        self,
        start_s: float,
        end_s: float,
        target_sr: int,
        apply_realtime_fx: bool = True,
        apply_gain_pan: bool = False,
    ) -> np.ndarray:
        """Mix all clips in this track over [start_s, end_s] into float32 (channels, N)."""
        n_out = max(0, int(round((end_s - start_s) * target_sr)))
        out_ch = 2 if apply_gain_pan else self.channels
        buf = np.zeros((self.channels, n_out), dtype=np.float32)
        if n_out == 0:
            return np.zeros((out_ch, 0), dtype=np.float32)

        for clip in self.clips:
            if clip.end_time <= start_s or clip.start_time >= end_s:
                continue
            rendered = self.ensure_channels(clip.render_audio(target_sr=target_sr))
            c_start_idx = int(round((clip.start_time - start_s) * target_sr))
            src_start = max(0, -c_start_idx)
            dst_start = max(0, c_start_idx)
            copy_len = min(rendered.shape[1] - src_start, n_out - dst_start)
            if copy_len > 0:
                buf[:, dst_start:dst_start + copy_len] += rendered[:, src_start:src_start + copy_len]

        if apply_realtime_fx and self.realtime_effects:
            from .dsp import apply_effect_chain
            buf = apply_effect_chain(buf, target_sr, self.realtime_effects)

        if apply_gain_pan:
            gain = 10.0 ** (self.gain_db / 20.0)
            buf = buf * gain
            pan = float(np.clip(self.pan, -1.0, 1.0))
            # Constant-power pan law
            angle = (pan + 1.0) * (math.pi / 4.0)
            l_gain = math.cos(angle) * math.sqrt(2.0) if self.channels == 1 else (1.0 if pan <= 0 else 1.0 - pan)
            r_gain = math.sin(angle) * math.sqrt(2.0) if self.channels == 1 else (1.0 if pan >= 0 else 1.0 + pan)
            if self.channels == 1:
                stereo = np.vstack([buf[0] * l_gain, buf[0] * r_gain]).astype(np.float32)
            else:
                stereo = np.vstack([buf[0] * l_gain, buf[1] * r_gain]).astype(np.float32)
            return stereo
        return buf

    def flatten_to_single_array(self, target_sr: Optional[int] = None) -> Tuple[np.ndarray, float]:
        """Render the track from its earliest clip to its latest clip."""
        sr = target_sr or self.sample_rate
        if not self.clips:
            return np.zeros((self.channels, 0), dtype=np.float32), 0.0
        t0 = max(0.0, self.start_time())
        t1 = self.duration()
        return self.render_range(t0, t1, sr, apply_realtime_fx=False, apply_gain_pan=False), t0

    def clone(self) -> "AudioTrack":
        return AudioTrack(
            name=self.name,
            kind="audio",
            height=self.height,
            collapsed=self.collapsed,
            selected=self.selected,
            sync_lock=self.sync_lock,
            channels=self.channels,
            sample_rate=self.sample_rate,
            sample_format=self.sample_format,
            gain_db=self.gain_db,
            pan=self.pan,
            mute=self.mute,
            solo=self.solo,
            view_mode=self.view_mode,
            show_clipping=self.show_clipping,
            spectrogram=SpectrogramConfig.from_dict(self.spectrogram.to_dict()),
            clips=[c.clone() for c in self.clips],
            realtime_effects=[EffectSlot.from_dict(e.to_dict()) for e in self.realtime_effects],
            color=self.color,
            uid=self.uid,
        )


@dataclass
class LabelItem:
    start: float
    end: float
    text: str = "Label"
    uid: str = field(default_factory=_uid)

    def to_dict(self) -> Dict[str, Any]:
        return {"uid": self.uid, "start": self.start, "end": self.end, "text": self.text}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LabelItem":
        return cls(uid=d.get("uid", _uid()), start=float(d["start"]), end=float(d["end"]), text=str(d.get("text", "")))


@dataclass
class LabelTrack(BaseTrack):
    kind: str = "label"
    height: int = 74
    labels: List[LabelItem] = field(default_factory=list)

    def duration(self) -> float:
        if not self.labels:
            return 0.0
        return max(max(lb.start, lb.end) for lb in self.labels)

    def clone(self) -> "LabelTrack":
        return LabelTrack(
            name=self.name,
            kind="label",
            height=self.height,
            collapsed=self.collapsed,
            selected=self.selected,
            sync_lock=self.sync_lock,
            labels=[LabelItem(lb.start, lb.end, lb.text, lb.uid) for lb in self.labels],
            uid=self.uid,
        )


@dataclass
class TimeTrack(BaseTrack):
    """Controls variable playback speed over time (multiplier range e.g. 0.5x to 2.0x)."""
    kind: str = "time"
    height: int = 86
    min_speed: float = 0.5
    max_speed: float = 2.0
    points: List[Tuple[float, float]] = field(default_factory=lambda: [(0.0, 1.0), (10.0, 1.0)])

    def speed_at(self, t: float) -> float:
        if not self.points:
            return 1.0
        pts = sorted(self.points, key=lambda p: p[0])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return float(np.clip(np.interp(t, xs, ys), self.min_speed, self.max_speed))

    def duration(self) -> float:
        return max((p[0] for p in self.points), default=0.0)

    def clone(self) -> "TimeTrack":
        return TimeTrack(
            name=self.name,
            kind="time",
            height=self.height,
            collapsed=self.collapsed,
            selected=self.selected,
            sync_lock=self.sync_lock,
            min_speed=self.min_speed,
            max_speed=self.max_speed,
            points=list(self.points),
            uid=self.uid,
        )


@dataclass
class MidiNote:
    start: float
    end: float
    pitch: int       # MIDI note 0..127 (60 = C4)
    velocity: int = 100
    channel: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "pitch": self.pitch,
            "velocity": self.velocity,
            "channel": self.channel,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MidiNote":
        return cls(
            start=float(d["start"]),
            end=float(d["end"]),
            pitch=int(d["pitch"]),
            velocity=int(d.get("velocity", 100)),
            channel=int(d.get("channel", 0)),
        )


@dataclass
class NoteTrack(BaseTrack):
    """MIDI Note track imported from or exported to Standard MIDI Files (.mid)."""
    kind: str = "note"
    height: int = 132
    notes: List[MidiNote] = field(default_factory=list)
    mute: bool = False
    solo: bool = False
    gain_db: float = -6.0

    def duration(self) -> float:
        if not self.notes:
            return 0.0
        return max(n.end for n in self.notes)

    def synthesize_audio(self, start_s: float, end_s: float, sample_rate: int) -> np.ndarray:
        """Synthesize lightweight polyphonic synth audio for MIDI note playback."""
        n_out = max(0, int(round((end_s - start_s) * sample_rate)))
        buf = np.zeros((2, n_out), dtype=np.float32)
        if n_out == 0 or not self.notes:
            return buf
        gain = 10.0 ** (self.gain_db / 20.0) * 0.18
        for note in self.notes:
            if note.end <= start_s or note.start >= end_s:
                continue
            s0 = max(start_s, note.start)
            s1 = min(end_s, note.end)
            i0 = int(round((s0 - start_s) * sample_rate))
            i1 = min(n_out, int(round((s1 - start_s) * sample_rate)))
            if i1 <= i0:
                continue
            t = np.arange(i1 - i0, dtype=np.float32) / sample_rate + (s0 - note.start)
            freq = 440.0 * (2.0 ** ((note.pitch - 69) / 12.0))
            amp = (note.velocity / 127.0) * gain
            # Warm electric-piano harmonic blend + ADSR decay
            dur = max(0.02, note.end - note.start)
            env = np.minimum(1.0, t / 0.008) * np.exp(-t * (2.2 / max(0.25, dur)))
            rel = np.clip((note.end - (s0 + np.arange(i1 - i0, dtype=np.float32) / sample_rate)) / 0.02, 0.0, 1.0)
            wave = (
                0.70 * np.sin(2.0 * np.pi * freq * t)
                + 0.22 * np.sin(4.0 * np.pi * freq * t)
                + 0.08 * np.sin(6.0 * np.pi * freq * t)
            ) * env * rel * amp
            buf[0, i0:i1] += wave
            buf[1, i0:i1] += wave
        return buf

    def clone(self) -> "NoteTrack":
        return NoteTrack(
            name=self.name,
            kind="note",
            height=self.height,
            collapsed=self.collapsed,
            selected=self.selected,
            sync_lock=self.sync_lock,
            notes=[MidiNote(n.start, n.end, n.pitch, n.velocity, n.channel) for n in self.notes],
            mute=self.mute,
            solo=self.solo,
            gain_db=self.gain_db,
            uid=self.uid,
        )


@dataclass
class ProjectMetadata:
    artist: str = ""
    title: str = ""
    album: str = ""
    track_number: str = ""
    year: str = ""
    genre: str = ""
    comments: str = ""
    custom_tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artist": self.artist,
            "title": self.title,
            "album": self.album,
            "track_number": self.track_number,
            "year": self.year,
            "genre": self.genre,
            "comments": self.comments,
            "custom_tags": dict(self.custom_tags),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProjectMetadata":
        return cls(
            artist=str(d.get("artist", "")),
            title=str(d.get("title", "")),
            album=str(d.get("album", "")),
            track_number=str(d.get("track_number", "")),
            year=str(d.get("year", "")),
            genre=str(d.get("genre", "")),
            comments=str(d.get("comments", "")),
            custom_tags=dict(d.get("custom_tags", {})),
        )


@dataclass
class HistoryState:
    description: str
    timestamp: str
    tracks: List[BaseTrack]
    master_effects: List[EffectSlot]
    sel_start: float
    sel_end: float
    spectral_low_hz: Optional[float]
    spectral_high_hz: Optional[float]
    size_kb: float = 0.0


class KinoWaveProject:
    """Complete multitrack audio project with unlimited undo/redo, editing ops,
    selection/spectral selection, sync-lock, beats/tempo grid, and master FX."""

    def __init__(self, name: str = "Untitled.kwp", sample_rate: int = 48000) -> None:
        self.name: str = name
        self.file_path: Optional[str] = None
        self.sample_rate: int = sample_rate
        self.sample_format: str = "32-bit float"
        self.tracks: List[BaseTrack] = []
        self.master_effects: List[EffectSlot] = []
        self.master_gain_db: float = 0.0
        self.metadata: ProjectMetadata = ProjectMetadata(title=name.replace(".kwp", ""))

        # Selection & Cursor
        self.cursor_time: float = 0.0
        self.sel_start: float = 0.0
        self.sel_end: float = 0.0
        self.spectral_low_hz: Optional[float] = None
        self.spectral_high_hz: Optional[float] = None
        self.stored_cursor: Optional[float] = None
        self.stored_selection: Optional[Tuple[float, float]] = None

        # Loop & Playback
        self.loop_enabled: bool = False
        self.loop_start: float = 0.0
        self.loop_end: float = 4.0
        self.playback_speed: float = 1.0

        # Grid & Tempo
        self.show_beats_grid: bool = False
        self.bpm: float = 120.0
        self.time_sig_num: int = 4
        self.time_sig_den: int = 4
        self.snap_mode: str = "Off"  # Off | Nearest | Prior
        self.snap_unit: str = "Seconds"
        self.time_format: str = "hh:mm:ss + ms"

        # Sync-Lock
        self.sync_lock: bool = False

        # Noise Profile (for 2-step Noise Reduction)
        self.noise_profile: Optional[np.ndarray] = None
        self.noise_profile_sr: int = 48000

        # Unlimited Undo/Redo History
        self.history: List[HistoryState] = []
        self.history_index: int = -1
        self.dirty: bool = False
        self._color_idx: int = 0

    def next_clip_color(self) -> str:
        c = CLIP_PALETTE[self._color_idx % len(CLIP_PALETTE)]
        self._color_idx += 1
        return c

    # ---- History ----
    def _estimate_size_kb(self, tracks: List[BaseTrack]) -> float:
        total_bytes = 0
        for t in tracks:
            if isinstance(t, AudioTrack):
                for c in t.clips:
                    total_bytes += c.samples.nbytes
        return round(total_bytes / 1024.0, 1)

    def push_history(self, description: str) -> None:
        if self.history_index < len(self.history) - 1:
            self.history = self.history[: self.history_index + 1]
        snap_tracks = [t.clone() for t in self.tracks]
        snap_fx = [EffectSlot.from_dict(e.to_dict()) for e in self.master_effects]
        st = HistoryState(
            description=description,
            timestamp=datetime.datetime.now().strftime("%H:%M:%S"),
            tracks=snap_tracks,
            master_effects=snap_fx,
            sel_start=self.sel_start,
            sel_end=self.sel_end,
            spectral_low_hz=self.spectral_low_hz,
            spectral_high_hz=self.spectral_high_hz,
            size_kb=self._estimate_size_kb(snap_tracks),
        )
        self.history.append(st)
        self.history_index = len(self.history) - 1
        self.dirty = True

    def can_undo(self) -> bool:
        return self.history_index > 0

    def can_redo(self) -> bool:
        return 0 <= self.history_index < len(self.history) - 1

    def restore_history(self, idx: int) -> bool:
        if idx < 0 or idx >= len(self.history):
            return False
        st = self.history[idx]
        self.tracks = [t.clone() for t in st.tracks]
        self.master_effects = [EffectSlot.from_dict(e.to_dict()) for e in st.master_effects]
        self.sel_start = st.sel_start
        self.sel_end = st.sel_end
        self.cursor_time = st.sel_start
        self.spectral_low_hz = st.spectral_low_hz
        self.spectral_high_hz = st.spectral_high_hz
        self.history_index = idx
        self.dirty = True
        return True

    def undo(self) -> bool:
        if self.can_undo():
            return self.restore_history(self.history_index - 1)
        return False

    def redo(self) -> bool:
        if self.can_redo():
            return self.restore_history(self.history_index + 1)
        return False

    def discard_history(self, levels_to_discard: int) -> int:
        """Discard oldest undo levels up to current history_index."""
        discardable = max(0, min(levels_to_discard, self.history_index))
        if discardable > 0:
            self.history = self.history[discardable:]
            self.history_index -= discardable
        return discardable

    # ---- Queries ----
    def duration(self) -> float:
        d = 0.0
        for t in self.tracks:
            d = max(d, t.duration())
        return d

    def audio_tracks(self) -> List[AudioTrack]:
        return [t for t in self.tracks if isinstance(t, AudioTrack)]

    def label_tracks(self) -> List[LabelTrack]:
        return [t for t in self.tracks if isinstance(t, LabelTrack)]

    def time_track(self) -> Optional[TimeTrack]:
        for t in self.tracks:
            if isinstance(t, TimeTrack):
                return t
        return None

    def selected_tracks(self) -> List[BaseTrack]:
        sel = [t for t in self.tracks if t.selected]
        return sel if sel else list(self.tracks)

    def selected_audio_tracks(self) -> List[AudioTrack]:
        sel = [t for t in self.tracks if isinstance(t, AudioTrack) and t.selected]
        return sel if sel else self.audio_tracks()

    def has_selection(self) -> bool:
        return abs(self.sel_end - self.sel_start) > 1e-6

    def selection_bounds(self) -> Tuple[float, float]:
        a, b = min(self.sel_start, self.sel_end), max(self.sel_start, self.sel_end)
        if b - a <= 1e-6:
            return 0.0, self.duration()
        return a, b

    def set_selection(self, start: float, end: float, snap: bool = False) -> None:
        if snap and self.snap_mode != "Off":
            start = snap_time_value(start, self.snap_mode, self.snap_unit, self.sample_rate, self.bpm, self.time_sig_num)
            end = snap_time_value(end, self.snap_mode, self.snap_unit, self.sample_rate, self.bpm, self.time_sig_num)
        self.sel_start = max(0.0, min(start, end))
        self.sel_end = max(0.0, max(start, end))
        self.cursor_time = self.sel_start

    # ---- Track Management ----
    def add_audio_track(self, channels: int = 2, name: Optional[str] = None, sample_rate: Optional[int] = None) -> AudioTrack:
        idx = len(self.audio_tracks()) + 1
        kind_lbl = "Stereo" if channels == 2 else "Mono"
        tr = AudioTrack(
            name=name or f"{kind_lbl} Track {idx}",
            channels=channels,
            sample_rate=sample_rate or self.sample_rate,
            sample_format=self.sample_format,
            color=self.next_clip_color(),
            selected=True,
        )
        self.tracks.append(tr)
        return tr

    def add_label_track(self, name: Optional[str] = None) -> LabelTrack:
        idx = len(self.label_tracks()) + 1
        tr = LabelTrack(name=name or f"Label Track {idx}")
        self.tracks.append(tr)
        return tr

    def add_time_track(self, name: str = "Time Track") -> TimeTrack:
        existing = self.time_track()
        if existing is not None:
            return existing
        dur = max(10.0, self.duration())
        tr = TimeTrack(name=name, points=[(0.0, 1.0), (dur, 1.0)])
        self.tracks.insert(0, tr)
        return tr

    def add_note_track(self, name: str = "MIDI Note Track", notes: Optional[List[MidiNote]] = None) -> NoteTrack:
        tr = NoteTrack(name=name, notes=notes or [])
        self.tracks.append(tr)
        return tr

    def remove_track(self, uid: str) -> bool:
        for i, t in enumerate(self.tracks):
            if t.uid == uid:
                self.tracks.pop(i)
                return True
        return False

    def move_track(self, uid: str, delta: int) -> bool:
        for i, t in enumerate(self.tracks):
            if t.uid == uid:
                ni = max(0, min(len(self.tracks) - 1, i + delta))
                if ni != i:
                    self.tracks.insert(ni, self.tracks.pop(i))
                    return True
        return False

    def sort_tracks(self, by: str = "name") -> None:
        if by == "name":
            self.tracks.sort(key=lambda t: t.name.lower())
        elif by == "start":
            self.tracks.sort(key=lambda t: t.start_time() if isinstance(t, AudioTrack) else 0.0)

    def make_stereo_from_two_mono(self, t1: AudioTrack, t2: AudioTrack) -> Optional[AudioTrack]:
        if t1.channels != 1 or t2.channels != 1 or t1 is t2:
            return None
        sr = t1.sample_rate
        dur = max(t1.duration(), t2.duration())
        a1 = t1.render_range(0.0, dur, sr, apply_realtime_fx=False)
        a2 = t2.render_range(0.0, dur, sr, apply_realtime_fx=False)
        stereo = np.vstack([a1[0], a2[0]]).astype(np.float32)
        new_tr = AudioTrack(name=f"{t1.name} (Stereo)", channels=2, sample_rate=sr, color=t1.color, selected=True)
        new_tr.clips.append(AudioClip(samples=stereo, sample_rate=sr, start_time=0.0, name=new_tr.name, color=t1.color))
        idx = self.tracks.index(t1)
        self.tracks.remove(t1)
        if t2 in self.tracks:
            self.tracks.remove(t2)
        self.tracks.insert(min(idx, len(self.tracks)), new_tr)
        return new_tr

    def split_stereo_track(self, tr: AudioTrack, to_mono: bool = False) -> List[AudioTrack]:
        if tr.channels != 2:
            return []
        idx = self.tracks.index(tr)
        left = AudioTrack(
            name=f"{tr.name} L",
            channels=1,
            sample_rate=tr.sample_rate,
            pan=0.0 if to_mono else -1.0,
            color=tr.color,
            selected=tr.selected,
        )
        right = AudioTrack(
            name=f"{tr.name} R",
            channels=1,
            sample_rate=tr.sample_rate,
            pan=0.0 if to_mono else 1.0,
            color=self.next_clip_color(),
            selected=tr.selected,
        )
        for c in tr.clips:
            left.clips.append(AudioClip(samples=c.samples[0:1].copy(), sample_rate=c.sample_rate, start_time=c.start_time, name=f"{c.name} L", color=left.color, trim_start=c.trim_start, trim_end=c.trim_end))
            right.clips.append(AudioClip(samples=c.samples[1:2].copy(), sample_rate=c.sample_rate, start_time=c.start_time, name=f"{c.name} R", color=right.color, trim_start=c.trim_start, trim_end=c.trim_end))
        self.tracks.pop(idx)
        self.tracks.insert(idx, right)
        self.tracks.insert(idx, left)
        return [left, right]

    def swap_stereo_channels(self, tr: AudioTrack) -> bool:
        if tr.channels != 2:
            return False
        for c in tr.clips:
            if c.samples.shape[0] >= 2:
                c.samples = np.ascontiguousarray(c.samples[[1, 0], :])
        return True

    def mix_stereo_to_mono(self, tr: AudioTrack) -> bool:
        if tr.channels != 2:
            return False
        for c in tr.clips:
            c.samples = np.mean(c.samples, axis=0, keepdims=True).astype(np.float32)
        tr.channels = 1
        return True

    # ---- Mixing & Rendering ----
    def mix_render(
        self,
        start_s: float = 0.0,
        end_s: Optional[float] = None,
        sample_rate: Optional[int] = None,
        tracks: Optional[List[BaseTrack]] = None,
        apply_master_fx: bool = True,
    ) -> np.ndarray:
        """Render complete multitrack mix (float32, shape (2, N)) respecting Mute, Solo,
        Gain, Pan, Time Track, Per-Track Real-Time FX, MIDI Note Tracks, and Master FX."""
        sr = sample_rate or self.sample_rate
        t_end = self.duration() if end_s is None else end_s
        if t_end <= start_s:
            return np.zeros((2, 0), dtype=np.float32)
        n_out = int(round((t_end - start_s) * sr))
        mix = np.zeros((2, n_out), dtype=np.float32)

        src_tracks = tracks if tracks is not None else self.tracks
        any_solo = any(getattr(t, "solo", False) for t in src_tracks if isinstance(t, (AudioTrack, NoteTrack)))

        for tr in src_tracks:
            if isinstance(tr, AudioTrack):
                if any_solo and not tr.solo:
                    continue
                if not any_solo and tr.mute:
                    continue
                part = tr.render_range(start_s, t_end, sr, apply_realtime_fx=True, apply_gain_pan=True)
                n = min(n_out, part.shape[1])
                mix[:, :n] += part[:, :n]
            elif isinstance(tr, NoteTrack):
                if any_solo and not tr.solo:
                    continue
                if not any_solo and tr.mute:
                    continue
                part = tr.synthesize_audio(start_s, t_end, sr)
                n = min(n_out, part.shape[1])
                mix[:, :n] += part[:, :n]

        # Master gain & Master Real-Time FX chain
        if apply_master_fx and self.master_effects:
            from .dsp import apply_effect_chain
            mix = apply_effect_chain(mix, sr, self.master_effects)
        if abs(self.master_gain_db) > 1e-4:
            mix *= 10.0 ** (self.master_gain_db / 20.0)

        # Apply Time Track variable speed warp if non-unit
        tt = self.time_track()
        if tt is not None and any(abs(p[1] - 1.0) > 1e-3 for p in tt.points) and mix.shape[1] > 16:
            times = np.linspace(start_s, t_end, mix.shape[1], dtype=np.float64)
            speeds = np.array([tt.speed_at(t) for t in times[:: max(1, len(times) // 256)]], dtype=np.float64)
            t_grid = np.linspace(0.0, 1.0, len(speeds))
            full_speeds = np.interp(np.linspace(0.0, 1.0, mix.shape[1]), t_grid, speeds)
            cum_src = np.cumsum(full_speeds)
            cum_src = cum_src - cum_src[0]
            new_len = max(1, int(np.searchsorted(cum_src, mix.shape[1] - 1)))
            src_idx = cum_src[:new_len]
            x_old = np.arange(mix.shape[1], dtype=np.float64)
            warped = np.empty((2, new_len), dtype=np.float32)
            warped[0] = np.interp(src_idx, x_old, mix[0]).astype(np.float32)
            warped[1] = np.interp(src_idx, x_old, mix[1]).astype(np.float32)
            mix = warped

        return mix

    # ---- Core Editing Operations ----
    def _split_clip_at(self, tr: AudioTrack, clip: AudioClip, split_t: float) -> Tuple[Optional[AudioClip], Optional[AudioClip]]:
        if split_t <= clip.start_time + 1e-5 or split_t >= clip.end_time - 1e-5:
            return clip, None
        rendered = clip.render_audio(target_sr=tr.sample_rate)
        rel_idx = int(round((split_t - clip.start_time) * tr.sample_rate))
        rel_idx = max(1, min(rendered.shape[1] - 1, rel_idx))
        left = AudioClip(
            samples=rendered[:, :rel_idx].copy(),
            sample_rate=tr.sample_rate,
            start_time=clip.start_time,
            name=clip.name,
            color=clip.color,
        )
        right = AudioClip(
            samples=rendered[:, rel_idx:].copy(),
            sample_rate=tr.sample_rate,
            start_time=clip.start_time + rel_idx / tr.sample_rate,
            name=clip.name,
            color=clip.color,
        )
        return left, right

    def split_at_time(self, t: float, tracks: Optional[List[AudioTrack]] = None) -> int:
        count = 0
        for tr in (tracks or self.selected_audio_tracks()):
            new_clips: List[AudioClip] = []
            for c in tr.clips:
                if c.start_time + 1e-4 < t < c.end_time - 1e-4:
                    l, r = self._split_clip_at(tr, c, t)
                    if l:
                        new_clips.append(l)
                    if r:
                        new_clips.append(r)
                        count += 1
                else:
                    new_clips.append(c)
            tr.clips = new_clips
        return count

    def copy_selection(self) -> Dict[str, Any]:
        """Return a serializable clipboard payload usable within or across projects."""
        t0, t1 = self.selection_bounds()
        tracks_data = []
        for tr in self.selected_audio_tracks():
            arr = tr.render_range(t0, t1, tr.sample_rate, apply_realtime_fx=False)
            tracks_data.append({
                "name": tr.name,
                "channels": tr.channels,
                "sample_rate": tr.sample_rate,
                "samples": arr.copy(),
                "color": tr.color,
            })
        return {"duration": t1 - t0, "tracks": tracks_data}

    def delete_range(self, t0: float, t1: float, leave_gap: bool = False, tracks: Optional[List[AudioTrack]] = None) -> None:
        if t1 <= t0 + 1e-6:
            return
        delta = t1 - t0
        target_tracks = tracks if tracks is not None else self.selected_audio_tracks()
        target_uids = {t.uid for t in target_tracks}

        for tr in self.tracks:
            if isinstance(tr, AudioTrack):
                if tr.uid not in target_uids and not (self.sync_lock and tr.sync_lock):
                    continue
                new_clips: List[AudioClip] = []
                for c in tr.clips:
                    if c.end_time <= t0:
                        new_clips.append(c)
                    elif c.start_time >= t1:
                        if not leave_gap:
                            c.start_time = max(0.0, c.start_time - delta)
                        new_clips.append(c)
                    else:
                        rendered = c.render_audio(target_sr=tr.sample_rate)
                        # Left piece
                        if c.start_time < t0:
                            i_cut = max(1, int(round((t0 - c.start_time) * tr.sample_rate)))
                            new_clips.append(AudioClip(samples=rendered[:, :i_cut].copy(), sample_rate=tr.sample_rate, start_time=c.start_time, name=c.name, color=c.color))
                        # Right piece
                        if c.end_time > t1:
                            i_res = min(rendered.shape[1] - 1, int(round((t1 - c.start_time) * tr.sample_rate)))
                            new_start = t1 if leave_gap else t0
                            new_clips.append(AudioClip(samples=rendered[:, i_res:].copy(), sample_rate=tr.sample_rate, start_time=new_start, name=c.name, color=c.color))
                tr.clips = new_clips
            elif isinstance(tr, LabelTrack) and not leave_gap and (tr.selected or (self.sync_lock and tr.sync_lock)):
                kept = []
                for lb in tr.labels:
                    if lb.end <= t0:
                        kept.append(lb)
                    elif lb.start >= t1:
                        lb.start = max(0.0, lb.start - delta)
                        lb.end = max(lb.start, lb.end - delta)
                        kept.append(lb)
                    else:
                        if lb.start < t0:
                            lb.end = max(lb.start, lb.end - delta)
                            kept.append(lb)
                        elif lb.end > t1:
                            lb.start = t0
                            lb.end = max(t0, lb.end - delta)
                            kept.append(lb)
                tr.labels = kept
            elif isinstance(tr, NoteTrack) and not leave_gap and (tr.selected or (self.sync_lock and tr.sync_lock)):
                kept_n = []
                for nt in tr.notes:
                    if nt.end <= t0:
                        kept_n.append(nt)
                    elif nt.start >= t1:
                        nt.start = max(0.0, nt.start - delta)
                        nt.end = max(nt.start + 0.02, nt.end - delta)
                        kept_n.append(nt)
                tr.notes = kept_n

        if not leave_gap:
            self.set_selection(t0, t0)

    def silence_range(self, t0: float, t1: float, tracks: Optional[List[AudioTrack]] = None) -> None:
        if t1 <= t0 + 1e-6:
            return
        for tr in (tracks or self.selected_audio_tracks()):
            for c in tr.clips:
                if c.end_time <= t0 or c.start_time >= t1:
                    continue
                rendered = c.render_audio(target_sr=tr.sample_rate)
                i0 = max(0, int(round((t0 - c.start_time) * tr.sample_rate)))
                i1 = min(rendered.shape[1], int(round((t1 - c.start_time) * tr.sample_rate)))
                rendered[:, i0:i1] = 0.0
                c.samples = rendered
                c.sample_rate = tr.sample_rate
                c.trim_start = 0
                c.trim_end = 0
                c.speed_ratio = 1.0
                c.stretch_ratio = 1.0
                c.pitch_semitones = 0.0
                c.envelope_points.clear()

    def trim_to_range(self, t0: float, t1: float, tracks: Optional[List[AudioTrack]] = None) -> None:
        if t1 <= t0 + 1e-6:
            return
        for tr in (tracks or self.selected_audio_tracks()):
            new_clips: List[AudioClip] = []
            for c in tr.clips:
                if c.end_time <= t0 or c.start_time >= t1:
                    continue
                rendered = c.render_audio(target_sr=tr.sample_rate)
                i0 = max(0, int(round((t0 - c.start_time) * tr.sample_rate)))
                i1 = min(rendered.shape[1], int(round((t1 - c.start_time) * tr.sample_rate)))
                if i1 > i0:
                    new_clips.append(
                        AudioClip(
                            samples=rendered[:, i0:i1].copy(),
                            sample_rate=tr.sample_rate,
                            start_time=max(c.start_time, t0),
                            name=c.name,
                            color=c.color,
                        )
                    )
            tr.clips = new_clips

    def paste_clipboard(self, clipboard: Dict[str, Any], at_time: float, replace_selection: bool = True) -> bool:
        if not clipboard or not clipboard.get("tracks"):
            return False
        if replace_selection and self.has_selection():
            t0, t1 = self.selection_bounds()
            self.delete_range(t0, t1, leave_gap=False)
            at_time = t0
        dur = float(clipboard.get("duration", 0.0))
        sel_tracks = self.selected_audio_tracks()
        if not sel_tracks:
            for td in clipboard["tracks"]:
                sel_tracks.append(self.add_audio_track(channels=td["channels"], name=td["name"]))

        for idx, td in enumerate(clipboard["tracks"]):
            tr = sel_tracks[idx] if idx < len(sel_tracks) else self.add_audio_track(channels=td["channels"])
            samples = tr.ensure_channels(td["samples"].copy())
            if td["sample_rate"] != tr.sample_rate:
                from .dsp import resample_audio
                samples = resample_audio(samples, td["sample_rate"], tr.sample_rate)
            # Shift clips after insertion point right (ripple insert)
            if dur > 0:
                self.split_at_time(at_time, tracks=[tr])
                for c in tr.clips:
                    if c.start_time >= at_time - 1e-5:
                        c.start_time += dur
            tr.clips.append(AudioClip(samples=samples, sample_rate=tr.sample_rate, start_time=at_time, name=f"{td['name']} (Pasted)", color=td.get("color", tr.color)))
            tr.clips.sort(key=lambda c: c.start_time)

        if self.sync_lock and dur > 0:
            pasted_uids = {t.uid for t in sel_tracks}
            for tr in self.tracks:
                if tr.uid in pasted_uids or not tr.sync_lock:
                    continue
                if isinstance(tr, AudioTrack):
                    for c in tr.clips:
                        if c.start_time >= at_time - 1e-5:
                            c.start_time += dur
                elif isinstance(tr, LabelTrack):
                    for lb in tr.labels:
                        if lb.start >= at_time - 1e-5:
                            lb.start += dur
                            lb.end += dur

        self.set_selection(at_time, at_time + dur)
        return True

    def duplicate_selection(self) -> List[AudioTrack]:
        t0, t1 = self.selection_bounds()
        created: List[AudioTrack] = []
        for tr in self.selected_audio_tracks():
            arr = tr.render_range(t0, t1, tr.sample_rate, apply_realtime_fx=False)
            if arr.shape[1] == 0:
                continue
            dup = AudioTrack(name=f"{tr.name} (Copy)", channels=tr.channels, sample_rate=tr.sample_rate, color=self.next_clip_color())
            dup.clips.append(AudioClip(samples=arr, sample_rate=tr.sample_rate, start_time=t0, name=f"{tr.name} Dup", color=dup.color))
            self.tracks.append(dup)
            created.append(dup)
        return created

    def split_new_track(self) -> List[AudioTrack]:
        """Cut selection (leaving gap) into brand new track(s) at the same time."""
        t0, t1 = self.selection_bounds()
        created = self.duplicate_selection()
        if created:
            self.delete_range(t0, t1, leave_gap=True)
        return created

    def join_clips_in_range(self, t0: float, t1: float, tracks: Optional[List[AudioTrack]] = None) -> int:
        joined = 0
        for tr in (tracks or self.selected_audio_tracks()):
            overlapping = [c for c in tr.clips if c.end_time > t0 and c.start_time < t1]
            if len(overlapping) < 2:
                continue
            s_min = min(c.start_time for c in overlapping)
            s_max = max(c.end_time for c in overlapping)
            merged = tr.render_range(s_min, s_max, tr.sample_rate, apply_realtime_fx=False)
            for c in overlapping:
                tr.clips.remove(c)
            tr.clips.append(AudioClip(samples=merged, sample_rate=tr.sample_rate, start_time=s_min, name=overlapping[0].name, color=overlapping[0].color))
            tr.clips.sort(key=lambda c: c.start_time)
            joined += 1
        return joined

    def detach_at_silences(self, threshold_db: float = -48.0, min_silence_s: float = 0.25) -> int:
        """Split audio clips into separate clips by removing silent stretches."""
        thresh = 10.0 ** (threshold_db / 20.0)
        total_clips = 0
        for tr in self.selected_audio_tracks():
            new_clips: List[AudioClip] = []
            min_len = max(1, int(min_silence_s * tr.sample_rate))
            for c in tr.clips:
                arr = c.render_audio(target_sr=tr.sample_rate)
                mono = np.max(np.abs(arr), axis=0)
                silent = mono < thresh
                # Find contiguous non-silent islands separated by >= min_len silence
                win = max(1, min_len // 4)
                idx = 0
                n = len(silent)
                segments: List[Tuple[int, int]] = []
                in_sound = False
                seg_start = 0
                sil_run = 0
                step = max(1, tr.sample_rate // 200)
                for i in range(0, n, step):
                    block_silent = bool(np.all(silent[i : min(n, i + step)]))
                    if not block_silent:
                        if not in_sound:
                            in_sound = True
                            seg_start = i
                        sil_run = 0
                    else:
                        if in_sound:
                            sil_run += step
                            if sil_run >= min_len:
                                seg_end = max(seg_start + 1, i - sil_run + step)
                                segments.append((seg_start, seg_end))
                                in_sound = False
                                sil_run = 0
                if in_sound:
                    segments.append((seg_start, n))
                for s0, s1 in segments:
                    if s1 - s0 > 64:
                        new_clips.append(
                            AudioClip(
                                samples=arr[:, s0:s1].copy(),
                                sample_rate=tr.sample_rate,
                                start_time=c.start_time + s0 / tr.sample_rate,
                                name=c.name,
                                color=c.color,
                            )
                        )
                        total_clips += 1
            if new_clips:
                tr.clips = new_clips
        return total_clips

    def align_tracks(self, mode: str = "zero") -> None:
        """Align tracks: zero | cursor | end_to_end | together."""
        atracks = self.selected_audio_tracks()
        if not atracks:
            return
        if mode == "zero":
            for tr in atracks:
                st = tr.start_time()
                for c in tr.clips:
                    c.start_time = max(0.0, c.start_time - st)
        elif mode == "cursor":
            for tr in atracks:
                st = tr.start_time()
                delta = self.cursor_time - st
                for c in tr.clips:
                    c.start_time = max(0.0, c.start_time + delta)
        elif mode == "end_to_end":
            cursor = 0.0
            for tr in atracks:
                st = tr.start_time()
                delta = cursor - st
                for c in tr.clips:
                    c.start_time = max(0.0, c.start_time + delta)
                cursor = tr.duration()
        elif mode == "together":
            avg = sum(tr.start_time() for tr in atracks) / len(atracks)
            for tr in atracks:
                delta = avg - tr.start_time()
                for c in tr.clips:
                    c.start_time = max(0.0, c.start_time + delta)

    def apply_destructive_processor(
        self,
        processor,
        description: str,
        tracks: Optional[List[AudioTrack]] = None,
    ) -> int:
        """Apply a destructive audio function fn(samples, sr) -> samples to the current
        selection (or full track if no selection) on target audio tracks."""
        has_sel = self.has_selection()
        t0, t1 = self.selection_bounds()
        modified = 0
        for tr in (tracks or self.selected_audio_tracks()):
            if not tr.clips:
                continue
            if not has_sel:
                new_clips: List[AudioClip] = []
                for c in tr.clips:
                    arr = c.render_audio(target_sr=tr.sample_rate)
                    out = tr.ensure_channels(processor(arr, tr.sample_rate))
                    new_clips.append(AudioClip(samples=out, sample_rate=tr.sample_rate, start_time=c.start_time, name=c.name, color=c.color))
                    modified += 1
                tr.clips = new_clips
            else:
                # Flatten range [t0, t1], process, splice back cleanly
                seg = tr.render_range(t0, t1, tr.sample_rate, apply_realtime_fx=False)
                if seg.shape[1] == 0:
                    continue
                out = tr.ensure_channels(processor(seg, tr.sample_rate))
                old_dur = t1 - t0
                new_dur = out.shape[1] / tr.sample_rate
                delta = new_dur - old_dur
                # Replace region in track
                self.delete_range(t0, t1, leave_gap=True, tracks=[tr])
                if abs(delta) > 1e-4:
                    for c in tr.clips:
                        if c.start_time >= t1 - 1e-4:
                            c.start_time = max(0.0, c.start_time + delta)
                tr.clips.append(AudioClip(samples=out, sample_rate=tr.sample_rate, start_time=t0, name=f"{tr.name}", color=tr.color))
                tr.clips.sort(key=lambda c: c.start_time)
                modified += 1
        if modified:
            self.push_history(description)
        return modified
