typedef Json = Map<String, dynamic>;

class Verification {
  Verification(this.data);
  final Json data;
  String get status =>
      data['status'] as String? ?? 'Unknown / Insufficient Evidence';
  Json get prediction => (data['prediction'] as Json?) ?? {};
  Json? get nearest => data['nearest_reference'] as Json?;
  Json? get metadata => data['metadata'] as Json?;
  Json? get visualMetadata => data['visual_candidate_metadata'] as Json?;
  List<String> get warnings =>
      List<String>.from(data['warnings'] as List? ?? []);
  List<String> get explanations =>
      List<String>.from(data['explanations'] as List? ?? []);
  List<Json> get safetyRecords =>
      (data['safety_records'] as List? ?? []).cast<Json>();
  String get disclaimer =>
      data['disclaimer'] as String? ??
      'AI predictions are estimates, not official authentication.';
}

String percentage(dynamic value) {
  if (value is! num || !value.isFinite) return 'Unavailable';
  return '${(value * 100).toStringAsFixed(1)}%';
}

String? barcodeError(String value) {
  if (!RegExp(r'^(?:[0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})$')
      .hasMatch(value)) {
    return 'Enter an 8, 12, 13 or 14 digit product barcode.';
  }
  final digits = value.split('').map(int.parse).toList();
  var total = 0;
  final body = digits.sublist(0, digits.length - 1).reversed.toList();
  for (var i = 0; i < body.length; i++) {
    total += body[i] * (i.isEven ? 3 : 1);
  }
  if ((10 - total % 10) % 10 != digits.last)
    return 'Barcode checksum is invalid.';
  return null;
}
