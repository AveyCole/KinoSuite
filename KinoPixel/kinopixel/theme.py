"""KinoSuite Dark, Studio Light & High-Contrast themes for KinoPixel.

Shares the exact KinoSuite (KinoCut / KinoShop / KinoWave) deep-slate architectural
design philosophy (#12151C base, #181C25 panels, #222836 controls, #2A3242 hairlines)
paired with KinoPixel's signature Cartridge Violet-Indigo (#8B5CF6 / #A78BFA),
Game Boy LCD Mint (#34D399), Pixel Gold (#F59E0B), and Arcade Crimson (#F43F5E).
"""
from __future__ import annotations

from typing import Dict

PALETTES: Dict[str, Dict[str, str]] = {
    "Dark": {
        "bg_base": "#12151C",
        "bg_panel": "#181C25",
        "bg_canvas": "#0E1118",
        "bg_canvas_alt": "#141925",
        "bg_card": "#1A202E",
        "bg_card_header": "#21283A",
        "border": "#2A3242",
        "border_strong": "#3B475E",
        "grid_major": "#2F3950",
        "grid_minor": "#1F2636",
        "checker_a": "#1B202C",
        "checker_b": "#232A39",
        "text": "#E6EAF2",
        "text_muted": "#8D99AE",
        "accent": "#8B5CF6",
        "accent_bright": "#A78BFA",
        "mint": "#34D399",
        "gold": "#F59E0B",
        "crimson": "#F43F5E",
        "cyan": "#22D3EE",
    },
    "Light": {
        "bg_base": "#EEF1F6",
        "bg_panel": "#F4F6FA",
        "bg_canvas": "#FFFFFF",
        "bg_canvas_alt": "#F8FAFC",
        "bg_card": "#FFFFFF",
        "bg_card_header": "#E8EBF5",
        "border": "#CBD5E1",
        "border_strong": "#94A3B8",
        "grid_major": "#CBD5E1",
        "grid_minor": "#E2E8F0",
        "checker_a": "#E2E8F0",
        "checker_b": "#F8FAFC",
        "text": "#1A202C",
        "text_muted": "#64748B",
        "accent": "#7C3AED",
        "accent_bright": "#8B5CF6",
        "mint": "#059669",
        "gold": "#D97706",
        "crimson": "#DC2626",
        "cyan": "#0284C7",
    },
    "High Contrast": {
        "bg_base": "#000000",
        "bg_panel": "#000000",
        "bg_canvas": "#000000",
        "bg_canvas_alt": "#0A0A0A",
        "bg_card": "#000000",
        "bg_card_header": "#140028",
        "border": "#FFFFFF",
        "border_strong": "#FFFF00",
        "grid_major": "#808080",
        "grid_minor": "#404040",
        "checker_a": "#181818",
        "checker_b": "#2C2C2C",
        "text": "#FFFFFF",
        "text_muted": "#FFFF00",
        "accent": "#C084FC",
        "accent_bright": "#E9D5FF",
        "mint": "#00FFCC",
        "gold": "#FFFF00",
        "crimson": "#FF4444",
        "cyan": "#00FFFF",
    },
}

KINOPIXEL_DARK_THEME = """
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
    color: #A78BFA;
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
    background-color: #8B5CF6;
    color: #FFFFFF;
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
    color: #A78BFA;
}
QWidget#ControlBar, QWidget#StageBar {
    background-color: #1A1F29;
    border-top: 1px solid #2A3242;
    border-bottom: 1px solid #2A3242;
}
QWidget#StudioPanel {
    background-color: #181C25;
    border-left: 1px solid #283040;
}
QWidget#SidePane {
    background-color: #161A23;
    border-right: 1px solid #283040;
}
QWidget#CardFrame {
    background-color: #1A202E;
    border: 1px solid #2D364A;
    border-radius: 8px;
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
    background-color: #271E47;
    border: 1px solid #8B5CF6;
    color: #C4B5FD;
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
    background-color: #271E47;
    border: 1px solid #8B5CF6;
    color: #C4B5FD;
}
QPushButton#PrimaryButton {
    background-color: #8B5CF6;
    color: #FFFFFF;
    border: 1px solid #A78BFA;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: #9D74FA;
}
QPushButton#PlayButton {
    background-color: #10B981;
    color: #061410;
    border: 1px solid #34D399;
    font-weight: 700;
}
QPushButton#PlayButton:hover {
    background-color: #34D399;
}
QPushButton#KinoAccentButton {
    background-color: #D97706;
    color: #FFFFFF;
    border: 1px solid #F59E0B;
    font-weight: 600;
}
QPushButton#KinoAccentButton:hover {
    background-color: #F59E0B;
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
    padding: 6px 14px;
    margin-right: 2px;
    font-size: 8.8pt;
}
QTabBar::tab:selected {
    background: #232A38;
    color: #FFFFFF;
    border-top: 2px solid #8B5CF6;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: #1F2532;
    color: #DCE2EE;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #10141B;
    color: #EEF2F8;
    border: 1px solid #30394C;
    border-radius: 5px;
    padding: 3px 6px;
    selection-background-color: #8B5CF6;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #A78BFA;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: #1B202B;
    color: #E6EAF2;
    border: 1px solid #354056;
    selection-background-color: #8B5CF6;
    selection-color: #FFFFFF;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #2B3345;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #A78BFA;
    border: 1px solid #12151C;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #8B5CF6;
    border-radius: 2px;
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
    background-color: #2E2257;
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
    color: #A78BFA;
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
    background: #8B5CF6;
    border-color: #A78BFA;
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
    height: 16px;
    font-size: 7.8pt;
}
QProgressBar::chunk {
    background-color: #8B5CF6;
    border-radius: 3px;
}
QLabel#SuiteBadge {
    background-color: #1F173B;
    color: #C4B5FD;
    border: 1px solid #6D48D9;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8pt;
}
QLabel#TargetBadge {
    background-color: #0D2D24;
    color: #34D399;
    border: 1px solid #10B981;
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

KINOPIXEL_LIGHT_THEME = """
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
    background-color: #EDE9FE;
    color: #6D28D9;
}
QMenu {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
}
QMenu::item:selected {
    background-color: #7C3AED;
    color: #FFFFFF;
}
QToolBar, QWidget#ControlBar, QWidget#StageBar, QWidget#StudioPanel, QWidget#SidePane {
    background-color: #F4F6FA;
    border: 1px solid #D3DBE8;
}
QWidget#CardFrame {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
}
QDockWidget::title {
    background-color: #E7ECF4;
    border: 1px solid #CBD5E1;
    padding: 5px 8px;
    font-weight: 600;
    color: #6D28D9;
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
    background-color: #EDE9FE;
    border: 1px solid #7C3AED;
    color: #5B21B6;
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
    background-color: #EDE9FE;
    border: 1px solid #7C3AED;
    color: #5B21B6;
}
QPushButton#PrimaryButton {
    background-color: #7C3AED;
    color: #FFFFFF;
    border: 1px solid #6D28D9;
    font-weight: 700;
}
QPushButton#PlayButton {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    font-weight: 700;
}
QPushButton#KinoAccentButton {
    background-color: #D97706;
    color: #FFFFFF;
    border: 1px solid #B45309;
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
    padding: 6px 14px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #6D28D9;
    border-top: 2px solid #7C3AED;
    font-weight: 600;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
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
    background-color: #EDE9FE;
    color: #4C1D95;
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
    color: #6D28D9;
}
QStatusBar {
    background-color: #E7ECF4;
    color: #4A5568;
    border-top: 1px solid #CBD5E1;
}
QLabel#SuiteBadge {
    background-color: #EDE9FE;
    color: #5B21B6;
    border: 1px solid #C4B5FD;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8pt;
}
QLabel#TargetBadge {
    background-color: #D1FAE5;
    color: #065F46;
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

KINOPIXEL_HIGH_CONTRAST_THEME = """
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
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #FFFF00;
    color: #000000;
    font-weight: 700;
}
QMenu {
    background-color: #000000;
    color: #FFFFFF;
    border: 2px solid #FFFFFF;
}
QToolBar, QWidget#ControlBar, QWidget#StageBar, QWidget#StudioPanel, QWidget#SidePane, QWidget#CardFrame {
    background-color: #000000;
    border: 1px solid #FFFFFF;
}
QDockWidget::title {
    background-color: #000000;
    border: 2px solid #C084FC;
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
QToolButton:checked, QPushButton:checked, QPushButton#PrimaryButton, QPushButton#PlayButton {
    background-color: #C084FC;
    color: #000000;
    border: 2px solid #FFFF00;
    font-weight: 700;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QListWidget, QTreeWidget, QTableWidget {
    background-color: #000000;
    color: #FFFFFF;
    border: 2px solid #FFFFFF;
}
QTabBar::tab {
    background: #000000;
    color: #FFFFFF;
    border: 2px solid #FFFFFF;
    padding: 5px 12px;
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
    color: #C084FC;
    border: 2px solid #C084FC;
    padding: 2px 8px;
    font-weight: 700;
}
QLabel#TargetBadge {
    background-color: #000000;
    color: #00FFCC;
    border: 2px solid #00FFCC;
    padding: 2px 7px;
    font-weight: 700;
}
"""

THEMES: Dict[str, str] = {
    "Dark": KINOPIXEL_DARK_THEME,
    "Light": KINOPIXEL_LIGHT_THEME,
    "High Contrast": KINOPIXEL_HIGH_CONTRAST_THEME,
}


def get_theme_stylesheet(name: str) -> str:
    return THEMES.get(name, KINOPIXEL_DARK_THEME)


def get_palette(name: str) -> Dict[str, str]:
    return PALETTES.get(name, PALETTES["Dark"])
