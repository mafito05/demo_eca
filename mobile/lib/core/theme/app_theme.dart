/// Tema de la app: Material 3 en claro y oscuro.
///
/// Antes había cuatro component themes personalizados y dos estilos de texto; el resto era el
/// valor por defecto de Material. Eso significaba, en la práctica, que la app no tenía jerarquía
/// tipográfica y que varios controles se veían desalineados entre sí.
///
/// Varias decisiones de aquí **corrigen defectos**, no son estética:
///
/// - `inputDecorationTheme` tenía `borderSide: none` en todos los estados, así que un campo
///   enfocado no se distinguía de uno inactivo.
/// - `chipTheme` con `showCheckmark: false`: al seleccionar un `FilterChip` aparecía el check, le
///   añadía ancho y desplazaba toda la fila de filtros.
/// - `cardTheme` con color explícito por brightness: en oscuro, `elevation 0` + `surface` + borde
///   `outlineVariant` dejaba las tarjetas casi invisibles.
/// - `snackBarTheme` flotante: los avisos salían pegados al borde inferior, **detrás** de la barra
///   de navegación y bajo el FAB.
/// - `progressIndicatorTheme` con `borderRadius`: elimina los `ClipRRect(999)` manuales que había
///   repartidos por tres pantallas.
/// - `outlinedButtonTheme` y `textButtonTheme`: solo `FilledButton` estaba tematizado, así que en
///   las pantallas de error un outlined de 36 de alto quedaba pegado a un filled de 48.
///
/// Escala tipográfica: un paso por encima de lo que propone Material 3 (que pone `bodyMedium` en 14
/// y `bodySmall` en 12), con suelo de 13 px salvo eyebrows en mayúsculas. La app se lee **de pie a
/// un brazo de distancia**. Y los títulos van en peso 600 en lugar de 500 porque con reflejo de luz
/// sobre el cristal se pierde antes el contraste de trazo que el de tamaño.
///
/// Fuente: Roboto para la interfaz (0 bytes, y la escala de M3 está calibrada sobre ella) y
/// **JetBrains Mono empaquetada** solo para los códigos de equipo. Eso corrige un defecto real:
/// había cuatro sitios pidiendo `fontFamily: 'monospace'` sin declarar ninguna fuente, lo que en
/// Android resuelve por casualidad del sistema y en iOS cae en silencio a la fuente por defecto. Y
/// un código de equipo necesita distinguir O/0 e I/1/l, porque el técnico lo teclea a mano cuando
/// el adhesivo del QR está rozado.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_theme_extensions.dart';
import 'design_tokens.dart';

abstract final class AppTheme {
  /// Azul profundo corporativo. Registro de software hospitalario, no de app de consumo.
  static const Color _seed = Color(0xFF1E40AF);

  /// Familia mono empaquetada. Único punto de uso: el widget `CodeBadge`.
  static const String monoFamily = 'DemoEcaMono';

  static ThemeData light() => _base(Brightness.light);
  static ThemeData dark() => _base(Brightness.dark);

  static ThemeData _base(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(seedColor: _seed, brightness: brightness);
    final isDark = brightness == Brightness.dark;
    final text = _textTheme();

    return ThemeData(
      colorScheme: scheme,
      brightness: brightness,
      scaffoldBackgroundColor: scheme.surface,
      textTheme: text,
      // Explícito para que un plegable o Android en escritorio no compacte los objetivos táctiles
      // que se han dimensionado a propósito para usarse con guantes.
      visualDensity: VisualDensity.standard,

      extensions: <ThemeExtension<dynamic>>[
        SpecialtyPalette.of(brightness),
        isDark ? AppSemanticColors.dark : AppSemanticColors.light,
      ],

      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        // Bajo scroll cambia de superficie en lugar de proyectar sombra: en oscuro una sombra no se
        // ve y la barra se fundiría con el contenido.
        scrolledUnderElevation: 0,
        shadowColor: Colors.transparent,
        centerTitle: false,
        // Color EXPLÍCITO, obligatorio: si `appBarTheme.titleTextStyle` existe, Flutter ya no
        // aplica el `copyWith(color: foregroundColor)` de los defaults (app_bar.dart), y un
        // TextStyle con color null cae al blanco del engine — título invisible en modo claro.
        // El merge de Typography que pone color solo alcanza a ThemeData.textTheme, no a los
        // component themes (D-051).
        titleTextStyle: text.titleLarge?.copyWith(color: scheme.onSurface),
        iconTheme: IconThemeData(color: scheme.onSurface, size: 24),
        actionsIconTheme: IconThemeData(color: scheme.onSurfaceVariant, size: 24),
        // Sin esto los iconos de la barra de estado del sistema pueden quedar blanco sobre blanco.
        systemOverlayStyle: isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      ),

      cardTheme: CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        // En claro, tarjeta blanca sobre fondo hueso. En oscuro hay que subir un nivel de
        // superficie o la tarjeta desaparece contra el fondo.
        color: isDark ? scheme.surfaceContainer : scheme.surfaceContainerLowest,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadii.card,
          side: BorderSide(
            color: isDark ? scheme.outlineVariant.withValues(alpha: 0.5) : scheme.outlineVariant,
          ),
        ),
      ),

      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(AppSizes.buttonHeight),
          shape: const RoundedRectangleBorder(borderRadius: AppRadii.button),
          textStyle: text.labelLarge,
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(AppSizes.buttonHeight),
          shape: const RoundedRectangleBorder(borderRadius: AppRadii.button),
          textStyle: text.labelLarge,
          side: BorderSide(color: scheme.outline),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          minimumSize: const Size(64, AppSizes.minTouch),
          shape: const RoundedRectangleBorder(borderRadius: AppRadii.button),
          textStyle: text.labelLarge,
        ),
      ),

      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(minimumSize: const Size.square(AppSizes.minTouch)),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        // `surfaceContainerHighest` en oscuro queda casi negro y el campo desaparece.
        fillColor: isDark ? scheme.surfaceContainerHigh : scheme.surfaceContainerHighest,
        contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: 14),
        border: const OutlineInputBorder(
          borderRadius: AppRadii.field,
          borderSide: BorderSide.none,
        ),
        enabledBorder: const OutlineInputBorder(
          borderRadius: AppRadii.field,
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadii.field,
          borderSide: BorderSide(color: scheme.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: AppRadii.field,
          borderSide: BorderSide(color: scheme.error, width: 1.5),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: AppRadii.field,
          borderSide: BorderSide(color: scheme.error, width: 2),
        ),
        hintStyle: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
        labelStyle: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
      ),

      navigationBarTheme: NavigationBarThemeData(
        height: AppSizes.navBarHeight,
        backgroundColor: scheme.surfaceContainer,
        surfaceTintColor: Colors.transparent,
        indicatorColor: scheme.secondaryContainer,
        indicatorShape: const RoundedRectangleBorder(borderRadius: AppRadii.card),
        elevation: 0,
        // Etiquetas siempre visibles: con prisa y con guantes no se adivinan iconos.
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        labelTextStyle: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? text.labelMedium?.copyWith(color: scheme.onSurface)
              : text.labelMedium?.copyWith(color: scheme.onSurfaceVariant),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) => IconThemeData(
            size: 24,
            color: states.contains(WidgetState.selected)
                ? scheme.onSecondaryContainer
                : scheme.onSurfaceVariant,
          ),
        ),
      ),

      chipTheme: ChipThemeData(
        shape: const StadiumBorder(),
        // Quitar el checkmark corrige un salto real: al seleccionar un FilterChip, el check le
        // añadía ancho y desplazaba toda la fila horizontal de filtros.
        showCheckmark: false,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: AppSpacing.sm),
        side: BorderSide(color: scheme.outlineVariant),
        backgroundColor: scheme.surface,
        selectedColor: scheme.secondaryContainer,
        // Con color explícito por lo mismo que el AppBar (D-051): el labelStyle del theme
        // descarta el default M3 que sí lo tenía, y el copyWith(color: null) de Chip lo respeta.
        labelStyle: text.labelMedium?.copyWith(color: scheme.onSurfaceVariant),
        secondaryLabelStyle: text.labelMedium?.copyWith(color: scheme.onSurfaceVariant),
      ),

      listTileTheme: ListTileThemeData(
        minVerticalPadding: AppSpacing.md,
        shape: const RoundedRectangleBorder(borderRadius: AppRadii.field),
        titleTextStyle: text.titleMedium,
        subtitleTextStyle: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
        iconColor: scheme.onSurfaceVariant,
      ),

      dialogTheme: DialogThemeData(
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(AppRadii.xl)),
        ),
        backgroundColor: isDark ? scheme.surfaceContainerHigh : scheme.surface,
        titleTextStyle: text.headlineSmall?.copyWith(color: scheme.onSurface),
        contentTextStyle: text.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
        insetPadding: const EdgeInsets.all(AppSpacing.xxl),
        actionsPadding: const EdgeInsets.fromLTRB(
          AppSpacing.lg,
          0,
          AppSpacing.lg,
          AppSpacing.md,
        ),
      ),

      snackBarTheme: SnackBarThemeData(
        // Flotante: pegado al borde quedaba detrás de la NavigationBar y bajo el FAB.
        behavior: SnackBarBehavior.floating,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(AppRadii.md)),
        ),
        insetPadding: const EdgeInsets.all(AppSpacing.lg),
        backgroundColor: scheme.inverseSurface,
        contentTextStyle: text.bodyMedium?.copyWith(color: scheme.onInverseSurface),
        actionTextColor: scheme.inversePrimary,
        showCloseIcon: true,
        closeIconColor: scheme.onInverseSurface,
      ),

      bottomSheetTheme: BottomSheetThemeData(
        shape: const RoundedRectangleBorder(borderRadius: AppRadii.sheet),
        backgroundColor: isDark ? scheme.surfaceContainerHigh : scheme.surfaceContainerLow,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        constraints: const BoxConstraints(maxWidth: 560),
      ),

      dividerTheme: DividerThemeData(color: scheme.outlineVariant, thickness: 1, space: 1),

      progressIndicatorTheme: ProgressIndicatorThemeData(
        linearMinHeight: 8,
        linearTrackColor: scheme.surfaceContainerHighest,
        // Con esto desaparecen los `ClipRRect(999)` manuales de machine_screen y lesson_screen.
        borderRadius: AppRadii.bar,
        strokeWidth: 3,
      ),

      floatingActionButtonTheme: FloatingActionButtonThemeData(
        shape: const RoundedRectangleBorder(borderRadius: AppRadii.card),
        backgroundColor: scheme.primary,
        foregroundColor: scheme.onPrimary,
        extendedTextStyle: text.labelLarge,
        elevation: 3,
      ),

      tooltipTheme: const TooltipThemeData(waitDuration: Duration(milliseconds: 500)),
    );
  }

  /// Escala tipográfica completa.
  ///
  /// Los colores se dejan a `null` para que cada rol herede del `ColorScheme` según dónde se use;
  /// fijarlos aquí rompería el contraste dentro de contenedores tonales.
  static TextTheme _textTheme() => const TextTheme(
    // Solo para el wordmark de la pantalla de entrada.
    displaySmall: TextStyle(
      fontSize: 36,
      height: 1.22,
      fontWeight: FontWeight.w400,
      letterSpacing: -0.25,
    ),

    headlineMedium: TextStyle(
      fontSize: 28,
      height: 1.28,
      fontWeight: FontWeight.w700,
      letterSpacing: -0.25,
    ),
    headlineSmall: TextStyle(fontSize: 24, height: 1.33, fontWeight: FontWeight.w600),

    titleLarge: TextStyle(fontSize: 22, height: 1.27, fontWeight: FontWeight.w600),
    titleMedium: TextStyle(
      fontSize: 17,
      height: 1.41,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.1,
    ),
    titleSmall: TextStyle(
      fontSize: 15,
      height: 1.33,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.1,
    ),

    bodyLarge: TextStyle(fontSize: 17, height: 1.5, letterSpacing: 0.15),
    bodyMedium: TextStyle(fontSize: 15, height: 1.45, letterSpacing: 0.15),
    // 13, no 12: es el suelo de lectura a un brazo de distancia.
    bodySmall: TextStyle(fontSize: 13, height: 1.4, letterSpacing: 0.2),

    labelLarge: TextStyle(
      fontSize: 15,
      height: 1.33,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.1,
    ),
    labelMedium: TextStyle(
      fontSize: 13,
      height: 1.23,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.3,
    ),
    // Único uso de 12: eyebrows en mayúsculas, donde la caja alta compensa el tamaño.
    labelSmall: TextStyle(
      fontSize: 12,
      height: 1.33,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.6,
    ),
  );
}
