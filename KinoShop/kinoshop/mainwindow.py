"""KinoShop Main Studio Window — KinoSuite Architectural Layout + Full Photoshop Toolset."""
from __future__ import annotations

import contextlib
import io
import os
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .canvas import KinoCanvas
from .dialogs import (
    AutomationScriptsDialog,
    CameraRawDialog,
    ExtensionsDialog,
    LayerStylesDialog,
    LensAndVanishingDialog,
    LiquifyDialog,
    MeasurementCountDialog,
    MetadataCredentialsDialog,
    NeuralFiltersDialog,
    NewDocumentDialog,
    PatternTextureDialog,
    PhotoMergeDialog,
    PrintPrepDialog,
    SaveForWebSlicesDialog,
    ScanContactSheetDialog,
    SelectAndMaskDialog,
    SkyReplacementDialog,
    Studio3DDialog,
    VariablesDataSetsDialog,
)
from .engine import apply_filter_rgba, composite_document, render_single_layer_rgba
from .icons import make_app_pixmap, make_tool_icon
from .io_export import (
    ActionManager,
    KinoCloudManager,
    export_animated_gif,
    export_image,
    export_video_mp4,
    import_video_to_frames,
    load_image_rgba,
    load_ksd,
    save_ksd,
    update_linked_smart_objects,
)
from .models import ADJUSTMENT_TYPES, AnimationFrame, KinoDocument, Layer, SmartFilter
from .panels import (
    BrushesPanel,
    ChannelsPanel,
    ColorPanel,
    CompsCloudPanel,
    HistoryPanel,
    LayersPanel,
    PropertiesPanel,
    TimelinePanel,
)
from .photo_ops import (
    ai_select_sky,
    ai_select_subject,
    content_aware_fill,
    content_aware_scale,
    harmonize_layer_to_scene,
    match_color_reinhard,
)
from .plugins_builtin import load_all_plugins
from .sample_project import create_sample_studio_document
from .theme import KINOSUITE_DARK_THEME, KINOSUITE_LIGHT_THEME

TOOL_DEFS = [
    ("move", "Move Tool (V)", "V"),
    ("marquee_rect", "Rectangular Marquee (M)", "M"),
    ("marquee_ellipse", "Elliptical Marquee", ""),
    ("lasso", "Lasso Tool (L)", "L"),
    ("poly_lasso", "Polygonal Lasso", ""),
    ("quick_select", "Quick Selection (W)", "W"),
    ("magic_wand", "Magic Wand", ""),
    ("crop", "Crop & Straighten (C)", "C"),
    ("slice", "Slice Tool", ""),
    ("eyedropper", "Eyedropper (I)", "I"),
    ("spot_heal", "Spot Healing Brush (J)", "J"),
    ("remove", "AI Remove Tool", ""),
    ("clone", "Clone Stamp (S)", "S"),
    ("brush", "Brush Tool (B)", "B"),
    ("mixer_brush", "Wet Mixer Brush", ""),
    ("history_brush", "History Brush (Y)", "Y"),
    ("eraser", "Eraser (E)", "E"),
    ("gradient", "Gradient Tool (G)", "G"),
    ("bucket", "Paint Bucket", ""),
    ("dodge_burn", "Dodge / Burn (O)", "O"),
    ("blur_smudge", "Blur / Smudge", ""),
    ("pen", "Pen Path Tool (P)", "P"),
    ("text", "Type Tool (T)", "T"),
    ("shape", "Vector Shape Tool (U)", "U"),
    ("puppet_warp", "Puppet Warp Pins", ""),
    ("perspective_warp", "Perspective Warp Quad", ""),
    ("ruler_count", "Ruler & Scientific Count", ""),
    ("artboard", "Artboard Tool", ""),
    ("comment", "Review Comment Pin", ""),
    ("hand", "Hand Pan Tool (H)", "H"),
    ("zoom", "Zoom Tool (Z)", "Z"),
]


class KinoShopWindow(QMainWindow):
    def __init__(self, initial_files: Optional[List[str]] = None) -> None:
        super().__init__()
        self.setWindowTitle("KinoShop — KinoSuite Photo & Design Studio")
        self.app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico_path = os.path.join(self.app_root, "KinoShop.ico")
        if os.path.isfile(ico_path):
            self.setWindowIcon(QIcon(ico_path))
        else:
            self.setWindowIcon(QIcon(make_app_pixmap(64)))
        self.resize(1520, 930)

        self.cloud_mgr = KinoCloudManager(self.app_root)
        self.action_mgr = ActionManager(os.path.join(self.app_root, ".kinoconfig"))
        self.plugins = load_all_plugins(os.path.join(self.app_root, "plugins"))
        self.dark_theme = True
        self.current_workspace = "Essentials"

        self.canvases: List[KinoCanvas] = []
        self.tool_buttons: Dict[str, QToolButton] = {}

        self._build_ui()
        self._build_menus()

        if initial_files:
            for fp in initial_files:
                if os.path.isfile(fp):
                    self.open_path(fp)
        if not self.canvases:
            self._open_document_tab(create_sample_studio_document())

    def apply_native_taskbar_icon(self) -> None:
        """Bind KinoShop.ico directly to the Win32 HWND (ICON_SMALL & ICON_BIG) so the Windows taskbar shows Ks."""
        import sys
        if sys.platform != "win32":
            return
        ico_path = os.path.join(self.app_root, "KinoShop.ico")
        if not os.path.isfile(ico_path):
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1
            hwnd = int(self.winId())
            h_small = user32.LoadImageW(0, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            h_big = user32.LoadImageW(0, ico_path, IMAGE_ICON, 48, 48, LR_LOADFROMFILE)
            if h_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
            if h_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
        except Exception:
            pass

    # ---- Active document / canvas helpers ----
    def current_canvas(self) -> Optional[KinoCanvas]:
        w = self.doc_tabs.currentWidget()
        return w if isinstance(w, KinoCanvas) else None

    def current_doc(self) -> Optional[KinoDocument]:
        c = self.current_canvas()
        return c.doc if c else None

    # ---- UI Construction ----
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Top Control / Options Bar (KinoSuite style)
        self.ctrl_bar = QWidget()
        self.ctrl_bar.setObjectName("ControlBar")
        self.ctrl_bar.setFixedHeight(40)
        cl = QHBoxLayout(self.ctrl_bar)
        cl.setContentsMargins(10, 4, 10, 4)
        cl.setSpacing(8)

        badge = QLabel("Ks  KinoShop")
        badge.setObjectName("SuiteBadge")
        cl.addWidget(badge)

        self.lbl_tool = QLabel("Move Tool")
        self.lbl_tool.setStyleSheet("font-weight:700; color:#31A8FF;")
        cl.addWidget(self.lbl_tool)

        self.sp_opt_size = QSpinBox()
        self.sp_opt_size.setRange(1, 400)
        self.sp_opt_size.setValue(36)
        self.sp_opt_size.setPrefix("Size: ")
        self.sp_opt_size.setSuffix(" px")
        self.sp_opt_size.valueChanged.connect(self._on_opt_size)
        cl.addWidget(self.sp_opt_size)

        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems(["rounded_rect", "rectangle", "ellipse", "polygon", "star", "line"])
        self.cmb_shape.currentTextChanged.connect(self._on_opt_shape)
        cl.addWidget(QLabel("Shape:"))
        cl.addWidget(self.cmb_shape)

        self.cmb_grad = QComboBox()
        self.cmb_grad.addItems(["Linear", "Radial", "Angle", "Reflected", "Diamond"])
        self.cmb_grad.currentTextChanged.connect(self._on_opt_grad)
        cl.addWidget(QLabel("Grad:"))
        cl.addWidget(self.cmb_grad)

        self.chk_pattern_prev = QCheckBox("Pattern Preview")
        self.chk_pattern_prev.toggled.connect(self._toggle_pattern_preview)
        cl.addWidget(self.chk_pattern_prev)

        self.chk_soft_proof = QCheckBox("CMYK Soft-Proof")
        self.chk_soft_proof.toggled.connect(self._toggle_soft_proof)
        cl.addWidget(self.chk_soft_proof)

        cl.addStretch(1)

        # Workspace switcher (Accessibility & Setup)
        cl.addWidget(QLabel("Workspace:"))
        self.cmb_ws = QComboBox()
        self.cmb_ws.addItems(["Essentials", "Photography", "Painting", "Graphic & Web", "Print Prep", "Motion / Video"])
        self.cmb_ws.currentTextChanged.connect(self.apply_workspace)
        cl.addWidget(self.cmb_ws)

        b_raw = QPushButton("Camera Raw")
        b_raw.setObjectName("PrimaryButton")
        b_raw.clicked.connect(self.open_camera_raw)
        cl.addWidget(b_raw)

        root.addWidget(self.ctrl_bar)

        # 2. Main Horizontal Studio Body: Left Tools | Center Viewport + Timeline | Right Panels
        body_split = QSplitter(Qt.Orientation.Horizontal)

        # Left Tools Dock (2-column compact scrollable strip)
        tools_scroll = QScrollArea()
        tools_scroll.setObjectName("ToolsDock")
        tools_scroll.setFixedWidth(74)
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tools_box = QWidget()
        tools_box.setObjectName("ToolsDock")
        tg = QVBoxLayout(tools_box)
        tg.setContentsMargins(4, 6, 4, 6)
        tg.setSpacing(3)

        row_box = None
        for idx, (tid, tip, sc) in enumerate(TOOL_DEFS):
            if idx % 2 == 0:
                row_box = QHBoxLayout()
                row_box.setSpacing(3)
                tg.addLayout(row_box)
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setFixedSize(30, 30)
            btn.setIcon(make_tool_icon(tid, 22))
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, t=tid: self.select_tool(t))
            row_box.addWidget(btn)
            self.tool_buttons[tid] = btn
        tg.addStretch(1)

        # Iconic Photoshop-style FG/BG Color Swatch Dock & Quick Mask button at bottom of Tools Dock
        swatch_box = QWidget()
        swatch_box.setFixedSize(62, 68)
        sbl = QVBoxLayout(swatch_box)
        sbl.setContentsMargins(2, 4, 2, 2)
        sbl.setSpacing(3)
        sw_top = QHBoxLayout()
        sw_top.setSpacing(2)
        self.dock_fg_btn = QPushButton()
        self.dock_fg_btn.setFixedSize(26, 26)
        self.dock_fg_btn.setToolTip("Foreground Color (click to edit)")
        self.dock_fg_btn.clicked.connect(lambda: self.color_panel._pick_fg())
        self.dock_bg_btn = QPushButton()
        self.dock_bg_btn.setFixedSize(22, 22)
        self.dock_bg_btn.setToolTip("Background Color (click to edit)")
        self.dock_bg_btn.clicked.connect(lambda: self.color_panel._pick_bg())
        sw_top.addWidget(self.dock_fg_btn)
        sw_top.addWidget(self.dock_bg_btn)
        sbl.addLayout(sw_top)

        sw_bot = QHBoxLayout()
        sw_bot.setSpacing(2)
        b_swp = QPushButton("⇄")
        b_swp.setFixedSize(26, 20)
        b_swp.setToolTip("Swap Foreground / Background (X)")
        b_swp.clicked.connect(lambda: self.color_panel.swap_colors())
        b_def = QPushButton("D")
        b_def.setFixedSize(26, 20)
        b_def.setToolTip("Default B/W Colors (D)")
        b_def.clicked.connect(lambda: self.color_panel._reset_bw())
        sw_bot.addWidget(b_swp)
        sw_bot.addWidget(b_def)
        sbl.addLayout(sw_bot)
        tg.addWidget(swatch_box)

        tools_scroll.setWidget(tools_box)
        body_split.addWidget(tools_scroll)

        # Center Column: Document Tabs + Collapsible Bottom Timeline
        center_split = QSplitter(Qt.Orientation.Vertical)
        self.doc_tabs = QTabWidget()
        self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.setStyleSheet("QTabWidget { background: #141820; } QTabBar { background: #141820; }")
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.tabCloseRequested.connect(self._close_tab)
        self.doc_tabs.currentChanged.connect(self._on_tab_changed)
        center_split.addWidget(self.doc_tabs)

        self.timeline_panel = TimelinePanel()
        self.timeline_panel.setVisible(False)
        self.timeline_panel.frameApplied.connect(self.refresh_all)
        self.timeline_panel.exportGifRequested.connect(self.export_gif)
        self.timeline_panel.exportMp4Requested.connect(self.export_mp4)
        self.timeline_panel.importVideoRequested.connect(self.import_video_clip)
        center_split.addWidget(self.timeline_panel)
        center_split.setSizes([720, 140])
        body_split.addWidget(center_split)

        # Right Studio Dock (Top Tabs: Properties/Color/Brushes/History/Cloud | Bottom Tabs: Layers/Channels)
        right_panel = QWidget()
        right_panel.setObjectName("StudioPanel")
        right_panel.setMinimumWidth(345)
        right_panel.setMaximumWidth(440)
        rl = QVBoxLayout(right_panel)
        rl.setContentsMargins(0, 0, 0, 0)
        right_split = QSplitter(Qt.Orientation.Vertical)

        self.top_right_tabs = QTabWidget()
        self.props_panel = PropertiesPanel()
        self.props_panel.documentModified.connect(self.refresh_all)
        self.color_panel = ColorPanel()
        self.color_panel.colorChanged.connect(self._on_color_changed)
        self.brushes_panel = BrushesPanel(KinoCanvas(KinoDocument(16, 16)).brush_settings)
        self.brushes_panel.settingsChanged.connect(self._sync_brush_settings)
        self.brushes_panel.captureBrushRequested.connect(self.capture_custom_brush)
        self.history_panel = HistoryPanel()
        self.history_panel.historyRestored.connect(self.refresh_all)
        self.cloud_panel = CompsCloudPanel()
        self.cloud_panel.documentModified.connect(self.refresh_all)
        self.cloud_panel.saveCloudRequested.connect(self._save_cloud_version)
        self.cloud_panel.loadCloudRequested.connect(self._load_cloud_version)
        self.cloud_panel.shareReviewRequested.connect(self._share_for_review)

        self.top_right_tabs.addTab(self.props_panel, "Properties")
        self.top_right_tabs.addTab(self.color_panel, "Color")
        self.top_right_tabs.addTab(self.brushes_panel, "Brushes")
        self.top_right_tabs.addTab(self.history_panel, "History")
        self.top_right_tabs.addTab(self.cloud_panel, "Comps & Cloud")
        self.top_right_tabs.currentChanged.connect(self._on_right_tab_changed)

        self.bot_right_tabs = QTabWidget()
        self.layers_panel = LayersPanel()
        self.layers_panel.layersModified.connect(self.refresh_all)
        self.layers_panel.activeLayerSelected.connect(self._on_active_layer_selected)
        self.layers_panel.editMaskToggled.connect(self._on_edit_mask_toggled)
        self.layers_panel.openStylesRequested.connect(self.open_layer_styles)
        self.layers_panel.addAdjustmentRequested.connect(self.add_adjustment_layer)
        self.channels_panel = ChannelsPanel()
        self.channels_panel.channelsChanged.connect(self.refresh_all)

        self.bot_right_tabs.addTab(self.layers_panel, "Layers")
        self.bot_right_tabs.addTab(self.channels_panel, "Channels")

        right_split.addWidget(self.top_right_tabs)
        right_split.addWidget(self.bot_right_tabs)
        right_split.setSizes([380, 420])
        rl.addWidget(right_split)
        body_split.addWidget(right_panel)

        body_split.setSizes([74, 1110, 336])
        root.addWidget(body_split, 1)

        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_coords = QLabel("0, 0")
        self.lbl_doc_info = QLabel("1280×800 · 300 DPI · RGB")
        self.status_bar.addPermanentWidget(self.lbl_coords)
        self.status_bar.addPermanentWidget(self.lbl_doc_info)

        self.select_tool("move")
        self._sync_dock_swatches()

    def _sync_dock_swatches(self) -> None:
        r, g, b = self.color_panel.fg
        br, bg, bb = self.color_panel.bg
        self.dock_fg_btn.setStyleSheet(f"background:rgb({r},{g},{b}); border:2px solid #E6EAF2; border-radius:4px;")
        self.dock_bg_btn.setStyleSheet(f"background:rgb({br},{bg},{bb}); border:1px solid #64748B; border-radius:4px;")

    def keyPressEvent(self, event) -> None:
        # Classic Photoshop single-key tool & swatch shortcuts when not typing in an input widget
        if not event.modifiers():
            key_map = {
                Qt.Key.Key_V: "move",
                Qt.Key.Key_M: "marquee_rect",
                Qt.Key.Key_L: "lasso",
                Qt.Key.Key_W: "quick_select",
                Qt.Key.Key_C: "crop",
                Qt.Key.Key_I: "eyedropper",
                Qt.Key.Key_J: "spot_heal",
                Qt.Key.Key_S: "clone",
                Qt.Key.Key_B: "brush",
                Qt.Key.Key_Y: "history_brush",
                Qt.Key.Key_E: "eraser",
                Qt.Key.Key_G: "gradient",
                Qt.Key.Key_O: "dodge_burn",
                Qt.Key.Key_P: "pen",
                Qt.Key.Key_T: "text",
                Qt.Key.Key_U: "shape",
                Qt.Key.Key_H: "hand",
                Qt.Key.Key_Z: "zoom",
            }
            if event.key() in key_map:
                self.select_tool(key_map[event.key()])
                return
            if event.key() == Qt.Key.Key_X:
                self.color_panel.swap_colors()
                return
            if event.key() == Qt.Key.Key_D:
                self.color_panel._reset_bw()
                return
        super().keyPressEvent(event)

    # ---- Menus ----
    def _act(self, menu: QMenu, text: str, cb, shortcut: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(cb)
        menu.addAction(a)
        return a

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # FILE
        m_file = mb.addMenu("File")
        self._act(m_file, "New Document…", self.new_document, "Ctrl+N")
        self._act(m_file, "Open Image / .ksd…", self.open_dialog, "Ctrl+O")
        self._act(m_file, "Open Sample Studio Project", lambda: self._open_document_tab(create_sample_studio_document()))
        m_file.addSeparator()
        self._act(m_file, "Place Embedded Image…", lambda: self.place_smart_object(linked=False))
        self._act(m_file, "Place Linked Smart Object…", lambda: self.place_smart_object(linked=True))
        self._act(m_file, "Update All Linked Smart Objects", self.update_all_linked)
        m_file.addSeparator()
        self._act(m_file, "Save (.ksd)", self.save_document, "Ctrl+S")
        self._act(m_file, "Save As (.ksd)…", self.save_as_document, "Ctrl+Shift+S")
        self._act(m_file, "Export As (PNG/JPG/TIFF/WebP/SVG/PDF)…", self.export_dialog, "Ctrl+Alt+S")
        self._act(m_file, "Save for Web & Multi-Scale Slices…", self.open_save_for_web)
        self._act(m_file, "Print Prep & Export CMYK PDF…", self.open_print_prep, "Ctrl+P")
        m_file.addSeparator()
        m_auto = m_file.addMenu("Automate")
        self._act(m_auto, "Photomerge Panorama…", lambda: self.open_photomerge("Photomerge Panorama"))
        self._act(m_auto, "Merge to HDR Pro…", lambda: self.open_photomerge("Merge to HDR Pro (Exposure Fusion)"))
        self._act(m_auto, "Focus Stack…", lambda: self.open_photomerge("Focus Stack (Macro Sharpness)"))
        self._act(m_auto, "Auto-Align & Auto-Blend Layers…", lambda: self.open_photomerge("Auto-Align & Auto-Blend (Group Shot)"))
        self._act(m_auto, "Contact Sheet II & Picture Package…", self.open_scan_contact)
        self._act(m_auto, "Scan / Auto-Straighten / Split Scanned Photos…", self.open_scan_contact)
        self._act(m_auto, "Image Processor (Batch Convert)…", lambda: self.open_automation(1))
        self._act(m_auto, "Variables & Data Sets (CSV Batch)…", self.open_variables)
        m_file.addSeparator()
        self._act(m_file, "File Info, Metadata & Content Credentials…", self.open_metadata)
        self._act(m_file, "Script Events Manager…", lambda: self.open_automation(2))
        self._act(m_file, "Python Scripting Console…", lambda: self.open_automation(3))
        m_file.addSeparator()
        self._act(m_file, "Exit", self.close, "Ctrl+Q")

        # EDIT
        m_edit = mb.addMenu("Edit")
        self._act(m_edit, "Undo", self.undo, "Ctrl+Z")
        self._act(m_edit, "Redo", self.redo, "Ctrl+Y")
        m_edit.addSeparator()
        self._act(m_edit, "Content-Aware Fill", self.run_content_aware_fill, "Shift+Backspace")
        self._act(m_edit, "Content-Aware Scale…", self.run_content_aware_scale)
        self._act(m_edit, "Harmonize Active Layer to Scene Lighting", self.run_harmonize)
        m_edit.addSeparator()
        self._act(m_edit, "Sky Replacement…", self.open_sky_replacement)
        self._act(m_edit, "Puppet Warp", lambda: self.select_tool("puppet_warp"))
        self._act(m_edit, "Perspective Warp", lambda: self.select_tool("perspective_warp"))
        self._act(m_edit, "Vanishing Point (Perspective Tiling)…", lambda: self.open_lens_vanishing(1))
        self._act(m_edit, "Pattern Maker & Texture Synthesis…", self.open_pattern_maker)
        m_edit.addSeparator()
        self._act(m_edit, "Flip Horizontal", lambda: self.flip_active(1))
        self._act(m_edit, "Flip Vertical", lambda: self.flip_active(0))
        self._act(m_edit, "Rotate 90° CW", self.rotate_doc_90)
        self._act(m_edit, "Keyboard Shortcuts Reference", self.show_shortcuts)

        # IMAGE
        m_img = mb.addMenu("Image")
        m_mode = m_img.addMenu("Mode")
        for cm in ("RGB", "CMYK", "Grayscale", "Lab"):
            self._act(m_mode, f"{cm} Color", lambda _=False, m=cm: self.set_color_mode(m))
        m_img.addSeparator()
        self._act(m_img, "Image Size (Resize)…", self.resize_image_dialog, "Ctrl+Alt+I")
        self._act(m_img, "Canvas Size…", self.resize_canvas_dialog, "Ctrl+Alt+C")
        self._act(m_img, "Match Color from Reference Image…", self.run_match_color)
        self._act(m_img, "Auto-Straighten Horizon / Scan", self.run_auto_straighten)
        self._act(m_img, "Scientific Measurement & Auto-Count…", self.open_measurement_count)

        # LAYER
        m_lyr = mb.addMenu("Layer")
        self._act(m_lyr, "New Raster Layer", lambda: self.layers_panel._add_raster(), "Ctrl+Shift+N")
        self._act(m_lyr, "New Layer Group", lambda: self.layers_panel._add_group(), "Ctrl+G")
        m_adj = m_lyr.addMenu("New Adjustment Layer")
        for at in ADJUSTMENT_TYPES:
            self._act(m_adj, at, lambda _=False, t=at: self.add_adjustment_layer(t))
        self._act(m_lyr, "Add Layer Mask", lambda: self.layers_panel._add_mask())
        self._act(m_lyr, "Toggle Clipping Mask", self.toggle_clipping_mask, "Ctrl+Alt+G")
        self._act(m_lyr, "Layer Styles (fx)…", self.open_layer_styles)
        self._act(m_lyr, "Convert to Smart Object", lambda: self.layers_panel._convert_smart())
        self._act(m_lyr, "Flatten Image", self.flatten_image)

        # TYPE
        m_type = mb.addMenu("Type")
        self._act(m_type, "Add Point Text Layer", lambda: self.select_tool("text"))
        self._act(m_type, "Warp Active Text (Arc/Flag/Wave)…", self.quick_warp_text)
        self._act(m_type, "Toggle Type on a Curved Path", self.toggle_type_on_path)

        # SELECT
        m_sel = mb.addMenu("Select")
        self._act(m_sel, "Select All", self.select_all, "Ctrl+A")
        self._act(m_sel, "Deselect", self.deselect, "Ctrl+D")
        self._act(m_sel, "Inverse Selection", self.invert_selection, "Ctrl+Shift+I")
        m_sel.addSeparator()
        self._act(m_sel, "AI Select Subject", self.run_select_subject)
        self._act(m_sel, "AI Select Sky", self.run_select_sky)
        self._act(m_sel, "Remove Background (One-Click Mask)", self.run_remove_background)
        self._act(m_sel, "Select and Mask (Refine Hair & Edges)…", self.open_select_and_mask)
        self._act(m_sel, "Feather Selection…", self.feather_selection)
        self._act(m_sel, "Save Selection as Alpha Channel", self.save_sel_alpha)

        # FILTER
        m_flt = mb.addMenu("Filter")
        self._act(m_flt, "Camera Raw Studio…", self.open_camera_raw, "Ctrl+Shift+A")
        self._act(m_flt, "Liquify Studio…", self.open_liquify, "Ctrl+Shift+X")
        self._act(m_flt, "Neural Filters Studio…", self.open_neural_filters)
        self._act(m_flt, "Lens Correction…", lambda: self.open_lens_vanishing(0))
        self._act(m_flt, "Vanishing Point…", lambda: self.open_lens_vanishing(1))
        m_flt.addSeparator()
        for grp_name, flts in [
            ("Blur", ["Gaussian Blur", "Motion Blur", "Radial Blur", "Surface Blur"]),
            ("Sharpen", ["Unsharp Mask", "High Pass"]),
            ("Noise", ["Add Noise", "Reduce Noise", "Median"]),
            ("Distort", ["Twirl", "Ripple", "Spherize"]),
            ("Stylize & Render", ["Oil Paint", "Emboss", "Find Edges", "Halftone", "Vignette", "Chromatic Aberration", "Lens Flare", "Lighting Effects"]),
        ]:
            sub = m_flt.addMenu(grp_name)
            for fn in flts:
                self._act(sub, f"{fn} (Smart Filter)", lambda _=False, n=fn: self.apply_smart_or_raster_filter(n))

        # 3D
        m_3d = mb.addMenu("3D")
        self._act(m_3d, "3D Primitive & Texture Studio…", self.open_3d_studio)

        # VIEW
        m_view = mb.addMenu("View")
        self._act(m_view, "Zoom In", lambda: self.zoom_by(1.25), "Ctrl+=")
        self._act(m_view, "Zoom Out", lambda: self.zoom_by(0.8), "Ctrl+-")
        self._act(m_view, "Fit on Screen", lambda: self.current_canvas() and self.current_canvas().fit_to_view(), "Ctrl+0")
        m_view.addSeparator()
        self._act(m_view, "Toggle Pattern Preview (Seamless Tiles)", lambda: self.chk_pattern_prev.toggle())
        self._act(m_view, "Toggle CMYK Soft-Proofing", lambda: self.chk_soft_proof.toggle())
        self._act(m_view, "Toggle Rulers", self.toggle_rulers, "Ctrl+R")
        self._act(m_view, "Toggle Grid", self.toggle_grid, "Ctrl+'")
        self._act(m_view, "Add Horizontal Guide…", lambda: self.add_guide("h"))
        self._act(m_view, "Add Vertical Guide…", lambda: self.add_guide("v"))
        self._act(m_view, "Toggle Contextual Taskbar", self.toggle_context_bar)
        self._act(m_view, "Switch Dark / Studio Light Theme", self.toggle_theme)

        # PLUGINS / EXTENSIONS
        m_plg = mb.addMenu("Plugins")
        self._act(m_plg, "Extensions & Plugins Manager (Denoise / Portrait / Stock)…", self.open_extensions)
        self._act(m_plg, "Reload External Plugins Folder", self.reload_plugins)

        # WINDOW
        m_win = mb.addMenu("Window")
        self._act(m_win, "Toggle Timeline (GIF & Video)", lambda: self.timeline_panel.setVisible(not self.timeline_panel.isVisible()))
        self._act(m_win, "Actions Panel / Recorder…", lambda: self.open_automation(0))
        self._act(m_win, "Layer Comps & KinoCloud", lambda: self.top_right_tabs.setCurrentWidget(self.cloud_panel))
        self._act(m_win, "History & Snapshots", lambda: self.top_right_tabs.setCurrentWidget(self.history_panel))

    # ---- Document Tab Management ----
    def _open_document_tab(self, doc: KinoDocument) -> KinoCanvas:
        canvas = KinoCanvas(doc)
        canvas.brush_settings = self.brushes_panel.settings
        canvas.fg_color = self.color_panel.fg
        canvas.bg_color = self.color_panel.bg
        canvas.documentChanged.connect(self.refresh_all)
        canvas.selectionChanged.connect(self._on_selection_changed)
        canvas.colorPicked.connect(lambda c: self.color_panel.set_fg(c, emit=True))
        canvas.cursorMoved.connect(self._on_cursor_moved)
        canvas.statusMessage.connect(lambda m: self.status_bar.showMessage(m, 5000))
        canvas.contextAction.connect(self._handle_context_action)

        self.canvases.append(canvas)
        idx = self.doc_tabs.addTab(canvas, doc.name)
        self.doc_tabs.setCurrentIndex(idx)
        canvas.fit_to_view()
        self._sync_panels_to_current()
        self._fire_script_event("on_open")
        return canvas

    def _close_tab(self, idx: int) -> None:
        if self.doc_tabs.count() <= 1:
            return
        w = self.doc_tabs.widget(idx)
        self.doc_tabs.removeTab(idx)
        if w in self.canvases:
            self.canvases.remove(w)
            w.deleteLater()

    def _on_right_tab_changed(self, _idx: int) -> None:
        doc = self.current_doc()
        c = self.current_canvas()
        if not doc or not c:
            return
        cur = self.top_right_tabs.currentWidget()
        if cur is self.props_panel:
            self.props_panel.rebuild()
            self.props_panel.update_histogram(c._comp_rgba)
        elif cur is self.history_panel:
            self.history_panel.refresh()
        elif cur is self.cloud_panel:
            self.cloud_panel.refresh(self.cloud_mgr.list_versions(doc))

    def _on_tab_changed(self, _idx: int) -> None:
        self._sync_panels_to_current()

    def _sync_panels_to_current(self) -> None:
        doc = self.current_doc()
        c = self.current_canvas()
        if not doc or not c:
            return
        self.layers_panel.set_document(doc)
        self.channels_panel.set_document(doc)
        self.props_panel.set_document(doc)
        self.history_panel.set_document(doc)
        self.cloud_panel.set_document(doc, self.cloud_mgr.list_versions(doc))
        self.timeline_panel.set_document(doc)
        self.props_panel.update_histogram(c._comp_rgba)
        self.chk_pattern_prev.blockSignals(True)
        self.chk_pattern_prev.setChecked(doc.pattern_preview)
        self.chk_pattern_prev.blockSignals(False)
        self.chk_soft_proof.blockSignals(True)
        self.chk_soft_proof.setChecked(doc.print_settings.soft_proof)
        self.chk_soft_proof.blockSignals(False)
        self.lbl_doc_info.setText(f"{doc.width}×{doc.height} px · {doc.dpi} DPI · {doc.color_mode} ({doc.color_profile[:16]})")

    def _on_active_layer_selected(self) -> None:
        """Fast path (<2ms) when clicking a layer in the Layers panel — zero image re-compositing!"""
        c = self.current_canvas()
        if c:
            c._update_context_bar_mode()
        self.props_panel.rebuild()

    def refresh_all(self) -> None:
        c = self.current_canvas()
        doc = self.current_doc()
        if not c or not doc:
            return
        c.refresh_composite()
        self.layers_panel.refresh()
        self.channels_panel.refresh()
        if self.top_right_tabs.currentWidget() is self.props_panel:
            self.props_panel.update_histogram(c._comp_rgba)
        elif self.top_right_tabs.currentWidget() is self.history_panel:
            self.history_panel.refresh()
        elif self.top_right_tabs.currentWidget() is self.cloud_panel:
            self.cloud_panel.refresh(self.cloud_mgr.list_versions(doc))
        self.doc_tabs.setTabText(self.doc_tabs.currentIndex(), doc.name + ("*" if doc.dirty else ""))
        self.lbl_doc_info.setText(f"{doc.width}×{doc.height} px · {doc.dpi} DPI · {doc.color_mode}")

    # ---- Tool & Option Handlers ----
    def select_tool(self, tid: str) -> None:
        for k, b in self.tool_buttons.items():
            b.blockSignals(True)
            b.setChecked(k == tid)
            b.setIcon(make_tool_icon(k, 22, active=(k == tid)))
            b.blockSignals(False)
        c = self.current_canvas()
        if c:
            c.set_tool(tid)
        self.lbl_tool.setText(tid.replace("_", " ").title())

    def _on_opt_size(self, v: int) -> None:
        self.brushes_panel.sp_size.setValue(v)

    def _on_opt_shape(self, s: str) -> None:
        for c in self.canvases:
            c.shape_subtool = s

    def _on_opt_grad(self, s: str) -> None:
        for c in self.canvases:
            c.gradient_style = s

    def _on_color_changed(self, fg, bg) -> None:
        for c in self.canvases:
            c.fg_color = fg
            c.bg_color = bg
        if hasattr(self, "dock_fg_btn"):
            self._sync_dock_swatches()

    def _sync_brush_settings(self) -> None:
        self.sp_opt_size.blockSignals(True)
        self.sp_opt_size.setValue(int(self.brushes_panel.settings.size))
        self.sp_opt_size.blockSignals(False)

    def _on_edit_mask_toggled(self, v: bool) -> None:
        c = self.current_canvas()
        if c:
            c.editing_mask = v
            self.status_bar.showMessage("Painting on Layer Mask (white reveals, black hides)." if v else "Painting on Layer Pixels.", 3000)

    def _on_cursor_moved(self, x: int, y: int, col: str) -> None:
        self.lbl_coords.setText(f"X:{x} Y:{y}  {col}")

    def _on_selection_changed(self) -> None:
        c = self.current_canvas()
        if c:
            c._update_context_bar_mode()

    def _handle_context_action(self, cmd: str) -> None:
        dispatch = {
            "select_subject": self.run_select_subject,
            "select_sky": self.run_select_sky,
            "remove_bg": self.run_remove_background,
            "sky_replace": self.open_sky_replacement,
            "harmonize": self.run_harmonize,
            "camera_raw": self.open_camera_raw,
            "caf": self.run_content_aware_fill,
            "select_mask": self.open_select_and_mask,
            "add_mask": lambda: self.layers_panel._add_mask(),
            "invert_sel": self.invert_selection,
            "deselect": self.deselect,
            "edit_text": lambda: self.top_right_tabs.setCurrentWidget(self.props_panel),
            "warp_text": self.quick_warp_text,
            "type_on_path": self.toggle_type_on_path,
            "layer_styles": self.open_layer_styles,
        }
        fn = dispatch.get(cmd)
        if fn:
            fn()

    # ---- File I/O Actions ----
    def new_document(self) -> None:
        dlg = NewDocumentDialog(self)
        if dlg.exec():
            sp = dlg.result_spec()
            doc = KinoDocument(
                width=sp["width"], height=sp["height"], name=sp["name"],
                dpi=sp["dpi"], color_mode=sp["color_mode"],
                color_profile=sp["color_profile"], background=sp["background"],
            )
            doc.print_settings.bleed_mm = sp["bleed_mm"]
            self._open_document_tab(doc)
            self._fire_script_event("on_new")

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "",
            "All Supported (*.ksd *.png *.jpg *.jpeg *.tif *.tiff *.webp *.bmp *.gif *.psd);;KinoShop Document (*.ksd);;Images (*.png *.jpg *.jpeg *.tif *.webp)",
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if path.lower().endswith(".ksd"):
            doc = load_ksd(path)
        else:
            rgba = load_image_rgba(path)
            h, w = rgba.shape[:2]
            doc = KinoDocument(width=w, height=h, name=os.path.basename(path))
            doc.layers[0].image = rgba
            doc.layers[0].name = os.path.splitext(os.path.basename(path))[0]
            doc.file_path = None
            doc.push_history("Opened Image", is_snapshot=True)
        self._open_document_tab(doc)

    def place_smart_object(self, linked: bool = False) -> None:
        doc = self.current_doc()
        if not doc:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Place Linked" if linked else "Place Embedded", "", "Images & KSD (*.png *.jpg *.jpeg *.tif *.webp *.ksd)")
        if not path:
            return
        if path.lower().endswith(".ksd"):
            src = composite_document(load_ksd(path), apply_view_effects=False)
        else:
            src = load_image_rgba(path)
        lyr = Layer(
            name=os.path.basename(path) + (" [Linked]" if linked else " [Smart]"),
            kind="smart_object",
            smart_source=src,
            linked_path=path if linked else "",
            linked_mtime=os.path.getmtime(path) if linked else 0.0,
        )
        doc.layers.append(lyr)
        doc.active_layer_id = lyr.uid
        doc.push_history("Place Linked Smart Object" if linked else "Place Embedded Smart Object")
        self.refresh_all()

    def update_all_linked(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        n = update_linked_smart_objects(doc, force=True)
        self.refresh_all()
        self.status_bar.showMessage(f"Updated {n} Linked Smart Object(s).", 4000)

    def save_document(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        if doc.file_path and doc.file_path.lower().endswith(".ksd"):
            save_ksd(doc, doc.file_path)
            self._fire_script_event("on_save")
            self.refresh_all()
            self.status_bar.showMessage(f"Saved {doc.file_path}", 4000)
        else:
            self.save_as_document()

    def save_as_document(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save KinoShop Document", doc.name, "KinoShop Document (*.ksd)")
        if path:
            if not path.lower().endswith(".ksd"):
                path += ".ksd"
            save_ksd(doc, path)
            self._fire_script_event("on_save")
            self.refresh_all()
            self.status_bar.showMessage(f"Saved {path}", 4000)

    def export_dialog(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        stem = os.path.splitext(doc.name)[0]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Image", f"{stem}.png",
            "PNG (*.png);;JPEG (*.jpg);;TIFF (*.tiff);;WebP (*.webp);;Print PDF (*.pdf);;SVG (*.svg);;BMP (*.bmp);;ICO (*.ico)",
        )
        if path:
            export_image(doc, path)
            self._fire_script_event("on_export")
            self.status_bar.showMessage(f"Exported {path}", 4000)

    # ---- Edit / Selection / AI Operations ----
    def undo(self) -> None:
        doc = self.current_doc()
        if doc and doc.undo():
            self.refresh_all()

    def redo(self) -> None:
        doc = self.current_doc()
        if doc and doc.redo():
            self.refresh_all()

    def select_all(self) -> None:
        doc = self.current_doc()
        if doc:
            doc.selection = np.ones((doc.height, doc.width), dtype=np.float32)
            self.refresh_all()

    def deselect(self) -> None:
        doc = self.current_doc()
        if doc:
            doc.selection = None
            self.refresh_all()

    def invert_selection(self) -> None:
        doc = self.current_doc()
        if doc and doc.selection is not None:
            doc.selection = np.clip(1.0 - doc.selection, 0.0, 1.0)
            self.refresh_all()

    def feather_selection(self) -> None:
        doc = self.current_doc()
        if not doc or doc.selection is None:
            return
        rad, ok = QInputDialog.getInt(self, "Feather Selection", "Feather radius (px):", 8, 1, 100)
        if ok:
            k = rad * 2 + 1
            doc.selection = cv2.GaussianBlur(doc.selection, (k, k), rad * 0.5)
            self.refresh_all()

    def save_sel_alpha(self) -> None:
        doc = self.current_doc()
        if doc:
            doc.save_selection_as_alpha()
            self.refresh_all()

    def run_select_subject(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        doc.selection = ai_select_subject(comp)
        self.refresh_all()
        self.status_bar.showMessage("AI Select Subject completed.", 4000)

    def run_select_sky(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        doc.selection = ai_select_sky(comp)
        self.refresh_all()
        self.status_bar.showMessage("AI Select Sky completed.", 4000)

    def run_remove_background(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.active_layer()
        if not lyr:
            return
        comp = render_single_layer_rgba(lyr, doc.width, doc.height) or composite_document(doc, apply_view_effects=False)
        sel = ai_select_subject(comp)
        lyr.mask = np.clip(sel * 255.0, 0, 255).astype(np.uint8)
        lyr.mask_enabled = True
        doc.push_history("Remove Background")
        self.refresh_all()

    def open_select_and_mask(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        mask = doc.selection if doc.selection is not None else ai_select_subject(comp)
        dlg = SelectAndMaskDialog(comp, mask, self)
        if dlg.exec():
            m, decont = dlg.result_mask_and_image()
            doc.selection = m
            if dlg.chk_dec.isChecked() and doc.active_layer() and doc.active_layer().image is not None:
                doc.active_layer().image = decont
            doc.push_history("Select and Mask")
            self.refresh_all()

    def run_content_aware_fill(self) -> None:
        doc = self.current_doc()
        if not doc or doc.selection is None:
            self.status_bar.showMessage("Make a selection first for Content-Aware Fill.", 3500)
            return
        lyr = doc.ensure_raster_layer()
        lyr.image = content_aware_fill(lyr.image, doc.selection)
        doc.push_history("Content-Aware Fill")
        doc.metadata.record_provenance("Content-Aware Fill", ai_used=True)
        self.refresh_all()

    def run_content_aware_scale(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        nw, ok = QInputDialog.getInt(self, "Content-Aware Scale", "Target Width (px, protects key subjects & skin):", max(64, int(doc.width * 0.85)), 64, doc.width * 2)
        if not ok:
            return
        lyr = doc.ensure_raster_layer()
        scaled = content_aware_scale(lyr.image, nw, doc.height, protect_mask=doc.selection, protect_skin=True)
        lyr.image = np.zeros((doc.height, doc.width, 4), dtype=np.uint8)
        cw = min(doc.width, scaled.shape[1])
        lyr.image[:, :cw] = scaled[:, :cw]
        doc.push_history("Content-Aware Scale")
        self.refresh_all()

    def run_harmonize(self) -> None:
        doc = self.current_doc()
        if not doc or len(doc.layers) < 2:
            self.status_bar.showMessage("Harmonize blends the active foreground layer into the layers below it.", 4000)
            return
        lyr = doc.active_layer()
        if not lyr:
            return
        idx = doc.layers.index(lyr) if lyr in doc.layers else len(doc.layers) - 1
        bg = composite_document(doc, apply_view_effects=False)
        if idx > 0:
            from .engine import composite_layer_list
            bg = composite_layer_list(doc.layers[:idx], doc.width, doc.height)
        fg = render_single_layer_rgba(lyr, doc.width, doc.height)
        if fg is not None:
            harm = harmonize_layer_to_scene(fg, bg, strength=0.82)
            if lyr.kind == "smart_object":
                lyr.smart_source = harm
            else:
                lyr.kind = "raster"
                lyr.image = harm
                lyr.offset_x = 0
                lyr.offset_y = 0
            doc.push_history("Harmonize Layer Lighting")
            doc.metadata.record_provenance("Harmonize AI Lighting", ai_used=True)
            self.refresh_all()

    def run_match_color(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select Reference Image for Color Match", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        ref = load_image_rgba(path)
        lyr = doc.ensure_raster_layer()
        lyr.image = match_color_reinhard(lyr.image, ref, strength=0.85)
        doc.push_history("Match Color")
        self.refresh_all()

    def run_auto_straighten(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        from .photo_ops import auto_straighten_scan
        lyr = doc.ensure_raster_layer()
        deskewed, deg = auto_straighten_scan(lyr.image)
        lyr.image = deskewed
        doc.push_history(f"Auto-Straighten ({deg:.1f}°)")
        self.refresh_all()

    # ---- Studio Dialog Launchers ----
    def open_layer_styles(self) -> None:
        doc = self.current_doc()
        if not doc or not doc.active_layer():
            return
        lyr = doc.active_layer()
        dlg = LayerStylesDialog(lyr.styles, self)
        if dlg.exec():
            lyr.styles = dlg.styles
            doc.push_history("Edit Layer Styles")
            self.refresh_all()

    def add_adjustment_layer(self, adj_type: str) -> None:
        doc = self.current_doc()
        if not doc:
            return
        doc.add_adjustment_layer(adj_type)
        doc.push_history(f"Add {adj_type} Adjustment")
        self.action_mgr.record_step("add_adjustment", {"type": adj_type})
        self.top_right_tabs.setCurrentWidget(self.props_panel)
        self.refresh_all()

    def apply_smart_or_raster_filter(self, name: str) -> None:
        doc = self.current_doc()
        if not doc or not doc.active_layer():
            return
        lyr = doc.active_layer()
        lyr.smart_filters.append(SmartFilter(name=name, enabled=True, params={}))
        doc.push_history(f"Smart Filter: {name}")
        self.action_mgr.record_step("apply_filter", {"name": name})
        self.refresh_all()

    def open_camera_raw(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.ensure_raster_layer()
        dlg = CameraRawDialog(lyr.image, self)
        if dlg.exec():
            lyr.image = dlg.result_image()
            doc.push_history("Camera Raw Develop")
            doc.metadata.record_provenance("Camera Raw Develop")
            self.refresh_all()

    def open_liquify(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.ensure_raster_layer()
        dlg = LiquifyDialog(lyr.image, self)
        if dlg.exec():
            lyr.image = dlg.result_image()
            doc.push_history("Liquify")
            self.refresh_all()

    def open_sky_replacement(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.ensure_raster_layer()
        dlg = SkyReplacementDialog(lyr.image, self)
        if dlg.exec():
            lyr.image = dlg.result_image()
            doc.push_history("Sky Replacement")
            doc.metadata.record_provenance("Sky Replacement", ai_used=True)
            self.refresh_all()

    def open_neural_filters(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.ensure_raster_layer()
        dlg = NeuralFiltersDialog(lyr.image, self)
        if dlg.exec():
            res = dlg.result_image()
            if res.shape[:2] != (doc.height, doc.width):
                doc.width, doc.height = res.shape[1], res.shape[0]
                doc.selection = None
            lyr.image = res
            doc.push_history(f"Neural Filter: {dlg.cmb_filter.currentText()}")
            doc.metadata.record_provenance("Neural Filter", ai_used=True, details=dlg.cmb_filter.currentText())
            self.refresh_all()

    def open_photomerge(self, mode: str) -> None:
        doc = self.current_doc()
        if not doc:
            return
        dlg = PhotoMergeDialog(doc, initial_mode=mode, parent=self)
        if dlg.exec() and dlg.result_rgba is not None:
            h, w = dlg.result_rgba.shape[:2]
            ndoc = KinoDocument(width=w, height=h, name=f"{mode.split()[0]}_Merged.ksd")
            ndoc.layers[0].image = dlg.result_rgba
            ndoc.layers[0].name = mode
            ndoc.push_history(mode, is_snapshot=True)
            self._open_document_tab(ndoc)

    def open_pattern_maker(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        dlg = PatternTextureDialog(comp, self)
        if dlg.exec():
            doc.add_raster_layer("Seamless Pattern", dlg.result_image())
            doc.pattern_preview = True
            doc.push_history("Pattern / Texture Synthesis")
            self.refresh_all()

    def open_lens_vanishing(self, tab: int = 0) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.ensure_raster_layer()
        dlg = LensAndVanishingDialog(lyr.image, tab=tab, parent=self)
        if dlg.exec():
            lyr.image = dlg.result_image()
            doc.push_history("Vanishing Point" if tab == 1 else "Lens Correction")
            self.refresh_all()

    def open_3d_studio(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        dlg = Studio3DDialog(doc.width, doc.height, comp, self)
        if dlg.exec():
            doc.add_raster_layer("3D Object", dlg.result_image())
            doc.push_history("Add 3D Object")
            self.refresh_all()

    def open_print_prep(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        dlg = PrintPrepDialog(doc, self)
        if dlg.exec():
            self.refresh_all()

    def open_save_for_web(self) -> None:
        doc = self.current_doc()
        if doc:
            SaveForWebSlicesDialog(doc, self).exec()

    def open_variables(self) -> None:
        doc = self.current_doc()
        if doc:
            VariablesDataSetsDialog(doc, self).exec()

    def open_automation(self, tab: int = 0) -> None:
        AutomationScriptsDialog(self.action_mgr, self.play_action, self.run_python_script, initial_tab=tab, parent=self).exec()

    def open_scan_contact(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        dlg = ScanContactSheetDialog(comp, self)
        if dlg.exec():
            for name, arr in dlg.output_images:
                h, w = arr.shape[:2]
                nd = KinoDocument(width=w, height=h, name=name)
                nd.layers[0].image = arr
                nd.push_history(name, is_snapshot=True)
                self._open_document_tab(nd)

    def open_metadata(self) -> None:
        doc = self.current_doc()
        if doc:
            MetadataCredentialsDialog(doc, self).exec()

    def open_extensions(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.ensure_raster_layer()
        dlg = ExtensionsDialog(self.plugins, lyr.image, self)
        if dlg.exec() and dlg.result_rgba is not None:
            if "Stock" in dlg.result_name:
                doc.add_raster_layer(f"Stock: {dlg.ed_query.text()}", dlg.result_rgba)
            else:
                lyr.image = dlg.result_rgba
            doc.push_history(f"Extension: {dlg.result_name}")
            self.refresh_all()

    def reload_plugins(self) -> None:
        self.plugins = load_all_plugins(os.path.join(self.app_root, "plugins"))
        self.status_bar.showMessage(f"Loaded {len(self.plugins)} plugins/extensions.", 4000)

    def open_measurement_count(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        if MeasurementCountDialog(doc, comp, self).exec():
            self.refresh_all()

    # ---- Actions / Scripting / Events ----
    def play_action(self, name: str) -> None:
        doc = self.current_doc()
        steps = self.action_mgr.actions.get(name, [])
        if not doc or not steps:
            return
        for st in steps:
            cmd = st.get("cmd")
            p = st.get("params", {})
            if cmd == "add_adjustment":
                doc.add_adjustment_layer(p.get("type", "Levels"), p)
            elif cmd == "apply_filter":
                lyr = doc.active_layer()
                if lyr:
                    lyr.smart_filters.append(SmartFilter(name=p.get("name", "Unsharp Mask"), params=p))
        doc.push_history(f"Action: {name}")
        self.refresh_all()

    def run_python_script(self, code: str) -> str:
        buf = io.StringIO()
        ns = {"doc": self.current_doc(), "app": self, "np": np, "cv2": cv2}
        try:
            with contextlib.redirect_stdout(buf):
                exec(code, ns, ns)
            out = buf.getvalue() or "Script executed cleanly."
        except Exception as exc:
            out = f"Error: {exc}"
        self.refresh_all()
        return out

    def _fire_script_event(self, event_name: str) -> None:
        script = self.action_mgr.script_events.get(event_name, "").strip()
        if not script:
            return
        if os.path.isfile(script):
            script = open(script, "r", encoding="utf-8").read()
        self.run_python_script(script)

    # ---- Image / Transform / Brush / View Utilities ----
    def set_color_mode(self, mode: str) -> None:
        doc = self.current_doc()
        if doc:
            doc.set_color_mode(mode)
            self.refresh_all()

    def resize_image_dialog(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        nw, ok = QInputDialog.getInt(self, "Image Size", "New Width (px, aspect preserved):", doc.width, 32, 8192)
        if not ok:
            return
        nh = max(16, int(round(doc.height * (nw / max(1, doc.width)))))
        for lyr in doc.iter_all_layers():
            if lyr.image is not None:
                lyr.image = cv2.resize(lyr.image, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
            if lyr.mask is not None:
                lyr.mask = cv2.resize(lyr.mask, (nw, nh), interpolation=cv2.INTER_LINEAR)
        doc.width, doc.height = nw, nh
        doc.selection = None
        doc.push_history("Image Size")
        self.refresh_all()

    def resize_canvas_dialog(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        nw, ok = QInputDialog.getInt(self, "Canvas Size", "New Canvas Width (px):", doc.width + 200, 32, 8192)
        if not ok:
            return
        nh, ok2 = QInputDialog.getInt(self, "Canvas Size", "New Canvas Height (px):", doc.height + 200, 32, 8192)
        if not ok2:
            return
        dx = (nw - doc.width) // 2
        dy = (nh - doc.height) // 2
        for lyr in doc.iter_all_layers():
            if lyr.image is not None:
                nc = np.zeros((nh, nw, 4), dtype=np.uint8)
                sx0, sy0 = max(0, -dx), max(0, -dy)
                dx0, dy0 = max(0, dx), max(0, dy)
                cw = min(doc.width - sx0, nw - dx0)
                ch = min(doc.height - sy0, nh - dy0)
                if cw > 0 and ch > 0:
                    nc[dy0:dy0 + ch, dx0:dx0 + cw] = lyr.image[sy0:sy0 + ch, sx0:sx0 + cw]
                lyr.image = nc
        doc.width, doc.height = nw, nh
        doc.selection = None
        doc.push_history("Canvas Size")
        self.refresh_all()

    def flip_active(self, code: int) -> None:
        doc = self.current_doc()
        if not doc:
            return
        lyr = doc.ensure_raster_layer()
        lyr.image = cv2.flip(lyr.image, code)
        doc.push_history("Flip Layer")
        self.refresh_all()

    def rotate_doc_90(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        for lyr in doc.iter_all_layers():
            if lyr.image is not None:
                lyr.image = cv2.rotate(lyr.image, cv2.ROTATE_90_CLOCKWISE)
        doc.width, doc.height = doc.height, doc.width
        doc.selection = None
        doc.push_history("Rotate 90° CW")
        self.refresh_all()

    def toggle_clipping_mask(self) -> None:
        doc = self.current_doc()
        if doc and doc.active_layer():
            doc.active_layer().clipping_mask = not doc.active_layer().clipping_mask
            self.refresh_all()

    def flatten_image(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        doc.layers = [Layer(name="Background", kind="raster", image=comp)]
        doc.active_layer_id = doc.layers[0].uid
        doc.push_history("Flatten Image")
        self.refresh_all()

    def quick_warp_text(self) -> None:
        doc = self.current_doc()
        if not doc or not doc.active_layer() or doc.active_layer().kind != "text":
            self.status_bar.showMessage("Select a Type layer first to Warp Text.", 3500)
            return
        style, ok = QInputDialog.getItem(self, "Warp Text", "Warp Style:", ["None", "Arc", "Arch", "Bulge", "Flag", "Wave", "Rise", "Fish", "Twist"], 1, False)
        if ok:
            doc.active_layer().text_data.warp_style = style
            doc.push_history(f"Warp Text ({style})")
            self.refresh_all()

    def toggle_type_on_path(self) -> None:
        doc = self.current_doc()
        if doc and doc.active_layer() and doc.active_layer().kind == "text":
            td = doc.active_layer().text_data
            td.on_path = not td.on_path
            if td.on_path and len(td.path_points) < 3:
                td.path_points = [(td.x, td.y), (td.x + 220, td.y - 100), (td.x + 440, td.y)]
            doc.push_history("Type on Path")
            self.refresh_all()

    def capture_custom_brush(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        comp = composite_document(doc, apply_view_effects=False)
        if doc.selection is not None and float(doc.selection.max()) > 0.1:
            ys, xs = np.nonzero(doc.selection > 0.2)
            crop = comp[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        else:
            crop = comp
        gray = 1.0 - (cv2.cvtColor(crop[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0)
        self.brushes_panel.settings.custom_tip = gray
        self.brushes_panel.cmb_preset.setCurrentText("Custom")
        self.status_bar.showMessage("Captured Custom Brush Tip from selection!", 4000)

    # ---- Cloud, Timeline & Workspace Helpers ----
    def _save_cloud_version(self, note: str) -> None:
        doc = self.current_doc()
        if not doc:
            return
        entry = self.cloud_mgr.save_cloud_version(doc, note)
        self.cloud_panel.refresh(self.cloud_mgr.list_versions(doc))
        self.status_bar.showMessage(f"Saved KinoCloud v{entry['version']:03d}: {note}", 4000)

    def _load_cloud_version(self, vfile: str) -> None:
        doc = self.current_doc()
        if not doc:
            return
        loaded = self.cloud_mgr.load_version(doc, vfile)
        self._open_document_tab(loaded)

    def _share_for_review(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export KinoCloud Share-for-Review HTML", f"{os.path.splitext(doc.name)[0]}_review.html", "HTML (*.html)")
        if path:
            self.cloud_mgr.export_share_for_review_html(doc, path)
            QMessageBox.information(self, "Share for Review", f"Exported interactive review package:\n{path}")

    def export_gif(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export Animated GIF", "animation.gif", "GIF (*.gif)")
        if p:
            export_animated_gif(doc, p)
            self.status_bar.showMessage(f"Exported animated GIF: {p}", 4000)

    def export_mp4(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export Video MP4", "timeline.mp4", "MP4 (*.mp4)")
        if p:
            export_video_mp4(doc, p, fps=doc.timeline_fps)
            self.status_bar.showMessage(f"Exported MP4 video: {p}", 4000)

    def import_video_clip(self) -> None:
        doc = self.current_doc()
        if not doc:
            return
        p, _ = QFileDialog.getOpenFileName(self, "Import Video to Timeline", "", "Video (*.mp4 *.avi *.mov *.mkv)")
        if p:
            frames, fps = import_video_to_frames(p, max_frames=60)
            if frames:
                doc.width, doc.height = frames[0].shape[1], frames[0].shape[0]
                doc.timeline_fps = fps
                doc.frames = [AnimationFrame(name=f"Video {i+1}", duration_ms=int(1000 / max(1, fps)), video_frame=fr) for i, fr in enumerate(frames)]
                doc.layers[0].image = frames[0].copy()
                self.timeline_panel.setVisible(True)
                self.timeline_panel.refresh()
                self.refresh_all()

    def apply_workspace(self, ws: str) -> None:
        self.current_workspace = ws
        self.timeline_panel.setVisible(ws == "Motion / Video")
        if ws == "Painting":
            self.top_right_tabs.setCurrentWidget(self.brushes_panel)
        elif ws == "Photography":
            self.top_right_tabs.setCurrentWidget(self.props_panel)
        elif ws == "Print Prep":
            self.bot_right_tabs.setCurrentWidget(self.channels_panel)
        elif ws == "Graphic & Web":
            self.top_right_tabs.setCurrentWidget(self.cloud_panel)
        else:
            self.top_right_tabs.setCurrentWidget(self.props_panel)
            self.bot_right_tabs.setCurrentWidget(self.layers_panel)
        self.status_bar.showMessage(f"Switched Workspace → {ws}", 3000)

    def _toggle_pattern_preview(self, v: bool) -> None:
        doc = self.current_doc()
        if doc:
            doc.pattern_preview = v
            self.refresh_all()

    def _toggle_soft_proof(self, v: bool) -> None:
        doc = self.current_doc()
        if doc:
            doc.print_settings.soft_proof = v
            self.refresh_all()

    def zoom_by(self, factor: float) -> None:
        c = self.current_canvas()
        if c:
            c.zoom = max(0.08, min(24.0, c.zoom * factor))
            c.update()

    def toggle_rulers(self) -> None:
        c = self.current_canvas()
        if c:
            c.show_rulers = not c.show_rulers
            c.update()

    def toggle_grid(self) -> None:
        c = self.current_canvas()
        if c:
            c.show_grid = not c.show_grid
            c.update()

    def toggle_context_bar(self) -> None:
        c = self.current_canvas()
        if c:
            c.show_contextual_bar = not c.show_contextual_bar
            c._reposition_context_bar()

    def add_guide(self, axis: str) -> None:
        doc = self.current_doc()
        if not doc:
            return
        val, ok = QInputDialog.getInt(self, "Add Guide", "Position (px):", doc.height // 2 if axis == "h" else doc.width // 2, 0, 8192)
        if ok:
            (doc.guides_h if axis == "h" else doc.guides_v).append(float(val))
            self.refresh_all()

    def toggle_theme(self) -> None:
        self.dark_theme = not self.dark_theme
        QApplication.instance().setStyleSheet(KINOSUITE_DARK_THEME if self.dark_theme else KINOSUITE_LIGHT_THEME)

    def show_shortcuts(self) -> None:
        lines = [f"{sc or '—':6s}  {tip}" for _, tip, sc in TOOL_DEFS if sc]
        lines += ["", "Ctrl+N New  |  Ctrl+O Open  |  Ctrl+S Save .ksd  |  Ctrl+Z/Y Undo/Redo",
                  "Ctrl+Shift+A Camera Raw  |  Ctrl+Shift+X Liquify  |  [ / ] Brush Size  |  Space+Drag Pan"]
        QMessageBox.information(self, "KinoShop Keyboard Shortcuts", "\n".join(lines))
