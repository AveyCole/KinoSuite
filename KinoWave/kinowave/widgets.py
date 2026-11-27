"""KinoWave Custom Audio Widgets:
- Stereo LED Peak/RMS Level Meters with Clipping Indicators
- Interactive Timeline Ruler (Seconds / Beats & Measures / Quick-Play / Scrub / Loop)
- Multitrack Canvas (Linear & dB Waveform, Cached Spectrogram, Split View,
  Clip Headers/Colors, Non-Destructive Edge Trim, Clip Move/Stretch, Volume
  Envelopes, Individual Sample Draw, Spectral Frequency Selection, Multi-Tool,
  Label Track, Time Track, MIDI Piano Roll, Drag-and-Drop)
- Audacity-style Bottom Selection & Precision Time Bar
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollBar,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .dsp import compute_spectrogram_db, lin_to_db
from .models import (
    AudioClip,
    AudioTrack,
    BaseTrack,
    KinoWaveProject,
    LabelItem,
    LabelTrack,
    NoteTrack,
    SAMPLE_RATES,
    SNAP_UNITS,
    TIME_FORMATS,
    TimeTrack,
    format_time,
    parse_time,
    snap_time_value,
)
from .theme import get_palette


# ---------------------------------------------------------------------------
# Spectrogram Color LUTs (256 x 3 uint8)
# ---------------------------------------------------------------------------
def _build_colormap(name: str) -> np.ndarray:
    t = np.linspace(0.0, 1.0, 256)
    if name == "Grayscale":
        g = (t * 255).astype(np.uint8)
        return np.stack([g, g, g], axis=1)
    if name == "Magma":
        r = np.clip(np.interp(t, [0, 0.25, 0.55, 0.85, 1.0], [10, 80, 185, 250, 255]), 0, 255)
        g = np.clip(np.interp(t, [0, 0.25, 0.55, 0.85, 1.0], [8, 18, 55, 155, 252]), 0, 255)
        b = np.clip(np.interp(t, [0, 0.25, 0.55, 0.85, 1.0], [20, 118, 122, 108, 195]), 0, 255)
    elif name == "Inferno":
        r = np.clip(np.interp(t, [0, 0.3, 0.6, 0.85, 1.0], [4, 110, 210, 250, 255]), 0, 255)
        g = np.clip(np.interp(t, [0, 0.3, 0.6, 0.85, 1.0], [4, 22, 80, 185, 252]), 0, 255)
        b = np.clip(np.interp(t, [0, 0.3, 0.6, 0.85, 1.0], [16, 110, 50, 35, 165]), 0, 255)
    elif name == "Viridis":
        r = np.clip(np.interp(t, [0, 0.33, 0.66, 1.0], [16, 48, 70, 253]), 0, 255)
        g = np.clip(np.interp(t, [0, 0.33, 0.66, 1.0], [10, 95, 175, 231]), 0, 255)
        b = np.clip(np.interp(t, [0, 0.33, 0.66, 1.0], [48, 138, 128, 37]), 0, 255)
    elif name == "Roseus":
        r = np.clip(np.interp(t, [0, 0.3, 0.65, 1.0], [12, 65, 220, 255]), 0, 255)
        g = np.clip(np.interp(t, [0, 0.3, 0.65, 1.0], [15, 45, 75, 240]), 0, 255)
        b = np.clip(np.interp(t, [0, 0.3, 0.65, 1.0], [28, 145, 165, 215]), 0, 255)
    else:  # KinoWave Cyber Emerald-Cyan-Gold
        r = np.clip(np.interp(t, [0, 0.3, 0.6, 0.85, 1.0], [12, 14, 16, 245, 255]), 0, 255)
        g = np.clip(np.interp(t, [0, 0.3, 0.6, 0.85, 1.0], [16, 65, 217, 175, 245]), 0, 255)
        b = np.clip(np.interp(t, [0, 0.3, 0.6, 0.85, 1.0], [26, 115, 165, 40, 225]), 0, 255)
    return np.stack([r, g, b], axis=1).astype(np.uint8)


_COLORMAP_CACHE: Dict[str, np.ndarray] = {}


def get_colormap(name: str) -> np.ndarray:
    if name not in _COLORMAP_CACHE:
        _COLORMAP_CACHE[name] = _build_colormap(name)
    return _COLORMAP_CACHE[name]


# ---------------------------------------------------------------------------
# Stereo Level Meter Widget (Input & Output Metering + Clipping Reset)
# ---------------------------------------------------------------------------
class LevelMeterWidget(QWidget):
    clipResetRequested = Signal()

    def __init__(self, label: str = "OUT", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.label = label
        self.setMinimumWidth(165)
        self.setFixedHeight(32)
        self.peak = (0.0, 0.0)
        self.rms = (0.0, 0.0)
        self.hold = [0.0, 0.0]
        self.clipped = False
        self.setToolTip(f"{label} Stereo dB Level Meter (click to reset clipping indicator)")
        self.setAccessibleName(f"{label} Stereo Level Meter")

    def set_levels(self, peak: Tuple[float, float], rms: Tuple[float, float], clipped: bool) -> None:
        self.peak = peak
        self.rms = rms
        self.clipped = clipped
        for i in range(2):
            self.hold[i] = max(peak[i], self.hold[i] * 0.92)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clipped = False
        self.hold = [0.0, 0.0]
        self.clipResetRequested.emit()
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.fillRect(r, QColor("#0E1219"))
        p.setPen(QPen(QColor("#2A3242"), 1))
        p.drawRoundedRect(r.adjusted(0, 0, -1, -1), 4, 4)

        # Label badge
        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.setPen(QColor("#8D99AE"))
        p.drawText(QRect(4, 2, 28, r.height() - 4), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label)

        bar_x = 34
        clip_w = 10
        bar_w = max(20, r.width() - bar_x - clip_w - 6)

        grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
        grad.setColorAt(0.0, QColor("#10D9A0"))
        grad.setColorAt(0.72, QColor("#22D3EE"))
        grad.setColorAt(0.88, QColor("#F59E0B"))
        grad.setColorAt(1.0, QColor("#F43F5E"))

        for ch in range(2):
            by = 5 + ch * 11
            bh = 8
            p.fillRect(QRectF(bar_x, by, bar_w, bh), QColor("#18202D"))
            db_pk = max(-60.0, min(0.0, lin_to_db(self.peak[ch], -60.0)))
            frac = (db_pk + 60.0) / 60.0
            if frac > 0.005:
                p.fillRect(QRectF(bar_x, by, bar_w * frac, bh), QBrush(grad))
            # Peak hold tick
            db_h = max(-60.0, min(0.0, lin_to_db(self.hold[ch], -60.0)))
            h_frac = (db_h + 60.0) / 60.0
            if h_frac > 0.01:
                hx = bar_x + bar_w * h_frac
                p.setPen(QPen(QColor("#FFFFFF"), 1.5))
                p.drawLine(QPointF(hx, by), QPointF(hx, by + bh))

        # dB ticks
        p.setPen(QColor("#64748B"))
        p.setFont(QFont("Segoe UI", 6))
        for db_mark in (-48, -36, -24, -12, -6, 0):
            mx = bar_x + bar_w * ((db_mark + 60.0) / 60.0)
            p.drawLine(QPointF(mx, 2), QPointF(mx, 4))

        # Clipping indicator LED
        clip_rect = QRectF(r.width() - clip_w - 3, 5, clip_w, 19)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#F43F5E") if self.clipped else QColor("#261820"))
        p.drawRoundedRect(clip_rect, 2, 2)
        p.end()


# ---------------------------------------------------------------------------
# Timeline Ruler Widget (Quick-Play, Scrub, Loop Bracket, Beats & Measures)
# ---------------------------------------------------------------------------
HEADER_WIDTH = 216
RULER_HEIGHT = 32


class TimelineRulerWidget(QWidget):
    quickPlayRequested = Signal(float, float)  # start_s, end_s (end<=start means play from start)
    scrubRequested = Signal(float)
    loopChanged = Signal(float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(RULER_HEIGHT)
        self.project: Optional[KinoWaveProject] = None
        self.pps: float = 100.0  # pixels per second
        self.scroll_x_s: float = 0.0
        self.playhead_s: float = 0.0
        self.theme_name: str = "Dark"
        self.scrub_mode: bool = False
        self._drag_mode: Optional[str] = None
        self._drag_start_s: float = 0.0
        self._drag_cur_s: float = 0.0
        self.setMouseTracking(True)
        self.setToolTip("Timeline Ruler: Click/drag to Quick-Play | Shift+Drag to set Loop | Right-drag to Scrub")

    def x_to_time(self, x: float) -> float:
        return max(0.0, self.scroll_x_s + (x - HEADER_WIDTH) / max(1.0, self.pps))

    def time_to_x(self, t: float) -> float:
        return HEADER_WIDTH + (t - self.scroll_x_s) * self.pps

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.project is None or event.position().x() < HEADER_WIDTH:
            return
        t = self.x_to_time(event.position().x())
        self._drag_start_s = t
        self._drag_cur_s = t
        if event.button() == Qt.MouseButton.RightButton or self.scrub_mode:
            self._drag_mode = "scrub"
            self.scrubRequested.emit(t)
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._drag_mode = "loop"
        else:
            self._drag_mode = "quickplay"
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._drag_mode or self.project is None:
            return
        t = self.x_to_time(event.position().x())
        self._drag_cur_s = t
        if self._drag_mode == "scrub":
            self.scrubRequested.emit(t)
        elif self._drag_mode == "loop":
            a, b = min(self._drag_start_s, t), max(self._drag_start_s, t)
            if b - a > 0.05:
                self.project.loop_start = a
                self.project.loop_end = b
                self.project.loop_enabled = True
                self.loopChanged.emit(a, b)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode == "quickplay":
            a, b = min(self._drag_start_s, self._drag_cur_s), max(self._drag_start_s, self._drag_cur_s)
            if b - a > 0.08:
                self.quickPlayRequested.emit(a, b)
            else:
                self.quickPlayRequested.emit(self._drag_start_s, -1.0)
        self._drag_mode = None
        self.update()

    def paintEvent(self, event) -> None:
        pal = get_palette(self.theme_name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(pal["bg_ruler"]))

        # Left corner label
        p.fillRect(QRect(0, 0, HEADER_WIDTH, self.height()), QColor(pal["bg_panel"]))
        p.setPen(QColor(pal["border"]))
        p.drawLine(HEADER_WIDTH - 1, 0, HEADER_WIDTH - 1, self.height())
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        proj = self.project
        p.setPen(QColor(pal["accent"]))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        mode_lbl = f"BEATS {proj.bpm:.0f} BPM" if (proj and proj.show_beats_grid) else "TIMELINE"
        p.drawText(QRect(10, 0, HEADER_WIDTH - 16, self.height()), Qt.AlignmentFlag.AlignVCenter, mode_lbl)

        if proj is None:
            p.end()
            return

        p.setClipRect(QRect(HEADER_WIDTH, 0, self.width() - HEADER_WIDTH, self.height()))

        # Loop region bracket
        if proj.loop_enabled and proj.loop_end > proj.loop_start:
            lx0 = self.time_to_x(proj.loop_start)
            lx1 = self.time_to_x(proj.loop_end)
            p.fillRect(QRectF(lx0, 0, max(2.0, lx1 - lx0), 8), QColor(pal["loop_bar"]))

        # Quick-play drag preview
        if self._drag_mode == "quickplay" and abs(self._drag_cur_s - self._drag_start_s) > 0.05:
            qx0 = self.time_to_x(min(self._drag_start_s, self._drag_cur_s))
            qx1 = self.time_to_x(max(self._drag_start_s, self._drag_cur_s))
            c = QColor(pal["accent"])
            c.setAlpha(90)
            p.fillRect(QRectF(qx0, 0, qx1 - qx0, self.height()), c)

        # Ticks
        t_start = max(0.0, self.scroll_x_s)
        t_end = self.x_to_time(self.width())
        p.setFont(QFont("Segoe UI", 7.5))

        if proj.show_beats_grid:
            beat_s = 60.0 / max(20.0, proj.bpm)
            bar_s = beat_s * max(1, proj.time_sig_num)
            b0 = max(0, int(math.floor(t_start / beat_s)))
            b1 = int(math.ceil(t_end / beat_s)) + 1
            step_b = 1
            while step_b * beat_s * self.pps < 24:
                step_b *= 2
            for b in range(b0, b1, step_b):
                t = b * beat_s
                x = self.time_to_x(t)
                is_bar = (b % max(1, proj.time_sig_num)) == 0
                p.setPen(QColor(pal["text"] if is_bar else pal["border_strong"]))
                p.drawLine(QPointF(x, self.height() - (12 if is_bar else 6)), QPointF(x, self.height()))
                if is_bar or beat_s * self.pps >= 45:
                    bar_num = b // max(1, proj.time_sig_num) + 1
                    beat_num = (b % max(1, proj.time_sig_num)) + 1
                    lbl = f"{bar_num}" if is_bar else f"{bar_num}.{beat_num}"
                    p.setPen(QColor(pal["text"] if is_bar else pal["text_muted"]))
                    p.drawText(QPointF(x + 3, 18), lbl)
        else:
            # Adaptive time step
            candidates = [0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 300.0]
            step = candidates[-1]
            for c in candidates:
                if c * self.pps >= 68:
                    step = c
                    break
            k0 = max(0, int(math.floor(t_start / step)))
            k1 = int(math.ceil(t_end / step)) + 1
            for k in range(k0, k1):
                t = k * step
                x = self.time_to_x(t)
                p.setPen(QColor(pal["border_strong"]))
                p.drawLine(QPointF(x, self.height() - 10), QPointF(x, self.height()))
                # Sub-ticks
                for sub in range(1, 4):
                    sx = self.time_to_x(t + sub * step / 4.0)
                    p.drawLine(QPointF(sx, self.height() - 5), QPointF(sx, self.height()))
                p.setPen(QColor(pal["text_muted"]))
                if step < 0.1:
                    lbl = f"{t:.3f}s"
                elif step < 1.0:
                    lbl = f"{t:.2f}s"
                elif t >= 60.0:
                    lbl = f"{int(t // 60)}:{int(t % 60):02d}"
                else:
                    lbl = f"{t:.1f}s" if step < 1 else f"{int(round(t))}s"
                p.drawText(QPointF(x + 3, 19), lbl)

        # Playhead triangle
        px = self.time_to_x(self.playhead_s)
        p.setBrush(QBrush(QColor(pal["playhead"])))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([QPointF(px - 6, self.height() - 11), QPointF(px + 6, self.height() - 11), QPointF(px, self.height() - 1)]))
        p.end()


# ---------------------------------------------------------------------------
# Multitrack Canvas Widget (Track Controls + Audio / Spectrogram / Label / Time / MIDI)
# ---------------------------------------------------------------------------
class MultitrackCanvasWidget(QWidget):
    selectionChanged = Signal()
    projectModified = Signal(str)
    trackFXRequested = Signal(str)  # track uid
    trackActionRequested = Signal(str, str)  # track uid, action name
    filesDropped = Signal(list)
    zoomRequested = Signal(float, float)  # factor, anchor_time_s
    labelEditRequested = Signal(str, str)  # track uid, label uid

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[KinoWaveProject] = None
        self.theme_name: str = "Dark"
        self.pps: float = 100.0
        self.scroll_x_s: float = 0.0
        self.scroll_y: int = 0
        self.playhead_s: float = 0.0
        self.tool: str = "multi"  # select | envelope | draw | multi | zoom | shift
        self.mouse_wheel_zoom: bool = True

        self._spec_cache: Dict[Tuple[str, int, str, str, int], QImage] = {}
        self._wave_cache: Dict[Tuple, Any] = {}
        self._drag_kind: Optional[str] = None
        self._drag_track: Optional[BaseTrack] = None
        self._drag_clip: Optional[AudioClip] = None
        self._drag_anchor_s: float = 0.0
        self._drag_anchor_y: float = 0.0
        self._drag_orig_start: float = 0.0
        self._drag_orig_trim: int = 0
        self._drag_orig_stretch: float = 1.0
        self._drag_env_idx: int = -1
        self._drag_label: Optional[LabelItem] = None
        self._drag_time_pt: int = -1
        self._header_hit_rects: List[Tuple[QRectF, str, str]] = []  # (rect, track_uid, action)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("KinoWave Multitrack Workspace")

    def invalidate_caches(self) -> None:
        self._spec_cache.clear()
        self._wave_cache.clear()
        self.update()

    def total_content_height(self) -> int:
        if not self.project:
            return 300
        return sum(t.display_height + 6 for t in self.project.tracks) + 80

    def x_to_time(self, x: float) -> float:
        return max(0.0, self.scroll_x_s + (x - HEADER_WIDTH) / max(1.0, self.pps))

    def time_to_x(self, t: float) -> float:
        return HEADER_WIDTH + (t - self.scroll_x_s) * self.pps

    def _track_rects(self) -> List[Tuple[BaseTrack, QRectF]]:
        if not self.project:
            return []
        res = []
        y = 6 - self.scroll_y
        for tr in self.project.tracks:
            h = tr.display_height
            res.append((tr, QRectF(0, y, self.width(), h)))
            y += h + 6
        return res

    def _track_at_y(self, y: float) -> Tuple[Optional[BaseTrack], QRectF]:
        for tr, rect in self._track_rects():
            if rect.top() <= y <= rect.bottom():
                return tr, rect
        return None, QRectF()

    def _clip_at(self, tr: AudioTrack, t: float) -> Optional[AudioClip]:
        for c in reversed(tr.clips):
            if c.start_time <= t <= c.end_time:
                return c
        return None

    def _y_to_freq(self, y: float, top: float, height: float, tr: AudioTrack) -> float:
        frac = 1.0 - np.clip((y - top) / max(1.0, height), 0.0, 1.0)
        fmin = max(10.0, tr.spectrogram.min_freq)
        fmax = min(tr.sample_rate / 2.0, tr.spectrogram.max_freq)
        if tr.spectrogram.freq_scale == "Logarithmic":
            return float(fmin * ((fmax / fmin) ** frac))
        return float(fmin + frac * (fmax - fmin))

    def _freq_to_y(self, freq: float, top: float, height: float, tr: AudioTrack) -> float:
        fmin = max(10.0, tr.spectrogram.min_freq)
        fmax = min(tr.sample_rate / 2.0, tr.spectrogram.max_freq)
        f = np.clip(freq, fmin, fmax)
        if tr.spectrogram.freq_scale == "Logarithmic":
            frac = math.log(f / fmin) / max(1e-6, math.log(fmax / fmin))
        else:
            frac = (f - fmin) / max(1e-6, fmax - fmin)
        return float(top + (1.0 - frac) * height)

    # ---- Drag-and-Drop Audio / MIDI / Label Files ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()

    # ---- Wheel Zoom & Scroll ----
    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.project is None:
            return
        dy = event.angleDelta().y()
        mods = event.modifiers()
        if (mods & Qt.KeyboardModifier.ControlModifier) or (self.mouse_wheel_zoom and not (mods & Qt.KeyboardModifier.ShiftModifier) and event.position().x() > HEADER_WIDTH):
            factor = 1.25 if dy > 0 else 0.8
            anchor = self.x_to_time(event.position().x())
            self.zoomRequested.emit(factor, anchor)
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            self.scroll_x_s = max(0.0, self.scroll_x_s - (dy / 120.0) * (80.0 / max(1.0, self.pps)))
            self.update()
        else:
            self.scroll_y = max(0, min(max(0, self.total_content_height() - self.height()), self.scroll_y - int(dy * 0.4)))
            self.update()

    # ---- Mouse Interaction (Multi-Tool, Select, Spectral, Envelope, Draw, Trim, Move, Stretch) ----
    def _effective_action(self, tr: AudioTrack, rect: QRectF, x: float, y: float, mods) -> Tuple[str, Optional[AudioClip]]:
        t = self.x_to_time(x)
        clip = self._clip_at(tr, t)
        if self.tool == "zoom":
            return "zoom", clip
        if self.tool == "shift":
            return ("move_clip" if clip else "select"), clip
        if self.tool == "draw":
            return "draw", clip
        if self.tool == "envelope":
            return ("envelope" if clip else "select"), clip
        if self.tool == "select":
            if tr.view_mode in ("Spectrogram", "Split View"):
                return "spectral_select", clip
            return "select", clip

        # Multi-tool (F6): context-aware Audacity behavior
        if clip is not None:
            cx0 = self.time_to_x(clip.start_time)
            cx1 = self.time_to_x(clip.end_time)
            if y - rect.top() <= 18:
                return "move_clip", clip
            if abs(x - cx0) <= 7:
                return ("stretch_clip" if (mods & Qt.KeyboardModifier.AltModifier) else "trim_left"), clip
            if abs(x - cx1) <= 7:
                return ("stretch_clip" if (mods & Qt.KeyboardModifier.AltModifier) else "trim_right"), clip
            if self.pps >= 8000:
                return "draw", clip
            rel_y = (y - (rect.top() + 18)) / max(1.0, rect.height() - 18)
            if rel_y < 0.16 or rel_y > 0.84:
                return "envelope", clip
        if tr.view_mode in ("Spectrogram", "Split View"):
            return "spectral_select", clip
        return "select", clip

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.project is None:
            return
        pos = event.position()
        x, y = pos.x(), pos.y()

        # Check left track-header controls first
        if x < HEADER_WIDTH:
            for hrect, uid, act in self._header_hit_rects:
                if hrect.contains(pos):
                    if act in ("gain_drag", "pan_drag"):
                        self._drag_kind = act
                        self._drag_track = next((t for t in self.project.tracks if t.uid == uid), None)
                        self._update_header_slider(act, hrect, x)
                    else:
                        self.trackActionRequested.emit(uid, act)
                    return
            # Clicking empty track header selects that track
            tr, _ = self._track_at_y(y)
            if tr:
                if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    for other in self.project.tracks:
                        other.selected = False
                tr.selected = True
                self.selectionChanged.emit()
                self.update()
            return

        tr, rect = self._track_at_y(y)
        if tr is None:
            return
        t = self.x_to_time(x)

        # Right-click context menu on Audio Clip
        if event.button() == Qt.MouseButton.RightButton:
            if self.tool == "zoom":
                self.zoomRequested.emit(0.65, t)
                return
            if isinstance(tr, AudioTrack):
                clip = self._clip_at(tr, t)
                self._show_clip_context_menu(tr, clip, t, event.globalPosition().toPoint())
            return

        # Select track
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            for other in self.project.tracks:
                other.selected = False
        tr.selected = True

        # Label Track interaction
        if isinstance(tr, LabelTrack):
            for lb in tr.labels:
                lx0 = self.time_to_x(lb.start)
                lx1 = max(lx0 + 48, self.time_to_x(lb.end))
                if lx0 - 6 <= x <= lx1 + 6:
                    self._drag_kind = "label_move"
                    self._drag_track = tr
                    self._drag_label = lb
                    self._drag_anchor_s = t
                    self._drag_orig_start = lb.start
                    self.project.set_selection(lb.start, lb.end)
                    self.selectionChanged.emit()
                    self.update()
                    return
            self.project.set_selection(t, t, snap=True)
            self._drag_kind = "select"
            self._drag_anchor_s = self.project.sel_start
            self.selectionChanged.emit()
            self.update()
            return

        # Time Track interaction
        if isinstance(tr, TimeTrack):
            # Find or add control point
            for idx, (pt, pv) in enumerate(tr.points):
                px = self.time_to_x(pt)
                py = rect.bottom() - ((pv - tr.min_speed) / max(0.01, tr.max_speed - tr.min_speed)) * (rect.height() - 16) - 8
                if math.hypot(x - px, y - py) <= 10:
                    self._drag_kind = "time_pt"
                    self._drag_track = tr
                    self._drag_time_pt = idx
                    return
            val = tr.min_speed + (1.0 - np.clip((y - rect.top() - 8) / max(1.0, rect.height() - 16), 0.0, 1.0)) * (tr.max_speed - tr.min_speed)
            tr.points.append((t, float(val)))
            tr.points.sort(key=lambda p: p[0])
            self._drag_kind = "time_pt"
            self._drag_track = tr
            self._drag_time_pt = min(range(len(tr.points)), key=lambda i: abs(tr.points[i][0] - t))
            self.projectModified.emit("Edited Time Track")
            self.update()
            return

        if not isinstance(tr, AudioTrack):
            self.project.set_selection(t, t, snap=True)
            self._drag_kind = "select"
            self._drag_anchor_s = self.project.sel_start
            self.selectionChanged.emit()
            self.update()
            return

        act, clip = self._effective_action(tr, rect, x, y, event.modifiers())
        if act == "zoom":
            self.zoomRequested.emit(1.6, t)
            return

        self._drag_kind = act
        self._drag_track = tr
        self._drag_clip = clip
        self._drag_anchor_s = t
        self._drag_anchor_y = y

        if act == "move_clip" and clip is not None:
            self._drag_orig_start = clip.start_time
        elif act == "trim_left" and clip is not None:
            self._drag_orig_start = clip.start_time
            self._drag_orig_trim = clip.trim_start
        elif act == "trim_right" and clip is not None:
            self._drag_orig_trim = clip.trim_end
        elif act == "stretch_clip" and clip is not None:
            self._drag_orig_stretch = clip.stretch_ratio
        elif act == "envelope" and clip is not None:
            rel_t = max(0.0, min(clip.duration, t - clip.start_time))
            # Gain from distance to center of waveform
            top = rect.top() + 18
            h = max(10.0, rect.height() - 18)
            mid = top + h * 0.5
            g = float(np.clip(abs(y - mid) / (h * 0.45), 0.0, 1.8))
            if not clip.envelope_points:
                clip.envelope_points = [(0.0, 1.0), (clip.duration, 1.0)]
            # Check existing point
            hit = -1
            for i, (pt, pg) in enumerate(clip.envelope_points):
                if abs(self.time_to_x(clip.start_time + pt) - x) <= 8:
                    hit = i
                    break
            if hit >= 0:
                self._drag_env_idx = hit
                clip.envelope_points[hit] = (rel_t, g)
            else:
                clip.envelope_points.append((rel_t, g))
                clip.envelope_points.sort(key=lambda p: p[0])
                self._drag_env_idx = min(range(len(clip.envelope_points)), key=lambda i: abs(clip.envelope_points[i][0] - rel_t))
            self.update()
        elif act == "draw" and clip is not None:
            self._draw_sample_at(tr, clip, rect, x, y)
        elif act == "spectral_select":
            snapped = snap_time_value(t, self.project.snap_mode, self.project.snap_unit, self.project.sample_rate, self.project.bpm, self.project.time_sig_num)
            self._drag_anchor_s = snapped
            self.project.set_selection(snapped, snapped)
            top = rect.top() + 18 + ((rect.height() - 18) * 0.5 if tr.view_mode == "Split View" else 0)
            h = (rect.height() - 18) * (0.5 if tr.view_mode == "Split View" else 1.0)
            f0 = self._y_to_freq(y, top, h, tr)
            self.project.spectral_low_hz = f0
            self.project.spectral_high_hz = f0
            self.selectionChanged.emit()
        else:
            snapped = snap_time_value(t, self.project.snap_mode, self.project.snap_unit, self.project.sample_rate, self.project.bpm, self.project.time_sig_num)
            self._drag_anchor_s = snapped
            self.project.set_selection(snapped, snapped)
            self.project.spectral_low_hz = None
            self.project.spectral_high_hz = None
            self.selectionChanged.emit()
        self.update()

    def _update_header_slider(self, act: str, hrect: QRectF, x: float) -> None:
        if not isinstance(self._drag_track, AudioTrack):
            return
        frac = float(np.clip((x - hrect.left()) / max(1.0, hrect.width()), 0.0, 1.0))
        if act == "gain_drag":
            self._drag_track.gain_db = round(-36.0 + frac * 72.0, 1)
        elif act == "pan_drag":
            self._drag_track.pan = round(-1.0 + frac * 2.0, 2)
        self.update()

    def _draw_sample_at(self, tr: AudioTrack, clip: AudioClip, rect: QRectF, x: float, y: float) -> None:
        t = self.x_to_time(x)
        rel_idx = int(round((t - clip.start_time) * clip.sample_rate)) + clip.trim_start
        if 0 <= rel_idx < clip.samples.shape[1]:
            top = rect.top() + 18
            h = max(10.0, rect.height() - 18)
            ch = 0
            if tr.channels == 2:
                half = h * 0.5
                if y > top + half:
                    ch = 1
                    mid = top + half * 1.5
                else:
                    mid = top + half * 0.5
                amp = float(np.clip((mid - y) / max(1.0, half * 0.45), -1.0, 1.0))
            else:
                mid = top + h * 0.5
                amp = float(np.clip((mid - y) / max(1.0, h * 0.45), -1.0, 1.0))
            clip.samples[min(ch, clip.samples.shape[0] - 1), rel_idx] = amp
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.project is None:
            return
        pos = event.position()
        x, y = pos.x(), pos.y()

        # Hover cursor update when not dragging
        if self._drag_kind is None:
            if x >= HEADER_WIDTH:
                tr, rect = self._track_at_y(y)
                if isinstance(tr, AudioTrack):
                    act, _ = self._effective_action(tr, rect, x, y, event.modifiers())
                    cursors = {
                        "move_clip": Qt.CursorShape.OpenHandCursor,
                        "trim_left": Qt.CursorShape.SizeHorCursor,
                        "trim_right": Qt.CursorShape.SizeHorCursor,
                        "stretch_clip": Qt.CursorShape.SplitHCursor,
                        "envelope": Qt.CursorShape.SizeVerCursor,
                        "draw": Qt.CursorShape.CrossCursor,
                        "zoom": Qt.CursorShape.PointingHandCursor,
                    }
                    self.setCursor(cursors.get(act, Qt.CursorShape.IBeamCursor))
                else:
                    self.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self._drag_kind in ("gain_drag", "pan_drag") and self._drag_track is not None:
            for hrect, uid, act in self._header_hit_rects:
                if uid == self._drag_track.uid and act == self._drag_kind:
                    self._update_header_slider(act, hrect, x)
                    break
            return

        t = self.x_to_time(x)
        if self._drag_kind == "select":
            snapped = snap_time_value(t, self.project.snap_mode, self.project.snap_unit, self.project.sample_rate, self.project.bpm, self.project.time_sig_num)
            self.project.set_selection(self._drag_anchor_s, snapped)
            self.selectionChanged.emit()
        elif self._drag_kind == "spectral_select" and isinstance(self._drag_track, AudioTrack):
            tr = self._drag_track
            _, rect = next(((tt, rr) for tt, rr in self._track_rects() if tt.uid == tr.uid), (None, QRectF()))
            snapped = snap_time_value(t, self.project.snap_mode, self.project.snap_unit, self.project.sample_rate, self.project.bpm, self.project.time_sig_num)
            self.project.set_selection(self._drag_anchor_s, snapped)
            top = rect.top() + 18 + ((rect.height() - 18) * 0.5 if tr.view_mode == "Split View" else 0)
            h = (rect.height() - 18) * (0.5 if tr.view_mode == "Split View" else 1.0)
            f0 = self._y_to_freq(self._drag_anchor_y, top, h, tr)
            f1 = self._y_to_freq(y, top, h, tr)
            self.project.spectral_low_hz = min(f0, f1)
            self.project.spectral_high_hz = max(f0, f1)
            self.selectionChanged.emit()
        elif self._drag_kind == "move_clip" and self._drag_clip is not None and isinstance(self._drag_track, AudioTrack):
            dt = t - self._drag_anchor_s
            new_st = max(0.0, self._drag_orig_start + dt)
            if self.project.snap_mode != "Off":
                new_st = snap_time_value(new_st, self.project.snap_mode, self.project.snap_unit, self.project.sample_rate, self.project.bpm, self.project.time_sig_num)
            self._drag_clip.start_time = new_st
            # Allow moving clip between audio tracks vertically!
            target_tr, _ = self._track_at_y(y)
            if isinstance(target_tr, AudioTrack) and target_tr is not self._drag_track:
                if self._drag_clip in self._drag_track.clips:
                    self._drag_track.clips.remove(self._drag_clip)
                    self._drag_clip.samples = target_tr.ensure_channels(self._drag_clip.samples)
                    target_tr.clips.append(self._drag_clip)
                    self._drag_track = target_tr
        elif self._drag_kind == "trim_left" and self._drag_clip is not None:
            dt = t - self._drag_anchor_s
            d_smpl = int(round(dt * self._drag_clip.sample_rate))
            new_trim = max(0, min(self._drag_clip.raw_length - self._drag_clip.trim_end - 64, self._drag_orig_trim + d_smpl))
            delta_s = (new_trim - self._drag_orig_trim) / self._drag_clip.sample_rate
            self._drag_clip.trim_start = new_trim
            self._drag_clip.start_time = max(0.0, self._drag_orig_start + delta_s)
        elif self._drag_kind == "trim_right" and self._drag_clip is not None:
            dt = self._drag_anchor_s - t
            d_smpl = int(round(dt * self._drag_clip.sample_rate))
            self._drag_clip.trim_end = max(0, min(self._drag_clip.raw_length - self._drag_clip.trim_start - 64, self._drag_orig_trim + d_smpl))
        elif self._drag_kind == "stretch_clip" and self._drag_clip is not None:
            base_dur = max(0.05, self._drag_clip.visible_sample_count / self._drag_clip.sample_rate)
            new_dur = max(0.05, t - self._drag_clip.start_time)
            self._drag_clip.stretch_ratio = float(np.clip(new_dur / base_dur, 0.25, 4.0))
        elif self._drag_kind == "envelope" and self._drag_clip is not None and self._drag_env_idx >= 0:
            _, rect = next(((tt, rr) for tt, rr in self._track_rects() if tt.uid == self._drag_track.uid), (None, QRectF()))
            top = rect.top() + 18
            h = max(10.0, rect.height() - 18)
            mid = top + h * 0.5
            g = float(np.clip(abs(y - mid) / (h * 0.45), 0.0, 1.8))
            rel_t = float(np.clip(t - self._drag_clip.start_time, 0.0, self._drag_clip.duration))
            self._drag_clip.envelope_points[self._drag_env_idx] = (rel_t, g)
        elif self._drag_kind == "draw" and self._drag_clip is not None and isinstance(self._drag_track, AudioTrack):
            _, rect = next(((tt, rr) for tt, rr in self._track_rects() if tt.uid == self._drag_track.uid), (None, QRectF()))
            self._draw_sample_at(self._drag_track, self._drag_clip, rect, x, y)
        elif self._drag_kind == "label_move" and self._drag_label is not None:
            dt = t - self._drag_anchor_s
            span = self._drag_label.end - self._drag_label.start
            self._drag_label.start = max(0.0, self._drag_orig_start + dt)
            self._drag_label.end = self._drag_label.start + span
        elif self._drag_kind == "time_pt" and isinstance(self._drag_track, TimeTrack) and 0 <= self._drag_time_pt < len(self._drag_track.points):
            tr = self._drag_track
            _, rect = next(((tt, rr) for tt, rr in self._track_rects() if tt.uid == tr.uid), (None, QRectF()))
            val = tr.min_speed + (1.0 - np.clip((y - rect.top() - 8) / max(1.0, rect.height() - 16), 0.0, 1.0)) * (tr.max_speed - tr.min_speed)
            tr.points[self._drag_time_pt] = (max(0.0, t), float(val))
            tr.points.sort(key=lambda p: p[0])
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_kind in ("move_clip", "trim_left", "trim_right", "stretch_clip", "envelope", "draw", "label_move", "time_pt"):
            self._spec_cache.clear()
            self._wave_cache.clear()
            desc_map = {
                "move_clip": "Moved Clip",
                "trim_left": "Trimmed Clip Edge",
                "trim_right": "Trimmed Clip Edge",
                "stretch_clip": "Stretched Clip",
                "envelope": "Edited Volume Envelope",
                "draw": "Drew Audio Samples",
                "label_move": "Moved Label",
                "time_pt": "Edited Time Track",
            }
            self.projectModified.emit(desc_map[self._drag_kind])
        self._drag_kind = None
        self._drag_clip = None
        self._drag_label = None
        self._drag_env_idx = -1
        self._drag_time_pt = -1

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.project is None or event.position().x() < HEADER_WIDTH:
            return
        tr, rect = self._track_at_y(event.position().y())
        t = self.x_to_time(event.position().x())
        if isinstance(tr, LabelTrack):
            for lb in tr.labels:
                if abs(self.time_to_x(lb.start) - event.position().x()) <= 60:
                    self.labelEditRequested.emit(tr.uid, lb.uid)
                    return
        elif isinstance(tr, AudioTrack):
            clip = self._clip_at(tr, t)
            if clip:
                self.project.set_selection(clip.start_time, clip.end_time)
                self.selectionChanged.emit()
                self.update()

    def _show_clip_context_menu(self, tr: AudioTrack, clip: Optional[AudioClip], t: float, global_pos) -> None:
        menu = QMenu(self)
        if clip is not None:
            a_ren = menu.addAction(f"Rename Clip '{clip.name}'...")
            a_col = menu.addAction("Change Clip Color...")
            a_ps = menu.addAction("Clip Pitch, Speed & Stretch...")
            a_split = menu.addAction("Split Clip at Click Position")
            a_reset = menu.addAction("Restore Trimmed Edges")
            a_del = menu.addAction("Delete Clip")
            chosen = menu.exec(global_pos)
            if chosen == a_ren:
                name, ok = QInputDialog.getText(self, "Rename Clip", "Clip Name:", text=clip.name)
                if ok and name.strip():
                    clip.name = name.strip()
                    self.projectModified.emit("Renamed Clip")
            elif chosen == a_col:
                col = QColorDialog.getColor(QColor(clip.color), self, "Clip Color")
                if col.isValid():
                    clip.color = col.name()
                    self.projectModified.emit("Changed Clip Color")
            elif chosen == a_ps:
                val, ok = QInputDialog.getDouble(self, "Clip Pitch Shift", "Pitch Shift (semitones):", clip.pitch_semitones, -24.0, 24.0, 2)
                if ok:
                    clip.pitch_semitones = val
                    st, ok2 = QInputDialog.getDouble(self, "Clip Time Stretch", "Duration Stretch Ratio (1.0 = normal):", clip.stretch_ratio, 0.25, 4.0, 2)
                    if ok2:
                        clip.stretch_ratio = st
                    self.projectModified.emit("Adjusted Clip Pitch/Stretch")
            elif chosen == a_split and self.project:
                self.project.split_at_time(t, tracks=[tr])
                self.projectModified.emit("Split Clip")
            elif chosen == a_reset:
                clip.trim_start = 0
                clip.trim_end = 0
                self.projectModified.emit("Restored Clip Edges")
            elif chosen == a_del:
                tr.clips.remove(clip)
                self.projectModified.emit("Deleted Clip")
            self.invalidate_caches()

    # ---- Painting ----
    def paintEvent(self, event) -> None:
        pal = get_palette(self.theme_name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(pal["bg_base"]))
        self._header_hit_rects.clear()

        if self.project is None:
            p.end()
            return

        if not self.project.tracks:
            p.setPen(QColor(pal["text_muted"]))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drop audio/MIDI files here, click Record, or use Tracks -> Add New")
            p.end()
            return

        for idx, (tr, rect) in enumerate(self._track_rects()):
            if rect.bottom() < 0 or rect.top() > self.height():
                continue
            self._paint_track_header(p, tr, QRectF(0, rect.top(), HEADER_WIDTH, rect.height()), pal)
            lane = QRectF(HEADER_WIDTH, rect.top(), max(10, self.width() - HEADER_WIDTH), rect.height())
            self._paint_track_lane(p, tr, lane, pal, idx % 2 == 1)

        # Global vertical selection, cursor & playhead overlays across lane area
        p.setClipRect(QRectF(HEADER_WIDTH, 0, self.width() - HEADER_WIDTH, self.height()))
        if self.project.has_selection():
            sx0 = self.time_to_x(self.project.sel_start)
            sx1 = self.time_to_x(self.project.sel_end)
            sel_c = QColor(pal["accent"])
            sel_c.setAlpha(42)
            p.fillRect(QRectF(sx0, 0, max(1.0, sx1 - sx0), self.height()), sel_c)
            p.setPen(QPen(QColor(pal["accent"]), 1.2))
            p.drawLine(QPointF(sx0, 0), QPointF(sx0, self.height()))
            p.drawLine(QPointF(sx1, 0), QPointF(sx1, self.height()))
        else:
            cx = self.time_to_x(self.project.cursor_time)
            p.setPen(QPen(QColor(pal["cursor"]), 1.2))
            p.drawLine(QPointF(cx, 0), QPointF(cx, self.height()))

        # Playhead
        px = self.time_to_x(self.playhead_s)
        p.setPen(QPen(QColor(pal["playhead"]), 1.8))
        p.drawLine(QPointF(px, 0), QPointF(px, self.height()))
        p.end()

    def _paint_track_header(self, p: QPainter, tr: BaseTrack, rect: QRectF, pal: Dict[str, str]) -> None:
        p.save()
        bg = QColor(pal["bg_panel"])
        if tr.selected:
            bg = bg.lighter(115) if self.theme_name != "Light" else bg.darker(104)
        p.fillRect(rect, bg)
        # Left accent strip
        strip_col = QColor(tr.color if isinstance(tr, AudioTrack) else (pal["label_border"] if tr.kind == "label" else pal["time_curve"]))
        p.fillRect(QRectF(rect.left(), rect.top(), 4, rect.height()), strip_col)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(pal["accent"] if tr.selected else pal["border"]), 1.2 if tr.selected else 1.0))
        p.drawRect(rect.adjusted(0, 0, -1, -1))

        # Top row: Close [x], Name + Menu [v], Collapse [^/v]
        r_close = QRectF(rect.left() + 8, rect.top() + 6, 18, 18)
        r_menu = QRectF(rect.left() + 28, rect.top() + 5, rect.width() - 56, 20)
        r_coll = QRectF(rect.right() - 24, rect.top() + 6, 18, 18)
        self._header_hit_rects.append((r_close, tr.uid, "close"))
        self._header_hit_rects.append((r_menu, tr.uid, "menu"))
        self._header_hit_rects.append((r_coll, tr.uid, "collapse"))

        p.setFont(QFont("Segoe UI", 8.5, QFont.Weight.Bold))
        p.setPen(QColor(pal["text_muted"]))
        p.drawText(r_close, Qt.AlignmentFlag.AlignCenter, "✕")
        p.setPen(QColor(pal["text"]))
        p.drawText(r_menu, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, f"{tr.name[:18]} ▾")
        p.setPen(QColor(pal["text_muted"]))
        p.drawText(r_coll, Qt.AlignmentFlag.AlignCenter, "▸" if tr.collapsed else "▾")

        if tr.collapsed:
            p.restore()
            return

        if isinstance(tr, AudioTrack):
            # Info line
            p.setFont(QFont("Segoe UI", 7.5))
            p.setPen(QColor(pal["text_muted"]))
            ch_txt = "Stereo" if tr.channels == 2 else "Mono"
            p.drawText(QRectF(rect.left() + 10, rect.top() + 25, rect.width() - 18, 15), f"{ch_txt} · {tr.sample_rate} Hz · {tr.view_mode[:4]}")

            # Mute / Solo / FX pills
            r_mute = QRectF(rect.left() + 10, rect.top() + 44, 48, 22)
            r_solo = QRectF(rect.left() + 62, rect.top() + 44, 48, 22)
            r_fx = QRectF(rect.left() + 114, rect.top() + 44, 52, 22)
            r_sync = QRectF(rect.left() + 170, rect.top() + 44, 34, 22)
            self._header_hit_rects.extend([
                (r_mute, tr.uid, "mute"),
                (r_solo, tr.uid, "solo"),
                (r_fx, tr.uid, "fx"),
                (r_sync, tr.uid, "sync"),
            ])

            def draw_pill(pr: QRectF, txt: str, on: bool, on_col: str) -> None:
                p.setBrush(QColor(on_col) if on else QColor("#222836" if self.theme_name == "Dark" else pal["bg_ruler"]))
                p.setPen(QPen(QColor(on_col if on else pal["border"]), 1))
                p.drawRoundedRect(pr, 4, 4)
                p.setPen(QColor("#0B1218" if on else pal["text"]))
                p.setFont(QFont("Segoe UI", 7.5, QFont.Weight.Bold))
                p.drawText(pr, Qt.AlignmentFlag.AlignCenter, txt)

            draw_pill(r_mute, "Mute", tr.mute, "#F43F5E")
            draw_pill(r_solo, "Solo", tr.solo, "#F59E0B")
            fx_cnt = sum(1 for e in tr.realtime_effects if e.enabled)
            draw_pill(r_fx, f"FX({fx_cnt})" if fx_cnt else "FX", fx_cnt > 0, pal["accent"])
            draw_pill(r_sync, "🔒" if (self.project and self.project.sync_lock and tr.sync_lock) else "🔓", bool(self.project and self.project.sync_lock and tr.sync_lock), pal["accent_alt"])

            # Gain & Pan mini-sliders
            r_gain = QRectF(rect.left() + 46, rect.top() + 76, rect.width() - 60, 14)
            r_pan = QRectF(rect.left() + 46, rect.top() + 98, rect.width() - 60, 14)
            self._header_hit_rects.append((r_gain, tr.uid, "gain_drag"))
            self._header_hit_rects.append((r_pan, tr.uid, "pan_drag"))

            p.setFont(QFont("Segoe UI", 7.2))
            p.setPen(QColor(pal["text_muted"]))
            p.drawText(QRectF(rect.left() + 10, rect.top() + 74, 34, 16), Qt.AlignmentFlag.AlignVCenter, f"{tr.gain_db:+.0f}dB")
            pan_lbl = "C" if abs(tr.pan) < 0.05 else (f"L{int(-tr.pan*100)}" if tr.pan < 0 else f"R{int(tr.pan*100)}")
            p.drawText(QRectF(rect.left() + 10, rect.top() + 96, 34, 16), Qt.AlignmentFlag.AlignVCenter, pan_lbl)

            for srect, norm in [(r_gain, (tr.gain_db + 36.0) / 72.0), (r_pan, (tr.pan + 1.0) / 2.0)]:
                cy = srect.center().y()
                p.setPen(QPen(QColor(pal["border_strong"]), 2.5))
                p.drawLine(QPointF(srect.left(), cy), QPointF(srect.right(), cy))
                kx = srect.left() + np.clip(norm, 0.0, 1.0) * srect.width()
                p.setBrush(QColor(pal["accent"]))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(kx, cy), 5.0, 5.0)

        elif isinstance(tr, LabelTrack):
            p.setFont(QFont("Segoe UI", 7.5))
            p.setPen(QColor(pal["text_muted"]))
            p.drawText(QRectF(rect.left() + 10, rect.top() + 30, rect.width() - 20, 18), f"Label Track · {len(tr.labels)} labels")
            r_ed = QRectF(rect.left() + 10, rect.top() + 48, 90, 20)
            self._header_hit_rects.append((r_ed, tr.uid, "edit_labels"))
            p.setBrush(QColor("#222836" if self.theme_name == "Dark" else pal["bg_ruler"]))
            p.setPen(QColor(pal["border"]))
            p.drawRoundedRect(r_ed, 4, 4)
            p.setPen(QColor(pal["text"]))
            p.drawText(r_ed, Qt.AlignmentFlag.AlignCenter, "Edit Table...")

        elif isinstance(tr, TimeTrack):
            p.setFont(QFont("Segoe UI", 7.5))
            p.setPen(QColor(pal["time_curve"]))
            p.drawText(QRectF(rect.left() + 10, rect.top() + 30, rect.width() - 20, 32), f"Speed Warp\n{int(tr.min_speed*100)}% – {int(tr.max_speed*100)}%")

        elif isinstance(tr, NoteTrack):
            p.setFont(QFont("Segoe UI", 7.5))
            p.setPen(QColor(pal["accent"]))
            p.drawText(QRectF(rect.left() + 10, rect.top() + 28, rect.width() - 20, 18), f"MIDI Note Track · {len(tr.notes)} notes")
            r_mute = QRectF(rect.left() + 10, rect.top() + 50, 48, 22)
            r_solo = QRectF(rect.left() + 62, rect.top() + 50, 48, 22)
            self._header_hit_rects.extend([(r_mute, tr.uid, "mute"), (r_solo, tr.uid, "solo")])
            for pr, txt, on, col in [(r_mute, "Mute", tr.mute, "#F43F5E"), (r_solo, "Solo", tr.solo, "#F59E0B")]:
                p.setBrush(QColor(col) if on else QColor("#222836" if self.theme_name == "Dark" else pal["bg_ruler"]))
                p.setPen(QColor(col if on else pal["border"]))
                p.drawRoundedRect(pr, 4, 4)
                p.setPen(QColor("#0B1218" if on else pal["text"]))
                p.drawText(pr, Qt.AlignmentFlag.AlignCenter, txt)
        p.restore()

    def _paint_track_lane(self, p: QPainter, tr: BaseTrack, lane: QRectF, pal: Dict[str, str], alt: bool) -> None:
        p.save()
        p.setClipRect(lane)
        p.fillRect(lane, QColor(pal["bg_track_alt"] if alt else pal["bg_track"]))

        # Vertical beats/measures grid lines inside tracks
        if self.project and self.project.show_beats_grid:
            beat_s = 60.0 / max(20.0, self.project.bpm)
            b0 = max(0, int(math.floor(self.scroll_x_s / beat_s)))
            b1 = int(math.ceil(self.x_to_time(lane.right()) / beat_s)) + 1
            for b in range(b0, b1):
                gx = self.time_to_x(b * beat_s)
                is_bar = (b % max(1, self.project.time_sig_num)) == 0
                p.setPen(QPen(QColor(pal["grid_major"] if is_bar else pal["grid_minor"]), 1))
                p.drawLine(QPointF(gx, lane.top()), QPointF(gx, lane.bottom()))

        if isinstance(tr, AudioTrack):
            self._paint_audio_track(p, tr, lane, pal)
        elif isinstance(tr, LabelTrack):
            self._paint_label_track(p, tr, lane, pal)
        elif isinstance(tr, TimeTrack):
            self._paint_time_track(p, tr, lane, pal)
        elif isinstance(tr, NoteTrack):
            self._paint_note_track(p, tr, lane, pal)

        p.setPen(QPen(QColor(pal["border"]), 1))
        p.drawLine(QPointF(lane.left(), lane.bottom()), QPointF(lane.right(), lane.bottom()))
        p.restore()

    def _paint_audio_track(self, p: QPainter, tr: AudioTrack, lane: QRectF, pal: Dict[str, str]) -> None:
        for clip in tr.clips:
            cx0 = self.time_to_x(clip.start_time)
            cx1 = self.time_to_x(clip.end_time)
            if cx1 < lane.left() or cx0 > lane.right():
                continue
            vis_x0 = max(lane.left(), cx0)
            vis_x1 = min(lane.right(), cx1)
            if vis_x1 - vis_x0 < 1:
                continue

            # Clip background & header bar
            header_h = 18 if not tr.collapsed else 0
            clip_rect = QRectF(cx0, lane.top() + 1, max(2.0, cx1 - cx0), lane.height() - 2)
            p.fillRect(clip_rect, QColor(pal["bg_clip"]))

            if header_h > 0:
                hdr_rect = QRectF(cx0, lane.top() + 1, max(2.0, cx1 - cx0), header_h)
                hdr_col = QColor(clip.color)
                hdr_col.setAlpha(60)
                p.fillRect(hdr_rect, hdr_col)
                p.setPen(QColor(pal["text"]))
                p.setFont(QFont("Segoe UI", 7.5, QFont.Weight.DemiBold))
                badges = []
                if abs(clip.pitch_semitones) > 0.05:
                    badges.append(f"{clip.pitch_semitones:+.1f}st")
                if abs(clip.stretch_ratio - 1.0) > 0.02:
                    badges.append(f"{clip.stretch_ratio:.2f}x")
                title = clip.name + (f" [{', '.join(badges)}]" if badges else "")
                p.drawText(hdr_rect.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, title)

            body = QRectF(cx0, lane.top() + 1 + header_h, max(2.0, cx1 - cx0), max(4.0, lane.height() - 2 - header_h))

            if tr.view_mode == "Spectrogram":
                self._paint_clip_spectrogram(p, tr, clip, body)
            elif tr.view_mode == "Split View":
                top_half = QRectF(body.left(), body.top(), body.width(), body.height() * 0.5)
                bot_half = QRectF(body.left(), body.top() + body.height() * 0.5, body.width(), body.height() * 0.5)
                self._paint_clip_waveform(p, tr, clip, top_half, pal, db_mode=False)
                self._paint_clip_spectrogram(p, tr, clip, bot_half)
            else:
                self._paint_clip_waveform(p, tr, clip, body, pal, db_mode=(tr.view_mode == "Waveform (dB)"))

            # Volume envelope overlay
            if clip.envelope_points and not tr.collapsed:
                pts = sorted(clip.envelope_points, key=lambda pt: pt[0])
                p.setPen(QPen(QColor(pal["envelope"]), 1.6))
                mid_y = body.center().y()
                half_h = body.height() * 0.45
                for sign in (-1.0, 1.0):
                    path = QPainterPath()
                    for i, (et, eg) in enumerate(pts):
                        ex = self.time_to_x(clip.start_time + et)
                        ey = mid_y + sign * min(1.0, eg) * half_h
                        if i == 0:
                            path.moveTo(ex, ey)
                        else:
                            path.lineTo(ex, ey)
                    p.drawPath(path)
                p.setBrush(QColor(pal["envelope"]))
                for et, eg in pts:
                    ex = self.time_to_x(clip.start_time + et)
                    for sign in (-1.0, 1.0):
                        ey = mid_y + sign * min(1.0, eg) * half_h
                        p.drawEllipse(QPointF(ex, ey), 3.5, 3.5)

            # Clip border
            p.setPen(QPen(QColor(clip.color), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(clip_rect)

        # Spectral selection box overlay
        if self.project and self.project.spectral_low_hz is not None and self.project.spectral_high_hz is not None and tr.view_mode in ("Spectrogram", "Split View"):
            sx0 = self.time_to_x(self.project.sel_start)
            sx1 = self.time_to_x(self.project.sel_end)
            header_h = 18 if not tr.collapsed else 0
            top = lane.top() + header_h + ((lane.height() - header_h) * 0.5 if tr.view_mode == "Split View" else 0)
            h = (lane.height() - header_h) * (0.5 if tr.view_mode == "Split View" else 1.0)
            y_hi = self._freq_to_y(self.project.spectral_high_hz, top, h, tr)
            y_lo = self._freq_to_y(self.project.spectral_low_hz, top, h, tr)
            sbox = QRectF(sx0, min(y_hi, y_lo), max(2.0, sx1 - sx0), max(2.0, abs(y_lo - y_hi)))
            p.fillRect(sbox, QColor(pal["bg_spectral_sel"]))
            p.setPen(QPen(QColor(pal["accent_alt"]), 1.4, Qt.PenStyle.DashLine))
            p.drawRect(sbox)

    def _paint_clip_waveform(self, p: QPainter, tr: AudioTrack, clip: AudioClip, body: QRectF, pal: Dict[str, str], db_mode: bool = False) -> None:
        vis = clip.visible_samples()
        n = vis.shape[1]
        if n == 0 or body.width() < 1:
            return
        ch_count = min(2, vis.shape[0])
        ch_h = body.height() / ch_count

        vis_x0 = max(HEADER_WIDTH, int(math.floor(body.left())))
        vis_x1 = min(self.width(), int(math.ceil(body.right())))
        if vis_x1 <= vis_x0:
            return

        peak_col = QColor(clip.color)
        rms_col = QColor(pal["wave_rms"])
        rms_col.setAlpha(185)
        clip_col = QColor(pal["clip_red"])

        eff_sr = clip.sample_rate * max(0.05, clip.speed_ratio) / max(0.05, clip.stretch_ratio)

        for ch in range(ch_count):
            y_top = body.top() + ch * ch_h
            mid = y_top + ch_h * 0.5
            amp_scale = ch_h * 0.46
            p.setPen(QPen(QColor(pal["center_line"]), 1))
            p.drawLine(QPointF(vis_x0, mid), QPointF(vis_x1, mid))

            samples = vis[ch]
            # Sample-dot draw mode when zoomed in very closely
            if self.pps >= 8000:
                i0 = max(0, int((self.x_to_time(vis_x0) - clip.start_time) * eff_sr))
                i1 = min(n, int((self.x_to_time(vis_x1) - clip.start_time) * eff_sr) + 2)
                p.setPen(QPen(peak_col, 1.3))
                prev_pt = None
                for idx in range(i0, i1):
                    sx = self.time_to_x(clip.start_time + idx / eff_sr)
                    sy = mid - float(samples[idx]) * amp_scale
                    pt = QPointF(sx, sy)
                    if prev_pt is not None:
                        p.drawLine(prev_pt, pt)
                    p.setBrush(QColor(pal["accent_alt"]))
                    p.drawEllipse(pt, 2.5, 2.5)
                    prev_pt = pt
                continue

            # Vectorized NumPy + cached peak/RMS waveform rendering (60 FPS smooth)
            eff_len = max(1, vis_x1 - vis_x0)
            i_start = max(0, min(n - 1, int((self.x_to_time(vis_x0) - clip.start_time) * eff_sr)))
            i_end = max(i_start + 1, min(n, int((self.x_to_time(vis_x1) - clip.start_time) * eff_sr)))
            cache_key = (clip.uid, ch, i_start, i_end, eff_len, int(ch_h), db_mode, tr.show_clipping, clip.color, self.theme_name)
            cached = self._wave_cache.get(cache_key)
            if cached is None:
                if len(self._wave_cache) > 96:
                    self._wave_cache.clear()
                sub = samples[i_start:i_end]
                cols = min(eff_len, max(1, len(sub)))
                # Fast vectorized binning into `cols` columns
                if len(sub) >= cols * 2:
                    trim_n = (len(sub) // cols) * cols
                    blk = sub[:trim_n].reshape(cols, -1)
                    his = np.max(blk, axis=1)
                    los = np.min(blk, axis=1)
                    rmss = np.sqrt(np.mean(blk * blk, axis=1))
                else:
                    idx_map = np.linspace(0, max(0, len(sub) - 1), cols).astype(np.int64)
                    vals = sub[idx_map]
                    his = np.maximum(vals, 0.0)
                    los = np.minimum(vals, 0.0)
                    rmss = np.abs(vals) * 0.65
                xs_arr = np.linspace(vis_x0, vis_x1 - 1, cols)
                clipped_mask = tr.show_clipping and ((his >= 0.995) | (los <= -0.995))
                if db_mode:
                    def _vec_db(v: np.ndarray) -> np.ndarray:
                        db = np.clip(20.0 * np.log10(np.maximum(np.abs(v), 1e-3)), -60.0, 0.0)
                        return ((db + 60.0) / 60.0) * np.sign(v)
                    y_his = mid - _vec_db(his) * amp_scale
                    y_los = mid - _vec_db(los) * amp_scale
                    y_rmss = np.abs(_vec_db(rmss)) * amp_scale
                else:
                    y_his = mid - np.clip(his, -1.0, 1.0) * amp_scale
                    y_los = mid - np.clip(los, -1.0, 1.0) * amp_scale
                    y_rmss = np.clip(rmss, 0.0, 1.0) * amp_scale
                # Build QPainterPath polygons for single-call GPU-accelerated draw
                poly_pk = QPolygonF()
                poly_rms = QPolygonF()
                for k in range(cols):
                    poly_pk.append(QPointF(float(xs_arr[k]), float(y_his[k])))
                for k in range(cols - 1, -1, -1):
                    poly_pk.append(QPointF(float(xs_arr[k]), float(y_los[k])))
                for k in range(cols):
                    poly_rms.append(QPointF(float(xs_arr[k]), float(mid - y_rmss[k])))
                for k in range(cols - 1, -1, -1):
                    poly_rms.append(QPointF(float(xs_arr[k]), float(mid + y_rmss[k])))
                clip_xs = xs_arr[clipped_mask] if isinstance(clipped_mask, np.ndarray) else np.array([])
                cached = (poly_pk, poly_rms, clip_xs, y_top, ch_h)
                self._wave_cache[cache_key] = cached

            poly_pk, poly_rms, clip_xs, _, _ = cached
            fill_pk = QColor(peak_col)
            fill_pk.setAlpha(195)
            p.setPen(QPen(peak_col, 1.0))
            p.setBrush(QBrush(fill_pk))
            p.drawPolygon(poly_pk)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(rms_col))
            p.drawPolygon(poly_rms)
            if len(clip_xs) > 0:
                p.setPen(QPen(clip_col, 1.2))
                for cx in clip_xs:
                    p.drawLine(QPointF(float(cx), y_top + 2), QPointF(float(cx), y_top + ch_h - 2))

    def _paint_clip_spectrogram(self, p: QPainter, tr: AudioTrack, clip: AudioClip, body: QRectF) -> None:
        cfg = tr.spectrogram
        key = (clip.uid, cfg.window_size, cfg.window_type, cfg.color_scheme, cfg.freq_scale, clip.visible_sample_count)
        img = self._spec_cache.get(key)
        if img is None:
            vis = clip.visible_samples()
            db, freqs = compute_spectrogram_db(vis, clip.sample_rate, window_size=cfg.window_size, window_type=cfg.window_type, max_cols=700)
            # Map frequency bins to display rows (default log-friendly slice up to max_freq so musical lows/mids shine)
            f_hi = min(clip.sample_rate / 2.0, max(1000.0, cfg.max_freq))
            f_lo = max(20.0, cfg.min_freq)
            n_rows = 128
            if cfg.freq_scale in ("Logarithmic", "Mel", "Bark", "ERB"):
                target_f = np.geomspace(f_lo, f_hi, n_rows)
            else:
                target_f = np.linspace(f_lo, f_hi, n_rows)
            bin_idx = np.clip(np.searchsorted(freqs, target_f), 0, db.shape[0] - 1)
            mapped = db[bin_idx, :]
            # Auto-lift relative to peak so musical audio renders richly
            pk = float(np.max(mapped)) if mapped.size else 0.0
            norm = np.clip((mapped - (pk - cfg.range_db) + (cfg.gain_db - 20.0)) / max(10.0, cfg.range_db), 0.0, 1.0)
            idx = (norm[::-1, :] * 255.0).astype(np.uint8)
            lut = get_colormap(cfg.color_scheme)
            rgb = np.ascontiguousarray(lut[idx])
            h, w, _ = rgb.shape
            img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            self._spec_cache[key] = img
        p.drawImage(body, img)

    def _paint_label_track(self, p: QPainter, tr: LabelTrack, lane: QRectF, pal: Dict[str, str]) -> None:
        p.setFont(QFont("Segoe UI", 8))
        for lb in tr.labels:
            x0 = self.time_to_x(lb.start)
            x1 = self.time_to_x(lb.end)
            if x1 + 90 < lane.left() or x0 - 10 > lane.right():
                continue
            p.setPen(QPen(QColor(pal["label_border"]), 1.6))
            p.drawLine(QPointF(x0, lane.top() + 4), QPointF(x0, lane.bottom() - 4))
            if x1 > x0 + 3:
                p.drawLine(QPointF(x1, lane.top() + 4), QPointF(x1, lane.bottom() - 4))
                p.drawLine(QPointF(x0, lane.top() + 14), QPointF(x1, lane.top() + 14))
            box_w = max(58.0, x1 - x0, len(lb.text) * 7.2 + 14)
            box = QRectF(x0, lane.top() + 18, box_w, 24)
            p.fillRect(box, QColor(pal["label_fill"]))
            p.setPen(QPen(QColor(pal["label_border"]), 1.1))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(QColor(pal["text"]))
            p.drawText(box.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, lb.text or "Label")

    def _paint_time_track(self, p: QPainter, tr: TimeTrack, lane: QRectF, pal: Dict[str, str]) -> None:
        # 100% baseline
        norm_1 = (1.0 - tr.min_speed) / max(0.01, tr.max_speed - tr.min_speed)
        y_1 = lane.bottom() - norm_1 * (lane.height() - 16) - 8
        p.setPen(QPen(QColor(pal["grid_major"]), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(lane.left(), y_1), QPointF(lane.right(), y_1))

        pts = sorted(tr.points, key=lambda pt: pt[0])
        if not pts:
            return
        p.setPen(QPen(QColor(pal["time_curve"]), 2.0))
        path = QPainterPath()
        for i, (pt, pv) in enumerate(pts):
            px = self.time_to_x(pt)
            py = lane.bottom() - ((pv - tr.min_speed) / max(0.01, tr.max_speed - tr.min_speed)) * (lane.height() - 16) - 8
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        p.drawPath(path)
        p.setBrush(QColor(pal["time_curve"]))
        for pt, pv in pts:
            px = self.time_to_x(pt)
            py = lane.bottom() - ((pv - tr.min_speed) / max(0.01, tr.max_speed - tr.min_speed)) * (lane.height() - 16) - 8
            p.drawEllipse(QPointF(px, py), 4.0, 4.0)

    def _paint_note_track(self, p: QPainter, tr: NoteTrack, lane: QRectF, pal: Dict[str, str]) -> None:
        if not tr.notes:
            p.setPen(QColor(pal["text_muted"]))
            p.drawText(lane, Qt.AlignmentFlag.AlignCenter, "Empty MIDI Note Track (Import .mid to populate)")
            return
        p_min = max(0, min(n.pitch for n in tr.notes) - 4)
        p_max = min(127, max(n.pitch for n in tr.notes) + 4)
        span = max(12, p_max - p_min)
        row_h = max(3.5, (lane.height() - 10) / span)
        for n in tr.notes:
            x0 = self.time_to_x(n.start)
            x1 = max(x0 + 4.0, self.time_to_x(n.end))
            if x1 < lane.left() or x0 > lane.right():
                continue
            y = lane.bottom() - 5 - (n.pitch - p_min) * row_h
            col = QColor(pal["midi_note"])
            col.setAlpha(int(120 + (n.velocity / 127.0) * 135))
            p.fillRect(QRectF(x0, y - row_h, x1 - x0, max(3.0, row_h - 1)), col)
            p.setPen(QPen(QColor(pal["accent_alt"]), 0.8))
            p.drawRect(QRectF(x0, y - row_h, x1 - x0, max(3.0, row_h - 1)))


# ---------------------------------------------------------------------------
# Bottom Selection & Precision Time Bar (Audacity-style)
# ---------------------------------------------------------------------------
class SelectionStatusBar(QWidget):
    sampleRateChanged = Signal(int)
    snapChanged = Signal(str, str)
    selectionEdited = Signal(float, float)
    formatChanged = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SelectionBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(44)
        self.project: Optional[KinoWaveProject] = None
        self._updating = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Rate:"))
        self.cmb_sr = QComboBox()
        for r in SAMPLE_RATES:
            self.cmb_sr.addItem(f"{r} Hz", r)
        self.cmb_sr.setCurrentText("48000 Hz")
        self.cmb_sr.currentIndexChanged.connect(lambda: self.sampleRateChanged.emit(int(self.cmb_sr.currentData())))
        lay.addWidget(self.cmb_sr)

        lay.addWidget(QLabel("Snap:"))
        self.cmb_snap = QComboBox()
        self.cmb_snap.addItems(["Off", "Nearest", "Prior"])
        self.cmb_snap.currentTextChanged.connect(lambda: self.snapChanged.emit(self.cmb_snap.currentText(), self.cmb_unit.currentText()))
        lay.addWidget(self.cmb_snap)

        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(SNAP_UNITS)
        self.cmb_unit.currentTextChanged.connect(lambda: self.snapChanged.emit(self.cmb_snap.currentText(), self.cmb_unit.currentText()))
        lay.addWidget(self.cmb_unit)

        lay.addWidget(QLabel("Start:"))
        self.ed_start = QLineEdit("00:00:00.000")
        self.ed_start.setFixedWidth(112)
        self.ed_start.editingFinished.connect(self._apply_edits)
        lay.addWidget(self.ed_start)

        self.cmb_end_mode = QComboBox()
        self.cmb_end_mode.addItems(["End", "Length", "Center"])
        self.cmb_end_mode.setFixedWidth(74)
        self.cmb_end_mode.currentTextChanged.connect(self.refresh_from_project)
        lay.addWidget(self.cmb_end_mode)

        self.ed_end = QLineEdit("00:00:00.000")
        self.ed_end.setFixedWidth(112)
        self.ed_end.editingFinished.connect(self._apply_edits)
        lay.addWidget(self.ed_end)

        lay.addWidget(QLabel("Format:"))
        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItems(TIME_FORMATS)
        self.cmb_fmt.currentTextChanged.connect(self._on_fmt_changed)
        lay.addWidget(self.cmb_fmt)

        lay.addWidget(QLabel("Pos:"))
        self.lbl_pos = QLabel("00:00:00.000")
        self.lbl_pos.setStyleSheet("font-family: Consolas, monospace; font-weight: 700; color: #10D9A0;")
        lay.addWidget(self.lbl_pos)

        lay.addStretch(1)

    def _on_fmt_changed(self, fmt: str) -> None:
        if self.project:
            self.project.time_format = fmt
        self.formatChanged.emit(fmt)
        self.refresh_from_project()

    def set_project(self, proj: KinoWaveProject) -> None:
        self.project = proj
        self._updating = True
        idx = self.cmb_sr.findData(proj.sample_rate)
        if idx >= 0:
            self.cmb_sr.setCurrentIndex(idx)
        self.cmb_snap.setCurrentText(proj.snap_mode)
        self.cmb_unit.setCurrentText(proj.snap_unit)
        self.cmb_fmt.setCurrentText(proj.time_format)
        self._updating = False
        self.refresh_from_project()

    def refresh_from_project(self, playhead_s: Optional[float] = None) -> None:
        if not self.project or self._updating:
            return
        p = self.project
        self._updating = True
        fmt = p.time_format
        self.ed_start.setText(format_time(p.sel_start, fmt, p.sample_rate, p.bpm, p.time_sig_num))
        mode = self.cmb_end_mode.currentText()
        if mode == "Length":
            val = max(0.0, p.sel_end - p.sel_start)
        elif mode == "Center":
            val = 0.5 * (p.sel_start + p.sel_end)
        else:
            val = p.sel_end
        self.ed_end.setText(format_time(val, fmt, p.sample_rate, p.bpm, p.time_sig_num))
        pos_t = p.cursor_time if playhead_s is None else playhead_s
        self.lbl_pos.setText(format_time(pos_t, fmt, p.sample_rate, p.bpm, p.time_sig_num))
        self._updating = False

    def _apply_edits(self) -> None:
        if not self.project or self._updating:
            return
        p = self.project
        s0 = parse_time(self.ed_start.text(), p.time_format, p.sample_rate, p.bpm, p.time_sig_num)
        v1 = parse_time(self.ed_end.text(), p.time_format, p.sample_rate, p.bpm, p.time_sig_num)
        mode = self.cmb_end_mode.currentText()
        if mode == "Length":
            s1 = s0 + max(0.0, v1)
        elif mode == "Center":
            half = abs(v1 - s0)
            s1 = v1 + half
        else:
            s1 = v1
        self.selectionEdited.emit(min(s0, s1), max(s0, s1))
