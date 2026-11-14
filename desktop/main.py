"""
Starts the patient desktop program and connects all the parts.

Flow for every camera frame:
    camera.py  ->  gaze.py     ->  move the cursor
                   blink.py    ->  click
                   zoom.py     ->  zoom when leaning in
                   lighting.py ->  brighten the screen in a dark room

Run with:  python main.py
Press F8 at any time to pause or resume eye control, and F9 to quit.
Moving the real mouse also takes over: eye control lets go until the
mouse has been still for a moment.

Libraries:
- PySide6 (Qt for Python) for windows and timers: https://doc.qt.io/qtforpython-6/
- pynput for mouse clicks and the F8 hotkey: https://pynput.readthedocs.io

Written with the assistance of Claude Code (Anthropic).
"""

import math
import sys
import threading
import time
from collections import deque

from pynput import keyboard, mouse
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from activity_log import ActivityLog
from blink import BlinkClicker
from calibration import CalibrationScreen
from camera import FaceTracker
from caregiver_link import CaregiverLink
from config import apply_changes, load_settings, save_settings
from gaze import (GazeMapper, GazeSmoother, eyes_closed_amount, face_size,
                  gaze_features)
from keyboard import OnScreenKeyboard
from lighting import LowLightHelper
from overlay import (INSTRUCTIONS, ButtonBar, ChoicePopup, IncomingCallPopup,
                     NotificationsPanel, SettingsPanel, Toast)
from speech import Speaker
from telemetry import GazeSampler
from video_call import VideoWindow, frame_to_jpeg
from zoom import LeanDetector, ZoomView

FREEZE_AFTER_BLINK_SECONDS = 0.25  # eyes need a moment to settle after opening
GOOD_CALIBRATION = 0.07            # expected error below 7% of the screen

# The camera gives about 30 gaze readings a second. Moving the cursor only
# that often looks jerky, so a fast timer glides it towards the latest one.
GLIDE_TIMER_MILLISECONDS = 8       # about 120 small moves a second
GLIDE_SECONDS = 0.05               # how quickly the cursor catches up

# The gaze drifts as the eyelids start to close. A click goes to where the
# patient was looking this long before the blink began.
LOOK_BACK_SECONDS = 0.25

# The real mouse wins: if it moves, eye control lets go for this long.
MOUSE_HOLD_SECONDS = 2.0
MOUSE_MOVED_PIXELS = 4             # smaller differences are just rounding


def play_tone(hertz: int, milliseconds: int) -> None:
    """A short beep, played in the background so the cursor never pauses."""
    try:
        import winsound  # part of Python, but only on Windows
    except ImportError:
        QApplication.beep()
        return
    threading.Thread(
        target=winsound.Beep, args=(hertz, milliseconds), daemon=True).start()


def play_ready_sound() -> None:
    """Low and soft: the eyes have been closed long enough, open them to click."""
    play_tone(700, 40)


def play_click_sound() -> None:
    """Higher: the click went through."""
    play_tone(1200, 60)


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

    # Sent from the hotkey thread to the main thread.
    pause_pressed = Signal()
    quit_pressed = Signal()

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = load_settings()

        # Eye tracking parts
        self.mapper = GazeMapper()
        self.smoother = GazeSmoother(self.settings.cursor_smoothing)
        self.clicker = BlinkClicker()
        self.lean = LeanDetector()
        self.mouse = mouse.Controller()
        self.paused = False
        self.frozen_until = 0.0
        self.resting_face_size = None  # face size at normal sitting distance

        # Cursor movement
        self.target = None             # where the eyes say the cursor should be
        self.position = QPointF()      # where the cursor is while gliding there
        self.placed = None             # where this program last put the cursor
        self.mouse_until = 0.0         # the real mouse is in charge until then
        self.last_glide = time.monotonic()
        self.recent_targets = deque(maxlen=120)  # (time, target) for a few seconds
        self.glide_timer = QTimer(self, interval=GLIDE_TIMER_MILLISECONDS,
                                  timeout=self.glide_cursor)
        self.glide_timer.setTimerType(Qt.PreciseTimer)
        self.glide_timer.start()

        # Helpers
        self.log = ActivityLog()
        self.speaker = Speaker(self.settings)
        self.lighting = LowLightHelper()
        self.link = CaregiverLink(self.settings.backend_url)
        self.link.event_received.connect(self.on_caregiver_event)
        self.logging_enabled = False
        self.gaze_sampler = GazeSampler()
        self.tracking_found = None
        self.last_connection_notice = 0.0
        QTimer.singleShot(0, self.link.start)

        # Windows
        self.buttons = ButtonBar()
        self.buttons.call_clicked.connect(self.ask_to_call)
        # The four overlay buttons and the panels they open.
        self.keyboard = OnScreenKeyboard()
        self.keyboard.key_typed.connect(lambda: self.record("key"))
        self.buttons.keyboard_clicked.connect(self.keyboard.toggle)

        # Settings has three tabs: Instructions, Recalibrate, Turn off.
        self.settings_panel = SettingsPanel()
        self.buttons.settings_clicked.connect(self.settings_panel.toggle)
        self.settings_panel.read_aloud_clicked.connect(
            lambda: self.speaker.say(" ".join(INSTRUCTIONS)))
        self.settings_panel.recalibrate_clicked.connect(self.start_calibration)
        self.settings_panel.quit_clicked.connect(self.ask_to_quit)

        self.notifications = NotificationsPanel()
        self.unread = 0
        self.buttons.notifications_clicked.connect(self.open_notifications)
        self.notifications.read_aloud_clicked.connect(self.read_notifications)

        self.incoming_call = IncomingCallPopup()
        self.incoming_call.answered.connect(self.answer_video)
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

        # F8 pauses eye control and F9 quits, so a helper can always take
        # the mouse back.
        self.pause_pressed.connect(self.toggle_pause)
        self.quit_pressed.connect(self.app.quit)
        self.hotkeys = keyboard.Listener(on_press=self.on_key)
        self.hotkeys.start()

        self.record("session_start")
        self.start_calibration()

    # ----- calibration -----

    def reset_tracking(self) -> None:
        """Discard old movements and gestures when eye control is interrupted."""
        self.target = None
        self.recent_targets.clear()
        self.clicker = BlinkClicker()
        self.smoother = GazeSmoother(self.settings.cursor_smoothing)
        self.lean = LeanDetector()
        self.frozen_until = 0.0

    def start_calibration(self) -> None:
        self.reset_tracking()
        for window in (self.buttons, self.settings_panel, self.notifications,
                       self.keyboard):
            window.hide()
        self.calibration.start()

    def on_calibration_finished(self, features, targets, resting_face_size) -> None:
        # The expected error (fraction of the screen) is logged, so a doctor
        # can see if eye control gets less precise over time.
        error = self.mapper.fit(features, targets)
        self.record("calibration", error)
        self.resting_face_size = resting_face_size
        self.reset_tracking()
        self.buttons.show()

        if error <= GOOD_CALIBRATION:
            self.announce("Ready. Close both eyes for half a second to click.")
        else:
            self.announce(
                "Ready, but tracking may be rough. For better accuracy, light "
                "your face, keep your head still and recalibrate from Settings.",
                seconds=10)

    # ----- every camera frame -----

    def on_face(self, face) -> None:
        now = time.monotonic()
        if face.found != getattr(self, 'tracking_found', None):
            self.tracking_found = face.found
            self.record('tracking_resumed' if face.found else 'tracking_lost')
        if self.settings.low_light_enabled:
            self.lighting.update(face.brightness, self.settings.low_light_threshold, now)
        if self.link.video_active:
            self.link.my_frame = frame_to_jpeg(face.frame)
        if not face.found:
            self.reset_tracking()
            return

        features = gaze_features(face)
        closed = eyes_closed_amount(face)
        # Gaze is unreliable while the eyelids are moving.
        eyelids_moving = closed > self.settings.blink_threshold * 0.6

        if self.calibration.isVisible():
            self.calibration.add_sample(
                features, face_size(face), eyes_open=not eyelids_moving)
            return
        if self.paused or not self.mapper.ready:
            return
        if self.mouse_in_charge(now):
            # Mouse takeover also suspends eye gestures, including lean-to-zoom.
            # Nothing accumulated during the override should fire on resuming.
            self.reset_tracking()
            return

        wants_click = self.clicker.update(
            closed, now,
            self.settings.blink_threshold, self.settings.click_hold_seconds,
        )

        # Hold the cursor still during a blink and for a moment after it.
        if eyelids_moving or self.clicker.eyes_closed:
            self.frozen_until = now + FREEZE_AFTER_BLINK_SECONDS
        if self.clicker.just_ready and not self.mouse_in_charge(now):
            play_ready_sound()
        if wants_click:
            self.click(now)
        elif now >= self.frozen_until:
            self.aim_cursor(self.mapper.predict(features), now)

        leaned_in = self.lean.update(
            face_size(face), self.resting_face_size,
            self.settings.zoom_lean_ratio, now,
        )
        if leaned_in and self.settings.zoom_enabled and not self.zoom.isVisible():
            self.zoom.open_at_cursor(self.settings.zoom_factor)
            self.record("zoom")

    def aim_cursor(self, gaze_point: tuple[float, float], now: float) -> None:
        """Set where the cursor should go. glide_cursor() takes it there.

        gaze_point is (x, y) with 0 = left/top and 1 = right/bottom.
        """
        x, y = gaze_point
        # Sensitivity stretches movement away from the screen centre, for
        # patients whose eye movement range has become smaller.
        gain = self.settings.cursor_sensitivity
        x = 0.5 + (x - 0.5) * gain
        y = 0.5 + (y - 0.5) * gain
        x, y = self.smoother.update((x, y))
        x = min(max(x, 0.0), 1.0)
        y = min(max(y, 0.0), 1.0)

        screen = self.app.primaryScreen().geometry()
        self.target = QPointF(
            screen.x() + x * (screen.width() - 1),
            screen.y() + y * (screen.height() - 1),
        )
        self.recent_targets.append((now, self.target))
        if self.logging_enabled:
            cursor = QCursor.pos()
            sample = self.gaze_sampler.sample(gaze_point, (cursor.x(), cursor.y()),
                                              (screen.width(), screen.height()), now,
                                              (screen.x(), screen.y()))
            if sample:
                self.record('gaze', details=sample)

    def glide_cursor(self) -> None:
        """Runs about 120 times a second: move the cursor a little closer
        to the target, unless the real mouse is being used."""
        now = time.monotonic()
        actual = QCursor.pos()
        # If the cursor is not where we left it, someone moved the mouse.
        if (self.placed is not None
                and (actual - self.placed).manhattanLength() > MOUSE_MOVED_PIXELS):
            self.mouse_until = now + MOUSE_HOLD_SECONDS
            self.reset_tracking()

        waiting = (self.paused or self.target is None or self.calibration.isVisible()
                   or now < self.frozen_until or self.mouse_in_charge(now))
        if waiting:
            # Leave the cursor alone, but remember where it is.
            self.placed = actual
            self.position = QPointF(actual)
            self.last_glide = now
            return

        # Cover a share of the remaining distance. The share depends on the
        # time since the last move, so the speed is the same on any computer.
        share = 1 - math.exp(-(now - self.last_glide) / GLIDE_SECONDS)
        self.last_glide = now
        self.position += (self.target - self.position) * share
        self.place_cursor(self.position.toPoint())

    def place_cursor(self, point: QPoint) -> None:
        """Move the cursor and remember that it was us, not the mouse."""
        QCursor.setPos(point)
        self.placed = QCursor.pos()

    def mouse_in_charge(self, now: float) -> bool:
        return now < self.mouse_until

    def spot_before_blink(self):
        """Where the patient was looking just before they began to blink."""
        moment = self.clicker.last_started - LOOK_BACK_SECONDS
        for time_stamp, target in reversed(self.recent_targets):
            if time_stamp <= moment:
                return target
        return None

    def click(self, now: float) -> None:
        if self.mouse_in_charge(now):
            return  # a helper is using the mouse: do not click for them
        spot = self.spot_before_blink()
        if spot is not None:
            self.target = spot
            self.position = QPointF(spot)
            self.place_cursor(spot.toPoint())
        action = self.settings.blink_action
        button = mouse.Button.right if action == "right_click" else mouse.Button.left
        self.mouse.click(button, 2 if action == "double_click" else 1)
        play_click_sound()  # tells the patient the click went through
        # The blink length is logged: it shows how eyelid control is changing.
        self.record("click", self.clicker.last_duration, details=self.cursor_details(action))

    def click_zoom_target(self, target: QPoint) -> None:
        """The patient clicked in the zoomed view: click the real spot."""
        self.frozen_until = time.monotonic() + 0.6

        def click_real_spot():
            self.target = QPointF(target)
            self.position = QPointF(target)
            self.place_cursor(target)
            self.mouse.click(mouse.Button.left)
            self.record('click', details=self.cursor_details('zoom_left_click'))

        # Wait a moment so the zoomed view has disappeared first.
        QTimer.singleShot(200, click_real_spot)

    # ----- overlay buttons -----

    def open_notifications(self) -> None:
        self.unread = 0
        self.buttons.set_unread(0)
        self.notifications.toggle()

    def read_notifications(self) -> None:
        messages = [message for _, message in self.notifications.newest()]
        self.speaker.say(" ".join(messages) or "No notifications.")

    def ask(self, question: str, choices: list[str], on_choice) -> None:
        if self.popup is not None:
            self.popup.close()
        self.popup = ChoicePopup(question, choices, on_choice)

    def ask_to_call(self) -> None:
        self.ask("Call your caregiver?", ["Call", "Cancel"],
                 self.call_caregiver)

    def call_caregiver(self, choice: str) -> None:
        if choice == "Cancel":
            return
        self.link.send("/patient/call", {"video": choice == "Call with video"})
        self.record("call_caregiver", note=choice)
        self.announce("Your request is queued. Waiting for the care server.")

    def ask_to_quit(self) -> None:
        self.settings_panel.hide()
        self.ask("Turn off eye control?", ["Yes, turn off", "Cancel"],
                 lambda choice: self.app.quit() if choice != "Cancel" else None)

    # ----- caregiver events -----

    def on_caregiver_event(self, event: dict) -> None:
        kind = event["type"]
        if kind == "integration_ready":
            self.logging_enabled = bool(event.get("logging", False))
            apply_changes(self.settings, event["settings"])
            save_settings(self.settings)
            self.smoother.set_smoothing(self.settings.cursor_smoothing)
            self.notify("Connected to the care server. Your saved phone settings are loaded.")
            self.record("session_start")
        elif kind == "call_delivered":
            self.announce("Your caregiver notification was delivered to the care server.")
        elif kind == "caregiver_message":
            self.announce(event.get("message", "Your caregiver is asking to connect."))
        elif kind == "logging_changed":
            self.logging_enabled = bool(event.get('logging', False))
            self.notify('Patient activity logging is now ' + ('on.' if self.logging_enabled else 'off.'))
        elif kind == "connection_error":
            now = time.monotonic()
            if now - self.last_connection_notice > 30:
                self.last_connection_notice = now
                self.notify(event.get("message", "Care server unavailable."))
        elif kind == "settings_changed":
            self.on_settings_changed(event)
        elif kind == "video_request":
            # Ring like a phone until the patient accepts or declines.
            self.notify("Your caregiver asked for a video call.")
            self.speaker.say("Your caregiver would like a video call.")
            self.incoming_call.start_ringing()
        elif kind == "video_started":
            self.incoming_call.stop_ringing()
            self.link.video_active = True
            self.video.show()
            self.announce("Video call started. Your camera is on.")
        elif kind == "video_ended":
            self.incoming_call.stop_ringing()
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
        """Tell the patient something on screen and out loud, and keep it."""
        self.toast.show_message(text, seconds)
        self.speaker.say(text)
        self.notify(text)

    def notify(self, text: str) -> None:
        """Add a message to the Notifications panel and count it as unread."""
        self.notifications.add(time.strftime("%H:%M"), text)
        if not self.notifications.isVisible():
            self.unread += 1
            self.buttons.set_unread(self.unread)

    def cursor_details(self, action):
        screen = self.app.primaryScreen().geometry()
        cursor = QCursor.pos()
        return {'action': action, 'cursor_x': cursor.x(), 'cursor_y': cursor.y(),
                'screen_width': screen.width(), 'screen_height': screen.height(),
                'screen_left': screen.x(), 'screen_top': screen.y()}

    def record(self, kind: str, value: float = 0.0, note: str = "", details=None) -> None:
        """Save to the local log and send a copy to the backend."""
        if getattr(self, 'logging_enabled', False):
            self.link.send("/patient/logs", self.log.record(kind, value, note, details))

    # ----- pause, errors and shutdown -----

    def on_key(self, key) -> None:
        if key == keyboard.Key.f8:
            self.pause_pressed.emit()
        elif key == keyboard.Key.f9:
            self.quit_pressed.emit()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.record('paused' if self.paused else 'resumed')
        self.reset_tracking()
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
    from caregiver_link import DEVICE_FILE
    if not DEVICE_FILE.exists():
        QMessageBox.information(None, "Pair your desktop", "Run python connect.py first and sign in with the patient account. Then run python main.py again.")
        return
    control = EyeControl(app)
    app.aboutToQuit.connect(control.shut_down)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
