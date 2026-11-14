"""Try the real overlay with a mouse, without a camera or caregiver backend.

Run with python preview_overlay.py. Press F9 or use Settings > Turn off to exit.
The on-screen keyboard types into the foreground app, as in the full program.
"""

import sys
import time

from pynput import keyboard
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from keyboard import OnScreenKeyboard
from overlay import (ButtonBar, ChoicePopup, IncomingCallPopup,
                     NotificationsPanel, SettingsPanel, Toast)


class OverlayPreview(QObject):
    quit_pressed = Signal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.buttons = ButtonBar()
        self.settings = SettingsPanel()
        self.notifications = NotificationsPanel()
        self.keyboard = OnScreenKeyboard()
        self.toast = Toast()
        self.incoming = IncomingCallPopup()
        self.popup = None
        for window, name in (
            (self.buttons, "Buttons"), (self.settings, "Settings"),
            (self.notifications, "Notifications"), (self.keyboard, "Keyboard"),
            (self.incoming, "Incoming call"), (self.toast, "Message"),
        ):
            window.setWindowTitle(f"SignalSpeak preview - {name}")
        self.buttons.settings_clicked.connect(self.settings.toggle)
        self.buttons.keyboard_clicked.connect(self.keyboard.toggle)
        self.buttons.notifications_clicked.connect(self.open_notifications)
        self.buttons.call_clicked.connect(self.preview_call)
        self.settings.quit_clicked.connect(app.quit)
        self.settings.recalibrate_clicked.connect(lambda: self.toast.show_message(
            "Preview: run main.py to calibrate with your webcam."))
        self.settings.read_aloud_clicked.connect(lambda: self.toast.show_message(
            "Preview: read-aloud is available in the full program."))
        self.notifications.read_aloud_clicked.connect(lambda: self.toast.show_message(
            "Preview: read-aloud is available in the full program."))
        self.incoming.answered.connect(lambda action: self.toast.show_message(
            "Preview call accepted. No camera or network was used."
            if action == "accept" else "Preview call declined."))
        self.notifications.add(time.strftime("%H:%M"),
                               "Sample notification: your caregiver is available.")
        self.buttons.set_unread(1)
        self.quit_pressed.connect(app.quit)
        self.hotkeys = keyboard.Listener(on_press=self.on_key)
        self.hotkeys.start()
        app.aboutToQuit.connect(self.hotkeys.stop)
        app.aboutToQuit.connect(self.incoming.stop_ringing)
        self.buttons.show()
        self.settings.toggle()
        self.toast.show_message("Overlay preview. Mouse control only. F9 exits.")

    def on_key(self, key):
        if key == keyboard.Key.f9:
            self.quit_pressed.emit()

    def open_notifications(self):
        self.buttons.set_unread(0)
        self.notifications.toggle()

    def preview_call(self):
        self.popup = ChoicePopup(
            "Preview a caregiver call?", ["Incoming call", "Cancel"],
            lambda choice: self.incoming.start_ringing()
            if choice == "Incoming call" else None)
        self.popup.setWindowTitle("SignalSpeak preview - Call options")


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    preview = OverlayPreview(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
