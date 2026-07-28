import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../core/providers.dart';
import '../../../core/theme/design_tokens.dart';
import '../../../shared/widgets/status_view.dart';
import 'widgets/scanner_overlay.dart';
import '../qr_token_parser.dart';

/// Módulo de escaneo de QR.
///
/// Está siempre disponible en la barra de navegación: un técnico que recorre varias máquinas
/// escanea una, ve su capacitación, vuelve aquí y escanea la siguiente sin reiniciar nada.
///
/// Escrito a la defensiva porque la cámara es la parte menos fiable de la app:
///
/// 1. **El arranque se hace a mano, con `try/catch`.** El widget de `mobile_scanner` llama a
///    `controller.start()` en su `initState` sin await ni captura de errores, así que un fallo
///    queda como excepción asíncrona no gestionada y la pantalla se queda en negro sin explicar
///    nada. Aquí se arranca explícitamente y el error se muestra.
/// 2. **El ciclo de vida lo gestiona esta pantalla.** El plugin se salta su propio manejo de
///    `didChangeAppLifecycleState` cuando se le pasa un controlador externo (`if
///    (widget.controller != null) return;`), así que sin esto la cámara no se libera al pasar a
///    segundo plano y al volver queda en un estado roto.
/// 3. **La cámara se apaga al cambiar de módulo.** Con `indexedStack` esta rama sigue viva aunque
///    no se vea; sin esto la cámara quedaría encendida mientras el usuario ve un video en otra
///    pestaña, gastando batería y bloqueando el dispositivo para otras apps.
/// 4. **Siempre hay salida sin cámara.** Un emulador sin webcam, o un adhesivo rozado sobre el
///    equipo, no pueden dejar al usuario sin poder abrir su capacitación.
class ScannerScreen extends ConsumerStatefulWidget {
  const ScannerScreen({super.key});

  /// Índice de este módulo en la barra de navegación.
  static const tabIndex = 1;

  @override
  ConsumerState<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends ConsumerState<ScannerScreen> with WidgetsBindingObserver {
  MobileScannerController? _controller;
  String? _cameraError;
  bool _starting = false;

  /// Evita navegar varias veces: la cámara puede emitir el mismo código en ráfaga.
  bool _handled = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // No se arranca aquí: la cámara se enciende cuando el módulo pasa a estar visible, que es lo
    // que decide el `ref.listen` del build.
  }

  Future<void> _stopCamera() async {
    final controller = _controller;
    if (controller == null) {
      return;
    }
    setState(() => _controller = null);
    // Se destruye en lugar de solo parar: `mobile_scanner` deja el dispositivo tomado con `stop()`
    // en algunas plataformas, y un controlador huérfano es justo el estado que provoca que al
    // volver la vista previa salga en negro.
    await controller.dispose();
  }

  Future<void> _startCamera() async {
    if (_controller != null || _starting) {
      return;
    }
    setState(() {
      _starting = true;
      _cameraError = null;
      _handled = false;
    });

    // `autoStart: false` porque el arranque se controla aquí para poder capturar el fallo.
    final controller = MobileScannerController(
      autoStart: false,
      detectionSpeed: DetectionSpeed.noDuplicates,
      formats: const [BarcodeFormat.qrCode],
    );

    try {
      await controller.start();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _starting = false;
      });
    } catch (error) {
      await controller.dispose();
      if (mounted) {
        setState(() {
          _controller = null;
          _starting = false;
          _cameraError = _describe(error);
        });
      }
    }
  }

  /// Traduce el error del plugin a algo accionable.
  static String _describe(Object error) {
    if (error is MobileScannerException) {
      return switch (error.errorCode) {
        MobileScannerErrorCode.permissionDenied =>
          'Camera permission is missing. Grant it in the Android settings for this app.',
        MobileScannerErrorCode.unsupported =>
          'This device does not support code scanning. Enter the code manually.',
        _ => 'The camera could not start. On an emulator this is expected if no webcam is assigned.'
            '\n\n${error.errorDetails?.message ?? error.errorCode.name}',
      };
    }
    return 'The camera could not start.\n\n$error';
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        // Solo si este módulo sigue siendo el visible: volver a la app estando en Equipos no debe
        // encender la cámara.
        if (ref.read(activeTabProvider) == ScannerScreen.tabIndex) {
          _startCamera();
        }
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _stopCamera();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_handled) {
      return;
    }
    for (final barcode in capture.barcodes) {
      final token = extractMachineToken(barcode.rawValue ?? '');
      if (token != null) {
        _handled = true;
        // `go` a la ruta del equipo: al vivir en el módulo Equipos, esto cambia de pestaña y deja
        // al usuario en la capacitación. El escáner queda listo para el siguiente equipo.
        context.go('/m/$token');
        return;
      }
    }
  }

  Future<void> _promptManualEntry() async {
    final controller = TextEditingController();
    final token = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Enter code'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'Code printed below the QR'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('Open'),
          ),
        ],
      ),
    );

    if (!mounted || token == null) {
      return;
    }
    final parsed = extractMachineToken(token);
    if (parsed == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('That code is not in a valid format.')),
      );
      return;
    }
    context.go('/m/$parsed');
  }

  @override
  Widget build(BuildContext context) {
    // Enciende y apaga la cámara según la pestaña activa. `ref.listen` y no `ref.watch` porque esto
    // es un efecto secundario, no un valor a renderizar.
    ref.listen<int>(activeTabProvider, (previous, next) {
      if (next == ScannerScreen.tabIndex) {
        _startCamera();
      } else if (previous == ScannerScreen.tabIndex) {
        _stopCamera();
      }
    });

    // Primera vez que se abre el módulo: `listen` solo dispara con cambios, así que el arranque
    // inicial se cubre aquí.
    if (ref.read(activeTabProvider) == ScannerScreen.tabIndex &&
        _controller == null &&
        !_starting &&
        _cameraError == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _startCamera());
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan equipment'),
        actions: [
          IconButton(
            tooltip: 'Enter code',
            icon: const Icon(Icons.keyboard),
            onPressed: _promptManualEntry,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_starting) {
      return const Center(child: CircularProgressIndicator());
    }

    // Solo se muestra el estado de error si de verdad hubo un fallo. Sin esta distinción, la cámara
    // apagada por estar en otra pestaña se vería como "cámara no disponible", que es mentira.
    if (_cameraError != null) {
      return _CameraUnavailable(
        message: _cameraError!,
        onRetry: _startCamera,
        onManualEntry: _promptManualEntry,
      );
    }

    final controller = _controller;
    if (controller == null) {
      return const Center(child: CircularProgressIndicator());
    }

    return Stack(
      fit: StackFit.expand,
      children: [
        MobileScanner(
          controller: controller,
          onDetect: _onDetect,
          errorBuilder: (context, error, child) => _CameraUnavailable(
            message: _describe(error),
            onRetry: _startCamera,
            onManualEntry: _promptManualEntry,
          ),
        ),

        const ScannerOverlay(),

        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: DecoratedBox(
            decoration: const BoxDecoration(
              color: AppOverlays.cameraScrim,
              borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadii.xxl)),
            ),
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.xl,
                  AppSpacing.xl,
                  AppSpacing.xl,
                  AppSpacing.xl,
                ),
                child: Column(
                  children: [
                    Text(
                      'Point at the QR code on the machine',
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppOverlays.onCamera,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        // El icono refleja el estado REAL de la antorcha. Antes era
                        // `Icons.flashlight_on` fijo, así que parecía encendida siempre y no había
                        // forma de saber si el toque había funcionado.
                        ValueListenableBuilder(
                          valueListenable: controller,
                          builder: (context, state, _) {
                            final on = state.torchState == TorchState.on;
                            return IconButton.filledTonal(
                              tooltip: on ? 'Turn torch off' : 'Turn torch on',
                              onPressed: () => controller.toggleTorch().catchError((_) {}),
                              icon: Icon(
                                on ? Icons.flashlight_on : Icons.flashlight_off,
                              ),
                            );
                          },
                        ),
                        const SizedBox(width: AppSpacing.md),
                        OutlinedButton.icon(
                          onPressed: _promptManualEntry,
                          icon: const Icon(Icons.keyboard_outlined),
                          label: const Text('Enter code'),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppOverlays.onCamera,
                            side: const BorderSide(color: AppOverlays.onCameraDim),
                            // El mínimo de 52 del tema hace la fila demasiado alta sobre la cámara.
                            minimumSize: const Size(0, 44),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Estado sin cámara. No es una pantalla de error muerta: ofrece las dos vías alternativas.
///
/// Este widget era el estado de error más completo del proyecto y sirvió de referencia para diseñar
/// `StatusView`; ahora lo consume, así que la apariencia es la misma que en el resto de la app.
class _CameraUnavailable extends StatelessWidget {
  const _CameraUnavailable({
    required this.message,
    required this.onRetry,
    required this.onManualEntry,
  });

  final String message;
  final VoidCallback onRetry;
  final VoidCallback onManualEntry;

  @override
  Widget build(BuildContext context) => StatusView(
    icon: Icons.no_photography_outlined,
    title: 'Camera unavailable',
    message: message,
    tone: StatusTone.caution,
    actions: [
      AppAction(
        label: 'Enter the code manually',
        icon: Icons.keyboard_outlined,
        onPressed: onManualEntry,
      ),
      AppAction(
        label: 'Retry the camera',
        style: AppActionStyle.outlined,
        onPressed: onRetry,
      ),
      AppAction(
        label: 'View the equipment catalogue',
        style: AppActionStyle.text,
        onPressed: () => context.go('/equipos'),
      ),
    ],
  );
}
