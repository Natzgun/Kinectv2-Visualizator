# Alphabet model provenance

These are **experimental static-letter reference classifiers**, not full sign-language translators. No model download or training is required when running the app. Classification uses the average distance to the three nearest references per letter, with rejection for distant or ambiguous poses. Distances are not confidence probabilities.

## LSP

- Source: Expo99, [Static Hand Gestures of the Peruvian Sign Language Alphabet](https://github.com/Expo99/Static-Hand-Gestures-of-the-Peruvian-Sign-Language-Alphabet).
- Revision: `351a609dfba4d38203a5bd46306cecb7887dc4dc`.
- License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The derived `lsp.npz` reference data is distributed under the same license. No endorsement is implied.
- Changes: extracted MediaPipe image landmarks, normalized wrist-relative pixel coordinates, canonicalized horizontal reflection, removed exact duplicates and reserved validation samples. Original images are not bundled.
- Source provides 150 images for each of 24 static letters. Images have isolated hands and dark backgrounds; Kinect scenes differ substantially. No signer-independent evaluation is available.

## ASL

- Source: Akram ADRANE, Othmane DAOUDI and Yassir HAKKOU, [American Sign Language Detection](https://github.com/AkramOM606/American-Sign-Language-Detection).
- Revision: `b85cfab0aa8b3c2d52a1deac32513840095dd06f`.
- Source file: `model/keypoint_classifier/keypoint.csv`, with its A–Z label mapping.
- License: MIT, reproduced in `ASL-LICENSE.txt`.
- Changes: excluded one non-single-hand row and dynamic J/Z classes, canonicalized reflection, removed exact duplicates and selected up to 300 training references per letter. No upstream executable code or pickle was loaded.

## Scope and evaluation

Both base models cover **A–I, K–Y** (24 letters). J/Z require motion and are deliberately excluded; Ñ is also unsupported. LSP and ASL use separate datasets and are never relabeled as each other. LSE remains personal-samples-only.

`*-evaluation.json` reports development-validation results on seeded per-letter random holdouts of detected landmarks. The ASL reference budget was adjusted using this validation set; it is **not an independent final test**. Similar captures/augmentations may occur across partitions, despite exact-feature deduplication. Results do not establish recognition accuracy on new signers or Kinect images. Detection failures and unknown inputs are not covered by accepted-only accuracy.

LSP: 608 correct / 670 held-out detected samples; 52 rejected and 10 wrong. ASL: 5,204 correct / 6,697 held-out samples; 1,335 rejected and 158 wrong. Counts include all classes; see per-letter results. LSP N in particular has 13 correct / 24 held-out samples; personal calibration remains useful for closed-fist/occluded-thumb signs. Do not interpret successful model loading as proof of real-world accuracy.

## Rebuild

Clone the sources at the revisions above outside the project, then run from `app/` in the `kinectv2-dev` environment:

```sh
python build_alphabet_models.py --lsp /path/to/lsp-data --asl /path/to/asl-data --cache /path/to/lsp-landmarks.npz
```

Use a fresh cache if the source images, normalization code or MediaPipe version change. Bundled artifacts were built with MediaPipe 0.10.35 and NumPy 1.26.4. All inference remains local.
