"""
The on-screen overlay: four icon buttons, their panels and pop-ups.

Design rules:
- Only four icon buttons stay on screen: Call Caregiver, Keyboard,
  Settings and Notifications.
- Settings is one window with tabs along the top (game-menu style):
  Instructions, Controls, Recalibrate and Turn off.
- An incoming video call pops up and rings until it is answered.
- Everything is large, because webcam eye tracking is not pixel-accurate.
- Overlay windows never take keyboard focus, so typing still goes to the
  app the patient is using.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

# Always on top, no title bar, no taskbar entry, never takes keyboard focus.
OVERLAY_FLAGS = (
    Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    | Qt.Tool | Qt.WindowDoesNotAcceptFocus
)

# Colours
RED, BLUE, GREEN, GREY = "#c62828", "#1f6bff", "#2e9d4f", "#3a4a78"
NAVY, NAVY_LIGHT, YELLOW, PALE = "#0b1638", "#18295e", "#ffd60a", "#c9d6ff"
PANEL_STYLE = f"background: {NAVY}; color: white; font-size: 20px;"

INSTRUCTIONS = [
    "Move the cursor: look where you want it to go.",
    "Click: close both eyes for about half a second, then open them.",
    "Zoom: look at a target and lean towards the screen. "
    "Then sit back and click in the zoomed view.",
    "The phone button sends a message to your caregiver's phone.",
    "The keyboard button opens the on-screen keyboard for typing.",
    "The gear button opens Settings.",
    "The bell button shows your notifications.",
    "Your camera is never shared unless you accept a video call.",
]

# Numbers the patient can tune in the Controls tab:
# (label, name in config.py, step, smallest, largest)
ADJUSTABLE = [
    ("Eyes closed for (seconds)", "click_hold_seconds", 0.1, 0.3, 1.4),
    ("Cursor steadiness", "cursor_smoothing", 0.1, 0.0, 1.0),
    ("Cursor reach", "cursor_sensitivity", 0.1, 0.5, 2.5),
]

# What a long blink can do: (text shown, value stored in config.py)
BLINK_ACTIONS = [
    ("Left click", "left_click"),
    ("Right click", "right_click"),
    ("Double click", "double_click"),
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
        f"QPushButton:hover {{ border: 6px solid {YELLOW}; }}"
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
    """The four icon buttons that are always visible, bottom-right corner."""

    call_clicked = Signal()
    keyboard_clicked = Signal()
    settings_clicked = Signal()
    notifications_clicked = Signal()

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        for icon, colour, signal, tip in [
            ("☎", RED, self.call_clicked, "Call caregiver"),          # telephone
            ("⌨", BLUE, self.keyboard_clicked, "Keyboard"),           # keyboard
            ("⚙", GREY, self.settings_clicked, "Settings"),           # gear
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


class Panel(QFrame):
    """A dark window in the middle of the screen. Base for the panels below."""

    def __init__(self, title: str):
        super().__init__(None, OVERLAY_FLAGS)
        self.setObjectName("panel")
        self.setStyleSheet(
            f"#panel {{ background: {NAVY}; border: 3px solid {BLUE}; }}"
            " QLabel { color: white; font-size: 20px; }"
        )
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(30, 24, 30, 30)
        self.rows.setSpacing(14)
        heading = QLabel(title.upper())
        heading.setStyleSheet(
            "font-size: 34px; font-weight: 900; font-style: italic;"
            f" letter-spacing: 3px; color: {YELLOW};")
        self.rows.addWidget(heading)

    def add_button_row(self, buttons: list, layout=None) -> None:
        """buttons is a list of (text, colour, function to call)."""
        row = QHBoxLayout()
        row.addStretch()
        for text, colour, on_click in buttons:
            row.addWidget(make_button(text, colour, on_click, 200, 90))
        (layout or self.rows).addLayout(row)

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            centre_on_screen(self)
            self.show()


class SettingRow(QFrame):
    """One line in the Controls tab:   LABEL            <   value   >"""

    def __init__(self, label: str, on_previous, on_next):
        super().__init__()
        self.setObjectName("row")
        self.setStyleSheet(f"#row {{ background: {NAVY_LIGHT}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 8, 8)

        name = QLabel(label.upper())
        name.setStyleSheet("font-size: 20px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(name, 1)

        self.value = QLabel()
        self.value.setFixedWidth(220)
        self.value.setAlignment(Qt.AlignCenter)
        self.value.setStyleSheet(
            f"font-size: 24px; font-weight: 900; color: {YELLOW};")

        layout.addWidget(self.arrow("◀", on_previous))  # left triangle
        layout.addWidget(self.value)
        layout.addWidget(self.arrow("▶", on_next))      # right triangle

    @staticmethod
    def arrow(symbol: str, on_click) -> QPushButton:
        button = QPushButton(symbol)
        button.setFixedSize(90, 74)
        button.setFocusPolicy(Qt.NoFocus)
        button.setStyleSheet(
            f"QPushButton {{ background: {GREY}; color: white; font-size: 28px;"
            f" border: none; }} QPushButton:hover {{ background: {BLUE}; }}")
        button.clicked.connect(on_click)
        return button

    def show_value(self, text: str) -> None:
        self.value.setText(text.upper())


class SettingsPanel(Panel):
    """One window with four tabs along the top, like a game settings menu."""

    TABS = ["Instructions", "Controls", "Recalibrate", "Turn off"]

    read_aloud_clicked = Signal()
    recalibrate_clicked = Signal()
    quit_clicked = Signal()
    setting_changed = Signal(str, object)  # (name in config.py, new value)

    def __init__(self, settings):
        super().__init__("Settings")
        self.settings = settings
        self.setFixedWidth(1040)

        # The tab strip.
        self.tab_buttons = []
        strip = QHBoxLayout()
        strip.setSpacing(4)
        for index, name in enumerate(self.TABS):
            button = QPushButton(name.upper())
            button.setFixedHeight(84)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda checked=False, i=index: self.show_tab(i))
            self.tab_buttons.append(button)
            strip.addWidget(button)
        self.rows.addLayout(strip)

        # One page per tab. Only the chosen page is visible.
        self.pages = QStackedWidget()
        self.pages.addWidget(self.instructions_page())
        self.pages.addWidget(self.controls_page())
        self.pages.addWidget(self.action_page(
            "Look at 13 dots, one at a time. It takes about 30 seconds.\n"
            "Do this again if the cursor stops matching where you look.",
            "Start", BLUE, self.recalibrate_clicked.emit))
        self.pages.addWidget(self.action_page(
            "Turns eye control off and removes the buttons from the screen.\n"
            "A helper will need to start the program again.",
            "Turn off", RED, self.quit_clicked.emit))
        self.rows.addWidget(self.pages)

        self.add_button_row([("Close", GREY, self.hide)])
        self.show_tab(0)
        self.refresh()

    # ----- tabs -----

    def show_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for number, button in enumerate(self.tab_buttons):
            chosen = number == index
            # The chosen tab is bright yellow, the others are dim.
            button.setStyleSheet(
                "QPushButton { font-size: 20px; font-weight: 900; font-style: italic;"
                " letter-spacing: 2px; border: none;"
                f" border-bottom: 6px solid {YELLOW if chosen else NAVY_LIGHT};"
                f" background: {YELLOW if chosen else NAVY_LIGHT};"
                f" color: {NAVY if chosen else PALE}; }}"
                f" QPushButton:hover {{ border-bottom: 6px solid {YELLOW}; }}"
            )

    def instructions_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        for line in INSTRUCTIONS:
            label = QLabel("▸  " + line)  # small triangle bullet
            label.setWordWrap(True)
            layout.addWidget(label)
        self.add_button_row(
            [("Read aloud", BLUE, self.read_aloud_clicked.emit)], layout)
        return page

    def controls_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        self.action_row = SettingRow(
            "Long blink does a",
            lambda: self.cycle_blink_action(-1), lambda: self.cycle_blink_action(1))
        layout.addWidget(self.action_row)

        self.number_rows = {}
        for label, name, step, smallest, largest in ADJUSTABLE:
            row = SettingRow(
                label,
                self.stepper(name, -step, smallest, largest),
                self.stepper(name, step, smallest, largest))
            self.number_rows[name] = row
            layout.addWidget(row)

        self.zoom_row = SettingRow("Zoom when leaning in", self.toggle_zoom, self.toggle_zoom)
        layout.addWidget(self.zoom_row)
        layout.addStretch()
        return page

    def action_page(self, text: str, button_text: str, colour: str, on_click) -> QWidget:
        """A tab with an explanation and one big button."""
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 24px;")
        layout.addWidget(label)
        layout.addStretch()
        row = QHBoxLayout()
        row.addWidget(make_button(button_text.upper(), colour, on_click, 360, 130, 30))
        layout.addLayout(row)
        layout.addStretch()
        return page

    # ----- changing a control -----

    def cycle_blink_action(self, direction: int) -> None:
        """Move to the previous (-1) or next (+1) blink action."""
        values = [value for _, value in BLINK_ACTIONS]
        position = values.index(self.settings.blink_action) + direction
        self.change("blink_action", values[position % len(values)])

    def stepper(self, name: str, step: float, smallest: float, largest: float):
        """Makes the function that an arrow button runs when clicked."""
        def change_number():
            value = round(getattr(self.settings, name) + step, 2)
            self.change(name, min(max(value, smallest), largest))
        return change_number

    def toggle_zoom(self) -> None:
        self.change("zoom_enabled", not self.settings.zoom_enabled)

    def change(self, name: str, value) -> None:
        self.setting_changed.emit(name, value)
        self.refresh()

    def refresh(self) -> None:
        """Show the current values (the caregiver may have changed them)."""
        texts = dict((value, text) for text, value in BLINK_ACTIONS)
        self.action_row.show_value(texts[self.settings.blink_action])
        for name, row in self.number_rows.items():
            row.show_value(f"{getattr(self.settings, name):.1f}")
        self.zoom_row.show_value("On" if self.settings.zoom_enabled else "Off")

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
            ("Close", GREY, self.hide),
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
        self.phone = QLabel("☎")
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
        colour = YELLOW if self.rings % 2 else "white"
        self.phone.setStyleSheet(f"font-size: 110px; color: {colour};")

    def answer(self, choice: str) -> None:
        self.ring_timer.stop()
        self.hide()
        self.answered.emit(choice)

    def stop_ringing(self) -> None:
        """The caregiver hung up before the patient answered."""
        self.ring_timer.stop()
        self.hide()


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
            PANEL_STYLE + f"padding: 18px 30px; border: 3px solid {YELLOW};"
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
