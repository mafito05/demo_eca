/// Traduce excepciones a frases que un médico o un técnico pueda leer.
///
/// **Es el cambio que más se nota de todo el rediseño.** Hoy la app pinta a pantalla completa
/// cosas como `DioException [connection error]: SocketException: Failed host lookup` en cuatro
/// sitios distintos. Nada dice "esto es un prototipo" más alto que eso, y nada dice "esto es un
/// producto" más rápido que arreglarlo.
///
/// El detalle crudo no se pierde: se anexa **solo en `kDebugMode`**, donde sirve para diagnosticar.
/// En una compilación de release el usuario ve la frase y nada más.
library;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Frase legible para el usuario.
String friendlyMessage(Object? error) {
  final message = _humanise(error);
  if (kDebugMode && error != null) {
    return '$message\n\n$error';
  }
  return message;
}

/// Si el problema es de red y no del servidor.
///
/// Sirve para decidir el icono y, sobre todo, el texto del botón: ante un fallo de red "Reintentar"
/// tiene sentido; ante un 403 no lo tiene y hay que ofrecer otra salida.
bool isOffline(Object? error) {
  if (error is! DioException) {
    return false;
  }
  return const {
    DioExceptionType.connectionError,
    DioExceptionType.connectionTimeout,
    DioExceptionType.sendTimeout,
    DioExceptionType.receiveTimeout,
  }.contains(error.type);
}

String _humanise(Object? error) {
  if (error is DioException) {
    switch (error.type) {
      case DioExceptionType.connectionError:
        return 'No connection to the server. Check that this device is on the same network.';
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
        return 'The server took too long to respond. It may be starting up.';
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return 'The server stopped responding halfway through.';
      case DioExceptionType.badCertificate:
        return 'The server certificate could not be verified.';
      case DioExceptionType.cancel:
        return 'The request was cancelled.';
      case DioExceptionType.badResponse:
        return _fromStatus(error.response?.statusCode);
      case DioExceptionType.unknown:
        return 'Something went wrong while talking to the server.';
    }
  }
  return 'Something went wrong.';
}

String _fromStatus(int? status) {
  switch (status) {
    case 401:
      return 'Your session expired. Sign in again.';
    case 403:
      return 'This account does not have access to that.';
    case 404:
      return 'That is no longer available.';
    case 409:
      return 'That conflicts with something that already exists.';
    case 422:
      return 'The server rejected the request as invalid.';
    case 429:
      return 'Too many requests. Wait a moment and try again.';
    case null:
      return 'The server returned an unexpected response.';
    default:
      if (status >= 500) {
        return 'The server ran into a problem. It is not something you did.';
      }
      return 'The server returned an unexpected response ($status).';
  }
}
