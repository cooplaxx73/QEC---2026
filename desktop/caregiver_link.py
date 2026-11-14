"""Authenticated desktop adapter. Original architecture: desktop teammate.
Integration assistance: OpenAI Codex. Uses Requests and PySide6.
Run connect.py once before starting the desktop application.
"""
import json
import queue
import threading
import time
from pathlib import Path
import requests
from PySide6.QtCore import QObject, Signal

DEVICE_FILE = Path(__file__).parent / "device.json"

class CaregiverLink(QObject):
    event_received = Signal(dict)
    frame_received = Signal(bytes)

    def __init__(self, backend_url: str):
        super().__init__()
        self.device = json.loads(DEVICE_FILE.read_text(encoding="utf-8"))
        self.url = self.device["backend_url"].rstrip("/") + "/api/device"
        self.http = requests.Session()
        self.http.headers["Authorization"] = "Bearer " + self.device["deviceToken"]
        self.outbox = queue.Queue(maxsize=500)
        self.last_event_id = 0
        self.video_active = False
        self.my_frame = None
        self.running = True
        self.pending = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, path, data):
        try:
            self.outbox.put_nowait((path, data))
        except queue.Full:
            self.event_received.emit({"type": "connection_error", "message": "Some activity could not be queued. Check the server connection."})

    def stop(self):
        self.running = False

    def _run(self):
        bootstrapped = False
        while self.running:
            try:
                if not bootstrapped:
                    state = self.http.get(self.url + "/bootstrap", timeout=3)
                    state.raise_for_status()
                    data = state.json()
                    self.last_event_id = data["eventCursor"]
                    self.event_received.emit({"type": "integration_ready", **data})
                    bootstrapped = True
                response = self.http.get(self.url + "/patient/events", params={"after": self.last_event_id}, timeout=3)
                response.raise_for_status()
                for event in response.json():
                    self.last_event_id = max(self.last_event_id, event["id"])
                    self.event_received.emit(event)
                for _ in range(20):
                    if self.pending is None:
                        try:
                            self.pending = self.outbox.get_nowait()
                        except queue.Empty:
                            break
                    route, data = self.pending
                    result = self.http.post(self.url + route, json=data, timeout=3)
                    result.raise_for_status()
                    self.pending = None
                    if route == "/patient/call":
                        self.event_received.emit({"type": "call_delivered"})
            except (requests.RequestException, ValueError):
                self.event_received.emit({"type": "connection_error", "message": "Care server unavailable. Requests will retry; eye control continues."})
                time.sleep(2)
            time.sleep(1)
