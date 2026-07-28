import 'package:demoeca_app/shared/domain/specialty.dart';
import 'package:flutter_test/flutter_test.dart';

/// El caso que motiva estos tests: el mapa de etiquetas vivía **privado** dentro de
/// `CatalogScreen`, y por eso la ficha del equipo pintaba el slug crudo `urologia` mientras el
/// catálogo, dos pantallas antes, ya mostraba "Urology". Ahora es dominio compartido y se prueba.
void main() {
  group('Resolución de especialidad', () {
    test('traduce los slugs del backend', () {
      expect(SpecialtyStyle.labelOf('urologia'), 'Urology');
      expect(SpecialtyStyle.labelOf('trauma'), 'Trauma');
      expect(SpecialtyStyle.labelOf('cardiologia'), 'Cardiology');
      expect(SpecialtyStyle.labelOf('neurocirugia'), 'Neurosurgery');
      expect(SpecialtyStyle.labelOf('otro'), 'Other');
    });

    test('un slug desconocido cae en Other, no lanza', () {
      // El backend puede añadir un valor al enum sin que la app se recompile. Un `!` aquí sería
      // un crash con datos perfectamente válidos.
      expect(SpecialtyStyle.labelOf('radiologia'), 'Other');
      expect(SpecialtyStyle.labelOf(null), 'Other');
      expect(SpecialtyStyle.labelOf(''), 'Other');
    });

    test('cada especialidad tiene su propio icono', () {
      final iconos = SpecialtyStyle.all.map((style) => style.icon).toSet();
      // Si dos especialidades comparten icono, el catálogo pierde la señal visual que justifica
      // todo el sistema de color por especialidad.
      expect(iconos.length, SpecialtyStyle.all.length);
    });
  });

  group('Coincidencia con la especialidad del usuario', () {
    test('compara contra la etiqueta, porque el campo del usuario es texto libre', () {
      // `AppUser.specialty` lo rellena una persona ("Urology"), no un enum ("urologia").
      expect(SpecialtyStyle.matchesUserSpecialty('Urology', 'urologia'), isTrue);
      expect(SpecialtyStyle.matchesUserSpecialty('urology', 'urologia'), isTrue);
      expect(SpecialtyStyle.matchesUserSpecialty('  Urology  ', 'urologia'), isTrue);
    });

    test('acepta también el slug, por si alguien lo escribe así', () {
      expect(SpecialtyStyle.matchesUserSpecialty('urologia', 'urologia'), isTrue);
    });

    test('no coincide con otra especialidad', () {
      expect(SpecialtyStyle.matchesUserSpecialty('Urology', 'trauma'), isFalse);
    });

    test('sin especialidad de usuario no coincide con nada', () {
      // Importante: si un valor vacío coincidiese con todo, el catálogo marcaría todas las
      // secciones como "las tuyas".
      expect(SpecialtyStyle.matchesUserSpecialty(null, 'urologia'), isFalse);
      expect(SpecialtyStyle.matchesUserSpecialty('', 'urologia'), isFalse);
      expect(SpecialtyStyle.matchesUserSpecialty('   ', 'urologia'), isFalse);
    });
  });
}
