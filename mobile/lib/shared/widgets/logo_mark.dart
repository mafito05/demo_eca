/// Logotipo dibujado en código.
///
/// `assets/images/` está vacío y no hay identidad gráfica del cliente todavía, así que esto es lo
/// que hay: un cuadrado redondeado con el símbolo del QR y un halo suave detrás. Sigue siendo mejor
/// que el `Icon(Icons.qr_code_2, size: 72)` suelto que había, que se leía como un icono de sistema y
/// no como una marca.
///
/// El día que el cliente entregue su logo, se sustituye el contenido de este widget y no hay que
/// tocar ninguna pantalla.
library;

import 'package:flutter/material.dart';

class LogoMark extends StatelessWidget {
  const LogoMark({super.key, this.size = 88});

  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return SizedBox(
      width: size * 1.9,
      height: size * 1.9,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Halo radial: da profundidad sin necesitar una sombra, que en oscuro no se vería.
          DecoratedBox(
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  scheme.primary.withValues(alpha: 0.16),
                  scheme.primary.withValues(alpha: 0),
                ],
              ),
            ),
            child: SizedBox(width: size * 1.9, height: size * 1.9),
          ),
          Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: scheme.primary,
              borderRadius: BorderRadius.all(Radius.circular(size * 0.26)),
            ),
            child: Icon(Icons.qr_code_2_rounded, size: size * 0.56, color: scheme.onPrimary),
          ),
        ],
      ),
    );
  }
}
