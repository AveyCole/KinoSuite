"""KinoSuite Dark, Studio Light & High-Contrast themes for KinoWave.

Shares the KinoSuite / KinoCut / KinoShop sleek deep-slate architectural design
philosophy (#12151C base, #181C25 panels, #222836 controls, #2A3242 hairlines)
paired with KinoWave's signature acoustic emerald-cyan (#10D9A0 / #22D3EE)
accent, crimson record/clipping indicators (#F43F5E), and amber peak markers (#F59E0B).
"""
from __future__ import annotations

from typing import Dict

# Semantic palette tokens used by custom-painted audio widgets (waveforms, meters, rulers)
PALETTES: Dict[str, Dict[str, str]] = {
    "Dark": {
        "bg_base": "#12151C",
        "bg_panel": "#181C25",
        "bg_track": "#10141B",
        "bg_track_alt": "#131822",
        "bg_clip": "#151D2B",
        "bg_clip_header": "#1D2738",
        "bg_ruler": "#161B24",
        "bg_selection": "#10D9A033",
        "bg_spectral_sel": "#22D3EE3A",
        "border": "#2A3242",
        "border_strong": "#3B475E",
        "grid_major": "#2B3446",
        "grid_minor": "#1D2432",
        "center_line": "#2B364A",
        "text": "#E6EAF2",
        "text_muted": "#8D99AE",
        "accent": "#10D9A0",
        "accent_alt": "#22D3EE",
        "wave_peak": "#10D9A0",
        "wave_rms": "#22D3EE",
        "wave_outline": "#5EF2C8",
        "clip_red": "#F43F5E",
        "record_red": "#EF4444",
        "playhead": "#38BDF8",
        "cursor": "#F8FAFC",
        "loop_bar": "#F59E0B",
        "envelope": "#A78BFA",
        "label_fill": "#1F293B",
        "label_border": "#38BDF8",
        "midi_note": "#10D9A0",
        "time_curve": "#F59E0B",
    },
    "Light": {
        "bg_base": "#EEF1F6",
        "bg_panel": "#F4F6FA",
        "bg_track": "#FFFFFF",
        "bg_track_alt": "#F8FAFC",
        "bg_clip": "#EFF6FF",
        "bg_clip_header": "#DCE7F5",
        "bg_ruler": "#E6EAF2",
        "bg_selection": "#05966930",
        "bg_spectral_sel": "#0284C735",
        "border": "#CBD5E1",
        "border_strong": "#94A3B8",
        "grid_major": "#CBD5E1",
        "grid_minor": "#E2E8F0",
        "center_line": "#CBD5E1",
        "text": "#1A202C",
        "text_muted": "#64748B",
        "accent": "#059669",
        "accent_alt": "#0284C7",
        "wave_peak": "#059669",
        "wave_rms": "#0284C7",
        "wave_outline": "#047857",
        "clip_red": "#DC2626",
        "record_red": "#DC2626",
        "playhead": "#0284C7",
        "cursor": "#0F172A",
        "loop_bar": "#D97706",
        "envelope": "#7C3AED",
        "label_fill": "#E0F2FE",
        "label_border": "#0284C7",
        "midi_note": "#059669",
        "time_curve": "#D97706",
    },
    "High Contrast": {
        "bg_base": "#000000",
        "bg_panel": "#000000",
        "bg_track": "#000000",
        "bg_track_alt": "#0A0A0A",
        "bg_clip": "#00141A",
        "bg_clip_header": "#1A1A00",
        "bg_ruler": "#000000",
        "bg_selection": "#FFFF0055",
        "bg_spectral_sel": "#00FFFF55",
        "border": "#FFFFFF",
        "border_strong": "#FFFF00",
        "grid_major": "#808080",
        "grid_minor": "#404040",
        "center_line": "#808080",
        "text": "#FFFFFF",
        "text_muted": "#FFFF00",
        "accent": "#00FFCC",
        "accent_alt": "#FFFF00",
        "wave_peak": "#00FFCC",
        "wave_rms": "#FFFF00",
        "wave_outline": "#FFFFFF",
        "clip_red": "#FF3333",
        "record_red": "#FF2222",
        "playhead": "#FFFF00",
        "cursor": "#FFFFFF",
        "loop_bar": "#FFFF00",
        "envelope": "#FF66FF",
        "label_fill": "#000000",
        "label_border": "#FFFF00",
        "midi_note": "#00FFCC",
        "time_curve": "#FFFF00",
    },
}

KINOWAVE_DARK_THEME = """
QMainWindow, QDialog {
    background-color: #12151C;
    color: #E6EAF2;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9pt;
}
QWidget {
    color: #E6EAF2;
    background-color: transparent;
}
QScrollArea {
    background-color: #181C25;
    border: none;
}
QScrollArea > QWidget > QWidget, QWidget#ScrollContent {
    background-color: #181C25;
}
QLabel {
    background-color: transparent;
    color: #DCE2EE;
}
QMenuBar {
    background-color: #161A22;
    color: #DCE2EE;
    border-bottom: 1px solid #262D3B;
    padding: 2px 6px;
}
QMenuBar::item {
    padding: 4px 9px;
    border-radius: 5px;
    background: transparent;
}
QMenuBar::item:selected {
    background-color: #252C3A;
    color: #10D9A0;
}
QMenu {
    background-color: #1B202B;
    color: #E6EAF2;
    border: 1px solid #30384A;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 5px 26px 5px 14px;
    border-radius: 5px;
}
QMenu::item:selected {
    background-color: #10D9A0;
    color: #0B1218;
    font-weight: 600;
}
QMenu::separator {
    height: 1px;
    background: #2C3445;
    margin: 4px 8px;
}
QToolBar {
    background-color: #171B24;
    border-bottom: 1px solid #283040;
    spacing: 4px;
    padding: 3px 6px;
}
QToolBar::separator {
    width: 1px;
    background: #2A3242;
    margin: 4px 4px;
}
QDockWidget {
    color: #DCE2EE;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background-color: #1A1F29;
    border: 1px solid #2A3242;
    padding: 5px 8px;
    font-weight: 600;
    color: #10D9A0;
}
QWidget#ControlBar, QWidget#SelectionBar {
    background-color: #1A1F29;
    border-top: 1px solid #2A3242;
    border-bottom: 1px solid #2A3242;
}
QWidget#StudioPanel {
    background-color: #181C25;
    border-left: 1px solid #283040;
}
QToolButton {
    background-color: transparent;
    color: #DCE2EE;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px;
}
QToolButton:hover {
    background-color: #252C3B;
    border-color: #364056;
}
QToolButton:checked {
    background-color: #0E2F29;
    border: 1px solid #10D9A0;
    color: #10D9A0;
}
QToolButton#RecordButton:checked {
    background-color: #45151E;
    border: 1px solid #F43F5E;
    color: #FDA4AF;
}
QPushButton {
    background-color: #222836;
    color: #E6EAF2;
    border: 1px solid #343D52;
    border-radius: 6px;
    padding: 5px 11px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #2B3345;
    border-color: #495672;
}
QPushButton:pressed {
    background-color: #1D2330;
}
QPushButton:checked {
    background-color: #0E2F29;
    border: 1px solid #10D9A0;
    color: #10D9A0;
}
QPushButton#PrimaryButton {
    background-color: #10D9A0;
    color: #081218;
    border: 1px solid #4AF0BF;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: #2CE6B2;
}
QPushButton#KinoAccentButton {
    background-color: #0891B2;
    color: #FFFFFF;
    border: 1px solid #22D3EE;
    font-weight: 600;
}
QPushButton#KinoAccentButton:hover {
    background-color: #06B6D4;
}
QPushButton#DangerButton {
    background-color: #3B1D24;
    color: #FCA5A5;
    border: 1px solid #7F2D3A;
}
QPushButton#DangerButton:hover {
    background-color: #512530;
}
QTabWidget::pane {
    border: none;
    background: #141820;
}
QTabBar {
    background-color: #141820;
}
QTabBar::tab {
    background: #181C24;
    color: #9AA4B8;
    border: 1px solid #272F3F;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 5px 11px;
    margin-right: 2px;
    font-size: 8.5pt;
}
QTabBar::tab:selected {
    background: #232A38;
    color: #FFFFFF;
    border-top: 2px solid #10D9A0;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: #1F2532;
    color: #DCE2EE;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QTimeEdit, QDateTimeEdit {
    background-color: #10141B;
    color: #EEF2F8;
    border: 1px solid #30394C;
    border-radius: 5px;
    padding: 3px 6px;
    selection-background-color: #10D9A0;
    selection-color: #081218;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #10D9A0;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: #1B202B;
    color: #E6EAF2;
    border: 1px solid #354056;
    selection-background-color: #10D9A0;
    selection-color: #081218;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #2B3345;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #10D9A0;
    border: 1px solid #12151C;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #10D9A0;
    border-radius: 2px;
}
QSlider::groove:vertical {
    width: 4px;
    background: #2B3345;
    border-radius: 2px;
}
QSlider::handle:vertical {
    background: #10D9A0;
    border: 1px solid #12151C;
    width: 12px;
    height: 12px;
    margin: 0 -4px;
    border-radius: 6px;
}
QListWidget, QTreeWidget, QTableWidget {
    background-color: #141821;
    color: #E6EAF2;
    border: 1px solid #2A3242;
    border-radius: 6px;
    outline: none;
    gridline-color: #252D3D;
}
QListWidget::item, QTreeWidget::item {
    padding: 4px 6px;
    border-radius: 4px;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #123D34;
    color: #FFFFFF;
}
QHeaderView::section {
    background-color: #1D222D;
    color: #B4BDD0;
    border: 1px solid #2A3242;
    padding: 4px;
    font-weight: 600;
}
QGroupBox {
    font-weight: 600;
    color: #CBD5E1;
    border: 1px solid #2A3242;
    border-radius: 7px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #10D9A0;
    font-size: 8.5pt;
}
QCheckBox, QRadioButton {
    spacing: 6px;
    color: #DCE2EE;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #47536B;
    background: #10141B;
}
QCheckBox::indicator:checked {
    background: #10D9A0;
    border-color: #10D9A0;
}
QStatusBar {
    background-color: #151922;
    color: #9AA4B8;
    border-top: 1px solid #272F3F;
    font-size: 8.5pt;
}
QSplitter::handle {
    background-color: #252C3B;
    width: 2px;
    height: 2px;
}
QScrollBar:vertical {
    background: #141821;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #364056;
    border-radius: 4px;
    min-height: 26px;
}
QScrollBar::handle:vertical:hover {
    background: #4E5C7A;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #141821;
    height: 10px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #364056;
    border-radius: 4px;
    min-width: 26px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QProgressBar {
    background-color: #10141B;
    border: 1px solid #2A3242;
    border-radius: 4px;
    text-align: center;
    color: #E6EAF2;
}
QProgressBar::chunk {
    background-color: #10D9A0;
    border-radius: 3px;
}
QLabel#SuiteBadge {
    background-color: #0B2A26;
    color: #10D9A0;
    border: 1px solid #167C65;
    border-radius: 5px;
    padding: 2px 7px;
    font-weight: 700;
    font-size: 8pt;
}
QLabel#SectionHeader {
    color: #94A3B8;
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    padding-top: 4px;
}
"""

KINOWAVE_LIGHT_THEME = """
QMainWindow, QDialog {
    background-color: #EEF1F6;
    color: #1A202C;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9pt;
}
QWidget {
    color: #1A202C;
    background-color: transparent;
}
QScrollArea, QScrollArea > QWidget > QWidget, QWidget#ScrollContent {
    background-color: #F6F8FB;
}
QMenuBar {
    background-color: #E6EAF2;
    color: #1A202C;
    border-bottom: 1px solid #CBD5E1;
}
QMenuBar::item:selected {
    background-color: #D1FAE5;
    color: #047857;
}
QMenu {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
}
QMenu::item:selected {
    background-color: #059669;
    color: #FFFFFF;
}
QToolBar, QWidget#ControlBar, QWidget#SelectionBar, QWidget#StudioPanel {
    background-color: #F4F6FA;
    border: 1px solid #D3DBE8;
}
QDockWidget::title {
    background-color: #E7ECF4;
    border: 1px solid #CBD5E1;
    padding: 5px 8px;
    font-weight: 600;
    color: #047857;
}
QToolButton {
    background-color: transparent;
    color: #1A202C;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px;
}
QToolButton:hover {
    background-color: #E2E8F0;
}
QToolButton:checked {
    background-color: #D1FAE5;
    border: 1px solid #059669;
    color: #047857;
}
QPushButton {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 5px 11px;
}
QPushButton:hover {
    background-color: #EDF2F7;
}
QPushButton:checked {
    background-color: #D1FAE5;
    border: 1px solid #059669;
    color: #047857;
}
QPushButton#PrimaryButton {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    font-weight: 700;
}
QPushButton#KinoAccentButton {
    background-color: #0284C7;
    color: #FFFFFF;
    border: 1px solid #0369A1;
    font-weight: 600;
}
QPushButton#DangerButton {
    background-color: #FEE2E2;
    color: #991B1B;
    border: 1px solid #FCA5A5;
}
QTabBar::tab {
    background: #E7ECF4;
    color: #4A5568;
    border: 1px solid #CBD5E1;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 5px 11px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #047857;
    border-top: 2px solid #059669;
    font-weight: 600;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QTimeEdit, QDateTimeEdit {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 3px 6px;
}
QListWidget, QTreeWidget, QTableWidget {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #D1FAE5;
    color: #064E3B;
}
QGroupBox {
    font-weight: 600;
    color: #2D3748;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
}
QGroupBox::title {
    color: #047857;
}
QStatusBar {
    background-color: #E7ECF4;
    color: #4A5568;
    border-top: 1px solid #CBD5E1;
}
QLabel#SuiteBadge {
    background-color: #D1FAE5;
    color: #047857;
    border: 1px solid #6EE7B7;
    border-radius: 5px;
    padding: 2px 7px;
    font-weight: 700;
    font-size: 8pt;
}
QLabel#SectionHeader {
    color: #64748B;
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
}
"""

KINOWAVE_HIGH_CONTRAST_THEME = """
QMainWindow, QDialog {
    background-color: #000000;
    color: #FFFFFF;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9.5pt;
}
QWidget {
    color: #FFFFFF;
    background-color: #000000;
}
QLabel {
    color: #FFFFFF;
    background-color: transparent;
}
QMenuBar {
    background-color: #000000;
    color: #FFFFFF;
    border-bottom: 2px solid #FFFFFF;
}
QMenuBar::item:selected {
    background-color: #FFFF00;
    color: #000000;
    font-weight: 700;
}
QMenu {
    background-color: #000000;
    color: #FFFFFF;
    border: 2px solid #FFFFFF;
}
QMenu::item:selected {
    background-color: #FFFF00;
    color: #000000;
    font-weight: 700;
}
QToolBar, QWidget#ControlBar, QWidget#SelectionBar, QWidget#StudioPanel {
    background-color: #000000;
    border: 1px solid #FFFFFF;
}
QDockWidget::title {
    background-color: #000000;
    border: 2px solid #00FFCC;
    color: #FFFF00;
    font-weight: 700;
    padding: 4px 8px;
}
QToolButton, QPushButton {
    background-color: #000000;
    color: #FFFFFF;
    border: 2px solid #FFFFFF;
    border-radius: 4px;
    padding: 4px 8px;
    font-weight: 600;
}
QToolButton:hover, QPushButton:hover {
    background-color: #1A1A00;
    border-color: #FFFF00;
    color: #FFFF00;
}
QToolButton:checked, QPushButton:checked, QPushButton#PrimaryButton {
    background-color: #00FFCC;
    color: #000000;
    border: 2px solid #FFFF00;
    font-weight: 700;
}
QPushButton#DangerButton {
    background-color: #000000;
    color: #FF5555;
    border: 2px solid #FF5555;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QListWidget, QTreeWidget, QTableWidget {
    background-color: #000000;
    color: #FFFFFF;
    border: 2px solid #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPushButton:focus {
    border: 2px solid #FFFF00;
}
QTabBar::tab {
    background: #000000;
    color: #FFFFFF;
    border: 2px solid #FFFFFF;
    padding: 5px 10px;
}
QTabBar::tab:selected {
    background: #FFFF00;
    color: #000000;
    font-weight: 700;
}
QGroupBox {
    border: 2px solid #FFFFFF;
    color: #FFFF00;
    font-weight: 700;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
}
QStatusBar {
    background-color: #000000;
    color: #FFFF00;
    border-top: 2px solid #FFFFFF;
}
QLabel#SuiteBadge {
    background-color: #000000;
    color: #00FFCC;
    border: 2px solid #00FFCC;
    padding: 2px 7px;
    font-weight: 700;
}
"""

THEMES: Dict[str, str] = {
    "Dark": KINOWAVE_DARK_THEME,
    "Light": KINOWAVE_LIGHT_THEME,
    "High Contrast": KINOWAVE_HIGH_CONTRAST_THEME,
}


def get_theme_stylesheet(name: str) -> str:
    return THEMES.get(name, KINOWAVE_DARK_THEME)


def get_palette(name: str) -> Dict[str, str]:
    return PALETTES.get(name, PALETTES["Dark"])
