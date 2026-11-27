"""Comprehensive end-to-end automated verification suite for KinoShop."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

from kinoshop.brushes import BrushSettings, flood_fill_layer, paint_stroke_segment, render_gradient
from kinoshop.engine import apply_adjustment_rgb, apply_filter_rgba, blend_rgb, composite_document, rgb_to_cmyk, cmyk_to_rgb
from kinoshop.io_export import (
    ActionManager,
    KinoCloudManager,
    batch_export_datasets,
    build_content_credentials_manifest,
    export_animated_gif,
    export_image,
    export_print_pdf,
    export_slices_multiscale,
    load_ksd,
    run_image_processor,
    save_ksd,
    update_linked_smart_objects,
)
from kinoshop.mainwindow import KinoShopWindow
from kinoshop.models import ADJUSTMENT_TYPES, BLEND_MODES, AnimationFrame, KinoDocument, Layer, LayerStyles, SmartFilter
from kinoshop.photo_ops import (
    ai_select_sky,
    ai_select_subject,
    apply_camera_raw,
    apply_lens_correction,
    apply_liquify_field,
    apply_perspective_warp,
    apply_puppet_warp,
    auto_align_layers,
    auto_blend_layers,
    auto_count_objects,
    auto_straighten_scan,
    build_contact_sheet,
    build_picture_package,
    content_aware_fill,
    content_aware_scale,
    focus_stack_images,
    harmonize_layer_to_scene,
    liquify_brush_step,
    make_seamless_pattern,
    match_color_reinhard,
    merge_to_hdr_pro,
    neural_filter_colorize,
    neural_filter_depth_blur,
    neural_filter_smart_portrait,
    neural_filter_style_transfer,
    neural_filter_super_zoom,
    photomerge_panorama,
    refine_select_and_mask,
    render_3d_object,
    replace_sky,
    split_scanned_photos,
    synthesize_procedural_texture,
    vanishing_point_tile_or_paste,
)
from kinoshop.plugins_builtin import load_all_plugins
from kinoshop.sample_project import create_sample_studio_document


def run_all() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = tempfile.mkdtemp(prefix="kinoshop_test_")

    # 1. Sample Project & Full Compositing
    doc = create_sample_studio_document()
    comp = composite_document(doc)
    assert comp.shape == (800, 1280, 4) and comp.dtype == np.uint8
    print("[PASS] Sample studio project & full compositor")

    # 2. All 24 Blend Modes & 13 Adjustments
    base = np.full((32, 32, 3), 0.4, dtype=np.float32)
    top = np.full((32, 32, 3), 0.7, dtype=np.float32)
    for bm in BLEND_MODES:
        res = blend_rgb(base, top, bm)
        assert res.shape == (32, 32, 3) and not np.isnan(res).any()
    for at in ADJUSTMENT_TYPES:
        from kinoshop.models import default_adjustment_params
        res = apply_adjustment_rgb(base, at, default_adjustment_params(at))
        assert res.shape == (32, 32, 3) and not np.isnan(res).any()
    print(f"[PASS] All {len(BLEND_MODES)} blend modes & {len(ADJUSTMENT_TYPES)} adjustments")

    # 3. Print Prep: CMYK, Soft-Proof, Gamut Warning, Bleed & Print PDF
    doc.set_color_mode("CMYK")
    doc.print_settings.soft_proof = True
    doc.print_settings.gamut_warning = True
    doc.print_settings.crop_marks = True
    doc.print_settings.registration_marks = True
    doc.print_settings.color_bars = True
    doc.print_settings.page_info = True
    cmyk_comp = composite_document(doc)
    assert cmyk_comp.shape == (800, 1280, 4)
    pdf_path = os.path.join(tmp, "print_cmyk.pdf")
    export_print_pdf(doc, pdf_path)
    assert os.path.getsize(pdf_path) > 2000
    doc.set_color_mode("RGB")
    doc.print_settings.soft_proof = False
    print("[PASS] CMYK color mode, soft-proof, gamut warning & print-ready PDF")

    # 4. Channels: Alpha & Spot Color
    doc.selection = np.zeros((800, 1280), dtype=np.float32)
    doc.selection[100:300, 100:300] = 1.0
    doc.save_selection_as_alpha("Alpha Test")
    doc.add_spot_channel("Pantone Cyan", (0, 174, 239))
    assert composite_document(doc).shape == (800, 1280, 4)
    print("[PASS] Alpha & Spot Color channels")

    # 5. Painting, Mixer Brush, Symmetry, Gradient & Flood Fill
    canvas = np.zeros((128, 128, 4), dtype=np.uint8)
    bs = BrushSettings(size=18, symmetry="Radial4")
    paint_stroke_segment(canvas, (20, 20), (80, 80), (49, 168, 255), bs, pressure=0.7, mode="brush")
    paint_stroke_segment(canvas, (30, 30), (90, 50), (255, 160, 40), bs, pressure=0.9, mode="mixer")
    grad = render_gradient(128, 128, (0, 0), (128, 128), (20, 40, 80, 255), (49, 168, 255, 255), style="Radial")
    flood_fill_layer(grad, 10, 10, (255, 255, 255, 255), tolerance=20)
    assert canvas[..., 3].max() > 0 and grad.shape == (128, 128, 4)
    print("[PASS] Painting, Mixer Brush, Symmetry, Gradient & Bucket")

    # 6. Smart Filters including Lighting Effects & Lens Flare
    small = np.ascontiguousarray(comp[::4, ::4])  # 200x320
    for fn in ["Gaussian Blur", "Motion Blur", "Unsharp Mask", "Add Noise", "Twirl", "Ripple", "Halftone", "Lens Flare", "Lighting Effects", "Vignette"]:
        out = apply_filter_rgba(small, fn, {})
        assert out.shape == small.shape
    print("[PASS] Smart Filters, Lighting Effects & Lens Flare")

    # 7. AI Selections, Select & Mask, Sky Replace, Camera Raw, Liquify, Warps, Vanishing Point, Seam Carving
    sub_m = ai_select_subject(small)
    sky_m = ai_select_sky(small)
    ref_m, _ = refine_select_and_mask(small, sub_m, smooth=2.0, feather=2.0, decontaminate=True)
    assert ref_m.shape == small.shape[:2]
    assert replace_sky(small, "Dramatic Twilight Aurora").shape == small.shape
    assert apply_camera_raw(small, {"exposure": 0.4, "clarity": 25, "vibrance": 30}).shape == small.shape

    dx = np.zeros(small.shape[:2], np.float32)
    dy = np.zeros(small.shape[:2], np.float32)
    liquify_brush_step(dx, dy, 120, 100, 15, -10, 35, 0.7, "Forward Warp")
    assert apply_liquify_field(small, dx, dy).shape == small.shape
    assert apply_puppet_warp(small, [(50, 50), (200, 150)], [(60, 45), (210, 165)]).shape == small.shape
    assert apply_perspective_warp(small, [(0, 0), (320, 0), (320, 200), (0, 200)], [(20, 10), (300, 20), (310, 190), (10, 180)]).shape == small.shape
    assert apply_lens_correction(small, k1=-0.12, vertical_tilt=0.15).shape == small.shape
    tile = synthesize_procedural_texture(64, 64, "Marble Veins")
    assert vanishing_point_tile_or_paste(small, [(60, 120), (260, 120), (310, 195), (10, 195)], tile).shape == small.shape
    assert content_aware_fill(small, sky_m).shape == small.shape
    assert content_aware_scale(small, 290, 200).shape == (200, 290, 4)
    print("[PASS] AI Select, Select&Mask, Sky Replace, Camera Raw, Liquify, Puppet/Perspective/Vanishing, CAS")

    # 8. PhotoMerge, Auto-Align, Auto-Blend, HDR Pro, Focus Stack, Patterns, Harmonize, Neural Filters, 3D
    imgs = [small, np.clip(small.astype(np.int32) + 25, 0, 255).astype(np.uint8)]
    assert photomerge_panorama(imgs).shape[2] == 4
    assert auto_blend_layers(auto_align_layers(imgs)).shape == small.shape
    assert merge_to_hdr_pro(imgs).shape == small.shape
    assert focus_stack_images(imgs).shape == small.shape
    assert make_seamless_pattern(small).shape == small.shape
    assert harmonize_layer_to_scene(small, small).shape == small.shape
    assert match_color_reinhard(small, tile).shape == small.shape
    assert neural_filter_colorize(small).shape == small.shape
    assert neural_filter_style_transfer(small, "Watercolor").shape == small.shape
    assert neural_filter_smart_portrait(small).shape == small.shape
    assert neural_filter_depth_blur(small).shape == small.shape
    assert neural_filter_super_zoom(small, 2).shape == (400, 640, 4)
    assert render_3d_object(160, 160, "Sphere", small).shape == (160, 160, 4)
    print("[PASS] PhotoMerge, HDR Pro, Focus Stack, Pattern Maker, Harmonize, Neural Filters, 3D")

    # 9. Scanning Deskew/Split, Contact Sheet, Picture Package, Scientific Count
    deskewed, _ = auto_straighten_scan(small)
    assert deskewed.shape == small.shape
    flatbed = np.full((240, 320, 4), 245, dtype=np.uint8)
    flatbed[20:100, 20:120, :3] = (40, 80, 160)
    flatbed[120:210, 150:290, :3] = (180, 70, 50)
    splits = split_scanned_photos(flatbed)
    assert len(splits) == 2
    assert build_contact_sheet([("a.png", small), ("b.png", tile)], 400, 500, 2, 2).shape == (500, 400, 4)
    assert build_picture_package(small, page_w=400, page_h=500).shape == (500, 400, 4)
    objs = auto_count_objects(flatbed, threshold=200, invert=True, min_area=100)
    assert len(objs) == 2
    print("[PASS] Scan Deskew & Multi-Photo Split, Contact Sheet, Picture Package, Auto-Count")

    # 10. Native .ksd Roundtrip, Multi-Format Export, Linked Smart Object, Slices, Variables, Image Processor, GIF, Cloud, Plugins
    ksd_path = os.path.join(tmp, "test.ksd")
    save_ksd(doc, ksd_path)
    loaded = load_ksd(ksd_path)
    assert loaded.width == doc.width and len(loaded.layers) == len(doc.layers) and len(loaded.layer_comps) >= 2
    for ext in (".png", ".jpg", ".webp", ".tiff", ".svg"):
        ep = os.path.join(tmp, f"out{ext}")
        export_image(loaded, ep)
        assert os.path.getsize(ep) > 200

    # Linked smart object auto-refresh test
    link_png = os.path.join(tmp, "linked_asset.png")
    export_image(loaded, link_png, scale=0.2)
    loaded.layers.append(Layer(name="Linked", kind="smart_object", smart_source=small, linked_path=link_png, linked_mtime=0.0))
    assert update_linked_smart_objects(loaded) == 1

    # Slices multi-scale export
    slice_files = export_slices_multiscale(loaded, os.path.join(tmp, "slices"))
    assert len(slice_files) >= 4

    # Variables & Data Sets batch export
    loaded.data_sets = [{"Headline": "ALPHA", "Subtitle": "Edition 1"}, {"Headline": "BETA", "Subtitle": "Edition 2"}]
    var_files = batch_export_datasets(loaded, os.path.join(tmp, "vars"), fmt="PNG")
    assert len(var_files) == 2

    # Image Processor batch
    proc_files = run_image_processor(os.path.join(tmp, "vars"), os.path.join(tmp, "proc"), ["PNG", "JPEG"], max_w=640, max_h=400)
    assert len(proc_files) == 4

    # Animated GIF
    loaded.frames = [AnimationFrame(name="F1", duration_ms=100), AnimationFrame(name="F2", duration_ms=100)]
    gif_path = os.path.join(tmp, "anim.gif")
    export_animated_gif(loaded, gif_path)
    assert os.path.getsize(gif_path) > 500

    # KinoCloud Version & Share-for-Review HTML + Content Credentials
    cm = KinoCloudManager(tmp)
    v = cm.save_cloud_version(loaded, "Initial Release")
    assert v["version"] == 1 and len(cm.list_versions(loaded)) == 1
    rev_html = cm.export_share_for_review_html(loaded, os.path.join(tmp, "review.html"))
    assert os.path.getsize(rev_html) > 2000
    creds = build_content_credentials_manifest(loaded, small)
    assert len(creds["asset_sha256"]) == 64

    # Plugins (built-in + external film_halation.py)
    plugs = load_all_plugins(os.path.join(ROOT, "plugins"))
    assert len(plugs) >= 4
    for pl in plugs:
        assert pl.run(small, pl.default_params).shape == small.shape
    print(f"[PASS] .ksd roundtrip, exports, linked SO, slices, variables, image proc, GIF, KinoCloud, {len(plugs)} plugins")

    # 11. Full Main Window UI Instantiation (Offscreen Qt)
    win = KinoShopWindow()
    win.show()
    app.processEvents()
    assert win.current_doc() is not None and win.current_canvas() is not None
    win.select_tool("brush")
    win.apply_workspace("Photography")
    win.apply_workspace("Motion / Video")
    win.close()
    print("[PASS] KinoShopWindow full UI, panels, tools & workspaces verified!")
    print("\nALL KINOSHOP VERIFICATION TESTS PASSED!")


if __name__ == "__main__":
    run_all()
