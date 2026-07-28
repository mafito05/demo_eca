import 'package:flutter/material.dart';

import 'agent_chat_view.dart';

/// Chat contextual del asistente, abierto desde un equipo o una lección.
///
/// A diferencia del módulo ECAHelp, aquí el contexto de máquina viene dado y no se puede cambiar: se
/// llegó desde ese equipo, y el agente responde sobre él. Toda la lógica del chat vive en
/// `AgentChatView`, compartida con ECAHelp.
class AgentChatScreen extends StatelessWidget {
  const AgentChatScreen({
    super.key,
    required this.machineModelId,
    this.machineName,
    this.lessonId,
  });

  final String? machineModelId;
  final String? machineName;
  final String? lessonId;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('ECAHelp'),
            if (machineName != null)
              Text(
                machineName!,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
          ],
        ),
      ),
      body: AgentChatView(machineModelId: machineModelId, lessonId: lessonId),
    );
  }
}
