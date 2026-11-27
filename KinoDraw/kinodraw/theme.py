"""KinoSuite Dark & Studio Light themes for KinoDraw.

Shares the KinoSuite / KinoCut sleek deep-slate architectural design philosophy
(#12151C base, #181C24 panels, #212733 controls, #2E3545 hairlines) paired with
Adobe Illustrator's signature warm amber-orange (#FF9A00) creative accent and
KinoSuite cyan (#00C2FF) / electric blue (#3B82F6) focus accents.
"""

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
    color: #FF9A00;
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
    background-color: #FF9A00;
    color: #12151C;
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
QTabWidget {
    background-color: #181C25;
}
QTabBar {
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
    background-color: #2A2218;
    border: 1px solid #FF9A00;
    color: #FF9A00;
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
    background-color: #FF9A00;
    color: #12151C;
    border: 1px solid #FFB340;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: #FFA924;
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
    padding: 5px 11px;
    margin-right: 2px;
    font-size: 8.5pt;
}
QTabBar::tab:selected {
    background: #232A38;
    color: #FFFFFF;
    border-top: 2px solid #FF9A00;
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
    selection-background-color: #FF9A00;
    selection-color: #12151C;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border-color: #FF9A00;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: #1B202B;
    color: #E6EAF2;
    border: 1px solid #354056;
    selection-background-color: #FF9A00;
    selection-color: #12151C;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #2B3345;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #FF9A00;
    border: 1px solid #12151C;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #FF9A00;
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
    background-color: #2C374F;
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
    color: #FF9A00;
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
    background: #FF9A00;
    border-color: #FF9A00;
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
    background-color: #241D15;
    color: #FF9A00;
    border: 1px solid #593B10;
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
