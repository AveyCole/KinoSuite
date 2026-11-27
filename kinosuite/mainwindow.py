"""KinoSuite Hub Main Window — Unified Launcher, Universal File Router,
Process Monitor, KinoCloud Project Browser, Cross-App Workflows & Suite Health."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .icons import make_app_badge, make_suite_icon, make_suite_pixmap
from .registry import (
    KinoAppInfo,
    SuiteConfig,
    check_environment_health,
    collect_suite_plugins,
    collect_suite_projects,
    discover_suite_apps,
    find_python_executable,
    launch_kino_app,
    query_running_kino_processes,
    route_file_to_app,
    terminate_process,
)
from .theme import KINOSUITE_HUB_DARK, KINOSUITE_HUB_LIGHT


# ---------------------------------------------------------------------------
# Universal Drag-and-Drop File Router Zone
# ---------------------------------------------------------------------------
class FileDropZone(QFrame):
    filesDropped = Signal(list)
    browseClicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)

        lbl = QLabel("<b>Universal File Router</b> — Drop any Video, Photo, Vector, Audio, MIDI, PDF, or Retro Game (.kpx/.gba) file here to open it automatically in the matching KinoSuite app")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)

        btn = QPushButton("Open Any File...")
        btn.setObjectName("PrimaryButton")
        btn.clicked.connect(self.browseClicked.emit)
        lay.addWidget(btn)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()


# ---------------------------------------------------------------------------
# Sleek KinoSuite App Card
# ---------------------------------------------------------------------------
class AppCardWidget(QFrame):
    launchRequested = Signal(str)
    openFileRequested = Signal(str)
    openFolderRequested = Signal(str)
    stopRequested = Signal(str)

    def __init__(self, app: KinoAppInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app = app
        self.setObjectName("AppCard")
        self.setMinimumHeight(178)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # Header: Badge + Name/Category + Status pill
        top = QHBoxLayout()
        top.setSpacing(12)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(make_app_badge(app.monogram, app.accent, app.bg_hex, 52, wave_bars=(app.app_id == "kinowave"), pixel_blocks=(app.app_id == "kinopixel")))
        lbl_icon.setFixedSize(52, 52)
        top.addWidget(lbl_icon)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        title = QLabel(f"<span style='font-size:12pt; font-weight:700;'>{app.name}</span>")
        cat = QLabel(f"{app.category}  ·  {app.disk_size_mb():.1f} MB")
        cat.setObjectName("MutedText")
        meta.addWidget(title)
        meta.addWidget(cat)
        top.addLayout(meta, 1)

        self.lbl_status = QLabel("READY")
        self.lbl_status.setFixedHeight(22)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.lbl_status, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)

        # Description
        desc = QLabel(app.tagline)
        desc.setWordWrap(True)
        desc.setObjectName("MutedText")
        lay.addWidget(desc, 1)

        # Supported extensions preview
        ext_txt = "  ".join(app.extensions[:7]) + (" ..." if len(app.extensions) > 7 else "")
        lbl_ext = QLabel(ext_txt)
        lbl_ext.setStyleSheet(f"color: {app.accent}; font-family: Consolas, monospace; font-size: 7.8pt;")
        lay.addWidget(lbl_ext)

        # Action row
        brow = QHBoxLayout()
        brow.setSpacing(6)
        self.btn_launch = QPushButton("Launch")
        self.btn_launch.setStyleSheet(
            f"QPushButton {{ background-color: {app.accent}; color: #091118; border: 1px solid {app.accent}; font-weight: 700; border-radius: 7px; padding: 6px 14px; }}"
            f"QPushButton:hover {{ opacity: 0.92; }}"
        )
        self.btn_launch.clicked.connect(lambda: self.launchRequested.emit(self.app.app_id))

        self.btn_open = QPushButton("Open File...")
        self.btn_open.clicked.connect(lambda: self.openFileRequested.emit(self.app.app_id))

        self.btn_dir = QPushButton("Folder")
        self.btn_dir.clicked.connect(lambda: self.openFolderRequested.emit(self.app.app_id))

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("DangerButton")
        self.btn_stop.setVisible(False)
        self.btn_stop.clicked.connect(lambda: self.stopRequested.emit(self.app.app_id))

        brow.addWidget(self.btn_launch)
        brow.addWidget(self.btn_open)
        brow.addWidget(self.btn_dir)
        brow.addWidget(self.btn_stop)
        brow.addStretch(1)
        lay.addLayout(brow)

        self.set_running_pids([])

    def set_running_pids(self, pids: List[int]) -> None:
        if not self.app.installed:
            self.lbl_status.setText("MISSING")
            self.lbl_status.setStyleSheet("background:#3B1D24; color:#FCA5A5; border:1px solid #7F2D3A; border-radius:5px; padding:2px 8px; font-size:7.5pt; font-weight:700;")
            self.btn_launch.setEnabled(False)
            self.btn_stop.setVisible(False)
        elif pids:
            self.lbl_status.setText(f"● RUNNING ({len(pids)})")
            self.lbl_status.setStyleSheet("background:#0B2E26; color:#10D9A0; border:1px solid #10D9A0; border-radius:5px; padding:2px 8px; font-size:7.5pt; font-weight:700;")
            self.btn_launch.setText("New Window")
            self.btn_launch.setEnabled(True)
            self.btn_stop.setVisible(True)
        else:
            self.lbl_status.setText("READY")
            self.lbl_status.setStyleSheet("background:#1B2436; color:#9AA4B8; border:1px solid #303C52; border-radius:5px; padding:2px 8px; font-size:7.5pt; font-weight:700;")
            self.btn_launch.setText("Launch")
            self.btn_launch.setEnabled(True)
            self.btn_stop.setVisible(False)


# ---------------------------------------------------------------------------
# Register Custom Kino App Dialog
# ---------------------------------------------------------------------------
class RegisterAppDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Register Custom KinoSuite App")
        self.setMinimumWidth(460)
        self.accent_color = "#A78BFA"
        form = QFormLayout(self)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("e.g. Kino3D or KinoMotion")
        self.ed_mono = QLineEdit("K3")
        self.ed_mono.setMaxLength(3)
        self.ed_cat = QLineEdit("Creative Studio")
        self.ed_tag = QLineEdit("Custom KinoSuite Creative Application")
        self.ed_ext = QLineEdit(".k3d, .obj, .fbx")

        prow = QHBoxLayout()
        self.ed_exe = QLineEdit()
        b_br = QPushButton("Browse...")
        b_br.clicked.connect(self._browse)
        prow.addWidget(self.ed_exe, 1)
        prow.addWidget(b_br)

        self.btn_col = QPushButton(self.accent_color)
        self.btn_col.clicked.connect(self._pick_col)

        form.addRow("App Name:", self.ed_name)
        form.addRow("Monogram (2 chars):", self.ed_mono)
        form.addRow("Category:", self.ed_cat)
        form.addRow("Description:", self.ed_tag)
        form.addRow("Executable (.exe / .py):", prow)
        form.addRow("File Extensions:", self.ed_ext)
        form.addRow("Accent Color:", self.btn_col)

        row = QHBoxLayout()
        b_c = QPushButton("Cancel"); b_c.clicked.connect(self.reject)
        b_o = QPushButton("Register App"); b_o.setObjectName("PrimaryButton"); b_o.clicked.connect(self.accept)
        row.addWidget(b_c); row.addWidget(b_o)
        form.addRow(row)

    def _browse(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Select Executable or Python Script", "", "Executables (*.exe *.py);;All Files (*.*)")
        if fp:
            self.ed_exe.setText(fp)
            if not self.ed_name.text().strip():
                nm = os.path.splitext(os.path.basename(fp))[0]
                self.ed_name.setText(nm)
                self.ed_mono.setText(nm[:2])

    def _pick_col(self) -> None:
        col = QColorDialog.getColor(QColor(self.accent_color), self, "Pick Accent Color")
        if col.isValid():
            self.accent_color = col.name()
            self.btn_col.setText(self.accent_color)

    def to_entry(self) -> Dict[str, Any]:
        name = self.ed_name.text().strip() or "KinoApp"
        exts = [e.strip().lower() for e in self.ed_ext.text().split(",") if e.strip()]
        exts = [e if e.startswith(".") else "." + e for e in exts]
        return {
            "app_id": name.lower().replace(" ", "_"),
            "name": name,
            "monogram": self.ed_mono.text().strip() or name[:2],
            "category": self.ed_cat.text().strip() or "Custom",
            "tagline": self.ed_tag.text().strip(),
            "exe_path": self.ed_exe.text().strip(),
            "extensions": exts,
            "accent": self.accent_color,
            "bg_hex": "#161B26",
        }


# ---------------------------------------------------------------------------
# Main KinoSuite Hub Window
# ---------------------------------------------------------------------------
class KinoSuiteHubWindow(QMainWindow):
    def __init__(self, suite_root: str) -> None:
        super().__init__()
        self.suite_root = suite_root
        self.cfg = SuiteConfig(suite_root)
        self.apps: List[KinoAppInfo] = discover_suite_apps(suite_root, self.cfg)
        self.tracked_procs: Dict[int, str] = {}
        self.running_rows: List[Dict[str, Any]] = []
        self.app_cards: Dict[str, AppCardWidget] = {}
        self._all_projects: List[Dict[str, Any]] = []
        self._all_plugins: List[Dict[str, str]] = []
        self._tray: Optional[QSystemTrayIcon] = None

        self.setWindowTitle(f"KinoSuite Hub v{__version__} — Unified Creative Suite")
        self.setWindowIcon(make_suite_icon(64))
        self.resize(1340, 840)
        self.setAcceptDrops(True)

        self._build_ui()
        self._setup_tray()
        self._apply_theme(self.cfg.data.get("theme", "Dark"))

        # Ctrl+K focuses global search
        QShortcut(QKeySequence("Ctrl+K"), self, activated=lambda: (self.ed_global_search.setFocus(), self.ed_global_search.selectAll()))

        # Lightweight 2.5s live process monitor timer
        self._proc_timer = QTimer(self)
        self._proc_timer.setInterval(2500)
        self._proc_timer.timeout.connect(self.refresh_processes)
        self._proc_timer.start()

        self.refresh_all()

    def apply_native_taskbar_icon(self) -> None:
        """Bind KinoSuite.ico directly to the 64-bit Win32 HWND & Window Class so the Windows taskbar & Alt+Tab show the KS badge."""
        if sys.platform != "win32":
            return
        ico_path = os.path.join(self.suite_root, "KinoSuite.ico")
        if not os.path.isfile(ico_path):
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.LoadImageW.restype = ctypes.c_void_p
            user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
            user32.SendMessageW.restype = ctypes.c_ssize_t
            user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            user32.SetClassLongPtrW.restype = ctypes.c_void_p

            hwnd = ctypes.c_void_p(int(self.winId()))
            h_small = user32.LoadImageW(None, ico_path, 1, 16, 16, 0x0010)
            h_big = user32.LoadImageW(None, ico_path, 1, 48, 48, 0x0010)
            self._h_icon_small = h_small
            self._h_icon_big = h_big
            if h_small:
                user32.SendMessageW(hwnd, 0x0080, 0, h_small)
                user32.SetClassLongPtrW(hwnd, -34, h_small)  # GCLP_HICONSM
            if h_big:
                user32.SendMessageW(hwnd, 0x0080, 1, h_big)
                user32.SetClassLongPtrW(hwnd, -14, h_big)    # GCLP_HICON
        except Exception:
            pass

    # ---- Drag-and-drop anywhere on main window ----
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.open_files_smart(paths)
            event.acceptProposedAction()

    # ---- UI Construction ----
    def _build_ui(self) -> None:
        root_w = QWidget()
        self.setCentralWidget(root_w)
        outer = QHBoxLayout(root_w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 1. Left Navigation Rail
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sidebar.setFixedWidth(228)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 16, 14, 14)
        sl.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        b_ico = QLabel()
        b_ico.setPixmap(make_suite_pixmap(42))
        b_ico.setFixedSize(42, 42)
        b_txt = QLabel("<span style='font-size:13pt; font-weight:800;'>KinoSuite</span><br><span style='font-size:8pt; color:#00C2FF;'>CREATIVE HUB</span>")
        brand.addWidget(b_ico)
        brand.addWidget(b_txt, 1)
        sl.addLayout(brand)
        sl.addSpacing(14)

        self.nav_btns: List[QPushButton] = []
        nav_items = [
            ("Apps & Launchpad", 0),
            ("Projects & KinoCloud", 1),
            ("Processes & Plugins", 2),
            ("Workflows & Tools", 3),
            ("Health & Settings", 4),
        ]
        for label, idx in nav_items:
            b = QPushButton(label)
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=idx: self._switch_page(i))
            sl.addWidget(b)
            self.nav_btns.append(b)
        self.nav_btns[0].setChecked(True)

        sl.addSpacing(14)
        ql_hdr = QLabel("QUICK LAUNCH")
        ql_hdr.setStyleSheet("color:#64748B; font-size:7.5pt; font-weight:700; padding-left:4px;")
        sl.addWidget(ql_hdr)
        self.quick_launch_box = QVBoxLayout()
        self.quick_launch_box.setSpacing(4)
        sl.addLayout(self.quick_launch_box)

        sl.addStretch(1)
        self.lbl_running_summary = QLabel("0 apps running")
        self.lbl_running_summary.setObjectName("SuiteBadge")
        self.lbl_running_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.lbl_running_summary)

        outer.addWidget(sidebar)

        # 2. Right Main Content Area
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        # Top Command Bar
        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        topbar.setFixedHeight(54)
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(18, 8, 18, 8)
        tl.setSpacing(10)

        self.ed_global_search = QLineEdit()
        self.ed_global_search.setPlaceholderText("Search apps, recent projects, plugins... (Ctrl+K, Enter to launch)")
        self.ed_global_search.textChanged.connect(self._on_search_changed)
        self.ed_global_search.returnPressed.connect(self._on_search_enter)
        tl.addWidget(self.ed_global_search, 1)

        b_open_any = QPushButton("Open File...")
        b_open_any.clicked.connect(self._browse_any_file)
        b_refresh = QPushButton("Refresh")
        b_refresh.clicked.connect(self.refresh_all)
        self.btn_theme = QPushButton("Light Mode")
        self.btn_theme.clicked.connect(self._toggle_theme)
        tl.addWidget(b_open_any)
        tl.addWidget(b_refresh)
        tl.addWidget(self.btn_theme)
        right.addWidget(topbar)

        # Stacked Pages
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_apps_page())
        self.pages.addWidget(self._build_projects_page())
        self.pages.addWidget(self._build_processes_page())
        self.pages.addWidget(self._build_workflows_page())
        self.pages.addWidget(self._build_settings_page())
        right.addWidget(self.pages, 1)

        outer.addLayout(right, 1)

        # Status Bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_status = QLabel("KinoSuite Hub Ready")
        self.status.addWidget(self.lbl_status, 1)
        badge = QLabel("KINOSUITE UNIFIED PLATFORM")
        badge.setObjectName("SuiteBadge")
        self.status.addPermanentWidget(badge)

    # ---- Page 0: Apps & Launchpad ----
    def _build_apps_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(22, 18, 22, 22)
        lay.setSpacing(16)

        hdr_row = QHBoxLayout()
        t = QLabel("KinoSuite Applications")
        t.setObjectName("SectionTitle")
        hdr_row.addWidget(t)
        hdr_row.addStretch(1)
        b_reg = QPushButton("+ Register Custom App")
        b_reg.clicked.connect(self._register_custom_app)
        b_suite_dir = QPushButton("Open Suite Folder")
        b_suite_dir.clicked.connect(lambda: self._open_in_explorer(self.suite_root))
        hdr_row.addWidget(b_reg)
        hdr_row.addWidget(b_suite_dir)
        lay.addLayout(hdr_row)

        drop = FileDropZone()
        drop.filesDropped.connect(self.open_files_smart)
        drop.browseClicked.connect(self._browse_any_file)
        lay.addWidget(drop)

        self.apps_grid = QGridLayout()
        self.apps_grid.setSpacing(14)
        lay.addLayout(self.apps_grid)
        lay.addStretch(1)

        scroll.setWidget(inner)
        return scroll

    def _populate_apps_grid(self) -> None:
        while self.apps_grid.count():
            it = self.apps_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        while self.quick_launch_box.count():
            it = self.quick_launch_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.app_cards.clear()

        q = self.ed_global_search.text().strip().lower()
        visible = [a for a in self.apps if not q or q in a.name.lower() or q in a.category.lower() or q in a.tagline.lower()]
        for i, app in enumerate(visible):
            card = AppCardWidget(app)
            card.launchRequested.connect(self.launch_app_by_id)
            card.openFileRequested.connect(self.open_file_for_app)
            card.openFolderRequested.connect(self._open_app_folder)
            card.stopRequested.connect(self.stop_app_by_id)
            self.apps_grid.addWidget(card, i // 2, i % 2)
            self.app_cards[app.app_id] = card

        for app in self.apps:
            qb = QPushButton(f"  {app.monogram}  {app.name}")
            qb.setStyleSheet(f"QPushButton {{ text-align:left; padding:5px 8px; border-left: 3px solid {app.accent}; }}")
            qb.clicked.connect(lambda _=False, aid=app.app_id: self.launch_app_by_id(aid))
            self.quick_launch_box.addWidget(qb)

    # ---- Page 1: Projects & KinoCloud ----
    def _build_projects_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        top = QHBoxLayout()
        t = QLabel("Recent Projects & KinoCloud Assets")
        t.setObjectName("SectionTitle")
        top.addWidget(t)
        top.addStretch(1)
        self.cmb_proj_filter = QComboBox()
        self.cmb_proj_filter.addItems(["All Apps", "KinoCut", "KinoShop", "KinoDraw", "KinoWave", "KinoFill", "KinoPixel"])
        self.cmb_proj_filter.currentTextChanged.connect(self._render_projects_table)
        top.addWidget(self.cmb_proj_filter)
        lay.addLayout(top)

        self.tbl_projects = QTableWidget(0, 5)
        self.tbl_projects.setHorizontalHeaderLabels(["File / Project", "App", "Source", "Modified", "Path"])
        self.tbl_projects.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_projects.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_projects.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_projects.cellDoubleClicked.connect(lambda _r, _c: self._open_selected_project())
        lay.addWidget(self.tbl_projects, 1)

        brow = QHBoxLayout()
        b_open = QPushButton("Open in App")
        b_open.setObjectName("PrimaryButton")
        b_open.clicked.connect(self._open_selected_project)
        b_rev = QPushButton("Reveal in Explorer")
        b_rev.clicked.connect(self._reveal_selected_project)
        brow.addWidget(b_open)
        brow.addWidget(b_rev)
        brow.addStretch(1)
        lay.addLayout(brow)
        return w

    # ---- Page 2: Processes & Plugins ----
    def _build_processes_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        top = QHBoxLayout()
        t = QLabel("Running KinoSuite Processes")
        t.setObjectName("SectionTitle")
        top.addWidget(t)
        top.addStretch(1)
        b_all = QPushButton("Launch All Installed Apps")
        b_all.setObjectName("PrimaryButton")
        b_all.clicked.connect(self.launch_all_apps)
        b_kill_sel = QPushButton("Stop Selected")
        b_kill_sel.setObjectName("DangerButton")
        b_kill_sel.clicked.connect(self._stop_selected_process)
        b_kill_all = QPushButton("Stop All Running")
        b_kill_all.setObjectName("DangerButton")
        b_kill_all.clicked.connect(self.stop_all_apps)
        top.addWidget(b_all)
        top.addWidget(b_kill_sel)
        top.addWidget(b_kill_all)
        lay.addLayout(top)

        self.tbl_procs = QTableWidget(0, 4)
        self.tbl_procs.setHorizontalHeaderLabels(["Application", "PID", "Process Image", "Memory (MB)"])
        self.tbl_procs.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_procs.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_procs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_procs.setMaximumHeight(220)
        lay.addWidget(self.tbl_procs)

        t2 = QLabel("Cross-Suite Plugin & Extension Inventory (VST3, VST2, Nyquist, Python)")
        t2.setObjectName("SectionTitle")
        lay.addWidget(t2)

        self.tbl_plugins = QTableWidget(0, 4)
        self.tbl_plugins.setHorizontalHeaderLabels(["Kino App", "Plugin Name", "Format", "Path"])
        self.tbl_plugins.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_plugins.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tbl_plugins, 1)
        return w

    # ---- Page 3: Workflows & Build/Test Runner ----
    def _build_workflows_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(14)

        t = QLabel("Cross-App Studio Workflows")
        t.setObjectName("SectionTitle")
        lay.addWidget(t)

        wgrid = QGridLayout()
        wgrid.setSpacing(12)
        workflows = [
            ("Video + Audio Mastering", "Launch KinoCut & KinoWave side-by-side for soundtrack mixing & sound design.", ["kinocut", "kinowave"], "#FF4D6D"),
            ("Vector + Photo Design", "Launch KinoDraw & KinoShop together for brand assets, posters, and retouching.", ["kinodraw", "kinoshop"], "#FF9A00"),
            ("Retro Game + Chiptune Dev", "Launch KinoPixel & KinoWave together to craft GB/GBC/GBA sprites, SFX, and playable .gba ROMs.", ["kinopixel", "kinowave"], "#8B5CF6"),
            ("Complete KinoSuite Studio", "Launch all 6 KinoSuite creative studios at once.", ["kinocut", "kinoshop", "kinodraw", "kinowave", "kinofill", "kinopixel"], "#00C2FF"),
        ]
        for i, (title, desc, ids, col) in enumerate(workflows):
            card = QFrame()
            card.setObjectName("AppCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.addWidget(QLabel(f"<b style='font-size:10.5pt; color:{col};'>{title}</b>"))
            dl = QLabel(desc); dl.setWordWrap(True); dl.setObjectName("MutedText")
            cl.addWidget(dl, 1)
            btn = QPushButton("Launch Workflow")
            btn.clicked.connect(lambda _=False, app_ids=ids: self._launch_workflow(app_ids))
            cl.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
            wgrid.addWidget(card, i // 2, i % 2)
        lay.addLayout(wgrid)

        t2 = QLabel("Suite Diagnostics — Run App Test Suite or Rebuild Native Launcher")
        t2.setObjectName("SectionTitle")
        lay.addWidget(t2)

        trow = QHBoxLayout()
        self.cmb_tool_app = QComboBox()
        for a in self.apps:
            self.cmb_tool_app.addItem(a.name, a.app_id)
        b_test = QPushButton("Run App Verification Tests")
        b_test.setObjectName("PrimaryButton")
        b_test.clicked.connect(self._run_app_tests)
        b_build = QPushButton("Rebuild App Launcher (.exe)")
        b_build.clicked.connect(self._rebuild_app_launcher)
        trow.addWidget(self.cmb_tool_app)
        trow.addWidget(b_test)
        trow.addWidget(b_build)
        trow.addStretch(1)
        lay.addLayout(trow)

        self.txt_console = QPlainTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setPlaceholderText("Command output from app verification tests and launcher builds appears here...")
        self.txt_console.setStyleSheet("font-family: Consolas, monospace; font-size: 8.5pt;")
        lay.addWidget(self.txt_console, 1)
        return w

    # ---- Page 4: Suite Health & Settings ----
    def _build_settings_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        t = QLabel("Suite Environment Health & Settings")
        t.setObjectName("SectionTitle")
        lay.addWidget(t)

        opt_row = QHBoxLayout()
        self.cb_tray = QCheckBox("Minimize to Windows System Tray on close (quick-launch menu stays active)")
        self.cb_tray.setChecked(bool(self.cfg.data.get("minimize_to_tray", True)))
        self.cb_tray.toggled.connect(lambda v: (self.cfg.data.__setitem__("minimize_to_tray", v), self.cfg.save()))
        opt_row.addWidget(self.cb_tray, 1)

        b_sc = QPushButton("Create Desktop Shortcut for KinoSuite")
        b_sc.setObjectName("PrimaryButton")
        b_sc.clicked.connect(self._create_desktop_shortcut)
        opt_row.addWidget(b_sc)
        lay.addLayout(opt_row)

        self.tbl_health = QTableWidget(0, 3)
        self.tbl_health.setHorizontalHeaderLabels(["Component", "Status", "Path / Details"])
        self.tbl_health.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tbl_health, 1)
        return w

    # ---- System Tray ----
    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(make_suite_icon(32), self)
        self._tray.setToolTip("KinoSuite Hub — Creative Suite Launcher")
        menu = QMenu()
        menu.addAction("Open KinoSuite Hub", self._restore_from_tray)
        menu.addSeparator()
        for a in self.apps:
            menu.addAction(f"Launch {a.name}", lambda _=False, aid=a.app_id: self.launch_app_by_id(aid))
        menu.addSeparator()
        menu.addAction("Quit KinoSuite Hub", self._force_quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda reason: self._restore_from_tray() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self._tray.show()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _force_quit(self) -> None:
        if self._tray:
            self._tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self.cfg.data.get("minimize_to_tray", True) and self._tray and self._tray.isVisible():
            event.ignore()
            self.hide()
            self._tray.showMessage("KinoSuite Hub", "Still running in the system tray for quick app launching.", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            super().closeEvent(event)

    # ---- Navigation & Theme ----
    def _switch_page(self, idx: int) -> None:
        self.pages.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_btns):
            b.setChecked(i == idx)

    def _apply_theme(self, theme_name: str) -> None:
        self.cfg.data["theme"] = theme_name
        self.cfg.save()
        app = QApplication.instance()
        if app:
            app.setStyleSheet(KINOSUITE_HUB_LIGHT if theme_name == "Light" else KINOSUITE_HUB_DARK)
        self.btn_theme.setText("Dark Mode" if theme_name == "Light" else "Light Mode")

    def _toggle_theme(self) -> None:
        cur = self.cfg.data.get("theme", "Dark")
        self._apply_theme("Light" if cur == "Dark" else "Dark")

    # ---- Refresh & Search ----
    def refresh_all(self) -> None:
        self.apps = discover_suite_apps(self.suite_root, self.cfg)
        self._populate_apps_grid()
        self.refresh_processes()
        self._all_projects = collect_suite_projects(self.apps, self.cfg)
        self._render_projects_table()
        self._all_plugins = collect_suite_plugins(self.apps)
        self._render_plugins_table()
        self._render_health_table()
        self.lbl_status.setText(f"Discovered {sum(1 for a in self.apps if a.installed)}/{len(self.apps)} KinoSuite apps · {len(self._all_projects)} cloud/recent files · {len(self._all_plugins)} plugins")

    def refresh_processes(self) -> None:
        self.running_rows = query_running_kino_processes(self.apps, self.tracked_procs)
        by_app: Dict[str, List[int]] = {}
        for r in self.running_rows:
            by_app.setdefault(r["app"], []).append(r["pid"])
        for app in self.apps:
            card = self.app_cards.get(app.app_id)
            if card:
                card.set_running_pids(by_app.get(app.name, []))
        self.lbl_running_summary.setText(f"{len(self.running_rows)} active process(es)")

        self.tbl_procs.setRowCount(len(self.running_rows))
        for i, r in enumerate(self.running_rows):
            self.tbl_procs.setItem(i, 0, QTableWidgetItem(r["app"]))
            self.tbl_procs.setItem(i, 1, QTableWidgetItem(str(r["pid"])))
            self.tbl_procs.setItem(i, 2, QTableWidgetItem(r["image"]))
            self.tbl_procs.setItem(i, 3, QTableWidgetItem(f"{r['mem_mb']:.1f} MB"))

    def _render_projects_table(self) -> None:
        q = self.ed_global_search.text().strip().lower()
        filt = self.cmb_proj_filter.currentText()
        app_map = {a.app_id: a.name for a in self.apps}
        rows = [
            p for p in self._all_projects
            if (filt == "All Apps" or app_map.get(p["app_id"], "") == filt)
            and (not q or q in p["name"].lower() or q in p["path"].lower())
        ]
        self.tbl_projects.setRowCount(len(rows))
        for i, p in enumerate(rows):
            it0 = QTableWidgetItem(p["name"])
            it0.setData(Qt.ItemDataRole.UserRole, p)
            self.tbl_projects.setItem(i, 0, it0)
            self.tbl_projects.setItem(i, 1, QTableWidgetItem(app_map.get(p["app_id"], p["app_id"])))
            self.tbl_projects.setItem(i, 2, QTableWidgetItem(p["source"]))
            self.tbl_projects.setItem(i, 3, QTableWidgetItem(p["updated"]))
            self.tbl_projects.setItem(i, 4, QTableWidgetItem(p["path"]))

    def _render_plugins_table(self) -> None:
        q = self.ed_global_search.text().strip().lower()
        rows = [p for p in self._all_plugins if not q or q in p["name"].lower() or q in p["app"].lower() or q in p["kind"].lower()]
        self.tbl_plugins.setRowCount(len(rows))
        for i, p in enumerate(rows):
            self.tbl_plugins.setItem(i, 0, QTableWidgetItem(p["app"]))
            self.tbl_plugins.setItem(i, 1, QTableWidgetItem(p["name"]))
            self.tbl_plugins.setItem(i, 2, QTableWidgetItem(p["kind"]))
            self.tbl_plugins.setItem(i, 3, QTableWidgetItem(p["path"]))

    def _render_health_table(self) -> None:
        rows = check_environment_health(self.suite_root, self.apps)
        self.tbl_health.setRowCount(len(rows))
        for i, (comp, st, det) in enumerate(rows):
            self.tbl_health.setItem(i, 0, QTableWidgetItem(comp))
            st_item = QTableWidgetItem(st)
            st_item.setForeground(QColor("#10D9A0" if st in ("OK", "READY") else ("#F59E0B" if st == "OPTIONAL" else "#F43F5E")))
            self.tbl_health.setItem(i, 1, st_item)
            self.tbl_health.setItem(i, 2, QTableWidgetItem(det))

    def _on_search_changed(self) -> None:
        self._populate_apps_grid()
        self._render_projects_table()
        self._render_plugins_table()

    def _on_search_enter(self) -> None:
        q = self.ed_global_search.text().strip().lower()
        if not q:
            return
        for a in self.apps:
            if q in a.name.lower() or q == a.monogram.lower():
                self.launch_app_by_id(a.app_id)
                return

    # ---- App Actions & Routing ----
    def _app_by_id(self, app_id: str) -> Optional[KinoAppInfo]:
        return next((a for a in self.apps if a.app_id == app_id), None)

    def launch_app_by_id(self, app_id: str, file_args: Optional[List[str]] = None) -> None:
        app = self._app_by_id(app_id)
        if not app:
            return
        try:
            proc = launch_kino_app(app, file_args=file_args)
            self.tracked_procs[proc.pid] = app.name
            if file_args:
                for fp in file_args:
                    self.cfg.add_recent(fp, app.app_id)
            self.lbl_status.setText(f"Launched {app.name} (PID {proc.pid})")
            QTimer.singleShot(800, self.refresh_processes)
        except Exception as e:
            QMessageBox.critical(self, f"Failed to Launch {app.name}", str(e))

    def open_file_for_app(self, app_id: str) -> None:
        app = self._app_by_id(app_id)
        if not app:
            return
        flt = " ".join(f"*{e}" for e in app.extensions) if app.extensions else "*.*"
        fp, _ = QFileDialog.getOpenFileName(self, f"Open File in {app.name}", "", f"{app.name} Files ({flt});;All Files (*.*)")
        if fp:
            self.launch_app_by_id(app_id, [fp])
            self._all_projects = collect_suite_projects(self.apps, self.cfg)
            self._render_projects_table()

    def _browse_any_file(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Open Any Creative File in KinoSuite", "", "All Files (*.*)")
        if fp:
            self.open_files_smart([fp])

    def open_files_smart(self, paths: List[str]) -> None:
        for fp in paths:
            app = route_file_to_app(fp, self.apps)
            if app:
                self.launch_app_by_id(app.app_id, [fp])
            else:
                QMessageBox.information(self, "Unknown File Type", f"No KinoSuite app registered for '{os.path.basename(fp)}'.")
        self._all_projects = collect_suite_projects(self.apps, self.cfg)
        self._render_projects_table()

    def _open_selected_project(self) -> None:
        r = self.tbl_projects.currentRow()
        if r < 0:
            return
        it = self.tbl_projects.item(r, 0)
        if not it:
            return
        d = it.data(Qt.ItemDataRole.UserRole)
        if d and os.path.isfile(d["path"]):
            aid = d.get("app_id", "")
            if self._app_by_id(aid):
                self.launch_app_by_id(aid, [d["path"]])
            else:
                self.open_files_smart([d["path"]])

    def _reveal_selected_project(self) -> None:
        r = self.tbl_projects.currentRow()
        if r >= 0 and self.tbl_projects.item(r, 4):
            fp = self.tbl_projects.item(r, 4).text()
            if os.path.exists(fp):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(fp)])

    def _open_app_folder(self, app_id: str) -> None:
        app = self._app_by_id(app_id)
        if app:
            self._open_in_explorer(app.folder)

    def _open_in_explorer(self, path: str) -> None:
        if os.path.exists(path):
            os.startfile(path)

    def stop_app_by_id(self, app_id: str) -> None:
        app = self._app_by_id(app_id)
        if not app:
            return
        killed = 0
        for r in list(self.running_rows):
            if r["app"] == app.name:
                if terminate_process(r["pid"]):
                    killed += 1
        self.lbl_status.setText(f"Stopped {killed} process(es) for {app.name}")
        QTimer.singleShot(500, self.refresh_processes)

    def _stop_selected_process(self) -> None:
        r = self.tbl_procs.currentRow()
        if 0 <= r < len(self.running_rows):
            pid = self.running_rows[r]["pid"]
            terminate_process(pid)
            QTimer.singleShot(400, self.refresh_processes)

    def stop_all_apps(self) -> None:
        for r in list(self.running_rows):
            terminate_process(r["pid"])
        self.lbl_status.setText("Stopped all running KinoSuite apps")
        QTimer.singleShot(500, self.refresh_processes)

    def launch_all_apps(self) -> None:
        for a in self.apps:
            if a.installed:
                self.launch_app_by_id(a.app_id)

    def _launch_workflow(self, app_ids: List[str]) -> None:
        for aid in app_ids:
            app = self._app_by_id(aid)
            if app and app.installed:
                self.launch_app_by_id(aid)

    def _run_app_tests(self) -> None:
        app = self._app_by_id(str(self.cmb_tool_app.currentData()))
        if not app or not app.test_script:
            self.txt_console.setPlainText(f"No verification test script found for {app.name if app else 'selected app'}.")
            return
        py = find_python_executable(windowed=False)
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        self.txt_console.setPlainText(f"Running {app.test_script} ...\n")
        QApplication.processEvents()
        proc = subprocess.run([py, app.test_script], cwd=app.folder, env=env, capture_output=True, text=True, timeout=90)
        self.txt_console.appendPlainText(proc.stdout + "\n" + proc.stderr)
        self.txt_console.appendPlainText(f"\nExit code: {proc.returncode}")

    def _rebuild_app_launcher(self) -> None:
        app = self._app_by_id(str(self.cmb_tool_app.currentData()))
        if not app or not app.build_script:
            self.txt_console.setPlainText(f"No build script found for {app.name if app else 'selected app'}.")
            return
        self.txt_console.setPlainText(f"Running {app.build_script} ...\n")
        QApplication.processEvents()
        if app.build_script.endswith(".ps1"):
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", app.build_script]
        else:
            cmd = [find_python_executable(windowed=False), app.build_script]
        proc = subprocess.run(cmd, cwd=app.folder, capture_output=True, text=True, timeout=180)
        self.txt_console.appendPlainText(proc.stdout + "\n" + proc.stderr)
        self.txt_console.appendPlainText(f"\nExit code: {proc.returncode}")
        self.refresh_all()

    def _register_custom_app(self) -> None:
        dlg = RegisterAppDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry = dlg.to_entry()
            customs = list(self.cfg.data.get("custom_apps", []))
            customs.append(entry)
            self.cfg.data["custom_apps"] = customs
            self.cfg.save()
            self.refresh_all()

    def _create_desktop_shortcut(self) -> None:
        target = os.path.join(self.suite_root, "KinoSuite.exe")
        if not os.path.isfile(target):
            QMessageBox.warning(self, "Missing Launcher", f"{target} not found yet.")
            return
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        lnk = os.path.join(desktop, "KinoSuite.lnk")
        ps = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{lnk}"); '
            f'$s.TargetPath = "{target}"; '
            f'$s.WorkingDirectory = "{self.suite_root}"; '
            f'$s.IconLocation = "{target},0"; '
            f'$s.Save()'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=15)
        QMessageBox.information(self, "Shortcut Created", f"Created Desktop shortcut:\n{lnk}")
