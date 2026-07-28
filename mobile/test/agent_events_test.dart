import 'package:demoeca_app/features/agent/data/agent_socket.dart';
import 'package:flutter_test/flutter_test.dart';

/// Interpretación de los eventos del WebSocket del agente.
///
/// Los payloads son los que emite `app/modules/agent/ws.py`. Cubre en particular que un tipo de
/// evento desconocido no rompa nada: el backend puede añadir eventos y una app ya publicada tiene
/// que seguir funcionando.
void main() {
  group('AgentEvent', () {
    test('reconoce los tipos que emite el backend', () {
      expect(
        AgentEvent.fromJson({
          'type': 'token',
          'data': {'text': 'hola'},
        }).type,
        AgentEventType.token,
      );
      expect(
        AgentEvent.fromJson({'type': 'confirmation_required', 'data': {}}).type,
        AgentEventType.confirmationRequired,
      );
      expect(
        AgentEvent.fromJson({'type': 'tool_call', 'data': {}}).type,
        AgentEventType.toolCall,
      );
      expect(AgentEvent.fromJson({'type': 'done', 'data': {}}).type, AgentEventType.done);
      expect(AgentEvent.fromJson({'type': 'pong', 'data': {}}).type, AgentEventType.pong);
    });

    test('un tipo desconocido no rompe la app', () {
      final event = AgentEvent.fromJson({'type': 'evento_futuro', 'data': {}});
      expect(event.type, AgentEventType.unknown);
      expect(event.text, isEmpty);
      expect(event.sources, isEmpty);
    });

    test('tolera un payload sin `data`', () {
      final event = AgentEvent.fromJson({'type': 'done'});
      expect(event.type, AgentEventType.done);
      expect(event.sources, isEmpty);
    });

    test('extrae las fuentes citadas con su distancia', () {
      final event = AgentEvent.fromJson({
        'type': 'sources',
        'data': {
          'sources': [
            {
              'label': '[1]',
              'citation': 'Manual de operación URO-LITHO-3000 · 4. RESOLUCIÓN DE FALLOS',
              'distance': 0.4897,
            },
            {
              'label': '[2]',
              'citation': 'Manual de operación URO-LITHO-3000 · 3. SEGURIDAD DEL OPERADOR',
              'distance': 0.6117,
            },
          ],
        },
      });

      expect(event.sources, hasLength(2));
      expect(event.sources.first.label, '[1]');
      expect(event.sources.first.citation, contains('RESOLUCIÓN DE FALLOS'));
      expect(event.sources.first.distance, closeTo(0.4897, 0.0001));
    });

    test('un evento de error trae un mensaje legible', () {
      final event = AgentEvent.fromJson({
        'type': 'error',
        'data': {'message': 'Token inválido o expirado.', 'code': 'unauthorized'},
      });

      expect(event.type, AgentEventType.error);
      expect(event.errorMessage, 'Token inválido o expirado.');
    });

    test('un error sin mensaje tiene un texto por defecto', () {
      expect(
        AgentEvent.fromJson({'type': 'error', 'data': {}}).errorMessage,
        'Error desconocido',
      );
    });
  });

  group('PendingToolConfirmation', () {
    test('conserva la herramienta y los argumentos propuestos por el modelo', () {
      final pending = PendingToolConfirmation.fromEvent(
        AgentEvent.fromJson({
          'type': 'confirmation_required',
          'data': {
            'tool_name': 'consultar_estado_equipo',
            'tool_description': 'Consulta el estado operativo actual de un equipo.',
            'arguments': {'serial': 'ABC-123'},
            'partial_text': 'Voy a comprobar el estado…',
          },
        }),
      );

      expect(pending.toolName, 'consultar_estado_equipo');
      expect(pending.description, contains('estado operativo'));
      expect(pending.arguments['serial'], 'ABC-123');
    });

    test('sobrevive a un payload incompleto', () {
      final pending = PendingToolConfirmation.fromEvent(
        AgentEvent.fromJson({'type': 'confirmation_required', 'data': {}}),
      );

      expect(pending.toolName, isEmpty);
      expect(pending.arguments, isEmpty);
    });
  });
}
