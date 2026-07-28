/// Preferencias de interfaz que sobreviven al cierre de la app.
///
/// Reutiliza el `FlutterSecureStorage` que ya monta `TokenStorage` en lugar de añadir
/// `shared_preferences`. El modo de tema no es un secreto y el almacenamiento seguro es más lento
/// que el normal, pero: es **una escritura por interacción explícita del usuario** (pulsar el
/// selector de tema), la dependencia ya está en el proyecto, y añadir otra por un solo valor no se
/// paga.
///
/// Si algún día hay que guardar más preferencias, o alguna que se escriba a menudo,
/// `shared_preferences` es la alternativa correcta y el cambio queda encapsulado aquí.
library;

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class PreferencesStorage {
  PreferencesStorage({FlutterSecureStorage? storage})
    : _storage =
          storage ??
          const FlutterSecureStorage(
            aOptions: AndroidOptions(encryptedSharedPreferences: true),
          );

  final FlutterSecureStorage _storage;

  static const _themeKey = 'demoeca.theme_mode';

  Future<ThemeMode> readThemeMode() async {
    try {
      return switch (await _storage.read(key: _themeKey)) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
    } catch (_) {
      // Un keystore corrupto o inaccesible no debe impedir que la app arranque: se cae al
      // comportamiento por defecto, que es seguir al sistema.
      return ThemeMode.system;
    }
  }

  Future<void> writeThemeMode(ThemeMode mode) async {
    try {
      await _storage.write(key: _themeKey, value: mode.name);
    } catch (_) {
      // El tema no persiste, pero la sesión actual sigue respetando la elección.
    }
  }
}
