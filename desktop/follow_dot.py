"""
Follow-the-dot selection: choose a button by following a moving dot.

A small dot circles every button on our own windows. To choose a button
the patient follows its dot with their eyes for about a second and a half.
No blink is needed.

How it works:
- Every dot moves differently from the others (other starting point,
  other direction or other speed).
- We do not ask WHERE the patient is looking. We ask whether their eyes
  are MOVING the same way as one of the dots. That is measured with a
  correlation: +1 means "moving exactly together", 0 means "unrelated".
- A webcam is poor at telling where someone looks, but good at telling
  how the eyes move, so this is steadier than pointing at small targets.

Sources:
- Vidal, Bulling and Gellersen, "Pursuits: Spontaneous Interaction with
  Displays based on Smooth Pursuit Eye Movement and Moving Targets",
  UbiComp 2013. https://doi.org/10.1145/2493432.2493477
- Esteves et al., "Orbits: Gaze Interaction for Smart Watches using
  Smooth Pursuit Eye Movements", UIST 2015.
  https://doi.org/10.1145/2807442.2807499
- PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
- NumPy: https://numpy.org

Written with the assistance of Claude Code (Anthropic).
"""

import math
import time
from collections import deque

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from shiboken6 import isValid

import theme
from overlay import Card

WINDOW_SECONDS = 1.5      # how much recent eye movement we compare
EYE_DELAY_SECONDS = 0.15  # eyes trail a moving target by about this much
AVERAGE_OVER = 5          # eye readings averaged together to cut shake
MATCH_NEEDED = 0.8        # how alike the movements must be (1 = identical)
LEAD_NEEDED = 0.15        # and how far ahead of the next-best dot
HOLD_SECONDS = 0.35       # the match must last this long
REST_SECONDS = 1.5        # pause after a choice, so it cannot fire twice
NEAR_FRACTION = 0.45      # ignore buttons further than this share of the screen

ORBIT_GAP = 22            # space between a button's edge and its dot path
SMALLEST_ORBIT = 70       # a smaller path would be too hard to follow
DOT_RADIUS = 9

# Every dot gets one of these movements: (direction, starting angle, seconds
# per lap). Two dots are easy to tell apart when they start on opposite
# sides or go round in opposite directions.
MOVEMENTS = [
    (direction, start, lap)
    for lap in (2.4, 3.4)
    for direction in (1, -1)
    for start in (0.0, math.pi, math.pi / 2, 3 * math.pi / 2)
]


class Orbit:
    """One button and the dot that circles it."""

    def __init__(self, button: QPushButton, movement: tuple):
        self.button = button
        self.direction, self.start, self.lap = movement
        self.place()

    def place(self) -> None:
        """Work out where the button is on the screen right now."""
        size = self.button.size()
        middle = self.button.mapToGlobal(self.button.rect().center())
        self.centre = (middle.x(), middle.y())
        self.reach = (max(size.width() / 2 + ORBIT_GAP, SMALLEST_ORBIT),
                      max(size.height() / 2 + ORBIT_GAP, SMALLEST_ORBIT))

    def dot_position(self, moment):
        """Where the dot is at a time. Works for one time or an array."""
        angle = self.start + self.direction * 2 * math.pi * moment / self.lap
        return (self.centre[0] + self.reach[0] * np.cos(angle),
                self.centre[1] + self.reach[1] * np.sin(angle))


def how_alike(first: np.ndarray, second: np.ndarray) -> float:
    """Correlation of two lists of numbers: +1 together, 0 unrelated."""
    first = first - first.mean()
    second = second - second.mean()
    size = math.sqrt(float((first ** 2).sum()) * float((second ** 2).sum()))
    return float((first * second).sum() / size) if size > 1e-9 else 0.0


class DotMatcher:
    """Remembers recent eye positions and compares them with the dots."""

    def __init__(self):
        self.readings = deque()  # (time, x, y) in screen pixels

    def add(self, moment: float, x: float, y: float) -> None:
        self.readings.append((moment, x, y))
        while self.readings and moment - self.readings[0][0] > WINDOW_SECONDS:
            self.readings.popleft()

    def clear(self) -> None:
        self.readings.clear()

    def scores(self, orbits: list, screen_size: float) -> list[float]:
        """One number per orbit: how well the eyes are following its dot."""
        # Wait until we have nearly a full window of readings.
        if (len(self.readings) < 20
                or self.readings[-1][0] - self.readings[0][0] < WINDOW_SECONDS * 0.8):
            return [0.0] * len(orbits)
        moments, eye_x, eye_y = (np.array(column) for column in zip(*self.readings))
        # Average neighbouring readings: the shake goes, the movement stays.
        blur = np.ones(AVERAGE_OVER) / AVERAGE_OVER
        eye_x = np.convolve(eye_x, blur, mode="valid")
        eye_y = np.convolve(eye_y, blur, mode="valid")
        moments = np.convolve(moments, blur, mode="valid")

        results = []
        for orbit in orbits:
            distance = math.hypot(eye_x.mean() - orbit.centre[0],
                                  eye_y.mean() - orbit.centre[1])
            if distance > NEAR_FRACTION * screen_size:
                results.append(0.0)  # looking at another part of the screen
                continue
            dot_x, dot_y = orbit.dot_position(moments - EYE_DELAY_SECONDS)
            # Both the sideways and the up-down movement must match.
            results.append(min(how_alike(eye_x, dot_x), how_alike(eye_y, dot_y)))
        return results


class DotLayer(QWidget):
    """A see-through sheet over the whole screen that draws the dots.

    Clicks pass straight through it. Call add_gaze() for every camera frame.
    """

    chosen = Signal(object)  # the QPushButton whose dot was followed

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.matcher = DotMatcher()
        self.orbits = []
        self.leader = None          # the orbit the eyes follow best right now
        self.leader_strength = 0.0  # 0 = no match yet, 1 = strong enough
        self.leading_since = None
        self.resting_until = 0.0
        self.find_timer = QTimer(self, interval=250, timeout=self.find_buttons)
        self.draw_timer = QTimer(self, interval=16, timeout=self.update)

    # ----- on and off -----

    def start(self) -> None:
        self.setGeometry(QGuiApplication.primaryScreen().geometry())
        self.find_buttons()
        self.show()
        self.find_timer.start()
        self.draw_timer.start()

    def stop(self) -> None:
        self.find_timer.stop()
        self.draw_timer.stop()
        self.hide()
        self.forget()

    def forget(self) -> None:
        """Drop the eye movement collected so far (tracking was interrupted)."""
        self.matcher.clear()
        self.leader = None
        self.leader_strength = 0.0
        self.leading_since = None

    # ----- which buttons get a dot -----

    def find_buttons(self) -> None:
        """Give a dot to every button showing on our own windows."""
        buttons = [
            button
            for window in QApplication.topLevelWidgets()
            if isinstance(window, Card) and window.isVisible()
            for button in window.findChildren(QPushButton)
            if button.isVisible() and button.isEnabled()
        ]
        known = {orbit.button: orbit for orbit in self.orbits
                 if isValid(orbit.button) and orbit.button in buttons}
        taken = {(o.direction, o.start, o.lap) for o in known.values()}
        spare = [movement for movement in MOVEMENTS if movement not in taken]
        changed = len(known) != len(self.orbits)
        for button in buttons:
            if button not in known and spare:
                known[button] = Orbit(button, spare.pop(0))
                changed = True
        self.orbits = [known[button] for button in buttons if button in known]
        for orbit in self.orbits:
            orbit.place()  # windows may have moved
        if changed:
            self.forget()
            self.raise_()  # stay above windows that have just opened

    # ----- matching -----

    def add_gaze(self, x: float, y: float, now: float) -> None:
        """x and y are where the eyes point, in screen pixels."""
        self.matcher.add(now, x, y)
        if now < self.resting_until or not self.orbits:
            return
        scores = self.matcher.scores(self.orbits, self.width())
        ranked = sorted(range(len(scores)), key=lambda index: scores[index])
        best = ranked[-1]
        runner_up = scores[ranked[-2]] if len(ranked) > 1 else 0.0
        clear_lead = scores[best] - runner_up >= LEAD_NEEDED

        self.leader = self.orbits[best] if scores[best] > 0.4 and clear_lead else None
        self.leader_strength = min(1.0, max(0.0, (scores[best] - 0.4) / (MATCH_NEEDED - 0.4)))
        if self.leader is None or scores[best] < MATCH_NEEDED:
            self.leading_since = None
            return
        if self.leading_since is None:
            self.leading_since = now
        elif now - self.leading_since >= HOLD_SECONDS:
            button = self.leader.button
            self.forget()
            self.resting_until = now + REST_SECONDS
            self.chosen.emit(button)

    # ----- drawing -----

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        now = time.monotonic()
        corner = self.geometry().topLeft()
        for orbit in self.orbits:
            if not isValid(orbit.button):
                continue
            centre = QPointF(orbit.centre[0] - corner.x(), orbit.centre[1] - corner.y())
            path = QRectF(centre.x() - orbit.reach[0], centre.y() - orbit.reach[1],
                          2 * orbit.reach[0], 2 * orbit.reach[1])
            leading = orbit is self.leader

            # The path the dot travels: faint, or filling in green as the
            # match with the patient's eyes gets stronger.
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(42, 92, 72, 60), 2))
            painter.drawEllipse(path)
            if leading:
                painter.setPen(QPen(QColor(theme.GREEN), 6, Qt.SolidLine, Qt.RoundCap))
                painter.drawArc(path, 90 * 16, int(-360 * 16 * self.leader_strength))

            dot_x, dot_y = orbit.dot_position(now)
            dot = QPointF(float(dot_x) - corner.x(), float(dot_y) - corner.y())
            radius = DOT_RADIUS + (4 if leading else 0)
            painter.setPen(QPen(QColor(theme.WHITE), 3))
            painter.setBrush(QColor(theme.GREEN if leading else theme.LIME))
            painter.drawEllipse(dot, radius, radius)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.GREEN_DARK))
            painter.drawEllipse(dot, 3, 3)
