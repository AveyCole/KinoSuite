"""Main Window for KinoDraw — KinoSuite Vector Graphics Studio."""
from __future__ import annotations

import copy
import json
import os
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .canvas import VectorCanvas
from .dialogs import (
    Effect3DDialog,
    ExportScreensDialog,
    GenerativeAIDialog,
    GraphDataDialog,
    ImageTraceDialog,
    MockupDialog,
    NewDocumentDialog,
    PluginsDialog,
    PrintPdfDialog,
    RecolorArtworkDialog,
    ShortcutsDialog,
    WarpEffectDialog,
)
from .geometry import (
    WIDTH_PROFILES,
    convert_object_to_path,
    object_bounds,
    object_to_qpath,
    offset_qpath,
    outline_stroke_qpath,
    pathfinder_op,
    qpath_to_subpaths,
    simplify_subpaths,
    transform_object_affine,
    translate_object,
)
from .icons import get_tool_icon, make_app_pixmap
from .importers_exporters import (
    create_placed_image_object,
    export_print_pdf,
    export_raster,
    export_svg,
    import_svg_objects,
)
from .models import (
    Appearance,
    AppearanceFill,
    AppearanceStroke,
    Color,
    Document,
    LiveEffect,
    VectorObject,
)
from .panels import StudioPanels
from .plugins_builtin import load_all_plugins
from .sample_artwork import create_blank_document, create_showcase_document
from .trace_and_ai import generate_pattern_from_prompt, generate_vector_from_prompt

TOOL_DEFS: List[Tuple[str, str, str, str]] = [
    # (tool_id, icon_name, label, shortcut)
    ("select", "select", "Selection Tool", "V"),
    ("direct_select", "direct_select", "Direct Selection Tool", "A"),
    ("pen", "pen", "Pen Tool", "P"),
    ("curvature", "curvature", "Curvature Tool", "Shift+`"),
    ("pencil", "pencil", "Pencil Tool", "N"),
    ("blob_brush", "blob_brush", "Blob Brush Tool", "Shift+B"),
    ("shaper", "shaper", "Shaper Tool", "Shift+N"),
    ("rect", "rect", "Rectangle Tool", "M"),
    ("ellipse", "ellipse", "Ellipse Tool", "L"),
    ("polygon", "polygon", "Polygon Tool", ""),
    ("star", "star", "Star Tool", ""),
    ("line", "line", "Line Segment Tool", "\\"),
    ("type", "type", "Type Tool (Point)", "T"),
    ("area_type", "type", "Area Type Tool", ""),
    ("type_on_path", "curvature", "Type on a Path Tool", ""),
    ("touch_type", "touch_type", "Touch Type Tool", "Shift+T"),
    ("shape_builder", "shape_builder", "Shape Builder Tool", "Shift+M"),
    ("live_paint", "live_paint", "Live Paint Bucket", "K"),
    ("width", "width", "Variable Width Tool", "Shift+W"),
    ("scissors", "scissors", "Scissors Tool", "C"),
    ("knife", "knife", "Knife Tool", ""),
    ("rotate", "rotate", "Rotate Tool", "R"),
    ("scale", "scale", "Scale Tool", "S"),
    ("puppet_warp", "puppet_warp", "Puppet Warp Tool", ""),
    ("blend", "blend", "Blend Tool", "W"),
    ("gradient", "gradient", "Gradient Tool", "G"),
    ("eyedropper", "eyedropper", "Eyedropper Tool", "I"),
    ("perspective", "perspective", "Perspective Grid Tool", "Shift+P"),
    ("graph", "graph", "Data Graph Tool", "J"),
    ("symbol_sprayer", "symbol_sprayer", "Symbol Sprayer Tool", "Shift+S"),
    ("artboard", "artboard", "Artboard Tool", "Shift+O"),
    ("hand", "hand", "Hand Tool", "H"),
    ("zoom", "zoom", "Zoom Tool", "Z"),
]


class FillStrokeSwatchWidget(QWidget):
    """Classic Illustrator overlapping Fill & Stroke swatch box at the bottom of the Tools dock."""

    fill_clicked = Signal()
    stroke_clicked = Signal()
    swap_clicked = Signal()
    default_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 62)
        self.fill_color = QColor("#FF9A00")
        self.stroke_color = QColor("#141821")
        self.fill_enabled = True
        self.stroke_enabled = True
        self.setToolTip("Click Fill/Stroke to pick color • Top-right to Swap (Shift+X) • Bottom-left for Default (D)")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Stroke square (back bottom-right)
        sr = (24, 24, 28, 28)
        p.setPen(QPen(QColor("#8E98AB"), 1.2))
        p.setBrush(self.stroke_color if self.stroke_enabled else QColor("#222836"))
        p.drawRoundedRect(*sr, 3, 3)
        p.setBrush(QColor("#171B24"))
        p.drawRect(31, 31, 14, 14)
        if not self.stroke_enabled:
            p.setPen(QPen(QColor("#EF4444"), 2.0))
            p.drawLine(25, 51, 51, 25)

        # Fill square (front top-left)
        fr = (10, 10, 28, 28)
        p.setPen(QPen(QColor("#E2E8F0"), 1.3))
        p.setBrush(self.fill_color if self.fill_enabled else QColor("#222836"))
        p.drawRoundedRect(*fr, 3, 3)
        if not self.fill_enabled:
            p.setPen(QPen(QColor("#EF4444"), 2.0))
            p.drawLine(11, 37, 37, 11)

        # Swap double-arrow top-right
        p.setPen(QPen(QColor("#94A3B8"), 1.2))
        p.drawText(42, 18, "⇄")
        # Default mini icon bottom-left
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(8, 44, 8, 8)
        p.setBrush(QColor("#111111"))
        p.drawRect(12, 48, 8, 8)
        p.end()

    def mousePressEvent(self, event) -> None:
        x, y = event.position().x(), event.position().y()
        if x >= 40 and y <= 22:
            self.swap_clicked.emit()
        elif x <= 22 and y >= 40:
            self.default_clicked.emit()
        elif 10 <= x <= 38 and 10 <= y <= 38:
            self.fill_clicked.emit()
        elif 24 <= x <= 52 and 24 <= y <= 52:
            self.stroke_clicked.emit()


class KinoDrawWindow(QMainWindow):
    """Primary KinoDraw Studio Main Window."""

    def __init__(self, initial_files: Optional[List[str]] = None):
        super().__init__()
        self.setWindowTitle("KinoDraw — KinoSuite Vector Studio")
        self.setWindowIcon(QIcon(make_app_pixmap(64)))
        self.resize(1480, 900)

        self.app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cloud_dir = os.path.join(self.app_dir, ".kinocloud")
        os.makedirs(self.cloud_dir, exist_ok=True)
        self.plugins_dir = os.path.join(self.app_dir, "plugins")
        os.makedirs(self.plugins_dir, exist_ok=True)
        self.plugins = load_all_plugins(self.plugins_dir)
        self.custom_shortcuts: Dict[str, str] = {lbl: sc for _, _, lbl, sc in TOOL_DEFS if sc}
        self._tool_buttons: Dict[str, QToolButton] = {}
        self._clipboard_objs: List[VectorObject] = []

        self._build_menus()
        self._build_ui()
        self._build_statusbar()

        # Open command-line files or the flagship KinoSuite showcase document
        opened = False
        if initial_files:
            for fp in initial_files:
                if os.path.isfile(fp):
                    self.open_path(fp)
                    opened = True
        if not opened:
            self.add_document_tab(create_showcase_document())

    # ------------------------------------------------------------------
    # UI Layout Assembly
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 1. Top Control Bar (Illustrator Control Strip + KinoSuite Identity)
        outer.addWidget(self._build_control_bar())

        # 2. Main Studio Area: Left Tools Dock | Center Document Tabs | Right Studio Panels
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_tools_dock())

        self.splitter = QSplitter(Qt.Horizontal)
        self.doc_tabs = QTabWidget()
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.tabCloseRequested.connect(self._close_tab)
        self.doc_tabs.currentChanged.connect(self._on_tab_changed)
        self.splitter.addWidget(self.doc_tabs)

        self.panels = StudioPanels(self.current_canvas, self)
        self.panels.setMinimumWidth(295)
        self.panels.setMaximumWidth(420)
        self.panels.command_requested.connect(self.dispatch_command)
        self.splitter.addWidget(self.panels)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([1120, 320])

        body.addWidget(self.splitter, 1)
        outer.addLayout(body, 1)

    def _build_control_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("ControlBar")
        bar.setFixedHeight(40)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(8)

        # KinoSuite Brand Pill
        logo = QLabel()
        logo.setPixmap(make_app_pixmap(24))
        badge = QLabel("KINODRAW  •  KinoSuite")
        badge.setObjectName("SuiteBadge")
        lay.addWidget(logo)
        lay.addWidget(badge)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.VLine); sep1.setStyleSheet("color: #2E3545;")
        lay.addWidget(sep1)

        # Quick Fill / Stroke / Weight / Width Profile
        self.btn_top_fill = QPushButton("Fill")
        self.btn_top_fill.setFixedHeight(26)
        self.btn_top_fill.clicked.connect(lambda: self._pick_active_color(True))
        self.btn_top_stroke = QPushButton("Stroke")
        self.btn_top_stroke.setFixedHeight(26)
        self.btn_top_stroke.clicked.connect(lambda: self._pick_active_color(False))
        lay.addWidget(self.btn_top_fill)
        lay.addWidget(self.btn_top_stroke)

        lay.addWidget(QLabel("Stroke:"))
        self.sp_top_sw = QDoubleSpinBox()
        self.sp_top_sw.setRange(0.0, 200.0)
        self.sp_top_sw.setValue(2.0)
        self.sp_top_sw.setFixedWidth(64)
        self.sp_top_sw.valueChanged.connect(self._on_top_sw_changed)
        lay.addWidget(self.sp_top_sw)

        self.cb_top_profile = QComboBox()
        self.cb_top_profile.addItems(list(WIDTH_PROFILES.keys()))
        self.cb_top_profile.setFixedWidth(155)
        self.cb_top_profile.currentTextChanged.connect(self._on_top_profile_changed)
        lay.addWidget(self.cb_top_profile)

        # Perspective Grid quick selector
        self.cb_persp = QComboBox()
        self.cb_persp.addItems(["Perspective: Off", "1-Point Grid", "2-Point Grid", "3-Point Grid"])
        self.cb_persp.setFixedWidth(118)
        self.cb_persp.currentIndexChanged.connect(self._on_persp_changed)
        lay.addWidget(self.cb_persp)

        # Quick View buttons
        self.btn_outline = QPushButton("Outline")
        self.btn_outline.setCheckable(True)
        self.btn_outline.toggled.connect(self._toggle_outline_view)
        self.btn_pixel = QPushButton("Pixel")
        self.btn_pixel.setCheckable(True)
        self.btn_pixel.toggled.connect(self._toggle_pixel_preview)
        self.btn_gen = QPushButton("✦ Generate Vector")
        self.btn_gen.setObjectName("PrimaryButton")
        self.btn_gen.clicked.connect(lambda: self.dispatch_command("ai_generate"))
        lay.addWidget(self.btn_outline)
        lay.addWidget(self.btn_pixel)
        lay.addWidget(self.btn_gen)

        lay.addStretch()

        # Workspace Switcher
        lay.addWidget(QLabel("Workspace:"))
        self.cb_workspace = QComboBox()
        self.cb_workspace.addItems([
            "Essentials", "Typography", "Painting & Brushes",
            "Print & Proofing", "Web & UI Assets", "Automation & Cloud",
        ])
        self.cb_workspace.setFixedWidth(145)
        self.cb_workspace.currentTextChanged.connect(self._apply_workspace)
        lay.addWidget(self.cb_workspace)
        return bar

    def _build_tools_dock(self) -> QWidget:
        dock = QWidget()
        dock.setObjectName("ToolsDock")
        dock.setFixedWidth(74)
        lay = QVBoxLayout(dock)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(4)

        grid = QGridLayout()
        grid.setSpacing(2)
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        for idx, (tid, icon_name, label, sc) in enumerate(TOOL_DEFS):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setFixedSize(31, 25)
            btn.setIcon(get_tool_icon(icon_name, active=False, size=20))
            btn.setIconSize(QSize(18, 18))
            tip = f"{label} ({sc})" if sc else label
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, t=tid: self.select_tool(t))
            self._tool_group.addButton(btn)
            self._tool_buttons[tid] = btn
            grid.addWidget(btn, idx // 2, idx % 2)
        self._tool_buttons["select"].setChecked(True)
        lay.addLayout(grid)
        lay.addStretch()

        self.swatch_box = FillStrokeSwatchWidget()
        self.swatch_box.fill_clicked.connect(lambda: self._pick_active_color(True))
        self.swatch_box.stroke_clicked.connect(lambda: self._pick_active_color(False))
        self.swatch_box.swap_clicked.connect(lambda: self.dispatch_command("swap_colors"))
        self.swatch_box.default_clicked.connect(lambda: self.dispatch_command("default_colors"))
        lay.addWidget(self.swatch_box, alignment=Qt.AlignHCenter)
        return dock

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # File
        m_file = mb.addMenu("&File")
        self._add_act(m_file, "New Document...", "Ctrl+N", lambda: self.dispatch_command("new_doc"))
        self._add_act(m_file, "New Showcase Template", "", lambda: self.add_document_tab(create_showcase_document()))
        self._add_act(m_file, "Open (.kdrw / .svg)...", "Ctrl+O", lambda: self.dispatch_command("open_doc"))
        self._add_act(m_file, "Open Cloud Document...", "", lambda: self.dispatch_command("cloud_open"))
        m_file.addSeparator()
        self._add_act(m_file, "Save", "Ctrl+S", lambda: self.dispatch_command("save_doc"))
        self._add_act(m_file, "Save As...", "Ctrl+Shift+S", lambda: self.dispatch_command("save_as"))
        self._add_act(m_file, "Save to KinoSuite Cloud", "", lambda: self.dispatch_command("cloud_save"))
        m_file.addSeparator()
        self._add_act(m_file, "Place Linked / Embedded File (PNG/JPG/SVG/PSD/PDF)...", "Ctrl+Shift+P", lambda: self.dispatch_command("place_file"))
        m_file.addSeparator()
        self._add_act(m_file, "Export SVG...", "", lambda: self.dispatch_command("export_svg"))
        self._add_act(m_file, "Export for Screens (PNG / JPG / WebP / SVG)...", "Ctrl+Alt+E", lambda: self.dispatch_command("export_screens"))
        self._add_act(m_file, "Export Print-Ready PDF (CMYK & Marks)...", "", lambda: self.dispatch_command("export_pdf"))
        m_file.addSeparator()
        self._add_act(m_file, "Exit", "Alt+F4", self.close)

        # Edit
        m_edit = mb.addMenu("&Edit")
        self._add_act(m_edit, "Undo", "Ctrl+Z", lambda: self.dispatch_command("undo"))
        self._add_act(m_edit, "Redo", "Ctrl+Shift+Z", lambda: self.dispatch_command("redo"))
        m_edit.addSeparator()
        self._add_act(m_edit, "Copy", "Ctrl+C", lambda: self.dispatch_command("copy"))
        self._add_act(m_edit, "Paste", "Ctrl+V", lambda: self.dispatch_command("paste"))
        self._add_act(m_edit, "Duplicate", "Ctrl+D", lambda: self.dispatch_command("duplicate"))
        self._add_act(m_edit, "Delete", "Del", lambda: self.dispatch_command("delete"))
        m_edit.addSeparator()
        self._add_act(m_edit, "Recolor Artwork / Generative Recolor...", "", lambda: self.dispatch_command("recolor"))
        self._add_act(m_edit, "Keyboard Shortcuts...", "Ctrl+Alt+Shift+K", lambda: self.dispatch_command("shortcuts"))

        # Object
        m_obj = mb.addMenu("&Object")
        self._add_act(m_obj, "Group", "Ctrl+G", lambda: self.dispatch_command("group"))
        self._add_act(m_obj, "Ungroup", "Ctrl+Shift+G", lambda: self.dispatch_command("ungroup"))
        m_obj.addSeparator()
        self._add_act(m_obj, "Make Clipping Mask", "Ctrl+7", lambda: self.dispatch_command("clip_mask"))
        self._add_act(m_obj, "Make Opacity Mask", "", lambda: self.dispatch_command("opacity_mask"))
        m_obj.addSeparator()
        m_path = m_obj.addMenu("Path")
        self._add_act(m_path, "Convert Shape to Editable Path", "", lambda: self.dispatch_command("convert_to_path"))
        self._add_act(m_path, "Join Paths", "Ctrl+J", lambda: self.dispatch_command("join_paths"))
        self._add_act(m_path, "Offset Path...", "", lambda: self.dispatch_command("offset_path"))
        self._add_act(m_path, "Simplify Path...", "", lambda: self.dispatch_command("simplify_path"))
        self._add_act(m_path, "Outline Stroke (Expand Width)", "", lambda: self.dispatch_command("outline_stroke"))
        m_rep = m_obj.addMenu("Repeat")
        self._add_act(m_rep, "Radial Repeat", "", lambda: self.dispatch_command("repeat_radial"))
        self._add_act(m_rep, "Grid Repeat", "", lambda: self.dispatch_command("repeat_grid"))
        self._add_act(m_rep, "Mirror Repeat", "", lambda: self.dispatch_command("repeat_mirror"))
        self._add_act(m_obj, "Blend Selected Objects", "Ctrl+Alt+B", lambda: self.dispatch_command("make_blend"))
        self._add_act(m_obj, "Envelope Distort (Warp)...", "", lambda: self.dispatch_command("effect_warp"))
        m_obj.addSeparator()
        self._add_act(m_obj, "Image Trace...", "", lambda: self.dispatch_command("image_trace"))
        self._add_act(m_obj, "Crop Placed Image...", "", lambda: self.dispatch_command("crop_image"))
        self._add_act(m_obj, "Create Product Mockup...", "", lambda: self.dispatch_command("create_mockup"))
        self._add_act(m_obj, "Start / Stop Global Edit", "", lambda: self.dispatch_command("toggle_global_edit"))

        # Type
        m_type = mb.addMenu("&Type")
        self._add_act(m_type, "Edit Text...", "", lambda: self.dispatch_command("edit_text"))
        self._add_act(m_type, "Create Outlines", "Ctrl+Shift+O", lambda: self.dispatch_command("create_outlines"))
        self._add_act(m_type, "Thread Two Area Text Frames", "", lambda: self.dispatch_command("thread_text"))
        self._add_act(m_type, "Touch Type Tool", "Shift+T", lambda: self.select_tool("touch_type"))

        # Select
        m_sel = mb.addMenu("&Select")
        self._add_act(m_sel, "Select All", "Ctrl+A", lambda: self.dispatch_command("select_all"))
        self._add_act(m_sel, "Deselect", "Ctrl+Shift+A", lambda: self.dispatch_command("deselect"))
        self._add_act(m_sel, "Select Same Fill Color", "", lambda: self.dispatch_command("select_same_fill"))

        # Effect
        m_fx = mb.addMenu("E&ffect")
        self._add_act(m_fx, "3D and Materials (Extrude & Bevel)...", "", lambda: self.dispatch_command("effect_3d"))
        self._add_act(m_fx, "Warp / Envelope...", "", lambda: self.dispatch_command("effect_warp"))
        self._add_act(m_fx, "Stylize > Drop Shadow", "", lambda: self.dispatch_command("fx_drop_shadow"))
        self._add_act(m_fx, "Stylize > Outer Glow", "", lambda: self.dispatch_command("fx_outer_glow"))
        self._add_act(m_fx, "Distort > Roughen", "", lambda: self.dispatch_command("fx_roughen"))
        self._add_act(m_fx, "Blur > Gaussian Blur", "", lambda: self.dispatch_command("fx_blur"))

        # View
        m_view = mb.addMenu("&View")
        self._add_act(m_view, "Fit Artboard in Window", "Ctrl+0", lambda: self.current_canvas().fit_artboard())
        self._add_act(m_view, "Zoom In", "Ctrl+=", lambda: self.current_canvas().set_zoom(self.current_canvas().zoom * 1.25))
        self._add_act(m_view, "Zoom Out", "Ctrl+-", lambda: self.current_canvas().set_zoom(self.current_canvas().zoom * 0.8))
        m_view.addSeparator()
        self._add_act(m_view, "Outline View", "Ctrl+Y", lambda: self.btn_outline.toggle())
        self._add_act(m_view, "Pixel Preview", "Ctrl+Alt+Y", lambda: self.btn_pixel.toggle())
        self._add_act(m_view, "Toggle Rulers", "Ctrl+R", lambda: self.dispatch_command("toggle_rulers"))
        self._add_act(m_view, "Toggle Guides", "Ctrl+;", lambda: self.dispatch_command("toggle_guides"))
        self._add_act(m_view, "Toggle Grid", "Ctrl+'", lambda: self.dispatch_command("toggle_grid"))
        self._add_act(m_view, "Snap to Pixel Grid", "", lambda: self.dispatch_command("toggle_snap_pixel"))

        # Window & Plugins
        m_win = mb.addMenu("&Window")
        self._add_act(m_win, "✦ Text to Vector Graphic / Pattern...", "", lambda: self.dispatch_command("ai_generate"))
        for idx, name in enumerate(["Properties", "Layers", "Appearance", "Color", "Stroke", "Type", "Assets", "Proof/CSS", "Workflow"]):
            self._add_act(m_win, name, "", lambda i=idx: self.panels.tabs.setCurrentIndex(i))

        m_pl = mb.addMenu("&Plugins")
        self._add_act(m_pl, "Plugins & Extensions Manager...", "", lambda: self.dispatch_command("plugins"))
        m_pl.addSeparator()
        for pl in self.plugins:
            self._add_act(m_pl, f"Run: {pl.name}", "", lambda p_obj=pl: self._run_plugin(p_obj))

        # Help
        m_help = mb.addMenu("&Help")
        self._add_act(m_help, "About KinoDraw (KinoSuite)", "", self._show_about)

    def _add_act(self, menu: QMenu, text: str, shortcut: str, fn) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(fn)
        menu.addAction(a)
        return a

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.cb_zoom = QComboBox()
        self.cb_zoom.addItems(["25%", "50%", "75%", "100%", "150%", "200%", "400%", "Fit"])
        self.cb_zoom.setCurrentText("75%")
        self.cb_zoom.currentTextChanged.connect(self._on_zoom_combo)
        sb.addPermanentWidget(QLabel("Zoom:"))
        sb.addPermanentWidget(self.cb_zoom)

        self.lbl_tool = QLabel("Tool: Selection")
        self.lbl_coords = QLabel("X: 0.0  Y: 0.0")
        self.lbl_mode = QLabel("RGB  |  KinoSuite")
        sb.addWidget(self.lbl_tool)
        sb.addPermanentWidget(self.lbl_coords)
        sb.addPermanentWidget(self.lbl_mode)

    # ------------------------------------------------------------------
    # Multi-Document Tab Management
    # ------------------------------------------------------------------

    def add_document_tab(self, doc: Document) -> VectorCanvas:
        canvas = VectorCanvas(doc, self)
        canvas.selection_changed.connect(self._on_canvas_selection)
        canvas.document_modified.connect(self._on_canvas_modified)
        canvas.cursor_moved.connect(lambda x, y: self.lbl_coords.setText(f"X: {x:.1f}  Y: {y:.1f}"))
        canvas.zoom_changed.connect(lambda z: self.cb_zoom.setCurrentText(f"{int(round(z * 100))}%") if f"{int(round(z * 100))}%" in ["25%","50%","75%","100%","150%","200%","400%"] else None)
        canvas.context_action.connect(self.dispatch_command)
        idx = self.doc_tabs.addTab(canvas, doc.name)
        self.doc_tabs.setCurrentIndex(idx)
        canvas.fit_artboard()
        self.panels.refresh_all()
        self._sync_top_controls()
        return canvas

    def current_canvas(self) -> VectorCanvas:
        w = self.doc_tabs.currentWidget()
        if isinstance(w, VectorCanvas):
            return w
        return self.add_document_tab(create_blank_document())

    def _close_tab(self, idx: int) -> None:
        if self.doc_tabs.count() <= 1:
            return
        self.doc_tabs.removeTab(idx)

    def _on_tab_changed(self, idx: int) -> None:
        if idx >= 0:
            self.panels.refresh_all()
            self._sync_top_controls()

    def _on_canvas_selection(self) -> None:
        self.panels.refresh_all()
        self._sync_top_controls()

    def _on_canvas_modified(self, label: str) -> None:
        self.panels.refresh_all()
        self._sync_top_controls()
        c = self.current_canvas()
        idx = self.doc_tabs.currentIndex()
        if idx >= 0:
            star = " *" if c.doc.dirty else ""
            self.doc_tabs.setTabText(idx, f"{c.doc.name}{star}")

    def _sync_top_controls(self) -> None:
        c = self.current_canvas()
        self.swatch_box.fill_color = QColor(c.active_fill_color.to_hex())
        self.swatch_box.stroke_color = QColor(c.active_stroke_color.to_hex())
        self.swatch_box.fill_enabled = c.active_fill_enabled
        self.swatch_box.stroke_enabled = c.active_stroke_enabled
        self.swatch_box.update()

        self.btn_top_fill.setStyleSheet(f"border-left: 10px solid {c.active_fill_color.to_hex()}; padding: 3px 8px;")
        self.btn_top_stroke.setStyleSheet(f"border-left: 10px solid {c.active_stroke_color.to_hex()}; padding: 3px 8px;")
        ge = "  |  GLOBAL EDIT" if c.global_edit_mode else ""
        self.lbl_mode.setText(f"{c.doc.color_mode}  |  Bleed {c.doc.bleed:.0f}px{ge}")

    # ------------------------------------------------------------------
    # Tool Switching & Top Bar Handlers
    # ------------------------------------------------------------------

    def select_tool(self, tid: str) -> None:
        c = self.current_canvas()
        c.set_tool(tid)
        for k, btn in self._tool_buttons.items():
            icon_name = next((ic for t, ic, _, _ in TOOL_DEFS if t == k), "select")
            btn.setIcon(get_tool_icon(icon_name, active=(k == tid), size=20))
            if k == tid:
                btn.setChecked(True)
        lbl = next((l for t, _, l, _ in TOOL_DEFS if t == tid), tid)
        self.lbl_tool.setText(f"Tool: {lbl}")

    def keyPressEvent(self, event) -> None:
        # Single-letter Illustrator tool shortcuts when no text box has focus
        fw = QApplication.focusWidget()
        if not isinstance(fw, (QDoubleSpinBox, QComboBox)) and not hasattr(fw, "text"):
            k = event.key()
            mods = event.modifiers()
            if mods == Qt.NoModifier:
                quick = {
                    Qt.Key_V: "select", Qt.Key_A: "direct_select", Qt.Key_P: "pen",
                    Qt.Key_N: "pencil", Qt.Key_M: "rect", Qt.Key_L: "ellipse",
                    Qt.Key_Backslash: "line", Qt.Key_T: "type", Qt.Key_K: "live_paint",
                    Qt.Key_C: "scissors", Qt.Key_R: "rotate", Qt.Key_S: "scale",
                    Qt.Key_W: "blend", Qt.Key_G: "gradient", Qt.Key_I: "eyedropper",
                    Qt.Key_J: "graph", Qt.Key_H: "hand", Qt.Key_Z: "zoom",
                }
                if k in quick:
                    self.select_tool(quick[k])
                    return
                if k == Qt.Key_D:
                    self.dispatch_command("default_colors")
                    return
            elif mods == Qt.ShiftModifier:
                squick = {
                    Qt.Key_B: "blob_brush", Qt.Key_N: "shaper", Qt.Key_M: "shape_builder",
                    Qt.Key_W: "width", Qt.Key_T: "touch_type", Qt.Key_P: "perspective",
                    Qt.Key_O: "artboard", Qt.Key_S: "symbol_sprayer", Qt.Key_AsciiTilde: "curvature",
                }
                if k in squick:
                    self.select_tool(squick[k])
                    return
                if k == Qt.Key_X:
                    self.dispatch_command("swap_colors")
                    return
        super().keyPressEvent(event)

    def _pick_active_color(self, is_fill: bool) -> None:
        c = self.current_canvas()
        start = c.active_fill_color if is_fill else c.active_stroke_color
        qc = QColorDialog.getColor(QColor(start.to_hex()), self, "Pick Fill Color" if is_fill else "Pick Stroke Color")
        if not qc.isValid():
            return
        col = Color(qc.red(), qc.green(), qc.blue(), 255)
        if is_fill:
            c.active_fill_color = col
            c.active_fill_enabled = True
        else:
            c.active_stroke_color = col
            c.active_stroke_enabled = True
        for o in c.selected_objects() + c.global_edit_matches():
            if is_fill:
                o.appearance.primary_fill.fill_type = "solid"
                o.appearance.primary_fill.color = copy.deepcopy(col)
            else:
                o.appearance.primary_stroke.stroke_type = "solid"
                o.appearance.primary_stroke.color = copy.deepcopy(col)
        c.push_undo("Color Change")

    def _on_top_sw_changed(self, v: float) -> None:
        c = self.current_canvas()
        c.active_stroke_width = v
        for o in c.selected_objects():
            o.appearance.primary_stroke.width = v
            if v > 0 and o.appearance.primary_stroke.stroke_type == "none":
                o.appearance.primary_stroke.stroke_type = "solid"
        c.update()

    def _on_top_profile_changed(self, name: str) -> None:
        c = self.current_canvas()
        for o in c.selected_objects():
            st = o.appearance.primary_stroke
            st.width_profile_name = name
            st.width_stations = []
            if name != "Uniform" and st.width < 4.0:
                st.width = 10.0
                st.stroke_type = "solid"
        c.push_undo("Width Profile")

    def _on_persp_changed(self, idx: int) -> None:
        c = self.current_canvas()
        if idx == 0:
            c.doc.perspective.visible = False
        else:
            c.doc.perspective.visible = True
            c.doc.perspective.points = idx
        c.update()

    def _toggle_outline_view(self, checked: bool) -> None:
        self.current_canvas().view_opts.outline_mode = checked
        self.current_canvas().update()

    def _toggle_pixel_preview(self, checked: bool) -> None:
        self.current_canvas().view_opts.pixel_preview = checked
        self.current_canvas().update()

    def _on_zoom_combo(self, txt: str) -> None:
        c = self.current_canvas()
        if txt == "Fit":
            c.fit_artboard()
        elif txt.endswith("%"):
            try:
                c.set_zoom(float(txt[:-1]) / 100.0)
            except ValueError:
                pass

    def _apply_workspace(self, name: str) -> None:
        tab_map = {
            "Essentials": 0, "Typography": 5, "Painting & Brushes": 4,
            "Print & Proofing": 7, "Web & UI Assets": 7, "Automation & Cloud": 8,
        }
        self.panels.tabs.setCurrentIndex(tab_map.get(name, 0))

    # ------------------------------------------------------------------
    # Unified Command Dispatcher (Menus, Contextual Bar, Panels, Actions)
    # ------------------------------------------------------------------

    def dispatch_command(self, cmd: str) -> None:
        self.panels.record_command_if_active(cmd)
        c = self.current_canvas()
        doc = c.doc
        sel = c.selected_objects()

        if cmd == "new_doc":
            dlg = NewDocumentDialog(self)
            if dlg.exec():
                d = create_blank_document(
                    name=dlg.ed_name.text().strip() or "Untitled",
                    width=dlg.sp_w.value(), height=dlg.sp_h.value(),
                    color_mode=dlg.cb_mode.currentText(),
                    artboards=dlg.sp_abs.value(), bleed=dlg.sp_bleed.value(),
                )
                self.add_document_tab(d)

        elif cmd == "open_doc":
            path, _ = QFileDialog.getOpenFileName(self, "Open Document", "", "KinoDraw & SVG (*.kdrw *.svg *.json)")
            if path:
                self.open_path(path)

        elif cmd == "save_doc":
            if doc.file_path:
                doc.save_to_file(doc.file_path)
                self._on_canvas_modified("Saved")
            else:
                self.dispatch_command("save_as")

        elif cmd == "save_as":
            path, _ = QFileDialog.getSaveFileName(self, "Save KinoDraw Document", f"{doc.name}.kdrw", "KinoDraw Project (*.kdrw)")
            if path:
                doc.name = os.path.basename(path)
                doc.save_to_file(path)
                self._on_canvas_modified("Saved")

        elif cmd == "cloud_save":
            doc.is_cloud_doc = True
            cname = doc.name if doc.name.endswith(".kdrw") else f"{doc.name}.kdrw"
            cpath = os.path.join(self.cloud_dir, cname)
            doc.save_version("Cloud Sync")
            doc.save_to_file(cpath)
            QMessageBox.information(self, "KinoSuite Cloud", f"Synced cloud document:\n{cpath}")
            self._on_canvas_modified("Cloud Saved")

        elif cmd == "cloud_open":
            files = [f for f in os.listdir(self.cloud_dir) if f.endswith(".kdrw")]
            if not files:
                QMessageBox.information(self, "KinoSuite Cloud", "No cloud documents saved yet.")
                return
            choice, ok = QInputDialog.getItem(self, "Open Cloud Document", "Select cloud document:", files, 0, False)
            if ok and choice:
                self.open_path(os.path.join(self.cloud_dir, choice))

        elif cmd == "place_file":
            path, _ = QFileDialog.getOpenFileName(
                self, "Place File", "",
                "Supported Assets (*.png *.jpg *.jpeg *.webp *.bmp *.svg *.psd *.pdf)"
            )
            if not path:
                return
            if path.lower().endswith(".svg"):
                objs = import_svg_objects(path)
                for o in objs:
                    doc.add_object(o)
                c.selected_ids = [o.id for o in objs]
                c.selection_changed.emit()
                c.push_undo("Place SVG")
            else:
                ab = doc.active_artboard()
                img_obj = create_placed_image_object(path, ab.x + 60, ab.y + 60, embed=False)
                doc.add_object(img_obj)
                c.selected_ids = [img_obj.id]
                c.selection_changed.emit()
                c.push_undo("Place Linked File")

        elif cmd == "export_svg":
            path, _ = QFileDialog.getSaveFileName(self, "Export SVG", f"{os.path.splitext(doc.name)[0]}.svg", "SVG (*.svg)")
            if path:
                export_svg(doc, path)
                QMessageBox.information(self, "Export SVG", f"Exported crisp vector SVG:\n{path}")

        elif cmd == "export_screens":
            dlg = ExportScreensDialog(doc, self)
            if dlg.exec():
                folder = QFileDialog.getExistingDirectory(self, "Choose Export Folder")
                if folder:
                    cnt = 0
                    for idx, ab in enumerate(doc.artboards):
                        stem = f"{os.path.splitext(doc.name)[0]}_{idx + 1}_{ab.name.replace(' ', '_')}"
                        for fmt in dlg.selected_formats():
                            if fmt == "SVG":
                                export_svg(doc, os.path.join(folder, f"{stem}.svg"), artboard=ab)
                                cnt += 1
                            else:
                                for sc in dlg.selected_scales():
                                    sfx = "" if abs(sc - 1.0) < 0.01 else f"@{sc:g}x"
                                    export_raster(doc, os.path.join(folder, f"{stem}{sfx}.{fmt.lower()}"),
                                                  fmt=fmt, scale=sc, artboard=ab, transparent_bg=dlg.chk_trans.isChecked())
                                    cnt += 1
                    QMessageBox.information(self, "Export for Screens", f"Exported {cnt} screen files to:\n{folder}")

        elif cmd == "export_pdf":
            dlg = PrintPdfDialog(doc, self)
            if dlg.exec():
                path, _ = QFileDialog.getSaveFileName(self, "Export Print-Ready PDF", f"{os.path.splitext(doc.name)[0]}_print.pdf", "PDF (*.pdf)")
                if path:
                    export_print_pdf(
                        doc, path, cmyk=dlg.chk_cmyk.isChecked(),
                        bleed_pt=dlg.sp_bleed.value(), crop_marks=dlg.chk_crop.isChecked(),
                        reg_marks=dlg.chk_reg.isChecked(), color_bars=dlg.chk_bars.isChecked(),
                    )
                    QMessageBox.information(self, "Print PDF Export", f"Exported print-ready PDF:\n{path}")

        elif cmd == "undo":
            c.undo()
        elif cmd == "redo":
            c.redo()

        elif cmd == "copy":
            self._clipboard_objs = [o.clone() for o in sel]
        elif cmd == "paste":
            if self._clipboard_objs:
                new_ids = []
                for o in self._clipboard_objs:
                    cl = o.clone()
                    translate_object(cl, 24, 24)
                    doc.add_object(cl)
                    new_ids.append(cl.id)
                c.selected_ids = new_ids
                c.selection_changed.emit()
                c.push_undo("Paste")
        elif cmd == "duplicate":
            if sel:
                new_ids = []
                for o in sel:
                    cl = o.clone()
                    translate_object(cl, 24, 24)
                    doc.add_object(cl)
                    new_ids.append(cl.id)
                c.selected_ids = new_ids
                c.selection_changed.emit()
                c.push_undo("Duplicate")
        elif cmd == "delete":
            for oid in list(c.selected_ids):
                doc.remove_object(oid)
            c.selected_ids = []
            c.selection_changed.emit()
            c.push_undo("Delete")

        elif cmd == "select_all":
            c.selected_ids = [o.id for o in doc.iter_all_objects() if not o.locked]
            c.selection_changed.emit()
            c.update_contextual_bar()
            c.update()
        elif cmd == "deselect":
            c.selected_ids = []
            c.selection_changed.emit()
            c.update_contextual_bar()
            c.update()
        elif cmd == "select_same_fill" and sel:
            hx = sel[0].appearance.primary_fill.color.to_hex()
            c.selected_ids = [o.id for o in doc.iter_all_objects() if o.appearance.primary_fill.fill_type == "solid" and o.appearance.primary_fill.color.to_hex() == hx]
            c.selection_changed.emit()
            c.update()

        elif cmd == "swap_colors":
            c.active_fill_color, c.active_stroke_color = c.active_stroke_color, c.active_fill_color
            c.active_fill_enabled, c.active_stroke_enabled = c.active_stroke_enabled, c.active_fill_enabled
            for o in sel:
                fc, ft = copy.deepcopy(o.appearance.primary_fill.color), o.appearance.primary_fill.fill_type
                sc, st = copy.deepcopy(o.appearance.primary_stroke.color), o.appearance.primary_stroke.stroke_type
                o.appearance.primary_fill.color = sc
                o.appearance.primary_fill.fill_type = "solid" if st != "none" else "none"
                o.appearance.primary_stroke.color = fc
                o.appearance.primary_stroke.stroke_type = "solid" if ft != "none" else "none"
            c.push_undo("Swap Fill/Stroke")

        elif cmd == "default_colors":
            c.active_fill_color = Color.from_hex("#FFFFFF")
            c.active_stroke_color = Color.from_hex("#000000")
            c.active_fill_enabled = True
            c.active_stroke_enabled = True
            c.active_stroke_width = 1.5
            self._sync_top_controls()

        elif cmd == "group" and len(sel) >= 2:
            for o in sel:
                doc.remove_object(o.id)
            grp = VectorObject(name="Group", kind="group", children=sel)
            doc.add_object(grp)
            c.selected_ids = [grp.id]
            c.selection_changed.emit()
            c.push_undo("Group")

        elif cmd == "ungroup" and sel:
            new_ids = []
            for o in sel:
                if o.kind == "group":
                    doc.remove_object(o.id)
                    for ch in o.children:
                        doc.add_object(ch)
                        new_ids.append(ch.id)
            if new_ids:
                c.selected_ids = new_ids
                c.selection_changed.emit()
                c.push_undo("Ungroup")

        elif cmd in ("clip_mask", "opacity_mask") and len(sel) >= 2:
            for o in sel:
                doc.remove_object(o.id)
            grp = VectorObject(
                name="Clipping Group" if cmd == "clip_mask" else "Opacity Mask Group",
                kind="group", children=sel,
                is_clipping_group=(cmd == "clip_mask"),
                opacity_mask_enabled=(cmd == "opacity_mask"),
            )
            doc.add_object(grp)
            c.selected_ids = [grp.id]
            c.selection_changed.emit()
            c.push_undo("Make Mask")

        elif cmd.startswith("pf_") and len(sel) >= 2:
            op_map = {
                "pf_unite": "unite", "pf_minus": "minus_front", "pf_minus_back": "minus_back",
                "pf_intersect": "intersect", "pf_exclude": "exclude", "pf_divide": "divide",
                "pf_trim": "trim", "pf_crop": "crop", "pf_outline": "outline",
            }
            res = pathfinder_op(sel, op_map[cmd], doc)
            if res:
                for o in sel:
                    doc.remove_object(o.id)
                for r in res:
                    doc.add_object(r)
                c.selected_ids = [r.id for r in res]
                c.selection_changed.emit()
                c.push_undo(f"Pathfinder {op_map[cmd]}")

        elif cmd == "convert_to_path" and sel:
            new_ids = []
            for o in sel:
                po = convert_object_to_path(o, doc)
                doc.remove_object(o.id)
                doc.add_object(po)
                new_ids.append(po.id)
            c.selected_ids = new_ids
            c.selection_changed.emit()
            c.push_undo("Convert to Path")

        elif cmd == "create_outlines" and sel:
            new_ids = []
            for o in sel:
                if o.kind == "text":
                    po = convert_object_to_path(o, doc)
                    po.name = f"{o.name} (Outlines)"
                    doc.remove_object(o.id)
                    doc.add_object(po)
                    new_ids.append(po.id)
            if new_ids:
                c.selected_ids = new_ids
                c.selection_changed.emit()
                c.push_undo("Create Text Outlines")

        elif cmd == "join_paths" and sel:
            if len(sel) >= 2:
                combined_sps = []
                for o in sel:
                    po = o if o.kind == "path" else convert_object_to_path(o, doc)
                    combined_sps.extend(po.subpaths)
                    doc.remove_object(o.id)
                if len(combined_sps) >= 2:
                    merged_anchors = []
                    for sp in combined_sps:
                        merged_anchors.extend(sp.anchors)
                    from .models import SubPath
                    jobj = VectorObject(name="Joined Path", kind="path", subpaths=[SubPath(merged_anchors, closed=False)],
                                        appearance=copy.deepcopy(sel[0].appearance))
                    doc.add_object(jobj)
                    c.selected_ids = [jobj.id]
                    c.selection_changed.emit()
                    c.push_undo("Join Paths")

        elif cmd == "offset_path" and sel:
            dist, ok = QInputDialog.getDouble(self, "Offset Path", "Offset distance (px, negative = inset):", 12.0, -300.0, 300.0, 1)
            if ok:
                new_ids = []
                for o in sel:
                    qp = offset_qpath(object_to_qpath(o, doc), dist)
                    sps = qpath_to_subpaths(qp)
                    if sps:
                        br = qp.boundingRect()
                        no = VectorObject(name=f"{o.name} Offset", kind="path", subpaths=sps,
                                          x=br.x(), y=br.y(), width=br.width(), height=br.height(),
                                          appearance=copy.deepcopy(o.appearance))
                        doc.add_object(no)
                        new_ids.append(no.id)
                c.selected_ids = new_ids
                c.selection_changed.emit()
                c.push_undo("Offset Path")

        elif cmd == "simplify_path" and sel:
            tol, ok = QInputDialog.getDouble(self, "Simplify Path", "Simplification tolerance (px):", 4.0, 0.5, 40.0, 1)
            if ok:
                for o in sel:
                    if o.kind != "path":
                        po = convert_object_to_path(o, doc)
                        o.kind = "path"
                        o.subpaths = po.subpaths
                    o.subpaths = simplify_subpaths(o.subpaths, tolerance=tol, smooth=True)
                c.push_undo("Simplify Path")

        elif cmd == "outline_stroke" and sel:
            new_ids = []
            for o in sel:
                qp = outline_stroke_qpath(object_to_qpath(o, doc), o.appearance.primary_stroke)
                sps = qpath_to_subpaths(qp)
                if sps:
                    br = qp.boundingRect()
                    sc = copy.deepcopy(o.appearance.primary_stroke.color)
                    no = VectorObject(name=f"{o.name} Outlined Stroke", kind="path", subpaths=sps,
                                      x=br.x(), y=br.y(), width=br.width(), height=br.height(),
                                      appearance=Appearance(fills=[AppearanceFill(color=sc)], strokes=[AppearanceStroke(stroke_type="none")]))
                    doc.remove_object(o.id)
                    doc.add_object(no)
                    new_ids.append(no.id)
            c.selected_ids = new_ids
            c.selection_changed.emit()
            c.push_undo("Outline Stroke")

        elif cmd in ("repeat_radial", "repeat_grid", "repeat_mirror") and sel:
            src = sel[0]
            doc.remove_object(src.id)
            br = object_bounds(src, doc)
            mode = cmd.split("_")[1]
            rep = VectorObject(
                name=f"{mode.title()} Repeat", kind="repeat", repeat_mode=mode,
                x=br.center().x(), y=br.center().y(),
                repeat_count=8, repeat_radius=max(60.0, br.width()),
                repeat_rows=3, repeat_cols=4,
                repeat_spacing_x=br.width() + 24, repeat_spacing_y=br.height() + 24,
                children=[src],
            )
            doc.add_object(rep)
            c.selected_ids = [rep.id]
            c.selection_changed.emit()
            c.push_undo(f"{mode.title()} Repeat")

        elif cmd == "make_blend" and len(sel) >= 2:
            a, b = sel[0], sel[1]
            doc.remove_object(a.id)
            doc.remove_object(b.id)
            bl = VectorObject(name="Blend", kind="blend", blend_steps=6, children=[a, b])
            doc.add_object(bl)
            c.selected_ids = [bl.id]
            c.selection_changed.emit()
            c.push_undo("Make Blend")

        elif cmd == "recolor":
            targets = sel if sel else doc.iter_all_objects()
            dlg = RecolorArtworkDialog(targets, self)
            if dlg.exec():
                c.push_undo("Recolor Artwork")

        elif cmd == "image_trace" and sel and sel[0].kind == "image":
            dlg = ImageTraceDialog(sel[0], self)
            if dlg.exec() and dlg.result_group:
                doc.remove_object(sel[0].id)
                doc.add_object(dlg.result_group)
                c.selected_ids = [dlg.result_group.id]
                c.selection_changed.emit()
                c.push_undo("Image Trace")

        elif cmd == "crop_image" and sel and sel[0].kind == "image":
            pct, ok = QInputDialog.getDouble(self, "Crop Image", "Crop inset margin (% on each side):", 12.0, 0.0, 42.0, 1)
            if ok:
                m = pct / 100.0
                sel[0].crop_rect = [m, m, max(0.1, 1.0 - 2 * m), max(0.1, 1.0 - 2 * m)]
                c.push_undo("Crop Image")

        elif cmd == "embed_image" and sel and sel[0].kind == "image":
            o = sel[0]
            if o.image_path and os.path.exists(o.image_path):
                import base64
                with open(o.image_path, "rb") as f:
                    o.image_embedded_b64 = base64.b64encode(f.read()).decode("ascii")
                o.image_is_linked = False
                c.push_undo("Embed Image")

        elif cmd == "effect_3d" and sel:
            dlg = Effect3DDialog(self)
            if dlg.exec():
                for o in sel:
                    o.appearance.effects.append(LiveEffect(kind="extrude_3d", params=dlg.params()))
                c.push_undo("3D Extrude & Materials")

        elif cmd == "effect_warp" and sel:
            dlg = WarpEffectDialog(self)
            if dlg.exec():
                for o in sel:
                    o.appearance.effects.append(LiveEffect(kind="warp", params=dlg.params()))
                c.push_undo("Envelope Warp")

        elif cmd in ("fx_drop_shadow", "fx_outer_glow", "fx_roughen", "fx_blur") and sel:
            m = {
                "fx_drop_shadow": ("drop_shadow", {"dx": 6, "dy": 8, "blur": 12, "color": "#000000", "opacity": 0.4}),
                "fx_outer_glow": ("outer_glow", {"color": "#00C2FF", "blur": 14, "opacity": 0.8}),
                "fx_roughen": ("roughen", {"amount": 5.0, "detail": 26}),
                "fx_blur": ("gaussian_blur", {"blur": 8.0}),
            }
            kind, prm = m[cmd]
            for o in sel:
                o.appearance.effects.append(LiveEffect(kind=kind, params=dict(prm)))
            c.push_undo(f"Effect {kind}")

        elif cmd == "create_mockup":
            dlg = MockupDialog(self)
            if dlg.exec():
                ab = doc.active_artboard()
                art = sel[0].clone() if sel else VectorObject(
                    name="Mockup Art", kind="shape", shape_type="star", sides=8,
                    x=0, y=0, width=120, height=120,
                    appearance=Appearance(fills=[AppearanceFill(color=Color.from_hex("#FF9A00"))]),
                )
                mk = VectorObject(
                    name=f"{dlg.cb_preset.currentText().title()} Mockup",
                    kind="mockup", mockup_preset=dlg.cb_preset.currentText(),
                    mockup_color=dlg.color, mockup_art_scale=dlg.sp_scale.value(),
                    x=ab.x + ab.width * 0.5 - 190, y=ab.y + ab.height * 0.5 - 210,
                    width=380, height=420, children=[art],
                )
                doc.add_object(mk)
                c.selected_ids = [mk.id]
                c.selection_changed.emit()
                c.push_undo("Create Mockup")

        elif cmd == "ai_generate":
            dlg = GenerativeAIDialog(self)
            if dlg.exec():
                prompt = dlg.ed_prompt.text().strip() or "kinosuite emblem"
                if dlg.cb_mode.currentIndex() == 0:
                    ab = doc.active_artboard()
                    gen = generate_vector_from_prompt(prompt, x=ab.x + ab.width * 0.5 - 140, y=ab.y + ab.height * 0.5 - 140, size=280)
                    doc.add_object(gen)
                    c.selected_ids = [gen.id]
                    c.selection_changed.emit()
                    c.push_undo("Generate Vector Graphic")
                else:
                    pat = generate_pattern_from_prompt(prompt)
                    targets = sel
                    if not targets:
                        ab = doc.active_artboard()
                        r = VectorObject(name=pat.name, kind="shape", shape_type="rect",
                                         x=ab.x + 120, y=ab.y + 120, width=320, height=240, corner_radius=12)
                        doc.add_object(r)
                        targets = [r]
                        c.selected_ids = [r.id]
                    for o in targets:
                        o.appearance.primary_fill.fill_type = "pattern"
                        o.appearance.primary_fill.pattern = copy.deepcopy(pat)
                    c.selection_changed.emit()
                    c.push_undo("Generate Pattern Fill")

        elif cmd == "edit_text" and sel and sel[0].kind == "text":
            txt, ok = QInputDialog.getMultiLineText(self, "Edit Text", "Text content:", sel[0].text)
            if ok:
                sel[0].text = txt
                c.push_undo("Edit Text")

        elif cmd == "thread_text" and len(sel) >= 2:
            texts = [o for o in sel if o.kind == "text"]
            if len(texts) >= 2:
                texts[0].thread_next_id = texts[1].id
                c.push_undo("Thread Text Frames")

        elif cmd == "tool_touch_type":
            self.select_tool("touch_type")

        elif cmd == "edit_graph" and sel and sel[0].kind == "graph":
            dlg = GraphDataDialog(sel[0], self)
            if dlg.exec():
                c.push_undo("Edit Graph Data")

        elif cmd == "toggle_global_edit":
            c.global_edit_mode = not c.global_edit_mode
            self._sync_top_controls()
            c.update()

        elif cmd in ("flip_h", "flip_v") and sel:
            br = c.selection_bounds()
            if br:
                tr = QTransform()
                tr.translate(br.center().x(), br.center().y())
                tr.scale(-1.0 if cmd == "flip_h" else 1.0, -1.0 if cmd == "flip_v" else 1.0)
                tr.translate(-br.center().x(), -br.center().y())
                for o in sel:
                    transform_object_affine(o, tr, doc)
                c.push_undo("Reflect")

        elif cmd == "align_pixel" and sel:
            for o in sel:
                o.x, o.y = round(o.x), round(o.y)
                o.width, o.height = max(1.0, round(o.width)), max(1.0, round(o.height))
            c.push_undo("Align to Pixel Grid")

        elif cmd.startswith("align_") or cmd.startswith("dist_"):
            self._do_align_distribute(cmd)

        elif cmd == "toggle_rulers":
            c.show_rulers = not c.show_rulers
            c.update()
        elif cmd == "toggle_guides":
            doc.guides_visible = not doc.guides_visible
            c.update()
        elif cmd == "toggle_grid":
            doc.grid_visible = not doc.grid_visible
            c.update()
        elif cmd == "toggle_snap_pixel":
            doc.snap_to_pixel = not doc.snap_to_pixel

        elif cmd == "plugins":
            dlg = PluginsDialog(self.plugins, doc, self)
            if dlg.exec() and dlg.ran_message:
                c.push_undo("Plugin")
                QMessageBox.information(self, "KinoDraw Plugin", dlg.ran_message)

        elif cmd == "shortcuts":
            dlg = ShortcutsDialog(self.custom_shortcuts, self)
            if dlg.exec():
                self.custom_shortcuts = dlg.shortcuts

    def _do_align_distribute(self, cmd: str) -> None:
        c = self.current_canvas()
        sel = c.selected_objects()
        if not sel:
            return
        ab = c.doc.active_artboard()
        ref = c.selection_bounds() if len(sel) > 1 and cmd != "align_artboard_center" else None
        ref_x0 = ref.left() if ref else ab.x
        ref_x1 = ref.right() if ref else (ab.x + ab.width)
        ref_y0 = ref.top() if ref else ab.y
        ref_y1 = ref.bottom() if ref else (ab.y + ab.height)
        ref_cx = (ref_x0 + ref_x1) * 0.5
        ref_cy = (ref_y0 + ref_y1) * 0.5

        if cmd == "dist_h" and len(sel) >= 3:
            ordered = sorted(sel, key=lambda o: object_bounds(o, c.doc).center().x())
            first_cx = object_bounds(ordered[0], c.doc).center().x()
            last_cx = object_bounds(ordered[-1], c.doc).center().x()
            step = (last_cx - first_cx) / (len(ordered) - 1)
            for i, o in enumerate(ordered[1:-1], start=1):
                cur_cx = object_bounds(o, c.doc).center().x()
                translate_object(o, (first_cx + i * step) - cur_cx, 0)
        elif cmd == "dist_v" and len(sel) >= 3:
            ordered = sorted(sel, key=lambda o: object_bounds(o, c.doc).center().y())
            first_cy = object_bounds(ordered[0], c.doc).center().y()
            last_cy = object_bounds(ordered[-1], c.doc).center().y()
            step = (last_cy - first_cy) / (len(ordered) - 1)
            for i, o in enumerate(ordered[1:-1], start=1):
                cur_cy = object_bounds(o, c.doc).center().y()
                translate_object(o, 0, (first_cy + i * step) - cur_cy)
        else:
            for o in sel:
                b = object_bounds(o, c.doc)
                dx = dy = 0.0
                if cmd == "align_left": dx = ref_x0 - b.left()
                elif cmd == "align_right": dx = ref_x1 - b.right()
                elif cmd == "align_hcenter": dx = ref_cx - b.center().x()
                elif cmd == "align_top": dy = ref_y0 - b.top()
                elif cmd == "align_bottom": dy = ref_y1 - b.bottom()
                elif cmd == "align_vcenter": dy = ref_cy - b.center().y()
                elif cmd == "align_artboard_center":
                    dx = ref_cx - b.center().x()
                    dy = ref_cy - b.center().y()
                translate_object(o, dx, dy)
        c.push_undo("Align / Distribute")

    def open_path(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".svg":
                doc = create_blank_document(name=os.path.basename(path))
                for o in import_svg_objects(path):
                    doc.add_object(o)
                doc.dirty = False
                self.add_document_tab(doc)
            elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                doc = create_blank_document(name=os.path.basename(path))
                artboard = doc.active_artboard()
                doc.add_object(create_placed_image_object(path,artboard.x+60,artboard.y+60,embed=True))
                doc.dirty = True
                self.add_document_tab(doc)
            else:
                doc = Document.load_from_file(path)
                self.add_document_tab(doc)
        except Exception as exc:
            QMessageBox.warning(self, "Open Failed", f"Could not open {path}:\n{exc}")

    def _run_plugin(self, pl) -> None:
        c = self.current_canvas()
        msg = pl.action(c.doc)
        c.push_undo(f"Plugin: {pl.name}")
        self.statusBar().showMessage(msg, 4000)

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About KinoDraw — KinoSuite",
            "<h3>KinoDraw 1.0 — KinoSuite Vector Studio</h3>"
            "<p>Professional Windows vector graphics workstation sharing the KinoSuite design language "
            "and Adobe Illustrator studio workflow.</p>"
            "<p>Features Bezier Pen/Curvature/Shaper/Blob Brush, Pathfinder & Shape Builder, "
            "Freeform & Mesh Gradients, Variable Width & Brushes, OpenType & Touch Type, "
            "3D Extrusion & Materials, Image Trace, Perspective Grids, Data Graphics, "
            "Product Mockups, Generative Vectors, CMYK Print PDF & Multi-Scale Screen Export.</p>",
        )
