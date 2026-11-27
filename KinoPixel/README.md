# KinoPixel — KinoSuite Retro Handheld Game Studio (GB / GBC / GBA)

**KinoPixel** is a start-to-finish Game Boy (`DMG`), Game Boy Color (`GBC`), and Game Boy Advance (`GBA`) game creation studio built in the **KinoSuite** architectural design language (alongside KinoCut, KinoShop, and KinoWave).

## Highlights

- **KinoSuite Identity & Layout**: Deep-slate architectural UI (`Dark`, `Studio Light`, `High Contrast`), `Kp` badge icon, multi-project document tabs, collapsible right Hardware Budget & Undo History Inspector Dock, and 5-stage creation workflow.
- **Stage 1 — Sprites & Animation Studio**: 16×16 sprite pixel-art editor with Pencil, Eraser, Flood Fill, Line, Rectangle, Eyedropper, Horizontal Mirror Symmetry, Onion Skinning, Flip/Rotate, live animated preview, Animation Clips (`idle`, `walk`, `jump`, `attack`), Filmstrip Frame Timeline, and hardware-quantized 15-bit `BGR555` palette editor.
- **Stage 2 — Tiles & Level Map Studio**: Inline 8×8 tile painter with hardware collision/behavior tags (`Empty`, `Solid`, `One-Way`, `Hazard`, `Coin`, `Spring`, `Goal`), 64×32 scrollable level canvas, hero spawn placement, patrolling enemy placement, collision overlay, and 240×160 GBA / 160×144 GB/GBC screen viewport guide.
- **Stage 3 — Visual Button Wiring**: Interactive clickable GBA / GB handheld controller diagram + human-readable rule cards (`When [Button] is [Held / Pressed / Released] → Do [Action] + Play [Anim] + Play [SFX]`) with one-click Platformer, Top-Down RPG, and Action Blaster presets.
- **Stage 4 — Chiptune Audio & Sequence Genie Studio**:
  - **Sequence Genie Composer**: Authentic 19-scale REDUX library, interactive 16-step Piano Roll with per-step Lock / Chance / Repeat ratchets / Gate, Swing (50–75%), 16th Straight & Triplet grids, 8 Phrase Slots, **Chord Genie** (4/8-bar diatonic progressions, Strum 0–120ms, Arp/Block/Fast-Arp styles, 4-bit Wave Bass), **Euclidean Drum Genie** (4 chiptune drum lanes with Hits & Rotate), live loop playback, WAV bounce (for KinoWave), and direct embedding into the `.gba` ROM PSG Channel 2 soundtrack!
  - **Hardware PSG SFX Designer**: Authentic GBA/GB Sound Channel 1 (Square + Pitch Sweep + Envelope) and Channel 4 (LFSR Noise) synthesizer with real-time waveform visualization, instant audio preview, and exact compiled hardware registers.
- **Stage 5 — Live 60 FPS Playtest & Zero-Toolchain `.gba` ROM Compiler**: Embedded interactive playtest handheld + pure-Python **ARM7TDMI Assembler & GBA Cartridge Compiler** that emits real, bootable, playable `.gba` ROMs (verified 156-byte Nintendo logo, complement checksum, Mode 0 BG0 scrolling + BG1 HUD + 4bpp OAM sprites + PSG sound) — plus native `.gb` / `.gbc` and C header exports!

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
