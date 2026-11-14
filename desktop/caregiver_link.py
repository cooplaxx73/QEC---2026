"""
Connection between the patient's computer and the caregiver backend.

Runs on a background thread so a slow network never freezes the cursor.
- Sends: calls, video answers, log entries and (only during an accepted
  video call) camera frames.
- Receives: events such as "settings changed" or "video call requested".

The backend address is in config.py. Until the real backend exists it
talks to stub_server.py. The web addresses used are listed in that file.

Libraries:
- Requests for HTTP: https://requests.readthedocs.io
- PySide6 signals to hand results to the main thread: https://doc.qt.io/qtforpython-6/

Written with the assistance of Claude Code (Anthropic).
"""

import queue
import threading
import time

import requests
from PySide6.QtCore import QObject, Signal

POLL_SECONDS = 1.0     # how often to ask for new events
FRAME_SECONDS = 0.12   # time between video frames during a call
TIMEOUT = 2            # seconds before giving up on one request


class CaregiverLink(QObject):
    event_received = Signal(dict)    # an event from the caregiver side
    frame_received = Signal(bytes)   # one JPEG picture of the caregiver

    def __init__(self, backend_url: str):
        super().__init__()
        self.url = backend_url.rstrip("/")
        self.outbox = queue.Queue()
        self.last_event_id = None    # None until the first check
        self.video_active = False    # True only after BOTH sides accepted
        self.my_frame = None         # newest JPEG of the patient camera
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, path: str, data: dict) -> None:
        """Queue a message for the backend. Returns straight away."""
        self.outbox.put((path, data))

    def stop(self) -> None:
        self.running = False

    def _run(self) -> None:
        next_poll = 0.0
        while self.running:
            try:
                self._send_waiting_messages()
                if time.monotonic() >= next_poll:
                    self._fetch_events()
                    next_poll = time.monotonic() + POLL_SECONDS
                if self.video_active:
                    self._swap_video_frames()
            except requests.RequestException:
                time.sleep(POLL_SECONDS)  # backend not reachable, try again later
            time.sleep(FRAME_SECONDS if self.video_active else 0.2)

    def _send_waiting_messages(self) -> None:
        while not self.outbox.empty():
            path, data = self.outbox.get()
            requests.post(self.url + path, json=data, timeout=TIMEOUT)

    def _fetch_events(self) -> None:
        reply = requests.get(
            self.url + "/patient/events",
            params={"after": self.last_event_id or 0}, timeout=TIMEOUT,
        )
        # Events from before this program started are old news: skip them.
        is_first_check = self.last_event_id is None
        self.last_event_id = self.last_event_id or 0
        for event in reply.json():
            self.last_event_id = event["id"]
            if not is_first_check:
                self.event_received.emit(event)

    def _swap_video_frames(self) -> None:
        if self.my_frame is not None:
            requests.post(self.url + "/patient/frame", data=self.my_frame, timeout=TIMEOUT)
        reply = requests.get(self.url + "/caregiver/frame", timeout=TIMEOUT)
        if reply.status_code == 200 and reply.content:
            self.frame_received.emit(reply.content)
