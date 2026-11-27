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
| **`Kp`** | **KinoPixel v2.0** | Retro Games (GB/GBC/GBA) | Full Metroidvania & retro handheld game studio — `16×16`/`16×32`/`32×32` metasprites, Morph Ball, 8-way aim, Wall-Jump, multi-room doors, GBA SRAM saves, BG2 parallax + alpha blend, **Sequence Genie** chiptune composer, Direct Sound DMA PCM & playable `.gba`/`.gb`/`.gbc` ROMs |

## Prebuilt Windows Downloads (No Python Required)

Download ready-to-run standalone Windows `.exe` executables directly from [**GitHub Releases**](https://github.com/AveyCole/KinoSuite/releases/latest):

- **`KinoSuite.exe`** — Unified KinoSuite Hub (drop alongside any `Kino*.exe` apps to launch and route files)
- **`KinoCut.exe`** — Non-linear Video Editor
- **`KinoShop.exe`** — Raster Photo Editor
- **`KinoDraw.exe`** — Vector Illustration Studio
- **`KinoWave.exe`** — Multitrack Audio & VST3/VST2 Studio
- **`KinoFill.exe`** — PDF Editor & Form Studio
- **`KinoPixel.exe`** — GB/GBC/GBA Metroidvania Game Studio v2.0 with Sequence Genie & `.gba` ROM Compiler
- **`bsl_fusion.gba`** — Playable 3-room Metroidvania GBA ROM (16×32 Hero, Morph Ball, SRAM, BG2 Parallax, Omega Core Boss, DMA Audio)
- **`starbit_quest.gba`** — Playable GBA Platformer ROM built with KinoPixel

## Quick Start (From Source)

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

## Phone transfers with KinoPortal

Install the bundled `KinoPortal.apk` on Android and open **KinoPortal** from the
KinoSuite Hub. In the phone app, start sharing a folder or tap **Send files**.
You can also choose **Send to KinoSuite** from the Android share sheet. Paste
the phone's pairing link into the Windows receiver.

Browse the shared folder or select **Phone queue**. Select files and click
**Open in KinoSuite**. If several apps can use a file, choose the destination.
Photos can become editable images, vector tracing references, or game sprites.
Videos and audio can go to KinoCut's media library, audio and MIDI to KinoWave,
PDFs to KinoFill, and native game projects to KinoPixel.

**Pull files…** on the phone queue saves to **Portal Inbox**, which the Hub can
open. Downloads are acknowledged after the file is saved, and reconnecting
does not pull previously acknowledged files. Opening in an editor is optional.
