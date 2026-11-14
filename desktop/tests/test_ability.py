"""Ability-test scoring, with made-up data."""

import random
import unittest

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

import numpy as np  # noqa: E402

from ability_test import (MOVEMENTS, head_angles, make_schedule,  # noqa: E402
                          score_head, score_movements)
from gaze import POINTER_COLUMNS, GazeMapper  # noqa: E402

FRAME = 1 / 30      # the camera gives about 30 pictures a second
class AbilityScoring(unittest.TestCase):
    def record(self, face, head=lambda kind, name: (0.0, 0.0)) -> list:
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
                values = {
                    each: min(1, max(0, amounts.get(each, 0.03) + random.gauss(0, 0.02)))
                    for each in MOVEMENTS}
                sideways, up_down = head(doing, name)
                values["sideways"] = sideways + random.gauss(0, self.head_wobble)
                values["up_down"] = up_down + random.gauss(0, self.head_wobble)
                readings.append((part, moment, values))
        self.head = score_head(schedule, readings)
        return score_movements(schedule, readings)

    head_wobble = 0.3  # degrees the head shakes while holding still

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

    @staticmethod
    def turning(degrees):
        """A head that turns this far each way when asked."""
        ways = {"left": (-degrees, 0), "right": (degrees, 0),
                "up": (0, -degrees * 0.7), "down": (0, degrees * 0.7)}
        return lambda kind, name: ways[name] if kind == "turn" else (0.0, 0.0)

    def test_good_head_movement_is_recommended(self):
        self.record(lambda kind, name, attempt: {}, self.turning(18))
        self.assertGreaterEqual(self.head["score"], 90)
        self.assertEqual(self.head["reach"]["left"], 18)

    def test_small_or_one_sided_head_movement_is_not(self):
        self.record(lambda kind, name, attempt: {}, self.turning(4))
        self.assertLess(self.head["score"], 20)
        one_sided = lambda kind, name: (15.0, 0.0) if kind == "turn" and name == "right" else (0.0, 0.0)
        self.record(lambda kind, name, attempt: {}, one_sided)
        self.assertEqual(self.head["score"], 0)

    def test_shaky_head_scores_lower(self):
        self.record(lambda kind, name, attempt: {}, self.turning(18))
        steady = self.head["score"]
        self.head_wobble = 3.0
        self.record(lambda kind, name, attempt: {}, self.turning(18))
        self.assertLess(self.head["score"], steady - 30)

    def test_head_angles_from_matrix(self):
        turn = np.radians(20)
        matrix = np.eye(4)
        matrix[:3, 2] = [np.sin(turn), 0, np.cos(turn)]
        sideways, up_down = head_angles(matrix)
        self.assertAlmostEqual(sideways, 20, places=3)
        self.assertAlmostEqual(up_down, 0, places=3)


class HeadPointing(unittest.TestCase):
    def test_head_mode_ignores_the_eyes(self):
        rng = np.random.default_rng(3)
        targets = np.array([(x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9)] * 20)
        features = rng.normal(0, 1, (len(targets), 10))             # eyes: random
        features[:, 6] = targets[:, 0] * 0.5 + rng.normal(0, 0.005, len(targets))
        features[:, 7] = targets[:, 1] * 0.3 + rng.normal(0, 0.005, len(targets))
        mapper = GazeMapper()
        error = mapper.fit(features, targets, POINTER_COLUMNS["head"])
        self.assertLess(error, 0.03)
        looking_away = np.array([9.0] * 6 + [0.25, 0.15, 9.0, 9.0])  # eyes anywhere
        x, y = mapper.predict(looking_away)
        self.assertAlmostEqual(x, 0.5, delta=0.03)
        self.assertAlmostEqual(y, 0.5, delta=0.03)

    def test_eye_mode_still_uses_everything(self):
        mapper = GazeMapper()
        rng = np.random.default_rng(1)
        targets = np.array([(x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9)] * 10)
        features = rng.normal(0, 0.01, (len(targets), 10))
        features[:, 0] += targets[:, 0]
        features[:, 1] += targets[:, 1]
        self.assertLess(mapper.fit(features, targets), 0.05)
        self.assertEqual(mapper.columns, list(range(10)))


if __name__ == "__main__":
    unittest.main()
