import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/providers.dart';
import '../../../core/theme/design_tokens.dart';
import '../../../shared/widgets/code_badge.dart';
import '../../../shared/widgets/info_banner.dart';
import '../../../shared/widgets/logo_mark.dart';

/// Pantalla de entrada.
///
/// Durante la demo el acceso es un botón: el bypass del backend emite un token real para el
/// usuario de demostración (D-003). El formulario de credenciales está previsto pero no se
/// muestra todavía, porque el flujo que se quiere enseñar es *escanear y entrar*.
///
/// En compilaciones de depuración muestra además la URL del backend y un comprobador de
/// conexión. No es decoración: probando en un emulador o en un teléfono, el fallo más frecuente es
/// de red (IP equivocada, DHCP que cambió la del host, firewall), y sin esto todos esos casos se
/// ven igual —"no entra"— y hay que adivinar cuál es.
class EntryScreen extends ConsumerStatefulWidget {
  const EntryScreen({super.key});

  @override
  ConsumerState<EntryScreen> createState() => _EntryScreenState();
}

class _EntryScreenState extends ConsumerState<EntryScreen> {
  String? _diagnosis;
  bool _checking = false;

  Future<void> _diagnose() async {
    setState(() {
      _checking = true;
      _diagnosis = null;
    });
    final result = await ref.read(apiClientProvider).diagnose();
    if (mounted) {
      setState(() {
        _checking = false;
        _diagnosis = result;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Align(child: LogoMark()),
                  const SizedBox(height: AppSpacing.lg),
                  Text(
                    'DemoECA',
                    style: theme.textTheme.headlineMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: AppSpacing.xs + 2),
                  Text(
                    'Technical training for medical equipment',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 36),
                  if (auth is AuthAnonymous && auth.error != null) ...[
                    InfoBanner(message: auth.error!, tone: BannerTone.error),
                    const SizedBox(height: AppSpacing.xl),
                  ],
                  if (auth is AuthLoading)
                    const Center(child: CircularProgressIndicator())
                  else
                    FilledButton.icon(
                      onPressed: () => ref.read(authProvider.notifier).enterAsDemo(),
                      icon: const Icon(Icons.login),
                      label: const Text('Sign in'),
                    ),
                  const SizedBox(height: 14),
                  Text(
                    'Demo access. Scan the QR code on a machine to open its training.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  if (kDebugMode) ...[
                    const SizedBox(height: AppSpacing.xxl),
                    Theme(
                      data: theme.copyWith(dividerColor: Colors.transparent),
                      child: ExpansionTile(
                        tilePadding: EdgeInsets.zero,
                        title: Text(
                          'Developer diagnostics',
                          style: theme.textTheme.labelMedium?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                        leading: Icon(
                          Icons.build_outlined,
                          size: 18,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        children: [
                          const Align(
                            alignment: Alignment.centerLeft,
                            child: CodeBadge(AppConfig.apiBaseUrl),
                          ),
                          const SizedBox(height: AppSpacing.md),
                          if (_checking)
                            const Center(
                              child: SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              ),
                            )
                          else
                            OutlinedButton.icon(
                              onPressed: _diagnose,
                              icon: const Icon(Icons.network_check, size: 18),
                              label: const Text('Check connection'),
                            ),
                          if (_diagnosis != null) ...[
                            const SizedBox(height: AppSpacing.md),
                            InfoBanner(message: _diagnosis!),
                          ],
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
