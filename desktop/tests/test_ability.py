"""Ability-test scoring, with made-up data."""

import random
import unittest

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from ability_test import make_schedule, score_movements, MOVEMENTS  # noqa: E402

FRAME = 1 / 30      # the camera gives about 30 pictures a second
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
