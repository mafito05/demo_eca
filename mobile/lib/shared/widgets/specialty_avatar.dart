/// Cuadrado redondeado tonal con el icono de la especialidad.
///
/// Es lo que diferencia visualmente las tarjetas del catálogo. Antes todas llevaban el mismo
/// `CircleAvatar` con `Icons.precision_manufacturing_outlined` sobre `primaryContainer`, así que una
/// lista de diez equipos era diez veces el mismo icono y la única diferencia era el texto.
///
/// Cuadrado redondeado y no círculo: un círculo lee como avatar de persona, y esto es un objeto.
library;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme_extensions.dart';
import '../../core/theme/design_tokens.dart';
import '../domain/specialty.dart';

class SpecialtyAvatar extends StatelessWidget {
  const SpecialtyAvatar({required this.specialty, super.key, this.size = AppSizes.specialtyTile});

  final String? specialty;
  final double size;

  @override
  Widget build(BuildContext context) {
    final colors = context.specialties.resolve(specialty);
    final style = SpecialtyStyle.resolve(specialty);

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: colors.container,
        borderRadius: BorderRadius.all(Radius.circular(size * 0.28)),
      ),
      child: Icon(style.icon, size: size * 0.5, color: colors.onContainer),
    );
  }
}
