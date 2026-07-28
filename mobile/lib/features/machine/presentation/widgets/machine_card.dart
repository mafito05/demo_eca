/// Tarjeta de un equipo en el catálogo.
///
/// Sustituye al `Card > ListTile` con `CircleAvatar` genérico, que hacía que diez equipos fuesen
/// diez veces el mismo icono. Ahora el color y el icono vienen de la especialidad, así que una lista
/// larga se recorre de un vistazo sin leer.
///
/// Muestra tres datos que existían y no se usaban: la descripción (el backend ya la devolvía), el
/// progreso del usuario (endpoint ampliado) y el código en tipografía mono.
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme_extensions.dart';
import '../../../../core/theme/design_tokens.dart';
import '../../../../shared/widgets/app_progress_bar.dart';
import '../../../../shared/widgets/code_badge.dart';
import '../../../../shared/widgets/specialty_avatar.dart';
import '../../data/machine_repository.dart';

class MachineCard extends StatelessWidget {
  const MachineCard({required this.machine, required this.onTap, super.key});

  final MachineSummary machine;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.specialties.resolve(machine.specialty);

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        // El radio del InkWell tiene que coincidir con el de la Card o la onda de tinta se sale
        // por las esquinas.
        borderRadius: AppRadii.card,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.cardPad),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SpecialtyAvatar(specialty: machine.specialty),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      machine.name,
                      style: theme.textTheme.titleMedium,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Row(
                      children: [
                        // `Flexible` y no ancho fijo: hay códigos de equipo de 28 caracteres, y sin
                        // esto imponen su ancho a la fila y la desbordan en un móvil de 320.
                        Flexible(
                          child: CodeBadge(machine.code, tone: colors.accent, dense: true),
                        ),
                        if (machine.manufacturer != null) ...[
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: Text(
                              machine.manufacturer!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (machine.description != null && machine.description!.isNotEmpty) ...[
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        machine.description!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                    // El progreso solo aparece si el usuario ya empezó. Una barra a cero en cada
                    // tarjeta añade ruido y no informa de nada.
                    if (machine.isStarted) ...[
                      const SizedBox(height: AppSpacing.md),
                      AppProgressBar(
                        value: machine.progressPercent / 100,
                        height: 6,
                        label: '${machine.completedLessons}/${machine.lessonsCount}',
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Icon(
                Icons.chevron_right,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
