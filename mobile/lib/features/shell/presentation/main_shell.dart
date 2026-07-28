import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/providers.dart';
import '../../../shared/widgets/ai_head_icon.dart';

/// Armazón de la app con barra de navegación inferior.
///
/// Los módulos conviven: el escáner **no** es un paso obligatorio, es un atajo disponible en
/// cualquier momento. El usuario puede recorrer el catálogo completo, entrar a cualquier equipo y
/// su capacitación, y escanear otro QR cuando se ponga delante de otra máquina, sin salir de la
/// app ni volver a empezar.
///
/// Se usa `StatefulShellRoute.indexedStack`, así que cada módulo conserva su propio estado y su
/// pila de navegación: volver a Equipos después de escanear mantiene el scroll y el equipo donde
/// se estaba.
///
/// **Consecuencia que hay que gestionar:** con `indexedStack` la rama del escáner sigue viva
/// aunque no se vea, y una cámara abierta en segundo plano gasta batería y bloquea el dispositivo
/// para otras apps. Por eso el índice activo se publica en `activeTabProvider` y el escáner
/// enciende y apaga la cámara según su visibilidad.
class MainShell extends ConsumerWidget {
  const MainShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Se publica tras el frame: escribir en un provider durante el build es un error en Riverpod,
    // y hace falta hacerlo aquí (y no solo en el `onTap`) para capturar también los cambios de
    // rama provocados por navegación programática, como un deep link entrante.
    //
    // El notifier se captura **antes** del callback: `ref` pertenece a este build y usarlo después
    // de que el widget se destruya lanzaría. El notifier, en cambio, vive tanto como el contenedor
    // porque el provider no es `autoDispose`.
    final tabNotifier = ref.read(activeTabProvider.notifier);
    final currentIndex = navigationShell.currentIndex;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (tabNotifier.state != currentIndex) {
        tabNotifier.state = currentIndex;
      }
    });

    return Scaffold(
      body: navigationShell,
      // La hairline superior va aquí y no en `NavigationBarThemeData`, que no tiene propiedad de
      // borde. Sin ella, en modo oscuro la barra se funde con el contenido y los tres destinos
      // parecen flotar sobre la pantalla.
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: Theme.of(context).colorScheme.outlineVariant)),
        ),
        child: NavigationBar(
          selectedIndex: navigationShell.currentIndex,
          onDestinationSelected: (index) => navigationShell.goBranch(
            index,
            // Volver a tocar el módulo activo devuelve a su raíz, que es el comportamiento que
            // espera cualquiera acostumbrado a una barra de pestañas.
            initialLocation: index == navigationShell.currentIndex,
          ),
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.medical_services_outlined),
              selectedIcon: Icon(Icons.medical_services),
              label: 'Equipment',
            ),
            NavigationDestination(
              icon: Icon(Icons.qr_code_scanner_outlined),
              selectedIcon: Icon(Icons.qr_code_scanner),
              label: 'Scan',
            ),
            // Icono propio (cabeza robótica con circuito, petición del cliente). Lee el
            // IconTheme, así que hereda el color de seleccionado/no-seleccionado igual que
            // un Icon normal.
            NavigationDestination(
              icon: AiHeadIcon(),
              selectedIcon: AiHeadIcon(filled: true),
              label: 'ECAHelp',
            ),
          ],
        ),
      ),
    );
  }
}
