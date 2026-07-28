/// Encabezado de la ficha de equipo.
///
/// Dos mejoras de fondo respecto al `Card` outlined que había:
///
/// 1. **Se pinta antes de que resuelva la ruta de aprendizaje.** Solo necesita `ResolvedMachine`,
///    que ya está disponible, así que la pantalla deja de tener un estado de carga en blanco: se ve
///    el equipo al instante y el progreso aparece cuando llega.
/// 2. Usa `modulesCount`, que el backend devolvía y nadie leía, y la **etiqueta traducida** de la
///    especialidad. Antes se pintaba el slug crudo (`urologia`) porque el mapa de etiquetas era
///    privado del catálogo.
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme_extensions.dart';
import '../../../../core/theme/design_tokens.dart';
import '../../../../shared/domain/specialty.dart';
import '../../../../shared/format/formatters.dart';
import '../../../../shared/widgets/code_badge.dart';
import '../../../../shared/widgets/progress_ring.dart';
import '../../../../shared/widgets/tonal_pill.dart';
import '../../../lms/data/lms_repository.dart';
import '../../data/machine_repository.dart';

class MachineHeader extends StatelessWidget {
  const MachineHeader({required this.machine, super.key, this.path});

  final ResolvedMachine machine;

  /// Nulo mientras la ruta de aprendizaje todavía carga.
  final LearningPath? path;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.specialties.resolve(machine.specialty);
    final style = SpecialtyStyle.resolve(machine.specialty);

    final totalMinutes = path == null
        ? 0
        : path!.modules
              .expand((module) => module.lessons)
              .fold<int>(0, (sum, lesson) => sum + (lesson.estimatedMinutes ?? 0));

    return Container(
      padding: const EdgeInsets.all(AppSpacing.xl),
      decoration: BoxDecoration(
        borderRadius: AppRadii.card,
        // Degradado tenue derivado de la especialidad: da identidad al equipo sin necesitar una
        // fotografía, que no existe (`cover_image_key` no se expone en ningún endpoint).
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            colors.container,
            Color.lerp(colors.container, theme.colorScheme.surface, 0.65)!,
          ],
        ),
        border: Border.all(color: colors.accent.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        TonalPill(
                          label: style.label,
                          icon: style.icon,
                          foreground: colors.onContainer,
                          background: theme.colorScheme.surface.withValues(alpha: 0.55),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        CodeBadge(machine.code, tone: colors.accent, dense: true),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      machine.name,
                      style: theme.textTheme.headlineSmall?.copyWith(color: colors.onContainer),
                    ),
                  ],
                ),
              ),
              if (path != null) ...[
                const SizedBox(width: AppSpacing.lg),
                ProgressRing(percent: path!.progressPercent),
              ],
            ],
          ),

          if (machine.description != null && machine.description!.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              machine.description!,
              style: theme.textTheme.bodyMedium?.copyWith(
                // Sólido, no alpha: el fondo ya se degrada hacia surface, y atenuar el texto
              // encima acumulaba pérdida de contraste por los dos lados (bug de "letras que no
              // se ven").
              color: colors.onContainer,
              ),
            ),
          ],

          const SizedBox(height: AppSpacing.lg),
          // Metadatos disponibles desde el primer frame: `modulesCount` viene con la resolución
          // del QR, no con la ruta de aprendizaje.
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            children: [
              _Meta(
                icon: Icons.layers_outlined,
                label: '${machine.modulesCount} '
                    '${machine.modulesCount == 1 ? 'module' : 'modules'}',
                color: colors.onContainer,
              ),
              if (path != null)
                _Meta(
                  icon: Icons.menu_book_outlined,
                  label: '${path!.totalLessons} lessons',
                  color: colors.onContainer,
                ),
              if (totalMinutes > 0)
                _Meta(
                  icon: Icons.schedule_outlined,
                  label: totalMinutesLabel(totalMinutes),
                  color: colors.onContainer,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.icon, required this.label, required this.color});

  final IconData icon;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 15, color: color),
      const SizedBox(width: AppSpacing.xs + 2),
      Text(
        label,
        style: Theme.of(context).textTheme.bodySmall?.copyWith(color: color),
      ),
    ],
  );
}
