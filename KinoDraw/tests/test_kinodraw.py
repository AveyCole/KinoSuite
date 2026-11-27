"""Comprehensive automated verification suite for KinoDraw (KinoSuite)."""
from __future__ import annotations

import os
import sys
import tempfile

# Ensure KinoDraw root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PIL import Image, ImageDraw
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication

from kinodraw.geometry import (
    apply_puppet_warp,
    apply_warp_to_qpath,
    build_corner_aligned_dash_path,
    build_variable_width_path,
    compute_planar_regions,
    convert_object_to_path,
    generate_blend_steps,
    object_to_qpath,
    offset_qpath,
    pathfinder_op,
    project_rect_to_perspective,
    recognize_shaper_gesture,
    simplify_subpaths,
)
from kinodraw.importers_exporters import (
    create_placed_image_object,
    export_print_pdf,
    export_raster,
    export_svg,
    generate_css_snippet,
    import_svg_objects,
    render_artboard_to_qimage,
)
from kinodraw.mainwindow import KinoDrawWindow
from kinodraw.models import (
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Color,
    Document,
    PerspectiveGridState,
    PuppetPin,
    VectorObject,
    WidthStation,
)
from kinodraw.plugins_builtin import load_all_plugins
from kinodraw.renderer import apply_separations_filter
from kinodraw.sample_artwork import create_showcase_document
from kinodraw.theme import KINOSUITE_DARK_THEME
from kinodraw.trace_and_ai import (
    generate_palette_from_prompt,
    generate_pattern_from_prompt,
    generate_vector_from_prompt,
    recolor_objects,
    trace_image_object,
)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(KINOSUITE_DARK_THEME)

    with tempfile.TemporaryDirectory() as tmp:
        # 1. Showcase Document Save / Load & Version History
        doc = create_showcase_document()
        assert len(doc.artboards) == 2
        assert len(doc.iter_all_objects()) >= 10
        doc_path = os.path.join(tmp, "test.kdrw")
        doc.save_to_file(doc_path)
        doc2 = Document.load_from_file(doc_path)
        assert len(doc2.artboards) == 2
        assert len(doc2.iter_all_objects()) == len(doc.iter_all_objects())
        snap = doc2.save_version("Before Edit")
        doc2.artboards.pop()
        assert len(doc2.artboards) == 1
        assert doc2.restore_version(snap.id)
        assert len(doc2.artboards) == 2
        print("[PASS] 1. Models, .kdrw JSON persistence & Version History")

        # 2. Geometry Engine: Pathfinder, Shape Builder, Width, Dashes, Offset, Warp, Puppet, Perspective, Shaper, Blend
        r1 = VectorObject(name="R1", kind="shape", shape_type="rect", x=10, y=10, width=100, height=100,
                          appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#FF9A00"))]))
        r2 = VectorObject(name="R2", kind="shape", shape_type="ellipse", x=60, y=40, width=100, height=100,
                          appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#00C2FF"))]))
        for op in ("unite", "minus_front", "intersect", "exclude", "divide", "trim", "outline"):
            res = pathfinder_op([r1, r2], op)
            assert len(res) >= 1, f"Pathfinder {op} returned empty"
        regions = compute_planar_regions([r1, r2])
        assert len(regions) == 3, f"Expected 3 Venn regions, got {len(regions)}"

        qp1 = object_to_qpath(r1)
        var_w = build_variable_width_path(qp1, 14.0, [WidthStation(0.0, 0.2, 0.2), WidthStation(0.5, 1.8, 1.8), WidthStation(1.0, 0.2, 0.2)])
        assert not var_w.isEmpty()
        dash_qp = build_corner_aligned_dash_path(qp1, [10.0, 6.0], 2.0)
        assert not dash_qp.isEmpty()
        off_qp = offset_qpath(qp1, 12.0)
        assert off_qp.boundingRect().width() > qp1.boundingRect().width()
        warp_qp = apply_warp_to_qpath(qp1, "flag", 0.4)
        assert not warp_qp.isEmpty()

        p_obj = convert_object_to_path(r1)
        simp_sps = simplify_subpaths(p_obj.subpaths, 2.0)
        assert len(simp_sps) >= 1
        warped = apply_puppet_warp(p_obj.subpaths, [PuppetPin(20, 20, 10, 10), PuppetPin(110, 125, 110, 110)])
        assert len(warped) == len(p_obj.subpaths)

        persp = PerspectiveGridState(visible=True, points=3, active_plane="left")
        persp_sp = project_rect_to_perspective(QRectF(200, 300, 140, 120), persp)
        assert len(persp_sp.anchors) == 4

        circle_pts = [(100 + 50 * __import__("math").cos(i * 0.25), 100 + 50 * __import__("math").sin(i * 0.25)) for i in range(26)]
        kind, _ = recognize_shaper_gesture(circle_pts)
        assert kind == "ellipse", f"Shaper misclassified circle as {kind}"

        bl_steps = generate_blend_steps(r1, r2, 5)
        assert len(bl_steps) == 5
        print("[PASS] 2. Geometry Engine (Pathfinder, Shape Builder, Width, Warp, Puppet, Perspective, Shaper, Blend)")

        # 3. Rendering + Separations + Exports (PNG, JPG, WebP, SVG round-trip, CMYK Print PDF, CSS)
        qimg = render_artboard_to_qimage(doc, doc.artboards[0], scale=1.0)
        assert qimg.width() == 1080 and qimg.height() == 740
        sep = apply_separations_filter(qimg, {"C": True, "M": False, "Y": False, "K": True})
        assert sep.width() == 1080

        for fmt in ("PNG", "JPG", "WEBP"):
            p_out = os.path.join(tmp, f"art.{fmt.lower()}")
            export_raster(doc, p_out, fmt=fmt, scale=1.0, artboard=doc.artboards[0])
            assert os.path.getsize(p_out) > 2000

        svg_out = os.path.join(tmp, "art.svg")
        export_svg(doc, svg_out, artboard=doc.artboards[0])
        assert os.path.getsize(svg_out) > 500
        reimp = import_svg_objects(svg_out)
        assert len(reimp) >= 3

        pdf_out = os.path.join(tmp, "print_cmyk.pdf")
        export_print_pdf(doc, pdf_out, cmyk=True, bleed_pt=9.0, crop_marks=True, reg_marks=True, color_bars=True)
        assert os.path.getsize(pdf_out) > 5000

        css = generate_css_snippet(r1)
        assert "background-color: #FF9A00" in css
        print("[PASS] 3. Rendering, CMYK Separations, PNG/JPG/WebP, SVG Round-Trip, Print PDF & CSS")

        # 4. OpenCV Image Trace (Color + AI-Assisted Sketch)
        sample_png = os.path.join(tmp, "sample_logo.png")
        pil = Image.new("RGB", (200, 200), (255, 255, 255))
        dr = ImageDraw.Draw(pil)
        dr.ellipse((25, 25, 175, 175), fill=(255, 154, 0))
        dr.rectangle((65, 65, 135, 135), fill=(20, 24, 33))
        pil.save(sample_png)
        placed = create_placed_image_object(sample_png, 50, 50, embed=True)
        traced_col = trace_image_object(placed, mode="color", colors=3)
        assert traced_col is not None and len(traced_col.children) >= 1
        traced_sk = trace_image_object(placed, mode="sketch", sketch_ai=True)
        assert traced_sk is not None and len(traced_sk.children) >= 1
        print("[PASS] 4. Image Trace (Color K-Means & AI-Assisted Sketch)")

        # 5. Generative Vector, Generative Pattern, Generative Recolor & Plugins
        gv = generate_vector_from_prompt("sunset mountain landscape")
        assert len(gv.children) >= 3
        gp = generate_pattern_from_prompt("botanical jungle leaves")
        assert gp.kind == "botanical"
        pal = generate_palette_from_prompt("cyberpunk neon")
        recolor_objects([gv], pal)
        plugins = load_all_plugins(os.path.join(ROOT, "plugins"))
        assert len(plugins) >= 4
        for pl in plugins:
            msg = pl.action(doc2)
            assert isinstance(msg, str) and len(msg) > 0
        print("[PASS] 5. Generative Vector / Pattern / Recolor & Built-in KinoSuite Plugins")

        # 6. Full GUI MainWindow Smoke Test & Visual Screenshot Capture
        win = KinoDrawWindow()
        win.resize(1440, 880)
        win.show()
        app.processEvents()
        win.current_canvas().fit_artboard()
        app.processEvents()
        shot_path = os.path.join(ROOT, "tests", "kinodraw_ui_smoke.png")
        win.grab().save(shot_path)
        assert os.path.getsize(shot_path) > 20000
        win.close()
        print(f"[PASS] 6. KinoDraw GUI Smoke Test & Screenshot saved to {shot_path}")

    print("\nALL KINODRAW VERIFICATION TESTS PASSED!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
