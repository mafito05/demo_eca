import 'package:demoeca_app/shared/format/formatters.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('durationLabel', () {
    test('formatea m:ss', () {
      expect(durationLabel(0), '0:00');
      expect(durationLabel(9), '0:09');
      expect(durationLabel(65), '1:05');
      expect(durationLabel(252), '4:12');
    });

    test('añade horas solo cuando hacen falta', () {
      expect(durationLabel(3600), '1:00:00');
      expect(durationLabel(3725), '1:02:05');
    });

    test('un valor ausente o negativo da un marcador, no una excepción', () {
      // El reproductor pide la duración antes de que el controller inicialice, así que este caso
      // ocurre en cada apertura de lección.
      expect(durationLabel(null), '--:--');
      expect(durationLabel(-5), '--:--');
    });

    test('redondea los decimales que llegan del backend', () {
      expect(durationLabel(65.7), '1:06');
    });
  });

  group('minutesLabel', () {
    test('minutos y horas', () {
      expect(minutesLabel(12), '12 min');
      expect(minutesLabel(60), '1 h');
      expect(minutesLabel(95), '1 h 35 min');
    });

    test('cero o nulo devuelve cadena vacía, para poder omitir el widget', () {
      expect(minutesLabel(null), '');
      expect(minutesLabel(0), '');
    });
  });

  group('percentLabel', () {
    test('redondea hacia abajo salvo al llegar al 100', () {
      // Deliberado: anunciar "100%" en algo que está al 99,7 % engaña, y la diferencia importa
      // porque el 100 % es lo que desbloquea el módulo siguiente.
      expect(percentLabel(99.7), '99%');
      expect(percentLabel(100), '100%');
      expect(percentLabel(100.4), '100%');
      expect(percentLabel(0), '0%');
    });

    test('nulo da cadena vacía', () {
      expect(percentLabel(null), '');
    });
  });

  group('completedAtLabel', () {
    test('formatea día y mes', () {
      final iso = DateTime(DateTime.now().year, 7, 26, 12).toIso8601String();
      expect(completedAtLabel(iso), '26 Jul');
    });

    test('añade el año si es de otro año', () {
      expect(completedAtLabel(DateTime(2024, 3, 4, 12).toIso8601String()), '4 Mar 2024');
    });

    test('nulo o basura da cadena vacía, sin lanzar', () {
      expect(completedAtLabel(null), '');
      expect(completedAtLabel(''), '');
      expect(completedAtLabel('no es una fecha'), '');
    });
  });
}
