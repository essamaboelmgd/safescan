import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:scan_safe/api_client.dart';
import 'package:scan_safe/models.dart';

void main() {
  test('GTIN checks reject bad length, checksum and non-ASCII digits', () {
    expect(barcodeError('4006381333931'), isNull);
    expect(barcodeError('4006381333932'), isNotNull);
    expect(barcodeError('１２３４５６７８'), isNotNull);
    expect(barcodeError('123'), isNotNull);
  });
  test('scores preserve missing evidence', () {
    expect(percentage(null), 'Unavailable');
    expect(percentage(double.nan), 'Unavailable');
    expect(percentage(.91), '91.0%');
    expect(Verification({}).status, 'Unknown / Insufficient Evidence');
  });
  test('URL configuration requires a backend origin', () {
    expect(
      ApiClient.normalizeUrl(' http://192.168.1.2:8000/ '),
      'http://192.168.1.2:8000',
    );
    for (final url in [
      'file:///tmp',
      'localhost:8000',
      'https://user:pass@host',
      'http://host/api?x=1',
    ]) {
      expect(() => ApiClient.normalizeUrl(url), throwsA(isA<ApiException>()));
    }
  });
  test('upload uses actual two-stage API contract and barcode', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      baseUrl: 'http://test:8000',
      client: MockClient((request) async {
        requests.add(request);
        if (request.url.path == '/api/uploads') {
          expect(
            request.headers['content-type'],
            contains('multipart/form-data'),
          );
          return http.Response(jsonEncode({'upload_id': 'a' * 32}), 201);
        }
        expect(jsonDecode(request.body), {
          'upload_id': 'a' * 32,
          'barcode': '4006381333931',
        });
        return http.Response(
          jsonEncode({
            'status': 'Unknown / Insufficient Evidence',
            'prediction': {'available': false},
          }),
          200,
        );
      }),
    );
    final result = await client.verify(
      Uint8List.fromList([1, 2]),
      'test.png',
      barcode: '4006381333931',
    );
    expect(result.status, 'Unknown / Insufficient Evidence');
    expect(requests.map((r) => r.url.path), ['/api/uploads', '/api/verify']);
    client.close();
  });
  test(
    'HTTP errors, invalid JSON and network failures are actionable',
    () async {
      for (final response in [
        http.Response('{"detail":"Model missing"}', 503),
        http.Response('<html>error</html>', 502),
      ]) {
        final client = ApiClient(client: MockClient((_) async => response));
        await expectLater(client.health(), throwsA(isA<ApiException>()));
        client.close();
      }
      final client = ApiClient(
        client: MockClient((_) async => throw http.ClientException('offline')),
      );
      await expectLater(
        client.health(),
        throwsA(
          isA<ApiException>().having(
            (e) => e.message,
            'message',
            contains('Cannot reach'),
          ),
        ),
      );
      client.close();
    },
  );
  test(
    'empty upload and invalid barcode never send network requests',
    () async {
      final client = ApiClient(
        client: MockClient((_) async => throw StateError('Must not be called')),
      );
      await expectLater(
        client.verify(Uint8List(0), 'empty'),
        throwsA(isA<ApiException>()),
      );
      expect(() => client.lookupBarcode('123'), throwsA(isA<ApiException>()));
      client.close();
    },
  );
  test('history requests bounded pages and decodes results', () async {
    final client = ApiClient(
      client: MockClient((request) async {
        expect(request.url.queryParameters, {'limit': '20', 'offset': '20'});
        return http.Response(
          '{"items":[{"status":"Unknown / Insufficient Evidence"}]}',
          200,
        );
      }),
    );
    expect(
      (await client.history(offset: 20)).single.status,
      'Unknown / Insufficient Evidence',
    );
    client.close();
  });
}
