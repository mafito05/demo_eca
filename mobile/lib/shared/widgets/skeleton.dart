/// Placeholders de carga con pulso.
///
/// **Pulso y no barrido, sin el paquete `shimmer`.** Tres razones: el paquete es un `ShaderMask` con
/// un gradiente animado (~60 líneas que no merecen una dependencia); su barrido blanco por defecto
/// queda mal en oscuro, así que habría que pasarle colores propios de todas formas; y un pulso de
/// `ColorTween` es más barato en GPU que repintar un shader cada frame. En una sala en penumbra, un
/// destello blanco recorriendo la pantalla molesta físicamente.
///
/// **Un solo `AnimationController`** para todo el árbol, propagado por `InheritedWidget`. Sin eso, la
/// lista del catálogo tendría ocho controllers latiendo desincronizados, que es exactamente el
/// aspecto de algo roto.
///
/// Respeta `MediaQuery.disableAnimationsOf`: quien desactivó las animaciones ve un bloque estático.
library;

import 'package:flutter/material.dart';

import '../../core/theme/design_tokens.dart';

/// Raíz del pulso. Envuelve un subárbol de `SkeletonBox`.
class Skeleton extends StatefulWidget {
  const Skeleton({required this.child, super.key});

  final Widget child;

  @override
  State<Skeleton> createState() => _SkeletonState();
}

class _SkeletonState extends State<Skeleton> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: AppDurations.skeletonPulse,
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _SkeletonScope(
    animation: _controller,
    child: widget.child,
  );
}

class _SkeletonScope extends InheritedWidget {
  const _SkeletonScope({required this.animation, required super.child});

  final Animation<double> animation;

  static Animation<double>? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_SkeletonScope>()?.animation;

  @override
  bool updateShouldNotify(_SkeletonScope oldWidget) => animation != oldWidget.animation;
}

/// Bloque gris que late. Sin `Skeleton` padre se pinta plano, sin fallar.
class SkeletonBox extends StatelessWidget {
  const SkeletonBox({
    super.key,
    this.width,
    this.height = 14,
    this.borderRadius = AppRadii.badge,
  });

  final double? width;
  final double height;
  final BorderRadius borderRadius;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final animation = _SkeletonScope.maybeOf(context);
    final base = scheme.surfaceContainerHigh;
    final peak = scheme.surfaceContainerHighest;

    if (animation == null || MediaQuery.disableAnimationsOf(context)) {
      return _box(base);
    }

    return AnimatedBuilder(
      animation: animation,
      builder: (context, _) => _box(Color.lerp(base, peak, animation.value)!),
    );
  }

  Widget _box(Color color) => Container(
    width: width,
    height: height,
    decoration: BoxDecoration(color: color, borderRadius: borderRadius),
  );
}

/// Línea de texto simulada. `widthFactor` para que las líneas no queden todas iguales, que es lo
/// que hace que un skeleton parezca una tabla y no un párrafo.
class SkeletonLine extends StatelessWidget {
  const SkeletonLine({super.key, this.widthFactor = 1, this.height = 12});

  final double widthFactor;
  final double height;

  @override
  Widget build(BuildContext context) => FractionallySizedBox(
    alignment: Alignment.centerLeft,
    widthFactor: widthFactor,
    child: SkeletonBox(height: height),
  );
}

class SkeletonCircle extends StatelessWidget {
  const SkeletonCircle({required this.size, super.key});

  final double size;

  @override
  Widget build(BuildContext context) => SkeletonBox(
    width: size,
    height: size,
    borderRadius: BorderRadius.all(Radius.circular(size / 2)),
  );
}
