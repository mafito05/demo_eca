import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../shared/widgets/ai_head_icon.dart';

/// Botón flotante del asistente.
///
/// Está presente en todas las vistas de la máquina y de sus lecciones, y arrastra el contexto:
/// el equipo actual y, si aplica, la lección en curso. Ese contexto es lo que hace que el agente
/// responda sobre *este* equipo en lugar de dar generalidades.
class AgentFab extends StatelessWidget {
  const AgentFab({
    super.key,
    required this.machineModelId,
    required this.machineName,
    this.lessonId,
  });

  final String machineModelId;
  final String? machineName;
  final String? lessonId;

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton.extended(
      onPressed: () {
        final query = <String, String>{'machine': machineModelId};
        if (machineName != null) {
          query['name'] = machineName!;
        }
        if (lessonId != null) {
          query['lesson'] = lessonId!;
        }
        context.push(Uri(path: '/agent', queryParameters: query).toString());
      },
      icon: const AiHeadIcon(),
      label: const Text('ECAHelp'),
    );
  }
}
