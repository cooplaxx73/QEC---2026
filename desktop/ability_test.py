"""
Ability test: "show me what you can do".

ALS takes away different muscles in different people, and it changes over
time. This test finds the face movement that a patient can make most
reliably TODAY, so that movement can be used to click instead of always
assuming a long blink.

The test takes about 95 seconds:
1. Relax for a few seconds. This measures the resting face.
2. For each movement (close eyes, raise eyebrows, open mouth, smile,
   pucker lips): do it three times, holding until the tone, with a rest
   in between.
3. Turn the head left, right, up and down, holding each until the tone.
   This shows whether the patient could steer the cursor with their head
   (steadier than the eyes) and how far and how steadily they can turn.

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

import math
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

# The head part: direction -> what to tell the patient.
HEAD_TURNS = {
    "left": "Turn your head left",
    "right": "Turn your head right",
    "up": "Tilt your head up",
    "down": "Tilt your head down",
}
TURN_SECONDS = 2.5     # hold each head turn this long
CENTRE_SECONDS = 2.0   # come back to the middle
# Pointing your nose at the edge of a laptop screen needs about this much.
FULL_SIDEWAYS_DEGREES = 12
FULL_UP_DOWN_DEGREES = 8
STEADY_DEGREES = 0.8   # wobble below this while holding earns full marks
GOOD_HEAD_SCORE = 60   # at or above this, head pointing is suggested


def movement_amount(name: str, blendshapes: dict) -> float:
    """How strongly the face is making a movement right now (0 to 1)."""
    return float(MOVEMENTS[name][2](blendshapes))


def head_angles(head_matrix) -> tuple[float, float]:
    """Which way the face points, in degrees: (sideways, up or down).

    The third column of MediaPipe's head matrix is the direction the face
    is pointing. Straight at the camera gives (0, 0).
    """
    forward = np.array(head_matrix)[:3, 2]
    forward = forward / (np.linalg.norm(forward) + 1e-9)
    return (math.degrees(math.asin(max(-1.0, min(1.0, float(forward[0]))))),
            math.degrees(math.asin(max(-1.0, min(1.0, float(forward[1]))))))


def make_schedule() -> list[tuple]:
    """The parts of the test in order: (kind, movement, seconds)."""
    parts = [("rest", None, REST_SECONDS)]
    for name in MOVEMENTS:
        parts.append(("ready", name, READY_SECONDS))
        for _ in range(TRIES):
            parts.append(("do", name, DO_SECONDS))
            parts.append(("relax", name, RELAX_SECONDS))
    parts.append(("ready", "head", READY_SECONDS))
    for direction in HEAD_TURNS:
        parts.append(("turn", direction, TURN_SECONDS))
        parts.append(("centre", direction, CENTRE_SECONDS))
    return parts


def score_head(schedule: list, readings: list) -> dict:
    """How well the patient can turn and hold their head.

    Uses the "sideways" and "up_down" angles stored with every reading.
    """
    def angles(axis, wanted):
        return [values[axis] for part, seconds, values in readings
                if seconds >= SETTLE_SECONDS and wanted(*schedule[part][:2])]

    reach, wobble = {}, []
    for direction in HEAD_TURNS:
        axis = "sideways" if direction in ("left", "right") else "up_down"
        resting = angles(axis, lambda kind, who: kind == "rest")
        held = angles(axis, lambda kind, who: kind == "turn" and who == direction)
        if not resting or not held:
            reach[direction] = 0.0
            continue
        reach[direction] = abs(float(np.median(held)) - float(np.median(resting)))
        wobble.append(float(np.std(held)))

    # Left and right must go opposite ways, and so must up and down.
    # (Someone who can only turn one way cannot reach the whole screen.)
    sideways = min(reach["left"], reach["right"])
    up_down = min(reach["up"], reach["down"])
    steadiness = float(np.mean(wobble)) if wobble else 99.0
    marks = {
        "sideways": min(1.0, sideways / FULL_SIDEWAYS_DEGREES),
        "up_down": min(1.0, up_down / FULL_UP_DOWN_DEGREES),
        "steady": 1.0 if steadiness <= STEADY_DEGREES
        else max(0.3, 1.0 - (steadiness - STEADY_DEGREES) * 0.3),
    }
    score = 100.0
    for mark in marks.values():
        score *= mark
    return {
        "score": round(score), "steadiness": round(steadiness, 1),
        "reach": {direction: round(amount) for direction, amount in reach.items()},
    }


def describe_head(head: dict) -> str:
    reach = head["reach"]
    if max(reach.values()) < 3:
        return "No head movement seen"
    turns = (f"{reach['left']}° left, {reach['right']}° right, "
             f"{reach['up']}° up, {reach['down']}° down")
    return turns + (", steady" if head["steadiness"] <= STEADY_DEGREES * 2 else ", shaky")


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

    finished = Signal(object)   # {"movements": [...], "head": {...}}
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
        self.resting_angles = {"sideways": 0.0, "up_down": 0.0}
        self.showFullScreen()
        self.repaint_timer.start()
        self.begin_part(0)

    def begin_part(self, part: int) -> None:
        self.part = part
        self.part_started = time.monotonic()
        kind, name, _ = self.schedule[part]
        if kind == "rest":
            self.say.emit("Relax your face and look at the screen.")
        elif kind == "ready" and name == "head":
            # The head angles while relaxing are "straight ahead".
            for axis in self.resting_angles:
                relaxed = [values[axis] for p, _, values in self.readings if p == 0]
                self.resting_angles[axis] = float(np.median(relaxed)) if relaxed else 0.0
            self.say.emit("Next: head movement. Hold each turn until the tone.")
        elif kind == "ready":
            self.say.emit(f"Next: {MOVEMENTS[name][1]}. Hold it until the tone.")
        elif kind == "turn":
            self.tone.emit("go")
            self.say.emit(HEAD_TURNS[name])
        elif kind == "do":
            self.tone.emit("go")
        elif kind in ("relax", "centre"):
            self.tone.emit("stop")

    def add_sample(self, blendshapes: dict, head_matrix) -> None:
        """Called for every camera frame while the test is showing."""
        elapsed = time.monotonic() - self.part_started
        kind, name, seconds = self.schedule[self.part]
        values = {each: movement_amount(each, blendshapes) for each in MOVEMENTS}
        values["sideways"], values["up_down"] = head_angles(head_matrix)
        self.readings.append((self.part, elapsed, values))

        # The live meter: the movement being asked for right now.
        if kind in ("turn", "centre"):
            axis = "sideways" if name in ("left", "right") else "up_down"
            self.level = abs(values[axis] - self.resting_angles[axis]) / 20
        else:
            self.level = values[name] if name in MOVEMENTS else 0.0

        if elapsed < seconds:
            return
        if self.part + 1 < len(self.schedule):
            self.begin_part(self.part + 1)
        else:
            self.repaint_timer.stop()
            self.hide()
            self.finished.emit({
                "movements": score_movements(self.schedule, self.readings),
                "head": score_head(self.schedule, self.readings),
            })

    def words(self, kind: str, name: str) -> tuple[str, str, str]:
        """The small heading, the big instruction and the hint under it."""
        if kind == "rest":
            return "Ability test", "Relax your face", "Just look at the screen"
        if name == "head":
            return ("Head movement", "Turn your head when asked",
                    "Get ready. Hold each turn until the tone")
        if kind == "turn":
            return "Head movement", HEAD_TURNS[name], "Now, and hold it"
        if kind == "centre":
            return "Head movement", HEAD_TURNS[name], "Back to the middle"
        names = list(MOVEMENTS)
        hint = {"ready": "Get ready. Hold it until the tone",
                "do": "Now, and hold it", "relax": "Relax"}[kind]
        return f"Movement {names.index(name) + 1} of {len(names)}", MOVEMENTS[name][1], hint

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        kind, name, seconds = self.schedule[self.part]
        elapsed = min(time.monotonic() - self.part_started, seconds)
        width, height = self.width(), self.height()
        small, big, hint = self.words(kind, name)
        active = kind in ("do", "turn")  # the patient should be moving now

        painter.setPen(QColor(theme.MUTED))
        painter.setFont(theme.font(theme.SANS, 14, bold=True))
        painter.drawText(QRectF(0, height * 0.24, width, 40), Qt.AlignCenter, small.upper())
        painter.setPen(QColor(theme.INK))
        painter.setFont(theme.font(theme.SERIF, 44))
        painter.drawText(QRectF(0, height * 0.30, width, 110), Qt.AlignCenter, big)
        painter.setPen(QColor(theme.GREEN if active else theme.MUTED))
        painter.setFont(theme.font(theme.SANS, 22, bold=active))
        painter.drawText(QRectF(0, height * 0.45, width, 60), Qt.AlignCenter, hint)

        # A bar that empties as the time for this part runs out.
        bar = QRectF(width * 0.3, height * 0.58, width * 0.4, 14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.SAGE))
        painter.drawRoundedRect(bar, 7, 7)
        painter.setBrush(QColor(theme.GREEN if active else theme.SAGE_DEEP))
        left = QRectF(bar.left(), bar.top(), bar.width() * (1 - elapsed / seconds), bar.height())
        painter.drawRoundedRect(left, 7, 7)

        # A live meter, so the patient can see the camera picking it up.
        if kind in ("do", "relax", "turn", "centre"):
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
    """Shows the scores and lets the patient choose how to click and point."""

    chosen = Signal(str, float)   # click with: (movement name, its threshold)
    pointer_chosen = Signal(str)  # point with: "eyes" or "head"

    def __init__(self, results: dict, current_click: str, current_pointer: str):
        super().__init__("Your results")
        self.rows.setSpacing(10)
        movements, head = results["movements"], results["head"]
        best = movements[0]
        usable = best["score"] >= GOOD_SCORE

        self.add_heading(
            "Click with", f"{best['label']} was your most reliable movement."
            if usable else "No movement was clear enough. Try again with more light.")
        for position, result in enumerate(movements):
            self.rows.addWidget(self.result_row(
                result["label"], result["score"], describe(result),
                top=position == 0 and usable))

        head_is_good = head["score"] >= GOOD_HEAD_SCORE
        self.add_heading(
            "Point with", "Your head movement is good enough to steer the cursor."
            if head_is_good else "Eye pointing suits you better than head pointing for now.")
        self.rows.addWidget(self.result_row(
            "Head pointing", head["score"], describe_head(head), top=head_is_good))

        # One button for each change worth making, then Close.
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addStretch()
        if usable and best["name"] != current_click:
            row.addWidget(self.offer(
                f"Click with {best['label'].lower()}",
                lambda: self.chosen.emit(best["name"], best["threshold"])))
        better_pointer = "head" if head_is_good else "eyes"
        if better_pointer != current_pointer:
            row.addWidget(self.offer(
                f"Point with {better_pointer}",
                lambda: self.pointer_chosen.emit(better_pointer)))
        row.addWidget(make_button("Close", "secondary", self.close, 200, 90))
        self.rows.addSpacing(8)
        self.rows.addLayout(row)
        centre_on_screen(self)
        theme.fade_in(self)

    def add_heading(self, title: str, summary: str) -> None:
        label = QLabel(f"<span style='font-weight:600; color:{theme.INK};'>{title}</span>"
                       f"&nbsp;&nbsp;<span style='color:{theme.MUTED};'>{summary}</span>")
        label.setStyleSheet("font-size: 20px; padding-top: 6px;")
        self.rows.addWidget(label)

    def offer(self, text: str, on_click):
        """A wide green button that disappears once it has been used."""
        def use():
            button.hide()
            on_click()
        button = make_button(text, "primary", use, 350, 90)
        return button

    def result_row(self, label: str, score: int, note_text: str, top: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        row.setStyleSheet(
            f"#row {{ background: {theme.WHITE}; border-radius: 16px;"
            f" border: {'3px solid ' + theme.GREEN if top else '1px solid ' + theme.BORDER}; }}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(22, 8, 22, 8)
        layout.setSpacing(18)

        name = QLabel(label)
        name.setFixedWidth(190)
        name.setStyleSheet("font-size: 21px; font-weight: 600;")
        layout.addWidget(name)

        # The score as a bar: a pale track with a green part on top.
        track = QFrame()
        track.setFixedSize(240, 16)
        track.setStyleSheet(f"background: {theme.SAGE}; border-radius: 8px;")
        fill = QFrame(track)
        fill.setGeometry(0, 0, int(240 * score / 100), 16)
        fill.setStyleSheet(
            f"background: {theme.GREEN if top else theme.SAGE_DEEP}; border-radius: 8px;")
        layout.addWidget(track)

        number = QLabel(str(score))
        number.setFixedWidth(56)
        number.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        number.setStyleSheet(f"font-size: 23px; font-weight: 700; color: {theme.GREEN};")
        layout.addWidget(number)

        note = QLabel(note_text)
        note.setMinimumWidth(360)
        note.setStyleSheet(f"font-size: 18px; color: {theme.MUTED};")
        layout.addWidget(note, 1)
        return row
