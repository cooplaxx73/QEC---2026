"""Test the integration adapter without webcam, mouse, or third-party packages."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


class Signal:
    def __init__(self, *args):
        self.events = []

    def emit(self, value):
        self.events.append(value)


class RequestError(Exception):
    pass


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.file = Path(self.folder.name) / "device.json"
        self.file.write_text(json.dumps({"backend_url": "http://localhost:3000", "deviceToken": "test-token"}))
        qt = ModuleType("PySide6.QtCore")
        qt.QObject = object
        qt.Signal = Signal
        self.http = Mock()
        self.http.headers = {}
        requests = ModuleType("requests")
        requests.Session = lambda: self.http
        requests.RequestException = RequestError
        source = Path(__file__).resolve().parents[1] / "caregiver_link.py"
        spec = importlib.util.spec_from_file_location("integration_link_test", source)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"PySide6": ModuleType("PySide6"), "PySide6.QtCore": qt, "requests": requests}):
            spec.loader.exec_module(self.module)
        self.module.DEVICE_FILE = self.file
        self.link = self.module.CaregiverLink("unused")
        self.http.get.side_effect = [self.response({"settings": {"click_hold_seconds": .8}, "logging": False, "eventCursor": 10}), self.response([{"id": 11, "type": "settings_changed", "changes": {"click_hold_seconds": 1}}])]

    def response(self, value):
        response = Mock()
        response.json.return_value = value
        return response

    def stop(self, *args):
        self.link.running = False

    def test_pairing_bootstrap_and_delivered_call(self):
        self.link.send("/patient/call", {"video": False})
        self.http.post.return_value = self.response({"ok": True})
        with patch.object(self.module.time, "sleep", self.stop):
            self.link._run()
        self.assertEqual(self.http.headers["Authorization"], "Bearer test-token")
        self.assertEqual(self.link.last_event_id, 11)
        self.assertEqual(self.http.get.call_args.kwargs["params"], {"after": 10})
        self.assertIn("call_delivered", [event["type"] for event in self.link.event_received.events])
        self.http.post.assert_called_once_with("http://localhost:3000/api/device/patient/call", json={"video": False}, timeout=3)

    def test_failed_write_stays_pending_without_false_success(self):
        self.link.send("/patient/call", {"video": False})
        self.http.post.side_effect = RequestError("offline")
        with patch.object(self.module.time, "sleep", self.stop):
            self.link._run()
        self.assertIsNotNone(self.link.pending)
        types = [event["type"] for event in self.link.event_received.events]
        self.assertNotIn("call_delivered", types)
        self.assertIn("connection_error", types)


if __name__ == "__main__":
    unittest.main()
