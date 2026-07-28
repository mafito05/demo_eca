/// Selector de contexto de equipo para ECAHelp.
///
/// Sustituye al `DropdownButtonFormField` que iba en el `bottom` del AppBar. Dos problemas de aquel:
/// el `PreferredSize(64)` daba una franja estrecha donde el campo quedaba apretado, y las opciones
/// `"CODE — Nombre completo del equipo"` desbordaban el menú desplegable en cuanto el nombre era
/// largo. Con más de diez máquinas, además, un desplegable sin búsqueda es inservible.
///
/// Aquí es un tile en el cuerpo que abre una hoja con búsqueda, agrupada por especialidad. El AppBar
/// queda limpio y el selector escala.
library;

import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme_extensions.dart';
import '../../../../core/theme/design_tokens.dart';
import '../../../../shared/domain/specialty.dart';
import '../../../../shared/widgets/code_badge.dart';
import '../../../../shared/widgets/specialty_avatar.dart';
import '../../../machine/data/machine_repository.dart';

/// Tile que muestra el contexto actual y abre el selector.
class MachineContextTile extends StatelessWidget {
  const MachineContextTile({
    required this.machines,
    required this.selectedId,
    required this.onChanged,
    super.key,
  });

  final List<MachineSummary> machines;
  final String? selectedId;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selected = machines.where((machine) => machine.id == selectedId).firstOrNull;

    return Material(
      color: theme.colorScheme.surfaceContainerHigh,
      child: InkWell(
        onTap: () => _open(context),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.screenH,
            vertical: AppSpacing.md,
          ),
          child: Row(
            children: [
              if (selected != null)
                SpecialtyAvatar(specialty: selected.specialty, size: AppSizes.avatarSm)
              else
                Container(
                  width: AppSizes.avatarSm,
                  height: AppSizes.avatarSm,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    Icons.public,
                    size: 18,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'EQUIPMENT CONTEXT',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    Text(
                      selected?.name ?? 'No equipment — general questions only',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleSmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                'Change',
                style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.primary),
              ),
              Icon(Icons.expand_more, size: 18, color: theme.colorScheme.primary),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _open(BuildContext context) async {
    final result = await showModalBottomSheet<_Selection>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => _PickerSheet(machines: machines, selectedId: selectedId),
    );
    if (result != null) {
      onChanged(result.machineId);
    }
  }
}

/// Envoltorio para poder devolver `null` (sin equipo) distinguiéndolo de cerrar la hoja.
class _Selection {
  const _Selection(this.machineId);
  final String? machineId;
}

class _PickerSheet extends StatefulWidget {
  const _PickerSheet({required this.machines, required this.selectedId});

  final List<MachineSummary> machines;
  final String? selectedId;

  @override
  State<_PickerSheet> createState() => _PickerSheetState();
}

class _PickerSheetState extends State<_PickerSheet> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final needle = _query.trim().toLowerCase();
    final visible = needle.isEmpty
        ? widget.machines
        : widget.machines
              .where(
                (machine) =>
                    machine.name.toLowerCase().contains(needle) ||
                    machine.code.toLowerCase().contains(needle) ||
                    SpecialtyStyle.labelOf(machine.specialty).toLowerCase().contains(needle),
              )
              .toList();

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Equipment context', style: theme.textTheme.titleMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'With a machine selected, answers come from its manual and cite the exact section. '
              'Without one, only the global corpus is available.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),

            // La búsqueda solo aparece cuando hay suficientes máquinas para necesitarla: con tres,
            // un campo de búsqueda es un obstáculo.
            if (widget.machines.length > 6) ...[
              TextField(
                autofocus: false,
                decoration: const InputDecoration(
                  hintText: 'Search by name, code or specialty',
                  prefixIcon: Icon(Icons.search),
                ),
                onChanged: (value) => setState(() => _query = value),
              ),
              const SizedBox(height: AppSpacing.md),
            ],

            Flexible(
              child: ListView(
                shrinkWrap: true,
                children: [
                  _Option(
                    icon: Icons.public,
                    title: 'No equipment',
                    subtitle: 'General questions only',
                    selected: widget.selectedId == null,
                    onTap: () => Navigator.pop(context, const _Selection(null)),
                  ),
                  const Divider(),
                  for (final machine in visible)
                    _Option(
                      machine: machine,
                      title: machine.name,
                      subtitle: SpecialtyStyle.labelOf(machine.specialty),
                      selected: widget.selectedId == machine.id,
                      onTap: () => Navigator.pop(context, _Selection(machine.id)),
                    ),
                  if (visible.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(AppSpacing.xl),
                      child: Text(
                        'No equipment matches "$_query".',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
          ],
        ),
      ),
    );
  }
}

class _Option extends StatelessWidget {
  const _Option({
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
    this.machine,
    this.icon,
  });

  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;
  final MachineSummary? machine;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = machine == null ? null : context.specialties.resolve(machine!.specialty);

    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: machine != null
          ? SpecialtyAvatar(specialty: machine!.specialty, size: AppSizes.avatarSm)
          : Container(
              width: AppSizes.avatarSm,
              height: AppSizes.avatarSm,
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
            ),
      title: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Row(
        children: [
          if (machine != null) ...[
            CodeBadge(machine!.code, tone: colors!.accent, dense: true),
            const SizedBox(width: AppSpacing.sm),
          ],
          Expanded(
            child: Text(
              subtitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
      trailing: selected ? Icon(Icons.check, color: theme.colorScheme.primary) : null,
      onTap: onTap,
    );
  }
}
