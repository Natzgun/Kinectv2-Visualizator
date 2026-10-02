import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from sign_commands import ActivationGate, ActionRegistry, Templates


class CommandTests(unittest.TestCase):
    def test_stability_release_and_frame_gap(self):
        gate = ActivationGate()
        for t in (0, .2, .4, .6):
            self.assertIsNone(gate.update("N", t))
        self.assertEqual(gate.update("N", .9), "N")
        self.assertIsNone(gate.update("T", 1.1))
        self.assertIsNone(gate.update("T", 4))
        for t in (4.2, 4.4, 4.8):
            self.assertIsNone(gate.update(None, t))
        for t in (5, 5.3, 5.6):
            self.assertIsNone(gate.update("T", t))
        self.assertEqual(gate.update("T", 5.9), "T")

    def test_templates_persist_and_reject_ambiguous_or_other_profiles(self):
        points = np.arange(63).reshape(21, 3).tolist()
        hand = {"world_landmarks": points, "handedness": "Right"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "templates.json"
            templates = Templates(path)
            for _ in range(3):
                templates.add("LSP", "N", hand)
            templates = Templates(path)
            self.assertEqual(templates.recognize("LSP", hand), "N")
            self.assertIsNone(templates.recognize("LSE", hand))
            for _ in range(3):
                templates.add("LSP", "T", hand)
            self.assertIsNone(templates.recognize("LSP", hand))

    def test_actions_are_replaceable(self):
        light = Mock()
        registry = ActionRegistry({"light": light})
        registry.bindings["N"] = "light"
        registry.execute("N")
        light.assert_called_once_with()
        registry.execute("Z")
        light.assert_called_once_with()
