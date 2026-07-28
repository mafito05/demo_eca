/// Pastilla de estado o etiqueta.
///
/// Sustituye a los `Chip` que se usaban solo para mostrar estado. Un `Chip` de Material carga con
/// semántica de acción (es pulsable, entra en el orden de foco) que aquí no aplica y que confunde a
/// un lector de pantalla: "Completed" no es un botón.
library;

import 'package:flutter/material.dart';

import '../../core/theme/design_tokens.dart';

class TonalPill extends StatelessWidget {
  const TonalPill({
    required this.label,
    super.key,
    this.icon,
    this.foreground,
    this.background,
  });

  final String label;
  final IconData? icon;
  final Color? foreground;
  final Color? background;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fg = foreground ?? scheme.onSurfaceVariant;
    final bg = background ?? scheme.surfaceContainerHighest;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 5),
      decoration: BoxDecoration(color: bg, borderRadius: AppRadii.bar),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: fg),
            const SizedBox(width: AppSpacing.xs + 1),
          ],
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(color: fg),
          ),
        ],
      ),
    );
  }
}
