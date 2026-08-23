"""Visual tokens and Qt stylesheet for the FideliChem desktop console.

The GUI deliberately keeps visual decisions in this module. Views expose
scientific data and user actions, while this file owns color, spacing, focus,
and surface treatment.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

COLORS = {
    "canvas": "#0B1220",
    "surface": "#111B2F",
    "surface_raised": "#16243A",
    "surface_input": "#0F192B",
    "border": "#273750",
    "border_strong": "#385170",
    "text": "#EAF2FF",
    "text_muted": "#95A7C2",
    "accent": "#5BE6C7",
    "accent_pressed": "#35B99D",
    "accent_soft": "#173A3D",
    "warning": "#FFCA7A",
    "danger": "#FF7B88",
}


APPLICATION_STYLESHEET = f"""
QMainWindow, QWidget {{
    background: {COLORS['canvas']};
    color: {COLORS['text']};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}

QWidget#sidebarPanel {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}

QLabel#brandMark {{
    color: {COLORS['accent']};
    font-size: 19px;
    font-weight: 700;
    letter-spacing: 1px;
}}

QLabel#brandCaption {{
    color: {COLORS['text_muted']};
    font-size: 11px;
}}

QLabel#pageTitle {{
    color: {COLORS['text']};
    font-size: 23px;
    font-weight: 700;
    padding: 4px 0 2px 0;
}}

QLabel#pageSubtitle {{
    color: {COLORS['text_muted']};
    font-size: 12px;
    padding-bottom: 8px;
}}

QLabel#sectionLabel {{
    color: {COLORS['text_muted']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

QLabel#projectStatusLabel, QLabel#exportStatusLabel, QLabel#statusBadge {{
    background: {COLORS['accent_soft']};
    border: 1px solid {COLORS['accent_pressed']};
    border-radius: 8px;
    color: {COLORS['accent']};
    padding: 8px 10px;
}}

QListWidget#sidebarNav {{
    background: transparent;
    border: none;
    outline: none;
    padding: 6px;
}}

QListWidget#sidebarNav::item {{
    border-radius: 8px;
    color: {COLORS['text_muted']};
    padding: 10px 12px;
    margin: 2px 0;
}}

QListWidget#sidebarNav::item:hover {{
    background: {COLORS['surface_raised']};
    color: {COLORS['text']};
}}

QListWidget#sidebarNav::item:selected {{
    background: {COLORS['accent_soft']};
    color: {COLORS['accent']};
    font-weight: 700;
}}

QLineEdit, QComboBox, QTextEdit, QTableWidget {{
    background: {COLORS['surface_input']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    color: {COLORS['text']};
    selection-background-color: {COLORS['accent_pressed']};
    selection-color: {COLORS['canvas']};
}}

QLineEdit, QComboBox {{
    min-height: 32px;
    padding: 0 10px;
}}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QTableWidget:focus {{
    border: 1px solid {COLORS['accent']};
}}

QLineEdit:disabled, QComboBox:disabled, QPushButton:disabled {{
    color: {COLORS['text_muted']};
    background: {COLORS['surface']};
}}

QPushButton {{
    background: {COLORS['surface_raised']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 8px;
    color: {COLORS['text']};
    font-weight: 600;
    min-height: 32px;
    padding: 0 14px;
}}

QPushButton:hover {{
    border-color: {COLORS['accent']};
    color: {COLORS['accent']};
}}

QPushButton:pressed {{
    background: {COLORS['accent_pressed']};
    color: {COLORS['canvas']};
}}

QPushButton[role="primary"] {{
    background: {COLORS['accent']};
    border-color: {COLORS['accent']};
    color: {COLORS['canvas']};
}}

QPushButton[role="primary"]:hover {{
    background: {COLORS['accent_pressed']};
    color: {COLORS['canvas']};
}}

QPushButton[role="secondary"] {{
    background: transparent;
}}

QTableWidget {{
    alternate-background-color: {COLORS['surface']};
    gridline-color: {COLORS['border']};
}}

QTableWidget::item {{
    padding: 6px;
}}

QHeaderView::section {{
    background: {COLORS['surface_raised']};
    border: none;
    border-bottom: 1px solid {COLORS['border_strong']};
    color: {COLORS['text_muted']};
    font-size: 11px;
    font-weight: 700;
    padding: 8px;
}}

QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background: {COLORS['surface']};
    border: 1px solid transparent;
    border-bottom: none;
    color: {COLORS['text_muted']};
    padding: 8px 12px;
}}

QTabBar::tab:hover {{
    color: {COLORS['text']};
}}

QTabBar::tab:selected {{
    background: {COLORS['surface_raised']};
    border-color: {COLORS['border']};
    color: {COLORS['accent']};
}}

QSplitter::handle {{
    background: {COLORS['border']};
}}

QStatusBar {{
    background: {COLORS['surface']};
    border-top: 1px solid {COLORS['border']};
    color: {COLORS['text_muted']};
}}

QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    border: 1px solid {COLORS['border_strong']};
    border-radius: 4px;
    height: 16px;
    width: 16px;
}}

QCheckBox::indicator:checked {{
    background: {COLORS['accent']};
    border-color: {COLORS['accent']};
}}
"""


def apply_theme(widget: QWidget) -> None:
    """Apply the shared visual system to a top-level GUI widget."""

    widget.setStyleSheet(APPLICATION_STYLESHEET)


__all__ = ["APPLICATION_STYLESHEET", "COLORS", "apply_theme"]
