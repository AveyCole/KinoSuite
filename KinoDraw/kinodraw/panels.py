"""Dockable Adobe Illustrator / KinoSuite Studio Panels for KinoDraw."""
from __future__ import annotations

import copy
import csv
import datetime
import json
import os
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .canvas import VectorCanvas
from .geometry import WIDTH_PROFILES, object_bounds, transform_object_affine, translate_object
from .importers_exporters import export_raster, export_svg, generate_css_snippet
from .models import (
    AppearanceFill,
    AppearanceStroke,
    Artboard,
    AssetExportItem,
    BrushDef,
    Color,
    Document,
    GradientDef,
    GradientStop,
    GraphicStyle,
    Layer,
    LiveEffect,
    PatternDef,
    SymbolDef,
    VectorObject,
)


def _scroll_wrap(inner: QWidget) -> QScrollArea:
    inner.setObjectName("ScrollContent")
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QScrollArea.NoFrame)
    sc.setWidget(inner)
    return sc


class StudioPanels(QWidget):
    """Right-hand tabbed Studio Panel dock (Properties, Layers, Appearance, Color/Grad,
    Stroke/Brushes, Type/Glyphs, Symbols/Artboards/Links, Export/CSS/Proof, Automation/Versions).
    """

    command_requested = Signal(str)

    def __init__(self, get_canvas: Callable[[], VectorCanvas], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("StudioPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.get_canvas = get_canvas
        self._syncing = False
        self._recording_action = False
        self._recorded_commands: List[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setUsesScrollButtons(True)
        root.addWidget(self.tabs)

        self.tabs.addTab(_scroll_wrap(self._build_properties_tab()), "Properties")
        self.tabs.addTab(self._build_layers_tab(), "Layers")
        self.tabs.addTab(_scroll_wrap(self._build_appearance_tab()), "Appearance")
        self.tabs.addTab(_scroll_wrap(self._build_color_gradient_tab()), "Color")
        self.tabs.addTab(_scroll_wrap(self._build_stroke_brushes_tab()), "Stroke")
        self.tabs.addTab(_scroll_wrap(self._build_type_glyphs_tab()), "Type")
        self.tabs.addTab(_scroll_wrap(self._build_symbols_artboards_links_tab()), "Assets")
        self.tabs.addTab(_scroll_wrap(self._build_export_proof_tab()), "Proof/CSS")
        self.tabs.addTab(_scroll_wrap(self._build_automation_versions_tab()), "Workflow")

    def _canvas(self) -> VectorCanvas:
        return self.get_canvas()

    def _doc(self) -> Document:
        return self.get_canvas().doc

    # ------------------------------------------------------------------
    # 1. Properties Tab
    # ------------------------------------------------------------------

    def _build_properties_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        # Selection Info & Transform
        grp_tr = QGroupBox("Transform")
        g = QGridLayout(grp_tr)
        self.sp_x = self._dspin(-9999, 9999, 0)
        self.sp_y = self._dspin(-9999, 9999, 0)
        self.sp_w = self._dspin(1, 9999, 100)
        self.sp_h = self._dspin(1, 9999, 100)
        self.sp_rot = self._dspin(-360, 360, 0)
        self.sp_corner = self._dspin(0, 400, 0)
        self.sp_sides = QSpinBox()
        self.sp_sides.setRange(3, 48)
        self.sp_sides.setValue(6)

        g.addWidget(QLabel("X"), 0, 0); g.addWidget(self.sp_x, 0, 1)
        g.addWidget(QLabel("Y"), 0, 2); g.addWidget(self.sp_y, 0, 3)
        g.addWidget(QLabel("W"), 1, 0); g.addWidget(self.sp_w, 1, 1)
        g.addWidget(QLabel("H"), 1, 2); g.addWidget(self.sp_h, 1, 3)
        g.addWidget(QLabel("Rot°"), 2, 0); g.addWidget(self.sp_rot, 2, 1)
        g.addWidget(QLabel("Radius"), 2, 2); g.addWidget(self.sp_corner, 2, 3)
        g.addWidget(QLabel("Sides"), 3, 0); g.addWidget(self.sp_sides, 3, 1)

        btn_apply_tr = QPushButton("Apply")
        btn_apply_tr.clicked.connect(self._apply_transform_fields)
        g.addWidget(btn_apply_tr, 3, 2, 1, 2)

        row_flip = QHBoxLayout()
        for lbl, cmd in [("Flip H", "flip_h"), ("Flip V", "flip_v"), ("Pixel Snap", "align_pixel")]:
            b = QPushButton(lbl)
            b.clicked.connect(lambda _=False, c=cmd: self.command_requested.emit(c))
            row_flip.addWidget(b)
        g.addLayout(row_flip, 4, 0, 1, 4)
        lay.addWidget(grp_tr)

        # Quick Opacity & Blend
        grp_app = QGroupBox("Opacity && Blend")
        fl = QFormLayout(grp_app)
        self.sl_opacity = QSlider(Qt.Horizontal)
        self.sl_opacity.setRange(0, 100)
        self.sl_opacity.setValue(100)
        self.sl_opacity.valueChanged.connect(self._on_opacity_changed)
        self.cb_blend = QComboBox()
        self.cb_blend.addItems(["Normal", "Multiply", "Screen", "Overlay", "Darken", "Lighten", "ColorDodge", "ColorBurn", "HardLight", "SoftLight", "Difference", "Exclusion"])
        self.cb_blend.currentTextChanged.connect(self._on_blend_changed)
        fl.addRow("Opacity %", self.sl_opacity)
        fl.addRow("Blend Mode", self.cb_blend)
        lay.addWidget(grp_app)

        # Align & Distribute
        grp_al = QGroupBox("Align && Distribute")
        ag = QGridLayout(grp_al)
        aligns = [
            ("Left", "align_left"), ("Center H", "align_hcenter"), ("Right", "align_right"),
            ("Top", "align_top"), ("Middle V", "align_vcenter"), ("Bottom", "align_bottom"),
            ("Dist H", "dist_h"), ("Dist V", "dist_v"), ("To Artboard", "align_artboard_center"),
        ]
        for idx, (lbl, cmd) in enumerate(aligns):
            b = QPushButton(lbl)
            b.clicked.connect(lambda _=False, c=cmd: self.command_requested.emit(c))
            ag.addWidget(b, idx // 3, idx % 3)
        lay.addWidget(grp_al)

        # Pathfinder
        grp_pf = QGroupBox("Pathfinder")
        pg = QGridLayout(grp_pf)
        pfs = [
            ("Unite", "pf_unite"), ("Minus Front", "pf_minus"), ("Intersect", "pf_intersect"),
            ("Exclude", "pf_exclude"), ("Divide", "pf_divide"), ("Trim", "pf_trim"),
            ("Crop", "pf_crop"), ("Outline", "pf_outline"), ("Minus Back", "pf_minus_back"),
        ]
        for idx, (lbl, cmd) in enumerate(pfs):
            b = QPushButton(lbl)
            b.clicked.connect(lambda _=False, c=cmd: self.command_requested.emit(c))
            pg.addWidget(b, idx // 3, idx % 3)
        lay.addWidget(grp_pf)

        # Quick Actions
        grp_qa = QGroupBox("Quick Actions")
        qg = QGridLayout(grp_qa)
        qas = [
            ("Recolor Artwork", "recolor"), ("✦ Text to Vector", "ai_generate"),
            ("Offset Path...", "offset_path"), ("Simplify Path...", "simplify_path"),
            ("Radial Repeat", "repeat_radial"), ("Grid Repeat", "repeat_grid"),
            ("Mirror Repeat", "repeat_mirror"), ("Make Blend", "make_blend"),
            ("3D Extrude...", "effect_3d"), ("Envelope Warp...", "effect_warp"),
            ("Create Mockup...", "create_mockup"), ("Global Edit", "toggle_global_edit"),
        ]
        for idx, (lbl, cmd) in enumerate(qas):
            b = QPushButton(lbl)
            if cmd == "ai_generate":
                b.setObjectName("PrimaryButton")
            b.clicked.connect(lambda _=False, c=cmd: self.command_requested.emit(c))
            qg.addWidget(b, idx // 2, idx % 2)
        self.chk_text_wrap = QCheckBox("Wrap Area Text Around Object")
        self.chk_text_wrap.toggled.connect(self._on_text_wrap_toggled)
        qg.addWidget(self.chk_text_wrap, 6, 0, 1, 2)
        lay.addWidget(grp_qa)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # 2. Layers Tab
    # ------------------------------------------------------------------

    def _build_layers_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tree_layers = QTreeWidget()
        self.tree_layers.setHeaderLabels(["Layer / Object", "Vis", "Lock"])
        self.tree_layers.setColumnWidth(0, 170)
        self.tree_layers.setColumnWidth(1, 36)
        self.tree_layers.setColumnWidth(2, 36)
        self.tree_layers.itemClicked.connect(self._on_layer_item_clicked)
        lay.addWidget(self.tree_layers)

        row1 = QHBoxLayout()
        for lbl, fn in [("+ Layer", self._add_layer), ("Del Layer", self._del_layer),
                        ("Up", lambda: self._reorder_selected(-1)), ("Down", lambda: self._reorder_selected(1))]:
            b = QPushButton(lbl)
            b.clicked.connect(fn)
            row1.addWidget(b)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        for lbl, cmd in [("Group", "group"), ("Ungroup", "ungroup"), ("Clip Mask", "clip_mask"), ("Opacity Mask", "opacity_mask")]:
            b = QPushButton(lbl)
            b.clicked.connect(lambda _=False, c=cmd: self.command_requested.emit(c))
            row2.addWidget(b)
        lay.addLayout(row2)
        return w

    # ------------------------------------------------------------------
    # 3. Appearance & Graphic Styles Tab
    # ------------------------------------------------------------------

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        grp = QGroupBox("Appearance Stack (Editable Fills, Strokes & Live Effects)")
        gl = QVBoxLayout(grp)
        self.list_appearance = QListWidget()
        self.list_appearance.setMaximumHeight(210)
        gl.addWidget(self.list_appearance)

        row = QHBoxLayout()
        b_af = QPushButton("+ Fill")
        b_af.clicked.connect(self._add_appearance_fill)
        b_as = QPushButton("+ Stroke")
        b_as.clicked.connect(self._add_appearance_stroke)
        b_rm = QPushButton("Remove")
        b_rm.clicked.connect(self._remove_appearance_item)
        row.addWidget(b_af); row.addWidget(b_as); row.addWidget(b_rm)
        gl.addLayout(row)

        fx_row = QHBoxLayout()
        self.cb_add_fx = QComboBox()
        self.cb_add_fx.addItems(["drop_shadow", "outer_glow", "inner_glow", "gaussian_blur", "warp", "roughen", "offset_path", "extrude_3d"])
        b_fx = QPushButton("+ Add Live Effect")
        b_fx.setObjectName("PrimaryButton")
        b_fx.clicked.connect(self._add_live_effect)
        fx_row.addWidget(self.cb_add_fx); fx_row.addWidget(b_fx)
        gl.addLayout(fx_row)
        lay.addWidget(grp)

        grp_st = QGroupBox("Graphic Styles")
        sl = QVBoxLayout(grp_st)
        self.list_styles = QListWidget()
        self.list_styles.setMaximumHeight(160)
        self.list_styles.itemClicked.connect(self._apply_graphic_style)
        sl.addWidget(self.list_styles)
        b_save_st = QPushButton("+ Save Selection as Graphic Style")
        b_save_st.clicked.connect(self._save_graphic_style)
        sl.addWidget(b_save_st)
        lay.addWidget(grp_st)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # 4. Color, Swatches, Gradient, Mesh & Pattern Tab
    # ------------------------------------------------------------------

    def _build_color_gradient_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        grp_c = QGroupBox("Color & Print Ink (RGB / CMYK / Spot)")
        cl = QVBoxLayout(grp_c)
        row_t = QHBoxLayout()
        self.cb_color_target = QComboBox()
        self.cb_color_target.addItems(["Fill", "Stroke"])
        self.ed_hex = QLineEdit("#FF9A00")
        b_pick = QPushButton("Picker...")
        b_pick.clicked.connect(self._open_color_picker)
        b_none = QPushButton("None")
        b_none.clicked.connect(self._set_color_none)
        row_t.addWidget(self.cb_color_target); row_t.addWidget(self.ed_hex); row_t.addWidget(b_pick); row_t.addWidget(b_none)
        cl.addLayout(row_t)

        # CMYK Sliders
        self.cmyk_sliders = {}
        for ch, tint in [("C", "#00C2FF"), ("M", "#FF2E93"), ("Y", "#FFD166"), ("K", "#94A3B8")]:
            hr = QHBoxLayout()
            lbl = QLabel(ch)
            lbl.setFixedWidth(16)
            lbl.setStyleSheet(f"color: {tint}; font-weight: 700;")
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 100)
            sl.valueChanged.connect(self._on_cmyk_slider)
            self.cmyk_sliders[ch] = sl
            hr.addWidget(lbl); hr.addWidget(sl)
            cl.addLayout(hr)

        self.chk_overprint = QCheckBox("Overprint Fill / Stroke")
        self.chk_overprint.toggled.connect(self._on_overprint_toggled)
        cl.addWidget(self.chk_overprint)

        b_recolor = QPushButton("Recolor Artwork / Generative Palette...")
        b_recolor.setObjectName("PrimaryButton")
        b_recolor.clicked.connect(lambda: self.command_requested.emit("recolor"))
        cl.addWidget(b_recolor)
        lay.addWidget(grp_c)

        # Swatch Groups
        grp_sw = QGroupBox("Swatches & Color Groups")
        swl = QVBoxLayout(grp_sw)
        self.cb_swatch_group = QComboBox()
        self.cb_swatch_group.currentIndexChanged.connect(self._rebuild_swatch_grid)
        swl.addWidget(self.cb_swatch_group)
        self.swatch_grid_host = QWidget()
        self.swatch_grid = QGridLayout(self.swatch_grid_host)
        self.swatch_grid.setSpacing(4)
        swl.addWidget(self.swatch_grid_host)
        b_add_sw = QPushButton("+ Add Current Color to Swatches")
        b_add_sw.clicked.connect(self._add_current_swatch)
        swl.addWidget(b_add_sw)
        lay.addWidget(grp_sw)

        # Gradient (Linear, Radial, Freeform, Mesh) & Pattern
        grp_g = QGroupBox("Gradient (Linear / Radial / Freeform / Mesh) & Pattern")
        gl = QFormLayout(grp_g)
        self.cb_grad_kind = QComboBox()
        self.cb_grad_kind.addItems(["linear", "radial", "freeform", "mesh"])
        self.sl_grad_angle = QSlider(Qt.Horizontal)
        self.sl_grad_angle.setRange(0, 360)
        self.sl_grad_angle.setValue(35)
        self.cb_grad_stroke_mode = QComboBox()
        self.cb_grad_stroke_mode.addItems(["within", "along", "across"])
        b_apply_grad = QPushButton("Apply Gradient to Fill")
        b_apply_grad.clicked.connect(lambda: self._apply_gradient(to_stroke=False))
        b_apply_sgrad = QPushButton("Apply Gradient to Stroke")
        b_apply_sgrad.clicked.connect(lambda: self._apply_gradient(to_stroke=True))
        gl.addRow("Type", self.cb_grad_kind)
        gl.addRow("Angle", self.sl_grad_angle)
        gl.addRow("Stroke Mode", self.cb_grad_stroke_mode)
        gl.addRow(b_apply_grad, b_apply_sgrad)

        self.cb_pattern_kind = QComboBox()
        self.cb_pattern_kind.addItems(["dots", "stripes", "grid", "chevron", "waves", "terrazzo", "botanical", "stars", "memphis", "art_deco"])
        b_pat = QPushButton("Apply Pattern Fill")
        b_pat.clicked.connect(self._apply_pattern_fill)
        gl.addRow("Pattern", self.cb_pattern_kind)
        gl.addRow(b_pat)
        lay.addWidget(grp_g)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # 5. Stroke, Variable Width & Brushes Tab
    # ------------------------------------------------------------------

    def _build_stroke_brushes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        grp_s = QGroupBox("Stroke, Dashes & Variable Width")
        fl = QFormLayout(grp_s)
        self.sp_stroke_w = self._dspin(0.0, 200.0, 2.0)
        self.sp_stroke_w.valueChanged.connect(self._on_stroke_changed)
        self.cb_cap = QComboBox(); self.cb_cap.addItems(["round", "butt", "square"])
        self.cb_cap.currentTextChanged.connect(self._on_stroke_changed)
        self.cb_join = QComboBox(); self.cb_join.addItems(["round", "miter", "bevel"])
        self.cb_join.currentTextChanged.connect(self._on_stroke_changed)
        self.ed_dash = QLineEdit("")
        self.ed_dash.setPlaceholderText("e.g. 10, 6")
        self.ed_dash.editingFinished.connect(self._on_stroke_changed)
        self.chk_dash_corners = QCheckBox("Align Dashes to Corners & Ends")
        self.chk_dash_corners.setChecked(True)
        self.chk_dash_corners.toggled.connect(self._on_stroke_changed)
        self.cb_arrow_start = QComboBox(); self.cb_arrow_start.addItems(["none", "arrow", "dot", "diamond"])
        self.cb_arrow_start.currentTextChanged.connect(self._on_stroke_changed)
        self.cb_arrow_end = QComboBox(); self.cb_arrow_end.addItems(["none", "arrow", "dot", "diamond"])
        self.cb_arrow_end.currentTextChanged.connect(self._on_stroke_changed)
        self.cb_width_prof = QComboBox()
        self.cb_width_prof.addItems(list(WIDTH_PROFILES.keys()))
        self.cb_width_prof.currentTextChanged.connect(self._on_width_profile_changed)

        fl.addRow("Weight (px)", self.sp_stroke_w)
        fl.addRow("Cap", self.cb_cap)
        fl.addRow("Join", self.cb_join)
        fl.addRow("Dash Array", self.ed_dash)
        fl.addRow(self.chk_dash_corners)
        fl.addRow("Arrow Start", self.cb_arrow_start)
        fl.addRow("Arrow End", self.cb_arrow_end)
        fl.addRow("Width Profile", self.cb_width_prof)
        lay.addWidget(grp_s)

        grp_b = QGroupBox("Brushes (Calligraphic / Art / Scatter / Pattern / Bristle)")
        bl = QVBoxLayout(grp_b)
        self.list_brushes = QListWidget()
        self.list_brushes.setMaximumHeight(200)
        self.list_brushes.itemClicked.connect(self._apply_brush)
        bl.addWidget(self.list_brushes)
        b_new_br = QPushButton("+ New Custom Brush...")
        b_new_br.clicked.connect(self._create_custom_brush)
        bl.addWidget(b_new_br)
        lay.addWidget(grp_b)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # 6. Type, OpenType, Paragraph & Glyphs Tab
    # ------------------------------------------------------------------

    def _build_type_glyphs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        grp_t = QGroupBox("Character, Variable Fonts & OpenType")
        fl = QFormLayout(grp_t)
        self.cb_font = QComboBox()
        fams = QFontDatabase.families()
        self.cb_font.addItems(fams[:120] if fams else ["Segoe UI", "Arial", "Georgia", "Consolas"])
        self.cb_font.currentTextChanged.connect(self._on_type_changed)
        self.sp_font_size = self._dspin(6, 360, 36)
        self.sp_font_size.valueChanged.connect(self._on_type_changed)
        self.sl_weight = QSlider(Qt.Horizontal); self.sl_weight.setRange(100, 900); self.sl_weight.setValue(600)
        self.sl_weight.valueChanged.connect(self._on_type_changed)
        self.sl_width_var = QSlider(Qt.Horizontal); self.sl_width_var.setRange(50, 200); self.sl_width_var.setValue(100)
        self.sl_width_var.valueChanged.connect(self._on_type_changed)
        self.sp_leading = self._dspin(0.8, 3.0, 1.25)
        self.sp_leading.setSingleStep(0.05)
        self.sp_leading.valueChanged.connect(self._on_type_changed)
        self.sp_tracking = self._dspin(-10, 40, 0)
        self.sp_tracking.valueChanged.connect(self._on_type_changed)
        self.cb_text_align = QComboBox(); self.cb_text_align.addItems(["left", "center", "right"])
        self.cb_text_align.currentTextChanged.connect(self._on_type_changed)

        fl.addRow("Font Family", self.cb_font)
        fl.addRow("Size (px)", self.sp_font_size)
        fl.addRow("Var Weight", self.sl_weight)
        fl.addRow("Var Width %", self.sl_width_var)
        fl.addRow("Leading", self.sp_leading)
        fl.addRow("Tracking", self.sp_tracking)
        fl.addRow("Align", self.cb_text_align)

        ot_row = QGridLayout()
        self.chk_ot_liga = QCheckBox("Ligatures"); self.chk_ot_liga.setChecked(True)
        self.chk_ot_smcp = QCheckBox("Small Caps")
        self.chk_ot_tnum = QCheckBox("Tabular Figs")
        self.chk_ot_frac = QCheckBox("Fractions")
        for idx, chk in enumerate([self.chk_ot_liga, self.chk_ot_smcp, self.chk_ot_tnum, self.chk_ot_frac]):
            chk.toggled.connect(self._on_type_changed)
            ot_row.addWidget(chk, idx // 2, idx % 2)
        fl.addRow("OpenType", ot_row)

        btn_row = QHBoxLayout()
        b_out = QPushButton("Create Outlines")
        b_out.clicked.connect(lambda: self.command_requested.emit("create_outlines"))
        b_thr = QPushButton("Thread Text")
        b_thr.clicked.connect(lambda: self.command_requested.emit("thread_text"))
        btn_row.addWidget(b_out); btn_row.addWidget(b_thr)
        fl.addRow(btn_row)
        lay.addWidget(grp_t)

        # Glyphs Panel
        grp_g = QGroupBox("Glyphs Panel (Click to Insert)")
        gg = QGridLayout(grp_g)
        gg.setSpacing(3)
        glyphs = list("©®™§¶•†‡—–…«»€£¥¢°±×÷≈≠≤≥∞∑√πΩ★☆✦✧❖◆▲▼◀▶→←↑↓↔✓✕♪♫☀☾")
        for idx, ch in enumerate(glyphs):
            b = QPushButton(ch)
            b.setFixedSize(28, 28)
            b.setStyleSheet("padding: 0px; font-size: 11pt;")
            b.clicked.connect(lambda _=False, gch=ch: self._insert_glyph(gch))
            gg.addWidget(b, idx // 8, idx % 8)
        lay.addWidget(grp_g)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # 7. Symbols, Artboards & Links Tab
    # ------------------------------------------------------------------

    def _build_symbols_artboards_links_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        grp_sym = QGroupBox("Symbols (Edit Once -> Update All Instances)")
        sl = QVBoxLayout(grp_sym)
        self.list_symbols = QListWidget()
        self.list_symbols.setMaximumHeight(110)
        sl.addWidget(self.list_symbols)
        srow = QHBoxLayout()
        b_pl = QPushButton("Place"); b_pl.clicked.connect(self._place_selected_symbol)
        b_cr = QPushButton("+ From Sel"); b_cr.clicked.connect(self._create_symbol_from_selection)
        b_ed = QPushButton("Recolor All"); b_ed.clicked.connect(self._edit_symbol_color)
        srow.addWidget(b_pl); srow.addWidget(b_cr); srow.addWidget(b_ed)
        sl.addLayout(srow)
        lay.addWidget(grp_sym)

        grp_ab = QGroupBox("Artboards")
        al = QVBoxLayout(grp_ab)
        self.list_artboards = QListWidget()
        self.list_artboards.setMaximumHeight(110)
        self.list_artboards.currentRowChanged.connect(self._select_artboard_row)
        al.addWidget(self.list_artboards)
        arow = QHBoxLayout()
        b_ab_add = QPushButton("+ Add"); b_ab_add.clicked.connect(self._add_artboard)
        b_ab_dup = QPushButton("Duplicate"); b_ab_dup.clicked.connect(self._dup_artboard)
        b_ab_del = QPushButton("Delete"); b_ab_del.clicked.connect(self._del_artboard)
        arow.addWidget(b_ab_add); arow.addWidget(b_ab_dup); arow.addWidget(b_ab_del)
        al.addLayout(arow)
        lay.addWidget(grp_ab)

        grp_lk = QGroupBox("Links (Placed Images / PSD / PDF / SVG)")
        ll = QVBoxLayout(grp_lk)
        self.list_links = QListWidget()
        self.list_links.setMaximumHeight(110)
        ll.addWidget(self.list_links)
        lrow = QHBoxLayout()
        b_pl_f = QPushButton("Place File..."); b_pl_f.clicked.connect(lambda: self.command_requested.emit("place_file"))
        b_emb = QPushButton("Embed"); b_emb.clicked.connect(lambda: self.command_requested.emit("embed_image"))
        b_tr = QPushButton("Image Trace"); b_tr.clicked.connect(lambda: self.command_requested.emit("image_trace"))
        lrow.addWidget(b_pl_f); lrow.addWidget(b_emb); lrow.addWidget(b_tr)
        ll.addLayout(lrow)
        lay.addWidget(grp_lk)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # 8. Asset Export, CSS Snippets, Document Info, Separations & Flattener
    # ------------------------------------------------------------------

    def _build_export_proof_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        grp_ast = QGroupBox("Asset Export (Multi-Scale Screen Assets)")
        al = QVBoxLayout(grp_ast)
        self.list_assets = QListWidget()
        self.list_assets.setMaximumHeight(95)
        al.addWidget(self.list_assets)
        arow = QHBoxLayout()
        b_add_a = QPushButton("+ Add Selection"); b_add_a.clicked.connect(self._add_export_asset)
        b_exp_a = QPushButton("Batch Export..."); b_exp_a.setObjectName("PrimaryButton"); b_exp_a.clicked.connect(self._batch_export_assets)
        arow.addWidget(b_add_a); arow.addWidget(b_exp_a)
        al.addLayout(arow)
        lay.addWidget(grp_ast)

        grp_css = QGroupBox("CSS Properties Snippet")
        cl = QVBoxLayout(grp_css)
        self.txt_css = QPlainTextEdit()
        self.txt_css.setReadOnly(True)
        self.txt_css.setMaximumHeight(125)
        self.txt_css.setStyleSheet("font-family: Consolas, monospace; font-size: 8.5pt;")
        cl.addWidget(self.txt_css)
        lay.addWidget(grp_css)

        grp_sep = QGroupBox("Separations, Overprint & Flattener Preview")
        sl = QVBoxLayout(grp_sep)
        self.chk_sep_enable = QCheckBox("Enable Separations Preview")
        self.chk_sep_enable.toggled.connect(self._on_proof_changed)
        sl.addWidget(self.chk_sep_enable)
        plates_row = QHBoxLayout()
        self.chk_plates = {}
        for pl in ("C", "M", "Y", "K"):
            cb = QCheckBox(pl); cb.setChecked(True)
            cb.toggled.connect(self._on_proof_changed)
            self.chk_plates[pl] = cb
            plates_row.addWidget(cb)
        sl.addLayout(plates_row)
        self.chk_overprint_prev = QCheckBox("Overprint Preview (CMYK Proof)")
        self.chk_flattener_prev = QCheckBox("Flattener Preview (Highlight Transparency)")
        self.chk_pixel_prev = QCheckBox("Pixel Preview (Screen Raster Grid)")
        for cb in (self.chk_overprint_prev, self.chk_flattener_prev, self.chk_pixel_prev):
            cb.toggled.connect(self._on_proof_changed)
            sl.addWidget(cb)
        lay.addWidget(grp_sep)

        grp_info = QGroupBox("Document Info")
        il = QVBoxLayout(grp_info)
        self.lbl_doc_info = QLabel("Ready")
        self.lbl_doc_info.setWordWrap(True)
        il.addWidget(self.lbl_doc_info)
        lay.addWidget(grp_info)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # 9. Actions, Scripts, Variables, Libraries & Version History
    # ------------------------------------------------------------------

    def _build_automation_versions_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        grp_act = QGroupBox("Actions Recorder")
        al = QHBoxLayout(grp_act)
        self.btn_rec = QPushButton("● Record")
        self.btn_rec.clicked.connect(self._toggle_record_action)
        b_play = QPushButton("▶ Play Action")
        b_play.clicked.connect(self._play_recorded_action)
        al.addWidget(self.btn_rec); al.addWidget(b_play)
        lay.addWidget(grp_act)

        grp_scr = QGroupBox("Document Script Runner (Python API)")
        scl = QVBoxLayout(grp_scr)
        self.txt_script = QPlainTextEdit(
            "# Live KinoDraw API: `doc`, `canvas`, `VectorObject`, `Color`\n"
            "for i in range(5):\n"
            "    doc.add_object(VectorObject(name=f'AutoStar {i}', kind='shape', shape_type='star',\n"
            "        x=120+i*95, y=620, width=64, height=64))\n"
            "canvas.push_undo('Script Run')\n"
        )
        self.txt_script.setMaximumHeight(105)
        self.txt_script.setStyleSheet("font-family: Consolas, monospace; font-size: 8pt;")
        scl.addWidget(self.txt_script)
        b_run = QPushButton("▶ Run Script on Document")
        b_run.setObjectName("KinoAccentButton")
        b_run.clicked.connect(self._run_user_script)
        scl.addWidget(b_run)
        lay.addWidget(grp_scr)

        grp_var = QGroupBox("Variables (CSV Data-Driven Graphics)")
        vl = QVBoxLayout(grp_var)
        vrow = QHBoxLayout()
        self.ed_var_bind = QLineEdit()
        self.ed_var_bind.setPlaceholderText("Bind selected text to column name")
        b_bind = QPushButton("Bind"); b_bind.clicked.connect(self._bind_variable)
        vrow.addWidget(self.ed_var_bind); vrow.addWidget(b_bind)
        vl.addLayout(vrow)
        vrow2 = QHBoxLayout()
        b_csv = QPushButton("Load CSV..."); b_csv.clicked.connect(self._load_variables_csv)
        b_nxt = QPushButton("Next Row ▶"); b_nxt.clicked.connect(self._next_variable_row)
        vrow2.addWidget(b_csv); vrow2.addWidget(b_nxt)
        vl.addLayout(vrow2)
        lay.addWidget(grp_var)

        grp_ver = QGroupBox("Cloud Documents & Version History")
        verl = QVBoxLayout(grp_ver)
        self.list_versions = QListWidget()
        self.list_versions.setMaximumHeight(120)
        verl.addWidget(self.list_versions)
        ver_row = QHBoxLayout()
        b_snap = QPushButton("+ Save Version"); b_snap.clicked.connect(self._save_version_snapshot)
        b_rest = QPushButton("Restore"); b_rest.clicked.connect(self._restore_version_snapshot)
        b_cloud = QPushButton("Cloud Save"); b_cloud.clicked.connect(lambda: self.command_requested.emit("cloud_save"))
        ver_row.addWidget(b_snap); ver_row.addWidget(b_rest); ver_row.addWidget(b_cloud)
        verl.addLayout(ver_row)
        lay.addWidget(grp_ver)
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # Sync UI From Active Canvas / Document
    # ------------------------------------------------------------------

    def refresh_all(self) -> None:
        self._syncing = True
        try:
            canvas = self._canvas()
            doc = canvas.doc
            sel = canvas.selected_objects()

            # Transform & Properties
            if sel:
                o = sel[0]
                br = canvas.selection_bounds()
                if br:
                    self.sp_x.setValue(br.x())
                    self.sp_y.setValue(br.y())
                    self.sp_w.setValue(max(1.0, br.width()))
                    self.sp_h.setValue(max(1.0, br.height()))
                self.sp_rot.setValue(o.rotation)
                self.sp_corner.setValue(o.corner_radius)
                self.sp_sides.setValue(max(3, o.sides))
                self.sl_opacity.setValue(int(round(o.appearance.opacity * 100)))
                self.cb_blend.setCurrentText(o.appearance.blend_mode)
                self.chk_text_wrap.setChecked(o.text_wrap)
                self.ed_var_bind.setText(o.variable_name)

                # Fill/Stroke controls
                f = o.appearance.primary_fill
                s = o.appearance.primary_stroke
                self.ed_hex.setText(f.color.to_hex() if self.cb_color_target.currentText() == "Fill" else s.color.to_hex())
                col = f.color if self.cb_color_target.currentText() == "Fill" else s.color
                self.cmyk_sliders["C"].setValue(int(col.c))
                self.cmyk_sliders["M"].setValue(int(col.m))
                self.cmyk_sliders["Y"].setValue(int(col.y))
                self.cmyk_sliders["K"].setValue(int(col.k))
                self.chk_overprint.setChecked(f.overprint)

                self.sp_stroke_w.setValue(s.width)
                self.cb_cap.setCurrentText(s.cap)
                self.cb_join.setCurrentText(s.join)
                self.ed_dash.setText(", ".join(str(x) for x in s.dash_pattern))
                self.chk_dash_corners.setChecked(s.dash_align_corners)
                self.cb_arrow_start.setCurrentText(s.arrow_start)
                self.cb_arrow_end.setCurrentText(s.arrow_end)
                if s.width_profile_name in WIDTH_PROFILES:
                    self.cb_width_prof.setCurrentText(s.width_profile_name)

                if o.kind == "text":
                    ts = o.text_style
                    self.cb_font.setCurrentText(ts.font_family)
                    self.sp_font_size.setValue(ts.font_size)
                    self.sl_weight.setValue(ts.font_weight)
                    self.sl_width_var.setValue(int(ts.font_width))
                    self.sp_leading.setValue(ts.leading)
                    self.sp_tracking.setValue(ts.tracking)
                    self.cb_text_align.setCurrentText(ts.align)
                    self.chk_ot_liga.setChecked(ts.ot_ligatures)
                    self.chk_ot_smcp.setChecked(ts.ot_small_caps)
                    self.chk_ot_tnum.setChecked(ts.ot_tabular_nums)
                    self.chk_ot_frac.setChecked(ts.ot_fractions)

                self.txt_css.setPlainText(generate_css_snippet(o, doc))
            else:
                self.txt_css.setPlainText("/* Select an object to inspect CSS properties */")

            # Layers Tree
            self.tree_layers.clear()
            for lyr in reversed(doc.layers):
                li = QTreeWidgetItem([lyr.name, "👁" if lyr.visible else "—", "🔒" if lyr.locked else ""])
                li.setData(0, Qt.UserRole, ("layer", lyr.id))
                if lyr.id == doc.active_layer_id:
                    li.setForeground(0, QColor("#FF9A00"))
                for obj in reversed(lyr.objects):
                    oi = QTreeWidgetItem([f"  {obj.name} ({obj.kind})", "👁" if obj.visible else "—", "🔒" if obj.locked else ""])
                    oi.setData(0, Qt.UserRole, ("obj", obj.id))
                    if obj.id in canvas.selected_ids:
                        oi.setSelected(True)
                    li.addChild(oi)
                self.tree_layers.addTopLevelItem(li)
                li.setExpanded(True)

            # Appearance Stack
            self.list_appearance.clear()
            if sel:
                app = sel[0].appearance
                for i, f in enumerate(app.fills):
                    self.list_appearance.addItem(f"Fill #{i + 1}: {f.fill_type} ({f.color.to_hex() if f.fill_type == 'solid' else f.fill_type})")
                for i, s in enumerate(app.strokes):
                    self.list_appearance.addItem(f"Stroke #{i + 1}: {s.width:.1f}px {s.stroke_type} ({s.color.to_hex()})")
                for i, fx in enumerate(app.effects):
                    self.list_appearance.addItem(f"fx {fx.kind} [{'ON' if fx.enabled else 'OFF'}]")

            # Graphic Styles & Brushes & Symbols & Artboards & Links & Assets & Versions
            self.list_styles.clear()
            for gs in doc.graphic_styles:
                it = QListWidgetItem(gs.name)
                it.setData(Qt.UserRole, gs.id)
                self.list_styles.addItem(it)

            self.list_brushes.clear()
            for br in doc.brushes:
                it = QListWidgetItem(f"{br.name}  [{br.kind}]")
                it.setData(Qt.UserRole, br.id)
                self.list_brushes.addItem(it)

            self.list_symbols.clear()
            for sym in doc.symbols:
                it = QListWidgetItem(sym.name)
                it.setData(Qt.UserRole, sym.id)
                self.list_symbols.addItem(it)

            self.list_artboards.blockSignals(True)
            self.list_artboards.clear()
            for idx, ab in enumerate(doc.artboards):
                self.list_artboards.addItem(f"{idx + 1}. {ab.name} ({int(ab.width)}×{int(ab.height)})")
            self.list_artboards.setCurrentRow(doc.active_artboard_index)
            self.list_artboards.blockSignals(False)

            self.list_links.clear()
            for o in doc.iter_all_objects(include_hidden=True):
                if o.kind == "image":
                    status = "Linked" if o.image_is_linked else "Embedded"
                    it = QListWidgetItem(f"{o.name} [{status}] {o.image_orig_w}×{o.image_orig_h}")
                    it.setData(Qt.UserRole, o.id)
                    self.list_links.addItem(it)

            self.list_assets.clear()
            for ast in doc.assets:
                self.list_assets.addItem(f"{ast.name} ({','.join(ast.formats)} @ {','.join(str(x)+'x' for x in ast.scales)})")

            self.list_versions.clear()
            for v in reversed(doc.versions):
                ts_str = datetime.datetime.fromtimestamp(v.timestamp).strftime("%H:%M:%S")
                it = QListWidgetItem(f"{v.label}  ({ts_str})")
                it.setData(Qt.UserRole, v.id)
                self.list_versions.addItem(it)

            # Swatch groups dropdown
            cur_g = max(0, self.cb_swatch_group.currentIndex())
            self.cb_swatch_group.blockSignals(True)
            self.cb_swatch_group.clear()
            for sg in doc.swatch_groups:
                self.cb_swatch_group.addItem(sg.name)
            self.cb_swatch_group.setCurrentIndex(min(cur_g, max(0, len(doc.swatch_groups) - 1)))
            self.cb_swatch_group.blockSignals(False)
            self._rebuild_swatch_grid()

            # Document Info
            all_objs = doc.iter_all_objects(include_hidden=True)
            anchors = sum(len(sp.anchors) for o in all_objs for sp in o.subpaths)
            fonts = sorted({o.text_style.font_family for o in all_objs if o.kind == "text"})
            links = sum(1 for o in all_objs if o.kind == "image")
            self.lbl_doc_info.setText(
                f"Mode: {doc.color_mode} | Bleed: {doc.bleed:.0f}px\n"
                f"Artboards: {len(doc.artboards)} | Layers: {len(doc.layers)} | Objects: {len(all_objs)}\n"
                f"Bezier Anchors: {anchors} | Linked/Placed: {links}\n"
                f"Fonts: {', '.join(fonts) if fonts else 'None'}"
            )
        finally:
            self._syncing = False

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _dspin(self, mn: float, mx: float, val: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(mn, mx)
        sp.setDecimals(1)
        sp.setValue(val)
        sp.setMaximumWidth(82)
        return sp

    def _apply_transform_fields(self) -> None:
        if self._syncing:
            return
        c = self._canvas()
        sel = c.selected_objects()
        if not sel:
            return
        br = c.selection_bounds()
        if br:
            dx = self.sp_x.value() - br.x()
            dy = self.sp_y.value() - br.y()
            sx = self.sp_w.value() / max(1.0, br.width())
            sy = self.sp_h.value() / max(1.0, br.height())
            for o in sel:
                if abs(dx) > 0.05 or abs(dy) > 0.05:
                    translate_object(o, dx, dy)
                if abs(sx - 1.0) > 0.005 or abs(sy - 1.0) > 0.005:
                    from PySide6.QtGui import QTransform
                    tr = QTransform()
                    tr.translate(self.sp_x.value(), self.sp_y.value())
                    tr.scale(sx, sy)
                    tr.translate(-self.sp_x.value(), -self.sp_y.value())
                    transform_object_affine(o, tr, c.doc)
                o.rotation = self.sp_rot.value()
                o.corner_radius = self.sp_corner.value()
                o.sides = self.sp_sides.value()
            c.push_undo("Transform")

    def _on_opacity_changed(self, val: int) -> None:
        if self._syncing:
            return
        c = self._canvas()
        for o in c.selected_objects():
            o.appearance.opacity = val / 100.0
        c.update()

    def _on_blend_changed(self, mode: str) -> None:
        if self._syncing:
            return
        c = self._canvas()
        for o in c.selected_objects():
            o.appearance.blend_mode = mode
        c.push_undo("Blend Mode")

    def _on_text_wrap_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        c = self._canvas()
        for o in c.selected_objects():
            o.text_wrap = checked
        c.push_undo("Text Wrap")

    def _on_layer_item_clicked(self, item: QTreeWidgetItem, col: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, ident = data
        c = self._canvas()
        if kind == "layer":
            lyr = c.doc.get_layer(ident)
            if not lyr:
                return
            if col == 1:
                lyr.visible = not lyr.visible
                c.push_undo("Toggle Layer Visibility")
            elif col == 2:
                lyr.locked = not lyr.locked
                c.push_undo("Toggle Layer Lock")
            else:
                c.doc.active_layer_id = lyr.id
            self.refresh_all()
        else:
            obj = c.doc.find_object(ident)
            if not obj:
                return
            if col == 1:
                obj.visible = not obj.visible
                c.push_undo("Toggle Object Visibility")
            elif col == 2:
                obj.locked = not obj.locked
                c.push_undo("Toggle Object Lock")
            else:
                c.selected_ids = [obj.id]
                c.selection_changed.emit()
                c.update_contextual_bar()
                c.update()

    def _add_layer(self) -> None:
        doc = self._doc()
        palette = ["#FF9A00", "#00C2FF", "#06D6A0", "#EF476F", "#6E2CF2"]
        lyr = Layer(name=f"Layer {len(doc.layers) + 1}", color_tag=palette[len(doc.layers) % len(palette)])
        doc.layers.append(lyr)
        doc.active_layer_id = lyr.id
        self._canvas().push_undo("Add Layer")

    def _del_layer(self) -> None:
        doc = self._doc()
        if len(doc.layers) <= 1:
            return
        doc.layers = [l for l in doc.layers if l.id != doc.active_layer_id]
        doc.active_layer_id = doc.layers[-1].id
        self._canvas().push_undo("Delete Layer")

    def _reorder_selected(self, direction: int) -> None:
        c = self._canvas()
        for oid in c.selected_ids:
            lyr = c.doc.find_object_layer(oid)
            if not lyr:
                continue
            for idx, o in enumerate(lyr.objects):
                if o.id == oid:
                    ni = max(0, min(len(lyr.objects) - 1, idx - direction))
                    lyr.objects.insert(ni, lyr.objects.pop(idx))
                    break
        c.push_undo("Arrange Order")

    def _add_appearance_fill(self) -> None:
        c = self._canvas()
        for o in c.selected_objects():
            o.appearance.fills.insert(0, AppearanceFill(color=copy.deepcopy(c.active_fill_color), opacity=0.75))
        c.push_undo("Add Appearance Fill")

    def _add_appearance_stroke(self) -> None:
        c = self._canvas()
        for o in c.selected_objects():
            o.appearance.strokes.insert(0, AppearanceStroke(color=Color.from_hex("#FFFFFF"), width=4.0))
        c.push_undo("Add Appearance Stroke")

    def _remove_appearance_item(self) -> None:
        c = self._canvas()
        row = self.list_appearance.currentRow()
        sel = c.selected_objects()
        if not sel or row < 0:
            return
        app = sel[0].appearance
        nf, ns = len(app.fills), len(app.strokes)
        if row < nf and nf > 1:
            app.fills.pop(row)
        elif nf <= row < nf + ns and ns > 1:
            app.strokes.pop(row - nf)
        elif row >= nf + ns:
            idx = row - nf - ns
            if 0 <= idx < len(app.effects):
                app.effects.pop(idx)
        c.push_undo("Remove Appearance Item")

    def _add_live_effect(self) -> None:
        c = self._canvas()
        kind = self.cb_add_fx.currentText()
        defaults = {
            "drop_shadow": {"dx": 6, "dy": 8, "blur": 12, "color": "#000000", "opacity": 0.38},
            "outer_glow": {"color": "#00C2FF", "blur": 14, "opacity": 0.78},
            "inner_glow": {"color": "#FFFFFF", "blur": 10, "opacity": 0.55},
            "gaussian_blur": {"blur": 8},
            "warp": {"style": "arc", "bend": 0.35},
            "roughen": {"amount": 5.0, "detail": 24},
            "offset_path": {"offset": 10.0, "join": "round"},
            "extrude_3d": {"depth": 26, "angle_x": -22, "angle_y": 28, "material": "glossy"},
        }
        for o in c.selected_objects():
            o.appearance.effects.append(LiveEffect(kind=kind, params=defaults.get(kind, {})))
        c.push_undo(f"Add Effect {kind}")

    def _apply_graphic_style(self, item: QListWidgetItem) -> None:
        sid = item.data(Qt.UserRole)
        c = self._canvas()
        style = next((s for s in c.doc.graphic_styles if s.id == sid), None)
        if not style:
            return
        for o in c.selected_objects():
            o.appearance = copy.deepcopy(style.appearance)
        c.push_undo(f"Apply Style {style.name}")

    def _save_graphic_style(self) -> None:
        c = self._canvas()
        sel = c.selected_objects()
        if not sel:
            return
        name, ok = QInputDialog.getText(self, "New Graphic Style", "Style name:", text=f"Style {len(c.doc.graphic_styles) + 1}")
        if ok and name:
            c.doc.graphic_styles.append(GraphicStyle(name=name, appearance=copy.deepcopy(sel[0].appearance)))
            c.push_undo("Save Graphic Style")

    def _open_color_picker(self) -> None:
        qc = QColorDialog.getColor(QColor(self.ed_hex.text()), self, "Choose Color")
        if qc.isValid():
            self._apply_solid_color(Color(qc.red(), qc.green(), qc.blue(), 255))

    def _set_color_none(self) -> None:
        c = self._canvas()
        is_fill = (self.cb_color_target.currentText() == "Fill")
        if is_fill:
            c.active_fill_enabled = False
        else:
            c.active_stroke_enabled = False
        for o in c.selected_objects():
            if is_fill:
                o.appearance.primary_fill.fill_type = "none"
            else:
                o.appearance.primary_stroke.stroke_type = "none"
        c.push_undo("Clear Color")

    def _apply_solid_color(self, col: Color) -> None:
        c = self._canvas()
        is_fill = (self.cb_color_target.currentText() == "Fill")
        if is_fill:
            c.active_fill_color = copy.deepcopy(col)
            c.active_fill_enabled = True
        else:
            c.active_stroke_color = copy.deepcopy(col)
            c.active_stroke_enabled = True
        for o in c.selected_objects() + c.global_edit_matches():
            if is_fill:
                o.appearance.primary_fill.fill_type = "solid"
                o.appearance.primary_fill.color = copy.deepcopy(col)
            else:
                o.appearance.primary_stroke.stroke_type = "solid"
                o.appearance.primary_stroke.color = copy.deepcopy(col)
                if o.appearance.primary_stroke.width < 0.5:
                    o.appearance.primary_stroke.width = 2.0
        c.push_undo("Set Color")

    def _on_cmyk_slider(self) -> None:
        if self._syncing:
            return
        col = Color.from_cmyk(
            self.cmyk_sliders["C"].value(),
            self.cmyk_sliders["M"].value(),
            self.cmyk_sliders["Y"].value(),
            self.cmyk_sliders["K"].value(),
        )
        self._apply_solid_color(col)

    def _on_overprint_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        c = self._canvas()
        for o in c.selected_objects():
            o.appearance.primary_fill.overprint = checked
            o.appearance.primary_stroke.overprint = checked
        c.push_undo("Toggle Overprint")

    def _rebuild_swatch_grid(self) -> None:
        while self.swatch_grid.count():
            w = self.swatch_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        doc = self._doc()
        idx = self.cb_swatch_group.currentIndex()
        if idx < 0 or idx >= len(doc.swatch_groups):
            return
        sg = doc.swatch_groups[idx]
        for i, col in enumerate(sg.colors):
            b = QPushButton()
            b.setFixedSize(26, 22)
            tip = f"{col.spot_name} ({col.to_hex()})" if col.spot_name else f"{col.to_hex()} (CMYK {int(col.c)}/{int(col.m)}/{int(col.y)}/{int(col.k)})"
            b.setToolTip(tip)
            b.setStyleSheet(f"background-color: {col.to_hex()}; border: 1px solid #495672; border-radius: 4px;")
            b.clicked.connect(lambda _=False, cc=copy.deepcopy(col): self._apply_solid_color(cc))
            self.swatch_grid.addWidget(b, i // 6, i % 6)

    def _add_current_swatch(self) -> None:
        doc = self._doc()
        idx = max(0, self.cb_swatch_group.currentIndex())
        if idx < len(doc.swatch_groups):
            doc.swatch_groups[idx].colors.append(Color.from_hex(self.ed_hex.text()))
            self._rebuild_swatch_grid()

    def _apply_gradient(self, to_stroke: bool) -> None:
        c = self._canvas()
        g = GradientDef(
            kind=self.cb_grad_kind.currentText(),
            angle=float(self.sl_grad_angle.value()),
            stroke_mode=self.cb_grad_stroke_mode.currentText(),
            stops=[
                GradientStop(0.0, copy.deepcopy(c.active_fill_color)),
                GradientStop(1.0, Color.from_hex("#00C2FF")),
            ],
        )
        if g.kind == "freeform":
            g.ensure_freeform()
        elif g.kind == "mesh":
            g.ensure_mesh()
        for o in c.selected_objects():
            if to_stroke:
                st = o.appearance.primary_stroke
                st.stroke_type = "gradient"
                st.gradient = copy.deepcopy(g)
                if st.width < 2.0:
                    st.width = 8.0
            else:
                o.appearance.primary_fill.fill_type = "gradient"
                o.appearance.primary_fill.gradient = copy.deepcopy(g)
        c.push_undo("Apply Gradient")

    def _apply_pattern_fill(self) -> None:
        c = self._canvas()
        pat = PatternDef(
            name=self.cb_pattern_kind.currentText().title(),
            kind=self.cb_pattern_kind.currentText(),
            bg_color=Color.from_hex("#181C25"),
            fg_color=copy.deepcopy(c.active_fill_color),
            accent_color=Color.from_hex("#00C2FF"),
        )
        for o in c.selected_objects():
            o.appearance.primary_fill.fill_type = "pattern"
            o.appearance.primary_fill.pattern = copy.deepcopy(pat)
        c.push_undo("Apply Pattern Fill")

    def _on_stroke_changed(self) -> None:
        if self._syncing:
            return
        c = self._canvas()
        c.active_stroke_width = self.sp_stroke_w.value()
        dashes: List[float] = []
        raw = self.ed_dash.text().strip()
        if raw:
            try:
                dashes = [max(0.5, float(x.strip())) for x in raw.split(",") if x.strip()]
            except ValueError:
                dashes = []
        for o in c.selected_objects():
            st = o.appearance.primary_stroke
            st.width = self.sp_stroke_w.value()
            st.stroke_type = "none" if st.width <= 0.01 else ("gradient" if st.stroke_type == "gradient" else "solid")
            st.cap = self.cb_cap.currentText()
            st.join = self.cb_join.currentText()
            st.dash_pattern = list(dashes)
            st.dash_align_corners = self.chk_dash_corners.isChecked()
            st.arrow_start = self.cb_arrow_start.currentText()
            st.arrow_end = self.cb_arrow_end.currentText()
        c.push_undo("Stroke Settings")

    def _on_width_profile_changed(self, name: str) -> None:
        if self._syncing:
            return
        c = self._canvas()
        for o in c.selected_objects():
            st = o.appearance.primary_stroke
            st.width_profile_name = name
            st.width_stations = []
            if st.stroke_type == "none":
                st.stroke_type = "solid"
            if st.width < 4.0 and name != "Uniform":
                st.width = 10.0
        c.push_undo("Width Profile")

    def _apply_brush(self, item: QListWidgetItem) -> None:
        bid = item.data(Qt.UserRole)
        c = self._canvas()
        c.active_brush_id = None if bid == "br_basic" else bid
        for o in c.selected_objects():
            st = o.appearance.primary_stroke
            st.brush_id = c.active_brush_id
            if st.stroke_type == "none":
                st.stroke_type = "solid"
                st.width = max(4.0, st.width)
        c.push_undo("Apply Brush")

    def _create_custom_brush(self) -> None:
        kind, ok = QInputDialog.getItem(self, "New Brush", "Brush Type:", ["calligraphic", "art", "scatter", "pattern", "bristle"], 0, False)
        if not ok:
            return
        name, ok2 = QInputDialog.getText(self, "Brush Name", "Name:", text=f"Custom {kind.title()}")
        if ok2 and name:
            self._doc().brushes.append(BrushDef(name=name, kind=kind, size=14.0))
            self._canvas().push_undo("Create Brush")

    def _on_type_changed(self) -> None:
        if self._syncing:
            return
        c = self._canvas()
        for o in c.selected_objects():
            if o.kind == "text":
                ts = o.text_style
                ts.font_family = self.cb_font.currentText()
                ts.font_size = self.sp_font_size.value()
                ts.font_weight = self.sl_weight.value()
                ts.font_width = float(self.sl_width_var.value())
                ts.leading = self.sp_leading.value()
                ts.tracking = self.sp_tracking.value()
                ts.align = self.cb_text_align.currentText()
                ts.ot_ligatures = self.chk_ot_liga.isChecked()
                ts.ot_small_caps = self.chk_ot_smcp.isChecked()
                ts.ot_tabular_nums = self.chk_ot_tnum.isChecked()
                ts.ot_fractions = self.chk_ot_frac.isChecked()
        c.push_undo("Typography Update")

    def _insert_glyph(self, ch: str) -> None:
        c = self._canvas()
        for o in c.selected_objects():
            if o.kind == "text":
                o.text += ch
        c.push_undo("Insert Glyph")

    def _place_selected_symbol(self) -> None:
        it = self.list_symbols.currentItem()
        if not it:
            return
        sid = it.data(Qt.UserRole)
        c = self._canvas()
        ab = c.doc.active_artboard()
        inst = VectorObject(name=f"{it.text()} Instance", kind="symbol_instance", symbol_id=sid,
                            x=ab.x + ab.width * 0.5 - 40, y=ab.y + ab.height * 0.5 - 40, width=80, height=80)
        c.doc.add_object(inst)
        c.selected_ids = [inst.id]
        c.selection_changed.emit()
        c.push_undo("Place Symbol")

    def _create_symbol_from_selection(self) -> None:
        c = self._canvas()
        sel = c.selected_objects()
        if not sel:
            return
        name, ok = QInputDialog.getText(self, "Create Symbol", "Symbol Name:", text=sel[0].name)
        if ok and name:
            c.doc.symbols.append(SymbolDef(name=name, artwork=sel[0].clone()))
            c.push_undo("Create Symbol")

    def _edit_symbol_color(self) -> None:
        it = self.list_symbols.currentItem()
        if not it:
            return
        sym = self._doc().get_symbol(it.data(Qt.UserRole))
        if not sym:
            return
        qc = QColorDialog.getColor(QColor("#FF9A00"), self, f"Update All Instances of {sym.name}")
        if qc.isValid():
            sym.artwork.appearance.primary_fill.color = Color(qc.red(), qc.green(), qc.blue(), 255)
            self._canvas().push_undo("Edit Symbol Definition")

    def _select_artboard_row(self, row: int) -> None:
        if self._syncing or row < 0:
            return
        c = self._canvas()
        if row < len(c.doc.artboards):
            c.doc.active_artboard_index = row
            c.fit_artboard(c.doc.artboards[row])

    def _add_artboard(self) -> None:
        doc = self._doc()
        last = doc.artboards[-1]
        ab = Artboard(name=f"Artboard {len(doc.artboards) + 1}", x=last.x + last.width + 80, y=last.y, width=last.width, height=last.height)
        doc.artboards.append(ab)
        doc.active_artboard_index = len(doc.artboards) - 1
        self._canvas().push_undo("Add Artboard")

    def _dup_artboard(self) -> None:
        doc = self._doc()
        cur = doc.active_artboard()
        ab = Artboard(name=f"{cur.name} Copy", x=cur.x + cur.width + 80, y=cur.y, width=cur.width, height=cur.height, bg_color=copy.deepcopy(cur.bg_color))
        doc.artboards.append(ab)
        self._canvas().push_undo("Duplicate Artboard")

    def _del_artboard(self) -> None:
        doc = self._doc()
        if len(doc.artboards) <= 1:
            return
        doc.artboards.pop(doc.active_artboard_index)
        doc.active_artboard_index = max(0, doc.active_artboard_index - 1)
        self._canvas().push_undo("Delete Artboard")

    def _add_export_asset(self) -> None:
        c = self._canvas()
        if not c.selected_ids:
            return
        name, ok = QInputDialog.getText(self, "Add Asset", "Asset filename stem:", text=f"asset_{len(c.doc.assets) + 1}")
        if ok and name:
            c.doc.assets.append(AssetExportItem(name=name, object_ids=list(c.selected_ids), scales=[1.0, 2.0], formats=["PNG", "SVG"]))
            c.push_undo("Add Export Asset")

    def _batch_export_assets(self) -> None:
        doc = self._doc()
        if not doc.assets:
            QMessageBox.information(self, "Asset Export", "Select artwork and click '+ Add Selection' first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose Asset Export Folder")
        if not folder:
            return
        count = 0
        for ast in doc.assets:
            objs = [o for oid in ast.object_ids if (o := doc.find_object(oid))]
            if not objs:
                continue
            for fmt in ast.formats:
                if fmt == "SVG":
                    export_svg(doc, os.path.join(folder, f"{ast.name}.svg"), objects=objs)
                    count += 1
                else:
                    for sc in ast.scales:
                        sfx = "" if abs(sc - 1.0) < 0.01 else f"@{sc:g}x"
                        export_raster(doc, os.path.join(folder, f"{ast.name}{sfx}.{fmt.lower()}"), fmt=fmt, scale=sc, objects=objs)
                        count += 1
        QMessageBox.information(self, "Asset Export", f"Exported {count} asset files to:\n{folder}")

    def _on_proof_changed(self) -> None:
        c = self._canvas()
        c.view_opts.separations_preview = self.chk_sep_enable.isChecked()
        for k, cb in self.chk_plates.items():
            c.view_opts.sep_plates[k] = cb.isChecked()
        c.view_opts.overprint_preview = self.chk_overprint_prev.isChecked()
        c.view_opts.flattener_preview = self.chk_flattener_prev.isChecked()
        c.view_opts.pixel_preview = self.chk_pixel_prev.isChecked()
        c.update()

    def record_command_if_active(self, cmd: str) -> None:
        if self._recording_action:
            self._recorded_commands.append(cmd)

    def _toggle_record_action(self) -> None:
        self._recording_action = not self._recording_action
        if self._recording_action:
            self._recorded_commands = []
            self.btn_rec.setText("■ Stop Rec")
            self.btn_rec.setObjectName("PrimaryButton")
        else:
            self.btn_rec.setText(f"● Record ({len(self._recorded_commands)})")
            self.btn_rec.setObjectName("")
        self.btn_rec.style().polish(self.btn_rec)

    def _play_recorded_action(self) -> None:
        for cmd in list(self._recorded_commands):
            self.command_requested.emit(cmd)

    def _run_user_script(self) -> None:
        c = self._canvas()
        code = self.txt_script.toPlainText()
        env = {"doc": c.doc, "canvas": c, "VectorObject": VectorObject, "Color": Color}
        try:
            exec(code, env)
            c.update()
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Script Error", str(exc))

    def _bind_variable(self) -> None:
        c = self._canvas()
        col_name = self.ed_var_bind.text().strip()
        for o in c.selected_objects():
            o.variable_name = col_name
        c.push_undo("Bind Variable")

    def _load_variables_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open CSV Dataset", "", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if rows:
            doc = self._doc()
            doc.variables_datasets = rows
            doc.active_dataset_index = -1
            self._next_variable_row()

    def _next_variable_row(self) -> None:
        doc = self._doc()
        if not doc.variables_datasets:
            return
        doc.active_dataset_index = (doc.active_dataset_index + 1) % len(doc.variables_datasets)
        row = doc.variables_datasets[doc.active_dataset_index]
        for o in doc.iter_all_objects(include_hidden=True):
            if o.variable_name and o.variable_name in row:
                if o.kind == "text":
                    o.text = row[o.variable_name]
        self._canvas().push_undo(f"Dataset Row {doc.active_dataset_index + 1}")

    def _save_version_snapshot(self) -> None:
        lbl, ok = QInputDialog.getText(self, "Save Version", "Snapshot label:", text=f"Milestone {len(self._doc().versions) + 1}")
        if ok:
            self._doc().save_version(lbl)
            self.refresh_all()

    def _restore_version_snapshot(self) -> None:
        it = self.list_versions.currentItem()
        if not it:
            return
        if self._doc().restore_version(it.data(Qt.UserRole)):
            self._canvas().push_undo("Restore Version")
