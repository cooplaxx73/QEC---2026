"""Sample estimated gaze at 2 Hz without storing video, text or screen contents.
Integration assistance: OpenAI Codex. Standard library only.
"""
import math


class GazeSampler:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.last_sample = float('-inf')

    def sample(self, gaze, cursor, size, now, origin=(0, 0)):
        if now - self.last_sample < self.interval:
            return None
        values = (*gaze, *cursor, *size, *origin)
        if not all(math.isfinite(v) for v in values) or min(size) <= 0:
            return None
        self.last_sample = now
        return {"gaze_x": round(min(1.0, max(0.0, gaze[0])), 4),
                "gaze_y": round(min(1.0, max(0.0, gaze[1])), 4),
                "cursor_x": int(cursor[0]), "cursor_y": int(cursor[1]),
                "screen_width": int(size[0]), "screen_height": int(size[1]),
                "screen_left": int(origin[0]), "screen_top": int(origin[1])}
