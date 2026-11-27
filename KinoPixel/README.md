# KinoPixel v3.0 — KinoSuite Universal GB / GBC / GBA Game Studio

**KinoPixel** is a start-to-finish, genre-agnostic Game Boy (`DMG`), Game Boy Color (`GBC`), and Game Boy Advance (`GBA`) game creation studio built in the **KinoSuite** architectural design language (alongside KinoCut, KinoShop, KinoDraw, KinoWave, and KinoFill).

Designed with flexible, composable hardware primitives rather than locked templates, KinoPixel lets you create commercial-grade handheld games across **any genre** — side-scrolling platformers, interconnected action-exploration adventures, top-down action-RPGs, 8-way space shooters, tactical grid strategy games, and beyond — with zero external SDK required, plus full `devkitARM` C asset export when you want unrestricted custom C/C++ code.

## Highlights

- **KinoSuite Identity & Layout**: Deep-slate architectural UI (`Dark`, `Studio Light`, `High Contrast`), `Kp` badge icon, multi-project document tabs, collapsible right Hardware Budget & Undo History Inspector Dock, and 5-stage creation workflow.
- **Stage 1 — Pro Metasprites & Animation Studio**: Supports all GBA hardware OAM sizes (`16×16`, `16×32` Tall Character, `32×16` Wide Vehicle, `32×32` Large/Boss/Portrait, and `64×64` Giant Boss) with Pencil, Eraser, Flood Fill, Line, Rectangle, Eyedropper, **Checkerboard Dither Brush**, **Palette-Aware Luminance Shade Brush (darken/lighten)**, **1-Click Auto-Outline**, **Pixel Nudge Arrows**, Horizontal Mirror Symmetry, Onion Skinning, Flip/Rotate, **PNG/BMP/WebP Sprite Sheet & Portrait Importer** (with Pillow `MEDIANCUT` 15-color `BGR555` GBA palette quantization), live animated preview, Animation Clips, and Filmstrip Frame Timeline.
- **Stage 2 — Tiles & Multi-Room World Editor (Up to 128 Maps)**:
  - Inline 8×8 tile painter with **17 universal hardware tile behaviors**: `Empty`, `Solid`, `One-Way Platform`, `45° Slopes (/) & (\)`, `Water / Low-G Swim`, `Climbable Ladder`, `World Switch`, `Destructible Block`, `Map Warp / Door`, `SRAM Save Checkpoint`, `Key / Skill Unlock`, `Dialogue Trigger`, `Spring / Boost`, `Hazard`, `Collectible`, and `Stage Goal`.
  - **4 Native Physics / Movement Engines**: Side-View Platformer, Top-Down 4-Way RPG, 8-Way Space Action / Flight, and Tactical Grid (16px tile-step).
  - **6 Universal Entity / AI Archetypes**: `Patrol`, `Chaser / Stalker`, `Projectile Turret`, `Multi-Phase Boss` (configurable Phase 2 HP threshold for 3-way spread + 2× speed & World Flag on defeat), `Sine-Wave Hover / Swooper`, and `Friendly NPC` (triggers multi-page dialogue).
  - Room Minimap `(X, Y)` coordinates, **2-Page Dialogue Box**, and `BG2` ½-speed parallax backdrops with hardware Alpha Blending.
- **Stage 3 — Visual Button Wiring, 9-Slice GBA UI Designer & KinoScript Native ARM7TDMI Studio**:
  - **Visual Wiring Mode (Zero-Code)**: Interactive clickable GBA / GB handheld diagram + rule cards wiring any button to **19 universal actions** with **Conditional Gates** (`Always`, `If Var > 0`, `If World Flag Set`, `If Skill Unlocked`) and **Variable Modifiers (`Var +/-`)** across 8 persistent Game Variables (`VAR[0..7]`) and 32 World Flags!
  - **Visual UI & Menu Designer (9-Slice GBA)**: Interactive 30×20 layout editor for beveled **9-slice GBA windows** (`draw_window`), drop-shadow text labels, and **segmented HP/progress gauge bars** (`draw_bar`) with live 240×160 preview and 1-click **`Send to KinoScript →`** export.
  - **KinoScript Native ARM7TDMI Studio (Full 1:1 Commercial GBA Power!)**: Write unrestricted Python-syntax game logic (`def on_init():`, `def on_frame():`, custom functions, loops, conditionals, and up to **240 KB of EWRAM arrays & variables**) with full direct access to all **128 OAM sprites (`16×16`..`64×64`)**, **BG0/BG1/BG2 tilemaps**, commercial **9-slice beveled windows**, **segmented gauge bars**, **hardware `REG_BLDCNT`/`REG_BLDY` screen fades & hit flashes (`set_fade`)**, **5-voice audio**, and **32 KB GBA SRAM**. Compiles **directly to native 32-bit ARM7TDMI machine code** inside `.gba` ROMs with zero external SDK AND runs 1:1 in the live 60 FPS Playtester!
  - Proven out-of-the-box by **`Advance Ops`** — a commercial-grade turn-based tactical strategy game written in KinoScript featuring a **9-slice Animated Title Screen** (`NEW CAMPAIGN` / `CO BRIEFING` / `CONTINUE`), **`32×32` Shaded Commander Portrait Briefing**, **Move-then-Command Popup Menu** (`FIRE` / `CAPT` / `WAIT` with `B` undo-move snapback), **Live Battle Forecast Window** (predicted attacker & counter-attack damage % + segmented gauges before engaging!), **White Impact Flash + Camera Shake + 3-Frame Animated Explosion VFX**, **Command Pause Menu** & **War Room Intel Screen**, Factory Production Menu, autonomous Red Army AI turn, and GBA SRAM save!
- **Stage 4 — 5-Voice GBA Audio & Sequence Genie Studio**:
  - **Sequence Genie Composer**: 19-scale REDUX library, interactive 16-step Piano Roll (Lock / Chance / Repeat / Gate), Swing (50–75%), 8 Phrase Slots, Chord Genie, Euclidean Drum Genie, WAV bounce, and native 3-voice ROM playback (**PSG Ch2 Lead + Ch3 4-bit Wave RAM Bass + Ch4 Euclidean Drums**)!
  - **Hardware PSG SFX (Ch1 & Ch4)** + **GBA Direct Sound DMA Channel A (8-bit PCM via DMA1 + Timer 0 + FIFO_A)**!
- **Stage 5 — Live 60 FPS Playtest & Zero-Toolchain `.gba` ROM Compiler**: Embedded interactive playtest handheld (with live Pause-Screen Auto-Minimap) + pure-Python **ARM7TDMI Assembler & GBA Cartridge Compiler** emitting bootable `.gba` ROMs with Mode 0 `BG0`+`BG1`+`BG2`+`OBJ`, **Pause Auto-Minimap**, real **24-byte GBA Cartridge SRAM (`0x0E000000` + `SRAM_V113`)**, native `.gb`/`.gbc` export, and full **`devkitARM` C starter export** (`kinopixel_assets.h`, `main.c`, `Makefile`).
- **7 Multi-Genre Showcase Templates**: GBA Platformer (`Starbit`), GBA Sci-Fi Exploration (`BSL Sector`), GBA Action-RPG (`Legacy Quest`), GBA Space Action (`Omega Wing`), GBA Tactical Grid (`Advance Ops`), GBC Adventure, and GB Classic (`DMG`).

## Quick Start

```bash
pip install PySide6 numpy Pillow sounddevice
python main.py
```

## Build Standalone Executable & ARM7TDMI Tests

```bash
python tests/test_kinopixel.py
python build_exe.py
```
