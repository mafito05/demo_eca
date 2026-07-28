/// Acceso REST del agente: sugerencias y parámetros de runtime.
///
/// El chat en sí va por WebSocket (`agent_socket.dart`); esto cubre lo que se pide por HTTP
/// una vez y se pinta: las preguntas de ejemplo del estado vacío (que antes estaban hardcodeadas
/// en el widget y obligaban a recompilar la app para cambiar un texto) y el umbral de distancia
/// del RAG (que estaba copiado a mano y se desincronizaba del backend en silencio). D-053.
library;

import '../../../core/network/api_client.dart';

class SuggestedQuestions {
  const SuggestedQuestions({
    required this.questions,
    required this.hasMachineContext,
    required this.source,
  });

  final List<String> questions;
  final bool hasMachineContext;

  /// `"config"` si vienen del Agent Builder, `"default"` si son las genéricas del backend.
  final String source;

  factory SuggestedQuestions.fromJson(Map<String, dynamic> json) => SuggestedQuestions(
    questions: ((json['questions'] as List?) ?? const []).cast<String>(),
    hasMachineContext: json['has_machine_context'] as bool? ?? false,
    source: json['source'] as String? ?? 'default',
  );
}

class AgentRuntimeSettings {
  const AgentRuntimeSettings({required this.ragMaxDistance, required this.ragTopK});

  final double ragMaxDistance;
  final int ragTopK;

  factory AgentRuntimeSettings.fromJson(Map<String, dynamic> json) => AgentRuntimeSettings(
    ragMaxDistance: (json['rag_max_distance'] as num).toDouble(),
    ragTopK: (json['rag_top_k'] as num).toInt(),
  );
}

class AgentRepository {
  AgentRepository({required this.client});

  final ApiClient client;

  Future<SuggestedQuestions> suggestions(String? machineModelId) async {
    final response = await client.dio.get(
      '/agent/suggestions',
      queryParameters: {
        if (machineModelId != null) 'machine_model_id': machineModelId,
      },
    );
    return SuggestedQuestions.fromJson((response.data as Map).cast<String, dynamic>());
  }

  Future<AgentRuntimeSettings> settings() async {
    final response = await client.dio.get('/agent/settings');
    return AgentRuntimeSettings.fromJson((response.data as Map).cast<String, dynamic>());
  }
}
