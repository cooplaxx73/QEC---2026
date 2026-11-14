"""
Stand-in caregiver backend, for testing until the real one exists.

Run with:  python stub_server.py
Then open http://127.0.0.1:8000 for a simple caregiver test page.

Everything is kept in memory and is lost when the server stops.
"side" below is either "patient" or "caregiver".

    GET  /{side}/events?after=ID   new events for that side
    POST /patient/call             {"video": true/false}
    POST /{side}/video             {"action": "request" | "accept" | "decline" | "end"}
    POST /caregiver/settings       {"changes": {"click_hold_seconds": 0.8}, "by": "Sam"}
    POST /patient/logs             one activity log entry
    POST /{side}/frame             a JPEG picture (kept only during a call)
    GET  /{side}/frame             the newest JPEG picture from that side
    GET  /logs/patient             patient progression log
    GET  /logs/audit               caregiver audit log

A video call only starts when BOTH sides have said yes.

Libraries: http.server and json (part of Python):
https://docs.python.org/3/library/http.server.html

Written with the assistance of Claude Code (Anthropic).
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8000
TEST_PAGE = Path(__file__).parent / "caregiver_test_page.html"

lock = threading.Lock()
events = {"patient": [], "caregiver": []}   # messages waiting for each side
said_yes_to_video = {"patient": False, "caregiver": False}
frames = {"patient": b"", "caregiver": b""}
patient_log = []
audit_log = []
next_event_id = 1


def add_event(side: str, kind: str, **details) -> None:
    global next_event_id
    events[side].append({"id": next_event_id, "type": kind, **details})
    next_event_id += 1


def add_audit(action: str, **details) -> None:
    """Every caregiver action that affects the patient is written down."""
    audit_log.append({"time": time.time(), "action": action, **details})


def video_action(side: str, action: str) -> None:
    other = "caregiver" if side == "patient" else "patient"
    if side == "caregiver":
        add_audit("video " + action)

    if action in ("request", "accept"):
        said_yes_to_video[side] = True
        if said_yes_to_video[other]:
            add_event("patient", "video_started")
            add_event("caregiver", "video_started")
        else:
            add_event(other, "video_request")
    else:  # decline or end
        said_yes_to_video["patient"] = said_yes_to_video["caregiver"] = False
        frames["patient"] = frames["caregiver"] = b""
        add_event("patient", "video_ended")
        add_event("caregiver", "video_ended")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        with lock:
            if url.path == "/":
                self.reply(TEST_PAGE.read_bytes(), "text/html")
            elif parts[-1] == "events" and parts[0] in events:
                after = int(parse_qs(url.query).get("after", ["0"])[0])
                self.reply_json([e for e in events[parts[0]] if e["id"] > after])
            elif parts[-1] == "frame" and parts[0] in frames:
                self.reply(frames[parts[0]], "image/jpeg")
            elif url.path == "/logs/patient":
                self.reply_json(patient_log)
            elif url.path == "/logs/audit":
                self.reply_json(audit_log)
            else:
                self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        side = path.strip("/").split("/")[0]
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with lock:
            if path.endswith("/frame") and side in frames:
                # Privacy: pictures are thrown away unless both sides accepted.
                if all(said_yes_to_video.values()):
                    frames[side] = body
            elif path == "/patient/call":
                wants_video = json.loads(body).get("video", False)
                add_event("caregiver", "call", video=wants_video)
                if wants_video:
                    video_action("patient", "request")
            elif path.endswith("/video") and side in events:
                video_action(side, json.loads(body)["action"])
            elif path == "/caregiver/settings":
                data = json.loads(body)
                add_audit("settings changed", changes=data["changes"], by=data.get("by", ""))
                add_event("patient", "settings_changed",
                          changes=data["changes"], by=data.get("by", ""))
            elif path == "/patient/logs":
                patient_log.append(json.loads(body))
            else:
                self.send_error(404)
                return
        self.reply_json({"ok": True})

    def do_OPTIONS(self) -> None:
        # Lets a web app on another address call this server (CORS).
        self.reply(b"", "text/plain")

    def reply_json(self, data) -> None:
        self.reply(json.dumps(data).encode(), "application/json")

    def reply(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass  # keep the terminal quiet


if __name__ == "__main__":
    print(f"Stub caregiver backend running at http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
