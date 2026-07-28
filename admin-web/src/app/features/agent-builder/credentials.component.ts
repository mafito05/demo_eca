import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AgentBuilderService } from '../../core/services/agent-builder.service';
import { LlmProvider, ProviderCredential, ProviderSpec } from '../../core/models/api.models';

/**
 * Credenciales de proveedores LLM. Solo `superadmin`.
 *
 * La clave se envía una vez y **nunca vuelve**: el backend la cifra con Fernet y la API solo
 * expone los últimos 4 caracteres. Si se pierde, se sustituye. El botón "Probar" existe para
 * que un error de clave se descubra aquí y no en medio de una demo delante del cliente.
 */
@Component({
  selector: 'app-credentials',
  imports: [FormsModule],
  template: `
    <p class="hint" style="margin: -0.5rem 0 1rem">
      Provider API keys, encrypted at rest. The agent uses the active credential of the provider it
      is configured with.
    </p>

    @if (message()) {
      <div class="alert" [class.error]="messageIsError()" [class.info]="!messageIsError()">
        {{ message() }}
      </div>
    }

    <div class="split wide-left">
      <section class="card">
        <h2>Registered credentials</h2>
        @if (credentials().length === 0) {
          <div class="empty">No credentials. The agent will not be able to answer.</div>
        } @else {
          <table>
            <thead>
              <tr>
                <th>Provider</th>
                <th>Label</th>
                <th>Key</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (credential of credentials(); track credential.id) {
                <tr>
                  <td>{{ displayName(credential.provider) }}</td>
                  <td class="mono">{{ credential.label }}</td>
                  <td class="mono">{{ credential.api_key_masked }}</td>
                  <td>
                    @if (credential.last_check_ok === true) {
                      <span class="badge ok">verified</span>
                    } @else if (credential.last_check_ok === false) {
                      <span class="badge danger" [title]="credential.last_check_error ?? ''">
                        failing
                      </span>
                    } @else {
                      <span class="badge">untested</span>
                    }
                    @if (!credential.is_active) {
                      <span class="badge warn">inactive</span>
                    }
                  </td>
                  <td>
                    <button
                      class="small"
                      (click)="test(credential)"
                      [disabled]="testing() === credential.id"
                    >
                      @if (testing() === credential.id) {
                        <span class="spinner"></span>
                      } @else {
                        Test
                      }
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
          @for (credential of credentials(); track credential.id) {
            @if (credential.last_check_ok === false && credential.last_check_error) {
              <p class="hint" style="color: var(--danger)">
                {{ displayName(credential.provider) }}: {{ credential.last_check_error }}
              </p>
            }
          }
        }
      </section>

      <section class="card">
        <h2>Register credential</h2>
        <form (ngSubmit)="save()">
          <div class="field">
            <label for="provider">Provider</label>
            <select id="provider" name="provider" [(ngModel)]="draft.provider">
              @for (spec of providers(); track spec.key) {
                <option [ngValue]="spec.key">{{ spec.display_name }}</option>
              }
            </select>
            @if (selectedSpec()?.api_key_url) {
              <p class="hint">
                Get the key:
                <a [href]="selectedSpec()!.api_key_url" target="_blank" rel="noopener">
                  {{ selectedSpec()!.api_key_url }}
                </a>
              </p>
            }
          </div>

          <div class="field">
            <label for="label">Label</label>
            <input id="label" name="label" [(ngModel)]="draft.label" />
            <p class="hint">
              Useful to separate accounts or environments. Only one active per provider.
            </p>
          </div>

          <div class="field">
            <label for="apiKey">API key</label>
            <input id="apiKey" name="apiKey" type="password" [(ngModel)]="draft.api_key" required />
            <p class="hint">
              Encrypted before storage and never returned, not even to a superadmin. If lost,
              replace it.
            </p>
          </div>

          @if (selectedSpec()?.requires_base_url) {
            <div class="field">
              <label for="baseUrl">Base URL</label>
              <input
                id="baseUrl"
                name="baseUrl"
                [(ngModel)]="draft.base_url"
                [placeholder]="selectedSpec()!.default_base_url ?? ''"
              />
              <p class="hint">
                This provider speaks the OpenAI protocol with a different endpoint. Empty = the
                default.
              </p>
            </div>
          }

          <button class="primary" type="submit" [disabled]="saving() || !draft.api_key">
            Save
          </button>
        </form>
      </section>
    </div>
  `,
  styles: ``,
})
export class CredentialsComponent {
  private readonly service = inject(AgentBuilderService);

  readonly providers = signal<ProviderSpec[]>([]);
  readonly credentials = signal<ProviderCredential[]>([]);
  readonly saving = signal(false);
  readonly testing = signal<string | null>(null);
  readonly message = signal<string | null>(null);
  readonly messageIsError = signal(false);

  draft: { provider: LlmProvider; label: string; api_key: string; base_url: string } = {
    provider: 'openai',
    label: 'default',
    api_key: '',
    base_url: '',
  };

  constructor() {
    this.service.listProviders().subscribe((specs) => this.providers.set(specs));
    this.load();
  }

  selectedSpec(): ProviderSpec | undefined {
    return this.providers().find((spec) => spec.key === this.draft.provider);
  }

  displayName(provider: LlmProvider): string {
    return this.providers().find((spec) => spec.key === provider)?.display_name ?? provider;
  }

  private load(): void {
    this.service.listCredentials().subscribe((list) => this.credentials.set(list));
  }

  save(): void {
    this.saving.set(true);
    this.service
      .createCredential({
        provider: this.draft.provider,
        label: this.draft.label || 'default',
        api_key: this.draft.api_key,
        base_url: this.draft.base_url || null,
        is_active: true,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.draft.api_key = '';
          this.notify('Credential saved and encrypted. Worth testing it now.', false);
          this.load();
        },
        error: (err) => {
          this.saving.set(false);
          this.notify(
            err?.status === 409
              ? 'A credential with that provider and label already exists.'
              : 'Could not save the credential.',
            true,
          );
        },
      });
  }

  test(credential: ProviderCredential): void {
    this.testing.set(credential.id);
    this.service.testCredential(credential.id).subscribe({
      next: (result) => {
        this.testing.set(null);
        this.notify(
          result.ok
            ? `Connection to ${this.displayName(credential.provider)} works (${result.latency_ms} ms).`
            : `Failed: ${result.message}`,
          !result.ok,
        );
        this.load();
      },
      error: () => {
        this.testing.set(null);
        this.notify('Could not run the connectivity test.', true);
      },
    });
  }

  private notify(text: string, isError: boolean): void {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
