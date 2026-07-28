/// Código de equipo en tipografía mono.
///
/// **Único punto de uso de la familia `DemoEcaMono`** de todo el proyecto. Está concentrado aquí a
/// propósito: si mañana se cambia de fuente, se cambia en un sitio.
///
/// Por qué se empaqueta una fuente para esto: un código como `URO-LITHO-3000` se teclea a mano
/// cuando el adhesivo del QR está rozado —es literalmente el camino de respaldo de la app— y una
/// fuente mono con cero rasgada y ele con cola es lo que distingue `O` de `0` e `I` de `l`. Antes
/// había cuatro sitios pidiendo `fontFamily: 'monospace'` sin declarar ninguna fuente, lo que en
/// iOS no garantiza nada.
library;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/theme/design_tokens.dart';

class CodeBadge extends StatelessWidget {
  const CodeBadge(this.code, {super.key, this.tone, this.dense = false});

  final String code;

  /// Color del texto y del borde. Por defecto, el primario del tema.
  final Color? tone;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final color = tone ?? Theme.of(context).colorScheme.primary;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: dense ? AppSpacing.xs + 2 : AppSpacing.sm,
        vertical: dense ? 1 : 3,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: AppRadii.badge,
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Text(
        code,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontFamily: AppTheme.monoFamily,
          fontSize: dense ? 11 : 12.5,
          fontWeight: FontWeight.w500,
          color: color,
          letterSpacing: 0.2,
          height: 1.3,
        ),
      ),
    );
  }
}
