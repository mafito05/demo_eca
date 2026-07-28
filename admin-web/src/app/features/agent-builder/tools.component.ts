import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AgentBuilderService } from '../../core/services/agent-builder.service';
import { ToolDefinition } from '../../core/models/api.models';

/**
 * Registro de herramientas HTTP que el LLM puede invocar. Solo `superadmin`.
 *
 * Es la pantalla más peligrosa del panel: registra URLs que el backend llamará, y quien decide
 * cuándo llamarlas es un modelo influenciable por el texto que escribe el usuario final. La UI
 * lo dice con claridad en lugar de esconderlo, y el backend valida en cada invocación (allowlist
 * de hosts, rechazo de IPs internas, timeout y tamaño máximo de respuesta).
 */
@Component({
  selector: 'app-tools',
  imports: [FormsModule],
  template: `
    <p class="hint" style="margin: -0.5rem 0 1rem">
      External APIs the agent can call through function calling.
    </p>

    <div class="alert warn">
      <strong>Sensitive surface.</strong> The backend only allows hosts listed in
      <code>TOOL_ALLOWED_HOSTS</code> and rejects any destination that resolves to an internal
      address, including the cloud metadata endpoint. With an empty list no tool runs at all:
      restrictive by default, on purpose.
    </div>

    @if (message()) {
      <div class="alert" [class.error]="messageIsError()" [class.info]="!messageIsError()">
        {{ message() }}
      </div>
    }

    <div class="split">
      <section class="card">
        <h2>Registered</h2>
        @if (tools().length === 0) {
          <div class="empty">No tools registered.</div>
        } @else {
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Target</th>
                <th>Confirmation</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (tool of tools(); track tool.id) {
                <tr>
                  <td class="mono">{{ tool.name }}</td>
                  <td class="mono trunc">{{ tool.http_method }} {{ tool.url_template }}</td>
                  <td>
                    @if (tool.requires_confirmation) {
                      <span class="badge warn">required</span>
                    } @else {
                      <span class="badge">automatic</span>
                    }
                  </td>
                  <td>
                    <span class="badge" [class.ok]="tool.is_active">
                      {{ tool.is_active ? 'active' : 'inactive' }}
                    </span>
                  </td>
                  <td>
                    @if (tool.is_active) {
                      <button class="small" (click)="deactivate(tool)">Disable</button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <p class="hint">
            Disabling does not delete: the audit table keeps the reference for every run.
          </p>
        }
      </section>

      <section class="card">
        <h2>Register tool</h2>
        <form (ngSubmit)="save()">
          <div class="field">
            <label for="name">Function name</label>
            <input
              id="name"
              name="name"
              [(ngModel)]="draft.name"
              placeholder="consultar_estado_equipo"
            />
            <p class="hint">
              snake_case, no spaces or accents: this is the identifier the LLM sees, and providers
              reject other formats.
            </p>
          </div>

          <div class="field">
            <label for="description">Description</label>
            <textarea
              id="description"
              name="description"
              [(ngModel)]="draft.description"
              style="min-height: 70px"
              placeholder="Look up the current operational status of a machine by serial number."
            ></textarea>
            <p class="hint">
              This is <strong>prompt</strong> text, not internal documentation: it is what the model
              uses to decide whether to call the tool.
            </p>
          </div>

          <div class="grid cols-2">
            <div class="field">
              <label for="method">Method</label>
              <select id="method" name="method" [(ngModel)]="draft.http_method">
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="PATCH">PATCH</option>
                <option value="DELETE">DELETE</option>
              </select>
            </div>
            <div class="field">
              <label for="timeout">Timeout (s)</label>
              <input
                id="timeout"
                name="timeout"
                type="number"
                min="1"
                max="60"
                [(ngModel)]="draft.timeout_seconds"
              />
            </div>
          </div>

          <div class="field">
            <label for="url">URL</label>
            <input
              id="url"
              name="url"
              [(ngModel)]="draft.url_template"
              placeholder="https://api.ejemplo.com/equipos/{serial}/estado"
            />
            <p class="hint">
              Path parameters in braces are supported. They are substituted with escaping, so a
              value containing <code>/</code> cannot inject extra segments.
            </p>
          </div>

          <div class="field">
            <label for="schema">Parameters JSON Schema</label>
            <textarea
              id="schema"
              name="schema"
              [(ngModel)]="schemaText"
              style="min-height: 130px"
            ></textarea>
            @if (schemaError()) {
              <p class="hint" style="color: var(--danger)">{{ schemaError() }}</p>
            }
          </div>

          <div class="row" style="margin-bottom: 1rem">
            <label class="check">
              <input type="checkbox" name="confirm" [(ngModel)]="draft.requires_confirmation" />
              Requires user confirmation
            </label>
          </div>
          <p class="hint" style="margin-top:-0.6rem; margin-bottom:1rem">
            Leave it checked for anything that is not read-only. A model must not be able to trigger
            side effects on its own.
          </p>

          <div class="row">
            <label class="check">
              <input type="checkbox" name="active" [(ngModel)]="draft.is_active" />
              Activate on save
            </label>
          </div>

          <button class="primary" type="submit" style="margin-top:1rem" [disabled]="saving()">
            Register
          </button>
        </form>
      </section>
    </div>
  `,
  styles: `
    .trunc {
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .check {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      text-transform: none;
      letter-spacing: normal;
      font-size: 0.85rem;
      color: var(--text);
      margin: 0;
    }
    .check input {
      width: auto;
    }
  `,
})
export class ToolsComponent {
  private readonly service = inject(AgentBuilderService);

  readonly tools = signal<ToolDefinition[]>([]);
  readonly saving = signal(false);
  readonly schemaError = signal<string | null>(null);
  readonly message = signal<string | null>(null);
  readonly messageIsError = signal(false);

  schemaText = JSON.stringify(
    {
      type: 'object',
      properties: { serial: { type: 'string', description: 'Equipment serial number.' } },
      required: ['serial'],
    },
    null,
    2,
  );

  draft = {
    name: '',
    description: '',
    http_method: 'GET',
    url_template: '',
    requires_confirmation: true,
    timeout_seconds: 15,
    is_active: false,
  };

  constructor() {
    this.load();
  }

  private load(): void {
    this.service.listTools().subscribe((list) => this.tools.set(list));
  }

  save(): void {
    let schema: Record<string, unknown>;
    try {
      schema = JSON.parse(this.schemaText);
      this.schemaError.set(null);
    } catch (error) {
      this.schemaError.set(`Invalid JSON: ${(error as Error).message}`);
      return;
    }

    this.saving.set(true);
    this.service
      .createTool({
        ...this.draft,
        parameters_schema: schema,
        timeout_seconds: Number(this.draft.timeout_seconds),
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.notify('Tool registered.', false);
          this.load();
        },
        error: (err) => {
          this.saving.set(false);
          // El 422 aquí suele venir de la validación anti-SSRF, y su mensaje explica exactamente
          // qué política se incumplió. Mostrarlo tal cual ahorra media hora de depuración.
          const detail = err?.error?.detail;
          this.notify(typeof detail === 'string' ? detail : 'Could not register the tool.', true);
        },
      });
  }

  deactivate(tool: ToolDefinition): void {
    this.service.deactivateTool(tool.id).subscribe({
      next: () => {
        this.notify(`"${tool.name}" disabled.`, false);
        this.load();
      },
      error: () => this.notify('Could not disable it.', true),
    });
  }

  private notify(text: string, isError: boolean): void {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
