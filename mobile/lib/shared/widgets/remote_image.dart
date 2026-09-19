/// Imagen de red con respaldo, carga y fundido.
///
/// Es el primer sitio del proyecto que carga una imagen remota: hasta ahora toda la identidad
/// visual eran `CustomPainter`, iconos y degradados por especialidad.
///
/// **Sin `cached_network_image`**, y no por ahorrar una línea en el pubspec: arrastra
/// `flutter_cache_manager`, `path_provider` y `sqflite` —plugins nativos— para cachear en disco
/// un catálogo de una decena de fotos servidas con cabeceras de caché. El `ImageCache` en memoria
/// de Flutter ya cubre el desplazamiento por el catálogo y la ida y vuelta a la ficha. Y esos
/// plugins meterían `MethodChannel` en unos tests que hoy son `flutter_test` puro. El día que se
/// pida modo sin conexión, esa sí será una decisión con su propia entrada en DECISIONS.
library;

import 'package:flutter/material.dart';

import '../../core/theme/design_tokens.dart';
import 'skeleton.dart';

class RemoteImage extends StatelessWidget {
  const RemoteImage({
    required this.url,
    required this.fallback,
    super.key,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.borderRadius,
    this.semanticLabel,
    this.imageProvider,
  });

  /// URL absoluta. Null o vacía pinta directamente el respaldo, que es el caso de todo equipo
  /// al que aún no le han subido foto.
  final String? url;

  /// Qué pintar cuando no hay imagen o falla su carga. En el catálogo es `SpecialtyAvatar`, que
  /// mantiene la identidad por especialidad que el catálogo ya tenía.
  final Widget fallback;

  final double? width;
  final double? height;
  final BoxFit fit;
  final BorderRadius? borderRadius;
  final String? semanticLabel;

  /// Proveedor explícito, para probar este widget en aislamiento.
  final ImageProvider? imageProvider;

  /// Fábrica del proveedor, sustituible en tests.
  ///
  /// Tiene que ser estática y no un parámetro: `MachineCard` y `MachineHeader` construyen el
  /// `RemoteImage` por dentro, así que un parámetro nunca llegaría hasta ellos desde un test.
  /// El helper `useFakeImages()` de `test/support/` la reemplaza por un `MemoryImage` y la
  /// restaura con `addTearDown` — sin restaurar, contaminaría el resto del fichero de tests.
  static ImageProvider Function(String url) providerFactory = _networkProvider;

  static ImageProvider _networkProvider(String url) => NetworkImage(url);

  static void resetProviderFactory() => providerFactory = _networkProvider;

  @override
  Widget build(BuildContext context) {
    final source = url;
    if (imageProvider == null && (source == null || source.isEmpty)) {
      return fallback;
    }

    final image = Image(
      image: imageProvider ?? providerFactory(source!),
      width: width,
      height: height,
      fit: fit,
      semanticLabel: semanticLabel,
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return SkeletonBox(
          width: width,
          height: height ?? AppSizes.machineThumb,
          borderRadius: borderRadius ?? AppRadii.card,
        );
      },
      // Cubre 404, DNS caído y un bucket que dejó de ser público: en todos esos casos es mejor
      // el icono de la especialidad que un hueco roto.
      errorBuilder: (context, error, stack) => fallback,
      frameBuilder: (context, child, frame, wasSynchronouslyLoaded) {
        // Si viene del ImageCache no debe reaparecer con fundido: al desplazarse por el catálogo
        // se vería parpadear cada tarjeta que vuelve a entrar en pantalla.
        if (wasSynchronouslyLoaded) return child;
        return AnimatedOpacity(
          opacity: frame == null ? 0 : 1,
          duration: AppDurations.normal,
          curve: AppCurves.standard,
          child: child,
        );
      },
    );

    if (borderRadius == null) return image;
    return ClipRRect(borderRadius: borderRadius!, child: image);
  }
}
