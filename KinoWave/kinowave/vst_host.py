"""KinoWave External Audio Plugin Host Engine (VST3, VST2 64-bit, Audio Unit, LADSPA).

Provides:
- Native VST3 & macOS Audio Unit hosting via Spotify's open-source JUCE-backed
  `pedalboard` engine (C++ 32-bit float DSP, full parameter control, AND native
  vendor plugin GUI windows!).
- Native 64-bit Windows VST 2.4 (.dll) hosting via pure-Python `ctypes` C ABI
  (`VSTPluginMain` / `AEffect` / `processReplacing` / `getParameter` /
  `setParameter` / embedded Win32 HWND `effEditOpen` native plugin editor!).
- LADSPA execution bridge via FFmpeg's built-in `--enable-ladspa` filter.
- Thread-safe instance caching so real-time FX racks & previews run smoothly.
"""
from __future__ import annotations

import ctypes
import os
import struct
import subprocess
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import pedalboard
    from pedalboard import load_plugin as _pb_load_plugin
    HAS_PEDALBOARD = True
except Exception:
    pedalboard = None
    _pb_load_plugin = None
    HAS_PEDALBOARD = False


# ---------------------------------------------------------------------------
# PE Architecture Helper (safely distinguish 64-bit vs 32-bit Windows DLLs)
# ---------------------------------------------------------------------------
def get_pe_arch(path: str) -> str:
    """Return 'x64', 'x86', or 'unknown' by reading PE COFF header without loading DLL."""
    if not os.path.isfile(path):
        return "unknown"
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                return "unknown"
            f.seek(0x3C)
            pe_off = struct.unpack("<I", f.read(4))[0]
            f.seek(pe_off)
            if f.read(4) != b"PE\x00\x00":
                return "unknown"
            machine = struct.unpack("<H", f.read(2))[0]
            if machine == 0x8664:
                return "x64"
            if machine == 0x014C:
                return "x86"
            if machine == 0xAA64:
                return "arm64"
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# VST 2.4 C ABI Host (Pure Python ctypes, 64-bit Windows .dll)
# ---------------------------------------------------------------------------
_VST_MAGIC = 0x56737450  # 'VstP'

# Host -> Plugin opcodes
_EFF_OPEN = 0
_EFF_CLOSE = 1
_EFF_SET_PROGRAM = 2
_EFF_GET_PARAM_LABEL = 6
_EFF_GET_PARAM_DISPLAY = 7
_EFF_GET_PARAM_NAME = 8
_EFF_SET_SAMPLE_RATE = 10
_EFF_SET_BLOCK_SIZE = 11
_EFF_MAINS_CHANGED = 12
_EFF_EDIT_GET_RECT = 13
_EFF_EDIT_OPEN = 14
_EFF_EDIT_CLOSE = 15
_EFF_EDIT_IDLE = 19
_EFF_GET_EFFECT_NAME = 45
_EFF_GET_VENDOR_STRING = 47
_EFF_START_PROCESS = 71
_EFF_STOP_PROCESS = 72

# Plugin -> Host opcodes
_AM_VERSION = 1
_AM_CURRENT_ID = 2
_AM_IDLE = 3
_AM_GET_SAMPLE_RATE = 16
_AM_GET_BLOCK_SIZE = 17
_AM_GET_VENDOR = 32
_AM_GET_PRODUCT = 33
_AM_GET_VENDOR_VER = 34
_AM_CAN_DO = 37
_AM_GET_PROCESS_LEVEL = 23


class _ERect(ctypes.Structure):
    _fields_ = [
        ("top", ctypes.c_int16),
        ("left", ctypes.c_int16),
        ("bottom", ctypes.c_int16),
        ("right", ctypes.c_int16),
    ]


class _AEffect(ctypes.Structure):
    pass


_DISPATCHER_PROC = ctypes.CFUNCTYPE(
    ctypes.c_int64,
    ctypes.POINTER(_AEffect),
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int64,
    ctypes.c_void_p,
    ctypes.c_float,
)
_PROCESS_PROC = ctypes.CFUNCTYPE(
    None,
    ctypes.POINTER(_AEffect),
    ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
    ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
    ctypes.c_int32,
)
_SET_PARAM_PROC = ctypes.CFUNCTYPE(None, ctypes.POINTER(_AEffect), ctypes.c_int32, ctypes.c_float)
_GET_PARAM_PROC = ctypes.CFUNCTYPE(ctypes.c_float, ctypes.POINTER(_AEffect), ctypes.c_int32)
_AUDIO_MASTER_CB = ctypes.CFUNCTYPE(
    ctypes.c_int64,
    ctypes.POINTER(_AEffect),
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int64,
    ctypes.c_void_p,
    ctypes.c_float,
)

_AEffect._fields_ = [
    ("magic", ctypes.c_int32),
    ("dispatcher", _DISPATCHER_PROC),
    ("process", _PROCESS_PROC),
    ("setParameter", _SET_PARAM_PROC),
    ("getParameter", _GET_PARAM_PROC),
    ("numPrograms", ctypes.c_int32),
    ("numParams", ctypes.c_int32),
    ("numInputs", ctypes.c_int32),
    ("numOutputs", ctypes.c_int32),
    ("flags", ctypes.c_int32),
    ("resvd1", ctypes.c_int64),
    ("resvd2", ctypes.c_int64),
    ("initialDelay", ctypes.c_int32),
    ("realQualities", ctypes.c_int32),
    ("offQualities", ctypes.c_int32),
    ("ioRatio", ctypes.c_float),
    ("object", ctypes.c_void_p),
    ("user", ctypes.c_void_p),
    ("uniqueID", ctypes.c_int32),
    ("version", ctypes.c_int32),
    ("processReplacing", _PROCESS_PROC),
    ("processDoubleReplacing", ctypes.c_void_p),
]


class VST2PluginInstance:
    """Native 64-bit VST 2.4 (.dll) plugin wrapper with audio processing,
    parameter control, and native Win32 HWND GUI editor support."""

    def __init__(self, path: str, sample_rate: int = 48000, block_size: int = 2048) -> None:
        if os.name != "nt":
            raise RuntimeError("Direct VST2 .dll hosting is only supported on Windows.")
        arch = get_pe_arch(path)
        if arch == "x86":
            raise RuntimeError(f"'{os.path.basename(path)}' is a 32-bit VST2 DLL; KinoWave is 64-bit. Use the 64-bit VST2 or VST3 version.")
        self.path = path
        self.plugin_type = "VST2"
        self.sample_rate = float(sample_rate)
        self.block_size = int(block_size)
        self._lock = threading.Lock()
        self._closed = False
        self._editor_open = False

        # Keep callback alive as instance attribute
        self._master_cb = _AUDIO_MASTER_CB(self._audio_master)

        # Add plugin folder to DLL search path for sidecar DLLs
        dll_dir = os.path.dirname(os.path.abspath(path))
        self._dll_dir_handle = os.add_dll_directory(dll_dir) if hasattr(os, "add_dll_directory") else None
        self._lib = ctypes.CDLL(path)

        entry = None
        for sym in ("VSTPluginMain", "main"):
            if hasattr(self._lib, sym):
                entry = getattr(self._lib, sym)
                break
        if entry is None:
            raise RuntimeError(f"'{os.path.basename(path)}' is not a valid VST2 plugin (missing VSTPluginMain).")
        entry.argtypes = [_AUDIO_MASTER_CB]
        entry.restype = ctypes.POINTER(_AEffect)

        eff_ptr = entry(self._master_cb)
        if not eff_ptr or eff_ptr.contents.magic != _VST_MAGIC:
            raise RuntimeError(f"'{os.path.basename(path)}' failed VST2 magic handshake.")
        self._eff_ptr = eff_ptr
        self._eff = eff_ptr.contents

        self._dispatch(_EFF_OPEN)
        self._dispatch(_EFF_SET_SAMPLE_RATE, opt=float(self.sample_rate))
        self._dispatch(_EFF_SET_BLOCK_SIZE, value=self.block_size)
        self._dispatch(_EFF_MAINS_CHANGED, value=1)

        self.name = self._get_string(_EFF_GET_EFFECT_NAME) or os.path.splitext(os.path.basename(path))[0]
        self.vendor = self._get_string(_EFF_GET_VENDOR_STRING) or ""
        self.has_editor = bool(self._eff.flags & 1)  # effFlagsHasEditor

    def _audio_master(self, eff, opcode, index, value, ptr, opt) -> int:
        if opcode == _AM_VERSION:
            return 2400
        if opcode == _AM_CURRENT_ID:
            return 0
        if opcode == _AM_GET_SAMPLE_RATE:
            return int(self.sample_rate)
        if opcode == _AM_GET_BLOCK_SIZE:
            return int(self.block_size)
        if opcode == _AM_GET_VENDOR and ptr:
            ctypes.memmove(ptr, b"KinoSuite\x00", 10)
            return 1
        if opcode == _AM_GET_PRODUCT and ptr:
            ctypes.memmove(ptr, b"KinoWave\x00", 9)
            return 1
        if opcode == _AM_GET_VENDOR_VER:
            return 1000
        if opcode == _AM_CAN_DO:
            return 1
        if opcode == _AM_GET_PROCESS_LEVEL:
            return 2
        return 0

    def _dispatch(self, opcode: int, index: int = 0, value: int = 0, ptr: Any = None, opt: float = 0.0) -> int:
        return int(self._eff.dispatcher(self._eff_ptr, opcode, index, value, ptr, ctypes.c_float(opt)))

    def _get_string(self, opcode: int, index: int = 0) -> str:
        buf = ctypes.create_string_buffer(128)
        self._dispatch(opcode, index=index, ptr=ctypes.cast(buf, ctypes.c_void_p))
        return buf.value.decode("utf-8", errors="replace").strip()

    def list_parameters(self) -> List[Dict[str, Any]]:
        params: List[Dict[str, Any]] = []
        n = min(256, max(0, int(self._eff.numParams)))
        for i in range(n):
            pname = self._get_string(_EFF_GET_PARAM_NAME, i) or f"Param {i + 1}"
            disp = self._get_string(_EFF_GET_PARAM_DISPLAY, i)
            lbl = self._get_string(_EFF_GET_PARAM_LABEL, i)
            val = float(self._eff.getParameter(self._eff_ptr, i))
            params.append({
                "key": f"p{i}",
                "index": i,
                "name": pname,
                "value": val,
                "min": 0.0,
                "max": 1.0,
                "display": f"{disp} {lbl}".strip() or f"{val:.2f}",
                "kind": "float",
            })
        return params

    def get_param_dict(self) -> Dict[str, Any]:
        return {p["key"]: p["value"] for p in self.list_parameters()}

    def set_param(self, key: str, value: Any) -> None:
        idx = int(key[1:]) if key.startswith("p") else int(key)
        if 0 <= idx < self._eff.numParams:
            self._eff.setParameter(self._eff_ptr, idx, ctypes.c_float(float(np.clip(float(value), 0.0, 1.0))))

    def apply_params(self, params: Dict[str, Any]) -> None:
        for k, v in params.items():
            if k.startswith("p") and k[1:].isdigit():
                self.set_param(k, v)

    def open_editor_in_hwnd(self, hwnd: int) -> Tuple[int, int]:
        """Embed native VST2 GUI inside a Qt QWidget's Win32 HWND; returns (width, height)."""
        if not self.has_editor:
            return (0, 0)
        rect_ptr = ctypes.POINTER(_ERect)()
        self._dispatch(_EFF_EDIT_GET_RECT, ptr=ctypes.byref(rect_ptr))
        w, h = 640, 420
        if rect_ptr:
            r = rect_ptr.contents
            w = max(200, int(r.right - r.left))
            h = max(140, int(r.bottom - r.top))
        self._dispatch(_EFF_EDIT_OPEN, ptr=ctypes.c_void_p(int(hwnd)))
        self._editor_open = True
        return (w, h)

    def idle_editor(self) -> None:
        if self._editor_open:
            self._dispatch(_EFF_EDIT_IDLE)

    def close_editor(self) -> None:
        if self._editor_open:
            self._dispatch(_EFF_EDIT_CLOSE)
            self._editor_open = False

    def process(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Process float32 audio shaped (channels, N) via VST2 processReplacing."""
        with self._lock:
            a = np.asarray(audio, dtype=np.float32)
            if a.ndim == 1:
                a = a[None, :]
            orig_ch, n_total = a.shape
            if n_total == 0:
                return a.copy()

            if abs(sr - self.sample_rate) > 1.0:
                self._dispatch(_EFF_MAINS_CHANGED, value=0)
                self.sample_rate = float(sr)
                self._dispatch(_EFF_SET_SAMPLE_RATE, opt=self.sample_rate)
                self._dispatch(_EFF_MAINS_CHANGED, value=1)

            n_in = max(1, min(8, int(self._eff.numInputs)))
            n_out = max(1, min(8, int(self._eff.numOutputs)))
            blk = min(self.block_size, max(256, n_total))

            out_full = np.zeros((max(orig_ch, min(2, n_out)), n_total), dtype=np.float32)
            self._dispatch(_EFF_START_PROCESS)
            try:
                pos = 0
                while pos < n_total:
                    take = min(blk, n_total - pos)
                    in_bufs = [np.zeros(take, dtype=np.float32) for _ in range(n_in)]
                    out_bufs = [np.zeros(take, dtype=np.float32) for _ in range(n_out)]
                    for c in range(n_in):
                        src_c = min(c, orig_ch - 1)
                        in_bufs[c][:] = a[src_c, pos : pos + take]
                    in_ptrs = (ctypes.POINTER(ctypes.c_float) * n_in)(*[b.ctypes.data_as(ctypes.POINTER(ctypes.c_float)) for b in in_bufs])
                    out_ptrs = (ctypes.POINTER(ctypes.c_float) * n_out)(*[b.ctypes.data_as(ctypes.POINTER(ctypes.c_float)) for b in out_bufs])
                    self._eff.processReplacing(self._eff_ptr, in_ptrs, out_ptrs, take)
                    for c in range(out_full.shape[0]):
                        out_full[c, pos : pos + take] = out_bufs[min(c, n_out - 1)]
                    pos += take
            finally:
                self._dispatch(_EFF_STOP_PROCESS)

            return np.ascontiguousarray(out_full[:orig_ch], dtype=np.float32)

    def close(self) -> None:
        if not self._closed:
            self.close_editor()
            try:
                self._dispatch(_EFF_MAINS_CHANGED, value=0)
                self._dispatch(_EFF_CLOSE)
            except Exception:
                pass
            self._closed = True


# ---------------------------------------------------------------------------
# VST3 & Audio Unit Host (Spotify pedalboard / JUCE C++ Engine)
# ---------------------------------------------------------------------------
class PedalboardPluginInstance:
    """Native VST3 (.vst3) & macOS Audio Unit (.component) plugin host backed by JUCE."""

    def __init__(self, path: str, plugin_name: Optional[str] = None) -> None:
        if not HAS_PEDALBOARD or _pb_load_plugin is None:
            raise RuntimeError("pedalboard is not installed. Run `pip install pedalboard` to enable VST3/AU hosting.")
        self.path = path
        self.plugin_type = "Audio Unit" if path.lower().endswith(".component") else "VST3"
        self.plugin_name = plugin_name
        self._lock = threading.Lock()
        self.plugin = _pb_load_plugin(path, plugin_name=plugin_name)
        self.name = str(getattr(self.plugin, "name", "") or os.path.splitext(os.path.basename(path))[0])
        self.has_editor = hasattr(self.plugin, "show_editor")

    def list_parameters(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        raw_params = getattr(self.plugin, "parameters", {})
        for key, param in raw_params.items():
            try:
                valid = getattr(param, "valid_values", None)
                val = getattr(self.plugin, key)
                if valid and len(valid) > 0 and isinstance(valid[0], str):
                    out.append({
                        "key": key,
                        "name": getattr(param, "name", key) or key,
                        "value": str(val),
                        "choices": list(valid),
                        "display": str(val),
                        "kind": "choice",
                    })
                elif isinstance(val, bool):
                    out.append({
                        "key": key,
                        "name": getattr(param, "name", key) or key,
                        "value": bool(val),
                        "display": "On" if val else "Off",
                        "kind": "bool",
                    })
                else:
                    rval = float(getattr(param, "raw_value", 0.5))
                    out.append({
                        "key": key,
                        "name": getattr(param, "name", key) or key,
                        "value": rval,
                        "min": 0.0,
                        "max": 1.0,
                        "display": str(getattr(param, "string_value", f"{val}")),
                        "kind": "float",
                    })
            except Exception:
                continue
        return out

    def get_param_dict(self) -> Dict[str, Any]:
        return {p["key"]: p["value"] for p in self.list_parameters()}

    def set_param(self, key: str, value: Any) -> None:
        raw_params = getattr(self.plugin, "parameters", {})
        if key not in raw_params:
            return
        param = raw_params[key]
        try:
            valid = getattr(param, "valid_values", None)
            if valid and len(valid) > 0 and isinstance(valid[0], str):
                setattr(self.plugin, key, str(value))
            elif isinstance(getattr(self.plugin, key), bool):
                setattr(self.plugin, key, bool(value))
            else:
                param.raw_value = float(np.clip(float(value), 0.0, 1.0))
        except Exception:
            try:
                setattr(self.plugin, key, value)
            except Exception:
                pass

    def apply_params(self, params: Dict[str, Any]) -> None:
        for k, v in params.items():
            if not k.startswith("__"):
                self.set_param(k, v)

    def show_native_editor(self) -> None:
        """Open the plugin's native vendor GUI window (modal until closed by user)."""
        if self.has_editor:
            self.plugin.show_editor()

    def process(self, audio: np.ndarray, sr: int) -> np.ndarray:
        with self._lock:
            a = np.asarray(audio, dtype=np.float32)
            if a.ndim == 1:
                a = a[None, :]
            if a.shape[1] == 0:
                return a.copy()
            # Ensure float32 contiguous (channels, samples)
            inp = np.ascontiguousarray(a, dtype=np.float32)
            try:
                out = self.plugin.process(inp, float(sr), buffer_size=4096, reset=False)
            except Exception:
                # Some stereo-only VST3s require 2 channels even for mono input
                if inp.shape[0] == 1:
                    st = np.vstack([inp, inp])
                    out = self.plugin.process(st, float(sr), buffer_size=4096, reset=False)
                    out = np.mean(out, axis=0, keepdims=True)
                else:
                    raise
            out = np.asarray(out, dtype=np.float32)
            if out.ndim == 1:
                out = out[None, :]
            return np.ascontiguousarray(out[: a.shape[0]], dtype=np.float32)


# ---------------------------------------------------------------------------
# LADSPA Execution via FFmpeg (`--enable-ladspa`)
# ---------------------------------------------------------------------------
def run_ladspa_ffmpeg(path: str, audio: np.ndarray, sr: int, plugin_label: str = "", controls: str = "", ffmpeg_path: str = "") -> np.ndarray:
    from .audio_io import find_ffmpeg
    ff = find_ffmpeg(ffmpeg_path)
    if not ff:
        raise RuntimeError("FFmpeg is required to run LADSPA plugins.")
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    ch = a.shape[0]
    escaped = path.replace("\\", "/").replace(":", "\\:")
    flt = f"ladspa=f='{escaped}'"
    if plugin_label:
        flt += f":p='{plugin_label}'"
    if controls:
        flt += f":c='{controls}'"
    cmd = [ff, "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", str(ch), "-i", "pipe:0", "-af", flt, "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"]
    proc = subprocess.run(cmd, input=np.ascontiguousarray(a.T, dtype="<f4").tobytes(), capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"LADSPA filter error: {proc.stderr.decode('utf-8', errors='replace')[:250]}")
    raw = np.frombuffer(proc.stdout, dtype="<f4")
    n = len(raw) // ch
    return np.ascontiguousarray(raw[: n * ch].reshape(n, ch).T, dtype=np.float32)


# ---------------------------------------------------------------------------
# Unified Instance Cache & Processing API
# ---------------------------------------------------------------------------
_INSTANCE_CACHE: Dict[Tuple[str, str], Any] = {}
_CACHE_LOCK = threading.Lock()


def get_external_plugin(path: str, plugin_type: str, sample_rate: int = 48000, plugin_name: Optional[str] = None) -> Any:
    """Load or return cached VST3, Audio Unit, or 64-bit VST2 plugin instance."""
    key = (os.path.abspath(path), plugin_name or "")
    with _CACHE_LOCK:
        inst = _INSTANCE_CACHE.get(key)
        if inst is not None:
            return inst
    if plugin_type in ("VST3", "Audio Unit") or path.lower().endswith((".vst3", ".component")):
        inst = PedalboardPluginInstance(path, plugin_name=plugin_name)
    elif plugin_type in ("VST", "VST2", "VST2 (64-bit)") or path.lower().endswith(".dll"):
        inst = VST2PluginInstance(path, sample_rate=sample_rate)
    else:
        raise RuntimeError(f"Unsupported external plugin type: {plugin_type}")
    with _CACHE_LOCK:
        _INSTANCE_CACHE[key] = inst
    return inst


def list_vst3_subplugins(path: str) -> List[str]:
    """Return sub-plugin names inside a multi-plugin .vst3 bundle if available."""
    if HAS_PEDALBOARD and pedalboard is not None:
        try:
            return list(pedalboard.VST3Plugin.get_plugin_names_for_file(path))
        except Exception:
            pass
    return []


def process_external_plugin(
    path: str,
    plugin_type: str,
    audio: np.ndarray,
    sr: int,
    params: Optional[Dict[str, Any]] = None,
    plugin_name: Optional[str] = None,
) -> np.ndarray:
    """Process audio through any cached external VST3, VST2 (64-bit), AU, or LADSPA plugin."""
    if plugin_type == "LADSPA":
        return run_ladspa_ffmpeg(path, audio, sr)
    inst = get_external_plugin(path, plugin_type, sample_rate=sr, plugin_name=plugin_name)
    if params:
        inst.apply_params(params)
    return inst.process(audio, sr)
