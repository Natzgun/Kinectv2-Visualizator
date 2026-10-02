"""Build reproducible landmark reference models from the attributed datasets.

Run from app/: python build_alphabet_models.py --lsp /path/to/lsp --asl /path/to/asl
Only data files are consumed; no upstream Python or serialized executable models run.
"""

import argparse
import csv
import json
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

from alphabet_model import AlphabetModel, MODEL_DIR, STATIC_LETTERS, normalize_points


def extract_lsp(root, cache):
    if cache.exists():
        with np.load(cache, allow_pickle=False) as data:
            return data["samples"], data["labels"], int(data["attempted"])
    samples, labels = [], []
    attempted = 0
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(Path(__file__).with_name("hand_landmarker.task"))),
        running_mode=mp.tasks.vision.RunningMode.IMAGE, num_hands=1)
    with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
        for letter in STATIC_LETTERS:
            before = len(samples)
            for path in sorted((root / letter.lower()).glob("*.jpg")):
                attempted += 1
                rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
                result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
                if len(result.hand_landmarks) == 1:
                    points = [(p.x * rgb.shape[1], p.y * rgb.shape[0]) for p in result.hand_landmarks[0]]
                    samples.append(normalize_points(points))
                    labels.append(letter)
            print(letter, len(samples) - before, flush=True)
    np.savez_compressed(cache, samples=samples, labels=labels, attempted=attempted)
    return np.asarray(samples), np.asarray(labels), attempted


def build(language, samples, labels, attempted):
    # Remove exact duplicated feature rows before splitting.
    _, unique = np.unique(samples, axis=0, return_index=True)
    samples, labels = samples[unique], labels[unique]
    rng = np.random.default_rng(42)
    training, testing = [], []
    for letter in STATIC_LETTERS:
        indices = np.flatnonzero(labels == letter)
        rng.shuffle(indices)
        if len(indices) < 10:
            raise ValueError(f"Too few samples for {language} {letter}: {len(indices)}")
        split = max(2, len(indices) // 5)
        testing.extend(indices[:split])
        training.extend(indices[split:split + 300])
    MODEL_DIR.mkdir(exist_ok=True)
    np.savez_compressed(MODEL_DIR / f"{language.lower()}.npz",
                        samples=samples[training], labels=labels[training])
    model = AlphabetModel(language)
    results = [model.predict(samples[i])["letter"] for i in testing]
    accepted = sum(result is not None for result in results)
    correct = sum(result == labels[i] for result, i in zip(results, testing))
    report = {"attempted": attempted, "detected_unique": len(samples), "training": len(training),
              "held_out": len(testing), "accepted": accepted, "correct": correct,
              "coverage": accepted / len(testing), "accuracy_including_rejections": correct / len(testing),
              "accepted_accuracy": correct / accepted if accepted else 0,
              "split": "seed 42, per-letter 20% random holdout; not signer-independent",
              "per_letter": {letter: {"tested": sum(labels[i] == letter for i in testing),
                  "correct": sum(result == letter and labels[i] == letter for result, i in zip(results, testing))}
                  for letter in STATIC_LETTERS}}
    (MODEL_DIR / f"{language.lower()}-evaluation.json").write_text(json.dumps(report, indent=2))
    print(language, report, flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--lsp", type=Path, required=True)
    parser.add_argument("--asl", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    samples, labels, attempted = extract_lsp(args.lsp, args.cache)
    build("LSP", samples, labels, attempted)
    with (args.asl / "model/keypoint_classifier/keypoint.csv").open() as stream:
        rows = list(csv.reader(stream))
    # Some upstream rows contain two concatenated hands; this model is one-hand only.
    data = np.asarray([row for row in rows if len(row) == 43], dtype=np.float32)
    print("ASL excluded multi-hand/malformed rows:", len(rows) - len(data), flush=True)
    labels = np.array([chr(65 + int(value)) for value in data[:, 0]])
    keep = np.isin(labels, STATIC_LETTERS)
    samples = np.array([normalize_points(row) for row in data[keep, 1:]])
    build("ASL", samples, labels[keep], len(data))


if __name__ == "__main__":
    main()
