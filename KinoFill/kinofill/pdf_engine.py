"""PDF processing engine for KinoFill (KinoSuite).

Handles:
- Coordinate conversion across CropBox and /Rotate (0, 90, 180, 270)
- Windows TrueType font registration in ReportLab
- AcroForm widget extraction, value updates, brand-new form field creation, and flattening
- Vector overlay rendering (text, whiteout, redact, highlight/underline/strike, ink, shapes,
  arrows, stamps, signatures/images, sticky notes, watermarks, headers & footers)
- True raster redaction (destroys underlying PDF text streams on redacted pages)
- Page management (rotate, reorder, delete, duplicate, insert blank, insert PDF, merge, split)
- Image-to-PDF, PDF-to-Images, password encryption/decryption, and metadata editing
"""

from __future__ import annotations

import base64
import io
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image
import pypdf
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from .models import (
    BaseItem,
    DocumentState,
    EditableTextBlock,
    FormFieldItem,
    HeaderFooterConfig,
    HighlightItem,
    ImageItem,
    InkItem,
    NoteItem,
    PdfMetadata,
    RedactItem,
    SecurityConfig,
    ShapeItem,
    StampItem,
    TextItem,
    WatermarkConfig,
    WhiteoutItem,
)

# Standard Windows TrueType font mappings: display name -> (regular, bold, italic, bold_italic)
WINDOWS_FONT_MAP: Dict[str, Tuple[str, str, str, str]] = {
    "Arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "Courier New": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    "Comic Sans MS": ("comic.ttf", "comicbd.ttf", "comici.ttf", "comicz.ttf"),
    "Impact": ("impact.ttf", "impact.ttf", "impact.ttf", "impact.ttf"),
}

SIGNATURE_SCRIPT_FONTS: List[Tuple[str, str]] = [
    ("Segoe Script", "segoesc.ttf"),
    ("Brush Script MT", "brushsci.ttf"),
    ("Lucida Handwriting", "lhandw.ttf"),
    ("Freestyle Script", "freescpt.ttf"),
    ("Ink Free", "inkfree.ttf"),
    ("Gabriola", "gabriola.ttf"),
    ("Georgia Italic", "georgiai.ttf"),
]

_REGISTERED_RL_FONTS: Dict[str, str] = {}


def get_available_fonts() -> List[str]:
    return list(WINDOWS_FONT_MAP.keys())


def get_available_signature_fonts() -> List[Tuple[str, str]]:
    fonts_dir = Path(r"C:\Windows\Fonts")
    result: List[Tuple[str, str]] = []
    for display, fname in SIGNATURE_SCRIPT_FONTS:
        p = fonts_dir / fname
        if p.exists():
            result.append((display, str(p)))
    if not result:
        result.append(("Segoe UI", ""))
    return result


def resolve_rl_font(family: str, bold: bool = False, italic: bool = False) -> str:
    """Register and return a ReportLab font name for the requested Windows font & style."""
    key = f"{family}|{int(bold)}|{int(italic)}"
    if key in _REGISTERED_RL_FONTS:
        return _REGISTERED_RL_FONTS[key]

    fonts_dir = Path(r"C:\Windows\Fonts")
    idx = (1 if bold else 0) + (2 if italic else 0)
    tuple_files = WINDOWS_FONT_MAP.get(family)
    if tuple_files:
        candidates = [tuple_files[idx], tuple_files[0]]
        for fname in candidates:
            fpath = fonts_dir / fname
            if fpath.exists():
                rl_name = f"LF_{fname.replace('.', '_')}"
                if rl_name not in pdfmetrics.getRegisteredFontNames():
                    try:
                        pdfmetrics.registerFont(TTFont(rl_name, str(fpath)))
                    except Exception:
                        continue
                _REGISTERED_RL_FONTS[key] = rl_name
                return rl_name

    # Built-in PDF Base14 fallbacks
    fam_low = family.lower()
    if "times" in fam_low or "georgia" in fam_low:
        base = "Times"
        if bold and italic:
            name = "Times-BoldItalic"
        elif bold:
            name = "Times-Bold"
        elif italic:
            name = "Times-Italic"
        else:
            name = "Times-Roman"
    elif "courier" in fam_low or "mono" in fam_low:
        if bold and italic:
            name = "Courier-BoldOblique"
        elif bold:
            name = "Courier-Bold"
        elif italic:
            name = "Courier-Oblique"
        else:
            name = "Courier"
    else:
        if bold and italic:
            name = "Helvetica-BoldOblique"
        elif bold:
            name = "Helvetica-Bold"
        elif italic:
            name = "Helvetica-Oblique"
        else:
            name = "Helvetica"
    _REGISTERED_RL_FONTS[key] = name
    return name


def hex_to_rl_color(hex_str: str, alpha: float = 1.0) -> Color:
    s = (hex_str or "#000000").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return Color(0, 0, 0, alpha=alpha)
    r = int(s[0:2], 16) / 255.0
    g = int(s[2:4], 16) / 255.0
    b = int(s[4:6], 16) / 255.0
    return Color(r, g, b, alpha=alpha)


def parse_page_range(range_str: str, total_pages: int) -> List[int]:
    """Parse 'all' or '1-3, 5, 7-9' into sorted 0-based page indices."""
    s = (range_str or "all").strip().lower()
    if not s or s == "all":
        return list(range(total_pages))
    indices: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            pieces = part.split("-", 1)
            try:
                start = max(1, int(pieces[0].strip()))
                end = min(total_pages, int(pieces[1].strip()))
                for p in range(start, end + 1):
                    indices.add(p - 1)
            except ValueError:
                continue
        else:
            try:
                p = int(part)
                if 1 <= p <= total_pages:
                    indices.add(p - 1)
            except ValueError:
                continue
    return sorted(indices)


def get_page_geometry(page: pypdf.PageObject) -> Tuple[float, float, float, float, int, float, float]:
    """Return (x0, y0, x1, y1, rotation, vis_w, vis_h) for a pypdf page."""
    box = page.cropbox if page.cropbox is not None else page.mediabox
    x0 = float(box.left)
    y0 = float(box.bottom)
    x1 = float(box.right)
    y1 = float(box.top)
    rot = int(page.get("/Rotate", 0) or 0) % 360
    if rot in (90, 270):
        vis_w, vis_h = (y1 - y0), (x1 - x0)
    else:
        vis_w, vis_h = (x1 - x0), (y1 - y0)
    return x0, y0, x1, y1, rot, vis_w, vis_h


def pdf_rect_to_visual(
    rect: Sequence[float],
    cropbox: Tuple[float, float, float, float],
    rotation: int,
) -> Tuple[float, float, float, float]:
    """Convert PDF user-space [rx0, ry0, rx1, ry1] into visual top-left (x, y, w, h)."""
    x0, y0, x1, y1 = cropbox
    rx0, ry0, rx1, ry1 = [float(v) for v in rect]
    if rx0 > rx1:
        rx0, rx1 = rx1, rx0
    if ry0 > ry1:
        ry0, ry1 = ry1, ry0

    corners_pdf = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)]
    vis_pts: List[Tuple[float, float]] = []
    rot = rotation % 360
    for px, py in corners_pdf:
        if rot == 0:
            vx = px - x0
            vy = y1 - py
        elif rot == 90:
            vx = py - y0
            vy = px - x0
        elif rot == 180:
            vx = x1 - px
            vy = py - y0
        elif rot == 270:
            vx = y1 - py
            vy = x1 - px
        else:
            vx = px - x0
            vy = y1 - py
        vis_pts.append((vx, vy))

    xs = [p[0] for p in vis_pts]
    ys = [p[1] for p in vis_pts]
    vx0, vx1 = min(xs), max(xs)
    vy0, vy1 = min(ys), max(ys)
    return vx0, vy0, max(2.0, vx1 - vx0), max(2.0, vy1 - vy0)


def visual_rect_to_pdf(
    vx: float,
    vy: float,
    vw: float,
    vh: float,
    cropbox: Tuple[float, float, float, float],
    rotation: int,
) -> List[float]:
    """Convert visual top-left (vx, vy, vw, vh) into PDF user-space [rx0, ry0, rx1, ry1]."""
    x0, y0, x1, y1 = cropbox
    corners_vis = [(vx, vy), (vx + vw, vy), (vx + vw, vy + vh), (vx, vy + vh)]
    pdf_pts: List[Tuple[float, float]] = []
    rot = rotation % 360
    for ux, uy in corners_vis:
        if rot == 0:
            px = x0 + ux
            py = y1 - uy
        elif rot == 90:
            px = x0 + uy
            py = y0 + ux
        elif rot == 180:
            px = x1 - ux
            py = y0 + uy
        elif rot == 270:
            px = x1 - uy
            py = y1 - ux
        else:
            px = x0 + ux
            py = y1 - uy
        pdf_pts.append((px, py))

    xs = [p[0] for p in pdf_pts]
    ys = [p[1] for p in pdf_pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def overlay_transform_for_page(
    cropbox: Tuple[float, float, float, float], rotation: int
) -> Transformation:
    """Return pypdf Transformation mapping visual-space ReportLab overlay to PDF page space."""
    x0, y0, x1, y1 = cropbox
    rot = rotation % 360
    if rot == 0:
        return Transformation().translate(x0, y0)
    if rot == 90:
        return Transformation().rotate(90).translate(x1, y0)
    if rot == 180:
        return Transformation().rotate(180).translate(x1, y1)
    if rot == 270:
        return Transformation().rotate(-90).translate(x0, y1)
    return Transformation().translate(x0, y0)


def open_reader(pdf_path: str, password: str = "") -> PdfReader:
    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        res = reader.decrypt(password or "")
        if not res:
            raise ValueError("PDF is password-protected or password is incorrect.")
    return reader


def _map_pdf_font_name(raw_name: str) -> Tuple[str, bool, bool]:
    """Map a PDF /BaseFont name (e.g. /ABCDEF+Calibri-BoldItalic) to (WindowsFamily, bold, italic)."""
    name = (raw_name or "").lstrip("/")
    if "+" in name:
        name = name.split("+", 1)[1]
    low = name.lower()

    bold = any(k in low for k in ("bold", "black", "heavy", "demi", "semi", "extrab", "ultrab"))
    italic = any(k in low for k in ("italic", "oblique", "slant", "cursiv"))

    if "calibri" in low:
        fam = "Calibri"
    elif "segoe" in low:
        fam = "Segoe UI"
    elif "times" in low or "garamond" in low or "cambria" in low or "serif" in low:
        fam = "Times New Roman"
    elif "georgia" in low:
        fam = "Georgia"
    elif "courier" in low or "consola" in low or "mono" in low:
        fam = "Courier New"
    elif "comic" in low:
        fam = "Comic Sans MS"
    elif "impact" in low:
        fam = "Impact"
    else:
        fam = "Arial"
    return fam, bold, italic


def _extract_pypdf_style_spans(
    page: pypdf.PageObject,
) -> List[Dict[str, Any]]:
    """Extract text runs with visual (x, y), font family, font size, bold/italic, and fill color."""
    x0, y0, x1, y1, rot, _, _ = get_page_geometry(page)
    cropbox = (x0, y0, x1, y1)

    color_stack: List[str] = ["#111827"]
    spans: List[Dict[str, Any]] = []

    def op_before(op: bytes, args: Any, cm: Any, tm: Any) -> None:
        try:
            if op == b"q":
                color_stack.append(color_stack[-1])
            elif op == b"Q":
                if len(color_stack) > 1:
                    color_stack.pop()
            elif op == b"rg" and len(args) >= 3:
                rr, gg, bb = [max(0, min(255, int(round(float(v) * 255)))) for v in args[:3]]
                color_stack[-1] = f"#{rr:02X}{gg:02X}{bb:02X}"
            elif op == b"g" and len(args) >= 1:
                g = max(0, min(255, int(round(float(args[0]) * 255))))
                color_stack[-1] = f"#{g:02X}{g:02X}{g:02X}"
            elif op == b"k" and len(args) >= 4:
                cc, mm, yy, kk = [float(v) for v in args[:4]]
                rr = max(0, min(255, int(round(255 * (1 - cc) * (1 - kk)))))
                gg = max(0, min(255, int(round(255 * (1 - mm) * (1 - kk)))))
                bb = max(0, min(255, int(round(255 * (1 - yy) * (1 - kk)))))
                color_stack[-1] = f"#{rr:02X}{gg:02X}{bb:02X}"
        except Exception:
            pass

    def vis_text(text: str, cm: Any, tm: Any, font_dict: Any, font_size: Any) -> None:
        clean = (text or "").strip()
        if not clean:
            return
        try:
            raw_font = str(font_dict.get("/BaseFont", "")) if isinstance(font_dict, dict) else ""
            fam, bold, italic = _map_pdf_font_name(raw_font)
            tm_a, tm_b, tm_c, tm_d, tm_e, tm_f = [float(v) for v in (tm or [1, 0, 0, 1, 0, 0])]
            cm_a, cm_b, cm_c, cm_d, cm_e, cm_f = [float(v) for v in (cm or [1, 0, 0, 1, 0, 0])]
            # Combined origin in PDF user space: CTM * TM * (0, 0)
            px = cm_a * tm_e + cm_c * tm_f + cm_e
            py = cm_b * tm_e + cm_d * tm_f + cm_f
            # Combined vertical scale
            sy = math.hypot(tm_c, tm_d) * math.hypot(cm_c, cm_d)
            eff_size = abs(float(font_size or 11.0)) * (sy if sy > 0.05 else 1.0)
            eff_size = max(6.0, min(96.0, eff_size))
            vx, vy, _, _ = pdf_rect_to_visual([px, py, px + 2, py + eff_size], cropbox, rot)
            spans.append(
                {
                    "text": clean,
                    "x": vx,
                    "y": vy,
                    "font_family": fam,
                    "font_size": round(eff_size, 1),
                    "bold": bold,
                    "italic": italic,
                    "color": color_stack[-1],
                }
            )
        except Exception:
            pass

    try:
        page.extract_text(visitor_operand_before=op_before, visitor_text=vis_text)
    except Exception:
        pass
    return spans


def extract_editable_text_blocks(
    pdf_path: str,
    password: str,
    pdf_doc: Any,
    existing_form_fields: Optional[Sequence[FormFieldItem]] = None,
) -> Dict[int, List[EditableTextBlock]]:
    """Detect every editable text line/column block on every page with matched font, size, and color."""
    from PySide6.QtCore import QPointF, QRectF

    result: Dict[int, List[EditableTextBlock]] = {}
    reader: Optional[PdfReader] = None
    try:
        reader = open_reader(pdf_path, password)
    except Exception:
        reader = None

    form_rects_by_page: Dict[int, List[QRectF]] = {}
    for ff in existing_form_fields or []:
        form_rects_by_page.setdefault(ff.page, []).append(QRectF(ff.x, ff.y, ff.w, ff.h))

    page_count = pdf_doc.pageCount()
    for page_idx in range(page_count):
        blocks: List[EditableTextBlock] = []
        style_spans = (
            _extract_pypdf_style_spans(reader.pages[page_idx])
            if (reader is not None and page_idx < len(reader.pages))
            else []
        )
        form_rects = form_rects_by_page.get(page_idx, [])

        try:
            full_sel = pdf_doc.getAllText(page_idx)
            full_text = full_sel.text() or ""
        except Exception:
            full_text = ""

        if not full_text.strip():
            result[page_idx] = blocks
            continue

        for match in re.finditer(r"[^\r\n]+", full_text):
            raw_line = match.group()
            if not raw_line.strip():
                continue
            try:
                line_sel = pdf_doc.getSelectionAtIndex(page_idx, match.start(), len(raw_line))
                raw_rects = [b.boundingRect() for b in line_sel.bounds() if b.boundingRect().width() > 1.0 and b.boundingRect().height() > 1.0]
            except Exception:
                continue
            if not raw_rects:
                continue

            # Sort left-to-right and merge horizontally close rects on the same line,
            # while splitting wide column gaps into separate clickable boxes!
            raw_rects.sort(key=lambda r: (round(r.top() / 4.0), r.left()))
            merged_rects: List[QRectF] = []
            for r in raw_rects:
                if not merged_rects:
                    merged_rects.append(QRectF(r))
                    continue
                prev = merged_rects[-1]
                same_row = abs(prev.center().y() - r.center().y()) <= max(prev.height(), r.height()) * 0.7
                gap = r.left() - prev.right()
                max_gap = max(14.0, max(prev.height(), r.height()) * 1.45)
                if same_row and gap <= max_gap:
                    merged_rects[-1] = prev.united(r)
                else:
                    merged_rects.append(QRectF(r))

            for mr in merged_rects:
                if len(merged_rects) == 1:
                    seg_text = raw_line.strip()
                else:
                    try:
                        seg_sel = pdf_doc.getSelection(
                            page_idx,
                            QPointF(mr.left() + 0.5, mr.center().y()),
                            QPointF(mr.right() - 0.5, mr.center().y()),
                        )
                        seg_text = (seg_sel.text() or "").strip()
                    except Exception:
                        seg_text = ""
                    if not seg_text:
                        seg_text = raw_line.strip()

                if not seg_text:
                    continue

                # Skip text sitting strictly inside an interactive AcroForm widget
                center_pt = mr.center()
                if any(fr.contains(center_pt) for fr in form_rects):
                    continue

                # Match best style span from pypdf (font family, size, bold, italic, color)
                best_span: Optional[Dict[str, Any]] = None
                best_score = -1.0
                seg_low = seg_text.lower()
                for sp in style_spans:
                    sp_low = sp["text"].lower()
                    dist = math.hypot(sp["x"] - mr.left(), sp["y"] - mr.top())
                    if dist > 90.0:
                        continue
                    overlap = 0.0
                    if seg_low == sp_low:
                        overlap = 40.0
                    elif sp_low in seg_low or seg_low in sp_low:
                        overlap = 25.0
                    score = overlap - dist * 0.45
                    if score > best_score:
                        best_score = score
                        best_span = sp

                if best_span is not None and best_score > -18.0:
                    fam = best_span["font_family"]
                    fsize = best_span["font_size"]
                    bold = best_span["bold"]
                    italic = best_span["italic"]
                    col = best_span["color"]
                else:
                    fam = "Arial"
                    fsize = round(max(7.5, min(42.0, mr.height() * 1.18)), 1)
                    bold = False
                    italic = False
                    col = "#111827"

                # Keep editable box tight around glyphs so it never clips adjacent form underlines
                pad_top = max(0.5, fsize * 0.08)
                pad_bot = max(0.5, fsize * 0.08)
                blocks.append(
                    EditableTextBlock(
                        page=page_idx,
                        x=max(0.0, mr.left() - 0.5),
                        y=max(0.0, mr.top() - pad_top),
                        w=mr.width() + 2.0,
                        h=max(mr.height() + pad_top + pad_bot, fsize * 1.12),
                        text=seg_text,
                        font_family=fam,
                        font_size=fsize,
                        bold=bold,
                        italic=italic,
                        color=col,
                    )
                )

        result[page_idx] = blocks
    return result


def read_pdf_metadata(pdf_path: str, password: str = "") -> PdfMetadata:
    try:
        reader = open_reader(pdf_path, password)
        meta = reader.metadata or {}
        return PdfMetadata(
            title=str(meta.get("/Title", "") or ""),
            author=str(meta.get("/Author", "") or ""),
            subject=str(meta.get("/Subject", "") or ""),
            keywords=str(meta.get("/Keywords", "") or ""),
            creator=str(meta.get("/Creator", "") or "KinoFill"),
        )
    except Exception:
        return PdfMetadata()


def _resolve_inherited(obj: Any, key: str) -> Any:
    cur = obj
    seen = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        try:
            real = cur.get_object() if hasattr(cur, "get_object") else cur
        except Exception:
            break
        if isinstance(real, dict) and key in real:
            return real[key]
        cur = real.get("/Parent") if isinstance(real, dict) else None
    return None


def _qualified_field_name(annot: Any) -> str:
    parts: List[str] = []
    cur = annot
    seen = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        try:
            real = cur.get_object() if hasattr(cur, "get_object") else cur
        except Exception:
            break
        if isinstance(real, dict) and "/T" in real:
            parts.append(str(real["/T"]))
        cur = real.get("/Parent") if isinstance(real, dict) else None
    parts.reverse()
    return ".".join(parts)


def extract_acroform_fields(pdf_path: str, password: str = "") -> List[FormFieldItem]:
    """Parse interactive AcroForm widget fields from every page."""
    fields: List[FormFieldItem] = []
    try:
        reader = open_reader(pdf_path, password)
    except Exception:
        return fields

    for page_idx, page in enumerate(reader.pages):
        annots = page.get("/Annots")
        if not annots:
            continue
        try:
            annot_list = annots.get_object()
        except Exception:
            continue
        if not isinstance(annot_list, list):
            continue

        x0, y0, x1, y1, rot, _, _ = get_page_geometry(page)
        cropbox = (x0, y0, x1, y1)

        for annot_ref in annot_list:
            try:
                annot = annot_ref.get_object()
            except Exception:
                continue
            if not isinstance(annot, dict):
                continue
            if str(annot.get("/Subtype", "")) != "/Widget":
                continue
            rect = annot.get("/Rect")
            if not rect or len(rect) != 4:
                continue

            ft = str(_resolve_inherited(annot, "/FT") or "")
            name = _qualified_field_name(annot)
            if not name:
                name = f"field_{page_idx}_{len(fields)}"
            ff = int(_resolve_inherited(annot, "/Ff") or 0)
            val_obj = _resolve_inherited(annot, "/V")
            val_str = "" if val_obj is None else str(val_obj)
            vx, vy, vw, vh = pdf_rect_to_visual(rect, cropbox, rot)

            if ft == "/Tx":
                multiline = bool(ff & (1 << 12))
                fields.append(
                    FormFieldItem(
                        page=page_idx,
                        x=vx,
                        y=vy,
                        w=vw,
                        h=vh,
                        field_name=name,
                        field_type="text",
                        value=val_str,
                        multiline=multiline,
                        font_size=max(8.0, min(14.0, vh * 0.55 if not multiline else 10.5)),
                        is_existing=True,
                    )
                )
            elif ft == "/Btn":
                is_pushbutton = bool(ff & (1 << 16))
                if is_pushbutton:
                    continue
                is_radio = bool(ff & (1 << 15))
                # Determine ON state from /AP /N keys
                on_state = "/Yes"
                ap = annot.get("/AP")
                if ap:
                    try:
                        ap_obj = ap.get_object()
                        n_obj = ap_obj.get("/N")
                        if n_obj:
                            n_dict = n_obj.get_object()
                            if isinstance(n_dict, dict):
                                for k in n_dict.keys():
                                    ks = str(k)
                                    if ks != "/Off":
                                        on_state = ks
                                        break
                    except Exception:
                        pass
                as_val = str(annot.get("/AS", "") or "")
                checked = (as_val == on_state) or (val_str == on_state and on_state != "/Off")
                fields.append(
                    FormFieldItem(
                        page=page_idx,
                        x=vx,
                        y=vy,
                        w=vw,
                        h=vh,
                        field_name=name,
                        field_type="radio" if is_radio else "checkbox",
                        checked=checked,
                        checked_value=on_state,
                        value=on_state if checked else "/Off",
                        radio_group=name if is_radio else "",
                        is_existing=True,
                    )
                )
            elif ft == "/Ch":
                opt_obj = _resolve_inherited(annot, "/Opt")
                options: List[str] = []
                if opt_obj:
                    try:
                        opt_list = opt_obj.get_object() if hasattr(opt_obj, "get_object") else opt_obj
                        for opt in opt_list:
                            if isinstance(opt, list) and opt:
                                options.append(str(opt[-1]))
                            else:
                                options.append(str(opt))
                    except Exception:
                        pass
                fields.append(
                    FormFieldItem(
                        page=page_idx,
                        x=vx,
                        y=vy,
                        w=vw,
                        h=vh,
                        field_name=name,
                        field_type="dropdown",
                        value=val_str,
                        options=options,
                        font_size=max(8.0, min(13.0, vh * 0.55)),
                        is_existing=True,
                    )
                )
    return fields


def _wrap_text_lines(text: str, font_name: str, font_size: float, max_width: float) -> List[str]:
    """Word-wrap text to fit max_width in ReportLab points."""
    lines: List[str] = []
    usable_w = max(12.0, max_width)
    for raw_para in (text or "").splitlines() or [""]:
        if not raw_para:
            lines.append("")
            continue
        words = raw_para.split(" ")
        cur = ""
        for word in words:
            candidate = f"{cur} {word}".strip() if cur else word
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= usable_w:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                # Break extra-long word if needed
                if pdfmetrics.stringWidth(word, font_name, font_size) > usable_w:
                    chunk = ""
                    for ch in word:
                        if pdfmetrics.stringWidth(chunk + ch, font_name, font_size) <= usable_w:
                            chunk += ch
                        else:
                            if chunk:
                                lines.append(chunk)
                            chunk = ch
                    cur = chunk
                else:
                    cur = word
        lines.append(cur)
    return lines


def _mm(m1: Sequence[float], m2: Sequence[float]) -> List[float]:
    """Multiply two 2D PDF affine matrices [a, b, c, d, e, f] (row-vector convention: v * m1 * m2)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return [
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    ]


def _get_font_widths(font_obj: Any) -> Tuple[int, List[float]]:
    """Extract (first_char, widths_in_1000_units) from a simple PDF font dictionary if available."""
    try:
        if hasattr(font_obj, "get_object"):
            font_obj = font_obj.get_object()
        if not isinstance(font_obj, dict):
            return 0, []
        first_ch = int(font_obj.get("/FirstChar", 0) or 0)
        w_obj = font_obj.get("/Widths")
        if w_obj is not None:
            if hasattr(w_obj, "get_object"):
                w_obj = w_obj.get_object()
            if isinstance(w_obj, list):
                return first_ch, [float(v) for v in w_obj]
    except Exception:
        pass
    return 0, []


def _string_advance_tx(
    raw_str_obj: Any,
    first_char: int,
    widths: Sequence[float],
    font_size: float,
    tc: float,
    tw: float,
    tz: float,
) -> float:
    """Estimate horizontal advance in text space for a PDF string operand."""
    try:
        if isinstance(raw_str_obj, bytes):
            bs = raw_str_obj
        else:
            s = str(raw_str_obj)
            bs = s.encode("latin-1", errors="replace")
    except Exception:
        bs = b""
    if not bs:
        return 0.0

    scale_h = tz / 100.0
    total = 0.0
    for code in bs:
        w1000 = 520.0
        idx = code - first_char
        if 0 <= idx < len(widths):
            w1000 = widths[idx]
        elif code == 32:
            w1000 = 280.0
        adv = (w1000 / 1000.0) * font_size + tc
        if code == 32:
            adv += tw
        total += adv * scale_h
    return total


def _rect_overlaps_target(
    vx0: float,
    vy0: float,
    vx1: float,
    vy1: float,
    targets: Sequence[Tuple[str, float, float, float, float]],
) -> Optional[str]:
    """Return matching target ID if a text run's visual box overlaps a replaced block."""
    if vx0 > vx1:
        vx0, vx1 = vx1, vx0
    if vy0 > vy1:
        vy0, vy1 = vy1, vy0
    run_w = max(2.0, vx1 - vx0)
    run_h = max(2.0, vy1 - vy0)
    run_cy = (vy0 + vy1) * 0.5

    for tid, mx, my, mw, mh in targets:
        # Vertical alignment: text baseline/center must sit within target vertical band
        if not ((my - 3.5) <= run_cy <= (my + mh + 4.5)):
            continue
        # Horizontal overlap
        ov_x = min(vx1, mx + mw + 3.0) - max(vx0, mx - 3.0)
        if ov_x <= 0.0:
            continue
        # Require meaningful overlap (at least 35% of the smaller span, or >= 4pt)
        if ov_x >= min(run_w, mw) * 0.35 or ov_x >= 4.0:
            return tid
    return None


def _strip_text_ops_in_stream(
    writer: PdfWriter,
    stream_owner: Any,
    resources: Any,
    targets: Sequence[Tuple[str, float, float, float, float]],
    cropbox: Tuple[float, float, float, float],
    rotation: int,
    initial_cm: Optional[List[float]] = None,
    depth: int = 0,
) -> Tuple[Optional[bytes], set[str]]:
    """Recursively strip replaced text operators from a page or Form XObject content stream."""
    removed_ids: set[str] = set()
    if depth > 6 or not targets:
        return None, removed_ids

    try:
        if isinstance(stream_owner, pypdf.PageObject):
            raw_contents = stream_owner.get_contents()
            if raw_contents is None:
                return None, removed_ids
            cs = ContentStream(raw_contents, writer)
        else:
            cs = ContentStream(stream_owner, writer)
    except Exception:
        return None, removed_ids

    res_dict = {}
    try:
        if resources is not None:
            res_dict = resources.get_object() if hasattr(resources, "get_object") else resources
            if not isinstance(res_dict, dict):
                res_dict = {}
    except Exception:
        res_dict = {}

    fonts_map: Dict[str, Tuple[int, List[float]]] = {}
    try:
        fdict = res_dict.get("/Font")
        if fdict is not None:
            fdict = fdict.get_object() if hasattr(fdict, "get_object") else fdict
            if isinstance(fdict, dict):
                for fk, fv in fdict.items():
                    fonts_map[str(fk)] = _get_font_widths(fv)
    except Exception:
        pass

    cm_stack: List[List[float]] = [list(initial_cm) if initial_cm else [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]]
    tm: List[float] = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    tlm: List[float] = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    leading: float = 0.0
    font_size: float = 12.0
    cur_font_key: str = ""
    tc: float = 0.0
    tw: float = 0.0
    tz: float = 100.0

    new_ops: List[Tuple[Any, bytes]] = []
    modified = False

    for operands, operator in cs.operations:
        try:
            if operator == b"q":
                cm_stack.append(cm_stack[-1][:])
                new_ops.append((operands, operator))
                continue
            if operator == b"Q":
                if len(cm_stack) > 1:
                    cm_stack.pop()
                new_ops.append((operands, operator))
                continue
            if operator == b"cm" and len(operands) >= 6:
                m = [float(v) for v in operands[:6]]
                cm_stack[-1] = _mm(m, cm_stack[-1])
                new_ops.append((operands, operator))
                continue
            if operator == b"BT":
                tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
                tlm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
                new_ops.append((operands, operator))
                continue
            if operator == b"Tm" and len(operands) >= 6:
                m = [float(v) for v in operands[:6]]
                tm = m[:]
                tlm = m[:]
                new_ops.append((operands, operator))
                continue
            if operator == b"Td" and len(operands) >= 2:
                tx, ty = float(operands[0]), float(operands[1])
                tlm = _mm([1.0, 0.0, 0.0, 1.0, tx, ty], tlm)
                tm = tlm[:]
                new_ops.append((operands, operator))
                continue
            if operator == b"TD" and len(operands) >= 2:
                tx, ty = float(operands[0]), float(operands[1])
                leading = -ty
                tlm = _mm([1.0, 0.0, 0.0, 1.0, tx, ty], tlm)
                tm = tlm[:]
                new_ops.append((operands, operator))
                continue
            if operator == b"TL" and len(operands) >= 1:
                leading = float(operands[0])
                new_ops.append((operands, operator))
                continue
            if operator == b"T*":
                tlm = _mm([1.0, 0.0, 0.0, 1.0, 0.0, -leading], tlm)
                tm = tlm[:]
                new_ops.append((operands, operator))
                continue
            if operator == b"Tf" and len(operands) >= 2:
                cur_font_key = str(operands[0])
                font_size = abs(float(operands[1]))
                new_ops.append((operands, operator))
                continue
            if operator == b"Tc" and len(operands) >= 1:
                tc = float(operands[0])
                new_ops.append((operands, operator))
                continue
            if operator == b"Tw" and len(operands) >= 1:
                tw = float(operands[0])
                new_ops.append((operands, operator))
                continue
            if operator == b"Tz" and len(operands) >= 1:
                tz = float(operands[0]) or 100.0
                new_ops.append((operands, operator))
                continue

            # Recurse into Form XObjects invoked by Do!
            if operator == b"Do" and len(operands) >= 1:
                xname = NameObject(str(operands[0]))
                xobjs = res_dict.get("/XObject")
                if xobjs is not None:
                    xobjs = xobjs.get_object() if hasattr(xobjs, "get_object") else xobjs
                    if isinstance(xobjs, dict) and xname in xobjs:
                        xobj = xobjs[xname].get_object()
                        if isinstance(xobj, dict) and str(xobj.get("/Subtype", "")) == "/Form":
                            xmat = [float(v) for v in xobj.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                            child_cm = _mm(xmat, cm_stack[-1])
                            child_res = xobj.get("/Resources", res_dict)
                            sub_bytes, sub_ids = _strip_text_ops_in_stream(
                                writer,
                                xobj,
                                child_res,
                                targets,
                                cropbox,
                                rotation,
                                initial_cm=child_cm,
                                depth=depth + 1,
                            )
                            if sub_bytes is not None:
                                new_xo = DecodedStreamObject()
                                for k, v in xobj.items():
                                    if str(k) not in ("/Length", "/Filter", "/DecodeParms"):
                                        new_xo[k] = v
                                new_xo.set_data(sub_bytes)
                                xobjs[xname] = writer._add_object(new_xo)
                                removed_ids.update(sub_ids)
                new_ops.append((operands, operator))
                continue

            first_ch, widths = fonts_map.get(cur_font_key, (0, []))

            if operator in (b"Tj", b"'", b'"') and len(operands) >= 1:
                if operator in (b"'", b'"'):
                    if operator == b'"' and len(operands) >= 3:
                        tw = float(operands[0])
                        tc = float(operands[1])
                        str_op = operands[2]
                    else:
                        str_op = operands[0]
                    tlm = _mm([1.0, 0.0, 0.0, 1.0, 0.0, -leading], tlm)
                    tm = tlm[:]
                else:
                    str_op = operands[0]

                adv = _string_advance_tx(str_op, first_ch, widths, font_size, tc, tw, tz)
                comb0 = _mm(tm, cm_stack[-1])
                tm_after = _mm([1.0, 0.0, 0.0, 1.0, adv, 0.0], tm)
                comb1 = _mm(tm_after, cm_stack[-1])
                eff_h = max(2.0, font_size * math.hypot(comb0[2], comb0[3]))

                vx0, vy0, _, vh0 = pdf_rect_to_visual(
                    [comb0[4], comb0[5], comb0[4] + 1.0, comb0[5] + eff_h], cropbox, rotation
                )
                vx1, vy1, _, _ = pdf_rect_to_visual(
                    [comb1[4], comb1[5], comb1[4] + 1.0, comb1[5] + eff_h], cropbox, rotation
                )
                tm = tm_after

                matched = _rect_overlaps_target(vx0, vy0, vx1, vy0 + vh0, targets)
                if matched is not None:
                    removed_ids.add(matched)
                    modified = True
                    if operator in (b"'", b'"'):
                        new_ops.append(([], b"T*"))
                    elif abs(adv) > 0.01:
                        # Advance text matrix cleanly via empty TJ kerning so subsequent Tj ops keep exact X!
                        kern = -(adv / max(0.01, font_size * (tz / 100.0))) * 1000.0
                        new_ops.append(([ArrayObject([FloatObject(kern)])], b"TJ"))
                    continue

            elif operator == b"TJ" and len(operands) >= 1 and isinstance(operands[0], list):
                arr = operands[0]
                new_arr = ArrayObject()
                any_removed_in_tj = False
                any_kept_string = False

                for elem in arr:
                    if isinstance(elem, (int, float, NumberObject, FloatObject)):
                        num = float(elem)
                        dx = -(num / 1000.0) * font_size * (tz / 100.0)
                        tm = _mm([1.0, 0.0, 0.0, 1.0, dx, 0.0], tm)
                        new_arr.append(elem)
                    else:
                        adv = _string_advance_tx(elem, first_ch, widths, font_size, tc, tw, tz)
                        comb0 = _mm(tm, cm_stack[-1])
                        tm_after = _mm([1.0, 0.0, 0.0, 1.0, adv, 0.0], tm)
                        comb1 = _mm(tm_after, cm_stack[-1])
                        eff_h = max(2.0, font_size * math.hypot(comb0[2], comb0[3]))
                        vx0, vy0, _, vh0 = pdf_rect_to_visual(
                            [comb0[4], comb0[5], comb0[4] + 1.0, comb0[5] + eff_h], cropbox, rotation
                        )
                        vx1, _, _, _ = pdf_rect_to_visual(
                            [comb1[4], comb1[5], comb1[4] + 1.0, comb1[5] + eff_h], cropbox, rotation
                        )
                        tm = tm_after

                        matched = _rect_overlaps_target(vx0, vy0, vx1, vy0 + vh0, targets)
                        if matched is not None:
                            removed_ids.add(matched)
                            any_removed_in_tj = True
                            modified = True
                            # Preserve horizontal cursor position for any untouched columns later in the same TJ!
                            kern = -(adv / max(0.01, font_size * (tz / 100.0))) * 1000.0
                            new_arr.append(FloatObject(kern))
                        else:
                            any_kept_string = True
                            new_arr.append(elem)

                if any_removed_in_tj:
                    if any_kept_string:
                        new_ops.append(([new_arr], b"TJ"))
                    continue

        except Exception:
            pass
        new_ops.append((operands, operator))

    if modified:
        cs.operations = new_ops
        if isinstance(stream_owner, pypdf.PageObject):
            stream_owner[NameObject("/Contents")] = writer._add_object(cs)
            return b"page_updated", removed_ids
        return cs.get_data(), removed_ids
    return None, removed_ids


def remove_replaced_text_from_page(
    writer: PdfWriter,
    page: pypdf.PageObject,
    replaced_items: Sequence[TextItem],
    cropbox: Tuple[float, float, float, float],
    rotation: int,
) -> set[str]:
    """Surgically remove original PDF text operators (top-level & Form XObjects) overlapping replaced TextItems."""
    targets: List[Tuple[str, float, float, float, float]] = []
    for it in replaced_items:
        if it.mask_rect and len(it.mask_rect) == 4:
            mx, my, mw, mh = [float(v) for v in it.mask_rect]
            targets.append((it.id, mx, my, mw, mh))
    if not targets:
        return set()

    _, removed_ids = _strip_text_ops_in_stream(
        writer,
        page,
        page.get("/Resources"),
        targets,
        cropbox,
        rotation,
        initial_cm=None,
        depth=0,
    )
    return removed_ids


def build_stripped_single_page_pdf(
    working_pdf_path: str,
    password: str,
    page_idx: int,
    replaced_items: Sequence[TextItem],
) -> Tuple[Optional[bytes], set[str]]:
    """Build a tiny 1-page PDF in memory with replaced native text stripped for live canvas preview."""
    if not replaced_items:
        return None, set()
    try:
        reader = open_reader(working_pdf_path, password)
        if page_idx >= len(reader.pages):
            return None, set()
        writer = PdfWriter()
        writer.add_page(reader.pages[page_idx])
        page = writer.pages[0]
        x0, y0, x1, y1, rot, _, _ = get_page_geometry(page)
        removed_ids = remove_replaced_text_from_page(
            writer, page, replaced_items, (x0, y0, x1, y1), rot
        )
        if not removed_ids:
            return None, set()
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue(), removed_ids
    except Exception:
        return None, set()


def _draw_overlay_item(
    c: rl_canvas.Canvas,
    item: BaseItem,
    vis_w: float,
    vis_h: float,
    flatten_forms: bool = False,
    skip_mask: bool = False,
) -> None:
    """Draw a single KinoFill item onto a visual-space ReportLab canvas."""
    c.saveState()
    try:
        if isinstance(item, WhiteoutItem):
            c.setFillColor(hex_to_rl_color(item.fill_color, item.opacity))
            c.setFillAlpha(item.opacity)
            has_border = bool(item.border_color)
            if has_border:
                c.setStrokeColor(hex_to_rl_color(item.border_color, item.opacity))
                c.setLineWidth(0.75)
            c.rect(item.x, vis_h - item.y - item.h, item.w, item.h, fill=1, stroke=1 if has_border else 0)

        elif isinstance(item, RedactItem):
            c.setFillColor(hex_to_rl_color(item.fill_color or "#000000", 1.0))
            c.setFillAlpha(1.0)
            c.rect(item.x, vis_h - item.y - item.h, item.w, item.h, fill=1, stroke=0)
            if item.label:
                c.setFillColor(hex_to_rl_color("#FFFFFF", 1.0))
                font_name = resolve_rl_font("Arial", bold=True)
                fs = max(7.0, min(11.0, item.h * 0.55))
                c.setFont(font_name, fs)
                c.drawCentredString(
                    item.x + item.w / 2.0,
                    vis_h - item.y - item.h / 2.0 - fs * 0.32,
                    item.label,
                )

        elif isinstance(item, HighlightItem):
            col = hex_to_rl_color(item.color, item.opacity)
            if item.style == "highlight":
                c.setFillColor(col)
                c.setFillAlpha(item.opacity)
                c.rect(item.x, vis_h - item.y - item.h, item.w, item.h, fill=1, stroke=0)
            elif item.style == "underline":
                c.setStrokeColor(hex_to_rl_color(item.color, 1.0))
                c.setStrokeAlpha(min(1.0, max(0.7, item.opacity)))
                c.setLineWidth(max(1.5, item.h * 0.12))
                y_line = vis_h - item.y - item.h + 1.5
                c.line(item.x, y_line, item.x + item.w, y_line)
            elif item.style == "strikeout":
                c.setStrokeColor(hex_to_rl_color(item.color, 1.0))
                c.setStrokeAlpha(min(1.0, max(0.7, item.opacity)))
                c.setLineWidth(max(1.5, item.h * 0.12))
                y_line = vis_h - item.y - item.h / 2.0
                c.line(item.x, y_line, item.x + item.w, y_line)

        elif isinstance(item, ShapeItem):
            has_fill = bool(item.fill_color)
            has_stroke = bool(item.stroke_color) and item.stroke_width > 0
            if has_fill:
                c.setFillColor(hex_to_rl_color(item.fill_color, item.opacity))
                c.setFillAlpha(item.opacity)
            if has_stroke:
                c.setStrokeColor(hex_to_rl_color(item.stroke_color, item.opacity))
                c.setStrokeAlpha(item.opacity)
                c.setLineWidth(item.stroke_width)
                c.setLineCap(1)
                c.setLineJoin(1)

            if item.shape_type == "rect":
                c.rect(item.x, vis_h - item.y - item.h, item.w, item.h, fill=int(has_fill), stroke=int(has_stroke))
            elif item.shape_type == "roundrect":
                radius = min(10.0, item.w * 0.2, item.h * 0.2)
                c.roundRect(
                    item.x,
                    vis_h - item.y - item.h,
                    item.w,
                    item.h,
                    radius,
                    fill=int(has_fill),
                    stroke=int(has_stroke),
                )
            elif item.shape_type == "ellipse":
                c.ellipse(
                    item.x,
                    vis_h - item.y - item.h,
                    item.x + item.w,
                    vis_h - item.y,
                    fill=int(has_fill),
                    stroke=int(has_stroke),
                )
            elif item.shape_type in ("line", "arrow"):
                x1_p, y1_p = item.x, vis_h - item.y
                x2_p, y2_p = item.x2, vis_h - item.y2
                c.line(x1_p, y1_p, x2_p, y2_p)
                if item.shape_type == "arrow":
                    angle = math.atan2(y2_p - y1_p, x2_p - x1_p)
                    head_len = max(9.0, item.stroke_width * 4.2)
                    a1 = angle + math.radians(152)
                    a2 = angle - math.radians(152)
                    p = c.beginPath()
                    p.moveTo(x2_p, y2_p)
                    p.lineTo(x2_p + head_len * math.cos(a1), y2_p + head_len * math.sin(a1))
                    p.moveTo(x2_p, y2_p)
                    p.lineTo(x2_p + head_len * math.cos(a2), y2_p + head_len * math.sin(a2))
                    c.drawPath(p, stroke=1, fill=0)

        elif isinstance(item, InkItem):
            if len(item.points) >= 2:
                c.setStrokeColor(hex_to_rl_color(item.color, item.opacity))
                c.setStrokeAlpha(item.opacity)
                c.setLineWidth(item.stroke_width)
                c.setLineCap(1)
                c.setLineJoin(1)
                p = c.beginPath()
                p.moveTo(item.points[0][0], vis_h - item.points[0][1])
                for pt in item.points[1:]:
                    p.lineTo(pt[0], vis_h - pt[1])
                c.drawPath(p, stroke=1, fill=0)

        elif isinstance(item, ImageItem):
            if item.image_b64:
                raw = base64.b64decode(item.image_b64)
                img = Image.open(io.BytesIO(raw)).convert("RGBA")
                if item.opacity < 0.99:
                    alpha_ch = img.split()[3].point(lambda a: int(a * item.opacity))
                    img.putalpha(alpha_ch)
                c.drawImage(
                    ImageReader(img),
                    item.x,
                    vis_h - item.y - item.h,
                    width=item.w,
                    height=item.h,
                    mask="auto",
                    preserveAspectRatio=False,
                )

        elif isinstance(item, StampItem):
            cx = item.x + item.w / 2.0
            cy = vis_h - item.y - item.h / 2.0
            c.translate(cx, cy)
            if item.rotation:
                c.rotate(-item.rotation)
            c.setStrokeColor(hex_to_rl_color(item.color, item.opacity))
            c.setFillColor(hex_to_rl_color(item.color, item.opacity))
            c.setFillAlpha(item.opacity)
            c.setStrokeAlpha(item.opacity)

            hw, hh = item.w / 2.0, item.h / 2.0
            if item.stamp_type == "check":
                c.setLineWidth(max(1.8, min(item.w, item.h) * 0.13))
                c.setLineCap(1)
                c.setLineJoin(1)
                p = c.beginPath()
                p.moveTo(-hw * 0.72, 0.0)
                p.lineTo(-hw * 0.15, -hh * 0.62)
                p.lineTo(hw * 0.76, hh * 0.62)
                c.drawPath(p, stroke=1, fill=0)
            elif item.stamp_type == "cross":
                c.setLineWidth(max(1.8, min(item.w, item.h) * 0.13))
                c.setLineCap(1)
                c.line(-hw * 0.65, -hh * 0.65, hw * 0.65, hh * 0.65)
                c.line(-hw * 0.65, hh * 0.65, hw * 0.65, -hh * 0.65)
            elif item.stamp_type == "dot":
                r = min(hw, hh) * 0.55
                c.circle(0, 0, r, fill=1, stroke=0)
            elif item.stamp_type == "circle":
                c.setLineWidth(max(1.6, min(item.w, item.h) * 0.1))
                c.ellipse(-hw * 0.85, -hh * 0.85, hw * 0.85, hh * 0.85, fill=0, stroke=1)
            elif item.stamp_type == "date":
                font_name = resolve_rl_font("Arial", bold=False)
                fs = max(8.0, min(18.0, item.h * 0.65))
                c.setFont(font_name, fs)
                c.drawCentredString(0, -fs * 0.34, item.text)
            elif item.stamp_type == "rubber":
                if item.border:
                    c.setLineWidth(2.2)
                    c.roundRect(-hw + 1.5, -hh + 1.5, item.w - 3, item.h - 3, 4.0, stroke=1, fill=0)
                font_name = resolve_rl_font("Arial", bold=True)
                fs = max(9.0, min(28.0, item.h * 0.52))
                # Shrink to fit width
                tw = pdfmetrics.stringWidth(item.text, font_name, fs)
                if tw > item.w - 12 and tw > 0:
                    fs = fs * ((item.w - 12) / tw)
                c.setFont(font_name, fs)
                c.drawCentredString(0, -fs * 0.35, item.text)

        elif isinstance(item, TextItem):
            # Only draw fallback background mask if original PDF text couldn't be stripped from ContentStream
            # (e.g., flat scanned/image-only PDF). Keep mask tight with ZERO vertical bleed into form underlines!
            if not skip_mask and item.mask_rect and len(item.mask_rect) == 4:
                mx, my, mw, mh = [float(v) for v in item.mask_rect]
                c.setFillColor(hex_to_rl_color(item.mask_color or "#FFFFFF", 1.0))
                c.setFillAlpha(1.0)
                c.rect(mx, vis_h - (my + mh), mw, mh, fill=1, stroke=0)

            if item.bg_color:
                c.setFillColor(hex_to_rl_color(item.bg_color, item.bg_opacity))
                c.setFillAlpha(item.bg_opacity)
                c.rect(item.x, vis_h - item.y - item.h, item.w, item.h, fill=1, stroke=0)

            if item.text:
                font_name = resolve_rl_font(item.font_family, item.bold, item.italic)
                c.setFont(font_name, item.font_size)
                c.setFillColor(hex_to_rl_color(item.color, item.opacity))
                c.setFillAlpha(item.opacity)
                pad_x = 0.5 if item.source_block_id else 2.0
                pad_y = 0.0 if item.source_block_id else 2.0
                line_h = item.font_size * 1.24
                lines = _wrap_text_lines(item.text, font_name, item.font_size, item.w - pad_x * 2)
                y_cursor = vis_h - item.y - pad_y - item.font_size * 0.92
                for line in lines:
                    if item.align == "center":
                        c.drawCentredString(item.x + item.w / 2.0, y_cursor, line)
                    elif item.align == "right":
                        c.drawRightString(item.x + item.w - pad_x, y_cursor, line)
                    else:
                        c.drawString(item.x + pad_x, y_cursor, line)
                    y_cursor -= line_h

        elif isinstance(item, NoteItem):
            # Draw sticky note badge on page
            c.setFillColor(hex_to_rl_color(item.color or "#FEF08A", 0.95))
            c.setStrokeColor(hex_to_rl_color("#CA8A04", 1.0))
            c.setLineWidth(1.0)
            c.roundRect(item.x, vis_h - item.y - item.h, item.w, item.h, 3, fill=1, stroke=1)
            c.setStrokeColor(hex_to_rl_color("#854D0E", 1.0))
            c.setLineWidth(0.8)
            for frac in (0.35, 0.55, 0.72):
                ly = vis_h - item.y - item.h * frac
                c.line(item.x + 4, ly, item.x + item.w - 4, ly)

        elif isinstance(item, FormFieldItem) and flatten_forms:
            if item.field_type in ("text", "dropdown") and item.value:
                font_name = resolve_rl_font("Arial", False, False)
                fs = item.font_size
                c.setFont(font_name, fs)
                c.setFillColor(hex_to_rl_color("#111827", 1.0))
                if item.multiline:
                    lines = _wrap_text_lines(item.value, font_name, fs, item.w - 6)
                    y_cur = vis_h - item.y - 3 - fs * 0.88
                    for line in lines:
                        c.drawString(item.x + 3, y_cur, line)
                        y_cur -= fs * 1.22
                else:
                    y_base = vis_h - item.y - (item.h + fs * 0.72) / 2.0
                    c.drawString(item.x + 3, y_base, item.value)
            elif item.field_type in ("checkbox", "radio") and item.checked:
                c.setStrokeColor(hex_to_rl_color("#111827", 1.0))
                c.setFillColor(hex_to_rl_color("#111827", 1.0))
                cx = item.x + item.w / 2.0
                cy = vis_h - item.y - item.h / 2.0
                if item.field_type == "radio":
                    c.circle(cx, cy, min(item.w, item.h) * 0.3, fill=1, stroke=0)
                else:
                    c.setLineWidth(max(1.5, min(item.w, item.h) * 0.14))
                    c.setLineCap(1)
                    c.setLineJoin(1)
                    hw, hh = item.w * 0.32, item.h * 0.32
                    p = c.beginPath()
                    p.moveTo(cx - hw, cy)
                    p.lineTo(cx - hw * 0.2, cy - hh * 0.8)
                    p.lineTo(cx + hw, cy + hh * 0.8)
                    c.drawPath(p, stroke=1, fill=0)
    finally:
        c.restoreState()


def _draw_watermark(c: rl_canvas.Canvas, wm: WatermarkConfig, vis_w: float, vis_h: float) -> None:
    if not wm.enabled or not wm.text:
        return
    c.saveState()
    c.translate(vis_w / 2.0, vis_h / 2.0)
    c.rotate(wm.angle)
    font_name = resolve_rl_font("Arial", bold=True)
    c.setFont(font_name, wm.font_size)
    c.setFillColor(hex_to_rl_color(wm.color, wm.opacity))
    c.setFillAlpha(wm.opacity)
    c.drawCentredString(0, -wm.font_size * 0.35, wm.text)
    c.restoreState()


def _draw_header_footer(
    c: rl_canvas.Canvas,
    hf: HeaderFooterConfig,
    vis_w: float,
    vis_h: float,
    page_idx: int,
    total_pages: int,
) -> None:
    if not hf.enabled:
        return
    if (page_idx + 1) < hf.start_page:
        return
    c.saveState()
    font_name = resolve_rl_font("Arial", False, False)
    c.setFont(font_name, hf.font_size)
    c.setFillColor(hex_to_rl_color(hf.color, 1.0))

    def fmt(tpl: str) -> str:
        return (
            (tpl or "")
            .replace("{page}", str(page_idx + 1))
            .replace("{total}", str(total_pages))
        )

    m = hf.margin
    top_y = vis_h - m
    bot_y = m - hf.font_size * 0.4

    if hf.header_left:
        c.drawString(m, top_y, fmt(hf.header_left))
    if hf.header_center:
        c.drawCentredString(vis_w / 2.0, top_y, fmt(hf.header_center))
    if hf.header_right:
        c.drawRightString(vis_w - m, top_y, fmt(hf.header_right))
    if hf.footer_left:
        c.drawString(m, bot_y, fmt(hf.footer_left))
    if hf.footer_center:
        c.drawCentredString(vis_w / 2.0, bot_y, fmt(hf.footer_center))
    if hf.footer_right:
        c.drawRightString(vis_w - m, bot_y, fmt(hf.footer_right))
    c.restoreState()


def _add_new_acroform_widget(
    writer: PdfWriter,
    page: pypdf.PageObject,
    field: FormFieldItem,
    cropbox: Tuple[float, float, float, float],
    rotation: int,
) -> None:
    """Create a real interactive PDF AcroForm /Widget annotation on page."""
    rect = visual_rect_to_pdf(field.x, field.y, field.w, field.h, cropbox, rotation)
    widget = DictionaryObject()
    widget[NameObject("/Type")] = NameObject("/Annot")
    widget[NameObject("/Subtype")] = NameObject("/Widget")
    widget[NameObject("/Rect")] = ArrayObject([FloatObject(v) for v in rect])
    widget[NameObject("/F")] = NumberObject(4)  # Print flag
    widget[NameObject("/T")] = TextStringObject(field.field_name or f"Field_{field.id}")
    widget[NameObject("/MK")] = DictionaryObject(
        {
            NameObject("/BC"): ArrayObject([FloatObject(0.25), FloatObject(0.35), FloatObject(0.55)]),
            NameObject("/BG"): ArrayObject([FloatObject(0.96), FloatObject(0.98), FloatObject(1.0)]),
        }
    )

    if field.field_type == "text":
        widget[NameObject("/FT")] = NameObject("/Tx")
        widget[NameObject("/V")] = TextStringObject(field.value or "")
        widget[NameObject("/DA")] = TextStringObject(f"/Helv {field.font_size:.1f} Tf 0 0 0 rg")
        if field.multiline:
            widget[NameObject("/Ff")] = NumberObject(1 << 12)
    elif field.field_type == "checkbox":
        widget[NameObject("/FT")] = NameObject("/Btn")
        state = NameObject("/Yes" if field.checked else "/Off")
        widget[NameObject("/V")] = state
        widget[NameObject("/AS")] = state
    elif field.field_type == "dropdown":
        widget[NameObject("/FT")] = NameObject("/Ch")
        widget[NameObject("/Ff")] = NumberObject(1 << 17)  # Combo box
        opts = ArrayObject([TextStringObject(o) for o in (field.options or ["Option 1", "Option 2"])])
        widget[NameObject("/Opt")] = opts
        widget[NameObject("/V")] = TextStringObject(field.value or (field.options[0] if field.options else ""))
        widget[NameObject("/DA")] = TextStringObject(f"/Helv {field.font_size:.1f} Tf 0 0 0 rg")

    widget_ref = writer._add_object(widget)
    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    annots_obj = page["/Annots"].get_object()
    annots_obj.append(widget_ref)

    root = writer._root_object
    if "/AcroForm" not in root:
        acro = DictionaryObject(
            {
                NameObject("/Fields"): ArrayObject(),
                NameObject("/NeedAppearances"): BooleanObject(True),
            }
        )
        root[NameObject("/AcroForm")] = writer._add_object(acro)
    acro_obj = root["/AcroForm"].get_object()
    if "/Fields" not in acro_obj:
        acro_obj[NameObject("/Fields")] = ArrayObject()
    acro_obj["/Fields"].get_object().append(widget_ref)
    acro_obj[NameObject("/NeedAppearances")] = BooleanObject(True)


def _add_pdf_text_note_annotation(
    writer: PdfWriter,
    page: pypdf.PageObject,
    note: NoteItem,
    cropbox: Tuple[float, float, float, float],
    rotation: int,
) -> None:
    """Also embed a native PDF /Text popup annotation so standard viewers show the note text."""
    rect = visual_rect_to_pdf(note.x, note.y, note.w, note.h, cropbox, rotation)
    annot = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Text"),
            NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
            NameObject("/Contents"): TextStringObject(note.text or ""),
            NameObject("/T"): TextStringObject(note.author or "User"),
            NameObject("/Name"): NameObject("/Comment"),
            NameObject("/C"): ArrayObject([FloatObject(1.0), FloatObject(0.92), FloatObject(0.35)]),
            NameObject("/Open"): BooleanObject(False),
        }
    )
    ref = writer._add_object(annot)
    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    page["/Annots"].get_object().append(ref)


def _rasterize_redacted_page(
    working_pdf_path: str,
    password: str,
    page_idx: int,
    vis_w: float,
    vis_h: float,
    redact_items: List[RedactItem],
    whiteout_items: List[WhiteoutItem],
    dpi: int = 200,
) -> Optional[pypdf.PageObject]:
    """Burn blackout boxes irreversibly into page pixels via QPdfDocument."""
    try:
        from PySide6.QtCore import QRectF, QSize
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtPdf import QPdfDocument
    except Exception:
        return None

    doc = QPdfDocument()
    if password:
        doc.setPassword(password)
    if doc.load(working_pdf_path) != QPdfDocument.Error.None_:
        return None
    if page_idx >= doc.pageCount():
        return None

    scale = dpi / 72.0
    px_w = max(1, int(round(vis_w * scale)))
    px_h = max(1, int(round(vis_h * scale)))
    img = doc.render(page_idx, QSize(px_w, px_h))
    if img.isNull():
        return None

    # Ensure white background behind transparent areas
    out_img = QImage(px_w, px_h, QImage.Format.Format_RGB32)
    out_img.fill(QColor("#FFFFFF"))
    painter = QPainter(out_img)
    painter.drawImage(0, 0, img)

    for wo in whiteout_items:
        painter.fillRect(
            QRectF(wo.x * scale, wo.y * scale, wo.w * scale, wo.h * scale),
            QColor(wo.fill_color or "#FFFFFF"),
        )
    for red in redact_items:
        painter.fillRect(
            QRectF(red.x * scale, red.y * scale, red.w * scale, red.h * scale),
            QColor(red.fill_color or "#000000"),
        )
    painter.end()
    doc.close()

    # Convert QImage -> PNG bytes -> ReportLab single-page PDF
    from PySide6.QtCore import QBuffer, QIODevice

    qbuf = QBuffer()
    qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
    out_img.save(qbuf, "JPEG", 94)
    jpg_bytes = bytes(qbuf.data())
    qbuf.close()

    pdf_buf = io.BytesIO()
    c = rl_canvas.Canvas(pdf_buf, pagesize=(vis_w, vis_h))
    c.drawImage(ImageReader(io.BytesIO(jpg_bytes)), 0, 0, width=vis_w, height=vis_h)
    c.save()
    pdf_buf.seek(0)
    return PdfReader(pdf_buf).pages[0]


def save_edited_pdf(
    state: DocumentState,
    output_path: str,
    security: Optional[SecurityConfig] = None,
) -> None:
    """Save the working PDF with all annotations, form values, watermarks, redactions, metadata & security."""
    sec = security or state.security
    reader = open_reader(state.working_pdf_path, state.password)
    writer = PdfWriter()
    writer.append(reader)

    total_pages = len(writer.pages)
    wm_pages = set(parse_page_range(state.watermark.page_range, total_pages)) if state.watermark.enabled else set()

    for page_idx in range(total_pages):
        page = writer.pages[page_idx]
        x0, y0, x1, y1, rot, vis_w, vis_h = get_page_geometry(page)
        cropbox = (x0, y0, x1, y1)
        page_items = state.items_on_page(page_idx)

        redact_items = [it for it in page_items if isinstance(it, RedactItem)]
        whiteout_items = [it for it in page_items if isinstance(it, WhiteoutItem)]
        existing_forms = [it for it in page_items if isinstance(it, FormFieldItem) and it.is_existing]
        new_forms = [it for it in page_items if isinstance(it, FormFieldItem) and not it.is_existing]
        note_items = [it for it in page_items if isinstance(it, NoteItem)]

        did_raster_redact = False
        if redact_items and sec.true_redact:
            raster_page = _rasterize_redacted_page(
                state.working_pdf_path,
                state.password,
                page_idx,
                vis_w,
                vis_h,
                redact_items,
                whiteout_items,
            )
            if raster_page is not None:
                # Replace page with rasterized, un-rotated page of exact visual size
                writer.insert_page(raster_page, index=page_idx)
                writer.remove_page(page_idx + 1)
                page = writer.pages[page_idx]
                x0, y0, x1, y1, rot, vis_w, vis_h = get_page_geometry(page)
                cropbox = (x0, y0, x1, y1)
                did_raster_redact = True

        # Update existing AcroForm values if not flattening (and not rasterized)
        if existing_forms and not sec.flatten_forms and not did_raster_redact:
            update_map: Dict[str, Any] = {}
            for ff in existing_forms:
                if ff.field_type in ("text", "dropdown"):
                    update_map[ff.field_name] = ff.value
                elif ff.field_type in ("checkbox", "radio"):
                    update_map[ff.field_name] = ff.checked_value if ff.checked else "/Off"
            try:
                writer.update_page_form_field_values(page, update_map, auto_regenerate=False)
            except Exception:
                pass
            if "/AcroForm" in writer._root_object:
                writer._root_object["/AcroForm"].get_object()[NameObject("/NeedAppearances")] = BooleanObject(True)

        # Strip widget annotations if flattening forms
        if sec.flatten_forms and "/Annots" in page:
            try:
                annots = page["/Annots"].get_object()
                kept = ArrayObject()
                for ref in annots:
                    a = ref.get_object()
                    if isinstance(a, dict) and str(a.get("/Subtype", "")) == "/Widget":
                        continue
                    kept.append(ref)
                page[NameObject("/Annots")] = kept
            except Exception:
                pass

        # Surgically strip replaced native PDF text operators from the page ContentStream
        # so the old text is truly gone (not hidden behind a white box!)
        replaced_text_items = [
            it for it in page_items if isinstance(it, TextItem) and it.mask_rect and not did_raster_redact
        ]
        stream_removed_ids: set[str] = set()
        if replaced_text_items:
            stream_removed_ids = remove_replaced_text_from_page(
                writer, page, replaced_text_items, cropbox, rot
            )

        # Render vector overlay if there is anything to draw
        items_to_draw = [
            it
            for it in page_items
            if not (did_raster_redact and isinstance(it, (RedactItem, WhiteoutItem)))
            and (sec.flatten_forms or not isinstance(it, FormFieldItem))
        ]
        needs_overlay = bool(items_to_draw) or (page_idx in wm_pages) or state.header_footer.enabled

        if needs_overlay:
            ov_buf = io.BytesIO()
            c = rl_canvas.Canvas(ov_buf, pagesize=(vis_w, vis_h))
            for it in items_to_draw:
                _draw_overlay_item(
                    c,
                    it,
                    vis_w,
                    vis_h,
                    flatten_forms=sec.flatten_forms,
                    skip_mask=(it.id in stream_removed_ids),
                )
            if page_idx in wm_pages:
                _draw_watermark(c, state.watermark, vis_w, vis_h)
            if state.header_footer.enabled:
                _draw_header_footer(c, state.header_footer, vis_w, vis_h, page_idx, total_pages)
            c.save()
            ov_buf.seek(0)
            ov_page = PdfReader(ov_buf).pages[0]
            tx = overlay_transform_for_page(cropbox, rot)
            page.merge_transformed_page(ov_page, tx)

        # Add brand-new AcroForm widgets if not flattening
        if new_forms and not sec.flatten_forms:
            for nf in new_forms:
                _add_new_acroform_widget(writer, page, nf, cropbox, rot)

        # Add native popup annotations for sticky notes
        for note in note_items:
            _add_pdf_text_note_annotation(writer, page, note, cropbox, rot)

    # Metadata
    meta_dict: Dict[str, str] = {}
    if state.metadata.title:
        meta_dict["/Title"] = state.metadata.title
    if state.metadata.author:
        meta_dict["/Author"] = state.metadata.author
    if state.metadata.subject:
        meta_dict["/Subject"] = state.metadata.subject
    if state.metadata.keywords:
        meta_dict["/Keywords"] = state.metadata.keywords
    meta_dict["/Creator"] = state.metadata.creator or "KinoFill"
    writer.add_metadata(meta_dict)

    # Encryption
    if sec.encrypt and (sec.user_password or sec.owner_password):
        try:
            writer.encrypt(
                user_password=sec.user_password,
                owner_password=sec.owner_password or sec.user_password,
                algorithm="AES-256",
            )
        except Exception:
            writer.encrypt(
                user_password=sec.user_password,
                owner_password=sec.owner_password or sec.user_password,
                algorithm="RC4-128",
            )

    # Write atomically via temp file in same directory to allow saving over source file!
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".lf_save_", suffix=".pdf", dir=str(out_path.parent))
    os.close(fd)
    try:
        with open(tmp_name, "wb") as f:
            writer.write(f)
        os.replace(tmp_name, str(out_path))
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Document & Page Utilities
# ---------------------------------------------------------------------------

PAGE_PRESETS: Dict[str, Tuple[float, float]] = {
    "Letter (8.5 x 11 in)": (612.0, 792.0),
    "A4 (210 x 297 mm)": (595.28, 841.89),
    "Legal (8.5 x 14 in)": (612.0, 1008.0),
    "Tabloid (11 x 17 in)": (792.0, 1224.0),
    "A5 (148 x 210 mm)": (419.53, 595.28),
}


def create_blank_pdf(
    output_path: str,
    width: float = 612.0,
    height: float = 792.0,
    page_count: int = 1,
) -> str:
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(width, height))
    for _ in range(max(1, page_count)):
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, width, height, fill=1, stroke=0)
        c.showPage()
    c.save()
    with open(output_path, "wb") as f:
        f.write(buf.getvalue())
    return output_path


def merge_pdfs(input_paths: Sequence[str], output_path: str) -> str:
    writer = PdfWriter()
    for p in input_paths:
        reader = PdfReader(p)
        writer.append(reader)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path


def split_pdf(
    input_path: str,
    output_dir_or_file: str,
    page_range: str = "all",
    burst: bool = False,
    password: str = "",
) -> List[str]:
    reader = open_reader(input_path, password)
    total = len(reader.pages)
    indices = parse_page_range(page_range, total)
    if not indices:
        raise ValueError("No valid pages matched the specified page range.")

    created: List[str] = []
    if burst:
        out_dir = Path(output_dir_or_file)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(input_path).stem
        for idx in indices:
            w = PdfWriter()
            w.add_page(reader.pages[idx])
            out_file = out_dir / f"{stem}_page_{idx + 1}.pdf"
            with open(out_file, "wb") as f:
                w.write(f)
            created.append(str(out_file))
    else:
        w = PdfWriter()
        for idx in indices:
            w.add_page(reader.pages[idx])
        with open(output_dir_or_file, "wb") as f:
            w.write(f)
        created.append(output_dir_or_file)
    return created


def images_to_pdf(image_paths: Sequence[str], output_path: str) -> str:
    if not image_paths:
        raise ValueError("No images selected.")
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf)
    for img_path in image_paths:
        img = Image.open(img_path)
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])
            else:
                bg.paste(img.convert("RGB"))
            img = bg
        else:
            img = img.convert("RGB")
        dpi_x, dpi_y = img.info.get("dpi", (96, 96))
        dpi_x = dpi_x if dpi_x and dpi_x > 20 else 96
        dpi_y = dpi_y if dpi_y and dpi_y > 20 else 96
        pw = img.width * 72.0 / dpi_x
        ph = img.height * 72.0 / dpi_y
        # Cap giant photos gently to standard page bounds while preserving ratio
        max_dim = 1224.0
        if max(pw, ph) > max_dim:
            ratio = max_dim / max(pw, ph)
            pw *= ratio
            ph *= ratio
        c.setPageSize((pw, ph))
        c.drawImage(ImageReader(img), 0, 0, width=pw, height=ph)
        c.showPage()
    c.save()
    with open(output_path, "wb") as f:
        f.write(buf.getvalue())
    return output_path


def export_pdf_to_images(
    pdf_path: str,
    output_dir: str,
    fmt: str = "PNG",
    dpi: int = 200,
    page_range: str = "all",
    password: str = "",
) -> List[str]:
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    if password:
        doc.setPassword(password)
    if doc.load(pdf_path) != QPdfDocument.Error.None_:
        raise RuntimeError("Could not open PDF for image export.")
    total = doc.pageCount()
    indices = parse_page_range(page_range, total)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(pdf_path).stem
    ext = "jpg" if fmt.upper() in ("JPG", "JPEG") else "png"
    created: List[str] = []

    scale = dpi / 72.0
    for idx in indices:
        pt_size = doc.pagePointSize(idx)
        w = max(1, int(round(pt_size.width() * scale)))
        h = max(1, int(round(pt_size.height() * scale)))
        rendered = doc.render(idx, QSize(w, h))
        canvas_img = QImage(w, h, QImage.Format.Format_RGB32)
        canvas_img.fill(QColor("#FFFFFF"))
        p = QPainter(canvas_img)
        p.drawImage(0, 0, rendered)
        p.end()
        out_file = out_dir / f"{stem}_page_{idx + 1}.{ext}"
        canvas_img.save(str(out_file), "JPEG" if ext == "jpg" else "PNG", 95)
        created.append(str(out_file))

    doc.close()
    return created


def mutate_pdf_pages(
    working_pdf_path: str,
    password: str,
    op: str,
    page_idx: int = 0,
    target_idx: int = 0,
    angle: int = 90,
    extra_pdf_path: str = "",
    blank_size: Tuple[float, float] = (612.0, 792.0),
) -> Tuple[str, Dict[int, int]]:
    """Perform a structural page mutation on a new working temp PDF.

    Returns (new_working_pdf_path, old_to_new_page_map).
    """
    reader = open_reader(working_pdf_path, password)
    total = len(reader.pages)
    writer = PdfWriter()
    old_to_new: Dict[int, int] = {}

    if op == "rotate":
        for i in range(total):
            p = writer.add_page(reader.pages[i])
            if i == page_idx:
                p.rotate(angle)
            old_to_new[i] = i

    elif op == "delete":
        if total <= 1:
            raise ValueError("Cannot delete the only page in the document.")
        new_i = 0
        for i in range(total):
            if i == page_idx:
                continue
            writer.add_page(reader.pages[i])
            old_to_new[i] = new_i
            new_i += 1

    elif op == "duplicate":
        new_i = 0
        for i in range(total):
            writer.add_page(reader.pages[i])
            old_to_new[i] = new_i
            new_i += 1
            if i == page_idx:
                writer.add_page(reader.pages[i])
                new_i += 1

    elif op == "move":
        order = list(range(total))
        val = order.pop(page_idx)
        target_idx = max(0, min(len(order), target_idx))
        order.insert(target_idx, val)
        for new_i, old_i in enumerate(order):
            writer.add_page(reader.pages[old_i])
            old_to_new[old_i] = new_i

    elif op == "insert_blank":
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=blank_size)
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, blank_size[0], blank_size[1], fill=1, stroke=0)
        c.showPage()
        c.save()
        buf.seek(0)
        blank_page = PdfReader(buf).pages[0]

        insert_pos = max(0, min(total, page_idx))
        new_i = 0
        for i in range(total + 1):
            if i == insert_pos:
                writer.add_page(blank_page)
                new_i += 1
            if i < total:
                writer.add_page(reader.pages[i])
                old_to_new[i] = new_i
                new_i += 1

    elif op == "insert_pdf":
        extra_reader = PdfReader(extra_pdf_path)
        insert_pos = max(0, min(total, page_idx))
        new_i = 0
        for i in range(total + 1):
            if i == insert_pos:
                for ep in extra_reader.pages:
                    writer.add_page(ep)
                    new_i += 1
            if i < total:
                writer.add_page(reader.pages[i])
                old_to_new[i] = new_i
                new_i += 1
    else:
        raise ValueError(f"Unknown page op: {op}")

    fd, new_path = tempfile.mkstemp(prefix="kinofill_work_", suffix=".pdf")
    os.close(fd)
    with open(new_path, "wb") as f:
        writer.write(f)
    return new_path, old_to_new


def clean_signature_image(img: Image.Image, threshold: int = 215, remove_bg: bool = True) -> Image.Image:
    """Convert uploaded signature photo into crisp transparent ink PNG and trim whitespace."""
    rgba = img.convert("RGBA")
    if remove_bg:
        px = rgba.load()
        w, h = rgba.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                lum = int(0.299 * r + 0.587 * g + 0.114 * b)
                if lum >= threshold:
                    px[x, y] = (r, g, b, 0)
                elif lum >= threshold - 35:
                    # Soft anti-aliased edge
                    fade = int(a * (threshold - lum) / 35.0)
                    px[x, y] = (r, g, b, max(0, min(255, fade)))
    bbox = rgba.getbbox()
    if bbox:
        pad = 6
        x0 = max(0, bbox[0] - pad)
        y0 = max(0, bbox[1] - pad)
        x1 = min(rgba.width, bbox[2] + pad)
        y1 = min(rgba.height, bbox[3] + pad)
        rgba = rgba.crop((x0, y0, x1, y1))
    return rgba


def image_to_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
