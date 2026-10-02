"""Model contract checks; held-out recognition results live in models/*-evaluation.json."""

import unittest

import numpy as np

from alphabet_model import AlphabetModel, STATIC_LETTERS, image_features, normalize_points


class AlphabetTests(unittest.TestCase):
    def test_both_bundled_models_have_distinct_static_reference_data(self):
        lsp, asl = AlphabetModel("LSP"), AlphabetModel("ASL")
        self.assertEqual(lsp.letters, list(STATIC_LETTERS))
        self.assertEqual(asl.letters, list(STATIC_LETTERS))
        self.assertNotEqual(lsp.samples.shape, asl.samples.shape)
        self.assertIsNone(lsp.predict(np.full(42, 100))["letter"])
        self.assertIsNone(asl.predict(np.full(42, 100))["letter"])

    def test_pixel_aspect_ratio_translation_and_mirror_are_consistent(self):
        rng = np.random.default_rng(10)
        points = rng.normal(size=(21, 2))
        expected = normalize_points(points)
        np.testing.assert_allclose(expected, normalize_points(points * 3 + 20), atol=1e-5)
        np.testing.assert_allclose(expected, normalize_points(points * [-1, 1]), atol=1e-5)
        hand = {"landmarks": np.column_stack((points / [1920, 1080], np.zeros(21))),
                "image_size": (1920, 1080)}
        np.testing.assert_allclose(expected, image_features(hand), atol=1e-5)

    def test_degenerate_and_unavailable_models_are_not_predictions(self):
        with self.assertRaises(ValueError):
            normalize_points(np.zeros((21, 2)))
        with self.assertRaises(ValueError):
            AlphabetModel("LSE")
