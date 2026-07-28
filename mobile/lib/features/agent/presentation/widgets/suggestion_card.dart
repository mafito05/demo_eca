/// Pregunta de ejemplo del estado inicial del chat.
///
/// Corrige un truncado real: las sugerencias iban en `OutlinedButton > Align > Text`, y un
/// `OutlinedButton` no envuelve el texto — en un móvil estrecho las tres preguntas se recortaban a
/// una línea con puntos suspensivos, dejando "What should I do if the unit..." sin más.
///
/// Aquí es un `InkWell` sobre un contenedor, así que el texto fluye en varias líneas.
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/design_tokens.dart';

class SuggestionCard extends StatelessWidget {
  const SuggestionCard({required this.question, required this.onTap, super.key});

  final String question;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Material(
        color: theme.colorScheme.surfaceContainerHigh,
        borderRadius: AppRadii.field,
        child: InkWell(
          onTap: onTap,
          borderRadius: AppRadii.field,
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.help_outline,
                  size: 18,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Text(question, style: theme.textTheme.bodyMedium),
                ),
                Icon(
                  Icons.north_east,
                  size: 15,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
