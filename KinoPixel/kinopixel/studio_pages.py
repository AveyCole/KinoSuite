"""KinoPixel 5-Stage Start-to-Finish Studio Pages:
1. SpriteEditorPage   — Sprite creation, BGR555 palette editing & multi-frame animation studio
2. LevelEditorPage    — 8x8 Tile painter, collision tags & 64x32 scrolling level editor
3. ButtonWiringPage   — Visual GBA/GB handheld diagram + intuitive When/Trigger/Action rule wiring
4. SfxEditorPage      — Hardware PSG Chiptune SFX designer + live waveform preview
5. PlaytestBuildPage  — Live 60fps playable handheld + 1-click playable .gba / .gb / .gbc ROM builder
"""
from __future__ import annotations

import copy
import os
from typing import Dict, List, Optional, Set

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .audio_sfx import ChiptuneAudioPlayer, DIRECT_SOUND_PRESETS, synthesize_sfx_waveform
from .gba_compiler import BuildReport, compile_gb_rom, compile_gba_rom, export_c_source
from .genie_widget import SequenceGeniePanel
from .icons import make_icon
from .kinoscript import validate_kinoscript
from .models import (
    ABILITY_NAMES,
    ACTION_AIM_UP,
    ACTION_BOMB,
    ACTION_DASH,
    ACTION_HEAL,
    ACTION_JUMP,
    ACTION_MELEE,
    ACTION_MORPH_BALL,
    ACTION_MOVE_DOWN,
    ACTION_MOVE_LEFT,
    ACTION_MOVE_RIGHT,
    ACTION_MOVE_UP,
    ACTION_NAMES,
    ACTION_PALETTE_NEXT,
    ACTION_PAUSE,
    ACTION_RESET_LEVEL,
    ACTION_SHOOT,
    ACTION_SUPER_BURST,
    AI_BOSS,
    AI_TYPE_NAMES,
    AnimationClip,
    BUTTON_ORDER,
    ButtonRule,
    COND_NAMES,
    COND_VAR_POS,
    DoorLink,
    KinoPixelProject,
    LevelMap,
    PRESET_PALETTES,
    SPRITE_SIZES,
    SfxPatch,
    SpriteAsset,
    TILE_SOLID,
    TILE_TYPE_NAMES,
    TRIGGER_HELD,
    TRIGGER_NAMES,
    TRIGGER_PRESSED,
    TileAsset,
    empty_grid,
    hex_to_bgr555,
)
from .simulator import GamePlaytestEngine
from .widgets import (
    HandheldDiagramWidget,
    LevelMapCanvasWidget,
    PaletteStripWidget,
    PixelCanvasWidget,
    PlaytestScreenWidget,
    SfxWaveformWidget,
    render_grid_pixmap,
)


# ---------------------------------------------------------------------------
# Stage 1: Sprites & Animation Studio
# ---------------------------------------------------------------------------
class SpriteEditorPage(QWidget):
    projectModified = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[KinoPixelProject] = None
        self.sprite_idx: int = 0
        self.frame_idx: int = 0
        self.clip_idx: int = 0
        self._anim_playing: bool = True
        self._anim_tick: int = 0
        self._build_ui()

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(80)
        self._preview_timer.timeout.connect(self._tick_preview)
        self._preview_timer.start()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # --- Left Pane: Sprite List & Hardware Palette ---
        left = QWidget()
        left.setObjectName("SidePane")
        left.setFixedWidth(250)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)

        h1 = QLabel("METASPRITES (16×16 TO 64×64)")
        h1.setObjectName("SectionHeader")
        ll.addWidget(h1)

        self.lst_sprites = QListWidget()
        self.lst_sprites.setMaximumHeight(145)
        self.lst_sprites.currentRowChanged.connect(self._on_sprite_selected)
        ll.addWidget(self.lst_sprites)

        sp_btns = QHBoxLayout()
        b_add_sp = QPushButton("+ Sprite")
        b_add_sp.clicked.connect(self._add_sprite)
        b_dup_sp = QPushButton("Duplicate")
        b_dup_sp.clicked.connect(self._dup_sprite)
        sp_btns.addWidget(b_add_sp)
        sp_btns.addWidget(b_dup_sp)
        ll.addLayout(sp_btns)

        sz_row = QHBoxLayout()
        sz_row.addWidget(QLabel("Size:"))
        self.cmb_sp_size = QComboBox()
        size_tags = {
            (16, 16): "Standard",
            (16, 32): "Tall Character",
            (32, 16): "Wide Vehicle",
            (32, 32): "Large / Boss",
            (64, 64): "Giant Boss",
        }
        for sw, sh in SPRITE_SIZES:
            tag = size_tags.get((sw, sh), "Custom")
            self.cmb_sp_size.addItem(f"{sw}×{sh} ({tag})", (sw, sh))
        self.cmb_sp_size.currentIndexChanged.connect(self._on_sprite_size_changed)
        sz_row.addWidget(self.cmb_sp_size, 1)
        ll.addLayout(sz_row)

        h2 = QLabel("HARDWARE PALETTE (BGR555)")
        h2.setObjectName("SectionHeader")
        ll.addWidget(h2)

        pal_row = QHBoxLayout()
        self.cmb_pal_slot = QComboBox()
        self.cmb_pal_slot.currentIndexChanged.connect(self._on_pal_slot_changed)
        pal_row.addWidget(self.cmb_pal_slot, 1)
        b_preset = QPushButton("Preset...")
        b_preset.clicked.connect(self._apply_preset_palette)
        pal_row.addWidget(b_preset)
        ll.addLayout(pal_row)

        self.pal_strip = PaletteStripWidget(transparent_zero=True)
        self.pal_strip.colorSelected.connect(self._on_color_selected)
        self.pal_strip.paletteEdited.connect(self._on_palette_edited)
        ll.addWidget(self.pal_strip)

        self.lbl_color_info = QLabel("Color #1 · #FFFFFF · BGR555 0x7FFF")
        self.lbl_color_info.setStyleSheet("color:#94A3B8; font-size:8pt;")
        ll.addWidget(self.lbl_color_info)

        # Live Animated Preview Card
        h3 = QLabel("LIVE ANIMATION PREVIEW")
        h3.setObjectName("SectionHeader")
        ll.addWidget(h3)

        prev_card = QWidget()
        prev_card.setObjectName("CardFrame")
        pl = QVBoxLayout(prev_card)
        pl.setContentsMargins(8, 8, 8, 8)
        self.lbl_anim_preview = QLabel()
        self.lbl_anim_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_anim_preview.setMinimumHeight(96)
        self.lbl_anim_preview.setStyleSheet("background-color:#0E1118; border-radius:6px;")
        pl.addWidget(self.lbl_anim_preview)

        prow = QHBoxLayout()
        self.btn_anim_play = QPushButton("Pause")
        self.btn_anim_play.setCheckable(True)
        self.btn_anim_play.clicked.connect(self._toggle_anim_play)
        prow.addWidget(self.btn_anim_play)
        self.sp_fps = QSpinBox()
        self.sp_fps.setRange(1, 24)
        self.sp_fps.setValue(8)
        self.sp_fps.setSuffix(" FPS")
        self.sp_fps.valueChanged.connect(self._on_fps_changed)
        prow.addWidget(self.sp_fps)
        pl.addLayout(prow)
        ll.addWidget(prev_card)
        ll.addStretch(1)
        root.addWidget(left)

        # --- Center: Drawing Tools + Pixel Canvas + Filmstrip Timeline ---
        center = QVBoxLayout()
        center.setSpacing(6)

        tbar = QWidget()
        tbar.setObjectName("ControlBar")
        tl = QHBoxLayout(tbar)
        tl.setContentsMargins(6, 4, 6, 4)
        tl.setSpacing(4)

        self.tool_btns: Dict[str, QToolButton] = {}
        for tid, ic, tip in [
            ("pencil", "pencil", "Pencil (B)"),
            ("eraser", "eraser", "Eraser (E)"),
            ("fill", "fill", "Flood Fill (G)"),
            ("eyedropper", "eyedropper", "Color Picker (I)"),
            ("line", "line", "Line Tool (L)"),
            ("rect", "rect", "Rectangle Tool (R)"),
        ]:
            b = QToolButton()
            b.setIcon(make_icon(ic, 20))
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setFixedSize(30, 28)
            b.clicked.connect(lambda _=False, t=tid: self._set_tool(t))
            self.tool_btns[tid] = b
            tl.addWidget(b)
        self.tool_btns["pencil"].setChecked(True)

        tl.addSpacing(8)
        self.btn_mirror = QToolButton()
        self.btn_mirror.setIcon(make_icon("mirror", 20))
        self.btn_mirror.setToolTip("Horizontal Mirror Symmetry")
        self.btn_mirror.setCheckable(True)
        self.btn_mirror.setFixedSize(30, 28)
        self.btn_mirror.toggled.connect(self._toggle_mirror)
        tl.addWidget(self.btn_mirror)

        self.btn_onion = QToolButton()
        self.btn_onion.setIcon(make_icon("onion", 20))
        self.btn_onion.setToolTip("Onion Skin (Show Previous Frame)")
        self.btn_onion.setCheckable(True)
        self.btn_onion.setFixedSize(30, 28)
        self.btn_onion.toggled.connect(self._toggle_onion)
        tl.addWidget(self.btn_onion)

        self.btn_grid = QToolButton()
        self.btn_grid.setIcon(make_icon("grid", 20))
        self.btn_grid.setToolTip("Toggle Pixel Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setFixedSize(30, 28)
        self.btn_grid.toggled.connect(self._toggle_grid)
        tl.addWidget(self.btn_grid)

        tl.addSpacing(8)
        for ic, tip, fn in [
            ("flip_h", "Flip Frame Horizontal", self._flip_h),
            ("flip_v", "Flip Frame Vertical", self._flip_v),
            ("rotate", "Rotate 90° Clockwise", self._rotate_cw),
        ]:
            b = QToolButton()
            b.setIcon(make_icon(ic, 20))
            b.setToolTip(tip)
            b.setFixedSize(30, 28)
            b.clicked.connect(fn)
            tl.addWidget(b)

        b_clear = QPushButton("Clear")
        b_clear.setFixedHeight(26)
        b_clear.clicked.connect(self._clear_frame)
        tl.addWidget(b_clear)

        tl.addStretch(1)
        self.lbl_coords = QLabel("Pixel: --, --")
        self.lbl_coords.setStyleSheet("color:#94A3B8;")
        tl.addWidget(self.lbl_coords)
        center.addWidget(tbar)

        self.canvas = PixelCanvasWidget(transparent_zero=True)
        self.canvas.pixelsChanged.connect(self._refresh_thumbnails)
        self.canvas.strokeFinished.connect(lambda lbl: self.projectModified.emit(lbl))
        self.canvas.colorPicked.connect(self._on_color_picked)
        self.canvas.hoverChanged.connect(lambda x, y: self.lbl_coords.setText(f"Pixel: {x:02d}, {y:02d}"))
        center.addWidget(self.canvas, 1)

        # Bottom Animation Clip & Frame Filmstrip Bar
        anim_box = QGroupBox("Animation Clips & Frame Timeline")
        al = QVBoxLayout(anim_box)
        al.setContentsMargins(8, 6, 8, 6)
        al.setSpacing(6)

        crow = QHBoxLayout()
        crow.addWidget(QLabel("Clip:"))
        self.cmb_clip = QComboBox()
        self.cmb_clip.setMinimumWidth(120)
        self.cmb_clip.currentIndexChanged.connect(self._on_clip_selected)
        crow.addWidget(self.cmb_clip)
        b_add_clip = QPushButton("+ Clip")
        b_add_clip.clicked.connect(self._add_clip)
        crow.addWidget(b_add_clip)

        crow.addSpacing(12)
        b_add_fr = QPushButton("+ Blank Frame")
        b_add_fr.clicked.connect(self._add_frame)
        b_dup_fr = QPushButton("Duplicate Frame")
        b_dup_fr.clicked.connect(self._dup_frame)
        b_del_fr = QPushButton("Delete Frame")
        b_del_fr.setObjectName("DangerButton")
        b_del_fr.clicked.connect(self._del_frame)
        crow.addWidget(b_add_fr)
        crow.addWidget(b_dup_fr)
        crow.addWidget(b_del_fr)
        crow.addStretch(1)
        self.cb_in_clip = QCheckBox("Include Current Frame in Active Clip")
        self.cb_in_clip.toggled.connect(self._on_toggle_frame_in_clip)
        crow.addWidget(self.cb_in_clip)
        al.addLayout(crow)

        self.lst_frames = QListWidget()
        self.lst_frames.setFlow(QListWidget.Flow.LeftToRight)
        self.lst_frames.setWrapping(False)
        self.lst_frames.setFixedHeight(78)
        self.lst_frames.setIconSize(self.lst_frames.iconSize() * 2)
        self.lst_frames.currentRowChanged.connect(self._on_frame_selected)
        al.addWidget(self.lst_frames)
        center.addWidget(anim_box)
        root.addLayout(center, 1)

    def set_project(self, proj: KinoPixelProject) -> None:
        self.project = proj
        self.sprite_idx = min(self.sprite_idx, max(0, len(proj.sprites) - 1))
        self.refresh_all()

    def _cur_sprite(self) -> Optional[SpriteAsset]:
        if self.project and 0 <= self.sprite_idx < len(self.project.sprites):
            return self.project.sprites[self.sprite_idx]
        return None

    def _cur_clip(self) -> Optional[AnimationClip]:
        sp = self._cur_sprite()
        if sp and 0 <= self.clip_idx < len(sp.animations):
            return sp.animations[self.clip_idx]
        return None

    def refresh_all(self) -> None:
        if not self.project:
            return
        self.lst_sprites.blockSignals(True)
        self.lst_sprites.clear()
        for idx, sp in enumerate(self.project.sprites):
            pm = render_grid_pixmap(sp.frames[0], self.project.get_palette_colors(sp.palette_index), scale=2)
            it = QListWidgetItem(QIcon(pm), f"{sp.name} ({len(sp.frames)}f · {sp.role})")
            self.lst_sprites.addItem(it)
        self.lst_sprites.setCurrentRow(self.sprite_idx)
        self.lst_sprites.blockSignals(False)

        self.cmb_pal_slot.blockSignals(True)
        self.cmb_pal_slot.clear()
        for pi in range(len(self.project.palettes)):
            self.cmb_pal_slot.addItem(f"Palette Slot {pi}")
        sp = self._cur_sprite()
        if sp:
            self.cmb_pal_slot.setCurrentIndex(sp.palette_index % max(1, len(self.project.palettes)))
            self.cmb_sp_size.blockSignals(True)
            si = self.cmb_sp_size.findData((sp.width, sp.height))
            if si >= 0:
                self.cmb_sp_size.setCurrentIndex(si)
            self.cmb_sp_size.blockSignals(False)
        self.cmb_pal_slot.blockSignals(False)

        self._refresh_clips_and_frames()
        self._sync_canvas()

    def _refresh_clips_and_frames(self) -> None:
        sp = self._cur_sprite()
        if not sp or not self.project:
            return
        self.frame_idx = min(self.frame_idx, max(0, len(sp.frames) - 1))
        self.clip_idx = min(self.clip_idx, max(0, len(sp.animations) - 1))

        self.cmb_clip.blockSignals(True)
        self.cmb_clip.clear()
        for cl in sp.animations:
            self.cmb_clip.addItem(f"{cl.name} ({len(cl.frame_indices)}f)")
        self.cmb_clip.setCurrentIndex(self.clip_idx)
        self.cmb_clip.blockSignals(False)

        cl = self._cur_clip()
        if cl:
            self.sp_fps.blockSignals(True)
            self.sp_fps.setValue(cl.fps)
            self.sp_fps.blockSignals(False)
            self.cb_in_clip.blockSignals(True)
            self.cb_in_clip.setChecked(self.frame_idx in cl.frame_indices)
            self.cb_in_clip.blockSignals(False)

        self._refresh_thumbnails()

    def _refresh_thumbnails(self) -> None:
        sp = self._cur_sprite()
        if not sp or not self.project:
            return
        cols = self.project.get_palette_colors(sp.palette_index)
        cl = self._cur_clip()
        in_set = set(cl.frame_indices) if cl else set()
        self.lst_frames.blockSignals(True)
        self.lst_frames.clear()
        for i, fr in enumerate(sp.frames):
            pm = render_grid_pixmap(fr, cols, scale=3)
            mark = "★" if i in in_set else ""
            self.lst_frames.addItem(QListWidgetItem(QIcon(pm), f"F{i}{mark}"))
        self.lst_frames.setCurrentRow(self.frame_idx)
        self.lst_frames.blockSignals(False)
        # Update sprite icon too
        if 0 <= self.sprite_idx < self.lst_sprites.count():
            pm0 = render_grid_pixmap(sp.frames[0], cols, scale=2)
            self.lst_sprites.item(self.sprite_idx).setIcon(QIcon(pm0))

    def _sync_canvas(self) -> None:
        sp = self._cur_sprite()
        if not sp or not self.project:
            return
        cols = self.project.get_palette_colors(sp.palette_index)
        self.pal_strip.set_palette(cols, self.project.active_palette_size())
        onion = sp.frames[self.frame_idx - 1] if self.frame_idx > 0 else None
        self.canvas.set_data(sp.frames[self.frame_idx], cols, onion_grid=onion)
        self._update_color_info(self.pal_strip.selected_idx)

    def _update_color_info(self, idx: int) -> None:
        sp = self._cur_sprite()
        if not sp or not self.project:
            return
        cols = self.project.get_palette_colors(sp.palette_index)
        hx = cols[idx % len(cols)]
        b555 = hex_to_bgr555(hx)
        t_lbl = " (Transparent)" if idx == 0 else ""
        self.lbl_color_info.setText(f"Color #{idx}{t_lbl} · {hx} · BGR555 0x{b555:04X}")

    def _set_tool(self, t: str) -> None:
        self.canvas.tool = t
        for k, b in self.tool_btns.items():
            b.setChecked(k == t)

    def _toggle_mirror(self, on: bool) -> None:
        self.canvas.mirror_x = on
        self.canvas.update()

    def _toggle_onion(self, on: bool) -> None:
        self.canvas.show_onion = on
        self.canvas.update()

    def _toggle_grid(self, on: bool) -> None:
        self.canvas.show_grid = on
        self.canvas.update()

    def _on_sprite_selected(self, row: int) -> None:
        if row >= 0:
            self.sprite_idx = row
            self.frame_idx = 0
            self.clip_idx = 0
            self.refresh_all()

    def _on_frame_selected(self, row: int) -> None:
        if row >= 0:
            self.frame_idx = row
            cl = self._cur_clip()
            if cl:
                self.cb_in_clip.blockSignals(True)
                self.cb_in_clip.setChecked(row in cl.frame_indices)
                self.cb_in_clip.blockSignals(False)
            self._sync_canvas()

    def _on_clip_selected(self, row: int) -> None:
        if row >= 0:
            self.clip_idx = row
            cl = self._cur_clip()
            if cl:
                self.sp_fps.blockSignals(True)
                self.sp_fps.setValue(cl.fps)
                self.sp_fps.blockSignals(False)
                self.cb_in_clip.blockSignals(True)
                self.cb_in_clip.setChecked(self.frame_idx in cl.frame_indices)
                self.cb_in_clip.blockSignals(False)
            self._refresh_thumbnails()

    def _on_color_selected(self, idx: int) -> None:
        self.canvas.active_color = idx
        self._update_color_info(idx)

    def _on_color_picked(self, idx: int) -> None:
        self.pal_strip.selected_idx = idx
        self.pal_strip.update()
        self.canvas.active_color = idx
        self._set_tool("pencil")
        self._update_color_info(idx)

    def _on_palette_edited(self) -> None:
        self._sync_canvas()
        self._refresh_thumbnails()
        self.projectModified.emit("Edit Palette Color")

    def _on_pal_slot_changed(self, idx: int) -> None:
        sp = self._cur_sprite()
        if sp and idx >= 0:
            sp.palette_index = idx
            self._sync_canvas()
            self._refresh_thumbnails()
            self.projectModified.emit("Change Sprite Palette")

    def _on_sprite_size_changed(self) -> None:
        sp = self._cur_sprite()
        data = self.cmb_sp_size.currentData()
        if sp and data and (sp.width, sp.height) != tuple(data):
            sp.resize_frames(data[0], data[1])
            self._sync_canvas()
            self._refresh_thumbnails()
            self.projectModified.emit(f"Resize Metasprite ({data[0]}×{data[1]})")

    def _apply_preset_palette(self) -> None:
        if not self.project:
            return
        names = list(PRESET_PALETTES.keys())
        choice, ok = QInputDialog.getItem(self, "Load Retro Palette Preset", "Select Palette:", names, 0, False)
        if ok and choice in PRESET_PALETTES:
            slot = max(0, self.cmb_pal_slot.currentIndex())
            self.project.palettes[slot] = list(PRESET_PALETTES[choice])
            self._sync_canvas()
            self._refresh_thumbnails()
            self.projectModified.emit(f"Load Palette ({choice})")

    def _add_sprite(self) -> None:
        if not self.project:
            return
        name, ok = QInputDialog.getText(self, "New Sprite", "Sprite Name:", text=f"Sprite {len(self.project.sprites) + 1}")
        if ok and name.strip():
            self.project.sprites.append(SpriteAsset(name=name.strip(), role="enemy"))
            self.sprite_idx = len(self.project.sprites) - 1
            self.frame_idx = 0
            self.refresh_all()
            self.projectModified.emit("Add Sprite")

    def _dup_sprite(self) -> None:
        sp = self._cur_sprite()
        if not sp or not self.project:
            return
        clone = copy.deepcopy(sp)
        clone.name = f"{sp.name} Copy"
        self.project.sprites.append(clone)
        self.sprite_idx = len(self.project.sprites) - 1
        self.refresh_all()
        self.projectModified.emit("Duplicate Sprite")

    def _add_frame(self) -> None:
        sp = self._cur_sprite()
        if not sp:
            return
        sp.frames.append(empty_grid(sp.width, sp.height, 0))
        self.frame_idx = len(sp.frames) - 1
        self._refresh_clips_and_frames()
        self._sync_canvas()
        self.projectModified.emit("Add Sprite Frame")

    def _dup_frame(self) -> None:
        sp = self._cur_sprite()
        if not sp:
            return
        sp.frames.insert(self.frame_idx + 1, copy.deepcopy(sp.frames[self.frame_idx]))
        self.frame_idx += 1
        self._refresh_clips_and_frames()
        self._sync_canvas()
        self.projectModified.emit("Duplicate Sprite Frame")

    def _del_frame(self) -> None:
        sp = self._cur_sprite()
        if not sp or len(sp.frames) <= 1:
            return
        sp.frames.pop(self.frame_idx)
        for cl in sp.animations:
            cl.frame_indices = [min(i, len(sp.frames) - 1) for i in cl.frame_indices if i != self.frame_idx] or [0]
        self.frame_idx = max(0, self.frame_idx - 1)
        self._refresh_clips_and_frames()
        self._sync_canvas()
        self.projectModified.emit("Delete Sprite Frame")

    def _add_clip(self) -> None:
        sp = self._cur_sprite()
        if not sp:
            return
        name, ok = QInputDialog.getText(self, "New Animation Clip", "Clip Name:", text="custom")
        if ok and name.strip():
            sp.animations.append(AnimationClip(name.strip(), [self.frame_idx], fps=8, loop=True))
            self.clip_idx = len(sp.animations) - 1
            self._refresh_clips_and_frames()
            self.projectModified.emit("Add Animation Clip")

    def _on_fps_changed(self, v: int) -> None:
        cl = self._cur_clip()
        if cl:
            cl.fps = v
            self.projectModified.emit("Change Animation FPS")

    def _on_toggle_frame_in_clip(self, checked: bool) -> None:
        cl = self._cur_clip()
        if not cl:
            return
        if checked and self.frame_idx not in cl.frame_indices:
            cl.frame_indices.append(self.frame_idx)
            cl.frame_indices.sort()
        elif not checked and self.frame_idx in cl.frame_indices and len(cl.frame_indices) > 1:
            cl.frame_indices.remove(self.frame_idx)
        self._refresh_thumbnails()
        self.projectModified.emit("Edit Clip Frames")

    def _flip_h(self) -> None:
        sp = self._cur_sprite()
        if not sp:
            return
        fr = sp.frames[self.frame_idx]
        for y in range(len(fr)):
            fr[y].reverse()
        self._sync_canvas()
        self._refresh_thumbnails()
        self.projectModified.emit("Flip Frame Horizontal")

    def _flip_v(self) -> None:
        sp = self._cur_sprite()
        if not sp:
            return
        sp.frames[self.frame_idx].reverse()
        self._sync_canvas()
        self._refresh_thumbnails()
        self.projectModified.emit("Flip Frame Vertical")

    def _rotate_cw(self) -> None:
        sp = self._cur_sprite()
        if not sp:
            return
        fr = sp.frames[self.frame_idx]
        h, w = len(fr), len(fr[0])
        sp.frames[self.frame_idx] = [[fr[h - 1 - x][y] for x in range(h)] for y in range(w)]
        self._sync_canvas()
        self._refresh_thumbnails()
        self.projectModified.emit("Rotate Frame 90°")

    def _clear_frame(self) -> None:
        sp = self._cur_sprite()
        if not sp:
            return
        sp.frames[self.frame_idx] = empty_grid(sp.width, sp.height, 0)
        self._sync_canvas()
        self._refresh_thumbnails()
        self.projectModified.emit("Clear Frame")

    def _toggle_anim_play(self, checked: bool) -> None:
        self._anim_playing = not checked
        self.btn_anim_play.setText("Play" if checked else "Pause")

    def _tick_preview(self) -> None:
        sp = self._cur_sprite()
        cl = self._cur_clip()
        if not sp or not cl or not self.project or not self._anim_playing:
            return
        self._anim_tick += 1
        step = max(1, int(round(12.5 / max(1, cl.fps))))
        fids = cl.frame_indices or [0]
        fi = fids[(self._anim_tick // step) % len(fids)]
        fi = max(0, min(len(sp.frames) - 1, fi))
        pm = render_grid_pixmap(sp.frames[fi], self.project.get_palette_colors(sp.palette_index), scale=5)
        self.lbl_anim_preview.setPixmap(pm)


# ---------------------------------------------------------------------------
# Stage 2: Tiles & Level Map Studio
# ---------------------------------------------------------------------------
class LevelEditorPage(QWidget):
    projectModified = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[KinoPixelProject] = None
        self.tile_idx: int = 1
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # Left Pane: Tileset List + Inline 8x8 Tile Painter
        left = QWidget()
        left.setObjectName("SidePane")
        left.setFixedWidth(272)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)

        h1 = QLabel("TILESET (8×8 HARDWARE TILES)")
        h1.setObjectName("SectionHeader")
        ll.addWidget(h1)

        self.lst_tiles = QListWidget()
        self.lst_tiles.setMaximumHeight(175)
        self.lst_tiles.currentRowChanged.connect(self._on_tile_selected)
        ll.addWidget(self.lst_tiles)

        tbtn_row = QHBoxLayout()
        b_new_t = QPushButton("+ Tile")
        b_new_t.clicked.connect(self._add_tile)
        self.cmb_tile_type = QComboBox()
        for k, v in TILE_TYPE_NAMES.items():
            self.cmb_tile_type.addItem(v, k)
        self.cmb_tile_type.currentIndexChanged.connect(self._on_tile_type_changed)
        tbtn_row.addWidget(b_new_t)
        tbtn_row.addWidget(self.cmb_tile_type, 1)
        ll.addLayout(tbtn_row)

        h2 = QLabel("INLINE 8×8 TILE PAINTER")
        h2.setObjectName("SectionHeader")
        ll.addWidget(h2)

        self.tile_canvas = PixelCanvasWidget(transparent_zero=True)
        self.tile_canvas.setFixedHeight(190)
        self.tile_canvas.pixelsChanged.connect(self._on_tile_pixels_live)
        self.tile_canvas.strokeFinished.connect(lambda _: self.projectModified.emit("Paint 8x8 Tile"))
        ll.addWidget(self.tile_canvas)

        self.tile_pal = PaletteStripWidget(transparent_zero=True)
        self.tile_pal.colorSelected.connect(lambda ci: setattr(self.tile_canvas, "active_color", ci))
        self.tile_pal.paletteEdited.connect(self._on_tile_pixels_live)
        ll.addWidget(self.tile_pal)
        ll.addStretch(1)
        root.addWidget(left)

        # Right / Center: Multi-Room World Bar + Level Toolbar + Scrollable Map Canvas
        right = QVBoxLayout()
        right.setSpacing(6)

        # Multi-Room World & Map Metadata Bar (up to 128 rooms!)
        wbar = QWidget()
        wbar.setObjectName("CardFrame")
        wl = QGridLayout(wbar)
        wl.setContentsMargins(8, 5, 8, 5)
        wl.setHorizontalSpacing(6)
        wl.setVerticalSpacing(4)
        wl.addWidget(QLabel("Room:"), 0, 0)
        self.cmb_room = QComboBox()
        self.cmb_room.setMinimumWidth(155)
        self.cmb_room.currentIndexChanged.connect(self._on_room_selected)
        wl.addWidget(self.cmb_room, 0, 1)
        b_add_rm = QPushButton("+ Room")
        b_add_rm.clicked.connect(self._add_room)
        wl.addWidget(b_add_rm, 0, 2)
        b_door = QPushButton("+ Link Warp")
        b_door.clicked.connect(self._link_door_dialog)
        wl.addWidget(b_door, 0, 3)

        wl.addWidget(QLabel("Map X/Y:"), 0, 4)
        xy_row = QHBoxLayout()
        xy_row.setSpacing(3)
        self.sp_wx = QSpinBox()
        self.sp_wx.setRange(0, 15)
        self.sp_wx.setFixedWidth(48)
        self.sp_wx.valueChanged.connect(self._on_room_meta_changed)
        self.sp_wy = QSpinBox()
        self.sp_wy.setRange(0, 7)
        self.sp_wy.setFixedWidth(48)
        self.sp_wy.valueChanged.connect(self._on_room_meta_changed)
        xy_row.addWidget(self.sp_wx)
        xy_row.addWidget(self.sp_wy)
        wl.addLayout(xy_row, 0, 5)

        wl.addWidget(QLabel("Unlock:"), 0, 6)
        self.cmb_upg = QComboBox()
        for k, v in ABILITY_NAMES.items():
            self.cmb_upg.addItem(v, k)
        self.cmb_upg.currentIndexChanged.connect(self._on_room_meta_changed)
        wl.addWidget(self.cmb_upg, 0, 7)

        self.cb_par = QCheckBox("BG2 Parallax")
        self.cb_par.setChecked(True)
        self.cb_par.toggled.connect(self._on_room_meta_changed)
        wl.addWidget(self.cb_par, 0, 8)

        wl.addWidget(QLabel("Dialogue P1:"), 1, 0)
        self.ed_dlg = QLineEdit()
        self.ed_dlg.setMaxLength(48)
        self.ed_dlg.setPlaceholderText("Dialogue / Signpost Page 1 (48 chars)...")
        self.ed_dlg.editingFinished.connect(self._on_room_meta_changed)
        wl.addWidget(self.ed_dlg, 1, 1, 1, 3)

        wl.addWidget(QLabel("Page 2:"), 1, 4)
        self.ed_dlg2 = QLineEdit()
        self.ed_dlg2.setMaxLength(48)
        self.ed_dlg2.setPlaceholderText("Optional Page 2 (press A to advance)...")
        self.ed_dlg2.editingFinished.connect(self._on_room_meta_changed)
        wl.addWidget(self.ed_dlg2, 1, 5, 1, 4)
        right.addWidget(wbar)

        bar = QWidget()
        bar.setObjectName("ControlBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(6, 4, 6, 4)
        bl.setSpacing(6)

        self.map_tool_btns: Dict[str, QPushButton] = {}
        for tid, lbl in [
            ("brush", "Paint Tile"),
            ("rect", "Rect Fill"),
            ("eraser", "Erase"),
            ("eyedropper", "Pick"),
            ("spawn", "Set Spawn"),
            ("enemy", "Place Entity"),
        ]:
            b = QPushButton(lbl)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, t=tid: self._set_map_tool(t))
            self.map_tool_btns[tid] = b
            bl.addWidget(b)
        self.map_tool_btns["brush"].setChecked(True)

        self.cmb_ai = QComboBox()
        for k, v in AI_TYPE_NAMES.items():
            self.cmb_ai.addItem(v.split(" (")[0], k)
        self.cmb_ai.currentIndexChanged.connect(lambda: setattr(self.map_canvas, "selected_ai", int(self.cmb_ai.currentData())))
        bl.addWidget(self.cmb_ai)

        bl.addSpacing(6)
        bl.addWidget(QLabel("Physics:"))
        self.cmb_phys = QComboBox()
        self.cmb_phys.addItem("Platformer (Slopes/Water)", "platformer")
        self.cmb_phys.addItem("Top-Down RPG (4-Way)", "topdown")
        self.cmb_phys.addItem("Space Action (8-Way)", "shmup")
        self.cmb_phys.addItem("Tactical Grid (16px Step)", "tactical")
        self.cmb_phys.currentIndexChanged.connect(self._on_physics_changed)
        bl.addWidget(self.cmb_phys)

        self.cb_col = QCheckBox("Collisions")
        self.cb_col.setChecked(True)
        self.cb_col.toggled.connect(self._toggle_collision)
        bl.addWidget(self.cb_col)

        self.cb_vp = QCheckBox("Screen Guide")
        self.cb_vp.setChecked(True)
        self.cb_vp.toggled.connect(self._toggle_viewport)
        bl.addWidget(self.cb_vp)

        bl.addStretch(1)
        self.lbl_tile_pos = QLabel("Tile: --, --")
        self.lbl_tile_pos.setStyleSheet("color:#94A3B8;")
        bl.addWidget(self.lbl_tile_pos)
        right.addWidget(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        self.map_canvas = LevelMapCanvasWidget()
        self.map_canvas.mapStrokeFinished.connect(lambda lbl: self.projectModified.emit(lbl))
        self.map_canvas.tilePicked.connect(self._on_tile_picked)
        self.map_canvas.hoverTileChanged.connect(lambda x, y: self.lbl_tile_pos.setText(f"Tile: {x:02d}, {y:02d}"))
        scroll.setWidget(self.map_canvas)
        right.addWidget(scroll, 1)
        root.addLayout(right, 1)

    def set_project(self, proj: KinoPixelProject) -> None:
        self.project = proj
        self.tile_idx = min(self.tile_idx, max(0, len(proj.tiles) - 1))
        self.refresh_all()

    def refresh_all(self) -> None:
        if not self.project:
            return
        self.cmb_room.blockSignals(True)
        self.cmb_room.clear()
        for i, rm in enumerate(self.project.rooms):
            self.cmb_room.addItem(f"R{i + 1}: {rm.name}", i)
        self.cmb_room.setCurrentIndex(self.project.active_room_idx)
        self.cmb_room.blockSignals(False)

        cur_rm = self.project.level
        self.sp_wx.blockSignals(True)
        self.sp_wx.setValue(cur_rm.world_x)
        self.sp_wx.blockSignals(False)
        self.sp_wy.blockSignals(True)
        self.sp_wy.setValue(cur_rm.world_y)
        self.sp_wy.blockSignals(False)
        self.cmb_upg.blockSignals(True)
        ui = self.cmb_upg.findData(cur_rm.upgrade_ability)
        if ui >= 0:
            self.cmb_upg.setCurrentIndex(ui)
        self.cmb_upg.blockSignals(False)
        self.cb_par.blockSignals(True)
        self.cb_par.setChecked(cur_rm.parallax_enabled)
        self.cb_par.blockSignals(False)
        self.ed_dlg.blockSignals(True)
        self.ed_dlg.setText(cur_rm.dialogue_text)
        self.ed_dlg.blockSignals(False)
        self.ed_dlg2.blockSignals(True)
        self.ed_dlg2.setText(cur_rm.dialogue_page2)
        self.ed_dlg2.blockSignals(False)

        self.cmb_phys.blockSignals(True)
        pi = self.cmb_phys.findData(self.project.physics_mode)
        self.cmb_phys.setCurrentIndex(max(0, pi))
        self.cmb_phys.blockSignals(False)

        self.lst_tiles.blockSignals(True)
        self.lst_tiles.clear()
        for i, t in enumerate(self.project.tiles):
            pm = render_grid_pixmap(t.pixels, self.project.get_palette_colors(t.palette_index), scale=3)
            tag = TILE_TYPE_NAMES.get(t.tile_type, "").split(" /")[0]
            self.lst_tiles.addItem(QListWidgetItem(QIcon(pm), f"#{i} {t.name} [{tag}]"))
        self.lst_tiles.setCurrentRow(self.tile_idx)
        self.lst_tiles.blockSignals(False)

        self.map_canvas.selected_tile = self.tile_idx
        self.map_canvas.set_project(self.project)
        self._sync_tile_painter()

    def _sync_tile_painter(self) -> None:
        if not self.project or not (0 <= self.tile_idx < len(self.project.tiles)):
            return
        t = self.project.tiles[self.tile_idx]
        cols = self.project.get_palette_colors(t.palette_index)
        self.tile_canvas.set_data(t.pixels, cols)
        self.tile_pal.set_palette(cols, self.project.active_palette_size())
        self.cmb_tile_type.blockSignals(True)
        idx = self.cmb_tile_type.findData(t.tile_type)
        if idx >= 0:
            self.cmb_tile_type.setCurrentIndex(idx)
        self.cmb_tile_type.blockSignals(False)

    def _on_tile_selected(self, row: int) -> None:
        if row >= 0:
            self.tile_idx = row
            self.map_canvas.selected_tile = row
            self._sync_tile_painter()

    def _on_tile_picked(self, ti: int) -> None:
        self.tile_idx = ti
        self.lst_tiles.setCurrentRow(ti)
        self._set_map_tool("brush")

    def _on_tile_pixels_live(self) -> None:
        if not self.project:
            return
        t = self.project.tiles[self.tile_idx]
        pm = render_grid_pixmap(t.pixels, self.project.get_palette_colors(t.palette_index), scale=3)
        if 0 <= self.tile_idx < self.lst_tiles.count():
            self.lst_tiles.item(self.tile_idx).setIcon(QIcon(pm))
        self.map_canvas.update()

    def _on_tile_type_changed(self) -> None:
        if not self.project:
            return
        t = self.project.tiles[self.tile_idx]
        t.tile_type = int(self.cmb_tile_type.currentData())
        self.refresh_all()
        self.projectModified.emit("Change Tile Collision Type")

    def _add_tile(self) -> None:
        if not self.project:
            return
        name, ok = QInputDialog.getText(self, "New 8×8 Tile", "Tile Name:", text=f"Tile {len(self.project.tiles)}")
        if ok and name.strip():
            self.project.tiles.append(TileAsset(name=name.strip(), tile_type=TILE_SOLID, pixels=empty_grid(8, 8, 1)))
            self.tile_idx = len(self.project.tiles) - 1
            self.refresh_all()
            self.projectModified.emit("Add Tile")

    def _set_map_tool(self, t: str) -> None:
        self.map_canvas.tool = t
        for k, b in self.map_tool_btns.items():
            b.setChecked(k == t)

    def _on_physics_changed(self) -> None:
        if not self.project:
            return
        self.project.physics_mode = str(self.cmb_phys.currentData())
        self.projectModified.emit("Change Physics Mode")

    def _toggle_collision(self, on: bool) -> None:
        self.map_canvas.show_collision = on
        self.map_canvas.update()

    def _toggle_viewport(self, on: bool) -> None:
        self.map_canvas.show_viewport = on
        self.map_canvas.update()

    def _on_room_selected(self, idx: int) -> None:
        if self.project and 0 <= idx < len(self.project.rooms):
            self.project.active_room_idx = idx
            self.refresh_all()

    def _add_room(self) -> None:
        if not self.project or len(self.project.rooms) >= 128:
            return
        n = len(self.project.rooms) + 1
        w, h = 40, 20
        cells = empty_grid(w, h, 0)
        for x in range(w):
            cells[0][x] = 9; cells[h - 2][x] = 2; cells[h - 1][x] = 9
        for y in range(h):
            cells[y][0] = 9; cells[y][w - 1] = 9
        self.project.rooms.append(LevelMap(name=f"Area {n}", width=w, height=h, world_x=(n - 1) % 16, world_y=((n - 1) // 16) % 8, spawn_x=3, spawn_y=h - 5, cells=cells))
        self.project.active_room_idx = len(self.project.rooms) - 1
        self.refresh_all()
        self.projectModified.emit(f"Add Room (Area {n})")

    def _link_door_dialog(self) -> None:
        if not self.project:
            return
        rm_names = [f"R{i + 1}: {r.name}" for i, r in enumerate(self.project.rooms)]
        choice, ok = QInputDialog.getItem(self, "Link Map Warp", "Target Destination Room:", rm_names, 0, False)
        if not ok:
            return
        target_idx = rm_names.index(choice)
        lvl = self.project.level
        tx = max(1, lvl.width - 2)
        ty = max(2, lvl.height - 3)
        lvl.set_tile(tx, ty, 11 if len(self.project.tiles) > 11 else 7)
        lvl.doors.append(DoorLink(tile_x=tx, tile_y=ty, target_room=target_idx, target_x=3, target_y=max(2, self.project.rooms[target_idx].height - 6)))
        self.map_canvas.update()
        self.projectModified.emit(f"Link Warp to R{target_idx + 1}")

    def _on_room_meta_changed(self) -> None:
        if not self.project:
            return
        rm = self.project.level
        rm.world_x = self.sp_wx.value()
        rm.world_y = self.sp_wy.value()
        rm.upgrade_ability = int(self.cmb_upg.currentData())
        rm.parallax_enabled = self.cb_par.isChecked()
        rm.dialogue_text = self.ed_dlg.text().strip().upper()[:48]
        rm.dialogue_page2 = self.ed_dlg2.text().strip().upper()[:48]
        self.projectModified.emit("Update Room Settings")


# ---------------------------------------------------------------------------
# Stage 3: Simple & Intuitive Visual Button Wiring Studio
# ---------------------------------------------------------------------------
class ButtonWiringPage(QWidget):
    projectModified = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[KinoPixelProject] = None
        self.filter_btn: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self.logic_tabs = QTabWidget()
        self.logic_tabs.setDocumentMode(True)

        # Sub-Tab 1: Visual Button & Event Wiring
        vis_tab = QWidget()
        root = QHBoxLayout(vis_tab)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(10)

        # Left: Interactive Handheld Diagram + Quick Presets
        left = QVBoxLayout()
        h1 = QLabel("INTERACTIVE CONTROLLER WIRING")
        h1.setObjectName("SectionHeader")
        left.addWidget(h1)

        self.diagram = HandheldDiagramWidget()
        self.diagram.buttonClicked.connect(self._on_diagram_clicked)
        left.addWidget(self.diagram, 1)

        preset_box = QGroupBox("One-Click Control Schemes")
        pl = QGridLayout(preset_box)
        for idx, (lbl, key) in enumerate([
            ("Platformer", "platformer"),
            ("Action-RPG", "topdown"),
            ("Space Action", "shmup"),
            ("Tactical Grid", "tactical"),
            ("Exploration Action", "exploration"),
        ]):
            b = QPushButton(lbl)
            b.clicked.connect(lambda _=False, k=key: self._apply_scheme(k))
            pl.addWidget(b, idx // 3, idx % 3)
        left.addWidget(preset_box)
        root.addLayout(left, 2)

        # Right: Visual Rule Cards + Conditional Variable Controls
        right = QVBoxLayout()
        hdr = QHBoxLayout()
        self.lbl_rules_hdr = QLabel("BUTTON & EVENT WIRING RULES — ALL BUTTONS")
        self.lbl_rules_hdr.setObjectName("SectionHeader")
        hdr.addWidget(self.lbl_rules_hdr, 1)
        hdr.addWidget(QLabel("Start Var[0]:"))
        self.sp_start_v0 = QSpinBox()
        self.sp_start_v0.setRange(0, 99)
        self.sp_start_v0.setToolTip("Starting value for Game Variable #0 (Ammo / Ki / MP / Funds)")
        self.sp_start_v0.valueChanged.connect(self._on_start_var0_changed)
        hdr.addWidget(self.sp_start_v0)
        b_add = QPushButton("+ Add Button Wire")
        b_add.setObjectName("PrimaryButton")
        b_add.clicked.connect(self._add_rule)
        hdr.addWidget(b_add)
        right.addLayout(hdr)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_host = QWidget()
        self.cards_host.setObjectName("ScrollContent")
        self.cards_lay = QVBoxLayout(self.cards_host)
        self.cards_lay.setContentsMargins(4, 4, 4, 4)
        self.cards_lay.setSpacing(6)
        self.scroll.setWidget(self.cards_host)
        right.addWidget(self.scroll, 1)
        root.addLayout(right, 3)

        self.logic_tabs.addTab(vis_tab, "Visual Button & Variable Wiring (Zero-Code)")

        # Sub-Tab 2: KinoScript Native ARM7TDMI Studio (Unrestricted Custom Game Logic!)
        ks_tab = QWidget()
        kroot = QHBoxLayout(ks_tab)
        kroot.setContentsMargins(6, 6, 6, 6)
        kroot.setSpacing(10)

        kleft = QVBoxLayout()
        kbar = QWidget()
        kbar.setObjectName("CardFrame")
        kbl = QHBoxLayout(kbar)
        kbl.setContentsMargins(8, 5, 8, 5)
        self.cb_ks_enable = QCheckBox("Enable Custom KinoScript Engine (Compiles directly to ARM7TDMI .gba ROM)")
        self.cb_ks_enable.toggled.connect(self._on_ks_toggled)
        kbl.addWidget(self.cb_ks_enable, 1)
        b_val = QPushButton("Check & Compile ARM")
        b_val.setObjectName("PrimaryButton")
        b_val.clicked.connect(self._validate_ks)
        kbl.addWidget(b_val)
        b_tpl = QPushButton("Insert Starter...")
        b_tpl.clicked.connect(self._insert_ks_starter)
        kbl.addWidget(b_tpl)
        kleft.addWidget(kbar)

        self.ed_ks = QPlainTextEdit()
        self.ed_ks.setStyleSheet("font-family:Consolas; font-size:9.5pt; line-height:1.35;")
        self.ed_ks.setPlaceholderText(
            "# Write unrestricted Python-syntax GBA logic here!\n"
            "# Compiles directly to native ARM7TDMI machine code with zero external SDK.\n"
            "def on_init():\n    clear_ui()\n    draw_text(2, 1, 'HELLO GBA!')\n\n"
            "def on_frame():\n    pass\n"
        )
        self.ed_ks.textChanged.connect(self._on_ks_text_changed)
        kleft.addWidget(self.ed_ks, 1)

        self.lbl_ks_status = QLabel("Visual Mode Active — check 'Enable Custom KinoScript Engine' to take full hardware control.")
        self.lbl_ks_status.setStyleSheet("color:#94A3B8; font-family:Consolas; font-size:8.5pt; padding:3px;")
        kleft.addWidget(self.lbl_ks_status)
        kroot.addLayout(kleft, 3)

        # Right: Built-in GBA Hardware API Quick Reference
        ref_box = QGroupBox("KinoScript GBA Hardware API (128 OAM · 3 BGs · 240KB RAM · SRAM · Audio)")
        rl = QVBoxLayout(ref_box)
        ref = QPlainTextEdit()
        ref.setReadOnly(True)
        ref.setStyleSheet("font-family:Consolas; font-size:8.2pt; color:#CBD5E1;")
        ref.setPlainText(
            "LIFECYCLE:\n"
            "  def on_init():   # Called once at GBA boot\n"
            "  def on_frame():  # Called at 60 FPS VBlank\n\n"
            "GLOBALS & ARRAYS (240 KB EWRAM):\n"
            "  score = 0\n"
            "  u_hp = [0] * 32\n"
            "  costs = [1000, 2000, 3000, 4000]\n\n"
            "INPUT (BTN_A/B/L/R/UP/DOWN/LEFT/RIGHT/START/SELECT):\n"
            "  key_held(BTN_RIGHT)\n"
            "  key_pressed(BTN_A)\n"
            "  key_released(BTN_B)\n\n"
            "128 HARDWARE OAM SPRITES (16x16..64x64):\n"
            "  set_sprite(slot, x, y, sp_idx, frame, pal, hflip)\n"
            "  hide_sprite(slot)\n"
            "  hide_all_sprites()\n\n"
            "TILEMAPS & BG1 UI:\n"
            "  load_room(idx), room_width(), room_height()\n"
            "  get_tile(tx, ty), get_tile_type(tx, ty)\n"
            "  set_tile(tx, ty, tile_id)\n"
            "  set_ui_tile(tx, ty, tile_id, pal)\n"
            "  scroll_bg(layer, x, y)\n"
            "  draw_box(tx, ty, w, h)\n"
            "  draw_text(tx, ty, 'TEXT')\n"
            "  draw_num(tx, ty, val, digits)\n"
            "  clear_ui_rect(tx, ty, w, h), clear_ui()\n\n"
            "AUDIO, SRAM & MATH:\n"
            "  play_sfx(idx), play_dma(), bgm_enable(1)\n"
            "  sram_write(addr, val), sram_read(addr)\n"
            "  frame_count(), rand(), abs(x), min(a,b), max(a,b), clamp(x,lo,hi)\n"
        )
        rl.addWidget(ref)
        kroot.addWidget(ref_box, 2)

        self.logic_tabs.addTab(ks_tab, "KinoScript Native ARM7TDMI Studio (Full Custom Engine)")
        outer.addWidget(self.logic_tabs, 1)

    def set_project(self, proj: KinoPixelProject) -> None:
        self.project = proj
        self.filter_btn = ""
        self.diagram.selected_button = None
        self.refresh_all()

    def _on_diagram_clicked(self, btn: str) -> None:
        self.filter_btn = btn
        self.lbl_rules_hdr.setText(f"BUTTON WIRING RULES — [{btn}]" if btn else "BUTTON WIRING RULES — ALL BUTTONS")
        self._rebuild_cards()

    def refresh_all(self) -> None:
        if not self.project:
            return
        self.sp_start_v0.blockSignals(True)
        self.sp_start_v0.setValue(int(self.project.starting_vars[0]) if self.project.starting_vars else 10)
        self.sp_start_v0.blockSignals(False)
        self.cb_ks_enable.blockSignals(True)
        self.cb_ks_enable.setChecked(bool(self.project.script_enabled))
        self.cb_ks_enable.blockSignals(False)
        self.ed_ks.blockSignals(True)
        if self.ed_ks.toPlainText() != self.project.script_code:
            self.ed_ks.setPlainText(self.project.script_code)
        self.ed_ks.blockSignals(False)
        if self.project.script_enabled and self.project.script_code.strip():
            self._validate_ks(silent=True)
        else:
            self.lbl_ks_status.setText("Visual Mode Active — enable KinoScript to compile custom ARM7TDMI logic.")
            self.lbl_ks_status.setStyleSheet("color:#94A3B8; font-family:Consolas; font-size:8.5pt; padding:3px;")
        self.diagram.set_project(self.project)
        self._rebuild_cards()

    def _on_ks_toggled(self, on: bool) -> None:
        if not self.project:
            return
        self.project.script_enabled = on
        if on and not self.project.script_code.strip():
            self._insert_ks_starter(preset="Blank Custom GBA Loop")
        self.projectModified.emit("Toggle KinoScript Engine")
        if on:
            self._validate_ks(silent=True)

    def _on_ks_text_changed(self) -> None:
        if self.project:
            self.project.script_code = self.ed_ks.toPlainText()
            self.project.dirty = True

    def _validate_ks(self, silent: bool = False) -> None:
        if not self.project:
            return
        code = self.ed_ks.toPlainText()
        self.project.script_code = code
        ok, msg, _ = validate_kinoscript(code)
        if ok:
            self.lbl_ks_status.setText(f"✓ {msg}")
            self.lbl_ks_status.setStyleSheet("color:#34D399; font-family:Consolas; font-size:8.5pt; font-weight:600; padding:3px;")
        else:
            self.lbl_ks_status.setText(f"✕ {msg}")
            self.lbl_ks_status.setStyleSheet("color:#F43F5E; font-family:Consolas; font-size:8.5pt; font-weight:600; padding:3px;")

    def _insert_ks_starter(self, preset: Optional[str] = None) -> None:
        if not self.project:
            return
        if not preset:
            choice, ok = QInputDialog.getItem(
                self, "Insert KinoScript Starter", "Choose Starter Script:",
                ["Blank Custom GBA Loop", "Simple Cursor & Menu Sandbox"], 0, False,
            )
            if not ok:
                return
            preset = choice
        if "Cursor" in preset:
            src = (
                "cx = 4\ncy = 4\n\n"
                "def on_init():\n"
                "    clear_ui()\n"
                "    draw_text(1, 0, 'CUSTOM KINOSCRIPT GBA')\n\n"
                "def on_frame():\n"
                "    if key_pressed(BTN_RIGHT):\n        cx = clamp(cx + 1, 0, 14)\n        play_sfx(1)\n"
                "    if key_pressed(BTN_LEFT):\n        cx = clamp(cx - 1, 0, 14)\n        play_sfx(1)\n"
                "    if key_pressed(BTN_DOWN):\n        cy = clamp(cy + 1, 1, 8)\n        play_sfx(1)\n"
                "    if key_pressed(BTN_UP):\n        cy = clamp(cy - 1, 1, 8)\n        play_sfx(1)\n"
                "    set_sprite(0, cx * 16, cy * 16, 0, 0, 0, 0)\n"
                "    draw_num(26, 0, cx, 2)\n"
            )
        else:
            src = (
                "px = 112\npy = 72\n\n"
                "def on_init():\n"
                "    clear_ui()\n"
                "    draw_text(1, 0, 'KINOSCRIPT READY')\n\n"
                "def on_frame():\n"
                "    if key_held(BTN_RIGHT):\n        px = clamp(px + 2, 0, 224)\n"
                "    if key_held(BTN_LEFT):\n        px = clamp(px - 2, 0, 224)\n"
                "    if key_held(BTN_DOWN):\n        py = clamp(py + 2, 8, 144)\n"
                "    if key_held(BTN_UP):\n        py = clamp(py - 2, 8, 144)\n"
                "    if key_pressed(BTN_A):\n        play_sfx(0)\n"
                "    set_sprite(0, px, py, 0, (frame_count() >> 3) & 1, 0, 0)\n"
            )
        self.ed_ks.setPlainText(src)
        self.project.script_code = src
        self.project.script_enabled = True
        self.cb_ks_enable.setChecked(True)
        self._validate_ks(silent=True)
        self.projectModified.emit("Insert KinoScript Starter")

    def _on_start_var0_changed(self, v: int) -> None:
        if self.project:
            if not self.project.starting_vars:
                self.project.starting_vars = [v, 0, 0, 0, 0, 0, 0, 0]
            else:
                self.project.starting_vars[0] = v
            self.projectModified.emit("Edit Starting Var[0]")

    def _rebuild_cards(self) -> None:
        while self.cards_lay.count():
            item = self.cards_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.project:
            return

        avail_btns = list(self.project.profile()["buttons"])
        anim_names = [""] + [a.name for a in self.project.sprites[0].animations] if self.project.sprites else [""]

        for idx, rule in enumerate(self.project.button_rules):
            if self.filter_btn and rule.button != self.filter_btn:
                continue
            card = QWidget()
            card.setObjectName("CardFrame")
            cl = QGridLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setHorizontalSpacing(8)
            cl.setVerticalSpacing(5)

            cb_en = QCheckBox()
            cb_en.setChecked(rule.enabled)
            cb_en.toggled.connect(lambda v, r=rule: self._edit_rule(r, "enabled", v))
            cl.addWidget(cb_en, 0, 0)

            cl.addWidget(QLabel("When"), 0, 1)
            cmb_btn = QComboBox()
            for b in avail_btns:
                cmb_btn.addItem(b, b)
            bi = cmb_btn.findData(rule.button)
            if bi >= 0:
                cmb_btn.setCurrentIndex(bi)
            cmb_btn.currentIndexChanged.connect(lambda _, c=cmb_btn, r=rule: self._edit_rule(r, "button", str(c.currentData())))
            cl.addWidget(cmb_btn, 0, 2)

            cmb_trig = QComboBox()
            for k, v in TRIGGER_NAMES.items():
                cmb_trig.addItem(v, k)
            cmb_trig.setCurrentIndex(max(0, cmb_trig.findData(rule.trigger)))
            cmb_trig.currentIndexChanged.connect(lambda _, c=cmb_trig, r=rule: self._edit_rule(r, "trigger", int(c.currentData())))
            cl.addWidget(cmb_trig, 0, 3)

            cl.addWidget(QLabel("→ Do"), 0, 4)
            cmb_act = QComboBox()
            for k, v in ACTION_NAMES.items():
                cmb_act.addItem(v, k)
            cmb_act.setCurrentIndex(max(0, cmb_act.findData(rule.action)))
            cmb_act.currentIndexChanged.connect(lambda _, c=cmb_act, r=rule: self._edit_rule(r, "action", int(c.currentData())))
            cl.addWidget(cmb_act, 0, 5, 1, 2)

            b_del = QPushButton("✕")
            b_del.setObjectName("DangerButton")
            b_del.setFixedWidth(28)
            b_del.clicked.connect(lambda _=False, i=idx: self._delete_rule(i))
            cl.addWidget(b_del, 0, 7)

            # Row 2: Power/Speed, Animation, Chiptune SFX
            cl.addWidget(QLabel("Power:"), 1, 1)
            sp_p = QSpinBox()
            sp_p.setRange(0, 12)
            sp_p.setValue(rule.param)
            sp_p.valueChanged.connect(lambda v, r=rule: self._edit_rule(r, "param", v))
            cl.addWidget(sp_p, 1, 2)

            cl.addWidget(QLabel("Anim:"), 1, 3)
            cmb_an = QComboBox()
            for an in anim_names:
                cmb_an.addItem(an if an else "(Auto)", an)
            ai = cmb_an.findData(rule.anim_name)
            if ai >= 0:
                cmb_an.setCurrentIndex(ai)
            cmb_an.currentIndexChanged.connect(lambda _, c=cmb_an, r=rule: self._edit_rule(r, "anim_name", str(c.currentData())))
            cl.addWidget(cmb_an, 1, 4)

            cl.addWidget(QLabel("SFX:"), 1, 5)
            cmb_sfx = QComboBox()
            cmb_sfx.addItem("(None)", -1)
            for si, patch in enumerate(self.project.sfx_list):
                cmb_sfx.addItem(f"#{si} {patch.name}", si)
            sfi = cmb_sfx.findData(rule.sfx_index)
            if sfi >= 0:
                cmb_sfx.setCurrentIndex(sfi)
            cmb_sfx.currentIndexChanged.connect(lambda _, c=cmb_sfx, r=rule: self._edit_rule(r, "sfx_index", int(c.currentData())))
            cl.addWidget(cmb_sfx, 1, 6, 1, 2)

            # Row 3: Universal Conditional Gate & Variable Delta (Ammo / Ki / MP / Funds / Flags!)
            cl.addWidget(QLabel("Cond:"), 2, 1)
            cmb_cond = QComboBox()
            for ck, cv in COND_NAMES.items():
                cmb_cond.addItem(cv, ck)
            cmb_cond.setCurrentIndex(max(0, cmb_cond.findData(rule.cond_type)))
            cmb_cond.currentIndexChanged.connect(lambda _, c=cmb_cond, r=rule: self._edit_rule(r, "cond_type", int(c.currentData())))
            cl.addWidget(cmb_cond, 2, 2, 1, 2)

            cl.addWidget(QLabel("Idx:"), 2, 4)
            sp_ci = QSpinBox()
            sp_ci.setRange(0, 31)
            sp_ci.setValue(rule.cond_idx)
            sp_ci.valueChanged.connect(lambda v, r=rule: self._edit_rule(r, "cond_idx", v))
            cl.addWidget(sp_ci, 2, 5)

            cl.addWidget(QLabel("Var +/-:"), 2, 6)
            sp_vd = QSpinBox()
            sp_vd.setRange(-10, 10)
            sp_vd.setValue(rule.var_delta)
            sp_vd.valueChanged.connect(lambda v, r=rule: self._edit_rule(r, "var_delta", v))
            cl.addWidget(sp_vd, 2, 7)

            self.cards_lay.addWidget(card)

        self.cards_lay.addStretch(1)

    def _edit_rule(self, rule: ButtonRule, attr: str, val) -> None:
        setattr(rule, attr, val)
        self.diagram.update()
        self.projectModified.emit("Update Button Wiring")

    def _add_rule(self) -> None:
        if not self.project:
            return
        btn = self.filter_btn or "A"
        self.project.button_rules.append(ButtonRule(button=btn, trigger=TRIGGER_PRESSED, action=ACTION_JUMP, param=5, anim_name="jump", sfx_index=0))
        self.refresh_all()
        self.projectModified.emit("Add Button Wire")

    def _delete_rule(self, idx: int) -> None:
        if self.project and 0 <= idx < len(self.project.button_rules):
            self.project.button_rules.pop(idx)
            self.refresh_all()
            self.projectModified.emit("Delete Button Wire")

    def _apply_scheme(self, kind: str) -> None:
        if not self.project:
            return
        if kind in ("exploration", "metroidvania"):
            self.project.physics_mode = "platformer"
            rules = [
                ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="L", trigger=TRIGGER_HELD, action=ACTION_AIM_UP, param=0, anim_name="", sfx_index=-1),
                ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_JUMP, param=6, anim_name="jump", sfx_index=0),
                ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=5, anim_name="attack", sfx_index=2),
                ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_BOMB, param=4, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
                ButtonRule(button="SELECT", trigger=TRIGGER_PRESSED, action=ACTION_MORPH_BALL, param=0, anim_name="", sfx_index=3),
                ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
            ]
        elif kind == "topdown":
            self.project.physics_mode = "topdown"
            rules = [
                ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_MELEE, param=3, anim_name="attack", sfx_index=3),
                ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=4, anim_name="attack", sfx_index=2),
                ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_SUPER_BURST, param=5, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-2),
                ButtonRule(button="L", trigger=TRIGGER_PRESSED, action=ACTION_HEAL, param=1, anim_name="", sfx_index=1, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
                ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
            ]
        elif kind == "shmup":
            self.project.physics_mode = "shmup"
            rules = [
                ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=3, anim_name="walk", sfx_index=-1),
                ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=3, anim_name="walk", sfx_index=-1),
                ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=3, anim_name="walk", sfx_index=-1),
                ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=3, anim_name="walk", sfx_index=-1),
                ButtonRule(button="B", trigger=TRIGGER_HELD, action=ACTION_SHOOT, param=6, anim_name="attack", sfx_index=2),
                ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_DASH, param=6, anim_name="walk", sfx_index=3),
                ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_SUPER_BURST, param=5, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
                ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
            ]
        elif kind == "tactical":
            self.project.physics_mode = "tactical"
            rules = [
                ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="UP", trigger=TRIGGER_HELD, action=ACTION_MOVE_UP, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="DOWN", trigger=TRIGGER_HELD, action=ACTION_MOVE_DOWN, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=5, anim_name="attack", sfx_index=2),
                ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_BOMB, param=4, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
                ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_SUPER_BURST, param=5, anim_name="attack", sfx_index=4, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-2),
                ButtonRule(button="L", trigger=TRIGGER_PRESSED, action=ACTION_HEAL, param=1, anim_name="", sfx_index=1, cond_type=COND_VAR_POS, cond_idx=0, var_delta=-1),
                ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="", sfx_index=-1),
            ]
        else:
            self.project.physics_mode = "platformer"
            rules = [
                ButtonRule(button="LEFT", trigger=TRIGGER_HELD, action=ACTION_MOVE_LEFT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="RIGHT", trigger=TRIGGER_HELD, action=ACTION_MOVE_RIGHT, param=2, anim_name="walk", sfx_index=-1),
                ButtonRule(button="A", trigger=TRIGGER_PRESSED, action=ACTION_JUMP, param=5, anim_name="jump", sfx_index=0),
                ButtonRule(button="B", trigger=TRIGGER_PRESSED, action=ACTION_SHOOT, param=4, anim_name="attack", sfx_index=2),
                ButtonRule(button="R", trigger=TRIGGER_PRESSED, action=ACTION_DASH, param=5, anim_name="jump", sfx_index=3),
                ButtonRule(button="L", trigger=TRIGGER_PRESSED, action=ACTION_MELEE, param=3, anim_name="attack", sfx_index=3),
                ButtonRule(button="SELECT", trigger=TRIGGER_PRESSED, action=ACTION_PALETTE_NEXT, param=1, anim_name="", sfx_index=1),
                ButtonRule(button="START", trigger=TRIGGER_PRESSED, action=ACTION_PAUSE, param=0, anim_name="idle", sfx_index=-1),
            ]
        avail = set(self.project.profile()["buttons"])
        self.project.button_rules = [r for r in rules if r.button in avail]
        self.refresh_all()
        self.projectModified.emit(f"Apply {kind.title()} Wiring Preset")


# ---------------------------------------------------------------------------
# Stage 4: Chiptune Audio & Sequence Genie Studio (Soundtrack + Hardware SFX)
# ---------------------------------------------------------------------------
class SfxEditorPage(QWidget):
    projectModified = Signal(str)

    def __init__(self, audio: ChiptuneAudioPlayer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audio = audio
        self.project: Optional[KinoPixelProject] = None
        self.sfx_idx: int = 0
        self._loading = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.setDocumentMode(True)

        # Sub-Tab 1: Sequence Genie Generative Chiptune Composer
        self.genie_panel = SequenceGeniePanel()
        self.genie_panel.projectModified.connect(self.projectModified.emit)
        self.sub_tabs.addTab(self.genie_panel, "Sequence Genie Composer (BGM · Chords · Drums)")

        # Sub-Tab 2: Hardware PSG SFX Designer
        sfx_tab = QWidget()
        root = QHBoxLayout(sfx_tab)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(10)

        left = QWidget()
        left.setObjectName("SidePane")
        left.setFixedWidth(240)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)

        h = QLabel("HARDWARE PSG SFX BANK")
        h.setObjectName("SectionHeader")
        ll.addWidget(h)

        self.lst_sfx = QListWidget()
        self.lst_sfx.currentRowChanged.connect(self._on_sfx_selected)
        ll.addWidget(self.lst_sfx, 1)

        b_add = QPushButton("+ New SFX Patch")
        b_add.clicked.connect(self._add_sfx)
        ll.addWidget(b_add)
        root.addWidget(left)

        right = QVBoxLayout()
        self.wave_view = SfxWaveformWidget()
        right.addWidget(self.wave_view)

        form_box = QGroupBox("GBA / GB PSG Register Synthesizer")
        fl = QFormLayout(form_box)
        self.ed_name = QLineEdit()
        self.ed_name.textEdited.connect(self._apply_controls)
        fl.addRow("Patch Name:", self.ed_name)

        self.cmb_ch = QComboBox()
        self.cmb_ch.addItem("Channel 1 — Square Wave + Pitch Sweep", 1)
        self.cmb_ch.addItem("Channel 4 — LFSR Retro Noise", 4)
        self.cmb_ch.currentIndexChanged.connect(self._apply_controls)
        fl.addRow("Hardware Channel:", self.cmb_ch)

        self.sl_freq = self._mk_slider(100, 2200, 440, " Hz")
        fl.addRow("Base Pitch:", self.sl_freq[0])

        self.cmb_duty = QComboBox()
        for i, d in enumerate(["12.5% Thin", "25% Crisp", "50% Square", "75% Hollow"]):
            self.cmb_duty.addItem(d, i)
        self.cmb_duty.currentIndexChanged.connect(self._apply_controls)
        fl.addRow("Square Duty:", self.cmb_duty)

        self.sl_vol = self._mk_slider(1, 15, 13, "")
        fl.addRow("Volume (0..15):", self.sl_vol[0])

        self.sl_env = self._mk_slider(0, 7, 2, "")
        fl.addRow("Envelope Decay:", self.sl_env[0])

        self.sl_sw_time = self._mk_slider(0, 7, 2, "")
        fl.addRow("Sweep Speed:", self.sl_sw_time[0])

        self.cmb_sw_dir = QComboBox()
        self.cmb_sw_dir.addItem("Pitch Up (Jump / Coin)", 0)
        self.cmb_sw_dir.addItem("Pitch Down (Laser / Drop)", 1)
        self.cmb_sw_dir.currentIndexChanged.connect(self._apply_controls)
        fl.addRow("Sweep Direction:", self.cmb_sw_dir)

        self.sl_sw_shift = self._mk_slider(0, 7, 3, "")
        fl.addRow("Sweep Intensity:", self.sl_sw_shift[0])

        self.cb_short_noise = QCheckBox("7-Bit Metallic Noise (Channel 4)")
        self.cb_short_noise.toggled.connect(self._apply_controls)
        fl.addRow("", self.cb_short_noise)

        self.sl_dur = self._mk_slider(50, 700, 180, " ms")
        fl.addRow("Duration:", self.sl_dur[0])

        self.lbl_regs = QLabel("GBA Registers: SOUND1CNT_L=0x0000  H=0x0000  X=0x8000")
        self.lbl_regs.setStyleSheet("font-family:Consolas; color:#34D399; font-size:8.5pt;")
        fl.addRow("Compiled Regs:", self.lbl_regs)
        right.addWidget(form_box)

        prow = QHBoxLayout()
        b_play = QPushButton("▶  Preview Chiptune SFX")
        b_play.setObjectName("PlayButton")
        b_play.setFixedHeight(34)
        b_play.clicked.connect(self._preview_current)
        prow.addWidget(b_play, 1)
        right.addLayout(prow)

        # Direct Sound DMA Channel A (8-bit PCM Hardware Audio)
        dma_box = QGroupBox("GBA Direct Sound DMA Channel A (8-bit PCM Sample)")
        dl = QHBoxLayout(dma_box)
        self.cb_dma_en = QCheckBox("Enable DMA Audio")
        self.cb_dma_en.setChecked(True)
        self.cb_dma_en.toggled.connect(self._on_dma_changed)
        dl.addWidget(self.cb_dma_en)
        self.cmb_dma_preset = QComboBox()
        self.cmb_dma_preset.addItems(DIRECT_SOUND_PRESETS)
        self.cmb_dma_preset.currentIndexChanged.connect(self._on_dma_changed)
        dl.addWidget(self.cmb_dma_preset, 1)
        b_dma_play = QPushButton("▶ Preview DMA PCM")
        b_dma_play.clicked.connect(self._preview_dma)
        dl.addWidget(b_dma_play)
        right.addWidget(dma_box)
        right.addStretch(1)
        root.addLayout(right, 1)

        self.sub_tabs.addTab(sfx_tab, "Hardware PSG SFX Designer (Channel 1 & 4)")
        outer.addWidget(self.sub_tabs, 1)

    def _mk_slider(self, lo: int, hi: int, val: int, suffix: str):
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(val)
        lbl = QLabel(f"{val}{suffix}")
        lbl.setFixedWidth(60)
        sl.valueChanged.connect(lambda v, la=lbl, s=suffix: la.setText(f"{v}{s}"))
        sl.valueChanged.connect(self._apply_controls)
        l.addWidget(sl, 1)
        l.addWidget(lbl)
        return w, sl, lbl

    def set_project(self, proj: KinoPixelProject) -> None:
        self.project = proj
        self.sfx_idx = min(self.sfx_idx, max(0, len(proj.sfx_list) - 1))
        self.genie_panel.set_project(proj)
        self.refresh_all()

    def stop_audio(self) -> None:
        self.genie_panel.stop_audio()

    def refresh_all(self) -> None:
        if not self.project:
            return
        self.genie_panel.refresh_all()
        self.lst_sfx.blockSignals(True)
        self.lst_sfx.clear()
        for i, s in enumerate(self.project.sfx_list):
            ch_tag = "NOISE" if s.channel == 4 else "SQR"
            self.lst_sfx.addItem(f"#{i} {s.name} [{ch_tag}]")
        self.lst_sfx.setCurrentRow(self.sfx_idx)
        self.lst_sfx.blockSignals(False)
        self.cb_dma_en.blockSignals(True)
        self.cb_dma_en.setChecked(self.project.direct_sound.enabled)
        self.cb_dma_en.blockSignals(False)
        self.cmb_dma_preset.blockSignals(True)
        self.cmb_dma_preset.setCurrentText(self.project.direct_sound.preset)
        self.cmb_dma_preset.blockSignals(False)
        self._load_current()

    def _cur_patch(self) -> Optional[SfxPatch]:
        if self.project and 0 <= self.sfx_idx < len(self.project.sfx_list):
            return self.project.sfx_list[self.sfx_idx]
        return None

    def _on_sfx_selected(self, row: int) -> None:
        if row >= 0:
            self.sfx_idx = row
            self._load_current()

    def _load_current(self) -> None:
        p = self._cur_patch()
        if not p:
            return
        self._loading = True
        self.ed_name.setText(p.name)
        self.cmb_ch.setCurrentIndex(1 if p.channel == 4 else 0)
        self.sl_freq[1].setValue(p.freq_hz)
        self.cmb_duty.setCurrentIndex(p.duty & 3)
        self.sl_vol[1].setValue(p.volume)
        self.sl_env[1].setValue(p.env_step)
        self.sl_sw_time[1].setValue(p.sweep_time)
        self.cmb_sw_dir.setCurrentIndex(p.sweep_dir & 1)
        self.sl_sw_shift[1].setValue(p.sweep_shift)
        self.cb_short_noise.setChecked(p.noise_short)
        self.sl_dur[1].setValue(p.duration_ms)
        self._loading = False
        self._update_wave_and_regs()

    def _apply_controls(self) -> None:
        if self._loading:
            return
        p = self._cur_patch()
        if not p:
            return
        p.name = self.ed_name.text().strip() or "SFX"
        p.channel = int(self.cmb_ch.currentData())
        p.freq_hz = self.sl_freq[1].value()
        p.duty = int(self.cmb_duty.currentData())
        p.volume = self.sl_vol[1].value()
        p.env_step = self.sl_env[1].value()
        p.sweep_time = self.sl_sw_time[1].value()
        p.sweep_dir = int(self.cmb_sw_dir.currentData())
        p.sweep_shift = self.sl_sw_shift[1].value()
        p.noise_short = self.cb_short_noise.isChecked()
        p.duration_ms = self.sl_dur[1].value()
        if 0 <= self.sfx_idx < self.lst_sfx.count():
            ch_tag = "NOISE" if p.channel == 4 else "SQR"
            self.lst_sfx.item(self.sfx_idx).setText(f"#{self.sfx_idx} {p.name} [{ch_tag}]")
        self._update_wave_and_regs()
        self.projectModified.emit("Edit Chiptune SFX")

    def _update_wave_and_regs(self) -> None:
        p = self._cur_patch()
        if not p:
            return
        wave = synthesize_sfx_waveform(p)
        self.wave_view.set_samples(wave)
        ch, cl, ch_r, cx = p.to_gba_regs()
        if ch == 4:
            self.lbl_regs.setText(f"SOUND4CNT_L=0x{cl:04X}  SOUND4CNT_H=0x{ch_r:04X}")
        else:
            self.lbl_regs.setText(f"SOUND1CNT_L=0x{cl:04X}  H=0x{ch_r:04X}  X=0x{cx:04X}")

    def _preview_current(self) -> None:
        p = self._cur_patch()
        if p:
            self.audio.play_patch(p)

    def _add_sfx(self) -> None:
        if not self.project:
            return
        self.project.sfx_list.append(SfxPatch(name=f"Sound {len(self.project.sfx_list) + 1}"))
        self.sfx_idx = len(self.project.sfx_list) - 1
        self.refresh_all()
        self.projectModified.emit("Add Chiptune SFX")

    def _on_dma_changed(self) -> None:
        if not self.project:
            return
        self.project.direct_sound.enabled = self.cb_dma_en.isChecked()
        self.project.direct_sound.preset = self.cmb_dma_preset.currentText()
        self.projectModified.emit("Update Direct Sound DMA Sample")

    def _preview_dma(self) -> None:
        if self.project:
            self.audio.play_direct_sound(self.project.direct_sound)


# ---------------------------------------------------------------------------
# Stage 5: Live 60 FPS Playtest & Real Playable .gba ROM Builder
# ---------------------------------------------------------------------------
class PlaytestBuildPage(QWidget):
    projectModified = Signal(str)
    romBuilt = Signal(object)

    def __init__(self, audio: ChiptuneAudioPlayer, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audio = audio
        self.project: Optional[KinoPixelProject] = None
        self.sim: Optional[GamePlaytestEngine] = None
        self.running: bool = False
        self._held_mouse_btns: Set[str] = set()
        self._last_output_path: Optional[str] = None
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 Hz
        self._timer.timeout.connect(self._on_tick)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # Left: Live Playable Handheld + Touch Gamepad
        left = QVBoxLayout()
        tbar = QWidget()
        tbar.setObjectName("ControlBar")
        tl = QHBoxLayout(tbar)
        tl.setContentsMargins(6, 4, 6, 4)

        self.btn_run = QPushButton("▶  Start Live Playtest")
        self.btn_run.setObjectName("PlayButton")
        self.btn_run.clicked.connect(self.toggle_playtest)
        tl.addWidget(self.btn_run)

        b_rst = QPushButton("Restart Stage")
        b_rst.clicked.connect(self.reset_playtest)
        tl.addWidget(b_rst)

        self.cb_lcd = QCheckBox("LCD Matrix Grid")
        self.cb_lcd.setChecked(True)
        self.cb_lcd.toggled.connect(self._toggle_lcd)
        tl.addWidget(self.cb_lcd)

        self.cb_mute = QCheckBox("Mute SFX")
        self.cb_mute.toggled.connect(lambda v: setattr(self.audio, "muted", v))
        tl.addWidget(self.cb_mute)
        tl.addStretch(1)
        left.addWidget(tbar)

        self.screen = PlaytestScreenWidget()
        left.addWidget(self.screen, 1)

        # Clickable on-screen handheld gamepad + keyboard legend
        pad_bar = QWidget()
        pad_bar.setObjectName("CardFrame")
        pl = QHBoxLayout(pad_bar)
        pl.setContentsMargins(10, 6, 10, 6)
        for btn_name in ["LEFT", "RIGHT", "UP", "DOWN", "A", "B", "L", "R", "START", "SELECT"]:
            b = QPushButton(btn_name)
            b.setFixedHeight(28)
            b.pressed.connect(lambda n=btn_name: self._held_mouse_btns.add(n))
            b.released.connect(lambda n=btn_name: self._held_mouse_btns.discard(n))
            pl.addWidget(b)
        left.addWidget(pad_bar)

        hint = QLabel("Keyboard: Arrows / WASD = D-Pad  ·  Z / Space = A  ·  X / Shift = B  ·  Q = L  ·  E = R  ·  Enter = Start  ·  Tab = Select")
        hint.setStyleSheet("color:#94A3B8; font-size:8pt;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(hint)
        root.addLayout(left, 3)

        # Right: Cartridge Header & Native ROM Compiler
        right = QVBoxLayout()
        hdr_box = QGroupBox("Cartridge Header & Target Hardware")
        fl = QFormLayout(hdr_box)
        self.ed_title = QLineEdit()
        self.ed_title.setMaxLength(12)
        self.ed_title.textEdited.connect(self._on_header_edited)
        fl.addRow("ROM Title (12ch):", self.ed_title)

        self.ed_code = QLineEdit()
        self.ed_code.setMaxLength(4)
        self.ed_code.textEdited.connect(self._on_header_edited)
        fl.addRow("Game Code (4ch):", self.ed_code)

        self.ed_maker = QLineEdit()
        self.ed_maker.setMaxLength(2)
        self.ed_maker.textEdited.connect(self._on_header_edited)
        fl.addRow("Maker Code (2ch):", self.ed_maker)

        self.cmb_target = QComboBox()
        self.cmb_target.addItem("Game Boy Advance (GBA · 240×160)", "GBA")
        self.cmb_target.addItem("Game Boy Color (GBC · 160×144)", "GBC")
        self.cmb_target.addItem("Game Boy Classic (DMG · 160×144)", "GB")
        self.cmb_target.currentIndexChanged.connect(self._on_target_changed)
        fl.addRow("Target System:", self.cmb_target)

        self.cb_sram = QCheckBox("GBA Cartridge SRAM Save (SRAM_V113)")
        self.cb_sram.setChecked(True)
        self.cb_sram.toggled.connect(self._on_hw_flags_changed)
        fl.addRow("", self.cb_sram)

        self.cb_alpha = QCheckBox("BG2 Parallax Hardware Alpha Blending")
        self.cb_alpha.setChecked(True)
        self.cb_alpha.toggled.connect(self._on_hw_flags_changed)
        fl.addRow("", self.cb_alpha)
        right.addWidget(hdr_box)

        build_box = QGroupBox("One-Click Cartridge Compiler (Zero External Toolchain)")
        bl = QVBoxLayout(build_box)
        self.btn_build_gba = QPushButton("Build Playable .gba ROM...")
        self.btn_build_gba.setIcon(make_icon("cartridge", 18, color="#FFFFFF"))
        self.btn_build_gba.setObjectName("PrimaryButton")
        self.btn_build_gba.setFixedHeight(38)
        self.btn_build_gba.clicked.connect(self.build_gba_dialog)
        bl.addWidget(self.btn_build_gba)

        row2 = QHBoxLayout()
        b_gb = QPushButton("Export .gb / .gbc...")
        b_gb.clicked.connect(self.build_gb_dialog)
        b_c = QPushButton("Export C Starter (devkitARM)...")
        b_c.clicked.connect(self.export_c_dialog)
        row2.addWidget(b_gb)
        row2.addWidget(b_c)
        bl.addLayout(row2)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family:Consolas; font-size:8.3pt;")
        self.log.setPlaceholderText("Click 'Build Playable .gba ROM...' to compile native ARM7TDMI machine code directly into a bootable cartridge image.")
        bl.addWidget(self.log, 1)
        right.addWidget(build_box, 1)
        root.addLayout(right, 2)

    def set_project(self, proj: KinoPixelProject) -> None:
        self.project = proj
        self.sim = GamePlaytestEngine(proj, on_sfx=self._play_sfx_index, on_dma=self._play_dma)
        self.refresh_all()
        self._render_once()

    def refresh_all(self) -> None:
        if not self.project:
            return
        self.ed_title.blockSignals(True)
        self.ed_title.setText(self.project.title)
        self.ed_title.blockSignals(False)
        self.ed_code.blockSignals(True)
        self.ed_code.setText(self.project.game_code)
        self.ed_code.blockSignals(False)
        self.ed_maker.blockSignals(True)
        self.ed_maker.setText(self.project.maker_code)
        self.ed_maker.blockSignals(False)
        self.cmb_target.blockSignals(True)
        idx = self.cmb_target.findData(self.project.target_system)
        if idx >= 0:
            self.cmb_target.setCurrentIndex(idx)
        self.cmb_target.blockSignals(False)
        self.cb_sram.blockSignals(True)
        self.cb_sram.setChecked(self.project.sram_save_enabled)
        self.cb_sram.blockSignals(False)
        self.cb_alpha.blockSignals(True)
        self.cb_alpha.setChecked(self.project.alpha_blend_enabled)
        self.cb_alpha.blockSignals(False)

    def _play_sfx_index(self, idx: int) -> None:
        if self.project and 0 <= idx < len(self.project.sfx_list):
            self.audio.play_patch(self.project.sfx_list[idx])

    def _play_dma(self) -> None:
        if self.project:
            self.audio.play_direct_sound(self.project.direct_sound)

    def start_playtest(self) -> None:
        if not self.project:
            return
        self.sim = GamePlaytestEngine(self.project, on_sfx=self._play_sfx_index, on_dma=self._play_dma)
        self.running = True
        self.btn_run.setText("■  Stop Playtest")
        self._timer.start()
        self.screen.setFocus()

    def stop_playtest(self) -> None:
        self.running = False
        self._timer.stop()
        self.btn_run.setText("▶  Start Live Playtest")

    def toggle_playtest(self) -> None:
        if self.running:
            self.stop_playtest()
        else:
            self.start_playtest()

    def reset_playtest(self) -> None:
        if self.project:
            self.sim = GamePlaytestEngine(self.project, on_sfx=self._play_sfx_index, on_dma=self._play_dma)
            self._render_once()
            self.screen.setFocus()

    def _toggle_lcd(self, on: bool) -> None:
        self.screen.lcd_grid = on
        self.screen.update()

    def _on_tick(self) -> None:
        if not self.sim or not self.running:
            return
        keys = set(self.screen.pressed_keys) | set(self._held_mouse_btns)
        self.sim.step(keys)
        self._render_once()

    def _render_once(self) -> None:
        if not self.sim or not self.project:
            return
        rgb = self.sim.render_rgb()
        mrooms = [
            (ri, self.project.rooms[ri].world_x, self.project.rooms[ri].world_y)
            for ri in sorted(self.sim.visited_rooms)
            if 0 <= ri < len(self.project.rooms)
        ]
        self.screen.set_frame(
            rgb, self.sim.hp, self.sim.coins, self.sim.score, self.sim.paused, self.sim.won,
            room_idx=self.sim.room_idx, boss_hp=self.sim.boss_hp,
            banner=self.sim.banner_msg, dialogue=self.sim.dialog_text,
            var0=self.sim.vars[0] if self.sim.vars else 0,
            minimap_rooms=mrooms,
            script_mode=self.sim.is_script_mode(),
        )

    def _on_hw_flags_changed(self) -> None:
        if not self.project:
            return
        self.project.sram_save_enabled = self.cb_sram.isChecked()
        self.project.alpha_blend_enabled = self.cb_alpha.isChecked()
        self.projectModified.emit("Update GBA Hardware Flags")

    def _on_header_edited(self) -> None:
        if not self.project:
            return
        self.project.title = self.ed_title.text().upper()[:12] or "UNTITLED"
        self.project.game_code = self.ed_code.text().upper()[:4] or "KPIX"
        self.project.maker_code = self.ed_maker.text().upper()[:2] or "KP"
        self.projectModified.emit("Edit ROM Header")

    def _on_target_changed(self) -> None:
        if not self.project:
            return
        self.project.target_system = str(self.cmb_target.currentData())
        self.reset_playtest()
        self.projectModified.emit(f"Switch Target ({self.project.target_system})")

    def build_gba_dialog(self, default_path: Optional[str] = None) -> Optional[BuildReport]:
        if not self.project:
            return None
        safe_name = "".join(c if c.isalnum() else "_" for c in self.project.title.lower()).strip("_") or "game"
        if default_path:
            out_path = default_path
        else:
            out_path, _ = QFileDialog.getSaveFileName(self, "Build Playable GBA ROM", f"{safe_name}.gba", "Game Boy Advance ROM (*.gba)")
        if not out_path:
            return None
        if not out_path.lower().endswith(".gba"):
            out_path += ".gba"
        try:
            rep = compile_gba_rom(self.project, out_path)
            self._last_output_path = out_path
            self._log_report(rep)
            self.romBuilt.emit(rep)
            return rep
        except Exception as exc:
            self.log.appendPlainText(f"[ERROR] Build failed: {exc}")
            QMessageBox.critical(self, "ROM Build Error", str(exc))
            return None

    def build_gb_dialog(self) -> Optional[BuildReport]:
        if not self.project:
            return None
        ext = ".gbc" if self.project.target_system == "GBC" else ".gb"
        safe_name = "".join(c if c.isalnum() else "_" for c in self.project.title.lower()).strip("_") or "game"
        out_path, _ = QFileDialog.getSaveFileName(self, "Export Native GB/GBC ROM", f"{safe_name}{ext}", "Game Boy ROM (*.gb *.gbc)")
        if not out_path:
            return None
        rep = compile_gb_rom(self.project, out_path)
        self._last_output_path = out_path
        self._log_report(rep)
        self.romBuilt.emit(rep)
        return rep

    def export_c_dialog(self) -> None:
        if not self.project:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select Folder for C Assets Header")
        if not out_dir:
            return
        p = export_c_source(self.project, out_dir)
        self.log.appendPlainText(f"[EXPORT] Wrote C header: {p}")

    def _log_report(self, rep: BuildReport) -> None:
        self.log.clear()
        self.log.appendPlainText("================================================")
        self.log.appendPlainText(f"  KINOPIXEL CARTRIDGE BUILD SUCCEEDED")
        self.log.appendPlainText("================================================")
        self.log.appendPlainText(f"Format       : {rep.format_name}")
        self.log.appendPlainText(f"Output File  : {rep.output_path}")
        self.log.appendPlainText(f"ROM Size     : {rep.rom_size:,} bytes ({rep.rom_size // 1024} KB)")
        self.log.appendPlainText(f"ROM Title    : {rep.title}")
        self.log.appendPlainText(f"Header Check : {rep.checksum_hex} (Nintendo Logo VERIFIED)")
        self.log.appendPlainText(f"BG Tiles     : {rep.bg_tiles}")
        self.log.appendPlainText(f"OBJ Tiles    : {rep.obj_tiles}")
        self.log.appendPlainText(f"Button Rules : {rep.rules_compiled} wired hardware actions")
        self.log.appendPlainText(f"Enemies      : {rep.enemies_compiled} active patrol slots")
        self.log.appendPlainText(f"PSG Chiptune : {rep.sfx_compiled} hardware SFX patches")
        for w in rep.warnings:
            self.log.appendPlainText(f"Note         : {w}")
        self.log.appendPlainText("Ready to play in mGBA, VisualBoyAdvance-M, RetroArch, or real GBA hardware!")
