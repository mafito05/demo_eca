import 'package:demoeca_app/core/theme/app_theme.dart';
import 'package:demoeca_app/core/theme/app_theme_extensions.dart';
import 'package:demoeca_app/features/machine/data/machine_repository.dart';
import 'package:demoeca_app/features/machine/presentation/widgets/machine_card.dart';
import 'package:demoeca_app/shared/widgets/code_badge.dart';
import 'package:demoeca_app/shared/widgets/progress_ring.dart';
import 'package:demoeca_app/shared/widgets/skeleton.dart';
import 'package:demoeca_app/shared/widgets/skeletons/catalog_skeleton.dart';
import 'package:demoeca_app/shared/widgets/tonal_pill.dart';
import 'package:demoeca_app/shared/widgets/typing_indicator.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Smoke test de los widgets nuevos en los dos temas y en dos tamaños de pantalla.
///
/// Lo que caza esto y `flutter analyze` no puede: excepciones de layout. Un `Row` sin `Expanded`, un
/// `Wrap` que desborda, un sliver mal dimensionado — todo eso compila y solo falla al pintar.
///
/// 320x568 es un móvil pequeño real (iPhone SE de primera generación) y es donde se rompen los
/// textos largos; 411x891 es un Android de tamaño medio.
void main() {
  const pantallas = [Size(320, 568), Size(411, 891)];

  Widget wrap(Widget child, Brightness brightness) => MaterialApp(
    theme: brightness == Brightness.dark ? AppTheme.dark() : AppTheme.light(),
    home: Scaffold(body: SingleChildScrollView(child: child)),
  );

  Future<void> enCadaCombinacion(
    WidgetTester tester,
    Widget child,
    String descripcion,
  ) async {
    for (final size in pantallas) {
      for (final brightness in Brightness.values) {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        await tester.pumpWidget(wrap(child, brightness));
        await tester.pump(const Duration(milliseconds: 300));

        expect(
          tester.takeException(),
          isNull,
          reason: '$descripcion falló en $size con brightness $brightness',
        );
      }
    }
  }

  testWidgets('MachineCard soporta nombres largos y pantallas estrechas', (tester) async {
    // Un nombre largo con descripción es donde se rompe una tarjeta: si falta un `Expanded`, aquí
    // salta la excepción de overflow.
    const machine = MachineSummary(
      id: 'm1',
      code: 'URO-LITHO-3000-EXTENDED-CODE',
      name: 'Uro-Litho 3000 Extracorporeal Shock Wave Lithotripter, Mark IV',
      specialty: 'urologia',
      qrToken: 'abc123',
      manufacturer: 'A Manufacturer With A Very Long Corporate Name GmbH',
      description:
          'Extracorporeal shock wave lithotripter for the treatment of renal and ureteral '
          'stones, with integrated fluoroscopy and ultrasound localisation.',
      lessonsCount: 8,
      completedLessons: 3,
      progressPercent: 37.5,
    );

    await enCadaCombinacion(
      tester,
      MachineCard(machine: machine, onTap: () {}),
      'MachineCard',
    );
  });

  testWidgets('los widgets compartidos se pintan sin desbordar', (tester) async {
    await enCadaCombinacion(
      tester,
      const Column(
        children: [
          CodeBadge('URO-LITHO-3000'),
          SizedBox(height: 8),
          TonalPill(label: 'Locked', icon: Icons.lock_outline),
          SizedBox(height: 8),
          ProgressRing(percent: 62),
          SizedBox(height: 8),
          ProgressRing(percent: 100),
          SizedBox(height: 8),
          TypingIndicator(),
          SizedBox(height: 8),
          Skeleton(child: CatalogSkeleton(sections: 1, cardsPerSection: 2)),
        ],
      ),
      'widgets compartidos',
    );
  });

  testWidgets('las extensiones de tema resuelven sin lanzar', (tester) async {
    // Regresión concreta: `Theme.of(context).extension<T>()` es nullable, y resolverlo con `!`
    // compila pero crashea al pintar fuera de un MaterialApp con las extensiones registradas. Los
    // accesores usan un fallback en su lugar.
    late AppSemanticColors semantic;
    late SpecialtyPalette palette;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (context) {
            semantic = context.semantic;
            palette = context.specialties;
            return const SizedBox();
          },
        ),
      ),
    );

    expect(semantic.success, isNotNull);
    expect(palette.resolve('urologia'), isNotNull);
    // Una especialidad que el backend podría añadir mañana no debe romper nada.
    expect(palette.resolve('radiologia'), palette.fallback);
    expect(palette.resolve(null), palette.fallback);
  });

  testWidgets('sin las extensiones registradas se usa el fallback', (tester) async {
    // Este es el escenario que un `!` convertiría en crash: un tema sin nuestras extensiones.
    late AppSemanticColors semantic;

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.light(),
        home: Builder(
          builder: (context) {
            semantic = context.semantic;
            return const SizedBox();
          },
        ),
      ),
    );

    expect(semantic.success, AppSemanticColors.light.success);
  });
}
