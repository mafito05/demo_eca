import 'package:demoeca_app/core/theme/app_theme.dart';
import 'package:demoeca_app/shared/widgets/ai_head_icon.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Regresión directa del bug "hay letras que no se ven".
///
/// La causa: los component themes recibían una `TextTheme` sin color. El merge de `Typography`
/// que pone el color solo alcanza a `ThemeData.textTheme`, y un `appBarTheme.titleTextStyle`
/// presente cortocircuita el `copyWith(color: foregroundColor)` de los defaults de Flutter — el
/// título quedaba con color null, que el engine pinta BLANCO: invisible sobre la surface clara.
///
/// Estos tests verifican el color EFECTIVO del texto renderizado, no el del theme, para que la
/// regresión no pueda volver por otro camino.
void main() {
  Widget app(Widget home, {Brightness brightness = Brightness.light}) => MaterialApp(
    theme: brightness == Brightness.dark ? AppTheme.dark() : AppTheme.light(),
    home: home,
  );

  /// Color efectivo con el que se pinta un `Text`: su estilo mergeado con el DefaultTextStyle.
  Color? effectiveColor(WidgetTester tester, Finder finder) {
    final context = tester.element(finder);
    final widget = tester.widget<Text>(finder);
    final defaultStyle = DefaultTextStyle.of(context).style;
    return (widget.style == null ? defaultStyle : defaultStyle.merge(widget.style)).color;
  }

  for (final brightness in Brightness.values) {
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF1E40AF),
      brightness: brightness,
    );

    testWidgets('el título del AppBar tiene color y contrasta ($brightness)', (tester) async {
      await tester.pumpWidget(
        app(
          Scaffold(appBar: AppBar(title: const Text('Equipment'))),
          brightness: brightness,
        ),
      );

      final color = effectiveColor(tester, find.text('Equipment'));
      expect(color, isNotNull, reason: 'color null = blanco del engine = invisible en claro');
      // Contraste real contra la superficie del AppBar, no solo "no es null".
      final contrast = (color!.computeLuminance() + 0.05) /
          (scheme.surface.computeLuminance() + 0.05);
      final ratio = contrast >= 1 ? contrast : 1 / contrast;
      expect(ratio, greaterThan(4.5), reason: 'título ilegible sobre el AppBar');
    });

    testWidgets('la etiqueta de un FilterChip tiene color ($brightness)', (tester) async {
      await tester.pumpWidget(
        app(
          Scaffold(
            body: FilterChip(label: const Text('Urology'), onSelected: (_) {}),
          ),
          brightness: brightness,
        ),
      );
      expect(effectiveColor(tester, find.text('Urology')), isNotNull);
    });

    testWidgets('título y contenido de un AlertDialog tienen color ($brightness)', (
      tester,
    ) async {
      await tester.pumpWidget(
        app(
          const Scaffold(
            body: AlertDialog(
              title: Text('Equipment code'),
              content: Text('Code printed next to the QR'),
            ),
          ),
          brightness: brightness,
        ),
      );
      expect(effectiveColor(tester, find.text('Equipment code')), isNotNull);
      expect(effectiveColor(tester, find.text('Code printed next to the QR')), isNotNull);
    });

    testWidgets('AiHeadIcon se pinta y hereda el IconTheme ($brightness)', (tester) async {
      await tester.pumpWidget(
        app(
          const Scaffold(
            body: IconTheme(
              data: IconThemeData(size: 24, color: Colors.teal),
              child: Row(children: [AiHeadIcon(), AiHeadIcon(filled: true)]),
            ),
          ),
          brightness: brightness,
        ),
      );
      expect(find.byType(AiHeadIcon), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    });
  }
}
