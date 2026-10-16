import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:scan_safe/api_client.dart';
import 'package:scan_safe/main.dart';
import 'package:scan_safe/models.dart';

class RecordingApi implements SafeScanApi {
  int verificationCalls = 0;
  ApiException? failure;
  @override
  String get baseUrl => 'http://test:8000';
  @override
  Future<Json> health() async => {};
  @override
  Future<Json> lookupBarcode(String barcode) async => {};
  @override
  Future<Json> product(String id) async => {};
  @override
  Future<List<Verification>> history({int offset = 0}) async => [];
  @override
  Future<Verification> verify(
    Uint8List bytes,
    String filename, {
    String? barcode,
  }) async {
    verificationCalls++;
    if (failure != null) {
      throw failure!;
    }
    return Verification({'status': 'Unknown / Insufficient Evidence'});
  }
}

class ControlledPicker extends ImagePicker {
  ControlledPicker(this.action);
  final Future<XFile?> Function() action;
  int calls = 0;
  ImageSource? requestedSource;

  @override
  Future<XFile?> pickImage({
    required ImageSource source,
    double? maxWidth,
    double? maxHeight,
    int? imageQuality,
    CameraDevice preferredCameraDevice = CameraDevice.rear,
    bool requestFullMetadata = true,
  }) {
    calls++;
    requestedSource = source;
    return action();
  }
}

class UnreadableImage extends XFile {
  UnreadableImage() : super('TEST-ONLY-unreadable');
  @override
  Future<Uint8List> readAsBytes() async =>
      throw StateError('TEST-ONLY read failure');
}

Future<void> tapPhotograph(WidgetTester tester) async {
  await tester.scrollUntilVisible(
    find.text('Photograph product'),
    150,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.tap(find.text('Photograph product'));
  await tester.pump();
}

void main() {
  late List<String> logs;
  void cameraTest(
    String description,
    Future<void> Function(WidgetTester) body,
  ) {
    testWidgets(description, (tester) async {
      logs = [];
      final previous = debugPrint;
      debugPrint = (message, {wrapWidth}) {
        if (message != null) logs.add(message);
      };
      try {
        await body(tester);
      } finally {
        // Restore before Flutter checks its global debug-variable invariants.
        debugPrint = previous;
      }
    });
  }

  cameraTest('camera cancellation makes no backend call and allows retry', (
    tester,
  ) async {
    final api = RecordingApi();
    final picker = ControlledPicker(() async => null);
    await tester.pumpWidget(ScanSafeApp(api: api, imagePicker: picker));
    await tapPhotograph(tester);
    await tester.pumpAndSettle();
    expect(picker.requestedSource, ImageSource.camera);
    expect(api.verificationCalls, 0);
    expect(find.byKey(const Key('error')), findsNothing);
    await tapPhotograph(tester);
    await tester.pumpAndSettle();
    expect(picker.calls, 2);
  });

  cameraTest(
    'pending picker blocks duplicate taps before any network request',
    (tester) async {
      final pending = Completer<XFile?>();
      final api = RecordingApi();
      final picker = ControlledPicker(() => pending.future);
      await tester.pumpWidget(ScanSafeApp(api: api, imagePicker: picker));
      await tapPhotograph(tester);
      await tester.tap(find.text('Photograph product'));
      await tester.pump();
      expect(picker.calls, 1);
      expect(api.verificationCalls, 0);
      pending.complete(null);
      await tester.pumpAndSettle();
    },
  );

  for (final code in [
    'camera_access_denied',
    'already_active',
    'channel-error',
  ]) {
    cameraTest(
      '$code is logged at the picker boundary without contacting backend',
      (tester) async {
        final api = RecordingApi();
        final picker = ControlledPicker(
          () async => throw PlatformException(code: code),
        );
        await tester.pumpWidget(ScanSafeApp(api: api, imagePicker: picker));
        await tapPhotograph(tester);
        await tester.pumpAndSettle();
        expect(api.verificationCalls, 0);
        expect(find.byKey(const Key('error')), findsOneWidget);
        expect(find.textContaining('backend connection'), findsNothing);
        expect(
          logs.any(
            (line) =>
                line.contains(
                  'stage=camera.picker failed: PlatformException',
                ) &&
                line.contains(code),
          ),
          isTrue,
        );
        expect(logs.any((line) => line.contains('failure stack')), isTrue);
      },
    );
  }

  cameraTest('missing native registration has actionable camera feedback', (
    tester,
  ) async {
    final api = RecordingApi();
    final picker = ControlledPicker(
      () async => throw MissingPluginException('TEST-ONLY'),
    );
    await tester.pumpWidget(ScanSafeApp(api: api, imagePicker: picker));
    await tapPhotograph(tester);
    await tester.pumpAndSettle();
    expect(api.verificationCalls, 0);
    expect(find.textContaining('install the rebuilt app'), findsOneWidget);
    expect(logs.any((line) => line.contains('MissingPluginException')), isTrue);
  });

  cameraTest(
    'unreadable selected file is distinct from camera and network failure',
    (tester) async {
      final api = RecordingApi();
      final picker = ControlledPicker(() async => UnreadableImage());
      await tester.pumpWidget(ScanSafeApp(api: api, imagePicker: picker));
      await tapPhotograph(tester);
      await tester.pumpAndSettle();
      expect(api.verificationCalls, 0);
      expect(
        find.textContaining('Could not read the selected image'),
        findsOneWidget,
      );
      expect(
        logs.any((line) => line.contains('stage=image.read failed')),
        isTrue,
      );
    },
  );

  cameraTest(
    'backend failure occurs only after picker success and is logged separately',
    (tester) async {
      final api = RecordingApi()
        ..failure = ApiException('TEST-ONLY backend unavailable');
      final picker = ControlledPicker(
        () async =>
            XFile.fromData(Uint8List.fromList([1, 2]), name: 'TEST-ONLY.png'),
      );
      await tester.pumpWidget(ScanSafeApp(api: api, imagePicker: picker));
      await tapPhotograph(tester);
      await tester.pumpAndSettle();
      expect(api.verificationCalls, 1);
      expect(find.text('TEST-ONLY backend unavailable'), findsOneWidget);
      expect(
        logs.any(
          (line) => line.contains('stage=backend.verify failed: ApiException'),
        ),
        isTrue,
      );
    },
  );

  cameraTest('successful image selection reaches evidence screen', (
    tester,
  ) async {
    final api = RecordingApi();
    final picker = ControlledPicker(
      () async =>
          XFile.fromData(Uint8List.fromList([1, 2]), name: 'TEST-ONLY.png'),
    );
    await tester.pumpWidget(ScanSafeApp(api: api, imagePicker: picker));
    await tapPhotograph(tester);
    await tester.pumpAndSettle();
    expect(api.verificationCalls, 1);
    expect(find.text('Verification evidence'), findsOneWidget);
    expect(find.text('Unknown / Insufficient Evidence'), findsOneWidget);
  });
}
