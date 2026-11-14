"""
Settings for the patient desktop program.

Every value that a patient or caregiver may want to tune lives here, so the
caregiver app can change them remotely by sending the same names.

Libraries: Python standard library only (dataclasses, json).
Written with the assistance of Claude Code (Anthropic).
"""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

FOLDER = Path(__file__).parent
SETTINGS_FILE = FOLDER / "settings.json"


@dataclass
class Settings:
    # Camera
    camera_index: int = 0

    # What moves the cursor: "eyes" (look at the target) or "head" (point
    # your nose at it). Head pointing is steadier but needs neck movement.
    pointer_mode: str = "eyes"

    # Cursor
    cursor_sensitivity: float = 1.0   # above 1 = less eye movement needed
    cursor_smoothing: float = 0.5     # 0 = fast and shaky, 1 = slow and steady

    # Clicking with a long blink
    blink_threshold: float = 0.5      # how closed the eyes must be (0 to 1)
    click_hold_seconds: float = 0.6   # how long the eyes must stay closed
    blink_action: str = "left_click"  # left_click, right_click or double_click

    # Which face movement clicks: blink, eyebrows, jaw, smile or pucker.
    # The ability test (ability_test.py) finds the best one and its threshold.
    click_signal: str = "blink"
    click_signal_threshold: float = 0.4   # how strong it must be (0 to 1)

    # Zoom by leaning towards the screen
    zoom_enabled: bool = True
    zoom_lean_ratio: float = 1.18     # face must look this much bigger
    zoom_factor: float = 2.5

    # Dark rooms
    low_light_enabled: bool = True
    low_light_threshold: int = 70     # camera brightness, 0 (black) to 255

    # Read-aloud voice
    speech_rate: int = 160            # words per minute

    # Caregiver backend (the stub server by default)
    backend_url: str = "http://127.0.0.1:8000"


def load_settings() -> Settings:
    """Read settings.json if it exists, otherwise use the defaults."""
    settings = Settings()
    if SETTINGS_FILE.exists():
        apply_changes(settings, json.loads(SETTINGS_FILE.read_text()))
    return settings


def save_settings(settings: Settings) -> None:
    SETTINGS_FILE.write_text(json.dumps(asdict(settings), indent=2))


def apply_changes(settings: Settings, changes: dict) -> dict:
    """Apply only known setting names. Returns the changes that were applied."""
    applied = {}
    for field in fields(Settings):
        if field.name in changes:
            old_value = getattr(settings, field.name)
            # Convert to the same type as the default (e.g. "0.7" -> 0.7).
            new_value = type(old_value)(changes[field.name])
            setattr(settings, field.name, new_value)
            applied[field.name] = new_value
    return applied
