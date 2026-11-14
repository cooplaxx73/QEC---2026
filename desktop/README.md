# Desktop overlay (patient program)

Lets a person with ALS control their computer with their eyes, using a normal webcam.

| Action | How |
|---|---|
| Move the cursor | Look where you want it to go |
| Left click | Close both eyes for about half a second |
| Zoom | Look at a target and lean towards the screen. Sit back, then click in the zoomed view |
| Type | Use the on-screen keyboard |
| Pause eye control | Press F8 (for a helper) |
| Use the mouse | Just move it. Eye movement, blink clicks and lean-to-zoom pause, and return 2 seconds after the mouse stops |
| Quit | Press F9, or Settings then the Turn off tab |

Four icon buttons stay on screen: **Call Caregiver** (phone), **Keyboard**, **Settings** (gear) and **Notifications** (bell). Settings is one window with tabs: Instructions, Recalibrate and Turn off. An incoming video call pops up and rings; the camera picture only appears after both sides accept. A short beep confirms each click.

## Setup

Needs Python 3.11 and a webcam. Works on Windows, macOS and Linux.

```bash
cd desktop
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python stub_server.py         # stand-in caregiver backend (optional)
python main.py
```

The first run downloads the MediaPipe face model (about 4 MB).

To try the overlay layout with a mouse before starting eye tracking:

```bash
python preview_overlay.py
```

The preview uses no webcam or backend, and simulates caregiver calls. The
on-screen keyboard still types into the foreground app. Press F9 or use
Settings > Turn off to close it.

## Checks

From `desktop`, with the virtual environment active:

```bash
python -m unittest discover -s tests -v
```

The tracking tests run without opening a camera or moving the mouse.

## Files

| File | Job |
|---|---|
| `config.py` | Every tunable setting, in one place |
| `camera.py` | Webcam capture and face landmark tracking |
| `gaze.py` | Turns eye and head measurements into a screen position |
| `calibration.py` | The "look at the dots" screen |
| `blink.py` | Long-blink click detection |
| `overlay.py` | The four icon buttons, tabbed settings, notifications, ringing call pop-up |
| `keyboard.py` | On-screen keyboard |
| `zoom.py` | Lean-forward zoom |
| `lighting.py` | Dark-room detection and brightness boost |
| `speech.py` | Read-aloud |
| `video_call.py` | Corner video window for caregiver calls |
| `activity_log.py` | Patient progression log |
| `caregiver_link.py` | Talks to the caregiver backend |
| `stub_server.py` | Stand-in backend until the real one exists |
| `main.py` | Starts everything |

## For the website and app team

`stub_server.py` is a stand-in backend. The list of web addresses it answers
is at the top of that file. Point your app at it while building, or copy the
same addresses into the real backend and change `backend_url` in `config.py`.

Open http://127.0.0.1:8000 while it runs for a caregiver test page. It can
change settings, request a video call and show both activity logs.

Setting names the caregiver app can change are the field names in `config.py`,
for example `{"changes": {"click_hold_seconds": 0.8}, "by": "Sam"}`.

## Privacy

- Camera frames are processed on this computer and never saved.
- The camera is only shared after BOTH the patient and the caregiver accept a video call.
- The activity log stores counts and times of actions, not what was typed.

## References

- MediaPipe Face Landmarker (Google, Apache 2.0): https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- OpenCV (Apache 2.0): https://opencv.org
- NumPy (BSD): https://numpy.org
- Qt for Python / PySide6 (LGPL): https://doc.qt.io/qtforpython-6/
- pynput (LGPL): https://pynput.readthedocs.io
- pyttsx3 (MPL 2.0): https://pyttsx3.readthedocs.io
- screen-brightness-control (MIT): https://github.com/Crozzers/screen_brightness_control
- Requests (Apache 2.0): https://requests.readthedocs.io

## AI assistance

This code was written with the assistance of Claude Code (Anthropic). The team reviewed and tested it.
