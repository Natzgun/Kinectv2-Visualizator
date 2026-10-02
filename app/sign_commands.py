"""Personal static-pose templates; these are not validated language models."""

import json
from pathlib import Path

import numpy as np


def features(hand):
    points = np.asarray(hand.get("world_landmarks", []), dtype=float)
    if points.shape != (21, 3) or not np.isfinite(points).all():
        raise ValueError("A complete 3D hand is required")
    points = points - points[0]
    scale = np.linalg.norm(points[9])
    if scale < 1e-6:
        raise ValueError("Invalid palm size")
    return points / scale


class Templates:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
        if not isinstance(self.data, dict):
            raise ValueError("Invalid template file")
        for profile in self.data.values():
            if not isinstance(profile, dict):
                raise ValueError("Invalid template profile")
            for samples in profile.values():
                if not isinstance(samples, list) or len(samples) > 30:
                    raise ValueError("Invalid template samples")
                for sample in samples:
                    if not isinstance(sample, dict) or sample.get("side") not in ("Left", "Right"):
                        raise ValueError("Invalid template handedness")
                    points = np.asarray(sample.get("points"), dtype=float)
                    if points.shape != (21, 3) or not np.isfinite(points).all():
                        raise ValueError("Invalid template coordinates")

    def add(self, profile, letter, hand):
        sample = features(hand).tolist()
        samples = self.data.setdefault(profile, {}).setdefault(letter, [])
        samples.append({"side": hand["handedness"], "points": sample})
        del samples[:-30]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data), encoding="utf-8")
        temporary.replace(self.path)

    def recognize(self, profile, hand):
        vector = features(hand)
        distances = []
        for letter, samples in self.data.get(profile, {}).items():
            matches = [float(np.sqrt(np.mean((vector - np.asarray(s["points"])) ** 2)))
                       for s in samples if s["side"] == hand["handedness"]]
            if len(matches) >= 3:
                distances.append((min(matches), letter))
        distances.sort()
        if not distances or distances[0][0] > 0.12:
            return None
        if len(distances) > 1 and distances[1][0] - distances[0][0] < 0.035:
            return None
        return distances[0][1]


class ActivationGate:
    """Require a stable pose and sustained release before another action."""

    def __init__(self):
        self.candidate = None
        self.since = 0.0
        self.last = None
        self.release_since = None
        self.locked = False
        self.fired_at = float("-inf")

    def update(self, letter, now):
        if self.last is not None and now - self.last > 0.5:
            self.candidate = None
            self.release_since = None
        self.last = now
        if letter is None:
            self.candidate = None
            if self.release_since is None:
                self.release_since = now
            if now - self.release_since >= 0.5:
                self.locked = False
            return None
        self.release_since = None
        if letter != self.candidate:
            self.candidate, self.since = letter, now
        if not self.locked and now - self.since >= 0.8 and now - self.fired_at >= 2:
            self.locked, self.fired_at = True, now
            return letter
        return None


class ActionRegistry:
    """Handlers can later implement smart-device adapters without changing vision."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.bindings = {"N": "browser", "T": "terminal"}

    def execute(self, letter):
        action = self.bindings.get(letter)
        if action is None:
            return "No action assigned"
        self.handlers[action]()
        return f"Executed: {action}"
