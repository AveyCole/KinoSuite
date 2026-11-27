"""Studio Dialogs for KinoDraw (KinoSuite):
New Document, Recolor Artwork, Image Trace, 3D & Materials, Envelope Warp,
Offset/Simplify Path, Graph Data Editor, Studio Mockups, Generative Vector & Pattern,
Export for Screens, Print-Ready PDF, Keyboard Shortcuts, and Plugins Manager.
"""
from __future__ import annotations

import copy
import os
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .models import Color, Document, VectorObject
from .plugins_builtin import KinoPlugin
from .trace_and_ai import (
    GENERATIVE_PALETTES,
    TRACE_PRESETS,
    generate_palette_from_prompt,
    generate_pattern_from_prompt,
    generate_vector_from_prompt,
    recolor_objects,
    trace_image_object,
)


class NewDocumentDialog(QDialog):
    PRESETS = {
        "Web HD (1280 × 800 px, RGB)": (1280, 800, "RGB", 0.0),
        "Poster A3 Print (842 × 1191 pt, CMYK, 9pt Bleed)": (842, 1191, "CMYK", 9.0),
        "US Letter Print (612 × 792 pt, CMYK, 9pt Bleed)": (612, 792, "CMYK", 9.0),
        "Logo / Icon Square (1024 × 1024 px, RGB)": (1024, 1024, "RGB", 0.0),
        "Mobile UI Screen (390 × 844 px, RGB)": (390, 844, "RGB", 0.0),
        "4K Cinema Frame / KinoCut (1920 × 1080 px, RGB)": (1920, 1080, "RGB", 0.0),
        "Packaging Box Die (1200 × 900 pt, CMYK, 12pt Bleed)": (1200, 900, "CMYK", 12.0),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Document — KinoDraw")
        self.resize(440, 320)
        lay = QVBoxLayout(self)
        fl = QFormLayout()

        self.ed_name = QLineEdit("Untitled-1")
        self.cb_preset = QComboBox()
        self.cb_preset.addItems(list(self.PRESETS.keys()))
        self.cb_preset.currentTextChanged.connect(self._apply_preset)
        self.sp_w = QDoubleSpinBox(); self.sp_w.setRange(64, 10000); self.sp_w.setValue(1280)
        self.sp_h = QDoubleSpinBox(); self.sp_h.setRange(64, 10000); self.sp_h.setValue(800)
        self.sp_abs = QSpinBox(); self.sp_abs.setRange(1, 16); self.sp_abs.setValue(1)
        self.cb_mode = QComboBox(); self.cb_mode.addItems(["RGB", "CMYK"])
        self.sp_bleed = QDoubleSpinBox(); self.sp_bleed.setRange(0, 100); self.sp_bleed.setValue(0.0)

        fl.addRow("Document Name", self.ed_name)
        fl.addRow("Preset", self.cb_preset)
        fl.addRow("Width", self.sp_w)
        fl.addRow("Height", self.sp_h)
        fl.addRow("Artboards", self.sp_abs)
        fl.addRow("Color Mode", self.cb_mode)
        fl.addRow("Print Bleed", self.sp_bleed)
        lay.addLayout(fl)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _apply_preset(self, text: str) -> None:
        w, h, mode, bleed = self.PRESETS[text]
        self.sp_w.setValue(w)
        self.sp_h.setValue(h)
        self.cb_mode.setCurrentText(mode)
        self.sp_bleed.setValue(bleed)


class RecolorArtworkDialog(QDialog):
    def __init__(self, objects: List[VectorObject], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recolor Artwork & Generative Palette")
        self.resize(450, 260)
        self.objects = objects
        lay = QVBoxLayout(self)
        fl = QFormLayout()

        self.cb_pal = QComboBox()
        self.cb_pal.addItem("(Keep Palette / Hue Shift Only)")
        for k in GENERATIVE_PALETTES:
            self.cb_pal.addItem(k.title())
        self.ed_prompt = QLineEdit()
        self.ed_prompt.setPlaceholderText("e.g. 'cyberpunk neon', 'autumn forest', 'swiss modernist'...")
        self.sl_hue = QSlider(Qt.Horizontal)
        self.sl_hue.setRange(-180, 180)
        self.sl_hue.setValue(0)
        fl.addRow("Curated Palette", self.cb_pal)
        fl.addRow("✦ Generative Recolor Prompt", self.ed_prompt)
        fl.addRow("Hue Wheel Shift (°)", self.sl_hue)
        lay.addLayout(fl)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _apply(self) -> None:
        prompt = self.ed_prompt.text().strip()
        if prompt:
            pal = generate_palette_from_prompt(prompt)
            recolor_objects(self.objects, pal)
        elif self.cb_pal.currentIndex() > 0:
            key = self.cb_pal.currentText().lower()
            pal = [Color.from_hex(h) for h in GENERATIVE_PALETTES.get(key, [])]
            recolor_objects(self.objects, pal)
        else:
            recolor_objects(self.objects, [], hue_shift=float(self.sl_hue.value()))
        self.accept()


class ImageTraceDialog(QDialog):
    def __init__(self, img_obj: VectorObject, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Trace — Raster to Editable Vectors")
        self.resize(440, 320)
        self.img_obj = img_obj
        self.result_group: Optional[VectorObject] = None

        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.cb_preset = QComboBox()
        self.cb_preset.addItems(list(TRACE_PRESETS.keys()))
        self.cb_preset.currentTextChanged.connect(self._on_preset)
        self.cb_mode = QComboBox(); self.cb_mode.addItems(["color", "gray", "bw", "sketch", "line"])
        self.sp_colors = QSpinBox(); self.sp_colors.setRange(2, 24); self.sp_colors.setValue(6)
        self.sp_thresh = QSpinBox(); self.sp_thresh.setRange(10, 245); self.sp_thresh.setValue(135)
        self.sp_simp = QDoubleSpinBox(); self.sp_simp.setRange(0.5, 12.0); self.sp_simp.setValue(2.2)
        self.chk_ignore_w = QCheckBox("Ignore White Background"); self.chk_ignore_w.setChecked(True)
        self.chk_smooth = QCheckBox("Fit Smooth Cubic Beziers"); self.chk_smooth.setChecked(True)
        self.chk_ai_sketch = QCheckBox("AI-Assisted Sketch Cleanup"); self.chk_ai_sketch.setChecked(False)

        fl.addRow("Preset", self.cb_preset)
        fl.addRow("Mode", self.cb_mode)
        fl.addRow("Colors", self.sp_colors)
        fl.addRow("Threshold", self.sp_thresh)
        fl.addRow("Path Simplify", self.sp_simp)
        fl.addRow(self.chk_ignore_w)
        fl.addRow(self.chk_smooth)
        fl.addRow(self.chk_ai_sketch)
        lay.addLayout(fl)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Trace & Expand")
        bb.accepted.connect(self._run_trace)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_preset(self, name: str) -> None:
        cfg = TRACE_PRESETS[name]
        self.cb_mode.setCurrentText(cfg["mode"])
        self.sp_colors.setValue(cfg["colors"])
        self.sp_thresh.setValue(cfg["threshold"])
        self.sp_simp.setValue(cfg["simplify"])
        self.chk_ignore_w.setChecked(cfg["ignore_white"])
        self.chk_ai_sketch.setChecked(cfg["sketch_ai"])

    def _run_trace(self) -> None:
        self.result_group = trace_image_object(
            self.img_obj,
            mode=self.cb_mode.currentText(),
            colors=self.sp_colors.value(),
            threshold=self.sp_thresh.value(),
            simplify=self.sp_simp.value(),
            ignore_white=self.chk_ignore_w.isChecked(),
            smooth_curves=self.chk_smooth.isChecked(),
            sketch_ai=self.chk_ai_sketch.isChecked(),
        )
        self.accept()


class Effect3DDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Extrude & Materials")
        self.resize(360, 220)
        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.sp_depth = QSpinBox(); self.sp_depth.setRange(4, 90); self.sp_depth.setValue(28)
        self.sp_ax = QSpinBox(); self.sp_ax.setRange(-75, 75); self.sp_ax.setValue(-22)
        self.sp_ay = QSpinBox(); self.sp_ay.setRange(-75, 75); self.sp_ay.setValue(28)
        self.cb_mat = QComboBox(); self.cb_mat.addItems(["glossy", "metallic", "matte"])
        fl.addRow("Extrude Depth", self.sp_depth)
        fl.addRow("Pitch X (°)", self.sp_ax)
        fl.addRow("Yaw Y (°)", self.sp_ay)
        fl.addRow("Material", self.cb_mat)
        lay.addLayout(fl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def params(self) -> Dict:
        return {"depth": self.sp_depth.value(), "angle_x": self.sp_ax.value(), "angle_y": self.sp_ay.value(), "material": self.cb_mat.currentText()}


class WarpEffectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Envelope Distort / Warp Options")
        self.resize(360, 230)
        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.cb_style = QComboBox()
        self.cb_style.addItems(["arc", "arch", "bulge", "flag", "wave", "fish", "rise", "twist", "squeeze"])
        self.sp_bend = QDoubleSpinBox(); self.sp_bend.setRange(-1.5, 1.5); self.sp_bend.setSingleStep(0.05); self.sp_bend.setValue(0.35)
        self.sp_hd = QDoubleSpinBox(); self.sp_hd.setRange(-1.0, 1.0); self.sp_hd.setSingleStep(0.05); self.sp_hd.setValue(0.0)
        self.sp_vd = QDoubleSpinBox(); self.sp_vd.setRange(-1.0, 1.0); self.sp_vd.setSingleStep(0.05); self.sp_vd.setValue(0.0)
        fl.addRow("Warp Style", self.cb_style)
        fl.addRow("Bend", self.sp_bend)
        fl.addRow("Horizontal Distortion", self.sp_hd)
        fl.addRow("Vertical Distortion", self.sp_vd)
        lay.addLayout(fl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def params(self) -> Dict:
        return {"style": self.cb_style.currentText(), "bend": self.sp_bend.value(), "h_distort": self.sp_hd.value(), "v_distort": self.sp_vd.value()}


class GraphDataDialog(QDialog):
    def __init__(self, obj: VectorObject, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Data Graphics Editor")
        self.resize(520, 360)
        self.obj = obj
        lay = QVBoxLayout(self)
        top = QFormLayout()
        self.cb_type = QComboBox(); self.cb_type.addItems(["bar", "stacked_bar", "line", "pie", "scatter"])
        self.cb_type.setCurrentText(obj.graph_type)
        self.ed_title = QLineEdit(obj.graph_title)
        top.addRow("Chart Type", self.cb_type)
        top.addRow("Chart Title", self.ed_title)
        lay.addLayout(top)

        cols = len(obj.graph_headers) + 1
        rows = max(1, len(obj.graph_series))
        self.tbl = QTableWidget(rows, cols)
        self.tbl.setHorizontalHeaderLabels(["Series"] + list(obj.graph_headers))
        for r, s in enumerate(obj.graph_series):
            self.tbl.setItem(r, 0, QTableWidgetItem(str(s.get("name", f"S{r + 1}"))))
            for c, v in enumerate(s.get("values", [])):
                if c + 1 < cols:
                    self.tbl.setItem(r, c + 1, QTableWidgetItem(str(v)))
        lay.addWidget(self.tbl)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self) -> None:
        self.obj.graph_type = self.cb_type.currentText()
        self.obj.graph_title = self.ed_title.text()
        palette = ["#FF9A00", "#00C2FF", "#6E2CF2", "#06D6A0", "#EF476F"]
        new_ser = []
        for r in range(self.tbl.rowCount()):
            nm_it = self.tbl.item(r, 0)
            nm = nm_it.text() if nm_it else f"Series {r + 1}"
            vals = []
            for c in range(1, self.tbl.columnCount()):
                it = self.tbl.item(r, c)
                try:
                    vals.append(float(it.text()) if it and it.text().strip() else 0.0)
                except ValueError:
                    vals.append(0.0)
            old_col = self.obj.graph_series[r].get("color") if r < len(self.obj.graph_series) else palette[r % len(palette)]
            new_ser.append({"name": nm, "values": vals, "color": old_col})
        self.obj.graph_series = new_ser
        self.accept()


class MockupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Studio Product Mockup")
        self.resize(360, 220)
        self.color = Color.from_hex("#F4F4F6")
        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.cb_preset = QComboBox()
        self.cb_preset.addItems(["mug", "tshirt", "tote", "cup", "box", "phone"])
        self.sp_scale = QDoubleSpinBox(); self.sp_scale.setRange(0.2, 1.4); self.sp_scale.setSingleStep(0.05); self.sp_scale.setValue(0.60)
        self.btn_col = QPushButton("Product Surface Color...")
        self.btn_col.clicked.connect(self._pick_col)
        fl.addRow("Product Type", self.cb_preset)
        fl.addRow("Artwork Scale", self.sp_scale)
        fl.addRow("Surface Color", self.btn_col)
        lay.addLayout(fl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick_col(self) -> None:
        qc = QColorDialog.getColor(QColor(self.color.to_hex()), self)
        if qc.isValid():
            self.color = Color(qc.red(), qc.green(), qc.blue(), 255)


class GenerativeAIDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("✦ Text to Vector Graphic & Generative Pattern")
        self.resize(470, 260)
        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Vector Graphic (Subject / Scene / Icon)", "Seamless Pattern Fill"])
        self.ed_prompt = QLineEdit()
        self.ed_prompt.setPlaceholderText("e.g. 'sunset mountain landscape', 'retro rocket launch', 'botanical plant', 'cinema logo crest'")
        fl.addRow("Generate", self.cb_mode)
        fl.addRow("Prompt", self.ed_prompt)
        lay.addLayout(fl)

        sug_row = QHBoxLayout()
        for sample in ["Sunset Mountain", "Rocket Launch", "Botanical Plant", "Kino Logo Crest"]:
            b = QPushButton(sample)
            b.clicked.connect(lambda _=False, s=sample: self.ed_prompt.setText(s))
            sug_row.addWidget(b)
        lay.addLayout(sug_row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("✦ Generate")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class ExportScreensDialog(QDialog):
    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export for Screens (Multi-Scale Batch Export)")
        self.resize(440, 280)
        self.doc = doc
        lay = QVBoxLayout(self)
        fl = QFormLayout()

        self.chk_png = QCheckBox("PNG"); self.chk_png.setChecked(True)
        self.chk_svg = QCheckBox("SVG"); self.chk_svg.setChecked(True)
        self.chk_jpg = QCheckBox("JPG")
        self.chk_webp = QCheckBox("WebP")
        frow = QHBoxLayout()
        for cb in (self.chk_png, self.chk_svg, self.chk_jpg, self.chk_webp):
            frow.addWidget(cb)
        fl.addRow("Formats", frow)

        self.chk_1x = QCheckBox("1x"); self.chk_1x.setChecked(True)
        self.chk_2x = QCheckBox("2x"); self.chk_2x.setChecked(True)
        self.chk_3x = QCheckBox("3x")
        srow = QHBoxLayout()
        for cb in (self.chk_1x, self.chk_2x, self.chk_3x):
            srow.addWidget(cb)
        fl.addRow("Scales", srow)

        self.chk_trans = QCheckBox("Transparent Background (PNG/WebP)")
        fl.addRow(self.chk_trans)
        lay.addLayout(fl)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Choose Folder & Export")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected_formats(self) -> List[str]:
        return [f for f, cb in [("PNG", self.chk_png), ("SVG", self.chk_svg), ("JPG", self.chk_jpg), ("WebP", self.chk_webp)] if cb.isChecked()]

    def selected_scales(self) -> List[float]:
        return [s for s, cb in [(1.0, self.chk_1x), (2.0, self.chk_2x), (3.0, self.chk_3x)] if cb.isChecked()] or [1.0]


class PrintPdfDialog(QDialog):
    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Print-Ready PDF (CMYK & Prepress Marks)")
        self.resize(400, 240)
        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.chk_cmyk = QCheckBox("Convert to CMYK Process Color"); self.chk_cmyk.setChecked(True)
        self.sp_bleed = QDoubleSpinBox(); self.sp_bleed.setRange(0, 72); self.sp_bleed.setValue(max(9.0, doc.bleed))
        self.chk_crop = QCheckBox("Trim / Crop Marks"); self.chk_crop.setChecked(True)
        self.chk_reg = QCheckBox("Registration Targets"); self.chk_reg.setChecked(True)
        self.chk_bars = QCheckBox("CMYK Color Calibration Bars"); self.chk_bars.setChecked(True)
        fl.addRow(self.chk_cmyk)
        fl.addRow("Bleed (pt)", self.sp_bleed)
        fl.addRow(self.chk_crop)
        fl.addRow(self.chk_reg)
        fl.addRow(self.chk_bars)
        lay.addLayout(fl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Export PDF...")
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class PluginsDialog(QDialog):
    def __init__(self, plugins: List[KinoPlugin], doc: Document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KinoDraw Plugins & Extensions")
        self.resize(480, 320)
        self.plugins = plugins
        self.doc = doc
        self.ran_message: str = ""
        lay = QVBoxLayout(self)
        self.lst = QListWidget()
        for pl in plugins:
            self.lst.addItem(f"{pl.name} v{pl.version} — {pl.description}")
        lay.addWidget(self.lst)
        row = QHBoxLayout()
        b_run = QPushButton("▶ Run Selected Plugin")
        b_run.setObjectName("PrimaryButton")
        b_run.clicked.connect(self._run)
        b_close = QPushButton("Close")
        b_close.clicked.connect(self.reject)
        row.addWidget(b_run); row.addWidget(b_close)
        lay.addLayout(row)

    def _run(self) -> None:
        r = self.lst.currentRow()
        if 0 <= r < len(self.plugins):
            self.ran_message = self.plugins[r].action(self.doc)
            self.accept()


class ShortcutsDialog(QDialog):
    def __init__(self, shortcuts: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts — KinoDraw")
        self.resize(440, 420)
        self.shortcuts = dict(shortcuts)
        lay = QVBoxLayout(self)
        self.tbl = QTableWidget(len(shortcuts), 2)
        self.tbl.setHorizontalHeaderLabels(["Tool / Action", "Shortcut"])
        self.tbl.setColumnWidth(0, 240)
        for i, (k, v) in enumerate(shortcuts.items()):
            self.tbl.setItem(i, 0, QTableWidgetItem(k))
            self.tbl.setItem(i, 1, QTableWidgetItem(v))
        lay.addWidget(self.tbl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self) -> None:
        for i in range(self.tbl.rowCount()):
            k = self.tbl.item(i, 0).text()
            v = self.tbl.item(i, 1).text()
            self.shortcuts[k] = v
        self.accept()
