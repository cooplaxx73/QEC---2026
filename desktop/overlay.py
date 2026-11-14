"""
The on-screen overlay: two buttons, the instructions panel and pop-ups.

Design rules from the project brief:
- Only four icon buttons stay on screen: Call Caregiver, Keyboard,
  Controls and Notifications.
- An incoming video call pops up and rings until it is answered.
- Everything is large, because webcam eye tracking is not pixel-accurate.
- Overlay windows never take keyboard focus, so typing still goes to the
  app the patient is using.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

# Always on top, no title bar, no taskbar entry, never takes keyboard focus.
OVERLAY_FLAGS = (
    Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    | Qt.Tool | Qt.WindowDoesNotAcceptFocus
)

RED, BLUE, GREEN, GREY = "#c62828", "#1565c0", "#2e7d32", "#455a64"
PANEL_STYLE = "background: #101820; color: white; font-size: 20px;"

INSTRUCTIONS = [
    "Move the cursor: look where you want it to go.",
    "Click: close both eyes for about half a second, then open them.",
    "Zoom: look at a target and lean towards the screen. "
    "Then sit back and click in the zoomed view.",
    "The phone button sends a message to your caregiver's phone.",
    "The keyboard button opens the on-screen keyboard for typing.",
    "The gear button opens Controls, where you choose what a long blink does.",
    "The bell button shows your notifications.",
    "Your camera is never shared unless you accept a video call.",
]


def make_button(text: str, colour: str, on_click,
                width=220, height=110, font_size=22) -> QPushButton:
    """A large, high-contrast button that is easy to hit with eye tracking."""
    button = QPushButton(text)
    button.setFixedSize(width, height)
    button.setFocusPolicy(Qt.NoFocus)
    button.setStyleSheet(
        f"QPushButton {{ background: {colour}; color: white; font-size: {font_size}px;"
        f" font-weight: bold; border: 3px solid white; border-radius: 16px; }}"
        f"QPushButton:hover {{ border: 6px solid #ffeb3b; }}"
    )
    button.clicked.connect(on_click)
    return button


def set_button_colour(button: QPushButton, colour: str) -> None:
    """Change a button's background, e.g. to highlight the chosen option."""
    # Colours are always 7 characters long, like "#2e7d32".
    style = button.styleSheet()
    start = style.index("background: ") + len("background: ")
    button.setStyleSheet(style[:start] + colour + style[start + 7:])


def screen_area():
    """The usable part of the main screen (without the taskbar)."""
    return QGuiApplication.primaryScreen().availableGeometry()


def centre_on_screen(window: QWidget) -> None:
    window.adjustSize()
    area = screen_area()
    window.move(
        area.x() + (area.width() - window.width()) // 2,
        area.y() + (area.height() - window.height()) // 2,
    )


# Controls the patient can tune themselves:
# (label, name in config.py, step, smallest, largest)
ADJUSTABLE = [
    ("Eyes closed for (seconds)", "click_hold_seconds", 0.1, 0.3, 1.4),
    ("Cursor steadiness", "cursor_smoothing", 0.1, 0.0, 1.0),
    ("Cursor reach", "cursor_sensitivity", 0.1, 0.5, 2.5),
]

# What a long blink can do: (button text, value stored in config.py)
BLINK_ACTIONS = [
    ("Left click", "left_click"),
    ("Right click", "right_click"),
    ("Double click", "double_click"),
]


class ButtonBar(QWidget):
    """The four icon buttons that are always visible, bottom-right corner."""

    call_clicked = Signal()
    keyboard_clicked = Signal()
    controls_clicked = Signal()
    notifications_clicked = Signal()

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        for icon, colour, signal, tip in [
            ("\u260E", RED, self.call_clicked, "Call caregiver"),          # telephone
            ("\u2328", BLUE, self.keyboard_clicked, "Keyboard"),           # keyboard
            ("\u2699", GREY, self.controls_clicked, "Controls"),           # gear
            ("\U0001F514", GREY, self.notifications_clicked, "Notifications"),  # bell
        ]:
            button = make_button(icon, colour, signal.emit, 110, 110, font_size=52)
            button.setToolTip(tip)
            layout.addWidget(button)

        # A red number on the bell shows how many notifications are unread.
        self.badge = QLabel(button)  # "button" is the bell, the last one made
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setGeometry(70, 6, 34, 34)
        self.badge.setStyleSheet(
            f"background: {RED}; color: white; font-size: 18px;"
            " font-weight: bold; border-radius: 17px;")
        self.set_unread(0)

        self.adjustSize()
        area = screen_area()
        self.move(area.right() - self.width(), area.bottom() - self.height())

    def set_unread(self, count: int) -> None:
        self.badge.setText(str(count))
        self.badge.setVisible(count > 0)


class Panel(QWidget):
    """A dark window in the middle of the screen. Base for the panels below."""

    def __init__(self, title: str):
        super().__init__(None, OVERLAY_FLAGS)
        self.setStyleSheet(PANEL_STYLE)
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(30, 30, 30, 30)
        self.rows.setSpacing(14)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 28px; font-weight: bold;")
        self.rows.addWidget(heading)

    def add_button_row(self, buttons: list) -> None:
        """buttons is a list of (text, colour, function to call)."""
        row = QHBoxLayout()
        for text, colour, on_click in buttons:
            row.addWidget(make_button(text, colour, on_click, 200, 100))
        self.rows.addLayout(row)

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            centre_on_screen(self)
            self.show()


class ControlsPanel(Panel):
    """Lets the patient choose how the controls behave."""

    instructions_clicked = Signal()
    recalibrate_clicked = Signal()
    quit_clicked = Signal()
    setting_changed = Signal(str, object)  # (name in config.py, new value)

    def __init__(self, settings):
        super().__init__("Controls")
        self.settings = settings

        # Row 1: what a long blink does.
        self.rows.addWidget(QLabel("A long blink does a:"))
        self.action_buttons = {}
        row = QHBoxLayout()
        for text, value in BLINK_ACTIONS:
            button = make_button(text, GREY, self.setter("blink_action", value), 200, 90)
            self.action_buttons[value] = button
            row.addWidget(button)
        self.rows.addLayout(row)

        # One row per number:  label   [-]  value  [+]
        self.value_labels = {}
        for label, name, step, smallest, largest in ADJUSTABLE:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            row.addWidget(make_button(
                "\u2212", GREY, self.adjuster(name, -step, smallest, largest),
                80, 80, font_size=34))
            value = QLabel()
            value.setFixedWidth(90)
            value.setAlignment(Qt.AlignCenter)
            value.setStyleSheet("font-size: 26px; font-weight: bold;")
            self.value_labels[name] = value
            row.addWidget(value)
            row.addWidget(make_button(
                "+", GREY, self.adjuster(name, step, smallest, largest),
                80, 80, font_size=34))
            self.rows.addLayout(row)

        # Zoom on or off.
        row = QHBoxLayout()
        row.addWidget(QLabel("Zoom when leaning towards the screen"), 1)
        self.zoom_button = make_button("", GREY, self.toggle_zoom, 180, 80)
        row.addWidget(self.zoom_button)
        self.rows.addLayout(row)

        self.add_button_row([
            ("Instructions", BLUE, self.instructions_clicked.emit),
            ("Recalibrate", GREY, self.recalibrate_clicked.emit),
            ("Turn off", GREY, self.quit_clicked.emit),
            ("Close", GREEN, self.hide),
        ])
        self.refresh()

    def setter(self, name: str, value):
        """Makes the function that a choice button runs when clicked."""
        return lambda: self.change(name, value)

    def adjuster(self, name: str, step: float, smallest: float, largest: float):
        """Makes the function that a - or + button runs when clicked."""
        def adjust():
            value = round(getattr(self.settings, name) + step, 2)
            self.change(name, min(max(value, smallest), largest))
        return adjust

    def toggle_zoom(self) -> None:
        self.change("zoom_enabled", not self.settings.zoom_enabled)

    def change(self, name: str, value) -> None:
        self.setting_changed.emit(name, value)
        self.refresh()

    def refresh(self) -> None:
        """Show the current values (the caregiver may have changed them)."""
        for name, label in self.value_labels.items():
            label.setText(f"{getattr(self.settings, name):.1f}")
        for value, button in self.action_buttons.items():
            chosen = value == self.settings.blink_action
            set_button_colour(button, GREEN if chosen else GREY)
        self.zoom_button.setText("On" if self.settings.zoom_enabled else "Off")
        set_button_colour(
            self.zoom_button, GREEN if self.settings.zoom_enabled else GREY)

    def toggle(self) -> None:
        self.refresh()
        super().toggle()


class NotificationsPanel(Panel):
    """Recent messages, e.g. "your caregiver changed your settings"."""

    read_aloud_clicked = Signal()
    SHOWN = 6  # how many of the newest messages to show

    def __init__(self):
        super().__init__("Notifications")
        self.messages = []  # (time as text, message), newest last
        self.list = QLabel()
        self.list.setWordWrap(True)
        self.list.setMinimumWidth(700)
        self.rows.addWidget(self.list)
        self.add_button_row([
            ("Read aloud", BLUE, self.read_aloud_clicked.emit),
            ("Clear", GREY, self.clear),
            ("Close", GREEN, self.hide),
        ])
        self.refresh()

    def add(self, time_text: str, message: str) -> None:
        self.messages.append((time_text, message))
        self.refresh()

    def newest(self) -> list:
        return self.messages[-self.SHOWN:][::-1]

    def clear(self) -> None:
        self.messages = []
        self.refresh()

    def refresh(self) -> None:
        lines = [f"{time_text}   {message}" for time_text, message in self.newest()]
        self.list.setText("\n\n".join(lines) or "No notifications.")
        if self.isVisible():
            centre_on_screen(self)  # the size may have changed


class IncomingCallPopup(Panel):
    """Rings until the patient accepts or declines a video call."""

    answered = Signal(str)   # "accept" or "decline"
    RING_SECONDS = 1.2
    GIVE_UP_AFTER_RINGS = 30

    def __init__(self):
        super().__init__("Incoming video call")
        self.phone = QLabel("\u260E")
        self.phone.setAlignment(Qt.AlignCenter)
        self.rows.addWidget(self.phone)
        message = QLabel("Your caregiver would like a video call.\n"
                         "Your camera stays off unless you accept.")
        message.setAlignment(Qt.AlignCenter)
        self.rows.addWidget(message)
        self.add_button_row([
            ("Accept", GREEN, lambda: self.answer("accept")),
            ("Decline", RED, lambda: self.answer("decline")),
        ])
        self.ring_timer = QTimer(self, interval=int(self.RING_SECONDS * 1000),
                                 timeout=self.ring)

    def start_ringing(self) -> None:
        self.rings = 0
        centre_on_screen(self)
        self.show()
        self.ring()
        self.ring_timer.start()

    def ring(self) -> None:
        """Beep and flash the phone. Give up if nobody answers."""
        self.rings += 1
        if self.rings > self.GIVE_UP_AFTER_RINGS:
            self.answer("decline")
            return
        QApplication.beep()
        colour = "#ffeb3b" if self.rings % 2 else "white"
        self.phone.setStyleSheet(f"font-size: 110px; color: {colour};")

    def answer(self, choice: str) -> None:
        self.ring_timer.stop()
        self.hide()
        self.answered.emit(choice)

    def stop_ringing(self) -> None:
        """The caregiver hung up before the patient answered."""
        self.ring_timer.stop()
        self.hide()


class InstructionsPanel(Panel):
    """Lists the controls, with a read-aloud button."""

    read_aloud_clicked = Signal()

    def __init__(self):
        super().__init__("How to use your eyes to control the computer")
        for line in INSTRUCTIONS:
            label = QLabel("\u2022  " + line)
            label.setWordWrap(True)
            self.rows.addWidget(label)
        self.add_button_row([
            ("Read aloud", BLUE, self.read_aloud_clicked.emit),
            ("Close", GREEN, self.hide),
        ])


class ChoicePopup(QWidget):
    """A question with large answer buttons, e.g. "Are you sure?"."""

    def __init__(self, question: str, choices: list[str], on_choice):
        """on_choice is called with the text of the button that was clicked."""
        super().__init__(None, OVERLAY_FLAGS)
        self.setStyleSheet(PANEL_STYLE)
        self.on_choice = on_choice
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        label = QLabel(question)
        label.setWordWrap(True)
        label.setMinimumWidth(500)
        label.setStyleSheet("font-size: 26px; font-weight: bold;")
        layout.addWidget(label)

        buttons = QHBoxLayout()
        for index, choice in enumerate(choices):
            # The first choice is the "go ahead" one, the rest are neutral.
            colour = GREEN if index == 0 else GREY
            buttons.addWidget(make_button(
                choice, colour, lambda checked=False, c=choice: self.choose(c)))
        layout.addLayout(buttons)
        centre_on_screen(self)
        self.show()

    def choose(self, choice: str) -> None:
        self.close()
        self.on_choice(choice)


class Toast(QLabel):
    """A short message at the top of the screen that hides by itself."""

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setStyleSheet(
            PANEL_STYLE + "padding: 18px 30px; border: 3px solid #ffeb3b;"
            "font-size: 22px; font-weight: bold;"
        )
        self.setAlignment(Qt.AlignCenter)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_message(self, text: str, seconds: float = 6) -> None:
        self.setText(text)
        self.adjustSize()
        area = screen_area()
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + 30)
        self.show()
        self.hide_timer.start(int(seconds * 1000))
