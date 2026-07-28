/// Fila de una lección dentro de un módulo.
///
/// Muestra tres datos que el modelo ya traía y que no se pintaban en ninguna parte:
/// `completedAt` ("Completed 26 Jul"), `lastPositionSeconds` ("Resume at 4:12") y la duración
/// estimada. Son justo los que responden "¿por dónde iba?", que es la pregunta con la que un
/// técnico abre la app.
///
/// El círculo de estado a la izquierda sustituye al icono suelto: con cinco estados posibles
/// (completada, en curso, disponible, bloqueada, vídeo procesándose) hace falta que se distingan de
/// un vistazo, y un icono sin fondo no separa "bloqueada" de "por empezar".
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme_extensions.dart';
import '../../../../core/theme/design_tokens.dart';
import '../../../../shared/format/formatters.dart';
import '../../../lms/data/lms_repository.dart';

class LessonRow extends StatelessWidget {
  const LessonRow({
    required this.lesson,
    required this.locked,
    required this.onTap,
    super.key,
  });

  final PathLesson lesson;
  final bool locked;
  final VoidCallback onTap;

  /// Un vídeo aún transcodificándose no se puede abrir: el playlist todavía no existe.
  bool get _unavailable => locked || (lesson.hasVideo && !lesson.videoReady);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final semantic = context.semantic;
    final subtitle = _subtitle(theme, semantic);

    return InkWell(
      onTap: _unavailable ? null : onTap,
      borderRadius: AppRadii.field,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          vertical: AppSpacing.md,
          horizontal: AppSpacing.xs,
        ),
        child: Row(
          children: [
            _StatusCircle(lesson: lesson, locked: locked),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    lesson.title,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontSize: 15,
                      color: _unavailable ? theme.colorScheme.onSurfaceVariant : null,
                    ),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    subtitle,
                  ],
                ],
              ),
            ),
            if (lesson.estimatedMinutes != null && !_unavailable) ...[
              const SizedBox(width: AppSpacing.sm),
              Text(
                minutesLabel(lesson.estimatedMinutes),
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
            if (!_unavailable)
              Icon(Icons.chevron_right, size: 20, color: theme.colorScheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }

  Widget? _subtitle(ThemeData theme, AppSemanticColors semantic) {
    if (lesson.hasVideo && !lesson.videoReady) {
      return Text(
        'Video still processing',
        style: theme.textTheme.bodySmall?.copyWith(color: semantic.processing),
      );
    }
    if (locked) {
      return null;
    }
    if (lesson.progress.isCompleted) {
      final when = completedAtLabel(lesson.progress.completedAt);
      return Text(
        when.isEmpty ? 'Completed' : 'Completed $when',
        style: theme.textTheme.bodySmall?.copyWith(color: semantic.success),
      );
    }
    if (lesson.progress.isStarted) {
      // "Reanudar en 4:12" es más accionable que "37% visto": dice dónde retomar.
      final position = lesson.progress.lastPositionSeconds;
      final label = position > 5
          ? 'Resume at ${durationLabel(position)}'
          : '${lesson.progress.watchedPercent.round()}% watched';
      return Text(
        label,
        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.primary),
      );
    }
    return null;
  }
}

class _StatusCircle extends StatelessWidget {
  const _StatusCircle({required this.lesson, required this.locked});

  final PathLesson lesson;
  final bool locked;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final semantic = context.semantic;

    final (icon, foreground, background) = switch (lesson) {
      _ when locked => (
        Icons.lock_outline,
        scheme.onSurfaceVariant,
        scheme.surfaceContainerHighest,
      ),
      _ when lesson.hasVideo && !lesson.videoReady => (
        Icons.hourglass_empty,
        semantic.processing,
        semantic.processing.withValues(alpha: 0.12),
      ),
      _ when lesson.progress.isCompleted => (
        Icons.check_rounded,
        semantic.onSuccessContainer,
        semantic.successContainer,
      ),
      _ when lesson.progress.isStarted => (
        Icons.play_arrow_rounded,
        scheme.onPrimaryContainer,
        scheme.primaryContainer,
      ),
      _ => (_typeIcon, scheme.onSurfaceVariant, scheme.surfaceContainerHighest),
    };

    return Container(
      width: 32,
      height: 32,
      decoration: BoxDecoration(color: background, shape: BoxShape.circle),
      child: Icon(icon, size: 18, color: foreground),
    );
  }

  IconData get _typeIcon => switch (lesson.contentType) {
    'video' => Icons.play_arrow_rounded,
    'pdf' => Icons.description_outlined,
    _ => Icons.article_outlined,
  };
}
