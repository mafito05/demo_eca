import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AgentChatService } from '../../core/services/agent-chat.service';
import { AgentBuilderService } from '../../core/services/agent-builder.service';
import { MachinesService } from '../../core/services/machines.service';
import { Machine, RetrievedChunk } from '../../core/models/api.models';

/**
 * Playground del Agent Builder: la pantalla que demuestra el producto.
 *
 * Junta tres cosas en una sola vista, y ese es su valor:
 *
 * 1. El chat con streaming token a token por WebSocket.
 * 2. Las **fuentes citadas** que devuelve el evento `sources`, con su distancia vectorial. Un
 *    asistente sobre equipamiento médico sin trazabilidad no es utilizable.
 * 3. El inspector de recuperación, que muestra qué fragmentos devuelve el RAG **sin gastar
 *    tokens del LLM**. Cuando el agente responde mal, la primera pregunta siempre es "¿qué
 *    recuperó?", y responderla sin este panel obliga a mirar los logs del contenedor.
 */
@Component({
  selector: 'app-playground',
  imports: [FormsModule],
  template: `
    <div class="field" style="max-width: 520px">
      <label for="machine">Equipment context</label>
      <select id="machine" [(ngModel)]="machineId" (ngModelChange)="onMachineChange()">
        <option [ngValue]="null">No context (global corpus only)</option>
        @for (machine of machines(); track machine.id) {
          <option [ngValue]="machine.id">{{ machine.code }} — {{ machine.name }}</option>
        }
      </select>
      <p class="hint">
        This is the context the mobile app sends when opening the chat from an equipment page. It
        filters RAG retrieval to that equipment's documents.
      </p>
    </div>

    <div class="split">
      <!-- ---------------------------- Chat ---------------------------- -->
      <section class="card chat">
        <header>
          <div class="row">
            <h2 style="margin:0">Conversation</h2>
            @if (chat.connected()) {
              <span class="badge ok">connected</span>
            } @else {
              <span class="badge danger">disconnected</span>
            }
            @if (chat.activeModel()) {
              <span class="badge">{{ chat.activeModel() }}</span>
            }
          </div>
          <button class="small" (click)="chat.reset()">New thread</button>
        </header>

        <div class="messages">
          @if (chat.messages().length === 0) {
            <div class="empty">Try: <em>"What should I do if the unit shows error E-204?"</em></div>
          }
          @for (message of chat.messages(); track $index) {
            <article [class]="'msg ' + message.role" [class.error]="message.error">
              <span class="who">{{ message.role === 'user' ? 'You' : 'Agent' }}</span>
              <div class="text">
                {{ message.text }}
                @if (message.streaming) {
                  <span class="caret"></span>
                }
              </div>

              @if (message.sources?.length) {
                <div class="sources">
                  <span class="sources-title">Cited sources</span>
                  @for (source of message.sources; track source.label) {
                    <div class="source">
                      <span class="mono">{{ source.label }}</span>
                      {{ source.citation }}
                      <span class="badge">d={{ source.distance }}</span>
                    </div>
                  }
                </div>
              }

              @if (message.meta?.latency_ms) {
                <div class="meta">
                  {{ message.meta?.latency_ms }} ms · {{ message.meta?.prompt_tokens ?? '?' }} input
                  tokens · {{ message.meta?.completion_tokens ?? '?' }} output
                </div>
              }
            </article>
          }
        </div>

        <form class="composer" (ngSubmit)="send()">
          <input
            name="question"
            [(ngModel)]="question"
            placeholder="Technical question about the equipment…"
            [disabled]="chat.thinking()"
          />
          <button class="primary" type="submit" [disabled]="chat.thinking() || !question.trim()">
            @if (chat.thinking()) {
              <span class="spinner"></span>
            } @else {
              Send
            }
          </button>
        </form>

        <p class="hint">
          The agent is limited to technical equipment operation: it refuses clinical advice, dosage
          and treatment decisions.
        </p>
      </section>

      <!-- ---------------------- Inspector del RAG --------------------- -->
      <section class="card">
        <h2>Retrieval inspector</h2>
        <p class="hint" style="margin-top:-0.4rem">
          Runs the vector search only. It does not call the LLM, so it costs no tokens.
        </p>

        <form (ngSubmit)="inspect()">
          <div class="field">
            <input name="probe" [(ngModel)]="probe" placeholder="what does error E-204 mean" />
          </div>
          <button type="submit" [disabled]="inspecting() || !probe.trim()">
            @if (inspecting()) {
              <span class="spinner"></span>
            } @else {
              Retrieve
            }
          </button>
        </form>

        @if (chunks() !== null) {
          @if (chunks()!.length === 0) {
            <div class="alert warn" style="margin-top:1rem">
              No results. Is the document vectorised? Check the Knowledge base section.
            </div>
          } @else {
            <div class="chunks">
              @for (chunk of chunks(); track $index; let i = $index) {
                <div class="chunk" [class.discarded]="chunk.distance > maxDistance()">
                  <div class="row" style="justify-content: space-between">
                    <span class="mono">#{{ i + 1 }} · {{ chunk.citation }}</span>
                    <span
                      class="badge"
                      [class.ok]="chunk.distance <= maxDistance()"
                      [class.warn]="chunk.distance > maxDistance()"
                    >
                      d={{ chunk.distance.toFixed(4) }}
                    </span>
                  </div>
                  <p>{{ chunk.content }}</p>
                </div>
              }
            </div>
            <p class="hint">
              Chunks with a distance above {{ maxDistance() }} are discarded when building the
              context: better to answer "it is not in the documentation" than to cite something
              irrelevant.
            </p>
          }
        }
      </section>
    </div>
  `,
  styles: `
    .chat {
      display: flex;
      flex-direction: column;
      min-height: 560px;
    }
    .chat header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.8rem;
    }
    .messages {
      flex: 1;
      overflow-y: auto;
      max-height: 460px;
      display: flex;
      flex-direction: column;
      gap: 0.8rem;
      padding-right: 0.3rem;
    }
    .msg {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.7rem 0.85rem;
      background: var(--surface-2);
    }
    .msg.user {
      border-color: color-mix(in srgb, var(--accent) 35%, transparent);
    }
    .msg.error {
      border-color: color-mix(in srgb, var(--danger) 45%, transparent);
      color: var(--danger);
    }
    .who {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
      font-weight: 700;
    }
    .text {
      white-space: pre-wrap;
      margin-top: 0.25rem;
    }
    .caret {
      display: inline-block;
      width: 7px;
      height: 1em;
      background: var(--accent);
      vertical-align: text-bottom;
      animation: blink 1s steps(2) infinite;
    }
    @keyframes blink {
      50% {
        opacity: 0;
      }
    }
    .sources {
      margin-top: 0.6rem;
      border-top: 1px dashed var(--border);
      padding-top: 0.5rem;
    }
    .sources-title {
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
      font-weight: 700;
    }
    .source {
      font-size: 0.82rem;
      color: var(--text-dim);
      margin-top: 0.25rem;
      display: flex;
      gap: 0.4rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .meta {
      margin-top: 0.5rem;
      font-size: 0.75rem;
      color: var(--text-dim);
    }
    .composer {
      display: flex;
      gap: 0.5rem;
      margin-top: 0.9rem;
    }
    .chunks {
      margin-top: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
      max-height: 420px;
      overflow-y: auto;
    }
    .chunk {
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.6rem 0.7rem;
      background: var(--surface-2);
    }
    .chunk.discarded {
      opacity: 0.5;
    }
    .chunk p {
      margin: 0.4rem 0 0;
      font-size: 0.82rem;
      color: var(--text-dim);
      white-space: pre-wrap;
    }
  `,
})
export class PlaygroundComponent implements OnInit {
  readonly chat = inject(AgentChatService);
  private readonly agents = inject(AgentBuilderService);
  private readonly machinesService = inject(MachinesService);

  /** Umbral REAL del backend, vía GET /agent/settings (D-053). El 0.65 solo es el fallback
   * mientras la petición no responde: antes era una copia hardcodeada que se desincronizaba en
   * silencio al tocar el .env. */
  readonly maxDistance = signal(0.65);
  readonly topK = signal(5);

  readonly machines = signal<Machine[]>([]);
  readonly chunks = signal<RetrievedChunk[] | null>(null);
  readonly inspecting = signal(false);

  /** Contexto que puede llegar desde otra pestaña con "Test in playground" (?machine=). */
  readonly machine = input<string | undefined>();

  machineId: string | null = null;
  question = '';
  probe = '';

  ngOnInit(): void {
    this.agents.settings().subscribe((settings) => {
      this.maxDistance.set(settings.rag_max_distance);
      this.topK.set(settings.rag_top_k);
    });
    this.machinesService.list().subscribe((machines) => {
      this.machines.set(machines);
      // Si otra pestaña indicó el equipo, gana. Si no, se preselecciona el primero: sin contexto
      // el agente no tiene manual que citar y la demo arrancaría con una respuesta genérica.
      const requested = this.machine();
      this.machineId =
        (requested && machines.some((m) => m.id === requested) ? requested : null) ??
        machines[0]?.id ??
        null;
    });
  }

  // El ciclo de vida del socket vive en `AgentLayoutComponent`: si se desconectara aquí, cambiar
  // de pestaña para consultar un documento mataría la conversación en curso.

  onMachineChange(): void {
    // Cambiar de equipo cambia el corpus: seguir el hilo anterior mezclaría dos máquinas.
    this.chat.reset();
    this.chunks.set(null);
  }

  send(): void {
    const text = this.question.trim();
    if (!text) {
      return;
    }
    this.chat.send(text, this.machineId);
    this.question = '';
  }

  inspect(): void {
    this.inspecting.set(true);
    this.agents
      .retrievalTest({ query: this.probe, machine_model_id: this.machineId, top_k: this.topK() })
      .subscribe({
        next: (chunks) => {
          this.chunks.set(chunks);
          this.inspecting.set(false);
        },
        error: () => {
          this.chunks.set([]);
          this.inspecting.set(false);
        },
      });
  }
}
