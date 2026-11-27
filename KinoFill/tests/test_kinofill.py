"""End-to-end automated tests + offscreen Qt UI smoke & screenshot check for KinoFill (KinoSuite)."""

from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PIL import Image, ImageDraw
from pypdf import PdfReader
from reportlab.pdfgen import canvas as rl_canvas

from kinofill import APP_NAME, SUITE_NAME
from kinofill.models import (
    DocumentState,
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
)
from kinofill.pdf_engine import (
    clean_signature_image,
    create_blank_pdf,
    export_pdf_to_images,
    extract_acroform_fields,
    image_to_png_b64,
    images_to_pdf,
    merge_pdfs,
    mutate_pdf_pages,
    pdf_rect_to_visual,
    save_edited_pdf,
    split_pdf,
    visual_rect_to_pdf,
)


def make_sample_pdf(path: str) -> None:
    """Create a realistic 2-page PDF with shaded banner, multi-column text, and AcroForm fields."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(612, 792))

    # Colored shaded header banner (tests that true ContentStream replacement does NOT draw a white box!)
    c.setFillColorRGB(0.84, 0.91, 1.0)
    c.rect(40, 718, 532, 42, fill=1, stroke=0)

    c.setFillColorRGB(0.08, 0.22, 0.65)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(56, 732, "OLD HEADER TITLE")

    c.setFillColorRGB(0.08, 0.08, 0.08)
    c.setFont("Helvetica", 11)
    c.drawString(56, 694, "Please complete all fields below and sign at the bottom of Page 1.")

    c.setFont("Times-Italic", 11)
    c.setFillColorRGB(0.55, 0.1, 0.1)
    c.drawString(56, 668, "Bill To: Jane Smith")
    c.drawString(360, 668, "Date: Nov 26, 2026")

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 11)
    c.drawString(56, 628, "Full Name:")
    c.drawString(56, 588, "Department:")
    c.drawString(56, 548, "Agree to Terms:")
    c.drawString(56, 502, "Confidential Account SSN: 123-45-6789")

    # Official form thin underline ONLY 1.5pt below baseline (would be chopped by any opaque box!)
    c.setStrokeColorRGB(0.05, 0.05, 0.05)
    c.setLineWidth(1.0)
    c.line(56, 460.5, 420, 460.5)
    c.drawString(56, 462, "Legacy Clause v1 to be altered directly in place.")

    # Form XObject with blue grid line right underneath text (tests recursive Do XObject stripping!)
    c.beginForm("OfficialXObj")
    c.setStrokeColorRGB(0.0, 0.25, 0.85)
    c.setLineWidth(1.0)
    c.line(56, 418.5, 420, 418.5)
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.setFont("Helvetica", 11)
    c.drawString(56, 420, "XObject Official Entry Line")
    c.endForm()
    c.doForm("OfficialXObj")

    c.drawString(56, 200, "Authorized Signature: ___________________________")

    af = c.acroForm
    af.textfield(name="FullName", x=150, y=618, width=260, height=24, value="", borderWidth=1)
    af.choice(name="Department", x=150, y=578, width=180, height=24, options=["Engineering", "Finance", "Legal", "Operations"], value="Engineering")
    af.checkbox(name="AgreeTerms", x=160, y=542, size=18, checked=False, buttonStyle="check")

    c.showPage()
    c.setFont("Helvetica-Bold", 16)
    c.drawString(56, 736, "Page 2 - Appendix")
    c.setFont("Helvetica", 11)
    c.drawString(56, 700, "Searchable keyword: KINOFILL_VERIFIED_TOKEN")
    c.save()

    with open(path, "wb") as f:
        f.write(buf.getvalue())


def test_coordinate_roundtrip_all_rotations() -> None:
    crop = (10.0, 20.0, 622.0, 812.0)
    for rot in (0, 90, 180, 270):
        vx, vy, vw, vh = 45.0, 80.0, 120.0, 32.0
        pdf_r = visual_rect_to_pdf(vx, vy, vw, vh, crop, rot)
        vx2, vy2, vw2, vh2 = pdf_rect_to_visual(pdf_r, crop, rot)
        assert abs(vx - vx2) < 1e-4 and abs(vy - vy2) < 1e-4
        assert abs(vw - vw2) < 1e-4 and abs(vh - vh2) < 1e-4
    print("[PASS] Coordinate roundtrip across rotations 0/90/180/270")


def test_edit_all_text_and_content_stream_replacement(tmp: Path, screenshot_out: Path, welcome_out: Path) -> None:
    from PySide6.QtCore import QCoreApplication, QSize
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtWidgets import QApplication
    from kinofill.main_window import MainWindow

    assert APP_NAME == "KinoFill" and SUITE_NAME == "KinoSuite"
    src_pdf = tmp / "sample_banner_form.pdf"
    make_sample_pdf(str(src_pdf))

    os.environ["KINOFILL_DATA_DIR"] = str(tmp / "kinofill_data")
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    win = MainWindow()
    win.resize(1420, 880)
    win.show()

    # Verify default KinoSuite Dark Studio theme & default Edit All Text tool
    assert win.dark_mode is True, f"Expected KinoSuite dark_mode=True by default, got {win.dark_mode}"
    assert "KinoFill" in win.windowTitle() and "KinoSuite" in win.windowTitle()
    assert win.settings.tool == "edit_text", f"Expected default tool edit_text, got {win.settings.tool}"

    # Capture KinoSuite Welcome screen screenshot before opening PDF
    for _ in range(6):
        QCoreApplication.processEvents()
    win.grab().save(str(welcome_out), "PNG")
    assert welcome_out.exists() and welcome_out.stat().st_size > 10000
    print(f"[PASS] KinoSuite Welcome screenshot captured to {welcome_out}")

    tab = win.open_pdf(str(src_pdf))
    assert tab is not None
    assert tab.view.page_count() == 2

    # 1. Verify automatic text-block detection found all lines + split multi-column line!
    p0_blocks = tab.state.text_blocks.get(0, [])
    texts = [b.text for b in p0_blocks]
    print(f"Detected {len(p0_blocks)} editable text blocks on Page 1:", texts)
    header_blk = next((b for b in p0_blocks if "OLD HEADER TITLE" in b.text), None)
    assert header_blk is not None, f"Header block not detected! Found: {texts}"
    assert header_blk.bold is True, f"Expected header bold=True, got {header_blk.bold}"
    assert header_blk.font_size >= 16.0, f"Expected header size ~18, got {header_blk.font_size}"

    bill_blk = next((b for b in p0_blocks if "Bill To: Jane Smith" in b.text), None)
    date_blk = next((b for b in p0_blocks if "Date: Nov 26, 2026" in b.text), None)
    assert bill_blk is not None and date_blk is not None, f"Multi-column split failed! Found: {texts}"
    assert bill_blk.italic is True and bill_blk.font_family == "Times New Roman"

    # 2. Simulate clicking & altering the header right in place (just like clicking on the page!)
    page0_canvas = tab.view.page_widgets[0]
    edited_header = page0_canvas.start_editing_text_block(header_blk)
    assert page0_canvas._inline_editor is not None
    page0_canvas._inline_editor.setPlainText("ACME SERVICE AGREEMENT 2026")
    page0_canvas.close_inline_editor(commit=True)
    assert edited_header.text == "ACME SERVICE AGREEMENT 2026"
    assert tab.state.can_undo()

    # Also alter the legacy clause line (sits 1.5pt above a black form underline) AND the Form XObject line!
    clause_blk = next((b for b in p0_blocks if "Legacy Clause v1" in b.text), None)
    assert clause_blk is not None
    edited_clause = page0_canvas.start_editing_text_block(clause_blk)
    page0_canvas._inline_editor.setPlainText("Updated Clause v2 — zero box over underline!")
    page0_canvas.close_inline_editor(commit=True)

    xobj_blk = next((b for b in p0_blocks if "XObject Official Entry Line" in b.text), None)
    assert xobj_blk is not None, f"Form XObject text not detected! Found: {texts}"
    edited_xobj = page0_canvas.start_editing_text_block(xobj_blk)
    page0_canvas._inline_editor.setPlainText("Edited Form XObject Text (Blue Line Intact)")
    page0_canvas.close_inline_editor(commit=True)

    # Verify live canvas stripped ALL 3 replaced text blocks directly from the PDF stream (ZERO mask boxes on screen!)
    page0_canvas._ensure_rendered()
    assert edited_header.id in page0_canvas._stream_stripped_ids, "Live canvas fell back to mask box for header!"
    assert edited_clause.id in page0_canvas._stream_stripped_ids, "Live canvas fell back to mask box for clause!"
    assert edited_xobj.id in page0_canvas._stream_stripped_ids, "Live canvas fell back to mask box for Form XObject!"
    print("[PASS] Live canvas stripped all 3 replaced blocks directly from ContentStream + Form XObject (ZERO mask boxes on screen!)")

    # Fill existing AcroForm fields too
    for it in tab.state.items:
        if isinstance(it, FormFieldItem):
            if it.field_name == "FullName":
                it.value = "Austin Developer"
            elif it.field_name == "AgreeTerms":
                it.checked = True
                it.value = it.checked_value

    # Capture live GUI screenshot showing Edit All Text mode with subtle dotted boxes & live edits!
    tab.view.refresh_all_pages()
    for _ in range(8):
        QCoreApplication.processEvents()
    px = win.grab()
    px.save(str(screenshot_out), "PNG")
    assert screenshot_out.exists() and screenshot_out.stat().st_size > 10000
    print(f"[PASS] Live Edit-All-Text GUI screenshot captured to {screenshot_out}")

    # 3. Save PDF and verify TRUE ContentStream replacement (old text GONE, new text PRESENT, blue banner INTACT!)
    out_pdf = tmp / "replaced_stream.pdf"
    save_edited_pdf(tab.state, str(out_pdf), SecurityConfig(flatten_forms=False, true_redact=False))

    r = PdfReader(str(out_pdf))
    extracted = r.pages[0].extract_text() or ""
    assert "OLD HEADER TITLE" not in extracted, f"Old header text still in PDF stream! Extracted:\n{extracted}"
    assert "Legacy Clause v1" not in extracted, f"Old clause text still in PDF stream! Extracted:\n{extracted}"
    assert "XObject Official Entry Line" not in extracted, f"Old Form XObject text still in PDF stream! Extracted:\n{extracted}"
    assert "ACME SERVICE AGREEMENT 2026" in extracted, f"New header missing! Extracted:\n{extracted}"
    assert "Updated Clause v2" in extracted, f"New clause missing! Extracted:\n{extracted}"
    assert "Edited Form XObject Text" in extracted, f"New Form XObject text missing! Extracted:\n{extracted}"
    print("[PASS] True ContentStream + Form XObject text replacement verified!")

    # Verify the shaded blue banner, thin black underline (y=792-460.5=331.5), AND blue XObject underline (y=792-418.5=373.5) are 100% INTACT!
    qdoc = QPdfDocument()
    assert qdoc.load(str(out_pdf)) == QPdfDocument.Error.None_
    rendered = qdoc.render(0, QSize(1224, 1584))  # 2x HiDPI
    banner_px = rendered.pixelColor(120, 84)
    assert banner_px.blue() > banner_px.red() + 20, f"Blue banner damaged: RGB=({banner_px.red()},{banner_px.green()},{banner_px.blue()})"

    # Check black underline directly underneath the replaced clause text at x=120pt -> 240px, y=331.5pt -> 663px
    min_lum_black_line = min(
        rendered.pixelColor(240, y).red() + rendered.pixelColor(240, y).green() + rendered.pixelColor(240, y).blue()
        for y in range(660, 667)
    )
    assert min_lum_black_line < 220, f"Black form underline under replaced text was wiped out! min RGB sum={min_lum_black_line}"

    # Check blue underline inside Form XObject directly underneath replaced text at x=120pt -> 240px, y=373.5pt -> 747px
    best_blue_diff = max(
        rendered.pixelColor(240, y).blue() - rendered.pixelColor(240, y).red()
        for y in range(744, 751)
    )
    assert best_blue_diff > 80, f"Blue XObject underline under replaced text was wiped out! max B-R={best_blue_diff}"
    qdoc.close()
    print(f"[PASS] Background blue banner, black form underline (minLum={min_lum_black_line}), and XObject blue line (B-R={best_blue_diff}) are 100% INTACT!")

    # Verify Ctrl+F search works
    matches = tab.view.set_search_query("KINOFILL_VERIFIED_TOKEN")
    assert matches >= 1
    tab.view.set_search_query("")

    # Test True Redaction + Encryption
    tab.state.add_item(RedactItem(page=0, x=50, y=278, w=280, h=24, label="REDACTED"))
    enc_pdf = tmp / "redacted_enc.pdf"
    save_edited_pdf(
        tab.state,
        str(enc_pdf),
        SecurityConfig(encrypt=True, user_password="pw123", flatten_forms=True, true_redact=True),
    )
    re = PdfReader(str(enc_pdf))
    assert re.is_encrypted and re.decrypt("pw123")
    assert "123-45-6789" not in (re.pages[0].extract_text() or "")
    print("[PASS] True raster redaction + encryption verified")

    # Test page mutations, merge, split, images-to-PDF, PDF-to-PNG
    rot_pdf, _ = mutate_pdf_pages(str(src_pdf), "", op="rotate", page_idx=0, angle=90)
    assert int(PdfReader(rot_pdf).pages[0].get("/Rotate", 0)) == 90
    blank = tmp / "blank.pdf"
    create_blank_pdf(str(blank), 612, 792, 1)
    merged = tmp / "merged.pdf"
    merge_pdfs([str(out_pdf), str(blank)], str(merged))
    assert len(PdfReader(str(merged)).pages) == 3
    burst = split_pdf(str(merged), str(tmp / "burst"), "1-2", burst=True)
    assert len(burst) == 2
    imgs = export_pdf_to_images(str(out_pdf), str(tmp / "imgs"), fmt="PNG", dpi=150, page_range="1")
    assert len(imgs) == 1
    from_imgs = tmp / "from_imgs.pdf"
    images_to_pdf(imgs, str(from_imgs))
    assert len(PdfReader(str(from_imgs)).pages) == 1
    print("[PASS] Page mutations, merge, split/burst, PDF-to-PNG, and Images-to-PDF")

    tab.state.dirty = False
    win.close()


def main() -> int:
    test_coordinate_roundtrip_all_rotations()
    with tempfile.TemporaryDirectory(prefix="kinofill_test_") as td:
        shot = ROOT / "tests" / "kinofill_ui_screenshot.png"
        welcome = ROOT / "tests" / "kinofill_welcome_screenshot.png"
        test_edit_all_text_and_content_stream_replacement(Path(td), shot, welcome)
    print("\nALL KINOFILL TESTS PASSED SUCCESSFULLY!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
