# KinoDraw — KinoSuite Vector Graphics Studio

**KinoDraw** is a native Windows vector graphics studio designed as part of **KinoSuite** (sharing the sleek deep-slate KinoCut design philosophy paired with Adobe Illustrator's studio layout and warm amber creative accents).

## Launching on Windows
- **Double-click `KinoDraw.exe`** (native 64-bit Windows launcher with `Kd` KinoSuite icon, no console window)
- Or run `.\run.ps1` in PowerShell
- To rebuild `KinoDraw.exe` & `KinoDraw.ico`: `.\build_launcher.ps1`
- To build a self-contained PyInstaller folder: `.\build_standalone.ps1`

## Highlights
- **Drawing & Path Editing**: Pen (`P`), Curvature (`Shift+~`), Pencil (`N`), Blob Brush (`Shift+B` auto-merge), Shaper (`Shift+N` gesture recognition & scribble erase), Shape tools (`M`, `L`, Polygon, Star, Line, Arc, Spiral), Direct Selection (`A`), Pathfinder (Unite, Minus Front/Back, Intersect, Exclude, Divide, Trim, Crop, Outline), Shape Builder (`Shift+M`), Scissors (`C`), Knife, Offset Path, Simplify Path, Join (`Ctrl+J`).
- **Color, Gradients & Appearance**: Solid RGB/CMYK/Spot colors, Overprint, Swatches & Color Groups, Linear/Radial/Freeform/Mesh Gradients, Gradient Along Stroke, Vector Patterns, Recolor Artwork & Generative Recolor, Live Paint Bucket (`K`), stackable Appearance (multiple fills, strokes & editable live effects), Graphic Styles, Blend Modes.
- **Brushes & Variable Width**: Calligraphic, Art, Scatter, Pattern, and Bristle brushes; Variable Width Tool (`Shift+W`) & width profiles; corner-aligned dashed strokes & arrowheads.
- **Typography**: Point, Area, and Type on a Path; Variable Font Weight/Width axes; OpenType Ligatures, Small Caps, Tabular Figures, Fractions; Touch Type (`Shift+T`) per-letter move/scale/rotate; Glyphs panel; Text Threading; Text Wrap around objects; Create Outlines (`Ctrl+Shift+O`).
- **3D, Perspective, Transforms, Data Graphics & Mockups**: 3D Extrusion & Materials (Glossy/Metallic/Matte), Envelope Warp, Puppet Warp (MLS pins), 1/2/3-Point Perspective Grid (`Shift+P`), Radial/Grid/Mirror Repeats, Blends (`W`), Global Edit, Data Charts (Bar, Stacked Bar, Line, Pie, Scatter), Studio Product Mockups (Mug, T-Shirt, Tote, Cup, Box, Phone).
- **Image Trace & Generative Features**: OpenCV K-Means & Bezier Image Trace + AI-Assisted Sketch Tracing, Image Crop, Linked/Embedded Links panel (PNG, JPG, WebP, SVG, PSD, PDF), Text-to-Vector Graphic & Generative Pattern Fill.
- **Print & Screen Production**: CMYK & Spot inks, Bleeds, Crop Marks, Separations Preview, Overprint Preview, Flattener Preview, Document Info, Print-Ready CMYK PDF export, Multi-Scale Asset Export & Export for Screens (SVG, PNG, JPG, WebP), Pixel Preview, CSS Snippets.
- **Workflow & Extensibility**: Actions Recorder, Live Python Script Runner, CSV Data-Driven Variables, Custom Workspaces & Shortcuts, KinoSuite Cloud Documents & Version History, Built-in & external Python Plugins (`plugins/`).
