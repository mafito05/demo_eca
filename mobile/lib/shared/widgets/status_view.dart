/// Estado de error, vacío o bloqueado: un solo componente para los cinco que había.
///
/// Antes existían `_CatalogError`, `_Problem`, `_LessonError`, `_CameraUnavailable` y el
/// `errorBuilder` del router, todos con la misma estructura (icono grande, título, mensaje, botón) y
/// cinco tamaños y tonos distintos. Peor: los estados vacíos eran inconsistentes — unos ricos, otros
/// un `Text` plano de una frase.
///
/// Tres detalles que hay que respetar al usarlo o se rompen cosas:
///
/// 1. **`scrollable` va a `true` por defecto**, con `AlwaysScrollableScrollPhysics`. Sin eso, meter
///    este widget dentro del `RefreshIndicator` del catálogo **desactiva el pull-to-refresh en
///    silencio**, justo en el caso en el que el usuario quiere reintentar.
/// 2. Para listas de slivers hay `StatusView.sliver()`, que envuelve en
///    `SliverFillRemaining(hasScrollBody: true)`. Con `false`, tres acciones desbordan en un móvil
///    de 320 de ancho.
/// 3. `compact` para los sitios embebidos (la caja 16:9 del reproductor, la franja del chat): sin
///    círculo, icono pequeño, en fila.
library;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme_extensions.dart';
import '../../core/theme/design_tokens.dart';

enum StatusTone { neutral, error, caution, success }

enum AppActionStyle { filled, outlined, text }

/// Acción de un `StatusView`. Es un valor `const` y no lleva `BuildContext`.
@immutable
class AppAction {
  const AppAction({
    required this.label,
    required this.onPressed,
    this.icon,
    this.style = AppActionStyle.filled,
  });

  final String label;
  final VoidCallback onPressed;
  final IconData? icon;
  final AppActionStyle style;
}

class StatusView extends StatelessWidget {
  const StatusView({
    required this.icon,
    required this.title,
    super.key,
    this.message,
    this.actions = const <AppAction>[],
    this.tone = StatusTone.neutral,
    this.scrollable = true,
    this.compact = false,
  });

  /// Error de red o de servidor.
  const StatusView.error({
    required this.title,
    super.key,
    this.message,
    this.actions = const <AppAction>[],
    this.icon = Icons.cloud_off_outlined,
    this.scrollable = true,
    this.compact = false,
  }) : tone = StatusTone.error;

  /// Sin contenido todavía. No es un fallo, así que el tono es neutro.
  const StatusView.empty({
    required this.title,
    super.key,
    this.message,
    this.actions = const <AppAction>[],
    this.icon = Icons.inbox_outlined,
    this.scrollable = true,
    this.compact = false,
  }) : tone = StatusTone.neutral;

  /// Bloqueado por un prerrequisito. Tono de aviso: es esperado, no roto.
  const StatusView.locked({
    required this.title,
    super.key,
    this.message,
    this.actions = const <AppAction>[],
    this.icon = Icons.lock_outline,
    this.scrollable = true,
    this.compact = false,
  }) : tone = StatusTone.caution;

  final IconData icon;
  final String title;
  final String? message;
  final List<AppAction> actions;
  final StatusTone tone;
  final bool scrollable;
  final bool compact;

  /// Versión para listas de slivers.
  static Widget sliver({
    required IconData icon,
    required String title,
    String? message,
    List<AppAction> actions = const <AppAction>[],
    StatusTone tone = StatusTone.neutral,
  }) => SliverFillRemaining(
    hasScrollBody: true,
    child: StatusView(
      icon: icon,
      title: title,
      message: message,
      actions: actions,
      tone: tone,
      scrollable: false,
    ),
  );

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final semantic = context.semantic;
    final (accent, container) = switch (tone) {
      StatusTone.error => (scheme.error, scheme.errorContainer),
      StatusTone.caution => (semantic.warning, semantic.warningContainer),
      StatusTone.success => (semantic.success, semantic.successContainer),
      StatusTone.neutral => (scheme.onSurfaceVariant, scheme.surfaceContainerHighest),
    };

    if (compact) {
      return _CompactBody(icon: icon, title: title, message: message, accent: accent);
    }

    final body = Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: AppSizes.maxContentWidth),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xxl),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                child: Container(
                  width: AppSizes.statusCircle,
                  height: AppSizes.statusCircle,
                  decoration: BoxDecoration(color: container, shape: BoxShape.circle),
                  child: Icon(icon, size: AppSizes.statusIcon, color: accent),
                ),
              ),
              const SizedBox(height: AppSpacing.xxl),
              Text(
                title,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              if (message != null) ...[
                const SizedBox(height: AppSpacing.md),
                Text(
                  message!,
                  textAlign: TextAlign.center,
                  style: Theme.of(
                    context,
                  ).textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
                ),
              ],
              if (actions.isNotEmpty) const SizedBox(height: AppSpacing.xxl),
              for (final action in actions.take(3)) ...[
                _ActionButton(action: action),
                const SizedBox(height: AppSpacing.sm),
              ],
            ],
          ),
        ),
      ),
    );

    if (!scrollable) {
      return body;
    }
    // `AlwaysScrollableScrollPhysics` es lo que mantiene vivo el pull-to-refresh cuando este
    // widget es el único hijo de un RefreshIndicator.
    return SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: MediaQuery.sizeOf(context).height * 0.7),
        child: body,
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({required this.action});

  final AppAction action;

  @override
  Widget build(BuildContext context) {
    final label = Text(action.label);
    return switch (action.style) {
      AppActionStyle.filled => action.icon != null
          ? FilledButton.icon(
              onPressed: action.onPressed,
              icon: Icon(action.icon),
              label: label,
            )
          : FilledButton(onPressed: action.onPressed, child: label),
      AppActionStyle.outlined => action.icon != null
          ? OutlinedButton.icon(
              onPressed: action.onPressed,
              icon: Icon(action.icon),
              label: label,
            )
          : OutlinedButton(onPressed: action.onPressed, child: label),
      AppActionStyle.text => TextButton(onPressed: action.onPressed, child: label),
    };
  }
}

/// Variante en fila, para huecos pequeños como la caja del reproductor.
class _CompactBody extends StatelessWidget {
  const _CompactBody({
    required this.icon,
    required this.title,
    required this.message,
    required this.accent,
  });

  final IconData icon;
  final String title;
  final String? message;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 24, color: accent),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleSmall),
                if (message != null)
                  Text(
                    message!,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(
                      context,
                    ).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
