import 'dart:async';

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import '../storage/token_storage.dart';

/// Cliente HTTP con inyección del Bearer y refresco de token.
///
/// El refresco usa un `Completer` compartido: si cinco peticiones fallan a la vez con 401, solo
/// la primera refresca y las otras cuatro esperan su resultado. Sin eso se disparan cinco
/// refrescos concurrentes, cuatro con un token que el backend ya rotó, y el usuario acaba
/// expulsado teniendo sesión válida.
class ApiClient {
  final Dio dio;
  final TokenStorage storage;

  /// Se invoca cuando el refresco falla de forma definitiva: la sesión ya no es recuperable.
  final void Function()? onSessionExpired;

  Completer<String?>? _refreshing;

  ApiClient({required this.storage, this.onSessionExpired})
      : dio = Dio(
          BaseOptions(
            baseUrl: AppConfig.apiUrl,
            connectTimeout: const Duration(seconds: 15),
            receiveTimeout: const Duration(seconds: 30),
            headers: {'Content-Type': 'application/json'},
            // No se lanza excepción por códigos 4xx: cada repositorio decide qué hacer con un
            // 403 (lección bloqueada) o un 404 (QR desconocido), que son respuestas esperadas
            // del dominio y no errores de red.
            validateStatus: (status) => status != null && status < 500,
          ),
        ) {
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          if (!_isPublic(options.path)) {
            final token = await storage.readAccess();
            if (token != null) {
              options.headers['Authorization'] = 'Bearer $token';
            }
          }
          handler.next(options);
        },
        onResponse: (response, handler) async {
          if (response.statusCode != 401 || _isPublic(response.requestOptions.path)) {
            return handler.next(response);
          }

          final fresh = await _refreshToken();
          if (fresh == null) {
            onSessionExpired?.call();
            return handler.next(response);
          }

          // Se reintenta la petición original con el token nuevo.
          try {
            final retry = await dio.fetch(
              response.requestOptions..headers['Authorization'] = 'Bearer $fresh',
            );
            return handler.resolve(retry);
          } on DioException catch (error) {
            return handler.next(error.response ?? response);
          }
        },
      ),
    );
  }

  bool _isPublic(String path) =>
      path.contains('/auth/login') ||
      path.contains('/auth/refresh') ||
      path.contains('/auth/demo-login');

  /// Diagnóstico de conectividad para la pantalla de entrada.
  ///
  /// Existe porque el fallo más probable al probar en un emulador o un teléfono es de red, no de
  /// código: `10.0.2.2` solo funciona en el emulador de Android Studio, la IP del host cambia con
  /// DHCP y el firewall de Windows puede bloquear el puerto. Sin esto, todos esos casos se ven
  /// igual en la app —"no entra"— y hay que adivinar cuál es.
  ///
  /// Devuelve un mensaje ya redactado para mostrar al usuario.
  Future<String> diagnose() async {
    // `const`: `apiBaseUrl` es un `String.fromEnvironment`, resuelto en tiempo de compilación.
    const url = '${AppConfig.apiBaseUrl}/health/ready';
    try {
      final response = await Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 6),
          receiveTimeout: const Duration(seconds: 6),
          validateStatus: (_) => true,
        ),
      ).getUri(Uri.parse(url));

      if (response.statusCode == 200) {
        return 'Connection to $url is working';
      }
      return 'The server responded ${response.statusCode} at $url. '
          'It is reachable, but something is failing inside the backend.';
    } on DioException catch (error) {
      final motivo = switch (error.type) {
        DioExceptionType.connectionTimeout ||
        DioExceptionType.sendTimeout ||
        DioExceptionType.receiveTimeout =>
          'Request timed out. The IP responds but nothing is listening on that port, or a '
              'firewall is in the way.',
        DioExceptionType.connectionError =>
          'Could not establish a connection. Check that the IP is the computer running the '
              'backend and that both are on the same network.',
        _ => error.message ?? 'Unknown network error.',
      };
      return 'No connection to $url\n\n$motivo';
    }
  }

  Future<String?> _refreshToken() {
    // Ya hay un refresco en marcha: se espera su resultado en lugar de lanzar otro.
    final inFlight = _refreshing;
    if (inFlight != null) {
      return inFlight.future;
    }

    final completer = Completer<String?>();
    _refreshing = completer;

    Future<void>(() async {
      try {
        final refresh = await storage.readRefresh();
        if (refresh == null) {
          completer.complete(null);
          return;
        }

        final response = await Dio(BaseOptions(baseUrl: AppConfig.apiUrl)).post(
          '/auth/refresh',
          data: {'refresh_token': refresh},
        );
        final access = response.data['access_token'] as String;
        await storage.save(access: access, refresh: response.data['refresh_token'] as String);
        completer.complete(access);
      } catch (_) {
        await storage.clear();
        completer.complete(null);
      } finally {
        _refreshing = null;
      }
    });

    return completer.future;
  }
}
