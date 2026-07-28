import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { IconComponent } from '../../shared/icon/icon.component';

import { AgentBuilderService } from '../../core/services/agent-builder.service';
import { MachinesService } from '../../core/services/machines.service';
import {
  AgentConfig,
  BasePromptRead,
  LlmProvider,
  Machine,
  PromptPreview,
  ProviderSpec,
} from '../../core/models/api.models';

/**
 * Configuración de agentes: proveedor, modelo, temperatura y prompt adicional.
 *
 * Un agente sin `machine_model_id` es el global (fallback). Con valor, sobreescribe el
 * comportamiento para ese equipo concreto sin duplicar toda la configuración.
 */
@Component({
  selector: 'app-agent-config',
  imports: [FormsModule, RouterLink, IconComponent],
  template: `
    <p class="hint" style="margin: -0.5rem 0 1rem">
      The default agent serves any equipment. A machine-specific one can be created to tune its
      prompt or use a different model.
    </p>

    @if (message()) {
      <div class="alert" [class.error]="messageIsError()" [class.info]="!messageIsError()">
        {{ message() }}
      </div>
    }

    <div class="split even">
      <section class="card">
        <h2>Configured</h2>
        @if (configs().length === 0) {
          <div class="empty">No agents configured.</div>
        } @else {
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Model</th>
                <th>Scope</th>
                <th>RAG</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (config of configs(); track config.id) {
                <tr>
                  <td>
                    {{ config.name }}
                    @if (config.is_default) {
                      <span class="badge ok">default</span>
                    }
                    @if (!config.is_active) {
                      <span class="badge warn">inactive</span>
                    }
                  </td>
                  <td class="mono">{{ config.provider }}/{{ config.model_name }}</td>
                  <td>{{ scopeLabel(config) }}</td>
                  <td>
                    @if (config.rag_enabled) {
                      <span class="badge ok">top {{ config.rag_top_k }}</span>
                    } @else {
                      <span class="badge">off</span>
                    }
                  </td>
                  <td>
                    <div class="row" style="gap: 0.35rem; flex-wrap: nowrap">
                      <button class="small" (click)="edit(config)">Edit</button>
                      <!-- Lleva el contexto a la pestaña de prueba. El hilo del chat sobrevive
                             al cambio de pestaña porque el socket vive en el layout (D-042). -->
                      <a
                        class="badge accent"
                        [routerLink]="['../playground']"
                        [queryParams]="{ machine: config.machine_model_id }"
                        title="Open the playground with this agent's equipment context"
                      >
                        Test
                      </a>
                    </div>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </section>

      <section class="card">
        <h2>{{ editing() ? 'Edit agent' : 'New agent' }}</h2>
        <form (ngSubmit)="save()">
          <div class="field">
            <label for="name">Name</label>
            <input id="name" name="name" [(ngModel)]="draft.name" required />
          </div>

          <div class="grid cols-2">
            <div class="field">
              <label for="provider">Provider</label>
              <select
                id="provider"
                name="provider"
                [(ngModel)]="draft.provider"
                (ngModelChange)="onProviderChange()"
              >
                @for (spec of providers(); track spec.key) {
                  <option [ngValue]="spec.key">{{ spec.display_name }}</option>
                }
              </select>
            </div>
            <div class="field">
              <label for="model">Model</label>
              <input
                id="model"
                name="model"
                [(ngModel)]="draft.model_name"
                list="models"
                required
              />
              <datalist id="models">
                @for (model of suggestedModels(); track model) {
                  <option [value]="model"></option>
                }
              </datalist>
              <p class="hint">
                Free text on purpose: providers ship new models every few weeks and a closed list
                would require a backend deploy.
              </p>
            </div>
          </div>

          <div class="grid cols-2">
            <div class="field">
              <label for="temperature">Temperature ({{ draft.temperature }})</label>
              <input
                id="temperature"
                name="temperature"
                type="range"
                min="0"
                max="1"
                step="0.1"
                [(ngModel)]="draft.temperature"
              />
              <p class="hint">Low for technical documentation: fidelity matters, not creativity.</p>
            </div>
            <div class="field">
              <label for="maxTokens">Max tokens</label>
              <input
                id="maxTokens"
                name="maxTokens"
                type="number"
                min="64"
                max="32000"
                [(ngModel)]="draft.max_tokens"
              />
            </div>
          </div>

          <div class="field">
            <label for="scope">Scope</label>
            <select id="scope" name="scope" [(ngModel)]="draft.machine_model_id">
              <option [ngValue]="null">Global (all equipment)</option>
              @for (machine of machines(); track machine.id) {
                <option [ngValue]="machine.id">{{ machine.code }} — {{ machine.name }}</option>
              }
            </select>
          </div>

          <div class="field">
            <label for="description">Description</label>
            <input
              id="description"
              name="description"
              [(ngModel)]="draft.description"
              placeholder="What this agent is for"
            />
          </div>

          <!-- Prompt base: visible pero bloqueado (D-006/D-053). Antes ni siquiera se podía VER
               qué reglas llevaba el agente. -->
          <div class="field">
            <details>
              <summary class="hint" style="cursor: pointer">
                <app-icon name="key" [size]="12" /> View the base system prompt (locked)
              </summary>
              <pre class="prompt-view">{{ basePrompt()?.base_prompt || 'Loading…' }}</pre>
              <p class="hint">
                Read-only by design: the clinical guardrails (no dosage, no treatment advice) cannot
                be disabled from a screen. Your instructions below are appended to it.
              </p>
            </details>
          </div>

          <div class="field">
            <label for="prompt">Additional instructions</label>
            <textarea id="prompt" name="prompt" [(ngModel)]="draft.system_prompt_extra"></textarea>
            <div class="alert warn" style="margin-top:0.5rem">
              These are <strong>appended</strong> to the base safety prompt, they do not replace it.
              The clinical guardrails (no dosage, no treatment advice) cannot be disabled from here.
            </div>
          </div>

          <div class="field">
            <label for="suggested">Suggested questions (one per line)</label>
            <textarea
              id="suggested"
              name="suggested"
              [(ngModel)]="suggestedQuestionsText"
              style="min-height: 90px"
              placeholder="What should I do if the unit shows error E-204?"
            ></textarea>
            <p class="hint">
              Shown as tappable examples in the app's empty chat. Empty = the generic backend
              defaults. Max 8.
            </p>
          </div>

          <div class="grid cols-2">
            <div class="field">
              <label for="ragTopK">RAG top-k</label>
              <input
                id="ragTopK"
                name="ragTopK"
                type="number"
                min="1"
                max="20"
                [(ngModel)]="draft.rag_top_k"
              />
              <p class="hint">How many chunks are retrieved per question.</p>
            </div>
          </div>

          <div class="row" style="margin-bottom: 1rem">
            <label class="check">
              <input type="checkbox" name="rag" [(ngModel)]="draft.rag_enabled" />
              RAG enabled
            </label>
            <label class="check">
              <input type="checkbox" name="tools" [(ngModel)]="draft.tools_enabled" />
              HTTP tools
            </label>
            <label class="check">
              <input type="checkbox" name="isDefault" [(ngModel)]="draft.is_default" />
              Default agent
            </label>
            <label class="check">
              <input type="checkbox" name="isActive" [(ngModel)]="draft.is_active" />
              Active
            </label>
          </div>

          <div class="row">
            <button class="primary" type="submit" [disabled]="saving()">
              {{ editing() ? 'Save changes' : 'Create agent' }}
            </button>
            @if (editing()) {
              <button type="button" (click)="resetDraft()">Cancel</button>
              <button type="button" (click)="previewPrompt()">Preview full prompt</button>
            }
          </div>
        </form>

        @if (promptPreview(); as preview) {
          <div class="field" style="margin-top: 1rem">
            <div class="between">
              <label style="margin: 0">Exact prompt the LLM receives</label>
              <button class="small" type="button" (click)="promptPreview.set(null)">Close</button>
            </div>
            <pre class="prompt-view">{{ preview.prompt }}</pre>
            <p class="hint">{{ preview.note }}</p>
          </div>
        }
      </section>
    </div>
  `,
  styles: `
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
    input[type='range'] {
      padding: 0;
    }
    .prompt-view {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 0.75rem;
      font-family: var(--mono);
      font-size: 0.78rem;
      white-space: pre-wrap;
      max-height: 320px;
      overflow-y: auto;
      margin: 0.5rem 0 0;
    }
  `,
})
export class AgentConfigComponent {
  private readonly service = inject(AgentBuilderService);
  private readonly machinesService = inject(MachinesService);

  readonly providers = signal<ProviderSpec[]>([]);
  readonly machines = signal<Machine[]>([]);
  readonly configs = signal<AgentConfig[]>([]);
  readonly editing = signal<string | null>(null);
  readonly saving = signal(false);
  readonly message = signal<string | null>(null);
  readonly messageIsError = signal(false);
  readonly basePrompt = signal<BasePromptRead | null>(null);
  readonly promptPreview = signal<PromptPreview | null>(null);

  draft = this.blankDraft();

  /** El textarea trabaja con texto plano; el API con lista. La conversión vive aquí. */
  suggestedQuestionsText = '';

  constructor() {
    this.service.listProviders().subscribe((specs) => this.providers.set(specs));
    this.machinesService.list().subscribe((list) => this.machines.set(list));
    this.service.basePrompt().subscribe((prompt) => this.basePrompt.set(prompt));
    this.load();
  }

  private blankDraft() {
    return {
      name: '',
      description: '',
      provider: 'openai' as LlmProvider,
      model_name: 'gpt-5-mini',
      temperature: 0.2,
      max_tokens: 1024,
      system_prompt_extra: '',
      rag_enabled: true,
      rag_top_k: 5,
      tools_enabled: false,
      machine_model_id: null as string | null,
      is_default: false,
      is_active: true,
    };
  }

  suggestedModels(): string[] {
    return (
      this.providers().find((spec) => spec.key === this.draft.provider)?.suggested_models ?? []
    );
  }

  scopeLabel(config: AgentConfig): string {
    if (!config.machine_model_id) {
      return 'Global';
    }
    const machine = this.machines().find((item) => item.id === config.machine_model_id);
    return machine ? machine.code : 'Specific machine';
  }

  onProviderChange(): void {
    // Al cambiar de proveedor, el modelo anterior no existe en el nuevo: se propone el primero
    // sugerido en lugar de dejar un valor que fallaría al invocar.
    this.draft.model_name = this.suggestedModels()[0] ?? '';
  }

  private load(): void {
    this.service.listConfigs().subscribe((list) => this.configs.set(list));
  }

  edit(config: AgentConfig): void {
    this.editing.set(config.id);
    this.promptPreview.set(null);
    this.draft = {
      name: config.name,
      description: config.description ?? '',
      provider: config.provider,
      model_name: config.model_name,
      temperature: config.temperature,
      max_tokens: config.max_tokens,
      system_prompt_extra: config.system_prompt_extra ?? '',
      rag_enabled: config.rag_enabled,
      rag_top_k: config.rag_top_k,
      tools_enabled: config.tools_enabled,
      machine_model_id: config.machine_model_id,
      is_default: config.is_default,
      is_active: config.is_active,
    };
    this.suggestedQuestionsText = (config.suggested_questions ?? []).join('\n');
  }

  resetDraft(): void {
    this.editing.set(null);
    this.promptPreview.set(null);
    this.suggestedQuestionsText = '';
    this.draft = this.blankDraft();
  }

  previewPrompt(): void {
    const editingId = this.editing();
    if (!editingId) {
      return;
    }
    this.service.previewPrompt(editingId, this.draft.machine_model_id).subscribe({
      next: (preview) => this.promptPreview.set(preview),
      error: () => {
        this.message.set('Could not compose the prompt preview.');
        this.messageIsError.set(true);
      },
    });
  }

  save(): void {
    this.saving.set(true);
    const payload = {
      ...this.draft,
      // Cadena vacía y null significan lo mismo aquí, pero null es lo que espera el backend.
      system_prompt_extra: this.draft.system_prompt_extra || null,
      description: this.draft.description || null,
      temperature: Number(this.draft.temperature),
      max_tokens: Number(this.draft.max_tokens),
      rag_top_k: Number(this.draft.rag_top_k),
      // Una pregunta por línea; las vacías se descartan y el backend acepta hasta 8.
      suggested_questions: this.suggestedQuestionsText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .slice(0, 8),
    };
    const editingId = this.editing();
    const request = editingId
      ? this.service.updateConfig(editingId, payload)
      : this.service.createConfig(payload);

    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.message.set('Agent saved.');
        this.messageIsError.set(false);
        this.resetDraft();
        this.load();
      },
      error: () => {
        this.saving.set(false);
        this.message.set('Could not save the agent.');
        this.messageIsError.set(true);
      },
    });
  }
}
