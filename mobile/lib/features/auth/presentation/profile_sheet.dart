/// Hoja de perfil: identidad, tema y salida.
///
/// Existe por dos motivos. El primero es un fallo real: el catálogo tenía un `IconButton` de logout
/// que **cerraba la sesión de un solo toque, sin confirmación**, justo al lado del botón de teclado.
/// El segundo es que `AppUser` trae `fullName`, `role`, `specialty` e `institution` y **nada de eso
/// se mostraba en ninguna parte** de la app.
///
/// El selector de tema vive aquí porque el argumento de uso —de quirófano a sala técnica— implica que
/// a veces se quiere forzar el oscuro sin cambiar el ajuste del sistema entero.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../../../core/theme/design_tokens.dart';
import '../../../shared/domain/specialty.dart';

Future<void> showProfileSheet(BuildContext context) => showModalBottomSheet<void>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true,
  builder: (context) => const ProfileSheet(),
);

class ProfileSheet extends ConsumerWidget {
  const ProfileSheet({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final user = auth is AuthReady ? auth.user : null;
    final theme = Theme.of(context);
    final themeMode = ref.watch(themeModeProvider);

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl,
          0,
          AppSpacing.xl,
          AppSpacing.xl,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (user != null) ...[
              Row(
                children: [
                  Container(
                    width: AppSizes.avatarLg,
                    height: AppSizes.avatarLg,
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primaryContainer,
                      shape: BoxShape.circle,
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      _initials(user.fullName),
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: theme.colorScheme.onPrimaryContainer,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.lg),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(user.fullName, style: theme.textTheme.titleMedium),
                        Text(
                          _roleLabel(user.role),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
              if (user.institution != null)
                _InfoRow(
                  icon: Icons.business_outlined,
                  label: 'Institution',
                  value: user.institution!,
                ),
              if (user.specialty != null)
                _InfoRow(
                  icon: SpecialtyStyle.resolve(null).icon,
                  label: 'Specialty',
                  value: user.specialty!,
                ),
              _InfoRow(icon: Icons.mail_outline, label: 'Account', value: user.email),
              const SizedBox(height: AppSpacing.lg),
              const Divider(),
            ],

            const SizedBox(height: AppSpacing.lg),
            Text(
              'APPEARANCE',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            SegmentedButton<ThemeMode>(
              segments: const [
                ButtonSegment(
                  value: ThemeMode.system,
                  icon: Icon(Icons.brightness_auto_outlined),
                  label: Text('System'),
                ),
                ButtonSegment(
                  value: ThemeMode.light,
                  icon: Icon(Icons.light_mode_outlined),
                  label: Text('Light'),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  icon: Icon(Icons.dark_mode_outlined),
                  label: Text('Dark'),
                ),
              ],
              selected: {themeMode},
              showSelectedIcon: false,
              onSelectionChanged: (selection) =>
                  ref.read(themeModeProvider.notifier).set(selection.first),
            ),

            const SizedBox(height: AppSpacing.xxl),
            OutlinedButton.icon(
              icon: const Icon(Icons.logout),
              label: const Text('Sign out'),
              onPressed: () => _confirmSignOut(context, ref),
            ),
          ],
        ),
      ),
    );
  }

  /// Confirmación explícita. Antes bastaba un toque accidental en la barra superior.
  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text('You will need to sign in again to open any training.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );

    if (confirmed != true) {
      return;
    }
    // El notifier se captura ANTES del await implícito de la navegación: usar `ref` después de un
    // gap asíncrono es lo que dispara `use_build_context_synchronously`.
    final notifier = ref.read(authProvider.notifier);
    if (context.mounted) {
      Navigator.pop(context);
    }
    await notifier.logout();
  }

  static String _initials(String name) {
    final parts = name.split(' ').where((part) => part.isNotEmpty).take(2);
    if (parts.isEmpty) {
      return '?';
    }
    return parts.map((part) => part[0].toUpperCase()).join();
  }

  /// Etiqueta amable del rol. `trainee` es jerga interna del esquema, no algo que enseñar.
  static String _roleLabel(String role) => switch (role) {
    'superadmin' => 'Super administrator',
    'admin' => 'Content administrator',
    'trainee' => 'Technician in training',
    _ => role,
  };
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: Row(
        children: [
          Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.md),
          Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const Spacer(),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.end,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }
}
