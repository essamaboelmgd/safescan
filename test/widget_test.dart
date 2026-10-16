import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scan_safe/api_client.dart';
import 'package:scan_safe/main.dart';
import 'package:scan_safe/models.dart';
import 'package:scan_safe/result_screen.dart';

class FakeApi implements SafeScanApi {
  bool offline = false;
  @override
  String get baseUrl => 'http://test:8000';
  @override
  Future<Json> health() async {
    if (offline) throw ApiException('Cannot reach the backend.');
    return {'model_available': false, 'reference_count': 0};
  }

  @override
  Future<List<Verification>> history({int offset = 0}) async => [
    Verification({
      'status': 'Unknown / Insufficient Evidence',
      'created_at': 'TEST-TIME',
    }),
  ];
  @override
  Future<Json> lookupBarcode(String barcode) async => {
    'product': null,
    'warnings': ['No local record.'],
  };
  @override
  Future<Json> product(String id) async => {};
  @override
  Future<Verification> verify(
    Uint8List bytes,
    String filename, {
    String? barcode,
  }) async => Verification({});
}

void main() {
  testWidgets('home explains uncertainty and checks backend health', (
    tester,
  ) async {
    await tester.pumpWidget(ScanSafeApp(api: FakeApi()));
    expect(find.textContaining('AI predictions are estimates'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Check connection'), 180);
    await tester.tap(find.text('Check connection'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Model: unavailable'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('network failure stays visible and can be retried', (
    tester,
  ) async {
    final api = FakeApi()..offline = true;
    await tester.pumpWidget(ScanSafeApp(api: api));
    await tester.scrollUntilVisible(find.text('Check connection'), 180);
    await tester.tap(find.text('Check connection'));
    await tester.pumpAndSettle();
    expect(find.text('Cannot reach the backend.'), findsOneWidget);
    api.offline = false;
    await tester.scrollUntilVisible(find.text('Check connection'), 180);
    await tester.tap(find.text('Check connection'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('error')), findsNothing);
  });
  testWidgets('history loads saved results and opens evidence', (tester) async {
    await tester.pumpWidget(ScanSafeApp(api: FakeApi()));
    await tester.tap(find.text('History'));
    await tester.pumpAndSettle();
    expect(find.text('TEST-TIME'), findsOneWidget);
    await tester.tap(find.text('Unknown / Insufficient Evidence'));
    await tester.pumpAndSettle();
    expect(find.text('Verification evidence'), findsOneWidget);
    expect(find.text('Confidence score: Unavailable'), findsOneWidget);
  });
  testWidgets('missing model never renders zero or invented confidence', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ResultScreen(
          api: FakeApi(),
          result: Verification({
            'status': 'Unknown / Insufficient Evidence',
            'prediction': {
              'available': false,
              'reason': 'No trained model is installed.',
            },
            'warnings': ['No reference data.'],
            'explanations': ['More evidence is required.'],
          }),
        ),
      ),
    );
    expect(find.text('Prediction: Unavailable'), findsOneWidget);
    expect(find.text('Confidence score: Unavailable'), findsOneWidget);
    expect(find.text('Confidence score: 0.0%'), findsNothing);
    await tester.scrollUntilVisible(
      find.textContaining('Absence of records'),
      250,
    );
    expect(find.textContaining('Absence of records'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('small phone layout scrolls without overflow', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(ScanSafeApp(api: FakeApi()));
    await tester.scrollUntilVisible(
      find.text('Choose product image'),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    expect(tester.takeException(), isNull);
  });
}
