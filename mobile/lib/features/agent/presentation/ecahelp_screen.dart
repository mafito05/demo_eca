import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../../../shared/errors/error_presenter.dart';
import '../../../shared/widgets/info_banner.dart';
import 'agent_chat_view.dart';
import 'widgets/machine_context_picker.dart';

/// ECAHelp: el asistente como módulo propio del menú.
///
/// Se diferencia del chat que se abre desde un equipo en una cosa: **aquí no hay contexto de máquina
/// implícito**, así que se ofrece un selector. Sin equipo seleccionado el agente solo puede consultar
/// el corpus global (normativa, procedimientos de la compañía) y **no podrá citar el manual de ningún
/// equipo** — de ahí que el selector esté a la vista y no escondido en un menú de opciones (D-040).
///
/// El equipo elegido se recuerda en `ecahelpMachineProvider`, así que volver a la pestaña después de
/// ver una lección no obliga a elegirlo otra vez.
class EcaHelpScreen extends ConsumerWidget {
  const EcaHelpScreen({super.key});

  /// Índice de este módulo en la barra de navegación.
  static const tabIndex = 2;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalog = ref.watch(machineCatalogProvider);
    final selectedId = ref.watch(ecahelpMachineProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('ECAHelp')),
      body: Column(
        children: [
          // El selector va en el cuerpo y no en el `bottom` del AppBar: allí la franja era estrecha
          // y el desplegable desbordaba con nombres de equipo largos.
          catalog.when(
            loading: () => const LinearProgressIndicator(),
            error: (error, _) => Padding(
              padding: const EdgeInsets.all(12),
              child: InfoBanner(
                message: 'Equipment list unavailable. ${friendlyMessage(error)}',
                tone: BannerTone.warning,
                actionLabel: 'Retry',
                onAction: () => ref.invalidate(machineCatalogProvider),
              ),
            ),
            data: (machines) => MachineContextTile(
              machines: machines,
              selectedId: selectedId,
              onChanged: (value) => ref.read(ecahelpMachineProvider.notifier).state = value,
            ),
          ),

          // La `key` fuerza a reconstruir el chat al cambiar de equipo: el contexto del agente
          // cambia, así que continuar el mismo hilo mezclaría documentación de dos máquinas.
          Expanded(
            child: AgentChatView(
              key: ValueKey(selectedId ?? 'global'),
              machineModelId: selectedId,
              showEmptyStateHint: true,
            ),
          ),
        ],
      ),
    );
  }
}
