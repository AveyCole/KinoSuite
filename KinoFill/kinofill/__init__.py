"""KinoFill — KinoSuite Local PDF & Form Studio for Windows."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "KinoFill"
SUITE_NAME = "KinoSuite"
APP_SUBTITLE = "KinoSuite PDF Studio"
APP_VERSION = "1.0.0"

__version__ = APP_VERSION
__app_name__ = APP_NAME
__suite_name__ = SUITE_NAME


def get_app_data_dir() -> Path:
    candidates = []
    if os.environ.get("KINOFILL_DATA_DIR"):
        candidates.append(Path(os.environ["KINOFILL_DATA_DIR"]))
    elif os.environ.get("FREEFILL_DATA_DIR"):
        candidates.append(Path(os.environ["FREEFILL_DATA_DIR"]))
    base = os.environ.get("APPDATA") or str(Path.home())
    candidates.append(Path(base) / "KinoFill")
    candidates.append(Path(__file__).resolve().parent.parent / ".kinofill_data")

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError:
            continue
    return Path(__file__).resolve().parent.parent


def get_signatures_dir() -> Path:
    path = get_app_data_dir() / "signatures"
    path.mkdir(parents=True, exist_ok=True)
    # Non-destructively carry over any previously saved Freefill signatures if KinoFill vault is empty
    if not any(path.glob("*.png")):
        base = os.environ.get("APPDATA") or str(Path.home())
        legacy_dir = Path(base) / "Freefill" / "signatures"
        if legacy_dir.is_dir():
            for sig_file in legacy_dir.glob("*.png"):
                try:
                    shutil.copy2(sig_file, path / sig_file.name)
                except OSError:
                    pass
    return path


def get_config_path() -> Path:
    return get_app_data_dir() / "config.json"
