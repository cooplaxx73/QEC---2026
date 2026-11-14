"""
Zoom by leaning towards the screen.

When the patient leans in, their face looks bigger to the camera. We then
show an enlarged picture of the area they were looking at. They sit back,
look at the (now much bigger) target and click it with a long blink. The
click is passed on to the real position on the screen.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

LEAN_HOLD_SECONDS = 0.4    # ignore very short movements
ZOOM_TIMEOUT_SECONDS = 10  # the zoomed view closes by itself after this


class LeanDetector:
    """Notices when the patient leans towards the screen."""

    def __init__(self):
        self.lean_started = None  # time the lean began, or None
        self.already_fired = False

    def update(self, size: float, resting_size: float, ratio: float, now: float) -> bool:
        """Returns True once per lean, after it has been held briefly."""
        if size < resting_size * ratio:
            # Sitting back again: get ready for the next lean.
            self.lean_started = None
            self.already_fired = False
            return False
        if self.lean_started is None:
            self.lean_started = now
        if not self.already_fired and now - self.lean_started >= LEAN_HOLD_SECONDS:
            self.already_fired = True
            return True
        return False


class ZoomView(QWidget):
    """A full-screen enlarged picture of one part of the screen."""

    target_chosen = Signal(QPoint)  # the real screen position that was clicked

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.close_timer = QTimer(self, singleShot=True, timeout=self.hide)

    def open_at_cursor(self, factor: float) -> None:
        screen = QGuiApplication.primaryScreen()
        full = screen.geometry()
        # The area to enlarge: centred on the cursor, kept inside the screen.
        width, height = int(full.width() / factor), int(full.height() / factor)
        cursor = QCursor.pos()
        left = min(max(cursor.x() - width // 2, full.left()), full.right() - width)
        top = min(max(cursor.y() - height // 2, full.top()), full.bottom() - height)
        self.area = QRect(left, top, width, height)
        self.picture = screen.grabWindow(
            0, left - full.left(), top - full.top(), width, height)

        self.setGeometry(full)
        self.showFullScreen()
        self.close_timer.start(ZOOM_TIMEOUT_SECONDS * 1000)

    def mousePressEvent(self, event) -> None:
        # Convert the click in the big picture back to the real position.
        x = self.area.left() + event.position().x() * self.area.width() / self.width()
        y = self.area.top() + event.position().y() * self.area.height() / self.height()
        self.close_timer.stop()
        self.hide()
        self.target_chosen.emit(QPoint(int(x), int(y)))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.picture)
        # A yellow frame and a hint show that this is the zoomed view.
        painter.setPen(QColor("#ffeb3b"))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(2, 2, -3, -3))
        painter.setFont(QFont("Arial", 16, QFont.Bold))
        painter.fillRect(0, 0, self.width(), 40, QColor(0, 0, 0, 180))
        painter.drawText(
            0, 0, self.width(), 40, Qt.AlignCenter,
            "Zoomed in. Sit back, look at your target and close your eyes to click.",
        )
