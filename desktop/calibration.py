"""
Calibration screen: "look at the dots".

Shows 13 dots one at a time. While the patient looks at each dot we record
their gaze features, so gaze.GazeMapper can learn where they are looking.

To keep the data clean we skip frames where the eyes are closing, and for
each dot we keep only the steadiest half of the samples.

Libraries:
- PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
- NumPy: https://numpy.org

Written with the assistance of Claude Code (Anthropic).
"""

import time

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

# Dot positions as a fraction of the screen (0 = left/top, 1 = right/bottom).
# A 3 x 3 grid near the edges, plus 4 dots in between for extra detail.
EDGES = [0.08, 0.5, 0.92]
DOTS = [(x, y) for y in EDGES for x in EDGES]
DOTS += [(0.29, 0.29), (0.71, 0.29), (0.29, 0.71), (0.71, 0.71)]

SETTLE_SECONDS = 1.0   # time for the eyes to arrive at the dot
RECORD_SECONDS = 1.2   # time spent recording at each dot


def steadiest_half(samples: np.ndarray) -> np.ndarray:
    """Keep the half of the samples closest to the typical (median) one.

    This throws away moments when the eyes wandered off the dot.
    """
    spread = samples.std(axis=0) + 1e-6
    distance = (np.abs(samples - np.median(samples, axis=0)) / spread).sum(axis=1)
    return samples[distance <= np.median(distance)]


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
        self.samples = [[] for _ in DOTS]   # gaze features recorded per dot
        self.face_sizes = []
        self.showFullScreen()
        self.repaint_timer.start()

    def add_sample(self, features: np.ndarray, face_size: float, eyes_open: bool) -> None:
        """Called for every camera frame while calibrating."""
        elapsed = time.monotonic() - self.dot_started
        if elapsed < SETTLE_SECONDS:
            return
        if elapsed < SETTLE_SECONDS + RECORD_SECONDS:
            if eyes_open:  # gaze is unreliable during a blink
                self.samples[self.dot_index].append(features)
                self.face_sizes.append(face_size)
            return
        # This dot is done. Move to the next one, or finish.
        self.dot_index += 1
        self.dot_started = time.monotonic()
        if self.dot_index == len(DOTS):
            self.finish()

    def finish(self) -> None:
        self.repaint_timer.stop()
        self.hide()
        features, targets = [], []
        for dot, samples in zip(DOTS, self.samples):
            if len(samples) >= 4:  # skip a dot if the face was lost
                kept = steadiest_half(np.array(samples))
                features.extend(kept)
                targets.extend([dot] * len(kept))
        self.finished.emit(
            np.array(features), np.array(targets), float(np.mean(self.face_sizes)))

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
