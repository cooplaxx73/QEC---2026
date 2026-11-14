"""
Ability test: "show me what you can do".

ALS takes away different muscles in different people, and it changes over
time. This test finds the face movement that a patient can make most
reliably TODAY, so that movement can be used to click instead of always
assuming a long blink.

The test takes about 75 seconds:
1. Relax for a few seconds. This measures the resting face.
2. For each movement (close eyes, raise eyebrows, open mouth, smile,
   pucker lips): do it three times, holding until the tone, with a rest
   in between.

Each movement is then scored out of 100 from five things:
- Made it:     how many of the three tries clearly happened.
- Strength:    how far the movement goes beyond the resting face.
- Speed:       how soon after "go" it starts.
- Stays quiet: it must NOT show up while doing the other movements,
               or it would click by accident.
- Stamina:     the third try should be about as strong as the first.

The scores are written to the progression log, so a clinician can see how
each movement changes over the months.

Libraries:
- PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
- NumPy: https://numpy.org
- MediaPipe face blendshapes (the 0 to 1 movement scores used below):
  https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker

Written with the assistance of Claude Code (Anthropic).
"""

import time

import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

import theme
from overlay import Panel, centre_on_screen, make_button

# Each movement: name -> (label, what to tell the patient, how to measure it
# from MediaPipe's scores). Every measurement is 0 (not at all) to 1 (fully).
MOVEMENTS = {
    "blink": (
        "Close eyes", "Close both eyes",
        lambda s: min(s["eyeBlinkLeft"], s["eyeBlinkRight"])),
    "eyebrows": (
        "Raise eyebrows", "Raise your eyebrows",
        lambda s: (s["browInnerUp"] + (s["browOuterUpLeft"] + s["browOuterUpRight"]) / 2) / 2),
    "jaw": (
        "Open mouth", "Open your mouth",
        lambda s: s["jawOpen"]),
    "smile": (
        "Smile", "Smile",
        lambda s: (s["mouthSmileLeft"] + s["mouthSmileRight"]) / 2),
    "pucker": (
        "Pucker lips", "Pucker your lips, like a kiss",
        lambda s: s["mouthPucker"]),
}

TRIES = 3
REST_SECONDS = 4.0     # relaxed face at the very start
READY_SECONDS = 3.0    # time to read the next instruction
DO_SECONDS = 2.0       # hold the movement this long
RELAX_SECONDS = 2.0    # rest between tries
SETTLE_SECONDS = 0.6   # ignore the start of each part: faces need time to change

CLEAR_MOVEMENT = 0.15  # a try counts if it goes this far beyond resting
FULL_STRENGTH = 0.35   # going this far beyond resting earns full marks
GOOD_SCORE = 50        # below this, a movement is not offered for clicking


def movement_amount(name: str, blendshapes: dict) -> float:
    """How strongly the face is making a movement right now (0 to 1)."""
    return float(MOVEMENTS[name][2](blendshapes))


def make_schedule() -> list[tuple]:
    """The parts of the test in order: (kind, movement, seconds)."""
    parts = [("rest", None, REST_SECONDS)]
    for name in MOVEMENTS:
        parts.append(("ready", name, READY_SECONDS))
        for _ in range(TRIES):
            parts.append(("do", name, DO_SECONDS))
            parts.append(("relax", name, RELAX_SECONDS))
    return parts


def score_movements(schedule: list, readings: list) -> list[dict]:
    """Turn the recorded test into one result per movement, best first.

    readings is a list of (part number, seconds into that part, amounts),
    where amounts is a dict of movement name -> 0 to 1.
    """
    def amounts(name, wanted, skip=SETTLE_SECONDS):
        """Readings of one movement during the parts where wanted() is true."""
        return [values[name] for part, seconds, values in readings
                if seconds >= skip and wanted(part, *schedule[part][:2])]

    results = []
    for name, (label, _, _) in MOVEMENTS.items():
        resting = amounts(name, lambda part, kind, who: kind == "rest"
                          or (kind == "relax" and who == name))
        rest_level = float(np.median(resting)) if resting else 0.0

        # How far each try went, and how quickly it started.
        tries = [part for part, (kind, who, _) in enumerate(schedule)
                 if kind == "do" and who == name]
        levels = []
        for part in tries:
            held = amounts(name, lambda p, kind, who: p == part)
            levels.append(float(np.median(held)) - rest_level if held else 0.0)
        made = sum(level >= CLEAR_MOVEMENT for level in levels)
        strength = max(0.0, float(np.mean(levels))) if levels else 0.0
        threshold = rest_level + strength / 2

        starts = []
        for part in tries:
            crossed = [seconds for p, seconds, values in readings
                       if p == part and values[name] > threshold]
            if crossed:
                starts.append(min(crossed))
        start_seconds = float(np.mean(starts)) if starts else DO_SECONDS

        # Does it also fire while the patient does a different movement?
        elsewhere = amounts(name, lambda part, kind, who: kind == "do" and who != name)
        accidental = float(np.mean([value > threshold for value in elsewhere])) if elsewhere else 0.0

        # Is the last try weaker than the first (tiring)?
        stamina = levels[-1] / levels[0] if levels and levels[0] > 0.05 else 0.0
        stamina = min(1.0, max(0.0, stamina))

        marks = {
            "made": made / TRIES,
            "strength": min(1.0, strength / FULL_STRENGTH),
            "speed": 1.0 if start_seconds <= 0.7 else max(0.4, 1.0 - (start_seconds - 0.7) * 0.45),
            "quiet": max(0.0, 1.0 - 2 * accidental),
            "stamina": 0.6 + 0.4 * stamina,
        }
        score = 100.0
        for mark in marks.values():
            score *= mark

        results.append({
            "name": name, "label": label, "score": round(score),
            "threshold": round(threshold, 2), "made": made,
            "strength": round(strength, 2), "start_seconds": round(start_seconds, 2),
            "accidental": round(accidental, 2), "stamina": round(stamina, 2),
        })
    return sorted(results, key=lambda result: result["score"], reverse=True)


def describe(result: dict) -> str:
    """One short line that explains a score in plain words."""
    if result["made"] == 0:
        return "Not seen"
    notes = [f"{result['made']} of {TRIES} tries"]
    if result["accidental"] > 0.15:
        notes.append("also happens by accident")
    elif result["strength"] < 0.2:
        notes.append("weak")
    elif result["stamina"] < 0.7:
        notes.append("tires quickly")
    elif result["start_seconds"] > 1.0:
        notes.append("slow to start")
    else:
        notes.append("strong and steady")
    return ", ".join(notes)


class AbilityTestScreen(QWidget):
    """The full-screen test. Call add_sample() for every camera frame."""

    finished = Signal(object)   # the list from score_movements()
    say = Signal(str)           # an instruction to read aloud
    tone = Signal(str)          # "go" or "stop": play a sound

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(f"background: {theme.CREAM};")
        self.setCursor(Qt.BlankCursor)
        self.repaint_timer = QTimer(self, interval=30, timeout=self.update)
        self.part = 0

    def start(self) -> None:
        self.schedule = make_schedule()
        self.readings = []
        self.level = 0.0
        self.showFullScreen()
        self.repaint_timer.start()
        self.begin_part(0)

    def begin_part(self, part: int) -> None:
        self.part = part
        self.part_started = time.monotonic()
        kind, name, _ = self.schedule[part]
        if kind == "rest":
            self.say.emit("Relax your face and look at the screen.")
        elif kind == "ready":
            self.say.emit(f"Next: {MOVEMENTS[name][1]}. Hold it until the tone.")
        elif kind == "do":
            self.tone.emit("go")
        elif kind == "relax":
            self.tone.emit("stop")

    def add_sample(self, blendshapes: dict) -> None:
        """Called for every camera frame while the test is showing."""
        elapsed = time.monotonic() - self.part_started
        kind, name, seconds = self.schedule[self.part]
        values = {each: movement_amount(each, blendshapes) for each in MOVEMENTS}
        self.readings.append((self.part, elapsed, values))
        self.level = values[name] if name else 0.0
        if elapsed < seconds:
            return
        if self.part + 1 < len(self.schedule):
            self.begin_part(self.part + 1)
        else:
            self.repaint_timer.stop()
            self.hide()
            self.finished.emit(score_movements(self.schedule, self.readings))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        kind, name, seconds = self.schedule[self.part]
        elapsed = min(time.monotonic() - self.part_started, seconds)
        width, height = self.width(), self.height()

        if kind == "rest":
            small, big, hint = "Ability test", "Relax your face", "Just look at the screen"
        else:
            names = list(MOVEMENTS)
            small = f"Movement {names.index(name) + 1} of {len(names)}"
            big = MOVEMENTS[name][1]
            hint = {"ready": "Get ready. Hold it until the tone",
                    "do": "Now, and hold it",
                    "relax": "Relax"}[kind]

        painter.setPen(QColor(theme.MUTED))
        painter.setFont(theme.font(theme.SANS, 14, bold=True))
        painter.drawText(QRectF(0, height * 0.24, width, 40), Qt.AlignCenter, small.upper())
        painter.setPen(QColor(theme.INK))
        painter.setFont(theme.font(theme.SERIF, 44))
        painter.drawText(QRectF(0, height * 0.30, width, 110), Qt.AlignCenter, big)
        painter.setPen(QColor(theme.GREEN if kind == "do" else theme.MUTED))
        painter.setFont(theme.font(theme.SANS, 22, bold=kind == "do"))
        painter.drawText(QRectF(0, height * 0.45, width, 60), Qt.AlignCenter, hint)

        # A bar that empties as the time for this part runs out.
        bar = QRectF(width * 0.3, height * 0.58, width * 0.4, 14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.SAGE))
        painter.drawRoundedRect(bar, 7, 7)
        painter.setBrush(QColor(theme.GREEN if kind == "do" else theme.SAGE_DEEP))
        left = QRectF(bar.left(), bar.top(), bar.width() * (1 - elapsed / seconds), bar.height())
        painter.drawRoundedRect(left, 7, 7)

        # A live meter, so the patient can see the camera picking it up.
        if kind in ("do", "relax"):
            meter = QRectF(width * 0.3, height * 0.66, width * 0.4, 30)
            painter.setBrush(QColor(theme.WHITE))
            painter.setPen(QColor(theme.BORDER))
            painter.drawRoundedRect(meter, 15, 15)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.LIME))
            filled = QRectF(meter.left(), meter.top(),
                            max(30.0, meter.width() * min(1.0, self.level)), meter.height())
            painter.drawRoundedRect(filled, 15, 15)
            painter.setPen(QColor(theme.MUTED))
            painter.setFont(theme.font(theme.SANS, 12))
            painter.drawText(QRectF(0, meter.bottom() + 8, width, 30), Qt.AlignCenter,
                             "What the camera sees")


class AbilityResults(Panel):
    """Shows the scores and lets the patient choose how to click."""

    chosen = Signal(str, float)  # (movement name, its threshold)

    def __init__(self, results: list[dict], current: str):
        super().__init__("Your results")
        best = results[0]
        usable = best["score"] >= GOOD_SCORE
        summary = QLabel(
            f"{best['label']} was your most reliable movement."
            if usable else
            "No movement was clear enough this time. Try again with more light on your face.")
        summary.setWordWrap(True)
        summary.setStyleSheet(f"font-size: 22px; color: {theme.MUTED};")
        self.rows.addWidget(summary)

        for position, result in enumerate(results):
            self.rows.addWidget(self.result_row(result, top=position == 0 and usable))

        current_label = MOVEMENTS[current][0]
        buttons = []
        if usable and best["name"] != current:
            buttons.append((f"Use {best['label'].lower()}", "primary",
                            lambda: self.choose(best["name"], best["threshold"])))
        buttons.append((f"Keep {current_label.lower()}" if buttons else "Close",
                        "secondary", self.close))
        # Wider than the usual buttons, because these labels are long.
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addStretch()
        for text, kind, on_click in buttons:
            row.addWidget(make_button(text, kind, on_click, 330, 90))
        self.rows.addLayout(row)
        centre_on_screen(self)
        theme.fade_in(self)

    def result_row(self, result: dict, top: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        row.setStyleSheet(
            f"#row {{ background: {theme.WHITE}; border-radius: 16px;"
            f" border: {'3px solid ' + theme.GREEN if top else '1px solid ' + theme.BORDER}; }}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(22, 12, 22, 12)
        layout.setSpacing(18)

        name = QLabel(result["label"])
        name.setFixedWidth(190)
        name.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(name)

        # The score as a bar: a pale track with a green part on top.
        track = QFrame()
        track.setFixedSize(260, 16)
        track.setStyleSheet(f"background: {theme.SAGE}; border-radius: 8px;")
        fill = QFrame(track)
        fill.setGeometry(0, 0, int(260 * result["score"] / 100), 16)
        fill.setStyleSheet(
            f"background: {theme.GREEN if top else theme.SAGE_DEEP}; border-radius: 8px;")
        layout.addWidget(track)

        score = QLabel(str(result["score"]))
        score.setFixedWidth(56)
        score.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        score.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {theme.GREEN};")
        layout.addWidget(score)

        note = QLabel(describe(result))
        note.setMinimumWidth(300)
        note.setStyleSheet(f"font-size: 18px; color: {theme.MUTED};")
        layout.addWidget(note, 1)
        return row

    def choose(self, name: str, threshold: float) -> None:
        self.close()
        self.chosen.emit(name, threshold)
