"""
Read-aloud (text-to-speech) that works offline.

Speaking takes a few seconds, so it runs on its own thread and the rest of
the program keeps working.

Libraries: pyttsx3 (uses the voices built into the computer):
https://pyttsx3.readthedocs.io

Written with the assistance of Claude Code (Anthropic).
"""

import queue
import threading


class Speaker:
    def __init__(self, settings):
        self.settings = settings
        self.waiting = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str) -> None:
        """Queue some text to be read aloud. Returns straight away."""
        self.waiting.put(text)

    def _run(self) -> None:
        # Imported here because pyttsx3 must be set up on the thread that uses it.
        import pyttsx3

        while True:
            text = self.waiting.get()
            try:
                # A fresh engine per sentence avoids a known pyttsx3 bug where
                # the second runAndWait() call never returns.
                engine = pyttsx3.init()
                engine.setProperty("rate", self.settings.speech_rate)
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                del engine
            except Exception as error:
                print("Read-aloud failed:", error)
