# Meyar local verification — 16 October 2026

This record covers the current redesign in this workspace. The Flutter app and
backend could not complete their full test/build gates in the available
environment, so the project remains **implemented, awaiting full verification**.

## Environment

- Python: 3.14.7.
- Dart: 3.10.4. `pubspec.yaml` requires Dart `^3.13.5` (3.13.5 or newer).
- The installed Flutter SDK also tried to write `bin/cache/engine.stamp` outside
  the writable workspace and was denied.

## Checks that completed

- `git diff --check` — passed.
- `python tools/generate_android_icons.py` — passed; regenerated all five
  Android density buckets from `assets/branding/meyar_icon.png`.
- `python -m json.tool web/manifest.json` — passed.
- Python XML/plist parsing — passed for all 9 Android XML files and
  `ios/Runner/Info.plist`.
- `magick identify` — confirmed the source, web icons, favicon and Windows ICO
  are readable at their intended sizes.
- Dart formatter — processed all 5 edited Dart files and reported 0 files
  changed. The command still exited nonzero because Flutter package resolution
  was unavailable and Dart analytics could not write outside the workspace.

## Checks blocked by the environment

- `flutter pub get` — blocked because installed Dart 3.10.4 is below the
  project's `^3.13.5` requirement.
- `flutter analyze`, `flutter test` and `flutter build apk` — not run; the
  compatible Flutter SDK and package resolution are unavailable here.
- `python -m pytest -q` — stopped during test collection because `cv2` is not
  installed. The local `.venv` also has no pytest package. Installing the
  backend requirements was attempted, but the 62 MB OpenCV wheel downloaded at
  roughly 45 KB/s, so that download was cancelled before installation.
- Android camera, gallery, barcode scanning and layout have not been exercised
  on an emulator or physical device after this redesign.

## Required verification on a compatible machine

Install Flutter with Dart 3.13.5 or newer, install `backend/requirements.txt`,
then follow [the Windows and Android setup guide](SETUP.md). Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
flutter analyze
flutter test --reporter expanded
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Finally, use the [manual device checks](TESTING.md#manual-device-acceptance).
Do not describe the build or tests as passing until those commands have actually
completed successfully. Software test results do not establish product
authenticity accuracy; the exploratory dataset result documented by the project
is 52.05%, equal to its majority-class baseline.
