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

    def test_sign_workspace_starts_with_hand_analysis_without_advanced_setup(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            self.assertEqual(window.workspace.tabText(window.workspace.currentIndex()), "Recognize signs")
            window.gesture_mode.setCurrentText("Off")
            window.rgb_stream.setChecked(False)
            window.start_capture = Mock()
            window.start_recognition()
            self.assertEqual(window.gesture_mode.currentText(), "Landmarks")
            self.assertTrue(window.rgb_stream.isChecked())
            window.start_capture.assert_called_once_with()
            self.assertFalse(window.enable_actions.isChecked())
        finally:
            window.close()

    def test_live_letter_shows_match_not_training_selection_and_clears(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            window.templates = Mock()
            window.templates.recognize.return_value = "T"
            self.assertEqual(window.letter.currentText(), "N")
            window.process_commands([{}])
            self.assertEqual(window.recognized_letter.text(), "T")
            self.assertFalse(window.enable_actions.isChecked())
            window.process_commands([])
            self.assertEqual(window.recognized_letter.text(), "—")
            window.process_commands([{}])
            window.gesture_received_at = 0
            window.expire_recognized_letter()
            self.assertEqual(window.recognized_letter.text(), "—")
            window.process_commands([{}])
            window.reset_commands()
            self.assertEqual(window.recognized_letter.text(), "—")
        finally:
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
        self.assertEqual(hand["image_size"], (640, 360))

    def test_alphabet_dispatch_personal_priority_and_depth_rejection(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            personal = Mock()
            personal.data = {}
            personal.recognize.return_value = None
            window.templates = personal
            lsp, asl = Mock(), Mock()
            lsp.recognize.return_value = {"letter": "N"}
            asl.recognize.return_value = {"letter": "T"}
            window.base_models = {"LSP": lsp, "ASL": asl}
            window.process_commands([{}])
            self.assertEqual(window.recognized_letter.text(), "N")
            window.alphabet.setCurrentText("ASL")
            window.process_commands([{}])
            self.assertEqual(window.recognized_letter.text(), "T")
            personal.recognize.assert_called_with("ASL — personal samples", {})
            personal.recognize.return_value = "A"
            window.process_commands([{}])
            self.assertEqual(window.recognized_letter.text(), "A")
            window.require_distance.setChecked(True)
            window.process_commands([{}])
            self.assertEqual(window.recognized_letter.text(), "—")
            window.process_commands([{}, {}])
            self.assertEqual(window.recognized_letter.text(), "—")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
