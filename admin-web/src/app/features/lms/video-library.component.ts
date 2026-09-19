import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Machine, VideoAssetListItem } from '../../core/models/api.models';
import { IconComponent } from '../../shared/icon/icon.component';

export type LibraryScope = 'machine' | 'unassigned' | 'all';

/**
 * Biblioteca de videos: qué hay subido, en qué estado y a qué equipo pertenece.
 *
 * Se saca de `lms.component.ts` porque su estado —el ámbito y el texto del buscador— no se
 * solapa con nada de la edición del temario, y porque el fichero ya era difícil de leer antes de
 * añadirle un filtro.
 *
 * Antes esta lista se cortaba a los 8 primeros con un "…and N more". Aquello era un parche por no
 * tener forma de filtrar: con el ámbito por equipo la lista típica cabe entera, y lo que sobra se
 * resuelve con scroll, que no esconde nada.
 */
@Component({
  selector: 'app-video-library',
  imports: [FormsModule, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="card">
      <div class="card-head">
        <h2>Video library</h2>
        <div class="row" style="gap: 0.4rem">
          <span class="badge">{{ visible().length }}</span>
          <button class="small" type="button" (click)="refresh.emit()">Refresh</button>
        </div>
      </div>

      <p class="hint" style="margin-top:-0.4rem">
        Transcoding takes roughly a minute per minute of footage — a video stays here even if you
        leave the page while it processes.
      </p>

      <div class="segmented" role="group" aria-label="Video scope">
        <button
          type="button"
          [class.active]="scope() === 'machine'"
          [disabled]="!machineId()"
          (click)="scopeChange.emit('machine')"
        >
          This machine
        </button>
        <!--
          El recuento va a la vista a propósito: si el ámbito arranca filtrado por equipo y los
          videos antiguos están sin asignar, el administrador cree que se han borrado.
        -->
        <button
          type="button"
          [class.active]="scope() === 'unassigned'"
          (click)="scopeChange.emit('unassigned')"
        >
          Unassigned ({{ unassignedCount() }})
        </button>
        <button
          type="button"
          [class.active]="scope() === 'all'"
          (click)="scopeChange.emit('all')"
        >
          All
        </button>
      </div>

      <div class="field search">
        <app-icon name="search" [size]="14" />
        <input
          type="search"
          name="videoQuery"
          placeholder="Filter by file name"
          [ngModel]="query()"
          (ngModelChange)="query.set($event)"
        />
      </div>

      @if (visible().length === 0) {
        <!--
          El mensaje distingue "no hay ninguno" de "no hay ninguno AQUÍ": con el ámbito por
          equipo, decir "no videos uploaded yet" cuando la biblioteca tiene doce de otro equipo
          hace pensar que se han borrado.
        -->
        <div class="empty compact">
          @if (query().trim()) {
            No videos match “{{ query() }}”.
          } @else if (scope() === 'machine') {
            No videos for this machine yet. Check <strong>Unassigned</strong> or upload one.
          } @else if (scope() === 'unassigned') {
            Every video is assigned to a machine.
          } @else {
            No videos uploaded yet.
          }
        </div>
      } @else {
        <div class="scroll-y">
          @for (video of visible(); track video.id) {
            <div class="lesson" style="border-top: 1px solid var(--border)">
              <span class="grow trunc" [title]="video.original_filename">
                {{ video.original_filename }}
                <span
                  class="badge"
                  style="margin-left: 0.35rem"
                  [class.ok]="video.status === 'ready'"
                  [class.warn]="video.status === 'processing' || video.status === 'queued'"
                  [class.danger]="video.status === 'failed'"
                >
                  {{ video.status }}
                </span>
                @if (video.duration_seconds) {
                  <span class="badge" style="margin-left: 0.25rem">
                    {{ video.duration_seconds.toFixed(0) }}s
                  </span>
                }
                @if (video.used_by_lessons.length) {
                  <span
                    class="badge accent"
                    style="margin-left: 0.25rem"
                    [title]="video.used_by_lessons.join(', ')"
                  >
                    in use
                  </span>
                }
                @if (video.machine_name) {
                  <span class="badge" style="margin-left: 0.25rem">{{ video.machine_name }}</span>
                } @else {
                  <span class="badge warn" style="margin-left: 0.25rem">unassigned</span>
                }
              </span>
              <span class="row" style="flex-wrap: nowrap; gap: 0.25rem">
                @if (video.status === 'ready' && !video.used_by_lessons.length) {
                  <button class="small" type="button" (click)="use.emit(video)">Use</button>
                }
                @if (!video.machine_model_id && machineId()) {
                  <button class="small" type="button" (click)="assign.emit(video)">
                    Assign here
                  </button>
                }
                @if (video.status === 'failed' || video.status === 'uploaded') {
                  <button class="small" type="button" (click)="process.emit(video)">Process</button>
                }
                @if (!video.used_by_lessons.length) {
                  <button class="small danger-outline" type="button" (click)="remove.emit(video)">
                    Delete
                  </button>
                }
              </span>
            </div>
          }
        </div>
      }
    </section>
  `,
  styles: `
    .scroll-y {
      max-height: 22rem;
      overflow-y: auto;
    }
    .search {
      position: relative;
      margin-top: 0.6rem;
    }
    .search app-icon {
      position: absolute;
      left: 0.55rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-dim);
      pointer-events: none;
    }
    .search input {
      padding-left: 1.9rem;
    }
  `,
})
export class VideoLibraryComponent {
  readonly videos = input.required<VideoAssetListItem[]>();
  readonly machines = input<Machine[]>([]);
  readonly machineId = input<string | null>(null);
  readonly scope = input<LibraryScope>('machine');
  /** Se calcula sobre TODOS los videos, no sobre los del ámbito actual. */
  readonly unassignedCount = input(0);

  readonly scopeChange = output<LibraryScope>();
  readonly refresh = output<void>();
  readonly use = output<VideoAssetListItem>();
  readonly process = output<VideoAssetListItem>();
  readonly remove = output<VideoAssetListItem>();
  readonly assign = output<VideoAssetListItem>();

  /** El buscador filtra en cliente: es instantáneo y la lista ya viene acotada por el ámbito. */
  protected readonly query = signal('');

  protected readonly visible = computed(() => {
    const needle = this.query().trim().toLowerCase();
    if (!needle) return this.videos();
    return this.videos().filter((v) => v.original_filename.toLowerCase().includes(needle));
  });
}
