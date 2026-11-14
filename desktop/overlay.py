"""
The on-screen overlay: four icon buttons, their panels and pop-ups.

Design rules:
- Only four icon buttons stay on screen: Call Caregiver, Keyboard,
  Settings and Notifications.
- Settings is one window with tabs along the top: Instructions,
  Recalibrate and Turn off.
- An incoming video call pops up and rings until it is answered.
- Everything is large, because webcam eye tracking is not pixel-accurate.
- The button under the cursor gets a thick outline, so the patient can
  see what a blink will click.
- Overlay windows never take keyboard focus, so typing still goes to the
  app the patient is using.

Colours, fonts and icons live in theme.py.

Libraries: PySide6 (Qt for Python): https://doc.qt.io/qtforpython-6/
Written with the assistance of Claude Code (Anthropic).
"""

from html import escape

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

import theme

# Always on top, no title bar, no taskbar entry, never takes keyboard focus.
OVERLAY_FLAGS = (
    Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    | Qt.Tool | Qt.WindowDoesNotAcceptFocus
)

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

def make_button(text: str, kind: str, on_click,
                width=220, height=110, font_size=22) -> QPushButton:
    """A large button that is easy to hit with eye tracking.

    kind is "primary" (green), "secondary" (pale), "plain" (white) or
    "danger" (red). See BUTTON_KINDS in theme.py.
    """
    button = QPushButton(text)
    button.setFixedSize(width, height)
    button.setFocusPolicy(Qt.NoFocus)
    button.setStyleSheet(theme.button_style(kind, font_size))
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


class Card(QWidget):
    """A cream rounded card with a soft shadow. Base for every window here.

    The window itself is see-through. The card sits inside it with a
    margin, which leaves room for the shadow. Add content to self.rows.
    """

    def __init__(self, background: str = theme.CREAM, radius: int = 24):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        margin = theme.SHADOW_MARGIN
        outer = QVBoxLayout(self)
        outer.setContentsMargins(margin, margin, margin, margin)

        self.card = QFrame()
        self.card.setObjectName("card")
        self.card.setStyleSheet(
            f"#card {{ background: {background}; border: 1px solid {theme.BORDER};"
            f" border-radius: {radius}px; }}"
            f"QLabel {{ color: {theme.INK}; background: transparent;"
            f" font-family: {theme.SANS_CSS}; font-size: 20px; }}"
            f"QToolTip {{ color: {theme.WHITE}; background: {theme.GREEN_DARK};"
            f" border: none; padding: 6px 10px; font-size: 16px; }}"
        )
        theme.add_shadow(self.card)
        outer.addWidget(self.card)

        self.rows = QVBoxLayout(self.card)
        self.rows.setContentsMargins(34, 28, 34, 30)
        self.rows.setSpacing(16)


class ButtonBar(Card):
    """The four icon buttons that are always visible, bottom-right corner."""

    call_clicked = Signal()
    keyboard_clicked = Signal()
    settings_clicked = Signal()
    notifications_clicked = Signal()

    BUTTON_SIZE = 110

    def __init__(self):
        super().__init__(radius=30)
        self.rows.setContentsMargins(8, 8, 8, 8)
        self.rows.setSpacing(8)
        # Calling for help is the one green button, so it stands out.
        for name, kind, signal, tip in [
            ("phone", "primary", self.call_clicked, "Call caregiver"),
            ("keyboard", "plain", self.keyboard_clicked, "Keyboard"),
            ("gear", "plain", self.settings_clicked, "Settings"),
            ("bell", "plain", self.notifications_clicked, "Notifications"),
        ]:
            button = QPushButton()
            button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
            button.setFocusPolicy(Qt.NoFocus)
            button.setStyleSheet(theme.button_style(kind, radius=24))
            colour = theme.WHITE if kind == "primary" else theme.GREEN
            button.setIcon(theme.icon(name, colour, 54))
            button.setIconSize(QSize(54, 54))
            button.setToolTip(tip)
            button.clicked.connect(signal.emit)
            self.rows.addWidget(button)

        # A red number on the bell shows how many notifications are unread.
        self.badge = QLabel(button)  # "button" is the bell, the last one made
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setGeometry(68, 8, 34, 34)
        self.badge.setStyleSheet(
            f"background: {theme.DANGER}; color: {theme.WHITE}; font-size: 17px;"
            f" font-weight: 700; border: 2px solid {theme.WHITE}; border-radius: 17px;")
        self.set_unread(0)

        self.adjustSize()
        area = screen_area()
        self.move(area.right() - self.width() + 8, area.bottom() - self.height() + 8)

    def set_unread(self, count: int) -> None:
        self.badge.setText(str(count) if count < 100 else "99")
        self.badge.setVisible(count > 0)


class Panel(Card):
    """A titled window in the middle of the screen. Base for the panels below."""

    def __init__(self, title: str):
        super().__init__()
        self.heading = QLabel(title)
        self.heading.setStyleSheet(
            f"font-family: {theme.SERIF_CSS}; font-size: 38px; color: {theme.INK};")
        self.rows.addWidget(self.heading)

    def add_button_row(self, buttons: list, layout=None, centred=False) -> None:
        """buttons is a list of (text, kind, function to call)."""
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addStretch()
        for text, kind, on_click in buttons:
            row.addWidget(make_button(text, kind, on_click, 200, 90))
        if centred:
            row.addStretch()
        (layout or self.rows).addLayout(row)

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            centre_on_screen(self)
            theme.fade_in(self)


class SettingsPanel(Panel):
    """One window with three tabs along the top."""

    TABS = ["Instructions", "Recalibrate", "Turn off"]

    read_aloud_clicked = Signal()
    recalibrate_clicked = Signal()
    quit_clicked = Signal()

    def __init__(self):
        super().__init__("Settings")
        self.setFixedWidth(1040 + 2 * theme.SHADOW_MARGIN)

        # The tab strip: a pale bar, with the chosen tab filled in green.
        strip_frame = QFrame()
        strip_frame.setObjectName("tabs")
        strip_frame.setStyleSheet(
            f"#tabs {{ background: {theme.SAGE}; border-radius: 22px; }}")
        strip = QHBoxLayout(strip_frame)
        strip.setContentsMargins(6, 6, 6, 6)
        strip.setSpacing(6)
        self.tab_buttons = []
        for index, name in enumerate(self.TABS):
            button = QPushButton(name)
            button.setFixedHeight(84)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda checked=False, i=index: self.show_tab(i))
            self.tab_buttons.append(button)
            strip.addWidget(button)
        self.rows.addWidget(strip_frame)

        # One page per tab. Only the chosen page is visible.
        self.pages = QStackedWidget()
        self.pages.addWidget(self.instructions_page())
        self.pages.addWidget(self.action_page(
            "Look at 13 dots, one at a time. It takes about 30 seconds.\n"
            "Do this again if the cursor stops matching where you look.",
            "Start", "primary", self.recalibrate_clicked.emit))
        self.pages.addWidget(self.action_page(
            "Turns eye control off and removes the buttons from the screen.\n"
            "A helper will need to start the program again.",
            "Turn off", "danger", self.quit_clicked.emit))
        self.rows.addWidget(self.pages)

        self.add_button_row([("Close", "secondary", self.hide)])
        self.show_tab(0)

    # ----- tabs -----

    def show_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for number, button in enumerate(self.tab_buttons):
            if number == index:
                button.setStyleSheet(theme.button_style("primary", 21, 17))
            else:
                button.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {theme.INK};"
                    f" font-family: {theme.SANS_CSS}; font-size: 21px; font-weight: 600;"
                    f" border: {theme.HOVER_BORDER}px solid transparent;"
                    " border-radius: 17px; }"
                    f"QPushButton:hover {{ border-color: {theme.GREEN}; }}")

    def instructions_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 0)
        layout.setSpacing(12)
        for line in INSTRUCTIONS:
            row = QHBoxLayout()
            row.setSpacing(14)
            dot = QLabel("●")  # round bullet
            dot.setStyleSheet(f"color: {theme.GREEN}; font-size: 15px; padding-top: 5px;")
            dot.setAlignment(Qt.AlignTop)
            row.addWidget(dot)
            label = QLabel(line)
            label.setWordWrap(True)
            row.addWidget(label, 1)
            layout.addLayout(row)
        self.add_button_row(
            [("Read aloud", "primary", self.read_aloud_clicked.emit)], layout)
        return page

    def action_page(self, text: str, button_text: str, kind: str, on_click) -> QWidget:
        """A tab with an explanation and one big button."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 14, 6, 0)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"font-size: 23px; color: {theme.MUTED};")
        layout.addWidget(label)
        layout.addStretch()
        row = QHBoxLayout()
        row.addWidget(make_button(button_text, kind, on_click, 360, 130, 30))
        layout.addLayout(row)
        layout.addStretch()
        return page


class NotificationsPanel(Panel):
    """Recent messages, e.g. "your caregiver changed your settings"."""

    read_aloud_clicked = Signal()
    SHOWN = 6  # how many of the newest messages to show

    def __init__(self):
        super().__init__("Notifications")
        self.messages = []  # (time as text, message), newest last
        self.list = QLabel()
        self.list.setTextFormat(Qt.RichText)
        self.list.setWordWrap(True)
        self.list.setMinimumWidth(700)
        self.rows.addWidget(self.list)
        self.add_button_row([
            ("Read aloud", "primary", self.read_aloud_clicked.emit),
            ("Clear", "secondary", self.clear),
            ("Close", "secondary", self.hide),
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
        # Each message: the time in small grey text, then the message under it.
        lines = [
            f"<p style='margin: 0 0 16px 0;'>"
            f"<span style='color: {theme.MUTED}; font-size: 16px;'>{escape(time_text)}</span>"
            f"<br>{escape(message)}</p>"
            for time_text, message in self.newest()
        ]
        empty = f"<span style='color: {theme.MUTED};'>No notifications.</span>"
        self.list.setText("".join(lines) or empty)
        if self.isVisible():
            centre_on_screen(self)  # the size may have changed


class IncomingCallPopup(Panel):
    """Rings until the patient accepts or declines a video call."""

    answered = Signal(str)   # "accept" or "decline"
    RING_SECONDS = 1.2
    GIVE_UP_AFTER_RINGS = 30
    PHONE_SIZE = 132

    def __init__(self):
        super().__init__("Incoming video call")
        self.heading.setAlignment(Qt.AlignCenter)
        self.rows.setSpacing(20)

        # A round phone badge that pulses between green and pale as it rings.
        self.phone = QLabel()
        self.phone.setFixedSize(self.PHONE_SIZE, self.PHONE_SIZE)
        self.phone.setAlignment(Qt.AlignCenter)
        self.phone_pictures = {
            True: theme.icon_pixmap("phone", theme.WHITE, 64),
            False: theme.icon_pixmap("phone", theme.GREEN, 64),
        }
        self.rows.addWidget(self.phone, 0, Qt.AlignHCenter)

        message = QLabel("Your caregiver would like a video call.\n"
                         "Your camera stays off unless you accept.")
        message.setAlignment(Qt.AlignCenter)
        message.setMinimumWidth(520)
        self.rows.addWidget(message)
        self.add_button_row([
            ("Accept", "primary", lambda: self.answer("accept")),
            ("Decline", "danger", lambda: self.answer("decline")),
        ], centred=True)
        self.ring_timer = QTimer(self, interval=int(self.RING_SECONDS * 1000),
                                 timeout=self.ring)

    def start_ringing(self) -> None:
        self.rings = 0
        self.ring()
        centre_on_screen(self)
        theme.fade_in(self)
        self.ring_timer.start()

    def ring(self) -> None:
        """Beep and pulse the phone. Give up if nobody answers."""
        self.rings += 1
        if self.rings > self.GIVE_UP_AFTER_RINGS:
            self.answer("decline")
            return
        QApplication.beep()
        lit = self.rings % 2 == 1
        self.phone.setPixmap(self.phone_pictures[lit])
        self.phone.setStyleSheet(
            f"background: {theme.GREEN if lit else theme.SAGE};"
            f" border-radius: {self.PHONE_SIZE // 2}px;")

    def answer(self, choice: str) -> None:
        self.ring_timer.stop()
        self.hide()
        self.answered.emit(choice)

    def stop_ringing(self) -> None:
        """The caregiver hung up before the patient answered."""
        self.ring_timer.stop()
        self.hide()


class ChoicePopup(Card):
    """A question with large answer buttons, e.g. "Are you sure?"."""

    def __init__(self, question: str, choices: list[str], on_choice):
        """on_choice is called with the text of the button that was clicked."""
        super().__init__()
        self.on_choice = on_choice
        self.rows.setSpacing(26)
        label = QLabel(question)
        label.setWordWrap(True)
        label.setMinimumWidth(500)
        label.setStyleSheet(f"font-family: {theme.SERIF_CSS}; font-size: 28px;")
        self.rows.addWidget(label)

        buttons = QHBoxLayout()
        buttons.setSpacing(14)
        for index, choice in enumerate(choices):
            # The first choice is the "go ahead" one, the rest are neutral.
            kind = "primary" if index == 0 else "secondary"
            buttons.addWidget(make_button(
                choice, kind, lambda checked=False, c=choice: self.choose(c)))
        self.rows.addLayout(buttons)
        centre_on_screen(self)
        theme.fade_in(self)

    def choose(self, choice: str) -> None:
        self.close()
        self.on_choice(choice)


class Toast(Card):
    """A short message at the top of the screen that hides by itself."""

    def __init__(self):
        super().__init__(background=theme.GREEN_DARK, radius=20)
        self.rows.setContentsMargins(30, 18, 30, 18)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            f"color: {theme.WHITE}; font-size: 22px; font-weight: 600;")
        self.rows.addWidget(self.label)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_message(self, text: str, seconds: float = 6) -> None:
        self.label.setText(text)
        self.adjustSize()
        area = screen_area()
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + 4)
        if self.isVisible():
            self.setWindowOpacity(1)
        else:
            theme.fade_in(self)
        self.hide_timer.start(int(seconds * 1000))
