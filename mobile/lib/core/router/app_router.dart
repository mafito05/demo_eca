import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/agent/presentation/agent_chat_screen.dart';
import '../../features/agent/presentation/ecahelp_screen.dart';
import '../../features/auth/presentation/entry_screen.dart';
import '../../features/lms/presentation/lesson_screen.dart';
import '../../features/machine/presentation/catalog_screen.dart';
import '../../features/machine/presentation/machine_screen.dart';
import '../../features/qr_scanner/presentation/scanner_screen.dart';
import '../../features/qr_scanner/qr_token_parser.dart';
import '../../features/shell/presentation/main_shell.dart';
import '../../shared/widgets/status_view.dart';
import '../providers.dart';

/// Rutas, módulos y deep linking.
///
/// **Estructura.** Dos módulos conviven en una barra de navegación
/// (`StatefulShellRoute.indexedStack`), cada uno con su propio estado y su pila:
///
/// - `Equipos` (`/equipos`) — catálogo completo por especialidad, y el detalle de cada equipo en
///   `/m/:qrToken`. Es el punto de entrada tras iniciar sesión.
/// - `Escanear` (`/escanear`) — el lector de QR, disponible en cualquier momento.
///
/// Escanear es un **atajo, no un requisito**: se puede explorar todo el catálogo y todas las
/// capacitaciones sin pasar por la cámara, y se puede escanear otro equipo cuando haga falta sin
/// perder dónde se estaba.
///
/// **Por qué el detalle del equipo vive dentro del módulo Equipos y con la ruta `/m/:qrToken`
/// absoluta:** ese path es exactamente el de la URL que codifica el QR impreso
/// (`https://DOMINIO/m/TOKEN`). Anidarlo como `/equipos/m/:token` habría invalidado los códigos ya
/// impresos. Al declararlo con path absoluto dentro de la rama, el deep link entra en el módulo
/// correcto y la barra de navegación sigue visible.
///
/// La lección y el chat del agente se abren **fuera** del shell, a pantalla completa: un video y una
/// conversación piden todo el alto de la pantalla.
///
/// `refreshListenable` reacciona a los cambios de sesión: si el token caduca a mitad de una lección,
/// el `redirect` devuelve al usuario a la pantalla de entrada sin que cada pantalla lo compruebe.
GoRouter createRouter(Ref ref) {
  final notifier = _AuthRouterNotifier(ref);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: notifier,
    redirect: (context, state) {
      final auth = ref.read(authProvider);
      final goingToEntry = state.matchedLocation == '/';

      if (auth is AuthLoading) {
        return goingToEntry ? null : '/';
      }
      if (auth is AuthAnonymous) {
        // Se preserva el destino: si alguien escanea el QR sin sesión, tras entrar se le lleva
        // directamente a esa máquina en lugar de dejarlo en la portada.
        if (goingToEntry) {
          return null;
        }
        return '/?redirect=${Uri.encodeComponent(state.uri.toString())}';
      }
      if (goingToEntry) {
        final redirect = state.uri.queryParameters['redirect'];
        // Se aterriza en el catálogo, no en la cámara. Aterrizar en el escáner dejaba la app
        // inservible si este fallaba: la sesión persiste, así que cada relanzamiento volvía al
        // escáner y volvía a fallar (D-033).
        return redirect != null ? Uri.decodeComponent(redirect) : '/equipos';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/', builder: (context, state) => const EntryScreen()),

      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) => MainShell(navigationShell: navigationShell),
        branches: [
          // --- Módulo 1: Equipos --------------------------------------------
          StatefulShellBranch(
            routes: [
              GoRoute(path: '/equipos', builder: (context, state) => const CatalogScreen()),
              GoRoute(
                // Path absoluto a propósito: es el que llevan impresos los QR.
                path: '/m/:qrToken',
                builder: (context, state) =>
                    MachineScreen(qrToken: state.pathParameters['qrToken']!),
              ),
            ],
          ),

          // --- Módulo 2: Escanear -------------------------------------------
          StatefulShellBranch(
            routes: [
              GoRoute(path: '/escanear', builder: (context, state) => const ScannerScreen()),
            ],
          ),

          // --- Módulo 3: ECAHelp (el asistente) -----------------------------
          StatefulShellBranch(
            routes: [
              GoRoute(path: '/ecahelp', builder: (context, state) => const EcaHelpScreen()),
            ],
          ),
        ],
      ),

      // --- Pantalla completa, fuera del shell -----------------------------
      GoRoute(
        path: '/lesson/:lessonId',
        builder: (context, state) => LessonScreen(
          lessonId: state.pathParameters['lessonId']!,
          machineModelId: state.uri.queryParameters['machine'],
        ),
      ),

      GoRoute(
        path: '/agent',
        builder: (context, state) => AgentChatScreen(
          machineModelId: state.uri.queryParameters['machine'],
          machineName: state.uri.queryParameters['name'],
          lessonId: state.uri.queryParameters['lesson'],
        ),
      ),
    ],
    // Quinto y último patrón de error duplicado que pasa a `StatusView`.
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(),
      body: StatusView(
        icon: Icons.link_off,
        title: 'That link did not open',
        message:
            'The address "${state.uri}" does not match any screen. If it came from a QR code, '
            'the code may be from a different system.',
        tone: StatusTone.caution,
        actions: [
          AppAction(
            label: 'Go to the catalogue',
            icon: Icons.medical_services_outlined,
            onPressed: () => context.go('/equipos'),
          ),
          AppAction(
            label: 'Scan a code',
            style: AppActionStyle.outlined,
            onPressed: () => context.go('/escanear'),
          ),
        ],
      ),
    ),
  );
}

/// Puente entre Riverpod y GoRouter: convierte los cambios de `authProvider` en notificaciones que
/// hacen reevaluar el `redirect`.
class _AuthRouterNotifier extends ChangeNotifier {
  _AuthRouterNotifier(Ref ref) {
    ref.listen(authProvider, (_, __) => notifyListeners());
  }
}

/// Escucha los deep links que llegan cuando la app **ya está abierta**.
///
/// GoRouter atiende por su cuenta el enlace que arranca la app en frío, pero no los que llegan
/// después. Sin esto, escanear un segundo QR con la app en segundo plano no haría nada, que es
/// justo el caso real: un técnico recorriendo varias máquinas seguidas.
///
/// Acepta tanto la URL https del QR impreso como el esquema propio `demoeca://machine/TOKEN`, que
/// es el que se usa en pruebas mientras el dominio no sirva `assetlinks.json`.
class DeepLinkListener {
  DeepLinkListener(this._router);

  final GoRouter _router;
  final AppLinks _appLinks = AppLinks();
  StreamSubscription<Uri>? _subscription;

  void start() {
    _subscription = _appLinks.uriLinkStream.listen((uri) {
      // Se reutiliza el mismo parser que el escáner en lugar de repetir la lógica de segmentos:
      // ya cubre la URL https del QR impreso, el esquema propio y el token pelado, y está cubierto
      // por tests. Dos parsers acabarían divergiendo.
      final token = extractMachineToken(uri.toString());
      if (token != null) {
        _router.go('/m/$token');
      }
    });
  }

  void dispose() {
    _subscription?.cancel();
  }
}
