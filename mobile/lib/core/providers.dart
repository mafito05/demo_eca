import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/agent/data/agent_repository.dart';
import '../features/auth/data/auth_repository.dart';
import '../features/lms/data/lms_repository.dart';
import '../features/machine/data/machine_repository.dart';
import 'network/api_client.dart';
import 'storage/preferences_storage.dart';
import 'storage/token_storage.dart';

/// Grafo de dependencias de la app.
///
/// Todo se declara aquí en lugar de instanciarse en los widgets: así una pantalla puede
/// sustituirse por un doble en tests con `overrideWith`, y no hay varios `Dio` conviviendo con
/// interceptores distintos.

final preferencesStorageProvider = Provider<PreferencesStorage>((ref) => PreferencesStorage());

/// Modo de tema elegido por el usuario.
///
/// Arranca en `system` y restaura la preferencia guardada en un microtask, igual que hace
/// `AuthNotifier` con la sesión: leer del keystore es asíncrono, y bloquear el primer frame
/// esperándolo produce una pantalla en blanco al abrir.
class ThemeModeNotifier extends StateNotifier<ThemeMode> {
  ThemeModeNotifier(this._storage) : super(ThemeMode.system) {
    Future.microtask(_restore);
  }

  final PreferencesStorage _storage;

  Future<void> _restore() async {
    state = await _storage.readThemeMode();
  }

  Future<void> set(ThemeMode mode) async {
    state = mode;
    await _storage.writeThemeMode(mode);
  }
}

final themeModeProvider = StateNotifierProvider<ThemeModeNotifier, ThemeMode>(
  (ref) => ThemeModeNotifier(ref.watch(preferencesStorageProvider)),
);

final tokenStorageProvider = Provider<TokenStorage>((ref) => TokenStorage());

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(
    storage: ref.watch(tokenStorageProvider),
    // Cuando el refresco falla de forma definitiva se limpia la sesión, y el `authProvider`
    // hace que la app vuelva a la pantalla de entrada.
    onSessionExpired: () => ref.read(authProvider.notifier).sessionExpired(),
  );
});

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    client: ref.watch(apiClientProvider),
    storage: ref.watch(tokenStorageProvider),
  ),
);

final machineRepositoryProvider = Provider<MachineRepository>(
  (ref) => MachineRepository(client: ref.watch(apiClientProvider)),
);

final lmsRepositoryProvider = Provider<LmsRepository>(
  (ref) => LmsRepository(client: ref.watch(apiClientProvider)),
);

// =============================================================================
//  Sesión
// =============================================================================
sealed class AuthState {
  const AuthState();
}

class AuthLoading extends AuthState {
  const AuthLoading();
}

class AuthAnonymous extends AuthState {
  const AuthAnonymous({this.error});
  final String? error;
}

class AuthReady extends AuthState {
  const AuthReady(this.user);
  final AppUser user;
}

class AuthNotifier extends Notifier<AuthState> {
  @override
  AuthState build() {
    // Se intenta restaurar la sesión al arrancar; hasta que resuelva, la app muestra el splash.
    Future.microtask(restore);
    return const AuthLoading();
  }

  Future<void> restore() async {
    final user = await ref.read(authRepositoryProvider).me();
    state = user == null ? const AuthAnonymous() : AuthReady(user);
  }

  /// Entrada para la demo. Si el backend tiene el bypass desactivado devuelve 404 y se informa
  /// en lugar de dejar la app en un estado ambiguo.
  Future<void> enterAsDemo() async {
    state = const AuthLoading();
    try {
      final user = await ref.read(authRepositoryProvider).demoLogin();
      state = user == null
          ? const AuthAnonymous(
              error: 'Demo access is disabled on the server.',
            )
          : AuthReady(user);
    } catch (_) {
      state = const AuthAnonymous(
        error: 'Could not reach the server. Check the network and try again.',
      );
    }
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AuthAnonymous();
  }

  void sessionExpired() {
    state = const AuthAnonymous(error: 'Your session expired. Please sign in again.');
  }
}

final authProvider = NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);

// =============================================================================
//  Datos de pantalla
// =============================================================================

/// Catálogo de equipos para la pantalla principal.
/// Preguntas de ejemplo del estado vacío del chat, por contexto de equipo (D-053).
///
/// `family` sobre el id de máquina (o null para el corpus global). Si el backend no responde,
/// el widget cae a las preguntas por defecto empaquetadas — el estado vacío nunca queda vacío.
final agentSuggestionsProvider = FutureProvider.autoDispose
    .family<SuggestedQuestions, String?>(
      (ref, machineModelId) =>
          ref.watch(agentRepositoryProvider).suggestions(machineModelId),
    );

/// Parámetros de runtime del RAG (umbral de distancia, top_k), para pintar la confianza de las
/// fuentes con el MISMO umbral que aplica el backend en lugar de una copia hardcodeada.
final agentSettingsProvider = FutureProvider<AgentRuntimeSettings>(
  (ref) => ref.watch(agentRepositoryProvider).settings(),
);

final agentRepositoryProvider = Provider<AgentRepository>(
  (ref) => AgentRepository(client: ref.watch(apiClientProvider)),
);

final machineCatalogProvider = FutureProvider<List<MachineSummary>>(
  (ref) => ref.watch(machineRepositoryProvider).list(),
);

/// Índice del módulo activo en la barra de navegación.
///
/// Lo publica `MainShell`. El escáner lo vigila para encender la cámara solo cuando su módulo está
/// visible: con `indexedStack` la rama sigue viva aunque no se vea, y dejar la cámara abierta en
/// segundo plano gasta batería y bloquea el dispositivo para otras apps.
final activeTabProvider = StateProvider<int>((ref) => 0);

/// Especialidad seleccionada en el catálogo. Null = todas.
///
/// Vive en un provider y no en el `State` de la pantalla para que el filtro sobreviva a ir a un
/// equipo y volver, que es el recorrido normal cuando alguien explora varias capacitaciones.
final specialtyFilterProvider = StateProvider<String?>((ref) => null);

/// Equipo seleccionado en el módulo ECAHelp. Null = solo corpus global.
///
/// Se recuerda entre visitas a la pestaña: alguien que consulta el asistente sobre un equipo
/// concreto suele volver varias veces, y obligarle a reelegirlo cada vez sería absurdo.
final ecahelpMachineProvider = StateProvider<String?>((ref) => null);

/// Resuelve el token del QR. `family` porque el token viene de la ruta.
final resolveMachineProvider = FutureProvider.family<ScanResult, String>(
  (ref, qrToken) => ref.watch(machineRepositoryProvider).resolve(qrToken),
);

final learningPathProvider = FutureProvider.family<LearningPath, String>(
  (ref, machineModelId) => ref.watch(lmsRepositoryProvider).learningPath(machineModelId),
);

final lessonProvider = FutureProvider.family<LessonDetail, String>(
  (ref, lessonId) => ref.watch(lmsRepositoryProvider).lesson(lessonId),
);

/// Socket del agente, ligado al ciclo de vida del provider.
///
/// `autoDispose` cierra la conexión al cerrarse el chat: dejar un WebSocket abierto mientras el
/// usuario ve un video de 20 minutos gasta batería y ocupa una conexión del servidor para nada.
///
