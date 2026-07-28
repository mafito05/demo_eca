import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Almacenamiento de los tokens JWT.
///
/// `flutter_secure_storage` y no `SharedPreferences`: en Android los prefs son un XML en el
/// directorio de la app, legible en un dispositivo con root o desde una copia de seguridad mal
/// configurada. Aquí van al Keystore (Android) y al Keychain (iOS).
class TokenStorage {
  static const _accessKey = 'demoeca.access';
  static const _refreshKey = 'demoeca.refresh';

  final FlutterSecureStorage _storage;

  TokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  Future<String?> readAccess() => _storage.read(key: _accessKey);

  Future<String?> readRefresh() => _storage.read(key: _refreshKey);

  Future<void> save({required String access, required String refresh}) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
