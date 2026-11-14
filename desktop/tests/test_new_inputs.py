"""Follow-the-dot matching and ability-test scoring, with made-up data."""

import math
import random
import unittest

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from ability_test import make_schedule, score_movements, MOVEMENTS  # noqa: E402
from follow_dot import MOVEMENTS as DOT_MOVEMENTS  # noqa: E402
from follow_dot import DotLayer, Orbit  # noqa: E402

FRAME = 1 / 30      # the camera gives about 30 pictures a second
SHAKE_PIXELS = 30   # how much a webcam gaze estimate jumps around


def fake_orbit(index: int, centre: tuple) -> Orbit:
    """An orbit without a real button behind it."""
    orbit = Orbit.__new__(Orbit)
    orbit.button = f"button {index}"
    orbit.direction, orbit.start, orbit.lap = DOT_MOVEMENTS[index]
    orbit.centre, orbit.reach = centre, (79, 79)
    return orbit


class FollowTheDot(unittest.TestCase):
    def setUp(self):
        random.seed(4)
        self.layer = DotLayer()
        self.layer.resize(1700, 1060)
        # Four buttons stacked like the button bar, and three in a pop-up.
        centres = [(1600, 500 + 118 * row) for row in range(4)]
        centres += [(600 + 230 * column, 560) for column in range(3)]
        self.layer.orbits = [fake_orbit(i, centre) for i, centre in enumerate(centres)]
        self.chosen = []
        self.layer.chosen.connect(self.chosen.append)

    def watch(self, seconds: float, eye_position) -> None:
        for frame in range(int(seconds / FRAME)):
            now = 100 + frame * FRAME
            x, y = eye_position(now)
            self.layer.add_gaze(x + random.gauss(0, SHAKE_PIXELS),
                                y + random.gauss(0, SHAKE_PIXELS), now)

    def test_following_a_dot_chooses_its_button(self):
        for index, orbit in enumerate(self.layer.orbits):
            self.chosen.clear()
            self.layer.forget()
            self.layer.resting_until = 0.0
            # Eyes trail the dot by 0.15 seconds, as real eyes do.
            self.watch(4, lambda now: orbit.dot_position(now - 0.15))
            self.assertEqual(self.chosen[:1], [f"button {index}"])

    def test_resting_eyes_choose_nothing(self):
        self.watch(40, lambda now: (1600, 600))
        self.assertEqual(self.chosen, [])

    def test_looking_around_chooses_nothing(self):
        # Jump to a new spot near the buttons every 0.4 seconds, like reading.
        def wander(now):
            step = int(now / 0.4)
            return 1450 + 97 * (step * 7 % 4), 450 + 61 * (step * 5 % 8)
        self.watch(40, wander)
        self.assertEqual(self.chosen, [])

    def test_slow_head_sway_chooses_nothing(self):
        self.watch(40, lambda now: (1600 + 80 * math.sin(now * 1.1), 600))
        self.assertEqual(self.chosen, [])


class AbilityScoring(unittest.TestCase):
    def record(self, face) -> list:
        """face(kind, movement, try number) -> amounts for every movement."""
        random.seed(2)
        schedule, readings, tries = make_schedule(), [], {}
        for part, (kind, name, seconds) in enumerate(schedule):
            if kind == "do":
                tries[name] = tries.get(name, 0) + 1
            for frame in range(int(seconds / FRAME)):
                moment = frame * FRAME
                # A real face needs about 0.4 seconds to change expression.
                doing = kind if moment >= 0.4 else "relax"
                amounts = face(doing, name, tries.get(name, 0))
                readings.append((part, moment, {
                    each: min(1, max(0, amounts.get(each, 0.03) + random.gauss(0, 0.02)))
                    for each in MOVEMENTS}))
        return score_movements(schedule, readings)

    def test_best_movement_is_clean_and_strong(self):
        def face(kind, name, attempt):
            if kind != "do":
                return {}
            if name == "eyebrows":
                return {"eyebrows": 0.7}
            if name == "blink":
                return {"blink": 0.8, "eyebrows": 0.3}   # brows move when squeezing eyes
            if name == "jaw":
                return {"jaw": 0.6, "smile": 0.5}         # smile shows up by accident
            if name == "smile":
                return {"smile": 0.5}
            return {"pucker": 0.08}                        # too weak to see
        results = {result["name"]: result for result in self.record(face)}
        # Clean, strong movements score high.
        for name in ("eyebrows", "blink", "jaw"):
            self.assertGreater(results[name]["score"], 80, name)
        # Smile is strong too, but it fires while opening the mouth.
        self.assertGreater(results["smile"]["accidental"], 0.15)
        self.assertLess(results["smile"]["score"], results["jaw"]["score"] - 20)
        self.assertEqual(results["pucker"]["score"], 0)
        # The click threshold sits halfway between resting and doing.
        self.assertAlmostEqual(results["eyebrows"]["threshold"], 0.37, delta=0.05)

    def test_tiring_movement_scores_lower(self):
        steady = self.record(lambda kind, name, attempt:
                             {name: 0.6} if kind == "do" else {})
        tiring = self.record(lambda kind, name, attempt:
                             {name: 0.6 / attempt} if kind == "do" else {})
        self.assertGreater(steady[0]["score"], tiring[0]["score"] + 15)


if __name__ == "__main__":
    unittest.main()
