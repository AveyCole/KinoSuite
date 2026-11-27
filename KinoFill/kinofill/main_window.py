"""Main application window for KinoFill — KinoSuite PDF Studio."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QImage,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, APP_SUBTITLE, APP_VERSION, SUITE_NAME, get_config_path
from .canvas_widget import PdfDocumentView, ToolSettings
from .dialogs import (
    CustomStampDialog,
    ExportImagesDialog,
    HeaderFooterDialog,
    MergePdfsDialog,
    MetadataDialog,
    NewBlankPdfDialog,
    SecurityDialog,
    SignatureDialog,
    SplitPdfDialog,
    WatermarkDialog,
)
from .icons import make_app_pixmap, make_icon
from .models import (
    BaseItem,
    DocumentState,
    FormFieldItem,
    HighlightItem,
    ImageItem,
    InkItem,
    NoteItem,
    RedactItem,
    ShapeItem,
    StampItem,
    TextItem,
    WhiteoutItem,
)
from .pdf_engine import (
    create_blank_pdf,
    export_pdf_to_images,
    extract_acroform_fields,
    get_available_fonts,
    image_to_png_b64,
    images_to_pdf,
    merge_pdfs,
    mutate_pdf_pages,
    open_reader,
    read_pdf_metadata,
    save_edited_pdf,
    split_pdf,
)
from .theme import KINOSUITE_DARK_THEME, KINOSUITE_LIGHT_THEME


def _swatch_style(hex_col: str) -> str:
    if not hex_col:
        return (
            "QPushButton { background: transparent; border: 1.5px dashed #64748B; "
            "border-radius: 4px; padding: 0px; min-width: 24px; max-width: 24px; "
            "min-height: 22px; max-height: 22px; }"
        )
    return (
        f"QPushButton {{ background-color: {hex_col}; border: 1.5px solid #64748B; "
        "border-radius: 4px; padding: 0px; min-width: 24px; max-width: 24px; "
        "min-height: 22px; max-height: 22px; }"
    )


class DocumentTab(QWidget):
    """Container for one open document tab."""

    def __init__(self, state: DocumentState, settings: ToolSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self.temp_files: List[str] = []
        if state.working_pdf_path:
            self.temp_files.append(state.working_pdf_path)
        self.view = PdfDocumentView(state, settings, self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

    def cleanup_temps(self) -> None:
        self.view.pdf_doc.close()
        for p in self.temp_files:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        self.temp_files.clear()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {APP_SUBTITLE}")
        self.resize(1420, 890)
        self.setAcceptDrops(True)

        self.dark_mode: bool = True
        self.recent_files: List[str] = []
        self.settings = ToolSettings()
        self._tool_actions: Dict[str, QAction] = {}
        self._updating_ctx_ui: bool = False

        self._load_config()
        self.setWindowIcon(QIcon(make_app_pixmap(64)))

        self._build_menus()
        self._build_main_toolbar()
        self._build_context_bar()
        self._build_central_workspace()
        self._build_status_bar()
        self._apply_theme(self.dark_mode)
        self._refresh_welcome_recent()
        self._sync_ui_state()

    # ------------------------------------------------------------------
    # Config & Recent Files
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        try:
            p = get_config_path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self.dark_mode = bool(data.get("dark_mode", True))
                self.recent_files = [f for f in data.get("recent_files", []) if os.path.exists(f)][:10]
        except Exception:
            pass

    def _save_config(self) -> None:
        p = get_config_path()
        try:
            p.write_text(
                json.dumps({"dark_mode": self.dark_mode, "recent_files": self.recent_files[:10]}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _add_recent_file(self, path: str) -> None:
        if not path:
            return
        norm = str(Path(path).resolve())
        self.recent_files = [norm] + [f for f in self.recent_files if f.lower() != norm.lower()]
        self.recent_files = self.recent_files[:10]
        self._save_config()
        self._refresh_welcome_recent()

    # ------------------------------------------------------------------
    # Menus & Toolbars
    # ------------------------------------------------------------------
    def _icon_color(self) -> str:
        return "#DCE2EE" if self.dark_mode else "#2B3445"

    def _accent_color(self) -> str:
        return "#00C2FF" if self.dark_mode else "#0284C7"

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # File
        m_file = mb.addMenu("&File")
        m_file.addAction("Open PDF...", QKeySequence.StandardKey.Open, self.open_pdf_dialog)
        m_file.addAction("New Blank PDF...", QKeySequence.StandardKey.New, self.new_blank_pdf)
        m_file.addAction("Open Editable Project (.kinofill)...", self.open_project_file)
        m_file.addSeparator()
        m_file.addAction("Save PDF", QKeySequence.StandardKey.Save, self.save_current_pdf)
        m_file.addAction("Save PDF As...", QKeySequence("Ctrl+Shift+S"), self.save_current_pdf_as)
        m_file.addAction("Save Editable Project (.kinofill)...", self.save_project_file)
        m_file.addSeparator()
        m_file.addAction("Merge Multiple PDFs...", self.action_merge_pdfs)
        m_file.addAction("Split / Extract Pages...", self.action_split_pdf)
        m_file.addAction("Convert Images to PDF...", self.action_images_to_pdf)
        m_file.addAction("Export Pages to PNG/JPEG...", self.action_export_images)
        m_file.addSeparator()
        m_file.addAction("Print...", QKeySequence.StandardKey.Print, self.action_print)
        m_file.addAction("Document Properties...", self.action_metadata)
        m_file.addSeparator()
        m_file.addAction("Close Tab", QKeySequence("Ctrl+W"), self.close_current_tab)
        m_file.addAction("Exit", QKeySequence("Alt+F4"), self.close)

        # Edit
        m_edit = mb.addMenu("&Edit")
        self.act_undo = m_edit.addAction("Undo", QKeySequence.StandardKey.Undo, self.action_undo)
        self.act_redo = m_edit.addAction("Redo", QKeySequence.StandardKey.Redo, self.action_redo)
        m_edit.addSeparator()
        m_edit.addAction("Copy Object", QKeySequence.StandardKey.Copy, self.action_copy)
        m_edit.addAction("Paste Object", QKeySequence.StandardKey.Paste, self.action_paste)
        m_edit.addAction("Duplicate Object", QKeySequence("Ctrl+D"), self.action_duplicate)
        m_edit.addAction("Delete Selected", QKeySequence.StandardKey.Delete, self.action_delete)
        m_edit.addSeparator()
        m_edit.addAction("Find in Document...", QKeySequence.StandardKey.Find, self.show_find_bar)
        m_edit.addAction("Copy All Text on Current Page", self.action_copy_page_text)

        # Insert / Annotate
        m_ins = mb.addMenu("&Insert")
        m_ins.addAction("Edit All Existing Text (R)", lambda: self.set_tool("edit_text"))
        m_ins.addAction("Add New Text Box (T)", lambda: self.set_tool("text"))
        m_ins.addSeparator()
        m_ins.addAction("Checkmark ✓ (C)", lambda: self.set_tool("check"))
        m_ins.addAction("Cross ✕", lambda: self.set_tool("cross"))
        m_ins.addAction("Filled Dot •", lambda: self.set_tool("dot"))
        m_ins.addAction("Circle ○", lambda: self.set_tool("circle"))
        m_ins.addAction("Today's Date", lambda: self.set_tool("date"))
        m_ins.addSeparator()
        m_ins.addAction("Signature / Initials (S)...", self.open_signature_dialog)
        m_ins.addAction("Rubber Stamp...", self.open_stamp_dialog)
        m_ins.addAction("Insert Image (I)...", self.choose_image_to_place)
        m_ins.addAction("Sticky Note Comment", lambda: self.set_tool("note"))
        m_ins.addSeparator()
        m_ins.addAction("Highlight / Underline / Strike (H)", lambda: self.set_tool("highlight"))
        m_ins.addAction("Freehand Draw / Pen (P)", lambda: self.set_tool("pen"))
        m_ins.addAction("Shapes & Arrows", lambda: self.set_tool("shape"))
        m_ins.addAction("Erase / Whiteout (E)", lambda: self.set_tool("whiteout"))
        m_ins.addAction("Blackout / Redact (X)", lambda: self.set_tool("redact"))

        # Forms
        m_forms = mb.addMenu("F&orms")
        self.act_hl_forms = m_forms.addAction("Highlight Fillable Fields")
        self.act_hl_forms.setCheckable(True)
        self.act_hl_forms.setChecked(True)
        self.act_hl_forms.toggled.connect(self._toggle_highlight_forms)
        m_forms.addSeparator()
        m_forms.addAction("Add Fillable Text Field", lambda: self.set_tool("form_text"))
        m_forms.addAction("Add Fillable Checkbox", lambda: self.set_tool("form_check"))
        m_forms.addAction("Add Fillable Dropdown", lambda: self.set_tool("form_dropdown"))
        m_forms.addSeparator()
        m_forms.addAction("Clear All Form Values", self.action_clear_form_fields)
        m_forms.addAction("Flatten / Security Save Options...", self.action_security)

        # Pages
        m_pages = mb.addMenu("&Pages")
        m_pages.addAction("Rotate Page 90° Clockwise", lambda: self.mutate_current_page("rotate", angle=90))
        m_pages.addAction("Rotate Page 90° Counter-Clockwise", lambda: self.mutate_current_page("rotate", angle=-90))
        m_pages.addSeparator()
        m_pages.addAction("Insert Blank Page After Current", lambda: self.mutate_current_page("insert_blank"))
        m_pages.addAction("Insert Pages from Another PDF...", self.action_insert_pdf_pages)
        m_pages.addAction("Duplicate Current Page", lambda: self.mutate_current_page("duplicate"))
        m_pages.addAction("Move Current Page Up", lambda: self.move_current_page(-1))
        m_pages.addAction("Move Current Page Down", lambda: self.move_current_page(1))
        m_pages.addSeparator()
        m_pages.addAction("Delete Current Page", lambda: self.mutate_current_page("delete"))

        # Tools
        m_tools = mb.addMenu("&Tools")
        m_tools.addAction("Watermark...", self.action_watermark)
        m_tools.addAction("Headers, Footers & Page Numbers...", self.action_header_footer)
        m_tools.addAction("Security, Passwords & Redaction...", self.action_security)
        m_tools.addAction("Manage Saved Signatures...", self.open_signature_dialog)

        # View
        m_view = mb.addMenu("&View")
        m_view.addAction("Zoom In", QKeySequence.StandardKey.ZoomIn, lambda: self.step_zoom(1.15))
        m_view.addAction("Zoom Out", QKeySequence.StandardKey.ZoomOut, lambda: self.step_zoom(1.0 / 1.15))
        m_view.addAction("Actual Size (100%)", QKeySequence("Ctrl+0"), lambda: self.set_zoom_exact(1.0))
        m_view.addAction("Fit Width", self.action_fit_width)
        m_view.addAction("Fit Page", self.action_fit_page)
        m_view.addSeparator()
        self.act_toggle_sidebar = m_view.addAction("Show Left Sidebar")
        self.act_toggle_sidebar.setCheckable(True)
        self.act_toggle_sidebar.setChecked(True)
        self.act_toggle_sidebar.toggled.connect(lambda on: self.sidebar.setVisible(on))
        m_view.addAction("Toggle Dark / Light Theme", self.toggle_theme)

        # Help
        m_help = mb.addMenu("&Help")
        m_help.addAction("Keyboard Shortcuts & Tips", self.show_shortcuts_help)
        m_help.addAction(f"About {APP_NAME}", self.show_about)

    def _build_main_toolbar(self) -> None:
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(17, 17))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(self.toolbar)

        self.tb_open = self.toolbar.addAction("Open", self.open_pdf_dialog)
        self.tb_save = self.toolbar.addAction("Save", self.save_current_pdf)
        self.tb_print = self.toolbar.addAction("Print", self.action_print)
        self.toolbar.addSeparator()
        self.tb_undo = self.toolbar.addAction("Undo", self.action_undo)
        self.tb_redo = self.toolbar.addAction("Redo", self.action_redo)
        self.toolbar.addSeparator()

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        tools = [
            ("edit_text", "Edit Text", "Click ANY existing text on the page to edit & replace it directly (R)"),
            ("select", "Select", "Select, move, resize objects & fill forms (V)"),
            ("text", "Add Text", "Click anywhere to add a new text box (T)"),
            ("check", "Check", "Click to place a checkmark ✓ (C)"),
            ("cross", "Cross", "Click to place a cross ✕"),
            ("date", "Date", "Click to insert today's date"),
            ("sign", "Sign", "Draw, type, or upload signature & initials (S)"),
            ("highlight", "Highlight", "Highlight, underline, or strikethrough (H)"),
            ("pen", "Draw", "Freehand ink pen (P)"),
            ("whiteout", "Erase", "Whiteout / erase existing content (E)"),
            ("redact", "Redact", "Blackout & securely redact sensitive text (X)"),
            ("shape", "Shape", "Rectangle, circle, line, or arrow"),
            ("stamp", "Stamp", "Rubber stamps (APPROVED, CONFIDENTIAL, etc.)"),
            ("image", "Image", "Insert image or logo (I)"),
            ("note", "Note", "Add sticky note comment"),
        ]

        for key, label, tip in tools:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            if key == "sign":
                act.triggered.connect(self._on_sign_toolbar_clicked)
            elif key == "image":
                act.triggered.connect(self._on_image_toolbar_clicked)
            else:
                act.triggered.connect(lambda _=False, k=key: self.set_tool(k))
            self.tool_group.addAction(act)
            self.toolbar.addAction(act)
            self._tool_actions[key] = act

        # Form Builder dropdown toolbutton
        self.btn_forms_tb = QToolButton()
        self.btn_forms_tb.setText("Forms")
        self.btn_forms_tb.setToolTip("Add fillable AcroForm fields (Text, Checkbox, Dropdown)")
        self.btn_forms_tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.btn_forms_tb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        fm = QMenu(self)
        fm.addAction("Add Fillable Text Field", lambda: self.set_tool("form_text"))
        fm.addAction("Add Fillable Checkbox", lambda: self.set_tool("form_check"))
        fm.addAction("Add Fillable Dropdown", lambda: self.set_tool("form_dropdown"))
        fm.addSeparator()
        fm.addAction("Highlight Fillable Fields", lambda: self.act_hl_forms.toggle())
        self.btn_forms_tb.setMenu(fm)
        self.toolbar.addWidget(self.btn_forms_tb)

        self.toolbar.addSeparator()
        self.tb_search = self.toolbar.addAction("Find", self.show_find_bar)
        self.tb_lock = self.toolbar.addAction("Protect", self.action_security)
        self.tb_theme = self.toolbar.addAction("Theme", self.toggle_theme)

        self._tool_actions["edit_text"].setChecked(True)

    def _refresh_toolbar_icons(self) -> None:
        ic = self._icon_color()
        ac = self._accent_color()
        mapping = [
            (self.tb_open, "open"),
            (self.tb_save, "save"),
            (self.tb_print, "print"),
            (self.tb_undo, "undo"),
            (self.tb_redo, "redo"),
            (self.tb_search, "search"),
            (self.tb_lock, "lock"),
            (self.tb_theme, "theme"),
        ]
        for act, name in mapping:
            act.setIcon(make_icon(name, ic, accent_color=ac))
        self.btn_forms_tb.setIcon(make_icon("form", ic, accent_color=ac))
        for k, act in self._tool_actions.items():
            act.setIcon(make_icon(k, ic, accent_color=ac))

    def _build_context_bar(self) -> None:
        """Dynamic contextual properties bar directly beneath the main toolbar."""
        self.ctx_bar = QWidget()
        self.ctx_bar.setObjectName("ContextBar")
        self.ctx_bar.setFixedHeight(42)
        hl = QHBoxLayout(self.ctx_bar)
        hl.setContentsMargins(10, 4, 12, 4)
        hl.setSpacing(8)

        # KinoSuite Brand Pill (shared across KinoSuite apps)
        suite_logo = QLabel()
        suite_logo.setPixmap(make_app_pixmap(24))
        suite_badge = QLabel(f"{APP_NAME.upper()}  •  {SUITE_NAME}")
        suite_badge.setObjectName("SuiteBadge")
        hl.addWidget(suite_logo)
        hl.addWidget(suite_badge)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #2E3545;")
        hl.addWidget(sep)

        self.lbl_tool_badge = QLabel("Edit All Text")
        self.lbl_tool_badge.setObjectName("ToolBadge")
        hl.addWidget(self.lbl_tool_badge)

        self.chk_show_text_boxes = QCheckBox("Show text boxes")
        self.chk_show_text_boxes.setChecked(True)
        self.chk_show_text_boxes.setToolTip("Show subtle dotted outlines around all editable text on the page")
        self.chk_show_text_boxes.toggled.connect(self._toggle_show_text_boxes)
        hl.addWidget(self.chk_show_text_boxes)

        # Text controls
        self.w_text_controls = QWidget()
        tl = QHBoxLayout(self.w_text_controls)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        self.cmb_font = QComboBox()
        self.cmb_font.addItems(get_available_fonts())
        self.cmb_font.setCurrentText(self.settings.font_family)
        self.cmb_font.currentTextChanged.connect(self._on_ctx_font_changed)
        tl.addWidget(self.cmb_font)

        self.spn_font_size = QDoubleSpinBox()
        self.spn_font_size.setRange(6.0, 96.0)
        self.spn_font_size.setDecimals(1)
        self.spn_font_size.setValue(self.settings.font_size)
        self.spn_font_size.setFixedWidth(68)
        self.spn_font_size.valueChanged.connect(self._on_ctx_font_size_changed)
        tl.addWidget(self.spn_font_size)

        self.btn_bold = QToolButton()
        self.btn_bold.setObjectName("FormatBtn")
        self.btn_bold.setText("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setStyleSheet("font-weight: 800;")
        self.btn_bold.toggled.connect(self._on_ctx_bold_toggled)
        tl.addWidget(self.btn_bold)

        self.btn_italic = QToolButton()
        self.btn_italic.setObjectName("FormatBtn")
        self.btn_italic.setText("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setStyleSheet("font-style: italic; font-weight: 600;")
        self.btn_italic.toggled.connect(self._on_ctx_italic_toggled)
        tl.addWidget(self.btn_italic)

        tl.addWidget(QLabel("Color:"))
        self.btn_text_color = QPushButton()
        self.btn_text_color.setStyleSheet(_swatch_style(self.settings.text_color))
        self.btn_text_color.clicked.connect(self._pick_text_color)
        tl.addWidget(self.btn_text_color)

        tl.addWidget(QLabel("Bg:"))
        self.btn_text_bg = QPushButton()
        self.btn_text_bg.setToolTip("Text background box color (click to set, right-click or Clear to make transparent)")
        self.btn_text_bg.setStyleSheet(_swatch_style(self.settings.text_bg_color))
        self.btn_text_bg.clicked.connect(self._pick_text_bg_color)
        tl.addWidget(self.btn_text_bg)

        btn_clear_bg = QPushButton("Clear Bg")
        btn_clear_bg.setStyleSheet("padding: 3px 7px; font-size: 8pt;")
        btn_clear_bg.clicked.connect(self._clear_text_bg_color)
        tl.addWidget(btn_clear_bg)
        hl.addWidget(self.w_text_controls)

        # Highlight controls
        self.w_hl_controls = QWidget()
        hll = QHBoxLayout(self.w_hl_controls)
        hll.setContentsMargins(0, 0, 0, 0)
        hll.setSpacing(6)
        self.cmb_hl_style = QComboBox()
        self.cmb_hl_style.addItems(["Highlight", "Underline", "Strikeout"])
        self.cmb_hl_style.currentTextChanged.connect(lambda t: self._on_ctx_hl_style(t.lower()))
        hll.addWidget(self.cmb_hl_style)
        for name, hx in [("Yellow", "#FDE047"), ("Green", "#86EFAC"), ("Cyan", "#67E8F9"), ("Pink", "#F9A8D4"), ("Red", "#EF4444")]:
            b = QPushButton()
            b.setToolTip(name)
            b.setStyleSheet(_swatch_style(hx))
            b.clicked.connect(lambda _=False, c=hx: self._set_hl_color(c))
            hll.addWidget(b)
        hl.addWidget(self.w_hl_controls)

        # Shape / Pen controls
        self.w_draw_controls = QWidget()
        dl = QHBoxLayout(self.w_draw_controls)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems(["Rectangle", "Rounded Rect", "Ellipse", "Line", "Arrow"])
        self.cmb_shape.currentIndexChanged.connect(self._on_ctx_shape_changed)
        dl.addWidget(self.cmb_shape)

        dl.addWidget(QLabel("Stroke:"))
        self.btn_stroke_color = QPushButton()
        self.btn_stroke_color.setStyleSheet(_swatch_style(self.settings.stroke_color))
        self.btn_stroke_color.clicked.connect(self._pick_stroke_color)
        dl.addWidget(self.btn_stroke_color)

        self.lbl_fill = QLabel("Fill:")
        dl.addWidget(self.lbl_fill)
        self.btn_fill_color = QPushButton()
        self.btn_fill_color.setStyleSheet(_swatch_style(self.settings.fill_color))
        self.btn_fill_color.clicked.connect(self._pick_fill_color)
        dl.addWidget(self.btn_fill_color)

        self.btn_clear_fill = QPushButton("No Fill")
        self.btn_clear_fill.setStyleSheet("padding: 3px 7px; font-size: 8pt;")
        self.btn_clear_fill.clicked.connect(self._clear_fill_color)
        dl.addWidget(self.btn_clear_fill)

        dl.addWidget(QLabel("Width:"))
        self.spn_stroke_w = QDoubleSpinBox()
        self.spn_stroke_w.setRange(0.5, 24.0)
        self.spn_stroke_w.setValue(self.settings.stroke_width)
        self.spn_stroke_w.setFixedWidth(62)
        self.spn_stroke_w.valueChanged.connect(self._on_ctx_stroke_w_changed)
        dl.addWidget(self.spn_stroke_w)
        hl.addWidget(self.w_draw_controls)

        # Whiteout controls
        self.w_whiteout_controls = QWidget()
        wl = QHBoxLayout(self.w_whiteout_controls)
        wl.setContentsMargins(0, 0, 0, 0)
        self.chk_auto_bg = QCheckBox("Auto-match page background color")
        self.chk_auto_bg.setChecked(True)
        self.chk_auto_bg.toggled.connect(lambda v: setattr(self.settings, "whiteout_auto_sample", v))
        wl.addWidget(self.chk_auto_bg)
        self.btn_wo_color = QPushButton()
        self.btn_wo_color.setStyleSheet(_swatch_style(self.settings.whiteout_color))
        self.btn_wo_color.clicked.connect(self._pick_whiteout_color)
        wl.addWidget(self.btn_wo_color)
        hl.addWidget(self.w_whiteout_controls)

        # Stamp / Date / Mark controls
        self.w_stamp_controls = QWidget()
        sl = QHBoxLayout(self.w_stamp_controls)
        sl.setContentsMargins(0, 0, 0, 0)
        self.cmb_stamp_preset = QComboBox()
        for t, _ in CustomStampDialog.PRESETS:
            self.cmb_stamp_preset.addItem(t)
        self.cmb_stamp_preset.currentIndexChanged.connect(self._on_stamp_preset_changed)
        sl.addWidget(self.cmb_stamp_preset)
        btn_cust_stamp = QPushButton("Customize Stamp...")
        btn_cust_stamp.setStyleSheet("padding: 3px 9px;")
        btn_cust_stamp.clicked.connect(self.open_stamp_dialog)
        sl.addWidget(btn_cust_stamp)
        hl.addWidget(self.w_stamp_controls)

        self.w_date_controls = QWidget()
        dtl = QHBoxLayout(self.w_date_controls)
        dtl.setContentsMargins(0, 0, 0, 0)
        dtl.addWidget(QLabel("Date Format:"))
        self.cmb_date_fmt = QComboBox()
        self.cmb_date_fmt.addItems(["%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"])
        self.cmb_date_fmt.currentTextChanged.connect(lambda f: setattr(self.settings, "date_format", f))
        dtl.addWidget(self.cmb_date_fmt)
        hl.addWidget(self.w_date_controls)

        # Quick action hint / selected item delete
        hl.addStretch()
        self.btn_ctx_sig = QPushButton("Signature Vault...")
        self.btn_ctx_sig.setStyleSheet("padding: 3px 10px;")
        self.btn_ctx_sig.clicked.connect(self.open_signature_dialog)
        hl.addWidget(self.btn_ctx_sig)

        self.btn_ctx_del = QPushButton("Delete Selected")
        self.btn_ctx_del.setObjectName("DangerButton")
        self.btn_ctx_del.setStyleSheet("padding: 3px 10px;")
        self.btn_ctx_del.clicked.connect(self.action_delete)
        self.btn_ctx_del.hide()
        hl.addWidget(self.btn_ctx_del)

    def _build_central_workspace(self) -> None:
        central = QWidget()
        main_v = QVBoxLayout(central)
        main_v.setContentsMargins(0, 0, 0, 0)
        main_v.setSpacing(0)

        main_v.addWidget(self.ctx_bar)

        # Inline Find bar (hidden by default)
        self.find_bar = QWidget()
        self.find_bar.setObjectName("FindBar")
        fl = QHBoxLayout(self.find_bar)
        fl.setContentsMargins(12, 5, 12, 5)
        fl.addWidget(QLabel("Find:"))
        self.txt_find = QLineEdit()
        self.txt_find.setPlaceholderText("Search text in PDF...")
        self.txt_find.setFixedWidth(260)
        self.txt_find.textChanged.connect(self._on_find_text_changed)
        self.txt_find.returnPressed.connect(lambda: self._step_find(1))
        fl.addWidget(self.txt_find)
        self.lbl_find_count = QLabel("0 matches")
        fl.addWidget(self.lbl_find_count)
        b_prev = QPushButton("Prev")
        b_prev.clicked.connect(lambda: self._step_find(-1))
        b_next = QPushButton("Next")
        b_next.clicked.connect(lambda: self._step_find(1))
        b_close = QPushButton("✕")
        b_close.setFixedWidth(30)
        b_close.clicked.connect(self.hide_find_bar)
        fl.addWidget(b_prev)
        fl.addWidget(b_next)
        fl.addWidget(b_close)
        fl.addStretch()
        self.find_bar.hide()
        main_v.addWidget(self.find_bar)

        # Stacked: 0 = Welcome Home, 1 = Editor Splitter
        self.stack = QStackedWidget()
        main_v.addWidget(self.stack, 1)

        # Page 0: Welcome View
        self.welcome_widget = self._build_welcome_screen()
        self.stack.addWidget(self.welcome_widget)

        # Page 1: Sidebar + Tabs Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.sidebar = self._build_sidebar()
        self.splitter.addWidget(self.sidebar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("DocTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setAutoFillBackground(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([240, 1140])

        self.stack.addWidget(self.splitter)
        self.setCentralWidget(central)

    def _build_welcome_screen(self) -> QWidget:
        w = QWidget()
        w.setObjectName("WelcomeBackdrop")
        outer = QVBoxLayout(w)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QWidget()
        card.setObjectName("WelcomeCard")
        card.setFixedWidth(760)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(36, 32, 36, 30)
        cl.setSpacing(16)

        # KinoSuite Brand Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(make_app_pixmap(54))
        brand_row.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel(APP_NAME.upper())
        title.setObjectName("WelcomeTitle")
        suite_tag = QLabel("KINOSUITE PDF STUDIO  •  EDIT, FILL, SIGN & REDACT")
        suite_tag.setObjectName("WelcomeSuiteTag")
        title_col.addWidget(title)
        title_col.addWidget(suite_tag)
        brand_row.addLayout(title_col, 1)
        cl.addLayout(brand_row)

        sub = QLabel(
            "Local, private, and 100% free Windows PDF studio in the KinoSuite workspace — "
            "edit native PDF text in place, fill & build AcroForms, sign, redact, annotate, merge & protect."
        )
        sub.setObjectName("WelcomeSubtitle")
        sub.setWordWrap(True)
        cl.addWidget(sub)

        # Feature chips strip
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        for chip_txt in ("Edit PDF Text", "AcroForms", "Signatures Vault", "True Redaction", "100% Local"):
            chip = QLabel(chip_txt)
            chip.setObjectName("WelcomeChip")
            chip.setFixedHeight(26)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            chips_row.addWidget(chip)
        chips_row.addStretch()
        cl.addLayout(chips_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        b_open = QPushButton("Open PDF File...")
        b_open.setObjectName("PrimaryButton")
        b_open.setMinimumHeight(42)
        b_open.clicked.connect(self.open_pdf_dialog)

        b_new = QPushButton("New Blank PDF")
        b_new.setMinimumHeight(42)
        b_new.clicked.connect(self.new_blank_pdf)

        b_merge = QPushButton("Merge PDFs")
        b_merge.setMinimumHeight(42)
        b_merge.clicked.connect(self.action_merge_pdfs)

        b_img = QPushButton("Images to PDF")
        b_img.setMinimumHeight(42)
        b_img.clicked.connect(self.action_images_to_pdf)

        for b in (b_open, b_new, b_merge, b_img):
            btn_row.addWidget(b)
        cl.addLayout(btn_row)

        drop_hint = QLabel("Drag & drop any .pdf, .kinofill project, or image directly into this window.")
        drop_hint.setObjectName("DropHint")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(drop_hint)

        lbl_recent = QLabel("Recent Files")
        lbl_recent.setObjectName("SectionHeader")
        cl.addWidget(lbl_recent)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(165)
        self.recent_list.itemDoubleClicked.connect(lambda it: self.open_pdf(it.data(Qt.ItemDataRole.UserRole)))
        cl.addWidget(self.recent_list)

        outer.addWidget(card)
        return w

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("SidebarPanel")
        panel.setMinimumWidth(210)
        panel.setMaximumWidth(340)
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(6, 6, 6, 6)

        self.side_tabs = QTabWidget()
        self.side_tabs.setObjectName("SidebarTabs")
        vl.addWidget(self.side_tabs, 1)

        # Tab 1: Pages Thumbnails
        pages_w = QWidget()
        pl = QVBoxLayout(pages_w)
        pl.setContentsMargins(2, 4, 2, 2)
        pl.setSpacing(6)

        pbtns = QHBoxLayout()
        pbtns.setSpacing(3)
        for txt, tip, cb in [
            ("CW", "Rotate 90° Clockwise", lambda: self.mutate_current_page("rotate", angle=90)),
            ("CCW", "Rotate 90° Counter-Clockwise", lambda: self.mutate_current_page("rotate", angle=-90)),
            ("+", "Insert Blank Page", lambda: self.mutate_current_page("insert_blank")),
            ("Dup", "Duplicate Page", lambda: self.mutate_current_page("duplicate")),
            ("↑", "Move Page Up", lambda: self.move_current_page(-1)),
            ("↓", "Move Page Down", lambda: self.move_current_page(1)),
            ("Del", "Delete Page", lambda: self.mutate_current_page("delete")),
        ]:
            b = QPushButton(txt)
            b.setObjectName("CompactBtn")
            b.setToolTip(tip)
            b.setFixedHeight(24)
            b.clicked.connect(cb)
            pbtns.addWidget(b)
        pl.addLayout(pbtns)

        self.thumb_list = QListWidget()
        self.thumb_list.setIconSize(QSize(140, 180))
        self.thumb_list.setSpacing(4)
        self.thumb_list.currentRowChanged.connect(self._on_thumb_clicked)
        self.thumb_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumb_list.customContextMenuRequested.connect(self._show_thumb_context_menu)
        pl.addWidget(self.thumb_list, 1)
        self.side_tabs.addTab(pages_w, "Pages")

        # Tab 2: Fillable Forms
        forms_w = QWidget()
        fl = QVBoxLayout(forms_w)
        fl.setContentsMargins(2, 4, 2, 2)
        self.lbl_forms_summary = QLabel("No fillable fields detected.")
        self.lbl_forms_summary.setObjectName("MutedHint")
        self.lbl_forms_summary.setWordWrap(True)
        fl.addWidget(self.lbl_forms_summary)
        self.forms_list = QListWidget()
        self.forms_list.itemClicked.connect(self._on_form_list_clicked)
        fl.addWidget(self.forms_list, 1)
        self.side_tabs.addTab(forms_w, "Forms")

        # Tab 3: Page Objects / Annotations
        obj_w = QWidget()
        ol = QVBoxLayout(obj_w)
        ol.setContentsMargins(2, 4, 2, 2)
        self.objects_list = QListWidget()
        self.objects_list.itemClicked.connect(self._on_object_list_clicked)
        ol.addWidget(self.objects_list, 1)
        b_del_obj = QPushButton("Delete Selected Object")
        b_del_obj.clicked.connect(self.action_delete)
        ol.addWidget(b_del_obj)
        self.side_tabs.addTab(obj_w, "Objects")

        return panel

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self.lbl_status_hint = QLabel("Ready — Open a PDF or drag & drop a file to start editing.")
        sb.addWidget(self.lbl_status_hint, 1)

        # Page navigation
        nav = QWidget()
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(0, 0, 8, 0)
        nl.setSpacing(4)
        b_prev = QPushButton("<")
        b_prev.setObjectName("CompactBtn")
        b_prev.setToolTip("Previous Page")
        b_prev.setFixedSize(26, 24)
        b_prev.clicked.connect(lambda: self._step_page(-1))
        self.spn_page = QSpinBox()
        self.spn_page.setMinimum(1)
        self.spn_page.setFixedWidth(54)
        self.spn_page.valueChanged.connect(self._on_page_spin_changed)
        self.lbl_page_total = QLabel("/ 0")
        b_next = QPushButton(">")
        b_next.setObjectName("CompactBtn")
        b_next.setToolTip("Next Page")
        b_next.setFixedSize(26, 24)
        b_next.clicked.connect(lambda: self._step_page(1))
        for w in (b_prev, self.spn_page, self.lbl_page_total, b_next):
            nl.addWidget(w)
        sb.addPermanentWidget(nav)

        # Zoom controls
        zw = QWidget()
        zl = QHBoxLayout(zw)
        zl.setContentsMargins(4, 0, 6, 0)
        zl.setSpacing(4)
        b_zout = QPushButton("-")
        b_zout.setObjectName("CompactBtn")
        b_zout.setToolTip("Zoom Out")
        b_zout.setFixedSize(24, 24)
        b_zout.clicked.connect(lambda: self.step_zoom(1.0 / 1.15))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setValue(115)
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.valueChanged.connect(lambda v: self.set_zoom_exact(v / 100.0))
        b_zin = QPushButton("+")
        b_zin.setObjectName("CompactBtn")
        b_zin.setToolTip("Zoom In")
        b_zin.setFixedSize(24, 24)
        b_zin.clicked.connect(lambda: self.step_zoom(1.15))
        self.cmb_zoom = QComboBox()
        self.cmb_zoom.setEditable(True)
        self.cmb_zoom.addItems(["50%", "75%", "100%", "115%", "125%", "150%", "200%", "Fit Width", "Fit Page"])
        self.cmb_zoom.setCurrentText("115%")
        self.cmb_zoom.setFixedWidth(92)
        self.cmb_zoom.activated.connect(self._on_zoom_combo_activated)
        for w in (b_zout, self.zoom_slider, b_zin, self.cmb_zoom):
            zl.addWidget(w)
        sb.addPermanentWidget(zw)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _apply_theme(self, dark: bool) -> None:
        self.dark_mode = dark
        QApplication.instance().setStyleSheet(KINOSUITE_DARK_THEME if dark else KINOSUITE_LIGHT_THEME)
        self._refresh_toolbar_icons()
        self._save_config()

    def toggle_theme(self) -> None:
        self._apply_theme(not self.dark_mode)

    # ------------------------------------------------------------------
    # Active Tab Helpers
    # ------------------------------------------------------------------
    def current_tab(self) -> Optional[DocumentTab]:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocumentTab) else None

    def current_view(self) -> Optional[PdfDocumentView]:
        t = self.current_tab()
        return t.view if t else None

    def _refresh_welcome_recent(self) -> None:
        self.recent_list.clear()
        for f in self.recent_files:
            it = QListWidgetItem(f"{Path(f).name}   —   {f}")
            it.setData(Qt.ItemDataRole.UserRole, f)
            self.recent_list.addItem(it)

    def _update_tab_title(self, tab: DocumentTab) -> None:
        idx = self.tabs.indexOf(tab)
        if idx < 0:
            return
        name = Path(tab.state.source_path).name if tab.state.source_path else "Untitled.pdf"
        if tab.state.dirty:
            name = f"* {name}"
        self.tabs.setTabText(idx, name)
        self.tabs.setTabToolTip(idx, tab.state.source_path or "Unsaved document")

    def _sync_ui_state(self) -> None:
        tab = self.current_tab()
        has_doc = tab is not None
        self.stack.setCurrentIndex(1 if has_doc else 0)
        self.tb_save.setEnabled(has_doc)
        self.tb_print.setEnabled(has_doc)
        self.tb_search.setEnabled(has_doc)
        self.tb_lock.setEnabled(has_doc)
        self.tb_undo.setEnabled(has_doc and tab.state.can_undo())
        self.tb_redo.setEnabled(has_doc and tab.state.can_redo())
        self.act_undo.setEnabled(has_doc and tab.state.can_undo())
        self.act_redo.setEnabled(has_doc and tab.state.can_redo())

        if has_doc:
            self._update_tab_title(tab)
            pc = tab.view.page_count()
            self.spn_page.blockSignals(True)
            self.spn_page.setMaximum(max(1, pc))
            self.spn_page.setValue(tab.view.current_page + 1)
            self.spn_page.blockSignals(False)
            self.lbl_page_total.setText(f"/ {pc}")
            pct = int(round(tab.view.zoom * 100))
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(pct)
            self.zoom_slider.blockSignals(False)
            self.cmb_zoom.setCurrentText(f"{pct}%")
            self.setWindowTitle(f"{Path(tab.state.source_path).name if tab.state.source_path else 'Untitled.pdf'} — {APP_NAME} · {SUITE_NAME}")
        else:
            self.lbl_page_total.setText("/ 0")
            self.setWindowTitle(f"{APP_NAME} — {APP_SUBTITLE}")
        self._update_context_bar_visibility()

    def _on_tab_changed(self, _idx: int) -> None:
        self._sync_ui_state()
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    # Opening, Creating & Saving PDFs
    # ------------------------------------------------------------------
    def open_pdf_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Open PDF or Editable Project", "", "PDF & KinoFill Files (*.pdf *.kinofill *.freefill *.lfill);;PDF Files (*.pdf);;All Files (*.*)"
        )
        for f in files:
            if f.lower().endswith((".kinofill", ".freefill", ".lfill")):
                self.open_project_file(f)
            else:
                self.open_pdf(f)

    def open_pdf(self, path: str, display_source_path: Optional[str] = None) -> Optional[DocumentTab]:
        if not path or not os.path.exists(path):
            return None

        password = ""
        try:
            reader = open_reader(path, "")
        except ValueError:
            pw, ok = QInputDialog.getText(
                self, "Password Required", f"'{Path(path).name}' is encrypted.\nEnter password:", QLineEdit.EchoMode.Password
            )
            if not ok:
                return None
            try:
                reader = open_reader(path, pw)
                password = pw
            except Exception as exc:
                QMessageBox.critical(self, "Incorrect Password", f"Could not unlock PDF:\n{exc}")
                return None
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", f"Could not open PDF:\n{exc}")
            return None

        # Copy to working temp file so saving over original never conflicts with QPdfDocument lock!
        fd, work_path = tempfile.mkstemp(prefix="kinofill_work_", suffix=".pdf")
        os.close(fd)
        shutil.copy2(path, work_path)

        src = path if display_source_path is None else display_source_path
        state = DocumentState(source_path=src, working_pdf_path=work_path)
        state.password = password
        state.metadata = read_pdf_metadata(work_path, password)

        # Extract interactive AcroForm fields
        acro_fields = extract_acroform_fields(work_path, password)
        state.items.extend(acro_fields)

        tab = DocumentTab(state, self.settings, self)
        if not tab.view.load_working_pdf():
            tab.cleanup_temps()
            QMessageBox.critical(self, "Render Error", "PDFium failed to load this PDF file.")
            return None

        self._connect_tab_signals(tab)
        title = Path(src).name if src else "Untitled.pdf"
        idx = self.tabs.addTab(tab, title)
        self.tabs.setCurrentIndex(idx)
        if src:
            self._add_recent_file(src)

        self._refresh_sidebar()
        self._sync_ui_state()
        total_blocks = sum(len(b) for b in tab.state.text_blocks.values())
        msg = f"Loaded {tab.view.page_count()} page(s) — {total_blocks} editable text block(s) ready (click any text to edit)."
        if acro_fields:
            msg += f" {len(acro_fields)} fillable form field(s) detected."
        self.lbl_status_hint.setText(msg)
        return tab

    def _connect_tab_signals(self, tab: DocumentTab) -> None:
        v = tab.view
        v.currentPageChanged.connect(lambda p: self._on_view_page_changed(tab, p))
        v.zoomChanged.connect(lambda _z: self._sync_ui_state())
        v.selectionChanged.connect(self._on_selection_changed)
        v.itemsChanged.connect(lambda: (self._sync_ui_state(), self._refresh_forms_and_objects()))
        v.requestToolChange.connect(self.set_tool)
        v.toolFinishedAutoSelect.connect(lambda: self.set_tool("select"))
        v.signatureRequested.connect(self._on_canvas_signature_requested)
        v.imageRequested.connect(self._on_canvas_image_requested)

    def new_blank_pdf(self) -> None:
        dlg = NewBlankPdfDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        w, h, count = dlg.get_params()
        fd, tmp = tempfile.mkstemp(prefix="kinofill_blank_", suffix=".pdf")
        os.close(fd)
        create_blank_pdf(tmp, w, h, count)
        tab = self.open_pdf(tmp, display_source_path="")
        try:
            os.remove(tmp)
        except OSError:
            pass
        if tab:
            tab.state.dirty = True
            self._sync_ui_state()

    def save_current_pdf(self) -> bool:
        tab = self.current_tab()
        if not tab:
            return False
        if not tab.state.source_path:
            return self.save_current_pdf_as()
        return self._perform_save(tab, tab.state.source_path)

    def save_current_pdf_as(self) -> bool:
        tab = self.current_tab()
        if not tab:
            return False
        default = tab.state.source_path or str(Path.home() / "Documents" / "edited.pdf")
        out_path, _ = QFileDialog.getSaveFileName(self, "Save PDF As", default, "PDF Files (*.pdf)")
        if not out_path:
            return False
        if not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"
        if self._perform_save(tab, out_path):
            tab.state.source_path = out_path
            self._add_recent_file(out_path)
            self._sync_ui_state()
            return True
        return False

    def _perform_save(self, tab: DocumentTab, output_path: str) -> bool:
        tab.view.close_all_inline_editors()
        try:
            save_edited_pdf(tab.state, output_path)
            tab.state.dirty = False
            self._sync_ui_state()
            self.lbl_status_hint.setText(f"Saved successfully to {output_path}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not save PDF:\n{exc}")
            return False

    def save_project_file(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        if not tab.state.source_path:
            QMessageBox.information(self, "Save PDF First", "Please save the base PDF first before saving an editable .kinofill project.")
            return
        default = str(Path(tab.state.source_path).with_suffix(".kinofill"))
        path, _ = QFileDialog.getSaveFileName(self, "Save Editable Project", default, "KinoFill Project (*.kinofill)")
        if not path:
            return
        Path(path).write_text(tab.state.to_project_json(), encoding="utf-8")
        self.lbl_status_hint.setText(f"Saved editable project to {path}")

    def open_project_file(self, path: Optional[str] = None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Editable Project", "", "KinoFill Project (*.kinofill *.freefill *.lfill)")
        if not path or not os.path.exists(path):
            return
        try:
            raw = Path(path).read_text(encoding="utf-8")
            data = json.loads(raw)
            src_pdf = data.get("source_path", "")
            if not src_pdf or not os.path.exists(src_pdf):
                src_pdf, _ = QFileDialog.getOpenFileName(self, "Locate Base PDF for Project", "", "PDF Files (*.pdf)")
                if not src_pdf:
                    return
            tab = self.open_pdf(src_pdf)
            if tab:
                tab.state.load_project_json(raw)
                tab.view.refresh_all_pages()
                self._refresh_forms_and_objects()
                self._sync_ui_state()
                self.lbl_status_hint.setText(f"Loaded editable project: {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Open Project Failed", str(exc))

    def close_current_tab(self) -> None:
        idx = self.tabs.currentIndex()
        if idx >= 0:
            self.close_tab(idx)

    def close_tab(self, idx: int) -> bool:
        w = self.tabs.widget(idx)
        if isinstance(w, DocumentTab):
            w.view.close_all_inline_editors()
            if w.state.dirty:
                name = Path(w.state.source_path).name if w.state.source_path else "Untitled.pdf"
                res = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    f"Save changes to '{name}' before closing?",
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                )
                if res == QMessageBox.StandardButton.Cancel:
                    return False
                if res == QMessageBox.StandardButton.Save:
                    self.tabs.setCurrentIndex(idx)
                    if not self.save_current_pdf():
                        return False
            w.cleanup_temps()
        self.tabs.removeTab(idx)
        self._sync_ui_state()
        self._refresh_sidebar()
        return True

    def closeEvent(self, event) -> None:
        while self.tabs.count() > 0:
            if not self.close_tab(0):
                event.ignore()
                return
        event.accept()

    # ------------------------------------------------------------------
    # Tool Switching & Contextual Properties Bar
    # ------------------------------------------------------------------
    def set_tool(self, tool_key: str) -> None:
        self.settings.tool = tool_key
        if tool_key in self._tool_actions:
            self._tool_actions[tool_key].setChecked(True)
        else:
            for act in self._tool_actions.values():
                act.setChecked(False)

        v = self.current_view()
        if v:
            v.close_all_inline_editors()
            if tool_key != "select":
                v.select_item(None)

        names = {
            "edit_text": "Edit All Text",
            "select": "Select & Move",
            "text": "Add Text",
            "check": "Checkmark ✓",
            "cross": "Cross ✕",
            "dot": "Dot •",
            "circle": "Circle ○",
            "date": "Date Stamp",
            "sign": "Place Signature",
            "highlight": "Highlight / Markup",
            "pen": "Freehand Draw",
            "whiteout": "Erase / Whiteout",
            "redact": "Blackout Redact",
            "shape": "Shapes & Arrows",
            "stamp": "Rubber Stamp",
            "image": "Insert Image",
            "note": "Sticky Note",
            "form_text": "Add Fillable Text Field",
            "form_check": "Add Fillable Checkbox",
            "form_dropdown": "Add Fillable Dropdown",
        }
        self.lbl_tool_badge.setText(names.get(tool_key, tool_key))
        hints = {
            "edit_text": "All text on the page is live! Click ANY text to alter it in place, click blue form fields to fill, or double-click empty space to add text.",
            "select": "Click objects to move/resize, double-click any text to edit, or click blue form fields to fill.",
            "text": "Click anywhere on the page to add a new text box. Press Ctrl+Enter or click outside to finish.",
            "check": "Click anywhere on a form checkbox to stamp a crisp checkmark ✓.",
            "sign": "Click on the page to place your signature (or click 'Signature Vault...' to create/switch).",
            "whiteout": "Drag a box over content to whiteout. Auto-match blends seamlessly with paper color.",
            "redact": "Drag a box over sensitive info. Enable True Redaction in Protect to permanently destroy text.",
            "form_text": "Drag on the page to create a new fillable PDF text field.",
            "form_check": "Click or drag on the page to create a new fillable PDF checkbox.",
            "form_dropdown": "Drag on the page to create a new fillable PDF dropdown menu.",
        }
        if tool_key in hints:
            self.lbl_status_hint.setText(hints[tool_key])
        self._update_context_bar_visibility()
        if v:
            v.refresh_all_pages()

    def _toggle_show_text_boxes(self, on: bool) -> None:
        self.settings.show_text_boxes = on
        v = self.current_view()
        if v:
            v.refresh_all_pages()

    def _update_context_bar_visibility(self) -> None:
        t = self.settings.tool
        v = self.current_view()
        sel = v.state.find_item(v.selected_item_id) if (v and v.selected_item_id) else None

        self.chk_show_text_boxes.setVisible(t == "edit_text")
        show_text = t in ("edit_text", "text") or isinstance(sel, TextItem)
        show_hl = t == "highlight" or isinstance(sel, HighlightItem)
        show_draw = t in ("pen", "shape") or isinstance(sel, (InkItem, ShapeItem))
        show_wo = t == "whiteout" or isinstance(sel, WhiteoutItem)
        show_stamp = t == "stamp" or (isinstance(sel, StampItem) and sel.stamp_type == "rubber")
        show_date = t == "date"

        self.w_text_controls.setVisible(show_text)
        self.w_hl_controls.setVisible(show_hl)
        self.w_draw_controls.setVisible(show_draw)
        self.cmb_shape.setVisible(t == "shape" or isinstance(sel, ShapeItem))
        show_fill = (t == "shape" and self.settings.shape_type not in ("line", "arrow")) or (
            isinstance(sel, ShapeItem) and sel.shape_type not in ("line", "arrow")
        )
        self.lbl_fill.setVisible(show_fill)
        self.btn_fill_color.setVisible(show_fill)
        self.btn_clear_fill.setVisible(show_fill)
        self.w_whiteout_controls.setVisible(show_wo)
        self.w_stamp_controls.setVisible(show_stamp)
        self.w_date_controls.setVisible(show_date)
        self.btn_ctx_del.setVisible(sel is not None)

    def _on_selection_changed(self, item: Optional[BaseItem]) -> None:
        self._updating_ctx_ui = True
        try:
            if isinstance(item, TextItem):
                self.cmb_font.setCurrentText(item.font_family)
                self.spn_font_size.setValue(item.font_size)
                self.btn_bold.setChecked(item.bold)
                self.btn_italic.setChecked(item.italic)
                self.btn_text_color.setStyleSheet(_swatch_style(item.color))
                self.btn_text_bg.setStyleSheet(_swatch_style(item.bg_color))
            elif isinstance(item, ShapeItem):
                self.btn_stroke_color.setStyleSheet(_swatch_style(item.stroke_color))
                self.btn_fill_color.setStyleSheet(_swatch_style(item.fill_color))
                self.spn_stroke_w.setValue(item.stroke_width)
            elif isinstance(item, InkItem):
                self.btn_stroke_color.setStyleSheet(_swatch_style(item.color))
                self.spn_stroke_w.setValue(item.stroke_width)
        finally:
            self._updating_ctx_ui = False
        self._update_context_bar_visibility()

    def _selected_item(self) -> Optional[BaseItem]:
        v = self.current_view()
        if v and v.selected_item_id:
            return v.state.find_item(v.selected_item_id)
        return None

    def _mutate_selected_and_refresh(self, fn) -> None:
        v = self.current_view()
        sel = self._selected_item()
        if v and sel is not None:
            v.state.push_undo()
            fn(sel)
            v.refresh_all_pages()
            self._sync_ui_state()

    def _on_ctx_font_changed(self, family: str) -> None:
        if self._updating_ctx_ui:
            return
        self.settings.font_family = family
        if isinstance(self._selected_item(), TextItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "font_family", family))

    def _on_ctx_font_size_changed(self, val: float) -> None:
        if self._updating_ctx_ui:
            return
        self.settings.font_size = val
        if isinstance(self._selected_item(), TextItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "font_size", val))

    def _on_ctx_bold_toggled(self, on: bool) -> None:
        if self._updating_ctx_ui:
            return
        self.settings.bold = on
        if isinstance(self._selected_item(), TextItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "bold", on))

    def _on_ctx_italic_toggled(self, on: bool) -> None:
        if self._updating_ctx_ui:
            return
        self.settings.italic = on
        if isinstance(self._selected_item(), TextItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "italic", on))

    def _pick_text_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.settings.text_color), self, "Text Color")
        if col.isValid():
            hx = col.name()
            self.settings.text_color = hx
            self.settings.check_color = hx
            self.btn_text_color.setStyleSheet(_swatch_style(hx))
            sel = self._selected_item()
            if isinstance(sel, (TextItem, StampItem)):
                self._mutate_selected_and_refresh(lambda s: setattr(s, "color", hx))

    def _pick_text_bg_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.settings.text_bg_color or "#FFFFFF"), self, "Text Background Color")
        if col.isValid():
            hx = col.name()
            self.settings.text_bg_color = hx
            self.btn_text_bg.setStyleSheet(_swatch_style(hx))
            if isinstance(self._selected_item(), TextItem):
                self._mutate_selected_and_refresh(lambda s: setattr(s, "bg_color", hx))

    def _clear_text_bg_color(self) -> None:
        self.settings.text_bg_color = ""
        self.btn_text_bg.setStyleSheet(_swatch_style(""))
        if isinstance(self._selected_item(), TextItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "bg_color", ""))

    def _on_ctx_hl_style(self, st: str) -> None:
        self.settings.highlight_style = st
        if isinstance(self._selected_item(), HighlightItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "style", st))

    def _set_hl_color(self, hx: str) -> None:
        self.settings.highlight_color = hx
        if isinstance(self._selected_item(), HighlightItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "color", hx))

    def _on_ctx_shape_changed(self, idx: int) -> None:
        keys = ["rect", "roundrect", "ellipse", "line", "arrow"]
        if 0 <= idx < len(keys):
            self.settings.shape_type = keys[idx]
            self._update_context_bar_visibility()

    def _pick_stroke_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.settings.stroke_color), self, "Stroke Color")
        if col.isValid():
            hx = col.name()
            self.settings.stroke_color = hx
            self.btn_stroke_color.setStyleSheet(_swatch_style(hx))
            sel = self._selected_item()
            if isinstance(sel, ShapeItem):
                self._mutate_selected_and_refresh(lambda s: setattr(s, "stroke_color", hx))
            elif isinstance(sel, InkItem):
                self._mutate_selected_and_refresh(lambda s: setattr(s, "color", hx))

    def _pick_fill_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.settings.fill_color or "#DBEAFE"), self, "Shape Fill Color")
        if col.isValid():
            hx = col.name()
            self.settings.fill_color = hx
            self.btn_fill_color.setStyleSheet(_swatch_style(hx))
            if isinstance(self._selected_item(), ShapeItem):
                self._mutate_selected_and_refresh(lambda s: setattr(s, "fill_color", hx))

    def _clear_fill_color(self) -> None:
        self.settings.fill_color = ""
        self.btn_fill_color.setStyleSheet(_swatch_style(""))
        if isinstance(self._selected_item(), ShapeItem):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "fill_color", ""))

    def _on_ctx_stroke_w_changed(self, val: float) -> None:
        if self._updating_ctx_ui:
            return
        self.settings.stroke_width = val
        sel = self._selected_item()
        if isinstance(sel, (ShapeItem, InkItem)):
            self._mutate_selected_and_refresh(lambda s: setattr(s, "stroke_width", val))

    def _pick_whiteout_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.settings.whiteout_color), self, "Whiteout Fill Color")
        if col.isValid():
            hx = col.name()
            self.settings.whiteout_color = hx
            self.settings.whiteout_auto_sample = False
            self.chk_auto_bg.setChecked(False)
            self.btn_wo_color.setStyleSheet(_swatch_style(hx))
            if isinstance(self._selected_item(), WhiteoutItem):
                self._mutate_selected_and_refresh(lambda s: setattr(s, "fill_color", hx))

    def _on_stamp_preset_changed(self, idx: int) -> None:
        if 0 <= idx < len(CustomStampDialog.PRESETS):
            txt, col = CustomStampDialog.PRESETS[idx]
            self.settings.stamp_text = txt
            self.settings.stamp_color = col

    def _toggle_highlight_forms(self, on: bool) -> None:
        self.settings.highlight_forms = on
        v = self.current_view()
        if v:
            v.refresh_all_pages()

    # ------------------------------------------------------------------
    # Signature, Image, Stamp Triggers
    # ------------------------------------------------------------------
    def _on_sign_toolbar_clicked(self) -> None:
        if not self.settings.pending_signature_b64:
            self.open_signature_dialog()
        else:
            self.set_tool("sign")

    def open_signature_dialog(self) -> None:
        dlg = SignatureDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_b64:
            self.settings.pending_signature_b64 = dlg.result_b64
            self.settings.pending_signature_ratio = dlg.result_ratio
            self.set_tool("sign")
            self.lbl_status_hint.setText("Signature ready — click anywhere on the PDF to place it!")

    def _on_canvas_signature_requested(self, page_idx: int, x: float, y: float) -> None:
        dlg = SignatureDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_b64:
            self.settings.pending_signature_b64 = dlg.result_b64
            self.settings.pending_signature_ratio = dlg.result_ratio
            v = self.current_view()
            if v:
                w = 155.0
                h = max(28.0, w / max(0.3, dlg.result_ratio))
                item = ImageItem(page=page_idx, x=x - w / 2.0, y=y - h / 2.0, w=w, h=h, image_b64=dlg.result_b64, is_signature=True)
                v.state.add_item(item)
                v.select_item(item.id)
                self.set_tool("select")
                v.itemsChanged.emit()

    def _on_image_toolbar_clicked(self) -> None:
        self.choose_image_to_place()

    def choose_image_to_place(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            self.set_tool("select")
            return
        img = Image.open(path).convert("RGBA")
        self.settings.pending_image_b64 = image_to_png_b64(img)
        self.settings.pending_image_ratio = img.width / max(1, img.height)
        self.set_tool("image")
        self.lbl_status_hint.setText("Image loaded — click anywhere on the PDF to place it!")

    def _on_canvas_image_requested(self, page_idx: int, x: float, y: float) -> None:
        self.choose_image_to_place()

    def open_stamp_dialog(self) -> None:
        dlg = CustomStampDialog(self.settings.stamp_text, self.settings.stamp_color, self.settings.stamp_rotation, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            txt, col, rot = dlg.get_params()
            self.settings.stamp_text = txt
            self.settings.stamp_color = col
            self.settings.stamp_rotation = rot
            self.set_tool("stamp")

    # ------------------------------------------------------------------
    # Edit Actions
    # ------------------------------------------------------------------
    def action_undo(self) -> None:
        v = self.current_view()
        if v and v.state.undo():
            v.close_all_inline_editors()
            v.select_item(None)
            v.refresh_all_pages()
            self._refresh_forms_and_objects()
            self._sync_ui_state()

    def action_redo(self) -> None:
        v = self.current_view()
        if v and v.state.redo():
            v.close_all_inline_editors()
            v.select_item(None)
            v.refresh_all_pages()
            self._refresh_forms_and_objects()
            self._sync_ui_state()

    def action_copy(self) -> None:
        v = self.current_view()
        if v:
            v.copy_selected()

    def action_paste(self) -> None:
        v = self.current_view()
        if v:
            v.paste_at()

    def action_duplicate(self) -> None:
        v = self.current_view()
        if v:
            v.duplicate_selected()

    def action_delete(self) -> None:
        v = self.current_view()
        if v:
            v.delete_selected()

    def action_copy_page_text(self) -> None:
        v = self.current_view()
        if not v:
            return
        txt = v.pdf_doc.getAllText(v.current_page).text()
        if txt:
            QApplication.clipboard().setText(txt)
            self.lbl_status_hint.setText(f"Copied {len(txt)} characters from page {v.current_page + 1}.")
        else:
            self.lbl_status_hint.setText("No selectable text found on this page (it may be a scanned image).")

    def action_clear_form_fields(self) -> None:
        v = self.current_view()
        if not v:
            return
        v.state.push_undo()
        for it in v.state.items:
            if isinstance(it, FormFieldItem):
                it.value = ""
                it.checked = False
        v.refresh_all_pages()
        self._refresh_forms_and_objects()
        self._sync_ui_state()

    # ------------------------------------------------------------------
    # Sidebar (Thumbnails, Forms, Objects)
    # ------------------------------------------------------------------
    def _refresh_sidebar(self) -> None:
        self._refresh_thumbnails()
        self._refresh_forms_and_objects()

    def _refresh_thumbnails(self) -> None:
        self.thumb_list.blockSignals(True)
        self.thumb_list.clear()
        v = self.current_view()
        if v and v.pdf_doc.status() == QPdfDocument.Status.Ready:
            for i in range(v.page_count()):
                pt = v.pdf_doc.pagePointSize(i)
                scale = min(130.0 / max(1.0, pt.width()), 170.0 / max(1.0, pt.height()))
                w = max(24, int(round(pt.width() * scale)))
                h = max(24, int(round(pt.height() * scale)))
                img = v.pdf_doc.render(i, QSize(w, h))
                paper = QImage(w, h, QImage.Format.Format_RGB32)
                paper.fill(QColor("#FFFFFF"))
                p = QPainter(paper)
                p.drawImage(0, 0, img)
                p.setPen(QColor("#CBD5E1"))
                p.drawRect(0, 0, w - 1, h - 1)
                p.end()
                item = QListWidgetItem(QIcon(QPixmap.fromImage(paper)), f"Page {i + 1}")
                self.thumb_list.addItem(item)
            if 0 <= v.current_page < self.thumb_list.count():
                self.thumb_list.setCurrentRow(v.current_page)
        self.thumb_list.blockSignals(False)

    def _refresh_forms_and_objects(self) -> None:
        self.forms_list.clear()
        self.objects_list.clear()
        v = self.current_view()
        if not v:
            self.lbl_forms_summary.setText("No document open.")
            return

        form_fields = [it for it in v.state.items if isinstance(it, FormFieldItem)]
        self.lbl_forms_summary.setText(
            f"{len(form_fields)} fillable field(s). Click any field to jump & edit."
            if form_fields
            else "No fillable form fields yet. Use Forms menu to add them."
        )
        for ff in form_fields:
            val_preview = ("✓" if ff.checked else "☐") if ff.field_type in ("checkbox", "radio") else (ff.value or "(empty)")
            li = QListWidgetItem(f"P{ff.page + 1} · {ff.field_name} [{ff.field_type}]: {val_preview}")
            li.setData(Qt.ItemDataRole.UserRole, ff.id)
            self.forms_list.addItem(li)

        for it in v.state.items_on_page(v.current_page):
            label = it.kind.upper()
            if isinstance(it, TextItem):
                label = f"Text: {it.text[:24]}"
            elif isinstance(it, StampItem):
                label = f"Stamp: {it.stamp_type if it.stamp_type != 'rubber' else it.text}"
            elif isinstance(it, ImageItem):
                label = "Signature" if it.is_signature else "Image"
            elif isinstance(it, FormFieldItem):
                label = f"Field: {it.field_name}"
            elif isinstance(it, NoteItem):
                label = f"Note: {it.text[:22]}"
            li = QListWidgetItem(label)
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            self.objects_list.addItem(li)

    def _on_thumb_clicked(self, row: int) -> None:
        v = self.current_view()
        if v and row >= 0:
            v.set_current_page(row, scroll=True)

    def _on_view_page_changed(self, tab: DocumentTab, page_idx: int) -> None:
        if tab is not self.current_tab():
            return
        self.spn_page.blockSignals(True)
        self.spn_page.setValue(page_idx + 1)
        self.spn_page.blockSignals(False)
        self.thumb_list.blockSignals(True)
        if 0 <= page_idx < self.thumb_list.count():
            self.thumb_list.setCurrentRow(page_idx)
        self.thumb_list.blockSignals(False)
        self._refresh_forms_and_objects()

    def _on_form_list_clicked(self, item: QListWidgetItem) -> None:
        v = self.current_view()
        if not v:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        ff = v.state.find_item(fid)
        if isinstance(ff, FormFieldItem):
            v.set_current_page(ff.page, scroll=True)
            v.select_item(ff.id)
            if 0 <= ff.page < len(v.page_widgets):
                v.page_widgets[ff.page].open_inline_form_editor(ff)

    def _on_object_list_clicked(self, item: QListWidgetItem) -> None:
        v = self.current_view()
        if not v:
            return
        oid = item.data(Qt.ItemDataRole.UserRole)
        v.select_item(oid)

    def _show_thumb_context_menu(self, pos) -> None:
        if not self.current_tab():
            return
        menu = QMenu(self)
        menu.addAction("Rotate 90° Clockwise", lambda: self.mutate_current_page("rotate", angle=90))
        menu.addAction("Rotate 90° Counter-Clockwise", lambda: self.mutate_current_page("rotate", angle=-90))
        menu.addSeparator()
        menu.addAction("Insert Blank Page After", lambda: self.mutate_current_page("insert_blank"))
        menu.addAction("Insert Pages from PDF...", self.action_insert_pdf_pages)
        menu.addAction("Duplicate Page", lambda: self.mutate_current_page("duplicate"))
        menu.addAction("Move Page Up", lambda: self.move_current_page(-1))
        menu.addAction("Move Page Down", lambda: self.move_current_page(1))
        menu.addSeparator()
        menu.addAction("Extract / Split Pages...", self.action_split_pdf)
        menu.addAction("Delete Page", lambda: self.mutate_current_page("delete"))
        menu.exec(self.thumb_list.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Page Management Mutations
    # ------------------------------------------------------------------
    def mutate_current_page(self, op: str, angle: int = 90, extra_pdf_path: str = "") -> None:
        tab = self.current_tab()
        if not tab:
            return
        tab.view.close_all_inline_editors()
        cur_p = tab.view.current_page
        insert_pos = cur_p + 1 if op in ("insert_blank", "insert_pdf") else cur_p

        try:
            new_path, old_to_new = mutate_pdf_pages(
                tab.state.working_pdf_path,
                tab.state.password,
                op=op,
                page_idx=insert_pos if op in ("insert_blank", "insert_pdf") else cur_p,
                angle=angle,
                extra_pdf_path=extra_pdf_path,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Page Operation", str(exc))
            return

        tab.view.pdf_doc.close()
        tab.state.working_pdf_path = new_path
        tab.temp_files.append(new_path)
        tab.state.password = ""  # working copy is now decrypted
        tab.state.remap_pages(old_to_new)
        if op == "duplicate":
            tab.state.duplicate_page_items(old_to_new.get(cur_p, cur_p), old_to_new.get(cur_p, cur_p) + 1)

        tab.view.load_working_pdf()
        tab.view.set_current_page(min(cur_p, tab.view.page_count() - 1), scroll=True)
        self._refresh_sidebar()
        self._sync_ui_state()

    def move_current_page(self, delta: int) -> None:
        tab = self.current_tab()
        if not tab:
            return
        cur_p = tab.view.current_page
        target = cur_p + delta
        if target < 0 or target >= tab.view.page_count():
            return
        tab.view.close_all_inline_editors()
        new_path, old_to_new = mutate_pdf_pages(
            tab.state.working_pdf_path, tab.state.password, op="move", page_idx=cur_p, target_idx=target
        )
        tab.view.pdf_doc.close()
        tab.state.working_pdf_path = new_path
        tab.temp_files.append(new_path)
        tab.state.password = ""
        tab.state.remap_pages(old_to_new)
        tab.view.load_working_pdf()
        tab.view.set_current_page(target, scroll=True)
        self._refresh_sidebar()
        self._sync_ui_state()

    def action_insert_pdf_pages(self) -> None:
        if not self.current_tab():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Insert Pages from PDF", "", "PDF Files (*.pdf)")
        if path:
            self.mutate_current_page("insert_pdf", extra_pdf_path=path)

    # ------------------------------------------------------------------
    # Document Utilities (Merge, Split, Images, Watermark, Header/Footer, Security, Print)
    # ------------------------------------------------------------------
    def action_merge_pdfs(self) -> None:
        initial = []
        tab = self.current_tab()
        if tab and tab.state.source_path:
            initial.append(tab.state.source_path)
        dlg = MergePdfsDialog(initial, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Save Merged PDF", "merged.pdf", "PDF Files (*.pdf)")
        if not out_path:
            return
        try:
            merge_pdfs(dlg.selected_files(), out_path)
            self.open_pdf(out_path)
            self.lbl_status_hint.setText(f"Merged {len(dlg.selected_files())} PDFs into {Path(out_path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Merge Failed", str(exc))

    def action_split_pdf(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        dlg = SplitPdfDialog(tab.view.page_count(), self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        # Save a temporary copy with current edits so split includes user edits!
        fd, tmp_edited = tempfile.mkstemp(prefix="kinofill_split_", suffix=".pdf")
        os.close(fd)
        try:
            save_edited_pdf(tab.state, tmp_edited)
            if dlg.is_burst():
                out_dir = QFileDialog.getExistingDirectory(self, "Choose Folder for Split PDFs")
                if not out_dir:
                    return
                created = split_pdf(tmp_edited, out_dir, dlg.page_range(), burst=True)
                QMessageBox.information(self, "Split Complete", f"Exported {len(created)} individual PDF file(s) to:\n{out_dir}")
            else:
                out_file, _ = QFileDialog.getSaveFileName(self, "Save Extracted Pages", "extracted.pdf", "PDF Files (*.pdf)")
                if not out_file:
                    return
                split_pdf(tmp_edited, out_file, dlg.page_range(), burst=False)
                self.open_pdf(out_file)
        except Exception as exc:
            QMessageBox.critical(self, "Split Failed", str(exc))
        finally:
            if os.path.exists(tmp_edited):
                os.remove(tmp_edited)

    def action_images_to_pdf(self) -> None:
        imgs, _ = QFileDialog.getOpenFileNames(
            self, "Select Images to Convert to PDF", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
        )
        if not imgs:
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Save New PDF", "images.pdf", "PDF Files (*.pdf)")
        if not out_path:
            return
        try:
            images_to_pdf(imgs, out_path)
            self.open_pdf(out_path)
        except Exception as exc:
            QMessageBox.critical(self, "Conversion Failed", str(exc))

    def action_export_images(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        dlg = ExportImagesDialog(tab.view.page_count(), self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not out_dir:
            return
        fmt, dpi, prange = dlg.get_params()
        fd, tmp_edited = tempfile.mkstemp(prefix="kinofill_exp_", suffix=".pdf")
        os.close(fd)
        try:
            save_edited_pdf(tab.state, tmp_edited)
            created = export_pdf_to_images(tmp_edited, out_dir, fmt=fmt, dpi=dpi, page_range=prange)
            QMessageBox.information(self, "Export Complete", f"Exported {len(created)} {fmt} image(s) to:\n{out_dir}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
        finally:
            if os.path.exists(tmp_edited):
                os.remove(tmp_edited)

    def action_watermark(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        dlg = WatermarkDialog(tab.state.watermark, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            tab.state.watermark = dlg.to_config()
            tab.state.dirty = True
            tab.view.refresh_all_pages()
            self._sync_ui_state()

    def action_header_footer(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        dlg = HeaderFooterDialog(tab.state.header_footer, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            tab.state.header_footer = dlg.to_config()
            tab.state.dirty = True
            tab.view.refresh_all_pages()
            self._sync_ui_state()

    def action_security(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        dlg = SecurityDialog(tab.state.security, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            tab.state.security = dlg.to_config()
            tab.state.dirty = True
            self._sync_ui_state()
            self.lbl_status_hint.setText("Security & save options updated — click Save to apply them.")

    def action_metadata(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        dlg = MetadataDialog(tab.state.metadata, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            tab.state.metadata = dlg.to_metadata()
            tab.state.dirty = True
            self._sync_ui_state()

    def action_print(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return

        fd, tmp_print = tempfile.mkstemp(prefix="kinofill_print_", suffix=".pdf")
        os.close(fd)
        try:
            save_edited_pdf(tab.state, tmp_print)
            pdoc = QPdfDocument()
            if pdoc.load(tmp_print) != QPdfDocument.Error.None_:
                raise RuntimeError("Could not load prepared PDF for printing.")
            painter = QPainter(printer)
            for i in range(pdoc.pageCount()):
                if i > 0:
                    printer.newPage()
                target = painter.viewport()
                img = pdoc.render(i, QSize(target.width(), target.height()))
                painter.drawImage(target, img)
            painter.end()
            pdoc.close()
        except Exception as exc:
            QMessageBox.critical(self, "Print Failed", str(exc))
        finally:
            if os.path.exists(tmp_print):
                os.remove(tmp_print)

    # ------------------------------------------------------------------
    # Search, Zoom & Navigation
    # ------------------------------------------------------------------
    def show_find_bar(self) -> None:
        if not self.current_tab():
            return
        self.find_bar.show()
        self.txt_find.setFocus()
        self.txt_find.selectAll()

    def hide_find_bar(self) -> None:
        self.find_bar.hide()
        v = self.current_view()
        if v:
            v.set_search_query("")

    def _on_find_text_changed(self, query: str) -> None:
        v = self.current_view()
        if not v:
            return
        count = v.set_search_query(query)
        self.lbl_find_count.setText(f"{'1 / ' if count else ''}{count} match{'es' if count != 1 else ''}")

    def _step_find(self, step: int) -> None:
        v = self.current_view()
        if not v:
            return
        cur, total = v.next_search_result(step)
        self.lbl_find_count.setText(f"{cur} / {total}" if total else "0 matches")

    def _step_page(self, delta: int) -> None:
        v = self.current_view()
        if v:
            v.set_current_page(v.current_page + delta, scroll=True)

    def _on_page_spin_changed(self, val: int) -> None:
        v = self.current_view()
        if v:
            v.set_current_page(val - 1, scroll=True)

    def step_zoom(self, factor: float) -> None:
        v = self.current_view()
        if v:
            v.set_zoom(v.zoom * factor)

    def set_zoom_exact(self, z: float) -> None:
        v = self.current_view()
        if v:
            v.set_zoom(z)

    def action_fit_width(self) -> None:
        v = self.current_view()
        if v:
            v.fit_width()

    def action_fit_page(self) -> None:
        v = self.current_view()
        if v:
            v.fit_page()

    def _on_zoom_combo_activated(self, _idx: int) -> None:
        txt = self.cmb_zoom.currentText().strip()
        if txt == "Fit Width":
            self.action_fit_width()
        elif txt == "Fit Page":
            self.action_fit_page()
        else:
            try:
                pct = float(txt.rstrip("%"))
                self.set_zoom_exact(pct / 100.0)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Keyboard & Drag-and-Drop
    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Don't steal single-key shortcuts when typing in an input widget!
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox)) or (
            fw is not None and fw.inherits("QTextEdit")
        ):
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()
        v = self.current_view()

        if key == Qt.Key.Key_Escape:
            if self.find_bar.isVisible():
                self.hide_find_bar()
            else:
                self.set_tool("select")
            return

        if v and mods in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            step = 10.0 if (mods & Qt.KeyboardModifier.ShiftModifier) else 1.5
            if key == Qt.Key.Key_Left:
                v.nudge_selected(-step, 0)
                return
            if key == Qt.Key.Key_Right:
                v.nudge_selected(step, 0)
                return
            if key == Qt.Key.Key_Up:
                v.nudge_selected(0, -step)
                return
            if key == Qt.Key.Key_Down:
                v.nudge_selected(0, step)
                return

        if mods == Qt.KeyboardModifier.NoModifier:
            shortcut_map = {
                Qt.Key.Key_R: "edit_text",
                Qt.Key.Key_V: "select",
                Qt.Key.Key_T: "text",
                Qt.Key.Key_C: "check",
                Qt.Key.Key_H: "highlight",
                Qt.Key.Key_P: "pen",
                Qt.Key.Key_E: "whiteout",
                Qt.Key.Key_X: "redact",
            }
            if key in shortcut_map:
                self.set_tool(shortcut_map[key])
                return
            if key == Qt.Key.Key_S:
                self._on_sign_toolbar_clicked()
                return
            if key == Qt.Key.Key_I:
                self.choose_image_to_place()
                return

        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        imgs: List[str] = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if not p:
                continue
            low = p.lower()
            if low.endswith(".pdf"):
                self.open_pdf(p)
            elif low.endswith((".kinofill", ".freefill", ".lfill")):
                self.open_project_file(p)
            elif low.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")):
                imgs.append(p)
        if imgs:
            fd, tmp = tempfile.mkstemp(prefix="kinofill_imgs_", suffix=".pdf")
            os.close(fd)
            images_to_pdf(imgs, tmp)
            tab = self.open_pdf(tmp, display_source_path="")
            try:
                os.remove(tmp)
            except OSError:
                pass
            if tab:
                tab.state.dirty = True
                self._sync_ui_state()

    def show_shortcuts_help(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts & Quick Guide",
            "Tools (when not typing):\n"
            "  V  Select / Fill Forms      T  Add Text\n"
            "  R  Edit Existing Text       C  Checkmark ✓\n"
            "  S  Signature & Initials     H  Highlight / Markup\n"
            "  P  Freehand Pen             E  Erase / Whiteout\n"
            "  X  Blackout / Redact        I  Insert Image\n\n"
            "Editing & Navigation:\n"
            "  Ctrl+O  Open PDF            Ctrl+S  Save PDF\n"
            "  Ctrl+Z / Ctrl+Y  Undo/Redo  Ctrl+F  Find Text\n"
            "  Ctrl+C / V / D  Copy/Paste/Duplicate\n"
            "  Arrow Keys (Shift = 10pt)  Nudge Selected Item\n"
            "  Ctrl + Mouse Wheel          Smooth Zoom\n"
            "  Double-click Text / Note    Edit Inline",
        )

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} v{APP_VERSION} — {APP_SUBTITLE}</h3>"
            f"<p>Part of <b>{SUITE_NAME}</b> — a 100% local, private, free Windows PDF & form studio.</p>"
            "<p>Fill & create AcroForms, edit & replace existing PDF text directly in place, draw/type/upload signatures, "
            "highlight, whiteout, true-redact, stamp, watermark, merge, split, protect, and print — "
            "all locally on your PC with zero cloud uploads or subscriptions.</p>",
        )
