/// Fuentes citadas por el agente, como chips con indicador de confianza.
///
/// Antes eran líneas de texto gris. Ahora cada fuente es un chip pulsable que despliega la sección
/// exacta, y **`AgentCitation.distance` se convierte en un indicador de confianza** — ese campo
/// llegaba del backend y no se usaba en ninguna parte.
///
/// Por qué merece la pena: es exactamente la transparencia que pide personal clínico y técnico.
/// "Esto lo dice el manual, sección 4, y el emparejamiento es bueno" es una afirmación muy distinta
/// de "esto lo dice el asistente".
///
/// **Los umbrales están estimados, no calibrados.** `DECISIONS.md` (D-015) registra distancias
/// reales de 0.446 y 0.542 para consultas que recuperan la sección correcta, así que 0.50 y 0.65 son
/// defensibles: 0.65 es además el `RAG_MAX_DISTANCE` del backend, por encima del cual el fragmento
/// ni se envía al modelo. Con más datos de uso conviene revisarlos.
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme_extensions.dart';
import '../../../../core/theme/design_tokens.dart';
import '../../data/agent_socket.dart';

/// Umbral de FALLBACK cuando el backend aún no ha respondido a `/agent/settings`. Coincide con
/// el default de `RAG_MAX_DISTANCE`; el valor vivo llega por el parámetro `maxDistance` (D-053).
const double kFallbackMaxDistance = 0.65;

class SourceChips extends StatelessWidget {
  const SourceChips({required this.sources, super.key, this.maxDistance});

  final List<AgentCitation> sources;

  /// `RAG_MAX_DISTANCE` real del backend. Null mientras `/agent/settings` no responde.
  final double? maxDistance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              Icons.menu_book_outlined,
              size: 13,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: AppSpacing.xs + 2),
            Text(
              'FROM THE MANUAL',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            for (final source in sources)
              _SourceChip(
                source: source,
                maxDistance: maxDistance ?? kFallbackMaxDistance,
              ),
          ],
        ),
      ],
    );
  }
}

class _SourceChip extends StatelessWidget {
  const _SourceChip({required this.source, required this.maxDistance});

  final AgentCitation source;
  final double maxDistance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final semantic = context.semantic;

    // "Fuerte" = claramente por debajo del umbral del backend; "parcial" = dentro pero cerca
    // del corte. La proporción es una decisión de presentación; el umbral, del backend.
    final strong = maxDistance * 0.77;
    final (color, tooltip) = switch (source.distance) {
      final d when d <= strong => (semantic.success, 'Strong match with the documentation'),
      final d when d <= maxDistance => (
        semantic.warning,
        'Partial match with the documentation',
      ),
      _ => (theme.colorScheme.onSurfaceVariant, 'Weak match'),
    };

    return Tooltip(
      message: '$tooltip (distance ${source.distance.toStringAsFixed(3)})',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 5),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface.withValues(alpha: 0.6),
          borderRadius: AppRadii.bar,
          border: Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            const SizedBox(width: AppSpacing.sm),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 210),
              child: Text(
                source.citation.isEmpty ? source.label : source.citation,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.labelMedium?.copyWith(
                  color: theme.colorScheme.onSurface,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
