# SignalSpeak desktop — integrated demo

Original desktop implementation: `action-implementation` branch. Integration adapter and pairing flow: OpenAI Codex assistance. Original code's Claude Code attribution is preserved in source files.

## Setup before the hands-free demonstration

Requires Python 3.11, a webcam and the central Node account server running on the laptop (default http://127.0.0.1:3000).

Create the patient account on the website and accept privacy. The optional logging choice controls local patient activity collection and transmission. Caregiver audit entries are separate.

From this folder on Windows:

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python connect.py
python main.py
```

On macOS/Linux, activate with `source .venv/bin/activate` instead. `connect.py` asks for the patient account's email/password and saves an authenticated device token in `device.json`; it does not save the password. Pairing again invalidates the old token. Do not share this file or commit it to Git.

Do not run `stub_server.py` for this integration. It belongs to the original isolated desktop test setup and has no account permissions. The integrated adapter communicates only with the central account/care API.

## Controls

Look to move the cursor. Close both eyes for the configured duration and reopen them to select. Lean forward to zoom, then sit back and select. The keyboard button opens the on-screen keyboard. Instructions and recalibration are available in the overlay. All control customization is in the phone dashboard at `/app/`.

F8/F9 and real-mouse takeover are helper controls; do not use them to operate the patient interface during a hands-free demonstration. Webcam calibration and actual eye-only use require testing on the demonstration laptop.

## Care connections

Use the website to approve a caregiver, then sign in to the phone dashboard with that caregiver's own account. Choose the patient. Settings are validated and audited under that person's identity. The desktop loads saved settings on connection and receives subsequent changes while online.

Call Caregiver sends a support notification to the phone dashboard. Phone connection requests appear on the desktop. The integrated demo does not transmit video or audio. No camera or microphone frames are sent to the central server.

If the server goes offline, eye control keeps running and outbound requests retry. Delivery is announced only after the server accepts the support request. Website sign-out does not end desktop communication.

Patient progression entries are recorded in local `activity_log.db` and sent to the server only when logging was enabled at signup. They contain action types/timings, not typed text. Phone settings and caregiver actions are recorded separately in the server audit log.

The Activity log now includes estimated gaze samples at 2 Hz, cursor and click coordinates, screen dimensions, blink duration, tracking interruptions, pause/resume, calibration fit error, zoom and key-action counts. No screen contents, screenshots, video or typed text are recorded. The patient can turn logging on/off in the phone Activity log; approved caregivers can view events but cannot enable logging. Existing SQLite files migrate automatically to store spatial details. Server retention is 20,000 patient events; export and older-event paging are available in the phone app.

## Checks

From the repository root, standard-library-only adapter checks:

```sh
python -m unittest discover -s desktop/tests -p test_adapter.py -v
```

With desktop dependencies installed, from this folder:

```sh
python -m unittest discover -s tests -v
```

## Dependency references

- MediaPipe Face Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- OpenCV: https://opencv.org
- NumPy: https://numpy.org
- PySide6 / Qt for Python: https://doc.qt.io/qtforpython-6/
- pynput: https://pynput.readthedocs.io
- pyttsx3: https://pyttsx3.readthedocs.io
- screen-brightness-control: https://github.com/Crozzers/screen_brightness_control
- Requests: https://requests.readthedocs.io

The first launch downloads the MediaPipe model. This source package is not a standalone installer.
