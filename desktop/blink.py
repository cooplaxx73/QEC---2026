"""
Long-blink click detection.

A normal blink lasts about 0.1 to 0.4 seconds. We only click when both eyes
stay closed for longer than that, so reading never causes a click. Keeping
the eyes closed for a long time (resting) is ignored too.

The click fires when the eyes open again, so the patient can cancel a click
by simply keeping their eyes closed a little longer.

Libraries: none (plain Python).
Written with the assistance of Claude Code (Anthropic).
"""

MAX_HOLD_SECONDS = 1.5  # closed longer than this = resting or looking down, not clicking


class BlinkClicker:
    def __init__(self):
        self.closed_since = None  # time the eyes closed, or None if open
        self.last_duration = 0.0  # length of the latest blink, for the log

    @property
    def eyes_closed(self) -> bool:
        return self.closed_since is not None

    def update(self, closed_amount: float, now: float,
               threshold: float, hold_seconds: float) -> bool:
        """Call once per camera frame. Returns True when a click should happen."""
        if closed_amount >= threshold:
            if self.closed_since is None:
                self.closed_since = now
            return False

        # Eyes are open. Were they closed for the right length of time?
        if self.closed_since is None:
            return False
        self.last_duration = now - self.closed_since
        self.closed_since = None
        return hold_seconds <= self.last_duration <= MAX_HOLD_SECONDS
