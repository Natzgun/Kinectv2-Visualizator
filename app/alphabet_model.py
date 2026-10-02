"""Dataset-backed static alphabets, with distance-based unknown rejection."""

from pathlib import Path

import numpy as np


MODEL_DIR = Path(__file__).resolve().parent / "models"
STATIC_LETTERS = tuple("ABCDEFGHIKLMNOPQRSTUVWXY")


def normalize_points(points):
    points = np.asarray(points, dtype=np.float32).reshape(21, 2).copy()
    if not np.isfinite(points).all():
        raise ValueError("Non-finite hand coordinates")
    points -= points[0]
    scale = np.max(np.abs(points))
    if scale < 1e-6:
        raise ValueError("Degenerate hand coordinates")
    points /= scale
    # Canonical horizontal orientation permits either hand, retaining vertical orientation.
    if points[5, 0] > points[17, 0]:
        points[:, 0] *= -1
    return points.reshape(42)


def image_features(hand):
    width, height = hand["image_size"]
    points = np.asarray(hand["landmarks"], dtype=np.float32)[:, :2]
    return normalize_points(points * (width, height))


class AlphabetModel:
    def __init__(self, language, directory=MODEL_DIR):
        if language not in ("ASL", "LSP"):
            raise ValueError("No base model for this alphabet")
        with np.load(Path(directory) / f"{language.lower()}.npz", allow_pickle=False) as data:
            self.samples = data["samples"].astype(np.float32)
            self.labels = data["labels"].astype(str)
        if (self.samples.ndim != 2 or self.samples.shape[1] != 42 or
                len(self.labels) != len(self.samples) or not np.isfinite(self.samples).all()):
            raise ValueError("Invalid alphabet model")
        self.letters = sorted(set(self.labels))
        if not set(self.letters).issubset(STATIC_LETTERS):
            raise ValueError("Unsupported static letter in model")
        self.indices = [np.flatnonzero(self.labels == letter) for letter in self.letters]

    def predict(self, vector):
        distances = np.sqrt(np.mean((self.samples - vector) ** 2, axis=1))
        scores = np.array([np.mean(np.sort(distances[index])[:3]) for index in self.indices])
        order = np.argsort(scores)
        best = int(order[0])
        distance = float(scores[best])
        margin = float(scores[order[1]] - distance) if len(order) > 1 else 1.0
        # These are geometric thresholds, not calibrated probabilities.
        letter = self.letters[best] if distance <= 0.12 and margin >= 0.015 else None
        return {"letter": letter, "distance": distance, "margin": margin}

    def recognize(self, hand):
        return self.predict(image_features(hand))
