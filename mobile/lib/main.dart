import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/providers.dart';
import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';

void main() {
  // Todo dentro de la misma zona de errores: así una excepción en cualquier punto acaba en el
  // mismo sitio y se puede mostrar.
  runZonedGuarded(
    () {
      WidgetsFlutterBinding.ensureInitialized();

      // Sustituye la pantalla en blanco (o el rectángulo rojo) por algo legible.
      //
      // Motivo concreto: probando en un emulador, un error no capturado dejaba la app en blanco y
      // el único diagnóstico posible era "no funciona". Con esto, el mensaje y la línea del fallo
      // se ven en el dispositivo y se pueden fotografiar, sin necesidad de tener ADB conectado.
      ErrorWidget.builder = (details) => _FatalErrorScreen(details: details);

      FlutterError.onError = (details) {
        FlutterError.presentError(details);
        _lastError = details.exceptionAsString();
      };

      runApp(const ProviderScope(child: DemoEcaApp()));
    },
    (error, stack) {
      _lastError = '$error';
      debugPrint('Error no capturado: $error\n$stack');
    },
  );
}

String? _lastError;

/// El router se crea en un provider para que pueda leer el estado de sesión y reaccionar a sus
/// cambios sin que cada pantalla compruebe la autenticación por su cuenta.
final routerProvider = Provider<GoRouter>((ref) => createRouter(ref));

class DemoEcaApp extends ConsumerStatefulWidget {
  const DemoEcaApp({super.key});

  @override
  ConsumerState<DemoEcaApp> createState() => _DemoEcaAppState();
}

class _DemoEcaAppState extends ConsumerState<DemoEcaApp> {
  DeepLinkListener? _deepLinks;

  @override
  void initState() {
    super.initState();
    // Los deep links que llegan con la app ya abierta no los atiende GoRouter por su cuenta.
    // Sin este listener, escanear un segundo QR con la app en segundo plano no haría nada — que
    // es justo el caso real de un técnico recorriendo varias máquinas.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _deepLinks = DeepLinkListener(ref.read(routerProvider))..start();
    });
  }

  @override
  void dispose() {
    _deepLinks?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'ECA GEMINI DEMO',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      // El usuario puede forzar claro u oscuro desde el perfil, en lugar de quedar atado al
      // ajuste del sistema: se pasa de una sala técnica iluminada a un quirófano en penumbra.
      themeMode: ref.watch(themeModeProvider),
      routerConfig: ref.watch(routerProvider),
    );
  }
}

/// Pantalla que sustituye al fallo de renderizado.
class _FatalErrorScreen extends StatelessWidget {
  const _FatalErrorScreen({required this.details});

  final FlutterErrorDetails details;

  @override
  Widget build(BuildContext context) {
    // No se usa `Theme.of(context)`: si el error ocurrió construyendo la app, puede no haber
    // MaterialApp por encima todavía.
    return Directionality(
      textDirection: TextDirection.ltr,
      child: ColoredBox(
        color: const Color(0xFF1C1B1F),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'The app hit an error',
                    style:
                        TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Share this screen so it can be diagnosed.',
                    style: TextStyle(color: Colors.white70, fontSize: 13),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    details.exceptionAsString(),
                    style: const TextStyle(
                      color: Color(0xFFFFB4AB),
                      fontSize: 12,
                      fontFamily: 'monospace',
                    ),
                  ),
                  if (kDebugMode && details.stack != null) ...[
                    const SizedBox(height: 16),
                    Text(
                      details.stack.toString().split('\n').take(12).join('\n'),
                      style: const TextStyle(
                        color: Colors.white54,
                        fontSize: 10,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                  if (_lastError != null && _lastError != details.exceptionAsString()) ...[
                    const SizedBox(height: 16),
                    const Text(
                      'Previous error:',
                      style: TextStyle(color: Colors.white70, fontSize: 12),
                    ),
                    Text(
                      _lastError!,
                      style: const TextStyle(
                        color: Colors.white54,
                        fontSize: 10,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
