# Testing guide

See [local verification](LOCAL_VERIFICATION.md) for the commands attempted in this checkout, their outcomes and current environment blockers. This guide describes test intent and rerun commands; it does not assert that every platform is verified.

## Automated checks

Run from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
flutter analyze
flutter test --reporter expanded
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The backend suite isolates SQLite and images using temporary directories. It checks health, upload/preview, unavailable classification, exact/LSH retrieval, barcode and product lookup, combined verification, history, OpenAPI, malformed payloads, unknown fields, checksum failures, pagination limits, missing records, corrupt images and upload limits. Preprocessing tests cover deterministic features, normalization, canonical storage equivalence, size limits, orientation handling, unsupported containers and quality warnings.

Algorithm tests cover cosine ordering, zero vectors, dimension/NaN rejection, pHash popcount and identical-vector LSH behavior. Database tests check persistence, literal parameterized search, unique barcodes and absent records. Model tests check missing/incompatible/corrupt weights, metadata loading and conservative decision gates. Dataset tests reject missing data, duplicates, path escape and split leakage; splitter tests preserve groups deterministically. Network tests simulate failures and untrusted external claims, confirming that catalogue labels cannot create safety records.

Flutter unit tests check GTIN validation, nullable score formatting, URL validation, the two-stage multipart/verify contract, JSON/server/network errors, pre-network validation and history pagination. Widget tests cover health, connection failure/retry, saved evidence navigation, unknown results, missing confidence and scrolling at a small phone size. Geometric fixtures and temporary weights are clearly marked TEST ONLY. They are not a dataset or a model accuracy experiment.

## Real-network client contract

`test/live_backend_test.dart` is optional and skipped during the default offline test run. Start the real API on the test port in one terminal using a separate runtime directory:

```powershell
$env:SAFESCAN_DATA_DIR="$PWD\runtime\live-check"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

In a second terminal:

```powershell
flutter test test/live_backend_test.dart --dart-define=RUN_LIVE_API=true --dart-define=LIVE_API_URL=http://127.0.0.1:8765 --reporter expanded
```

This test sends a generated geometric PNG through the actual Dart HTTP client, verifies upload and combined result schema, and finds that scan in backend history. The fixture is generated in memory and is not a consumer product or training image. The check establishes a real HTTP contract on the host; it does not establish physical Android camera access or Wi-Fi connectivity.

## Manual device acceptance

On a real Android device, verify connection health, permission refusal, camera cancellation, gallery selection, barcode scanning/manual entry, invalid barcode, an actual product image, network loss, server restart, reference preview, candidate/metadata mismatch, history persistence, source visibility and small-screen scrolling. With a validated catalogue/model, assess each decision gate and copy-pasted genuine labels on counterfeit units. Record device/OS, image provenance, model/data checksums and actual outcomes.

The camera and mobile barcode plugin need hardware/emulator permission testing; they are not exercised by host widget tests. APK compilation and successful on-device launch are distinct outcomes. A passing test with an unavailable model is evidence of graceful degradation, not successful product classification.
