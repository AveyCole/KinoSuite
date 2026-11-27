"""KinoWave Automation & Extensibility Suite:
- Macros & Multi-File Batch Processing
- Embedded Nyquist Lisp Audio Scripting Interpreter + .ny Plugin Loader/Installer
- External Scripting Pipe Server (mod-script-pipe compatible)
- Plugin Manager (Built-in, Nyquist, VST, VST3, LV2, LADSPA, Audio Unit discovery)
- Preferences, Keyboard Shortcuts Import/Export, Tag Templates, Localization (i18n)
- Performance Benchmarks
"""
from __future__ import annotations

import json
import math
import os
import platform
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .dsp import (
    EFFECT_REGISTRY,
    ensure_2d,
    fx_high_pass,
    fx_low_pass,
    fx_reverb,
    gen_noise,
    gen_silence,
    gen_tone,
    resample_audio,
    run_effect,
)


# ---------------------------------------------------------------------------
# Multi-Language Interface Strings (English, Spanish, French, German, Japanese)
# ---------------------------------------------------------------------------
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "English": {
        "File": "&File", "Edit": "&Edit", "Select": "&Select", "View": "&View",
        "Transport": "&Transport", "Tracks": "T&racks", "Generate": "&Generate",
        "Effect": "Effe&ct", "Analyze": "&Analyze", "Tools": "Too&ls", "Help": "&Help",
        "Ready": "Ready — 32-bit float engine",
    },
    "Español": {
        "File": "&Archivo", "Edit": "&Editar", "Select": "&Seleccionar", "View": "&Ver",
        "Transport": "&Transporte", "Tracks": "&Pistas", "Generate": "&Generar",
        "Effect": "Efe&cto", "Analyze": "A&nalizar", "Tools": "&Herramientas", "Help": "A&yuda",
        "Ready": "Listo — Motor de 32 bits flotante",
    },
    "Français": {
        "File": "&Fichier", "Edit": "&Édition", "Select": "&Sélectionner", "View": "&Affichage",
        "Transport": "&Transport", "Tracks": "&Pistes", "Generate": "&Générer",
        "Effect": "Effe&ts", "Analyze": "&Analyse", "Tools": "&Outils", "Help": "&Aide",
        "Ready": "Prêt — Moteur 32 bits flottant",
    },
    "Deutsch": {
        "File": "&Datei", "Edit": "&Bearbeiten", "Select": "&Auswählen", "View": "&Ansicht",
        "Transport": "&Transport", "Tracks": "&Spuren", "Generate": "&Erzeugen",
        "Effect": "Effe&kt", "Analyze": "&Analyse", "Tools": "&Werkzeuge", "Help": "&Hilfe",
        "Ready": "Bereit — 32-Bit-Float-Engine",
    },
    "日本語": {
        "File": "ファイル(&F)", "Edit": "編集(&E)", "Select": "選択(&S)", "View": "表示(&V)",
        "Transport": "トランスポート(&T)", "Tracks": "トラック(&R)", "Generate": "ジェネレーター(&G)",
        "Effect": "エフェクト(&C)", "Analyze": "解析(&A)", "Tools": "ツール(&L)", "Help": "ヘルプ(&H)",
        "Ready": "準備完了 — 32ビット浮動小数点エンジン",
    },
}


# ---------------------------------------------------------------------------
# Preferences, Shortcuts, Recent Files & Metadata Tag Templates
# ---------------------------------------------------------------------------
DEFAULT_SHORTCUTS: Dict[str, str] = {
    "file_new": "Ctrl+N",
    "file_open": "Ctrl+O",
    "file_save": "Ctrl+S",
    "file_save_as": "Ctrl+Shift+S",
    "file_export": "Ctrl+Shift+E",
    "edit_undo": "Ctrl+Z",
    "edit_redo": "Ctrl+Y",
    "edit_cut": "Ctrl+X",
    "edit_copy": "Ctrl+C",
    "edit_paste": "Ctrl+V",
    "edit_delete": "Del",
    "edit_duplicate": "Ctrl+D",
    "edit_split": "Ctrl+I",
    "edit_join": "Ctrl+J",
    "edit_silence": "Ctrl+L",
    "edit_trim": "Ctrl+T",
    "select_all": "Ctrl+A",
    "select_none": "Ctrl+Shift+A",
    "transport_play_stop": "Space",
    "transport_pause": "P",
    "transport_record": "R",
    "transport_punch_roll": "Shift+D",
    "transport_loop": "L",
    "transport_cut_preview": "C",
    "tool_select": "F1",
    "tool_envelope": "F2",
    "tool_draw": "F3",
    "tool_multi": "F6",
    "zoom_in": "Ctrl+1",
    "zoom_normal": "Ctrl+2",
    "zoom_out": "Ctrl+3",
    "zoom_fit_project": "Ctrl+F",
    "zoom_fit_selection": "Ctrl+E",
    "add_label": "Ctrl+B",
    "repeat_last_effect": "Ctrl+R",
    "find_zero_crossings": "Z",
    "seek_short_left": "Left",
    "seek_short_right": "Right",
    "seek_long_left": "Shift+Left",
    "seek_long_right": "Shift+Right",
    "preferences": "Ctrl+P",
}


class PreferencesManager:
    """Manages all KinoWave settings, keyboard shortcuts, recent files, and tag templates."""

    DEFAULTS: Dict[str, Any] = {
        "theme": "Dark",
        "language": "English",
        "default_sample_rate": 48000,
        "default_sample_format": "32-bit float",
        "dither_mode": "Triangle",
        "resample_quality": "High",
        "buffer_size": 1024,
        "latency_ms": 0.0,
        "preroll_s": 2.0,
        "cut_preview_before_s": 1.5,
        "cut_preview_after_s": 1.5,
        "short_jump_s": 1.0,
        "long_jump_s": 10.0,
        "overdub": True,
        "software_playthrough": False,
        "sound_activated_record": False,
        "sound_activation_db": -36.0,
        "default_zoom_pps": 100.0,
        "default_track_view": "Waveform",
        "mouse_wheel_zoom": True,
        "ffmpeg_path": "",
        "temp_dir": "",
        "project_dir": "",
        "custom_vst_dirs": [],
        "extended_import_rules": ["*.mp3:FFmpeg", "*.m4a:FFmpeg", "*.flac:FFmpeg", "*.wav:Native"],
        "show_warnings": True,
        "check_updates": False,
        "enable_scripting_pipe": True,
        "scripting_pipe_port": 47921,
        "recent_files": [],
        "shortcuts": dict(DEFAULT_SHORTCUTS),
        "tag_templates": {
            "Podcast Episode": {"genre": "Podcast", "album": "Season 1", "comments": "Mastered in KinoWave"},
            "Music Single": {"genre": "Electronic", "year": "2026", "comments": "32-bit Float Mix"},
        },
    }

    def __init__(self, config_dir: str) -> None:
        self.config_dir = config_dir
        os.makedirs(self.config_dir, exist_ok=True)
        self.path = os.path.join(self.config_dir, "preferences.json")
        self.data: Dict[str, Any] = json.loads(json.dumps(self.DEFAULTS))
        self.load()

    def load(self) -> None:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                for k, v in loaded.items():
                    self.data[k] = v
            except Exception:
                pass

    def save(self) -> None:
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def reset_defaults(self) -> None:
        self.data = json.loads(json.dumps(self.DEFAULTS))
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, self.DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def add_recent_file(self, path: str) -> None:
        rec = [p for p in self.data.get("recent_files", []) if p != path]
        rec.insert(0, path)
        self.data["recent_files"] = rec[:15]
        self.save()

    def export_shortcuts(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data.get("shortcuts", DEFAULT_SHORTCUTS), f, indent=2)

    def import_shortcuts(self, path: str) -> Dict[str, str]:
        with open(path, "r", encoding="utf-8") as f:
            sc = json.load(f)
        if isinstance(sc, dict):
            merged = dict(DEFAULT_SHORTCUTS)
            merged.update({str(k): str(v) for k, v in sc.items()})
            self.data["shortcuts"] = merged
            self.save()
        return self.data["shortcuts"]


# ---------------------------------------------------------------------------
# Macros & Batch Processor
# ---------------------------------------------------------------------------
class MacroManager:
    """Build, edit, persist, and run multi-step command/effect macros + batch files."""

    DEFAULT_MACROS: Dict[str, List[Dict[str, Any]]] = {
        "Podcast Voice Polish": [
            {"command": "High-Pass Filter", "params": {"cutoff_hz": 80.0, "rolloff_db": 12}},
            {"command": "Noise Reduction", "params": {"reduction_db": 10.0, "sensitivity": 5.0}},
            {"command": "Compressor", "params": {"threshold_db": -18.0, "ratio": 3.5, "makeup_gain": True}},
            {"command": "Loudness Normalization", "params": {"mode": "LUFS", "target_db": -16.0}},
            {"command": "Limiter", "params": {"limit_type": "Soft Limit", "limit_db": -1.0}},
        ],
        "Broadcast Master & Export WAV": [
            {"command": "Normalize", "params": {"target_db": -1.0, "remove_dc": True}},
            {"command": "Loudness Normalization", "params": {"mode": "LUFS", "target_db": -14.0}},
            {"command": "Limiter", "params": {"limit_type": "Soft Limit", "limit_db": -0.5}},
            {"command": "ExportWAV", "params": {}},
        ],
        "Fade In/Out + Normalize": [
            {"command": "Fade In", "params": {}},
            {"command": "Studio Fade Out", "params": {}},
            {"command": "Normalize", "params": {"target_db": -1.0}},
        ],
    }

    def __init__(self, config_dir: str) -> None:
        self.path = os.path.join(config_dir, "macros.json")
        self.macros: Dict[str, List[Dict[str, Any]]] = json.loads(json.dumps(self.DEFAULT_MACROS))
        self.load()

    def load(self) -> None:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.macros = json.load(f)
            except Exception:
                pass

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.macros, f, indent=2)

    def run_on_audio(
        self,
        macro_name: str,
        audio: np.ndarray,
        sr: int,
        extra_ctx: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, List[str]]:
        """Execute all DSP steps in a macro on an audio array and return (audio, log)."""
        steps = self.macros.get(macro_name, [])
        cur = ensure_2d(audio).copy()
        logs: List[str] = []
        for st in steps:
            cmd = st.get("command", "")
            params = st.get("params", {})
            if cmd in EFFECT_REGISTRY:
                cur = run_effect(cmd, cur, sr, params, extra_ctx=extra_ctx)
                logs.append(f"Applied {cmd}")
            elif cmd == "Silence":
                cur[:] = 0.0
                logs.append("Silenced audio")
            elif cmd.startswith("Export"):
                logs.append(f"Export step ({cmd}) queued")
            else:
                logs.append(f"Skipped unknown step: {cmd}")
        return cur, logs


# ---------------------------------------------------------------------------
# Embedded Nyquist Mini-Interpreter + .ny Plugin Support
# ---------------------------------------------------------------------------
class NyquistInterpreter:
    """Lightweight S-expression Nyquist/XLISP audio engine supporting both
    synthesizing audio and processing the current track selection (`s`)."""

    def __init__(self) -> None:
        self.env: Dict[str, Any] = {}

    @staticmethod
    def _tokenize(code: str) -> List[str]:
        cleaned_lines = []
        for line in code.splitlines():
            if ";" in line:
                line = line[: line.index(";")]
            cleaned_lines.append(line)
        src = "\n".join(cleaned_lines)
        tokens: List[str] = []
        i = 0
        while i < len(src):
            c = src[i]
            if c.isspace():
                i += 1
            elif c in "()":
                tokens.append(c)
                i += 1
            elif c == '"':
                j = i + 1
                while j < len(src) and src[j] != '"':
                    j += 1
                tokens.append(src[i : j + 1])
                i = j + 1
            else:
                j = i
                while j < len(src) and not src[j].isspace() and src[j] not in "()":
                    j += 1
                tokens.append(src[i:j])
                i = j
        return tokens

    @staticmethod
    def _parse(tokens: List[str]) -> List[Any]:
        exprs: List[Any] = []
        idx = 0

        def read_expr() -> Any:
            nonlocal idx
            tok = tokens[idx]
            idx += 1
            if tok == "(":
                lst = []
                while idx < len(tokens) and tokens[idx] != ")":
                    lst.append(read_expr())
                if idx < len(tokens):
                    idx += 1
                return lst
            if tok.startswith('"') and tok.endswith('"'):
                return ("str", tok[1:-1])
            try:
                if "." in tok or "e" in tok.lower():
                    return float(tok)
                return int(tok)
            except ValueError:
                return tok.lower()

        while idx < len(tokens):
            exprs.append(read_expr())
        return exprs

    def evaluate(self, code: str, selection: Optional[np.ndarray], sr: int, duration_s: float = 2.0) -> Tuple[Any, str]:
        """Run Nyquist S-expression code. Returns (result_audio_or_value, stdout_msg)."""
        tokens = self._tokenize(code)
        if not tokens:
            return None, "Empty Nyquist script."
        exprs = self._parse(tokens)
        sel = ensure_2d(selection).copy() if (selection is not None and selection.size > 0) else None
        dur = (sel.shape[1] / sr) if sel is not None else max(0.5, duration_s)

        local_env: Dict[str, Any] = {
            "s": sel,
            "*track*": sel,
            "*sound-srate*": float(sr),
            "len": float(sel.shape[1]) if sel is not None else float(int(dur * sr)),
            "pi": math.pi,
            "t": True,
            "nil": None,
        }
        logs: List[str] = []

        def align_arrays(vals: List[Any]) -> List[np.ndarray]:
            arrs = [v for v in vals if isinstance(v, np.ndarray)]
            max_len = max((a.shape[1] for a in arrs), default=int(dur * sr))
            max_ch = max((a.shape[0] for a in arrs), default=1)
            out = []
            for v in vals:
                if isinstance(v, np.ndarray):
                    a = v
                    if a.shape[0] == 1 and max_ch == 2:
                        a = np.vstack([a, a])
                    if a.shape[1] < max_len:
                        a = np.pad(a, ((0, 0), (0, max_len - a.shape[1])))
                    out.append(a[:, :max_len])
                else:
                    out.append(np.full((max_ch, max_len), float(v), dtype=np.float32))
            return out

        def ev(expr: Any) -> Any:
            if isinstance(expr, (int, float)):
                return float(expr)
            if isinstance(expr, tuple) and expr[0] == "str":
                return expr[1]
            if isinstance(expr, str):
                if expr in local_env:
                    return local_env[expr]
                raise NameError(f"Unbound Nyquist symbol: {expr}")
            if not isinstance(expr, list) or not expr:
                return None

            op = expr[0]
            args = expr[1:]
            if op in ("setf", "setq"):
                val = ev(args[1])
                local_env[str(args[0])] = val
                return val
            if op == "let":
                saved = dict(local_env)
                for binding in args[0]:
                    local_env[str(binding[0])] = ev(binding[1])
                res = None
                for body in args[1:]:
                    res = ev(body)
                local_env.clear()
                local_env.update(saved)
                return res
            if op == "print":
                v = ev(args[0])
                logs.append(str(v))
                return v
            if op == "progn":
                res = None
                for a in args:
                    res = ev(a)
                return res

            evals = [ev(a) for a in args]
            if op == "+":
                return sum(evals)
            if op == "-":
                return -evals[0] if len(evals) == 1 else evals[0] - sum(evals[1:])
            if op == "*":
                r = 1.0
                for v in evals:
                    r *= v
                return r
            if op == "/":
                return evals[0] / max(1e-9, evals[1])
            if op == "hz-to-step":
                return 69.0 + 12.0 * math.log2(max(1e-6, evals[0]) / 440.0)
            if op == "step-to-hz":
                return 440.0 * (2.0 ** ((evals[0] - 69.0) / 12.0))
            if op == "db-to-linear":
                return 10.0 ** (evals[0] / 20.0)
            if op == "linear-to-db":
                return 20.0 * math.log10(max(1e-9, evals[0]))
            if op == "osc":
                pitch = evals[0] if len(evals) >= 1 else 60.0
                d = evals[1] if len(evals) >= 2 else dur
                freq = 440.0 * (2.0 ** ((pitch - 69.0) / 12.0))
                return gen_tone(sr, duration_s=d, waveform="Sine", freq_hz=freq, amplitude=0.8)
            if op == "hzosc":
                freq = evals[0] if len(evals) >= 1 else 440.0
                d = evals[1] if len(evals) >= 2 else dur
                return gen_tone(sr, duration_s=d, waveform="Sine", freq_hz=freq, amplitude=0.8)
            if op == "osc-saw":
                freq = evals[0] if len(evals) >= 1 else 220.0
                d = evals[1] if len(evals) >= 2 else dur
                return gen_tone(sr, duration_s=d, waveform="Sawtooth", freq_hz=freq, amplitude=0.7)
            if op == "osc-tri":
                freq = evals[0] if len(evals) >= 1 else 220.0
                d = evals[1] if len(evals) >= 2 else dur
                return gen_tone(sr, duration_s=d, waveform="Triangle", freq_hz=freq, amplitude=0.8)
            if op == "noise":
                d = evals[0] if len(evals) >= 1 else dur
                return gen_noise(sr, duration_s=d, noise_type="White", amplitude=0.5)
            if op == "s-rest":
                d = evals[0] if len(evals) >= 1 else dur
                return gen_silence(sr, duration_s=d)
            if op in ("mult", "prod"):
                arrs = align_arrays(evals)
                r = arrs[0].copy()
                for a in arrs[1:]:
                    r *= a
                return r
            if op in ("sum", "sim"):
                arrs = align_arrays(evals)
                r = np.zeros_like(arrs[0])
                for a in arrs:
                    r += a
                return r
            if op == "seq":
                arrs = [v for v in evals if isinstance(v, np.ndarray)]
                return np.concatenate(arrs, axis=1) if arrs else gen_silence(sr, 0.1)
            if op == "scale":
                return ensure_2d(evals[1]) * float(evals[0])
            if op == "clip":
                lim = abs(float(evals[1]))
                return np.clip(ensure_2d(evals[0]), -lim, lim).astype(np.float32)
            if op == "lp":
                return fx_low_pass(ensure_2d(evals[0]), sr, cutoff_hz=float(evals[1]), rolloff_db=12)
            if op == "hp":
                return fx_high_pass(ensure_2d(evals[0]), sr, cutoff_hz=float(evals[1]), rolloff_db=12)
            if op == "peak":
                return float(np.max(np.abs(ensure_2d(evals[0]))))
            if op == "rms":
                a = ensure_2d(evals[0])
                return float(np.sqrt(np.mean(a.astype(np.float64) ** 2)))
            if op == "pwl":
                # Piece-wise linear envelope: (pwl t1 v1 t2 v2 ... tn)
                pairs = [(0.0, 0.0)]
                for i in range(0, len(evals) - 1, 2):
                    pairs.append((float(evals[i]), float(evals[i + 1])))
                if len(evals) % 2 == 1:
                    pairs.append((float(evals[-1]), 0.0))
                max_t = max(p[0] for p in pairs)
                n = max(1, int(round(max_t * sr)))
                t = np.linspace(0.0, max_t, n)
                env = np.interp(t, [p[0] for p in pairs], [p[1] for p in pairs]).astype(np.float32)
                return env[None, :]
            if op == "env":
                t1, t2, t4, l1, l2, l3 = [float(x) for x in evals[:6]]
                d = float(evals[6]) if len(evals) > 6 else dur
                n = max(1, int(round(d * sr)))
                t = np.linspace(0.0, d, n)
                xs = [0.0, t1, t1 + t2, max(t1 + t2, d - t4), d]
                ys = [0.0, l1, l2, l3, 0.0]
                return np.interp(t, xs, ys).astype(np.float32)[None, :]
            raise ValueError(f"Unknown Nyquist function: {op}")

        result = None
        for ex in exprs:
            result = ev(ex)
        msg = "\n".join(logs) if logs else ("Nyquist audio buffer generated." if isinstance(result, np.ndarray) else f"Nyquist returned: {result}")
        return result, msg


# ---------------------------------------------------------------------------
# Plugin Manager (Built-in, Nyquist .ny, VST, VST3, LV2, LADSPA, Audio Unit)
# ---------------------------------------------------------------------------
class PluginManager:
    """Discovers, enables/disables, rescans, and installs Nyquist, VST, VST3, LV2,
    LADSPA, and Audio Unit plugins."""

    def __init__(self, app_root: str, config_dir: str, custom_dirs: Optional[List[str]] = None) -> None:
        self.app_root = app_root
        self.nyquist_dir = os.path.join(app_root, "plugins", "nyquist")
        os.makedirs(self.nyquist_dir, exist_ok=True)
        self.state_path = os.path.join(config_dir, "plugins_registry.json")
        self.custom_dirs: List[str] = list(custom_dirs or [])
        self.plugins: List[Dict[str, Any]] = []
        self._install_default_nyquist_plugins()
        self.rescan()

    def _install_default_nyquist_plugins(self) -> None:
        sample_ny = os.path.join(self.nyquist_dir, "warm_harmonic_shimmer.ny")
        if not os.path.isfile(sample_ny):
            with open(sample_ny, "w", encoding="utf-8") as f:
                f.write(
                    ";nyquist plug-in\n"
                    ";version 4\n"
                    ";type process\n"
                    ';name "Warm Harmonic Shimmer (Nyquist)"\n'
                    ";info \"Adds gentle harmonic presence and low-pass warmth\"\n"
                    "(sum (scale 0.85 s) (scale 0.15 (lp s 2800)))\n"
                )
        chime_ny = os.path.join(self.nyquist_dir, "studio_chime.ny")
        if not os.path.isfile(chime_ny):
            with open(chime_ny, "w", encoding="utf-8") as f:
                f.write(
                    ";nyquist plug-in\n"
                    ";version 4\n"
                    ";type generate\n"
                    ';name "Studio Bell Chime (Nyquist)"\n'
                    "(mult (sum (scale 0.6 (osc 72 2.0)) (scale 0.3 (osc 79 2.0)) (scale 0.15 (osc 84 2.0))) (pwl 0.01 1.0 0.4 0.35 2.0 0.0))\n"
                )

    def _standard_plugin_dirs(self) -> List[Tuple[str, str, Tuple[str, ...]]]:
        sys_name = platform.system()
        dirs: List[Tuple[str, str, Tuple[str, ...]]] = [("Nyquist", self.nyquist_dir, (".ny",))]
        if sys_name == "Windows":
            pf = os.environ.get("ProgramFiles", r"C:\Program Files")
            cf = os.environ.get("CommonProgramFiles", r"C:\Program Files\Common Files")
            dirs.extend([
                ("VST3", os.path.join(cf, "VST3"), (".vst3",)),
                ("VST", os.path.join(pf, "VstPlugins"), (".dll",)),
                ("VST", os.path.join(pf, "Steinberg", "VstPlugins"), (".dll",)),
                ("LV2", os.path.join(cf, "LV2"), (".lv2",)),
                ("LADSPA", os.path.join(pf, "LADSPA"), (".dll",)),
            ])
        elif sys_name == "Darwin":
            dirs.extend([
                ("VST3", "/Library/Audio/Plug-Ins/VST3", (".vst3",)),
                ("VST", "/Library/Audio/Plug-Ins/VST", (".vst",)),
                ("Audio Unit", "/Library/Audio/Plug-Ins/Components", (".component",)),
                ("LV2", "/Library/Audio/Plug-Ins/LV2", (".lv2",)),
                ("LADSPA", "/Library/Audio/Plug-Ins/LADSPA", (".so", ".dylib")),
            ])
        else:
            dirs.extend([
                ("VST3", "/usr/lib/vst3", (".vst3",)),
                ("VST", "/usr/lib/vst", (".so",)),
                ("LV2", "/usr/lib/lv2", (".lv2",)),
                ("LADSPA", "/usr/lib/ladspa", (".so",)),
            ])
        return dirs

    def rescan(self) -> List[Dict[str, Any]]:
        old_states = {}
        if os.path.isfile(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    for item in json.load(f):
                        old_states[item["id"]] = bool(item.get("enabled", True))
            except Exception:
                pass

        found: List[Dict[str, Any]] = []
        # 1. Built-in KinoWave DSP plugins
        for name, spec in EFFECT_REGISTRY.items():
            pid = f"builtin:{name}"
            found.append({
                "id": pid,
                "name": name,
                "type": "Built-in",
                "category": spec["category"],
                "path": "KinoWave Core DSP",
                "enabled": old_states.get(pid, True),
            })

        # 2. Recursively scan Nyquist, VST3, VST2, LV2, LADSPA, Audio Unit + custom directories
        from .vst_host import get_pe_arch

        scan_specs = list(self._standard_plugin_dirs())
        for cdir in self.custom_dirs:
            if os.path.isdir(cdir):
                scan_specs.append(("VST3", cdir, (".vst3",)))
                scan_specs.append(("VST2", cdir, (".dll", ".vst")))

        seen_paths = set()

        def _walk_plugins(ptype: str, folder: str, exts: Tuple[str, ...], depth: int = 0) -> None:
            if depth > 4 or not os.path.isdir(folder):
                return
            try:
                entries = sorted(os.listdir(folder))
            except OSError:
                return
            for entry in entries:
                full = os.path.join(folder, entry)
                norm_full = os.path.normcase(os.path.abspath(full))
                low = entry.lower()
                # Treat .vst3 / .vst / .component / .lv2 bundles as leaf plugins (do not recurse inside Contents/)
                if any(low.endswith(ext) for ext in exts):
                    if norm_full in seen_paths:
                        continue
                    seen_paths.add(norm_full)
                    disp = os.path.splitext(entry)[0]
                    real_type = ptype
                    if ptype == "Nyquist":
                        try:
                            with open(full, "r", encoding="utf-8", errors="replace") as f:
                                for ln in f:
                                    if ln.lower().startswith((";name", "$name")):
                                        if '"' in ln:
                                            disp = ln.split('"')[1]
                                        break
                        except Exception:
                            pass
                    elif low.endswith(".vst3") and os.path.isfile(full):
                        if get_pe_arch(full) == "x86":
                            real_type = "VST3 (32-bit)"
                    elif low.endswith(".dll") and ptype in ("VST", "VST2"):
                        # Skip known non-plugin uninstallers / helper DLLs & detect 32-bit vs 64-bit
                        if low.startswith(("unins", "msvcp", "vcruntime", "concrt")):
                            continue
                        arch = get_pe_arch(full)
                        if arch == "x86":
                            real_type = "VST2 (32-bit)"
                        elif arch == "x64":
                            real_type = "VST2 (64-bit)"
                        else:
                            continue
                    vendor = os.path.basename(folder)
                    if vendor.lower() in ("vst3", "vstplugins", "nyquist", "ladspa", "lv2", "components"):
                        vendor = real_type
                    pid = f"{real_type.lower()}:{norm_full}"
                    found.append({
                        "id": pid,
                        "name": disp,
                        "type": real_type,
                        "category": vendor,
                        "path": full,
                        "enabled": old_states.get(pid, "32-bit" not in real_type),
                    })
                elif os.path.isdir(full) and not low.endswith((".vst3", ".vst", ".component", ".lv2", ".app")):
                    _walk_plugins(ptype, full, exts, depth + 1)

        for ptype, folder, exts in scan_specs:
            _walk_plugins(ptype, folder, exts, 0)

        self.plugins = found
        self.save()
        return self.plugins

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.plugins, f, indent=2)

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        for p in self.plugins:
            if p["id"] == plugin_id:
                p["enabled"] = enabled
        self.save()

    def is_enabled(self, effect_name: str) -> bool:
        pid = f"builtin:{effect_name}"
        for p in self.plugins:
            if p["id"] == pid:
                return bool(p.get("enabled", True))
        return True

    def install_nyquist_plugin(self, src_path: str) -> str:
        dst = os.path.join(self.nyquist_dir, os.path.basename(src_path))
        with open(src_path, "rb") as rf, open(dst, "wb") as wf:
            wf.write(rf.read())
        self.rescan()
        return dst


# ---------------------------------------------------------------------------
# External Scripting Pipe Server (mod-script-pipe compatible over localhost TCP + File)
# ---------------------------------------------------------------------------
class ScriptingPipeServer:
    """Allows external Python/shell scripts to control KinoWave using Audacity-style
    pipe commands (e.g. `Play:`, `Stop:`, `Select: Start=0 End=4`, `Amplify: gain_db=3`,
    `GetInfo: Type=Tracks`, `Export2: Filename=out.wav`)."""

    def __init__(self, handler: Callable[[str], str], port: int = 47921) -> None:
        self.handler = handler
        self.port = port
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self.running = False
        self.history: List[str] = []

    def start(self) -> bool:
        if self.running:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self.port))
            s.listen(4)
            s.settimeout(0.5)
            self._sock = s
            self._stop_evt.clear()
            self.running = True
            self._thread = threading.Thread(target=self._serve, daemon=True)
            self._thread.start()
            return True
        except OSError:
            self.running = False
            return False

    def _serve(self) -> None:
        while not self._stop_evt.is_set() and self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    data = conn.recv(8192).decode("utf-8", errors="replace").strip()
                    if data:
                        self.history.append(f"> {data}")
                        reply = self.handler(data)
                        self.history.append(f"< {reply}")
                        conn.sendall((reply + "\nBatchCommand finished: OK\n").encode("utf-8"))
                except Exception as e:
                    try:
                        conn.sendall(f"Error: {e}\n".encode("utf-8"))
                    except Exception:
                        pass

    def stop(self) -> None:
        self._stop_evt.set()
        self.running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


# ---------------------------------------------------------------------------
# Performance Benchmark
# ---------------------------------------------------------------------------
def run_performance_benchmark(sr: int = 48000, duration_s: float = 10.0) -> str:
    """Benchmark 32-bit float synthesis, FFT filtering, resampling, and reverb."""
    lines = [f"=== KinoWave 32-bit Float Performance Benchmark ({sr} Hz, {duration_s:.1f}s stereo) ==="]
    t0 = time.perf_counter()
    sig = gen_tone(sr, duration_s=duration_s, waveform="Sawtooth", freq_hz=220.0, channels=2)
    t_gen = (time.perf_counter() - t0) * 1000.0
    lines.append(f"  1. Generate {duration_s:.0f}s Stereo Float32 ({sig.nbytes / 1e6:.2f} MB): {t_gen:.1f} ms")

    t0 = time.perf_counter()
    _ = fx_low_pass(sig, sr, cutoff_hz=3000.0, rolloff_db=24)
    t_flt = (time.perf_counter() - t0) * 1000.0
    lines.append(f"  2. Zero-Phase FFT Low-Pass (24 dB/oct): {t_flt:.1f} ms ({duration_s / max(1e-4, t_flt / 1000):.1f}x realtime)")

    t0 = time.perf_counter()
    _ = resample_audio(sig, sr, 96000, quality="High")
    t_res = (time.perf_counter() - t0) * 1000.0
    lines.append(f"  3. Band-Limited Resample {sr} -> 96000 Hz: {t_res:.1f} ms")

    t0 = time.perf_counter()
    _ = fx_reverb(sig[:, : sr * 3], sr, room_size=60.0)
    t_rev = (time.perf_counter() - t0) * 1000.0
    lines.append(f"  4. Algorithmic Stereo Convolution Reverb (3s): {t_rev:.1f} ms")

    score = int(100000.0 / max(1.0, t_gen + t_flt + t_res + t_rev))
    lines.append(f"\n  Overall KinoWave DSP Score: {score} pts  |  384 kHz Float32 Engine: READY")
    return "\n".join(lines)
