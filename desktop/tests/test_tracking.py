"""Tracking interruptions must cancel stale movements and incomplete gestures."""

from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, QPointF

from blink import BlinkClicker
from config import Settings
from gaze import GazeSmoother
from zoom import LeanDetector

# Importing the Windows brightness driver queries monitor hardware through WMI.
# These controller tests neither need that hardware nor change its brightness.
with patch.dict("sys.modules", {"screen_brightness_control": Mock()}):
    import main as controller
    from main import EyeControl


class TrackingInterruptions(unittest.TestCase):
    def setUp(self):
        # Exercise controller methods without opening a camera or moving the mouse.
        self.control = SimpleNamespace(
            settings=Settings(low_light_enabled=False),
            target=QPointF(400, 300),
            recent_targets=deque([(1.0, QPointF(400, 300))]),
            clicker=BlinkClicker(),
            smoother=GazeSmoother(),
            lean=LeanDetector(),
            frozen_until=10.0,
            paused=False,
            toast=Mock(),
            link=SimpleNamespace(video_active=False),
            ability_test=Mock(**{"isVisible.return_value": False}),
            record=Mock(),
            lighting=Mock(active=False),
        )
        self.control.reset_tracking = lambda: EyeControl.reset_tracking(self.control)
        self.control.hide_windows = lambda: EyeControl.hide_windows(self.control)
        self.control.clicker.update(1.0, 1.0, 0.5, 0.6)
        self.control.smoother.update((0.1, 0.2))
        self.control.lean.update(1.5, 1.0, 1.18, 1.0)

    def assert_tracking_cleared(self):
        self.assertIsNone(self.control.target)
        self.assertFalse(self.control.recent_targets)
        # Reappearing with open eyes must not complete the interrupted blink.
        self.assertFalse(self.control.clicker.update(0.0, 2.0, 0.5, 0.6))
        self.assertEqual(self.control.smoother.update((0.8, 0.9)), (0.8, 0.9))
        self.assertFalse(self.control.lean.update(1.5, 1.0, 1.18, 2.0))

    def test_face_loss_cancels_movement_and_gestures(self):
        EyeControl.on_face(self.control, SimpleNamespace(found=False))
        self.assert_tracking_cleared()

    def test_disabling_low_light_clears_an_existing_border(self):
        self.control.lighting.active = True
        EyeControl.on_face(self.control, SimpleNamespace(found=False))
        self.control.lighting.turn_off.assert_called_once()

    def test_pause_and_resume_discard_tracking_state(self):
        EyeControl.toggle_pause(self.control)
        self.assertTrue(self.control.paused)
        self.assert_tracking_cleared()
        self.control.target = QPointF(100, 100)
        self.control.clicker.update(1.0, 3.0, 0.5, 0.6)
        EyeControl.toggle_pause(self.control)
        self.assertFalse(self.control.paused)
        self.assertIsNone(self.control.target)
        self.assertFalse(self.control.clicker.update(0.0, 4.0, 0.5, 0.6))

    def test_recalibration_cancels_previous_tracking(self):
        windows = [Mock() for _ in range(4)]
        (self.control.buttons, self.control.settings_panel,
         self.control.notifications, self.control.keyboard) = windows
        self.control.calibration = Mock()
        EyeControl.start_calibration(self.control)
        self.assert_tracking_cleared()
        for window in windows:
            window.hide.assert_called_once()
        self.control.calibration.start.assert_called_once()

    def test_mouse_takeover_cancels_pending_eye_actions(self):
        self.control.placed = QPoint(0, 0)
        self.control.position = QPointF(0, 0)
        self.control.mouse_until = 0.0
        self.control.calibration = Mock()
        self.control.calibration.isVisible.return_value = False
        self.control.place_cursor = Mock()
        self.control.mouse_in_charge = lambda now: EyeControl.mouse_in_charge(
            self.control, now)
        with patch.object(controller.QCursor, "pos", return_value=QPoint(40, 0)), \
                patch.object(controller.time, "monotonic", return_value=2.0):
            EyeControl.glide_cursor(self.control)
        self.assert_tracking_cleared()
        self.assertTrue(self.control.mouse_in_charge(2.0))
        self.control.place_cursor.assert_not_called()

    def test_mouse_override_blocks_blink_and_lean_zoom(self):
        self.control.mouse_until = 5.0
        self.control.mouse_in_charge = lambda now: EyeControl.mouse_in_charge(
            self.control, now)
        self.control.calibration = Mock()
        self.control.calibration.isVisible.return_value = False
        self.control.mapper = Mock(ready=True)
        self.control.resting_face_size = 1.0
        self.control.click = Mock()
        self.control.aim_cursor = Mock()
        self.control.zoom = Mock()
        self.control.zoom.isVisible.return_value = False
        self.control.record = Mock()
        with patch.object(controller.time, "monotonic", return_value=2.0), \
                patch.object(controller, "gaze_features", return_value=(0.5, 0.5)), \
                patch.object(controller, "eyes_closed_amount", return_value=0.0), \
                patch.object(controller, "face_size", return_value=1.5):
            EyeControl.on_face(self.control, SimpleNamespace(found=True))
        self.assert_tracking_cleared()
        self.control.click.assert_not_called()
        self.control.aim_cursor.assert_not_called()
        self.control.zoom.open_at_cursor.assert_not_called()

        # Once the override expires, fresh gaze readings work normally and
        # the blink/lean that began before takeover cannot fire late.
        self.control.mapper.predict.return_value = (0.7, 0.6)
        with patch.object(controller.time, "monotonic", return_value=6.0), \
                patch.object(controller, "gaze_features", return_value=(0.5, 0.5)), \
                patch.object(controller, "eyes_closed_amount", return_value=0.0), \
                patch.object(controller, "face_size", return_value=1.0):
            EyeControl.on_face(self.control, SimpleNamespace(found=True))
        self.control.aim_cursor.assert_called_once_with((0.7, 0.6), 6.0)
        self.control.click.assert_not_called()
        self.control.zoom.open_at_cursor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
