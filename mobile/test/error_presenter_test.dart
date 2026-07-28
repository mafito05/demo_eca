import 'package:demoeca_app/shared/errors/error_presenter.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

/// Lo que se prueba: que la app **no** pinte excepciones de Dio a pantalla completa.
///
/// Antes había cuatro pantallas mostrando literalmente
/// `DioException [connection error]: ... SocketException: Failed host lookup`, que es lo que más
/// hacía parecer un prototipo lo que ya funcionaba.
///
/// Nota: en modo test `kDebugMode` es true, así que `friendlyMessage` **anexa** el error crudo. Por
/// eso se comprueba con `contains` y no con igualdad: lo que importa es que la frase legible esté
/// delante.
void main() {
  final request = RequestOptions(path: '/machines');

  DioException dio(DioExceptionType type, {int? status}) => DioException(
    requestOptions: request,
    type: type,
    response: status == null
        ? null
        : Response<void>(requestOptions: request, statusCode: status),
  );

  group('Frases legibles', () {
    test('sin red menciona la red, no SocketException', () {
      final message = friendlyMessage(dio(DioExceptionType.connectionError));
      expect(message, contains('No connection to the server'));
      expect(message.split('\n').first, isNot(contains('DioException')));
    });

    test('timeout de conexión sugiere que el servidor está arrancando', () {
      expect(
        friendlyMessage(dio(DioExceptionType.connectionTimeout)),
        contains('took too long'),
      );
    });

    test('401 habla de sesión, no de código de estado', () {
      final message = friendlyMessage(dio(DioExceptionType.badResponse, status: 401));
      expect(message, contains('session expired'));
    });

    test('403 no invita a reintentar: reintentar no lo arregla', () {
      final message = friendlyMessage(dio(DioExceptionType.badResponse, status: 403));
      expect(message, contains('does not have access'));
    });

    test('5xx aclara que no es culpa del usuario', () {
      final message = friendlyMessage(dio(DioExceptionType.badResponse, status: 503));
      expect(message, contains('not something you did'));
    });

    test('un error cualquiera no revienta', () {
      expect(friendlyMessage(Exception('boom')), contains('Something went wrong'));
      expect(friendlyMessage(null), contains('Something went wrong'));
    });
  });

  group('isOffline', () {
    test('true solo para fallos de red', () {
      expect(isOffline(dio(DioExceptionType.connectionError)), isTrue);
      expect(isOffline(dio(DioExceptionType.connectionTimeout)), isTrue);
      expect(isOffline(dio(DioExceptionType.receiveTimeout)), isTrue);
    });

    test('false para respuestas del servidor: el servidor SÍ contestó', () {
      // La distinción decide el icono y el texto del botón: ante un 404 "reintentar" no sirve.
      expect(isOffline(dio(DioExceptionType.badResponse, status: 404)), isFalse);
      expect(isOffline(dio(DioExceptionType.cancel)), isFalse);
      expect(isOffline(Exception('boom')), isFalse);
    });
  });
}
