# Desktop overlay (patient program)

Lets a person with ALS control their computer with their eyes, using a normal webcam.

| Action | How |
|---|---|
| Move the cursor | Look where you want it to go |
| Left click | Close both eyes for about half a second |
| Zoom | Lean towards the screen while looking at a target |
| Type | Use the on-screen keyboard |
| Pause eye control | Press F8 (for a helper) |

Only two buttons stay on screen: **Call Caregiver** and **Instructions**.

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

## Files

| File | Job |
|---|---|
| `config.py` | Every tunable setting, in one place |
| `camera.py` | Webcam capture and face landmark tracking |
| `gaze.py` | Turns eye and head measurements into a screen position |
| `calibration.py` | The "look at the dots" screen |
| `blink.py` | Long-blink click detection |
| `overlay.py` | The two buttons, instructions panel and pop-ups |
| `keyboard.py` | On-screen keyboard |
| `zoom.py` | Lean-forward zoom |
| `lighting.py` | Dark-room detection and brightness boost |
| `speech.py` | Read-aloud |
| `activity_log.py` | Patient progression log |
| `caregiver_link.py` | Talks to the caregiver backend |
| `stub_server.py` | Stand-in backend until the real one exists |
| `main.py` | Starts everything |

## Privacy

- Camera frames are processed on this computer and never saved.
- The camera is only shared with a caregiver after the patient accepts a video call.
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
- One Euro Filter: Casiez, Roussel and Vogel, "1€ Filter: A Simple Speed-based Low-pass Filter for Noisy Input in Interactive Systems", CHI 2012. https://gery.casiez.net/1euro/

## AI assistance

This code was written with the assistance of Claude Code (Anthropic). The team reviewed and tested it.
