import { Component, OnDestroy, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { MachinesService } from '../../core/services/machines.service';
import { Machine, PublishStatus, QrExport, Specialty } from '../../core/models/api.models';

/**
 * Catálogo de equipos y panel de QR.
 *
 * El QR se genera en el backend y se descarga autenticado, así que no se puede pintar con un
 * `<img src="/api/...">`: una etiqueta `img` no envía la cabecera `Authorization`. Se pide como
 * blob y se convierte en object URL, revocándola después para no filtrar memoria.
 */
@Component({
  selector: 'app-machines',
  imports: [FormsModule],
  template: `
    <div class="page">
      <div class="page-head">
        <h1>Equipment &amp; QR codes</h1>
        <p>
          Each equipment model has a QR code that is printed and stuck on the physical machines.
          Scanning it opens that equipment's training in the app.
        </p>
      </div>

      @if (error()) {
        <div class="alert error">{{ error() }}</div>
      }

      <div class="split wide-left">
        <section class="card">
          <div class="row" style="justify-content: space-between; margin-bottom: 0.8rem">
            <h2 style="margin:0">Catalogue</h2>
            <button class="small" (click)="toggleForm()">
              {{ formOpen() ? 'Cancel' : 'New machine' }}
            </button>
          </div>

          @if (formOpen()) {
            <form class="new" (ngSubmit)="save()">
              <div class="grid cols-2">
                <div class="field">
                  <label for="code">Internal code</label>
                  <input
                    id="code"
                    name="code"
                    [(ngModel)]="draft.code"
                    placeholder="URO-LITHO-3000"
                    required
                  />
                  <p class="hint">The identifier the business uses. Exported alongside the QR.</p>
                </div>
                <div class="field">
                  <label for="name">Name</label>
                  <input id="name" name="name" [(ngModel)]="draft.name" required />
                </div>
                <div class="field">
                  <label for="manufacturer">Manufacturer</label>
                  <input id="manufacturer" name="manufacturer" [(ngModel)]="draft.manufacturer" />
                </div>
                <div class="field">
                  <label for="specialty">Specialty</label>
                  <select id="specialty" name="specialty" [(ngModel)]="draft.specialty">
                    @for (option of specialties; track option) {
                      <option [ngValue]="option">{{ option }}</option>
                    }
                  </select>
                </div>
                <div class="field">
                  <label for="mstatus">Status</label>
                  <select id="mstatus" name="mstatus" [(ngModel)]="draft.status">
                    <option value="draft">draft</option>
                    <option value="published">published</option>
                    <option value="archived">archived</option>
                  </select>
                  <p class="hint">
                    Only <code>published</code> machines appear in the mobile catalogue.
                  </p>
                </div>
                <div class="field" style="grid-column: 1 / -1">
                  <label for="mdesc">Description</label>
                  <input id="mdesc" name="mdesc" [(ngModel)]="draft.description" />
                </div>
              </div>
              <button class="primary" type="submit" [disabled]="saving()">
                {{ editingId() ? 'Save changes' : 'Create machine' }}
              </button>
            </form>
          }

          @if (machines().length === 0) {
            <div class="empty">No machines yet.</div>
          } @else {
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Specialty</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                @for (machine of machines(); track machine.id) {
                  <tr [class.selected]="selected()?.id === machine.id">
                    <td class="mono">{{ machine.code }}</td>
                    <td>{{ machine.name }}</td>
                    <td>{{ machine.specialty }}</td>
                    <td>
                      <span class="badge" [class.ok]="machine.status === 'published'">
                        {{ machine.status }}
                      </span>
                    </td>
                    <td>
                      <div class="row" style="gap: 0.3rem; flex-wrap: nowrap">
                        <button class="small" (click)="select(machine)">View QR</button>
                        <button class="small" (click)="edit(machine)">Edit</button>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </section>

        <section class="card">
          <h2>QR code</h2>
          @if (!selected()) {
            <div class="empty">Pick a machine to view and print its QR code.</div>
          } @else {
            <p class="hint" style="margin-top:-0.4rem">
              {{ selected()!.code }} — {{ selected()!.name }}
            </p>

            @if (qrImageUrl()) {
              <div class="qr-frame">
                <img [src]="qrImageUrl()" alt="QR code for {{ selected()!.code }}" />
              </div>
            } @else {
              <div class="empty"><span class="spinner"></span></div>
            }

            <div class="row" style="margin-top: 0.8rem">
              <button class="small" (click)="download('png')">Download PNG</button>
              <button class="small" (click)="download('svg')">Download SVG</button>
            </div>
            <p class="hint">
              SVG is what a print shop needs for labels at any size. The QR uses high error
              correction: these codes sit on equipment that gets disinfected and scuffed.
            </p>

            @if (qrData()) {
              <div class="field" style="margin-top: 1rem">
                <label>Data for export to other systems</label>
                <div class="export">
                  <div>
                    <span>QR URL</span><code>{{ qrData()!.qr_url }}</code>
                  </div>
                  <div>
                    <span>Custom scheme</span><code>{{ qrData()!.qr_custom_scheme }}</code>
                  </div>
                  <div>
                    <span>Token</span><code>{{ qrData()!.qr_token }}</code>
                  </div>
                </div>
                <p class="hint">
                  The QR encodes the <code>https</code> URL, not the custom scheme: if the app is
                  not installed, a URL lands on a web page, whereas <code>demoeca://</code> would
                  leave a dead code stuck to the machine.
                </p>
              </div>
            }
          }
        </section>
      </div>
    </div>
  `,
  styles: `
    tr.selected td {
      background: var(--surface-2);
    }
    .new {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem;
      margin-bottom: 1rem;
      background: var(--surface-2);
    }
    .qr-frame {
      display: grid;
      place-items: center;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem;
    }
    .qr-frame img {
      width: 100%;
      max-width: 240px;
      image-rendering: pixelated;
    }
    .export div {
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
      margin-bottom: 0.5rem;
    }
    .export span {
      font-size: 0.7rem;
      text-transform: uppercase;
      color: var(--text-dim);
      letter-spacing: 0.04em;
    }
    .export code {
      word-break: break-all;
      background: var(--surface-2);
      padding: 0.25rem 0.4rem;
      border-radius: 4px;
    }
  `,
})
export class MachinesComponent implements OnDestroy {
  private readonly service = inject(MachinesService);

  readonly specialties: Specialty[] = ['urologia', 'trauma', 'cardiologia', 'neurocirugia', 'otro'];

  readonly machines = signal<Machine[]>([]);
  readonly selected = signal<Machine | null>(null);
  readonly qrImageUrl = signal<string | null>(null);
  readonly qrData = signal<QrExport | null>(null);
  readonly formOpen = signal(false);
  readonly editingId = signal<string | null>(null);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  draft = {
    code: '',
    name: '',
    manufacturer: '',
    description: '',
    specialty: 'otro' as Specialty,
    status: 'draft' as PublishStatus,
  };

  constructor() {
    this.load();
  }

  ngOnDestroy(): void {
    this.revokeQr();
  }

  private load(): void {
    this.service.list().subscribe({
      next: (machines) => {
        this.machines.set(machines);
        if (!this.selected() && machines.length) {
          this.select(machines[0]);
        }
      },
      error: () => this.error.set('Could not load the equipment catalogue.'),
    });
  }

  select(machine: Machine): void {
    this.selected.set(machine);
    this.revokeQr();
    this.qrData.set(null);

    this.service.qrImage(machine.id, 'png').subscribe({
      next: (blob) => this.qrImageUrl.set(URL.createObjectURL(blob)),
      error: () => this.error.set('Could not generate the QR image.'),
    });
    this.service.qrData(machine.id).subscribe((data) => this.qrData.set(data));
  }

  download(format: 'png' | 'svg'): void {
    const machine = this.selected();
    if (!machine) {
      return;
    }
    this.service.qrImage(machine.id, format).subscribe((blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `qr-${machine.code}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  toggleForm(): void {
    if (this.formOpen()) {
      this.resetForm();
    } else {
      this.formOpen.set(true);
    }
  }

  /** Precarga el formulario de alta con la máquina: mismo form, modo edición (PATCH). */
  edit(machine: Machine): void {
    this.editingId.set(machine.id);
    this.formOpen.set(true);
    this.draft = {
      code: machine.code,
      name: machine.name,
      manufacturer: machine.manufacturer ?? '',
      description: machine.description ?? '',
      specialty: machine.specialty,
      status: machine.status,
    };
  }

  save(): void {
    this.saving.set(true);
    this.error.set(null);

    const payload = {
      code: this.draft.code,
      name: this.draft.name,
      manufacturer: this.draft.manufacturer || null,
      description: this.draft.description || null,
      specialty: this.draft.specialty,
      // `status` editable: sin esto, una máquina creada desde el panel nacía en draft y no
      // había forma de publicarla jamás — su capacitación era invisible para la app (D-052).
      status: this.draft.status,
    };
    const editingId = this.editingId();
    const request = editingId
      ? this.service.update(editingId, payload)
      : this.service.create(payload);

    request.subscribe({
      next: () => {
        this.saving.set(false);
        this.resetForm();
        this.load();
      },
      error: (err) => {
        this.saving.set(false);
        this.error.set(
          err?.status === 409
            ? 'A machine with that internal code already exists.'
            : `Could not save the machine (HTTP ${err?.status ?? 'network error'}).`,
        );
      },
    });
  }

  private resetForm(): void {
    this.formOpen.set(false);
    this.editingId.set(null);
    this.draft = {
      code: '',
      name: '',
      manufacturer: '',
      description: '',
      specialty: 'otro',
      status: 'draft',
    };
  }

  /** Las object URL no se liberan solas: sin esto, cada QR visto deja el blob en memoria. */
  private revokeQr(): void {
    const url = this.qrImageUrl();
    if (url) {
      URL.revokeObjectURL(url);
      this.qrImageUrl.set(null);
    }
  }
}
