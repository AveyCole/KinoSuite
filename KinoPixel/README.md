# KinoPixel v2.0 — KinoSuite Retro Handheld Game Studio (GB / GBC / GBA)

**KinoPixel** is a start-to-finish Game Boy (`DMG`), Game Boy Color (`GBC`), and Game Boy Advance (`GBA`) game creation studio — including full **Metroidvania engine capabilities** — built in the **KinoSuite** architectural design language (alongside KinoCut, KinoShop, KinoDraw, KinoWave, and KinoFill).

## Highlights

- **KinoSuite Identity & Layout**: Deep-slate architectural UI (`Dark`, `Studio Light`, `High Contrast`), `Kp` badge icon, multi-project document tabs, collapsible right Hardware Budget & Undo History Inspector Dock, and 5-stage creation workflow.
- **Stage 1 — Metasprites & Animation Studio**: Supports `16×16`, `16×32` (tall armored Metroid-style heroes), and `32×32` (multi-HP bosses) hardware metasprites with Pencil, Eraser, Flood Fill, Line, Rectangle, Eyedropper, Horizontal Mirror Symmetry, Onion Skinning, Flip/Rotate, live animated preview, Animation Clips, Filmstrip Frame Timeline, and hardware-quantized 15-bit `BGR555` palettes.
- **Stage 2 — Tiles & Multi-Room World Editor**: Inline 8×8 tile painter with 12 hardware tile behaviors (`Empty`, `Solid`, `One-Way`, `Hazard`, `Coin`, `Spring`, `Goal`, `Destructible Block`, `Room Hatch/Door`, `SRAM Save Station`, `Ability Upgrade Orb`, `Navigation Terminal`), up to 16 interconnected rooms, ability-gated door warps, enemy/boss AI (`Patrol`, `Stalker/Chaser`, `Plasma Turret`, `32×32 Boss`), BG2 ½-speed parallax backdrops, and room dialogue boxes.
- **Stage 3 — Visual Button Wiring**: Interactive clickable GBA / GB handheld controller diagram + human-readable rule cards (`When [Button] is [Held / Pressed / Released] → Do [Action] + Play [Anim] + Play [SFX]`) including **Morph Ball hitbox swap**, **8-Way / Diagonal Aiming**, **Wall-Jump**, **Morph Bombs / Missiles**, and one-click Platformer, Top-Down RPG, Action Blaster, and **Metroidvania** presets.
- **Stage 4 — Chiptune Audio, Sequence Genie & Direct Sound DMA**:
  - **Sequence Genie Composer**: Authentic 19-scale REDUX library, interactive 16-step Piano Roll with per-step Lock / Chance / Repeat ratchets / Gate, Swing (50–75%), 16th Straight & Triplet grids, 8 Phrase Slots, **Chord Genie** (4/8-bar diatonic progressions, Strum 0–120ms, Arp/Block/Fast-Arp styles, 4-bit Wave Bass), **Euclidean Drum Genie** (4 chiptune drum lanes with Hits & Rotate), live loop playback, WAV bounce (for KinoWave), and direct embedding into the `.gba` ROM PSG Channel 2 soundtrack!
  - **Hardware PSG SFX & Direct Sound DMA Channel A**: Authentic GBA/GB Sound Channel 1 & 4 synthesizer plus **GBA Direct Sound DMA Channel A (8-bit PCM via DMA1 + Timer 0 + FIFO_A)** sample presets (`Boss Explosion`, `BSL Alarm`, `Item Fanfare`, `Laser Charge`).
- **Stage 5 — Live 60 FPS Playtest & Zero-Toolchain `.gba` ROM Compiler**: Embedded interactive playtest handheld + pure-Python **ARM7TDMI Assembler & GBA Cartridge Compiler** emitting bootable, playable `.gba` ROMs with Mode 0 `BG0` + `BG1` HUD/Dialogue + `BG2` Parallax + Hardware Alpha Blending (`REG_BLDCNT`), real **Cartridge SRAM battery saves (`0x0E000000` + `SRAM_V113`)**, PSG + Direct Sound DMA audio, and native `.gb` / `.gbc` & C header exports!
- **5 Playable Starter Templates**: **GBA Metroidvania (BSL Sector — 3 rooms + Omega Core Boss)**, GBA Platformer, GBA Top-Down RPG, GBC Adventure, and GB Classic (DMG).

## Quick Start

```bash
pip install PySide6 numpy Pillow sounddevice
python main.py
```

## Build Standalone Executable & Tests

```bash
python tests/test_kinopixel.py
python build_exe.py
```
