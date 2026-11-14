"""
Small video window in the corner of the screen during a caregiver call.

It only appears after BOTH the patient and the caregiver have accepted.

Libraries:
- PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
- OpenCV to shrink and compress camera frames: https://opencv.org

Written with the assistance of Claude Code (Anthropic).
"""

import cv2
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from overlay import GREY, OVERLAY_FLAGS, PANEL_STYLE, make_button, screen_area

VIDEO_WIDTH, VIDEO_HEIGHT = 360, 270


def frame_to_jpeg(frame) -> bytes:
    """Shrink a camera frame and compress it for sending."""
    small = cv2.resize(frame, (320, 240))
    ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return jpeg.tobytes()


class VideoWindow(QWidget):
    end_clicked = Signal()

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setStyleSheet(PANEL_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.picture = QLabel("Connecting to caregiver...")
        self.picture.setFixedSize(VIDEO_WIDTH, VIDEO_HEIGHT)
        self.picture.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.picture)
        layout.addWidget(make_button(
            "End call", GREY, self.end_clicked.emit, VIDEO_WIDTH, 80))
        self.adjustSize()
        # Top-right corner, away from the two overlay buttons.
        area = screen_area()
        self.move(area.right() - self.width() - 10, area.top() + 10)

    def show_frame(self, jpeg: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(jpeg):
            self.picture.setPixmap(pixmap.scaled(
                VIDEO_WIDTH, VIDEO_HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation))
