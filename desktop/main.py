"""
Starts the patient desktop program and connects all the parts.

Flow for every camera frame:
    camera.py  ->  gaze.py  ->  move the cursor
                   blink.py ->  click

Run with:  python main.py
Press F8 at any time to pause or resume eye control.

Libraries:
- PySide6 (Qt for Python) for windows and timers: https://doc.qt.io/qtforpython-6/
- pynput for mouse clicks and the F8 hotkey: https://pynput.readthedocs.io

Written with the assistance of Claude Code (Anthropic).
"""

import sys
import time

from pynput import keyboard, mouse
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from blink import BlinkClicker
from calibration import CalibrationScreen
from camera import FaceTracker
from config import load_settings
from gaze import (GazeMapper, OneEuroFilter, eyes_closed_amount, face_size,
                  gaze_features)

FREEZE_AFTER_BLINK_SECONDS = 0.25  # eyes need a moment to settle after opening


class CameraThread(QThread):
    """Reads the camera in the background so the screen never freezes."""

    face_ready = Signal(object)   # one FaceData per frame
    failed = Signal(str)

    def __init__(self, camera_index: int):
        super().__init__()
        self.camera_index = camera_index
        self.running = True

    def run(self) -> None:
        try:
            tracker = FaceTracker(self.camera_index)
        except Exception as error:
            self.failed.emit(str(error))
            return
        while self.running:
            data = tracker.read()
            if data is not None:
                self.face_ready.emit(data)
        tracker.close()

    def stop(self) -> None:
        self.running = False
        self.wait()


class EyeControl(QObject):
    """The main program: owns every part and passes data between them."""

    pause_pressed = Signal()  # sent from the hotkey thread to the main thread

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.mapper = GazeMapper()
        self.smoother = OneEuroFilter(self.settings.cursor_smoothing)
        self.clicker = BlinkClicker()
        self.mouse = mouse.Controller()
        self.paused = False
        self.frozen_until = 0.0
        self.resting_face_size = None  # face size at normal sitting distance

        self.calibration = CalibrationScreen()
        self.calibration.finished.connect(self.on_calibration_finished)

        self.camera = CameraThread(self.settings.camera_index)
        self.camera.face_ready.connect(self.on_face)
        self.camera.failed.connect(self.on_camera_failed)
        self.camera.start()

        # F8 pauses eye control, so a helper can always take the mouse back.
        self.pause_pressed.connect(self.toggle_pause)
        self.hotkeys = keyboard.Listener(on_press=self.on_key)
        self.hotkeys.start()

        self.start_calibration()

    # ----- calibration -----

    def start_calibration(self) -> None:
        self.calibration.start()

    def on_calibration_finished(self, features, targets, resting_face_size) -> None:
        self.mapper.fit(features, targets)
        self.resting_face_size = resting_face_size
        self.smoother = OneEuroFilter(self.settings.cursor_smoothing)

    # ----- every camera frame -----

    def on_face(self, face) -> None:
        if not face.found:
            return
        features = gaze_features(face)

        if self.calibration.isVisible():
            self.calibration.add_sample(features, face_size(face))
            return
        if self.paused or not self.mapper.ready:
            return

        now = time.monotonic()
        closed = eyes_closed_amount(face)
        wants_click = self.clicker.update(
            closed, now,
            self.settings.blink_threshold, self.settings.click_hold_seconds,
        )

        # Gaze is unreliable while the eyelids move, so hold the cursor still
        # during a blink and for a moment after it.
        eyelids_moving = closed > self.settings.blink_threshold * 0.6
        if eyelids_moving or self.clicker.eyes_closed:
            self.frozen_until = now + FREEZE_AFTER_BLINK_SECONDS
        if wants_click:
            self.click()
        elif now >= self.frozen_until:
            self.move_cursor(self.mapper.predict(features), now)

    def move_cursor(self, gaze_point: tuple[float, float], now: float) -> None:
        """gaze_point is (x, y) with 0 = left/top and 1 = right/bottom."""
        x, y = gaze_point
        # Sensitivity stretches movement away from the screen centre, for
        # patients whose eye movement range has become smaller.
        gain = self.settings.cursor_sensitivity
        x = 0.5 + (x - 0.5) * gain
        y = 0.5 + (y - 0.5) * gain
        x, y = self.smoother.update((x, y), now)
        x = min(max(x, 0.0), 1.0)
        y = min(max(y, 0.0), 1.0)

        screen = self.app.primaryScreen().geometry()
        QCursor.setPos(
            screen.x() + int(x * (screen.width() - 1)),
            screen.y() + int(y * (screen.height() - 1)),
        )

    def click(self) -> None:
        action = self.settings.blink_action
        button = mouse.Button.right if action == "right_click" else mouse.Button.left
        self.mouse.click(button, 2 if action == "double_click" else 1)

    # ----- pause, errors and shutdown -----

    def on_key(self, key) -> None:
        if key == keyboard.Key.f8:
            self.pause_pressed.emit()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        print("Eye control paused" if self.paused else "Eye control resumed")

    def on_camera_failed(self, message: str) -> None:
        self.calibration.hide()
        QMessageBox.critical(None, "Camera problem", message)
        self.app.quit()

    def shut_down(self) -> None:
        self.camera.stop()
        self.hotkeys.stop()


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    control = EyeControl(app)
    app.aboutToQuit.connect(control.shut_down)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
