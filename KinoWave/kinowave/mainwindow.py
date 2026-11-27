"""KinoWave Main Window — KinoSuite Visual Design Philosophy + Full Audacity Feature Set.

Lightweight, smooth, responsive, and fully functional multitrack audio platform.
Designed to run standalone or be embedded inside the KinoSuite ecosystem.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollBar,
    QSlider,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .audio_io import (
    AudioEngine,
    CrashRecoveryManager,
    KinoCloudAudioManager,
    export_audio_file,
    export_labels_txt,
    export_midi_file,
    import_audio_file,
    import_labels_txt,
    import_midi_file,
    import_raw_audio,
    list_audio_devices,
    list_audio_hosts,
    load_kwp,
    save_kwp,
)
from .automation import (
    MacroManager,
    NyquistInterpreter,
    PluginManager,
    PreferencesManager,
    ScriptingPipeServer,
    TRANSLATIONS,
    run_performance_benchmark,
)
from .dialogs import (
    CloudShareDialog,
    ContrastAnalysisDialog,
    DiagnosticsDialog,
    EffectDialog,
    ExportDialog,
    ExternalPluginDialog,
    GeneratorDialog,
    HistoryDialog,
    ImportRawDialog,
    LabelEditorDialog,
    MacroBatchDialog,
    ManualDialog,
    MetadataDialog,
    NyquistPromptDialog,
    PlotSpectrumDialog,
    PluginManagerDialog,
    PreferencesDialog,
    RealtimeEffectsDialog,
    ScriptingPipeDialog,
    SpectrogramSettingsDialog,
    TimerRecordDialog,
)
from .dsp import (
    EFFECT_REGISTRY,
    PresetManager,
    capture_noise_profile,
    export_sample_data_text,
    find_beats,
    find_clipping,
    find_sounds_or_silences,
    find_zero_crossing,
    gen_chirp,
    gen_dtmf,
    gen_noise,
    gen_plucked,
    gen_rhythm_track,
    gen_risset_drum,
    gen_silence,
    gen_tone,
    generate_regular_interval_labels,
    import_sample_data_text,
    measure_rms,
    resample_audio,
    run_effect,
)
from .icons import make_app_pixmap, make_icon
from .models import (
    AudioClip,
    AudioTrack,
    KinoWaveProject,
    LabelItem,
    LabelTrack,
    NoteTrack,
    SAMPLE_FORMATS,
    SAMPLE_RATES,
    TimeTrack,
)
from .sample_project import create_sample_session
from .theme import get_theme_stylesheet
from .widgets import LevelMeterWidget, MultitrackCanvasWidget, SelectionStatusBar, TimelineRulerWidget


class KinoWaveWindow(QMainWindow):
    """Main KinoWave Multitrack Audio Editing & Mastering Window."""

    # Class-level clipboard enables Copy & Paste seamlessly between project tabs or windows!
    SHARED_CLIPBOARD: Optional[Dict[str, Any]] = None

    def __init__(self, initial_files: Optional[List[str]] = None, load_sample: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("KinoWave — KinoSuite Audio Studio")
        self.setWindowIcon(QIcon(make_app_pixmap(64)))
        self.resize(1500, 900)

        import sys
        if getattr(sys, "frozen", False):
            self.app_root = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_dir = os.path.join(self.app_root, ".kinowave_config")
        os.makedirs(self.config_dir, exist_ok=True)

        # Core Managers
        self.prefs = PreferencesManager(self.config_dir)
        self.presets = PresetManager(self.config_dir)
        self.macros = MacroManager(self.config_dir)
        self.plugins = PluginManager(self.app_root, self.config_dir, custom_dirs=list(self.prefs.get("custom_vst_dirs", [])))
        self.nyquist = NyquistInterpreter()
        self.cloud = KinoCloudAudioManager(self.app_root)
        self.recovery = CrashRecoveryManager(self.config_dir)
        self.engine = AudioEngine()
        self._sync_engine_from_prefs()

        # Multi-project state (tabs support copy/paste between projects!)
        self.projects: List[KinoWaveProject] = []
        self.last_effect_name: Optional[str] = None
        self.last_effect_params: Dict[str, Any] = {}
        self.actions_by_id: Dict[str, QAction] = {}
        self.toolbars: Dict[str, QToolBar] = {}
        self._menu_refs: Dict[str, QMenu] = {}

        # Build UI cleanly
        self._build_central_workspace()
        self._build_toolbars()
        self._build_inspector_dock()
        self._build_menus()
        self._apply_theme(str(self.prefs.get("theme", "Dark")))
        self._apply_language(str(self.prefs.get("language", "English")))

        # External Scripting Pipe
        self.pipe_server = ScriptingPipeServer(self._handle_pipe_command, port=int(self.prefs.get("scripting_pipe_port", 47921)))
        if self.prefs.get("enable_scripting_pipe", True):
            self.pipe_server.start()

        # Lightweight 30 FPS playback / metering timer (idle when stopped)
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(33)
        self._ui_timer.timeout.connect(self._on_ui_tick)
        self._ui_timer.start()

        # Periodic crash auto-recovery timer (every 45s)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(45_000)
        self._autosave_timer.timeout.connect(self._autosave_dirty_projects)
        self._autosave_timer.start()

        # Open initial files or built-in studio showcase
        opened_any = False
        if initial_files:
            for fp in initial_files:
                if os.path.isfile(fp):
                    self.open_path(fp)
                    opened_any = True
        if not opened_any:
            if load_sample:
                self._add_project_tab(create_sample_session(int(self.prefs.get("default_sample_rate", 48000))))
            else:
                self.new_project()

        # Crash recovery check & initial fit-to-window after layout settles
        QTimer.singleShot(0, self.zoom_fit_project)
        QTimer.singleShot(400, self._check_crash_recovery)

    # -----------------------------------------------------------------------
    # Active Project Helpers
    # -----------------------------------------------------------------------
    def current_project(self) -> Optional[KinoWaveProject]:
        idx = self.proj_tabs.currentIndex()
        if 0 <= idx < len(self.projects):
            return self.projects[idx]
        return None

    def _sync_engine_from_prefs(self) -> None:
        self.engine.sample_rate = int(self.prefs.get("default_sample_rate", 48000))
        self.engine.buffer_size = int(self.prefs.get("buffer_size", 1024))
        self.engine.latency_ms = float(self.prefs.get("latency_ms", 0.0))
        self.engine.overdub = bool(self.prefs.get("overdub", True))
        self.engine.software_playthrough = bool(self.prefs.get("software_playthrough", False))
        self.engine.sound_activated_record = bool(self.prefs.get("sound_activated_record", False))
        self.engine.sound_activation_db = float(self.prefs.get("sound_activation_db", -36.0))

    # -----------------------------------------------------------------------
    # Central Workspace Construction
    # -----------------------------------------------------------------------
    def _build_central_workspace(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Multi-project Tab Bar (enables easy multi-project editing & cross-project copy/paste)
        self.proj_tabs = QTabWidget()
        self.proj_tabs.setDocumentMode(True)
        self.proj_tabs.setTabsClosable(True)
        self.proj_tabs.setMaximumHeight(30)
        self.proj_tabs.currentChanged.connect(self._on_project_tab_changed)
        self.proj_tabs.tabCloseRequested.connect(self._close_project_tab)
        root.addWidget(self.proj_tabs)

        # Timeline Ruler
        self.ruler = TimelineRulerWidget()
        self.ruler.quickPlayRequested.connect(self._on_quick_play)
        self.ruler.scrubRequested.connect(self._on_scrub)
        self.ruler.loopChanged.connect(lambda _a, _b: self._refresh_views())
        root.addWidget(self.ruler)

        # Multitrack Canvas + Vertical Scrollbar
        mid_row = QHBoxLayout()
        mid_row.setContentsMargins(0, 0, 0, 0)
        mid_row.setSpacing(0)
        self.canvas = MultitrackCanvasWidget()
        self.canvas.selectionChanged.connect(self._on_selection_changed)
        self.canvas.projectModified.connect(self._on_canvas_modified)
        self.canvas.trackActionRequested.connect(self._on_track_header_action)
        self.canvas.filesDropped.connect(self._on_files_dropped)
        self.canvas.zoomRequested.connect(self._zoom_by_factor)
        self.canvas.labelEditRequested.connect(self._on_edit_label_inline)
        mid_row.addWidget(self.canvas, 1)

        self.vscroll = QScrollBar(Qt.Orientation.Vertical)
        self.vscroll.valueChanged.connect(self._on_vscroll)
        mid_row.addWidget(self.vscroll)
        root.addLayout(mid_row, 1)

        # Horizontal Scrollbar
        self.hscroll = QScrollBar(Qt.Orientation.Horizontal)
        self.hscroll.valueChanged.connect(self._on_hscroll)
        root.addWidget(self.hscroll)

        # Audacity-style Precision Selection & Time Bar
        self.sel_bar = SelectionStatusBar()
        self.sel_bar.sampleRateChanged.connect(self._on_project_sr_changed)
        self.sel_bar.snapChanged.connect(self._on_snap_changed)
        self.sel_bar.selectionEdited.connect(self._on_sel_bar_edited)
        root.addWidget(self.sel_bar)

        # Status Bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_status_info = QLabel("Ready — 32-bit float engine (up to 384 kHz)")
        self.status.addWidget(self.lbl_status_info, 1)
        suite_badge = QLabel("KINOSUITE · KINOWAVE")
        suite_badge.setObjectName("SuiteBadge")
        self.status.addPermanentWidget(suite_badge)

    # -----------------------------------------------------------------------
    # Rearrangeable, Hideable, Resettable Audacity-style Toolbars
    # -----------------------------------------------------------------------
    def _build_toolbars(self) -> None:
        self.setDockNestingEnabled(True)

        # 1. Transport Toolbar
        tb_tr = QToolBar("Transport Toolbar", self)
        tb_tr.setObjectName("TransportToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_tr)
        self.toolbars["Transport"] = tb_tr

        self.btn_pause = self._mk_tb_btn("pause", "Pause (P)", self.pause_playback, checkable=True)
        self.btn_play = self._mk_tb_btn("play", "Play / Stop (Space)", self.toggle_play_stop)
        self.btn_stop = self._mk_tb_btn("stop", "Stop", self.stop_all)
        self.btn_start = self._mk_tb_btn("skip_start", "Skip to Start (Home)", self.skip_to_start)
        self.btn_end = self._mk_tb_btn("skip_end", "Skip to End (End)", self.skip_to_end)
        self.btn_rec = self._mk_tb_btn("record", "Record (R)", self.toggle_record, checkable=True)
        self.btn_rec.setObjectName("RecordButton")
        self.btn_loop = self._mk_tb_btn("loop", "Toggle Loop Play (L)", self.toggle_loop, checkable=True)
        for b in (self.btn_pause, self.btn_play, self.btn_stop, self.btn_start, self.btn_end, self.btn_rec, self.btn_loop):
            tb_tr.addWidget(b)

        # 2. Tools Toolbar (F1..F6)
        tb_tl = QToolBar("Tools Toolbar", self)
        tb_tl.setObjectName("ToolsToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_tl)
        self.toolbars["Tools"] = tb_tl

        self.tool_btns: Dict[str, QToolButton] = {}
        for tid, icon_n, tip in [
            ("select", "tool_select", "Selection Tool (F1)"),
            ("envelope", "tool_envelope", "Volume Envelope Tool (F2)"),
            ("draw", "tool_draw", "Sample Draw Tool (F3)"),
            ("zoom", "tool_zoom", "Zoom Tool (F4)"),
            ("shift", "tool_shift", "Clip Move / Time-Shift Tool (F5)"),
            ("multi", "tool_multi", "Multi-Tool (F6 — smart context switching)"),
        ]:
            b = self._mk_tb_btn(icon_n, tip, lambda _=False, t=tid: self.set_tool(t), checkable=True)
            self.tool_btns[tid] = b
            tb_tl.addWidget(b)
        self.tool_btns["multi"].setChecked(True)

        # 3. Edit & Zoom Toolbar
        tb_ed = QToolBar("Edit & Zoom Toolbar", self)
        tb_ed.setObjectName("EditToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_ed)
        self.toolbars["Edit & Zoom"] = tb_ed

        for ic, tip, fn in [
            ("cut", "Cut (Ctrl+X)", self.edit_cut),
            ("copy", "Copy (Ctrl+C)", self.edit_copy),
            ("paste", "Paste (Ctrl+V)", self.edit_paste),
            ("trim", "Trim Outside Selection (Ctrl+T)", self.edit_trim),
            ("silence", "Silence Selection (Ctrl+L)", self.edit_silence),
            ("split", "Split Clip (Ctrl+I)", self.edit_split),
            ("undo", "Undo (Ctrl+Z)", self.edit_undo),
            ("redo", "Redo (Ctrl+Y)", self.edit_redo),
            ("zoom_in", "Zoom In (Ctrl+1)", lambda: self._zoom_by_factor(1.5)),
            ("zoom_out", "Zoom Out (Ctrl+3)", lambda: self._zoom_by_factor(0.67)),
            ("fit_sel", "Zoom to Selection (Ctrl+E)", self.zoom_to_selection),
            ("fit_proj", "Fit Project in Window (Ctrl+F)", self.zoom_fit_project),
        ]:
            tb_ed.addWidget(self._mk_tb_btn(ic, tip, fn))

        self.btn_sync = self._mk_tb_btn("sync_lock", "Sync-Lock Tracks", self.toggle_sync_lock, checkable=True)
        self.btn_scrub = self._mk_tb_btn("scrub", "Scrub & Seek Mode on Ruler", self.toggle_scrub_mode, checkable=True)
        tb_ed.addSeparator()
        tb_ed.addWidget(self.btn_sync)
        tb_ed.addWidget(self.btn_scrub)

        # Break to second crisp toolbar row for Meters, Speed & Audio Devices
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)

        # 4. Meters & Gain Toolbar
        tb_mt = QToolBar("Meters Toolbar", self)
        tb_mt.setObjectName("MetersToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_mt)
        self.toolbars["Meters"] = tb_mt

        self.meter_in = LevelMeterWidget("REC")
        self.meter_in.clipResetRequested.connect(self.engine.reset_clip_indicators)
        tb_mt.addWidget(self.meter_in)

        self.sl_in_gain = QSlider(Qt.Orientation.Horizontal)
        self.sl_in_gain.setRange(10, 300)
        self.sl_in_gain.setValue(100)
        self.sl_in_gain.setFixedWidth(72)
        self.sl_in_gain.setToolTip("Input Recording Level")
        self.sl_in_gain.valueChanged.connect(lambda v: setattr(self.engine, "input_gain", v / 100.0))
        tb_mt.addWidget(self.sl_in_gain)

        btn_auto_lvl = QPushButton("Auto")
        btn_auto_lvl.setFixedHeight(24)
        btn_auto_lvl.setToolTip("Automated Input Level Adjustment (-6 dB target)")
        btn_auto_lvl.clicked.connect(self._auto_adjust_input_level)
        tb_mt.addWidget(btn_auto_lvl)
        tb_mt.addSeparator()

        self.meter_out = LevelMeterWidget("OUT")
        self.meter_out.clipResetRequested.connect(self.engine.reset_clip_indicators)
        tb_mt.addWidget(self.meter_out)

        self.sl_out_vol = QSlider(Qt.Orientation.Horizontal)
        self.sl_out_vol.setRange(0, 150)
        self.sl_out_vol.setValue(100)
        self.sl_out_vol.setFixedWidth(72)
        self.sl_out_vol.setToolTip("Playback Monitoring Volume")
        self.sl_out_vol.valueChanged.connect(lambda v: setattr(self.engine, "output_volume", v / 100.0))
        tb_mt.addWidget(self.sl_out_vol)

        # 5. Playback Speed & Audio Setup Toolbar
        tb_dv = QToolBar("Audio Setup & Speed Toolbar", self)
        tb_dv.setObjectName("DeviceToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_dv)
        self.toolbars["Audio Setup & Speed"] = tb_dv

        tb_dv.addWidget(QLabel(" Speed:"))
        self.sp_speed = QDoubleSpinBox()
        self.sp_speed.setRange(0.25, 3.0)
        self.sp_speed.setSingleStep(0.05)
        self.sp_speed.setValue(1.0)
        self.sp_speed.setSuffix("x")
        self.sp_speed.setFixedWidth(68)
        self.sp_speed.valueChanged.connect(self._on_speed_changed)
        tb_dv.addWidget(self.sp_speed)
        tb_dv.addSeparator()

        self.cmb_host = QComboBox()
        self.cmb_host.setFixedWidth(120)
        self.cmb_host.setToolTip("Audio Host API")
        for h in list_audio_hosts():
            self.cmb_host.addItem(h["name"], h["index"])
        self.cmb_host.currentIndexChanged.connect(self._populate_device_combos)
        tb_dv.addWidget(self.cmb_host)

        self.cmb_in_dev = QComboBox()
        self.cmb_in_dev.setFixedWidth(165)
        self.cmb_in_dev.setToolTip("Recording Input Device (Mic / Line / USB / Loopback)")
        self.cmb_in_dev.currentIndexChanged.connect(lambda: setattr(self.engine, "input_device", self.cmb_in_dev.currentData()))
        tb_dv.addWidget(self.cmb_in_dev)

        self.cmb_rec_ch = QComboBox()
        self.cmb_rec_ch.addItem("1 (Mono)", 1)
        self.cmb_rec_ch.addItem("2 (Stereo)", 2)
        self.cmb_rec_ch.addItem("4 (Quad)", 4)
        self.cmb_rec_ch.addItem("8 (Multi)", 8)
        self.cmb_rec_ch.setCurrentIndex(1)
        self.cmb_rec_ch.setFixedWidth(86)
        self.cmb_rec_ch.currentIndexChanged.connect(lambda: setattr(self.engine, "record_channels", int(self.cmb_rec_ch.currentData())))
        tb_dv.addWidget(self.cmb_rec_ch)

        self.cmb_out_dev = QComboBox()
        self.cmb_out_dev.setFixedWidth(165)
        self.cmb_out_dev.setToolTip("Playback Output Device")
        self.cmb_out_dev.currentIndexChanged.connect(lambda: setattr(self.engine, "output_device", self.cmb_out_dev.currentData()))
        tb_dv.addWidget(self.cmb_out_dev)
        self._populate_device_combos()

        tb_dv.addSeparator()
        btn_mfx = QPushButton("Master FX")
        btn_mfx.setObjectName("KinoAccentButton")
        btn_mfx.setFixedHeight(25)
        btn_mfx.clicked.connect(self._open_master_fx)
        tb_dv.addWidget(btn_mfx)

        btn_cloud = QPushButton("Cloud")
        btn_cloud.setIcon(make_icon("cloud", 16))
        btn_cloud.setFixedHeight(25)
        btn_cloud.clicked.connect(self._open_cloud_share)
        tb_dv.addWidget(btn_cloud)

    def _mk_tb_btn(self, icon_name: str, tooltip: str, slot: Callable, checkable: bool = False) -> QToolButton:
        b = QToolButton()
        b.setIcon(make_icon(icon_name, 20))
        b.setToolTip(tooltip)
        b.setAccessibleName(tooltip)
        b.setCheckable(checkable)
        b.setFixedSize(30, 28)
        b.clicked.connect(slot)
        return b

    def _populate_device_combos(self) -> None:
        host_idx = self.cmb_host.currentData()
        self.engine.host_index = host_idx
        devs = list_audio_devices(host_idx)
        self.cmb_in_dev.blockSignals(True)
        self.cmb_out_dev.blockSignals(True)
        self.cmb_in_dev.clear()
        for d in devs["inputs"]:
            self.cmb_in_dev.addItem(d["name"], d["index"])
        self.cmb_out_dev.clear()
        for d in devs["outputs"]:
            self.cmb_out_dev.addItem(d["name"], d["index"])
        self.cmb_in_dev.blockSignals(False)
        self.cmb_out_dev.blockSignals(False)
        if self.cmb_in_dev.count() > 0:
            self.engine.input_device = self.cmb_in_dev.currentData()
        if self.cmb_out_dev.count() > 0:
            self.engine.output_device = self.cmb_out_dev.currentData()

    # -----------------------------------------------------------------------
    # Right Collapsible KinoSuite Studio Inspector Dock
    # -----------------------------------------------------------------------
    def _build_inspector_dock(self) -> None:
        self.dock_inspector = QDockWidget("KinoWave Studio Inspector", self)
        self.dock_inspector.setObjectName("StudioInspectorDock")
        self.dock_inspector.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.dock_inspector.setMinimumWidth(240)
        self.dock_inspector.setMaximumWidth(340)

        w = QWidget()
        w.setObjectName("StudioPanel")
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # Quick Grid & Tempo controls
        lbl_g = QLabel("BEATS & TEMPO GRID")
        lbl_g.setObjectName("SectionHeader")
        lay.addWidget(lbl_g)
        grow = QHBoxLayout()
        self.cb_beats = QCheckBox("Beats Grid")
        self.cb_beats.toggled.connect(self._toggle_beats_grid)
        self.sp_bpm = QDoubleSpinBox()
        self.sp_bpm.setRange(30.0, 300.0)
        self.sp_bpm.setValue(120.0)
        self.sp_bpm.setSuffix(" BPM")
        self.sp_bpm.valueChanged.connect(self._on_bpm_changed)
        grow.addWidget(self.cb_beats)
        grow.addWidget(self.sp_bpm)
        lay.addLayout(grow)

        # Active Track Real-Time FX list
        lbl_fx = QLabel("REAL-TIME EFFECT RACK")
        lbl_fx.setObjectName("SectionHeader")
        lay.addWidget(lbl_fx)
        self.lst_insp_fx = QListWidget()
        self.lst_insp_fx.setMaximumHeight(140)
        lay.addWidget(self.lst_insp_fx)
        fx_row = QHBoxLayout()
        b_tfx = QPushButton("Track FX...")
        b_tfx.clicked.connect(self._open_selected_track_fx)
        b_mfx = QPushButton("Master FX...")
        b_mfx.clicked.connect(self._open_master_fx)
        fx_row.addWidget(b_tfx)
        fx_row.addWidget(b_mfx)
        lay.addLayout(fx_row)

        # Quick History summary
        lbl_h = QLabel("UNDO HISTORY")
        lbl_h.setObjectName("SectionHeader")
        lay.addWidget(lbl_h)
        self.lst_insp_hist = QListWidget()
        self.lst_insp_hist.itemClicked.connect(lambda it: self._restore_history(self.lst_insp_hist.row(it)))
        lay.addWidget(self.lst_insp_hist, 1)

        # Quick Actions
        b_exp = QPushButton("Export Audio...")
        b_exp.setObjectName("PrimaryButton")
        b_exp.clicked.connect(lambda: self._open_export("Entire Project"))
        lay.addWidget(b_exp)

        self.dock_inspector.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_inspector)

    # -----------------------------------------------------------------------
    # Complete Audacity-Parity Menu Bar
    # -----------------------------------------------------------------------
    def _act(self, aid: str, text: str, slot: Callable, default_sc: str = "", checkable: bool = False) -> QAction:
        a = QAction(text, self)
        sc = self.prefs.get("shortcuts", {}).get(aid, default_sc)
        if sc:
            a.setShortcut(QKeySequence(sc))
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        self.actions_by_id[aid] = a
        return a

    def _build_menus(self) -> None:
        mb = self.menuBar()

        # FILE
        m_file = mb.addMenu("&File")
        self._menu_refs["File"] = m_file
        m_file.addAction(self._act("file_new", "New Project", self.new_project, "Ctrl+N"))
        m_file.addAction(self._act("file_open", "Open Project / Audio...", self.open_file_dialog, "Ctrl+O"))
        self.m_recent = m_file.addMenu("Open Recent")
        self._rebuild_recent_menu()
        m_file.addAction(self._act("file_close", "Close Project Tab", lambda: self._close_project_tab(self.proj_tabs.currentIndex()), "Ctrl+W"))
        m_file.addSeparator()
        m_file.addAction(self._act("file_save", "Save Project", self.save_project, "Ctrl+S"))
        m_file.addAction(self._act("file_save_as", "Save Project As...", self.save_project_as, "Ctrl+Shift+S"))
        m_file.addAction(self._act("file_backup", "Save Copy / Backup of Project...", self.save_project_backup))
        m_file.addAction(self._act("file_cloud", "Save to KinoCloud & Share Online...", self._open_cloud_share))
        m_file.addSeparator()

        m_imp = m_file.addMenu("Import")
        m_imp.addAction("Audio (WAV, FLAC, MP3, OGG, Opus, M4A, Video)...", self.import_audio_dialog)
        m_imp.addAction("Labels (.txt)...", self.import_labels_dialog)
        m_imp.addAction("MIDI (.mid)...", self.import_midi_dialog)
        m_imp.addAction("Raw Data (Headerless)...", self.import_raw_dialog)

        m_exp = m_file.addMenu("Export")
        m_exp.addAction(self._act("file_export", "Export Audio...", lambda: self._open_export("Entire Project"), "Ctrl+Shift+E"))
        m_exp.addAction("Export Selected Audio...", lambda: self._open_export("Selected Audio Only"))
        m_exp.addAction("Export Multiple (Split by Track)...", lambda: self._open_export("Multiple Files — Split by Track"))
        m_exp.addAction("Export Multiple (Split by Labels)...", lambda: self._open_export("Multiple Files — Split by Labels"))
        m_exp.addSeparator()
        m_exp.addAction("Export Labels (.txt)...", self.export_labels_dialog)
        m_exp.addAction("Export MIDI Note Track (.mid)...", self.export_midi_dialog)

        m_file.addSeparator()
        m_file.addAction("Edit Metadata Tags...", self._open_metadata)
        m_file.addSeparator()
        m_file.addAction("Exit", self.close)

        # EDIT
        m_edit = mb.addMenu("&Edit")
        self._menu_refs["Edit"] = m_edit
        m_edit.addAction(self._act("edit_undo", "Undo", self.edit_undo, "Ctrl+Z"))
        m_edit.addAction(self._act("edit_redo", "Redo", self.edit_redo, "Ctrl+Y"))
        m_edit.addAction("Undo History...", self._open_history)
        m_edit.addSeparator()
        m_edit.addAction(self._act("edit_cut", "Cut", self.edit_cut, "Ctrl+X"))
        m_edit.addAction(self._act("edit_copy", "Copy", self.edit_copy, "Ctrl+C"))
        m_edit.addAction(self._act("edit_paste", "Paste", self.edit_paste, "Ctrl+V"))
        m_edit.addAction(self._act("edit_delete", "Delete", self.edit_delete, "Del"))
        m_edit.addAction(self._act("edit_duplicate", "Duplicate", self.edit_duplicate, "Ctrl+D"))
        m_edit.addSeparator()
        m_rem = m_edit.addMenu("Remove Special")
        m_rem.addAction("Split Cut (Leave Gap)", self.edit_split_cut)
        m_rem.addAction("Split Delete (Leave Gap)", self.edit_split_delete)
        m_rem.addAction(self._act("edit_silence", "Silence Audio", self.edit_silence, "Ctrl+L"))
        m_rem.addAction(self._act("edit_trim", "Trim Audio Outside Selection", self.edit_trim, "Ctrl+T"))

        m_clip = m_edit.addMenu("Clip Boundaries")
        m_clip.addAction(self._act("edit_split", "Split", self.edit_split, "Ctrl+I"))
        m_clip.addAction("Split New (Into New Track)", self.edit_split_new)
        m_clip.addAction(self._act("edit_join", "Join Clips", self.edit_join, "Ctrl+J"))
        m_clip.addAction("Detach at Silences", self.edit_detach_silences)

        m_lbl = m_edit.addMenu("Labels & Labeled Audio")
        m_lbl.addAction(self._act("add_label", "Add Label at Selection / Playback", self.add_label_at_selection, "Ctrl+B"))
        m_lbl.addAction("Edit Labels Table...", self._open_label_editor)
        m_lbl.addSeparator()
        m_lbl.addAction("Labeled Audio: Cut", lambda: self._labeled_audio_op("cut"))
        m_lbl.addAction("Labeled Audio: Delete", lambda: self._labeled_audio_op("delete"))
        m_lbl.addAction("Labeled Audio: Split Cut", lambda: self._labeled_audio_op("split_cut"))
        m_lbl.addAction("Labeled Audio: Split Delete", lambda: self._labeled_audio_op("split_delete"))
        m_lbl.addAction("Labeled Audio: Silence", lambda: self._labeled_audio_op("silence"))
        m_lbl.addAction("Labeled Audio: Split Clips at Labels", lambda: self._labeled_audio_op("split"))
        m_lbl.addAction("Labeled Audio: Join Clips in Labels", lambda: self._labeled_audio_op("join"))

        m_edit.addSeparator()
        m_edit.addAction(self._act("preferences", "Preferences...", self._open_preferences, "Ctrl+P"))

        # SELECT
        m_sel = mb.addMenu("&Select")
        self._menu_refs["Select"] = m_sel
        m_sel.addAction(self._act("select_all", "All", self.select_all, "Ctrl+A"))
        m_sel.addAction(self._act("select_none", "None", self.select_none, "Ctrl+Shift+A"))
        m_sel.addAction("Tracks -> In All Tracks", self.select_all_tracks)
        m_sel.addAction("Region -> Track Start to Cursor", self.select_to_start)
        m_sel.addAction("Region -> Cursor to Track End", self.select_to_end)
        m_sel.addSeparator()
        m_sel.addAction("Store Cursor Position", self.store_cursor)
        m_sel.addAction("Recall Cursor Position", self.recall_cursor)
        m_sel.addAction("Store Selection", self.store_selection)
        m_sel.addAction("Recall Selection", self.recall_selection)
        m_sel.addSeparator()
        m_sel.addAction(self._act("find_zero_crossings", "At Zero Crossings", self.snap_selection_zero_crossings, "Z"))
        m_sel.addAction("Spectral Selection (Set Frequency Range)...", self._set_spectral_selection_dialog)

        # VIEW
        m_view = mb.addMenu("&View")
        self._menu_refs["View"] = m_view
        m_view.addAction(self._act("zoom_in", "Zoom In", lambda: self._zoom_by_factor(1.5), "Ctrl+1"))
        m_view.addAction(self._act("zoom_normal", "Zoom Normal", self.zoom_normal, "Ctrl+2"))
        m_view.addAction(self._act("zoom_out", "Zoom Out", lambda: self._zoom_by_factor(0.67), "Ctrl+3"))
        m_view.addAction(self._act("zoom_fit_selection", "Zoom to Selection", self.zoom_to_selection, "Ctrl+E"))
        m_view.addAction(self._act("zoom_fit_project", "Fit in Window (Project)", self.zoom_fit_project, "Ctrl+F"))
        m_view.addSeparator()
        m_view.addAction("Fit Vertically (All Tracks)", self.fit_tracks_vertically)
        m_view.addAction("Collapse All Tracks", lambda: self._set_all_collapsed(True))
        m_view.addAction("Expand All Tracks", lambda: self._set_all_collapsed(False))
        m_view.addSeparator()
        m_view.addAction("Show Clipping in Waveform (Selected Tracks)", self._toggle_show_clipping)
        m_view.addAction("Toggle Beats & Measures Grid", lambda: self._toggle_beats_grid(not self.cb_beats.isChecked()))
        m_view.addAction("Set Time Signature...", self._set_time_signature)
        m_view.addAction("Undo History...", self._open_history)
        m_view.addSeparator()

        m_tb = m_view.addMenu("Toolbars")
        for name, tb in self.toolbars.items():
            m_tb.addAction(tb.toggleViewAction())
        m_tb.addAction(self.dock_inspector.toggleViewAction())
        m_tb.addSeparator()
        m_tb.addAction("Reset Toolbars", self._reset_toolbars)

        m_thm = m_view.addMenu("Theme")
        for thm in ("Dark", "Light", "High Contrast"):
            m_thm.addAction(thm, lambda _=False, t=thm: self._apply_theme(t))

        m_lng = m_view.addMenu("Language")
        for lng in TRANSLATIONS:
            m_lng.addAction(lng, lambda _=False, l=lng: self._apply_language(l))

        # TRANSPORT
        m_tr = mb.addMenu("&Transport")
        self._menu_refs["Transport"] = m_tr
        m_tr.addAction(self._act("transport_play_stop", "Play / Stop", self.toggle_play_stop, "Space"))
        m_tr.addAction(self._act("transport_pause", "Pause", self.pause_playback, "P"))
        m_tr.addAction("Play Selection Only", self.play_selection)
        m_tr.addAction("Play Before Selection", lambda: self.play_around_selection("before"))
        m_tr.addAction("Play After Selection", lambda: self.play_around_selection("after"))
        m_tr.addAction(self._act("transport_cut_preview", "Cut Preview", self.play_cut_preview, "C"))
        m_tr.addAction(self._act("transport_loop", "Toggle Looping", self.toggle_loop, "L"))
        m_tr.addSeparator()
        m_tr.addAction(self._act("transport_record", "Record (Append / New Track)", self.toggle_record, "R"))
        m_tr.addAction("Record Into New Track", lambda: self.start_record(new_track=True))
        m_tr.addAction(self._act("transport_punch_roll", "Punch and Roll Record", self.start_punch_and_roll, "Shift+D"))
        m_tr.addAction("Timer Record...", self._open_timer_record)
        m_tr.addSeparator()
        m_tr.addAction(self._act("seek_short_left", "Skip Backward (Short Jump)", lambda: self.seek_relative(-float(self.prefs.get("short_jump_s", 1.0))), "Left"))
        m_tr.addAction(self._act("seek_short_right", "Skip Forward (Short Jump)", lambda: self.seek_relative(float(self.prefs.get("short_jump_s", 1.0))), "Right"))
        m_tr.addAction(self._act("seek_long_left", "Skip Backward (Long Jump)", lambda: self.seek_relative(-float(self.prefs.get("long_jump_s", 10.0))), "Shift+Left"))
        m_tr.addAction(self._act("seek_long_right", "Skip Forward (Long Jump)", lambda: self.seek_relative(float(self.prefs.get("long_jump_s", 10.0))), "Shift+Right"))
        m_tr.addSeparator()
        a_ov = m_tr.addAction("Overdub (Play Other Tracks While Recording)")
        a_ov.setCheckable(True); a_ov.setChecked(self.engine.overdub)
        a_ov.toggled.connect(lambda v: (setattr(self.engine, "overdub", v), self.prefs.set("overdub", v)))
        a_pt = m_tr.addAction("Software Playthrough (Monitor Input)")
        a_pt.setCheckable(True); a_pt.setChecked(self.engine.software_playthrough)
        a_pt.toggled.connect(lambda v: (setattr(self.engine, "software_playthrough", v), self.prefs.set("software_playthrough", v)))
        a_sa = m_tr.addAction("Sound-Activated Recording")
        a_sa.setCheckable(True); a_sa.setChecked(self.engine.sound_activated_record)
        a_sa.toggled.connect(lambda v: (setattr(self.engine, "sound_activated_record", v), self.prefs.set("sound_activated_record", v)))

        # TRACKS
        m_tk = mb.addMenu("T&racks")
        self._menu_refs["Tracks"] = m_tk
        m_add = m_tk.addMenu("Add New")
        m_add.addAction("Mono Track", lambda: self._add_track("mono"))
        m_add.addAction("Stereo Track", lambda: self._add_track("stereo"))
        m_add.addAction("Label Track", lambda: self._add_track("label"))
        m_add.addAction("Time Track", lambda: self._add_track("time"))
        m_add.addAction("MIDI Note Track", lambda: self._add_track("note"))
        m_tk.addSeparator()
        m_tk.addAction("Mix and Render (Replace Selected Tracks)", lambda: self._mix_and_render(to_new=False))
        m_tk.addAction("Mix and Render to New Track", lambda: self._mix_and_render(to_new=True))
        m_tk.addAction("Make Stereo Track (From 2 Selected Mono Tracks)", self._make_stereo_selected)
        m_tk.addAction("Resample Selected Tracks...", self._resample_selected)
        m_tk.addSeparator()
        m_al = m_tk.addMenu("Align Tracks")
        m_al.addAction("Start to Zero", lambda: self._align_tracks("zero"))
        m_al.addAction("Start to Cursor / Selection Start", lambda: self._align_tracks("cursor"))
        m_al.addAction("Align End to End", lambda: self._align_tracks("end_to_end"))
        m_al.addAction("Align Together", lambda: self._align_tracks("together"))
        m_srt = m_tk.addMenu("Sort Tracks")
        m_srt.addAction("By Name", lambda: self._sort_tracks("name"))
        m_srt.addAction("By Start Time", lambda: self._sort_tracks("start"))
        m_tk.addSeparator()
        m_tk.addAction("Mute All Tracks", lambda: self._mute_all(True))
        m_tk.addAction("Unmute All Tracks", lambda: self._mute_all(False))
        m_tk.addAction("Sync-Lock Tracks (Toggle)", self.toggle_sync_lock)

        # GENERATE
        m_gen = mb.addMenu("&Generate")
        self._menu_refs["Generate"] = m_gen
        for gname in ("Tone", "Chirp", "Noise", "DTMF Tones", "Silence", "Rhythm Track", "Plucked", "Risset Drum"):
            m_gen.addAction(f"{gname}...", lambda _=False, g=gname: self._run_generator(g))

        # EFFECT (grouped cleanly by category + Repeat Last + Real-Time FX + VST3/VST2 + Plugin Manager)
        m_fx = mb.addMenu("Effe&ct")
        self._menu_refs["Effect"] = m_fx
        m_fx.addAction(self._act("repeat_last_effect", "Repeat Last Effect", self._repeat_last_effect, "Ctrl+R"))
        m_fx.addAction("Plugin Manager (VST3 / VST2 / LV2 / LADSPA / AU / Nyquist)...", self._open_plugin_manager)
        m_fx.addAction("Real-Time Track Effects Rack (Built-in + VST)...", self._open_selected_track_fx)
        m_fx.addAction("Real-Time Master Effects Rack (Built-in + VST)...", self._open_master_fx)
        m_fx.addSeparator()

        self.m_external_fx = m_fx.addMenu("VST3 / VST2 / External Plugins")
        self._rebuild_external_fx_menu()
        m_fx.addSeparator()

        cats: Dict[str, QMenu] = {}
        for ename, spec in EFFECT_REGISTRY.items():
            cat = spec["category"]
            if cat not in cats:
                cats[cat] = m_fx.addMenu(cat)
            cats[cat].addAction(f"{ename}...", lambda _=False, e=ename: self._open_effect_dialog(e))

        # ANALYZE
        m_an = mb.addMenu("&Analyze")
        self._menu_refs["Analyze"] = m_an
        m_an.addAction("Plot Spectrum...", self._open_plot_spectrum)
        m_an.addAction("Contrast Analysis (WCAG)...", self._open_contrast)
        m_an.addAction("Measure RMS...", self._analyze_measure_rms)
        m_an.addSeparator()
        m_an.addAction("Find Clipping...", self._analyze_find_clipping)
        m_an.addAction("Beat Finder...", self._analyze_beat_finder)
        m_an.addAction("Label Sounds...", lambda: self._analyze_sounds_silences("Sounds"))
        m_an.addAction("Label Silences...", lambda: self._analyze_sounds_silences("Silences"))
        m_an.addAction("Regular Interval Labels...", self._analyze_regular_labels)
        m_an.addSeparator()
        m_an.addAction("Sample Data Export...", self._sample_data_export)
        m_an.addAction("Sample Data Import...", self._sample_data_import)

        # TOOLS
        m_tls = mb.addMenu("Too&ls")
        self._menu_refs["Tools"] = m_tls
        m_tls.addAction("Macros & Batch Process Files...", self._open_macros)
        m_tls.addAction("Nyquist Prompt...", self._open_nyquist_prompt)
        m_tls.addAction("Plugin Manager & Nyquist Installer...", self._open_plugin_manager)
        m_tls.addAction("External Scripting Pipe Console...", self._open_scripting_pipe)
        m_tls.addSeparator()
        m_tls.addAction("Screenshot Tools (Capture Interface)...", self._capture_screenshot)
        m_tls.addAction("Run Performance Benchmark...", self._run_benchmark)
        m_tls.addAction("Reset Configuration...", self._reset_configuration)

        # HELP
        m_hlp = mb.addMenu("&Help")
        self._menu_refs["Help"] = m_hlp
        m_hlp.addAction("KinoWave Built-in Manual...", lambda: ManualDialog(self).exec())
        m_hlp.addAction("Audio Device Info & Diagnostics Log...", lambda: DiagnosticsDialog(self.engine.diagnostic_log, self).exec())
        m_hlp.addAction("Check for Updates...", self._check_updates)
        m_hlp.addSeparator()
        m_hlp.addAction("About KinoWave (KinoSuite)...", self._show_about)

    # -----------------------------------------------------------------------
    # Theme & Language
    # -----------------------------------------------------------------------
    def _apply_theme(self, theme_name: str) -> None:
        self.prefs.set("theme", theme_name)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_theme_stylesheet(theme_name))
        self.canvas.theme_name = theme_name
        self.ruler.theme_name = theme_name
        self.canvas.invalidate_caches()
        self.ruler.update()

    def _apply_language(self, lang: str) -> None:
        self.prefs.set("language", lang)
        tr = TRANSLATIONS.get(lang, TRANSLATIONS["English"])
        for key, menu in self._menu_refs.items():
            if key in tr:
                menu.setTitle(tr[key])
        self.lbl_status_info.setText(tr.get("Ready", "Ready"))

    # -----------------------------------------------------------------------
    # Project Tabs & File I/O
    # -----------------------------------------------------------------------
    def _add_project_tab(self, proj: KinoWaveProject) -> None:
        self.projects.append(proj)
        stub = QWidget()
        idx = self.proj_tabs.addTab(stub, proj.name)
        self.proj_tabs.setCurrentIndex(idx)
        self._bind_active_project(proj)

    def _bind_active_project(self, proj: KinoWaveProject) -> None:
        self.canvas.project = proj
        self.ruler.project = proj
        self.sel_bar.set_project(proj)
        self.btn_sync.setChecked(proj.sync_lock)
        self.btn_loop.setChecked(proj.loop_enabled)
        self.cb_beats.blockSignals(True)
        self.cb_beats.setChecked(proj.show_beats_grid)
        self.cb_beats.blockSignals(False)
        self.sp_bpm.blockSignals(True)
        self.sp_bpm.setValue(proj.bpm)
        self.sp_bpm.blockSignals(False)
        self.canvas.invalidate_caches()
        self._refresh_views()
        self.zoom_fit_project()

    def _on_project_tab_changed(self, idx: int) -> None:
        if 0 <= idx < len(self.projects):
            self.engine.stop()
            self._bind_active_project(self.projects[idx])

    def _close_project_tab(self, idx: int) -> None:
        if not (0 <= idx < len(self.projects)):
            return
        proj = self.projects[idx]
        if proj.dirty and self.prefs.get("show_warnings", True):
            r = QMessageBox.question(self, "Close Project", f"Save changes to '{proj.name}' before closing?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return
            if r == QMessageBox.StandardButton.Yes:
                self.save_project()
        self.engine.stop()
        self.projects.pop(idx)
        self.proj_tabs.removeTab(idx)
        if not self.projects:
            self.new_project()

    def new_project(self) -> None:
        sr = int(self.prefs.get("default_sample_rate", 48000))
        proj = KinoWaveProject(name=f"Untitled_{len(self.projects) + 1}.kwp", sample_rate=sr)
        proj.push_history("New Project")
        proj.dirty = False
        self._add_project_tab(proj)

    def open_file_dialog(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(
            self,
            "Open KinoWave Project or Audio",
            str(self.prefs.get("project_dir", "")),
            "All Supported (*.kwp *.wav *.aiff *.aif *.flac *.mp3 *.ogg *.opus *.m4a *.wma *.ac3 *.amr *.mp4 *.mkv *.mov *.mid);;KinoWave Projects (*.kwp);;All Files (*.*)",
        )
        if fp:
            self.open_path(fp)

    def open_path(self, fp: str) -> None:
        ext = os.path.splitext(fp)[1].lower()
        try:
            if ext == ".kwp":
                proj = load_kwp(fp)
                self._add_project_tab(proj)
                self.prefs.add_recent_file(fp)
                self._rebuild_recent_menu()
            elif ext in (".mid", ".midi"):
                self._import_midi_path(fp)
            elif ext == ".txt":
                self._import_labels_path(fp)
            else:
                self._import_audio_path(fp)
                self.prefs.add_recent_file(fp)
                self._rebuild_recent_menu()
        except Exception as e:
            QMessageBox.critical(self, "Open Error", str(e))

    def _rebuild_recent_menu(self) -> None:
        self.m_recent.clear()
        rec = self.prefs.get("recent_files", [])
        if not rec:
            a = self.m_recent.addAction("(No recent files)")
            a.setEnabled(False)
            return
        for fp in rec:
            self.m_recent.addAction(fp, lambda _=False, p=fp: self.open_path(p))

    def save_project(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        if not proj.file_path:
            self.save_project_as()
            return
        save_kwp(proj, proj.file_path)
        self.prefs.add_recent_file(proj.file_path)
        self._rebuild_recent_menu()
        self.lbl_status_info.setText(f"Saved project: {proj.file_path}")
        self._update_tab_title()

    def save_project_as(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Save KinoWave Project", proj.name, "KinoWave Project (*.kwp)")
        if fp:
            if not fp.lower().endswith(".kwp"):
                fp += ".kwp"
            save_kwp(proj, fp)
            self.prefs.add_recent_file(fp)
            self._rebuild_recent_menu()
            self._update_tab_title()

    def save_project_backup(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Save Copy / Backup", f"{os.path.splitext(proj.name)[0]}_backup.kwp", "KinoWave Project (*.kwp)")
        if fp:
            save_kwp(proj, fp, is_copy=True)
            self.lbl_status_info.setText(f"Backup saved to {fp}")

    def _autosave_dirty_projects(self) -> None:
        for i, p in enumerate(self.projects):
            if p.dirty and p.tracks:
                try:
                    self.recovery.save_recovery(p, f"tab{i}")
                except Exception:
                    pass

    def _check_crash_recovery(self) -> None:
        files = self.recovery.list_recoverable()
        if not files:
            return
        if QMessageBox.question(self, "Automatic Crash Recovery", f"Found {len(files)} unsaved recovery project(s). Recover them now?") == QMessageBox.StandardButton.Yes:
            for fp in files:
                try:
                    self._add_project_tab(load_kwp(fp))
                except Exception:
                    pass
        self.recovery.clear_all()

    def _on_files_dropped(self, paths: List[str]) -> None:
        for fp in paths:
            self.open_path(fp)

    def import_audio_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Audio or Video Soundtracks", "",
            "Audio/Video (*.wav *.aiff *.aif *.flac *.mp3 *.ogg *.opus *.m4a *.aac *.wma *.ac3 *.amr *.mp4 *.mkv *.mov *.avi *.webm);;All Files (*.*)",
        )
        for fp in files:
            try:
                self._import_audio_path(fp)
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"{os.path.basename(fp)}: {e}")

    def _import_audio_path(self, fp: str) -> None:
        proj = self.current_project()
        if not proj:
            self.new_project()
            proj = self.current_project()
        arr, sr, tags = import_audio_file(fp, ffmpeg_path=str(self.prefs.get("ffmpeg_path", "")))
        ch = min(2, arr.shape[0])
        tr = proj.add_audio_track(channels=ch, name=os.path.splitext(os.path.basename(fp))[0], sample_rate=sr)
        tr.view_mode = str(self.prefs.get("default_track_view", "Waveform"))
        tr.clips.append(AudioClip(samples=arr[:ch], sample_rate=sr, start_time=0.0, name=os.path.basename(fp), color=tr.color))
        if tags:
            if tags.get("artist") and not proj.metadata.artist: proj.metadata.artist = tags["artist"]
            if tags.get("title") and not proj.metadata.title: proj.metadata.title = tags["title"]
            if tags.get("album") and not proj.metadata.album: proj.metadata.album = tags["album"]
        proj.push_history(f"Imported {os.path.basename(fp)}")
        self._refresh_views()
        self.zoom_fit_project()

    def import_raw_dialog(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Import Raw Headerless Audio", "", "All Files (*.*)")
        if not fp:
            return
        dlg = ImportRawDialog(fp, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            proj = self.current_project()
            if not proj:
                return
            arr, sr = import_raw_audio(fp, dlg.cmb_enc.currentText(), dlg.cmb_end.currentText(), dlg.sp_ch.value(), dlg.sp_off.value(), dlg.sp_sr.value())
            ch = min(2, arr.shape[0])
            tr = proj.add_audio_track(channels=ch, name=os.path.basename(fp), sample_rate=sr)
            tr.clips.append(AudioClip(samples=arr[:ch], sample_rate=sr, start_time=0.0, name=os.path.basename(fp), color=tr.color))
            proj.push_history(f"Imported Raw {os.path.basename(fp)}")
            self._refresh_views()

    def import_labels_dialog(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Import Labels", "", "Text Files (*.txt);;All Files (*.*)")
        if fp:
            self._import_labels_path(fp)

    def _import_labels_path(self, fp: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        items = import_labels_txt(fp)
        tr = proj.add_label_track(os.path.splitext(os.path.basename(fp))[0])
        tr.labels = items
        proj.push_history(f"Imported Labels ({len(items)})")
        self._refresh_views()

    def export_labels_dialog(self) -> None:
        proj = self.current_project()
        if not proj or not proj.label_tracks():
            QMessageBox.information(self, "No Labels", "No Label Track in project.")
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Export Labels", "labels.txt", "Text Files (*.txt)")
        if fp:
            all_lbls = [lb for lt in proj.label_tracks() for lb in lt.labels]
            export_labels_txt(fp, all_lbls)

    def import_midi_dialog(self) -> None:
        fp, _ = QFileDialog.getOpenFileName(self, "Import MIDI", "", "MIDI Files (*.mid *.midi)")
        if fp:
            self._import_midi_path(fp)

    def _import_midi_path(self, fp: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        notes = import_midi_file(fp)
        proj.add_note_track(name=os.path.splitext(os.path.basename(fp))[0], notes=notes)
        proj.push_history(f"Imported MIDI ({len(notes)} notes)")
        self._refresh_views()

    def export_midi_dialog(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        ntracks = [t for t in proj.tracks if isinstance(t, NoteTrack)]
        if not ntracks:
            QMessageBox.information(self, "No MIDI Track", "No MIDI Note Track in project.")
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Export MIDI Note Track", "notes.mid", "MIDI Files (*.mid)")
        if fp:
            export_midi_file(fp, ntracks[0].notes, bpm=proj.bpm)

    def _open_export(self, scope: str) -> None:
        proj = self.current_project()
        if proj:
            ExportDialog(proj, self.prefs, default_scope=scope, parent=self).exec()

    def _open_metadata(self) -> None:
        proj = self.current_project()
        if proj:
            MetadataDialog(proj.metadata, self.prefs, self).exec()

    def _open_cloud_share(self) -> None:
        proj = self.current_project()
        if proj:
            CloudShareDialog(proj, self.cloud, self.open_path, self).exec()

    # -----------------------------------------------------------------------
    # Transport: Playback, Scrubbing, Cut Preview, Recording, Punch-and-Roll
    # -----------------------------------------------------------------------
    def toggle_play_stop(self) -> None:
        if self.engine.state in ("playing", "paused"):
            self.stop_all()
        else:
            self.start_playback()

    def start_playback(self, start_s: Optional[float] = None, end_s: Optional[float] = None) -> None:
        proj = self.current_project()
        if not proj or proj.duration() <= 0.0:
            return
        dur = proj.duration()
        t0 = proj.sel_start if start_s is None else max(0.0, start_s)
        t1 = (proj.sel_end if proj.has_selection() else dur) if end_s is None else min(dur, end_s)
        if t1 <= t0 + 0.01:
            t0, t1 = (0.0 if t0 >= dur - 0.05 else t0), dur
        mix = proj.mix_render(start_s=t0, end_s=t1, sample_rate=proj.sample_rate)
        loop_rel_s = max(0.0, proj.loop_start - t0) if proj.loop_enabled else 0.0
        loop_rel_e = max(0.1, proj.loop_end - t0) if (proj.loop_enabled and proj.loop_end > proj.loop_start) else None
        self.engine.play_buffer(mix, proj.sample_rate, offset_s=t0, speed=self.sp_speed.value(), loop=proj.loop_enabled, loop_start_rel=loop_rel_s, loop_end_rel=loop_rel_e)

    def play_selection(self) -> None:
        proj = self.current_project()
        if proj:
            t0, t1 = proj.selection_bounds()
            self.start_playback(t0, t1)

    def play_around_selection(self, side: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        t0, t1 = proj.selection_bounds()
        if side == "before":
            self.start_playback(max(0.0, t0 - 2.0), t0)
        else:
            self.start_playback(t1, min(proj.duration(), t1 + 2.0))

    def play_cut_preview(self) -> None:
        """Preview what cutting out the current selection would sound like."""
        proj = self.current_project()
        if not proj or not proj.has_selection():
            return
        t0, t1 = proj.selection_bounds()
        pre = float(self.prefs.get("cut_preview_before_s", 1.5))
        post = float(self.prefs.get("cut_preview_after_s", 1.5))
        a = proj.mix_render(max(0.0, t0 - pre), t0, proj.sample_rate)
        b = proj.mix_render(t1, min(proj.duration(), t1 + post), proj.sample_rate)
        cat = np.concatenate([a, b], axis=1)
        if cat.shape[1] > 0:
            self.engine.play_buffer(cat, proj.sample_rate, offset_s=max(0.0, t0 - pre), speed=1.0)

    def pause_playback(self) -> None:
        self.engine.pause()
        self.btn_pause.setChecked(self.engine.state == "paused")

    def stop_all(self) -> None:
        self.engine.stop()
        self.btn_rec.setChecked(False)
        self.btn_pause.setChecked(False)
        self.meter_in.set_levels((0.0, 0.0), (0.0, 0.0), self.engine.rec_clipped)
        self.meter_out.set_levels((0.0, 0.0), (0.0, 0.0), self.engine.play_clipped)

    def skip_to_start(self) -> None:
        proj = self.current_project()
        if proj:
            proj.set_selection(0.0, 0.0)
            self.canvas.playhead_s = 0.0
            self.ruler.playhead_s = 0.0
            self._refresh_views()

    def skip_to_end(self) -> None:
        proj = self.current_project()
        if proj:
            d = proj.duration()
            proj.set_selection(d, d)
            self.canvas.playhead_s = d
            self.ruler.playhead_s = d
            self._refresh_views()

    def seek_relative(self, delta_s: float) -> None:
        proj = self.current_project()
        if not proj:
            return
        cur = self.engine.current_time if self.engine.state == "playing" else proj.cursor_time
        nt = max(0.0, min(max(proj.duration(), 1.0), cur + delta_s))
        if self.engine.state == "playing":
            self.engine.seek(nt)
        proj.set_selection(nt, nt)
        self.canvas.playhead_s = nt
        self.ruler.playhead_s = nt
        self._refresh_views()

    def toggle_loop(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        proj.loop_enabled = not proj.loop_enabled
        if proj.loop_enabled and proj.has_selection():
            proj.loop_start, proj.loop_end = proj.selection_bounds()
        self.btn_loop.setChecked(proj.loop_enabled)
        self.ruler.update()

    def _on_speed_changed(self, spd: float) -> None:
        self.engine.set_speed(spd)
        proj = self.current_project()
        if proj:
            proj.playback_speed = spd

    def _on_quick_play(self, s0: float, s1: float) -> None:
        proj = self.current_project()
        if not proj:
            return
        self.start_playback(s0, proj.duration() if s1 <= s0 else s1)

    def _on_scrub(self, t: float) -> None:
        proj = self.current_project()
        if not proj:
            return
        # Audition short 120ms grain at scrub position smoothly
        self.canvas.playhead_s = t
        self.ruler.playhead_s = t
        if self.engine.state != "playing":
            mix = proj.mix_render(t, min(proj.duration(), t + 0.14), proj.sample_rate)
            if mix.shape[1] > 0:
                self.engine.play_buffer(mix, proj.sample_rate, offset_s=t)
        else:
            self.engine.seek(t)
        self.canvas.update()
        self.ruler.update()

    def toggle_record(self) -> None:
        if self.engine.state in ("recording", "preroll"):
            self.stop_all()
        else:
            self.start_record(new_track=False)

    def start_record(self, new_track: bool = False, preroll_s: float = 0.0) -> None:
        proj = self.current_project()
        if not proj:
            return
        target_tracks = proj.selected_audio_tracks()
        append_tr = None if (new_track or not target_tracks) else target_tracks[0]
        rec_start = append_tr.duration() if (append_tr is not None and preroll_s <= 0.0) else proj.cursor_time

        # Punch-and-roll deletes audio after punch-in point on target track first
        if preroll_s > 0.0 and append_tr is not None:
            proj.delete_range(rec_start, append_tr.duration() + 0.1, leave_gap=True, tracks=[append_tr])

        overdub_mix = None
        if self.engine.overdub or preroll_s > 0.0:
            mix_start = max(0.0, rec_start - preroll_s)
            overdub_mix = proj.mix_render(mix_start, max(proj.duration(), rec_start + 30.0), proj.sample_rate)

        def on_done(arr: np.ndarray, sr: int, start_t: float) -> None:
            ch = min(2, arr.shape[0])
            if append_tr is not None and append_tr in proj.tracks:
                tr = append_tr
            else:
                tr = proj.add_audio_track(channels=ch, name=f"Recorded Track {len(proj.audio_tracks()) + 1}", sample_rate=sr)
            tr.clips.append(AudioClip(samples=tr.ensure_channels(arr[:ch]), sample_rate=sr, start_time=start_t, name="Recording", color=tr.color))
            proj.push_history("Recorded Audio")
            QTimer.singleShot(0, self._refresh_views)

        self.btn_rec.setChecked(True)
        self.engine.start_recording(proj.sample_rate, start_time_s=rec_start, overdub_mix=overdub_mix, preroll_s=preroll_s, on_finished=on_done)
        self.lbl_status_info.setText("Recording..." if preroll_s <= 0 else f"Punch & Roll pre-roll ({preroll_s:.1f}s)...")

    def start_punch_and_roll(self) -> None:
        self.start_record(new_track=False, preroll_s=float(self.prefs.get("preroll_s", 2.0)))

    def _open_timer_record(self) -> None:
        proj = self.current_project()
        if not proj:
            return

        def _stop_and_auto(save_p: str, exp_p: str) -> None:
            self.stop_all()
            if save_p:
                save_kwp(proj, save_p)
            if exp_p:
                mix = proj.mix_render()
                export_audio_file(exp_p, mix, proj.sample_rate, "WAV", proj.sample_rate)

        TimerRecordDialog(lambda: self.start_record(new_track=True), _stop_and_auto, self).exec()

    def _auto_adjust_input_level(self) -> None:
        g = self.engine.auto_adjust_input_level()
        self.sl_in_gain.setValue(int(round(g * 100)))
        self.lbl_status_info.setText(f"Auto-level calibrated input gain to {g:.2f}x")

    # -----------------------------------------------------------------------
    # Lightweight UI Tick (Playhead + Live Meters)
    # -----------------------------------------------------------------------
    def _on_ui_tick(self) -> None:
        st = self.engine.state
        if st in ("playing", "recording", "preroll"):
            t = self.engine.current_time
            self.canvas.playhead_s = t
            self.ruler.playhead_s = t
            self.sel_bar.refresh_from_project(playhead_s=t)
            self.meter_out.set_levels(self.engine.play_peak, self.engine.play_rms, self.engine.play_clipped)
            self.meter_in.set_levels(self.engine.rec_peak, self.engine.rec_rms, self.engine.rec_clipped)
            self.canvas.update()
            self.ruler.update()
        else:
            if self.btn_rec.isChecked():
                self.btn_rec.setChecked(False)

    # -----------------------------------------------------------------------
    # Tools, Editing, Selection, Viewing, Track Management
    # -----------------------------------------------------------------------
    def set_tool(self, tool_id: str) -> None:
        self.canvas.tool = tool_id
        for tid, b in self.tool_btns.items():
            b.setChecked(tid == tool_id)
        self.lbl_status_info.setText(f"Active Tool: {tool_id.capitalize()}")

    def toggle_sync_lock(self) -> None:
        proj = self.current_project()
        if proj:
            proj.sync_lock = not proj.sync_lock
            self.btn_sync.setChecked(proj.sync_lock)
            self.canvas.update()

    def toggle_scrub_mode(self) -> None:
        self.ruler.scrub_mode = self.btn_scrub.isChecked()

    def edit_undo(self) -> None:
        proj = self.current_project()
        if proj and proj.undo():
            self._refresh_views()

    def edit_redo(self) -> None:
        proj = self.current_project()
        if proj and proj.redo():
            self._refresh_views()

    def _restore_history(self, idx: int) -> None:
        proj = self.current_project()
        if proj and proj.restore_history(idx):
            self._refresh_views()

    def _open_history(self) -> None:
        proj = self.current_project()
        if proj:
            HistoryDialog(proj, self._restore_history, self).exec()

    def edit_copy(self) -> None:
        proj = self.current_project()
        if proj:
            KinoWaveWindow.SHARED_CLIPBOARD = proj.copy_selection()
            self.lbl_status_info.setText(f"Copied {KinoWaveWindow.SHARED_CLIPBOARD['duration']:.2f}s to KinoWave clipboard")

    def edit_cut(self) -> None:
        proj = self.current_project()
        if proj and proj.has_selection():
            KinoWaveWindow.SHARED_CLIPBOARD = proj.copy_selection()
            t0, t1 = proj.selection_bounds()
            proj.delete_range(t0, t1, leave_gap=False)
            proj.push_history("Cut")
            self._refresh_views()

    def edit_paste(self) -> None:
        proj = self.current_project()
        if proj and KinoWaveWindow.SHARED_CLIPBOARD:
            proj.paste_clipboard(KinoWaveWindow.SHARED_CLIPBOARD, proj.cursor_time)
            proj.push_history("Paste")
            self._refresh_views()

    def edit_delete(self) -> None:
        proj = self.current_project()
        if proj and proj.has_selection():
            t0, t1 = proj.selection_bounds()
            proj.delete_range(t0, t1, leave_gap=False)
            proj.push_history("Delete")
            self._refresh_views()

    def edit_split_cut(self) -> None:
        proj = self.current_project()
        if proj and proj.has_selection():
            KinoWaveWindow.SHARED_CLIPBOARD = proj.copy_selection()
            t0, t1 = proj.selection_bounds()
            proj.delete_range(t0, t1, leave_gap=True)
            proj.push_history("Split Cut")
            self._refresh_views()

    def edit_split_delete(self) -> None:
        proj = self.current_project()
        if proj and proj.has_selection():
            t0, t1 = proj.selection_bounds()
            proj.delete_range(t0, t1, leave_gap=True)
            proj.push_history("Split Delete")
            self._refresh_views()

    def edit_duplicate(self) -> None:
        proj = self.current_project()
        if proj and proj.duplicate_selection():
            proj.push_history("Duplicate")
            self._refresh_views()

    def edit_silence(self) -> None:
        proj = self.current_project()
        if proj and proj.has_selection():
            t0, t1 = proj.selection_bounds()
            proj.silence_range(t0, t1)
            proj.push_history("Silence Audio")
            self._refresh_views()

    def edit_trim(self) -> None:
        proj = self.current_project()
        if proj and proj.has_selection():
            t0, t1 = proj.selection_bounds()
            proj.trim_to_range(t0, t1)
            proj.push_history("Trim Audio")
            self._refresh_views()

    def edit_split(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        n = 0
        if proj.has_selection():
            n += proj.split_at_time(proj.sel_start)
            n += proj.split_at_time(proj.sel_end)
        else:
            n += proj.split_at_time(proj.cursor_time)
        if n:
            proj.push_history("Split Clip")
            self._refresh_views()

    def edit_split_new(self) -> None:
        proj = self.current_project()
        if proj and proj.has_selection() and proj.split_new_track():
            proj.push_history("Split New Track")
            self._refresh_views()

    def edit_join(self) -> None:
        proj = self.current_project()
        if proj:
            t0, t1 = proj.selection_bounds()
            if proj.join_clips_in_range(t0, t1):
                proj.push_history("Join Clips")
                self._refresh_views()

    def edit_detach_silences(self) -> None:
        proj = self.current_project()
        if proj and proj.detach_at_silences():
            proj.push_history("Detach at Silences")
            self._refresh_views()

    def add_label_at_selection(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        lt = proj.label_tracks()[0] if proj.label_tracks() else proj.add_label_track("Labels")
        t0 = self.engine.current_time if self.engine.state == "playing" else proj.sel_start
        t1 = t0 if self.engine.state == "playing" else proj.sel_end
        txt, ok = QInputDialog.getText(self, "Add Label", "Label Text:", text=f"Marker {len(lt.labels) + 1}")
        if ok:
            lt.labels.append(LabelItem(start=min(t0, t1), end=max(t0, t1), text=txt))
            proj.push_history("Added Label")
            self._refresh_views()

    def _on_edit_label_inline(self, track_uid: str, label_uid: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        for lt in proj.label_tracks():
            if lt.uid == track_uid:
                for lb in lt.labels:
                    if lb.uid == label_uid:
                        txt, ok = QInputDialog.getText(self, "Edit Label", "Label Text:", text=lb.text)
                        if ok:
                            lb.text = txt
                            proj.push_history("Renamed Label")
                            self._refresh_views()
                        return

    def _open_label_editor(self) -> None:
        proj = self.current_project()
        if proj and LabelEditorDialog(proj, self).exec() == QDialog.DialogCode.Accepted:
            proj.push_history("Edited Labels Table")
            self._refresh_views()

    def _labeled_audio_op(self, op: str) -> None:
        proj = self.current_project()
        if not proj or not proj.label_tracks():
            return
        labels = sorted(proj.label_tracks()[0].labels, key=lambda x: x.start, reverse=True)
        for lb in labels:
            if lb.end <= lb.start + 1e-4:
                continue
            if op == "cut":
                proj.delete_range(lb.start, lb.end, leave_gap=False)
            elif op == "delete":
                proj.delete_range(lb.start, lb.end, leave_gap=False)
            elif op == "split_cut":
                proj.delete_range(lb.start, lb.end, leave_gap=True)
            elif op == "split_delete":
                proj.delete_range(lb.start, lb.end, leave_gap=True)
            elif op == "silence":
                proj.silence_range(lb.start, lb.end)
            elif op == "split":
                proj.split_at_time(lb.start)
                proj.split_at_time(lb.end)
            elif op == "join":
                proj.join_clips_in_range(lb.start, lb.end)
        proj.push_history(f"Labeled Audio: {op}")
        self._refresh_views()

    # Selection Actions
    def select_all(self) -> None:
        proj = self.current_project()
        if proj:
            for t in proj.tracks:
                t.selected = True
            proj.set_selection(0.0, proj.duration())
            self._refresh_views()

    def select_none(self) -> None:
        proj = self.current_project()
        if proj:
            proj.set_selection(proj.cursor_time, proj.cursor_time)
            proj.spectral_low_hz = None
            proj.spectral_high_hz = None
            self._refresh_views()

    def select_all_tracks(self) -> None:
        proj = self.current_project()
        if proj:
            for t in proj.tracks:
                t.selected = True
            self._refresh_views()

    def select_to_start(self) -> None:
        proj = self.current_project()
        if proj:
            proj.set_selection(0.0, proj.cursor_time)
            self._refresh_views()

    def select_to_end(self) -> None:
        proj = self.current_project()
        if proj:
            proj.set_selection(proj.cursor_time, proj.duration())
            self._refresh_views()

    def store_cursor(self) -> None:
        proj = self.current_project()
        if proj:
            proj.stored_cursor = proj.cursor_time
            self.lbl_status_info.setText(f"Stored cursor at {proj.cursor_time:.3f}s")

    def recall_cursor(self) -> None:
        proj = self.current_project()
        if proj and proj.stored_cursor is not None:
            proj.set_selection(proj.stored_cursor, proj.stored_cursor)
            self._refresh_views()

    def store_selection(self) -> None:
        proj = self.current_project()
        if proj:
            proj.stored_selection = (proj.sel_start, proj.sel_end)
            self.lbl_status_info.setText(f"Stored selection [{proj.sel_start:.3f}s .. {proj.sel_end:.3f}s]")

    def recall_selection(self) -> None:
        proj = self.current_project()
        if proj and proj.stored_selection is not None:
            proj.set_selection(*proj.stored_selection)
            self._refresh_views()

    def snap_selection_zero_crossings(self) -> None:
        proj = self.current_project()
        if not proj or not proj.selected_audio_tracks():
            return
        tr = proj.selected_audio_tracks()[0]
        arr, t_off = tr.flatten_to_single_array()
        if arr.shape[1] < 4:
            return
        i0 = find_zero_crossing(arr, int((proj.sel_start - t_off) * tr.sample_rate))
        i1 = find_zero_crossing(arr, int((proj.sel_end - t_off) * tr.sample_rate))
        proj.set_selection(t_off + i0 / tr.sample_rate, t_off + i1 / tr.sample_rate)
        self._refresh_views()

    def _set_spectral_selection_dialog(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        fl, ok1 = QInputDialog.getDouble(self, "Spectral Selection", "Low Frequency (Hz):", proj.spectral_low_hz or 300.0, 20.0, 24000.0, 1)
        if not ok1:
            return
        fh, ok2 = QInputDialog.getDouble(self, "Spectral Selection", "High Frequency (Hz):", proj.spectral_high_hz or 3000.0, fl + 10.0, 24000.0, 1)
        if ok2:
            proj.spectral_low_hz, proj.spectral_high_hz = fl, fh
            for tr in proj.selected_audio_tracks():
                if tr.view_mode == "Waveform":
                    tr.view_mode = "Split View"
            self._refresh_views()

    # Zoom & View
    def _zoom_by_factor(self, factor: float, anchor_s: Optional[float] = None) -> None:
        old_pps = self.canvas.pps
        new_pps = float(np.clip(old_pps * factor, 4.0, 48000.0))
        if anchor_s is None and self.current_project():
            anchor_s = self.current_project().cursor_time
        if anchor_s is not None:
            px_offset = (anchor_s - self.canvas.scroll_x_s) * old_pps
            self.canvas.scroll_x_s = max(0.0, anchor_s - px_offset / new_pps)
        self.canvas.pps = new_pps
        self.ruler.pps = new_pps
        self.ruler.scroll_x_s = self.canvas.scroll_x_s
        self._sync_scrollbars()
        self.canvas.update()
        self.ruler.update()

    def zoom_normal(self) -> None:
        self.canvas.pps = float(self.prefs.get("default_zoom_pps", 100.0))
        self.ruler.pps = self.canvas.pps
        self._sync_scrollbars()
        self.canvas.update()
        self.ruler.update()

    def zoom_to_selection(self) -> None:
        proj = self.current_project()
        if not proj or not proj.has_selection():
            return
        t0, t1 = proj.selection_bounds()
        lane_w = max(200, self.canvas.width() - 240)
        self.canvas.pps = float(np.clip(lane_w / max(0.005, t1 - t0), 4.0, 48000.0))
        self.canvas.scroll_x_s = max(0.0, t0 - 0.05 * (t1 - t0))
        self.ruler.pps = self.canvas.pps
        self.ruler.scroll_x_s = self.canvas.scroll_x_s
        self._sync_scrollbars()
        self.canvas.update()
        self.ruler.update()

    def zoom_fit_project(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        dur = max(1.0, proj.duration())
        lane_w = max(200, self.canvas.width() - 250)
        self.canvas.pps = float(np.clip(lane_w / (dur * 1.06), 4.0, 2000.0))
        self.canvas.scroll_x_s = 0.0
        self.ruler.pps = self.canvas.pps
        self.ruler.scroll_x_s = 0.0
        self._sync_scrollbars()
        self.canvas.update()
        self.ruler.update()

    def fit_tracks_vertically(self) -> None:
        proj = self.current_project()
        if not proj or not proj.tracks:
            return
        avail = max(160, self.canvas.height() - 20)
        per = max(54, int((avail - 6 * len(proj.tracks)) / len(proj.tracks)))
        for t in proj.tracks:
            t.collapsed = False
            t.height = per
        self.canvas.scroll_y = 0
        self._refresh_views()

    def _set_all_collapsed(self, val: bool) -> None:
        proj = self.current_project()
        if proj:
            for t in proj.tracks:
                t.collapsed = val
            self._refresh_views()

    def _toggle_show_clipping(self) -> None:
        proj = self.current_project()
        if proj:
            for tr in proj.selected_audio_tracks():
                tr.show_clipping = not tr.show_clipping
            self.canvas.invalidate_caches()

    def _toggle_beats_grid(self, checked: bool) -> None:
        proj = self.current_project()
        if proj:
            proj.show_beats_grid = checked
            self.cb_beats.blockSignals(True)
            self.cb_beats.setChecked(checked)
            self.cb_beats.blockSignals(False)
            self.ruler.update()
            self.canvas.update()

    def _on_bpm_changed(self, bpm: float) -> None:
        proj = self.current_project()
        if proj:
            proj.bpm = bpm
            self.ruler.update()
            self.canvas.update()
            self.sel_bar.refresh_from_project()

    def _set_time_signature(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        num, ok = QInputDialog.getInt(self, "Time Signature", "Beats per Measure (Numerator):", proj.time_sig_num, 1, 16)
        if ok:
            proj.time_sig_num = num
            self.ruler.update()
            self.canvas.update()

    def _reset_toolbars(self) -> None:
        for tb in self.toolbars.values():
            tb.setVisible(True)
            tb.setFloating(False)
        self.dock_inspector.setVisible(True)

    # Track Header Actions & Track Management
    def _on_track_header_action(self, uid: str, action: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        tr = next((t for t in proj.tracks if t.uid == uid), None)
        if tr is None:
            return
        if action == "close":
            proj.remove_track(uid)
            proj.push_history(f"Removed Track {tr.name}")
        elif action == "collapse":
            tr.collapsed = not tr.collapsed
        elif action == "mute" and hasattr(tr, "mute"):
            tr.mute = not tr.mute
        elif action == "solo" and hasattr(tr, "solo"):
            tr.solo = not tr.solo
        elif action == "sync":
            tr.sync_lock = not tr.sync_lock
        elif action == "fx" and isinstance(tr, AudioTrack):
            RealtimeEffectsDialog(tr.name, tr.realtime_effects, self.presets, self.plugins, proj.sample_rate, self).exec()
            proj.push_history(f"Updated FX on {tr.name}")
        elif action == "edit_labels":
            self._open_label_editor()
        elif action == "menu":
            self._show_track_dropdown_menu(tr)
        self._refresh_views()

    def _show_track_dropdown_menu(self, tr) -> None:
        proj = self.current_project()
        if not proj:
            return
        m = QMenu(self)
        a_ren = m.addAction("Rename Track...")
        a_up = m.addAction("Move Track Up")
        a_dn = m.addAction("Move Track Down")
        m.addSeparator()
        view_acts = {}
        a_spec_cfg = a_col = a_rate = a_fmt = a_split_m = a_split_lr = a_swap = a_mix_m = a_fx = None
        if isinstance(tr, AudioTrack):
            for vm in ("Waveform", "Waveform (dB)", "Spectrogram", "Split View"):
                va = m.addAction(vm)
                va.setCheckable(True); va.setChecked(tr.view_mode == vm)
                view_acts[va] = vm
            a_spec_cfg = m.addAction("Spectrogram Settings...")
            m.addSeparator()
            a_fx = m.addAction("Real-Time Effects Rack...")
            a_col = m.addAction("Track Wave Color...")
            a_rate = m.addAction("Set Sample Rate (Resample)...")
            a_fmt = m.addAction("Set Sample Format...")
            if tr.channels == 2:
                m.addSeparator()
                a_split_lr = m.addAction("Split Stereo Track (L/R)")
                a_split_m = m.addAction("Split Stereo to Mono")
                a_swap = m.addAction("Swap Stereo Channels")
                a_mix_m = m.addAction("Mix Stereo Down to Mono")
        chosen = m.exec(self.cursor().pos())
        if not chosen:
            return
        if chosen == a_ren:
            name, ok = QInputDialog.getText(self, "Rename Track", "Track Name:", text=tr.name)
            if ok and name.strip():
                tr.name = name.strip()
                proj.push_history("Renamed Track")
        elif chosen == a_up:
            proj.move_track(tr.uid, -1)
        elif chosen == a_dn:
            proj.move_track(tr.uid, 1)
        elif chosen in view_acts and isinstance(tr, AudioTrack):
            tr.view_mode = view_acts[chosen]
            self.canvas.invalidate_caches()
        elif chosen == a_spec_cfg and isinstance(tr, AudioTrack):
            if SpectrogramSettingsDialog(tr.spectrogram, self).exec() == QDialog.DialogCode.Accepted:
                self.canvas.invalidate_caches()
        elif chosen == a_fx and isinstance(tr, AudioTrack):
            RealtimeEffectsDialog(tr.name, tr.realtime_effects, self.presets, self.plugins, proj.sample_rate, self).exec()
        elif chosen == a_col and isinstance(tr, AudioTrack):
            col = QColorDialog.getColor(QColor(tr.color), self, "Track Color")
            if col.isValid():
                tr.color = col.name()
                for c in tr.clips:
                    c.color = tr.color
                self.canvas.invalidate_caches()
        elif chosen == a_rate and isinstance(tr, AudioTrack):
            sr_str, ok = QInputDialog.getItem(self, "Resample Track", "New Sample Rate (Hz):", [str(r) for r in SAMPLE_RATES], SAMPLE_RATES.index(tr.sample_rate) if tr.sample_rate in SAMPLE_RATES else 6, False)
            if ok:
                new_sr = int(sr_str)
                for c in tr.clips:
                    c.samples = resample_audio(c.samples, c.sample_rate, new_sr, str(self.prefs.get("resample_quality", "High")))
                    c.sample_rate = new_sr
                tr.sample_rate = new_sr
                proj.push_history(f"Resampled {tr.name} to {new_sr} Hz")
        elif chosen == a_fmt and isinstance(tr, AudioTrack):
            fmt, ok = QInputDialog.getItem(self, "Sample Format", "Format:", SAMPLE_FORMATS, 0, False)
            if ok:
                tr.sample_format = fmt
        elif chosen == a_split_lr and isinstance(tr, AudioTrack):
            proj.split_stereo_track(tr, to_mono=False); proj.push_history("Split Stereo Track")
        elif chosen == a_split_m and isinstance(tr, AudioTrack):
            proj.split_stereo_track(tr, to_mono=True); proj.push_history("Split Stereo to Mono")
        elif chosen == a_swap and isinstance(tr, AudioTrack):
            proj.swap_stereo_channels(tr); proj.push_history("Swapped Stereo Channels")
        elif chosen == a_mix_m and isinstance(tr, AudioTrack):
            proj.mix_stereo_to_mono(tr); proj.push_history("Mixed Stereo to Mono")
        self._refresh_views()

    def _add_track(self, kind: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        if kind == "mono": proj.add_audio_track(channels=1)
        elif kind == "stereo": proj.add_audio_track(channels=2)
        elif kind == "label": proj.add_label_track()
        elif kind == "time": proj.add_time_track()
        elif kind == "note": proj.add_note_track()
        proj.push_history(f"Added {kind.capitalize()} Track")
        self._refresh_views()

    def _make_stereo_selected(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        monos = [t for t in proj.selected_audio_tracks() if t.channels == 1]
        if len(monos) < 2:
            QMessageBox.information(self, "Make Stereo Track", "Select two Mono tracks first (Ctrl+Click track headers).")
            return
        if proj.make_stereo_from_two_mono(monos[0], monos[1]):
            proj.push_history("Made Stereo Track")
            self._refresh_views()

    def _mix_and_render(self, to_new: bool) -> None:
        proj = self.current_project()
        if not proj:
            return
        sel = proj.selected_audio_tracks()
        if not sel:
            return
        dur = max(t.duration() for t in sel)
        if dur <= 0:
            return
        mix = proj.mix_render(0.0, dur, proj.sample_rate, tracks=sel, apply_master_fx=False)
        if not to_new:
            for t in sel:
                proj.remove_track(t.uid)
        nt = proj.add_audio_track(channels=2, name="Mixdown")
        nt.clips.append(AudioClip(samples=mix, sample_rate=proj.sample_rate, start_time=0.0, name="Mixdown", color=nt.color))
        proj.push_history("Mix and Render")
        self._refresh_views()

    def _resample_selected(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        sr_str, ok = QInputDialog.getItem(self, "Resample Selected Tracks", "Target Sample Rate (Hz):", [str(r) for r in SAMPLE_RATES], 6, False)
        if not ok:
            return
        nsr = int(sr_str)
        for tr in proj.selected_audio_tracks():
            for c in tr.clips:
                c.samples = resample_audio(c.samples, c.sample_rate, nsr)
                c.sample_rate = nsr
            tr.sample_rate = nsr
        proj.push_history(f"Resampled Tracks to {nsr} Hz")
        self._refresh_views()

    def _align_tracks(self, mode: str) -> None:
        proj = self.current_project()
        if proj:
            proj.align_tracks(mode)
            proj.push_history(f"Aligned Tracks ({mode})")
            self._refresh_views()

    def _sort_tracks(self, by: str) -> None:
        proj = self.current_project()
        if proj:
            proj.sort_tracks(by)
            self._refresh_views()

    def _mute_all(self, val: bool) -> None:
        proj = self.current_project()
        if proj:
            for t in proj.tracks:
                if hasattr(t, "mute"):
                    t.mute = val
            self._refresh_views()

    # -----------------------------------------------------------------------
    # Generators, Destructive & Real-Time Effects, Analysis
    # -----------------------------------------------------------------------
    def _run_generator(self, gen_type: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        default_dur = (proj.sel_end - proj.sel_start) if proj.has_selection() else 5.0
        dlg = GeneratorDialog(gen_type, default_dur=default_dur, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        sr = proj.sample_rate
        sel_tr = proj.selected_audio_tracks()
        tr = sel_tr[0] if sel_tr else proj.add_audio_track(channels=1, name=f"Generated {gen_type}")
        ch = tr.channels
        if gen_type == "Tone": arr = gen_tone(sr, v["duration_s"], v["waveform"], v["freq_hz"], v["amplitude"], ch)
        elif gen_type == "Chirp": arr = gen_chirp(sr, v["duration_s"], v["waveform"], v["f_start"], v["f_end"], v["amp_start"], v["amp_end"], v["interp"], ch)
        elif gen_type == "Noise": arr = gen_noise(sr, v["duration_s"], v["noise_type"], v["amplitude"], ch)
        elif gen_type == "DTMF Tones": arr = gen_dtmf(sr, v["sequence"], v["duration_s"], v["duty_cycle_pct"], v["amplitude"], ch)
        elif gen_type == "Silence": arr = gen_silence(sr, v["duration_s"], ch)
        elif gen_type == "Rhythm Track": arr = gen_rhythm_track(sr, v["bpm"], v["beats_per_bar"], v["num_bars"], v["swing"], v["click_sound"], ch)
        elif gen_type == "Risset Drum": arr = gen_risset_drum(sr, v["freq_hz"], v["decay_s"], v["noise_cf_hz"], v["noise_bw_hz"], v["noise_pct"], v["amplitude"], ch)
        else: arr = gen_plucked(sr, v["midi_pitch"], v["duration_s"], v["decay_type"], v["amplitude"], ch)

        ins_t = proj.sel_start if proj.has_selection() else proj.cursor_time
        if proj.has_selection():
            proj.delete_range(proj.sel_start, proj.sel_end, leave_gap=True, tracks=[tr])
        tr.clips.append(AudioClip(samples=arr, sample_rate=sr, start_time=ins_t, name=gen_type, color=tr.color))
        proj.push_history(f"Generated {gen_type}")
        self._refresh_views()
        self.zoom_fit_project()

    def _open_effect_dialog(self, effect_name: str) -> None:
        proj = self.current_project()
        if not proj or not proj.selected_audio_tracks():
            QMessageBox.information(self, "No Audio Track", "Add or import an audio track before applying effects.")
            return

        init_params = None
        if effect_name.startswith("Spectral") and proj.spectral_low_hz and proj.spectral_high_hz:
            init_params = {"freq_low": proj.spectral_low_hz, "freq_high": proj.spectral_high_hz}

        extra_ctx: Dict[str, Any] = {}
        if proj.noise_profile is not None:
            extra_ctx["noise_profile"] = proj.noise_profile
        atracks = proj.selected_audio_tracks()
        if effect_name == "Auto Duck" and len(proj.audio_tracks()) >= 2:
            # Use track directly below selected track as control track (Audacity convention)
            all_a = proj.audio_tracks()
            idx = all_a.index(atracks[0])
            ctrl_tr = all_a[(idx + 1) % len(all_a)]
            t0, t1 = proj.selection_bounds()
            extra_ctx["control_audio"] = ctrl_tr.render_range(t0, t1, proj.sample_rate, apply_realtime_fx=False)

        def on_preview(params: Dict[str, Any]) -> None:
            t0, t1 = proj.selection_bounds()
            t1 = min(t1, t0 + 4.0)
            seg = atracks[0].render_range(t0, t1, proj.sample_rate, apply_realtime_fx=False)
            if seg.shape[1] == 0:
                return
            proc = run_effect(effect_name, seg, proj.sample_rate, params, extra_ctx=extra_ctx)
            self.engine.play_buffer(proc, proj.sample_rate, offset_s=t0)

        def on_get_np() -> None:
            t0, t1 = proj.selection_bounds()
            seg = atracks[0].render_range(t0, t1, proj.sample_rate, apply_realtime_fx=False)
            if seg.shape[1] > 64:
                proj.noise_profile = capture_noise_profile(seg, proj.sample_rate)
                extra_ctx["noise_profile"] = proj.noise_profile

        dlg = EffectDialog(
            effect_name,
            self.presets,
            initial_params=init_params,
            on_preview=on_preview,
            on_get_noise_profile=on_get_np if effect_name == "Noise Reduction" else None,
            has_noise_profile=(proj.noise_profile is not None),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
            self.last_effect_name = effect_name
            self.last_effect_params = params
            proj.apply_destructive_processor(lambda arr, sr: run_effect(effect_name, arr, sr, params, extra_ctx=extra_ctx), f"Effect: {effect_name}")
            self.canvas.invalidate_caches()
            self._refresh_views()

    def _repeat_last_effect(self) -> None:
        proj = self.current_project()
        if not proj or not self.last_effect_name:
            return
        ename, params = self.last_effect_name, self.last_effect_params
        proj.apply_destructive_processor(lambda arr, sr: run_effect(ename, arr, sr, params), f"Repeat Effect: {ename}")
        self.canvas.invalidate_caches()
        self._refresh_views()

    def _open_selected_track_fx(self) -> None:
        proj = self.current_project()
        if proj and proj.selected_audio_tracks():
            tr = proj.selected_audio_tracks()[0]
            RealtimeEffectsDialog(tr.name, tr.realtime_effects, self.presets, self.plugins, proj.sample_rate, self).exec()
            proj.push_history(f"Updated Track FX ({tr.name})")
            self._refresh_views()

    def _open_master_fx(self) -> None:
        proj = self.current_project()
        if proj:
            RealtimeEffectsDialog("Master Output Bus", proj.master_effects, self.presets, self.plugins, proj.sample_rate, self).exec()
            proj.push_history("Updated Master FX Rack")
            self._refresh_views()

    def _rebuild_external_fx_menu(self) -> None:
        self.m_external_fx.clear()
        groups: Dict[str, QMenu] = {}
        count = 0
        for pl in self.plugins.plugins:
            if not pl.get("enabled"):
                continue
            ptype = pl["type"]
            if ptype not in ("VST3", "VST2 (64-bit)", "Audio Unit", "LADSPA", "Nyquist"):
                continue
            if ptype not in groups:
                groups[ptype] = self.m_external_fx.addMenu(ptype)
            sub_parent = groups[ptype]
            if ptype == "Nyquist":
                sub_parent.addAction(pl["name"], lambda _=False, p=pl["path"]: self._run_nyquist_file(p))
            else:
                sub_parent.addAction(f"{pl['name']}...", lambda _=False, info=pl: self._open_external_plugin_dialog(info))
            count += 1
        if count == 0:
            a = self.m_external_fx.addAction("(No external plugins enabled — open Plugin Manager)")
            a.setEnabled(False)

    def _open_external_plugin_dialog(self, plugin_info: Dict[str, Any]) -> None:
        proj = self.current_project()
        if not proj or not proj.selected_audio_tracks():
            QMessageBox.information(self, "No Audio Track", "Add or import an audio track before applying a plugin.")
            return
        atracks = proj.selected_audio_tracks()

        def on_preview(params: Dict[str, Any]) -> None:
            t0, t1 = proj.selection_bounds()
            t1 = min(t1, t0 + 4.0)
            seg = atracks[0].render_range(t0, t1, proj.sample_rate, apply_realtime_fx=False)
            if seg.shape[1] == 0:
                return
            proc = run_effect(plugin_info["name"], seg, proj.sample_rate, params)
            self.engine.play_buffer(proc, proj.sample_rate, offset_s=t0)

        try:
            dlg = ExternalPluginDialog(plugin_info, sample_rate=proj.sample_rate, on_preview=on_preview, apply_label="Apply to Track", parent=self)
        except Exception as e:
            QMessageBox.critical(self, "Plugin Load Error", f"Could not load '{plugin_info['name']}':\n{e}")
            return
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
            self.last_effect_name = plugin_info["name"]
            self.last_effect_params = params
            proj.apply_destructive_processor(lambda arr, sr: run_effect(plugin_info["name"], arr, sr, params), f"{plugin_info['type']}: {plugin_info['name']}")
            self.canvas.invalidate_caches()
            self._refresh_views()

    # Analysis Actions
    def _selected_mix(self) -> np.ndarray:
        proj = self.current_project()
        if not proj:
            return np.zeros((2, 0), dtype=np.float32)
        t0, t1 = proj.selection_bounds()
        return proj.mix_render(t0, t1, proj.sample_rate)

    def _open_plot_spectrum(self) -> None:
        proj = self.current_project()
        if proj:
            PlotSpectrumDialog(self._selected_mix(), proj.sample_rate, self).exec()

    def _open_contrast(self) -> None:
        ContrastAnalysisDialog(self._selected_mix, self).exec()

    def _analyze_measure_rms(self) -> None:
        res = measure_rms(self._selected_mix())
        QMessageBox.information(self, "Measure RMS", res["summary"])

    def _add_analysis_labels(self, name: str, items: List) -> None:
        proj = self.current_project()
        if not proj:
            return
        t0, _ = proj.selection_bounds()
        lt = proj.add_label_track(name)
        lt.labels = [LabelItem(start=t0 + s, end=t0 + e, text=txt) for s, e, txt in items]
        proj.push_history(f"Analyze: {name} ({len(items)})")
        self._refresh_views()
        self.lbl_status_info.setText(f"{name}: created {len(items)} labels")

    def _analyze_find_clipping(self) -> None:
        proj = self.current_project()
        if proj:
            items = find_clipping(self._selected_mix(), proj.sample_rate)
            self._add_analysis_labels("Clipping", items)

    def _analyze_beat_finder(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        thr, ok = QInputDialog.getDouble(self, "Beat Finder", "Threshold Percentage (5-95):", 65.0, 5.0, 95.0, 1)
        if ok:
            self._add_analysis_labels("Beats", find_beats(self._selected_mix(), proj.sample_rate, thr))

    def _analyze_sounds_silences(self, mode: str) -> None:
        proj = self.current_project()
        if not proj:
            return
        db, ok1 = QInputDialog.getDouble(self, f"Label {mode}", "Threshold Level (dB):", -30.0, -80.0, -3.0, 1)
        if not ok1:
            return
        md, ok2 = QInputDialog.getDouble(self, f"Label {mode}", "Minimum Duration (s):", 0.35, 0.05, 30.0, 2)
        if ok2:
            self._add_analysis_labels(f"{mode} Labels", find_sounds_or_silences(self._selected_mix(), proj.sample_rate, mode, db, md))

    def _analyze_regular_labels(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        iv, ok = QInputDialog.getDouble(self, "Regular Interval Labels", "Label Interval (seconds):", 2.0, 0.1, 600.0, 2)
        if ok:
            t0, t1 = proj.selection_bounds()
            items = generate_regular_interval_labels(0.0, max(0.1, t1 - t0), iv)
            self._add_analysis_labels("Regular Labels", items)

    def _sample_data_export(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        fp, _ = QFileDialog.getSaveFileName(self, "Sample Data Export", "samples.csv", "CSV (*.csv);;Plain Text (*.txt)")
        if fp:
            fmt = "CSV" if fp.lower().endswith(".csv") else "Plain Text"
            txt = export_sample_data_text(self._selected_mix(), proj.sample_rate, fmt=fmt)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(txt)
            self.lbl_status_info.setText(f"Exported sample data to {fp}")

    def _sample_data_import(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        fp, _ = QFileDialog.getOpenFileName(self, "Sample Data Import", "", "Text / CSV (*.txt *.csv);;All Files (*.*)")
        if fp:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                arr = import_sample_data_text(f.read())
            if arr.shape[1] > 0:
                tr = proj.add_audio_track(channels=arr.shape[0], name=os.path.basename(fp))
                tr.clips.append(AudioClip(samples=arr, sample_rate=proj.sample_rate, start_time=0.0, name=os.path.basename(fp), color=tr.color))
                proj.push_history("Imported Sample Data")
                self._refresh_views()

    # -----------------------------------------------------------------------
    # Automation: Macros, Nyquist, Plugins, Pipe, Screenshot, Benchmark, Prefs
    # -----------------------------------------------------------------------
    def _open_macros(self) -> None:
        proj = self.current_project()
        if not proj:
            return

        def run_macro_on_proj(mname: str) -> None:
            proj.apply_destructive_processor(lambda arr, sr: self.macros.run_on_audio(mname, arr, sr)[0], f"Macro: {mname}")
            self.canvas.invalidate_caches()
            self._refresh_views()

        MacroBatchDialog(self.macros, self.prefs, run_macro_on_proj, self).exec()

    def _eval_nyquist_code(self, code: str) -> str:
        proj = self.current_project()
        if not proj:
            return "No active project."
        try:
            t0, t1 = proj.selection_bounds()
            sel = proj.selected_audio_tracks()[0].render_range(t0, t1, proj.sample_rate, apply_realtime_fx=False) if proj.selected_audio_tracks() else None
            res, msg = self.nyquist.evaluate(code, sel, proj.sample_rate, duration_s=max(1.0, t1 - t0))
            if isinstance(res, np.ndarray) and res.size > 0:
                tr = proj.selected_audio_tracks()[0] if proj.selected_audio_tracks() else proj.add_audio_track(channels=min(2, res.shape[0]), name="Nyquist Output")
                if proj.has_selection():
                    proj.delete_range(t0, t1, leave_gap=True, tracks=[tr])
                tr.clips.append(AudioClip(samples=tr.ensure_channels(res), sample_rate=proj.sample_rate, start_time=t0 if proj.has_selection() else proj.cursor_time, name="Nyquist", color=tr.color))
                proj.push_history("Nyquist Script")
                self.canvas.invalidate_caches()
                self._refresh_views()
            return msg
        except Exception as e:
            return f"Nyquist Error: {e}"

    def _open_nyquist_prompt(self) -> None:
        NyquistPromptDialog(self._eval_nyquist_code, self).exec()

    def _run_nyquist_file(self, path: str) -> None:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            msg = self._eval_nyquist_code(f.read())
        self.lbl_status_info.setText(msg)

    def _open_plugin_manager(self) -> None:
        def add_dir(d: str) -> None:
            dirs = list(self.prefs.get("custom_vst_dirs", []))
            if d not in dirs:
                dirs.append(d)
                self.prefs.set("custom_vst_dirs", dirs)

        PluginManagerDialog(
            self.plugins,
            self._run_nyquist_file,
            on_run_external_plugin=self._open_external_plugin_dialog,
            on_add_custom_dir=add_dir,
            parent=self,
        ).exec()
        self._rebuild_external_fx_menu()

    def _open_scripting_pipe(self) -> None:
        ScriptingPipeDialog(self.pipe_server, self).exec()

    def _handle_pipe_command(self, raw_cmd: str) -> str:
        """Process Audacity-compatible scripting pipe commands safely."""
        parts = raw_cmd.split(":", 1)
        cmd = parts[0].strip()
        arg_str = parts[1].strip() if len(parts) > 1 else ""
        kv: Dict[str, str] = {}
        for tok in arg_str.split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                kv[k.strip()] = v.strip().strip('"')
        proj = self.current_project()
        if not proj:
            return "No active project"
        if cmd == "Play":
            QTimer.singleShot(0, self.start_playback)
            return "Playback started"
        if cmd == "Stop":
            QTimer.singleShot(0, self.stop_all)
            return "Playback stopped"
        if cmd == "Select":
            s = float(kv.get("Start", 0.0))
            e = float(kv.get("End", proj.duration()))
            proj.set_selection(s, e)
            QTimer.singleShot(0, self._refresh_views)
            return f"Selected {s}..{e}s"
        if cmd == "GetInfo":
            return f"Project={proj.name} SR={proj.sample_rate} Tracks={len(proj.tracks)} Duration={proj.duration():.3f}s"
        if cmd in EFFECT_REGISTRY:
            parsed = {}
            for k, v in kv.items():
                try:
                    parsed[k] = float(v)
                except ValueError:
                    parsed[k] = v
            proj.apply_destructive_processor(lambda a, sr: run_effect(cmd, a, sr, parsed), f"Pipe: {cmd}")
            QTimer.singleShot(0, self._refresh_views)
            return f"Applied {cmd}"
        return f"Executed command '{cmd}'"

    def _capture_screenshot(self) -> None:
        fp, _ = QFileDialog.getSaveFileName(self, "Save Interface Screenshot", "kinowave_screenshot.png", "PNG Image (*.png)")
        if fp:
            self.grab().save(fp)
            self.lbl_status_info.setText(f"Screenshot saved to {fp}")

    def _run_benchmark(self) -> None:
        report = run_performance_benchmark(int(self.prefs.get("default_sample_rate", 48000)), duration_s=5.0)
        QMessageBox.information(self, "KinoWave Performance Benchmark", report)

    def _reset_configuration(self) -> None:
        self.prefs.reset_defaults()
        self._apply_theme("Dark")
        self._apply_language("English")
        self._sync_engine_from_prefs()
        self._reset_toolbars()
        self.lbl_status_info.setText("Configuration reset to factory defaults.")

    def _open_preferences(self) -> None:
        if PreferencesDialog(self.prefs, self._reset_configuration, self).exec() == QDialog.DialogCode.Accepted:
            self._sync_engine_from_prefs()
            self._apply_theme(str(self.prefs.get("theme", "Dark")))
            self._apply_language(str(self.prefs.get("language", "English")))
            self.canvas.mouse_wheel_zoom = bool(self.prefs.get("mouse_wheel_zoom", True))
            # Re-bind updated keyboard shortcuts live
            for aid, act in self.actions_by_id.items():
                sc = self.prefs.get("shortcuts", {}).get(aid, "")
                if sc:
                    act.setShortcut(QKeySequence(sc))

    def _check_updates(self) -> None:
        QMessageBox.information(self, "Check for Updates", f"KinoWave v{__version__} (KinoSuite Open-Source Audio Studio) is up to date.")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About KinoWave",
            f"<h3>KinoWave v{__version__}</h3>"
            "<p><b>KinoSuite Multitrack Audio Editing &amp; Mastering Platform</b></p>"
            "<p>32-bit float audio engine up to 384 kHz · Non-destructive Real-Time &amp; Destructive FX · "
            "Spectrogram &amp; Spectral Editing · MIDI, Labels, Time Tracks, Macros, Nyquist &amp; Scripting Pipe.</p>"
            "<p>Free &amp; Open Source · Cross-platform (Windows, macOS, Linux).</p>",
        )

    # -----------------------------------------------------------------------
    # UI Sync Helpers
    # -----------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        self.sel_bar.refresh_from_project()
        self._refresh_inspector()

    def _on_canvas_modified(self, desc: str) -> None:
        proj = self.current_project()
        if proj:
            proj.push_history(desc)
            self._refresh_views()

    def _on_project_sr_changed(self, sr: int) -> None:
        proj = self.current_project()
        if proj:
            proj.sample_rate = sr
            self.sel_bar.refresh_from_project()

    def _on_snap_changed(self, mode: str, unit: str) -> None:
        proj = self.current_project()
        if proj:
            proj.snap_mode = mode
            proj.snap_unit = unit

    def _on_sel_bar_edited(self, s0: float, s1: float) -> None:
        proj = self.current_project()
        if proj:
            proj.set_selection(s0, s1)
            self.canvas.update()
            self.sel_bar.refresh_from_project()

    def _on_vscroll(self, val: int) -> None:
        self.canvas.scroll_y = val
        self.canvas.update()

    def _on_hscroll(self, val: int) -> None:
        self.canvas.scroll_x_s = val / 100.0
        self.ruler.scroll_x_s = self.canvas.scroll_x_s
        self.canvas.update()
        self.ruler.update()

    def _sync_scrollbars(self) -> None:
        proj = self.current_project()
        max_y = max(0, self.canvas.total_content_height() - max(100, self.canvas.height()))
        self.vscroll.blockSignals(True)
        self.vscroll.setRange(0, max_y)
        self.vscroll.setValue(min(self.canvas.scroll_y, max_y))
        self.vscroll.blockSignals(False)

        dur = max(10.0, (proj.duration() if proj else 10.0) + 5.0)
        self.hscroll.blockSignals(True)
        self.hscroll.setRange(0, int(dur * 100))
        self.hscroll.setValue(int(self.canvas.scroll_x_s * 100))
        self.hscroll.blockSignals(False)

    def _update_tab_title(self) -> None:
        idx = self.proj_tabs.currentIndex()
        proj = self.current_project()
        if proj and idx >= 0:
            self.proj_tabs.setTabText(idx, ("* " if proj.dirty else "") + proj.name)

    def _refresh_inspector(self) -> None:
        proj = self.current_project()
        if not proj:
            return
        self.lst_insp_fx.clear()
        sel_a = proj.selected_audio_tracks()
        if sel_a:
            for sl in sel_a[0].realtime_effects:
                self.lst_insp_fx.addItem(f"[{'ON' if sl.enabled else 'OFF'}] {sel_a[0].name}: {sl.effect_name}")
        for sl in proj.master_effects:
            self.lst_insp_fx.addItem(f"[{'ON' if sl.enabled else 'OFF'}] Master: {sl.effect_name}")
        if self.lst_insp_fx.count() == 0:
            self.lst_insp_fx.addItem("(No active real-time FX)")

        self.lst_insp_hist.clear()
        for i, st in enumerate(proj.history):
            mark = "▶ " if i == proj.history_index else "  "
            self.lst_insp_hist.addItem(f"{mark}{st.description}")
        if 0 <= proj.history_index < self.lst_insp_hist.count():
            self.lst_insp_hist.setCurrentRow(proj.history_index)

    def _refresh_views(self) -> None:
        self._sync_scrollbars()
        self.sel_bar.refresh_from_project()
        self._refresh_inspector()
        self._update_tab_title()
        self.canvas.update()
        self.ruler.update()

    def closeEvent(self, event) -> None:
        self.engine.stop()
        self.pipe_server.stop()
        self.recovery.clear_all()
        super().closeEvent(event)
