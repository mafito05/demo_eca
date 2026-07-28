/// Cliente WebSocket del agente IA.
///
/// Implementa el protocolo que emite `app/modules/agent/ws.py`. Se mantiene libre de
/// dependencias de UI y de gestor de estado: expone un `Stream<AgentEvent>` que cualquier capa
/// de presentación puede consumir, y recibe la URL ya construida para poder probarlo contra un
/// servidor falso.
///
/// Detalles que importan en red móvil:
/// - Ping cada 30 s. Las redes móviles y los proxies hospitalarios cierran sockets inactivos sin
///   avisar, y sin keepalive el chat "se queda pensando" para siempre.
/// - El token JWT va como query param: el handshake WebSocket no admite cabeceras
///   personalizadas.
library;

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

enum AgentEventType {
  conversation,
  start,
  sources,
  token,
  toolCall,
  toolResult,
  confirmationRequired,
  done,
  error,
  pong,
  unknown,
}

AgentEventType _parseType(String raw) => switch (raw) {
      'conversation' => AgentEventType.conversation,
      'start' => AgentEventType.start,
      'sources' => AgentEventType.sources,
      'token' => AgentEventType.token,
      'tool_call' => AgentEventType.toolCall,
      'tool_result' => AgentEventType.toolResult,
      'confirmation_required' => AgentEventType.confirmationRequired,
      'done' => AgentEventType.done,
      'error' => AgentEventType.error,
      'pong' => AgentEventType.pong,
      _ => AgentEventType.unknown,
    };

/// Fuente citada por el RAG. Se muestra bajo la respuesta para que el técnico pueda ir al
/// manual: un asistente sin trazabilidad no es utilizable en un entorno médico.
class AgentCitation {
  const AgentCitation({required this.label, required this.citation, required this.distance});

  final String label;
  final String citation;
  final double distance;

  factory AgentCitation.fromJson(Map<String, dynamic> json) => AgentCitation(
        label: json['label'] as String? ?? '',
        citation: json['citation'] as String? ?? '',
        distance: (json['distance'] as num?)?.toDouble() ?? 0,
      );
}

class AgentEvent {
  const AgentEvent(this.type, this.data);

  final AgentEventType type;
  final Map<String, dynamic> data;

  String get text => data['text'] as String? ?? '';

  List<AgentCitation> get sources => ((data['sources'] as List?) ?? const [])
      .map((item) => AgentCitation.fromJson((item as Map).cast<String, dynamic>()))
      .toList();

  String get errorMessage => data['message'] as String? ?? 'Error desconocido';

  factory AgentEvent.fromJson(Map<String, dynamic> json) => AgentEvent(
        _parseType(json['type'] as String? ?? ''),
        (json['data'] as Map?)?.cast<String, dynamic>() ?? const {},
      );
}

/// Tool que el agente quiere ejecutar y que requiere confirmación explícita del usuario.
class PendingToolConfirmation {
  const PendingToolConfirmation({
    required this.toolName,
    required this.description,
    required this.arguments,
  });

  final String toolName;
  final String description;
  final Map<String, dynamic> arguments;

  factory PendingToolConfirmation.fromEvent(AgentEvent event) => PendingToolConfirmation(
        toolName: event.data['tool_name'] as String? ?? '',
        description: event.data['tool_description'] as String? ?? '',
        arguments: (event.data['arguments'] as Map?)?.cast<String, dynamic>() ?? const {},
      );
}

class AgentSocket {
  AgentSocket({required this.wsUrl, required this.accessToken});

  /// URL completa del endpoint, sin el token. Ej. `ws://10.0.2.2:8000/api/v1/agent/ws`
  final String wsUrl;
  final String accessToken;

  WebSocketChannel? _channel;
  StreamController<AgentEvent>? _events;
  Timer? _keepAlive;
  String? _conversationId;

  String? get conversationId => _conversationId;

  Stream<AgentEvent> connect() {
    final existing = _events;
    if (existing != null && !existing.isClosed) {
      return existing.stream;
    }

    final controller = StreamController<AgentEvent>.broadcast();
    _events = controller;

    final channel = WebSocketChannel.connect(Uri.parse('$wsUrl?token=$accessToken'));
    _channel = channel;

    channel.stream.listen(
      (message) {
        try {
          final event = AgentEvent.fromJson(
            jsonDecode(message as String) as Map<String, dynamic>,
          );
          // El backend devuelve el id de conversación en el primer evento del turno; se guarda
          // para que los mensajes siguientes continúen el mismo hilo.
          if (event.type == AgentEventType.conversation) {
            _conversationId = event.data['conversation_id'] as String?;
          }
          controller.add(event);
        } catch (error) {
          controller.add(
            AgentEvent(
              AgentEventType.error,
              {'message': 'Invalid response from the server: $error'},
            ),
          );
        }
      },
      onError: (Object error) => controller.add(
        AgentEvent(AgentEventType.error, {'message': 'Connection lost: $error'}),
      ),
      onDone: () {
        if (!controller.isClosed) {
          controller.close();
        }
      },
      cancelOnError: false,
    );

    _keepAlive = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _channel?.sink.add(jsonEncode({'type': 'ping'})),
    );

    return controller.stream;
  }

  /// Envía una pregunta. `machineModelId` da al agente el contexto del equipo desde el que se
  /// abrió el chat flotante; `lessonId` afina el contexto a la lección en curso.
  void sendMessage({
    required String content,
    String? machineModelId,
    String? lessonId,
    List<String> approvedTools = const [],
  }) {
    _channel?.sink.add(
      jsonEncode({
        'type': 'message',
        'content': content,
        'conversation_id': _conversationId,
        'machine_model_id': machineModelId,
        'lesson_id': lessonId,
        'approved_tools': approvedTools,
      }),
    );
  }

  /// Reenvía la última pregunta autorizando la tool pendiente. El backend no ejecuta acciones
  /// con efectos secundarios sin este paso explícito.
  void approveTool({
    required String lastQuestion,
    required String toolName,
    String? machineModelId,
    String? lessonId,
  }) {
    sendMessage(
      content: lastQuestion,
      machineModelId: machineModelId,
      lessonId: lessonId,
      approvedTools: [toolName],
    );
  }

  Future<void> dispose() async {
    _keepAlive?.cancel();
    _keepAlive = null;
    await _channel?.sink.close();
    _channel = null;
    final controller = _events;
    _events = null;
    if (controller != null && !controller.isClosed) {
      await controller.close();
    }
  }
}
