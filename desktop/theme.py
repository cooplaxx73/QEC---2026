"""
The look of the program, in one place: colours, fonts, icons and the
shared button styles. It follows the SignalSpeak website (cream, deep
green, serif headings) so the desktop program and the site feel like one
product.

Change a colour here and every window follows.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

from PySide6.QtCore import QByteArray, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

# ----- colours -----
CREAM = "#f7f7f2"       # window background
WHITE = "#ffffff"       # cards and keys
SAGE = "#e7ecdf"        # quiet buttons
SAGE_DEEP = "#cdd6c2"   # borders on quiet buttons
BORDER = "#dedfd4"      # hairlines
EDGE = "#eceee4"        # soft edge around white buttons
GREEN = "#2a5c48"       # main colour
GREEN_DARK = "#1e4435"  # main colour when pointed at
LIME = "#c9e265"        # highlight on green
INK = "#22302a"         # text
MUTED = "#66726a"       # secondary text
DANGER = "#a63d2f"      # decline, turn off
DANGER_DARK = "#86301f"

# ----- fonts -----
# The first font that is installed gets used, so this works on Windows,
# macOS and Linux.
SERIF = ["Georgia", "Charter", "DejaVu Serif"]
SANS = ["Segoe UI", "Helvetica Neue", "Noto Sans", "Arial"]
SERIF_CSS = ", ".join(f"'{name}'" for name in SERIF) + ", serif"
SANS_CSS = ", ".join(f"'{name}'" for name in SANS) + ", sans-serif"

HOVER_BORDER = 4   # thick, so the patient can see which button the cursor is on
SHADOW_MARGIN = 26  # clear space around a card for its shadow


def font(families: list, size: int, bold: bool = False) -> QFont:
    """A font for drawing with QPainter."""
    result = QFont()
    result.setFamilies(families)
    result.setPointSize(size)
    result.setBold(bold)
    return result


# ----- buttons -----
# (background, text, border, background when pointed at, border when pointed at)
BUTTON_KINDS = {
    "primary": (GREEN, WHITE, GREEN, GREEN_DARK, LIME),
    "secondary": (SAGE, INK, SAGE, SAGE, GREEN),
    "plain": (WHITE, INK, EDGE, WHITE, GREEN),
    "danger": (DANGER, WHITE, DANGER, DANGER_DARK, INK),
}


def button_style(kind: str, font_size: int = 22, radius: int = 16) -> str:
    background, text, border, hover_background, hover_border = BUTTON_KINDS[kind]
    return (
        f"QPushButton {{ background: {background}; color: {text};"
        f" font-family: {SANS_CSS}; font-size: {font_size}px; font-weight: 600;"
        f" border: {HOVER_BORDER}px solid {border}; border-radius: {radius}px; }}"
        f"QPushButton:hover {{ background: {hover_background};"
        f" border-color: {hover_border}; }}"
        f"QPushButton:pressed {{ background: {hover_border}; }}"
    )


# ----- icons -----
# Drawn on a 24 x 24 grid. "currentColor" is swapped for a real colour.

def _line(width: float = 1.8) -> str:
    """The shared attributes for an outline shape."""
    return (f'fill="none" stroke="currentColor" stroke-width="{width}"'
            ' stroke-linecap="round" stroke-linejoin="round"')


_GEAR_TEETH = "".join(
    f'<line x1="12" y1="2.6" x2="12" y2="4.6" transform="rotate({angle} 12 12)"/>'
    for angle in range(0, 360, 45))

ICONS = {
    # A handset: a thin curved neck with a thick ear and mouth piece.
    "phone": f'<path {_line(2.6)} d="M7.2 6.8 C7.4 12.6 11.4 16.6 17.2 16.8"/>'
             f'<path {_line(5)} d="M7 5.2v2.6M16.2 17h2.6"/>',
    "keyboard": f'<g {_line()}><rect x="2.5" y="6" width="19" height="12" rx="2.6"/>'
                '<path d="M6.5 10h.01M10.2 10h.01M13.8 10h.01M17.5 10h.01'
                'M6.5 13.6h.01M17.5 13.6h.01M9.5 14h5"/></g>',
    "gear": f'<g {_line()}><circle cx="12" cy="12" r="6.2"/>'
            '<circle cx="12" cy="12" r="2.4"/></g>'
            f'<g {_line(2.6)}>{_GEAR_TEETH}</g>',
    "bell": f'<g {_line()}><path d="M6.2 16.2v-5a5.8 5.8 0 0 1 11.6 0v5l1.5 2.2H4.7z"/>'
            '<path d="M10.2 20.6a1.9 1.9 0 0 0 3.6 0M12 3v2.2"/></g>',
    "left": f'<path {_line(2.4)} d="M14.5 6l-6 6 6 6"/>',
    "right": f'<path {_line(2.4)} d="M9.5 6l6 6-6 6"/>',
}


def icon_pixmap(name: str, colour: str, size: int) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'{ICONS[name]}</svg>').replace("currentColor", colour)
    # Drawn at twice the size so it stays sharp on high-resolution screens.
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size * 2, size * 2))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


def icon(name: str, colour: str, size: int) -> QIcon:
    return QIcon(icon_pixmap(name, colour, size))


# ----- effects -----

def add_shadow(widget: QWidget) -> None:
    """A soft shadow under a card, so it lifts off whatever is behind it."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(40)
    shadow.setOffset(0, 8)
    shadow.setColor(QColor(20, 40, 30, 70))
    widget.setGraphicsEffect(shadow)


def fade_in(window: QWidget, milliseconds: int = 150) -> None:
    """Show a window with a short fade instead of a hard pop."""
    window.setWindowOpacity(0)
    window.show()
    animation = QPropertyAnimation(window, b"windowOpacity", window)
    animation.setDuration(milliseconds)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    animation.start(QPropertyAnimation.DeleteWhenStopped)
