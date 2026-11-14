"""
Turns face measurements into a point on the screen.

How it works:
1. gaze_features() describes where the eyes and head are pointing as a
   short list of numbers.
2. During calibration the patient looks at dots we know the position of.
   GazeMapper.fit() learns the link between the numbers and the screen
   using ridge regression (a least-squares line fit that resists noise).
3. GazeSmoother steadies the result so the cursor does not shake.

Sources:
- MediaPipe face landmark numbers (iris 468 and 473, eye corners 33, 133,
  362, 263): https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- NumPy: https://numpy.org

Written with the assistance of Claude Code (Anthropic).
"""

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


# Which of the ten numbers from gaze_features() each way of pointing uses.
# Head pointing ignores the eyes completely: only the direction of the face.
POINTER_COLUMNS = {
    "eyes": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    "head": [6, 7],
}


class GazeMapper:
    """Learns to turn gaze features into a screen position (0 to 1)."""

    # Ridge strength: higher = smoother but less precise. We try each one
    # and keep whichever predicts best on dots it was not shown.
    RIDGE_CHOICES = [0.1, 1.0, 10.0, 100.0]

    def __init__(self):
        self.weights = None
        self.columns = None  # which features to use (see POINTER_COLUMNS)

    @property
    def ready(self) -> bool:
        return self.weights is not None

    def fit(self, features: np.ndarray, targets: np.ndarray,
            columns: list = None) -> float:
        """features: one row per sample. targets: matching (x, y) rows.

        Returns the expected error as a fraction of the screen (0.05 = 5%).
        """
        # Put every feature on the same scale so none dominates.
        self.columns = columns or list(range(features.shape[1]))
        self.mean = features[:, self.columns].mean(axis=0)
        self.spread = features[:, self.columns].std(axis=0) + 1e-6
        inputs = self._prepare(features)

        # Honest accuracy test (cross-validation): hide one dot, learn from
        # the others, then measure how well the hidden dot is predicted.
        dots = np.unique(targets, axis=0)
        best_error, best_ridge = float("inf"), self.RIDGE_CHOICES[0]
        for ridge in self.RIDGE_CHOICES:
            errors = []
            for dot in dots:
                hidden = (targets == dot).all(axis=1)
                weights = self._solve(inputs[~hidden], targets[~hidden], ridge)
                errors.append(np.abs(inputs[hidden] @ weights - dot).mean())
            if np.mean(errors) < best_error:
                best_error, best_ridge = float(np.mean(errors)), ridge

        self.weights = self._solve(inputs, targets, best_ridge)
        return best_error

    @staticmethod
    def _solve(inputs: np.ndarray, targets: np.ndarray, ridge: float) -> np.ndarray:
        """Ridge regression: solve (X'X + ridge*I) W = X'Y."""
        penalty = ridge * np.eye(inputs.shape[1])
        penalty[-1, -1] = 0  # do not penalise the constant term
        return np.linalg.solve(inputs.T @ inputs + penalty, inputs.T @ targets)

    def predict(self, features: np.ndarray) -> tuple[float, float]:
        x, y = self._prepare(features[None, :])[0] @ self.weights
        return float(x), float(y)

    def _prepare(self, features: np.ndarray) -> np.ndarray:
        scaled = (features[:, self.columns] - self.mean) / self.spread
        ones = np.ones((len(scaled), 1))  # constant term
        return np.hstack([scaled, ones])


class GazeSmoother:
    """Steadies a noisy (x, y) gaze point.

    Eyes do two things: rest on a spot, or jump to a new one. So:
    - a reading close to the cursor is probably shake, and only nudges it;
    - a reading far from the cursor is a real look elsewhere, and the
      cursor goes there almost at once.

    Each reading is first replaced by the middle one of the last three,
    which removes single wild readings.
    """

    def __init__(self, smoothing: float = 0.5):
        self.set_smoothing(smoothing)
        self.recent = []      # the last three raw readings
        self.position = None  # the steadied point

    def set_smoothing(self, smoothing: float) -> None:
        """0 = fast and shaky, 1 = slow and steady."""
        # Readings closer than this (as a fraction of the screen) count as shake.
        self.shake_distance = 0.04 + 0.12 * smoothing
        # How far the cursor follows one reading that is only shake (0 to 1).
        self.steady_follow = 0.03 + 0.2 * (1 - smoothing) ** 2

    def update(self, point: tuple[float, float]) -> tuple[float, float]:
        self.recent = (self.recent + [point])[-3:]
        middle = np.median(np.array(self.recent), axis=0)
        if self.position is None:
            self.position = middle

        distance = float(np.linalg.norm(middle - self.position))
        how_far = min(1.0, distance / self.shake_distance)
        follow = self.steady_follow + (1 - self.steady_follow) * how_far ** 3
        self.position = self.position + follow * (middle - self.position)
        return float(self.position[0]), float(self.position[1])
