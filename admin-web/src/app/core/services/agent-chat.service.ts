import { Injectable, inject, signal } from '@angular/core';

import { environment } from '../../../environments/environment';
import { AgentEvent, AgentSource } from '../models/api.models';
import { AuthService } from './auth.service';

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  sources?: AgentSource[];
  /** Métricas del evento `done`: sirven para juzgar coste y latencia en la demo. */
  meta?: { latency_ms?: number; prompt_tokens?: number; completion_tokens?: number };
  streaming?: boolean;
  error?: boolean;
}

/**
 * Cliente del WebSocket del agente para el playground del panel.
 *
 * Comparte protocolo con el cliente de Flutter (`mobile/lib/features/agent/data/agent_socket.dart`).
 * El token va como query param porque el handshake WebSocket del navegador no admite cabeceras
 * personalizadas — no es un atajo, es una limitación de la API del navegador.
 */
@Injectable({ providedIn: 'root' })
export class AgentChatService {
  private readonly auth = inject(AuthService);

  private socket: WebSocket | null = null;
  private keepAlive: ReturnType<typeof setInterval> | null = null;
  private conversationId: string | null = null;

  readonly messages = signal<ChatMessage[]>([]);
  readonly connected = signal(false);
  readonly thinking = signal(false);
  /** Proveedor y modelo que informa el evento `start`: confirma qué LLM respondió de verdad. */
  readonly activeModel = signal<string | null>(null);

  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
      return;
    }

    const token = this.auth.accessToken;
    if (!token) {
      return;
    }

    const socket = new WebSocket(`${environment.agentWsUrl()}?token=${token}`);
    this.socket = socket;

    socket.onopen = () => this.connected.set(true);
    socket.onclose = () => {
      this.connected.set(false);
      this.thinking.set(false);
    };
    socket.onerror = () => this.pushError('Connection error with the server.');
    socket.onmessage = (event) => this.handleEvent(JSON.parse(event.data) as AgentEvent);

    // Las redes corporativas y los proxies cierran sockets inactivos sin avisar.
    this.keepAlive = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30_000);
  }

  send(content: string, machineModelId: string | null, approvedTools: string[] = []): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.pushError('No connection to the agent. Reconnect and try again.');
      return;
    }

    this.messages.update((list) => [...list, { role: 'user', text: content }]);
    this.thinking.set(true);

    this.socket.send(
      JSON.stringify({
        type: 'message',
        content,
        conversation_id: this.conversationId,
        machine_model_id: machineModelId,
        approved_tools: approvedTools,
      }),
    );
  }

  /** Empieza un hilo nuevo sin reconectar el socket. */
  reset(): void {
    this.conversationId = null;
    this.messages.set([]);
    this.activeModel.set(null);
  }

  disconnect(): void {
    if (this.keepAlive) {
      clearInterval(this.keepAlive);
      this.keepAlive = null;
    }
    this.socket?.close();
    this.socket = null;
    this.connected.set(false);
  }

  private handleEvent(event: AgentEvent): void {
    switch (event.type) {
      case 'conversation':
        this.conversationId = event.data['conversation_id'];
        break;

      case 'start':
        this.activeModel.set(`${event.data['provider']}/${event.data['model']}`);
        // Se abre el mensaje del asistente en cuanto empieza, para que el usuario vea que
        // algo está pasando antes de que llegue el primer token.
        this.messages.update((list) => [...list, { role: 'assistant', text: '', streaming: true }]);
        break;

      case 'sources':
        this.patchLast({ sources: event.data['sources'] ?? [] });
        break;

      case 'token':
        this.appendToLast(event.data['text'] ?? '');
        break;

      case 'tool_call':
        this.appendToLast(`\n\n_[running tool: ${event.data['tool_name']}]_\n\n`);
        break;

      case 'confirmation_required':
        this.patchLast({ streaming: false });
        this.thinking.set(false);
        this.pushError(
          `The agent wants to run "${event.data['tool_name']}", which has side effects on ` +
            `external systems and needs explicit confirmation.`,
        );
        break;

      case 'done':
        this.patchLast({
          streaming: false,
          meta: {
            latency_ms: event.data['latency_ms'],
            prompt_tokens: event.data['prompt_tokens'],
            completion_tokens: event.data['completion_tokens'],
          },
        });
        this.thinking.set(false);
        break;

      case 'error':
        this.thinking.set(false);
        this.patchLast({ streaming: false });
        this.pushError(event.data['message'] ?? 'Unknown agent error.');
        break;
    }
  }

  private appendToLast(text: string): void {
    this.messages.update((list) => {
      const last = list.at(-1);
      if (!last || last.role !== 'assistant') {
        return [...list, { role: 'assistant', text, streaming: true }];
      }
      return [...list.slice(0, -1), { ...last, text: last.text + text }];
    });
  }

  private patchLast(patch: Partial<ChatMessage>): void {
    this.messages.update((list) => {
      const last = list.at(-1);
      if (!last || last.role !== 'assistant') {
        return list;
      }
      return [...list.slice(0, -1), { ...last, ...patch }];
    });
  }

  private pushError(text: string): void {
    this.messages.update((list) => [...list, { role: 'assistant', text, error: true }]);
  }
}
