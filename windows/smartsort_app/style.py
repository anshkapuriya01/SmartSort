"""A calm, flat look in the spirit of Windows 11: soft neutral background, white cards with
rounded corners and a hairline border, one accent color. Follows the system's light/dark mode."""

from __future__ import annotations

from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtCore import Qt

ACCENT = "#0a64d6"
EXISTING = "#0f8a8a"   # a folder that's already there
NEW = "#0a64d6"        # a folder SmartSort will make
REVIEW = "#c26a00"
DUPLICATE = "#6b7280"


def is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return QGuiApplication.palette().color(QPalette.Window).lightness() < 128


def colors() -> dict:
    if is_dark():
        return dict(bg="#1c1f24", card="#262a31", card_hover="#2d323a", border="#363c46", text="#eceff4",
                    muted="#9aa3b2", sidebar="#20242a", selected_tint="#1d3557")
    return dict(bg="#f3f5f8", card="#ffffff", card_hover="#f7f9fc", border="#dde2ea", text="#1b1f24",
                muted="#6b7280", sidebar="#eef1f5", selected_tint="#e8f0fd")


def tint_for(path: str, existing: bool) -> str:
    top = path.split("/")[0]
    if top == "Needs Review":
        return REVIEW
    if top == "Duplicates":
        return DUPLICATE
    return EXISTING if existing else NEW


def stylesheet() -> str:
    c = colors()
    return f"""
    QWidget {{ color: {c['text']}; font-size: 10pt; }}
    QMainWindow, #Page, #ScrollBody {{ background: {c['bg']}; }}
    QScrollArea {{ border: none; background: {c['bg']}; }}
    #Sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
    #Sidebar QListWidget {{ background: transparent; border: none; }}
    #Sidebar QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
    #Sidebar QListWidget::item:selected, #Sidebar QListWidget::item:hover {{ background: {c['card_hover']}; color: {c['text']}; }}
    #SidebarTitle {{ color: {c['muted']}; font-weight: 600; font-size: 9pt; padding: 12px 12px 4px 12px; }}
    #Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    #Tile {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    #Tile[hover="true"] {{ background: {c['card_hover']}; }}
    #Row[hover="true"] {{ background: {c['card_hover']}; border-radius: 8px; }}
    #Title {{ font-size: 20pt; font-weight: 600; }}
    #Subtitle {{ font-size: 11pt; color: {c['muted']}; }}
    #Heading {{ font-size: 12pt; font-weight: 600; }}
    #Muted {{ color: {c['muted']}; }}
    #Small {{ color: {c['muted']}; font-size: 9pt; }}
    #Badge {{ border-radius: 9px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600; }}
    QPushButton {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {c['card_hover']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton#Primary {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: #0956b8; }}
    QPushButton#Primary:disabled {{ background: {c['border']}; border-color: {c['border']}; }}
    QPushButton#Big {{ font-size: 12pt; padding: 10px 22px; }}
    QPushButton#Link {{ border: none; background: transparent; color: {ACCENT}; padding: 2px 4px; }}
    QPushButton#Link:hover {{ text-decoration: underline; }}
    QToolButton {{ border: none; border-radius: 6px; padding: 4px; }}
    QToolButton:hover {{ background: {c['card_hover']}; }}
    QToolButton:checked {{ background: {c['selected_tint']}; }}
    QComboBox {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 10px; }}
    QLineEdit {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 8px; }}
    QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
    QProgressBar {{ background: {c['border']}; border: none; border-radius: 3px; max-height: 6px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
    #ActionBar {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    #DropZone {{ background: {c['card']}; border: 2px dashed {c['border']}; border-radius: 18px; }}
    #DropZone[active="true"] {{ border: 2px dashed {ACCENT}; background: {c['selected_tint']}; }}
    QToolBar {{ background: {c['bg']}; border: none; border-bottom: 1px solid {c['border']}; spacing: 6px; padding: 6px; }}
    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 8px; background: {c['card']}; }}
    """


def apply(app) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())


def qcolor(hex_color: str, alpha: int = 255) -> QColor:
    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color
