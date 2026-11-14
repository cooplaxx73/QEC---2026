"""
Turns face measurements into a point on the screen.

How it works:
1. gaze_features() describes where the eyes and head are pointing as a
   short list of numbers.
2. During calibration the patient looks at dots we know the position of.
   GazeMapper.fit() learns the link between the numbers and the screen
   using ridge regression (a least-squares line fit that resists noise).
3. OneEuroFilter smooths the result so the cursor does not shake.

Sources:
- MediaPipe face landmark numbers (iris 468 and 473, eye corners 33, 133,
  362, 263): https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- One Euro Filter: Casiez, Roussel and Vogel, CHI 2012.
  https://gery.casiez.net/1euro/
- NumPy: https://numpy.org

Written with the assistance of Claude Code (Anthropic).
"""

import math

import numpy as np

# MediaPipe landmark numbers: (iris centre, outer corner, inner corner)
EYE_A = (468, 33, 133)
EYE_B = (473, 263, 362)


def iris_position(landmarks: np.ndarray, eye: tuple) -> tuple[float, float]:
    """Where the iris sits inside the eye, measured in eye-widths.

    Returns (across, up_down). Across is 0 at the outer corner and 1 at the
    inner corner. Dividing by the eye width means distance from the camera
    does not change the answer.
    """
    iris, outer, inner = (landmarks[i, :2] for i in eye)
    eye_line = inner - outer
    width = np.linalg.norm(eye_line)
    direction = eye_line / width
    offset = iris - outer
    across = float(offset @ direction) / width
    up_down = float(offset[1] * direction[0] - offset[0] * direction[1]) / width
    return across, up_down


def gaze_features(face) -> np.ndarray:
    """Ten numbers that describe where the eyes and head are pointing."""
    points = face.landmarks
    shapes = face.blendshapes
    across_a, up_down_a = iris_position(points, EYE_A)
    across_b, up_down_b = iris_position(points, EYE_B)

    # MediaPipe's own estimate of eye direction (each score is 0 to 1).
    look_sideways = (
        shapes["eyeLookInLeft"] - shapes["eyeLookOutLeft"]
        + shapes["eyeLookOutRight"] - shapes["eyeLookInRight"]
    ) / 2
    look_up = (
        shapes["eyeLookUpLeft"] + shapes["eyeLookUpRight"]
        - shapes["eyeLookDownLeft"] - shapes["eyeLookDownRight"]
    ) / 2

    # The third column of the head matrix is the way the face is pointing.
    head_sideways = face.head_matrix[0, 2]
    head_up = face.head_matrix[1, 2]

    # Where the face is in the camera picture (between the two eyes).
    face_x, face_y = (points[133, :2] + points[362, :2]) / 2

    return np.array([
        across_a, up_down_a, across_b, up_down_b,
        look_sideways, look_up, head_sideways, head_up, face_x, face_y,
    ])


def face_size(face) -> float:
    """Distance between the outer eye corners. Grows when leaning closer."""
    points = face.landmarks
    return float(np.linalg.norm(points[33, :2] - points[263, :2]))


def eyes_closed_amount(face) -> float:
    """0 = both eyes open, 1 = both closed. A one-eye wink scores low."""
    shapes = face.blendshapes
    return min(shapes["eyeBlinkLeft"], shapes["eyeBlinkRight"])


class GazeMapper:
    """Learns to turn gaze features into a screen position (0 to 1)."""

    RIDGE = 1.0  # higher = smoother but less precise mapping

    def __init__(self):
        self.weights = None

    @property
    def ready(self) -> bool:
        return self.weights is not None

    def fit(self, features: np.ndarray, targets: np.ndarray) -> None:
        """features: one row per sample. targets: matching (x, y) rows."""
        # Put every feature on the same scale so none dominates.
        self.mean = features.mean(axis=0)
        self.spread = features.std(axis=0) + 1e-6
        inputs = self._prepare(features)
        # Ridge regression: solve (X'X + ridge*I) W = X'Y
        penalty = self.RIDGE * np.eye(inputs.shape[1])
        penalty[-1, -1] = 0  # do not penalise the constant term
        self.weights = np.linalg.solve(
            inputs.T @ inputs + penalty, inputs.T @ targets
        )

    def predict(self, features: np.ndarray) -> tuple[float, float]:
        x, y = self._prepare(features[None, :])[0] @ self.weights
        return float(x), float(y)

    def _prepare(self, features: np.ndarray) -> np.ndarray:
        scaled = (features - self.mean) / self.spread
        ones = np.ones((len(scaled), 1))  # constant term
        return np.hstack([scaled, ones])


class OneEuroFilter:
    """Smooths a noisy (x, y) signal.

    Slow movements are smoothed a lot (steady cursor when reading) and fast
    movements only a little (no lag when looking across the screen).
    """

    def __init__(self, smoothing: float = 0.5):
        self.set_smoothing(smoothing)
        self.speed_gain = 1.0       # how quickly smoothing relaxes with speed
        self.previous = None
        self.previous_speed = np.zeros(2)
        self.previous_time = None

    def set_smoothing(self, smoothing: float) -> None:
        """0 = fast and shaky, 1 = slow and steady."""
        self.min_cutoff = 0.1 + 1.5 * (1 - smoothing) ** 2  # in hertz

    @staticmethod
    def _blend_amount(cutoff, dt):
        time_constant = 1 / (2 * math.pi * cutoff)
        return 1 / (1 + time_constant / dt)

    def update(self, point: tuple[float, float], now: float) -> tuple[float, float]:
        point = np.array(point)
        if self.previous is None:
            self.previous, self.previous_time = point, now
            return tuple(point)

        dt = max(now - self.previous_time, 1e-3)
        # Smooth the speed first, then use it to choose how much to smooth.
        speed = (point - self.previous) / dt
        blend = self._blend_amount(1.0, dt)
        speed = blend * speed + (1 - blend) * self.previous_speed
        cutoff = self.min_cutoff + self.speed_gain * np.abs(speed)
        blend = self._blend_amount(cutoff, dt)
        smoothed = blend * point + (1 - blend) * self.previous

        self.previous, self.previous_speed, self.previous_time = smoothed, speed, now
        return float(smoothed[0]), float(smoothed[1])
