import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import 'api_client.dart';
import 'app_theme.dart';
import 'models.dart';
import 'result_screen.dart';
import 'scanner_screen.dart';

void main() => runApp(const ScanSafeApp());

class ScanSafeApp extends StatelessWidget {
  const ScanSafeApp({super.key, this.api, this.imagePicker});
  final SafeScanApi? api;
  final ImagePicker? imagePicker;

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Meyar',
    debugShowCheckedModeBanner: false,
    theme: MeyarTheme.light,
    home: HomeScreen(api: api, imagePicker: imagePicker),
  );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.api, this.imagePicker});
  final SafeScanApi? api;
  final ImagePicker? imagePicker;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late SafeScanApi api = widget.api ?? ApiClient();
  late final ImagePicker imagePicker = widget.imagePicker ?? ImagePicker();
  String actionStage = 'action';
  final barcode = TextEditingController();
  bool busy = false;
  String? error;
  Json? health;
  List<Verification> history = [];
  int page = 0;
  bool moreHistory = true;

  @override
  void dispose() {
    barcode.dispose();
    if (api is ApiClient) (api as ApiClient).close();
    super.dispose();
  }

  void trace(String stage) {
    actionStage = stage;
    debugPrint('[Meyar] stage=$stage');
  }

  String failureMessage(Object exception) {
    if (exception is ApiException) {
      return exception.message;
    }
    final pickingCamera = actionStage == 'camera.picker';
    final picking = pickingCamera || actionStage == 'gallery.picker';
    if (picking && exception is MissingPluginException) {
      return 'Image picker integration is unavailable. Close and reopen Meyar; '
          'if it persists, install the rebuilt app.';
    }
    if (picking && exception is PlatformException) {
      switch (exception.code) {
        case 'camera_access_denied':
        case 'camera_access_restricted':
        case 'camera_access_denied_without_prompt':
          return 'Android denied camera access. Allow it in Meyar app permissions.';
        case 'already_active':
          return 'Another image picker is still active. Finish or cancel it, then try again.';
        case 'no_available_camera':
          return 'Android could not find an available camera app.';
        case 'channel-error':
          return 'Image picker connection failed. Close and reopen Meyar; '
              'if it persists, install the rebuilt app.';
      }
      return 'Could not open the ${pickingCamera ? 'camera' : 'image picker'} '
          '(${exception.code}). See the diagnostic log for details.';
    }
    if (picking) {
      return 'Could not open the ${pickingCamera ? 'camera' : 'image picker'}. '
          'See the diagnostic log for details.';
    }
    if (actionStage == 'image.read') {
      return 'Could not read the selected image. Please select or photograph it again.';
    }
    if (actionStage == 'backend.verify') {
      return 'The image was selected, but verification failed. See the diagnostic log for details.';
    }
    return 'Unable to complete this action. See the diagnostic log for details.';
  }

  Future<void> perform(
    Future<void> Function() action, {
    String operation = 'action',
  }) async {
    if (busy) return;
    trace(operation);
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await action();
    } catch (exception, stackTrace) {
      debugPrint(
        '[Meyar] stage=$actionStage failed: ${exception.runtimeType}: $exception',
      );
      debugPrintStack(label: '[Meyar] failure stack', stackTrace: stackTrace);
      if (mounted) {
        setState(() => error = failureMessage(exception));
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> pick(ImageSource source) => perform(() async {
    final code = barcode.text.trim();
    if (code.isNotEmpty && barcodeError(code) != null) {
      throw ApiException(barcodeError(code)!);
    }
    trace('${source.name}.picker');
    final image = await imagePicker.pickImage(
      source: source,
      maxWidth: 2000,
      maxHeight: 2000,
      imageQuality: 92,
    );
    if (image == null) {
      trace('${source.name}.cancelled');
      return;
    }
    trace('image.read');
    final bytes = await image.readAsBytes();
    trace('backend.verify');
    final result = await api.verify(
      bytes,
      image.name,
      barcode: code.isEmpty ? null : code,
    );
    if (!mounted) return;
    trace('results.open');
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => ResultScreen(result: result, api: api),
      ),
    );
  }, operation: '${source.name}.start');

  Future<void> lookup() => perform(() async {
    final result = await api.lookupBarcode(barcode.text.trim());
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Barcode metadata'),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (result['product'] != null)
                ProductInfo(product: result['product'] as Json)
              else
                const Text('No product metadata found.'),
              const SizedBox(height: 12),
              const Text(
                'A valid barcode identifies a catalogue entry. It does not prove this item is authentic.',
              ),
              for (final warning in result['warnings'] as List? ?? [])
                Text(warning.toString()),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  });

  Future<void> loadHistory({bool append = false}) => perform(() async {
    final items = await api.history(offset: append ? history.length : 0);
    if (mounted) {
      setState(() {
        history = append ? [...history, ...items] : items;
        moreHistory = items.length == 20;
      });
    }
  });

  Future<void> settings() async {
    final controller = TextEditingController(text: api.baseUrl);
    String? validation;
    final chosen = await showDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (_, dialogSetState) => AlertDialog(
          title: const Text('Backend address'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: controller,
                keyboardType: TextInputType.url,
                decoration: InputDecoration(
                  labelText: 'API URL',
                  errorText: validation,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'Physical Android: use your Windows Wi-Fi IPv4 address. Emulator: use 10.0.2.2. See docs/SETUP.md.',
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                try {
                  Navigator.pop(
                    dialogContext,
                    ApiClient.normalizeUrl(controller.text),
                  );
                } on ApiException catch (e) {
                  dialogSetState(() => validation = e.message);
                }
              },
              child: const Text('Connect'),
            ),
          ],
        ),
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 300));
    controller.dispose();
    if (chosen == null || !mounted) return;
    if (api is ApiClient) (api as ApiClient).close();
    setState(() {
      api = ApiClient(baseUrl: chosen);
      health = null;
      history = [];
    });
    await perform(() async {
      final result = await api.health();
      if (mounted) setState(() => health = result);
    });
  }

  Future<void> checkConnection() => perform(() async {
    final result = await api.health();
    if (mounted) setState(() => health = result);
  });

  Future<void> openBarcodeScanner() async {
    final code = await Navigator.push<String>(
      context,
      MaterialPageRoute(builder: (_) => const ScannerScreen()),
    );
    if (code != null && mounted) {
      barcode.text = code;
      await lookup();
    }
  }

  Widget _buildInspectPage(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const _Eyebrow('PRODUCT EVIDENCE · RESEARCH PROTOTYPE'),
      const SizedBox(height: 10),
      Text(
        'Inspect a product',
        style: Theme.of(context).textTheme.headlineMedium,
      ),
      const SizedBox(height: 6),
      Text(
        'Start with a photo or barcode. Review the sources before drawing conclusions.',
        style: Theme.of(
          context,
        ).textTheme.bodyMedium?.copyWith(color: MeyarColors.muted),
      ),
      const SizedBox(height: 20),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: MeyarColors.ink,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: MeyarColors.terracotta,
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: const Icon(
                    Icons.center_focus_weak_rounded,
                    color: MeyarColors.ink,
                  ),
                ),
                const SizedBox(width: 10),
                const Text(
                  '01  /  VISUAL SEARCH',
                  style: TextStyle(
                    color: MeyarColors.paper,
                    fontSize: 11,
                    letterSpacing: 1.1,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            const Text(
              'Capture the item',
              style: TextStyle(
                color: MeyarColors.paper,
                fontSize: 21,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 5),
            const Text(
              'A clear view of the product and its label gives the comparison more useful context.',
              style: TextStyle(color: Color(0xffd2ddd6), height: 1.4),
            ),
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: busy ? null : () => pick(ImageSource.camera),
                style: FilledButton.styleFrom(
                  backgroundColor: MeyarColors.paper,
                  foregroundColor: MeyarColors.ink,
                  disabledBackgroundColor: MeyarColors.line,
                  minimumSize: const Size(48, 54),
                ),
                icon: const Icon(Icons.photo_camera_outlined),
                label: const Text('Photograph product'),
              ),
            ),
            const SizedBox(height: 4),
            Center(
              child: TextButton.icon(
                onPressed: busy ? null : () => pick(ImageSource.gallery),
                style: TextButton.styleFrom(
                  foregroundColor: MeyarColors.paper,
                  minimumSize: const Size(48, 44),
                ),
                icon: const Icon(Icons.photo_library_outlined, size: 18),
                label: const Text('Choose product image'),
              ),
            ),
          ],
        ),
      ),
      const SizedBox(height: 24),
      Text('Add a barcode', style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 5),
      Text(
        'Catalogue lookup is separate from visual matching.',
        style: Theme.of(context).textTheme.bodySmall,
      ),
      const SizedBox(height: 12),
      TextField(
        controller: barcode,
        enabled: !busy,
        keyboardType: TextInputType.number,
        decoration: const InputDecoration(
          labelText: 'Product barcode',
          hintText: 'GTIN / EAN / UPC',
          prefixIcon: Icon(Icons.tag_rounded),
        ),
      ),
      const SizedBox(height: 10),
      Wrap(
        spacing: 9,
        runSpacing: 9,
        children: [
          OutlinedButton.icon(
            onPressed: busy ? null : openBarcodeScanner,
            icon: const Icon(Icons.qr_code_scanner_rounded),
            label: const Text('Scan barcode'),
          ),
          OutlinedButton.icon(
            onPressed: busy ? null : lookup,
            icon: const Icon(Icons.search_rounded),
            label: const Text('Look up barcode'),
          ),
        ],
      ),
      const SizedBox(height: 22),
      _ConnectionPanel(
        baseUrl: api.baseUrl,
        health: health,
        busy: busy,
        onCheck: checkConnection,
      ),
      const SizedBox(height: 12),
      const _Notice(
        icon: Icons.info_outline_rounded,
        text:
            'AI predictions are estimates, not official authentication. Unknown is a valid result when evidence is missing.',
      ),
      const SizedBox(height: 12),
      Text(
        'For a useful comparison, photograph the actual item in good light. Avoid personal information in the frame.',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    ],
  );

  Widget _buildHistoryPage(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const _Eyebrow('LOCAL RECORDS · BACKEND HISTORY'),
      const SizedBox(height: 10),
      Text('Scan history', style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 6),
      Text(
        'Saved evidence snapshots from the connected backend.',
        style: Theme.of(
          context,
        ).textTheme.bodyMedium?.copyWith(color: MeyarColors.muted),
      ),
      const SizedBox(height: 8),
      Row(
        children: [
          Expanded(
            child: Text(
              'History is shared with other local users of this backend.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          IconButton.filledTonal(
            tooltip: 'Refresh history',
            onPressed: busy ? null : loadHistory,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      const SizedBox(height: 8),
      if (history.isEmpty && !busy)
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            color: MeyarColors.surface,
            border: Border.all(color: MeyarColors.line),
            borderRadius: BorderRadius.circular(20),
          ),
          child: const Column(
            children: [
              Icon(Icons.inbox_outlined, size: 30, color: MeyarColors.sage),
              SizedBox(height: 9),
              Text('No scans found on this backend.'),
            ],
          ),
        ),
      for (final result in history)
        Padding(
          padding: const EdgeInsets.only(bottom: 9),
          child: Material(
            color: MeyarColors.surface,
            borderRadius: BorderRadius.circular(18),
            child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: busy
                  ? null
                  : () => Navigator.push(
                      context,
                      MaterialPageRoute<void>(
                        builder: (_) => ResultScreen(result: result, api: api),
                      ),
                    ),
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  border: Border.all(color: MeyarColors.line),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Row(
                  children: [
                    const _StatusMark(),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            result.status,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          const SizedBox(height: 4),
                          Text(
                            result.data['created_at'] as String? ?? '',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    const Icon(Icons.arrow_forward_ios_rounded, size: 15),
                  ],
                ),
              ),
            ),
          ),
        ),
      if (moreHistory && history.isNotEmpty)
        Center(
          child: TextButton.icon(
            onPressed: busy ? null : () => loadHistory(append: true),
            icon: const Icon(Icons.expand_more_rounded),
            label: const Text('Load more'),
          ),
        ),
    ],
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: MeyarColors.paper,
    appBar: AppBar(
      toolbarHeight: 76,
      titleSpacing: 20,
      title: const _BrandLockup(),
      actions: [
        Padding(
          padding: const EdgeInsets.only(right: 14),
          child: IconButton.filledTonal(
            tooltip: 'Backend address',
            onPressed: busy ? null : settings,
            icon: const Icon(Icons.tune_rounded),
          ),
        ),
      ],
    ),
    body: SafeArea(
      top: false,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(
            children: [
              if (busy) const LinearProgressIndicator(minHeight: 2),
              if (error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(13),
                    decoration: BoxDecoration(
                      color: const Color(0xffffe9e3),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Text(
                      error!,
                      key: const Key('error'),
                      style: const TextStyle(color: MeyarColors.error),
                    ),
                  ),
                ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
                  children: [
                    if (page == 0)
                      _buildInspectPage(context)
                    else
                      _buildHistoryPage(context),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    ),
    bottomNavigationBar: NavigationBar(
      selectedIndex: page,
      onDestinationSelected: busy
          ? null
          : (value) {
              setState(() => page = value);
              if (value == 1) loadHistory();
            },
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.center_focus_weak_rounded),
          selectedIcon: Icon(Icons.center_focus_strong_rounded),
          label: 'Inspect',
        ),
        NavigationDestination(
          icon: Icon(Icons.history_rounded),
          label: 'History',
        ),
      ],
    ),
  );
}

class _BrandLockup extends StatelessWidget {
  const _BrandLockup();

  @override
  Widget build(BuildContext context) => Row(
    children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(13),
        child: Image.asset(
          'assets/branding/meyar_icon.png',
          width: 42,
          height: 42,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => Container(
            width: 42,
            height: 42,
            color: MeyarColors.ink,
            alignment: Alignment.center,
            child: const Icon(
              Icons.center_focus_weak,
              color: MeyarColors.paper,
            ),
          ),
        ),
      ),
      const SizedBox(width: 11),
      const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Meyar',
            style: TextStyle(
              color: MeyarColors.ink,
              fontSize: 19,
              height: 1.05,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.3,
            ),
          ),
          SizedBox(height: 4),
          Text(
            'معيار  ·  EVIDENCE TOOLS',
            style: TextStyle(
              color: MeyarColors.muted,
              fontSize: 9,
              letterSpacing: 0.65,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    ],
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

class _ConnectionPanel extends StatelessWidget {
  const _ConnectionPanel({
    required this.baseUrl,
    required this.health,
    required this.busy,
    required this.onCheck,
  });

  final String baseUrl;
  final Json? health;
  final bool busy;
  final VoidCallback onCheck;

  @override
  Widget build(BuildContext context) {
    final isConnected = health != null;
    final modelAvailable = health?['model_available'] == true;
    return Container(
      padding: const EdgeInsets.fromLTRB(15, 13, 8, 13),
      decoration: BoxDecoration(
        color: MeyarColors.surface,
        border: Border.all(color: MeyarColors.line),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: [
          Container(
            width: 9,
            height: 9,
            decoration: BoxDecoration(
              color: isConnected ? MeyarColors.sage : MeyarColors.terracotta,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isConnected
                      ? 'Connected · Model: ${modelAvailable ? 'loaded' : 'unavailable'} · References: ${health!['reference_count']}'
                      : 'Backend not checked',
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: MeyarColors.ink,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  'Backend: $baseUrl',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(width: 2),
          TextButton(
            onPressed: busy ? null : onCheck,
            child: const Text('Check connection'),
          ),
        ],
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: const Color(0xffe9eee8),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 19, color: MeyarColors.ink),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              color: MeyarColors.ink,
              fontSize: 12,
              height: 1.42,
            ),
          ),
        ),
      ],
    ),
  );
}

class _StatusMark extends StatelessWidget {
  const _StatusMark();

  @override
  Widget build(BuildContext context) => Container(
    width: 36,
    height: 36,
    decoration: BoxDecoration(
      color: MeyarColors.paper,
      borderRadius: BorderRadius.circular(12),
    ),
    child: const Icon(Icons.receipt_long_outlined, color: MeyarColors.ink),
  );
}
