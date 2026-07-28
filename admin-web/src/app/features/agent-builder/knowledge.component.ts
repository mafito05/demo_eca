import { Component, OnDestroy, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AgentBuilderService } from '../../core/services/agent-builder.service';
import { MachinesService } from '../../core/services/machines.service';
import { KnowledgeDocument, Machine } from '../../core/models/api.models';

/**
 * Base de conocimiento del RAG.
 *
 * La indexación es asíncrona (worker Celery), así que el panel hace polling del estado mientras
 * haya documentos en `pending`/`processing`. El polling se detiene solo cuando todo termina y al
 * destruir el componente: un intervalo huérfano seguiría golpeando el API en segundo plano.
 */
@Component({
  selector: 'app-knowledge',
  imports: [FormsModule],
  template: `
    <p class="hint" style="margin: -0.5rem 0 1rem">
      Manuals and transcripts the agent uses to answer. They are chunked by section and vectorised
      into pgvector.
    </p>

    @if (message()) {
      <div class="alert" [class.error]="messageIsError()" [class.info]="!messageIsError()">
        {{ message() }}
      </div>
    }

    <div class="split">
      <section class="card">
        <div class="row" style="justify-content: space-between; margin-bottom: 0.8rem">
          <h2 style="margin:0">Documents</h2>
          @if (polling()) {
            <span class="row"><span class="spinner"></span> indexing…</span>
          }
        </div>

        @if (documents().length === 0) {
          <div class="empty">No documents. The agent will have nothing to cite.</div>
        } @else {
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Scope</th>
                <th>Status</th>
                <th>Chunks</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (document of documents(); track document.id) {
                <tr>
                  <td>{{ document.title }}</td>
                  <td>{{ scopeLabel(document) }}</td>
                  <td>
                    <span
                      class="badge"
                      [class.ok]="document.status === 'indexed'"
                      [class.warn]="
                        document.status === 'pending' || document.status === 'processing'
                      "
                      [class.danger]="document.status === 'failed'"
                    >
                      {{ document.status }}
                    </span>
                  </td>
                  <td>{{ document.chunk_count }}</td>
                  <td>
                    <button class="small" (click)="reindex(document)">Reindex</button>
                  </td>
                </tr>
                @if (document.error_message) {
                  <tr>
                    <td colspan="5" class="hint" style="color: var(--warn)">
                      {{ document.error_message }}
                    </td>
                  </tr>
                }
              }
            </tbody>
          </table>
          <p class="hint">
            Reindexing is mandatory after changing the chunking or the embedding model: old chunks
            would stay in the table and contaminate the answers.
          </p>
        }
      </section>

      <section class="card">
        <h2>Add document</h2>
        <form (ngSubmit)="save()">
          <div class="field">
            <label for="title">Title</label>
            <input id="title" name="title" [(ngModel)]="draft.title" required />
            <p class="hint">Used in the citations the agent shows. Make it recognisable.</p>
          </div>

          <div class="field">
            <label for="scope">Equipment</label>
            <select id="scope" name="scope" [(ngModel)]="draft.machine_model_id">
              <option [ngValue]="null">Global (visible to all)</option>
              @for (machine of machines(); track machine.id) {
                <option [ngValue]="machine.id">{{ machine.code }} — {{ machine.name }}</option>
              }
            </select>
          </div>

          <div class="field">
            <label for="type">Type</label>
            <select id="type" name="type" [(ngModel)]="draft.source_type">
              <option value="raw_text">Text (pasted manual)</option>
              <option value="video_transcript">Video transcript</option>
            </select>
            <p class="hint">
              PDF upload with text extraction is implemented in the backend; this screen exposes
              direct pasting, which is what the demo uses.
            </p>
          </div>

          <div class="field">
            <label for="text">Content</label>
            <textarea
              id="text"
              name="text"
              [(ngModel)]="draft.raw_text"
              style="min-height: 220px"
              placeholder="4. COMMON FAULT RESOLUTION&#10;E-204  Transducer continuity failure…"
            ></textarea>
            <p class="hint">
              If the text uses numbered headings (<code>4. TITLE</code>), the chunker respects them
              and citations include the exact section.
            </p>
          </div>

          <button
            class="primary"
            type="submit"
            [disabled]="saving() || !draft.title || !draft.raw_text"
          >
            Save and vectorise
          </button>
        </form>
      </section>
    </div>
  `,
  styles: ``,
})
export class KnowledgeComponent implements OnDestroy {
  private readonly service = inject(AgentBuilderService);
  private readonly machinesService = inject(MachinesService);

  readonly documents = signal<KnowledgeDocument[]>([]);
  readonly machines = signal<Machine[]>([]);
  readonly saving = signal(false);
  readonly polling = signal(false);
  readonly message = signal<string | null>(null);
  readonly messageIsError = signal(false);

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  draft = {
    title: '',
    source_type: 'raw_text' as 'raw_text' | 'video_transcript',
    machine_model_id: null as string | null,
    raw_text: '',
  };

  constructor() {
    this.machinesService.list().subscribe((list) => this.machines.set(list));
    this.load();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  scopeLabel(document: KnowledgeDocument): string {
    if (!document.machine_model_id) {
      return 'Global';
    }
    return this.machines().find((m) => m.id === document.machine_model_id)?.code ?? '—';
  }

  private load(): void {
    this.service.listDocuments().subscribe((list) => {
      this.documents.set(list);
      const busy = list.some((doc) => doc.status === 'pending' || doc.status === 'processing');
      busy ? this.startPolling() : this.stopPolling();
    });
  }

  private startPolling(): void {
    if (this.pollTimer) {
      return;
    }
    this.polling.set(true);
    this.pollTimer = setInterval(() => this.load(), 3000);
  }

  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this.polling.set(false);
  }

  save(): void {
    this.saving.set(true);
    this.service
      .createDocument({
        title: this.draft.title,
        source_type: this.draft.source_type,
        machine_model_id: this.draft.machine_model_id,
        raw_text: this.draft.raw_text,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.draft = { ...this.draft, title: '', raw_text: '' };
          this.notify('Document queued for vectorisation.', false);
          this.load();
        },
        error: (err) => {
          this.saving.set(false);
          this.notify(
            err?.error?.detail === undefined
              ? 'Could not save the document.'
              : `Could not save: ${JSON.stringify(err.error.detail).slice(0, 200)}`,
            true,
          );
        },
      });
  }

  reindex(document: KnowledgeDocument): void {
    this.service.reindexDocument(document.id).subscribe({
      next: () => {
        this.notify(`"${document.title}" queued for reindexing.`, false);
        this.load();
      },
      error: () => this.notify('Could not queue the reindex.', true),
    });
  }

  private notify(text: string, isError: boolean): void {
    this.message.set(text);
    this.messageIsError.set(isError);
  }
}
