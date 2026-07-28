import 'package:demoeca_app/core/theme/app_theme.dart';
import 'package:demoeca_app/shared/widgets/status_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Primeros tests de widget del proyecto.
///
/// Se centran en `StatusView` porque es el componente que sustituye a **cinco** implementaciones
/// distintas, así que un fallo aquí se ve en cinco sitios. Y en los dos temas, porque el mayor
/// agujero del tema oscuro anterior era exactamente de este tipo: algo que se pintaba pero no se
/// veía.
void main() {
  Widget wrap(Widget child, {Brightness brightness = Brightness.light}) => MaterialApp(
    theme: brightness == Brightness.dark ? AppTheme.dark() : AppTheme.light(),
    home: Scaffold(body: child),
  );

  testWidgets('pinta título, mensaje y acción', (tester) async {
    var pressed = 0;

    await tester.pumpWidget(
      wrap(
        StatusView.error(
          title: 'No connection',
          message: 'Check that this device is on the same network.',
          actions: [AppAction(label: 'Try again', onPressed: () => pressed++)],
        ),
      ),
    );

    expect(find.text('No connection'), findsOneWidget);
    expect(find.text('Check that this device is on the same network.'), findsOneWidget);

    await tester.tap(find.text('Try again'));
    expect(pressed, 1);
  });

  testWidgets('se pinta igual en los dos temas', (tester) async {
    for (final brightness in Brightness.values) {
      await tester.pumpWidget(
        wrap(
          const StatusView.empty(title: 'No equipment yet', message: 'Nothing published.'),
          brightness: brightness,
        ),
      );
      expect(find.text('No equipment yet'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('acepta hasta tres acciones y no más', (tester) async {
    await tester.pumpWidget(
      wrap(
        StatusView(
          icon: Icons.no_photography_outlined,
          title: 'Camera unavailable',
          actions: [
            AppAction(label: 'Enter code', onPressed: () {}),
            AppAction(label: 'Retry', style: AppActionStyle.outlined, onPressed: () {}),
            AppAction(label: 'Catalogue', style: AppActionStyle.text, onPressed: () {}),
            AppAction(label: 'Cuarta que no debe aparecer', onPressed: () {}),
          ],
        ),
      ),
    );

    expect(find.text('Enter code'), findsOneWidget);
    expect(find.text('Catalogue'), findsOneWidget);
    // Más de tres acciones apiladas desbordan en un móvil pequeño, así que se recortan.
    expect(find.text('Cuarta que no debe aparecer'), findsNothing);
  });

  testWidgets('scrollable mantiene el desplazamiento para el pull-to-refresh', (tester) async {
    // Sin `AlwaysScrollableScrollPhysics`, meter este widget dentro de un RefreshIndicator
    // desactiva el gesto de recarga en silencio — justo cuando el usuario quiere reintentar.
    await tester.pumpWidget(
      wrap(
        RefreshIndicator(
          onRefresh: () async {},
          child: const StatusView.error(title: 'Failed', message: 'Try pulling down.'),
        ),
      ),
    );

    await tester.fling(find.text('Failed'), const Offset(0, 300), 1000);
    await tester.pump();
    expect(find.byType(RefreshProgressIndicator), findsOneWidget);
  });

  testWidgets('la variante compacta cabe en una caja pequeña', (tester) async {
    // Se usa dentro del marco 16:9 del reproductor: si desborda, el análisis estático no lo ve
    // pero el test sí.
    await tester.pumpWidget(
      wrap(
        const SizedBox(
          width: 320,
          height: 180,
          child: StatusView.error(
            title: 'The video could not be played',
            message: 'The playlist did not load.',
            compact: true,
          ),
        ),
      ),
    );

    expect(find.text('The video could not be played'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
