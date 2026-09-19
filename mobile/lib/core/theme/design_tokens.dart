/// Tokens de diseño de la app.
///
/// **Constantes `static const`, no un `ThemeExtension`**, y el motivo es concreto:
/// `analysis_options.yaml` activa `prefer_const_constructors`, y con un ThemeExtension el valor
/// viene de un lookup en runtime, así que `EdgeInsets.all(spacing.md)` deja de poder ser const y
/// el lint dispara en cascada por toda la app. Con `static const double md = 12`, la expresión
/// `const EdgeInsets.all(AppSpacing.md)` sigue siendo const.
///
/// Además, espaciado y radios no dependen del brightness, así que el `lerp` gratis de un
/// ThemeExtension no compra nada. El color SÍ depende, y por eso vive en
/// `app_theme_extensions.dart`.
///
/// Contexto de uso que justifica varios de estos números: la app se usa **de pie junto a una
/// máquina**, a veces con guantes de nitrilo y con iluminación que va de quirófano a sala técnica.
/// De ahí los objetivos táctiles generosos y el suelo tipográfico alto.
library;

import 'package:flutter/material.dart';

/// Escala de espaciado, base 4.
abstract final class AppSpacing {
  static const double none = 0;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
  static const double huge = 48;

  /// Margen horizontal de todas las pantallas.
  static const double screenH = 16;

  /// Separación entre secciones del catálogo.
  static const double sectionGap = 24;

  /// Espacio inferior en listas que llevan FAB, para que la última fila no quede tapada.
  static const double fabClearance = 96;

  static const double cardPad = 16;
}

abstract final class AppRadii {
  static const double xs = 8;
  static const double sm = 10;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double pill = 999;

  // Un rectángulo redondeado de 14-16 lee como instrumental técnico; la pastilla completa de
  // Material 3 lee como app de consumo. Los chips sí van en stadium, porque esa forma ayuda a
  // leer una fila de filtros de un vistazo.
  static const BorderRadius card = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius field = BorderRadius.all(Radius.circular(14));
  static const BorderRadius button = BorderRadius.all(Radius.circular(14));
  static const BorderRadius badge = BorderRadius.all(Radius.circular(xs));
  static const BorderRadius bar = BorderRadius.all(Radius.circular(pill));
  static const BorderRadius sheet = BorderRadius.vertical(top: Radius.circular(xxl));
}

abstract final class AppDurations {
  static const Duration instant = Duration(milliseconds: 100);
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration normal = Duration(milliseconds: 220);
  static const Duration slow = Duration(milliseconds: 320);

  /// Pulso del skeleton. Lento a propósito: un parpadeo rápido cansa.
  static const Duration skeletonPulse = Duration(milliseconds: 1100);

  /// Tiempo hasta ocultar los controles del reproductor.
  static const Duration controlsAutoHide = Duration(seconds: 3);

  static const Duration scrollToEnd = Duration(milliseconds: 200);
}

abstract final class AppCurves {
  static const Curve standard = Curves.easeOutCubic;
  static const Curve emphasized = Curves.easeOutQuint;
  static const Curve decelerate = Curves.easeOut;
}

abstract final class AppSizes {
  /// Suelo absoluto de un objetivo táctil.
  static const double minTouch = 48;

  /// Altura de botón principal. Sube de 48 a 52: los guantes de nitrilo reducen la precisión del
  /// dedo, y este es el botón que se pulsa junto a la máquina.
  static const double buttonHeight = 52;

  static const double listRowMin = 56;
  static const double fieldHeight = 52;

  static const double avatarSm = 36;
  static const double avatarMd = 44;
  static const double avatarLg = 56;

  static const double specialtyTile = 48;

  /// Miniatura del equipo en el catálogo. Mayor que `specialtyTile` porque 48 dp bastan para un
  /// icono pero se quedan cortos para reconocer una fotografía de un equipo médico. A 320 dp
  /// siguen quedando ~150 dp de texto, que es lo que el test de nombres largos ya cubre.
  static const double machineThumb = 56;

  /// Alto del carrusel de la galería en la ficha del equipo.
  static const double galleryStrip = 132;

  static const double statusIcon = 40;
  static const double statusCircle = 96;

  /// Ancho máximo de una columna de contenido centrado (entrada, estados de error).
  static const double maxContentWidth = 480;

  /// Ancho máximo de texto largo. Más de ~70 caracteres por línea se lee peor.
  static const double maxReadWidth = 640;

  /// Ventana de puntería del escáner. Sube de 240: con el móvil a un brazo del adhesivo del QR,
  /// una ventana pequeña obliga a acercarse más de lo necesario.
  static const double scannerWindow = 260;

  static const double navBarHeight = 72;
}

/// Colores fijos sobre superficies que NO son del tema.
///
/// Están aquí, con nombre, en lugar de `Colors.white70` suelto en cada pantalla. Sobre la vista
/// previa de la cámara o sobre un fotograma de vídeo el fondo es imagen del mundo real, así que un
/// blanco o negro fijos son la decisión correcta y no un descuido — pero conviene que se lea como
/// intencionado.
abstract final class AppOverlays {
  /// Oscurecido alrededor de la ventana del escáner.
  static const Color cameraScrim = Color(0x8C000000);

  /// Texto e iconos sobre la cámara.
  static const Color onCamera = Color(0xFFFFFFFF);
  static const Color onCameraDim = Color(0xB3FFFFFF);

  /// Degradado inferior de los controles del reproductor.
  static const Color videoScrimStrong = Color(0xB3000000);
  static const Color videoScrimNone = Color(0x00000000);

  /// Fondo del visor de galería a pantalla completa. Negro fijo y no `surface`: una foto se
  /// juzga mejor sobre negro, y aquí no aplica el tema porque no hay más UI alrededor.
  static const Color mediaBackdrop = Color(0xFF000000);
}
