"""Exercise both user-provided MediaPipe models without requiring a sensor."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from gestures import GestureThread, HandAnalyzer
from main import MainWindow


class HandAnalyzerTests(unittest.TestCase):
    def test_gesture_bundle_accepts_kinect_color_and_monotonic_time(self):
        analyzer = HandAnalyzer("Gestures", num_hands=2)
        try:
            frame = {
                "Color": np.zeros((360, 640, 4), dtype=np.uint8),
                "color_timestamp": 8000,
                "color_sequence": 1,
            }
            self.assertEqual(analyzer.analyze(frame)["hands"], [])
            self.assertEqual(analyzer.last_timestamp_ms, 1000)
            frame["color_sequence"] = 2
            self.assertEqual(analyzer.analyze(frame)["sequence"], 2)
            self.assertEqual(analyzer.last_timestamp_ms, 1001)
        finally:
            analyzer.close()

    def test_landmark_bundle_accepts_kinect_color(self):
        analyzer = HandAnalyzer("Landmarks")
        try:
            result = analyzer.analyze({
                "Color": np.zeros((360, 640, 4), dtype=np.uint8),
                "color_timestamp": 8000,
                "color_sequence": 3,
            })
            self.assertEqual(result, {"sequence": 3, "hands": [], "mode": "Landmarks"})
        finally:
            analyzer.close()

    def test_worker_keeps_only_latest_frame_without_a_sensor(self):
        app = QApplication.instance() or QApplication([])
        loop = QEventLoop()
        worker = GestureThread("Gestures")
        results = []
        errors = []
        worker.results_ready.connect(lambda result: (results.append(result), worker.stop()))
        worker.analysis_error.connect(errors.append)
        worker.finished.connect(loop.quit)
        worker.start()
        color = np.zeros((360, 640, 4), dtype=np.uint8)
        worker.submit({"Color": color, "color_timestamp": 8000, "color_sequence": 1})
        worker.submit({"Color": color, "color_timestamp": 8001, "color_sequence": 2})
        QTimer.singleShot(10000, worker.stop)
        loop.exec()
        self.assertFalse(worker.isRunning())
        self.assertEqual(errors, [])
        self.assertEqual([result["sequence"] for result in results], [2])

    def test_live_frames_are_forwarded_to_hand_worker(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.worker = SimpleNamespace(isInterruptionRequested=lambda: False)
        submit = Mock()
        window.gesture_worker = SimpleNamespace(submit=submit)
        frame = {
            "Color": np.zeros((8, 8, 4), dtype=np.uint8),
            "color_timestamp": 8000,
            "color_sequence": 1,
            "sequence": 1,
            "timestamp": 8000,
        }
        try:
            window.on_frames(frame)
            submit.assert_called_once_with(frame)
        finally:
            window.worker = None
            window.gesture_worker = None
            window.close()

    def test_recognized_hand_includes_scores_landmarks_and_registered_depth(self):
        analyzer = object.__new__(HandAnalyzer)
        analyzer.mode = "Gestures"
        analyzer.last_timestamp_ms = -1
        points = [SimpleNamespace(x=0.5, y=0.5, z=0.1) for _ in range(21)]
        result = SimpleNamespace(
            hand_landmarks=[points],
            hand_world_landmarks=[points],
            handedness=[[SimpleNamespace(category_name="Right")]],
            gestures=[[SimpleNamespace(category_name="Victory", score=0.9)]],
        )
        analyzer.task = SimpleNamespace(recognize_for_video=lambda image, timestamp: result)
        frame = {
            "Color": np.zeros((360, 640, 4), dtype=np.uint8),
            "Big depth": np.full((1082, 1920), 1500, dtype=np.float32),
            "color_timestamp": 8000,
            "color_sequence": 7,
        }
        hand = analyzer.analyze(frame)["hands"][0]
        self.assertEqual((hand["gesture"], hand["handedness"], hand["wrist_depth_m"]),
                         ("Victory", "Right", 1.5))
        self.assertEqual(len(hand["landmarks"]), 21)
        self.assertEqual(len(hand["world_landmarks"]), 21)


if __name__ == "__main__":
    unittest.main()
