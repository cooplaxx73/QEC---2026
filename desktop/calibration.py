"""
Calibration screen: "look at the dots".

Shows nine dots one at a time. While the patient looks at each dot we record
their gaze features, so gaze.GazeMapper can learn where they are looking.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

import time

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

# Dot positions as a fraction of the screen (0 = left/top, 1 = right/bottom).
POSITIONS = [0.08, 0.5, 0.92]
DOTS = [(x, y) for y in POSITIONS for x in POSITIONS]

SETTLE_SECONDS = 1.0   # time for the eyes to arrive at the dot
RECORD_SECONDS = 1.2   # time spent recording at each dot


class CalibrationScreen(QWidget):
    # Sends (features, targets, average face size) when all dots are done.
    finished = Signal(object, object, float)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background: black;")
        self.setCursor(Qt.BlankCursor)
        self.repaint_timer = QTimer(self, interval=30, timeout=self.update)

    def start(self) -> None:
        self.dot_index = 0
        self.dot_started = time.monotonic()
        self.features, self.targets, self.face_sizes = [], [], []
        self.showFullScreen()
        self.repaint_timer.start()

    def add_sample(self, features: np.ndarray, face_size: float) -> None:
        """Called for every camera frame while calibrating."""
        elapsed = time.monotonic() - self.dot_started
        if elapsed < SETTLE_SECONDS:
            return
        if elapsed < SETTLE_SECONDS + RECORD_SECONDS:
            self.features.append(features)
            self.targets.append(DOTS[self.dot_index])
            self.face_sizes.append(face_size)
            return
        # This dot is done. Move to the next one, or finish.
        self.dot_index += 1
        self.dot_started = time.monotonic()
        if self.dot_index == len(DOTS):
            self.repaint_timer.stop()
            self.hide()
            self.finished.emit(
                np.array(self.features), np.array(self.targets),
                float(np.mean(self.face_sizes)),
            )

    def paintEvent(self, event) -> None:
        if self.dot_index >= len(DOTS):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QColor("white"))
        painter.setFont(QFont("Arial", 22))
        painter.drawText(
            self.rect().adjusted(0, 0, 0, -60), Qt.AlignHCenter | Qt.AlignBottom,
            "Look at the dot and keep your head still",
        )

        x, y = DOTS[self.dot_index]
        centre = QPointF(x * self.width(), y * self.height())
        # The ring shrinks while we wait, then the dot turns green to record.
        elapsed = time.monotonic() - self.dot_started
        waiting = max(0.0, 1 - elapsed / SETTLE_SECONDS)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawEllipse(centre, 18 + 40 * waiting, 18 + 40 * waiting)
        painter.setBrush(QColor("#ffcc00") if waiting > 0 else QColor("#33dd66"))
        painter.drawEllipse(centre, 18, 18)
        painter.setBrush(QColor("black"))
        painter.drawEllipse(centre, 4, 4)
