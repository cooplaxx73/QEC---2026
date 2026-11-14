"""
Webcam capture and face tracking.

Reads frames from the webcam and uses MediaPipe Face Landmarker to find
478 face points (including the iris of each eye), blink scores and the
direction the head is facing.

Libraries:
- OpenCV (cv2) for the webcam: https://opencv.org
- MediaPipe Face Landmarker for face tracking:
  https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- NumPy for arrays: https://numpy.org

Written with the assistance of Claude Code (Anthropic).
"""

import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

MODEL_FILE = Path(__file__).parent / "face_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


@dataclass
class FaceData:
    """Everything we measure from one camera frame."""

    frame: np.ndarray          # the camera picture (BGR colours)
    brightness: float          # average brightness, 0 (black) to 255
    found: bool = False        # was a face seen?
    landmarks: np.ndarray = None      # 478 rows of (x, y, z), each 0 to 1
    blendshapes: dict = None          # e.g. {"eyeBlinkLeft": 0.9, ...}
    head_matrix: np.ndarray = None    # 4x4 head position and rotation


class FaceTracker:
    """Opens the webcam and measures the face in each frame."""

    def __init__(self, camera_index: int = 0):
        download_model_if_missing()
        self.camera = cv2.VideoCapture(camera_index)
        # A small picture is enough and keeps tracking fast.
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self.camera.isOpened():
            raise RuntimeError("Could not open the webcam.")

        options = vision.FaceLandmarkerOptions(
            # Read the file ourselves so folders with unusual characters work.
            base_options=BaseOptions(model_asset_buffer=MODEL_FILE.read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        self.start_time = time.monotonic()
        self.last_timestamp_ms = -1

    def read(self) -> FaceData | None:
        """Grab one frame and measure it. Returns None if the camera failed."""
        ok, frame = self.camera.read()
        if not ok:
            return None

        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        data = FaceData(frame=frame, brightness=float(grey.mean()))

        # MediaPipe wants RGB colours and a timestamp that always goes up.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int((time.monotonic() - self.start_time) * 1000)
        timestamp_ms = max(timestamp_ms, self.last_timestamp_ms + 1)
        self.last_timestamp_ms = timestamp_ms
        result = self.landmarker.detect_for_video(image, timestamp_ms)

        if result.face_landmarks:
            points = result.face_landmarks[0]
            data.found = True
            data.landmarks = np.array([(p.x, p.y, p.z) for p in points])
            data.blendshapes = {
                shape.category_name: shape.score
                for shape in result.face_blendshapes[0]
            }
            data.head_matrix = np.array(result.facial_transformation_matrixes[0])
        return data

    def close(self) -> None:
        self.camera.release()
        self.landmarker.close()


def download_model_if_missing() -> None:
    """The face model is a 4 MB file from Google, fetched on first run."""
    if not MODEL_FILE.exists():
        print("Downloading the face tracking model (first run only)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_FILE)


if __name__ == "__main__":
    # Quick test: python camera.py
    tracker = FaceTracker()
    for _ in range(60):
        data = tracker.read()
        if data and data.found:
            blink = data.blendshapes["eyeBlinkLeft"]
            print(f"face found, brightness {data.brightness:.0f}, blink {blink:.2f}")
        else:
            print("no face")
    tracker.close()
