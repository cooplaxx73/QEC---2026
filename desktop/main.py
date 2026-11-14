"""
Starts the patient desktop program and connects all the parts.

Flow for every camera frame:
    camera.py  ->  gaze.py     ->  move the cursor
                   blink.py    ->  click
                   zoom.py     ->  zoom when leaning in
                   lighting.py ->  brighten the screen in a dark room

Run with:  python main.py
Press F8 at any time to pause or resume eye control.

Libraries:
- PySide6 (Qt for Python) for windows and timers: https://doc.qt.io/qtforpython-6/
- pynput for mouse clicks and the F8 hotkey: https://pynput.readthedocs.io
- NumPy: https://numpy.org

Written with the assistance of Claude Code (Anthropic).
"""

import sys
import time

import numpy as np
from pynput import keyboard, mouse
from PySide6.QtCore import QObject, QPoint, QThread, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from activity_log import ActivityLog
from blink import BlinkClicker
from calibration import CalibrationScreen
from camera import FaceTracker
from caregiver_link import CaregiverLink
from config import apply_changes, load_settings, save_settings
from gaze import (GazeMapper, OneEuroFilter, eyes_closed_amount, face_size,
                  gaze_features)
from keyboard import OnScreenKeyboard
from lighting import LowLightHelper
from overlay import INSTRUCTIONS, ButtonBar, ChoicePopup, InstructionsPanel, Toast
from speech import Speaker
from video_call import VideoWindow, frame_to_jpeg
from zoom import LeanDetector, ZoomView

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

        # Eye tracking parts
        self.mapper = GazeMapper()
        self.smoother = OneEuroFilter(self.settings.cursor_smoothing)
        self.clicker = BlinkClicker()
        self.lean = LeanDetector()
        self.mouse = mouse.Controller()
        self.paused = False
        self.frozen_until = 0.0
        self.resting_face_size = None  # face size at normal sitting distance

        # Helpers
        self.log = ActivityLog()
        self.speaker = Speaker(self.settings)
        self.lighting = LowLightHelper()
        self.link = CaregiverLink(self.settings.backend_url)
        self.link.event_received.connect(self.on_caregiver_event)

        # Windows
        self.buttons = ButtonBar()
        self.buttons.call_clicked.connect(self.ask_to_call)
        self.instructions = InstructionsPanel()
        self.buttons.instructions_clicked.connect(self.instructions.toggle)
        self.instructions.read_aloud_clicked.connect(
            lambda: self.speaker.say(" ".join(INSTRUCTIONS)))
        self.instructions.recalibrate_clicked.connect(self.start_calibration)
        self.instructions.quit_clicked.connect(self.ask_to_quit)
        self.keyboard = OnScreenKeyboard()
        self.keyboard.key_typed.connect(lambda: self.record("key"))
        self.instructions.keyboard_clicked.connect(self.open_keyboard)
        self.toast = Toast()
        self.popup = None
        self.zoom = ZoomView()
        self.zoom.target_chosen.connect(self.click_zoom_target)
        self.video = VideoWindow()
        self.video.end_clicked.connect(lambda: self.answer_video("end"))
        self.link.frame_received.connect(self.video.show_frame)
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

        self.record("session_start")
        self.start_calibration()

    # ----- calibration -----

    def start_calibration(self) -> None:
        for window in (self.buttons, self.instructions, self.keyboard):
            window.hide()
        self.calibration.start()

    def on_calibration_finished(self, features, targets, resting_face_size) -> None:
        self.mapper.fit(features, targets)
        self.resting_face_size = resting_face_size
        self.smoother = OneEuroFilter(self.settings.cursor_smoothing)
        self.buttons.show()

        # How far off the fit is, as a fraction of the screen. Logged so a
        # doctor can see if eye control gets less precise over time.
        guesses = np.array([self.mapper.predict(row) for row in features])
        self.record("calibration", float(np.abs(guesses - targets).mean()))
        self.announce("Ready. Close both eyes for half a second to click.")

    # ----- every camera frame -----

    def on_face(self, face) -> None:
        now = time.monotonic()
        if self.settings.low_light_enabled:
            self.lighting.update(face.brightness, self.settings.low_light_threshold, now)
        if self.link.video_active:
            self.link.my_frame = frame_to_jpeg(face.frame)
        if not face.found:
            return

        features = gaze_features(face)
        if self.calibration.isVisible():
            self.calibration.add_sample(features, face_size(face))
            return
        if self.paused or not self.mapper.ready:
            return

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

        leaned_in = self.lean.update(
            face_size(face), self.resting_face_size,
            self.settings.zoom_lean_ratio, now,
        )
        if leaned_in and self.settings.zoom_enabled and not self.zoom.isVisible():
            self.zoom.open_at_cursor(self.settings.zoom_factor)
            self.record("zoom")

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
        # The blink length is logged: it shows how eyelid control is changing.
        self.record("click", self.clicker.last_duration)

    def click_zoom_target(self, target: QPoint) -> None:
        """The patient clicked in the zoomed view: click the real spot."""
        self.frozen_until = time.monotonic() + 0.6

        def click_real_spot():
            QCursor.setPos(target)
            self.mouse.click(mouse.Button.left)

        # Wait a moment so the zoomed view has disappeared first.
        QTimer.singleShot(200, click_real_spot)

    # ----- overlay buttons -----

    def open_keyboard(self) -> None:
        self.instructions.hide()
        self.keyboard.show()

    def ask(self, question: str, choices: list[str], on_choice) -> None:
        if self.popup is not None:
            self.popup.close()
        self.popup = ChoicePopup(question, choices, on_choice)

    def ask_to_call(self) -> None:
        self.ask("Call your caregiver?", ["Call", "Call with video", "Cancel"],
                 self.call_caregiver)

    def call_caregiver(self, choice: str) -> None:
        if choice == "Cancel":
            return
        self.link.send("/patient/call", {"video": choice == "Call with video"})
        self.record("call_caregiver", note=choice)
        self.announce("Your caregiver has been notified.")

    def ask_to_quit(self) -> None:
        self.instructions.hide()
        self.ask("Turn off eye control?", ["Yes, turn off", "Cancel"],
                 lambda choice: self.app.quit() if choice != "Cancel" else None)

    # ----- caregiver events -----

    def on_caregiver_event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "settings_changed":
            self.on_settings_changed(event)
        elif kind == "video_request":
            question = "Your caregiver would like a video call. Turn on your camera?"
            self.speaker.say(question)
            self.ask(question, ["Accept", "Decline"],
                     lambda choice: self.answer_video(choice.lower()))
        elif kind == "video_started":
            self.link.video_active = True
            self.video.show()
            self.announce("Video call started. Your camera is on.")
        elif kind == "video_ended":
            self.link.video_active = False
            self.link.my_frame = None
            self.video.hide()
            self.announce("Video call ended. Your camera is not shared.")

    def answer_video(self, action: str) -> None:
        """action is accept, decline or end."""
        self.link.send("/patient/video", {"action": action})
        self.record("video_" + action)

    def on_settings_changed(self, event: dict) -> None:
        """The caregiver changed settings remotely: apply and tell the patient."""
        try:
            applied = apply_changes(self.settings, event.get("changes", {}))
        except (TypeError, ValueError):
            return  # ignore values that make no sense
        if not applied:
            return
        save_settings(self.settings)
        self.smoother.set_smoothing(self.settings.cursor_smoothing)
        changes = ", ".join(
            f"{name.replace('_', ' ')} is now {value}" for name, value in applied.items())
        self.record("settings_changed", note=changes)
        self.announce(f"Your caregiver changed your settings: {changes}.", seconds=10)

    # ----- small helpers -----

    def announce(self, text: str, seconds: float = 6) -> None:
        """Tell the patient something on screen and out loud."""
        self.toast.show_message(text, seconds)
        self.speaker.say(text)

    def record(self, kind: str, value: float = 0.0, note: str = "") -> None:
        """Save to the local log and send a copy to the backend."""
        self.link.send("/patient/logs", self.log.record(kind, value, note))

    # ----- pause, errors and shutdown -----

    def on_key(self, key) -> None:
        if key == keyboard.Key.f8:
            self.pause_pressed.emit()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.toast.show_message(
            "Eye control paused. Press F8 to resume." if self.paused
            else "Eye control resumed.")

    def on_camera_failed(self, message: str) -> None:
        self.calibration.hide()
        QMessageBox.critical(None, "Camera problem", message)
        self.app.quit()

    def shut_down(self) -> None:
        self.record("session_end")
        self.lighting.turn_off()
        self.camera.stop()
        self.hotkeys.stop()
        time.sleep(0.5)  # give the link a moment to send the last log entry
        self.link.stop()


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    control = EyeControl(app)
    app.aboutToQuit.connect(control.shut_down)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
