"""
On-screen keyboard with large keys.

Clicking a key types it into whichever app the patient is using. The
keyboard window never takes focus, so the text goes to the right place.

Libraries:
- PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
- pynput to send the key presses: https://pynput.readthedocs.io

Written with the assistance of Claude Code (Anthropic).
"""

from pynput.keyboard import Controller, Key
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

import theme
from overlay import OVERLAY_FLAGS, screen_area

KEY_HEIGHT = 92
BUTTON_BAR_WIDTH = 176  # space left free for the overlay buttons

LAYOUTS = {
    "letters": [
        list("qwertyuiop") + ["Back"],
        list("asdfghjkl") + ["'", "Enter"],
        ["Shift"] + list("zxcvbnm") + [",", ".", "?"],
        ["123", "Space", "Hide"],
    ],
    "numbers": [
        list("1234567890") + ["Back"],
        list("-/:;()$&@") + ['"', "Enter"],
        list("!#%*+=_~") + [",", ".", "?"],
        ["ABC", "Space", "Hide"],
    ],
}

# Keys that do something other than type a character are tinted, so the
# letters are easy to tell apart from them.
ACTION_KEYS = {"Back", "Enter", "Shift", "123", "ABC", "Hide"}

# Keys that are not a single character.
SPECIAL_KEYS = {"Back": Key.backspace, "Enter": Key.enter, "Space": Key.space}


class OnScreenKeyboard(QWidget):
    key_typed = Signal()  # for the activity log (we never log which key)

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setObjectName("keyboard")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(
            f"#keyboard {{ background: {theme.CREAM};"
            f" border-top: 1px solid {theme.SAGE_DEEP}; }}")
        self.typist = Controller()
        self.shift_on = False
        self.rows = QVBoxLayout(self)
        self.rows.setSpacing(8)
        self.rows.setContentsMargins(12, 12, 12, 12)
        self.show_layout("letters")

        # Dock along the bottom, leaving room for the overlay buttons.
        area = screen_area()
        height = 4 * KEY_HEIGHT + 48
        self.setGeometry(
            area.x(), area.bottom() - height,
            area.width() - BUTTON_BAR_WIDTH, height,
        )

    def show_layout(self, name: str) -> None:
        """Replace the keys with the letters or numbers layout."""
        self.layout_name = name
        while self.rows.count():
            row = self.rows.takeAt(0).layout()
            while row.count():
                row.takeAt(0).widget().deleteLater()
            row.deleteLater()

        for keys in LAYOUTS[name]:
            row = QHBoxLayout()
            row.setSpacing(8)
            for key in keys:
                row.addWidget(self.make_key(key), 6 if key == "Space" else 1)
            self.rows.addLayout(row)

    def make_key(self, key: str) -> QPushButton:
        label = key.upper() if self.shift_on and len(key) == 1 else key
        button = QPushButton(label)
        button.setFixedHeight(KEY_HEIGHT)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setFocusPolicy(Qt.NoFocus)
        if key == "Enter" or (key == "Shift" and self.shift_on):
            kind = "primary"
        elif key in ACTION_KEYS:
            kind = "secondary"
        else:
            kind = "plain"
        font_size = 28 if len(key) == 1 else 22
        button.setStyleSheet(theme.button_style(kind, font_size, radius=14))
        button.clicked.connect(lambda checked=False, k=key: self.press(k))
        return button

    def press(self, key: str) -> None:
        if key == "Hide":
            self.hide()
        elif key in ("123", "ABC"):
            self.show_layout("numbers" if key == "123" else "letters")
        elif key == "Shift":
            self.shift_on = not self.shift_on
            self.show_layout(self.layout_name)
        elif key in SPECIAL_KEYS:
            self.typist.tap(SPECIAL_KEYS[key])
            self.key_typed.emit()
        else:
            self.typist.type(key.upper() if self.shift_on else key)
            self.key_typed.emit()
            if self.shift_on:  # shift only applies to one letter
                self.shift_on = False
                self.show_layout(self.layout_name)

    def toggle(self) -> None:
        self.setVisible(not self.isVisible())
