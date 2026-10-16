import 'package:flutter/material.dart';

import 'api_client.dart';
import 'app_theme.dart';
import 'models.dart';

class ProductInfo extends StatelessWidget {
  const ProductInfo({super.key, required this.product});
  final Json product;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        product['name'] as String? ?? 'Unnamed record',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const SizedBox(height: 9),
      for (final field in [
        'brand',
        'category',
        'barcode',
        'batch_number',
        'description',
      ])
        if (product[field] != null && product[field].toString().isNotEmpty)
          _LabelValue(
            label: field.replaceAll('_', ' '),
            value: product[field].toString(),
          ),
      if (product['source_note'] != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(product['source_note'].toString()),
        ),
      if (product['source_url'] != null)
        _SourceLink(label: 'Source', value: product['source_url'].toString()),
      if (product['checked_at'] != null)
        _LabelValue(
          label: 'record checked',
          value: product['checked_at'].toString(),
        ),
      if ((product['alternatives'] as List? ?? []).isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Text(
            'Catalogue alternative ids: ${(product['alternatives'] as List).join(', ')}. Confirm their safety independently.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
    ],
  );
}

class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.result, required this.api});
  final Verification result;
  final SafeScanApi api;

  @override
  Widget build(BuildContext context) {
    final prediction = result.prediction;
    final nearest = result.nearest;
    return Scaffold(
      backgroundColor: MeyarColors.paper,
      appBar: AppBar(
        title: const Text('Verification evidence'),
        actions: const [
          Padding(
            padding: EdgeInsets.only(right: 20),
            child: Center(
              child: Text(
                'MEYAR  /  معيار',
                style: TextStyle(
                  color: MeyarColors.muted,
                  fontWeight: FontWeight.w800,
                  fontSize: 10,
                  letterSpacing: 0.7,
                ),
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 680),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 30),
              children: [
                const _Eyebrow('INSPECTION RECORD'),
                const SizedBox(height: 12),
                Text(
                  'Evidence report',
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                const SizedBox(height: 16),
                _ResultSummary(
                  status: result.status,
                  disclaimer: result.disclaimer,
                ),
                const SizedBox(height: 12),
                _EvidenceSection(
                  icon: Icons.auto_graph_rounded,
                  title: 'Model estimate',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Prediction: ${prediction['prediction']?.toString() ?? 'Unavailable'}',
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Confidence score: ${percentage(prediction['confidence'])}',
                      ),
                      const SizedBox(height: 7),
                      Text(
                        prediction['confidence_note'] as String? ??
                            prediction['reason'] as String? ??
                            'No trained prediction available.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      if (prediction['model_version'] != null)
                        _LabelValue(
                          label: 'model',
                          value: prediction['model_version'].toString(),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 11),
                _EvidenceSection(
                  icon: Icons.image_search_rounded,
                  title: 'Nearest visual reference',
                  child: nearest == null
                      ? const Text('No reference candidate available.')
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (nearest['image_url'] != null) ...[
                              ClipRRect(
                                borderRadius: BorderRadius.circular(15),
                                child: Image.network(
                                  '${api.baseUrl}${nearest['image_url']}',
                                  height: 180,
                                  width: double.infinity,
                                  fit: BoxFit.cover,
                                  errorBuilder: (_, _, _) => Container(
                                    height: 110,
                                    alignment: Alignment.center,
                                    color: MeyarColors.paper,
                                    child: const Text(
                                      'Reference preview unavailable.',
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 12),
                            ],
                            _LabelValue(
                              label: 'reference',
                              value:
                                  nearest['reference_id']?.toString() ??
                                  'Unavailable',
                            ),
                            _LabelValue(
                              label: 'reference label',
                              value:
                                  nearest['label']?.toString() ?? 'Unverified',
                            ),
                            _LabelValue(
                              label: 'cosine similarity',
                              value: percentage(
                                result.data['similarity_score'],
                              ),
                            ),
                            _LabelValue(
                              label: 'perceptual hash distance',
                              value:
                                  '${nearest['phash_distance'] ?? 'Unavailable'} / 64',
                            ),
                            const SizedBox(height: 8),
                            const _InlineNotice(
                              text:
                                  'Similarity measures appearance. It is not authenticity confidence.',
                            ),
                            if (nearest['source_url'] != null)
                              _SourceLink(
                                label: 'Reference source',
                                value: nearest['source_url'].toString(),
                              ),
                          ],
                        ),
                ),
                const SizedBox(height: 11),
                _EvidenceSection(
                  icon: Icons.qr_code_2_rounded,
                  title: 'Barcode product metadata',
                  child: result.metadata == null
                      ? const Text('No barcode product record available.')
                      : ProductInfo(product: result.metadata!),
                ),
                if (result.visualMetadata != null) ...[
                  const SizedBox(height: 11),
                  _EvidenceSection(
                    icon: Icons.manage_search_rounded,
                    title: 'Visual candidate · identity unconfirmed',
                    child: ProductInfo(product: result.visualMetadata!),
                  ),
                ],
                const SizedBox(height: 11),
                _EvidenceSection(
                  icon: Icons.fact_check_outlined,
                  title: 'Safety records and warnings',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (result.safetyRecords.isEmpty)
                        const _InlineNotice(
                          text:
                              'No sourced recall or certification records available. Absence of records is not proof of safety.',
                        ),
                      for (final record in result.safetyRecords)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${record['kind']}: ${record['title']}',
                                style: Theme.of(context).textTheme.titleMedium,
                              ),
                              const SizedBox(height: 6),
                              _LabelValue(
                                label: 'applies to',
                                value: record['scope'].toString(),
                              ),
                              _LabelValue(
                                label: 'jurisdiction · association',
                                value:
                                    '${record['jurisdiction']} · ${record['association']}',
                              ),
                              _LabelValue(
                                label: 'checked',
                                value: record['checked_at'].toString(),
                              ),
                              _SourceLink(
                                label: 'Source',
                                value: record['source_url'].toString(),
                              ),
                            ],
                          ),
                        ),
                      for (final warning in result.warnings)
                        Padding(
                          padding: const EdgeInsets.only(top: 7),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Icon(
                                Icons.info_outline_rounded,
                                color: MeyarColors.warning,
                                size: 17,
                              ),
                              const SizedBox(width: 8),
                              Expanded(child: Text(warning)),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 11),
                _EvidenceSection(
                  icon: Icons.notes_rounded,
                  title: 'How to read this result',
                  child: result.explanations.isEmpty
                      ? const Text('No additional explanation was returned.')
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            for (final explanation in result.explanations)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Text(explanation),
                              ),
                          ],
                        ),
                ),
                const SizedBox(height: 14),
                const Text(
                  'Meyar is a research prototype for evidence retrieval. It does not certify a product.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: MeyarColors.muted, fontSize: 12),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ResultSummary extends StatelessWidget {
  const _ResultSummary({required this.status, required this.disclaimer});
  final String status;
  final String disclaimer;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: const Color(0xffe7ece6),
      borderRadius: BorderRadius.circular(22),
      border: Border.all(color: const Color(0xffd6dfd5)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.assessment_outlined, color: MeyarColors.ink),
            const SizedBox(width: 9),
            Text(
              'CURRENT ASSESSMENT',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: MeyarColors.muted,
                letterSpacing: 1,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Text(
          status,
          key: const Key('verdict'),
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 8),
        Text(disclaimer, style: Theme.of(context).textTheme.bodyMedium),
      ],
    ),
  );
}

class _EvidenceSection extends StatelessWidget {
  const _EvidenceSection({
    required this.icon,
    required this.title,
    required this.child,
  });

  final IconData icon;
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(17),
    decoration: BoxDecoration(
      color: MeyarColors.surface,
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: MeyarColors.line),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, color: MeyarColors.sage, size: 20),
            const SizedBox(width: 9),
            Expanded(
              child: Text(
                title,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
          ],
        ),
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 13),
          child: Divider(height: 1),
        ),
        child,
      ],
    ),
  );
}

class _LabelValue extends StatelessWidget {
  const _LabelValue({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 7),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 128,
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: MeyarColors.muted),
          ),
        ),
        Expanded(
          child: Text(value, style: Theme.of(context).textTheme.bodyMedium),
        ),
      ],
    ),
  );
}

class _SourceLink extends StatelessWidget {
  const _SourceLink({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: SelectableText(
      '$label: $value',
      style: Theme.of(context).textTheme.bodySmall?.copyWith(
        color: MeyarColors.ink,
        decoration: TextDecoration.underline,
        decorationColor: MeyarColors.sage,
      ),
    ),
  );
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: const Color(0xfff3eee2),
      borderRadius: BorderRadius.circular(13),
    ),
    child: Text(
      text,
      style: Theme.of(
        context,
      ).textTheme.bodySmall?.copyWith(color: MeyarColors.ink),
    ),
  );
}

class _Eyebrow extends StatelessWidget {
  const _Eyebrow(this.label);
  final String label;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Container(
        width: 7,
        height: 7,
        decoration: const BoxDecoration(
          color: MeyarColors.terracotta,
          shape: BoxShape.circle,
        ),
      ),
      const SizedBox(width: 8),
      Text(
        label,
        style: const TextStyle(
          color: MeyarColors.muted,
          fontSize: 10,
          letterSpacing: 1,
          fontWeight: FontWeight.w800,
        ),
      ),
    ],
  );
}
