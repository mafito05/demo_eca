import '../../core/config/app_config.dart';

/// Extrae el token de máquina del contenido de un QR.
///
/// Vive separado de la pantalla porque es lógica pura y es lo que más conviene tener cubierto por
/// tests: si esto falla, el escaneo no lleva a ninguna parte y la demo se cae en el primer paso.
///
/// Acepta tres formas:
///
/// 1. `https://DOMINIO/m/TOKEN` — la URL que codifica el backend y que va impresa en la etiqueta.
/// 2. `demoeca://machine/TOKEN` — el esquema propio, solo para pruebas locales.
/// 3. `TOKEN` pelado — para poder teclearlo a mano cuando el adhesivo está rozado o sucio, algo
///    que en un hospital ocurre.
///
/// Devuelve `null` si no reconoce el formato, en lugar de lanzar: un QR de otra cosa (una etiqueta
/// de inventario, un envase) es un caso esperado, no un error.
String? extractMachineToken(String raw) {
  final value = raw.trim();
  if (value.isEmpty) {
    return null;
  }

  final uri = Uri.tryParse(value);
  if (uri != null) {
    final segments = uri.pathSegments.where((segment) => segment.isNotEmpty).toList();

    // https://DOMINIO/m/TOKEN
    if (segments.length >= 2 && (segments.first == 'm' || segments.first == 'machine')) {
      return _validToken(segments[1]);
    }
    // demoeca://machine/TOKEN  (el host es "machine" y el token el primer segmento)
    if (uri.scheme == AppConfig.deeplinkScheme && uri.host == 'machine' && segments.isNotEmpty) {
      return _validToken(segments.first);
    }
    // demoeca://TOKEN
    if (uri.scheme == AppConfig.deeplinkScheme && uri.host.isNotEmpty && segments.isEmpty) {
      return _validToken(uri.host);
    }
  }

  return _validToken(value);
}

/// El token lo genera `secrets.token_urlsafe(9)` en el backend: base64url, 12 caracteres. Se
/// admite un rango algo más amplio para no romper si esa longitud cambia.
final RegExp _tokenPattern = RegExp(r'^[A-Za-z0-9_-]{8,32}$');

String? _validToken(String candidate) => _tokenPattern.hasMatch(candidate) ? candidate : null;
