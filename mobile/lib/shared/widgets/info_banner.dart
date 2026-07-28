/// Franja informativa: icono, texto y acción opcional.
///
/// Sustituye los dos banners hechos a mano (`Card(color: errorContainer)` en la entrada y el
/// `Container(color: errorContainer)` del chat) y el aviso legal, que hoy es texto gris flotando al
/// final de una lista donde nadie llega.
library;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme_extensions.dart';
import '../../core/theme/design_tokens.dart';

enum BannerTone { info, warning, error, success }

class InfoBanner extends StatelessWidget {
  const InfoBanner({
    required this.message,
    super.key,
    this.tone = BannerTone.info,
    this.icon,
    this.actionLabel,
    this.onAction,
    this.margin = EdgeInsets.zero,
  });

  final String message;
  final BannerTone tone;
  final IconData? icon;
  final String? actionLabel;
  final VoidCallback? onAction;
  final EdgeInsetsGeometry margin;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final semantic = context.semantic;

    final (background, foreground, defaultIcon) = switch (tone) {
      BannerTone.error => (scheme.errorContainer, scheme.onErrorContainer, Icons.error_outline),
      BannerTone.warning => (
        semantic.warningContainer,
        semantic.onWarningContainer,
        Icons.warning_amber_outlined,
      ),
      BannerTone.success => (
        semantic.successContainer,
        semantic.onSuccessContainer,
        Icons.check_circle_outline,
      ),
      BannerTone.info => (
        semantic.infoContainer,
        semantic.onInfoContainer,
        Icons.info_outline,
      ),
    };

    return Container(
      margin: margin,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      decoration: BoxDecoration(color: background, borderRadius: AppRadii.field),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon ?? defaultIcon, size: 20, color: foreground),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              message,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: foreground),
            ),
          ),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(width: AppSpacing.sm),
            TextButton(
              onPressed: onAction,
              style: TextButton.styleFrom(
                foregroundColor: foreground,
                // El mínimo del tema (48) desbordaría la altura de la franja.
                minimumSize: const Size(0, 32),
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              ),
              child: Text(actionLabel!),
            ),
          ],
        ],
      ),
    );
  }
}
