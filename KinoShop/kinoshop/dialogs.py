"""KinoShop Pro Studio Modal Dialogs (Camera Raw, Liquify, Select & Mask, Sky Replace,
Neural Filters, PhotoMerge & HDR Pro, Print Prep, Vanishing Point, 3D Studio,
Scan/Contact Sheet, Variables, Automation/Script Events, Metadata & Content Credentials,
Extensions, Measurement/Count)."""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .canvas import rgba_to_qimage
from .engine import composite_document
from .io_export import (
    ActionManager,
    batch_export_datasets,
    build_content_credentials_manifest,
    export_print_pdf,
    export_slices_multiscale,
    load_csv_datasets,
    load_image_rgba,
    run_image_processor,
)
from .models import COLOR_MODES, COLOR_PROFILES, KinoDocument, LayerStyles
from .photo_ops import (
    SKY_PRESETS,
    apply_camera_raw,
    apply_lens_correction,
    apply_liquify_field,
    auto_align_layers,
    auto_blend_layers,
    auto_count_objects,
    auto_straighten_scan,
    build_contact_sheet,
    build_picture_package,
    focus_stack_images,
    liquify_brush_step,
    make_seamless_pattern,
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
    scan_from_wia_windows,
    split_scanned_photos,
    synthesize_procedural_texture,
    vanishing_point_tile_or_paste,
)
from .plugins_builtin import KinoPlugin


def _make_preview_label(w: int = 440, h: int = 310) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(w, h)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("background:#0D1017; border:1px solid #2A3242; border-radius:6px;")
    return lbl


def _set_preview(lbl: QLabel, rgba: np.ndarray) -> None:
    pm = QPixmap.fromImage(rgba_to_qimage(rgba))
    lbl.setPixmap(pm.scaled(lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


def _downscale_for_preview(rgba: np.ndarray, max_dim: int = 560) -> np.ndarray:
    h, w = rgba.shape[:2]
    sc = min(1.0, max_dim / max(h, w, 1))
    if sc >= 0.99:
        return rgba.copy()
    return cv2.resize(rgba, (max(16, int(w * sc)), max(16, int(h * sc))), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------
# 1. New Document Dialog (Print / Photo / Social / Web Presets)
# ---------------------------------------------------------------------------
DOC_PRESETS = {
    "Custom": (1280, 800, 300, "RGB", 0.0),
    "Photo Landscape (1920×1080)": (1920, 1080, 300, "RGB", 0.0),
    "Instagram Post (1080×1080)": (1080, 1080, 72, "RGB", 0.0),
    "Instagram Story / Reel (1080×1920)": (1080, 1920, 72, "RGB", 0.0),
    "YouTube Thumbnail (1280×720)": (1280, 720, 72, "RGB", 0.0),
    "Print US Letter CMYK (2550×3300)": (2550, 3300, 300, "CMYK", 3.0),
    "Print A4 Poster CMYK (2480×3508)": (2480, 3508, 300, "CMYK", 3.0),
    "Web UI Desktop (1440×900)": (1440, 900, 72, "RGB", 0.0),
    "Mobile UI iOS (1170×2532)": (1170, 2532, 72, "RGB", 0.0),
}


class NewDocumentDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New KinoShop Document (.ksd)")
        self.resize(440, 360)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(list(DOC_PRESETS.keys()))
        self.cmb_preset.currentTextChanged.connect(self._apply_preset)
        form.addRow("Preset:", self.cmb_preset)

        self.ed_name = QLineEdit("Untitled-1.ksd")
        form.addRow("Name:", self.ed_name)

        self.sp_w = QSpinBox()
        self.sp_w.setRange(16, 8192)
        self.sp_w.setValue(1280)
        self.sp_h = QSpinBox()
        self.sp_h.setRange(16, 8192)
        self.sp_h.setValue(800)
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(72, 1200)
        self.sp_dpi.setValue(300)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(COLOR_MODES)
        self.cmb_prof = QComboBox()
        self.cmb_prof.addItems(COLOR_PROFILES)
        self.sp_bleed = QDoubleSpinBox()
        self.sp_bleed.setRange(0.0, 25.0)
        self.sp_bleed.setSuffix(" mm")
        self.cmb_bg = QComboBox()
        self.cmb_bg.addItems(["Deep Slate (#181C25)", "White", "Black", "Transparent"])

        form.addRow("Width (px):", self.sp_w)
        form.addRow("Height (px):", self.sp_h)
        form.addRow("Resolution (DPI):", self.sp_dpi)
        form.addRow("Color Mode:", self.cmb_mode)
        form.addRow("Color Profile:", self.cmb_prof)
        form.addRow("Print Bleed:", self.sp_bleed)
        form.addRow("Background:", self.cmb_bg)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _apply_preset(self, name: str) -> None:
        w, h, dpi, mode, bleed = DOC_PRESETS[name]
        self.sp_w.setValue(w)
        self.sp_h.setValue(h)
        self.sp_dpi.setValue(dpi)
        self.cmb_mode.setCurrentText(mode)
        self.sp_bleed.setValue(bleed)

    def result_spec(self) -> Dict[str, Any]:
        bg_map = {
            "Deep Slate (#181C25)": (24, 28, 37, 255),
            "White": (255, 255, 255, 255),
            "Black": (0, 0, 0, 255),
            "Transparent": (0, 0, 0, 0),
        }
        return {
            "name": self.ed_name.text().strip() or "Untitled.ksd",
            "width": self.sp_w.value(),
            "height": self.sp_h.value(),
            "dpi": self.sp_dpi.value(),
            "color_mode": self.cmb_mode.currentText(),
            "color_profile": self.cmb_prof.currentText(),
            "bleed_mm": self.sp_bleed.value(),
            "background": bg_map[self.cmb_bg.currentText()],
        }


# ---------------------------------------------------------------------------
# 2. Layer Styles Dialog (fx)
# ---------------------------------------------------------------------------
class LayerStylesDialog(QDialog):
    def __init__(self, styles: LayerStyles, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Layer Styles (fx)")
        self.styles = LayerStyles.from_dict(styles.to_dict())
        self.resize(400, 420)
        lay = QVBoxLayout(self)

        self.chk_ds = QCheckBox("Drop Shadow")
        self.chk_ds.setChecked(self.styles.drop_shadow)
        self.sp_ds_dist = QSpinBox(); self.sp_ds_dist.setRange(0, 80); self.sp_ds_dist.setValue(self.styles.drop_shadow_distance)
        self.sp_ds_blur = QSpinBox(); self.sp_ds_blur.setRange(0, 80); self.sp_ds_blur.setValue(self.styles.drop_shadow_blur)

        self.chk_is = QCheckBox("Inner Shadow")
        self.chk_is.setChecked(self.styles.inner_shadow)
        self.chk_og = QCheckBox("Outer Glow")
        self.chk_og.setChecked(self.styles.outer_glow)
        self.sp_og_rad = QSpinBox(); self.sp_og_rad.setRange(1, 60); self.sp_og_rad.setValue(self.styles.outer_glow_radius)
        self.chk_ig = QCheckBox("Inner Glow")
        self.chk_ig.setChecked(self.styles.inner_glow)
        self.chk_bev = QCheckBox("Bevel & Emboss")
        self.chk_bev.setChecked(self.styles.bevel_emboss)
        self.chk_co = QCheckBox("Color Overlay")
        self.chk_co.setChecked(self.styles.color_overlay)
        self.chk_st = QCheckBox("Stroke")
        self.chk_st.setChecked(self.styles.stroke)
        self.sp_st_sz = QSpinBox(); self.sp_st_sz.setRange(1, 40); self.sp_st_sz.setValue(self.styles.stroke_size)
        self.cmb_st_pos = QComboBox(); self.cmb_st_pos.addItems(["Outside", "Inside", "Center"])
        self.cmb_st_pos.setCurrentText(self.styles.stroke_position)

        form = QFormLayout()
        form.addRow(self.chk_ds)
        form.addRow("  Shadow Dist / Blur:", self._pair(self.sp_ds_dist, self.sp_ds_blur))
        form.addRow(self.chk_is)
        form.addRow(self.chk_og, self.sp_og_rad)
        form.addRow(self.chk_ig)
        form.addRow(self.chk_bev)
        form.addRow(self.chk_co)
        form.addRow(self.chk_st, self._pair(self.sp_st_sz, self.cmb_st_pos))
        lay.addLayout(form)

        b_glow_col = QPushButton("Pick Outer Glow Color…")
        b_glow_col.clicked.connect(lambda: self._pick_col("outer_glow_color"))
        b_st_col = QPushButton("Pick Stroke Color…")
        b_st_col.clicked.connect(lambda: self._pick_col("stroke_color"))
        row_c = QHBoxLayout()
        row_c.addWidget(b_glow_col)
        row_c.addWidget(b_st_col)
        lay.addLayout(row_c)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._commit)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pair(self, w1: QWidget, w2: QWidget) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w1)
        h.addWidget(w2)
        return box

    def _pick_col(self, attr: str) -> None:
        cur = getattr(self.styles, attr)
        c = QColorDialog.getColor(QColor(*cur), self, "Pick Style Color")
        if c.isValid():
            setattr(self.styles, attr, (c.red(), c.green(), c.blue()))

    def _commit(self) -> None:
        self.styles.drop_shadow = self.chk_ds.isChecked()
        self.styles.drop_shadow_distance = self.sp_ds_dist.value()
        self.styles.drop_shadow_blur = self.sp_ds_blur.value()
        self.styles.inner_shadow = self.chk_is.isChecked()
        self.styles.outer_glow = self.chk_og.isChecked()
        self.styles.outer_glow_radius = self.sp_og_rad.value()
        self.styles.inner_glow = self.chk_ig.isChecked()
        self.styles.bevel_emboss = self.chk_bev.isChecked()
        self.styles.color_overlay = self.chk_co.isChecked()
        self.styles.stroke = self.chk_st.isChecked()
        self.styles.stroke_size = self.sp_st_sz.value()
        self.styles.stroke_position = self.cmb_st_pos.currentText()
        self.accept()


# ---------------------------------------------------------------------------
# 3. Camera Raw Studio Dialog
# ---------------------------------------------------------------------------
class CameraRawDialog(QDialog):
    def __init__(self, rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("KinoShop Camera Raw Studio")
        self.resize(840, 560)
        self.src = rgba
        self.prev_src = _downscale_for_preview(rgba, 520)
        self.params: Dict[str, float] = {}

        main = QHBoxLayout(self)
        self.preview = _make_preview_label(480, 440)
        main.addWidget(self.preview, 1)

        right = QVBoxLayout()
        form = QFormLayout()
        specs = [
            ("Temperature", "temperature", -100, 100, 1.0),
            ("Tint", "tint", -100, 100, 1.0),
            ("Exposure", "exposure", -300, 300, 0.01),
            ("Contrast", "contrast", -100, 100, 1.0),
            ("Highlights", "highlights", -100, 100, 1.0),
            ("Shadows", "shadows", -100, 100, 1.0),
            ("Whites", "whites", -100, 100, 1.0),
            ("Blacks", "blacks", -100, 100, 1.0),
            ("Clarity", "clarity", -100, 100, 1.0),
            ("Dehaze", "dehaze", -100, 100, 1.0),
            ("Vibrance", "vibrance", -100, 100, 1.0),
            ("Saturation", "saturation", -100, 100, 1.0),
            ("Sharpening", "sharpen", 0, 100, 1.0),
            ("Noise Reduction", "denoise", 0, 100, 1.0),
            ("Vignette", "vignette", -100, 100, 1.0),
        ]
        self._sliders = []
        for label, key, mn, mx, scale in specs:
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(mn, mx)
            sl.setValue(0)
            sl.valueChanged.connect(lambda v, k=key, sc=scale: self._on_change(k, v * sc))
            form.addRow(label, sl)
            self._sliders.append((sl, key))
            self.params[key] = 0.0
        right.addLayout(form)

        b_reset = QPushButton("Reset All")
        b_reset.clicked.connect(self._reset)
        right.addWidget(b_reset)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        main.addLayout(right)
        self._update_preview()

    def _on_change(self, key: str, val: float) -> None:
        self.params[key] = val
        self._update_preview()

    def _reset(self) -> None:
        for sl, key in self._sliders:
            sl.blockSignals(True)
            sl.setValue(0)
            sl.blockSignals(False)
            self.params[key] = 0.0
        self._update_preview()

    def _update_preview(self) -> None:
        _set_preview(self.preview, apply_camera_raw(self.prev_src, self.params))

    def result_image(self) -> np.ndarray:
        return apply_camera_raw(self.src, self.params)


# ---------------------------------------------------------------------------
# 4. Interactive Liquify Studio Dialog
# ---------------------------------------------------------------------------
class _LiquifyCanvas(QWidget):
    def __init__(self, rgba: np.ndarray) -> None:
        super().__init__()
        self.src = rgba
        self.h, self.w = rgba.shape[:2]
        self.disp_x = np.zeros((self.h, self.w), dtype=np.float32)
        self.disp_y = np.zeros((self.h, self.w), dtype=np.float32)
        self.tool = "Forward Warp"
        self.radius = 42.0
        self.pressure = 0.55
        self._drag = False
        self._last = QPointF()
        self._img = rgba_to_qimage(self.src)
        self.setMinimumSize(460, 380)

    def _to_img(self, pt: QPointF) -> Tuple[float, float]:
        sc = min(self.width() / max(1, self.w), self.height() / max(1, self.h))
        ox = (self.width() - self.w * sc) * 0.5
        oy = (self.height() - self.h * sc) * 0.5
        return (pt.x() - ox) / max(sc, 1e-4), (pt.y() - oy) / max(sc, 1e-4)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        self._drag = True
        self._last = e.position()
        ix, iy = self._to_img(e.position())
        if self.tool in ("Pucker", "Bloat", "Twirl CW", "Twirl CCW", "Reconstruct"):
            liquify_brush_step(self.disp_x, self.disp_y, ix, iy, 0, 0, self.radius, self.pressure, self.tool)
            self._refresh()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if not self._drag:
            return
        x0, y0 = self._to_img(self._last)
        x1, y1 = self._to_img(e.position())
        self._last = e.position()
        liquify_brush_step(self.disp_x, self.disp_y, x1, y1, x1 - x0, y1 - y0, self.radius, self.pressure, self.tool)
        self._refresh()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag = False

    def _refresh(self) -> None:
        warped = apply_liquify_field(self.src, self.disp_x, self.disp_y)
        self._img = rgba_to_qimage(warped)
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0D1017"))
        sc = min(self.width() / max(1, self.w), self.height() / max(1, self.h))
        dw, dh = int(self.w * sc), int(self.h * sc)
        ox, oy = (self.width() - dw) // 2, (self.height() - dh) // 2
        p.drawImage(ox, oy, self._img.scaled(dw, dh, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        p.end()


class LiquifyDialog(QDialog):
    def __init__(self, rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Liquify Studio (Face & Body Reshape)")
        self.resize(780, 520)
        self.full_src = rgba
        prev = _downscale_for_preview(rgba, 480)
        self.lcanvas = _LiquifyCanvas(prev)

        lay = QHBoxLayout(self)
        lay.addWidget(self.lcanvas, 1)

        ctrl = QVBoxLayout()
        cmb = QComboBox()
        cmb.addItems(["Forward Warp", "Twirl CW", "Twirl CCW", "Pucker", "Bloat", "Reconstruct"])
        cmb.currentTextChanged.connect(lambda t: setattr(self.lcanvas, "tool", t))
        sp_r = QSpinBox(); sp_r.setRange(8, 160); sp_r.setValue(42)
        sp_r.valueChanged.connect(lambda v: setattr(self.lcanvas, "radius", float(v)))
        sl_p = QSlider(Qt.Orientation.Horizontal); sl_p.setRange(10, 100); sl_p.setValue(55)
        sl_p.valueChanged.connect(lambda v: setattr(self.lcanvas, "pressure", v / 100.0))

        f = QFormLayout()
        f.addRow("Liquify Tool:", cmb)
        f.addRow("Brush Size:", sp_r)
        f.addRow("Pressure:", sl_p)
        ctrl.addLayout(f)

        b_rst = QPushButton("Reset Mesh")
        b_rst.clicked.connect(self._reset)
        ctrl.addWidget(b_rst)
        ctrl.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        ctrl.addWidget(bb)
        lay.addLayout(ctrl)

    def _reset(self) -> None:
        self.lcanvas.disp_x.fill(0)
        self.lcanvas.disp_y.fill(0)
        self.lcanvas._refresh()

    def result_image(self) -> np.ndarray:
        fh, fw = self.full_src.shape[:2]
        sx = fw / float(self.lcanvas.w)
        sy = fh / float(self.lcanvas.h)
        dx = cv2.resize(self.lcanvas.disp_x, (fw, fh), interpolation=cv2.INTER_CUBIC) * sx
        dy = cv2.resize(self.lcanvas.disp_y, (fw, fh), interpolation=cv2.INTER_CUBIC) * sy
        return apply_liquify_field(self.full_src, dx, dy)


# ---------------------------------------------------------------------------
# 5. Select and Mask Studio Dialog
# ---------------------------------------------------------------------------
class SelectAndMaskDialog(QDialog):
    def __init__(self, rgba: np.ndarray, mask: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select and Mask — Hair & Edge Refinement")
        self.resize(780, 480)
        self.rgba = rgba
        self.mask = mask
        self.prev_img = _downscale_for_preview(rgba, 480)
        self.prev_mask = cv2.resize(mask, (self.prev_img.shape[1], self.prev_img.shape[0]))

        lay = QHBoxLayout(self)
        self.preview = _make_preview_label(460, 400)
        lay.addWidget(self.preview, 1)

        right = QVBoxLayout()
        f = QFormLayout()
        self.cmb_view = QComboBox(); self.cmb_view.addItems(["Rubylith Overlay", "On Black", "Black & White Matte"])
        self.cmb_view.currentIndexChanged.connect(self._update)
        self.sl_sm = QSlider(Qt.Orientation.Horizontal); self.sl_sm.setRange(0, 20); self.sl_sm.setValue(2); self.sl_sm.valueChanged.connect(self._update)
        self.sl_fe = QSlider(Qt.Orientation.Horizontal); self.sl_fe.setRange(0, 25); self.sl_fe.setValue(2); self.sl_fe.valueChanged.connect(self._update)
        self.sl_co = QSlider(Qt.Orientation.Horizontal); self.sl_co.setRange(0, 100); self.sl_co.setValue(15); self.sl_co.valueChanged.connect(self._update)
        self.sl_sh = QSlider(Qt.Orientation.Horizontal); self.sl_sh.setRange(-15, 15); self.sl_sh.setValue(0); self.sl_sh.valueChanged.connect(self._update)
        self.chk_dec = QCheckBox("Decontaminate Colors (Hair Fringe)")
        self.chk_dec.toggled.connect(self._update)

        f.addRow("View Mode:", self.cmb_view)
        f.addRow("Smooth:", self.sl_sm)
        f.addRow("Feather:", self.sl_fe)
        f.addRow("Contrast:", self.sl_co)
        f.addRow("Shift Edge:", self.sl_sh)
        f.addRow(self.chk_dec)
        right.addLayout(f)
        right.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)
        self._update()

    def _update(self) -> None:
        m, img = refine_select_and_mask(
            self.prev_img, self.prev_mask,
            smooth=float(self.sl_sm.value()),
            feather=float(self.sl_fe.value()),
            contrast=self.sl_co.value() / 100.0,
            shift_edge=float(self.sl_sh.value()),
            decontaminate=self.chk_dec.isChecked(),
        )
        vm = self.cmb_view.currentText()
        if vm == "Black & White Matte":
            u = (m * 255).astype(np.uint8)
            vis = np.dstack([u, u, u, np.full_like(u, 255)])
        elif vm == "On Black":
            vis = img.copy()
            vis[..., :3] = (img[..., :3].astype(np.float32) * m[..., None]).astype(np.uint8)
        else:
            vis = img.copy()
            inv = (1.0 - m)[..., None] * 0.55
            vis[..., :3] = np.clip(img[..., :3].astype(np.float32) * (1.0 - inv) + np.array([255, 35, 80], np.float32) * inv, 0, 255).astype(np.uint8)
        _set_preview(self.preview, vis)

    def result_mask_and_image(self) -> Tuple[np.ndarray, np.ndarray]:
        return refine_select_and_mask(
            self.rgba, self.mask,
            smooth=float(self.sl_sm.value()),
            feather=float(self.sl_fe.value()),
            contrast=self.sl_co.value() / 100.0,
            shift_edge=float(self.sl_sh.value()),
            decontaminate=self.chk_dec.isChecked(),
        )


# ---------------------------------------------------------------------------
# 6. Sky Replacement Dialog
# ---------------------------------------------------------------------------
class SkyReplacementDialog(QDialog):
    def __init__(self, rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sky Replacement (One-Step)")
        self.resize(780, 460)
        self.src = rgba
        self.prev_src = _downscale_for_preview(rgba, 480)
        self.custom_sky: Optional[np.ndarray] = None

        lay = QHBoxLayout(self)
        self.preview = _make_preview_label(460, 380)
        lay.addWidget(self.preview, 1)

        right = QVBoxLayout()
        f = QFormLayout()
        self.cmb_sky = QComboBox(); self.cmb_sky.addItems(SKY_PRESETS)
        self.cmb_sky.currentIndexChanged.connect(self._update)
        self.sl_shift = QSlider(Qt.Orientation.Horizontal); self.sl_shift.setRange(-10, 10); self.sl_shift.setValue(0); self.sl_shift.valueChanged.connect(self._update)
        self.sl_relight = QSlider(Qt.Orientation.Horizontal); self.sl_relight.setRange(0, 100); self.sl_relight.setValue(35); self.sl_relight.valueChanged.connect(self._update)
        self.sl_temp = QSlider(Qt.Orientation.Horizontal); self.sl_temp.setRange(-100, 100); self.sl_temp.setValue(0); self.sl_temp.valueChanged.connect(self._update)

        f.addRow("Sky Preset:", self.cmb_sky)
        f.addRow("Shift Edge:", self.sl_shift)
        f.addRow("Relight Scene:", self.sl_relight)
        f.addRow("Temperature:", self.sl_temp)
        right.addLayout(f)

        b_custom = QPushButton("Load Custom Sky Image…")
        b_custom.clicked.connect(self._load_sky)
        right.addWidget(b_custom)
        right.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)
        self._update()

    def _load_sky(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Sky Image", "", "Images (*.png *.jpg *.jpeg *.webp *.tif)")
        if path:
            self.custom_sky = load_image_rgba(path)
            self._update()

    def _update(self) -> None:
        res = replace_sky(
            self.prev_src,
            sky_preset=self.cmb_sky.currentText(),
            custom_sky=self.custom_sky,
            shift_edge=float(self.sl_shift.value()),
            relight_fg=self.sl_relight.value() / 100.0,
            temperature=self.sl_temp.value() / 100.0,
        )
        _set_preview(self.preview, res)

    def result_image(self) -> np.ndarray:
        return replace_sky(
            self.src,
            sky_preset=self.cmb_sky.currentText(),
            custom_sky=self.custom_sky,
            shift_edge=float(self.sl_shift.value()),
            relight_fg=self.sl_relight.value() / 100.0,
            temperature=self.sl_temp.value() / 100.0,
        )


# ---------------------------------------------------------------------------
# 7. Neural Filters Dialog
# ---------------------------------------------------------------------------
class NeuralFiltersDialog(QDialog):
    def __init__(self, rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Neural Filters Studio")
        self.resize(780, 480)
        self.src = rgba
        self.prev_src = _downscale_for_preview(rgba, 460)

        lay = QHBoxLayout(self)
        self.preview = _make_preview_label(450, 390)
        lay.addWidget(self.preview, 1)

        right = QVBoxLayout()
        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(["Colorize", "Style Transfer", "Smart Portrait", "Depth Blur", "Super Zoom (2x Upscale)"])
        self.cmb_filter.currentIndexChanged.connect(self._update)
        right.addWidget(QLabel("Neural Filter:"))
        right.addWidget(self.cmb_filter)

        f = QFormLayout()
        self.cmb_style = QComboBox()
        self.cmb_style.addItems(["Watercolor", "Pencil Sketch", "Ink Comic", "Impressionist Oil", "Cyberpunk Neon", "Vintage Film"])
        self.cmb_style.currentIndexChanged.connect(self._update)
        self.sl_p1 = QSlider(Qt.Orientation.Horizontal); self.sl_p1.setRange(0, 100); self.sl_p1.setValue(65); self.sl_p1.valueChanged.connect(self._update)
        self.sl_p2 = QSlider(Qt.Orientation.Horizontal); self.sl_p2.setRange(-100, 100); self.sl_p2.setValue(15); self.sl_p2.valueChanged.connect(self._update)
        f.addRow("Style Preset:", self.cmb_style)
        f.addRow("Intensity / Smooth:", self.sl_p1)
        f.addRow("Warmth / Light / Focal:", self.sl_p2)
        right.addLayout(f)
        right.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)
        self._update()

    def _run_on(self, img: np.ndarray) -> np.ndarray:
        nm = self.cmb_filter.currentText()
        p1 = self.sl_p1.value() / 100.0
        p2 = self.sl_p2.value() / 100.0
        if nm == "Colorize":
            return neural_filter_colorize(img, warmth=p2, saturation=p1)
        if nm == "Style Transfer":
            return neural_filter_style_transfer(img, style=self.cmb_style.currentText(), strength=p1)
        if nm == "Smart Portrait":
            return neural_filter_smart_portrait(img, skin_smooth=p1, light_angle=p2 * 90.0, glow=0.22, eye_pop=0.35)
        if nm == "Depth Blur":
            return neural_filter_depth_blur(img, focal_y=0.5 + p2 * 0.45, blur_strength=max(2.0, p1 * 22.0))
        return neural_filter_super_zoom(img, scale=2)

    def _update(self) -> None:
        _set_preview(self.preview, self._run_on(self.prev_src))

    def result_image(self) -> np.ndarray:
        return self._run_on(self.src)


# ---------------------------------------------------------------------------
# 9. PhotoMerge, Auto-Align/Blend, Merge to HDR Pro & Focus Stack Dialog
# ---------------------------------------------------------------------------
class PhotoMergeDialog(QDialog):
    def __init__(self, doc: KinoDocument, initial_mode: str = "Photomerge Panorama", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PhotoMerge · Auto-Align/Blend · Merge to HDR Pro · Focus Stack")
        self.resize(620, 440)
        self.doc = doc
        self.file_paths: List[str] = []
        self.result_rgba: Optional[np.ndarray] = None

        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems([
            "Photomerge Panorama",
            "Merge to HDR Pro (Exposure Fusion)",
            "Focus Stack (Macro Sharpness)",
            "Auto-Align & Auto-Blend (Group Shot)",
        ])
        self.cmb_mode.setCurrentText(initial_mode)
        f.addRow("Operation:", self.cmb_mode)
        self.chk_use_layers = QCheckBox("Use visible raster layers from current document (if no external files added)")
        self.chk_use_layers.setChecked(True)
        f.addRow(self.chk_use_layers)

        # HDR Pro controls
        self.sl_exp = QSlider(Qt.Orientation.Horizontal); self.sl_exp.setRange(-200, 200); self.sl_exp.setValue(0)
        self.sl_det = QSlider(Qt.Orientation.Horizontal); self.sl_det.setRange(0, 100); self.sl_det.setValue(35)
        self.sl_vib = QSlider(Qt.Orientation.Horizontal); self.sl_vib.setRange(0, 100); self.sl_vib.setValue(25)
        f.addRow("HDR Exposure:", self.sl_exp)
        f.addRow("HDR Detail:", self.sl_det)
        f.addRow("HDR Vibrance:", self.sl_vib)
        lay.addLayout(f)

        self.list_files = QListWidget()
        lay.addWidget(self.list_files, 1)

        r = QHBoxLayout()
        b_add = QPushButton("+ Add Source Photos…")
        b_add.clicked.connect(self._add_files)
        b_clr = QPushButton("Clear")
        b_clr.clicked.connect(lambda: (self.file_paths.clear(), self.list_files.clear()))
        r.addWidget(b_add)
        r.addWidget(b_clr)
        lay.addLayout(r)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._execute)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select Photos to Merge", "", "Images (*.png *.jpg *.jpeg *.tif *.tiff *.webp)")
        for f in files:
            self.file_paths.append(f)
            self.list_files.addItem(os.path.basename(f))

    def _execute(self) -> None:
        imgs: List[np.ndarray] = []
        if self.file_paths:
            for p in self.file_paths:
                imgs.append(load_image_rgba(p))
        elif self.chk_use_layers.isChecked():
            for lyr in self.doc.layers:
                if lyr.visible and lyr.image is not None:
                    imgs.append(lyr.image.copy())
        if not imgs:
            QMessageBox.warning(self, "PhotoMerge", "Please add 2+ photos or have raster layers available.")
            return
        mode = self.cmb_mode.currentText()
        if mode == "Photomerge Panorama":
            self.result_rgba = photomerge_panorama(imgs)
        elif mode == "Merge to HDR Pro (Exposure Fusion)":
            self.result_rgba = merge_to_hdr_pro(
                imgs,
                exposure=self.sl_exp.value() / 100.0,
                detail=self.sl_det.value() / 100.0,
                vibrance=self.sl_vib.value() / 100.0,
            )
        elif mode == "Focus Stack (Macro Sharpness)":
            self.result_rgba = focus_stack_images(imgs)
        else:
            aligned = auto_align_layers(imgs)
            self.result_rgba = auto_blend_layers(aligned)
        self.accept()


# ---------------------------------------------------------------------------
# 10. Pattern Maker & Texture Synthesis Dialog
# ---------------------------------------------------------------------------
class PatternTextureDialog(QDialog):
    def __init__(self, rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pattern Maker & Texture Synthesis")
        self.resize(740, 440)
        self.src = rgba
        self.prev_src = _downscale_for_preview(rgba, 360)

        lay = QHBoxLayout(self)
        self.preview = _make_preview_label(400, 360)
        lay.addWidget(self.preview, 1)

        right = QVBoxLayout()
        f = QFormLayout()
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems([
            "Pattern Maker: Offset Seamless Blend",
            "Pattern Maker: Mirror Tile",
            "Pattern Maker: Brick Offset",
            "Synthesize: Brushed Metal",
            "Synthesize: Marble Veins",
            "Synthesize: Wood Grain",
            "Synthesize: Canvas Fabric",
            "Synthesize: Carbon Fiber",
            "Synthesize: Paper Grain",
        ])
        self.cmb_mode.currentIndexChanged.connect(self._update)
        self.sp_seed = QSpinBox(); self.sp_seed.setRange(1, 9999); self.sp_seed.setValue(42)
        self.sp_seed.valueChanged.connect(self._update)
        f.addRow("Generator:", self.cmb_mode)
        f.addRow("Seed:", self.sp_seed)
        right.addLayout(f)
        right.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)
        self._update()

    def _run_on(self, img: np.ndarray) -> np.ndarray:
        m = self.cmb_mode.currentText()
        h, w = img.shape[:2]
        if m.startswith("Synthesize: "):
            return synthesize_procedural_texture(w, h, m.replace("Synthesize: ", ""), seed=self.sp_seed.value())
        if "Mirror" in m:
            return make_seamless_pattern(img, mode="Mirror Tile")
        if "Brick" in m:
            return make_seamless_pattern(img, mode="Brick")
        return make_seamless_pattern(img, mode="Offset Blend")

    def _update(self) -> None:
        tile = self._run_on(self.prev_src)
        # Show 2x2 tiled preview to verify seamlessness!
        th, tw = tile.shape[:2]
        half = cv2.resize(tile, (max(16, tw // 2), max(16, th // 2)))
        tiled = np.tile(half, (2, 2, 1))
        _set_preview(self.preview, tiled)

    def result_image(self) -> np.ndarray:
        return self._run_on(self.src)


# ---------------------------------------------------------------------------
# 11. Lens Correction & Vanishing Point Dialog
# ---------------------------------------------------------------------------
class LensAndVanishingDialog(QDialog):
    def __init__(self, rgba: np.ndarray, tab: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lens Correction & Vanishing Point")
        self.resize(780, 480)
        self.src = rgba
        self.prev_src = _downscale_for_preview(rgba, 460)
        self.tile_src: np.ndarray = synthesize_procedural_texture(256, 256, "Marble Veins")

        lay = QHBoxLayout(self)
        self.preview = _make_preview_label(450, 390)
        lay.addWidget(self.preview, 1)

        right = QVBoxLayout()
        self.tabs = QTabWidget()

        # Tab 0: Lens Correction
        t0 = QWidget()
        f0 = QFormLayout(t0)
        self.sl_k1 = QSlider(Qt.Orientation.Horizontal); self.sl_k1.setRange(-50, 50); self.sl_k1.valueChanged.connect(self._update)
        self.sl_vt = QSlider(Qt.Orientation.Horizontal); self.sl_vt.setRange(-100, 100); self.sl_vt.valueChanged.connect(self._update)
        self.sl_ht = QSlider(Qt.Orientation.Horizontal); self.sl_ht.setRange(-100, 100); self.sl_ht.valueChanged.connect(self._update)
        self.sl_rot = QSlider(Qt.Orientation.Horizontal); self.sl_rot.setRange(-180, 180); self.sl_rot.valueChanged.connect(self._update)
        self.sl_vig = QSlider(Qt.Orientation.Horizontal); self.sl_vig.setRange(-100, 100); self.sl_vig.valueChanged.connect(self._update)
        f0.addRow("Barrel / Pincushion:", self.sl_k1)
        f0.addRow("Vertical Perspective:", self.sl_vt)
        f0.addRow("Horizontal Perspective:", self.sl_ht)
        f0.addRow("Straighten (°×0.1):", self.sl_rot)
        f0.addRow("Vignette Removal:", self.sl_vig)
        self.tabs.addTab(t0, "Lens Correction")

        # Tab 1: Vanishing Point Perspective Tiling
        t1 = QWidget()
        f1 = QFormLayout(t1)
        self.cmb_vp_plane = QComboBox()
        self.cmb_vp_plane.addItems(["Floor Plane (Bottom)", "Left Wall Plane", "Right Wall Plane", "Center Billboard"])
        self.cmb_vp_plane.currentIndexChanged.connect(self._update)
        self.sp_rx = QSpinBox(); self.sp_rx.setRange(1, 12); self.sp_rx.setValue(4); self.sp_rx.valueChanged.connect(self._update)
        self.sp_ry = QSpinBox(); self.sp_ry.setRange(1, 12); self.sp_ry.setValue(4); self.sp_ry.valueChanged.connect(self._update)
        self.sl_vpop = QSlider(Qt.Orientation.Horizontal); self.sl_vpop.setRange(10, 100); self.sl_vpop.setValue(82); self.sl_vpop.valueChanged.connect(self._update)
        b_tile = QPushButton("Load Custom Tile / Clone Image…")
        b_tile.clicked.connect(self._load_tile)
        f1.addRow("Perspective Plane:", self.cmb_vp_plane)
        f1.addRow("Tile Repeat X:", self.sp_rx)
        f1.addRow("Tile Repeat Y:", self.sp_ry)
        f1.addRow("Blend Opacity:", self.sl_vpop)
        f1.addRow(b_tile)
        self.tabs.addTab(t1, "Vanishing Point")
        self.tabs.setCurrentIndex(tab)
        self.tabs.currentChanged.connect(self._update)

        right.addWidget(self.tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)
        self._update()

    def _load_tile(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Select Tile/Texture", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if p:
            self.tile_src = load_image_rgba(p)
            self._update()

    def _quad_for(self, w: int, h: int) -> List[Tuple[float, float]]:
        pl = self.cmb_vp_plane.currentText()
        if pl.startswith("Floor"):
            return [(w * 0.22, h * 0.62), (w * 0.78, h * 0.62), (w * 0.98, h * 0.98), (w * 0.02, h * 0.98)]
        if pl.startswith("Left"):
            return [(w * 0.04, h * 0.08), (w * 0.45, h * 0.24), (w * 0.45, h * 0.78), (w * 0.04, h * 0.94)]
        if pl.startswith("Right"):
            return [(w * 0.55, h * 0.24), (w * 0.96, h * 0.08), (w * 0.96, h * 0.94), (w * 0.55, h * 0.78)]
        return [(w * 0.20, h * 0.16), (w * 0.80, h * 0.22), (w * 0.78, h * 0.76), (w * 0.22, h * 0.82)]

    def _run_on(self, img: np.ndarray) -> np.ndarray:
        if self.tabs.currentIndex() == 0:
            return apply_lens_correction(
                img,
                k1=self.sl_k1.value() / 100.0,
                vertical_tilt=self.sl_vt.value() / 100.0,
                horizontal_tilt=self.sl_ht.value() / 100.0,
                rotate_deg=self.sl_rot.value() * 0.1,
                vignette_fix=self.sl_vig.value() / 100.0,
            )
        h, w = img.shape[:2]
        return vanishing_point_tile_or_paste(
            img,
            self._quad_for(w, h),
            self.tile_src,
            repeat_x=self.sp_rx.value(),
            repeat_y=self.sp_ry.value(),
            opacity=self.sl_vpop.value() / 100.0,
        )

    def _update(self) -> None:
        _set_preview(self.preview, self._run_on(self.prev_src))

    def result_image(self) -> np.ndarray:
        return self._run_on(self.src)


# ---------------------------------------------------------------------------
# 12. Light 3D & Texturing Studio Dialog
# ---------------------------------------------------------------------------
class Studio3DDialog(QDialog):
    def __init__(self, width: int, height: int, texture: Optional[np.ndarray], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Light 3D & Texturing Studio")
        self.resize(740, 460)
        self.out_w, self.out_h = width, height
        self.texture = texture

        lay = QHBoxLayout(self)
        self.preview = _make_preview_label(400, 380)
        lay.addWidget(self.preview, 1)

        right = QVBoxLayout()
        f = QFormLayout()
        self.cmb_shape = QComboBox(); self.cmb_shape.addItems(["Sphere", "Cube", "Cylinder", "Torus", "Extruded Plate"])
        self.cmb_shape.currentIndexChanged.connect(self._update)
        self.chk_tex = QCheckBox("Wrap Active Layer as 3D Texture")
        self.chk_tex.setChecked(texture is not None)
        self.chk_tex.toggled.connect(self._update)
        self.sl_rx = QSlider(Qt.Orientation.Horizontal); self.sl_rx.setRange(-180, 180); self.sl_rx.setValue(22); self.sl_rx.valueChanged.connect(self._update)
        self.sl_ry = QSlider(Qt.Orientation.Horizontal); self.sl_ry.setRange(-180, 180); self.sl_ry.setValue(-30); self.sl_ry.valueChanged.connect(self._update)
        self.sl_met = QSlider(Qt.Orientation.Horizontal); self.sl_met.setRange(0, 100); self.sl_met.setValue(45); self.sl_met.valueChanged.connect(self._update)
        f.addRow("3D Primitive:", self.cmb_shape)
        f.addRow(self.chk_tex)
        f.addRow("Rotate X:", self.sl_rx)
        f.addRow("Rotate Y:", self.sl_ry)
        f.addRow("Metallic Gloss:", self.sl_met)
        right.addLayout(f)
        right.addStretch(1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)
        self._update()

    def _render(self, w: int, h: int) -> np.ndarray:
        return render_3d_object(
            w, h,
            shape=self.cmb_shape.currentText(),
            texture_rgba=self.texture if self.chk_tex.isChecked() else None,
            rot_x=float(self.sl_rx.value()),
            rot_y=float(self.sl_ry.value()),
            metallic=self.sl_met.value() / 100.0,
        )

    def _update(self) -> None:
        _set_preview(self.preview, self._render(380, 360))

    def result_image(self) -> np.ndarray:
        return self._render(self.out_w, self.out_h)


# ---------------------------------------------------------------------------
# 13. Print Prep, Soft-Proofing & CMYK PDF Dialog
# ---------------------------------------------------------------------------
class PrintPrepDialog(QDialog):
    def __init__(self, doc: KinoDocument, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Print Prep — CMYK, Color Profiles, Soft-Proof & Printer Marks")
        self.doc = doc
        self.resize(460, 410)
        lay = QVBoxLayout(self)
        f = QFormLayout()

        self.cmb_mode = QComboBox(); self.cmb_mode.addItems(COLOR_MODES); self.cmb_mode.setCurrentText(doc.color_mode)
        self.cmb_prof = QComboBox(); self.cmb_prof.addItems(COLOR_PROFILES); self.cmb_prof.setCurrentText(doc.color_profile)
        self.chk_sp = QCheckBox("Enable Soft-Proofing Preview"); self.chk_sp.setChecked(doc.print_settings.soft_proof)
        self.chk_gw = QCheckBox("Show Out-of-Gamut Warning"); self.chk_gw.setChecked(doc.print_settings.gamut_warning)
        self.sp_bleed = QDoubleSpinBox(); self.sp_bleed.setRange(0.0, 25.0); self.sp_bleed.setValue(doc.print_settings.bleed_mm); self.sp_bleed.setSuffix(" mm")
        self.chk_crop = QCheckBox("Crop Marks"); self.chk_crop.setChecked(doc.print_settings.crop_marks)
        self.chk_bm = QCheckBox("Bleed Marks"); self.chk_bm.setChecked(doc.print_settings.bleed_marks)
        self.chk_reg = QCheckBox("Registration Targets"); self.chk_reg.setChecked(doc.print_settings.registration_marks)
        self.chk_bar = QCheckBox("CMYK Color Bars"); self.chk_bar.setChecked(doc.print_settings.color_bars)
        self.chk_info = QCheckBox("Page Information"); self.chk_info.setChecked(doc.print_settings.page_info)

        f.addRow("Color Mode:", self.cmb_mode)
        f.addRow("Color Profile:", self.cmb_prof)
        f.addRow(self.chk_sp)
        f.addRow(self.chk_gw)
        f.addRow("Bleed Margin:", self.sp_bleed)
        f.addRow(self.chk_crop)
        f.addRow(self.chk_bm)
        f.addRow(self.chk_reg)
        f.addRow(self.chk_bar)
        f.addRow(self.chk_info)
        lay.addLayout(f)

        b_pdf = QPushButton("Export Print-Ready CMYK PDF…")
        b_pdf.setObjectName("PrimaryButton")
        b_pdf.clicked.connect(self._export_pdf)
        lay.addWidget(b_pdf)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._commit)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _apply_to_doc(self) -> None:
        self.doc.set_color_mode(self.cmb_mode.currentText())
        self.doc.color_profile = self.cmb_prof.currentText()
        ps = self.doc.print_settings
        ps.soft_proof = self.chk_sp.isChecked()
        ps.soft_proof_profile = self.cmb_prof.currentText()
        ps.gamut_warning = self.chk_gw.isChecked()
        ps.bleed_mm = self.sp_bleed.value()
        ps.crop_marks = self.chk_crop.isChecked()
        ps.bleed_marks = self.chk_bm.isChecked()
        ps.registration_marks = self.chk_reg.isChecked()
        ps.color_bars = self.chk_bar.isChecked()
        ps.page_info = self.chk_info.isChecked()

    def _export_pdf(self) -> None:
        self._apply_to_doc()
        path, _ = QFileDialog.getSaveFileName(self, "Export Print-Ready PDF", "print_ready.pdf", "PDF (*.pdf)")
        if path:
            export_print_pdf(self.doc, path)
            QMessageBox.information(self, "Print PDF Exported", f"Saved print-ready PDF:\n{path}")

    def _commit(self) -> None:
        self._apply_to_doc()
        self.accept()


# ---------------------------------------------------------------------------
# 14. Slicing & Save for Web Multi-Scale Export Dialog
# ---------------------------------------------------------------------------
class SaveForWebSlicesDialog(QDialog):
    def __init__(self, doc: KinoDocument, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Slicing & Multi-Scale Web Export")
        self.doc = doc
        self.resize(520, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Configured Slices ({len(doc.slices)}) — falls back to Artboards if empty:"))
        self.lst = QListWidget()
        for sl in doc.slices:
            self.lst.addItem(f"{sl.name}  [{sl.x},{sl.y} {sl.width}×{sl.height}]  {sl.fmt}  {sl.scales}")
        lay.addWidget(self.lst, 1)

        f = QFormLayout()
        self.cmb_fmt = QComboBox(); self.cmb_fmt.addItems(["PNG", "JPEG", "WebP"])
        self.sp_qual = QSpinBox(); self.sp_qual.setRange(20, 100); self.sp_qual.setValue(90)
        self.chk_1x = QCheckBox("1x"); self.chk_1x.setChecked(True)
        self.chk_2x = QCheckBox("2x"); self.chk_2x.setChecked(True)
        self.chk_3x = QCheckBox("3x"); self.chk_3x.setChecked(False)
        sc_w = QWidget(); sh = QHBoxLayout(sc_w); sh.setContentsMargins(0, 0, 0, 0)
        for c in (self.chk_1x, self.chk_2x, self.chk_3x):
            sh.addWidget(c)
        f.addRow("Default Format:", self.cmb_fmt)
        f.addRow("Quality:", self.sp_qual)
        f.addRow("Export Scales:", sc_w)
        lay.addLayout(f)

        b_exp = QPushButton("Export All Slices / Assets…")
        b_exp.setObjectName("PrimaryButton")
        b_exp.clicked.connect(self._export)
        lay.addWidget(b_exp)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _export(self) -> None:
        scales = [s for s, chk in [(1.0, self.chk_1x), (2.0, self.chk_2x), (3.0, self.chk_3x)] if chk.isChecked()] or [1.0]
        for sl in self.doc.slices:
            sl.fmt = self.cmb_fmt.currentText()
            sl.scales = scales
        out_dir = QFileDialog.getExistingDirectory(self, "Choose Asset Output Folder")
        if out_dir:
            written = export_slices_multiscale(self.doc, out_dir, quality=self.sp_qual.value())
            QMessageBox.information(self, "Slices Exported", f"Exported {len(written)} web asset files to:\n{out_dir}")


# ---------------------------------------------------------------------------
# 15. Variables & Data Sets Dialog (Spreadsheet Batch Generator)
# ---------------------------------------------------------------------------
class VariablesDataSetsDialog(QDialog):
    def __init__(self, doc: KinoDocument, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Variables & Data Sets — Spreadsheet Batch Generator")
        self.doc = doc
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Bind layer 'Variable' names (in Properties panel, e.g. Headline, Subtitle) to CSV columns:"))

        b_load = QPushButton("Load CSV Spreadsheet…")
        b_load.clicked.connect(self._load_csv)
        lay.addWidget(b_load)

        self.lbl_info = QLabel(f"Loaded Data Sets: {len(doc.data_sets)}")
        lay.addWidget(self.lbl_info)

        self.lst_rows = QListWidget()
        self._refresh_rows()
        lay.addWidget(self.lst_rows, 1)

        row = QHBoxLayout()
        self.cmb_fmt = QComboBox(); self.cmb_fmt.addItems(["PNG", "JPEG", "PDF", "KSD"])
        b_gen = QPushButton("Batch Generate All Variations…")
        b_gen.setObjectName("PrimaryButton")
        b_gen.clicked.connect(self._batch_export)
        row.addWidget(QLabel("Format:"))
        row.addWidget(self.cmb_fmt)
        row.addWidget(b_gen, 1)
        lay.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select CSV Spreadsheet", "", "CSV (*.csv)")
        if path:
            cols, rows = load_csv_datasets(path)
            self.doc.data_sets = rows
            self.lbl_info.setText(f"Loaded {len(rows)} rows · Columns: {', '.join(cols)}")
            self._refresh_rows()

    def _refresh_rows(self) -> None:
        self.lst_rows.clear()
        for i, r in enumerate(self.doc.data_sets, start=1):
            self.lst_rows.addItem(f"Set #{i}: " + " | ".join(f"{k}={v}" for k, v in r.items()))

    def _batch_export(self) -> None:
        if not self.doc.data_sets:
            QMessageBox.warning(self, "Data Sets", "Please load a CSV spreadsheet first.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Choose Output Folder for Generated Designs")
        if out_dir:
            files = batch_export_datasets(self.doc, out_dir, fmt=self.cmb_fmt.currentText())
            QMessageBox.information(self, "Batch Complete", f"Generated {len(files)} design variations in:\n{out_dir}")


# ---------------------------------------------------------------------------
# 16. Automation: Actions, Image Processor, Script Events Manager & Python Console
# ---------------------------------------------------------------------------
class AutomationScriptsDialog(QDialog):
    def __init__(
        self,
        action_mgr: ActionManager,
        run_action_cb: Callable[[str], None],
        run_script_cb: Callable[[str], str],
        initial_tab: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Automation · Actions · Image Processor · Script Events · Python")
        self.resize(680, 480)
        self.am = action_mgr
        self.run_action_cb = run_action_cb
        self.run_script_cb = run_script_cb

        lay = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 0: Actions Recorder
        t0 = QWidget()
        v0 = QVBoxLayout(t0)
        self.lst_act = QListWidget()
        self._refresh_actions()
        v0.addWidget(self.lst_act, 1)
        r0 = QHBoxLayout()
        b_play = QPushButton("▶ Play Selected Action")
        b_play.setObjectName("PrimaryButton")
        b_play.clicked.connect(self._play_selected)
        b_rec = QPushButton("⏺ Start/Stop Recording")
        b_rec.clicked.connect(self._toggle_rec)
        r0.addWidget(b_play)
        r0.addWidget(b_rec)
        v0.addLayout(r0)
        tabs.addTab(t0, "Actions (.ksa)")

        # Tab 1: Image Processor
        t1 = QWidget()
        f1 = QFormLayout(t1)
        self.ed_src = QLineEdit()
        b_src = QPushButton("Browse…"); b_src.clicked.connect(lambda: self._pick_dir(self.ed_src))
        self.ed_dst = QLineEdit()
        b_dst = QPushButton("Browse…"); b_dst.clicked.connect(lambda: self._pick_dir(self.ed_dst))
        self.chk_jpg = QCheckBox("JPEG"); self.chk_jpg.setChecked(True)
        self.chk_png = QCheckBox("PNG"); self.chk_png.setChecked(True)
        self.chk_webp = QCheckBox("WebP")
        self.chk_tif = QCheckBox("TIFF")
        self.sp_mw = QSpinBox(); self.sp_mw.setRange(0, 8192); self.sp_mw.setValue(1920)
        self.sp_mh = QSpinBox(); self.sp_mh.setRange(0, 8192); self.sp_mh.setValue(1080)
        self.ed_copy = QLineEdit("© KinoSuite Studio")
        b_proc = QPushButton("Run Batch Image Processor")
        b_proc.setObjectName("PrimaryButton")
        b_proc.clicked.connect(self._run_img_proc)

        f1.addRow("Source Folder:", self._row(self.ed_src, b_src))
        f1.addRow("Output Folder:", self._row(self.ed_dst, b_dst))
        f1.addRow("Formats:", self._row(self.chk_jpg, self.chk_png, self.chk_webp, self.chk_tif))
        f1.addRow("Resize to Fit (W×H):", self._row(self.sp_mw, self.sp_mh))
        f1.addRow("Copyright Stamp:", self.ed_copy)
        f1.addRow(b_proc)
        tabs.addTab(t1, "Image Processor")

        # Tab 2: Script Events Manager
        t2 = QWidget()
        f2 = QFormLayout(t2)
        self.ev_edits: Dict[str, QLineEdit] = {}
        for ev, lbl in [("on_open", "On Document Open:"), ("on_save", "On Document Save:"), ("on_export", "On Export:"), ("on_new", "On New Document:")]:
            ed = QLineEdit(self.am.script_events.get(ev, ""))
            ed.setPlaceholderText("Python one-liner or .py script path (e.g. app.status('Saved!'))")
            f2.addRow(lbl, ed)
            self.ev_edits[ev] = ed
        b_sev = QPushButton("Save Event Bindings")
        b_sev.setObjectName("PrimaryButton")
        b_sev.clicked.connect(self._save_events)
        f2.addRow(b_sev)
        tabs.addTab(t2, "Script Events Manager")

        # Tab 3: Python Scripting Console
        t3 = QWidget()
        v3 = QVBoxLayout(t3)
        self.ed_code = QPlainTextEdit(
            "# KinoShop Python Scripting API\n"
            "# Available: doc, app, np, cv2\n"
            "print(f'Document: {doc.name} ({doc.width}x{doc.height}), Layers: {len(doc.layers)}')\n"
            "doc.add_adjustment_layer('Vibrance', {'vibrance': 25, 'saturation': 10})\n"
            "app.refresh_all()\n"
        )
        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        self.ed_out.setMaximumHeight(110)
        b_run = QPushButton("▶ Execute Python Script")
        b_run.setObjectName("PrimaryButton")
        b_run.clicked.connect(self._exec_script)
        v3.addWidget(self.ed_code, 1)
        v3.addWidget(b_run)
        v3.addWidget(self.ed_out)
        tabs.addTab(t3, "Python Scripting")

        tabs.setCurrentIndex(initial_tab)
        lay.addWidget(tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _row(self, *widgets) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for wg in widgets:
            h.addWidget(wg)
        return w

    def _pick_dir(self, ed: QLineEdit) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose Folder")
        if d:
            ed.setText(d)

    def _refresh_actions(self) -> None:
        self.lst_act.clear()
        for nm, steps in self.am.actions.items():
            self.lst_act.addItem(f"{nm}  ({len(steps)} steps)")

    def _play_selected(self) -> None:
        it = self.lst_act.currentItem()
        if it:
            nm = it.text().split("  (")[0]
            self.run_action_cb(nm)

    def _toggle_rec(self) -> None:
        if self.am.recording:
            nm = self.am.stop_recording()
            self._refresh_actions()
            QMessageBox.information(self, "Action Saved", f"Stopped recording action: {nm}")
        else:
            self.am.start_recording(f"Custom Action {len(self.am.actions) + 1}")
            QMessageBox.information(self, "Recording Started", "Now recording filter & adjustment steps. Return here to Stop.")

    def _run_img_proc(self) -> None:
        fmts = [f for f, c in [("JPEG", self.chk_jpg), ("PNG", self.chk_png), ("WebP", self.chk_webp), ("TIFF", self.chk_tif)] if c.isChecked()]
        if not self.ed_src.text() or not self.ed_dst.text() or not fmts:
            QMessageBox.warning(self, "Image Processor", "Select source folder, output folder, and at least one format.")
            return
        files = run_image_processor(
            self.ed_src.text(), self.ed_dst.text(), fmts,
            max_w=self.sp_mw.value(), max_h=self.sp_mh.value(), copyright_text=self.ed_copy.text(),
        )
        QMessageBox.information(self, "Image Processor Complete", f"Processed {len(files)} output files.")

    def _save_events(self) -> None:
        for ev, ed in self.ev_edits.items():
            self.am.script_events[ev] = ed.text().strip()
        self.am.save_events()
        QMessageBox.information(self, "Script Events Saved", "Automatic event scripts updated.")

    def _exec_script(self) -> None:
        res = self.run_script_cb(self.ed_code.toPlainText())
        self.ed_out.setPlainText(res)


# ---------------------------------------------------------------------------
# 17. Scanning, Contact Sheet II & Picture Package Dialog
# ---------------------------------------------------------------------------
class ScanContactSheetDialog(QDialog):
    def __init__(self, current_rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scanning · Contact Sheet II · Picture Package")
        self.resize(620, 430)
        self.current_rgba = current_rgba
        self.output_images: List[Tuple[str, np.ndarray]] = []

        lay = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 0: Scanning & Auto-Straighten / Split
        t0 = QWidget()
        v0 = QVBoxLayout(t0)
        b_wia = QPushButton("Acquire from Windows Scanner (WIA)…")
        b_wia.setObjectName("PrimaryButton")
        b_wia.clicked.connect(self._scan_wia)
        b_str = QPushButton("Auto-Straighten Current Document / Scan")
        b_str.clicked.connect(self._auto_straighten)
        b_spl = QPushButton("Crop & Straighten: Split Multiple Scanned Photos into Separate Tabs")
        b_spl.clicked.connect(self._split_scans)
        v0.addWidget(b_wia)
        v0.addWidget(b_str)
        v0.addWidget(b_spl)
        v0.addStretch(1)
        tabs.addTab(t0, "Scanning & Straighten")

        # Tab 1: Contact Sheet II
        t1 = QWidget()
        f1 = QFormLayout(t1)
        self.sp_cols = QSpinBox(); self.sp_cols.setRange(1, 10); self.sp_cols.setValue(4)
        self.sp_rows = QSpinBox(); self.sp_rows.setRange(1, 12); self.sp_rows.setValue(5)
        self.chk_cap = QCheckBox("Show Filename Captions"); self.chk_cap.setChecked(True)
        b_cs = QPushButton("Select Photos & Build Contact Sheet…")
        b_cs.setObjectName("PrimaryButton")
        b_cs.clicked.connect(self._build_cs)
        f1.addRow("Columns:", self.sp_cols)
        f1.addRow("Rows:", self.sp_rows)
        f1.addRow(self.chk_cap)
        f1.addRow(b_cs)
        tabs.addTab(t1, "Contact Sheet II")

        # Tab 2: Picture Package
        t2 = QWidget()
        f2 = QFormLayout(t2)
        self.cmb_pkg = QComboBox()
        self.cmb_pkg.addItems(["1x(5x7) + 2x(3.5x5) + 4x(Wallet)", "2x(5x7)", "4x(4x5)", "9x(Wallet)"])
        b_pp = QPushButton("Generate Picture Package from Current Document")
        b_pp.setObjectName("PrimaryButton")
        b_pp.clicked.connect(self._build_pp)
        f2.addRow("Print Layout:", self.cmb_pkg)
        f2.addRow(b_pp)
        tabs.addTab(t2, "Picture Package")

        lay.addWidget(tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _scan_wia(self) -> None:
        img = scan_from_wia_windows()
        if img is None:
            QMessageBox.information(self, "Windows Scanner (WIA)", "No WIA scanner detected or scan cancelled. You can also open a scanned file and run Auto-Straighten / Split.")
            return
        self.output_images = [("WIA_Scan.ksd", img)]
        self.accept()

    def _auto_straighten(self) -> None:
        deskewed, deg = auto_straighten_scan(self.current_rgba)
        self.output_images = [(f"Straightened_{deg:.1f}deg.ksd", deskewed)]
        self.accept()

    def _split_scans(self) -> None:
        parts = split_scanned_photos(self.current_rgba)
        if not parts:
            QMessageBox.information(self, "Split Scans", "No distinct separate photo borders detected on the current flatbed scan.")
            return
        self.output_images = [(f"Scanned_Photo_{i+1}.ksd", arr) for i, arr in enumerate(parts)]
        self.accept()

    def _build_cs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images for Contact Sheet", "", "Images (*.png *.jpg *.jpeg *.webp *.tif)")
        if not files:
            return
        loaded = [(os.path.basename(f), load_image_rgba(f)) for f in files]
        sheet = build_contact_sheet(loaded, cols=self.sp_cols.value(), rows=self.sp_rows.value(), show_captions=self.chk_cap.isChecked())
        self.output_images = [("Contact_Sheet.ksd", sheet)]
        self.accept()

    def _build_pp(self) -> None:
        pkg = build_picture_package(self.current_rgba, layout=self.cmb_pkg.currentText())
        self.output_images = [("Picture_Package.ksd", pkg)]
        self.accept()


# ---------------------------------------------------------------------------
# 18. Metadata & Content Credentials (KinoC2PA) Dialog
# ---------------------------------------------------------------------------
class MetadataCredentialsDialog(QDialog):
    def __init__(self, doc: KinoDocument, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("File Info, Metadata & Content Credentials (KinoC2PA)")
        self.doc = doc
        self.resize(620, 500)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()

        # Tab 0: Copyright & Camera EXIF
        t0 = QWidget()
        f0 = QFormLayout(t0)
        md = doc.metadata
        self.ed_title = QLineEdit(md.title)
        self.ed_author = QLineEdit(md.author)
        self.cmb_cr = QComboBox(); self.cmb_cr.addItems(["Copyrighted", "Public Domain", "Unknown"]); self.cmb_cr.setCurrentText(md.copyright_status)
        self.ed_notice = QLineEdit(md.copyright_notice)
        self.ed_kw = QLineEdit(md.keywords)
        self.ed_cam = QLineEdit(md.camera_model)
        self.ed_lens = QLineEdit(md.lens)
        self.ed_iso = QLineEdit(md.iso)
        self.ed_ap = QLineEdit(md.aperture)
        f0.addRow("Title:", self.ed_title)
        f0.addRow("Author / Creator:", self.ed_author)
        f0.addRow("Copyright Status:", self.cmb_cr)
        f0.addRow("Copyright Notice:", self.ed_notice)
        f0.addRow("Keywords:", self.ed_kw)
        f0.addRow("Camera Model:", self.ed_cam)
        f0.addRow("Lens:", self.ed_lens)
        f0.addRow("ISO:", self.ed_iso)
        f0.addRow("Aperture:", self.ed_ap)
        tabs.addTab(t0, "Metadata & EXIF")

        # Tab 1: Content Credentials
        t1 = QWidget()
        v1 = QVBoxLayout(t1)
        self.chk_cc = QCheckBox("Attach Content Credentials (KinoC2PA Provenance) on Save & Export")
        self.chk_cc.setChecked(md.content_credentials_enabled)
        v1.addWidget(self.chk_cc)
        comp = composite_document(doc, apply_view_effects=False)
        self.manifest = build_content_credentials_manifest(doc, comp)
        txt = QPlainTextEdit(json.dumps(self.manifest, indent=2))
        txt.setReadOnly(True)
        v1.addWidget(txt, 1)
        b_exp = QPushButton("Export Content Credentials JSON Sidecar…")
        b_exp.clicked.connect(self._export_cc)
        v1.addWidget(b_exp)
        tabs.addTab(t1, "Content Credentials")

        lay.addWidget(tabs, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._commit)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _export_cc(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Save Content Credentials", "content_credentials.json", "JSON (*.json)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.manifest, f, indent=2)
            QMessageBox.information(self, "Exported", f"Saved Content Credentials manifest to:\n{p}")

    def _commit(self) -> None:
        md = self.doc.metadata
        md.title = self.ed_title.text()
        md.author = self.ed_author.text()
        md.copyright_status = self.cmb_cr.currentText()
        md.copyright_notice = self.ed_notice.text()
        md.keywords = self.ed_kw.text()
        md.camera_model = self.ed_cam.text()
        md.lens = self.ed_lens.text()
        md.iso = self.ed_iso.text()
        md.aperture = self.ed_ap.text()
        md.content_credentials_enabled = self.chk_cc.isChecked()
        self.accept()


# ---------------------------------------------------------------------------
# 19. Extensions / Third-Party Plugins Dialog
# ---------------------------------------------------------------------------
class ExtensionsDialog(QDialog):
    def __init__(self, plugins: List[KinoPlugin], rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("KinoShop Extensions & Plugins Manager")
        self.resize(640, 440)
        self.plugins = plugins
        self.rgba = rgba
        self.result_rgba: Optional[np.ndarray] = None
        self.result_name: str = ""

        lay = QVBoxLayout(self)
        self.lst = QListWidget()
        for p in plugins:
            badge = "Built-in" if p.is_builtin else "External .py"
            self.lst.addItem(f"[{badge}] {p.name} ({p.category}) — {p.description}")
        if plugins:
            self.lst.setCurrentRow(0)
        lay.addWidget(self.lst, 1)

        f = QFormLayout()
        self.ed_query = QLineEdit("Golden Hour Sunset")
        self.ed_query.setPlaceholderText("Used by KinoStock Asset Studio (sky/texture/prompt)")
        f.addRow("Stock / Plugin Query:", self.ed_query)
        lay.addLayout(f)

        b_run = QPushButton("▶ Run Selected Extension on Active Layer")
        b_run.setObjectName("PrimaryButton")
        b_run.clicked.connect(self._run)
        lay.addWidget(b_run)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _run(self) -> None:
        row = self.lst.currentRow()
        if not (0 <= row < len(self.plugins)):
            return
        pl = self.plugins[row]
        params = dict(pl.default_params)
        if "query" in params:
            params["query"] = self.ed_query.text().strip() or params["query"]
        self.result_rgba = pl.run(self.rgba, params)
        self.result_name = pl.name
        self.accept()


# ---------------------------------------------------------------------------
# 20. Measurement & Scientific Auto-Count Dialog
# ---------------------------------------------------------------------------
class MeasurementCountDialog(QDialog):
    def __init__(self, doc: KinoDocument, rgba: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scientific Measurement & Auto-Count")
        self.doc = doc
        self.rgba = rgba
        self.resize(480, 360)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.sp_ppu = QDoubleSpinBox(); self.sp_ppu.setRange(0.1, 10000.0); self.sp_ppu.setValue(doc.pixels_per_unit)
        self.cmb_unit = QComboBox(); self.cmb_unit.addItems(["mm", "cm", "µm", "in", "px"]); self.cmb_unit.setCurrentText(doc.measure_unit)
        self.sp_th = QSpinBox(); self.sp_th.setRange(1, 254); self.sp_th.setValue(135)
        self.chk_inv = QCheckBox("Detect Dark Objects on Light Background")
        self.sp_min = QSpinBox(); self.sp_min.setRange(5, 5000); self.sp_min.setValue(45)

        f.addRow("Calibration (px / unit):", self.sp_ppu)
        f.addRow("Unit:", self.cmb_unit)
        f.addRow("Threshold:", self.sp_th)
        f.addRow(self.chk_inv)
        f.addRow("Min Object Area (px²):", self.sp_min)
        lay.addLayout(f)

        self.lbl_res = QLabel(f"Current Count Markers: {len(doc.count_markers)}")
        lay.addWidget(self.lbl_res)

        row = QHBoxLayout()
        b_cnt = QPushButton("Auto-Detect & Count Objects")
        b_cnt.setObjectName("PrimaryButton")
        b_cnt.clicked.connect(self._auto_count)
        b_clr = QPushButton("Clear Markers")
        b_clr.clicked.connect(self._clear)
        b_csv = QPushButton("Export CSV…")
        b_csv.clicked.connect(self._export_csv)
        row.addWidget(b_cnt); row.addWidget(b_clr); row.addWidget(b_csv)
        lay.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self._ok)
        lay.addWidget(bb)

    def _auto_count(self) -> None:
        from .models import CountMarker

        objs = auto_count_objects(self.rgba, threshold=self.sp_th.value(), invert=self.chk_inv.isChecked(), min_area=self.sp_min.value())
        self.doc.count_markers = [CountMarker(index=i + 1, x=cx, y=cy, area_px=area) for i, (cx, cy, area) in enumerate(objs)]
        self.lbl_res.setText(f"Detected {len(objs)} distinct objects!")

    def _clear(self) -> None:
        self.doc.count_markers.clear()
        self.lbl_res.setText("Cleared count markers.")

    def _export_csv(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Export Measurement Log", "measurements.csv", "CSV (*.csv)")
        if p:
            ppu = max(0.01, self.sp_ppu.value())
            unit = self.cmb_unit.currentText()
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Index", "X_px", "Y_px", "Area_px2", f"Area_{unit}2"])
                for cm in self.doc.count_markers:
                    w.writerow([cm.index, f"{cm.x:.1f}", f"{cm.y:.1f}", f"{cm.area_px:.1f}", f"{cm.area_px / (ppu * ppu):.4f}"])
            QMessageBox.information(self, "Exported", f"Saved scientific measurements to:\n{p}")

    def _ok(self) -> None:
        self.doc.pixels_per_unit = self.sp_ppu.value()
        self.doc.measure_unit = self.cmb_unit.currentText()
        self.accept()
