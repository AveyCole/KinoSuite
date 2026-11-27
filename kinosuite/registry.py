"""KinoSuite App Discovery, Process Manager, Universal File Router, Cloud & Health Inspector."""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class KinoAppInfo:
    app_id: str
    name: str
    monogram: str
    tagline: str
    category: str
    accent: str
    bg_hex: str
    exe_path: str
    folder: str
    main_py: str = ""
    extensions: List[str] = field(default_factory=list)
    cloud_dirs: List[str] = field(default_factory=list)
    plugin_dirs: List[str] = field(default_factory=list)
    test_script: str = ""
    build_script: str = ""
    is_custom: bool = False

    @property
    def installed(self) -> bool:
        return bool((self.exe_path and os.path.isfile(self.exe_path)) or (self.main_py and os.path.isfile(self.main_py)))

    @property
    def process_match_names(self) -> List[str]:
        names = []
        if self.exe_path:
            names.append(os.path.splitext(os.path.basename(self.exe_path))[0].lower())
        names.append(self.name.lower())
        return list(dict.fromkeys(names))

    def disk_size_mb(self) -> float:
        if self.exe_path and os.path.isfile(self.exe_path):
            sz = os.path.getsize(self.exe_path)
            if sz > 1_000_000:
                return round(sz / (1024 * 1024), 1)
        if not os.path.isdir(self.folder):
            return 0.0
        total = 0
        for root, dirs, files in os.walk(self.folder):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "build", "dist", ".git")]
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        return round(total / (1024 * 1024), 1)


BUILTIN_APP_SPECS: List[Dict[str, Any]] = [
    {
        "app_id": "kinocut",
        "name": "KinoCut",
        "monogram": "Kc",
        "tagline": "Non-linear video editing, timeline compositing, color grading & motion export",
        "category": "Video & Motion",
        "accent": "#FF4D6D",
        "bg_hex": "#211018",
        "exe_candidates": ["KinoCut.exe", os.path.join("KinoCut", "KinoCut.exe")],
        "folder_rel": "KinoCut",
        "extensions": [".kcut", ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts"],
        "cloud_rel": [".kinocloud", os.path.join("KinoCut", ".kinocloud")],
        "plugin_rel": [os.path.join("KinoCut", "plugins")],
    },
    {
        "app_id": "kinoshop",
        "name": "KinoShop",
        "monogram": "Ks",
        "tagline": "Non-destructive raster photo editing, layers, smart filters, RAW & print prep",
        "category": "Photo & Raster",
        "accent": "#31A8FF",
        "bg_hex": "#0B1B2E",
        "exe_candidates": [os.path.join("KinoShop", "KinoShop.exe"), "KinoShop.exe"],
        "folder_rel": "KinoShop",
        "extensions": [".ksd", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".psd", ".gif"],
        "cloud_rel": [os.path.join("KinoShop", ".kinocloud")],
        "plugin_rel": [os.path.join("KinoShop", "plugins")],
    },
    {
        "app_id": "kinodraw",
        "name": "KinoDraw",
        "monogram": "Kd",
        "tagline": "Precision Bezier vector illustration, artboards, typography, image trace & SVG",
        "category": "Vector & Graphics",
        "accent": "#FF9A00",
        "bg_hex": "#1E150C",
        "exe_candidates": [os.path.join("KinoDraw", "KinoDraw.exe"), "KinoDraw.exe"],
        "folder_rel": "KinoDraw",
        "extensions": [".kdraw", ".kdrw", ".svg", ".eps", ".ai"],
        "cloud_rel": [os.path.join("KinoDraw", ".kinocloud")],
        "plugin_rel": [os.path.join("KinoDraw", "plugins")],
    },
    {
        "app_id": "kinowave",
        "name": "KinoWave",
        "monogram": "Kw",
        "tagline": "32-bit float multitrack audio studio, 46+ DSP FX, spectrogram, MIDI & VST3/VST2 host",
        "category": "Audio & Mastering",
        "accent": "#10D9A0",
        "bg_hex": "#091F1C",
        "exe_candidates": [os.path.join("KinoWave", "KinoWave.exe"), os.path.join("KinoWave", "dist", "KinoWave.exe"), "KinoWave.exe"],
        "folder_rel": "KinoWave",
        "extensions": [".kwp", ".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aiff", ".aif", ".wma", ".ac3", ".amr", ".mid", ".midi"],
        "cloud_rel": [os.path.join("KinoWave", ".kinocloud_wave")],
        "plugin_rel": [os.path.join("KinoWave", "plugins")],
    },
    {
        "app_id": "kinofill",
        "name": "KinoFill",
        "monogram": "Kf",
        "tagline": "PDF editing, interactive form filling, e-signatures, OCR, redaction & merging",
        "category": "PDF & Documents",
        "accent": "#38BDF8",
        "bg_hex": "#0E1929",
        "exe_candidates": [os.path.join("KinoFill", "KinoFill.exe"), "KinoFill.exe"],
        "folder_rel": "KinoFill",
        "extensions": [".pdf", ".kinofill", ".freefill", ".lfill", ".fdf", ".xfdf"],
        "cloud_rel": [os.path.join("KinoFill", ".kinofill_data")],
        "plugin_rel": [],
    },
    {
        "app_id": "kinopixel",
        "name": "KinoPixel",
        "monogram": "Kp",
        "tagline": "From-scratch GB/GBC/GBA game studio — sprites, animation, button wiring, PSG chiptune & playable .gba ROMs",
        "category": "Retro Games (GB/GBA)",
        "accent": "#8B5CF6",
        "bg_hex": "#161029",
        "exe_candidates": [os.path.join("KinoPixel", "KinoPixel.exe"), "KinoPixel.exe"],
        "folder_rel": "KinoPixel",
        "extensions": [".kpx", ".gba", ".gbc", ".gb"],
        "cloud_rel": [os.path.join("KinoPixel", ".kinocloud"), os.path.join("KinoPixel", "examples")],
        "plugin_rel": [],
    },
]


class SuiteConfig:
    """Persists KinoSuite Hub preferences, custom registered apps, and recent files."""

    def __init__(self, suite_root: str) -> None:
        self.suite_root = suite_root
        self.config_dir = os.path.join(suite_root, ".kinosuite_hub")
        os.makedirs(self.config_dir, exist_ok=True)
        self.path = os.path.join(self.config_dir, "hub_config.json")
        self.data: Dict[str, Any] = {
            "theme": "Dark",
            "minimize_to_tray": True,
            "recent_files": [],
            "custom_apps": [],
        }
        self.load()

    def load(self) -> None:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self) -> None:
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def add_recent(self, file_path: str, app_id: str) -> None:
        rec = [r for r in self.data.get("recent_files", []) if r.get("path") != file_path]
        rec.insert(0, {
            "path": file_path,
            "name": os.path.basename(file_path),
            "app_id": app_id,
            "opened_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        self.data["recent_files"] = rec[:40]
        self.save()


def discover_suite_apps(suite_root: str, cfg: SuiteConfig) -> List[KinoAppInfo]:
    """Discover all built-in + custom KinoSuite apps inside suite_root."""
    apps: List[KinoAppInfo] = []
    for sp in BUILTIN_APP_SPECS:
        exe_found = ""
        for cand in sp["exe_candidates"]:
            full = os.path.join(suite_root, cand)
            if os.path.isfile(full):
                exe_found = full
                break
        folder = os.path.join(suite_root, sp["folder_rel"])
        if not os.path.isdir(folder):
            folder = suite_root
        main_py = os.path.join(folder, "main.py") if os.path.isfile(os.path.join(folder, "main.py")) else ""
        tests_dir = os.path.join(folder, "tests")
        test_script = ""
        if os.path.isdir(tests_dir):
            for fn in sorted(os.listdir(tests_dir)):
                if fn.startswith("test_") and fn.endswith(".py"):
                    test_script = os.path.join(tests_dir, fn)
                    break
        build_script = ""
        for bname in ("build_launcher.ps1", "build_exe.py", "build_standalone.ps1"):
            bp = os.path.join(folder, bname)
            if os.path.isfile(bp):
                build_script = bp
                break

        apps.append(
            KinoAppInfo(
                app_id=sp["app_id"],
                name=sp["name"],
                monogram=sp["monogram"],
                tagline=sp["tagline"],
                category=sp["category"],
                accent=sp["accent"],
                bg_hex=sp["bg_hex"],
                exe_path=exe_found,
                folder=folder,
                main_py=main_py,
                extensions=list(sp["extensions"]),
                cloud_dirs=[os.path.join(suite_root, r) for r in sp["cloud_rel"] if os.path.isdir(os.path.join(suite_root, r))],
                plugin_dirs=[os.path.join(suite_root, r) for r in sp["plugin_rel"] if os.path.isdir(os.path.join(suite_root, r))],
                test_script=test_script,
                build_script=build_script,
            )
        )

    # Custom user-registered Kino apps (future-proofing for Kino3D, KinoMotion, etc.)
    for c in cfg.data.get("custom_apps", []):
        apps.append(
            KinoAppInfo(
                app_id=c["app_id"],
                name=c["name"],
                monogram=c.get("monogram", c["name"][:2]),
                tagline=c.get("tagline", "Custom KinoSuite Application"),
                category=c.get("category", "Custom"),
                accent=c.get("accent", "#A78BFA"),
                bg_hex=c.get("bg_hex", "#1A1629"),
                exe_path=c.get("exe_path", ""),
                folder=os.path.dirname(c.get("exe_path", "")) or suite_root,
                extensions=list(c.get("extensions", [])),
                is_custom=True,
            )
        )
    return apps


def route_file_to_app(file_path: str, apps: List[KinoAppInfo]) -> Optional[KinoAppInfo]:
    ext = os.path.splitext(file_path)[1].lower()
    for app in apps:
        if ext in app.extensions and app.installed:
            return app
    return None


def portal_inbox() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "KinoSuite", "Portal Inbox")


def portal_targets(file_path: str, apps: List[KinoAppInfo]) -> List[KinoAppInfo]:
    ext = os.path.splitext(file_path)[1].lower()
    raster = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    formats = {
        "kinocut": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts", ".wav", ".mp3", ".flac", ".m4a", ".png", ".gif"},
        "kinoshop": raster | {".ksd", ".tif", ".tiff", ".psd", ".gif"},
        "kinodraw": raster | {".svg", ".kdrw", ".kdraw"},
        "kinowave": {".kwp", ".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aiff", ".aif", ".wma", ".ac3", ".amr", ".mid", ".midi"},
        "kinofill": {".pdf", ".kinofill", ".freefill", ".lfill"},
        "kinopixel": raster | {".kpx"},
    }
    return [app for app in apps if not app.is_custom and app.installed and ext in formats.get(app.app_id, ())]


def find_python_executable(windowed: bool = False) -> str:
    exe_name = "pythonw.exe" if windowed else "python.exe"
    if not getattr(sys, "frozen", False):
        cand = os.path.join(os.path.dirname(sys.executable), exe_name)
        if os.path.isfile(cand):
            return cand
        return sys.executable
    local_app = os.environ.get("LOCALAPPDATA", "")
    for ver in ("Python310", "Python311", "Python312", "Python313"):
        cand = os.path.join(local_app, "Programs", "Python", ver, exe_name)
        if os.path.isfile(cand):
            return cand
    return shutil.which(exe_name) or shutil.which("python") or ""


def launch_kino_app(app: KinoAppInfo, file_args: Optional[List[str]] = None) -> subprocess.Popen:
    """Launch a KinoSuite application (preferring its native .exe, falling back to main.py)."""
    args = [a for a in (file_args or []) if a]
    if app.app_id == "kinocut" and args:
        args.insert(0,"--import-media")
    if app.exe_path and os.path.isfile(app.exe_path):
        cmd = [app.exe_path] + args
        cwd = os.path.dirname(app.exe_path)
    elif app.main_py and os.path.isfile(app.main_py):
        pyw = find_python_executable(windowed=True)
        cmd = [pyw, app.main_py] + args
        cwd = app.folder
    else:
        raise FileNotFoundError(f"Could not find executable or main.py for {app.name}")

    creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) if os.name == "nt" else 0
    return subprocess.Popen(cmd, cwd=cwd, creationflags=creation_flags)


# ---------------------------------------------------------------------------
# Live Windows Process Monitor (zero extra deps — fast tasklist / PowerShell)
# ---------------------------------------------------------------------------
def query_running_kino_processes(apps: List[KinoAppInfo], tracked_procs: Dict[int, str]) -> List[Dict[str, Any]]:
    """Return list of currently running KinoSuite processes with PID, App Name, Memory MB."""
    results: List[Dict[str, Any]] = []
    seen_pids = set()

    # 1. Check Windows tasklist for standalone .exe apps (KinoCut.exe, KinoWave.exe, etc.)
    exe_lookup = {}
    for a in apps:
        if a.exe_path:
            exe_lookup[os.path.basename(a.exe_path).lower()] = a.name
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in out.splitlines():
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 5:
                    img = parts[0].lower()
                    pid = int(parts[1]) if parts[1].isdigit() else -1
                    mem_str = parts[4].replace(",", "").replace(" K", "").strip()
                    mem_mb = round(int(mem_str) / 1024.0, 1) if mem_str.isdigit() else 0.0
                    if img in exe_lookup and pid > 0 and pid != os.getpid():
                        results.append({"app": exe_lookup[img], "pid": pid, "image": parts[0], "mem_mb": mem_mb})
                        seen_pids.add(pid)
        except Exception:
            pass

    # 2. Check tracked child processes launched via pythonw.exe (KinoShop, KinoDraw, KinoFill)
    dead = []
    for pid, app_name in list(tracked_procs.items()):
        if pid in seen_pids:
            continue
        alive = False
        mem_mb = 0.0
        if os.name == "nt":
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if str(pid) in out and "INFO:" not in out:
                    alive = True
                    parts = [p.strip('"') for p in out.strip().splitlines()[0].split('","')]
                    if len(parts) >= 5:
                        ms = parts[4].replace(",", "").replace(" K", "").strip()
                        mem_mb = round(int(ms) / 1024.0, 1) if ms.isdigit() else 0.0
            except Exception:
                pass
        if alive:
            results.append({"app": app_name, "pid": pid, "image": f"{app_name} (Python)", "mem_mb": mem_mb})
            seen_pids.add(pid)
        else:
            dead.append(pid)
    for d in dead:
        tracked_procs.pop(d, None)

    return results


def terminate_process(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.kill(pid, 15)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Unified KinoCloud & Project Aggregator across all KinoSuite Apps
# ---------------------------------------------------------------------------
def collect_suite_projects(apps: List[KinoAppInfo], cfg: SuiteConfig) -> List[Dict[str, Any]]:
    """Aggregate recent files + KinoCloud snapshots across all KinoSuite apps."""
    items: List[Dict[str, Any]] = []
    seen = set()

    # Recent files opened via Hub
    for r in cfg.data.get("recent_files", []):
        p = r.get("path", "")
        if p and os.path.isfile(p) and p not in seen:
            seen.add(p)
            items.append({
                "name": r.get("name", os.path.basename(p)),
                "app_id": r.get("app_id", ""),
                "source": "Recent",
                "updated": r.get("opened_at", ""),
                "path": p,
            })

    # Scan each app's .kinocloud / data directories for saved projects
    proj_exts = {".ksd", ".kdraw", ".kwp", ".kcut", ".kpx", ".gba", ".pdf", ".svg", ".wav", ".png"}
    for app in apps:
        for cdir in app.cloud_dirs:
            if not os.path.isdir(cdir):
                continue
            for root, _dirs, files in os.walk(cdir):
                for fn in files:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in proj_exts:
                        full = os.path.join(root, fn)
                        if full in seen:
                            continue
                        seen.add(full)
                        mt = datetime.datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M")
                        items.append({
                            "name": fn,
                            "app_id": app.app_id,
                            "source": f"{app.name} Cloud",
                            "updated": mt,
                            "path": full,
                        })
    items.sort(key=lambda x: x.get("updated", ""), reverse=True)
    return items


def collect_suite_plugins(apps: List[KinoAppInfo]) -> List[Dict[str, str]]:
    """Aggregate Python, Nyquist, VST3, and VST2 plugins across the entire KinoSuite."""
    rows: List[Dict[str, str]] = []
    for app in apps:
        for pdir in app.plugin_dirs:
            if not os.path.isdir(pdir):
                continue
            for root, dirs, files in os.walk(pdir):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in files:
                    if fn.endswith((".py", ".ny", ".vst3", ".dll")):
                        rows.append({
                            "app": app.name,
                            "name": os.path.splitext(fn)[0],
                            "kind": os.path.splitext(fn)[1].upper().lstrip("."),
                            "path": os.path.join(root, fn),
                        })
        # Also read KinoWave's discovered VST3/VST2 registry if present
        kw_reg = os.path.join(app.folder, ".kinowave_config", "plugins_registry.json")
        if os.path.isfile(kw_reg):
            try:
                with open(kw_reg, "r", encoding="utf-8") as f:
                    for pl in json.load(f):
                        if pl.get("type") in ("VST3", "VST2 (64-bit)"):
                            rows.append({
                                "app": app.name,
                                "name": pl.get("name", ""),
                                "kind": pl.get("type", ""),
                                "path": pl.get("path", ""),
                            })
            except Exception:
                pass
    return rows


def check_environment_health(suite_root: str, apps: List[KinoAppInfo]) -> List[Tuple[str, str, str]]:
    """Return [(Component, Status, Details)] for the Suite Health dashboard."""
    rows: List[Tuple[str, str, str]] = []
    rows.append(("KinoSuite Root", "OK", suite_root))
    py = find_python_executable(windowed=False)
    rows.append(("Python Runtime", "OK" if py else "MISSING", py or "Not found"))

    for mod, label in [("PySide6", "PySide6 Qt6 UI"), ("numpy", "NumPy DSP/Imaging"), ("sounddevice", "PortAudio (Audio I/O)"), ("pedalboard", "Pedalboard (VST3 Host)"), ("cv2", "OpenCV (Imaging)"), ("PIL", "Pillow (Graphics)")]:
        try:
            __import__(mod)
            rows.append((label, "OK", "Installed"))
        except Exception:
            rows.append((label, "OPTIONAL", "Not installed"))

    ff = shutil.which("ffmpeg") or (r"C:\Users\austi\scoop\shims\ffmpeg.exe" if os.path.isfile(r"C:\Users\austi\scoop\shims\ffmpeg.exe") else "")
    rows.append(("FFmpeg Media Engine", "OK" if ff else "OPTIONAL", ff or "Not on PATH"))
    csc = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    rows.append((".NET Launcher Compiler", "OK" if os.path.isfile(csc) else "OPTIONAL", csc if os.path.isfile(csc) else "Not found"))

    for a in apps:
        rows.append((f"{a.name} ({a.monogram})", "READY" if a.installed else "MISSING", a.exe_path or a.main_py or "Not found"))
    return rows
