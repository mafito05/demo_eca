/// Tres puntos animados mientras el agente piensa.
///
/// Sustituye al literal `'Checking the manual…'` que se pintaba como texto. Un texto fijo durante
/// varios segundos no comunica actividad: parece que la respuesta ya llegó y dice eso.
///
/// Lleva `semanticsLabel` porque una animación es invisible para un lector de pantalla, y "el
/// asistente está escribiendo" es información que hace falta para saber si esperar.
library;

import 'package:flutter/material.dart';

import '../../core/theme/design_tokens.dart';

class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key, this.color, this.dotSize = 7});

  final Color? color;
  final double dotSize;

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? Theme.of(context).colorScheme.onSurfaceVariant;

    return Semantics(
      label: 'The assistant is preparing an answer',
      liveRegion: true,
      child: SizedBox(
        height: widget.dotSize * 2.4,
        child: MediaQuery.disableAnimationsOf(context)
            // Sin animaciones, tres puntos estáticos siguen comunicando "hay algo en curso".
            ? Row(mainAxisSize: MainAxisSize.min, children: _staticDots(color))
            : AnimatedBuilder(
                animation: _controller,
                builder: (context, _) => Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (var index = 0; index < 3; index++) ...[
                      if (index > 0) SizedBox(width: widget.dotSize * 0.7),
                      _Dot(
                        size: widget.dotSize,
                        color: color,
                        // Desfase de un tercio de ciclo entre puntos: es lo que produce la onda.
                        opacity: _opacityFor(index),
                      ),
                    ],
                  ],
                ),
              ),
      ),
    );
  }

  double _opacityFor(int index) {
    final phase = (_controller.value + index / 3) % 1;
    // Curva triangular: sube y baja sin salto al cerrar el ciclo.
    final wave = phase < 0.5 ? phase * 2 : (1 - phase) * 2;
    return 0.35 + wave * 0.65;
  }

  List<Widget> _staticDots(Color color) => [
    for (var index = 0; index < 3; index++) ...[
      if (index > 0) SizedBox(width: widget.dotSize * 0.7),
      _Dot(size: widget.dotSize, color: color, opacity: 0.6),
    ],
  ];
}

class _Dot extends StatelessWidget {
  const _Dot({required this.size, required this.color, required this.opacity});

  final double size;
  final Color color;
  final double opacity;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    margin: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
    decoration: BoxDecoration(
      color: color.withValues(alpha: opacity),
      shape: BoxShape.circle,
    ),
  );
}
