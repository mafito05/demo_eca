/// Extensiones de tema para lo que SÍ depende del brightness: el color.
///
/// Aquí sí es un `ThemeExtension` y no constantes, al contrario que en `design_tokens.dart`. El
/// motivo es simétrico: estos valores cambian entre claro y oscuro, y el `lerp` que exige la
/// interfaz evita un salto brusco al conmutar el tema.
///
/// Resuelve dos huecos concretos de Material 3:
///
/// 1. `ColorScheme` **no tiene** `success` ni `warning`. Hoy el código usa `tertiary` para decir
///    "vídeo procesándose", que es un rol que no significa eso y que cambiaría de color si alguien
///    ajusta la semilla.
/// 2. Sin color por especialidad, todas las tarjetas de equipo se ven idénticas. Es lo que
///    diferencia el catálogo sin necesitar imágenes, que no existen (`assets/images/` está vacío).
library;

import 'package:flutter/material.dart';

/// Terna de colores de una especialidad, derivada y no escrita a mano.
@immutable
class SpecialtyColors {
  const SpecialtyColors({
    required this.container,
    required this.onContainer,
    required this.accent,
  });

  final Color container;
  final Color onContainer;
  final Color accent;

  static SpecialtyColors lerp(SpecialtyColors a, SpecialtyColors b, double t) => SpecialtyColors(
    container: Color.lerp(a.container, b.container, t)!,
    onContainer: Color.lerp(a.onContainer, b.onContainer, t)!,
    accent: Color.lerp(a.accent, b.accent, t)!,
  );
}

/// Paleta por especialidad.
///
/// Los colores se **derivan con `ColorScheme.fromSeed`** en lugar de escribirse a mano. Eso
/// garantiza que el par container/onContainer sigue siendo legible en modo oscuro sin auditar cinco
/// hexadecimales a ojo, que es exactamente el trabajo que Material 3 ya sabe hacer.
@immutable
class SpecialtyPalette extends ThemeExtension<SpecialtyPalette> {
  const SpecialtyPalette({required this.bySlug, required this.fallback});

  final Map<String, SpecialtyColors> bySlug;
  final SpecialtyColors fallback;

  /// Semillas por especialidad. La de urología coincide con el primario del producto porque es la
  /// especialidad del equipo de la demo.
  static const Map<String, Color> seeds = {
    'urologia': Color(0xFF1E40AF),
    'trauma': Color(0xFFB54708),
    'cardiologia': Color(0xFFBE185D),
    'neurocirugia': Color(0xFF6941C6),
    'otro': Color(0xFF475467),
  };

  factory SpecialtyPalette.of(Brightness brightness) {
    SpecialtyColors derive(Color seed) {
      final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: brightness);
      return SpecialtyColors(
        container: scheme.primaryContainer,
        onContainer: scheme.onPrimaryContainer,
        accent: scheme.primary,
      );
    }

    return SpecialtyPalette(
      bySlug: {for (final entry in seeds.entries) entry.key: derive(entry.value)},
      fallback: derive(seeds['otro']!),
    );
  }

  /// Resuelve un slug. El fallback importa: el backend puede añadir una especialidad nueva al
  /// enum sin que la app se recompile, y un `!` aquí sería un crash en producción.
  SpecialtyColors resolve(String? slug) => bySlug[slug] ?? fallback;

  @override
  SpecialtyPalette copyWith({
    Map<String, SpecialtyColors>? bySlug,
    SpecialtyColors? fallback,
  }) => SpecialtyPalette(bySlug: bySlug ?? this.bySlug, fallback: fallback ?? this.fallback);

  @override
  SpecialtyPalette lerp(ThemeExtension<SpecialtyPalette>? other, double t) {
    if (other is! SpecialtyPalette) {
      return this;
    }
    return SpecialtyPalette(
      bySlug: {
        for (final entry in bySlug.entries)
          entry.key: SpecialtyColors.lerp(
            entry.value,
            other.bySlug[entry.key] ?? entry.value,
            t,
          ),
      },
      fallback: SpecialtyColors.lerp(fallback, other.fallback, t),
    );
  }
}

/// Colores semánticos que `ColorScheme` no cubre.
@immutable
class AppSemanticColors extends ThemeExtension<AppSemanticColors> {
  const AppSemanticColors({
    required this.success,
    required this.onSuccess,
    required this.successContainer,
    required this.onSuccessContainer,
    required this.warning,
    required this.warningContainer,
    required this.onWarningContainer,
    required this.info,
    required this.infoContainer,
    required this.onInfoContainer,
    required this.processing,
  });

  final Color success;
  final Color onSuccess;
  final Color successContainer;
  final Color onSuccessContainer;
  final Color warning;
  final Color warningContainer;
  final Color onWarningContainer;
  final Color info;
  final Color infoContainer;
  final Color onInfoContainer;

  /// Estado "trabajo asíncrono en curso" (vídeo transcodificándose, documento indexándose).
  final Color processing;

  static const AppSemanticColors light = AppSemanticColors(
    success: Color(0xFF15803D),
    onSuccess: Color(0xFFFFFFFF),
    successContainer: Color(0xFFDCFCE7),
    onSuccessContainer: Color(0xFF14532D),
    warning: Color(0xFFA16207),
    warningContainer: Color(0xFFFEF3C7),
    onWarningContainer: Color(0xFF713F12),
    info: Color(0xFF0E7490),
    infoContainer: Color(0xFFCFFAFE),
    onInfoContainer: Color(0xFF164E63),
    processing: Color(0xFF0891B2),
  );

  static const AppSemanticColors dark = AppSemanticColors(
    success: Color(0xFF4ADE80),
    onSuccess: Color(0xFF052E16),
    successContainer: Color(0xFF14532D),
    onSuccessContainer: Color(0xFFBBF7D0),
    warning: Color(0xFFFBBF24),
    warningContainer: Color(0xFF78350F),
    onWarningContainer: Color(0xFFFDE68A),
    info: Color(0xFF22D3EE),
    infoContainer: Color(0xFF164E63),
    onInfoContainer: Color(0xFFA5F3FC),
    processing: Color(0xFF22D3EE),
  );

  @override
  AppSemanticColors copyWith({
    Color? success,
    Color? onSuccess,
    Color? successContainer,
    Color? onSuccessContainer,
    Color? warning,
    Color? warningContainer,
    Color? onWarningContainer,
    Color? info,
    Color? infoContainer,
    Color? onInfoContainer,
    Color? processing,
  }) => AppSemanticColors(
    success: success ?? this.success,
    onSuccess: onSuccess ?? this.onSuccess,
    successContainer: successContainer ?? this.successContainer,
    onSuccessContainer: onSuccessContainer ?? this.onSuccessContainer,
    warning: warning ?? this.warning,
    warningContainer: warningContainer ?? this.warningContainer,
    onWarningContainer: onWarningContainer ?? this.onWarningContainer,
    info: info ?? this.info,
    infoContainer: infoContainer ?? this.infoContainer,
    onInfoContainer: onInfoContainer ?? this.onInfoContainer,
    processing: processing ?? this.processing,
  );

  @override
  AppSemanticColors lerp(ThemeExtension<AppSemanticColors>? other, double t) {
    if (other is! AppSemanticColors) {
      return this;
    }
    return AppSemanticColors(
      success: Color.lerp(success, other.success, t)!,
      onSuccess: Color.lerp(onSuccess, other.onSuccess, t)!,
      successContainer: Color.lerp(successContainer, other.successContainer, t)!,
      onSuccessContainer: Color.lerp(onSuccessContainer, other.onSuccessContainer, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      warningContainer: Color.lerp(warningContainer, other.warningContainer, t)!,
      onWarningContainer: Color.lerp(onWarningContainer, other.onWarningContainer, t)!,
      info: Color.lerp(info, other.info, t)!,
      infoContainer: Color.lerp(infoContainer, other.infoContainer, t)!,
      onInfoContainer: Color.lerp(onInfoContainer, other.onInfoContainer, t)!,
      processing: Color.lerp(processing, other.processing, t)!,
    );
  }
}

/// Acceso cómodo y **a prueba de contexto sin tema**.
///
/// `Theme.of(context).extension<T>()` devuelve nullable. Resolverlo con `!` compila, pero crashea
/// en cuanto un widget se pinta fuera de un `MaterialApp` con estas extensiones — que es justo lo
/// que hace un widget test mal montado. De ahí el fallback en lugar del `!`.
extension AppThemeX on BuildContext {
  AppSemanticColors get semantic =>
      Theme.of(this).extension<AppSemanticColors>() ??
      (Theme.of(this).brightness == Brightness.dark
          ? AppSemanticColors.dark
          : AppSemanticColors.light);

  SpecialtyPalette get specialties =>
      Theme.of(this).extension<SpecialtyPalette>() ??
      SpecialtyPalette.of(Theme.of(this).brightness);
}
