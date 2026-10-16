import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:scan_safe/api_client.dart';

void main() {
  const enabled = bool.fromEnvironment('RUN_LIVE_API');
  test(
    'Dart HTTP client reaches real FastAPI upload verify and history',
    () async {
      final api = ApiClient(
        baseUrl: const String.fromEnvironment(
          'LIVE_API_URL',
          defaultValue: 'http://127.0.0.1:8765',
        ),
      );
      addTearDown(api.close);
      final health = await api.health();
      expect(health['status'], 'ok');
      // In-memory 64x64 geometric fixture; never a real product or training image.
      final bytes = base64Decode(
        'iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAABD0lEQVR4nO2ayQ7CMBBDnSf+G/Hlw6EXULd0IROjvBswcTzEaaS2JSLkDDIHmYPMeXx+KOV1r3rEUz8GmYPMQf+0B1IorzL/Mp5h0MCi9c+fatqgQ/eHanIaqHFWWUnP7mvq6dz97ij6d789Fgv3Gwr2Bxkuf/+azliBbDDKz6LaiFA2eOVnrjkilA0yB5mDzEHmIHOQOcgcZA6/nqD+Hts5zbEC2dBgjntTFN9qI0LZ0Gaau1IUM50RoYaLEEsKTVfgSg+xMrZ1hM71EOujEvbA0R5isz5nE9f3EHuVaVehmh6ioibzMevkz/g58cTFy+s4yLJB5iBzkDnIHGQOMgeZg8xB5pTx8ncyZBu4yhug204AJu+96AAAAABJRU5ErkJggg==',
      );
      final result = await api.verify(bytes, 'GEOMETRIC-TEST-ONLY.png');
      expect(result.data['scan_id'], isA<String>());
      expect(result.data['warnings'], isA<List>());
      expect(result.disclaimer, contains('not official authentication'));
      if (health['model_available'] == false) {
        expect(result.status, 'Unknown / Insufficient Evidence');
        expect(result.prediction['confidence'], isNull);
      }
      final history = await api.history();
      expect(
        history.any((item) => item.data['scan_id'] == result.data['scan_id']),
        isTrue,
      );
    },
    skip: !enabled
        ? 'Enable RUN_LIVE_API with a real API running; see docs/TESTING.md.'
        : false,
  );
}
