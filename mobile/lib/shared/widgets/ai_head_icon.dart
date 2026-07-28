/// Icono de ECAHelp: perfil de cabeza robótica con circuito cerebral.
///
/// Dibujado en código a partir de la referencia que dio el cliente (una cabeza de perfil con
/// trazas de circuito y nodos como cerebro), en versión androide: perfil anguloso en lugar de
/// orgánico. Es un `CustomPainter` y no un asset porque a 24 px un PNG se ve borroso, un SVG
/// exigiría una dependencia, y el trazo debe teñirse con el color del tema.
///
/// **Lee `IconTheme.of(context)`** para color y tamaño, exactamente igual que un `Icon`. Sin eso
/// se repetiría el bug de los colores fijos: la `NavigationBar` comunica el estado
/// seleccionado/no-seleccionado a través del `IconTheme`, y un color hardcodeado ignoraría el
/// tema y fallaría en uno de los dos brightness.
///
/// La variante `filled` (pestaña seleccionada) rellena la silueta y dibuja el circuito en el
/// color de fondo, siguiendo la convención outline/filled del resto de destinos.
library;

import 'package:flutter/material.dart';

class AiHeadIcon extends StatelessWidget {
  const AiHeadIcon({super.key, this.filled = false, this.size, this.color});

  final bool filled;

  /// Si no se pasan, se heredan del `IconTheme` — el comportamiento de un `Icon` normal.
  final double? size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final iconTheme = IconTheme.of(context);
    final resolvedSize = size ?? iconTheme.size ?? 24;
    final resolvedColor = color ?? iconTheme.color ?? Theme.of(context).colorScheme.onSurface;

    return Semantics(
      label: 'ECAHelp assistant',
      child: CustomPaint(
        size: Size.square(resolvedSize),
        painter: _AiHeadPainter(color: resolvedColor, filled: filled),
      ),
    );
  }
}

class _AiHeadPainter extends CustomPainter {
  const _AiHeadPainter({required this.color, required this.filled});

  final Color color;
  final bool filled;

  @override
  void paint(Canvas canvas, Size size) {
    // Todo se dibuja en un lienzo lógico de 24x24 y se escala: así el icono es idéntico a
    // cualquier tamaño que pida el IconTheme.
    final scale = size.width / 24;
    canvas.scale(scale);

    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.7
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    // --- Silueta: perfil androide mirando a la derecha ----------------------
    // Frente alta y recta, nariz angulosa, mentón corto y cuello: los quiebros rectos son lo
    // que lo lee como robot y no como humano.
    final head = Path()
      ..moveTo(9.5, 21) // base del cuello
      ..lineTo(9.5, 18.4) // cuello
      ..lineTo(7.2, 17.6) // hombro del maxilar
      ..quadraticBezierTo(5.6, 17.0, 5.9, 15.4) // mandíbula
      ..lineTo(4.6, 13.1) // garganta -> mentón
      ..lineTo(6.1, 12.6) // mentón
      ..lineTo(5.4, 11.2) // labio inferior
      ..lineTo(6.4, 10.9) // boca
      ..lineTo(5.0, 9.2) // punta de la nariz
      ..lineTo(6.6, 8.0) // puente de la nariz
      ..quadraticBezierTo(6.9, 4.4, 10.4, 3.3) // frente
      ..quadraticBezierTo(14.6, 2.1, 17.4, 4.6) // cráneo superior
      ..quadraticBezierTo(19.6, 6.6, 19.3, 9.8) // parte trasera del cráneo
      ..quadraticBezierTo(19.1, 13.4, 17.5, 15.6) // nuca
      ..lineTo(17.5, 21); // trasera del cuello

    if (filled) {
      final fill = Paint()
        ..color = color
        ..style = PaintingStyle.fill;
      final closed = Path.from(head)..close();
      canvas.drawPath(closed, fill);
      // En la variante rellena, el circuito se "recorta" pintándolo en modo clear no es posible
      // sin saveLayer; se dibuja con el color del indicador de la barra leyendo el contraste:
      // el painter no conoce el fondo, así que usa un trazo semitransparente oscuro/claro según
      // la luminancia del propio color de relleno.
      final onFill = Paint()
        ..color = color.computeLuminance() > 0.5
            ? const Color(0xB3000000)
            : const Color(0xE6FFFFFF)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4
        ..strokeCap = StrokeCap.round;
      _drawCircuit(canvas, onFill, nodeFill: true);
      return;
    }

    canvas.drawPath(head, stroke);
    _drawCircuit(canvas, stroke, nodeFill: false);
  }

  /// Circuito cerebral: tres trazas que salen de un nodo central hacia arriba, como en la
  /// imagen de referencia, cada una terminada en un nodo circular.
  void _drawCircuit(Canvas canvas, Paint paint, {required bool nodeFill}) {
    final node = Paint()
      ..color = paint.color
      ..style = nodeFill ? PaintingStyle.fill : PaintingStyle.stroke
      ..strokeWidth = paint.strokeWidth;

    // Nodo central (el "procesador").
    canvas.drawCircle(const Offset(12.2, 10.6), 1.9, paint);

    // Traza 1: vertical hacia la frente.
    canvas.drawLine(const Offset(12.2, 8.7), const Offset(12.2, 6.6), paint);
    canvas.drawCircle(const Offset(12.2, 5.7), 0.9, node);

    // Traza 2: diagonal hacia la parte trasera alta, con un quiebro de circuito.
    final trace2 = Path()
      ..moveTo(13.9, 9.8)
      ..lineTo(15.3, 8.9)
      ..lineTo(15.3, 7.3);
    canvas.drawPath(trace2, paint);
    canvas.drawCircle(const Offset(15.3, 6.4), 0.9, node);

    // Traza 3: horizontal hacia la nuca.
    final trace3 = Path()
      ..moveTo(14.1, 11.2)
      ..lineTo(16.2, 11.2)
      ..lineTo(17.2, 12.2);
    canvas.drawPath(trace3, paint);
    canvas.drawCircle(const Offset(17.8, 12.8), 0.9, node);

    // Traza 4: corta hacia la sien (delante).
    canvas.drawLine(const Offset(10.3, 10.6), const Offset(8.9, 10.6), paint);
    canvas.drawCircle(const Offset(8.2, 10.6), 0.7, node);
  }

  @override
  bool shouldRepaint(_AiHeadPainter oldDelegate) =>
      oldDelegate.color != color || oldDelegate.filled != filled;
}
