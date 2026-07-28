/// Barra de progreso con etiqueta y semántica.
///
/// El `ClipRRect(borderRadius: 999)` que envolvía cada `LinearProgressIndicator` ya no hace falta:
/// el `progressIndicatorTheme` lleva `borderRadius`. Esto añade lo que el tema no puede: el par
/// "3/8" al lado y un `semanticsLabel` legible, porque un lector de pantalla sobre una barra pelada
/// anuncia "37 por ciento" sin decir de qué.
library;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme_extensions.dart';
import '../../core/theme/design_tokens.dart';

class AppProgressBar extends StatelessWidget {
  const AppProgressBar({
    required this.value,
    super.key,
    this.label,
    this.height = 8,
    this.completeWhenFull = true,
  });

  /// Fracción 0..1.
  final double value;

  /// Texto a la derecha, p. ej. "3/8".
  final String? label;
  final double height;

  /// Al llegar al 100 % la barra pasa a verde. Es la señal de que el módulo siguiente se desbloquea.
  final bool completeWhenFull;

  @override
  Widget build(BuildContext context) {
    final clamped = value.clamp(0.0, 1.0);
    final complete = completeWhenFull && clamped >= 1;
    final color = complete ? context.semantic.success : Theme.of(context).colorScheme.primary;

    final bar = LinearProgressIndicator(
      value: clamped,
      minHeight: height,
      color: color,
      semanticsLabel: label ?? 'Progress',
      semanticsValue: '${(clamped * 100).round()}%',
    );

    if (label == null) {
      return bar;
    }
    return Row(
      children: [
        Expanded(child: bar),
        const SizedBox(width: AppSpacing.md),
        Text(
          label!,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(color: color),
        ),
      ],
    );
  }
}
