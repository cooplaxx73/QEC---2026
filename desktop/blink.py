"""
Long-blink click detection.

A normal blink lasts about 0.1 to 0.4 seconds. We only click when both eyes
stay closed for longer than that, so reading never causes a click. Keeping
the eyes closed for a long time (resting) is ignored too.

The click fires when the eyes open again, so the patient can cancel a click
by simply keeping their eyes closed a little longer. just_ready turns True
for one frame when the eyes have been closed long enough, so the program
can play a sound that means "you can open your eyes now".

Libraries: none (plain Python).
Written with the assistance of Claude Code (Anthropic).
"""

MAX_HOLD_SECONDS = 2.5  # closed longer than this = resting or looking down, not clicking


class BlinkClicker:
    def __init__(self):
        self.closed_since = None  # time the eyes closed, or None if open
        self.last_duration = 0.0  # length of the latest blink, for the log
        self.last_started = 0.0   # time the latest blink began
        self.just_ready = False   # True on the frame the blink became long enough
        self.told_ready = False

    @property
    def eyes_closed(self) -> bool:
        return self.closed_since is not None

    def update(self, closed_amount: float, now: float,
               threshold: float, hold_seconds: float) -> bool:
        """Call once per camera frame. Returns True when a click should happen."""
        self.just_ready = False
        if closed_amount >= threshold:
            if self.closed_since is None:
                self.closed_since = now
                self.last_started = now
                self.told_ready = False
            if not self.told_ready and now - self.closed_since >= hold_seconds:
                self.just_ready = self.told_ready = True
            return False

        # Eyes are open. Were they closed for the right length of time?
        if self.closed_since is None:
            return False
        self.last_duration = now - self.closed_since
        self.closed_since = None
        return hold_seconds <= self.last_duration <= MAX_HOLD_SECONDS
