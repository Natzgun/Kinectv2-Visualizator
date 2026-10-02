"""MediaPipe hand analysis on the latest owned Kinect color frame."""

from math import isfinite
from pathlib import Path
from threading import Condition

import cv2
import mediapipe as mp
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal


MODEL_DIR = Path(__file__).resolve().parent


class HandAnalyzer:
    def __init__(self, mode, num_hands=2):
        if mode not in ("Gestures", "Landmarks"):
            raise ValueError("Unknown hand analysis mode")
        self.mode = mode
        self.last_timestamp_ms = -1
        vision = mp.tasks.vision
        if mode == "Gestures":
            self.task = vision.GestureRecognizer.create_from_options(
                vision.GestureRecognizerOptions(
                    base_options=mp.tasks.BaseOptions(
                        model_asset_path=str(MODEL_DIR / "gesture_recognizer.task")
                    ),
                    running_mode=vision.RunningMode.VIDEO,
                    num_hands=num_hands,
                )
            )
        else:
            self.task = vision.HandLandmarker.create_from_options(
                vision.HandLandmarkerOptions(
                    base_options=mp.tasks.BaseOptions(
                        model_asset_path=str(MODEL_DIR / "hand_landmarker.task")
                    ),
                    running_mode=vision.RunningMode.VIDEO,
                    num_hands=num_hands,
                )
            )

    def close(self):
        self.task.close()

    def analyze(self, frame):
        color = frame["Color"]
        if color.shape[1] > 640:
            color = cv2.resize(color, (640, round(color.shape[0] * 640 / color.shape[1])),
                              interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(color, cv2.COLOR_BGRA2RGB)
        timestamp_ms = max(self.last_timestamp_ms + 1, int(frame["color_timestamp"]) // 8)
        self.last_timestamp_ms = timestamp_ms
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        if self.mode == "Gestures":
            result = self.task.recognize_for_video(image, timestamp_ms)
        else:
            result = self.task.detect_for_video(image, timestamp_ms)

        hands = []
        for index, landmarks in enumerate(result.hand_landmarks):
            hand = {
                "image_size": (color.shape[1], color.shape[0]),
                "landmarks": [(point.x, point.y, point.z) for point in landmarks],
                "world_landmarks": [(point.x, point.y, point.z)
                                    for point in (result.hand_world_landmarks[index]
                                                  if index < len(result.hand_world_landmarks) else ())],
                "handedness": (result.handedness[index][0].category_name
                               if result.handedness[index] else "Unknown"),
                "gesture": "None",
                "score": 0.0,
            }
            if self.mode == "Gestures" and result.gestures[index]:
                gesture = result.gestures[index][0]
                hand["gesture"] = gesture.category_name
                hand["score"] = gesture.score
            if "Big depth" in frame:
                wrist = landmarks[0]
                column = min(max(int(wrist.x * 1920), 0), 1919)
                row = min(max(int(wrist.y * 1080) + 1, 0), 1081)
                patch = frame["Big depth"][max(0, row-2):row+3, max(0, column-2):column+3]
                valid = patch[np.isfinite(patch) & (patch > 0)]
                distance_mm = float(np.median(valid)) if valid.size else 0.0
                if isfinite(distance_mm) and distance_mm > 0:
                    hand["wrist_depth_m"] = distance_mm / 1000
            hands.append(hand)
        return {"sequence": frame["color_sequence"], "hands": hands, "mode": self.mode}


class GestureThread(QThread):
    results_ready = pyqtSignal(object)
    analysis_error = pyqtSignal(str)

    def __init__(self, mode, num_hands=2, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.num_hands = num_hands
        self._condition = Condition()
        self._latest_frame = None

    def submit(self, frame):
        if "Color" not in frame:
            return
        with self._condition:
            if not self.isInterruptionRequested():
                self._latest_frame = frame
                self._condition.notify()

    def stop(self):
        self.requestInterruption()
        with self._condition:
            self._latest_frame = None
            self._condition.notify()

    def run(self):
        analyzer = None
        try:
            analyzer = HandAnalyzer(self.mode, self.num_hands)
            while not self.isInterruptionRequested():
                with self._condition:
                    while self._latest_frame is None and not self.isInterruptionRequested():
                        self._condition.wait()
                    frame = self._latest_frame
                    self._latest_frame = None
                if frame is not None and not self.isInterruptionRequested():
                    self.results_ready.emit(analyzer.analyze(frame))
        except Exception as error:
            self.analysis_error.emit(str(error))
        finally:
            if analyzer is not None:
                analyzer.close()
