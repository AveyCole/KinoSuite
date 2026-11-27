"""Sequence Genie Interactive Chiptune Composer Panel for KinoPixel.

Provides the 16-step Piano Roll (Hit/Rest, Pitch, Lock, Chance, Repeat, Gate),
19 Sequence Genie scales, Swing 50-75%, 8 Phrase Slots, Chord Genie progression
controls, 4 Euclidean chiptune drum lanes, live loop playback, WAV bounce, and
direct .gba ROM hardware BGM embedding.
"""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .models import KinoPixelProject
from .sequence_genie import (
    CHORD_DIRS,
    CHORD_STYLES,
    GENIE_SCALES,
    GRID_MODES,
    GenieLoopPlayer,
    NOTE_NAMES,
    SequenceGenieData,
    build_scale_pool,
    export_genie_wav,
    midi_to_name,
    mutate_phrase,
    reroll_chord_progression,
    reroll_phrase,
)


class GeniePianoRollWidget(QWidget):
    """Interactive 16-step Sequence Genie Piano Roll with Pitch, Hit/Rest, Lock, Chance & Repeat badges."""
    stepSelected = Signal(int)
    phraseEdited = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.genie: Optional[SequenceGenieData] = None
        self.selected_step: int = 0
        self.setMinimumHeight(185)
        self.setToolTip("Left-click column to set note & activate | Double-click to toggle Hit/Rest | Right-click to toggle Step Lock")

    def set_genie(self, genie: SequenceGenieData) -> None:
        self.genie = genie
        self.update()

    def _pool(self) -> List[int]:
        if not self.genie:
            return [60, 62, 64, 65, 67, 69, 71, 72]
        p = build_scale_pool(self.genie.root, self.genie.scale, self.genie.octave, self.genie.octave_span)
        return p[:14] if len(p) > 14 else p

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.genie:
            return
        left_m = 42
        w = max(1, self.width() - left_m - 8)
        col_w = w / 16.0
        step = int((event.position().x() - left_m) // col_w)
        if not (0 <= step < 16):
            return
        self.selected_step = step
        self.stepSelected.emit(step)
        st = self.genie.steps[step]

        if event.button() == Qt.MouseButton.RightButton:
            st.locked = not st.locked
            self.phraseEdited.emit("Toggle Step Lock")
            self.update()
            return

        pool = self._pool()
        rows = len(pool)
        top_m = 20
        bot_m = 24
        grid_h = max(1, self.height() - top_m - bot_m)
        ry = event.position().y() - top_m
        if 0 <= ry <= grid_h and rows > 0:
            row_idx = int((ry / grid_h) * rows)
            row_idx = max(0, min(rows - 1, row_idx))
            chosen_note = pool[rows - 1 - row_idx]
            if st.active and st.note == chosen_note:
                st.active = False
            else:
                st.active = True
                st.note = chosen_note
            self.phraseEdited.emit("Edit Piano Roll Step")
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0E1118"))
        if not self.genie:
            p.end()
            return

        pool = self._pool()
        rows = max(1, len(pool))
        left_m = 42
        top_m = 20
        bot_m = 24
        gw = max(16, self.width() - left_m - 8)
        gh = max(16, self.height() - top_m - bot_m)
        cw = gw / 16.0
        rh = gh / float(rows)

        # Beat header bar (1..16)
        p.setFont(QFont("Consolas", 7.5, QFont.Weight.Bold))
        for i in range(16):
            x = int(left_m + i * cw)
            w = max(1, int(cw))
            if i == self.selected_step:
                p.fillRect(QRect(x, 2, w, top_m - 3), QColor("#3A256E"))
            elif (i // 4) % 2 == 0:
                p.fillRect(QRect(x, 2, w, top_m - 3), QColor("#171C28"))
            p.setPen(QColor("#C4B5FD") if i == self.selected_step else (QColor("#E6EAF2") if i % 4 == 0 else QColor("#64748B")))
            p.drawText(QRect(x, 2, w, top_m - 3), Qt.AlignmentFlag.AlignCenter, str(i + 1))

        # Horizontal scale rows & note labels
        for r_idx in range(rows):
            note = pool[rows - 1 - r_idx]
            y = int(top_m + r_idx * rh)
            h = max(1, int(rh))
            if r_idx % 2 == 0:
                p.fillRect(QRect(left_m, y, gw, h), QColor("#131722"))
            p.setPen(QColor("#1E2536"))
            p.drawLine(left_m, y, left_m + gw, y)
            if rows <= 12 or r_idx % 2 == 0:
                p.setPen(QColor("#8D99AE"))
                p.setFont(QFont("Consolas", 7))
                p.drawText(QRect(2, y, left_m - 6, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, midi_to_name(note))

        # Vertical step columns & active step notes
        for i, st in enumerate(self.genie.steps):
            x = int(left_m + i * cw)
            w = max(2, int(cw) - 2)
            p.setPen(QColor("#2F3950") if i % 4 == 0 else QColor("#1C2232"))
            p.drawLine(x, top_m, x, top_m + gh)

            if i == self.selected_step:
                p.fillRect(QRect(x + 1, top_m, w, gh), QColor(139, 92, 246, 30))

            if st.active:
                nearest = min(range(rows), key=lambda idx: abs(pool[idx] - st.note))
                r_idx = rows - 1 - nearest
                ny = int(top_m + r_idx * rh) + 1
                nh = max(4, int(rh) - 2)
                col = QColor("#F59E0B") if st.locked else (QColor("#8B5CF6") if st.chance == 100 else QColor("#38BDF8"))
                p.fillRect(QRect(x + 2, ny, max(2, w - 2), nh), col)
                p.setPen(QPen(QColor("#FFFFFF"), 1))
                p.drawRect(QRect(x + 2, ny, max(2, w - 2), nh))
                if st.repeat > 1:
                    p.setFont(QFont("Segoe UI", 6.5, QFont.Weight.Bold))
                    p.setPen(QColor("#081018"))
                    p.drawText(QRect(x + 2, ny, max(2, w - 2), nh), Qt.AlignmentFlag.AlignCenter, f"{st.repeat}x")

            # Bottom step badges: Lock / Chance
            by = top_m + gh + 3
            p.setFont(QFont("Segoe UI", 6.5, QFont.Weight.Bold))
            if st.locked:
                p.setPen(QColor("#F59E0B"))
                p.drawText(QRect(x, by, w, 18), Qt.AlignmentFlag.AlignCenter, "LCK")
            elif st.active and st.chance < 100:
                p.setPen(QColor("#38BDF8"))
                p.drawText(QRect(x, by, w, 18), Qt.AlignmentFlag.AlignCenter, f"{st.chance}%")

        p.setPen(QPen(QColor("#2A3242"), 1))
        p.drawRect(left_m, top_m, gw, gh)
        p.end()


class SequenceGeniePanel(QWidget):
    """Full Sequence Genie Chiptune Composer Panel (Lead + Chord Genie + Euclidean Drums + 8 Slots)."""
    projectModified = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project: Optional[KinoPixelProject] = None
        self.player = GenieLoopPlayer()
        self.selected_step: int = 0
        self._loading = False
        self._drum_dots: List[QLabel] = []
        self._slot_recall_btns: List[QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        host = QWidget()
        host.setObjectName("ScrollContent")
        scroll.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # --- Top Transport & Generative Action Bar ---
        tbar = QWidget()
        tbar.setObjectName("ControlBar")
        tl = QHBoxLayout(tbar)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(8)

        self.btn_play = QPushButton("▶  Play Sequence Genie")
        self.btn_play.setObjectName("PlayButton")
        self.btn_play.clicked.connect(self._toggle_play)
        tl.addWidget(self.btn_play)

        b_reroll = QPushButton("Reroll Phrase")
        b_reroll.setObjectName("PrimaryButton")
        b_reroll.clicked.connect(self._on_reroll)
        tl.addWidget(b_reroll)

        b_mut = QPushButton("Mutate")
        b_mut.setObjectName("KinoAccentButton")
        b_mut.clicked.connect(self._on_mutate)
        tl.addWidget(b_mut)

        b_prog = QPushButton("Prog Reroll")
        b_prog.clicked.connect(self._on_prog_reroll)
        tl.addWidget(b_prog)

        b_wav = QPushButton("Bounce WAV (KinoWave)...")
        b_wav.clicked.connect(self._on_bounce_wav)
        tl.addWidget(b_wav)

        tl.addStretch(1)
        self.cb_rom_bgm = QCheckBox("Embed as .gba ROM Soundtrack")
        self.cb_rom_bgm.setChecked(True)
        self.cb_rom_bgm.toggled.connect(self._on_param_changed)
        tl.addWidget(self.cb_rom_bgm)
        root.addWidget(tbar)

        # --- Row 1: Sequence Genie Setup + Chord Genie ---
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Sequence Setup Box
        setup_box = QGroupBox("Sequence Genie Setup (19 REDUX Scales · Swing · Groove)")
        sg = QGridLayout(setup_box)
        sg.setHorizontalSpacing(8)
        sg.setVerticalSpacing(6)

        sg.addWidget(QLabel("Root:"), 0, 0)
        self.cmb_root = QComboBox()
        for i, n in enumerate(NOTE_NAMES):
            self.cmb_root.addItem(n, i)
        self.cmb_root.currentIndexChanged.connect(self._on_param_changed)
        sg.addWidget(self.cmb_root, 0, 1)

        sg.addWidget(QLabel("Scale:"), 0, 2)
        self.cmb_scale = QComboBox()
        for sname, _ in GENIE_SCALES:
            self.cmb_scale.addItem(sname, sname)
        self.cmb_scale.currentIndexChanged.connect(self._on_param_changed)
        sg.addWidget(self.cmb_scale, 0, 3)

        sg.addWidget(QLabel("BPM:"), 0, 4)
        self.sp_bpm = QSpinBox()
        self.sp_bpm.setRange(60, 220)
        self.sp_bpm.setValue(132)
        self.sp_bpm.valueChanged.connect(self._on_param_changed)
        sg.addWidget(self.sp_bpm, 0, 5)

        sg.addWidget(QLabel("Swing:"), 1, 0)
        self.sp_swing = QSpinBox()
        self.sp_swing.setRange(50, 75)
        self.sp_swing.setSuffix("%")
        self.sp_swing.setValue(54)
        self.sp_swing.valueChanged.connect(self._on_param_changed)
        sg.addWidget(self.sp_swing, 1, 1)

        sg.addWidget(QLabel("Grid:"), 1, 2)
        self.cmb_grid = QComboBox()
        self.cmb_grid.addItems(GRID_MODES)
        self.cmb_grid.currentIndexChanged.connect(self._on_param_changed)
        sg.addWidget(self.cmb_grid, 1, 3)

        sg.addWidget(QLabel("Density:"), 1, 4)
        self.sp_density = QSpinBox()
        self.sp_density.setRange(15, 100)
        self.sp_density.setSuffix("%")
        self.sp_density.setValue(68)
        self.sp_density.valueChanged.connect(self._on_param_changed)
        sg.addWidget(self.sp_density, 1, 5)

        sg.addWidget(QLabel("Octave:"), 2, 0)
        self.sp_oct = QSpinBox()
        self.sp_oct.setRange(3, 6)
        self.sp_oct.setValue(4)
        self.sp_oct.valueChanged.connect(self._on_param_changed)
        sg.addWidget(self.sp_oct, 2, 1)

        sg.addWidget(QLabel("Duty:"), 2, 2)
        self.cmb_duty = QComboBox()
        for i, d in enumerate(["12.5% Thin", "25% Retro Lead", "50% Square", "75% Hollow"]):
            self.cmb_duty.addItem(d, i)
        self.cmb_duty.currentIndexChanged.connect(self._on_param_changed)
        sg.addWidget(self.cmb_duty, 2, 3)

        sg.addWidget(QLabel("Span:"), 2, 4)
        self.sp_span = QSpinBox()
        self.sp_span.setRange(1, 3)
        self.sp_span.setSuffix(" oct")
        self.sp_span.setValue(2)
        self.sp_span.valueChanged.connect(self._on_param_changed)
        sg.addWidget(self.sp_span, 2, 5)
        top_row.addWidget(setup_box, 3)

        # Chord Genie Box
        chord_box = QGroupBox("Chord Genie (Diatonic Progressions · Strum · Wave Bass)")
        cg = QGridLayout(chord_box)
        cg.setHorizontalSpacing(8)
        cg.setVerticalSpacing(6)

        cg.addWidget(QLabel("Style:"), 0, 0)
        self.cmb_ch_style = QComboBox()
        self.cmb_ch_style.addItems(CHORD_STYLES)
        self.cmb_ch_style.currentIndexChanged.connect(self._on_param_changed)
        cg.addWidget(self.cmb_ch_style, 0, 1)

        cg.addWidget(QLabel("Dir:"), 0, 2)
        self.cmb_ch_dir = QComboBox()
        self.cmb_ch_dir.addItems(CHORD_DIRS)
        self.cmb_ch_dir.currentIndexChanged.connect(self._on_param_changed)
        cg.addWidget(self.cmb_ch_dir, 0, 3)

        cg.addWidget(QLabel("Strum:"), 1, 0)
        self.sp_strum = QSpinBox()
        self.sp_strum.setRange(0, 120)
        self.sp_strum.setSuffix(" ms")
        self.sp_strum.valueChanged.connect(self._on_param_changed)
        cg.addWidget(self.sp_strum, 1, 1)

        cg.addWidget(QLabel("Prog Bars:"), 1, 2)
        self.cmb_ch_bars = QComboBox()
        self.cmb_ch_bars.addItem("4 Bars", 4)
        self.cmb_ch_bars.addItem("8 Bars", 8)
        self.cmb_ch_bars.currentIndexChanged.connect(self._on_param_changed)
        cg.addWidget(self.cmb_ch_bars, 1, 3)

        self.cb_bass = QCheckBox("4-Bit Wave Channel Bass")
        self.cb_bass.setChecked(True)
        self.cb_bass.toggled.connect(self._on_param_changed)
        cg.addWidget(self.cb_bass, 2, 0, 1, 2)

        self.lbl_prog = QLabel("Prog: I - IV - V - III")
        self.lbl_prog.setStyleSheet("color:#34D399; font-family:Consolas; font-weight:700;")
        cg.addWidget(self.lbl_prog, 2, 2, 1, 2)
        top_row.addWidget(chord_box, 2)
        root.addLayout(top_row)

        # --- Row 2: Interactive 16-Step Piano Roll + Step Inspector ---
        pr_box = QGroupBox("Sequence Genie Piano Roll (Left-Click: Paint Note · Right-Click: Lock Step)")
        prl = QVBoxLayout(pr_box)
        self.piano_roll = GeniePianoRollWidget()
        self.piano_roll.stepSelected.connect(self._on_step_selected)
        self.piano_roll.phraseEdited.connect(self._on_phrase_edited)
        prl.addWidget(self.piano_roll)

        srow = QHBoxLayout()
        self.lbl_step = QLabel("Step 1:")
        self.lbl_step.setStyleSheet("color:#A78BFA; font-weight:700;")
        srow.addWidget(self.lbl_step)

        self.cb_st_hit = QCheckBox("Hit")
        self.cb_st_hit.toggled.connect(self._apply_step_edit)
        srow.addWidget(self.cb_st_hit)

        self.cb_st_lock = QCheckBox("Lock")
        self.cb_st_lock.toggled.connect(self._apply_step_edit)
        srow.addWidget(self.cb_st_lock)

        srow.addWidget(QLabel("Note:"))
        self.sp_st_note = QSpinBox()
        self.sp_st_note.setRange(36, 96)
        self.sp_st_note.valueChanged.connect(self._apply_step_edit)
        srow.addWidget(self.sp_st_note)

        srow.addWidget(QLabel("Chance:"))
        self.sp_st_chance = QSpinBox()
        self.sp_st_chance.setRange(0, 100)
        self.sp_st_chance.setSingleStep(5)
        self.sp_st_chance.setSuffix("%")
        self.sp_st_chance.valueChanged.connect(self._apply_step_edit)
        srow.addWidget(self.sp_st_chance)

        srow.addWidget(QLabel("Repeat:"))
        self.sp_st_rep = QSpinBox()
        self.sp_st_rep.setRange(1, 4)
        self.sp_st_rep.setSuffix("x")
        self.sp_st_rep.valueChanged.connect(self._apply_step_edit)
        srow.addWidget(self.sp_st_rep)

        srow.addWidget(QLabel("Gate:"))
        self.sp_st_gate = QSpinBox()
        self.sp_st_gate.setRange(15, 100)
        self.sp_st_gate.setSingleStep(5)
        self.sp_st_gate.setSuffix("%")
        self.sp_st_gate.valueChanged.connect(self._apply_step_edit)
        srow.addWidget(self.sp_st_gate)
        srow.addStretch(1)
        prl.addLayout(srow)
        root.addWidget(pr_box)

        # --- Row 3: Euclidean Drum Lanes + 8 Phrase Slots ---
        bot_row = QHBoxLayout()
        bot_row.setSpacing(8)

        drum_box = QGroupBox("Euclidean Drum Genie Lanes (Hits + Rotate)")
        self.drum_grid = QGridLayout(drum_box)
        self.drum_grid.setHorizontalSpacing(8)
        self.drum_grid.setVerticalSpacing(5)
        self._drum_widgets: List[tuple] = []
        for idx, dname in enumerate(["Kick", "Snare", "Hi-Hat", "Perc / Rim"]):
            cb = QCheckBox(dname)
            cb.setChecked(True)
            cb.toggled.connect(lambda _=False, i=idx: self._on_drum_edited(i))
            sp_h = QSpinBox()
            sp_h.setRange(0, 16)
            sp_h.setPrefix("Hits ")
            sp_h.valueChanged.connect(lambda _=0, i=idx: self._on_drum_edited(i))
            sp_r = QSpinBox()
            sp_r.setRange(0, 15)
            sp_r.setPrefix("Rot ")
            sp_r.valueChanged.connect(lambda _=0, i=idx: self._on_drum_edited(i))
            lbl_pat = QLabel("●···●···●···●···")
            lbl_pat.setStyleSheet("font-family:Consolas; color:#34D399; font-size:9.5pt;")
            self.drum_grid.addWidget(cb, idx, 0)
            self.drum_grid.addWidget(sp_h, idx, 1)
            self.drum_grid.addWidget(sp_r, idx, 2)
            self.drum_grid.addWidget(lbl_pat, idx, 3)
            self._drum_widgets.append((cb, sp_h, sp_r, lbl_pat))
        bot_row.addWidget(drum_box, 3)

        slot_box = QGroupBox("8 Phrase Slots (Save / Recall)")
        slg = QGridLayout(slot_box)
        slg.setSpacing(5)
        for s_idx in range(8):
            r = s_idx // 4
            c = (s_idx % 4) * 2
            b_rec = QPushButton(f"S{s_idx + 1}")
            b_rec.setToolTip(f"Recall Phrase Slot {s_idx + 1}")
            b_rec.clicked.connect(lambda _=False, si=s_idx: self._recall_slot(si))
            b_sav = QPushButton("Save")
            b_sav.setFixedWidth(44)
            b_sav.clicked.connect(lambda _=False, si=s_idx: self._save_slot(si))
            slg.addWidget(b_rec, r, c)
            slg.addWidget(b_sav, r, c + 1)
            self._slot_recall_btns.append(b_rec)
        bot_row.addWidget(slot_box, 2)
        root.addLayout(bot_row)

    def set_project(self, proj: KinoPixelProject) -> None:
        self.stop_audio()
        self.project = proj
        self.project.sequence_genie.ensure_initialized()
        self.refresh_all()

    def stop_audio(self) -> None:
        self.player.stop()
        self.btn_play.setText("▶  Play Sequence Genie")

    def _genie(self) -> Optional[SequenceGenieData]:
        return self.project.sequence_genie if self.project else None

    def refresh_all(self) -> None:
        g = self._genie()
        if not g:
            return
        self._loading = True
        self.cb_rom_bgm.setChecked(g.enabled_in_rom)
        self.cmb_root.setCurrentIndex(g.root % 12)
        si = self.cmb_scale.findData(g.scale)
        if si >= 0:
            self.cmb_scale.setCurrentIndex(si)
        self.sp_bpm.setValue(g.bpm)
        self.sp_swing.setValue(g.swing)
        self.cmb_grid.setCurrentText(g.grid_mode)
        self.sp_density.setValue(g.density)
        self.sp_oct.setValue(g.octave)
        self.cmb_duty.setCurrentIndex(g.lead_duty & 3)
        self.sp_span.setValue(g.octave_span)
        self.cmb_ch_style.setCurrentText(g.chord_style)
        self.cmb_ch_dir.setCurrentText(g.chord_dir)
        self.sp_strum.setValue(g.chord_strum_ms)
        self.cmb_ch_bars.setCurrentIndex(1 if g.chord_bars == 8 else 0)
        self.cb_bass.setChecked(g.bass_enabled)

        romans = ["I", "II", "III", "IV", "V", "VI", "VII"]
        prog_str = " - ".join(romans[d % 7] for d in g.chord_degrees)
        self.lbl_prog.setText(f"Prog: {prog_str}")

        for idx, (cb, sp_h, sp_r, lbl_pat) in enumerate(self._drum_widgets):
            if idx < len(g.drum_lanes):
                dl = g.drum_lanes[idx]
                cb.setChecked(dl.enabled)
                sp_h.setValue(dl.hits)
                sp_r.setValue(dl.rotate)
                pat = dl.pattern(16)
                lbl_pat.setText("".join("●" if hit else "·" for hit in pat))

        for s_idx, b in enumerate(self._slot_recall_btns):
            has = g.phrase_slots[s_idx] is not None
            b.setText(f"★ S{s_idx + 1}" if has else f"S{s_idx + 1}")

        self.piano_roll.set_genie(g)
        self._loading = False
        self._load_step_fields(self.selected_step)

    def _load_step_fields(self, step: int) -> None:
        g = self._genie()
        if not g or not (0 <= step < 16):
            return
        self._loading = True
        st = g.steps[step]
        self.lbl_step.setText(f"Step {step + 1} ({midi_to_name(st.note)}):")
        self.cb_st_hit.setChecked(st.active)
        self.cb_st_lock.setChecked(st.locked)
        self.sp_st_note.setValue(st.note)
        self.sp_st_chance.setValue(st.chance)
        self.sp_st_rep.setValue(st.repeat)
        self.sp_st_gate.setValue(st.gate)
        self._loading = False

    def _on_step_selected(self, step: int) -> None:
        self.selected_step = step
        self._load_step_fields(step)

    def _on_phrase_edited(self, label: str) -> None:
        self._load_step_fields(self.selected_step)
        self.projectModified.emit(label)

    def _apply_step_edit(self) -> None:
        if self._loading:
            return
        g = self._genie()
        if not g:
            return
        st = g.steps[self.selected_step]
        st.active = self.cb_st_hit.isChecked()
        st.locked = self.cb_st_lock.isChecked()
        st.note = self.sp_st_note.value()
        st.chance = self.sp_st_chance.value()
        st.repeat = self.sp_st_rep.value()
        st.gate = self.sp_st_gate.value()
        self.lbl_step.setText(f"Step {self.selected_step + 1} ({midi_to_name(st.note)}):")
        self.piano_roll.update()
        self.projectModified.emit("Edit Genie Step")

    def _on_param_changed(self) -> None:
        if self._loading:
            return
        g = self._genie()
        if not g:
            return
        g.enabled_in_rom = self.cb_rom_bgm.isChecked()
        g.root = int(self.cmb_root.currentData())
        g.scale = str(self.cmb_scale.currentData())
        g.bpm = self.sp_bpm.value()
        g.swing = self.sp_swing.value()
        g.grid_mode = self.cmb_grid.currentText()
        g.density = self.sp_density.value()
        g.octave = self.sp_oct.value()
        g.lead_duty = int(self.cmb_duty.currentData())
        g.octave_span = self.sp_span.value()
        g.chord_style = self.cmb_ch_style.currentText()
        g.chord_dir = self.cmb_ch_dir.currentText()
        g.chord_strum_ms = self.sp_strum.value()
        g.chord_bars = int(self.cmb_ch_bars.currentData())
        g.bass_enabled = self.cb_bass.isChecked()
        self.piano_roll.update()
        self.projectModified.emit("Update Sequence Genie Settings")

    def _on_drum_edited(self, idx: int) -> None:
        if self._loading:
            return
        g = self._genie()
        if not g or idx >= len(g.drum_lanes):
            return
        cb, sp_h, sp_r, lbl_pat = self._drum_widgets[idx]
        dl = g.drum_lanes[idx]
        dl.enabled = cb.isChecked()
        dl.hits = sp_h.value()
        dl.rotate = sp_r.value()
        lbl_pat.setText("".join("●" if hit else "·" for hit in dl.pattern(16)))
        self.projectModified.emit("Edit Euclidean Drum Lane")

    def _on_reroll(self) -> None:
        g = self._genie()
        if not g:
            return
        reroll_phrase(g)
        self.refresh_all()
        self.projectModified.emit("Sequence Genie Reroll Phrase")
        if self.player.playing:
            self.player.start(g)

    def _on_mutate(self) -> None:
        g = self._genie()
        if not g:
            return
        mutate_phrase(g)
        self.refresh_all()
        self.projectModified.emit("Sequence Genie Mutate")
        if self.player.playing:
            self.player.start(g)

    def _on_prog_reroll(self) -> None:
        g = self._genie()
        if not g:
            return
        reroll_chord_progression(g)
        self.refresh_all()
        self.projectModified.emit("Chord Genie Prog Reroll")
        if self.player.playing:
            self.player.start(g)

    def _save_slot(self, idx: int) -> None:
        g = self._genie()
        if not g:
            return
        g.save_slot(idx)
        self.refresh_all()
        self.projectModified.emit(f"Save Phrase Slot {idx + 1}")

    def _recall_slot(self, idx: int) -> None:
        g = self._genie()
        if g and g.recall_slot(idx):
            self.refresh_all()
            self.projectModified.emit(f"Recall Phrase Slot {idx + 1}")
            if self.player.playing:
                self.player.start(g)

    def _toggle_play(self) -> None:
        g = self._genie()
        if not g:
            return
        if self.player.playing:
            self.stop_audio()
        else:
            self.player.start(g)
            self.btn_play.setText("■  Stop Sequence Genie")

    def _on_bounce_wav(self) -> None:
        g = self._genie()
        if not g or not self.project:
            return
        safe = "".join(c if c.isalnum() else "_" for c in self.project.title.lower()).strip("_") or "chiptune"
        fp, _ = QFileDialog.getSaveFileName(self, "Bounce Sequence Genie Chiptune WAV", f"{safe}_bgm.wav", "WAV Audio (*.wav)")
        if fp:
            if not fp.lower().endswith(".wav"):
                fp += ".wav"
            export_genie_wav(g, fp, bars=max(2, g.chord_bars))
            QMessageBox.information(self, "Bounced Chiptune WAV", f"Exported Sequence Genie soundtrack to:\n{fp}\n\nYou can also open this WAV directly in KinoWave!")
