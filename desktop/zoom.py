"""
Zoom by leaning towards the screen.

When the patient leans in, their face looks bigger to the camera. We then
show an enlarged picture of the area they were looking at. They sit back,
look at the (now much bigger) target and click it with a long blink. The
click is passed on to the real position on the screen.

The picture grows smoothly from the normal screen into the enlarged area,
so the patient can follow where it is going.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

from PySide6.QtCore import (QEasingCurve, QPoint, QRectF, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

import theme

LEAN_HOLD_SECONDS = 0.4    # ignore very short movements
ZOOM_TIMEOUT_SECONDS = 10  # the zoomed view closes by itself after this
ZOOM_IN_MILLISECONDS = 700   # time to grow into the zoomed view
ZOOM_OUT_MILLISECONDS = 350  # time to shrink back when it closes by itself


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
        self.close_timer = QTimer(self, singleShot=True, timeout=self.zoom_out)
        # "amount" runs from 0 (normal screen) to 1 (fully zoomed in).
        self.amount = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.set_amount)
        self.animation.finished.connect(self.on_animation_finished)

    def open_at_cursor(self, factor: float) -> None:
        screen = QGuiApplication.primaryScreen()
        self.full = screen.geometry()
        full = self.full
        # The area to enlarge: centred on the cursor, kept inside the screen.
        # Positions are measured from the top-left corner of the screen.
        width, height = full.width() / factor, full.height() / factor
        cursor = QCursor.pos() - full.topLeft()
        left = min(max(cursor.x() - width / 2, 0), full.width() - width)
        top = min(max(cursor.y() - height / 2, 0), full.height() - height)
        self.area = QRectF(left, top, width, height)
        self.picture = screen.grabWindow(0)  # a picture of the whole screen

        self.setGeometry(full)
        self.animate(0.0, 1.0, ZOOM_IN_MILLISECONDS)
        self.showFullScreen()
        self.close_timer.start(ZOOM_TIMEOUT_SECONDS * 1000)

    def zoom_out(self) -> None:
        """Nothing was clicked in time: shrink back, then close."""
        self.animate(self.amount, 0.0, ZOOM_OUT_MILLISECONDS)

    def animate(self, start: float, end: float, milliseconds: int) -> None:
        self.animation.stop()
        self.animation.setDuration(milliseconds)
        self.animation.setStartValue(start)
        self.animation.setEndValue(end)
        self.set_amount(start)
        self.animation.start()

    def set_amount(self, amount: float) -> None:
        self.amount = amount
        self.update()

    def on_animation_finished(self) -> None:
        if self.amount == 0.0:
            self.hide()

    def shown_area(self) -> QRectF:
        """The part of the screen that is on show right now. It slides from
        the whole screen (amount 0) to the enlarged area (amount 1)."""
        whole = QRectF(0, 0, self.full.width(), self.full.height())
        area, amount = self.area, self.amount
        return QRectF(
            whole.left() + (area.left() - whole.left()) * amount,
            whole.top() + (area.top() - whole.top()) * amount,
            whole.width() + (area.width() - whole.width()) * amount,
            whole.height() + (area.height() - whole.height()) * amount,
        )

    def mousePressEvent(self, event) -> None:
        # Convert the click in the big picture back to the real position.
        shown = self.shown_area()
        x = self.full.left() + shown.left() + event.position().x() * shown.width() / self.width()
        y = self.full.top() + shown.top() + event.position().y() * shown.height() / self.height()
        self.close_timer.stop()
        self.animation.stop()
        self.hide()
        self.target_chosen.emit(QPoint(int(x), int(y)))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        # The picture may have more pixels than the screen has points
        # (high-resolution screens), so scale the area to picture pixels.
        shown = self.shown_area()
        scale = self.picture.width() / self.full.width()
        source = QRectF(shown.left() * scale, shown.top() * scale,
                        shown.width() * scale, shown.height() * scale)
        painter.drawPixmap(QRectF(self.rect()), self.picture, source)
        # A green frame and a hint show that this is the zoomed view.
        painter.setPen(QPen(QColor(theme.GREEN), 6))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(3, 3, -3, -3))
        painter.fillRect(0, 0, self.width(), 52, QColor(theme.GREEN_DARK))
        painter.setPen(QColor(theme.WHITE))
        painter.setFont(theme.font(theme.SANS, 15, bold=True))
        painter.drawText(
            0, 0, self.width(), 52, Qt.AlignCenter,
            "Zoomed in. Sit back, look at your target and close your eyes to click.",
        )
