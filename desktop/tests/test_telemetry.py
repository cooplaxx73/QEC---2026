"""Standard-library tests for sampling and backwards-compatible local logs."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class TelemetryTests(unittest.TestCase):
    def test_sampling_is_throttled_and_invalid_samples_are_ignored(self):
        sampler = load('telemetry').GazeSampler()
        sample = sampler.sample((.25, .75), (400, 800), (1920, 1080), 1)
        self.assertEqual(sample['gaze_x'], .25)
        self.assertIsNone(sampler.sample((.3, .7), (400, 800), (1920, 1080), 1.2))
        self.assertIsNone(sampler.sample((float('nan'), 0), (0, 0), (1920, 1080), 1.5))
        self.assertIsNotNone(sampler.sample((.4, .6), (500, 700), (1920, 1080), 1.5))

    def test_existing_database_migrates_without_losing_older_events(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'events.db'
            old = sqlite3.connect(file)
            old.execute('CREATE TABLE events (time REAL, kind TEXT, value REAL, note TEXT)')
            old.execute("INSERT INTO events VALUES (1, 'click', .6, '')")
            old.commit(); old.close()
            log = load('activity_log').ActivityLog(file)
            event = log.record('gaze', details={'gaze_x': .5, 'gaze_y': .25})
            self.assertEqual(event['details']['gaze_y'], .25)
            self.assertEqual(log.database.execute('SELECT COUNT(*) FROM events').fetchone()[0], 2)
            self.assertIn('gaze_x', log.database.execute("SELECT details FROM events WHERE kind='gaze'").fetchone()[0])
            log.database.close()

if __name__ == '__main__':
    unittest.main()
