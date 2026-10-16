# Setup guide for Windows and Android

## الفكرة ببساطة

التطبيق يعمل على الموبايل، وFastAPI يعمل على الكمبيوتر. الهاتف يرسل الصورة إلى الكمبيوتر عبر الشبكة المحلية. ظهور `Unknown / Insufficient Evidence` طبيعي عند عدم وجود نموذج مدرب أو صور مرجعية موثقة. لا يعني أن المنتج آمن أو غير آمن.

افتح PowerShell داخل مجلد المشروع. Python وFlutter وAndroid Studio مع Android SDK مطلوبة. يجب أن يكون Dart المرفق مع Flutter بإصدار **3.13.5 أو أحدث** لأن هذا هو الحد الأدنى المحدد في `pubspec.yaml`. نتائج الفحص الحالي موجودة في [تقرير التحقق](LOCAL_VERIFICATION.md). لا تحتاج إلى تفعيل البيئة الافتراضية إذا استخدمت مسار Python كما هو مكتوب.

```powershell
Set-Location C:\path\to\project
python --version
flutter --version
dart --version
flutter doctor -v
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
flutter pub get
```

أكمل إعداد Python وFlutter قبل تشغيل التطبيق. لا تستخدم SDK أقدم من متطلب Dart أعلاه؛ سيفشل `flutter pub get` قبل تنزيل الحزم.

## تشغيل الخادم

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

اترك النافذة مفتوحة. افتح `http://127.0.0.1:8000/health` على الكمبيوتر. يجب أن تظهر `status: ok`. قيمة `model_available: false` تعني عدم وجود نموذج، وليست عطلاً في الخادم. توثيق الطلبات التفاعلي في `http://127.0.0.1:8000/docs`.

للعمل على الكمبيوتر فقط استخدم `--host 127.0.0.1`. عنوان `0.0.0.0` يجعل الخادم يستمع على واجهات الشبكة، لكنه ليس العنوان الذي تكتبه على الهاتف.

## هاتف حقيقي على Wi-Fi

1. وصّل الهاتف والكمبيوتر بنفس شبكة Wi-Fi موثوقة. شبكات الضيوف قد تمنع الأجهزة من التواصل. أوقف VPN مؤقتاً إذا كان يمنع الاتصال المحلي.
2. شغّل `ipconfig` في PowerShell. ابحث عن `IPv4 Address` تحت Wi-Fi، مثلاً `192.168.1.10`. هذا مثال فقط؛ استخدم عنوان جهازك الحقيقي.
3. افتح على متصفح الهاتف `http://192.168.1.10:8000/health` بعد استبدال العنوان. لا تستخدم `localhost` على الهاتف لأنه يشير إلى الهاتف نفسه.
4. إذا منع Windows Firewall الاتصال، اسمح لـ Python على الشبكات الخاصة فقط من واجهة Windows Security، أو اطلب من مسؤول الجهاز فتح TCP 8000 للشبكة المحلية الموثوقة. لا توقف الجدار الناري بالكامل. لم يغيّر المشروع قواعد الجدار الناري تلقائياً.
5. فعّل Developer options وUSB debugging في Android، وصّل USB واقبل رسالة الثقة، ثم نفّذ `flutter devices` للحصول على معرّف الجهاز.
6. شغّل الأمر التالي بعد استبدال معرّف الجهاز وعنوان الكمبيوتر، أو عدّل العنوان من زر الإعدادات داخل التطبيق:

```powershell
flutter run -d YOUR_DEVICE_ID --dart-define=API_BASE_URL=http://192.168.1.10:8000
```

The API URL supplied with `--dart-define` is the default compiled into the app. The settings dialog overrides it only for the current process; restart restores the compiled value. API settings do not require rebuilding while the app is running.

## محاكي Android

```powershell
flutter emulators
flutter devices
flutter run -d YOUR_EMULATOR_ID --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` is the standard Android emulator alias for the host loopback interface. A physical phone uses the host LAN address. USB alternative, if Wi-Fi isolation is unavoidable:

```powershell
adb reverse tcp:8000 tcp:8000
flutter run -d YOUR_DEVICE_ID --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

## Model and network settings

| Variable | Default | Meaning |
|---|---|---|
| `SAFESCAN_DATA_DIR` | `runtime/` under project | SQLite and canonical uploaded images |
| `SAFESCAN_MODEL_PATH` | `models/shoes_exploratory_v1.npz` | Existing exploratory NumPy artifact; explicit overrides are honored |
| `SAFESCAN_ENABLE_ESTIMATES` | unset | `1` requests decision labels after independent validation; exploratory publisher-label models always remain Unknown |
| `SAFESCAN_NETWORK_METADATA` | unset | `1` permits external food barcode lookup on local miss |

Optional settings are set in the API terminal before launch. Relative model/data paths are resolved against the project directory. Paths outside the workspace are unnecessary. Defaults make no external catalogue requests and download no models. See [existing shoe model activation and reference import](SHOE_MODEL.md) for exact restart commands and the separation between weights and reference images. For external food metadata, review the provider's current API terms, attribution and rate limits before enabling it; do not use food data as an electrical, automotive or toy safety registry.

## Build and common failures

```powershell
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Debug APK location on success: `build/app/outputs/flutter-apk/app-debug.apk`. Debug/profile manifests allow plain HTTP for LAN development. Release builds require an HTTPS backend, real signing configuration and deployment work; the template's debug release signing is not a publishing configuration.

- If packages cannot download, check network/proxy permissions and rerun the install. Never interpret a failed download as an unavailable package version without checking the actual error.
- If Flutter stalls on its cache lock, close the command and verify SDK write permission; avoid deleting someone else's lock while a build is active.
- If Gradle reports a missing SDK/NDK/JDK, use `flutter doctor -v` and Android Studio SDK Manager. Accept Android licenses explicitly through `flutter doctor --android-licenses` when needed.
- For connection timeout, verify `/health` first on Windows and then on the phone; recheck the current Wi-Fi IPv4, port, private-network firewall permission and client isolation.
- For camera permission errors, allow camera access in Android app settings; barcode entry and gallery selection provide alternatives. A canceled image selection creates no scan.

The Android path is the supported target for this delivery. The retained iOS, desktop and web skeletons have not been built or verified.
