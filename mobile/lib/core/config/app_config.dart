/// Configuración de entorno.
///
/// Los valores se inyectan en tiempo de compilación con `--dart-define`, no se leen de un
/// fichero: un `.env` empaquetado en el APK es legible por cualquiera que lo descomprima, y
/// además obligaría a recompilar igualmente para cambiarlo.
///
///     flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
///
/// El valor por defecto es `10.0.2.2`, que es cómo el emulador de Android alcanza el
/// `localhost` de la máquina anfitriona. En el simulador de iOS sería `localhost`, y en un
/// dispositivo físico la IP de la red local.
library;

class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const String apiPrefix = '/api/v1';

  /// Dominio de los App Links / Universal Links. Debe coincidir con `DEEPLINK_DOMAIN` del
  /// backend: es lo que va codificado en el QR impreso sobre la máquina.
  static const String deeplinkDomain = String.fromEnvironment(
    'DEEPLINK_DOMAIN',
    defaultValue: 'demoeca.example.com',
  );

  /// Esquema propio, usado solo como respaldo en pruebas locales.
  static const String deeplinkScheme = String.fromEnvironment(
    'DEEPLINK_SCHEME',
    defaultValue: 'demoeca',
  );

  static String get apiUrl => '$apiBaseUrl$apiPrefix';

  static String get agentWsUrl {
    final ws = apiBaseUrl.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
    return '$ws$apiPrefix/agent/ws';
  }

  /// Cada cuánto se reporta la posición del reproductor al backend.
  ///
  /// 10 segundos y no cada tick: cada llamada es una escritura en base de datos, y con un
  /// heartbeat por segundo un solo usuario viendo una lección de 20 minutos generaría 1200
  /// escrituras. El progreso no necesita esa resolución.
  static const Duration progressHeartbeat = Duration(seconds: 10);
}
