"""KinoSuite Dark & Studio Light themes for KinoFill.

Shares the KinoSuite / KinoCut / KinoDraw sleek deep-slate architectural design philosophy
(#12151C base, #181C25 panels, #222836 controls, #283040 hairlines) paired with
KinoSuite signature cyan (#00C2FF) and KinoFill electric document blue (#2F8CFF) accents.
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
QLabel {
    background-color: transparent;
    color: #DCE2EE;
}
QScrollArea {
    background-color: #0E1117;
    border: none;
}
QScrollArea > QWidget > QWidget, QWidget#ScrollContent {
    background-color: #0E1117;
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
    color: #00C2FF;
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
    background-color: #00C2FF;
    color: #10151E;
    font-weight: 600;
}
QMenu::separator {
    height: 1px;
    background: #2C3445;
    margin: 4px 8px;
}
QToolBar {
    background-color: #171B24;
    border: none;
    border-bottom: 1px solid #283040;
    spacing: 2px;
    padding: 3px 8px;
}
QToolBar::separator {
    width: 1px;
    background-color: #2C3445;
    margin: 5px 5px;
}
QToolButton {
    background-color: transparent;
    color: #DCE2EE;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 3px 6px;
    font-size: 8pt;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #252C3B;
    border-color: #364056;
}
QToolButton:checked {
    background-color: #132536;
    color: #00C2FF;
    border: 1px solid #00C2FF;
    font-weight: 600;
}
QToolButton:pressed {
    background-color: #1B3147;
}
QToolButton:disabled {
    color: #5C677D;
}
QWidget#ContextBar, QWidget#FindBar {
    background-color: #1A1F29;
    border-bottom: 1px solid #2A3242;
}
QWidget#SidebarPanel {
    background-color: #181C25;
    border-right: 1px solid #283040;
}
QLabel#SuiteBadge {
    background-color: #122030;
    color: #00C2FF;
    border: 1px solid #1E4968;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8pt;
    letter-spacing: 0.4px;
}
QLabel#ToolBadge {
    background-color: #172436;
    color: #56B4FF;
    border: 1px solid #264873;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8.5pt;
}
QLabel#SectionHeader {
    color: #94A3B8;
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    padding-top: 2px;
}
QLabel#MutedHint {
    color: #9AA4B8;
    font-size: 8.5pt;
}
QTabWidget {
    background-color: #141820;
}
QTabWidget#DocTabs {
    background-color: #141820;
}
QTabWidget::pane {
    border: none;
    border-top: 1px solid #262D3B;
    background: #0E1117;
}
QTabWidget#SidebarTabs {
    background-color: #181C25;
}
QTabWidget#SidebarTabs::pane {
    border: none;
    border-top: 1px solid #262D3B;
    background: #181C25;
}
QTabBar {
    background-color: #141820;
    qproperty-drawBase: 0;
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
QTabWidget#DocTabs > QTabBar::tab {
    min-width: 118px;
    padding: 6px 14px;
}
QTabBar::tab:selected {
    background: #232A38;
    color: #FFFFFF;
    border-top: 2px solid #00C2FF;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: #1F2532;
    color: #DCE2EE;
}
QPushButton {
    background-color: #222836;
    color: #E6EAF2;
    border: 1px solid #343D52;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 500;
}
QPushButton#CompactBtn {
    padding: 0px 4px;
    min-width: 0px;
    border-radius: 5px;
    font-size: 8.5pt;
    font-weight: 600;
}
QToolButton#FormatBtn {
    background-color: #222836;
    border: 1px solid #343D52;
    border-radius: 5px;
    padding: 2px 6px;
    min-width: 24px;
    min-height: 22px;
}
QToolButton#FormatBtn:hover {
    background-color: #2B3345;
    border-color: #495672;
}
QToolButton#FormatBtn:checked {
    background-color: #132536;
    color: #00C2FF;
    border: 1px solid #00C2FF;
}
QPushButton:hover {
    background-color: #2B3345;
    border-color: #495672;
}
QPushButton:pressed {
    background-color: #1D2330;
}
QPushButton:disabled {
    color: #5C677D;
    background-color: #191E28;
    border-color: #262E3D;
}
QPushButton#PrimaryButton {
    background-color: #00C2FF;
    color: #10151E;
    border: 1px solid #4AD8FF;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: #29CEFF;
}
QPushButton#PrimaryButton:pressed {
    background-color: #00A8E0;
}
QPushButton#KinoAccentButton {
    background-color: #2F8CFF;
    color: #FFFFFF;
    border: 1px solid #5AA6FF;
    font-weight: 600;
}
QPushButton#KinoAccentButton:hover {
    background-color: #4499FF;
}
QPushButton#DangerButton {
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #EF4444;
    font-weight: 600;
}
QPushButton#DangerButton:hover {
    background-color: #B91C1C;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #10141B;
    color: #EEF2F8;
    border: 1px solid #30394C;
    border-radius: 5px;
    padding: 3px 7px;
    selection-background-color: #00C2FF;
    selection-color: #10151E;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #00C2FF;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: #1B202B;
    color: #E6EAF2;
    border: 1px solid #354056;
    selection-background-color: #00C2FF;
    selection-color: #10151E;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #2B3345;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #00C2FF;
    border: 1px solid #12151C;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #00C2FF;
    border-radius: 2px;
}
QListWidget, QTreeWidget {
    background-color: #141821;
    color: #E6EAF2;
    border: 1px solid #2A3242;
    border-radius: 6px;
    outline: none;
}
QListWidget::item, QTreeWidget::item {
    padding: 5px 7px;
    border-radius: 5px;
    margin: 2px 3px;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #1D3552;
    color: #FFFFFF;
    border: 1px solid #2F8CFF;
}
QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {
    background-color: #1F2634;
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
    background: #00C2FF;
    border-color: #00C2FF;
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
QScrollBar::handle:horizontal:hover {
    background: #4E5C7A;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
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
    padding: 0 5px;
    color: #00C2FF;
    font-size: 8.5pt;
}
QWidget#WelcomeBackdrop {
    background-color: #0E1117;
}
QWidget#WelcomeCard {
    background-color: #171B24;
    border: 1px solid #2C3445;
    border-radius: 12px;
}
QLabel#WelcomeTitle {
    font-size: 23pt;
    font-weight: 800;
    color: #F4F7FC;
    letter-spacing: 1.5px;
}
QLabel#WelcomeSuiteTag {
    font-size: 9pt;
    font-weight: 700;
    color: #00C2FF;
    letter-spacing: 1.4px;
}
QLabel#WelcomeSubtitle {
    font-size: 10pt;
    color: #9AA4B8;
}
QLabel#WelcomeChip {
    background-color: #1D2432;
    color: #B9C4D8;
    border: 1px solid #2E384D;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 8pt;
    font-weight: 600;
}
QLabel#DropHint {
    padding: 13px;
    background-color: #131822;
    border: 1.5px dashed #29597A;
    border-radius: 8px;
    color: #56C8F5;
    font-weight: 500;
}
QLabel#UploadPreview {
    background-color: #141821;
    color: #9AA4B8;
    border: 1px dashed #3A455C;
    border-radius: 6px;
}
"""

KINOSUITE_LIGHT_THEME = """
QMainWindow, QDialog {
    background-color: #EEF2F7;
    color: #161B26;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9pt;
}
QWidget {
    color: #161B26;
    background-color: transparent;
}
QLabel {
    background-color: transparent;
    color: #1E2534;
}
QScrollArea {
    background-color: #DFE5EF;
    border: none;
}
QScrollArea > QWidget > QWidget, QWidget#ScrollContent {
    background-color: #DFE5EF;
}
QMenuBar {
    background-color: #F8FAFC;
    color: #1E2534;
    border-bottom: 1px solid #D5DCE6;
    padding: 2px 6px;
}
QMenuBar::item {
    padding: 4px 9px;
    border-radius: 5px;
    background: transparent;
}
QMenuBar::item:selected {
    background-color: #E0F2FE;
    color: #0369A1;
}
QMenu {
    background-color: #FFFFFF;
    color: #161B26;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 5px 26px 5px 14px;
    border-radius: 5px;
}
QMenu::item:selected {
    background-color: #0284C7;
    color: #FFFFFF;
    font-weight: 600;
}
QMenu::separator {
    height: 1px;
    background: #E2E8F0;
    margin: 4px 8px;
}
QToolBar {
    background-color: #FFFFFF;
    border: none;
    border-bottom: 1px solid #D5DCE6;
    spacing: 2px;
    padding: 3px 8px;
}
QToolBar::separator {
    width: 1px;
    background-color: #D5DCE6;
    margin: 5px 5px;
}
QToolButton {
    background-color: transparent;
    color: #2B3445;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 3px 6px;
    font-size: 8pt;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #EEF2F7;
    border-color: #CBD5E1;
}
QToolButton:checked {
    background-color: #E0F2FE;
    color: #0369A1;
    border: 1px solid #0284C7;
    font-weight: 600;
}
QToolButton:pressed {
    background-color: #BAE6FD;
}
QToolButton:disabled {
    color: #94A3B8;
}
QWidget#ContextBar, QWidget#FindBar {
    background-color: #F4F7FB;
    border-bottom: 1px solid #D5DCE6;
}
QWidget#SidebarPanel {
    background-color: #F6F8FB;
    border-right: 1px solid #D5DCE6;
}
QLabel#SuiteBadge {
    background-color: #E0F2FE;
    color: #0369A1;
    border: 1px solid #7DD3FC;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8pt;
    letter-spacing: 0.4px;
}
QLabel#ToolBadge {
    background-color: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8.5pt;
}
QLabel#SectionHeader {
    color: #64748B;
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    padding-top: 2px;
}
QLabel#MutedHint {
    color: #64748B;
    font-size: 8.5pt;
}
QTabWidget {
    background-color: #E7EDF5;
}
QTabWidget#DocTabs {
    background-color: #E7EDF5;
}
QTabWidget::pane {
    border: none;
    border-top: 1px solid #CBD5E1;
    background: #DFE5EF;
}
QTabWidget#SidebarTabs {
    background-color: #F6F8FB;
}
QTabWidget#SidebarTabs::pane {
    border: none;
    border-top: 1px solid #CBD5E1;
    background: #F6F8FB;
}
QTabBar {
    background-color: #E7EDF5;
    qproperty-drawBase: 0;
}
QTabBar::tab {
    background: #E8EEF6;
    color: #475569;
    border: 1px solid #CBD5E1;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 5px 11px;
    margin-right: 2px;
    font-size: 8.5pt;
}
QTabWidget#DocTabs > QTabBar::tab {
    min-width: 118px;
    padding: 6px 14px;
}
QTabBar::tab:selected {
    background: #FFFFFF;
    color: #0F172A;
    border-top: 2px solid #0284C7;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: #F1F5F9;
}
QPushButton {
    background-color: #FFFFFF;
    color: #1E2534;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 500;
}
QPushButton#CompactBtn {
    padding: 0px 4px;
    min-width: 0px;
    border-radius: 5px;
    font-size: 8.5pt;
    font-weight: 600;
}
QToolButton#FormatBtn {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 2px 6px;
    min-width: 24px;
    min-height: 22px;
}
QToolButton#FormatBtn:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}
QToolButton#FormatBtn:checked {
    background-color: #E0F2FE;
    color: #0369A1;
    border: 1px solid #0284C7;
}
QPushButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}
QPushButton:pressed {
    background-color: #E2E8F0;
}
QPushButton#PrimaryButton {
    background-color: #0284C7;
    color: #FFFFFF;
    border: 1px solid #0369A1;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: #0369A1;
}
QPushButton#KinoAccentButton {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
    font-weight: 600;
}
QPushButton#DangerButton {
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #B91C1C;
    font-weight: 600;
}
QPushButton#DangerButton:hover {
    background-color: #B91C1C;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #FFFFFF;
    color: #0F172A;
    border: 1px solid #CBD5E1;
    border-radius: 5px;
    padding: 3px 7px;
    selection-background-color: #0284C7;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #0284C7;
}
QComboBox::drop-down {
    border: none;
    width: 18px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #CBD5E1;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #0284C7;
    border: 1px solid #FFFFFF;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #0284C7;
    border-radius: 2px;
}
QListWidget, QTreeWidget {
    background-color: #FFFFFF;
    color: #1E2534;
    border: 1px solid #D5DCE6;
    border-radius: 6px;
    outline: none;
}
QListWidget::item, QTreeWidget::item {
    padding: 5px 7px;
    border-radius: 5px;
    margin: 2px 3px;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #E0F2FE;
    color: #0369A1;
    border: 1px solid #7DD3FC;
}
QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {
    background-color: #F1F5F9;
}
QCheckBox, QRadioButton {
    spacing: 6px;
    color: #1E2534;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #94A3B8;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    background: #0284C7;
    border-color: #0284C7;
}
QStatusBar {
    background-color: #F8FAFC;
    color: #475569;
    border-top: 1px solid #D5DCE6;
    font-size: 8.5pt;
}
QSplitter::handle {
    background-color: #D5DCE6;
    width: 2px;
}
QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 4px;
    min-height: 26px;
}
QScrollBar::handle:vertical:hover {
    background: #94A3B8;
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
    background: #CBD5E1;
    border-radius: 4px;
    min-width: 26px;
}
QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QGroupBox {
    font-weight: 600;
    color: #334155;
    border: 1px solid #D5DCE6;
    border-radius: 7px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #0284C7;
    font-size: 8.5pt;
}
QWidget#WelcomeBackdrop {
    background-color: #E7EDF5;
}
QWidget#WelcomeCard {
    background-color: #FFFFFF;
    border: 1px solid #D5DCE6;
    border-radius: 12px;
}
QLabel#WelcomeTitle {
    font-size: 23pt;
    font-weight: 800;
    color: #0F172A;
    letter-spacing: 1.5px;
}
QLabel#WelcomeSuiteTag {
    font-size: 9pt;
    font-weight: 700;
    color: #0284C7;
    letter-spacing: 1.4px;
}
QLabel#WelcomeSubtitle {
    font-size: 10pt;
    color: #475569;
}
QLabel#WelcomeChip {
    background-color: #F1F5F9;
    color: #334155;
    border: 1px solid #CBD5E1;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 8pt;
    font-weight: 600;
}
QLabel#DropHint {
    padding: 13px;
    background-color: #F8FAFC;
    border: 1.5px dashed #7DD3FC;
    border-radius: 8px;
    color: #0369A1;
    font-weight: 500;
}
QLabel#UploadPreview {
    background-color: #F8FAFC;
    color: #64748B;
    border: 1px dashed #94A3B8;
    border-radius: 6px;
}
"""

DARK_THEME = KINOSUITE_DARK_THEME
LIGHT_THEME = KINOSUITE_LIGHT_THEME
