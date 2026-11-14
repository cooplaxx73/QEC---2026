"""
The on-screen overlay: two buttons, the instructions panel and pop-ups.

Design rules from the project brief:
- Only two buttons stay on screen: Call Caregiver and Instructions.
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
    "Type: open the keyboard from this panel.",
    "Call Caregiver sends a message to your caregiver's phone.",
    "Your camera is never shared unless you accept a video call.",
]


def make_button(text: str, colour: str, on_click, width=220, height=110) -> QPushButton:
    """A large, high-contrast button that is easy to hit with eye tracking."""
    button = QPushButton(text)
    button.setFixedSize(width, height)
    button.setFocusPolicy(Qt.NoFocus)
    button.setStyleSheet(
        f"QPushButton {{ background: {colour}; color: white; font-size: 22px;"
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


class ButtonBar(QWidget):
    """The two buttons that are always visible, in the bottom-right corner."""

    call_clicked = Signal()
    instructions_clicked = Signal()

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.addWidget(make_button("Call\nCaregiver", RED, self.call_clicked.emit))
        layout.addWidget(make_button("Instructions", BLUE, self.instructions_clicked.emit))
        self.adjustSize()
        area = screen_area()
        self.move(area.right() - self.width(), area.bottom() - self.height())


class InstructionsPanel(QWidget):
    """Lists the controls. Also holds the less-used actions."""

    read_aloud_clicked = Signal()
    keyboard_clicked = Signal()
    recalibrate_clicked = Signal()
    quit_clicked = Signal()

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setStyleSheet(PANEL_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        title = QLabel("How to use your eyes to control the computer")
        title.setStyleSheet("font-size: 28px; font-weight: bold;")
        layout.addWidget(title)
        for line in INSTRUCTIONS:
            label = QLabel("•  " + line)
            label.setWordWrap(True)
            layout.addWidget(label)

        buttons = QHBoxLayout()
        for text, colour, signal in [
            ("Read aloud", BLUE, self.read_aloud_clicked),
            ("Keyboard", BLUE, self.keyboard_clicked),
            ("Recalibrate", GREY, self.recalibrate_clicked),
            ("Quit", GREY, self.quit_clicked),
            ("Close", GREEN, None),
        ]:
            action = signal.emit if signal else self.hide
            buttons.addWidget(make_button(text, colour, action, 200, 100))
        layout.addLayout(buttons)

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            centre_on_screen(self)
            self.show()


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
