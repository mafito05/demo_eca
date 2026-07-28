/// Anillo de porcentaje para el encabezado de un equipo.
///
/// Un anillo con la cifra dentro comunica "cuánto llevas" en un vistazo mejor que una barra
/// horizontal cuando es el dato principal de la pantalla, y ocupa un cuadrado en lugar de una
/// franja, lo que deja el ancho libre para el nombre del equipo.
library;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme_extensions.dart';

class ProgressRing extends StatelessWidget {
  const ProgressRing({
    required this.percent,
    super.key,
    this.size = 64,
    this.strokeWidth = 6,
  });

  /// 0..100.
  final double percent;
  final double size;
  final double strokeWidth;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final clamped = (percent / 100).clamp(0.0, 1.0);
    final complete = clamped >= 1;
    final color = complete ? context.semantic.success : scheme.primary;

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // `value: 1` como pista de fondo, en lugar de un `Container` circular con borde: así
          // hereda el grosor exacto del indicador de delante y los dos anillos coinciden.
          SizedBox.expand(
            child: CircularProgressIndicator(
              value: 1,
              strokeWidth: strokeWidth,
              color: color.withValues(alpha: 0.16),
            ),
          ),
          SizedBox.expand(
            child: CircularProgressIndicator(
              value: clamped,
              strokeWidth: strokeWidth,
              color: color,
              strokeCap: StrokeCap.round,
              semanticsLabel: 'Training progress',
              semanticsValue: '${(clamped * 100).round()}%',
            ),
          ),
          if (complete)
            Icon(Icons.check_rounded, size: size * 0.42, color: color)
          else
            Text(
              '${(clamped * 100).round()}',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: color,
                fontSize: size * 0.28,
              ),
            ),
        ],
      ),
    );
  }
}
