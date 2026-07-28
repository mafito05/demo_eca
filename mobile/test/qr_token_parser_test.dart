import 'package:demoeca_app/features/qr_scanner/qr_token_parser.dart';
import 'package:flutter_test/flutter_test.dart';

/// Es el primer paso del flujo completo: si el parseo del QR falla, el escaneo no lleva a
/// ninguna parte y la demo se cae antes de empezar.
void main() {
  group('extractMachineToken', () {
    test('acepta la URL https que va impresa en la etiqueta', () {
      expect(
        extractMachineToken('https://demoeca.example.com/m/0hIB_HktchCK'),
        '0hIB_HktchCK',
      );
    });

    test('acepta el esquema propio usado en pruebas locales', () {
      expect(extractMachineToken('demoeca://machine/0hIB_HktchCK'), '0hIB_HktchCK');
    });

    test('acepta un token pelado, para teclearlo si el adhesivo está deteriorado', () {
      expect(extractMachineToken('0hIB_HktchCK'), '0hIB_HktchCK');
    });

    test('tolera espacios y saltos de línea alrededor', () {
      expect(extractMachineToken('  0hIB_HktchCK \n'), '0hIB_HktchCK');
    });

    test('funciona con cualquier dominio: el QR puede llevar el del cliente', () {
      expect(
        extractMachineToken('https://formacion.hospital.example/m/AbCdEf123456'),
        'AbCdEf123456',
      );
    });

    test('rechaza contenido que no es un código de máquina', () {
      expect(extractMachineToken(''), isNull);
      expect(extractMachineToken('   '), isNull);
      expect(extractMachineToken('un texto cualquiera con espacios'), isNull);
      // Demasiado corto para ser un token del backend.
      expect(extractMachineToken('abc'), isNull);
    });

    test('rechaza una URL del dominio correcto pero con otra ruta', () {
      expect(extractMachineToken('https://demoeca.example.com/politica-privacidad'), isNull);
    });

    test('rechaza un token con caracteres fuera de base64url', () {
      expect(extractMachineToken('token/con/barras'), isNull);
      expect(extractMachineToken('token con espacio'), isNull);
    });
  });

  // El listener de deep links usa este mismo parser (no tiene lógica propia), así que estos casos
  // cubren también lo que llega cuando el sistema abre la app desde un enlace.
  group('Formas que llegan por deep link', () {
    test('App Link con query encima', () {
      expect(
        extractMachineToken('https://demoeca.example.com/m/0hIB_HktchCK?utm_source=qr'),
        '0hIB_HktchCK',
      );
    });

    test('App Link con barra final', () {
      expect(extractMachineToken('https://demoeca.example.com/m/0hIB_HktchCK/'), '0hIB_HktchCK');
    });

    test('esquema propio, forma larga', () {
      expect(extractMachineToken('demoeca://machine/0hIB_HktchCK'), '0hIB_HktchCK');
    });

    test('un enlace de otra app no se confunde con un equipo', () {
      expect(extractMachineToken('https://demoeca.example.com/'), isNull);
      expect(extractMachineToken('mailto:soporte@demoeca.example.com'), isNull);
    });
  });
}
