# SignalSpeak

**Hands-free computer control for people with ALS, using an ordinary webcam.**

SignalSpeak was built for the QEC 2026 ALS hackathon. ALS gradually takes away the ability to move, speak and type, and it does so differently in every person. Dedicated eye-tracking hardware exists, but it is expensive. SignalSpeak runs on a normal laptop with its built-in camera, and it adapts to the movements each person still has.

It has three parts that work together:

| Part | Who uses it | What it does |
|---|---|---|
| **Desktop program** (`desktop/`) | The patient | Moves the cursor with the eyes or head, clicks with a face movement, types with an on-screen keyboard |
| **Website** (`public/`) | Patient and caregiver | Accounts, sign-in, privacy consent, and linking a caregiver to a patient |
| **Phone dashboard** (`public/companion/`) | The caregiver | Changes the patient's settings remotely, receives calls for help, shows the activity log |

A small server (`server.mjs`) connects them. Everything runs on one laptop for the demo.

## What makes it different

Most webcam tools assume one input: look at a target, then blink to click. SignalSpeak does not assume which movement a patient can make.

- **Ability test.** In about 95 seconds, the program asks for five face movements (close eyes, raise eyebrows, open mouth, smile, pucker lips) and four head turns. It scores each on whether it happened, how strong and fast it was, whether it fires by accident during other movements, and whether it tires. The patient then clicks with the most reliable one.
- **Eye or head pointing.** If the test shows good head movement, the cursor can follow the direction of the face instead of the eyes. A webcam measures head direction far more precisely than eye direction, so the cursor is steadier.
- **It follows the disease.** The test can be repeated at any time, by the patient or remotely by a caregiver. Scores go in a progression log, so changes over months are visible.
- **Lean to zoom.** Leaning towards the screen enlarges the area around the cursor, which makes small targets easy to hit.
- **The mouse always wins.** A helper can move the real mouse at any time and eye control lets go.

## How it works

1. **Seeing the face.** Each webcam frame goes through Google's MediaPipe Face Landmarker [1], [2]. It returns 478 points on the face [3], including the centre of each iris, plus 52 scores for facial movements (such as "left eye closed") and a matrix giving the direction of the head.
2. **Calibration.** The patient looks at (or points their nose at) 13 dots. For each dot the program records ten numbers describing the eyes and head. A ridge regression [4], which is a line fit that resists noise, learns how those numbers map to a position on the screen. The fit is checked by hiding one dot at a time and predicting it.
3. **Moving the cursor.** Each new frame gives a predicted screen position. A filter holds the cursor steady while the patient rests on a spot and lets it jump quickly when they look elsewhere. The cursor is then glided to that position about 120 times a second.
4. **Clicking.** The chosen movement must be held briefly. For a blink that is about half a second, so normal blinks never click. The click lands where the patient was looking just before the movement began.
5. **Staying connected.** The desktop is paired once with the patient's account. It then loads saved settings from the server, receives changes from the caregiver, and sends calls for help.

The details of each file are in [`desktop/README.md`](desktop/README.md).

## Setup

### 1. Patient program only (no accounts)

This is enough to try eye control, the keyboard and the ability test. Requires Python 3.11 and a webcam.

```sh
cd desktop
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

On macOS/Linux, activate with `source .venv/bin/activate`. The first run downloads the face model (about 4 MB). Unpaired, the program works by itself and nothing leaves the computer.

Press **F8** to pause eye control and **F9** to quit.

### 2. Full system (accounts, caregiver dashboard)

Requires Node.js 22 or newer [12]. There are no Node packages to install.

```sh
node scripts/package-desktop.mjs
node server.mjs
```

- Website: http://localhost:3000
- Phone dashboard (browser demo): http://localhost:3000/app/

The server only listens on this computer. A real phone cannot reach it through `localhost`; the dashboard is shown in the laptop's browser for the demo. Use fictional information only.

Then pair the desktop with the patient account, once:

```sh
cd desktop
python connect.py
python main.py
```

`connect.py` asks for the server address, patient email and password. It saves a device token in `desktop/device.json` (ignored by Git), not the password.

### End-to-end walkthrough

1. On the website, create a patient account. Accept the privacy notice and choose whether to enable activity logging.
2. Copy the patient ID. Sign out, create a caregiver account, and request a connection using that ID.
3. Sign back in as the patient and accept the connection in My account.
4. To be signed in as both at once, use a second browser profile or a private window.
5. Pair and start the desktop program. Calibrate by looking at the dots.
6. Open Settings on the desktop, then the Ability test tab, and run the test. Choose the suggested click movement and pointing method.
7. Open `/app/` as the caregiver and select the patient. The patient's choices appear there. Change a setting, or press "Run ability test on desktop".
8. On the desktop, use the phone button to call the caregiver. The request appears in the dashboard.
9. Revoke the connection on the website to remove the caregiver's access.

## Privacy and data

- Camera frames are processed on the patient's computer. They are never saved and never sent.
- Activity logging is off unless the patient turns it on. Only the patient can change this.
- With logging on, the log holds action types, timings, estimated gaze samples and click positions. It never holds typed text, screenshots or video.
- Every settings change is recorded in an audit log under the account that made it.
- Passwords are stored as salted scrypt hashes. The desktop authenticates with a separate token, never the password.
- The integrated demo does not transmit video or audio.
- Accounts and care data are stored in a local `data/` folder, which Git ignores.

## Tests

```sh
node --test
cd desktop
python -m unittest discover -s tests -v
```

The Python tests use made-up face data, so they need no camera.

## Status

**Working:** accounts and sign-in, consent, caregiver linking and revocation, desktop pairing, remote settings, eye and head pointing, click by blink or another movement, the ability test, lean-to-zoom, on-screen keyboard, automatic screen brightness in dark rooms, activity log with charts and export, calls for help.

**Not done:** video and audio calls (switched off), a packaged installer, real-phone networking over HTTPS, production-grade identity, account deletion.

**Known limits:** webcam eye tracking is accurate to roughly 3 to 7% of the screen width, which is why targets are large and zoom exists. Accuracy depends on lighting and on the laptop's camera. Head pointing needs neck movement. This is a prototype and not a medical device.

## Repository layout

| Path | Contents |
|---|---|
| `desktop/` | The patient program (Python) and its tests |
| `public/` | The website |
| `public/companion/` | The phone dashboard |
| `server.mjs`, `care-api.mjs`, `telemetry.mjs` | The account and care server (Node.js) |
| `scripts/` | Packs the desktop source for the website's Download page |
| `test/` | Server tests |

## References

[1] Google. (n.d.). *Face landmark detection guide (MediaPipe Face Landmarker)*. Google AI Edge. https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker

[2] Lugaresi, C., Tang, J., Nash, H., McClanahan, C., Uboweja, E., Hays, M., Zhang, F., Chang, C.-L., Yong, M. G., Lee, J., Chang, W.-T., Hua, W., Georg, M., & Grundmann, M. (2019). *MediaPipe: A framework for building perception pipelines*. arXiv:1906.08172. https://arxiv.org/abs/1906.08172

[3] Kartynnik, Y., Ablavatski, A., Grishchenko, I., & Grundmann, M. (2019). *Real-time facial surface geometry from monocular video on mobile GPUs*. arXiv:1907.06724. https://arxiv.org/abs/1907.06724

[4] Hoerl, A. E., & Kennard, R. W. (1970). Ridge regression: Biased estimation for nonorthogonal problems. *Technometrics, 12*(1), 55–67. https://doi.org/10.1080/00401706.1970.10488634

[5] Bradski, G. (2000). The OpenCV library. *Dr. Dobb's Journal of Software Tools*. https://opencv.org

[6] Harris, C. R., Millman, K. J., van der Walt, S. J., et al. (2020). Array programming with NumPy. *Nature, 585*, 357–362. https://doi.org/10.1038/s41586-020-2649-2

[7] The Qt Company. *Qt for Python (PySide6)* [Software, LGPL]. https://doc.qt.io/qtforpython-6/

[8] Palmér, M. *pynput* [Software, LGPL]. https://pynput.readthedocs.io

[9] Bhat, N. M. *pyttsx3* [Software, MPL 2.0]. https://pyttsx3.readthedocs.io

[10] Crozzers. *screen-brightness-control* [Software, MIT]. https://github.com/Crozzers/screen_brightness_control

[11] Reitz, K. *Requests* [Software, Apache 2.0]. https://requests.readthedocs.io

[12] OpenJS Foundation. *Node.js* [Software]. https://nodejs.org

OpenCV [5] reads the webcam, NumPy [6] does the calibration maths, PySide6 [7] draws the windows, pynput [8] sends clicks and key presses, pyttsx3 [9] reads text aloud, screen-brightness-control [10] adjusts brightness, and Requests [11] talks to the server.

## Attribution

Original phone interface: teammate's `app` branch. Original eye tracking and desktop program: teammate's `action-implementation` branch. Website and integration: `web` and `codex/integrated-demo` branches. Each source file names the libraries it uses and the AI assistance involved.

## AI Tools Acknowledgement

The following AI tools were used to assist with brainstorming, code development, debugging, and documentation. The team reviewed and tested the results.

- **OpenAI.** (2026). *ChatGPT* [Large language model]. https://chatgpt.com/
- **OpenAI.** (2026). *Codex* [AI coding agent]. https://openai.com/codex/
- **Anthropic.** (2026). *Claude* [Large language model]. https://claude.ai/
- **Anthropic.** (2026). *Claude Code* [AI coding agent]. https://claude.com/claude-code
