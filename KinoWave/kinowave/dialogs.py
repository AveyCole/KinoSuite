"""KinoWave Studio Dialogs — KinoSuite Architectural Style.

Covers Effects (with 31-Band Graphic EQ, Filter Curve EQ, 2-Step Noise Reduction,
Presets & Live Preview), Real-Time FX Rack, Generators, Plot Spectrum, WCAG
Contrast Analysis, Label Table Editor, Multi-Format/Multiple Export, Metadata &
Tag Templates, Raw Import, Timer Record, Undo History Browser, Spectrogram
Settings, Macro & Batch Processor, Nyquist Prompt, Plugin Manager, Scripting
Pipe, Preferences & Shortcuts, KinoCloud Share, Diagnostics/Logs, and Manual.
"""
from __future__ import annotations

import datetime
import json
import math
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .audio_io import (
    EXPORT_FORMATS,
    KinoCloudAudioManager,
    export_audio_file,
    export_labels_txt,
    find_ffmpeg,
    get_audio_device_diagnostics,
    import_audio_file,
    import_labels_txt,
    list_audio_devices,
    list_audio_hosts,
    save_kwp,
)
from .automation import (
    DEFAULT_SHORTCUTS,
    MacroManager,
    NyquistInterpreter,
    PluginManager,
    PreferencesManager,
    ScriptingPipeServer,
    TRANSLATIONS,
)
from .dsp import (
    EFFECT_REGISTRY,
    ISO_31_BANDS,
    PresetManager,
    compute_spectrum,
    default_effect_params,
    run_effect,
    wcag_contrast,
)
from .models import (
    AudioTrack,
    EffectSlot,
    KinoWaveProject,
    LabelItem,
    LabelTrack,
    ProjectMetadata,
    SAMPLE_FORMATS,
    SAMPLE_RATES,
    SPECTROGRAM_COLORMAPS,
    SPECTROGRAM_SCALES,
    SPECTROGRAM_WINDOWS,
    SpectrogramConfig,
)


# ---------------------------------------------------------------------------
# Interactive Filter Curve EQ Canvas
# ---------------------------------------------------------------------------
class FilterCurveWidget(QWidget):
    def __init__(self, points: List[Tuple[float, float]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.points: List[Tuple[float, float]] = sorted([(float(f), float(g)) for f, g in points], key=lambda p: p[0])
        self.setMinimumSize(460, 210)
        self._drag_idx: int = -1

    def _f_to_x(self, f: float) -> float:
        lo, hi = math.log10(20.0), math.log10(20000.0)
        frac = (math.log10(max(20.0, min(20000.0, f))) - lo) / (hi - lo)
        return 36.0 + frac * max(10.0, self.width() - 52.0)

    def _x_to_f(self, x: float) -> float:
        lo, hi = math.log10(20.0), math.log10(20000.0)
        frac = np.clip((x - 36.0) / max(10.0, self.width() - 52.0), 0.0, 1.0)
        return float(10.0 ** (lo + frac * (hi - lo)))

    def _g_to_y(self, g: float) -> float:
        frac = (20.0 - np.clip(g, -20.0, 20.0)) / 40.0
        return 14.0 + frac * max(10.0, self.height() - 36.0)

    def _y_to_g(self, y: float) -> float:
        frac = np.clip((y - 14.0) / max(10.0, self.height() - 36.0), 0.0, 1.0)
        return float(round(20.0 - frac * 40.0, 1))

    def mousePressEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        for i, (f, g) in enumerate(self.points):
            if math.hypot(self._f_to_x(f) - x, self._g_to_y(g) - y) <= 10:
                if event.button() == Qt.MouseButton.RightButton and len(self.points) > 2:
                    self.points.pop(i)
                    self.update()
                    return
                self._drag_idx = i
                return
        if event.button() == Qt.MouseButton.LeftButton:
            nf, ng = self._x_to_f(x), self._y_to_g(y)
            self.points.append((nf, ng))
            self.points.sort(key=lambda p: p[0])
            self._drag_idx = min(range(len(self.points)), key=lambda i: abs(self.points[i][0] - nf))
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if 0 <= self._drag_idx < len(self.points):
            nf, ng = self._x_to_f(event.position().x()), self._y_to_g(event.position().y())
            self.points[self._drag_idx] = (nf, ng)
            self.points.sort(key=lambda p: p[0])
            self._drag_idx = min(range(len(self.points)), key=lambda i: abs(self.points[i][0] - nf))
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_idx = -1

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0E1219"))
        p.setPen(QPen(QColor("#2A3242"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.setFont(QFont("Segoe UI", 7))
        for g in (-20, -10, 0, 10, 20):
            y = self._g_to_y(g)
            p.setPen(QPen(QColor("#384357" if g == 0 else "#1E2533"), 1))
            p.drawLine(QPointF(36, y), QPointF(self.width() - 16, y))
            p.setPen(QColor("#8D99AE"))
            p.drawText(QRectF(2, y - 7, 30, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{g:+d}")
        for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
            x = self._f_to_x(f)
            p.setPen(QPen(QColor("#1E2533"), 1))
            p.drawLine(QPointF(x, 14), QPointF(x, self.height() - 22))
            p.setPen(QColor("#8D99AE"))
            lbl = f"{f // 1000}k" if f >= 1000 else str(f)
            p.drawText(QRectF(x - 16, self.height() - 20, 32, 16), Qt.AlignmentFlag.AlignCenter, lbl)
        if self.points:
            path = QPainterPath()
            for i, (f, g) in enumerate(self.points):
                pt = QPointF(self._f_to_x(f), self._g_to_y(g))
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            p.setPen(QPen(QColor("#10D9A0"), 2.2))
            p.drawPath(path)
            p.setBrush(QColor("#22D3EE"))
            for f, g in self.points:
                p.drawEllipse(QPointF(self._f_to_x(f), self._g_to_y(g)), 4.5, 4.5)
        p.end()


# ---------------------------------------------------------------------------
# Unified Effect Dialog (All 45 Effects + Presets + Preview + Noise Profile)
# ---------------------------------------------------------------------------
class EffectDialog(QDialog):
    def __init__(
        self,
        effect_name: str,
        preset_mgr: PresetManager,
        initial_params: Optional[Dict[str, Any]] = None,
        on_preview: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_get_noise_profile: Optional[Callable[[], None]] = None,
        has_noise_profile: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.effect_name = effect_name
        self.preset_mgr = preset_mgr
        self.on_preview = on_preview
        self.on_get_noise_profile = on_get_noise_profile
        self.spec = EFFECT_REGISTRY[effect_name]
        self.params = default_effect_params(effect_name)
        if initial_params:
            self.params.update(initial_params)
        self.widgets: Dict[str, Any] = {}

        self.setWindowTitle(f"Effect — {effect_name}")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)

        # Presets bar
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Preset:"))
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(self.preset_mgr.list_presets(effect_name))
        self.cmb_preset.currentTextChanged.connect(self._load_preset)
        prow.addWidget(self.cmb_preset, 1)
        btn_save_p = QPushButton("Save Preset...")
        btn_save_p.clicked.connect(self._save_preset)
        btn_reset = QPushButton("Reset")
        btn_reset.clicked.connect(self._reset_defaults)
        prow.addWidget(btn_save_p)
        prow.addWidget(btn_reset)
        lay.addLayout(prow)

        # Noise Reduction Step 1 helper
        if effect_name == "Noise Reduction":
            box = QGroupBox("Step 1: Noise Profile")
            bl = QHBoxLayout(box)
            self.lbl_np = QLabel("Noise profile captured." if has_noise_profile else "Select a noise-only region and click Get Noise Profile (or auto-detect).")
            btn_np = QPushButton("Get Noise Profile")
            btn_np.clicked.connect(self._capture_np)
            bl.addWidget(self.lbl_np, 1)
            bl.addWidget(btn_np)
            lay.addWidget(box)

        # Parameters form / custom UI
        form = QFormLayout()
        for key, label, wtype, default, mn, mx, step in self.spec["params"]:
            val = self.params.get(key, default)
            if wtype == "float":
                sb = QDoubleSpinBox()
                sb.setRange(float(mn), float(mx))
                sb.setSingleStep(float(step))
                sb.setDecimals(2)
                sb.setValue(float(val))
                self.widgets[key] = sb
                form.addRow(label, sb)
            elif wtype == "int":
                sb = QSpinBox()
                sb.setRange(int(mn), int(mx))
                sb.setSingleStep(int(step))
                sb.setValue(int(val))
                self.widgets[key] = sb
                form.addRow(label, sb)
            elif wtype == "bool":
                cb = QCheckBox(label)
                cb.setChecked(bool(val))
                self.widgets[key] = cb
                form.addRow("", cb)
            elif wtype == "choice":
                cb = QComboBox()
                for opt in step:
                    cb.addItem(str(opt), opt)
                idx = cb.findData(val)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                self.widgets[key] = cb
                form.addRow(label, cb)
            elif wtype == "graphic_eq":
                # 31-band ISO vertical slider bank
                eq_box = QGroupBox("31-Band Graphic EQ (-20 dB to +20 dB)")
                eq_h = QHBoxLayout(eq_box)
                eq_h.setSpacing(3)
                sliders = []
                gains = list(val) if isinstance(val, list) else [0.0] * 31
                for i, hz in enumerate(ISO_31_BANDS):
                    col = QVBoxLayout()
                    sl = QSlider(Qt.Orientation.Vertical)
                    sl.setRange(-200, 200)
                    sl.setValue(int(round((gains[i] if i < len(gains) else 0.0) * 10)))
                    sl.setFixedHeight(140)
                    lbl = QLabel(f"{int(hz // 1000)}k" if hz >= 1000 else f"{int(hz)}")
                    lbl.setStyleSheet("font-size: 7pt; color: #8D99AE;")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    col.addWidget(sl, 0, Qt.AlignmentFlag.AlignHCenter)
                    col.addWidget(lbl)
                    eq_h.addLayout(col)
                    sliders.append(sl)
                self.widgets[key] = sliders
                lay.addWidget(eq_box)
            elif wtype == "filter_curve":
                fc_box = QGroupBox("Filter Curve EQ (Click to add/drag points, Right-click to remove)")
                fcl = QVBoxLayout(fc_box)
                fcw = FilterCurveWidget(val)
                fcl.addWidget(fcw)
                self.widgets[key] = fcw
                lay.addWidget(fc_box)

        if form.rowCount() > 0:
            lay.addLayout(form)
        elif not self.spec["params"]:
            lay.addWidget(QLabel(f"Apply {effect_name} to the current selection."))

        # Action buttons
        brow = QHBoxLayout()
        if self.on_preview:
            btn_prev = QPushButton("Preview")
            btn_prev.clicked.connect(lambda: self.on_preview(self.get_params()))
            brow.addWidget(btn_prev)
        brow.addStretch(1)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Apply")
        btn_ok.setObjectName("PrimaryButton")
        btn_ok.clicked.connect(self.accept)
        brow.addWidget(btn_cancel)
        brow.addWidget(btn_ok)
        lay.addLayout(brow)

    def _capture_np(self) -> None:
        if self.on_get_noise_profile:
            self.on_get_noise_profile()
            self.lbl_np.setText("Noise profile captured from current selection!")

    def _apply_params_to_widgets(self, params: Dict[str, Any]) -> None:
        for key, _lbl, wtype, default, *_ in self.spec["params"]:
            val = params.get(key, default)
            w = self.widgets.get(key)
            if w is None:
                continue
            if wtype == "float":
                w.setValue(float(val))
            elif wtype == "int":
                w.setValue(int(val))
            elif wtype == "bool":
                w.setChecked(bool(val))
            elif wtype == "choice":
                idx = w.findData(val)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            elif wtype == "graphic_eq" and isinstance(val, list):
                for i, sl in enumerate(w):
                    sl.setValue(int(round((val[i] if i < len(val) else 0.0) * 10)))
            elif wtype == "filter_curve" and isinstance(val, list):
                w.points = sorted([(float(f), float(g)) for f, g in val], key=lambda p: p[0])
                w.update()

    def _load_preset(self, name: str) -> None:
        self._apply_params_to_widgets(self.preset_mgr.get_preset(self.effect_name, name))

    def _reset_defaults(self) -> None:
        self._apply_params_to_widgets(default_effect_params(self.effect_name))

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset Name:")
        if ok and name.strip():
            self.preset_mgr.save_preset(self.effect_name, name.strip(), self.get_params())
            if self.cmb_preset.findText(name.strip()) < 0:
                self.cmb_preset.addItem(name.strip())
            self.cmb_preset.setCurrentText(name.strip())

    def get_params(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, _lbl, wtype, *_ in self.spec["params"]:
            w = self.widgets.get(key)
            if wtype == "float":
                out[key] = float(w.value())
            elif wtype == "int":
                out[key] = int(w.value())
            elif wtype == "bool":
                out[key] = bool(w.isChecked())
            elif wtype == "choice":
                out[key] = w.currentData()
            elif wtype == "graphic_eq":
                out[key] = [sl.value() / 10.0 for sl in w]
            elif wtype == "filter_curve":
                out[key] = list(w.points)
        return out


# ---------------------------------------------------------------------------
# External VST3 / VST2 / Audio Unit Plugin Dialog (Native Vendor UI + Parameters + Preview)
# ---------------------------------------------------------------------------
class _VST2NativeEditorDialog(QDialog):
    """Hosts a native Win32 HWND VST2 plugin GUI inside a clean KinoSuite dialog."""

    def __init__(self, vst_inst: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.vst_inst = vst_inst
        self.setWindowTitle(f"{vst_inst.name} — Native VST2 Editor")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.host_widget = QWidget(self)
        self.host_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        lay.addWidget(self.host_widget, 1)
        w, h = vst_inst.open_editor_in_hwnd(int(self.host_widget.winId()))
        self.resize(max(320, w), max(200, h))
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(40)
        self._idle_timer.timeout.connect(self.vst_inst.idle_editor)
        self._idle_timer.start()

    def closeEvent(self, event) -> None:
        self._idle_timer.stop()
        self.vst_inst.close_editor()
        super().closeEvent(event)


class ExternalPluginDialog(QDialog):
    """Unified dialog for hosting VST3, 64-bit VST2, and Audio Unit plugins
    with native plugin GUI editor window, searchable parameter controls, and live Preview."""

    def __init__(
        self,
        plugin_info: Dict[str, Any],
        sample_rate: int = 48000,
        initial_params: Optional[Dict[str, Any]] = None,
        on_preview: Optional[Callable[[Dict[str, Any]], None]] = None,
        apply_label: str = "Apply",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        from .vst_host import get_external_plugin, list_vst3_subplugins

        self.plugin_info = plugin_info
        self.on_preview = on_preview
        self.path = plugin_info["path"]
        self.ptype = plugin_info["type"]
        self.subname = (initial_params or {}).get("__plugin_subname__")
        if self.ptype == "VST3" and not self.subname:
            subs = list_vst3_subplugins(self.path)
            if len(subs) > 1:
                chosen, ok = QInputDialog.getItem(self, "Select VST3 Plugin", "This .vst3 bundle contains multiple plugins:", subs, 0, False)
                if ok:
                    self.subname = chosen

        self.inst = get_external_plugin(self.path, self.ptype, sample_rate=sample_rate, plugin_name=self.subname)
        if initial_params:
            self.inst.apply_params(initial_params)

        self.setWindowTitle(f"{self.ptype} Plugin — {self.inst.name}")
        self.resize(560, 520)
        lay = QVBoxLayout(self)

        # Top header bar with Native Plugin UI launcher
        hdr = QHBoxLayout()
        info_lbl = QLabel(f"<b>{self.inst.name}</b>  <span style='color:#8D99AE'>({self.ptype})</span>")
        hdr.addWidget(info_lbl, 1)
        if getattr(self.inst, "has_editor", False):
            btn_ui = QPushButton("Open Native Plugin UI...")
            btn_ui.setObjectName("KinoAccentButton")
            btn_ui.clicked.connect(self._open_native_ui)
            hdr.addWidget(btn_ui)
        lay.addLayout(hdr)

        # Search filter for plugins with many parameters
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Filter parameters by name...")
        self.ed_search.textChanged.connect(self._filter_params)
        lay.addWidget(self.ed_search)

        # Scrollable parameter rack
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._param_container = QWidget()
        self._param_lay = QVBoxLayout(self._param_container)
        self._param_lay.setSpacing(6)
        scroll.setWidget(self._param_container)
        lay.addWidget(scroll, 1)

        self._rows: List[Tuple[str, QWidget, Any, QLabel]] = []
        self._rebuild_param_rows()

        # Bottom buttons
        brow = QHBoxLayout()
        if self.on_preview:
            b_prev = QPushButton("Preview")
            b_prev.clicked.connect(lambda: self.on_preview(self.get_params()))
            brow.addWidget(b_prev)
        b_ref = QPushButton("Sync from Plugin")
        b_ref.clicked.connect(self._rebuild_param_rows)
        brow.addWidget(b_ref)
        brow.addStretch(1)
        b_c = QPushButton("Cancel")
        b_c.clicked.connect(self.reject)
        b_ok = QPushButton(apply_label)
        b_ok.setObjectName("PrimaryButton")
        b_ok.clicked.connect(self.accept)
        brow.addWidget(b_c)
        brow.addWidget(b_ok)
        lay.addLayout(brow)

    def _rebuild_param_rows(self) -> None:
        while self._param_lay.count():
            it = self._param_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._rows.clear()
        params = self.inst.list_parameters()
        if not params:
            self._param_lay.addWidget(QLabel("This plugin exposes no generic parameters (use 'Open Native Plugin UI...' above)."))
        for p in params[:180]:
            row_w = QWidget()
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(2, 1, 2, 1)
            lbl_name = QLabel(p["name"][:30])
            lbl_name.setFixedWidth(185)
            lbl_val = QLabel(str(p.get("display", ""))[:16])
            lbl_val.setFixedWidth(80)
            lbl_val.setStyleSheet("color: #10D9A0; font-family: Consolas, monospace; font-size: 8pt;")
            rl.addWidget(lbl_name)
            key = p["key"]
            if p["kind"] == "choice":
                cb = QComboBox()
                cb.addItems(p["choices"])
                cb.setCurrentText(str(p["value"]))
                cb.currentTextChanged.connect(lambda val, k=key, lv=lbl_val: (self.inst.set_param(k, val), lv.setText(str(val)[:16])))
                rl.addWidget(cb, 1)
                ctrl = cb
            elif p["kind"] == "bool":
                cb = QCheckBox()
                cb.setChecked(bool(p["value"]))
                cb.toggled.connect(lambda val, k=key, lv=lbl_val: (self.inst.set_param(k, val), lv.setText("On" if val else "Off")))
                rl.addWidget(cb, 1)
                ctrl = cb
            else:
                sl = QSlider(Qt.Orientation.Horizontal)
                sl.setRange(0, 1000)
                sl.setValue(int(round(float(p["value"]) * 1000)))
                sl.valueChanged.connect(lambda iv, k=key, lv=lbl_val: (self.inst.set_param(k, iv / 1000.0), lv.setText(f"{iv / 1000.0:.2f}")))
                rl.addWidget(sl, 1)
                ctrl = sl
            rl.addWidget(lbl_val)
            self._param_lay.addWidget(row_w)
            self._rows.append((p["name"].lower(), row_w, ctrl, lbl_val))
        self._param_lay.addStretch(1)

    def _filter_params(self, text: str) -> None:
        q = text.strip().lower()
        for name_l, row_w, _, _ in self._rows:
            row_w.setVisible(not q or q in name_l)

    def _open_native_ui(self) -> None:
        try:
            if self.ptype in ("VST3", "Audio Unit"):
                self.inst.show_native_editor()
            else:
                _VST2NativeEditorDialog(self.inst, self).exec()
            self._rebuild_param_rows()
        except Exception as e:
            QMessageBox.warning(self, "Plugin UI Error", f"Could not open native plugin UI:\n{e}")

    def get_params(self) -> Dict[str, Any]:
        d = self.inst.get_param_dict()
        d["__plugin_path__"] = self.path
        d["__plugin_type__"] = self.ptype
        if self.subname:
            d["__plugin_subname__"] = self.subname
        return d


# ---------------------------------------------------------------------------
# Real-Time Non-Destructive Effect Rack Dialog (Per-Track or Master — Built-in + VST3/VST2)
# ---------------------------------------------------------------------------
class RealtimeEffectsDialog(QDialog):
    def __init__(
        self,
        title: str,
        slots: List[EffectSlot],
        preset_mgr: PresetManager,
        plugin_mgr: Optional[PluginManager] = None,
        sample_rate: int = 48000,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.slots = slots
        self.preset_mgr = preset_mgr
        self.plugin_mgr = plugin_mgr
        self.sample_rate = sample_rate
        self.setWindowTitle(f"Real-Time Effects Rack — {title}")
        self.resize(580, 440)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("Non-destructive stackable effects (Built-in + VST3 / 64-bit VST2) applied live during playback & mixdown:"))
        self.lst = QListWidget()
        lay.addWidget(self.lst, 1)

        add_row = QHBoxLayout()
        self.cmb_fx = QComboBox()
        for ename in sorted(EFFECT_REGISTRY.keys()):
            self.cmb_fx.addItem(f"[Built-in] {ename}", {"kind": "builtin", "name": ename})
        if self.plugin_mgr:
            for pl in self.plugin_mgr.plugins:
                if pl.get("enabled") and pl["type"] in ("VST3", "VST2 (64-bit)", "Audio Unit"):
                    self.cmb_fx.addItem(f"[{pl['type']}] {pl['name']}", {"kind": "external", "info": pl})
        btn_add = QPushButton("+ Add Effect / VST")
        btn_add.setObjectName("PrimaryButton")
        btn_add.clicked.connect(self._add)
        add_row.addWidget(self.cmb_fx, 1)
        add_row.addWidget(btn_add)
        lay.addLayout(add_row)

        ctl = QHBoxLayout()
        for lbl, fn in [("Edit / Open UI...", self._edit), ("Toggle Bypass", self._toggle), ("Move Up", lambda: self._move(-1)), ("Move Down", lambda: self._move(1)), ("Remove", self._remove)]:
            b = QPushButton(lbl)
            b.clicked.connect(fn)
            ctl.addWidget(b)
        lay.addLayout(ctl)

        btn_done = QPushButton("Close")
        btn_done.clicked.connect(self.accept)
        lay.addWidget(btn_done, 0, Qt.AlignmentFlag.AlignRight)
        self._refresh()

    def _refresh(self) -> None:
        self.lst.clear()
        for i, sl in enumerate(self.slots):
            state = "ON " if sl.enabled else "BYP"
            tag = sl.params.get("__plugin_type__", "Built-in")
            self.lst.addItem(f"[{state}] {i + 1}. {sl.effect_name}  ({tag})")

    def _add(self) -> None:
        data = self.cmb_fx.currentData()
        if not data:
            return
        if data["kind"] == "builtin":
            name = data["name"]
            slot = EffectSlot(effect_name=name, enabled=True, params=default_effect_params(name))
        else:
            pl = data["info"]
            slot = EffectSlot(
                effect_name=pl["name"],
                enabled=True,
                params={"__plugin_path__": pl["path"], "__plugin_type__": pl["type"]},
            )
        self.slots.append(slot)
        self._refresh()
        self.lst.setCurrentRow(len(self.slots) - 1)

    def _edit(self) -> None:
        row = self.lst.currentRow()
        if 0 <= row < len(self.slots):
            sl = self.slots[row]
            if "__plugin_path__" in sl.params:
                try:
                    pinfo = {"name": sl.effect_name, "path": sl.params["__plugin_path__"], "type": sl.params.get("__plugin_type__", "VST3")}
                    dlg = ExternalPluginDialog(pinfo, sample_rate=self.sample_rate, initial_params=sl.params, apply_label="Save Slot", parent=self)
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        sl.params = dlg.get_params()
                        self._refresh()
                except Exception as e:
                    QMessageBox.critical(self, "VST Load Error", str(e))
            else:
                dlg = EffectDialog(sl.effect_name, self.preset_mgr, initial_params=sl.params, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    sl.params = dlg.get_params()
                    self._refresh()

    def _toggle(self) -> None:
        row = self.lst.currentRow()
        if 0 <= row < len(self.slots):
            self.slots[row].enabled = not self.slots[row].enabled
            self._refresh()
            self.lst.setCurrentRow(row)

    def _move(self, delta: int) -> None:
        row = self.lst.currentRow()
        nr = row + delta
        if 0 <= row < len(self.slots) and 0 <= nr < len(self.slots):
            self.slots.insert(nr, self.slots.pop(row))
            self._refresh()
            self.lst.setCurrentRow(nr)

    def _remove(self) -> None:
        row = self.lst.currentRow()
        if 0 <= row < len(self.slots):
            self.slots.pop(row)
            self._refresh()


# ---------------------------------------------------------------------------
# Audio Generator Dialog
# ---------------------------------------------------------------------------
class GeneratorDialog(QDialog):
    def __init__(self, gen_type: str, default_dur: float = 5.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.gen_type = gen_type
        self.setWindowTitle(f"Generate — {gen_type}")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.fields: Dict[str, Any] = {}

        def add_f(k, lbl, val, mn, mx, step=0.1, dec=2):
            sb = QDoubleSpinBox()
            sb.setRange(mn, mx)
            sb.setSingleStep(step)
            sb.setDecimals(dec)
            sb.setValue(val)
            self.fields[k] = sb
            form.addRow(lbl, sb)

        def add_i(k, lbl, val, mn, mx):
            sb = QSpinBox()
            sb.setRange(mn, mx)
            sb.setValue(val)
            self.fields[k] = sb
            form.addRow(lbl, sb)

        def add_c(k, lbl, opts):
            cb = QComboBox()
            cb.addItems(opts)
            self.fields[k] = cb
            form.addRow(lbl, cb)

        if gen_type == "Tone":
            add_c("waveform", "Waveform", ["Sine", "Square", "Square (No Alias)", "Sawtooth", "Triangle"])
            add_f("freq_hz", "Frequency (Hz)", 440.0, 1.0, 24000.0, 10.0)
            add_f("amplitude", "Amplitude (0-1)", 0.8, 0.01, 1.0, 0.05)
            add_f("duration_s", "Duration (s)", default_dur, 0.05, 600.0, 0.5)
        elif gen_type == "Chirp":
            add_c("waveform", "Waveform", ["Sine", "Square", "Sawtooth"])
            add_f("f_start", "Start Frequency (Hz)", 220.0, 1.0, 24000.0, 10.0)
            add_f("f_end", "End Frequency (Hz)", 1760.0, 1.0, 24000.0, 10.0)
            add_f("amp_start", "Start Amplitude", 0.8, 0.0, 1.0, 0.05)
            add_f("amp_end", "End Amplitude", 0.8, 0.0, 1.0, 0.05)
            add_c("interp", "Interpolation", ["Logarithmic", "Linear"])
            add_f("duration_s", "Duration (s)", default_dur, 0.05, 600.0, 0.5)
        elif gen_type == "Noise":
            add_c("noise_type", "Noise Type", ["White", "Pink", "Brown"])
            add_f("amplitude", "Amplitude (0-1)", 0.4, 0.01, 1.0, 0.05)
            add_f("duration_s", "Duration (s)", default_dur, 0.05, 600.0, 0.5)
        elif gen_type == "DTMF Tones":
            ed = QLineEdit("555-1234*#")
            self.fields["sequence"] = ed
            form.addRow("DTMF Sequence", ed)
            add_f("duty_cycle_pct", "Duty Cycle (%)", 55.0, 10.0, 95.0, 5.0)
            add_f("amplitude", "Amplitude (0-1)", 0.7, 0.01, 1.0, 0.05)
            add_f("duration_s", "Duration (s)", default_dur, 0.1, 120.0, 0.5)
        elif gen_type == "Silence":
            add_f("duration_s", "Duration (s)", default_dur, 0.01, 600.0, 0.5)
        elif gen_type == "Rhythm Track":
            add_f("bpm", "Tempo (BPM)", 120.0, 30.0, 300.0, 1.0)
            add_i("beats_per_bar", "Beats per Bar", 4, 1, 16)
            add_i("num_bars", "Number of Bars", 8, 1, 200)
            add_f("swing", "Swing (%)", 0.0, -50.0, 50.0, 5.0)
            add_c("click_sound", "Click Sound", ["Metronome", "Woodblock", "Ping"])
        elif gen_type == "Plucked":
            add_i("midi_pitch", "MIDI Pitch (60 = C4)", 60, 1, 120)
            add_c("decay_type", "Fade-Out Type", ["Gradual", "Abrupt"])
            add_f("amplitude", "Amplitude (0-1)", 0.85, 0.05, 1.0, 0.05)
            add_f("duration_s", "Duration (s)", 2.0, 0.1, 60.0, 0.2)
        elif gen_type == "Risset Drum":
            add_f("freq_hz", "Frequency (Hz)", 100.0, 50.0, 2000.0, 5.0)
            add_f("decay_s", "Decay (seconds)", 2.0, 0.1, 60.0, 0.2)
            add_f("noise_cf_hz", "Center Frequency of Noise (Hz)", 500.0, 100.0, 5000.0, 25.0)
            add_f("noise_bw_hz", "Width of Noise Band (Hz)", 400.0, 10.0, 1000.0, 20.0)
            add_f("noise_pct", "Amount of Noise in Mix (%)", 25.0, 0.0, 100.0, 5.0)
            add_f("amplitude", "Amplitude (0-1)", 0.8, 0.05, 1.0, 0.05)

        lay.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        b_c = QPushButton("Cancel")
        b_c.clicked.connect(self.reject)
        b_o = QPushButton("Generate")
        b_o.setObjectName("PrimaryButton")
        b_o.clicked.connect(self.accept)
        row.addWidget(b_c)
        row.addWidget(b_o)
        lay.addLayout(row)

    def values(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, w in self.fields.items():
            if isinstance(w, (QDoubleSpinBox, QSpinBox)):
                out[k] = w.value()
            elif isinstance(w, QComboBox):
                out[k] = w.currentText()
            elif isinstance(w, QLineEdit):
                out[k] = w.text()
        return out


# ---------------------------------------------------------------------------
# Plot Spectrum Dialog (with Export Data)
# ---------------------------------------------------------------------------
class _SpectrumPlotCanvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.freqs = np.array([20.0, 20000.0])
        self.vals = np.array([-90.0, -90.0])
        self.log_axis = True
        self.setMinimumSize(620, 320)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0E1219"))
        p.setPen(QColor("#2A3242"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if len(self.freqs) < 2:
            p.end()
            return

        left, top, right, bot = 48, 16, self.width() - 16, self.height() - 28
        w, h = max(10, right - left), max(10, bot - top)
        fmin, fmax = max(10.0, float(self.freqs[1])), max(100.0, float(self.freqs[-1]))
        vmin, vmax = -100.0, 6.0

        # Grid
        p.setFont(QFont("Segoe UI", 7.5))
        for db in (-90, -72, -54, -36, -18, 0):
            y = top + (vmax - db) / (vmax - vmin) * h
            p.setPen(QColor("#1E2533"))
            p.drawLine(QPointF(left, y), QPointF(right, y))
            p.setPen(QColor("#8D99AE"))
            p.drawText(QRectF(2, y - 8, 42, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{db} dB")

        path = QPainterPath()
        started = False
        step = max(1, len(self.freqs) // 600)
        for i in range(1, len(self.freqs), step):
            f = float(self.freqs[i])
            v = float(np.clip(self.vals[i], vmin, vmax))
            if self.log_axis:
                xf = (math.log10(max(fmin, f)) - math.log10(fmin)) / max(1e-6, math.log10(fmax) - math.log10(fmin))
            else:
                xf = (f - fmin) / max(1e-6, fmax - fmin)
            x = left + np.clip(xf, 0.0, 1.0) * w
            y = top + (vmax - v) / (vmax - vmin) * h
            if not started:
                path.moveTo(x, y)
                started = True
            else:
                path.lineTo(x, y)
        p.setPen(QPen(QColor("#10D9A0"), 1.8))
        p.drawPath(path)

        # Peak readout
        pk_i = int(np.argmax(self.vals[1:]) + 1)
        p.setPen(QColor("#22D3EE"))
        p.drawText(QRectF(left + 8, top + 4, 280, 18), f"Peak: {self.freqs[pk_i]:.1f} Hz ({self.vals[pk_i]:.1f} dB)")
        p.end()


class PlotSpectrumDialog(QDialog):
    def __init__(self, audio: np.ndarray, sr: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audio = audio
        self.sr = sr
        self.setWindowTitle("Frequency Analysis — Plot Spectrum")
        self.resize(700, 450)
        lay = QVBoxLayout(self)

        self.canvas = _SpectrumPlotCanvas()
        lay.addWidget(self.canvas, 1)

        ctl = QHBoxLayout()
        self.cmb_alg = QComboBox()
        self.cmb_alg.addItems(["Spectrum", "Autocorrelation"])
        self.cmb_size = QComboBox()
        self.cmb_size.addItems(["256", "512", "1024", "2048", "4096", "8192", "16384"])
        self.cmb_size.setCurrentText("4096")
        self.cmb_win = QComboBox()
        self.cmb_win.addItems(SPECTROGRAM_WINDOWS)
        self.cmb_axis = QComboBox()
        self.cmb_axis.addItems(["Log Frequency", "Linear Frequency"])
        for w in (self.cmb_alg, self.cmb_size, self.cmb_win, self.cmb_axis):
            w.currentTextChanged.connect(self._recompute)
            ctl.addWidget(w)

        btn_exp = QPushButton("Export...")
        btn_exp.clicked.connect(self._export)
        btn_cls = QPushButton("Close")
        btn_cls.clicked.connect(self.accept)
        ctl.addWidget(btn_exp)
        ctl.addWidget(btn_cls)
        lay.addLayout(ctl)
        self._recompute()

    def _recompute(self) -> None:
        freqs, vals = compute_spectrum(self.audio, self.sr, n_fft=int(self.cmb_size.currentText()), window=self.cmb_win.currentText(), algorithm=self.cmb_alg.currentText())
        self.canvas.freqs = freqs
        self.canvas.vals = vals
        self.canvas.log_axis = self.cmb_axis.currentText().startswith("Log") and self.cmb_alg.currentText() == "Spectrum"
        self.canvas.update()

    def _export(self) -> None:
        fp, _ = QFileDialog.getSaveFileName(self, "Export Spectrum Data", "spectrum.txt", "Text / CSV (*.txt *.csv)")
        if not fp:
            return
        with open(fp, "w", encoding="utf-8") as f:
            f.write("Frequency (Hz)\tLevel (dB)\n")
            for fr, lv in zip(self.canvas.freqs, self.canvas.vals):
                f.write(f"{fr:.4f}\t{lv:.4f}\n")
        QMessageBox.information(self, "Exported", f"Spectrum data saved to {fp}")


# ---------------------------------------------------------------------------
# WCAG Contrast Analysis Dialog
# ---------------------------------------------------------------------------
class ContrastAnalysisDialog(QDialog):
    def __init__(self, get_sel_audio: Callable[[], np.ndarray], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.get_sel_audio = get_sel_audio
        self.fg: Optional[np.ndarray] = None
        self.bg: Optional[np.ndarray] = None
        self.setWindowTitle("Contrast Analysis (WCAG 2.0 Audio Accessibility)")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)

        row1 = QHBoxLayout()
        self.lbl_fg = QLabel("Foreground: Not measured")
        b_fg = QPushButton("Measure Selection as Foreground")
        b_fg.clicked.connect(self._m_fg)
        row1.addWidget(self.lbl_fg, 1)
        row1.addWidget(b_fg)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_bg = QLabel("Background: Not measured")
        b_bg = QPushButton("Measure Selection as Background")
        b_bg.clicked.connect(self._m_bg)
        row2.addWidget(self.lbl_bg, 1)
        row2.addWidget(b_bg)
        lay.addLayout(row2)

        self.lbl_res = QLabel("Select speech (Foreground) and noise/music bed (Background) to check >= 20 dB contrast.")
        self.lbl_res.setStyleSheet("padding: 10px; background: #141821; border: 1px solid #2A3242; border-radius: 6px; font-weight: 600;")
        lay.addWidget(self.lbl_res)

        b_cls = QPushButton("Close")
        b_cls.clicked.connect(self.accept)
        lay.addWidget(b_cls, 0, Qt.AlignmentFlag.AlignRight)

    def _m_fg(self) -> None:
        self.fg = self.get_sel_audio()
        self._update()

    def _m_bg(self) -> None:
        self.bg = self.get_sel_audio()
        self._update()

    def _update(self) -> None:
        res = wcag_contrast(self.fg if self.fg is not None else np.zeros((1, 1)), self.bg if self.bg is not None else np.zeros((1, 1)))
        if self.fg is not None:
            self.lbl_fg.setText(f"Foreground RMS: {res['foreground_db']} dB")
        if self.bg is not None:
            self.lbl_bg.setText(f"Background RMS: {res['background_db']} dB")
        if self.fg is not None and self.bg is not None:
            col = "#10D9A0" if res["wcag_pass"] else "#F43F5E"
            self.lbl_res.setStyleSheet(f"padding: 10px; background: #141821; border: 1px solid {col}; color: {col}; border-radius: 6px; font-weight: 700;")
            self.lbl_res.setText(f"Difference: {res['difference_db']} dB  —  {res['result']}")


# ---------------------------------------------------------------------------
# Metadata Tags Editor (with Save/Load Templates)
# ---------------------------------------------------------------------------
class MetadataDialog(QDialog):
    def __init__(self, metadata: ProjectMetadata, prefs: PreferencesManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.metadata = metadata
        self.prefs = prefs
        self.setWindowTitle("Edit Metadata Tags")
        self.resize(520, 440)
        lay = QVBoxLayout(self)

        trow = QHBoxLayout()
        trow.addWidget(QLabel("Tag Template:"))
        self.cmb_tpl = QComboBox()
        self.cmb_tpl.addItems(list(self.prefs.get("tag_templates", {}).keys()))
        btn_load = QPushButton("Load Template")
        btn_load.clicked.connect(self._load_tpl)
        btn_save = QPushButton("Save Template...")
        btn_save.clicked.connect(self._save_tpl)
        trow.addWidget(self.cmb_tpl, 1)
        trow.addWidget(btn_load)
        trow.addWidget(btn_save)
        lay.addLayout(trow)

        form = QFormLayout()
        self.ed_artist = QLineEdit(metadata.artist)
        self.ed_title = QLineEdit(metadata.title)
        self.ed_album = QLineEdit(metadata.album)
        self.ed_track = QLineEdit(metadata.track_number)
        self.ed_year = QLineEdit(metadata.year)
        self.ed_genre = QLineEdit(metadata.genre)
        self.ed_comments = QLineEdit(metadata.comments)
        for lbl, w in [
            ("Artist Name:", self.ed_artist),
            ("Track Title:", self.ed_title),
            ("Album Title:", self.ed_album),
            ("Track Number:", self.ed_track),
            ("Year:", self.ed_year),
            ("Genre:", self.ed_genre),
            ("Comments:", self.ed_comments),
        ]:
            form.addRow(lbl, w)
        lay.addLayout(form)

        lay.addWidget(QLabel("Custom Tags:"))
        self.tbl = QTableWidget(len(metadata.custom_tags), 2)
        self.tbl.setHorizontalHeaderLabels(["Tag Name", "Value"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for r, (k, v) in enumerate(metadata.custom_tags.items()):
            self.tbl.setItem(r, 0, QTableWidgetItem(k))
            self.tbl.setItem(r, 1, QTableWidgetItem(v))
        lay.addWidget(self.tbl, 1)

        brow = QHBoxLayout()
        b_add = QPushButton("+ Add Custom Tag")
        b_add.clicked.connect(lambda: self.tbl.insertRow(self.tbl.rowCount()))
        brow.addWidget(b_add)
        brow.addStretch(1)
        b_c = QPushButton("Cancel")
        b_c.clicked.connect(self.reject)
        b_ok = QPushButton("Save Tags")
        b_ok.setObjectName("PrimaryButton")
        b_ok.clicked.connect(self._apply)
        brow.addWidget(b_c)
        brow.addWidget(b_ok)
        lay.addLayout(brow)

    def _load_tpl(self) -> None:
        tpl = self.prefs.get("tag_templates", {}).get(self.cmb_tpl.currentText(), {})
        if "artist" in tpl: self.ed_artist.setText(tpl["artist"])
        if "album" in tpl: self.ed_album.setText(tpl["album"])
        if "year" in tpl: self.ed_year.setText(tpl["year"])
        if "genre" in tpl: self.ed_genre.setText(tpl["genre"])
        if "comments" in tpl: self.ed_comments.setText(tpl["comments"])

    def _save_tpl(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Tag Template", "Template Name:")
        if ok and name.strip():
            tpls = dict(self.prefs.get("tag_templates", {}))
            tpls[name.strip()] = {
                "artist": self.ed_artist.text(),
                "album": self.ed_album.text(),
                "year": self.ed_year.text(),
                "genre": self.ed_genre.text(),
                "comments": self.ed_comments.text(),
            }
            self.prefs.set("tag_templates", tpls)
            if self.cmb_tpl.findText(name.strip()) < 0:
                self.cmb_tpl.addItem(name.strip())

    def _apply(self) -> None:
        self.metadata.artist = self.ed_artist.text()
        self.metadata.title = self.ed_title.text()
        self.metadata.album = self.ed_album.text()
        self.metadata.track_number = self.ed_track.text()
        self.metadata.year = self.ed_year.text()
        self.metadata.genre = self.ed_genre.text()
        self.metadata.comments = self.ed_comments.text()
        custom = {}
        for r in range(self.tbl.rowCount()):
            k = self.tbl.item(r, 0).text().strip() if self.tbl.item(r, 0) else ""
            v = self.tbl.item(r, 1).text().strip() if self.tbl.item(r, 1) else ""
            if k:
                custom[k] = v
        self.metadata.custom_tags = custom
        self.accept()


# ---------------------------------------------------------------------------
# Export Audio Dialog (Single, Selected Only, Multiple by Track / Label)
# ---------------------------------------------------------------------------
class ExportDialog(QDialog):
    def __init__(self, project: KinoWaveProject, prefs: PreferencesManager, default_scope: str = "Entire Project", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = project
        self.prefs = prefs
        self.setWindowTitle("Export Audio — KinoWave")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.cmb_scope = QComboBox()
        self.cmb_scope.addItems(["Entire Project", "Selected Audio Only", "Multiple Files — Split by Track", "Multiple Files — Split by Labels"])
        self.cmb_scope.setCurrentText(default_scope)
        form.addRow("Export Range:", self.cmb_scope)

        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItems(EXPORT_FORMATS)
        form.addRow("Format:", self.cmb_fmt)

        self.cmb_sr = QComboBox()
        for r in SAMPLE_RATES:
            self.cmb_sr.addItem(f"{r} Hz", r)
        idx = self.cmb_sr.findData(project.sample_rate)
        if idx >= 0:
            self.cmb_sr.setCurrentIndex(idx)
        form.addRow("Sample Rate:", self.cmb_sr)

        self.cmb_depth = QComboBox()
        self.cmb_depth.addItems(["16-bit PCM", "24-bit PCM", "32-bit float"])
        form.addRow("Bit Depth (Lossless):", self.cmb_depth)

        self.cmb_ch = QComboBox()
        self.cmb_ch.addItem("Stereo (2 channels)", 2)
        self.cmb_ch.addItem("Mono (1 channel)", 1)
        form.addRow("Channel Mapping:", self.cmb_ch)

        self.cmb_rate_mode = QComboBox()
        self.cmb_rate_mode.addItems(["VBR", "CBR"])
        form.addRow("Bitrate Mode:", self.cmb_rate_mode)

        self.sp_kbps = QSpinBox()
        self.sp_kbps.setRange(32, 512)
        self.sp_kbps.setValue(192)
        self.sp_kbps.setSuffix(" kbps")
        form.addRow("Bitrate (Lossy):", self.sp_kbps)

        self.ed_custom = QLineEdit("")
        self.ed_custom.setPlaceholderText("e.g. -c:a libopus -b:a 128k (for Custom FFmpeg)")
        form.addRow("Custom FFmpeg Args:", self.ed_custom)

        # Output destination
        prow = QHBoxLayout()
        self.ed_path = QLineEdit(os.path.join(os.path.expanduser("~"), f"{os.path.splitext(project.name)[0]}.wav"))
        b_br = QPushButton("Browse...")
        b_br.clicked.connect(self._browse)
        prow.addWidget(self.ed_path, 1)
        prow.addWidget(b_br)
        form.addRow("Output File / Folder:", prow)
        lay.addLayout(form)

        brow = QHBoxLayout()
        b_meta = QPushButton("Edit Metadata Tags...")
        b_meta.clicked.connect(lambda: MetadataDialog(self.project.metadata, self.prefs, self).exec())
        brow.addWidget(b_meta)
        brow.addStretch(1)
        b_c = QPushButton("Cancel")
        b_c.clicked.connect(self.reject)
        b_go = QPushButton("Export")
        b_go.setObjectName("PrimaryButton")
        b_go.clicked.connect(self._do_export)
        brow.addWidget(b_c)
        brow.addWidget(b_go)
        lay.addLayout(brow)

    def _ext_for_fmt(self, fmt: str) -> str:
        return {
            "WAV": ".wav", "AIFF": ".aiff", "FLAC": ".flac", "MP3": ".mp3", "OGG": ".ogg",
            "Opus": ".opus", "M4A (AAC)": ".m4a", "WMA": ".wma", "AC3": ".ac3", "AMR": ".amr", "Custom FFmpeg": ".mka",
        }.get(fmt, ".wav")

    def _browse(self) -> None:
        if "Multiple" in self.cmb_scope.currentText():
            d = QFileDialog.getExistingDirectory(self, "Choose Output Folder for Multiple Export")
            if d:
                self.ed_path.setText(d)
        else:
            ext = self._ext_for_fmt(self.cmb_fmt.currentText())
            fp, _ = QFileDialog.getSaveFileName(self, "Export Audio", self.ed_path.text(), f"Audio (*{ext});;All Files (*.*)")
            if fp:
                self.ed_path.setText(fp)

    def _do_export(self) -> None:
        scope = self.cmb_scope.currentText()
        fmt = self.cmb_fmt.currentText()
        ext = self._ext_for_fmt(fmt)
        sr = int(self.cmb_sr.currentData())
        depth = self.cmb_depth.currentText()
        ch = int(self.cmb_ch.currentData())
        rmode = self.cmb_rate_mode.currentText()
        kbps = self.sp_kbps.value()
        dither = self.prefs.get("dither_mode", "Triangle")
        ff = self.prefs.get("ffmpeg_path", "")
        cargs = self.ed_custom.text()

        try:
            if scope == "Entire Project":
                mix = self.project.mix_render(sample_rate=sr)
                out_path = self.ed_path.text()
                if not out_path.lower().endswith(ext) and fmt != "Custom FFmpeg":
                    out_path = os.path.splitext(out_path)[0] + ext
                export_audio_file(out_path, mix, sr, fmt, sr, depth, kbps, rmode, ch, self.project.metadata, dither, ff, cargs)
                QMessageBox.information(self, "Export Complete", f"Exported successfully to:\n{out_path}")
            elif scope == "Selected Audio Only":
                t0, t1 = self.project.selection_bounds()
                mix = self.project.mix_render(start_s=t0, end_s=t1, sample_rate=sr)
                out_path = self.ed_path.text()
                if not out_path.lower().endswith(ext) and fmt != "Custom FFmpeg":
                    out_path = os.path.splitext(out_path)[0] + ext
                export_audio_file(out_path, mix, sr, fmt, sr, depth, kbps, rmode, ch, self.project.metadata, dither, ff, cargs)
                QMessageBox.information(self, "Export Complete", f"Exported selection ({t1 - t0:.2f}s) to:\n{out_path}")
            elif scope == "Multiple Files — Split by Track":
                out_dir = self.ed_path.text()
                if not os.path.isdir(out_dir):
                    out_dir = os.path.dirname(out_dir) or os.getcwd()
                os.makedirs(out_dir, exist_ok=True)
                cnt = 0
                for idx, tr in enumerate(self.project.audio_tracks()):
                    arr = tr.render_range(0.0, tr.duration(), sr, apply_realtime_fx=True, apply_gain_pan=(ch == 2))
                    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in tr.name).strip() or f"Track_{idx+1}"
                    fp = os.path.join(out_dir, f"{idx+1:02d}_{safe}{ext}")
                    export_audio_file(fp, arr, sr, fmt, sr, depth, kbps, rmode, ch, self.project.metadata, dither, ff, cargs)
                    cnt += 1
                QMessageBox.information(self, "Export Multiple Complete", f"Exported {cnt} track files to:\n{out_dir}")
            else:  # Split by Labels
                ltracks = self.project.label_tracks()
                labels = sorted(ltracks[0].labels, key=lambda x: x.start) if ltracks else []
                if not labels:
                    QMessageBox.warning(self, "No Labels", "Add a Label Track with markers first to export split by labels.")
                    return
                out_dir = self.ed_path.text()
                if not os.path.isdir(out_dir):
                    out_dir = os.path.dirname(out_dir) or os.getcwd()
                os.makedirs(out_dir, exist_ok=True)
                total_dur = self.project.duration()
                for idx, lb in enumerate(labels):
                    t0 = lb.start
                    t1 = lb.end if lb.end > lb.start + 0.01 else (labels[idx + 1].start if idx + 1 < len(labels) else total_dur)
                    if t1 <= t0 + 0.01:
                        continue
                    mix = self.project.mix_render(start_s=t0, end_s=t1, sample_rate=sr)
                    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in (lb.text or f"Region_{idx+1}")).strip()
                    fp = os.path.join(out_dir, f"{idx+1:02d}_{safe}{ext}")
                    export_audio_file(fp, mix, sr, fmt, sr, depth, kbps, rmode, ch, self.project.metadata, dither, ff, cargs)
                QMessageBox.information(self, "Export Multiple Complete", f"Exported {len(labels)} labeled segments to:\n{out_dir}")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))


# ---------------------------------------------------------------------------
# Import Raw (Headerless) Data Dialog
# ---------------------------------------------------------------------------
class ImportRawDialog(QDialog):
    def __init__(self, path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Import Raw Data — {os.path.basename(path)}")
        form = QFormLayout(self)
        self.cmb_enc = QComboBox()
        self.cmb_enc.addItems(["Signed 16-bit PCM", "32-bit float", "64-bit float", "Signed 32-bit PCM", "Signed 8-bit PCM", "Unsigned 8-bit PCM"])
        self.cmb_end = QComboBox()
        self.cmb_end.addItems(["Little-endian", "Big-endian"])
        self.sp_ch = QSpinBox()
        self.sp_ch.setRange(1, 8)
        self.sp_ch.setValue(1)
        self.sp_off = QSpinBox()
        self.sp_off.setRange(0, 10_000_000)
        self.sp_sr = QSpinBox()
        self.sp_sr.setRange(8000, 384000)
        self.sp_sr.setValue(44100)
        form.addRow("Encoding:", self.cmb_enc)
        form.addRow("Byte Order:", self.cmb_end)
        form.addRow("Channels:", self.sp_ch)
        form.addRow("Start Offset (bytes):", self.sp_off)
        form.addRow("Sample Rate (Hz):", self.sp_sr)
        row = QHBoxLayout()
        b_c = QPushButton("Cancel"); b_c.clicked.connect(self.reject)
        b_o = QPushButton("Import"); b_o.setObjectName("PrimaryButton"); b_o.clicked.connect(self.accept)
        row.addWidget(b_c); row.addWidget(b_o)
        form.addRow(row)


# ---------------------------------------------------------------------------
# Timer Record Dialog (Start Time, Duration, Auto-Save, Auto-Export)
# ---------------------------------------------------------------------------
class TimerRecordDialog(QDialog):
    def __init__(self, on_start_rec: Callable[[], None], on_stop_rec: Callable[[str, str], None], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.on_start_rec = on_start_rec
        self.on_stop_rec = on_stop_rec
        self.setWindowTitle("Timer Record")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.dt_start = QDateTimeEdit(datetime.datetime.now() + datetime.timedelta(seconds=3))
        self.dt_start.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.sp_dur = QSpinBox()
        self.sp_dur.setRange(1, 86400)
        self.sp_dur.setValue(10)
        self.sp_dur.setSuffix(" seconds")
        self.ed_save = QLineEdit("")
        self.ed_save.setPlaceholderText("Optional auto-save .kwp path")
        self.ed_exp = QLineEdit("")
        self.ed_exp.setPlaceholderText("Optional auto-export .wav path")
        form.addRow("Start Time:", self.dt_start)
        form.addRow("Duration:", self.sp_dur)
        form.addRow("Auto-Save Project:", self.ed_save)
        form.addRow("Auto-Export WAV:", self.ed_exp)
        lay.addLayout(form)

        self.lbl_status = QLabel("Ready to schedule timer recording.")
        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        lay.addWidget(self.lbl_status)
        lay.addWidget(self.prog)

        row = QHBoxLayout()
        self.btn_start = QPushButton("Arm Timer Record")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_start.clicked.connect(self._arm)
        b_c = QPushButton("Cancel / Stop")
        b_c.clicked.connect(self._cancel)
        row.addStretch(1)
        row.addWidget(b_c)
        row.addWidget(self.btn_start)
        lay.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._recording = False
        self._rec_start_dt: Optional[datetime.datetime] = None

    def _arm(self) -> None:
        self.btn_start.setEnabled(False)
        self._timer.start()
        self.lbl_status.setText("Waiting for scheduled start time...")

    def _tick(self) -> None:
        now = datetime.datetime.now()
        target = self.dt_start.dateTime().toPython()
        if not self._recording:
            rem = (target - now).total_seconds()
            if rem <= 0:
                self._recording = True
                self._rec_start_dt = now
                self.on_start_rec()
                self.lbl_status.setText("Recording in progress...")
            else:
                self.lbl_status.setText(f"Starting in {rem:.1f}s...")
        else:
            elapsed = (now - self._rec_start_dt).total_seconds()
            dur = float(self.sp_dur.value())
            self.prog.setValue(int(min(100, (elapsed / dur) * 100)))
            self.lbl_status.setText(f"Recording: {elapsed:.1f}s / {dur:.0f}s")
            if elapsed >= dur:
                self._timer.stop()
                self.on_stop_rec(self.ed_save.text().strip(), self.ed_exp.text().strip())
                self.accept()

    def _cancel(self) -> None:
        self._timer.stop()
        if self._recording:
            self.on_stop_rec("", "")
        self.reject()


# ---------------------------------------------------------------------------
# Undo History Browser & Discard Dialog
# ---------------------------------------------------------------------------
class HistoryDialog(QDialog):
    def __init__(self, project: KinoWaveProject, on_restore: Callable[[int], None], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = project
        self.on_restore = on_restore
        self.setWindowTitle("Undo History — KinoWave")
        self.resize(520, 400)
        lay = QVBoxLayout(self)

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Action", "Time", "Audio Size"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.cellClicked.connect(self._jump)
        lay.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Levels to Discard:"))
        self.sp_disc = QSpinBox()
        self.sp_disc.setRange(1, max(1, project.history_index))
        b_disc = QPushButton("Discard")
        b_disc.setObjectName("DangerButton")
        b_disc.clicked.connect(self._discard)
        b_cls = QPushButton("Close")
        b_cls.clicked.connect(self.accept)
        row.addWidget(self.sp_disc)
        row.addWidget(b_disc)
        row.addStretch(1)
        row.addWidget(b_cls)
        lay.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        self.tbl.setRowCount(len(self.project.history))
        for i, st in enumerate(self.project.history):
            prefix = "▶ " if i == self.project.history_index else "   "
            self.tbl.setItem(i, 0, QTableWidgetItem(prefix + st.description))
            self.tbl.setItem(i, 1, QTableWidgetItem(st.timestamp))
            self.tbl.setItem(i, 2, QTableWidgetItem(f"{st.size_kb:.1f} KB"))
        if 0 <= self.project.history_index < self.tbl.rowCount():
            self.tbl.selectRow(self.project.history_index)
        self.sp_disc.setMaximum(max(1, self.project.history_index))

    def _jump(self, row: int, _col: int) -> None:
        self.on_restore(row)
        self._refresh()

    def _discard(self) -> None:
        self.project.discard_history(self.sp_disc.value())
        self._refresh()


# ---------------------------------------------------------------------------
# Label Table Editor Dialog
# ---------------------------------------------------------------------------
class LabelEditorDialog(QDialog):
    def __init__(self, project: KinoWaveProject, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Edit Labels")
        self.resize(620, 400)
        lay = QVBoxLayout(self)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Track", "Label Text", "Start Time (s)", "End Time (s)"])
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        for lbl, fn in [("Insert After", self._add), ("Remove", self._remove), ("Import...", self._import), ("Export...", self._export)]:
            b = QPushButton(lbl)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        b_ok = QPushButton("OK")
        b_ok.setObjectName("PrimaryButton")
        b_ok.clicked.connect(self._save_and_close)
        row.addWidget(b_ok)
        lay.addLayout(row)
        self._populate()

    def _populate(self) -> None:
        self.tbl.setRowCount(0)
        for lt in self.project.label_tracks():
            for lb in lt.labels:
                r = self.tbl.rowCount()
                self.tbl.insertRow(r)
                self.tbl.setItem(r, 0, QTableWidgetItem(lt.name))
                self.tbl.setItem(r, 1, QTableWidgetItem(lb.text))
                self.tbl.setItem(r, 2, QTableWidgetItem(f"{lb.start:.4f}"))
                self.tbl.setItem(r, 3, QTableWidgetItem(f"{lb.end:.4f}"))

    def _add(self) -> None:
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        tname = self.project.label_tracks()[0].name if self.project.label_tracks() else "Label Track 1"
        self.tbl.setItem(r, 0, QTableWidgetItem(tname))
        self.tbl.setItem(r, 1, QTableWidgetItem("New Label"))
        self.tbl.setItem(r, 2, QTableWidgetItem(f"{self.project.sel_start:.4f}"))
        self.tbl.setItem(r, 3, QTableWidgetItem(f"{self.project.sel_end:.4f}"))

    def _remove(self) -> None:
        r = self.tbl.currentRow()
        if r >= 0:
            self.tbl.removeRow(r)

    def _import(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Import Labels", "", "Text Files (*.txt);;All Files (*.*)")
        if not fp:
            return
        items = import_labels_txt(fp)
        tname = self.project.label_tracks()[0].name if self.project.label_tracks() else "Label Track 1"
        for lb in items:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(tname))
            self.tbl.setItem(r, 1, QTableWidgetItem(lb.text))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{lb.start:.4f}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{lb.end:.4f}"))

    def _export(self) -> None:
        fp, _ = QFileDialog.getSaveFileName(self, "Export Labels", "labels.txt", "Text Files (*.txt)")
        if not fp:
            return
        items = self._collect_items()
        export_labels_txt(fp, [lb for _, lb in items])

    def _collect_items(self) -> List[Tuple[str, LabelItem]]:
        out = []
        for r in range(self.tbl.rowCount()):
            tn = self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else "Label Track 1"
            tx = self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else ""
            try:
                t0 = float(self.tbl.item(r, 2).text())
                t1 = float(self.tbl.item(r, 3).text())
            except Exception:
                t0, t1 = 0.0, 0.0
            out.append((tn, LabelItem(start=min(t0, t1), end=max(t0, t1), text=tx)))
        return out

    def _save_and_close(self) -> None:
        by_track: Dict[str, List[LabelItem]] = {}
        for tn, lb in self._collect_items():
            by_track.setdefault(tn, []).append(lb)
        existing = {t.name: t for t in self.project.label_tracks()}
        for t in existing.values():
            t.labels.clear()
        for tn, lbs in by_track.items():
            tr = existing.get(tn) or self.project.add_label_track(tn)
            tr.labels = lbs
        self.accept()


# ---------------------------------------------------------------------------
# Spectrogram Settings Dialog
# ---------------------------------------------------------------------------
class SpectrogramSettingsDialog(QDialog):
    def __init__(self, cfg: SpectrogramConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Spectrogram Settings")
        form = QFormLayout(self)
        self.cmb_win = QComboBox(); self.cmb_win.addItems(SPECTROGRAM_WINDOWS); self.cmb_win.setCurrentText(cfg.window_type)
        self.cmb_size = QComboBox(); self.cmb_size.addItems(["64", "128", "256", "512", "1024", "2048", "4096", "8192", "16384"]); self.cmb_size.setCurrentText(str(cfg.window_size))
        self.cmb_col = QComboBox(); self.cmb_col.addItems(SPECTROGRAM_COLORMAPS); self.cmb_col.setCurrentText(cfg.color_scheme)
        self.cmb_scale = QComboBox(); self.cmb_scale.addItems(SPECTROGRAM_SCALES); self.cmb_scale.setCurrentText(cfg.freq_scale)
        self.sp_min = QDoubleSpinBox(); self.sp_min.setRange(0.0, 20000.0); self.sp_min.setValue(cfg.min_freq)
        self.sp_max = QDoubleSpinBox(); self.sp_max.setRange(100.0, 192000.0); self.sp_max.setValue(cfg.max_freq)
        self.sp_gain = QDoubleSpinBox(); self.sp_gain.setRange(-60.0, 60.0); self.sp_gain.setValue(cfg.gain_db)
        self.sp_range = QDoubleSpinBox(); self.sp_range.setRange(10.0, 140.0); self.sp_range.setValue(cfg.range_db)
        form.addRow("Window Type:", self.cmb_win)
        form.addRow("Window Size:", self.cmb_size)
        form.addRow("Color Scheme:", self.cmb_col)
        form.addRow("Frequency Scale:", self.cmb_scale)
        form.addRow("Min Frequency (Hz):", self.sp_min)
        form.addRow("Max Frequency (Hz):", self.sp_max)
        form.addRow("Gain (dB):", self.sp_gain)
        form.addRow("Range (dB):", self.sp_range)
        row = QHBoxLayout()
        b_c = QPushButton("Cancel"); b_c.clicked.connect(self.reject)
        b_o = QPushButton("Apply"); b_o.setObjectName("PrimaryButton"); b_o.clicked.connect(self._apply)
        row.addWidget(b_c); row.addWidget(b_o)
        form.addRow(row)

    def _apply(self) -> None:
        self.cfg.window_type = self.cmb_win.currentText()
        self.cfg.window_size = int(self.cmb_size.currentText())
        self.cfg.color_scheme = self.cmb_col.currentText()
        self.cfg.freq_scale = self.cmb_scale.currentText()
        self.cfg.min_freq = self.sp_min.value()
        self.cfg.max_freq = self.sp_max.value()
        self.cfg.gain_db = self.sp_gain.value()
        self.cfg.range_db = self.sp_range.value()
        self.accept()


# ---------------------------------------------------------------------------
# Macro Manager & Multi-File Batch Processor Dialog
# ---------------------------------------------------------------------------
class MacroBatchDialog(QDialog):
    def __init__(self, macro_mgr: MacroManager, prefs: PreferencesManager, on_run_project: Callable[[str], None], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.macro_mgr = macro_mgr
        self.prefs = prefs
        self.on_run_project = on_run_project
        self.setWindowTitle("Macro Manager & Batch File Processor")
        self.resize(720, 480)
        lay = QVBoxLayout(self)

        mid = QHBoxLayout()
        # Left: Macro list
        left = QVBoxLayout()
        left.addWidget(QLabel("Macros:"))
        self.lst_macros = QListWidget()
        self.lst_macros.currentTextChanged.connect(self._load_steps)
        left.addWidget(self.lst_macros, 1)
        lrow = QHBoxLayout()
        b_new = QPushButton("New..."); b_new.clicked.connect(self._new_macro)
        b_del = QPushButton("Delete"); b_del.clicked.connect(self._del_macro)
        lrow.addWidget(b_new); lrow.addWidget(b_del)
        left.addLayout(lrow)
        mid.addLayout(left, 1)

        # Right: Steps
        right = QVBoxLayout()
        right.addWidget(QLabel("Macro Steps (Chain of Commands):"))
        self.lst_steps = QListWidget()
        right.addWidget(self.lst_steps, 1)
        srow = QHBoxLayout()
        self.cmb_cmd = QComboBox()
        self.cmb_cmd.addItems(sorted(EFFECT_REGISTRY.keys()) + ["Silence", "ExportWAV", "ExportFLAC", "ExportMP3"])
        b_add_s = QPushButton("+ Insert Step"); b_add_s.clicked.connect(self._add_step)
        b_rm_s = QPushButton("Remove Step"); b_rm_s.clicked.connect(self._rm_step)
        srow.addWidget(self.cmb_cmd, 1); srow.addWidget(b_add_s); srow.addWidget(b_rm_s)
        right.addLayout(srow)
        mid.addLayout(right, 2)
        lay.addLayout(mid, 1)

        brow = QHBoxLayout()
        b_run_p = QPushButton("Apply Macro to Project")
        b_run_p.setObjectName("PrimaryButton")
        b_run_p.clicked.connect(self._run_proj)
        b_batch = QPushButton("Batch Process Files...")
        b_batch.setObjectName("KinoAccentButton")
        b_batch.clicked.connect(self._batch_files)
        b_cls = QPushButton("Close")
        b_cls.clicked.connect(self.accept)
        brow.addWidget(b_run_p); brow.addWidget(b_batch); brow.addStretch(1); brow.addWidget(b_cls)
        lay.addLayout(brow)
        self._refresh_macros()

    def _refresh_macros(self) -> None:
        self.lst_macros.clear()
        for name in self.macro_mgr.macros:
            self.lst_macros.addItem(name)
        if self.lst_macros.count() > 0:
            self.lst_macros.setCurrentRow(0)

    def _load_steps(self, name: str) -> None:
        self.lst_steps.clear()
        for i, st in enumerate(self.macro_mgr.macros.get(name, [])):
            self.lst_steps.addItem(f"{i+1}. {st['command']}  {st.get('params', {})}")

    def _new_macro(self) -> None:
        name, ok = QInputDialog.getText(self, "New Macro", "Macro Name:")
        if ok and name.strip():
            self.macro_mgr.macros[name.strip()] = []
            self.macro_mgr.save()
            self._refresh_macros()

    def _del_macro(self) -> None:
        name = self.lst_macros.currentItem().text() if self.lst_macros.currentItem() else ""
        if name in self.macro_mgr.macros:
            del self.macro_mgr.macros[name]
            self.macro_mgr.save()
            self._refresh_macros()

    def _add_step(self) -> None:
        if not self.lst_macros.currentItem():
            return
        name = self.lst_macros.currentItem().text()
        cmd = self.cmb_cmd.currentText()
        params = default_effect_params(cmd) if cmd in EFFECT_REGISTRY else {}
        self.macro_mgr.macros[name].append({"command": cmd, "params": params})
        self.macro_mgr.save()
        self._load_steps(name)

    def _rm_step(self) -> None:
        if not self.lst_macros.currentItem():
            return
        name = self.lst_macros.currentItem().text()
        r = self.lst_steps.currentRow()
        if 0 <= r < len(self.macro_mgr.macros.get(name, [])):
            self.macro_mgr.macros[name].pop(r)
            self.macro_mgr.save()
            self._load_steps(name)

    def _run_proj(self) -> None:
        if self.lst_macros.currentItem():
            self.on_run_project(self.lst_macros.currentItem().text())
            self.accept()

    def _batch_files(self) -> None:
        if not self.lst_macros.currentItem():
            return
        mname = self.lst_macros.currentItem().text()
        files, _ = QFileDialog.getOpenFileNames(self, "Select Audio Files to Batch Process", "", "Audio Files (*.wav *.flac *.mp3 *.ogg *.m4a *.aiff);;All Files (*.*)")
        if not files:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder for Batch Processed Files")
        if not out_dir:
            return
        ff = self.prefs.get("ffmpeg_path", "")
        ok_cnt = 0
        for fp in files:
            try:
                arr, sr, _ = import_audio_file(fp, ffmpeg_path=ff)
                proc, _ = self.macro_mgr.run_on_audio(mname, arr, sr)
                out_fp = os.path.join(out_dir, os.path.splitext(os.path.basename(fp))[0] + "_macro.wav")
                export_audio_file(out_fp, proc, sr, "WAV", sr, "24-bit PCM", ffmpeg_path=ff)
                ok_cnt += 1
            except Exception as e:
                QMessageBox.warning(self, "Batch Error", f"Failed on {os.path.basename(fp)}: {e}")
        QMessageBox.information(self, "Batch Complete", f"Processed {ok_cnt} / {len(files)} files into:\n{out_dir}")


# ---------------------------------------------------------------------------
# Nyquist Prompt Dialog
# ---------------------------------------------------------------------------
class NyquistPromptDialog(QDialog):
    def __init__(self, on_eval: Callable[[str], str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.on_eval = on_eval
        self.setWindowTitle("Nyquist Prompt — KinoWave")
        self.resize(560, 380)
        lay = QVBoxLayout(self)

        erow = QHBoxLayout()
        erow.addWidget(QLabel("Example:"))
        self.cmb_ex = QComboBox()
        self.examples = {
            "Warm Low-Pass + Boost on Selection (`s`)": "(scale 1.15 (lp s 3200))",
            "Generate Major Chord Pad (3s)": "(mult (sum (scale 0.4 (osc 60 3.0)) (scale 0.35 (osc 64 3.0)) (scale 0.35 (osc 67 3.0))) (pwl 0.2 1.0 2.2 0.8 3.0 0.0))",
            "Ring Modulate Selection at 8 Hz": "(mult s (hzosc 8.0))",
            "Measure RMS & Peak of Selection": "(progn (print (rms s)) (print (peak s)) s)",
        }
        self.cmb_ex.addItems(list(self.examples.keys()))
        self.cmb_ex.currentTextChanged.connect(lambda k: self.ed.setPlainText(self.examples[k]))
        erow.addWidget(self.cmb_ex, 1)
        lay.addLayout(erow)

        self.ed = QPlainTextEdit(next(iter(self.examples.values())))
        self.ed.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        lay.addWidget(self.ed, 1)

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumHeight(90)
        lay.addWidget(self.out)

        brow = QHBoxLayout()
        brow.addStretch(1)
        b_c = QPushButton("Close"); b_c.clicked.connect(self.accept)
        b_r = QPushButton("Run Nyquist Code"); b_r.setObjectName("PrimaryButton"); b_r.clicked.connect(self._run)
        brow.addWidget(b_c); brow.addWidget(b_r)
        lay.addLayout(brow)

    def _run(self) -> None:
        self.out.setPlainText(self.on_eval(self.ed.toPlainText()))


# ---------------------------------------------------------------------------
# Plugin Manager Dialog (Built-in, Nyquist, VST, VST3, LV2, LADSPA, Audio Unit)
# ---------------------------------------------------------------------------
class PluginManagerDialog(QDialog):
    def __init__(
        self,
        pm: PluginManager,
        on_run_nyquist_file: Callable[[str], None],
        on_run_external_plugin: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_add_custom_dir: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.pm = pm
        self.on_run_nyquist_file = on_run_nyquist_file
        self.on_run_external_plugin = on_run_external_plugin
        self.on_add_custom_dir = on_add_custom_dir
        self.setWindowTitle("Plugin Manager (VST3 / VST2 64-bit / LV2 / LADSPA / AU / Nyquist)")
        self.resize(820, 500)
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText("Search plugins by name, type (VST3, VST2, Nyquist), or vendor...")
        self.ed_filter.textChanged.connect(self._refresh)
        top.addWidget(self.ed_filter, 1)
        b_dir = QPushButton("+ Add VST Folder...")
        b_dir.clicked.connect(self._add_dir)
        top.addWidget(b_dir)
        lay.addLayout(top)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["Plugin Name", "Type", "Vendor / Category", "Status", "Path"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lay.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        for lbl, fn in [
            ("Enable", lambda: self._set_en(True)),
            ("Disable", lambda: self._set_en(False)),
            ("Rescan Plugins", self._rescan),
            ("Install Nyquist (.ny)...", self._install_ny),
            ("Open / Apply Selected", self._run_selected),
        ]:
            b = QPushButton(lbl); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch(1)
        b_ok = QPushButton("Close"); b_ok.setObjectName("PrimaryButton"); b_ok.clicked.connect(self.accept)
        row.addWidget(b_ok)
        lay.addLayout(row)
        self._visible_plugins: List[Dict[str, Any]] = []
        self._refresh()

    def _refresh(self) -> None:
        q = self.ed_filter.text().strip().lower()
        self._visible_plugins = [
            pl for pl in self.pm.plugins
            if not q or q in pl["name"].lower() or q in pl["type"].lower() or q in pl["category"].lower()
        ]
        self.tbl.setRowCount(len(self._visible_plugins))
        for i, pl in enumerate(self._visible_plugins):
            self.tbl.setItem(i, 0, QTableWidgetItem(pl["name"]))
            self.tbl.setItem(i, 1, QTableWidgetItem(pl["type"]))
            self.tbl.setItem(i, 2, QTableWidgetItem(pl["category"]))
            self.tbl.setItem(i, 3, QTableWidgetItem("Enabled" if pl["enabled"] else "Disabled"))
            self.tbl.setItem(i, 4, QTableWidgetItem(pl["path"]))

    def _current_plugin(self) -> Optional[Dict[str, Any]]:
        r = self.tbl.currentRow()
        return self._visible_plugins[r] if 0 <= r < len(self._visible_plugins) else None

    def _set_en(self, val: bool) -> None:
        pl = self._current_plugin()
        if pl:
            self.pm.set_enabled(pl["id"], val)
            self._refresh()

    def _rescan(self) -> None:
        self.pm.rescan()
        self._refresh()
        vst3_c = sum(1 for p in self.pm.plugins if p["type"] == "VST3")
        vst2_c = sum(1 for p in self.pm.plugins if p["type"] == "VST2 (64-bit)")
        QMessageBox.information(self, "Rescan Complete", f"Found {len(self.pm.plugins)} total plugins:\n- {vst3_c} VST3 plugins\n- {vst2_c} 64-bit VST2 plugins\n- Plus Built-in DSP & Nyquist plugins.")

    def _add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select Custom VST / VST3 Folder")
        if d:
            if d not in self.pm.custom_dirs:
                self.pm.custom_dirs.append(d)
                if self.on_add_custom_dir:
                    self.on_add_custom_dir(d)
            self._rescan()

    def _install_ny(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Install Nyquist Plugin", "", "Nyquist Plugins (*.ny);;All Files (*.*)")
        if fp:
            dst = self.pm.install_nyquist_plugin(fp)
            self._refresh()
            QMessageBox.information(self, "Installed", f"Installed Nyquist plugin to:\n{dst}")

    def _run_selected(self) -> None:
        pl = self._current_plugin()
        if not pl:
            return
        if pl["type"] == "Nyquist":
            self.on_run_nyquist_file(pl["path"])
            self.accept()
        elif pl["type"] in ("VST3", "VST2 (64-bit)", "Audio Unit", "LADSPA") and self.on_run_external_plugin:
            self.accept()
            self.on_run_external_plugin(pl)
        elif pl["type"] == "VST2 (32-bit)":
            QMessageBox.warning(self, "32-bit Plugin", "This DLL is 32-bit; KinoWave hosts 64-bit VST2 and VST3 plugins. Use the 64-bit or VST3 version.")


# ---------------------------------------------------------------------------
# External Scripting Pipe Console Dialog
# ---------------------------------------------------------------------------
class ScriptingPipeDialog(QDialog):
    def __init__(self, server: ScriptingPipeServer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.server = server
        self.setWindowTitle("External Scripting Pipe (mod-script-pipe)")
        self.resize(620, 420)
        lay = QVBoxLayout(self)

        status = f"ACTIVE on 127.0.0.1:{server.port}" if server.running else "STOPPED"
        lay.addWidget(QLabel(f"Scripting Pipe Server Status: {status}"))
        snippet = (
            f"# External Python control example:\n"
            f"import socket\n"
            f"with socket.create_connection(('127.0.0.1', {server.port})) as s:\n"
            f"    s.sendall(b'GetInfo: Type=Tracks\\n')\n"
            f"    print(s.recv(4096).decode())"
        )
        ex = QPlainTextEdit(snippet)
        ex.setReadOnly(True)
        ex.setMaximumHeight(95)
        ex.setStyleSheet("font-family: Consolas, monospace; font-size: 8.5pt;")
        lay.addWidget(ex)

        cmd_row = QHBoxLayout()
        self.ed_cmd = QLineEdit("GetInfo: Type=Tracks")
        b_send = QPushButton("Send Command")
        b_send.setObjectName("PrimaryButton")
        b_send.clicked.connect(self._send)
        cmd_row.addWidget(self.ed_cmd, 1)
        cmd_row.addWidget(b_send)
        lay.addLayout(cmd_row)

        self.log = QPlainTextEdit("\n".join(server.history))
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: Consolas, monospace;")
        lay.addWidget(self.log, 1)

        b_c = QPushButton("Close"); b_c.clicked.connect(self.accept)
        lay.addWidget(b_c, 0, Qt.AlignmentFlag.AlignRight)

    def _send(self) -> None:
        cmd = self.ed_cmd.text().strip()
        if cmd:
            rep = self.server.handler(cmd)
            self.log.appendPlainText(f"> {cmd}\n< {rep}\n")


# ---------------------------------------------------------------------------
# Preferences & Customization Dialog (Tabbed, Complete)
# ---------------------------------------------------------------------------
class PreferencesDialog(QDialog):
    def __init__(self, prefs: PreferencesManager, on_reset_config: Callable[[], None], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.prefs = prefs
        self.on_reset_config = on_reset_config
        self.setWindowTitle("Preferences — KinoWave")
        self.resize(680, 500)
        lay = QVBoxLayout(self)

        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # Tab 1: Audio & Recording
        t1 = QWidget(); f1 = QFormLayout(t1)
        self.cmb_host = QComboBox()
        for h in list_audio_hosts():
            self.cmb_host.addItem(h["name"], h["index"])
        devs = list_audio_devices()
        self.cmb_in = QComboBox()
        for d in devs["inputs"]:
            self.cmb_in.addItem(d["name"], d["index"])
        self.cmb_out = QComboBox()
        for d in devs["outputs"]:
            self.cmb_out.addItem(d["name"], d["index"])
        self.sp_buf = QSpinBox(); self.sp_buf.setRange(64, 8192); self.sp_buf.setValue(int(prefs.get("buffer_size", 1024)))
        self.sp_lat = QDoubleSpinBox(); self.sp_lat.setRange(-500.0, 500.0); self.sp_lat.setValue(float(prefs.get("latency_ms", 0.0))); self.sp_lat.setSuffix(" ms")
        self.sp_pre = QDoubleSpinBox(); self.sp_pre.setRange(0.5, 10.0); self.sp_pre.setValue(float(prefs.get("preroll_s", 2.0))); self.sp_pre.setSuffix(" s")
        self.cb_overdub = QCheckBox("Overdub: Play other tracks while recording"); self.cb_overdub.setChecked(bool(prefs.get("overdub", True)))
        self.cb_thru = QCheckBox("Software Playthrough (monitor live input)"); self.cb_thru.setChecked(bool(prefs.get("software_playthrough", False)))
        self.cb_sar = QCheckBox("Sound-Activated Recording"); self.cb_sar.setChecked(bool(prefs.get("sound_activated_record", False)))
        self.sp_sardb = QDoubleSpinBox(); self.sp_sardb.setRange(-70.0, -3.0); self.sp_sardb.setValue(float(prefs.get("sound_activation_db", -36.0))); self.sp_sardb.setSuffix(" dB")
        f1.addRow("Audio Host:", self.cmb_host)
        f1.addRow("Recording Device:", self.cmb_in)
        f1.addRow("Playback Device:", self.cmb_out)
        f1.addRow("Buffer Size (samples):", self.sp_buf)
        f1.addRow("Latency Compensation:", self.sp_lat)
        f1.addRow("Punch & Roll Pre-Roll:", self.sp_pre)
        f1.addRow("", self.cb_overdub)
        f1.addRow("", self.cb_thru)
        f1.addRow("", self.cb_sar)
        f1.addRow("Activation Level:", self.sp_sardb)
        tabs.addTab(t1, "Devices & Recording")

        # Tab 2: Quality & Import/Export
        t2 = QWidget(); f2 = QFormLayout(t2)
        self.cmb_sr = QComboBox()
        for r in SAMPLE_RATES:
            self.cmb_sr.addItem(f"{r} Hz", r)
        idx = self.cmb_sr.findData(int(prefs.get("default_sample_rate", 48000)))
        if idx >= 0: self.cmb_sr.setCurrentIndex(idx)
        self.cmb_fmt = QComboBox(); self.cmb_fmt.addItems(SAMPLE_FORMATS); self.cmb_fmt.setCurrentText(str(prefs.get("default_sample_format", "32-bit float")))
        self.cmb_dither = QComboBox(); self.cmb_dither.addItems(["Triangle", "Shaped", "Rectangle", "None"]); self.cmb_dither.setCurrentText(str(prefs.get("dither_mode", "Triangle")))
        self.cmb_res = QComboBox(); self.cmb_res.addItems(["High", "Fast"]); self.cmb_res.setCurrentText(str(prefs.get("resample_quality", "High")))
        self.ed_ext_rules = QPlainTextEdit("\n".join(prefs.get("extended_import_rules", [])))
        self.ed_ext_rules.setMaximumHeight(90)
        f2.addRow("Default Sample Rate:", self.cmb_sr)
        f2.addRow("Default Sample Format:", self.cmb_fmt)
        f2.addRow("Dithering:", self.cmb_dither)
        f2.addRow("Resampling Quality:", self.cmb_res)
        f2.addRow("Extended Import Rules:", self.ed_ext_rules)
        tabs.addTab(t2, "Quality & Import")

        # Tab 3: Interface, Tracks & Mouse
        t3 = QWidget(); f3 = QFormLayout(t3)
        self.cmb_theme = QComboBox(); self.cmb_theme.addItems(["Dark", "Light", "High Contrast"]); self.cmb_theme.setCurrentText(str(prefs.get("theme", "Dark")))
        self.cmb_lang = QComboBox(); self.cmb_lang.addItems(list(TRANSLATIONS.keys())); self.cmb_lang.setCurrentText(str(prefs.get("language", "English")))
        self.cmb_tview = QComboBox(); self.cmb_tview.addItems(["Waveform", "Waveform (dB)", "Spectrogram", "Split View"]); self.cmb_tview.setCurrentText(str(prefs.get("default_track_view", "Waveform")))
        self.sp_zoom = QDoubleSpinBox(); self.sp_zoom.setRange(10.0, 2000.0); self.sp_zoom.setValue(float(prefs.get("default_zoom_pps", 100.0))); self.sp_zoom.setSuffix(" px/s")
        self.cb_wheel = QCheckBox("Mouse wheel zooms timeline directly"); self.cb_wheel.setChecked(bool(prefs.get("mouse_wheel_zoom", True)))
        f3.addRow("Theme:", self.cmb_theme)
        f3.addRow("Interface Language:", self.cmb_lang)
        f3.addRow("Default Track View:", self.cmb_tview)
        f3.addRow("Default Zoom:", self.sp_zoom)
        f3.addRow("", self.cb_wheel)
        tabs.addTab(t3, "Interface & Tracks")

        # Tab 4: Libraries, Directories & Modules
        t4 = QWidget(); f4 = QFormLayout(t4)
        self.ed_ff = QLineEdit(str(prefs.get("ffmpeg_path", "") or find_ffmpeg() or ""))
        self.ed_tmp = QLineEdit(str(prefs.get("temp_dir", "")))
        self.ed_prj = QLineEdit(str(prefs.get("project_dir", "")))
        self.cb_warn = QCheckBox("Show confirmation warnings"); self.cb_warn.setChecked(bool(prefs.get("show_warnings", True)))
        self.cb_upd = QCheckBox("Check for updates on startup"); self.cb_upd.setChecked(bool(prefs.get("check_updates", False)))
        self.cb_pipe = QCheckBox("Enable External Scripting Pipe (mod-script-pipe)"); self.cb_pipe.setChecked(bool(prefs.get("enable_scripting_pipe", True)))
        f4.addRow("FFmpeg Executable:", self.ed_ff)
        f4.addRow("Temporary Directory:", self.ed_tmp)
        f4.addRow("Default Projects Folder:", self.ed_prj)
        f4.addRow("", self.cb_warn)
        f4.addRow("", self.cb_upd)
        f4.addRow("", self.cb_pipe)
        tabs.addTab(t4, "Libraries & Modules")

        # Tab 5: Keyboard Shortcuts (Edit, Import, Export)
        t5 = QWidget(); v5 = QVBoxLayout(t5)
        self.tbl_sc = QTableWidget(0, 2)
        self.tbl_sc.setHorizontalHeaderLabels(["Command", "Shortcut"])
        self.tbl_sc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        sc_map = prefs.get("shortcuts", DEFAULT_SHORTCUTS)
        self.tbl_sc.setRowCount(len(sc_map))
        for i, (k, v) in enumerate(sorted(sc_map.items())):
            it_k = QTableWidgetItem(k)
            it_k.setFlags(it_k.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_sc.setItem(i, 0, it_k)
            self.tbl_sc.setItem(i, 1, QTableWidgetItem(v))
        v5.addWidget(self.tbl_sc, 1)
        sc_btns = QHBoxLayout()
        b_imp = QPushButton("Import Shortcuts..."); b_imp.clicked.connect(self._imp_sc)
        b_exp = QPushButton("Export Shortcuts..."); b_exp.clicked.connect(self._exp_sc)
        sc_btns.addWidget(b_imp); sc_btns.addWidget(b_exp); sc_btns.addStretch(1)
        v5.addLayout(sc_btns)
        tabs.addTab(t5, "Keyboard Shortcuts")

        brow = QHBoxLayout()
        b_rst = QPushButton("Reset All Configuration")
        b_rst.setObjectName("DangerButton")
        b_rst.clicked.connect(self._reset_all)
        brow.addWidget(b_rst)
        brow.addStretch(1)
        b_c = QPushButton("Cancel"); b_c.clicked.connect(self.reject)
        b_ok = QPushButton("Save Preferences"); b_ok.setObjectName("PrimaryButton"); b_ok.clicked.connect(self._save)
        brow.addWidget(b_c); brow.addWidget(b_ok)
        lay.addLayout(brow)

    def _imp_sc(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Import Shortcuts", "", "JSON (*.json)")
        if fp:
            sc = self.prefs.import_shortcuts(fp)
            for i in range(self.tbl_sc.rowCount()):
                k = self.tbl_sc.item(i, 0).text()
                if k in sc:
                    self.tbl_sc.item(i, 1).setText(sc[k])

    def _exp_sc(self) -> None:
        fp, _ = QFileDialog.getSaveFileName(self, "Export Shortcuts", "kinowave_shortcuts.json", "JSON (*.json)")
        if fp:
            self.prefs.export_shortcuts(fp)

    def _reset_all(self) -> None:
        if QMessageBox.question(self, "Reset Configuration", "Reset all KinoWave preferences and shortcuts to factory defaults?") == QMessageBox.StandardButton.Yes:
            self.on_reset_config()
            self.accept()

    def _save(self) -> None:
        sc = {}
        for i in range(self.tbl_sc.rowCount()):
            sc[self.tbl_sc.item(i, 0).text()] = self.tbl_sc.item(i, 1).text().strip()
        updates = {
            "buffer_size": self.sp_buf.value(),
            "latency_ms": self.sp_lat.value(),
            "preroll_s": self.sp_pre.value(),
            "overdub": self.cb_overdub.isChecked(),
            "software_playthrough": self.cb_thru.isChecked(),
            "sound_activated_record": self.cb_sar.isChecked(),
            "sound_activation_db": self.sp_sardb.value(),
            "default_sample_rate": int(self.cmb_sr.currentData()),
            "default_sample_format": self.cmb_fmt.currentText(),
            "dither_mode": self.cmb_dither.currentText(),
            "resample_quality": self.cmb_res.currentText(),
            "extended_import_rules": [ln.strip() for ln in self.ed_ext_rules.toPlainText().splitlines() if ln.strip()],
            "theme": self.cmb_theme.currentText(),
            "language": self.cmb_lang.currentText(),
            "default_track_view": self.cmb_tview.currentText(),
            "default_zoom_pps": self.sp_zoom.value(),
            "mouse_wheel_zoom": self.cb_wheel.isChecked(),
            "ffmpeg_path": self.ed_ff.text().strip(),
            "temp_dir": self.ed_tmp.text().strip(),
            "project_dir": self.ed_prj.text().strip(),
            "show_warnings": self.cb_warn.isChecked(),
            "check_updates": self.cb_upd.isChecked(),
            "enable_scripting_pipe": self.cb_pipe.isChecked(),
            "shortcuts": sc,
        }
        self.prefs.data.update(updates)
        self.prefs.save()
        self.accept()


# ---------------------------------------------------------------------------
# KinoCloud Share, Diagnostics/Logs & Built-in Manual Dialogs
# ---------------------------------------------------------------------------
class CloudShareDialog(QDialog):
    def __init__(self, project: KinoWaveProject, cloud: KinoCloudAudioManager, on_open_cloud: Callable[[str], None], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project = project
        self.cloud = cloud
        self.on_open_cloud = on_open_cloud
        self.setWindowTitle("KinoCloud — Save & Share Audio Project Online")
        self.resize(560, 400)
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.ed_notes = QLineEdit()
        self.ed_notes.setPlaceholderText("Release notes or collaborator message...")
        b_pub = QPushButton("Save & Publish Share Link")
        b_pub.setObjectName("PrimaryButton")
        b_pub.clicked.connect(self._publish)
        row.addWidget(self.ed_notes, 1)
        row.addWidget(b_pub)
        lay.addLayout(row)

        self.lst = QListWidget()
        lay.addWidget(self.lst, 1)

        brow = QHBoxLayout()
        b_open = QPushButton("Open Selected Cloud Project")
        b_open.clicked.connect(self._open_sel)
        b_c = QPushButton("Close"); b_c.clicked.connect(self.accept)
        brow.addWidget(b_open); brow.addStretch(1); brow.addWidget(b_c)
        lay.addLayout(brow)
        self._refresh()

    def _refresh(self) -> None:
        self.lst.clear()
        for item in self.cloud.list_cloud_projects():
            it = QListWidgetItem(f"{item['name']}  |  {item['saved_at']}  |  {item['duration_s']}s  |  {item['share_url']}")
            it.setData(Qt.ItemDataRole.UserRole, item)
            self.lst.addItem(it)

    def _publish(self) -> None:
        entry = self.cloud.publish_project(self.project, notes=self.ed_notes.text().strip())
        self._refresh()
        QMessageBox.information(self, "Published to KinoCloud", f"Project saved & shareable web player generated!\n\nShare URL: {entry['share_url']}\nHTML Player: {entry['share_html']}")

    def _open_sel(self) -> None:
        it = self.lst.currentItem()
        if it:
            d = it.data(Qt.ItemDataRole.UserRole)
            if d and os.path.isfile(d["kwp_path"]):
                self.on_open_cloud(d["kwp_path"])
                self.accept()


class DiagnosticsDialog(QDialog):
    def __init__(self, logs: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Audio Device Info & Diagnostics Log")
        self.resize(680, 460)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        t_dev = QPlainTextEdit(get_audio_device_diagnostics()); t_dev.setReadOnly(True); t_dev.setStyleSheet("font-family: Consolas, monospace;")
        t_log = QPlainTextEdit("\n".join(logs) if logs else "No log events recorded yet."); t_log.setReadOnly(True); t_log.setStyleSheet("font-family: Consolas, monospace;")
        tabs.addTab(t_dev, "Audio Device Info")
        tabs.addTab(t_log, "Application Log")
        lay.addWidget(tabs, 1)
        b = QPushButton("Close"); b.clicked.connect(self.accept)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)


class ManualDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("KinoWave Built-in Manual & Reference")
        self.resize(680, 520)
        lay = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml("""
        <h2 style="color:#10D9A0;">KinoWave — KinoSuite Multitrack Audio Platform (v1.0)</h2>
        <p><b>Free &amp; Open Source</b> · Windows, macOS &amp; Linux · 32-bit Float up to 384 kHz.</p>
        <h3>Quick Start &amp; Essential Shortcuts</h3>
        <ul>
          <li><b>Space</b>: Play / Stop · <b>P</b>: Pause · <b>R</b>: Record · <b>Shift+D</b>: Punch-and-Roll Record · <b>L</b>: Toggle Loop</li>
          <li><b>C</b>: Cut Preview (listen before &amp; after selection skipping the cut)</li>
          <li><b>F1</b> Selection · <b>F2</b> Volume Envelope · <b>F3</b> Sample Draw (zoom in to draw individual samples) · <b>F6</b> Multi-Tool</li>
          <li><b>Multi-Tool (F6)</b>: Drag clip header to move within/between tracks · Drag clip edges to non-destructively trim · <b>Alt+Drag</b> clip edge to time-stretch · Drag top/bottom for envelope · Drag center to select (or draw a frequency box in Spectrogram/Split view!).</li>
          <li><b>Ctrl+I</b> Split Clip · <b>Ctrl+J</b> Join Clips · <b>Ctrl+B</b> Add Label · <b>Z</b> Snap to Zero Crossings · <b>Ctrl+R</b> Repeat Last Effect</li>
          <li><b>Timeline Ruler</b>: Click or drag to Quick-Play · <b>Shift+Drag</b> to set Loop Region · <b>Right-Drag</b> to Scrub &amp; Seek!</li>
        </ul>
        <h3>Real-Time &amp; Destructive Effects</h3>
        <p>Click <b>FX</b> on any track header (or the Master FX button) to stack non-destructive real-time effects, or apply any of the 45+ effects destructively from the <b>Effect</b> menu with live Preview and Presets.</p>
        <h3>Automation, Nyquist &amp; Scripting Pipe</h3>
        <p>Build command chains and batch-process folders under <b>Tools -&gt; Macros</b>, execute Lisp audio scripts in <b>Tools -&gt; Nyquist Prompt</b>, or drive KinoWave externally via <b>Tools -&gt; External Scripting Pipe</b>.</p>
        """)
        lay.addWidget(browser, 1)
        b = QPushButton("Close"); b.clicked.connect(self.accept)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)
