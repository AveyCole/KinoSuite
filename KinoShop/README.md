# KinoShop — KinoSuite Photo & Design Studio

**KinoShop** is a native Windows photo editing, retouching, compositing, print-prep, and generative design studio built as part of **KinoSuite** (sharing the sleek deep-slate architectural design philosophy of KinoCut and KinoDraw `#12151C` / `#181C25` paired with Photoshop's studio ergonomics and KinoShop's electric sapphire-cyan `#31A8FF` accent).

## Launching on Windows
- **Double-click `KinoShop.exe`** (native 64-bit Windows launcher with `Ks` KinoSuite icon, no console window)
- Or run `.\run.ps1` in PowerShell
- To rebuild `KinoShop.exe` & `KinoShop.ico`: `.\build_launcher.ps1`
- To build a self-contained PyInstaller bundle: `.\build_standalone.ps1`

## Native KinoShop File Types
- **`.ksd`** — KinoShop Document (lossless layered ZIP container storing raster, adjustment, smart object, vector, text, masks, channels, artboards, slices, layer comps, timeline, variables, comments, metadata, and Content Credentials)
- **`.ksa`** — KinoShop Actions presets

## Complete Feature Suite
- **Image Editing & Retouching**: Crop & Straighten (`C`), Image/Canvas Size, Spot Healing (`J`), AI Remove Tool, Clone Stamp (`S`), Content-Aware Fill, Dodge/Burn (`O`), Blur/Smudge, Liquify Studio (`Ctrl+Shift+X`), Lens & Perspective Correction.
- **Color, Tone & Camera Raw**: Non-destructive Adjustment Layers (Levels, Curves, Exposure, Hue/Saturation, Vibrance, Color Balance, Black & White, Photo Filter, Channel Mixer, 3D `.cube` & Built-in LUTs, Posterize, Threshold, Invert), Camera Raw Studio (`Ctrl+Shift+A`), Color Match between images.
- **Selections & Masking**: Marquee (`M`), Lasso / Polygonal Lasso (`L`), Quick Selection (`W`), Magic Wand, Pen Path (`P`), AI Select Subject, AI Select Sky, One-Click Remove Background, Layer Masks, Clipping Masks, Select and Mask (hair & edge decontamination).
- **Layers, Smart Objects, Styles & Comps**: Unlimited layers & groups with Photoshop-style thumbnails, 24 Blend Modes, Layer Styles (`fx`: Drop/Inner Shadow, Outer/Inner Glow, Bevel & Emboss, Color Overlay, Stroke), Embedded & **Linked Smart Objects** (auto-updating from disk), reversible **Smart Filters** (including **Lighting Effects** & **Lens Flare**), and **Layer Comps** for client layout variations.
- **Warping & Perspective**: Interactive **Puppet Warp** (MLS pins), **Perspective Warp** (4-point quad), **Vanishing Point** (perspective wall/floor tiling), and **Content-Aware Scale** (Seam Carving with skin & mask protection).
- **Smart Photo & Neural Filters**: **Harmonize** (scene lighting match), Sky Replacement, and Neural Filters (Colorize, Style Transfer, Smart Portrait, Depth Blur, Super Zoom 2×).
- **Painting & Tablet Support**: Pressure-sensitive `QTabletEvent` Brush (`B`), Wet **Mixer Brush**, Custom Captured Brushes, Symmetry Painting (Vertical/Horizontal/Dual/Radial), Eraser (`E`), Gradient (`G`), Paint Bucket, **History Panel, Snapshots & History Brush (`Y`)**.
- **Typography, Vectors & Artboards**: Point & Area Text, **Type on a Curved Path**, **Warped Text** (Arc, Arch, Bulge, Flag, Wave, Rise, Fish, Twist), Vector Shapes (`U`), and Multi-Artboards.
- **Photo Merging, Scanning & Print Production**: Photomerge Panorama, **Merge to HDR Pro**, Focus Stacking, Auto-Align & Auto-Blend, Windows WIA Scanner Acquire, Auto-Straighten Scan, Split Multiple Scanned Photos, **Contact Sheet II & Picture Package**.
- **Print Prep, Channels & Web**: RGB / CMYK / Grayscale / Lab modes, ICC Color Profiles, Soft-Proofing & Out-of-Gamut Warning, Bleed & Printer Marks (Crop, Bleed, Registration, CMYK Color Bars), Print-Ready CMYK PDF export, Individual Color / Alpha / Spot Ink Channels, Pattern Preview, Pattern Maker & Texture Synthesis, Slicing & Multi-Scale Web Export (`1x/2x/3x`).
- **Animation, Video, 3D & Science**: Frame-by-frame GIF Animator & Basic Video Timeline (MP4 import/export), Light 3D Primitives & Texturing, Calibrated Ruler & Scientific Auto-Count with CSV export.
- **Automation, Cloud, Extensions & Provenance**: Actions Recorder (`.ksa`), Batch Image Processor, CSV Variables & Data Sets, **Script Events Manager** (`on_open`/`on_save`/`on_export`/`on_new`), Live Python Scripting Console, KinoCloud Version History, Pinned Comments & Share-for-Review HTML, **Metadata & Content Credentials (KinoC2PA)**, and Built-in + External `.py` Extensions (`plugins/`).
