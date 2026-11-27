"""KinoShop Studio Panels: Layers, Channels, Properties & Histogram, Color/Swatches,
Brushes, History & Snapshots, Layer Comps / Slices / KinoCloud, and Animation/Video Timeline."""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .brushes import BrushSettings
from .engine import compute_histogram
from .models import (
    ADJUSTMENT_TYPES,
    BLEND_MODES,
    TEXT_WARP_STYLES,
    AnimationFrame,
    KinoDocument,
    Layer,
)


# ---------------------------------------------------------------------------
# Live RGB / Luminance Histogram Widget
# ---------------------------------------------------------------------------
class HistogramWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(78)
        self._hist = None

    def set_image(self, rgba: Optional[np.ndarray]) -> None:
        self._hist = compute_histogram(rgba) if rgba is not None else None
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#10141B"))
        p.setPen(QPen(QColor("#2A3242"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if not self._hist:
            p.end()
            return
        w, h = self.width() - 4, self.height() - 6
        mx = max(1, int(max(self._hist["R"].max(), self._hist["G"].max(), self._hist["B"].max())))
        for key, col in [("R", QColor(248, 113, 113, 120)), ("G", QColor(74, 222, 128, 120)), ("B", QColor(56, 189, 248, 130)), ("L", QColor(226, 232, 240, 140))]:
            vals = self._hist[key]
            p.setPen(QPen(col, 1.0))
            for i in range(0, 256, 2):
                x = 2 + int(i / 255.0 * w)
                bh = int((vals[i] / mx) * h)
                p.drawLine(x, self.height() - 2, x, self.height() - 2 - bh)
        p.end()


# ---------------------------------------------------------------------------
# Color & Swatches Panel
# ---------------------------------------------------------------------------
SWATCH_COLORS = [
    "#FFFFFF", "#CBD5E1", "#64748B", "#1E293B", "#0B0E14",
    "#31A8FF", "#00D4FF", "#3B82F6", "#6366F1", "#A855F7",
    "#EC4899", "#F43F5E", "#EF4444", "#F97316", "#FF9A00",
    "#FACC15", "#84CC16", "#22C55E", "#14B8A6", "#06B6D4",
]


class ColorPanel(QWidget):
    colorChanged = Signal(tuple, tuple)  # fg_rgb, bg_rgb

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.fg = (49, 168, 255)
        self.bg = (18, 21, 28)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # FG/BG preview row
        top = QHBoxLayout()
        self.btn_fg = QPushButton("FG")
        self.btn_fg.setFixedSize(46, 36)
        self.btn_fg.clicked.connect(self._pick_fg)
        self.btn_bg = QPushButton("BG")
        self.btn_bg.setFixedSize(46, 36)
        self.btn_bg.clicked.connect(self._pick_bg)
        btn_swap = QPushButton("⇄ Swap")
        btn_swap.clicked.connect(self.swap_colors)
        btn_def = QPushButton("B/W")
        btn_def.clicked.connect(self._reset_bw)
        top.addWidget(self.btn_fg)
        top.addWidget(self.btn_bg)
        top.addWidget(btn_swap)
        top.addWidget(btn_def)
        lay.addLayout(top)

        # RGB Sliders
        self.sliders = {}
        for ch, idx in [("R", 0), ("G", 1), ("B", 2)]:
            row = QHBoxLayout()
            row.addWidget(QLabel(ch))
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 255)
            sl.setValue(self.fg[idx])
            sl.valueChanged.connect(self._on_rgb_slider)
            val_lbl = QLabel(str(self.fg[idx]))
            val_lbl.setFixedWidth(28)
            row.addWidget(sl, 1)
            row.addWidget(val_lbl)
            self.sliders[ch] = (sl, val_lbl)
            lay.addLayout(row)

        # Hex + CMYK readout
        info_row = QHBoxLayout()
        self.hex_edit = QLineEdit()
        self.hex_edit.setFixedWidth(82)
        self.hex_edit.editingFinished.connect(self._on_hex_edited)
        self.cmyk_lbl = QLabel("CMYK: 81/34/0/0")
        self.cmyk_lbl.setStyleSheet("color:#94A3B8; font-size:8pt;")
        info_row.addWidget(QLabel("Hex"))
        info_row.addWidget(self.hex_edit)
        info_row.addWidget(self.cmyk_lbl, 1)
        lay.addLayout(info_row)

        # Swatches Grid
        sw_grp = QGroupBox("KinoSuite Swatches")
        grid = QGridLayout(sw_grp)
        grid.setSpacing(4)
        for i, hx in enumerate(SWATCH_COLORS):
            b = QPushButton()
            b.setFixedSize(26, 20)
            b.setStyleSheet(f"background-color:{hx}; border:1px solid #354056; border-radius:4px;")
            b.clicked.connect(lambda _=False, h=hx: self.set_fg_hex(h))
            grid.addWidget(b, i // 5, i % 5)
        lay.addWidget(sw_grp)
        lay.addStretch(1)
        self._sync_ui()

    def set_fg(self, rgb: Tuple[int, int, int], emit: bool = False) -> None:
        self.fg = tuple(int(max(0, min(255, c))) for c in rgb)
        self._sync_ui()
        if emit:
            self.colorChanged.emit(self.fg, self.bg)

    def set_fg_hex(self, hx: str) -> None:
        c = QColor(hx)
        if c.isValid():
            self.set_fg((c.red(), c.green(), c.blue()), emit=True)

    def swap_colors(self) -> None:
        self.fg, self.bg = self.bg, self.fg
        self._sync_ui()
        self.colorChanged.emit(self.fg, self.bg)

    def _reset_bw(self) -> None:
        self.fg = (255, 255, 255)
        self.bg = (0, 0, 0)
        self._sync_ui()
        self.colorChanged.emit(self.fg, self.bg)

    def _pick_fg(self) -> None:
        c = QColorDialog.getColor(QColor(*self.fg), self, "Foreground Color")
        if c.isValid():
            self.set_fg((c.red(), c.green(), c.blue()), emit=True)

    def _pick_bg(self) -> None:
        c = QColorDialog.getColor(QColor(*self.bg), self, "Background Color")
        if c.isValid():
            self.bg = (c.red(), c.green(), c.blue())
            self._sync_ui()
            self.colorChanged.emit(self.fg, self.bg)

    def _on_rgb_slider(self) -> None:
        r = self.sliders["R"][0].value()
        g = self.sliders["G"][0].value()
        b = self.sliders["B"][0].value()
        self.fg = (r, g, b)
        self._sync_ui()
        self.colorChanged.emit(self.fg, self.bg)

    def _on_hex_edited(self) -> None:
        c = QColor(self.hex_edit.text().strip())
        if c.isValid():
            self.set_fg((c.red(), c.green(), c.blue()), emit=True)

    def _sync_ui(self) -> None:
        r, g, b = self.fg
        br, bg, bb = self.bg
        self.btn_fg.setStyleSheet(f"background-color:rgb({r},{g},{b}); color:{'#000' if r+g+b>380 else '#fff'}; font-weight:700; border:2px solid #31A8FF;")
        self.btn_bg.setStyleSheet(f"background-color:rgb({br},{bg},{bb}); color:{'#000' if br+bg+bb>380 else '#fff'}; border:1px solid #475569;")
        for ch, val in zip(("R", "G", "B"), self.fg):
            sl, lbl = self.sliders[ch]
            sl.blockSignals(True)
            sl.setValue(val)
            sl.blockSignals(False)
            lbl.setText(str(val))
        self.hex_edit.setText(f"#{r:02X}{g:02X}{b:02X}")
        rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
        k = 1.0 - max(rf, gf, bf)
        if k >= 0.999:
            c = m = y = 0.0
        else:
            c = (1 - rf - k) / (1 - k)
            m = (1 - gf - k) / (1 - k)
            y = (1 - bf - k) / (1 - k)
        self.cmyk_lbl.setText(f"CMYK {int(c*100)}/{int(m*100)}/{int(y*100)}/{int(k*100)}")


# ---------------------------------------------------------------------------
# Brushes Panel
# ---------------------------------------------------------------------------
class BrushesPanel(QWidget):
    settingsChanged = Signal()
    captureBrushRequested = Signal()

    def __init__(self, settings: BrushSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        form = QFormLayout()
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems(["Soft Round", "Hard Round", "Chalk", "Calligraphy", "Spatter", "Custom"])
        self.cmb_preset.currentTextChanged.connect(self._apply)
        form.addRow("Tip Preset:", self.cmb_preset)

        self.sp_size = QSpinBox()
        self.sp_size.setRange(1, 400)
        self.sp_size.setValue(int(settings.size))
        self.sp_size.valueChanged.connect(self._apply)
        form.addRow("Size (px):", self.sp_size)

        self.sl_hard = QSlider(Qt.Orientation.Horizontal)
        self.sl_hard.setRange(0, 100)
        self.sl_hard.setValue(int(settings.hardness * 100))
        self.sl_hard.valueChanged.connect(self._apply)
        form.addRow("Hardness:", self.sl_hard)

        self.sl_op = QSlider(Qt.Orientation.Horizontal)
        self.sl_op.setRange(5, 100)
        self.sl_op.setValue(int(settings.opacity * 100))
        self.sl_op.valueChanged.connect(self._apply)
        form.addRow("Opacity:", self.sl_op)

        self.sl_flow = QSlider(Qt.Orientation.Horizontal)
        self.sl_flow.setRange(5, 100)
        self.sl_flow.setValue(int(settings.flow * 100))
        self.sl_flow.valueChanged.connect(self._apply)
        form.addRow("Flow:", self.sl_flow)

        self.sl_scatter = QSlider(Qt.Orientation.Horizontal)
        self.sl_scatter.setRange(0, 100)
        self.sl_scatter.setValue(0)
        self.sl_scatter.valueChanged.connect(self._apply)
        form.addRow("Scatter:", self.sl_scatter)

        self.cmb_sym = QComboBox()
        self.cmb_sym.addItems(["None", "Vertical", "Horizontal", "Dual", "Radial4", "Radial8"])
        self.cmb_sym.currentTextChanged.connect(self._apply)
        form.addRow("Symmetry:", self.cmb_sym)
        lay.addLayout(form)

        # Mixer Brush Dynamics
        mix_grp = QGroupBox("Mixer Brush Dynamics")
        mf = QFormLayout(mix_grp)
        self.sl_wet = QSlider(Qt.Orientation.Horizontal)
        self.sl_wet.setRange(0, 100)
        self.sl_wet.setValue(int(settings.wetness * 100))
        self.sl_wet.valueChanged.connect(self._apply)
        self.sl_load = QSlider(Qt.Orientation.Horizontal)
        self.sl_load.setRange(0, 100)
        self.sl_load.setValue(int(settings.load * 100))
        self.sl_load.valueChanged.connect(self._apply)
        self.sl_mix = QSlider(Qt.Orientation.Horizontal)
        self.sl_mix.setRange(5, 100)
        self.sl_mix.setValue(int(settings.mix * 100))
        self.sl_mix.valueChanged.connect(self._apply)
        mf.addRow("Wetness:", self.sl_wet)
        mf.addRow("Load:", self.sl_load)
        mf.addRow("Mix:", self.sl_mix)
        lay.addWidget(mix_grp)

        self.chk_psize = QCheckBox("Tablet Pressure → Size")
        self.chk_psize.setChecked(settings.pressure_size)
        self.chk_psize.toggled.connect(self._apply)
        self.chk_pop = QCheckBox("Tablet Pressure → Opacity")
        self.chk_pop.setChecked(settings.pressure_opacity)
        self.chk_pop.toggled.connect(self._apply)
        lay.addWidget(self.chk_psize)
        lay.addWidget(self.chk_pop)

        btn_cap = QPushButton("Capture Selection as Custom Brush")
        btn_cap.clicked.connect(self.captureBrushRequested.emit)
        lay.addWidget(btn_cap)
        lay.addStretch(1)

    def _apply(self) -> None:
        self.settings.preset = self.cmb_preset.currentText()
        self.settings.size = float(self.sp_size.value())
        self.settings.hardness = self.sl_hard.value() / 100.0
        self.settings.opacity = self.sl_op.value() / 100.0
        self.settings.flow = self.sl_flow.value() / 100.0
        self.settings.scatter = self.sl_scatter.value() / 100.0
        self.settings.symmetry = self.cmb_sym.currentText()
        self.settings.wetness = self.sl_wet.value() / 100.0
        self.settings.load = self.sl_load.value() / 100.0
        self.settings.mix = self.sl_mix.value() / 100.0
        self.settings.pressure_size = self.chk_psize.isChecked()
        self.settings.pressure_opacity = self.chk_pop.isChecked()
        self.settingsChanged.emit()


# ---------------------------------------------------------------------------
# Layers Panel
# ---------------------------------------------------------------------------
class LayersPanel(QWidget):
    layersModified = Signal()
    activeLayerSelected = Signal()
    editMaskToggled = Signal(bool)
    openStylesRequested = Signal()
    addAdjustmentRequested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc: Optional[KinoDocument] = None
        self._thumb_cache: dict = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # Blend mode & Opacity
        top = QHBoxLayout()
        self.cmb_blend = QComboBox()
        self.cmb_blend.addItems(BLEND_MODES)
        self.cmb_blend.currentTextChanged.connect(self._on_blend_changed)
        top.addWidget(self.cmb_blend, 1)
        self.sp_opacity = QSpinBox()
        self.sp_opacity.setRange(0, 100)
        self.sp_opacity.setSuffix("%")
        self.sp_opacity.valueChanged.connect(self._on_opacity_changed)
        top.addWidget(QLabel("Op:"))
        top.addWidget(self.sp_opacity)
        lay.addLayout(top)

        # Flags row: Lock, Clip, Mask Edit
        flags = QHBoxLayout()
        self.chk_lock = QCheckBox("Lock")
        self.chk_lock.toggled.connect(self._on_lock_toggled)
        self.chk_clip = QCheckBox("Clip Mask")
        self.chk_clip.toggled.connect(self._on_clip_toggled)
        self.chk_edit_mask = QCheckBox("Paint Mask")
        self.chk_edit_mask.toggled.connect(self.editMaskToggled.emit)
        flags.addWidget(self.chk_lock)
        flags.addWidget(self.chk_clip)
        flags.addWidget(self.chk_edit_mask)
        lay.addLayout(flags)

        # Layer list (top-to-bottom visual order = reversed doc.layers) with Photoshop-style thumbnails
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QPixmap(36, 26).size())
        self.list_widget.currentItemChanged.connect(self._on_selected)
        self.list_widget.itemChanged.connect(self._on_item_checked)
        lay.addWidget(self.list_widget, 1)

        # Action toolbar row 1
        r1 = QHBoxLayout()
        for txt, tip, cb in [
            ("+ Layer", "New Raster Layer", self._add_raster),
            ("▲", "Move Layer Up", lambda: self._move_layer(1)),
            ("▼", "Move Layer Down", lambda: self._move_layer(-1)),
            ("Mask", "Add Layer Mask", self._add_mask),
            ("fx", "Layer Styles", self.openStylesRequested.emit),
            ("✕", "Delete Layer", self._delete_layer),
        ]:
            b = QPushButton(txt)
            b.setToolTip(tip)
            b.setFixedHeight(26)
            b.clicked.connect(cb)
            r1.addWidget(b)
        lay.addLayout(r1)

        # Action row 2: Adjustments, Group, Smart Object, Duplicate
        r2 = QHBoxLayout()
        self.cmb_adj = QComboBox()
        self.cmb_adj.addItem("+ Adjustment…")
        self.cmb_adj.addItems(ADJUSTMENT_TYPES)
        self.cmb_adj.currentTextChanged.connect(self._on_add_adj_combo)
        r2.addWidget(self.cmb_adj, 1)
        b_grp = QPushButton("Group")
        b_grp.clicked.connect(self._add_group)
        b_so = QPushButton("Smart Obj")
        b_so.clicked.connect(self._convert_smart)
        b_dup = QPushButton("Dup")
        b_dup.clicked.connect(self._dup_layer)
        r2.addWidget(b_grp)
        r2.addWidget(b_so)
        r2.addWidget(b_dup)
        lay.addLayout(r2)

    def set_document(self, doc: KinoDocument) -> None:
        self.doc = doc
        self.refresh()

    def _layer_thumbnail_icon(self, lyr: Layer) -> QIcon:
        """Render & cache a crisp Photoshop-style 36x26 checkerboard layer thumbnail."""
        src = lyr.image if lyr.image is not None else lyr.smart_source
        cache_key = (lyr.uid, lyr.kind, lyr._version, id(src))
        if cache_key in self._thumb_cache:
            return self._thumb_cache[cache_key]
        pm = QPixmap(36, 26)
        p = QPainter(pm)
        # Mini transparency checker
        p.fillRect(0, 0, 36, 26, QColor("#252A34"))
        for y in range(0, 26, 6):
            for x in range(0, 36, 6):
                if ((x // 6) + (y // 6)) % 2 == 0:
                    p.fillRect(x, y, 6, 6, QColor("#323948"))

        if src is not None and src.size > 0:
            import cv2
            from .canvas import rgba_to_qimage

            small = cv2.resize(src, (34, 24), interpolation=cv2.INTER_NEAREST)
            p.drawImage(1, 1, rgba_to_qimage(small))
        elif lyr.kind == "text":
            p.fillRect(1, 1, 34, 24, QColor("#1A2232"))
            p.setPen(QColor("#E6EAF2"))
            p.setFont(QFont("Georgia", 13, QFont.Weight.Bold))
            p.drawText(QRectF(0, 0, 36, 26), Qt.AlignmentFlag.AlignCenter, "T")
        elif lyr.kind == "adjustment":
            p.fillRect(1, 1, 34, 24, QColor("#152236"))
            p.setPen(QPen(QColor("#31A8FF"), 1.5))
            p.setBrush(QColor("#31A8FF"))
            p.drawPie(QRectF(9, 4, 18, 18), 90 * 16, 180 * 16)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(9, 4, 18, 18))
        elif lyr.kind == "vector":
            p.fillRect(1, 1, 34, 24, QColor("#182130"))
            p.setPen(QPen(QColor("#38BDF8"), 1.4))
            p.setBrush(QColor(49, 168, 255, 80))
            p.drawRoundedRect(QRectF(7, 5, 22, 16), 3, 3)
        elif lyr.kind == "group":
            p.fillRect(1, 1, 34, 24, QColor("#1E2534"))
            p.setPen(QColor("#94A3B8"))
            p.drawRect(QRectF(7, 7, 22, 13))
            p.drawRect(QRectF(7, 5, 9, 3))

        p.setPen(QPen(QColor("#475569"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, 35, 25)
        p.end()
        icon = QIcon(pm)
        if len(self._thumb_cache) > 128:
            self._thumb_cache.clear()
        self._thumb_cache[cache_key] = icon
        return icon

    def refresh(self) -> None:
        if not self.doc:
            return
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        sel_row = -1
        flat = list(reversed(self.doc.layers))
        for idx, lyr in enumerate(flat):
            badges = []
            if lyr.clipping_mask:
                badges.append("↳")
            if lyr.linked_path:
                badges.append("🔗")
            if lyr.mask is not None:
                badges.append("[M]")
            if lyr.styles.has_any():
                badges.append("fx")
            if lyr.smart_filters:
                badges.append(f"SF:{len(lyr.smart_filters)}")
            if lyr.locked:
                badges.append("🔒")
            suffix = ("  " + " ".join(badges)) if badges else ""
            title = f"{lyr.name}{suffix}"
            it = QListWidgetItem(self._layer_thumbnail_icon(lyr), title)
            it.setData(Qt.ItemDataRole.UserRole, lyr.uid)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if lyr.visible else Qt.CheckState.Unchecked)
            self.list_widget.addItem(it)
            if lyr.uid == self.doc.active_layer_id:
                sel_row = idx
        if sel_row >= 0:
            self.list_widget.setCurrentRow(sel_row)
        self.list_widget.blockSignals(False)
        self._sync_controls()

    def _sync_controls(self) -> None:
        if not self.doc:
            return
        lyr = self.doc.active_layer()
        if not lyr:
            return
        for w in (self.cmb_blend, self.sp_opacity, self.chk_lock, self.chk_clip):
            w.blockSignals(True)
        self.cmb_blend.setCurrentText(lyr.blend_mode)
        self.sp_opacity.setValue(int(round(lyr.opacity * 100)))
        self.chk_lock.setChecked(lyr.locked)
        self.chk_clip.setChecked(lyr.clipping_mask)
        for w in (self.cmb_blend, self.sp_opacity, self.chk_lock, self.chk_clip):
            w.blockSignals(False)

    def _on_selected(self, cur: Optional[QListWidgetItem]) -> None:
        if not self.doc or not cur:
            return
        self.doc.active_layer_id = cur.data(Qt.ItemDataRole.UserRole)
        self._sync_controls()
        self.activeLayerSelected.emit()

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        if not self.doc:
            return
        lyr = self.doc.get_layer(item.data(Qt.ItemDataRole.UserRole))
        if lyr:
            lyr.visible = item.checkState() == Qt.CheckState.Checked
            self.layersModified.emit()

    def _on_blend_changed(self, mode: str) -> None:
        if self.doc and self.doc.active_layer():
            self.doc.active_layer().blend_mode = mode
            self.layersModified.emit()

    def _on_opacity_changed(self, val: int) -> None:
        if self.doc and self.doc.active_layer():
            self.doc.active_layer().opacity = val / 100.0
            self.layersModified.emit()

    def _on_lock_toggled(self, v: bool) -> None:
        if self.doc and self.doc.active_layer():
            self.doc.active_layer().locked = v
            self.refresh()

    def _on_clip_toggled(self, v: bool) -> None:
        if self.doc and self.doc.active_layer():
            self.doc.active_layer().clipping_mask = v
            self.refresh()
            self.layersModified.emit()

    def _add_raster(self) -> None:
        if not self.doc:
            return
        self.doc.add_raster_layer()
        self.doc.push_history("New Layer")
        self.refresh()
        self.layersModified.emit()

    def _add_group(self) -> None:
        if not self.doc:
            return
        self.doc.add_group_layer(f"Group {len(self.doc.layers) + 1}")
        self.doc.push_history("New Group")
        self.refresh()
        self.layersModified.emit()

    def _add_mask(self) -> None:
        if not self.doc:
            return
        self.doc.add_mask_to_active(255)
        self.doc.push_history("Add Layer Mask")
        self.refresh()
        self.layersModified.emit()

    def _convert_smart(self) -> None:
        if not self.doc:
            return
        lyr = self.doc.active_layer()
        if not lyr or lyr.kind == "smart_object":
            return
        from .engine import render_single_layer_rgba

        rendered = render_single_layer_rgba(lyr, self.doc.width, self.doc.height)
        if rendered is not None:
            lyr.kind = "smart_object"
            lyr.smart_source = rendered
            lyr.image = None
            lyr.offset_x = 0
            lyr.offset_y = 0
            self.doc.push_history("Convert to Smart Object")
            self.refresh()
            self.layersModified.emit()

    def _dup_layer(self) -> None:
        if not self.doc or not self.doc.active_layer():
            return
        from .models import new_id

        dup = self.doc.active_layer().clone()
        dup.uid = new_id()
        dup.name += " Copy"
        self.doc.layers.append(dup)
        self.doc.active_layer_id = dup.uid
        self.doc.push_history("Duplicate Layer")
        self.refresh()
        self.layersModified.emit()

    def _delete_layer(self) -> None:
        if not self.doc or not self.doc.active_layer_id:
            return
        if self.doc.remove_layer(self.doc.active_layer_id):
            self.doc.push_history("Delete Layer")
            self.refresh()
            self.layersModified.emit()

    def _move_layer(self, delta: int) -> None:
        if not self.doc or not self.doc.active_layer_id:
            return
        ids = [l.uid for l in self.doc.layers]
        if self.doc.active_layer_id not in ids:
            return
        idx = ids.index(self.doc.active_layer_id)
        nidx = max(0, min(len(self.doc.layers) - 1, idx + delta))
        if nidx != idx:
            l = self.doc.layers.pop(idx)
            self.doc.layers.insert(nidx, l)
            self.doc.push_history("Reorder Layer")
            self.refresh()
            self.layersModified.emit()

    def _on_add_adj_combo(self, text: str) -> None:
        if text.startswith("+"):
            return
        self.cmb_adj.blockSignals(True)
        self.cmb_adj.setCurrentIndex(0)
        self.cmb_adj.blockSignals(False)
        self.addAdjustmentRequested.emit(text)


# ---------------------------------------------------------------------------
# Channels Panel (RGB/CMYK + Alpha + Spot Colors)
# ---------------------------------------------------------------------------
class ChannelsPanel(QWidget):
    channelsChanged = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc: Optional[KinoDocument] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.mode_lbl = QLabel("Color Mode: RGB")
        self.mode_lbl.setObjectName("SectionHeader")
        lay.addWidget(self.mode_lbl)

        self.list_ch = QListWidget()
        self.list_ch.itemChanged.connect(self._on_toggled)
        self.list_ch.currentItemChanged.connect(self._on_select)
        lay.addWidget(self.list_ch, 1)

        row = QHBoxLayout()
        b_alpha = QPushButton("+ Alpha")
        b_alpha.clicked.connect(self._add_alpha)
        b_spot = QPushButton("+ Spot Ink")
        b_spot.clicked.connect(self._add_spot)
        b_load = QPushButton("Load as Sel")
        b_load.clicked.connect(self._load_sel)
        row.addWidget(b_alpha)
        row.addWidget(b_spot)
        row.addWidget(b_load)
        lay.addLayout(row)

    def set_document(self, doc: KinoDocument) -> None:
        self.doc = doc
        self.refresh()

    def refresh(self) -> None:
        if not self.doc:
            return
        self.mode_lbl.setText(f"Mode: {self.doc.color_mode} · {self.doc.color_profile[:24]}")
        self.list_ch.blockSignals(True)
        self.list_ch.clear()

        comp_it = QListWidgetItem(f"★  {self.doc.color_mode} Composite")
        comp_it.setData(Qt.ItemDataRole.UserRole, "Composite")
        self.list_ch.addItem(comp_it)

        for cname, vis in self.doc.channel_visible.items():
            it = QListWidgetItem(f"◉  {cname} Channel")
            it.setData(Qt.ItemDataRole.UserRole, cname)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if vis else Qt.CheckState.Unchecked)
            self.list_ch.addItem(it)

        for ec in self.doc.extra_channels:
            tag = "Spot" if ec.kind == "spot" else "Alpha"
            it = QListWidgetItem(f"[{tag}]  {ec.name}")
            it.setData(Qt.ItemDataRole.UserRole, ec.uid)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if ec.visible else Qt.CheckState.Unchecked)
            self.list_ch.addItem(it)

        self.list_ch.blockSignals(False)

    def _on_toggled(self, item: QListWidgetItem) -> None:
        if not self.doc:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        chk = item.checkState() == Qt.CheckState.Checked
        if key in self.doc.channel_visible:
            self.doc.channel_visible[key] = chk
        else:
            for ec in self.doc.extra_channels:
                if ec.uid == key:
                    ec.visible = chk
        self.channelsChanged.emit()

    def _on_select(self, cur: Optional[QListWidgetItem]) -> None:
        if not self.doc or not cur:
            return
        key = cur.data(Qt.ItemDataRole.UserRole)
        self.doc.active_channel = key
        if key == "Composite":
            for k in self.doc.channel_visible:
                self.doc.channel_visible[k] = True
        self.channelsChanged.emit()

    def _add_alpha(self) -> None:
        if not self.doc:
            return
        self.doc.save_selection_as_alpha()
        self.refresh()
        self.channelsChanged.emit()

    def _add_spot(self) -> None:
        if not self.doc:
            return
        c = QColorDialog.getColor(QColor("#00AEEF"), self, "Spot Color Ink")
        if c.isValid():
            self.doc.add_spot_channel(f"Spot {c.name().upper()}", (c.red(), c.green(), c.blue()))
            self.refresh()
            self.channelsChanged.emit()

    def _load_sel(self) -> None:
        if not self.doc:
            return
        it = self.list_ch.currentItem()
        if not it:
            return
        key = it.data(Qt.ItemDataRole.UserRole)
        for ec in self.doc.extra_channels:
            if ec.uid == key and ec.data is not None:
                self.doc.selection = ec.data.astype(np.float32) / 255.0
                self.channelsChanged.emit()
                break


# ---------------------------------------------------------------------------
# Properties & Live Inspector Panel (Adjustments, Text, Vector, Smart Filters, Histogram)
# ---------------------------------------------------------------------------
class PropertiesPanel(QWidget):
    documentModified = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc: Optional[KinoDocument] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self.histogram = HistogramWidget()
        outer.addWidget(self.histogram)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content.setObjectName("ScrollContent")
        self.vbox = QVBoxLayout(self.content)
        self.vbox.setContentsMargins(4, 4, 4, 4)
        self.vbox.setSpacing(6)
        scroll.setWidget(self.content)
        outer.addWidget(scroll, 1)

    def set_document(self, doc: KinoDocument) -> None:
        self.doc = doc
        self.rebuild()

    def update_histogram(self, rgba: Optional[np.ndarray]) -> None:
        self.histogram.set_image(rgba)

    def _clear(self) -> None:
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def rebuild(self) -> None:
        self._clear()
        if not self.doc:
            return
        lyr = self.doc.active_layer()
        if not lyr:
            self.vbox.addWidget(QLabel("No layer selected."))
            return

        # Layer header & rename
        hdr = QGroupBox(f"{lyr.kind.replace('_', ' ').title()} Properties")
        hf = QFormLayout(hdr)
        name_ed = QLineEdit(lyr.name)
        name_ed.editingFinished.connect(lambda: self._set_attr(lyr, "name", name_ed.text()))
        hf.addRow("Name:", name_ed)

        sp_rot = QDoubleSpinBox()
        sp_rot.setRange(-360, 360)
        sp_rot.setValue(lyr.rotation)
        sp_rot.setSuffix("°")
        sp_rot.valueChanged.connect(lambda v: self._set_attr(lyr, "rotation", float(v)))
        hf.addRow("Rotation:", sp_rot)

        sp_sc = QDoubleSpinBox()
        sp_sc.setRange(0.05, 8.0)
        sp_sc.setSingleStep(0.05)
        sp_sc.setValue(lyr.scale_x)
        sp_sc.valueChanged.connect(lambda v: self._set_scale(lyr, float(v)))
        hf.addRow("Scale:", sp_sc)

        var_ed = QLineEdit(lyr.variable_name)
        var_ed.setPlaceholderText("CSV Column (Data Sets)")
        var_ed.editingFinished.connect(lambda: self._set_attr(lyr, "variable_name", var_ed.text()))
        hf.addRow("Variable:", var_ed)
        self.vbox.addWidget(hdr)

        # Adjustment Layer Live Controls
        if lyr.kind == "adjustment":
            self._build_adjustment_controls(lyr)
        elif lyr.kind == "text" and lyr.text_data is not None:
            self._build_text_controls(lyr)
        elif lyr.kind == "vector" and lyr.vector_data is not None:
            self._build_vector_controls(lyr)

        # Smart Filters reversible stack
        if lyr.smart_filters:
            sf_grp = QGroupBox(f"Smart Filters ({len(lyr.smart_filters)})")
            sfl = QVBoxLayout(sf_grp)
            for idx, sf in enumerate(lyr.smart_filters):
                row = QHBoxLayout()
                chk = QCheckBox(sf.name)
                chk.setChecked(sf.enabled)
                chk.toggled.connect(lambda v, f=sf: self._toggle_sf(f, v))
                btn_del = QPushButton("✕")
                btn_del.setFixedWidth(24)
                btn_del.clicked.connect(lambda _=False, i=idx: self._remove_sf(lyr, i))
                row.addWidget(chk, 1)
                row.addWidget(btn_del)
                w = QWidget()
                w.setLayout(row)
                sfl.addWidget(w)
            self.vbox.addWidget(sf_grp)

        # Linked Smart Object info
        if lyr.linked_path:
            lk = QGroupBox("Linked Smart Object")
            ll = QVBoxLayout(lk)
            ll.addWidget(QLabel(lyr.linked_path))
            self.vbox.addWidget(lk)

        self.vbox.addStretch(1)

    def _set_attr(self, obj, attr: str, val) -> None:
        setattr(obj, attr, val)
        self.documentModified.emit()

    def _set_scale(self, lyr: Layer, val: float) -> None:
        lyr.scale_x = val
        lyr.scale_y = val
        self.documentModified.emit()

    def _toggle_sf(self, sf, v: bool) -> None:
        sf.enabled = v
        self.documentModified.emit()

    def _remove_sf(self, lyr: Layer, idx: int) -> None:
        if 0 <= idx < len(lyr.smart_filters):
            lyr.smart_filters.pop(idx)
            self.rebuild()
            self.documentModified.emit()

    def _add_slider_param(self, form: QFormLayout, label: str, params: dict, key: str, mn: int, mx: int, scale: float = 1.0) -> None:
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(mn, mx)
        sl.setValue(int(round(float(params.get(key, 0)) / scale)))
        def _chg(v: int) -> None:
            params[key] = v * scale
            self.documentModified.emit()
        sl.valueChanged.connect(_chg)
        form.addRow(label, sl)

    def _build_adjustment_controls(self, lyr: Layer) -> None:
        grp = QGroupBox(f"Adjustment: {lyr.adjustment_type}")
        f = QFormLayout(grp)
        p = lyr.adjustment_params
        t = lyr.adjustment_type
        if t == "Levels":
            self._add_slider_param(f, "In Black", p, "in_black", 0, 240)
            self._add_slider_param(f, "Gamma", p, "gamma", 20, 300, 0.01)
            self._add_slider_param(f, "In White", p, "in_white", 15, 255)
        elif t == "Curves":
            # Midtone lift & S-curve contrast shortcuts
            sl_mid = QSlider(Qt.Orientation.Horizontal)
            sl_mid.setRange(-80, 80)
            pts = p.get("points_rgb", [[0, 0], [64, 64], [128, 128], [192, 192], [255, 255]])
            sl_mid.setValue(int(pts[2][1] - 128) if len(pts) >= 3 else 0)
            sl_con = QSlider(Qt.Orientation.Horizontal)
            sl_con.setRange(-45, 45)
            def _upd_curve() -> None:
                m = sl_mid.value()
                c = sl_con.value()
                p["points_rgb"] = [
                    [0, 0],
                    [64, max(0, min(255, 64 - c + m // 2))],
                    [128, max(0, min(255, 128 + m))],
                    [192, max(0, min(255, 192 + c + m // 2))],
                    [255, 255],
                ]
                self.documentModified.emit()
            sl_mid.valueChanged.connect(_upd_curve)
            sl_con.valueChanged.connect(_upd_curve)
            f.addRow("Midtone Lift", sl_mid)
            f.addRow("S-Contrast", sl_con)
        elif t == "Exposure":
            self._add_slider_param(f, "Exposure", p, "exposure", -300, 300, 0.01)
            self._add_slider_param(f, "Offset", p, "offset", -50, 50, 0.01)
            self._add_slider_param(f, "Gamma", p, "gamma", 25, 250, 0.01)
        elif t == "Hue/Saturation":
            self._add_slider_param(f, "Hue", p, "hue", -180, 180)
            self._add_slider_param(f, "Saturation", p, "saturation", -100, 100)
            self._add_slider_param(f, "Lightness", p, "lightness", -100, 100)
        elif t == "Vibrance":
            self._add_slider_param(f, "Vibrance", p, "vibrance", -100, 100)
            self._add_slider_param(f, "Saturation", p, "saturation", -100, 100)
        elif t == "Color Balance":
            for ci, cname in enumerate(["Cyan-Red", "Mag-Grn", "Yel-Blu"]):
                sl = QSlider(Qt.Orientation.Horizontal)
                sl.setRange(-100, 100)
                sl.setValue(int(p.get("midtones", [0, 0, 0])[ci]))
                def _cb(v: int, idx=ci) -> None:
                    p.setdefault("midtones", [0, 0, 0])[idx] = v
                    self.documentModified.emit()
                sl.valueChanged.connect(_cb)
                f.addRow(cname, sl)
        elif t == "LUT / Color Lookup":
            cmb = QComboBox()
            cmb.addItems(["Cinema Teal & Orange", "Fuji Crisp Film", "Kodak Warm Gold", "Noir High Contrast", "Cyberpunk Neon", "Bleach Bypass", "Sunset Matte"])
            cmb.setCurrentText(str(p.get("preset", "Cinema Teal & Orange")))
            cmb.currentTextChanged.connect(lambda v: (p.__setitem__("preset", v), self.documentModified.emit()))
            f.addRow("LUT Preset", cmb)
            self._add_slider_param(f, "Intensity", p, "intensity", 0, 100, 0.01)
        elif t == "Posterize":
            self._add_slider_param(f, "Levels", p, "levels", 2, 24)
        elif t == "Threshold":
            self._add_slider_param(f, "Level", p, "level", 1, 254)
        elif t == "Photo Filter":
            self._add_slider_param(f, "Density", p, "density", 0, 100)
        self.vbox.addWidget(grp)

    def _build_text_controls(self, lyr: Layer) -> None:
        td = lyr.text_data
        grp = QGroupBox("Typography & Warp")
        f = QFormLayout(grp)
        ed = QLineEdit(td.text.replace("\n", " | "))
        ed.editingFinished.connect(lambda: self._set_attr(td, "text", ed.text().replace(" | ", "\n")))
        f.addRow("Text:", ed)

        sp_sz = QSpinBox()
        sp_sz.setRange(8, 320)
        sp_sz.setValue(td.font_size)
        sp_sz.valueChanged.connect(lambda v: self._set_attr(td, "font_size", v))
        f.addRow("Size:", sp_sz)

        cmb_w = QComboBox()
        cmb_w.addItems(TEXT_WARP_STYLES)
        cmb_w.setCurrentText(td.warp_style)
        cmb_w.currentTextChanged.connect(lambda v: self._set_attr(td, "warp_style", v))
        f.addRow("Warp:", cmb_w)

        sl_b = QSlider(Qt.Orientation.Horizontal)
        sl_b.setRange(-100, 100)
        sl_b.setValue(int(td.warp_bend * 100))
        sl_b.valueChanged.connect(lambda v: self._set_attr(td, "warp_bend", v / 100.0))
        f.addRow("Bend:", sl_b)

        chk_path = QCheckBox("Type on Curved Path")
        chk_path.setChecked(td.on_path)
        def _tpath(v: bool) -> None:
            td.on_path = v
            if v and len(td.path_points) < 3:
                td.path_points = [(td.x, td.y), (td.x + 220, td.y - 110), (td.x + 440, td.y)]
            self.documentModified.emit()
        chk_path.toggled.connect(_tpath)
        f.addRow(chk_path)
        self.vbox.addWidget(grp)

    def _build_vector_controls(self, lyr: Layer) -> None:
        vd = lyr.vector_data
        grp = QGroupBox("Vector Shape")
        f = QFormLayout(grp)
        sp_sw = QDoubleSpinBox()
        sp_sw.setRange(0, 40)
        sp_sw.setValue(vd.stroke_width)
        sp_sw.valueChanged.connect(lambda v: self._set_attr(vd, "stroke_width", float(v)))
        f.addRow("Stroke Width:", sp_sw)
        chk_d = QCheckBox("Dashed Stroke")
        chk_d.setChecked(vd.dashed)
        chk_d.toggled.connect(lambda v: self._set_attr(vd, "dashed", v))
        f.addRow(chk_d)
        self.vbox.addWidget(grp)


# ---------------------------------------------------------------------------
# History & Snapshots Panel (with History Brush Source selector)
# ---------------------------------------------------------------------------
class HistoryPanel(QWidget):
    historyRestored = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc: Optional[KinoDocument] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Snapshots (History Brush Source):"))
        self.list_snap = QListWidget()
        self.list_snap.setMaximumHeight(95)
        self.list_snap.itemClicked.connect(self._on_snap_clicked)
        lay.addWidget(self.list_snap)

        lay.addWidget(QLabel("History States:"))
        self.list_hist = QListWidget()
        self.list_hist.itemClicked.connect(self._on_hist_clicked)
        lay.addWidget(self.list_hist, 1)

        row = QHBoxLayout()
        b_snap = QPushButton("📷 New Snapshot")
        b_snap.clicked.connect(self._create_snapshot)
        b_hb = QPushButton("🖌 Set History Brush")
        b_hb.clicked.connect(self._set_hb_source)
        row.addWidget(b_snap)
        row.addWidget(b_hb)
        lay.addLayout(row)

    def set_document(self, doc: KinoDocument) -> None:
        self.doc = doc
        self.refresh()

    def refresh(self) -> None:
        if not self.doc:
            return
        self.list_snap.clear()
        for s in self.doc.snapshots:
            mark = "🖌 " if s.uid == self.doc.history_brush_source_id else "📷 "
            it = QListWidgetItem(f"{mark}{s.label} ({s.timestamp})")
            it.setData(Qt.ItemDataRole.UserRole, s.uid)
            self.list_snap.addItem(it)

        self.list_hist.clear()
        for idx, h in enumerate(self.doc.history):
            hb = "🖌 " if h.uid == self.doc.history_brush_source_id else ""
            cur = "▶ " if idx == self.doc.history_index else "   "
            it = QListWidgetItem(f"{cur}{hb}{h.label}  [{h.timestamp}]")
            it.setData(Qt.ItemDataRole.UserRole, idx)
            self.list_hist.addItem(it)
        if 0 <= self.doc.history_index < self.list_hist.count():
            self.list_hist.setCurrentRow(self.doc.history_index)

    def _on_hist_clicked(self, item: QListWidgetItem) -> None:
        if not self.doc:
            return
        idx = int(item.data(Qt.ItemDataRole.UserRole))
        if 0 <= idx < len(self.doc.history):
            self.doc.history_index = idx
            self.doc.restore_history_entry(self.doc.history[idx])
            self.refresh()
            self.historyRestored.emit()

    def _on_snap_clicked(self, item: QListWidgetItem) -> None:
        if not self.doc:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        for s in self.doc.snapshots:
            if s.uid == uid:
                self.doc.restore_history_entry(s)
                self.doc.push_history(f"Restore {s.label}")
                self.refresh()
                self.historyRestored.emit()
                break

    def _create_snapshot(self) -> None:
        if not self.doc:
            return
        name, ok = QInputDialog.getText(self, "New Snapshot", "Snapshot name:", text=f"Snapshot {len(self.doc.snapshots) + 1}")
        if ok and name.strip():
            self.doc.push_history(name.strip(), is_snapshot=True)
            self.refresh()

    def _set_hb_source(self) -> None:
        if not self.doc:
            return
        it = self.list_hist.currentItem()
        if it:
            idx = int(it.data(Qt.ItemDataRole.UserRole))
            if 0 <= idx < len(self.doc.history):
                self.doc.history_brush_source_id = self.doc.history[idx].uid
                self.refresh()


# ---------------------------------------------------------------------------
# Comps, Slices & KinoCloud Collaboration Panel
# ---------------------------------------------------------------------------
class CompsCloudPanel(QWidget):
    documentModified = Signal()
    saveCloudRequested = Signal(str)
    loadCloudRequested = Signal(str)
    shareReviewRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.doc: Optional[KinoDocument] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # Layer Comps
        cg = QGroupBox("Layer Comps (Client Variations)")
        cl = QVBoxLayout(cg)
        self.list_comps = QListWidget()
        self.list_comps.setMaximumHeight(92)
        self.list_comps.itemClicked.connect(self._apply_comp)
        cl.addWidget(self.list_comps)
        cr = QHBoxLayout()
        b_nc = QPushButton("+ New Comp")
        b_nc.clicked.connect(self._new_comp)
        b_dc = QPushButton("Delete")
        b_dc.clicked.connect(self._del_comp)
        cr.addWidget(b_nc)
        cr.addWidget(b_dc)
        cl.addLayout(cr)
        lay.addWidget(cg)

        # KinoCloud Collaboration & Version History
        kg = QGroupBox("KinoCloud · Versions & Comments")
        kl = QVBoxLayout(kg)
        self.list_versions = QListWidget()
        self.list_versions.setMaximumHeight(85)
        self.list_versions.itemDoubleClicked.connect(self._restore_version)
        kl.addWidget(self.list_versions)
        kr = QHBoxLayout()
        b_sv = QPushButton("☁ Save Version")
        b_sv.setObjectName("PrimaryButton")
        b_sv.clicked.connect(self._save_ver)
        b_sh = QPushButton("Share Review")
        b_sh.clicked.connect(self.shareReviewRequested.emit)
        kr.addWidget(b_sv)
        kr.addWidget(b_sh)
        kl.addLayout(kr)

        self.list_comments = QListWidget()
        self.list_comments.itemDoubleClicked.connect(self._toggle_resolve)
        kl.addWidget(QLabel("Pinned Comments (double-click resolve):"))
        kl.addWidget(self.list_comments, 1)
        lay.addWidget(kg, 1)

    def set_document(self, doc: KinoDocument, versions: List[dict]) -> None:
        self.doc = doc
        self.refresh(versions)

    def refresh(self, versions: Optional[List[dict]] = None) -> None:
        if not self.doc:
            return
        self.list_comps.clear()
        for lc in self.doc.layer_comps:
            it = QListWidgetItem(f"◈ {lc.name}" + (f" — {lc.comment}" if lc.comment else ""))
            it.setData(Qt.ItemDataRole.UserRole, lc.uid)
            self.list_comps.addItem(it)

        self.list_comments.clear()
        for idx, cp in enumerate(self.doc.comments, start=1):
            st = "✓" if cp.resolved else "●"
            it = QListWidgetItem(f"{st} #{idx} {cp.author}: {cp.text}")
            it.setData(Qt.ItemDataRole.UserRole, cp.uid)
            self.list_comments.addItem(it)

        if versions is not None:
            self.list_versions.clear()
            for v in reversed(versions):
                it = QListWidgetItem(f"v{v['version']:03d} · {v['note']} ({v['timestamp']})")
                it.setData(Qt.ItemDataRole.UserRole, v["file"])
                self.list_versions.addItem(it)

    def _new_comp(self) -> None:
        if not self.doc:
            return
        name, ok = QInputDialog.getText(self, "New Layer Comp", "Comp name:", text=f"Layout Comp {len(self.doc.layer_comps) + 1}")
        if ok and name.strip():
            self.doc.capture_layer_comp(name.strip())
            self.refresh()

    def _apply_comp(self, item: QListWidgetItem) -> None:
        if not self.doc:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        for lc in self.doc.layer_comps:
            if lc.uid == uid:
                self.doc.apply_layer_comp(lc)
                self.documentModified.emit()
                break

    def _del_comp(self) -> None:
        if not self.doc:
            return
        it = self.list_comps.currentItem()
        if it:
            uid = it.data(Qt.ItemDataRole.UserRole)
            self.doc.layer_comps = [c for c in self.doc.layer_comps if c.uid != uid]
            self.refresh()

    def _save_ver(self) -> None:
        note, ok = QInputDialog.getText(self, "Save KinoCloud Version", "Version note:", text="Design Milestone")
        if ok:
            self.saveCloudRequested.emit(note.strip() or "Checkpoint")

    def _restore_version(self, item: QListWidgetItem) -> None:
        self.loadCloudRequested.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _toggle_resolve(self, item: QListWidgetItem) -> None:
        if not self.doc:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        for cp in self.doc.comments:
            if cp.uid == uid:
                cp.resolved = not cp.resolved
                self.refresh()
                self.documentModified.emit()
                break


# ---------------------------------------------------------------------------
# Bottom Timeline Panel (Frame-by-Frame GIF & Basic Video Timeline)
# ---------------------------------------------------------------------------
class TimelinePanel(QWidget):
    frameApplied = Signal()
    exportGifRequested = Signal()
    exportMp4Requested = Signal()
    importVideoRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("TimelineDock")
        self.setFixedHeight(138)
        self.doc: Optional[KinoDocument] = None
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step_play)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(5)

        ctrl = QHBoxLayout()
        lbl = QLabel("TIMELINE · GIF & VIDEO")
        lbl.setObjectName("SectionHeader")
        ctrl.addWidget(lbl)
        ctrl.addSpacing(10)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setObjectName("PrimaryButton")
        self.btn_play.clicked.connect(self.toggle_play)
        b_add = QPushButton("+ Capture Frame")
        b_add.clicked.connect(self.capture_frame)
        b_dup = QPushButton("Duplicate")
        b_dup.clicked.connect(self.duplicate_frame)
        b_del = QPushButton("Delete")
        b_del.clicked.connect(self.delete_frame)

        self.sp_delay = QSpinBox()
        self.sp_delay.setRange(20, 3000)
        self.sp_delay.setValue(120)
        self.sp_delay.setSuffix(" ms")
        self.sp_delay.valueChanged.connect(self._on_delay_changed)

        b_vid = QPushButton("Import Video")
        b_vid.clicked.connect(self.importVideoRequested.emit)
        b_gif = QPushButton("Export GIF")
        b_gif.clicked.connect(self.exportGifRequested.emit)
        b_mp4 = QPushButton("Export MP4")
        b_mp4.clicked.connect(self.exportMp4Requested.emit)

        for w in (self.btn_play, b_add, b_dup, b_del, QLabel("Delay:"), self.sp_delay, b_vid, b_gif, b_mp4):
            ctrl.addWidget(w)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

        self.list_frames = QListWidget()
        self.list_frames.setFlow(QListWidget.Flow.LeftToRight)
        self.list_frames.setWrapping(False)
        self.list_frames.setFixedHeight(84)
        self.list_frames.currentRowChanged.connect(self._apply_row)
        lay.addWidget(self.list_frames)

    def set_document(self, doc: KinoDocument) -> None:
        self.doc = doc
        self.stop_play()
        self.refresh()

    def refresh(self) -> None:
        if not self.doc:
            return
        self.list_frames.blockSignals(True)
        self.list_frames.clear()
        for idx, fr in enumerate(self.doc.frames, start=1):
            tag = "🎞" if fr.video_frame is not None else "◻"
            it = QListWidgetItem(f"{tag} Frame {idx}\n{fr.duration_ms} ms")
            self.list_frames.addItem(it)
        if 0 <= self.doc.current_frame_idx < self.list_frames.count():
            self.list_frames.setCurrentRow(self.doc.current_frame_idx)
        self.list_frames.blockSignals(False)

    def capture_frame(self) -> None:
        if not self.doc:
            return
        fr = AnimationFrame(
            name=f"Frame {len(self.doc.frames) + 1}",
            duration_ms=self.sp_delay.value(),
            layer_visibility={l.uid: l.visible for l in self.doc.iter_all_layers()},
            layer_offsets={l.uid: (l.offset_x, l.offset_y) for l in self.doc.iter_all_layers()},
            layer_opacities={l.uid: l.opacity for l in self.doc.iter_all_layers()},
        )
        self.doc.frames.append(fr)
        self.doc.current_frame_idx = len(self.doc.frames) - 1
        self.refresh()

    def duplicate_frame(self) -> None:
        if not self.doc or not self.doc.frames:
            self.capture_frame()
            return
        cur = self.doc.frames[max(0, self.doc.current_frame_idx)]
        dup = AnimationFrame.from_dict(cur.to_dict())
        dup.video_frame = None if cur.video_frame is None else cur.video_frame.copy()
        self.doc.frames.append(dup)
        self.doc.current_frame_idx = len(self.doc.frames) - 1
        self.refresh()

    def delete_frame(self) -> None:
        if not self.doc or not self.doc.frames:
            return
        idx = self.list_frames.currentRow()
        if 0 <= idx < len(self.doc.frames):
            self.doc.frames.pop(idx)
            self.doc.current_frame_idx = max(0, idx - 1)
            self.refresh()

    def _on_delay_changed(self, v: int) -> None:
        if self.doc and 0 <= self.doc.current_frame_idx < len(self.doc.frames):
            self.doc.frames[self.doc.current_frame_idx].duration_ms = v
            self.refresh()

    def _apply_row(self, row: int) -> None:
        if not self.doc or not (0 <= row < len(self.doc.frames)):
            return
        self.doc.current_frame_idx = row
        fr = self.doc.frames[row]
        self.sp_delay.blockSignals(True)
        self.sp_delay.setValue(fr.duration_ms)
        self.sp_delay.blockSignals(False)
        if fr.video_frame is not None:
            lyr = self.doc.layers[0]
            lyr.image = fr.video_frame.copy()
        else:
            for lyr in self.doc.iter_all_layers():
                if lyr.uid in fr.layer_visibility:
                    lyr.visible = fr.layer_visibility[lyr.uid]
                if lyr.uid in fr.layer_offsets:
                    lyr.offset_x, lyr.offset_y = fr.layer_offsets[lyr.uid]
                if lyr.uid in fr.layer_opacities:
                    lyr.opacity = fr.layer_opacities[lyr.uid]
        self.frameApplied.emit()

    def toggle_play(self) -> None:
        if self._playing:
            self.stop_play()
        elif self.doc and self.doc.frames:
            self._playing = True
            self.btn_play.setText("⏹ Stop")
            dur = self.doc.frames[self.doc.current_frame_idx].duration_ms
            self._timer.start(max(30, dur))

    def stop_play(self) -> None:
        self._playing = False
        self._timer.stop()
        self.btn_play.setText("▶ Play")

    def _step_play(self) -> None:
        if not self.doc or not self.doc.frames:
            self.stop_play()
            return
        nxt = (self.doc.current_frame_idx + 1) % len(self.doc.frames)
        self.list_frames.setCurrentRow(nxt)
        self._timer.setInterval(max(30, self.doc.frames[nxt].duration_ms))
