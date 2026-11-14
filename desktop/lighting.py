"""
Dark-room help.

If the camera picture gets too dark to track the eyes, we use the screen as
a lamp: brightness goes to 100% and a white border lights up the face
(the same trick phones use for face unlock in the dark).

Libraries:
- screen-brightness-control: https://github.com/Crozzers/screen_brightness_control
- PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/

Written with the assistance of Claude Code (Anthropic).
"""

import screen_brightness_control as sbc
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

BORDER_WIDTH = 70          # pixels of white around the screen edge
MIN_BOOST_SECONDS = 60     # stay boosted at least this long (stops flicker)
BRIGHT_AGAIN_MARGIN = 40   # how much brighter the room must get to turn off


class FillLight(QWidget):
    """A white border around the screen. Clicks pass straight through it."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(QGuiApplication.primaryScreen().geometry())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor("white"), BORDER_WIDTH * 2))  # half is off-screen
        painter.drawRect(self.rect())


class LowLightHelper:
    def __init__(self):
        self.fill_light = FillLight()
        self.active = False
        self.boosted_at = 0.0
        self.original_brightness = None
        self.average = None  # smoothed camera brightness

    def update(self, brightness: float, threshold: int, now: float) -> None:
        """Call once per camera frame with the frame's average brightness."""
        # Smooth the reading so one dark frame does not trigger the boost.
        if self.average is None:
            self.average = brightness
        self.average = 0.95 * self.average + 0.05 * brightness

        if not self.active and self.average < threshold:
            self.turn_on(now)
        elif (self.active and now - self.boosted_at > MIN_BOOST_SECONDS
              and self.average > threshold + BRIGHT_AGAIN_MARGIN):
            self.turn_off()

    def turn_on(self, now: float) -> None:
        self.active = True
        self.boosted_at = now
        self.fill_light.show()
        try:
            self.original_brightness = sbc.get_brightness()[0]
            sbc.set_brightness(100)
        except Exception:
            pass  # some monitors do not allow brightness control

    def turn_off(self) -> None:
        self.active = False
        self.fill_light.hide()
        if self.original_brightness is not None:
            try:
                sbc.set_brightness(self.original_brightness)
            except Exception:
                pass
            self.original_brightness = None
