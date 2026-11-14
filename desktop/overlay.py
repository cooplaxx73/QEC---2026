"""
The on-screen overlay: two buttons, the instructions panel and pop-ups.

Design rules from the project brief:
- Only two icon buttons stay on screen: Settings and Call Caregiver.
- Everything else (instructions, keyboard, tuning) is behind Settings.
- Everything is large, because webcam eye tracking is not pixel-accurate.
- Overlay windows never take keyboard focus, so typing still goes to the
  app the patient is using.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

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
    "Type: open Settings and choose Keyboard.",
    "The gear button opens Settings.",
    "The phone button sends a message to your caregiver's phone.",
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


# Settings the patient can tune themselves:
# (label, name in config.py, step, smallest, largest)
ADJUSTABLE = [
    ("Click: eyes closed for (seconds)", "click_hold_seconds", 0.1, 0.3, 2.0),
    ("Cursor steadiness", "cursor_smoothing", 0.1, 0.0, 1.0),
    ("Cursor reach", "cursor_sensitivity", 0.1, 0.5, 2.5),
]


class ButtonBar(QWidget):
    """The two icon buttons that are always visible, bottom-right corner."""

    settings_clicked = Signal()
    call_clicked = Signal()

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        for icon, colour, signal, tip in [
            ("\u260E", RED, self.call_clicked, "Call caregiver"),   # telephone
            ("\u2699", GREY, self.settings_clicked, "Settings"),    # gear
        ]:
            button = make_button(icon, colour, signal.emit, 110, 110, font_size=52)
            button.setToolTip(tip)
            layout.addWidget(button)
        self.adjustSize()
        area = screen_area()
        self.move(area.right() - self.width(), area.bottom() - self.height())


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


class SettingsPanel(Panel):
    """Everything that is not needed all the time lives behind the gear."""

    instructions_clicked = Signal()
    keyboard_clicked = Signal()
    recalibrate_clicked = Signal()
    quit_clicked = Signal()
    setting_changed = Signal(str, float)  # (name in config.py, new value)

    def __init__(self, settings):
        super().__init__("Settings")
        self.settings = settings
        self.value_labels = {}

        # One row per adjustable setting:  label   [-]  value  [+]
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

        self.add_button_row([
            ("Instructions", BLUE, self.instructions_clicked.emit),
            ("Keyboard", BLUE, self.keyboard_clicked.emit),
            ("Recalibrate", GREY, self.recalibrate_clicked.emit),
            ("Turn off", GREY, self.quit_clicked.emit),
            ("Close", GREEN, self.hide),
        ])
        self.refresh()

    def adjuster(self, name: str, change: float, smallest: float, largest: float):
        """Makes the function that a - or + button runs when clicked."""
        return lambda: self.adjust(name, change, smallest, largest)

    def adjust(self, name: str, change: float, smallest: float, largest: float) -> None:
        value = round(getattr(self.settings, name) + change, 2)
        value = min(max(value, smallest), largest)
        self.setting_changed.emit(name, value)
        self.refresh()

    def refresh(self) -> None:
        """Show the current values (the caregiver may have changed them)."""
        for name, label in self.value_labels.items():
            label.setText(f"{getattr(self.settings, name):.1f}")

    def toggle(self) -> None:
        self.refresh()
        super().toggle()


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
