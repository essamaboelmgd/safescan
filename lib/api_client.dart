import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

abstract class SafeScanApi {
  String get baseUrl;
  Future<Json> health();
  Future<Verification> verify(
    Uint8List bytes,
    String filename, {
    String? barcode,
  });
  Future<Json> lookupBarcode(String barcode);
  Future<Json> product(String id);
  Future<List<Verification>> history({int offset = 0});
}

class ApiClient implements SafeScanApi {
  ApiClient({String? baseUrl, http.Client? client})
    : baseUrl = normalizeUrl(
        baseUrl ??
            const String.fromEnvironment(
              'API_BASE_URL',
              defaultValue: 'http://10.0.2.2:8000',
            ),
      ),
      _client = client ?? http.Client();

  @override
  final String baseUrl;
  final http.Client _client;

  static String normalizeUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw ApiException(
        'Use a backend address such as http://192.168.1.10:8000',
      );
    }
    return uri.replace(path: '').toString();
  }

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<Json> _send(http.BaseRequest request) async {
    try {
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 20)),
      ).timeout(const Duration(seconds: 20));
      dynamic decoded;
      try {
        decoded = jsonDecode(response.body);
      } on FormatException {
        throw ApiException(
          'The server returned an unreadable response (${response.statusCode}).',
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final detail = decoded is Json ? decoded['detail'] : null;
        throw ApiException(
          detail is String
              ? detail
              : 'Request rejected (${response.statusCode}). Check the input.',
        );
      }
      if (decoded is! Json)
        throw ApiException('The server returned an unexpected response.');
      return decoded;
    } on TimeoutException {
      throw ApiException(
        'Connection timed out. Check Wi-Fi and the backend address.',
      );
    } on http.ClientException {
      throw ApiException(
        'Cannot reach the backend. Check Wi-Fi, server address and Windows firewall.',
      );
    }
  }

  @override
  Future<Json> health() => _send(http.Request('GET', _uri('/health')));

  @override
  Future<Verification> verify(
    Uint8List bytes,
    String filename, {
    String? barcode,
  }) async {
    if (bytes.isEmpty || bytes.length > 8 * 1024 * 1024) {
      throw ApiException('Choose a nonempty image smaller than 8 MiB.');
    }
    if (barcode != null && barcodeError(barcode) != null)
      throw ApiException(barcodeError(barcode)!);
    final upload = http.MultipartRequest('POST', _uri('/api/uploads'));
    upload.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: filename),
    );
    final image = await _send(upload);
    final request = http.Request('POST', _uri('/api/verify'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode({
        'upload_id': image['upload_id'],
        'barcode': ?barcode,
      });
    return Verification(await _send(request));
  }

  @override
  Future<Json> lookupBarcode(String barcode) {
    final error = barcodeError(barcode);
    if (error != null) throw ApiException(error);
    return _send(http.Request('GET', _uri('/api/barcodes/$barcode')));
  }

  @override
  Future<Json> product(String id) => _send(
    http.Request('GET', _uri('/api/products/${Uri.encodeComponent(id)}')),
  );

  @override
  Future<List<Verification>> history({int offset = 0}) async {
    final response = await _send(
      http.Request('GET', _uri('/api/history?limit=20&offset=$offset')),
    );
    return (response['items'] as List)
        .map((item) => Verification(item as Json))
        .toList();
  }

  void close() => _client.close();
}
