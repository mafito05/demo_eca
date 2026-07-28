/// Controles del reproductor, superpuestos sobre el vídeo.
///
/// Los que había eran una fila de iconos **debajo** del vídeo, sin scrim, siempre visibles y sin
/// pantalla completa. Este es el cambio de mayor riesgo del rediseño y también el menos verificable:
/// sin un dispositivo no se puede comprobar el auto-ocultado, el agarre del scrubber con el dedo ni
/// el coste real del degradado sobre una superficie de vídeo. Va en su propio fichero y su propio
/// commit por eso mismo.
///
/// Decisiones concretas:
///
/// - **Degradado, no un color plano**: sobre un fotograma claro un scrim uniforme se ve como una
///   banda pegada; un degradado a transparente no.
/// - **`VideoProgressIndicator` envuelto en 24 de alto**: el widget mide 4-5 px, muy por debajo de
///   lo que un dedo puede agarrar. El envoltorio no cambia el aspecto, solo el área de impacto.
/// - `replay_10` **y** `forward_10`: en un manual técnico se retrocede para repetir un paso y se
///   avanza para saltar la introducción. Solo había el primero.
library;

import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../../../core/theme/design_tokens.dart';
import '../../../../shared/format/formatters.dart';

class PlayerControls extends StatelessWidget {
  const PlayerControls({
    required this.controller,
    required this.visible,
    required this.onToggleFullscreen,
    super.key,
    this.isFullscreen = false,
  });

  final VideoPlayerController controller;
  final bool visible;
  final VoidCallback onToggleFullscreen;
  final bool isFullscreen;

  @override
  Widget build(BuildContext context) {
    final value = controller.value;

    return AnimatedOpacity(
      opacity: visible ? 1 : 0,
      duration: AppDurations.fast,
      // Sin esto, los botones invisibles siguen capturando toques y el gesto de "mostrar
      // controles" no llega nunca al detector de debajo.
      child: IgnorePointer(
        ignoring: !visible,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Degradado inferior: da contraste al texto y a los iconos sobre cualquier fotograma.
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.center,
                  colors: [AppOverlays.videoScrimStrong, AppOverlays.videoScrimNone],
                ),
              ),
              child: SizedBox.expand(),
            ),

            // Play/pausa central, grande: es el control que se busca primero.
            Center(
              child: _RoundButton(
                icon: value.isPlaying ? Icons.pause : Icons.play_arrow,
                size: 56,
                onPressed: () => value.isPlaying ? controller.pause() : controller.play(),
                tooltip: value.isPlaying ? 'Pause' : 'Play',
              ),
            ),

            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: Column(
                children: [
                  // Área de impacto de 24 sobre una barra de 5: es lo que hace agarrable el
                  // scrubber con el dedo.
                  SizedBox(
                    height: 24,
                    child: Center(
                      child: VideoProgressIndicator(
                        controller,
                        allowScrubbing: true,
                        padding: EdgeInsets.zero,
                        colors: const VideoProgressColors(
                          playedColor: AppOverlays.onCamera,
                          bufferedColor: AppOverlays.onCameraDim,
                          backgroundColor: Color(0x40FFFFFF),
                        ),
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.sm,
                      0,
                      AppSpacing.sm,
                      AppSpacing.sm,
                    ),
                    child: Row(
                      children: [
                        _RoundButton(
                          icon: Icons.replay_10,
                          tooltip: 'Back 10 s',
                          onPressed: () =>
                              controller.seekTo(value.position - const Duration(seconds: 10)),
                        ),
                        _RoundButton(
                          icon: Icons.forward_10,
                          tooltip: 'Forward 10 s',
                          onPressed: () =>
                              controller.seekTo(value.position + const Duration(seconds: 10)),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        Text(
                          '${durationLabel(value.position.inSeconds)} / '
                          '${durationLabel(value.duration.inSeconds)}',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppOverlays.onCamera,
                          ),
                        ),
                        const Spacer(),
                        _RoundButton(
                          icon: isFullscreen
                              ? Icons.fullscreen_exit
                              : Icons.fullscreen,
                          tooltip: isFullscreen ? 'Exit full screen' : 'Full screen',
                          onPressed: onToggleFullscreen,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({
    required this.icon,
    required this.onPressed,
    required this.tooltip,
    this.size = 40,
  });

  final IconData icon;
  final VoidCallback onPressed;
  final String tooltip;
  final double size;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: tooltip,
    onPressed: onPressed,
    iconSize: size * 0.55,
    // Colores fijos: el fondo es un fotograma de vídeo, no una superficie del tema.
    color: AppOverlays.onCamera,
    style: IconButton.styleFrom(
      backgroundColor: const Color(0x59000000),
      minimumSize: Size.square(size),
      fixedSize: Size.square(size),
    ),
    icon: Icon(icon),
  );
}
