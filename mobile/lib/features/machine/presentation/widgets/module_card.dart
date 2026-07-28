/// Tarjeta de un módulo de la ruta de aprendizaje.
///
/// Añade dos cosas que faltaban: el **número de orden** en un círculo, que convierte una pila de
/// tarjetas en una secuencia (que es lo que es una ruta de aprendizaje), y la
/// **`description` del módulo** — el modelo la parseaba y nadie la renderizaba.
///
/// El bloqueo se comunica con una pastilla "Locked" y no solo atenuando el título: un título gris se
/// confunde con "vacío" o con un error de carga.
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme_extensions.dart';
import '../../../../core/theme/design_tokens.dart';
import '../../../../shared/widgets/app_progress_bar.dart';
import '../../../../shared/widgets/tonal_pill.dart';
import '../../../lms/data/lms_repository.dart';
import 'lesson_row.dart';

class ModuleCard extends StatelessWidget {
  const ModuleCard({
    required this.module,
    required this.index,
    required this.onOpenLesson,
    super.key,
  });

  final PathModule module;
  final int index;
  final void Function(PathLesson lesson) onOpenLesson;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final semantic = context.semantic;
    final complete = module.totalLessons > 0 && module.completedLessons == module.totalLessons;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.cardPad),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _OrderBadge(index: index, complete: complete, locked: module.locked),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        module.title,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: module.locked ? theme.colorScheme.onSurfaceVariant : null,
                        ),
                      ),
                      if (module.description != null && module.description!.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          module.description!,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                if (module.locked)
                  TonalPill(
                    label: 'Locked',
                    icon: Icons.lock_outline,
                    foreground: semantic.onWarningContainer,
                    background: semantic.warningContainer,
                  )
                else
                  Text(
                    '${module.completedLessons}/${module.totalLessons}',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: complete ? semantic.success : theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
              ],
            ),

            if (module.locked)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.md),
                child: Text(
                  'Complete the previous module to unlock this one.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              )
            else if (module.totalLessons > 0) ...[
              const SizedBox(height: AppSpacing.md),
              AppProgressBar(
                value: module.completedLessons / module.totalLessons,
                height: 5,
              ),
            ],

            if (!module.locked) ...[
              const SizedBox(height: AppSpacing.sm),
              const Divider(),
              for (final lesson in module.lessons)
                LessonRow(
                  lesson: lesson,
                  locked: module.locked,
                  onTap: () => onOpenLesson(lesson),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _OrderBadge extends StatelessWidget {
  const _OrderBadge({required this.index, required this.complete, required this.locked});

  final int index;
  final bool complete;
  final bool locked;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final semantic = context.semantic;

    final (background, foreground) = switch (true) {
      _ when complete => (semantic.successContainer, semantic.onSuccessContainer),
      _ when locked => (scheme.surfaceContainerHighest, scheme.onSurfaceVariant),
      _ => (scheme.primaryContainer, scheme.onPrimaryContainer),
    };

    return Container(
      width: 30,
      height: 30,
      decoration: BoxDecoration(color: background, shape: BoxShape.circle),
      alignment: Alignment.center,
      child: complete
          ? Icon(Icons.check_rounded, size: 18, color: foreground)
          : Text(
              '${index + 1}',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(color: foreground),
            ),
    );
  }
}
