import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';

import '../../../../core/config/app_config.dart';
import '../../../../core/theme/design_tokens.dart';
import '../../../../shared/errors/error_presenter.dart';
import '../../../../shared/widgets/status_view.dart';
import 'player_controls.dart';

/// Reproductor HLS con reporte de progreso.
///
/// Tres decisiones que importan:
///
/// 1. **El JWT del usuario viaja en la query del `master.m3u8`, nunca como cabecera** (D-049).
///    ExoPlayer aplica los `httpHeaders` a todas las peticiones del data source y los reenvía al
///    seguir redirects, así que una cabecera `Authorization` llegaba hasta la URL prefirmada de
///    MinIO y rompía la firma. El backend devuelve el playlist con las URIs ya firmadas mediante
///    un token de reproducción propio.
/// 2. **El heartbeat es periódico, no por tick.** Cada llamada es una escritura en base de
///    datos; una lección de 20 minutos generaría 1200 escrituras con un heartbeat por segundo.
/// 3. **Se reanuda en la última posición** que devolvió el backend, no desde cero.
class HlsPlayerView extends StatefulWidget {
  const HlsPlayerView({
    super.key,
    required this.masterUrl,
    required this.accessToken,
    required this.onProgress,
    this.startAtSeconds = 0,
  });

  final String masterUrl;
  final String accessToken;

  /// Se invoca con la posición actual, cada `AppConfig.progressHeartbeat`.
  final void Function(double positionSeconds) onProgress;
  final double startAtSeconds;

  @override
  State<HlsPlayerView> createState() => _HlsPlayerViewState();
}

class _HlsPlayerViewState extends State<HlsPlayerView> {
  VideoPlayerController? _controller;
  Timer? _heartbeat;
  Timer? _hideTimer;
  Object? _error;
  bool _controlsVisible = true;
  bool _fullscreen = false;

  @override
  void initState() {
    super.initState();
    _initialise();
  }

  Future<void> _initialise() async {
    // El token va en la QUERY del master, nunca como cabecera (D-049). `httpHeaders` de
    // video_player se aplica a TODAS las peticiones del data source de ExoPlayer y se reenvía al
    // seguir redirects — una cabecera `Authorization` acababa llegando al 307 hacia la URL
    // prefirmada de MinIO, que rechaza firma en query + Authorization a la vez, y el video no
    // arrancaba nunca. Las playlists derivadas ya llevan su propio token de reproducción.
    final master = Uri.parse(widget.masterUrl).replace(
      queryParameters: {'access_token': widget.accessToken},
    );
    final controller = VideoPlayerController.networkUrl(
      master,
      videoPlayerOptions: VideoPlayerOptions(allowBackgroundPlayback: false),
    );

    try {
      await controller.initialize();
      if (widget.startAtSeconds > 1) {
        await controller.seekTo(Duration(seconds: widget.startAtSeconds.round()));
      }
      controller.addListener(_onControllerUpdate);

      // Arranca el ciclo de auto-ocultado en cuanto el reproductor está listo.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _showControls();
        }
      });

      _heartbeat = Timer.periodic(AppConfig.progressHeartbeat, (_) {
        final value = controller.value;
        if (value.isPlaying) {
          widget.onProgress(value.position.inMilliseconds / 1000);
        }
      });

      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() => _controller = controller);
    } catch (error) {
      await controller.dispose();
      if (mounted) {
        setState(() => _error = error);
      }
    }
  }

  void _onControllerUpdate() {
    final controller = _controller;
    if (controller == null) {
      return;
    }
    // Al terminar se reporta la posición final: es lo que cruza el umbral de completado sin
    // esperar al siguiente heartbeat.
    if (controller.value.position >= controller.value.duration &&
        !controller.value.isPlaying &&
        controller.value.duration > Duration.zero) {
      widget.onProgress(controller.value.duration.inMilliseconds / 1000);
    }
    if (mounted) {
      setState(() {});
    }
  }

  @override
  void dispose() {
    _heartbeat?.cancel();
    _hideTimer?.cancel();
    final controller = _controller;
    if (controller != null) {
      // Se reporta la posición al salir, para poder reanudar exactamente donde se dejó.
      widget.onProgress(controller.value.position.inMilliseconds / 1000);
      controller.removeListener(_onControllerUpdate);
      controller.dispose();
    }
    super.dispose();
  }

  /// Alterna la visibilidad de los controles y rearma el temporizador de ocultado.
  void _showControls() {
    setState(() => _controlsVisible = true);
    _hideTimer?.cancel();
    // Solo se auto-ocultan si está reproduciendo: en pausa el usuario está mirando la pantalla
    // buscando un control, y hacerlos desaparecer justo entonces es lo contrario de lo que quiere.
    if (_controller?.value.isPlaying ?? false) {
      _hideTimer = Timer(AppDurations.controlsAutoHide, () {
        if (mounted) {
          setState(() => _controlsVisible = false);
        }
      });
    }
  }

  Future<void> _toggleFullscreen() async {
    final controller = _controller;
    if (controller == null) {
      return;
    }

    if (_fullscreen) {
      // El orden importa: primero se restauran las orientaciones y la UI del sistema, después se
      // cierra la ruta. Al revés, el frame de vuelta se pinta todavía en horizontal.
      await SystemChrome.setPreferredOrientations(DeviceOrientation.values);
      await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
      setState(() => _fullscreen = false);
      if (mounted) {
        Navigator.of(context).pop();
      }
      return;
    }

    setState(() => _fullscreen = true);
    await SystemChrome.setPreferredOrientations([
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    // `immersiveSticky` y no `immersive`: con el primero, un roce accidental en el borde no deja
    // las barras del sistema fijas encima del vídeo.
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

    if (!mounted) {
      return;
    }
    // Se empuja una ruta con el MISMO controller: recrear el reproductor perdería la posición y
    // volvería a negociar el playlist firmado.
    await Navigator.of(context).push(
      PageRouteBuilder<void>(
        pageBuilder: (context, _, __) => _FullscreenPlayer(
          controller: controller,
          onExit: _toggleFullscreen,
        ),
        transitionsBuilder: (context, animation, _, child) =>
            FadeTransition(opacity: animation, child: child),
      ),
    );

    // Si el usuario sale con el gesto de retroceso del sistema en lugar del botón, hay que
    // restaurar igualmente: sin esto la app se queda bloqueada en horizontal.
    if (_fullscreen) {
      await SystemChrome.setPreferredOrientations(DeviceOrientation.values);
      await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
      if (mounted) {
        setState(() => _fullscreen = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return AspectRatio(
        aspectRatio: 16 / 9,
        child: ColoredBox(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          child: Center(
            child: StatusView.error(
              title: 'The video could not be played',
              message: friendlyMessage(_error),
              compact: true,
              icon: Icons.videocam_off_outlined,
            ),
          ),
        ),
      );
    }

    final controller = _controller;
    if (controller == null) {
      return const AspectRatio(
        aspectRatio: 16 / 9,
        child: Center(child: CircularProgressIndicator()),
      );
    }

    final value = controller.value;

    return AspectRatio(
      aspectRatio: value.aspectRatio == 0 ? 16 / 9 : value.aspectRatio,
      child: GestureDetector(
        // Un toque alterna los controles. Sin esto no hay forma de recuperarlos tras el
        // auto-ocultado, que es el fallo clásico de un reproductor casero.
        onTap: () => _controlsVisible ? setState(() => _controlsVisible = false) : _showControls(),
        child: Stack(
          fit: StackFit.expand,
          children: [
            ColoredBox(color: Colors.black, child: VideoPlayer(controller)),
            PlayerControls(
              controller: controller,
              visible: _controlsVisible || !value.isPlaying,
              onToggleFullscreen: _toggleFullscreen,
            ),
          ],
        ),
      ),
    );
  }
}

/// Ruta de pantalla completa. Reutiliza el controller del reproductor incrustado.
class _FullscreenPlayer extends StatefulWidget {
  const _FullscreenPlayer({required this.controller, required this.onExit});

  final VideoPlayerController controller;
  final VoidCallback onExit;

  @override
  State<_FullscreenPlayer> createState() => _FullscreenPlayerState();
}

class _FullscreenPlayerState extends State<_FullscreenPlayer> {
  bool _visible = true;
  Timer? _hideTimer;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onUpdate);
    _arm();
  }

  void _onUpdate() {
    if (mounted) {
      setState(() {});
    }
  }

  void _arm() {
    _hideTimer?.cancel();
    if (widget.controller.value.isPlaying) {
      _hideTimer = Timer(AppDurations.controlsAutoHide, () {
        if (mounted) {
          setState(() => _visible = false);
        }
      });
    }
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    widget.controller.removeListener(_onUpdate);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Colors.black,
    body: GestureDetector(
      onTap: () {
        setState(() => _visible = !_visible);
        if (_visible) {
          _arm();
        }
      },
      child: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: AspectRatio(
              aspectRatio: widget.controller.value.aspectRatio == 0
                  ? 16 / 9
                  : widget.controller.value.aspectRatio,
              child: VideoPlayer(widget.controller),
            ),
          ),
          SafeArea(
            child: PlayerControls(
              controller: widget.controller,
              visible: _visible || !widget.controller.value.isPlaying,
              onToggleFullscreen: widget.onExit,
              isFullscreen: true,
            ),
          ),
        ],
      ),
    ),
  );
}
