/// Especialidad médica: etiqueta, icono y color.
///
/// Existe porque el mapa de etiquetas vivía **privado** dentro de `CatalogScreen`, y esa es
/// exactamente la causa de que la ficha del equipo pintase el slug crudo `urologia` mientras el
/// catálogo, dos pantallas antes, ya mostraba "Urology". Un dato de dominio compartido no puede
/// vivir en la capa de presentación de una feature.
///
/// El icono y el color por especialidad son también lo que evita que todas las tarjetas del catálogo
/// se vean idénticas. `assets/images/` está vacío y no hay portadas de equipo, así que sin esto la
/// única diferencia entre dos tarjetas sería el texto.
library;

import 'package:flutter/material.dart';

@immutable
class SpecialtyStyle {
  const SpecialtyStyle({required this.slug, required this.label, required this.icon});

  final String slug;
  final String label;
  final IconData icon;

  static const SpecialtyStyle _other = SpecialtyStyle(
    slug: 'otro',
    label: 'Other',
    icon: Icons.medical_services_outlined,
  );

  /// Los slugs son los del enum `Specialty` del backend y no se traducen: son identificadores.
  static const Map<String, SpecialtyStyle> _bySlug = {
    'urologia': SpecialtyStyle(
      slug: 'urologia',
      label: 'Urology',
      icon: Icons.water_drop_outlined,
    ),
    'trauma': SpecialtyStyle(
      slug: 'trauma',
      label: 'Trauma',
      icon: Icons.healing_outlined,
    ),
    'cardiologia': SpecialtyStyle(
      slug: 'cardiologia',
      label: 'Cardiology',
      icon: Icons.favorite_outline,
    ),
    'neurocirugia': SpecialtyStyle(
      slug: 'neurocirugia',
      label: 'Neurosurgery',
      icon: Icons.psychology_outlined,
    ),
    'otro': _other,
  };

  /// Nunca lanza: el backend puede añadir una especialidad al enum sin que la app se recompile, y
  /// un `!` aquí sería un crash con datos perfectamente válidos.
  static SpecialtyStyle resolve(String? slug) => _bySlug[slug] ?? _other;

  static String labelOf(String? slug) => resolve(slug).label;

  static Iterable<SpecialtyStyle> get all => _bySlug.values;

  /// Compara la especialidad de texto libre del usuario (`AppUser.specialty`, p. ej. "Urology")
  /// con el slug de una máquina. Se normaliza contra la etiqueta, no contra el slug, porque el
  /// campo del usuario lo rellena una persona y no un enum.
  static bool matchesUserSpecialty(String? userSpecialty, String? machineSlug) {
    if (userSpecialty == null || userSpecialty.trim().isEmpty) {
      return false;
    }
    final normalised = userSpecialty.trim().toLowerCase();
    final style = resolve(machineSlug);
    return normalised == style.label.toLowerCase() || normalised == style.slug;
  }
}
