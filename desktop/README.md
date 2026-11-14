# SignalSpeak desktop (patient program)

Lets a person with ALS control their computer with their eyes or head, using a normal webcam. It signs in to the SignalSpeak care server as the patient, so an approved caregiver can adjust it from the phone dashboard.

Original desktop implementation: `action-implementation` branch, written with the assistance of Claude Code (Anthropic). Integration adapter and pairing flow: OpenAI Codex assistance. The attribution is kept in each source file.

| Action | How |
|---|---|
| Move the cursor | Look where you want it to go, or turn your head if head pointing is on |
| Click | Close both eyes for about half a second, or use the movement the ability test chose |
| Zoom | Look at a target and lean towards the screen. Sit back, then click in the zoomed view |
| Type | Use the on-screen keyboard |
| Find your best movement | Settings, then the Ability test tab |
| Pause eye control | Press F8 (for a helper) |
| Use the mouse | Just move it. Eye movement, clicks and lean-to-zoom pause, and return 2 seconds after the mouse stops |
| Quit | Press F9, or Settings then the Turn off tab |

Four icon buttons stay on screen: **Call Caregiver** (phone), **Keyboard**, **Settings** (gear) and **Notifications** (bell). Settings is one window with tabs: Instructions, Recalibrate, Ability test and Turn off. A short beep confirms each click.

## Setup

Requires Python 3.11 and a webcam.

**Without an account:** skip `python connect.py` below. The program then runs by itself: eye control, clicking, the keyboard and the ability test all work, the progression log stays on this computer, and nothing is sent anywhere.

**With an account:** the central Node account server must be running on the laptop (default http://127.0.0.1:3000). See the README in the repository root. Create the patient account on the website and accept privacy. The optional logging choice controls local patient activity collection and transmission. Caregiver audit entries are separate.

From this folder on Windows:

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python connect.py
python main.py
```

On macOS/Linux, activate with `source .venv/bin/activate` instead. `connect.py` asks for the patient account's email/password and saves an authenticated device token in `device.json`; it does not save the password. Pairing again invalidates the old token. Do not share this file or commit it to Git.

After the environment setup is complete, Windows users can double-click **Start SignalSpeak.vbs** instead of opening a terminal. It uses the virtual environment's windowed Python. Launch failures are written to `startup.log` and shown in a message box. When paired, keep the central server running.

The first launch downloads the MediaPipe face model (about 4 MB). This source package is not a standalone installer.

To try the overlay layout with a mouse, without a webcam or server:

```sh
python preview_overlay.py
```

## Ability test: click and point with what works best

ALS affects different muscles in different people and changes over time. The test (about 95 seconds) asks for five movements (close eyes, raise eyebrows, open mouth, smile, pucker lips), three times each. It scores each one on whether it happened, how strong and fast it was, whether it also fires by accident during other movements, and whether it tires. The patient can then click with the best one (setting `click_signal`).

The test also asks the patient to turn their head left, right, up and down. If they can turn far enough and hold steady, it suggests **head pointing** (setting `pointer_mode` = `head`): the cursor follows the direction of the face instead of the eyes. The camera measures head direction much more precisely than eye direction, so the cursor is steadier. Switching between eyes and head starts a new calibration, where the patient points their nose at each dot.

The patient's choices are sent to the care server, so the phone dashboard shows them and they survive a restart. A caregiver can also change them, or start the test remotely, from the phone dashboard.

## Care connections

Use the website to approve a caregiver, then sign in to the phone dashboard at `/app/` with that caregiver's own account. Choose the patient. Settings are validated and audited under that person's identity. The desktop loads saved settings on connection and receives later changes while online.

Call Caregiver sends a support notification to the phone dashboard. Phone connection requests appear on the desktop. The integrated demo does not transmit video or audio. No camera or microphone frames are sent to the central server.

If the server goes offline, eye control keeps running and outbound requests retry. Delivery is announced only after the server accepts the support request. Website sign-out does not end desktop communication.

F8/F9 and real-mouse takeover are helper controls; do not use them to operate the patient interface during a hands-free demonstration.

## Privacy

- Camera frames are processed on this computer and never saved or sent.
- When paired, patient progression entries are recorded in local `activity_log.db` and sent to the server only when the patient enabled logging. Unpaired, they are recorded locally and never sent. They contain action types and timings, not typed text.
- With logging on, the log includes estimated gaze samples at 2 Hz, cursor and click coordinates, screen dimensions, blink duration, tracking interruptions, pause/resume, calibration fit error, ability test scores, zoom and key-action counts. No screen contents, screenshots, video or typed text are recorded.
- The patient can turn logging on or off in the phone Activity log. Approved caregivers can view events but cannot enable logging.
- Phone settings and caregiver actions are recorded separately in the server audit log.

## Files

| File | Job |
|---|---|
| `main.py` | Starts everything and passes data between the parts |
| `connect.py` | Pairs this computer with a patient account (run once) |
| `launch.pyw`, `Start SignalSpeak.vbs` | Start the program on Windows without a terminal |
| `config.py` | Every tunable setting, in one place |
| `camera.py` | Webcam capture and face landmark tracking |
| `gaze.py` | Turns eye and head measurements into a screen position |
| `calibration.py` | The "look at the dots" screen |
| `blink.py` | Detects the click movement (long blink or another movement) |
| `ability_test.py` | Finds the movement and pointing method the patient can use most reliably |
| `overlay.py` | The four icon buttons, tabbed settings, notifications, pop-ups |
| `theme.py` | Colours, fonts and icons for every window |
| `keyboard.py` | On-screen keyboard |
| `zoom.py` | Lean-forward zoom |
| `lighting.py` | Dark-room detection and automatic screen brightness |
| `speech.py` | Read-aloud |
| `activity_log.py`, `telemetry.py` | Patient progression log and gaze samples |
| `caregiver_link.py` | Talks to the care server with the paired device token |
| `video_call.py` | Corner video window. Video is switched off in the integrated demo |
| `preview_overlay.py` | Mouse-only preview of the overlay |
| `stub_server.py`, `caregiver_test_page.html` | From the original stand-alone desktop test setup. Not used by the integrated program |

## Checks

From the repository root, standard-library-only adapter checks:

```sh
python -m unittest discover -s desktop/tests -p test_adapter.py -v
```

With desktop dependencies installed, from this folder:

```sh
python -m unittest discover -s tests -v
```

Webcam calibration and actual eye-only use must be tested on the demonstration laptop.

## References

- MediaPipe Face Landmarker (Google, Apache 2.0): https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- OpenCV (Apache 2.0): https://opencv.org
- NumPy (BSD): https://numpy.org
- Qt for Python / PySide6 (LGPL): https://doc.qt.io/qtforpython-6/
- pynput (LGPL): https://pynput.readthedocs.io
- pyttsx3 (MPL 2.0): https://pyttsx3.readthedocs.io
- screen-brightness-control (MIT): https://github.com/Crozzers/screen_brightness_control
- Requests (Apache 2.0): https://requests.readthedocs.io
