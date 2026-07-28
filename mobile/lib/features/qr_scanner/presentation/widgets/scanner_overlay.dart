/// Superposición de puntería del escáner.
///
/// Tres cambios respecto al rectángulo blanco que había:
///
/// 1. **Scrim real** alrededor de la ventana, con `Path.combine(difference)` en un `CustomPainter`.
///    Se dibuja negro translúcido **fuera** del recorte, en lugar de aplicar un `ColorFiltered` sobre
///    la textura de la cámara — ese filtro procesaría cada fotograma de la vista previa, y aquí solo
///    se pinta una forma estática por encima.
/// 2. **Corchetes de esquina** en vez del rectángulo completo: sobre una imagen ocupada (una máquina
///    con etiquetas y cables) un marco cerrado se pierde entre las líneas del fondo.
/// 3. Los blancos y negros vienen de `AppOverlays`, con nombre. El fondo aquí es imagen del mundo
///    real, así que un color fijo es correcto — pero conviene que se lea como intencionado y no como
///    un `Colors.white70` que alguien olvidó cambiar.
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/design_tokens.dart';

class ScannerOverlay extends StatelessWidget {
  const ScannerOverlay({super.key, this.windowSize = AppSizes.scannerWindow});

  final double windowSize;

  @override
  Widget build(BuildContext context) => IgnorePointer(
    child: CustomPaint(
      painter: _ScannerOverlayPainter(windowSize: windowSize),
      child: const SizedBox.expand(),
    ),
  );
}

class _ScannerOverlayPainter extends CustomPainter {
  const _ScannerOverlayPainter({required this.windowSize});

  final double windowSize;

  static const double _cornerLength = 28;
  static const double _cornerWidth = 4;
  static const double _radius = 18;

  @override
  void paint(Canvas canvas, Size size) {
    final window = Rect.fromCenter(
      center: Offset(size.width / 2, size.height / 2),
      width: windowSize,
      height: windowSize,
    );
    final rounded = RRect.fromRectAndRadius(window, const Radius.circular(_radius));

    // Scrim: toda la pantalla menos la ventana.
    final scrim = Path.combine(
      PathOperation.difference,
      Path()..addRect(Rect.fromLTWH(0, 0, size.width, size.height)),
      Path()..addRRect(rounded),
    );
    canvas.drawPath(scrim, Paint()..color = AppOverlays.cameraScrim);

    final stroke = Paint()
      ..color = AppOverlays.onCamera
      ..strokeWidth = _cornerWidth
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    // Cuatro corchetes. Cada uno son dos segmentos y un arco en la esquina.
    void corner(Offset pivot, {required int dx, required int dy}) {
      final path = Path()
        ..moveTo(pivot.dx + dx * _cornerLength, pivot.dy)
        ..lineTo(pivot.dx + dx * _radius, pivot.dy)
        ..quadraticBezierTo(pivot.dx, pivot.dy, pivot.dx, pivot.dy + dy * _radius)
        ..lineTo(pivot.dx, pivot.dy + dy * _cornerLength);
      canvas.drawPath(path, stroke);
    }

    corner(window.topLeft, dx: 1, dy: 1);
    corner(window.topRight, dx: -1, dy: 1);
    corner(window.bottomLeft, dx: 1, dy: -1);
    corner(window.bottomRight, dx: -1, dy: -1);
  }

  @override
  bool shouldRepaint(_ScannerOverlayPainter oldDelegate) =>
      oldDelegate.windowSize != windowSize;
}
