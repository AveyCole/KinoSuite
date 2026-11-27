"""KinoSuite Dark & Studio Light themes for KinoShop.

Shares the KinoSuite / KinoCut / KinoDraw sleek deep-slate architectural design philosophy
(#12151C base, #181C25 panels, #222836 controls, #2A3242 hairlines) paired with
KinoShop's signature electric sapphire-cyan (#31A8FF / #00C2FF) photographic accent.
"""
from __future__ import annotations

KINOSUITE_DARK_THEME = """
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
    color: #31A8FF;
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
    background-color: #31A8FF;
    color: #0D1117;
    font-weight: 600;
}
QMenu::separator {
    height: 1px;
    background: #2C3445;
    margin: 4px 8px;
}
QWidget#ControlBar {
    background-color: #1A1F29;
    border-bottom: 1px solid #2A3242;
}
QWidget#ToolsDock {
    background-color: #171B24;
    border-right: 1px solid #283040;
}
QWidget#StudioPanel {
    background-color: #181C25;
    border-left: 1px solid #283040;
}
QWidget#TimelineDock {
    background-color: #161A23;
    border-top: 1px solid #283040;
}
QTabWidget {
    background-color: #141820;
}
QTabWidget::pane {
    border: none;
    background-color: #141820;
}
QTabBar {
    background-color: #141820;
}
QTabBar::scroller {
    background-color: #141820;
}
QStackedWidget {
    background-color: #141820;
}
QWidget#DocTabsWrap {
    background-color: #141820;
}
QTabBar QToolButton {
    background-color: #1C222E;
    color: #CBD5E1;
    border: 1px solid #2C3445;
    border-radius: 3px;
}
QWidget#ContextualBar {
    background-color: rgba(24, 28, 37, 242);
    border: 1px solid #39445B;
    border-radius: 9px;
}
QToolButton {
    background-color: transparent;
    color: #DCE2EE;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 3px;
}
QToolButton:hover {
    background-color: #252C3B;
    border-color: #364056;
}
QToolButton:checked {
    background-color: #13283F;
    border: 1px solid #31A8FF;
    color: #31A8FF;
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
QPushButton#PrimaryButton {
    background-color: #31A8FF;
    color: #0C121C;
    border: 1px solid #5CC0FF;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: #4BB5FF;
}
QPushButton#KinoAccentButton {
    background-color: #0077CC;
    color: #FFFFFF;
    border: 1px solid #00A2FF;
    font-weight: 600;
}
QPushButton#KinoAccentButton:hover {
    background-color: #008AE6;
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
QTabBar::tab {
    background: #181C24;
    color: #9AA4B8;
    border: 1px solid #272F3F;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 5px 10px;
    margin-right: 2px;
    font-size: 8.5pt;
}
QTabBar::tab:selected {
    background: #232A38;
    color: #FFFFFF;
    border-top: 2px solid #31A8FF;
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
    selection-background-color: #31A8FF;
    selection-color: #0D1117;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border-color: #31A8FF;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: #1B202B;
    color: #E6EAF2;
    border: 1px solid #354056;
    selection-background-color: #31A8FF;
    selection-color: #0D1117;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #2B3345;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #31A8FF;
    border: 1px solid #12151C;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #31A8FF;
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
    background-color: #1D3550;
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
    color: #31A8FF;
    font-size: 8.5pt;
}
QCheckBox {
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
    background: #31A8FF;
    border-color: #31A8FF;
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
    background: transparent;
    width: 9px;
    margin: 2px;
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
    background: transparent;
    height: 9px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #364056;
    border-radius: 4px;
    min-width: 26px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QLabel#SuiteBadge {
    background-color: #0E2238;
    color: #31A8FF;
    border: 1px solid #1E5B94;
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

KINOSUITE_LIGHT_THEME = """
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
    background-color: #D7E4F5;
    color: #0066CC;
}
QMenu {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
}
QMenu::item:selected {
    background-color: #0077CC;
    color: #FFFFFF;
}
QWidget#ControlBar, QWidget#ToolsDock, QWidget#StudioPanel, QWidget#TimelineDock {
    background-color: #F4F6FA;
    border: 1px solid #D3DBE8;
}
QWidget#ContextualBar {
    background-color: rgba(255, 255, 255, 242);
    border: 1px solid #B6C5DC;
    border-radius: 9px;
}
QToolButton {
    background-color: transparent;
    color: #1A202C;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 3px;
}
QToolButton:hover {
    background-color: #E2E8F0;
}
QToolButton:checked {
    background-color: #D8ECFF;
    border: 1px solid #0077CC;
    color: #005FA3;
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
QPushButton#PrimaryButton {
    background-color: #0077CC;
    color: #FFFFFF;
    border: 1px solid #0060A8;
    font-weight: 700;
}
QPushButton#KinoAccentButton {
    background-color: #0088DD;
    color: #FFFFFF;
    border: 1px solid #0070B8;
    font-weight: 600;
}
QTabBar::tab {
    background: #E7ECF4;
    color: #4A5568;
    border: 1px solid #CBD5E1;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 5px 10px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #0066CC;
    border-top: 2px solid #0077CC;
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
    background-color: #D8ECFF;
    color: #0A2540;
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
    color: #0066CC;
}
QStatusBar {
    background-color: #E7ECF4;
    color: #4A5568;
    border-top: 1px solid #CBD5E1;
}
QLabel#SuiteBadge {
    background-color: #D8ECFF;
    color: #005FA3;
    border: 1px solid #7CC4FA;
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
