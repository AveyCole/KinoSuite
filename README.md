# KinoSuite — Unified Creative Studio Platform

**KinoSuite** is an integrated suite of sleek, deep-slate desktop creative applications unified under the **KinoSuite Hub** launcher, Universal File Router, process monitor, and cross-app studio workflows.

## Included Applications

| Badge | Application | Category | Highlights |
| :---: | :--- | :--- | :--- |
| **`Kc`** | **KinoCut** | Video & Motion | Non-linear video editing, timeline compositing, color grading & motion export |
| **`Ks`** | **KinoShop** | Photo & Raster | Non-destructive raster editing, layers, smart filters, brushes & export |
| **`Kd`** | **KinoDraw** | Vector & Graphics | Precision Bezier vector illustration, artboards, typography, image trace & SVG |
| **`Kw`** | **KinoWave** | Audio & Mastering | 32-bit float multitrack audio studio, 46+ DSP FX, spectrogram, MIDI & VST3/VST2 host |
| **`Kf`** | **KinoFill** | PDF & Documents | PDF editing, interactive form filling, e-signatures, OCR, redaction & merging |
| **`Kp`** | **KinoPixel** | Retro Games (GB/GBC/GBA) | From-scratch sprite & animation editor, 8×8 tile & 64×32 level editor, visual button wiring, **Sequence Genie** chiptune composer (19 scales, Chord Genie, Euclidean drums), live 60 FPS playtester & zero-toolchain ARM7TDMI playable `.gba` / `.gb` / `.gbc` ROM compiler |

## Quick Start

```powershell
# Install core dependencies
pip install PySide6 numpy Pillow sounddevice

# Launch the unified KinoSuite Hub
python main.py
```

Or launch any studio directly:

```powershell
python KinoShop/main.py
python KinoDraw/main.py
python KinoWave/main.py
python KinoFill/main.py
python KinoPixel/main.py
```

### Build Native Windows `.exe` Launchers

Each app (and the Hub itself) includes a lightweight `.NET` launcher builder (`build_launcher.ps1`) that generates its custom multi-resolution `.ico` badge and compiles a native Windows `.exe`:

```powershell
.\build_launcher.ps1
.\KinoPixel\build_launcher.ps1
```

## Verification Tests

```powershell
python tests/test_kinosuite.py
python KinoPixel/tests/test_kinopixel.py
```
