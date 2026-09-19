import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { MachinesService } from '../../core/services/machines.service';
import {
  Machine,
  MachineImage,
  PublishStatus,
  QrExport,
  Specialty,
} from '../../core/models/api.models';
import { IconComponent } from '../../shared/icon/icon.component';
import { FileDropComponent } from '../../shared/upload/file-drop.component';

/**
 * Catálogo de equipos y panel de QR.
 *
 * El QR se genera en el backend y se descarga autenticado, así que no se puede pintar con un
 * `<img src="/api/...">`: una etiqueta `img` no envía la cabecera `Authorization`. Se pide como
 * blob y se convierte en object URL, revocándola después para no filtrar memoria.
 */
@Component({
  selector: 'app-machines',
  imports: [FormsModule, IconComponent, FileDropComponent],
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
                  <th class="thumb-col"></th>
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
                    <td class="thumb-col">
                      @if (machine.cover_image_url) {
                        <img class="row-thumb" [src]="machine.cover_image_url" alt="" />
                      } @else {
                        <span class="badge warn" title="This machine has no cover image">none</span>
                      }
                    </td>
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
                        <button class="small" (click)="select(machine)">Open</button>
                        <button class="small" (click)="edit(machine)">Edit</button>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </section>

        <div class="stack">
          <section class="card">
            <div class="card-head">
              <h2>Images</h2>
              @if (selected()) {
                <span class="badge">{{ images().length }}</span>
              }
            </div>

            @if (!selected()) {
              <div class="empty compact">Pick a machine to manage its images.</div>
            } @else {
              <p class="hint" style="margin-top:-0.4rem">
                The primary image is the thumbnail in the mobile catalogue and the cover of the
                equipment page. The rest appear as a gallery inside the equipment.
              </p>

              @if (cover(); as primary) {
                <figure class="cover">
                  <img [src]="primary.url" [alt]="primary.alt_text || 'Cover image'" />
                  <figcaption class="badge accent">primary</figcaption>
                </figure>
              } @else {
                <div class="empty compact">
                  No primary image yet — upload one, or star a picture below.
                </div>
              }

              @if (gallery().length) {
                <div class="thumbs">
                  @for (image of gallery(); track image.id) {
                    <div class="thumb" [class.pending]="!image.is_ready">
                      <img [src]="image.url" [alt]="image.alt_text || ''" />
                      <div class="thumb-actions">
                        <button
                          class="icon-btn"
                          type="button"
                          title="Make primary"
                          (click)="makePrimary(image)"
                        >
                          <app-icon name="star" [size]="14" />
                        </button>
                        <button
                          class="icon-btn"
                          type="button"
                          title="Move left"
                          [disabled]="$first"
                          (click)="moveImage(image, -1)"
                        >
                          <app-icon name="chevron-left" [size]="14" />
                        </button>
                        <button
                          class="icon-btn"
                          type="button"
                          title="Move right"
                          [disabled]="$last"
                          (click)="moveImage(image, 1)"
                        >
                          <app-icon name="chevron-right" [size]="14" />
                        </button>
                        <button
                          class="icon-btn"
                          type="button"
                          title="Delete"
                          (click)="removeImage(image)"
                        >
                          <app-icon name="trash" [size]="14" />
                        </button>
                      </div>
                      @if (!image.is_ready) {
                        <span class="badge warn pending-tag">incomplete</span>
                      }
                    </div>
                  }
                </div>
              }

              <app-file-drop
                style="margin-top: 0.8rem"
                accept="image/jpeg,image/png,image/webp"
                [maxSizeMb]="5"
                label="Drop a product photo here"
                hint="JPEG, PNG or WebP · max 5 MB"
                [busy]="uploadingImage()"
                [progress]="imageProgress()"
                [fileName]="imageFileName()"
                (picked)="onImagePicked($event)"
                (cancel)="cancelImageUpload()"
                (rejected)="onImageRejected($event)"
              />
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
    </div>
  `,
  styles: `
    tr.selected td {
      background: var(--surface-2);
    }
    .thumb-col {
      width: 52px;
    }
    .row-thumb {
      display: block;
      width: 40px;
      height: 28px;
      object-fit: cover;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--surface-2);
    }
    .cover {
      position: relative;
      margin: 0 0 var(--sp-3);
    }
    .cover img {
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface-2);
    }
    .cover figcaption {
      position: absolute;
      top: var(--sp-2);
      left: var(--sp-2);
    }
    .thumbs {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
      gap: var(--sp-2);
    }
    .thumb {
      position: relative;
      aspect-ratio: 4 / 3;
      border-radius: var(--radius-sm);
      overflow: hidden;
      border: 1px solid var(--border);
      background: var(--surface-2);
    }
    .thumb img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .thumb.pending img {
      opacity: 0.45;
    }
    .pending-tag {
      position: absolute;
      top: 2px;
      left: 2px;
    }
    .thumb-actions {
      position: absolute;
      inset: auto 0 0 0;
      display: flex;
      justify-content: center;
      gap: 2px;
      padding: 2px;
      background: var(--surface);
      opacity: 0;
      transition: opacity var(--dur-fast) var(--ease);
    }
    /* focus-within no es decorativo: sin él, las acciones son inalcanzables con teclado. */
    .thumb:hover .thumb-actions,
    .thumb:focus-within .thumb-actions {
      opacity: 1;
    }
    .thumb-actions .icon-btn {
      width: 26px;
      height: 26px;
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

  readonly images = signal<MachineImage[]>([]);
  readonly uploadingImage = signal(false);
  readonly imageProgress = signal<number | null>(null);
  readonly imageFileName = signal<string | null>(null);
  private imageUpload: Subscription | null = null;
  /** Id devuelto por el ticket: sirve para borrar el registro si se cancela a mitad. */
  private pendingImageId: string | null = null;

  readonly cover = computed(() => this.images().find((i) => i.role === 'cover' && i.is_ready));
  readonly gallery = computed(() => this.images().filter((i) => i.role !== 'cover'));

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
    this.imageUpload?.unsubscribe();
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
    this.loadImages(machine.id);

    this.service.qrImage(machine.id, 'png').subscribe({
      next: (blob) => this.qrImageUrl.set(URL.createObjectURL(blob)),
      error: () => this.error.set('Could not generate the QR image.'),
    });
    this.service.qrData(machine.id).subscribe((data) => this.qrData.set(data));
  }

  // ---------------------------------------------------------------------------
  //  Imágenes
  // ---------------------------------------------------------------------------
  //
  // Tras cada mutación se recarga del servidor en lugar de actualizar el estado local. No es
  // pereza: al borrar la portada el backend puede dejar la máquina sin ninguna, y al promocionar
  // una imagen degrada otra. Reproducir esas reglas en el cliente es garantizar que diverjan.

  private loadImages(machineId: string): void {
    this.service.images(machineId).subscribe({
      next: (images) => this.images.set(images),
      error: () => this.error.set('Could not load the images for this machine.'),
    });
  }

  private refreshAfterImageChange(): void {
    const machine = this.selected();
    if (!machine) return;
    this.loadImages(machine.id);
    // También el catálogo: la miniatura de la tabla sale de `cover_image_url`.
    this.load();
  }

  onImagePicked(files: File[]): void {
    const machine = this.selected();
    const file = files[0];
    if (!machine || !file) return;

    this.error.set(null);
    this.uploadingImage.set(true);
    this.imageProgress.set(0);
    this.imageFileName.set(file.name);
    this.pendingImageId = null;

    // La primera imagen de una máquina entra como portada: es lo que el admin quiere el 100 % de
    // las veces, y ahorra tener que subirla y marcarla en dos pasos.
    const role = this.images().some((i) => i.role === 'cover') ? 'gallery' : 'cover';

    this.imageUpload = this.service.uploadImage(machine.id, file, role).subscribe({
      next: (state) => {
        if (state.imageId) this.pendingImageId = state.imageId;
        if (state.progress >= 0) this.imageProgress.set(state.progress);
        if (state.done && state.imageId) {
          // `done`, y no la mera presencia de `imageId`: ese llega al principio, y confirmar
          // entonces preguntaría por un objeto que aún no está en MinIO.
          this.service.confirmImage(machine.id, state.imageId).subscribe({
            next: () => {
              this.resetImageUpload();
              this.refreshAfterImageChange();
            },
            error: (err) => {
              this.resetImageUpload();
              this.error.set(
                err?.error?.detail ?? 'The upload finished but the image could not be validated.',
              );
              this.refreshAfterImageChange();
            },
          });
        }
      },
      error: (err) => {
        this.resetImageUpload();
        this.error.set(err?.error?.detail ?? 'The image could not be uploaded.');
      },
    });
  }

  cancelImageUpload(): void {
    // `unsubscribe` aborta el XHR. El registro ya existe en el backend desde que respondió el
    // ticket, así que se borra: si no, quedaría una imagen sin fichero detrás.
    this.imageUpload?.unsubscribe();
    const machine = this.selected();
    if (machine && this.pendingImageId) {
      this.service.deleteImage(machine.id, this.pendingImageId).subscribe({
        next: () => this.refreshAfterImageChange(),
        error: () => this.refreshAfterImageChange(),
      });
    }
    this.resetImageUpload();
  }

  onImageRejected(event: { file: File; reason: 'type' | 'size' }): void {
    this.error.set(
      event.reason === 'size'
        ? `“${event.file.name}” is too large. The limit is 5 MB.`
        : `“${event.file.name}” is not a JPEG, PNG or WebP image.`,
    );
  }

  makePrimary(image: MachineImage): void {
    const machine = this.selected();
    if (!machine) return;
    this.service.patchImage(machine.id, image.id, { role: 'cover' }).subscribe({
      next: () => this.refreshAfterImageChange(),
      error: (err) => this.error.set(err?.error?.detail ?? 'Could not set the primary image.'),
    });
  }

  /**
   * Reordena intercambiando posiciones con la vecina.
   *
   * En dos PATCH y pasando por una posición libre alta: `uq_machine_image_order` no está
   * diferida, así que un intercambio directo A<->B chocaría en el primer UPDATE.
   */
  moveImage(image: MachineImage, delta: number): void {
    const machine = this.selected();
    if (!machine) return;

    const ordered = this.gallery();
    const index = ordered.findIndex((i) => i.id === image.id);
    const neighbour = ordered[index + delta];
    if (!neighbour) return;

    const parking = Math.max(...this.images().map((i) => i.order_index)) + 1;
    const mine = image.order_index;
    const theirs = neighbour.order_index;

    this.service.patchImage(machine.id, image.id, { order_index: parking }).subscribe({
      next: () =>
        this.service.patchImage(machine.id, neighbour.id, { order_index: mine }).subscribe({
          next: () =>
            this.service.patchImage(machine.id, image.id, { order_index: theirs }).subscribe({
              next: () => this.refreshAfterImageChange(),
              error: () => this.refreshAfterImageChange(),
            }),
          error: () => this.refreshAfterImageChange(),
        }),
      error: (err) => this.error.set(err?.error?.detail ?? 'Could not reorder the images.'),
    });
  }

  removeImage(image: MachineImage): void {
    const machine = this.selected();
    if (!machine) return;
    if (!confirm(`Delete this image from ${machine.code}? This cannot be undone.`)) return;

    this.service.deleteImage(machine.id, image.id).subscribe({
      next: () => this.refreshAfterImageChange(),
      error: (err) => this.error.set(err?.error?.detail ?? 'Could not delete the image.'),
    });
  }

  private resetImageUpload(): void {
    this.uploadingImage.set(false);
    this.imageProgress.set(null);
    this.imageFileName.set(null);
    this.imageUpload = null;
    this.pendingImageId = null;
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
