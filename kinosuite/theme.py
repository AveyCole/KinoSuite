"""KinoSuite Hub Dark & Studio Light Themes.

Unifies the KinoSuite architectural design philosophy (#12151C base, #181C25
panels, #222836 controls, #2A3242 hairlines) with the signature KinoSuite
electric cyan (#00C2FF) master accent.
"""
from __future__ import annotations

KINOSUITE_HUB_DARK = """
QMainWindow, QDialog {
    background-color: #12151C;
    color: #E6EAF2;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9.5pt;
}
QWidget {
    color: #E6EAF2;
    background-color: transparent;
}
QWidget#Sidebar {
    background-color: #151922;
    border-right: 1px solid #262E3D;
}
QWidget#TopBar {
    background-color: #161A23;
    border-bottom: 1px solid #262E3D;
}
QFrame#AppCard {
    background-color: #181C25;
    border: 1px solid #2A3242;
    border-radius: 12px;
}
QFrame#AppCard:hover {
    background-color: #1D2230;
    border: 1px solid #3D4B66;
}
QFrame#DropZone {
    background-color: #151B26;
    border: 1px dashed #2E4A66;
    border-radius: 10px;
}
QFrame#StatCard {
    background-color: #181C25;
    border: 1px solid #2A3242;
    border-radius: 10px;
}
QScrollArea {
    background-color: #12151C;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background-color: #12151C;
}
QPushButton {
    background-color: #222836;
    color: #E6EAF2;
    border: 1px solid #343D52;
    border-radius: 7px;
    padding: 6px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #2B3345;
    border-color: #495672;
}
QPushButton:pressed {
    background-color: #1B212E;
}
QPushButton#NavButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 9px 12px;
    text-align: left;
    color: #9AA4B8;
    font-weight: 600;
}
QPushButton#NavButton:hover {
    background-color: #1E2432;
    color: #E6EAF2;
}
QPushButton#NavButton:checked {
    background-color: #0E2638;
    border: 1px solid #00C2FF;
    color: #00C2FF;
}
QPushButton#PrimaryButton {
    background-color: #00C2FF;
    color: #08121C;
    border: 1px solid #4AD6FF;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background-color: #33D0FF;
}
QPushButton#DangerButton {
    background-color: #3B1D24;
    color: #FCA5A5;
    border: 1px solid #7F2D3A;
}
QPushButton#DangerButton:hover {
    background-color: #512530;
}
QLineEdit, QComboBox, QPlainTextEdit {
    background-color: #10141B;
    color: #EEF2F8;
    border: 1px solid #30394C;
    border-radius: 7px;
    padding: 6px 10px;
    selection-background-color: #00C2FF;
    selection-color: #08121C;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #00C2FF;
}
QComboBox QAbstractItemView {
    background-color: #1B202B;
    color: #E6EAF2;
    border: 1px solid #354056;
    selection-background-color: #00C2FF;
    selection-color: #08121C;
}
QTableWidget, QListWidget {
    background-color: #161A23;
    color: #E6EAF2;
    border: 1px solid #2A3242;
    border-radius: 8px;
    gridline-color: #242C3B;
    outline: none;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #14324A;
    color: #FFFFFF;
}
QHeaderView::section {
    background-color: #1D222E;
    color: #9AA4B8;
    border: 1px solid #2A3242;
    padding: 6px;
    font-weight: 600;
}
QStatusBar {
    background-color: #151922;
    color: #9AA4B8;
    border-top: 1px solid #262E3D;
    font-size: 8.5pt;
}
QLabel#SuiteBadge {
    background-color: #0B2536;
    color: #00C2FF;
    border: 1px solid #136B8E;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8pt;
}
QLabel#SectionTitle {
    color: #FFFFFF;
    font-size: 14pt;
    font-weight: 700;
}
QLabel#MutedText {
    color: #8D99AE;
    font-size: 8.5pt;
}
QScrollBar:vertical {
    background: #141821;
    width: 9px;
}
QScrollBar::handle:vertical {
    background: #364056;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

KINOSUITE_HUB_LIGHT = """
QMainWindow, QDialog {
    background-color: #EEF1F6;
    color: #1A202C;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9.5pt;
}
QWidget {
    color: #1A202C;
    background-color: transparent;
}
QWidget#Sidebar, QWidget#TopBar {
    background-color: #F7F9FC;
    border: 1px solid #D3DBE8;
}
QFrame#AppCard, QFrame#StatCard {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 12px;
}
QFrame#AppCard:hover {
    border: 1px solid #0284C7;
}
QFrame#DropZone {
    background-color: #F0F9FF;
    border: 1px dashed #38BDF8;
    border-radius: 10px;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: #EEF1F6;
    border: none;
}
QPushButton {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 6px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #EDF2F7;
}
QPushButton#NavButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 9px 12px;
    text-align: left;
    color: #4A5568;
    font-weight: 600;
}
QPushButton#NavButton:checked {
    background-color: #E0F2FE;
    border: 1px solid #0284C7;
    color: #0369A1;
}
QPushButton#PrimaryButton {
    background-color: #0284C7;
    color: #FFFFFF;
    border: 1px solid #0369A1;
    font-weight: 700;
}
QPushButton#DangerButton {
    background-color: #FEE2E2;
    color: #991B1B;
    border: 1px solid #FCA5A5;
}
QLineEdit, QComboBox, QPlainTextEdit, QTableWidget, QListWidget {
    background-color: #FFFFFF;
    color: #1A202C;
    border: 1px solid #CBD5E1;
    border-radius: 7px;
    padding: 5px 8px;
}
QHeaderView::section {
    background-color: #E7ECF4;
    color: #334155;
    border: 1px solid #CBD5E1;
    padding: 6px;
    font-weight: 600;
}
QStatusBar {
    background-color: #E7ECF4;
    color: #4A5568;
    border-top: 1px solid #CBD5E1;
}
QLabel#SuiteBadge {
    background-color: #E0F2FE;
    color: #0369A1;
    border: 1px solid #7DD3FC;
    border-radius: 5px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 8pt;
}
QLabel#SectionTitle {
    color: #0F172A;
    font-size: 14pt;
    font-weight: 700;
}
QLabel#MutedText {
    color: #64748B;
    font-size: 8.5pt;
}
"""
