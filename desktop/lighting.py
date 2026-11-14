"""
Dark-room help.

If the camera picture gets too dark to track the eyes, we use the screen as
a lamp: a white border lights up the face (the same trick phones use for
face unlock in the dark) and the screen brightness goes up.

The brightness is automatic. It rises one step at a time and stops as soon
as the camera can see well enough, so the screen is never brighter than the
room needs. When normal lighting persists for two seconds, the border
disappears and the original display brightness is restored.

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
BRIGHTNESS_STEP = 10       # how much the screen brightness changes at a time (%)
STEP_UP_SECONDS = 3        # wait between steps up, so the camera can react
RECOVERY_SECONDS = 2       # normal light must persist, rather than one bright frame
BRIGHT_AGAIN_MARGIN = 10   # modest hysteresis avoids getting stuck after room lights return


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
        self.changed_at = 0.0            # time of the last brightness step
        self.original_brightness = None  # what the patient had it set to
        self.current_brightness = None
        self.average = None              # smoothed camera brightness
        self.bright_since = None

    def update(self, brightness: float, threshold: int, now: float) -> None:
        """Call once per camera frame with the frame's average brightness."""
        # Smooth the reading so one dark frame does not trigger a change.
        if self.average is None:
            self.average = brightness
        self.average = 0.95 * self.average + 0.05 * brightness
        waited = now - self.changed_at

        if self.average < threshold:
            self.bright_since = None
            # Too dark: light the border, then add brightness a step at a time.
            if not self.active:
                self.turn_on(now)
            elif waited > STEP_UP_SECONDS:
                self.step(BRIGHTNESS_STEP, now)
        elif self.active and self.average >= min(255, threshold + BRIGHT_AGAIN_MARGIN):
            if self.bright_since is None:
                self.bright_since = now
            elif now - self.bright_since >= RECOVERY_SECONDS:
                # The border is a visibility aid, not part of the brightness
                # ramp. Remove it promptly and restore the original brightness.
                self.turn_off()
        else:
            self.bright_since = None
        # In between the two limits we leave the brightness where it is.

    def turn_on(self, now: float) -> None:
        self.active = True
        self.bright_since = None
        self.changed_at = now
        self.fill_light.show()
        try:
            self.original_brightness = sbc.get_brightness()[0]
            self.current_brightness = self.original_brightness
        except Exception:
            pass  # some monitors do not allow brightness control

    def step(self, amount: int, now: float) -> None:
        """Move the screen brightness up or down, between the patient's
        own setting and 100%."""
        if self.original_brightness is None:
            return
        target = self.current_brightness + amount
        target = min(max(target, self.original_brightness), 100)
        if target == self.current_brightness:
            return
        try:
            sbc.set_brightness(target)
            self.current_brightness = target
            self.changed_at = now
        except Exception:
            pass

    def at_original(self) -> bool:
        return (self.original_brightness is None
                or self.current_brightness <= self.original_brightness)

    def turn_off(self) -> None:
        self.active = False
        self.bright_since = None
        self.fill_light.hide()
        if self.original_brightness is not None:
            try:
                sbc.set_brightness(self.original_brightness)
            except Exception:
                pass
            self.original_brightness = None
            self.current_brightness = None
