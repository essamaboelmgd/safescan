# Meyar Android branding

The current Android display name is **Meyar**. The new launcher artwork is sourced from `assets/branding/meyar_icon.png`. The existing Android application ID `com.example.scan_safe` is preserved so the project keeps its install identity and existing local app data.

## Regenerate Android launcher resources

From the project root, with Pillow available in the active Python environment:

```powershell
python -m tools.generate_android_icons
```

The script creates legacy launcher PNGs and adaptive foreground layers for Android's five density buckets. Both use the full generated tile; the image's scan mark stays inside the adaptive icon's central safe area. The adaptive background is deep ink teal (`#143437`). The display-name string remains in `android/app/src/main/res/values/safescan_launcher.xml` to avoid changing the established native resource reference.

Build a debug APK from Windows PowerShell:

```powershell
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

This redesign also updates iOS, macOS, Windows and web icon assets. Those retained targets are not part of the Android release gate. Meyar has not yet been built or checked on a device in this checkout; see the [current verification record](LOCAL_VERIFICATION.md).
