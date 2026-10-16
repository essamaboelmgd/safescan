# Meyar | معيار

Meyar is the current name and UI/branding contribution for this project. It builds on the original SafeScan Flutter client and FastAPI research prototype. **Before academic submission, replace the placeholders in [the Arabic handoff](docs/MEYAR_HANDOFF_AR.md) with the original author's and each contributor's names.** The visual search gathers evidence; it does not authenticate products or certify safety.

The supplied Arabic concept document was read before implementation. Its examples describe intended uses, not verified product findings. A user-supplied shoe dataset has been audited and used for a separately named exploratory classifier trained on publisher-provided labels. Physical-unit independence and real-world authenticity accuracy remain unverified. No verified safety claims, recalls or certifications are bundled.

## Run from Windows PowerShell

```powershell
Set-Location C:\path\to\project
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

In a second terminal:

```powershell
dart --version
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The Flutter SDK must bundle Dart **3.13.5 or newer**, as required by `pubspec.yaml`.
`10.0.2.2` is for the standard Android emulator. For a phone, replace it with the Windows Wi-Fi IPv4 address and follow [setup](docs/SETUP.md). The in-app settings button changes the address for the current session. Debug/profile Android builds permit local HTTP; release deployments need HTTPS.

## What is implemented

- Camera/gallery upload and mobile barcode scanning, checksum validation, network errors, evidence results and paged server history.
- JPEG/PNG/WebP decoding with EXIF orientation, size limits, aspect-preserving resizing, blur/lighting checks, HSV/edge features and perceptual hashing.
- Exact cosine top-k search and deterministic random-hyperplane LSH with exact candidate reranking.
- SQLite products, source-qualified safety records, references, uploads and scans; local structured search and optional food catalogue lookup.
- Real-data manifest validation/import, group-isolated splitting, NumPy logistic classifier training, held-out evaluation and retrieval benchmarking.
- Conservative `Likely Authentic`, `Suspicious`, `Unknown / Insufficient Evidence` policy. Estimate labels are disabled by default pending domain validation. A barcode or high similarity alone never authenticates an item.

Current build and test status for this checkout is recorded in [local verification](docs/LOCAL_VERIFICATION.md). The later exploratory experiment below measures agreement with publisher labels; real-world authenticity accuracy is not established. The model is a handcrafted-feature baseline, not a fine-grained neural or forensic authentication system.

## Shoe dataset audit on 16 October 2026

The user-provided **Original or Fake Shoes v1 COCO ZIP** contains 1,497 images and 2,703 object annotations. Originals are preserved under `data/raw/original_or_fake_shoes_v1/`; every extracted file was verified against the unchanged ZIP. The [dataset publisher](https://universe.roboflow.com/shoes-classification-ovo/original-or-fake-shoes-5tbgz) and export declare Public Domain/CC0.

**The initial strict-authenticity audit stopped before training.** It found three exact-image groups with conflicting authentic/counterfeit labels, three exact-duplicate groups crossing train/validation, four shared video-source groups crossing train/validation, four mixed-class images, and no verified physical-unit identities. The original test split contains just one counterfeit image. All images decode; eight exceed the current pixel cap and two of those also have swapped COCO dimensions. Overall unambiguous publisher claims are 708 authentic and 779 counterfeit.

`data/manifest.csv` remains header-only. The preserved `data/manifest.shoes.review_required.csv` stages 1,465 records with blank group ids and splits; it remains **not trainable input**. The later exploratory run uses a separate manifest under an explicitly limited scope. See the [original strict audit](reports/shoes_dataset/REPORT.md) and [machine-readable audit](reports/shoes_dataset/audit.json); both are unchanged historical evidence.

The backend suite, including new extraction/audit checks, passed **53 tests**. Flutter and Android Gradle configuration were unchanged. To reproduce the audit:

```powershell
.\.venv\Scripts\python.exe -m tools.audit_coco --archive "data/Original or Fake Shoes.v1i.coco.zip" --reuse-extracted
```

## Exploratory publisher-label experiment on 16 October 2026

One real baseline training run and one final held-out test evaluation completed. The separate manifest, `data/manifest.shoes.exploratory_v1.csv`, retains **1,462 images** after conservative exclusions and exact deduplication. Connected components keep known exact copies, shared source/video keys and audited near-duplicate candidates together, including links through excluded aliases. Both publisher labels and both shoe families occur in every split.

| Split | Images | Publisher authentic | Publisher counterfeit |
|---|---:|---:|---:|
| train | 1,023 | 491 | 532 |
| val | 220 | 106 | 114 |
| test | 219 | 105 | 114 |

| Held-out exploratory metric | Actual result |
|---|---:|
| Accuracy | **52.05%** |
| Precision for publisher counterfeit label | 53.54% |
| Recall for publisher counterfeit label | 59.65% |
| F1 for publisher counterfeit label | 56.43% |

Confusion matrix, rows true publisher labels and columns predictions, in `authentic, counterfeit` order: `[[46, 59], [46, 68]]`. **Accuracy equals the 52.05% training-majority baseline**, so this run demonstrates no accuracy improvement over always predicting the publisher counterfeit label.

The model is saved separately at `models/shoes_exploratory_v1.npz`, with an exploratory model card beside it. It uses the existing 192-feature linear classifier, fixed seed 42, 500 epochs, validation-only epoch selection and threshold 0.5. No model or threshold was tuned after test evaluation. It was initially kept separate from the application's default. The backend is now configured to load this existing artifact by default, without retraining; exploratory results always retain `Unknown / Insufficient Evidence` as their final status.

Detected hashes, source keys and observed relationship groups do not cross splits. **Unknown physical units, undetected image aliases, shared sellers/backgrounds and noisy labels can still cause leakage or bias.** All four recognized video sources were assigned wholly to training, so this run does not assess held-out-video performance. The result measures publisher-label agreement and cannot establish verified counterfeit detection.

See the [full experiment report](reports/shoes_exploratory_v1/REPORT.md), [actual evaluation JSON](reports/shoes_exploratory_v1/evaluation.json), [split and exclusion evidence](reports/shoes_exploratory_v1/split_report.json), and [preservation checks](reports/shoes_exploratory_v1/preservation_checks.json). The backend suite passed **57 tests**; no dependencies were installed. Originals, prior audit reports, the review manifest, Flutter source and Android files were preserved.

Commands used for this run are below. Existing versioned outputs are protected; use new manifest/report/model names for another experiment.

```powershell
.\.venv\Scripts\python.exe -m tools.prepare_exploratory_shoes
.\.venv\Scripts\python.exe -m tools.dataset validate --manifest data/manifest.shoes.exploratory_v1.csv
.\.venv\Scripts\python.exe -m tools.train --manifest data/manifest.shoes.exploratory_v1.csv --output models/shoes_exploratory_v1.npz --epochs 500 --learning-rate 0.1 --seed 42 --exploratory
.\.venv\Scripts\python.exe -m tools.evaluate --manifest data/manifest.shoes.exploratory_v1.csv --model models/shoes_exploratory_v1.npz --output reports/shoes_exploratory_v1/evaluation.json
```

## Activate the existing shoe model

The previous backend default looked for the absent `models/classifier.npz`. The default now loads `models/shoes_exploratory_v1.npz`; explicit `SAFESCAN_MODEL_PATH` overrides are still honored. Restart the existing Uvicorn server for the new configuration to take effect. No Flutter rebuild is needed.

See [exact restart commands and optional shoe reference import](docs/SHOE_MODEL.md). Model availability and reference count are separate: training does not populate SQLite. The reference guide uses only training images in a separate catalog manifest and does not change the frozen validation/test splits. All reference labels remain unverified publisher claims; the exploratory scope blocks authenticity verdicts even if estimate labels are enabled.

Activation verification passed **65 backend tests**. A separate API check loaded the actual existing weights, imported **1,023 training references** and two family records into an isolated runtime, and confirmed classification, search and the enforced Unknown result. The live catalog was not modified. The model, frozen reports/manifests, Flutter source and Android files remained byte-for-byte unchanged; see the [activation verification record](reports/model_activation/REPORT.md).

In a later explicitly authorized step, the **live catalog** was backed up and populated with **1,023 references from the frozen training partition only** (491 publisher authentic, 532 publisher counterfeit) and two unverified family records. The running API reports the new count without a restart. No duplicate images or held-out rows were imported, and no weights or application files changed. See the [live import, backup and checks](reports/live_reference_import/REPORT.md).

## Data and model commands

Populate `data/manifest.csv`, real image files under `data/`, and `data/products.json` according to the dataset guide, then:

```powershell
.\.venv\Scripts\python.exe -m tools.dataset validate --manifest data/manifest.csv
.\.venv\Scripts\python.exe -m tools.dataset import --manifest data/manifest.csv --products data/products.json
.\.venv\Scripts\python.exe -m tools.train --manifest data/manifest.csv --output models/classifier.npz
.\.venv\Scripts\python.exe -m tools.evaluate --manifest data/manifest.csv --model models/classifier.npz --output reports/evaluation.json
.\.venv\Scripts\python.exe -m tools.benchmark --manifest data/manifest.csv
```

The default active manifest is intentionally empty while verified-authenticity requirements remain unresolved. The review-only CSV must not be substituted as training input. The exploratory experiment uses its separate, explicitly named manifest and weights. Restart the API after importing independently reviewed references or changing model weights. Estimate labels require domain validation and remain disabled by default; the publisher-label experiment does not establish that validation.

## Verify and build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
flutter analyze
flutter test --reporter expanded
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## Documentation

| Guide | Contents |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Components, data flow, uncertainty and boundaries |
| [Setup](docs/SETUP.md) | Beginner-friendly Arabic Windows and Android Wi-Fi setup |
| [Dataset](docs/DATASET.md) | Required real data, provenance and schema |
| [Training](docs/TRAINING.md) | Baseline, validation, evaluation and limitations |
| [Testing](docs/TESTING.md) | Automated checks and real-network contract test |
| [Complexity](docs/ALGORITHM_COMPLEXITY.md) | Exact search, LSH, hashing and scaling |
| [API](docs/API.md) | Endpoints, contracts and errors |
| [User guide](docs/USER_GUIDE.md) | Scan, read results and handle uncertainty |
| [Academic report](docs/ACADEMIC_REPORT.md) | Problem, methods, experiment design and limitations |
| [Presentation outline](docs/PRESENTATION_OUTLINE.md) | Slides and speaker prompts |
| [Demo](docs/DEMO.md) | Honest demonstration with and without real data |

Project layout: `lib/` client, `backend/app/` API and algorithms, `backend/tests/` Python tests, `tools/` data/training utilities, `data/` original ZIP/extraction and quarantined review manifest, `models/` weights location, `runtime/` local generated data, `test/` Dart tests, `reports/` verification and dataset-audit records.
