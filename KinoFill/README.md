# KinoFill — KinoSuite PDF Studio

**KinoFill** is a 100% local, private, free Windows desktop PDF & form editor built as part of **KinoSuite** — sharing the sleek deep-slate architectural design philosophy of **KinoCut** and **KinoDraw** (`#12151C` studio darkroom, `#181C25` panels, crisp hairlines, and signature KinoSuite cyan & electric blue accents), with zero cloud uploads, no accounts, and no subscriptions.

## Quick Launch

- **Double-click `KinoFill.exe`** (native 64-bit Windows launcher with `Kf` KinoSuite icon — drag & drop any `.pdf` or `.kinofill` onto it, or pin it to your Windows taskbar).
- Or run `.\run.ps1` from PowerShell.
- To rebuild `KinoFill.exe` & `KinoFill.ico`: `.\build_launcher.ps1`.
- Want a standalone bundle for PCs without Python? Run `.\build_standalone.ps1`.

## Features

- **Edit All Text Mode (Default!)**
  - Every existing text block on every PDF page is automatically detected and immediately editable — just click any existing text on the page and an inline editor pops up right over it with auto-matched font, size, bold/italic, and color.
  - On save, **KinoFill surgically removes the replaced PDF text operators directly from the page's PDF content stream** (preserving shaded banners, table borders, and background graphics with zero white boxes, and ensuring `Ctrl+F` and text selection only see your new text!).
- **Interactive AcroForms & Form Builder**
  - Auto-detects existing fillable text fields, checkboxes, radio buttons, and dropdowns — click any highlighted field to fill.
  - Create brand-new fillable Text Fields, Checkboxes, or Dropdowns on any PDF, or flatten filled forms permanently on save.
- **Signatures, Quick Fill Marks & Stamps**
  - **Signature & Initials Vault**: Draw smooth signatures, type in cursive script fonts, or upload a photo with automatic white-background removal — saved locally in `%APPDATA%\KinoFill\signatures\`.
  - One-click **Checkmark (`✓`)**, **Cross (`✕`)**, **Dot (`•`)**, **Circle (`○`)**, **Today's Date**, and **Rubber Stamps** (`APPROVED`, `CONFIDENTIAL`, `DRAFT`, `PAID`, `VOID`, custom).
- **Markup, Whiteout & True Redaction**
  - Translucent **Highlight**, **Underline**, **Strikethrough**, **Freehand Pen**, **Shapes & Arrows**, **Insert Images**, and **Sticky Note Comments**.
  - **Smart Whiteout** + **True Raster Redaction** (permanently destroys blacked-out sensitive text from the PDF stream).
- **KinoSuite Studio Workspace & Page Tools**
  - Multi-tab workspace, HiDPI PDFium rendering, `Ctrl+F` search, **KinoSuite Dark Studio** (default) & **Studio Light** themes, Undo/Redo, Thumbnail Page Manager (Rotate, Reorder, Duplicate, Insert Blank/PDF, Delete), Merge PDFs, Split/Burst PDFs, Images to PDF, Export to PNG/JPEG, Watermarks, Headers/Footers & Page Numbers, Metadata Editor, Password Encryption, Native Printing, and Editable `.kinofill` Projects (backward-compatible with `.freefill` / `.lfill`).
