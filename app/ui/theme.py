"""Color tokens and stylesheet generation for the application shell.

The window used to carry one hard-coded light stylesheet plus a forced light
palette, so the app ignored the desktop theme and was painfully bright next to
a dark session.  Colors now live in one token set per mode and every rule is
generated from it.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_CHOICES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)


@dataclass(frozen=True)
class Theme:
    """One resolved set of UI colors."""

    mode: str
    window: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str
    accent: str
    accent_soft: str
    accent_border: str
    secondary: str
    secondary_soft: str
    secondary_border: str
    selection: str
    scrollbar: str
    scrollbar_hover: str
    disabled_text: str
    disabled_surface: str
    success: str
    warning: str
    danger: str


LIGHT = Theme(
    mode=THEME_LIGHT,
    window="#ffffff",
    surface="#ffffff",
    surface_alt="#f8fafc",
    border="#eef2f7",
    border_strong="#dde5ef",
    text="#172033",
    text_muted="#475569",
    text_subtle="#344054",
    accent="#1d4ed8",
    accent_soft="#eef5ff",
    accent_border="#cfe0ff",
    secondary="#7c3aed",
    secondary_soft="#f6f0ff",
    secondary_border="#e2d4ff",
    selection="#dbeafe",
    scrollbar="#d7e2f0",
    scrollbar_hover="#bfd0e8",
    disabled_text="#9aa3b2",
    disabled_surface="#fafbfd",
    success="#047857",
    warning="#b45309",
    danger="#b91c1c",
)

DARK = Theme(
    mode=THEME_DARK,
    window="#10151d",
    surface="#171e28",
    surface_alt="#1d2530",
    border="#273140",
    border_strong="#35435a",
    text="#e7edf6",
    text_muted="#9db0c7",
    text_subtle="#c4d0e0",
    accent="#7fa9ff",
    accent_soft="#1b2740",
    accent_border="#31456b",
    secondary="#b696ff",
    secondary_soft="#241e3a",
    secondary_border="#3d3361",
    selection="#27395c",
    scrollbar="#33415a",
    scrollbar_hover="#44567a",
    disabled_text="#63718a",
    disabled_surface="#141a23",
    success="#34d399",
    warning="#fbbf24",
    danger="#f87171",
)


def system_prefers_dark() -> bool:
    """Ask Qt whether the desktop is running a dark color scheme."""
    app = QApplication.instance()
    if app is None:
        return False
    hints = app.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:
        try:
            from PySide6.QtCore import Qt

            return scheme() == Qt.ColorScheme.Dark
        except (AttributeError, TypeError):
            pass
    # Older Qt builds expose no color scheme hint; infer it from the palette.
    palette = app.palette()
    window = palette.color(QPalette.Window)
    return window.lightness() < 128


def resolve(preference: str) -> Theme:
    """Turn a stored preference into the theme that should be painted."""
    if preference == THEME_DARK:
        return DARK
    if preference == THEME_LIGHT:
        return LIGHT
    return DARK if system_prefers_dark() else LIGHT


def build_palette(theme: Theme) -> QPalette:
    """Build a QPalette so native widgets match the stylesheet."""
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(theme.window))
    palette.setColor(QPalette.WindowText, QColor(theme.text))
    palette.setColor(QPalette.Base, QColor(theme.surface))
    palette.setColor(QPalette.AlternateBase, QColor(theme.surface_alt))
    palette.setColor(QPalette.ToolTipBase, QColor(theme.surface))
    palette.setColor(QPalette.ToolTipText, QColor(theme.text))
    palette.setColor(QPalette.Text, QColor(theme.text))
    palette.setColor(QPalette.Button, QColor(theme.surface))
    palette.setColor(QPalette.ButtonText, QColor(theme.text))
    palette.setColor(QPalette.BrightText, QColor(theme.danger))
    palette.setColor(QPalette.Highlight, QColor(theme.selection))
    palette.setColor(QPalette.HighlightedText, QColor(theme.text))
    palette.setColor(QPalette.Link, QColor(theme.accent))
    palette.setColor(QPalette.PlaceholderText, QColor(theme.disabled_text))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(theme.disabled_text))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(theme.disabled_text))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(theme.disabled_text))
    return palette


def build_stylesheet(theme: Theme) -> str:
    """Generate the main window stylesheet for a theme."""
    return f"""
    QMainWindow {{ background: {theme.window}; }}
    QWidget {{ color: {theme.text}; }}
    QToolBar#mainToolbar {{
        background: {theme.window};
        border: 0;
        border-bottom: 1px solid {theme.border};
        spacing: 8px;
        padding: 10px 18px 8px 18px;
    }}
    QToolBar#mainToolbar QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 9px 15px;
        color: {theme.accent};
        font-weight: 700;
    }}
    QToolBar#mainToolbar QToolButton:hover {{
        background: {theme.accent_soft};
        border: 1px solid {theme.accent_border};
    }}
    QToolBar#mainToolbar QToolButton#toolbarMagicButton {{ color: {theme.secondary}; }}
    QToolBar#mainToolbar QToolButton#toolbarMagicButton:hover {{
        background: {theme.secondary_soft};
        border: 1px solid {theme.secondary_border};
    }}
    QFrame#sidebarCard {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 18px;
    }}
    QTabWidget::pane {{ border: 0; background: {theme.window}; }}
    QTabBar::tab {{
        background: transparent;
        color: {theme.text_muted};
        padding: 8px 14px;
        border: 1px solid transparent;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
    }}
    QTabBar::tab:selected {{
        color: {theme.accent};
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-bottom-color: {theme.surface};
        font-weight: 700;
    }}
    QListWidget#sidebarNav {{
        background: transparent;
        border: 0;
        outline: 0;
        padding: 2px;
    }}
    QListWidget#sidebarNav::item {{
        min-height: 34px;
        padding: 7px 12px;
        margin: 0;
        border: 1px solid transparent;
        border-radius: 12px;
        font-weight: 700;
        color: {theme.text_muted};
    }}
    QListWidget#sidebarNav::item:selected {{
        background: {theme.accent_soft};
        border: 1px solid {theme.accent_border};
    }}
    QToolButton#sidebarToggle {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 6px;
    }}
    QToolButton#sidebarToggle:hover {{
        background: {theme.surface_alt};
        border: 1px solid {theme.border};
    }}
    QListWidget#sidebarNav::item:hover {{
        background: {theme.surface_alt};
        border: 1px solid {theme.border};
    }}
    QStatusBar {{
        background: {theme.window};
        border-top: 1px solid {theme.border};
        color: {theme.text_muted};
    }}
    QScrollArea {{ border: 0; background: transparent; }}
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 4px 4px 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {theme.scrollbar};
        min-height: 36px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {theme.scrollbar_hover}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 0 4px 4px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {theme.scrollbar};
        min-width: 36px;
        border-radius: 6px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {theme.scrollbar_hover}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
        width: 0;
    }}
    QGroupBox {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 14px;
        margin-top: 16px;
        padding-top: 16px;
        font-weight: 700;
        color: {theme.accent};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 0 6px;
        color: {theme.accent};
        background: transparent;
    }}
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QDoubleSpinBox, QSpinBox, QTableWidget {{
        background: {theme.surface};
        border: 1px solid {theme.border_strong};
        border-radius: 12px;
        padding: 7px 9px;
        color: {theme.text};
        selection-background-color: {theme.selection};
        selection-color: {theme.text};
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QDoubleSpinBox:focus, QSpinBox:focus, QTableWidget:focus {{
        border: 1px solid {theme.accent};
    }}
    QComboBox QAbstractItemView {{
        background: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border_strong};
        selection-background-color: {theme.selection};
        selection-color: {theme.text};
    }}
    QHeaderView::section {{
        background: {theme.surface_alt};
        color: {theme.text_subtle};
        border: 0;
        border-bottom: 1px solid {theme.border};
        padding: 6px 8px;
        font-weight: 700;
    }}
    QTableWidget {{ gridline-color: {theme.border}; }}
    /* The corner button between the two headers keeps the raw palette colour
       and showed up as a white square in dark mode. */
    QTableCornerButton::section {{
        background: {theme.surface_alt};
        border: 0;
        border-bottom: 1px solid {theme.border};
        border-right: 1px solid {theme.border};
    }}
    QHeaderView {{ background: {theme.surface_alt}; }}
    QPushButton, QToolButton {{
        background: {theme.surface};
        border: 1px solid {theme.border_strong};
        border-radius: 12px;
        padding: 8px 13px;
        color: {theme.text};
        font-weight: 600;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {theme.surface_alt};
        border: 1px solid {theme.accent_border};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        background: {theme.disabled_surface};
        color: {theme.disabled_text};
        border: 1px solid transparent;
    }}
    QProgressBar {{
        background: {theme.surface_alt};
        border: 1px solid {theme.border};
        border-radius: 8px;
        text-align: center;
        color: {theme.text_muted};
    }}
    QProgressBar::chunk {{ background: {theme.accent}; border-radius: 7px; }}
    QCheckBox, QRadioButton {{ color: {theme.text}; }}
    QLabel {{ color: {theme.text_subtle}; }}
    QSplitter::handle {{ background: {theme.border}; }}
    """ + page_stylesheet(theme)


def page_stylesheet(theme: Theme) -> str:
    """Rules for the cards, titles and badges used inside the tab pages.

    These used to live as literal light-mode stylesheets on each tab.  A
    stylesheet set on a child widget wins over the window's, so leaving them
    there meant every page stayed white no matter what theme was selected.
    """
    return f"""
    QFrame#heroCard, QFrame#summaryCard, QFrame#setupSidebar, QFrame#setupPageCard {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 18px;
    }}
    QFrame#summaryItem, QFrame#sectionCard, QFrame#subCard, QFrame#statusCard {{
        background: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 16px;
    }}
    QFrame#subCard, QFrame#statusCard {{ background: {theme.surface_alt}; }}
    QLabel#pageTitle {{ font-size: 24px; font-weight: 800; color: {theme.accent}; }}
    QLabel#pageSubtitle {{ font-size: 13px; color: {theme.text_muted}; }}
    QLabel#summaryLabel {{ font-size: 11px; font-weight: 700; color: {theme.text_muted}; }}
    QLabel#summaryValue {{ font-size: 14px; font-weight: 700; color: {theme.text}; }}
    QLabel#sectionHeading {{ font-size: 13px; font-weight: 800; color: {theme.accent}; }}
    QLabel#hintLabel, QLabel#inlineHint {{ color: {theme.text_muted}; font-size: 12px; }}
    QLabel#statusCardTitle {{ color: {theme.text_muted}; font-size: 12px; font-weight: 700; }}
    QLabel#statusCardValue {{ color: {theme.text}; font-size: 15px; font-weight: 800; }}
    QLabel#activityText {{ color: {theme.text_subtle}; font-weight: 700; }}
    QLabel#readyBadge {{
        color: {theme.success};
        background: {theme.surface_alt};
        border: 1px solid {theme.border_strong};
        border-radius: 11px;
        padding: 5px 10px;
        font-weight: 800;
    }}
    QLabel#activityBadge {{
        min-width: 28px; max-width: 28px;
        min-height: 28px; max-height: 28px;
        border-radius: 14px;
        font-weight: 900;
        font-size: 15px;
        padding: 0;
    }}
    QListWidget#setupSteps {{ background: transparent; border: 0; outline: 0; }}
    QListWidget#setupSteps::item {{
        min-height: 34px;
        padding: 8px 12px;
        margin: 0 0 6px 0;
        border: 1px solid transparent;
        border-radius: 12px;
        font-weight: 700;
        color: {theme.text_muted};
    }}
    QListWidget#setupSteps::item:selected {{
        background: {theme.accent_soft};
        border: 1px solid {theme.accent_border};
        color: {theme.accent};
    }}
    QTabWidget#preferencesSubtabs::pane {{
        border: 1px solid {theme.border};
        border-radius: 18px;
        background: {theme.surface};
        margin-top: 8px;
    }}
    QTabWidget#preferencesSubtabs QTabBar {{ background: transparent; }}
    QTabWidget#preferencesSubtabs QWidget#preferencesGeneralPage,
    QTabWidget#preferencesSubtabs QWidget#preferencesSetupPage {{
        background: {theme.surface};
    }}
    QTabWidget#preferencesSubtabs QTabBar::tab {{
        background: {theme.surface_alt};
        color: {theme.text_muted};
        border: 1px solid {theme.border};
        border-bottom: 0;
        padding: 10px 16px;
        margin-right: 6px;
        border-top-left-radius: 12px;
        border-top-right-radius: 12px;
        font-weight: 700;
    }}
    QTabWidget#preferencesSubtabs QTabBar::tab:selected {{
        background: {theme.surface};
        color: {theme.accent};
        border-color: {theme.accent_border};
    }}
    QTabWidget#preferencesSubtabs QTabBar::tab:hover:!selected {{
        background: {theme.accent_soft};
    }}
    /* The scroll viewport and the stacked page keep the default palette
       colour unless they are told otherwise, which left a pale frame around
       every page in dark mode. */
    /* One accented button per page, so the main action is obvious. */
    QPushButton#primaryAction {{
        background: {theme.accent};
        color: {theme.window};
        border: 1px solid {theme.accent};
        font-weight: 800;
        padding: 9px 18px;
    }}
    QPushButton#primaryAction:hover {{
        background: {theme.accent_border};
        border: 1px solid {theme.accent};
        color: {theme.text};
    }}
    QPushButton#primaryAction:disabled {{
        background: {theme.disabled_surface};
        color: {theme.disabled_text};
        border: 1px solid {theme.border};
    }}
    QStackedWidget {{ background: {theme.window}; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollArea {{ background: {theme.window}; }}
    """


def heading_style(theme: Theme, size: int = 18) -> str:
    """Inline style for a section heading."""
    return f"font-size: {size}px; font-weight: 800; color: {theme.accent};"


def hint_style(theme: Theme) -> str:
    """Inline style for secondary explanatory text."""
    return f"color: {theme.text_muted};"


def badge_style(theme: Theme, kind: str) -> str:
    """Inline style for the small status pills in the setup assistant."""
    palettes = {
        "idle": (theme.text_muted, theme.surface_alt, theme.border_strong),
        "busy": (theme.accent, theme.accent_soft, theme.accent_border),
        "ok": (theme.success, theme.surface_alt, theme.border_strong),
        "error": (theme.danger, theme.surface_alt, theme.border_strong),
    }
    color, background, border = palettes.get(kind, palettes["idle"])
    return f"background: {background}; color: {color}; border: 1px solid {border};"
