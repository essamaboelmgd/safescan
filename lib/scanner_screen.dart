import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'app_theme.dart';

class ScannerScreen extends StatefulWidget {
  const ScannerScreen({super.key});

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen> {
  final MobileScannerController controller = MobileScannerController();
  bool isScanned = false;

  void onDetect(BarcodeCapture capture) {
    if (isScanned) return;
    final barcodes = capture.barcodes;
    if (barcodes.isEmpty) return;
    final String? code = barcodes.first.rawValue;
    if (code == null || code.isEmpty) return;
    isScanned = true;
    controller.stop();
    Navigator.pop(context, code);
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: MeyarColors.ink,
    appBar: AppBar(
      backgroundColor: MeyarColors.ink,
      foregroundColor: MeyarColors.paper,
      title: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Scan barcode', style: TextStyle(fontWeight: FontWeight.w700)),
          Text(
            'MEYAR  /  PRODUCT LOOKUP',
            style: TextStyle(
              color: Color(0xffbecac3),
              fontSize: 10,
              letterSpacing: 1,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    ),
    body: SafeArea(
      top: false,
      child: Stack(
        fit: StackFit.expand,
        children: [
          MobileScanner(
            controller: controller,
            onDetect: onDetect,
            errorBuilder: (context, error) => ColoredBox(
              color: MeyarColors.ink,
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.camera_alt_outlined,
                        color: MeyarColors.terracotta,
                        size: 38,
                      ),
                      const SizedBox(height: 14),
                      const Text(
                        'Camera unavailable. Allow camera access in Android settings, or enter the barcode manually.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: MeyarColors.paper, height: 1.5),
                      ),
                      const SizedBox(height: 14),
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('Back to inspection'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const Positioned.fill(
            child: IgnorePointer(
              child: CustomPaint(painter: _ScannerOverlayPainter()),
            ),
          ),
          Positioned(
            left: 20,
            right: 20,
            bottom: 18,
            child: Container(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
              decoration: BoxDecoration(
                color: MeyarColors.ink,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0x55f4f0e6)),
              ),
              child: const Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.center_focus_weak_rounded,
                    color: MeyarColors.terracotta,
                  ),
                  SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Keep the code inside the frame',
                          style: TextStyle(
                            color: MeyarColors.paper,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        SizedBox(height: 4),
                        Text(
                          'A barcode can locate catalogue information. It does not prove an item is authentic.',
                          style: TextStyle(
                            color: Color(0xffc5d0ca),
                            fontSize: 12,
                            height: 1.4,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

class _ScannerOverlayPainter extends CustomPainter {
  const _ScannerOverlayPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final frameWidth = size.width * 0.76;
    final frameHeight = (size.height * 0.24).clamp(132.0, 188.0).toDouble();
    final frame = Rect.fromCenter(
      center: Offset(size.width / 2, size.height * 0.43),
      width: frameWidth,
      height: frameHeight,
    );
    final outside = Path()..addRect(Offset.zero & size);
    outside.addRRect(RRect.fromRectAndRadius(frame, const Radius.circular(20)));
    outside.fillType = PathFillType.evenOdd;
    canvas.drawPath(
      outside,
      Paint()..color = const Color.fromRGBO(4, 21, 22, 0.45),
    );

    const corner = 24.0;
    final guide = Paint()
      ..color = MeyarColors.paper
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final accent = Paint()
      ..color = MeyarColors.terracotta
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final corners = <Path>[
      Path()
        ..moveTo(frame.left, frame.top + corner)
        ..lineTo(frame.left, frame.top + 8)
        ..quadraticBezierTo(frame.left, frame.top, frame.left + 8, frame.top)
        ..lineTo(frame.left + corner, frame.top),
      Path()
        ..moveTo(frame.right - corner, frame.top)
        ..lineTo(frame.right - 8, frame.top)
        ..quadraticBezierTo(frame.right, frame.top, frame.right, frame.top + 8)
        ..lineTo(frame.right, frame.top + corner),
      Path()
        ..moveTo(frame.left, frame.bottom - corner)
        ..lineTo(frame.left, frame.bottom - 8)
        ..quadraticBezierTo(
          frame.left,
          frame.bottom,
          frame.left + 8,
          frame.bottom,
        )
        ..lineTo(frame.left + corner, frame.bottom),
      Path()
        ..moveTo(frame.right - corner, frame.bottom)
        ..lineTo(frame.right - 8, frame.bottom)
        ..quadraticBezierTo(
          frame.right,
          frame.bottom,
          frame.right,
          frame.bottom - 8,
        )
        ..lineTo(frame.right, frame.bottom - corner),
    ];
    for (final path in corners.take(2)) {
      canvas.drawPath(path, accent);
    }
    for (final path in corners.skip(2)) {
      canvas.drawPath(path, guide);
    }
  }

  @override
  bool shouldRepaint(covariant _ScannerOverlayPainter oldDelegate) => false;
}
