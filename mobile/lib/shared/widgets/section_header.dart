/// Cabecera de sección: eyebrow en mayúsculas y contador.
///
/// El único sitio donde se usa `labelSmall` (12 px) de toda la app: la caja alta compensa el tamaño,
/// así que sigue siendo legible a distancia sin romper el suelo de 13 px del resto del texto.
library;

import 'package:flutter/material.dart';

import '../../core/theme/design_tokens.dart';

class SectionHeader extends StatelessWidget {
  const SectionHeader({required this.title, super.key, this.trailing, this.color, this.icon});

  final String title;
  final String? trailing;

  /// Color del eyebrow y del icono. Se usa el de la especialidad para teñir cada sección del
  /// catálogo, que es lo que permite recorrer una lista larga sin leer.
  final Color? color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final tone = color ?? scheme.onSurfaceVariant;

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenH,
        AppSpacing.xl,
        AppSpacing.screenH,
        AppSpacing.sm,
      ),
      child: Row(
        children: [
          if (icon != null) ...[
            Icon(icon, size: 15, color: tone),
            const SizedBox(width: AppSpacing.sm),
          ],
          Expanded(
            child: Text(
              title.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(color: tone),
            ),
          ),
          if (trailing != null)
            Text(
              trailing!,
              style: Theme.of(
                context,
              ).textTheme.labelMedium?.copyWith(color: scheme.onSurfaceVariant),
            ),
        ],
      ),
    );
  }
}
