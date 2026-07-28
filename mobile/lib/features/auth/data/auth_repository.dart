import 'package:dio/dio.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/token_storage.dart';

class AppUser {
  const AppUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.role,
    this.specialty,
    this.institution,
  });

  final String id;
  final String email;
  final String fullName;
  final String role;
  final String? specialty;
  final String? institution;

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
        id: json['id'] as String,
        email: json['email'] as String,
        fullName: json['full_name'] as String,
        role: json['role'] as String,
        specialty: json['specialty'] as String?,
        institution: json['institution'] as String?,
      );
}

class AuthRepository {
  AuthRepository({required this.client, required this.storage});

  final ApiClient client;
  final TokenStorage storage;

  /// Bypass de la demo: entra sin credenciales para poder escanear el QR directamente.
  ///
  /// Devuelve un token real con el mismo contrato que el login normal, así que el resto de la
  /// app no sabe que hubo bypass. Si el backend tiene el flag desactivado responde 404, y en ese
  /// caso hay que pedir credenciales.
  Future<AppUser?> demoLogin() async {
    final response = await client.dio.post('/auth/demo-login');
    if (response.statusCode != 200) {
      return null;
    }
    await _persist(response.data as Map<String, dynamic>);
    return me();
  }

  Future<AppUser?> login(String email, String password) async {
    final response = await client.dio.post(
      '/auth/login',
      data: {'email': email, 'password': password},
    );
    if (response.statusCode != 200) {
      return null;
    }
    await _persist(response.data as Map<String, dynamic>);
    return me();
  }

  /// Recupera el usuario del token guardado. Devuelve null si no hay sesión utilizable.
  Future<AppUser?> me() async {
    if (await storage.readAccess() == null) {
      return null;
    }
    try {
      final response = await client.dio.get('/auth/me');
      if (response.statusCode != 200) {
        return null;
      }
      return AppUser.fromJson(response.data as Map<String, dynamic>);
    } on DioException {
      return null;
    }
  }

  Future<void> logout() => storage.clear();

  Future<void> _persist(Map<String, dynamic> tokens) => storage.save(
        access: tokens['access_token'] as String,
        refresh: tokens['refresh_token'] as String,
      );
}
