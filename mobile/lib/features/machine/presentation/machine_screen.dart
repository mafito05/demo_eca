import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/providers.dart';
import '../../../core/theme/design_tokens.dart';
import '../../../shared/errors/error_presenter.dart';
import '../../../shared/widgets/info_banner.dart';
import '../../../shared/widgets/skeleton.dart';
import '../../../shared/widgets/skeletons/learning_path_skeleton.dart';
import '../../../shared/widgets/status_view.dart';
import '../../agent/presentation/agent_fab.dart';
import '../data/machine_repository.dart';
import 'widgets/machine_header.dart';
import 'widgets/module_card.dart';

/// Pantalla de la máquina: resultado del escaneo del QR.
///
/// Resuelve el token, carga la ruta de capacitación con el progreso del usuario y expone el botón
/// flotante del agente con el contexto de este equipo.
///
/// Es lo primero que ve el público en una demo, justo después de escanear, así que el encabezado se
/// pinta **en cuanto resuelve el QR**, sin esperar a la ruta de aprendizaje: `ResolvedMachine` trae
/// nombre, código, especialidad, descripción y número de módulos. Eso elimina un estado de carga a
/// pantalla completa del recorrido más visible de la app.
class MachineScreen extends ConsumerWidget {
  const MachineScreen({required this.qrToken, super.key});

  final String qrToken;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scan = ref.watch(resolveMachineProvider(qrToken));

    return scan.when(
      loading: () => const _OpeningScaffold(),
      error: (error, _) => _Problem(
        title: 'Could not open the equipment',
        message: friendlyMessage(error),
        action: AppAction(
          label: 'Try again',
          icon: Icons.refresh,
          onPressed: () => ref.invalidate(resolveMachineProvider(qrToken)),
        ),
      ),
      data: (result) => switch (result) {
        ScanSuccess(:final machine) => _MachineView(machine: machine),
        ScanNotFound(:final message) => _Problem(
          title: 'Code not recognised',
          message: message,
          icon: Icons.qr_code_scanner,
          action: AppAction(
            label: 'Scan another code',
            icon: Icons.qr_code_scanner,
            onPressed: () => context.go('/escanear'),
          ),
        ),
        ScanError(:final message) => _Problem(
          title: 'No connection',
          message: message,
          icon: Icons.cloud_off_outlined,
          action: AppAction(
            label: 'Try again',
            icon: Icons.refresh,
            onPressed: () => ref.invalidate(resolveMachineProvider(qrToken)),
          ),
        ),
      },
    );
  }
}

class _MachineView extends ConsumerWidget {
  const _MachineView({required this.machine});

  final ResolvedMachine machine;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final path = ref.watch(learningPathProvider(machine.machineModelId));

    return Scaffold(
      appBar: AppBar(
        title: Text(machine.name, overflow: TextOverflow.ellipsis),
        actions: [
          IconButton(
            tooltip: 'Scan another machine',
            icon: const Icon(Icons.qr_code_scanner),
            onPressed: () => context.go('/escanear'),
          ),
        ],
      ),
      floatingActionButton: AgentFab(
        machineModelId: machine.machineModelId,
        machineName: machine.name,
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(learningPathProvider(machine.machineModelId)),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.screenH,
            AppSpacing.lg,
            AppSpacing.screenH,
            AppSpacing.fabClearance,
          ),
          children: [
            // El encabezado no espera a la ruta: con `path: null` pinta todo menos el progreso.
            MachineHeader(machine: machine, path: path.valueOrNull),
            const SizedBox(height: AppSpacing.xl),

            ...switch (path) {
              AsyncLoading() => const [Skeleton(child: LearningPathSkeleton())],
              AsyncError(:final error) => [
                // Antes esto era `Text('Could not load the training.\n$error')`, que pintaba la
                // excepción de Dio en crudo dentro de la pantalla más visible de la demo.
                StatusView.error(
                  title: 'Could not load the training',
                  message: friendlyMessage(error),
                  scrollable: false,
                  actions: [
                    AppAction(
                      label: 'Try again',
                      icon: Icons.refresh,
                      onPressed: () =>
                          ref.invalidate(learningPathProvider(machine.machineModelId)),
                    ),
                  ],
                ),
              ],
              AsyncValue(:final value?) => [
                if (value.modules.isEmpty)
                  const StatusView.empty(
                    title: 'No training published yet',
                    message:
                        'This equipment is registered but its modules are still being prepared.',
                    icon: Icons.school_outlined,
                    scrollable: false,
                  )
                else
                  for (final (index, module) in value.modules.indexed) ...[
                    ModuleCard(
                      module: module,
                      index: index,
                      onOpenLesson: (lesson) => context.push(
                        '/lesson/${lesson.id}?machine=${machine.machineModelId}',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                  ],
              ],
              _ => const <Widget>[],
            },

            const SizedBox(height: AppSpacing.lg),
            // Antes era texto gris al final de la lista, donde nadie llega. Como franja tonal se
            // lee sin buscarlo, que es el punto de un descargo de responsabilidad.
            const InfoBanner(
              message:
                  'The assistant answers about the technical handling of this equipment. It does '
                  'not replace professional clinical judgement.',
              icon: Icons.info_outline,
            ),
          ],
        ),
      ),
    );
  }
}

/// Carga inicial, mientras se resuelve el token del QR.
class _OpeningScaffold extends StatelessWidget {
  const _OpeningScaffold();

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Opening training…')),
    body: const Padding(
      padding: EdgeInsets.all(AppSpacing.screenH),
      child: Skeleton(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SkeletonBox(height: 132, borderRadius: AppRadii.card),
            SizedBox(height: AppSpacing.xl),
            LearningPathSkeleton(),
          ],
        ),
      ),
    ),
  );
}

class _Problem extends StatelessWidget {
  const _Problem({
    required this.title,
    required this.message,
    required this.action,
    this.icon = Icons.error_outline,
  });

  final String title;
  final String message;
  final AppAction action;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(),
    body: StatusView(
      icon: icon,
      title: title,
      message: message,
      tone: StatusTone.error,
      actions: [action],
    ),
  );
}
