"""KinoPixel Main Window — KinoSuite Architectural Design + Start-to-Finish GB/GBC/GBA Game Studio."""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QImageReader, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .audio_sfx import ChiptuneAudioPlayer
from .icons import make_app_pixmap, make_icon
from .models import KinoPixelProject, SpriteAsset
from .sample_project import create_starter_project
from .studio_pages import (
    ButtonWiringPage,
    LevelEditorPage,
    PlaytestBuildPage,
    SfxEditorPage,
    SpriteEditorPage,
)
from .theme import get_theme_stylesheet


class KinoPixelWindow(QMainWindow):
    """Main KinoPixel Retro Handheld Game Creation Window (KinoSuite)."""

    def __init__(self, initial_files: Optional[List[str]] = None, load_starter: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("KinoPixel — KinoSuite Retro Game Studio")
        self.setWindowIcon(QIcon(make_app_pixmap(64)))
        self.resize(1480, 900)

        if getattr(sys, "frozen", False):
            self.app_root = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.audio = ChiptuneAudioPlayer()
        self.projects: List[KinoPixelProject] = []
        self.current_theme: str = "Dark"
        self.toolbars: Dict[str, QToolBar] = {}

        self._build_central_workspace()
        self._build_toolbars()
        self._build_inspector_dock()
        self._build_menus()
        self._apply_theme("Dark")

        opened = False
        if initial_files:
            for fp in initial_files:
                if os.path.isfile(fp) and fp.lower().endswith(".kpx"):
                    self.open_path(fp)
                    opened = True
                elif os.path.isfile(fp) and os.path.splitext(fp)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                    self.open_sprite_image(fp)
                    opened = True
        if not opened:
            if load_starter:
                self._add_project_tab(create_starter_project("GBA Platformer"))
            else:
                self._add_project_tab(create_starter_project("GBA Platformer"))

    # ------------------------------------------------------------------
    # Active Project Helpers
    # ------------------------------------------------------------------
    def current_project(self) -> Optional[KinoPixelProject]:
        idx = self.proj_tabs.currentIndex()
        if 0 <= idx < len(self.projects):
            return self.projects[idx]
        return None

    def _add_project_tab(self, proj: KinoPixelProject) -> None:
        self.projects.append(proj)
        dummy = QWidget()
        idx = self.proj_tabs.addTab(dummy, f"{proj.title} [{proj.target_system}]")
        self.proj_tabs.setCurrentIndex(idx)
        self._bind_project_to_pages(proj)

    def _bind_project_to_pages(self, proj: KinoPixelProject) -> None:
        self.page_sprite.set_project(proj)
        self.page_level.set_project(proj)
        self.page_wiring.set_project(proj)
        self.page_sfx.set_project(proj)
        self.page_play.set_project(proj)
        self._sync_header_and_inspector()

    # ------------------------------------------------------------------
    # Central Workspace (Multi-Project Tabs + 5-Stage Studio Workflow)
    # ------------------------------------------------------------------
    def _build_central_workspace(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Multi-project document tabs (matching KinoWave)
        self.proj_tabs = QTabWidget()
        self.proj_tabs.setDocumentMode(True)
        self.proj_tabs.setTabsClosable(True)
        self.proj_tabs.setMaximumHeight(30)
        self.proj_tabs.currentChanged.connect(self._on_project_tab_changed)
        self.proj_tabs.tabCloseRequested.connect(self._close_project_tab)
        root.addWidget(self.proj_tabs)

        # 5-Stage Start-to-Finish Studio Tabs
        self.stage_tabs = QTabWidget()
        self.stage_tabs.setDocumentMode(True)
        self.page_sprite = SpriteEditorPage()
        self.page_level = LevelEditorPage()
        self.page_wiring = ButtonWiringPage()
        self.page_sfx = SfxEditorPage(self.audio)
        self.page_play = PlaytestBuildPage(self.audio)

        for pg in (self.page_sprite, self.page_level, self.page_wiring, self.page_sfx, self.page_play):
            pg.projectModified.connect(self._on_project_modified)
        self.page_play.romBuilt.connect(self._on_rom_built)

        self.stage_tabs.addTab(self.page_sprite, make_icon("sprite", 16), "1. Sprites & Animation")
        self.stage_tabs.addTab(self.page_level, make_icon("map", 16), "2. Tiles & Level Map")
        self.stage_tabs.addTab(self.page_wiring, make_icon("gamepad", 16), "3. Logic & KinoScript")
        self.stage_tabs.addTab(self.page_sfx, make_icon("sfx", 16), "4. Chiptune & Sequence Genie")
        self.stage_tabs.addTab(self.page_play, make_icon("cartridge", 16), "5. Playtest & Build ROM")
        self.stage_tabs.currentChanged.connect(self._on_stage_changed)
        root.addWidget(self.stage_tabs, 1)

        # KinoSuite Status Bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_status_info = QLabel("Ready — Native ARM7TDMI GBA / GB / GBC Cartridge Studio")
        self.status.addWidget(self.lbl_status_info, 1)
        self.lbl_target_badge = QLabel("TARGET · GBA 240×160")
        self.lbl_target_badge.setObjectName("TargetBadge")
        self.status.addPermanentWidget(self.lbl_target_badge)
        suite_badge = QLabel("KINOSUITE · KINOPIXEL")
        suite_badge.setObjectName("SuiteBadge")
        self.status.addPermanentWidget(suite_badge)

    # ------------------------------------------------------------------
    # KinoSuite Top Toolbars
    # ------------------------------------------------------------------
    def _build_toolbars(self) -> None:
        self.setDockNestingEnabled(True)

        tb_file = QToolBar("Project Toolbar", self)
        tb_file.setObjectName("ProjectToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_file)
        self.toolbars["Project"] = tb_file

        for ic, tip, fn in [
            ("new", "New Game from Template (Ctrl+N)", self.new_project_dialog),
            ("open", "Open Project (.kpx) (Ctrl+O)", self.open_file_dialog),
            ("save", "Save Project (Ctrl+S)", self.save_project),
            ("undo", "Undo (Ctrl+Z)", self.do_undo),
            ("redo", "Redo (Ctrl+Y)", self.do_redo),
        ]:
            b = QToolButton()
            b.setIcon(make_icon(ic, 20))
            b.setToolTip(tip)
            b.setFixedSize(30, 28)
            b.clicked.connect(fn)
            tb_file.addWidget(b)

        tb_hw = QToolBar("Target & Build Toolbar", self)
        tb_hw.setObjectName("BuildToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_hw)
        self.toolbars["Build"] = tb_hw

        tb_hw.addWidget(QLabel(" Target: "))
        self.cmb_tb_target = QComboBox()
        self.cmb_tb_target.setFixedWidth(180)
        self.cmb_tb_target.addItem("GBA (240×160 · 16-color)", "GBA")
        self.cmb_tb_target.addItem("GBC (160×144 · 4-color)", "GBC")
        self.cmb_tb_target.addItem("GB Classic (160×144 · DMG)", "GB")
        self.cmb_tb_target.currentIndexChanged.connect(self._on_toolbar_target_changed)
        tb_hw.addWidget(self.cmb_tb_target)

        tb_hw.addSeparator()
        b_play = QPushButton("▶  Playtest")
        b_play.setObjectName("PlayButton")
        b_play.setFixedHeight(26)
        b_play.clicked.connect(self.launch_playtest)
        tb_hw.addWidget(b_play)

        b_build = QPushButton("Build .gba ROM")
        b_build.setIcon(make_icon("cartridge", 16, color="#FFFFFF"))
        b_build.setObjectName("PrimaryButton")
        b_build.setFixedHeight(26)
        b_build.clicked.connect(self.build_gba_rom_action)
        tb_hw.addWidget(b_build)

        tb_hw.addSeparator()
        tb_hw.addWidget(QLabel(" Theme: "))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["Dark", "Light", "High Contrast"])
        self.cmb_theme.currentTextChanged.connect(self._apply_theme)
        tb_hw.addWidget(self.cmb_theme)

    # ------------------------------------------------------------------
    # Right Collapsible KinoSuite Studio Inspector Dock
    # ------------------------------------------------------------------
    def _build_inspector_dock(self) -> None:
        self.dock_inspector = QDockWidget("KinoPixel Studio Inspector", self)
        self.dock_inspector.setObjectName("StudioInspectorDock")
        self.dock_inspector.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.dock_inspector.setMinimumWidth(240)
        self.dock_inspector.setMaximumWidth(320)

        w = QWidget()
        w.setObjectName("StudioPanel")
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(7)

        h_hw = QLabel("CARTRIDGE HARDWARE BUDGET")
        h_hw.setObjectName("SectionHeader")
        lay.addWidget(h_hw)

        self.pb_bg = QProgressBar()
        self.pb_bg.setFormat("BG Tiles: %v / %m")
        lay.addWidget(self.pb_bg)

        self.pb_obj = QProgressBar()
        self.pb_obj.setFormat("OBJ Tiles: %v / %m")
        lay.addWidget(self.pb_obj)

        self.pb_oam = QProgressBar()
        self.pb_oam.setFormat("OAM Sprites: %v / %m")
        lay.addWidget(self.pb_oam)

        self.lbl_rules_stat = QLabel("Button Rules: 0 active")
        self.lbl_rules_stat.setStyleSheet("color:#A78BFA; font-weight:600; font-size:8.5pt;")
        lay.addWidget(self.lbl_rules_stat)

        h_hist = QLabel("UNDO HISTORY")
        h_hist.setObjectName("SectionHeader")
        lay.addWidget(h_hist)

        self.lst_history = QListWidget()
        self.lst_history.itemClicked.connect(lambda it: self._restore_history(self.lst_history.row(it)))
        lay.addWidget(self.lst_history, 1)

        b_play = QPushButton("▶  Live Playtest")
        b_play.setObjectName("PlayButton")
        b_play.clicked.connect(self.launch_playtest)
        lay.addWidget(b_play)

        b_rom = QPushButton("Build Playable .gba ROM...")
        b_rom.setObjectName("PrimaryButton")
        b_rom.clicked.connect(self.build_gba_rom_action)
        lay.addWidget(b_rom)

        self.dock_inspector.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_inspector)

    # ------------------------------------------------------------------
    # KinoSuite Menu Bar
    # ------------------------------------------------------------------
    def _act(self, text: str, slot, shortcut: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        return a

    def _build_menus(self) -> None:
        mb = self.menuBar()

        m_file = mb.addMenu("&File")
        m_tpl = m_file.addMenu("New from Starter Template")
        for tpl in [
            "GBA Platformer (Starbit)",
            "GBA Sci-Fi Exploration (BSL Sector)",
            "GBA Action-RPG (Legacy Quest)",
            "GBA Space Action (Omega Wing)",
            "GBA Tactical Grid (Advance Ops)",
            "GBC Adventure",
            "GB Classic (DMG)",
        ]:
            m_tpl.addAction(tpl, lambda _=False, t=tpl: self._add_project_tab(create_starter_project(t)))
        m_file.addAction(self._act("Open Project (.kpx)...", self.open_file_dialog, "Ctrl+O"))
        m_file.addAction(self._act("Save Project", self.save_project, "Ctrl+S"))
        m_file.addAction(self._act("Save Project As...", self.save_project_as, "Ctrl+Shift+S"))
        m_file.addSeparator()
        m_file.addAction(self._act("Build Playable .gba ROM...", self.build_gba_rom_action, "Ctrl+B"))
        m_file.addAction(self._act("Export Native .gb / .gbc ROM...", self.page_play.build_gb_dialog))
        m_file.addAction(self._act("Export C Assets Header (.h)...", self.page_play.export_c_dialog))
        m_file.addSeparator()
        m_file.addAction(self._act("Exit", self.close, "Ctrl+Q"))

        m_edit = mb.addMenu("&Edit")
        m_edit.addAction(self._act("Undo", self.do_undo, "Ctrl+Z"))
        m_edit.addAction(self._act("Redo", self.do_redo, "Ctrl+Y"))

        m_stage = mb.addMenu("&Studio")
        for idx, lbl in enumerate([
            "1. Sprites & Animation",
            "2. Tiles & Level Map",
            "3. Button Wiring",
            "4. Chiptune SFX",
            "5. Playtest & Build ROM",
        ]):
            m_stage.addAction(self._act(lbl, lambda _=False, i=idx: self.stage_tabs.setCurrentIndex(i), f"Ctrl+{idx + 1}"))
        m_stage.addSeparator()
        m_stage.addAction(self._act("Start / Focus Live Playtest", self.launch_playtest, "F5"))

        m_view = mb.addMenu("&View")
        m_view.addAction(self.dock_inspector.toggleViewAction())
        m_th = m_view.addMenu("Theme")
        for th in ("Dark", "Light", "High Contrast"):
            m_th.addAction(th, lambda _=False, t=th: self._apply_theme(t))

        m_help = mb.addMenu("&Help")
        m_help.addAction("About KinoPixel (KinoSuite)...", self._show_about)

    # ------------------------------------------------------------------
    # State Synchronization & Actions
    # ------------------------------------------------------------------
    def _apply_theme(self, name: str) -> None:
        self.current_theme = name
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_theme_stylesheet(name))
        self.page_sprite.canvas.theme_name = name
        self.page_level.tile_canvas.theme_name = name
        self.page_level.map_canvas.theme_name = name
        self.cmb_theme.blockSignals(True)
        self.cmb_theme.setCurrentText(name)
        self.cmb_theme.blockSignals(False)
        self.update()

    def _on_project_tab_changed(self, idx: int) -> None:
        if 0 <= idx < len(self.projects):
            self.page_play.stop_playtest()
            self._bind_project_to_pages(self.projects[idx])

    def _close_project_tab(self, idx: int) -> None:
        if len(self.projects) <= 1:
            return
        self.projects.pop(idx)
        self.proj_tabs.removeTab(idx)

    def _on_stage_changed(self, idx: int) -> None:
        proj = self.current_project()
        if not proj:
            return
        if idx != 3:
            self.page_sfx.stop_audio()
        if idx != 4:
            self.page_play.stop_playtest()
        if idx == 0:
            self.page_sprite.refresh_all()
        elif idx == 1:
            self.page_level.refresh_all()
        elif idx == 2:
            self.page_wiring.refresh_all()
        elif idx == 3:
            self.page_sfx.refresh_all()
        elif idx == 4:
            self.page_play.set_project(proj)

    def _on_project_modified(self, label: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        proj.snapshot_push(label)
        self._sync_header_and_inspector()
        self.lbl_status_info.setText(f"Updated: {label}")

    def _sync_header_and_inspector(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        idx = self.proj_tabs.currentIndex()
        mark = "*" if proj.dirty else ""
        if idx >= 0:
            self.proj_tabs.setTabText(idx, f"{proj.title}{mark} [{proj.target_system}]")

        prof = proj.profile()
        self.lbl_target_badge.setText(f"TARGET · {proj.target_system} {prof['width']}×{prof['height']}")
        self.cmb_tb_target.blockSignals(True)
        ti = self.cmb_tb_target.findData(proj.target_system)
        if ti >= 0:
            self.cmb_tb_target.setCurrentIndex(ti)
        self.cmb_tb_target.blockSignals(False)

        stats = proj.hardware_stats()
        self.pb_bg.setMaximum(stats["bg_tiles_max"])
        self.pb_bg.setValue(min(stats["bg_tiles"], stats["bg_tiles_max"]))
        self.pb_obj.setMaximum(stats["obj_tiles_max"])
        self.pb_obj.setValue(min(stats["obj_tiles"], stats["obj_tiles_max"]))
        self.pb_oam.setMaximum(stats["oam_sprites_max"])
        self.pb_oam.setValue(min(stats["oam_sprites"], stats["oam_sprites_max"]))
        self.lbl_rules_stat.setText(f"Button Rules: {stats['rules_count']} wired · {len(proj.sfx_list)} PSG SFX")

        labels, h_idx = proj.history_labels()
        self.lst_history.blockSignals(True)
        self.lst_history.clear()
        for i, h_lbl in enumerate(labels):
            prefix = "▶ " if i == h_idx else "   "
            self.lst_history.addItem(f"{prefix}{h_lbl}")
        if 0 <= h_idx < self.lst_history.count():
            self.lst_history.setCurrentRow(h_idx)
        self.lst_history.blockSignals(False)

    def _on_toolbar_target_changed(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        new_t = str(self.cmb_tb_target.currentData())
        if proj.target_system != new_t:
            proj.target_system = new_t
            proj.snapshot_push(f"Switch Hardware ({new_t})")
            self._bind_project_to_pages(proj)

    def _restore_history(self, idx: int) -> None:
        proj = self.current_project()
        if proj and proj.restore_history_index(idx):
            self._bind_project_to_pages(proj)
            self.lbl_status_info.setText("Restored history state")

    def do_undo(self) -> None:
        proj = self.current_project()
        if proj:
            lbl = proj.undo()
            if lbl:
                self._bind_project_to_pages(proj)
                self.lbl_status_info.setText(f"Undo → {lbl}")

    def do_redo(self) -> None:
        proj = self.current_project()
        if proj:
            lbl = proj.redo()
            if lbl:
                self._bind_project_to_pages(proj)
                self.lbl_status_info.setText(f"Redo → {lbl}")

    def new_project_dialog(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        tpls = [
            "GBA Platformer (Starbit)",
            "GBA Sci-Fi Exploration (BSL Sector)",
            "GBA Action-RPG (Legacy Quest)",
            "GBA Space Action (Omega Wing)",
            "GBA Tactical Grid (Advance Ops)",
            "GBC Adventure",
            "GB Classic (DMG)",
        ]
        choice, ok = QInputDialog.getItem(self, "New KinoPixel Game", "Choose Starter Template:", tpls, 0, False)
        if ok and choice:
            self._add_project_tab(create_starter_project(choice))

    def open_file_dialog(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Open KinoPixel Project", "", "KinoPixel Project (*.kpx)")
        if fp:
            self.open_path(fp)

    def open_sprite_image(self, path: str) -> None:
        reader = QImageReader(path)
        size = reader.size()
        if not size.isValid():
            QMessageBox.warning(self,"Open Sprite",reader.errorString())
            return
        size.scale(32,32,Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            QMessageBox.warning(self,"Open Sprite",reader.errorString())
            return
        proj = self.current_project()
        if proj is None:
            proj = create_starter_project("GBA Platformer")
            self._add_project_tab(proj)
        palette = [QColor(value).getRgb()[:3] for value in proj.get_palette_colors(0)[:proj.active_palette_size()]]
        pixels = []
        for y in range(image.height()):
            row = []
            for x in range(image.width()):
                red,green,blue,alpha = image.pixelColor(x,y).getRgb()
                index = min(range(1,len(palette)),key=lambda i: sum((a-b)**2 for a,b in zip((red,green,blue),palette[i]))) if alpha >= 128 else 0
                row.append(index)
            pixels.append(row)
        proj.sprites.append(SpriteAsset(name=os.path.splitext(os.path.basename(path))[0], role="prop",
                                       width=image.width(),height=image.height(),frames=[pixels]))
        self._bind_project_to_pages(proj)
        self.lbl_status_info.setText(f"Imported sprite from {os.path.basename(path)}")

    def open_path(self, fp: str) -> None:
        try:
            proj = KinoPixelProject.load_kpx(fp)
            self._add_project_tab(proj)
            self.lbl_status_info.setText(f"Opened {os.path.basename(fp)}")
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))

    def save_project(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        if not proj.file_path:
            self.save_project_as()
            return
        proj.save_kpx(proj.file_path)
        self._sync_header_and_inspector()
        self.lbl_status_info.setText(f"Saved {os.path.basename(proj.file_path)}")

    def save_project_as(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        safe = "".join(c if c.isalnum() else "_" for c in proj.title.lower()).strip("_") or "project"
        fp, _ = QFileDialog.getSaveFileName(self, "Save KinoPixel Project", f"{safe}.kpx", "KinoPixel Project (*.kpx)")
        if fp:
            if not fp.lower().endswith(".kpx"):
                fp += ".kpx"
            proj.save_kpx(fp)
            self._sync_header_and_inspector()
            self.lbl_status_info.setText(f"Saved {os.path.basename(fp)}")

    def launch_playtest(self) -> None:
        self.stage_tabs.setCurrentIndex(4)
        self.page_play.start_playtest()

    def build_gba_rom_action(self) -> None:
        self.stage_tabs.setCurrentIndex(4)
        self.page_play.build_gba_dialog()

    def _on_rom_built(self, rep) -> None:
        self.lbl_status_info.setText(f"Built {os.path.basename(rep.output_path)} ({rep.rom_size // 1024} KB · Checksum {rep.checksum_hex})")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About KinoPixel — KinoSuite",
            f"<h2 style='color:#A78BFA;'>KinoPixel v{__version__}</h2>"
            "<p><b>KinoSuite Universal GB / GBC / GBA Game Creation Studio</b></p>"
            "<p>Start-to-finish pixel art &amp; multi-size metasprites (16×16 to 64×64), multi-room "
            "worlds (up to 128 maps with slopes, water, ladders, switches &amp; BG2 parallax), "
            "4 native physics modes (Platformer, Action-RPG, Space Action, Tactical Grid), "
            "conditional button &amp; variable wiring, 5-voice Sequence Genie + DMA audio, "
            "live 60fps playtesting, native ARM7TDMI <code>.gba</code> ROM compilation (plus "
            "<code>.gb</code>/<code>.gbc</code> and full <code>devkitARM</code> C asset export).</p>",
        )
