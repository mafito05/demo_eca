import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/providers.dart';
import '../../../core/theme/app_theme_extensions.dart';
import '../../../core/theme/design_tokens.dart';
import '../../../shared/domain/specialty.dart';
import '../../../shared/widgets/async_value_view.dart';
import '../../../shared/widgets/section_header.dart';
import '../../../shared/widgets/skeletons/catalog_skeleton.dart';
import '../../../shared/widgets/status_view.dart';
import '../../auth/data/auth_repository.dart';
import '../../auth/presentation/profile_sheet.dart';
import '../data/machine_repository.dart';
import 'widgets/machine_card.dart';

/// Catálogo de equipos, agrupado por especialidad.
///
/// Es el módulo principal y el punto de entrada tras iniciar sesión. El usuario explora libremente:
/// todas las especialidades, todos los equipos y todas sus capacitaciones. Escanear un QR es un
/// atajo para saltar directo a un equipo concreto, no un requisito para ver el resto (D-036).
///
/// **La especialidad del usuario ordena, no filtra.** Sus equipos salen primero, con un marcador,
/// pero el resto sigue visible: filtrar automáticamente ocultaría equipo, y con una máquina delante
/// en un pasillo eso es un fallo grave, no una comodidad.
class CatalogScreen extends ConsumerWidget {
  const CatalogScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalog = ref.watch(machineCatalogProvider);
    final auth = ref.watch(authProvider);
    final user = auth is AuthReady ? auth.user : null;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(machineCatalogProvider),
        child: CustomScrollView(
          slivers: [
            SliverAppBar.large(
              title: const Text('Equipment'),
              actions: [
                IconButton(
                  tooltip: 'Enter equipment code',
                  icon: const Icon(Icons.keyboard_outlined),
                  onPressed: () => _promptCode(context),
                ),
                // Avatar en lugar del icono de logout que había: aquel cerraba la sesión de un solo
                // toque, sin confirmación, y estaba justo al lado del botón de teclado.
                Padding(
                  padding: const EdgeInsets.only(right: AppSpacing.md),
                  child: _ProfileButton(user: user),
                ),
              ],
            ),

            if (user != null)
              SliverToBoxAdapter(child: _WelcomeHeader(user: user)),

            AsyncValueView<List<MachineSummary>>(
              value: catalog,
              sliver: true,
              errorTitle: 'Could not load the catalogue',
              onRetry: () => ref.invalidate(machineCatalogProvider),
              skeleton: () => const CatalogSkeleton(),
              data: (machines) => machines.isEmpty
                  ? StatusView.sliver(
                      icon: Icons.inbox_outlined,
                      title: 'No equipment yet',
                      message:
                          'Published training will appear here. You can also scan the QR code '
                          'stuck on a machine to open it directly.',
                      actions: [
                        AppAction(
                          label: 'Scan a QR code',
                          icon: Icons.qr_code_scanner,
                          onPressed: () => context.go('/escanear'),
                        ),
                      ],
                    )
                  : _CatalogBody(machines: machines, userSpecialty: user?.specialty),
            ),

            const SliverToBoxAdapter(child: SizedBox(height: AppSpacing.xxl)),
          ],
        ),
      ),
    );
  }

  Future<void> _promptCode(BuildContext context) async {
    final controller = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Equipment code'),
        content: TextField(
          controller: controller,
          autofocus: true,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(hintText: 'Code printed next to the QR'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Open'),
          ),
        ],
      ),
    );

    if (code == null || code.isEmpty || !context.mounted) {
      return;
    }
    context.push('/m/$code');
  }
}

/// Filtros y secciones.
///
/// Es un widget aparte porque necesita `ref` para el filtro pero no debe reconstruir el AppBar
/// grande al cambiarlo: un `SliverAppBar.large` que se rehace al pulsar un chip pierde su posición
/// de scroll.
class _CatalogBody extends ConsumerWidget {
  const _CatalogBody({required this.machines, required this.userSpecialty});

  final List<MachineSummary> machines;
  final String? userSpecialty;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(specialtyFilterProvider);

    final specialties = machines.map((machine) => machine.specialty).toSet().toList()
      ..sort(_bySpecialtyPriority);

    final visible = filter == null
        ? machines
        : machines.where((machine) => machine.specialty == filter).toList();

    final grouped = <String, List<MachineSummary>>{};
    for (final machine in visible) {
      grouped.putIfAbsent(machine.specialty, () => []).add(machine);
    }
    final sections = grouped.keys.toList()..sort(_bySpecialtyPriority);

    return SliverList.list(
      children: [
        if (specialties.length > 1) _FilterRow(specialties: specialties, selected: filter),

        for (final specialty in sections) ...[
          SectionHeader(
            title: SpecialtyStyle.labelOf(specialty),
            icon: SpecialtyStyle.resolve(specialty).icon,
            color: context.specialties.resolve(specialty).accent,
            trailing: _sectionTrailing(specialty, grouped[specialty]!.length),
          ),
          for (final machine in grouped[specialty]!)
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.screenH,
                vertical: AppSpacing.xs,
              ),
              // Misma ruta que abre el QR: el token es el identificador común, así que explorar el
              // catálogo y escanear llevan exactamente al mismo sitio.
              //
              // `push` y no `go`: apila sobre el catálogo, así aparece la flecha de volver.
              child: MachineCard(
                machine: machine,
                onTap: () => context.push('/m/${machine.qrToken}'),
              ),
            ),
        ],
      ],
    );
  }

  String? _sectionTrailing(String specialty, int count) {
    if (SpecialtyStyle.matchesUserSpecialty(userSpecialty, specialty)) {
      return 'Yours · $count';
    }
    return '$count';
  }

  /// La especialidad del usuario primero; el resto, alfabético.
  int _bySpecialtyPriority(String a, String b) {
    final aMine = SpecialtyStyle.matchesUserSpecialty(userSpecialty, a);
    final bMine = SpecialtyStyle.matchesUserSpecialty(userSpecialty, b);
    if (aMine != bMine) {
      return aMine ? -1 : 1;
    }
    return SpecialtyStyle.labelOf(a).compareTo(SpecialtyStyle.labelOf(b));
  }
}

class _FilterRow extends ConsumerWidget {
  const _FilterRow({required this.specialties, required this.selected});

  final List<String> specialties;
  final String? selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    padding: const EdgeInsets.fromLTRB(
      AppSpacing.screenH,
      AppSpacing.sm,
      AppSpacing.screenH,
      0,
    ),
    child: Row(
      children: [
        FilterChip(
          label: const Text('All'),
          selected: selected == null,
          onSelected: (_) => ref.read(specialtyFilterProvider.notifier).state = null,
        ),
        for (final specialty in specialties) ...[
          const SizedBox(width: AppSpacing.sm),
          FilterChip(
            avatar: Icon(
              SpecialtyStyle.resolve(specialty).icon,
              size: 16,
              color: context.specialties.resolve(specialty).accent,
            ),
            label: Text(SpecialtyStyle.labelOf(specialty)),
            selected: selected == specialty,
            onSelected: (isSelected) => ref.read(specialtyFilterProvider.notifier).state =
                isSelected ? specialty : null,
          ),
        ],
      ],
    ),
  );
}

/// Saludo con el nombre y la institución del usuario, que hasta ahora no se mostraban en ninguna
/// pantalla de la app pese a venir en `/auth/me`.
class _WelcomeHeader extends StatelessWidget {
  const _WelcomeHeader({required this.user});

  final AppUser user;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final subtitle = [
      if (user.specialty != null) user.specialty!,
      if (user.institution != null) user.institution!,
    ].join(' · ');

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenH,
        0,
        AppSpacing.screenH,
        AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(user.fullName, style: theme.textTheme.titleMedium),
          if (subtitle.isNotEmpty)
            Text(
              subtitle,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
        ],
      ),
    );
  }
}

class _ProfileButton extends StatelessWidget {
  const _ProfileButton({required this.user});

  final AppUser? user;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final initials = user == null
        ? '?'
        : user!.fullName
              .split(' ')
              .where((part) => part.isNotEmpty)
              .take(2)
              .map((part) => part[0].toUpperCase())
              .join();

    return Tooltip(
      message: 'Profile and settings',
      child: InkWell(
        onTap: () => showProfileSheet(context),
        customBorder: const CircleBorder(),
        child: Container(
          width: AppSizes.avatarSm,
          height: AppSizes.avatarSm,
          decoration: BoxDecoration(
            color: theme.colorScheme.primaryContainer,
            shape: BoxShape.circle,
          ),
          alignment: Alignment.center,
          child: Text(
            initials.isEmpty ? '?' : initials,
            style: theme.textTheme.labelMedium?.copyWith(
              color: theme.colorScheme.onPrimaryContainer,
            ),
          ),
        ),
      ),
    );
  }
}
