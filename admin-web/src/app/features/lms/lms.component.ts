import { Component, OnDestroy, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription, forkJoin } from 'rxjs';

import { LmsService } from '../../core/services/lms.service';
import { MachinesService } from '../../core/services/machines.service';
import {
  AuthoringTree,
  LearningPath,
  LessonAuthoring,
  Machine,
  ModuleAuthoring,
  PublishStatus,
  VideoAsset,
  VideoAssetListItem,
} from '../../core/models/api.models';
import { IconComponent } from '../../shared/icon/icon.component';
import { FileDropComponent } from '../../shared/upload/file-drop.component';
import { LibraryScope, VideoLibraryComponent } from './video-library.component';

/**
 * Capacitación: autoría completa de módulos y lecciones + pipeline de video.
 *
 * Reescrito sobre `GET /lms/machines/{id}/authoring` (D-052). La versión anterior era
 * solo-lectura salvo un caso: podía subir un video y crear su lección, pero **no podía crear un
 * módulo**, con lo que un video subido a una máquina sin módulos era impublicable, ni editar ni
 * borrar nada. Los métodos del servicio existían como código muerto.
 *
 * Estructura: a la izquierda el árbol de autoría editable (crear/editar/borrar/reordenar
 * módulos y lecciones, incluidas las de texto); a la derecha la subida de video y la vista
 * previa de consumo — la misma respuesta del API que ve la app, para comprobar el resultado
 * real sin abrir el móvil.
 */
@Component({
  selector: 'app-lms',
  imports: [FormsModule, IconComponent, FileDropComponent, VideoLibraryComponent],
  template: `
    <div class="page">
      <div class="page-head">
        <h1>Training</h1>
        <p>
          Create and edit modules and lessons, upload videos, and preview what the trainee sees.
        </p>
      </div>

      @if (message()) {
        <div class="alert" [class.error]="messageIsError()" [class.info]="!messageIsError()">
          {{ message() }}
        </div>
      }

      <div class="toolbar">
        <div class="field" style="max-width: 460px; margin: 0; flex: 1">
          <label for="machine">Equipment</label>
          <select id="machine" [(ngModel)]="machineId" (ngModelChange)="reload()">
            @for (machine of machines(); track machine.id) {
              <option [ngValue]="machine.id">{{ machine.code }} — {{ machine.name }}</option>
            }
          </select>
        </div>
        <button class="primary" type="button" (click)="toggleNewModule()">
          <app-icon name="plus" [size]="14" />
          {{ creatingModule() ? 'Cancel' : 'New module' }}
        </button>
      </div>

      <div class="split wide-left">
        <!-- ==================== Árbol de autoría ==================== -->
        <section class="card">
          <div class="card-head">
            <h2>Modules &amp; lessons</h2>
            @if (tree(); as t) {
              <span class="badge" [class.ok]="t.machine_status === 'published'">
                machine {{ t.machine_status }}
              </span>
            }
          </div>

          @if (creatingModule()) {
            <form class="editor" (ngSubmit)="createModule()">
              <div class="field">
                <label for="nm-title">Module title</label>
                <input id="nm-title" name="nmTitle" [(ngModel)]="moduleDraft.title" required />
              </div>
              <div class="field">
                <label for="nm-desc">Description</label>
                <input id="nm-desc" name="nmDesc" [(ngModel)]="moduleDraft.description" />
              </div>
              <div class="row" style="margin-bottom: 0.75rem">
                <label class="check">
                  <input
                    type="checkbox"
                    name="nmPrev"
                    [(ngModel)]="moduleDraft.requires_previous"
                  />
                  Requires completing the previous module
                </label>
                <select
                  name="nmStatus"
                  [(ngModel)]="moduleDraft.status"
                  style="width: auto; margin-left: auto"
                >
                  <option value="draft">draft</option>
                  <option value="published">published</option>
                </select>
              </div>
              <button class="primary" type="submit" [disabled]="!moduleDraft.title.trim()">
                Create module
              </button>
            </form>
          }

          @if (!tree()) {
            <div class="empty">Pick a machine.</div>
          } @else if (tree()!.modules.length === 0 && !creatingModule()) {
            <div class="empty">
              No modules yet. Create the first one — without a module, uploaded videos cannot be
              published as lessons.
            </div>
          }

          @for (module of tree()?.modules ?? []; track module.id; let mi = $index) {
            <div class="module">
              @if (editingModuleId() === module.id) {
                <form class="editor" (ngSubmit)="saveModule(module)">
                  <div class="field">
                    <label [for]="'em-title-' + module.id">Title</label>
                    <input
                      [id]="'em-title-' + module.id"
                      name="emTitle"
                      [(ngModel)]="moduleDraft.title"
                    />
                  </div>
                  <div class="field">
                    <label [for]="'em-desc-' + module.id">Description</label>
                    <input
                      [id]="'em-desc-' + module.id"
                      name="emDesc"
                      [(ngModel)]="moduleDraft.description"
                    />
                  </div>
                  <div class="row" style="margin-bottom: 0.75rem">
                    <label class="check">
                      <input
                        type="checkbox"
                        name="emPrev"
                        [(ngModel)]="moduleDraft.requires_previous"
                      />
                      Requires previous module
                    </label>
                    <select
                      name="emStatus"
                      [(ngModel)]="moduleDraft.status"
                      style="width: auto; margin-left: auto"
                    >
                      <option value="draft">draft</option>
                      <option value="published">published</option>
                      <option value="archived">archived</option>
                    </select>
                  </div>
                  <div class="row">
                    <button class="primary small" type="submit">Save</button>
                    <button class="small" type="button" (click)="cancelEdits()">Cancel</button>
                  </div>
                </form>
              } @else {
                <div class="row" style="justify-content: space-between; flex-wrap: nowrap">
                  <div class="grow">
                    <strong>{{ module.order_index + 1 }}. {{ module.title }}</strong>
                    <span
                      class="badge"
                      style="margin-left: 0.5rem"
                      [class.ok]="module.status === 'published'"
                      [class.warn]="module.status === 'draft'"
                    >
                      {{ module.status }}
                    </span>
                    @if (module.description) {
                      <div class="hint" style="margin-top: 2px">{{ module.description }}</div>
                    }
                  </div>
                  <div class="row" style="flex-wrap: nowrap; gap: 0.25rem">
                    <button
                      class="icon-btn"
                      type="button"
                      title="Move up"
                      [disabled]="mi === 0"
                      (click)="moveModule(module, -1)"
                    >
                      <app-icon name="chevron-down" [size]="14" style="transform: rotate(180deg)" />
                    </button>
                    <button
                      class="icon-btn"
                      type="button"
                      title="Move down"
                      [disabled]="mi === (tree()?.modules?.length ?? 0) - 1"
                      (click)="moveModule(module, 1)"
                    >
                      <app-icon name="chevron-down" [size]="14" />
                    </button>
                    <button class="small" type="button" (click)="editModule(module)">Edit</button>
                    <button class="small" type="button" (click)="startLesson(module)">
                      + Lesson
                    </button>
                    <button
                      class="small danger-outline"
                      type="button"
                      (click)="removeModule(module)"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              }

              <!-- Lecciones -->
              @for (lesson of module.lessons; track lesson.id; let li = $index) {
                @if (editingLessonId() === lesson.id) {
                  <form class="editor" style="margin-top: 0.6rem" (ngSubmit)="saveLesson(lesson)">
                    <div class="field">
                      <label [for]="'el-title-' + lesson.id">Title</label>
                      <input
                        [id]="'el-title-' + lesson.id"
                        name="elTitle"
                        [(ngModel)]="lessonDraft.title"
                      />
                    </div>
                    @if (lesson.content_type === 'video') {
                      <div class="field">
                        <label [for]="'el-video-' + lesson.id">Video</label>
                        <select
                          [id]="'el-video-' + lesson.id"
                          name="elVideo"
                          [(ngModel)]="lessonDraft.video_asset_id"
                        >
                          @if (videosForMachine().length) {
                            <optgroup [label]="machineCode()">
                              @for (video of videosForMachine(); track video.id) {
                                <option [ngValue]="video.id">
                                  {{ video.original_filename }}
                                  ({{ (video.duration_seconds ?? 0).toFixed(0) }}s)
                                </option>
                              }
                            </optgroup>
                          }
                          @if (videosUnassigned().length) {
                            <optgroup label="Unassigned">
                              @for (video of videosUnassigned(); track video.id) {
                                <option [ngValue]="video.id">
                                  {{ video.original_filename }}
                                  ({{ (video.duration_seconds ?? 0).toFixed(0) }}s)
                                </option>
                              }
                            </optgroup>
                          }
                          <!--
                            El video actualmente seleccionado, si pertenece a otro equipo. NO es
                            cosmético: si el filtro lo excluyera, el select se renderizaría vacío
                            y al guardar mandaría video_asset_id: null — la lección perdería su
                            video en silencio.
                          -->
                          @if (foreignSelected(); as foreign) {
                            <optgroup label="Other equipment">
                              <option [ngValue]="foreign.id">
                                {{ foreign.original_filename }}
                                @if (foreign.machine_name) {
                                  — {{ foreign.machine_name }}
                                }
                              </option>
                            </optgroup>
                          }
                        </select>
                        <p class="hint">
                          Any transcoded video from the library below. Upload a new one first if it
                          is not listed.
                        </p>
                      </div>
                    }
                    <div class="field">
                      <label [for]="'el-body-' + lesson.id">
                        {{ lesson.content_type === 'text' ? 'Body' : 'Description (optional)' }}
                      </label>
                      <textarea
                        [id]="'el-body-' + lesson.id"
                        name="elBody"
                        [(ngModel)]="lessonDraft.body"
                        [style.min-height]="lesson.content_type === 'text' ? '120px' : '70px'"
                      ></textarea>
                      @if (lesson.content_type !== 'text') {
                        <p class="hint">Shown in the app below the {{ lesson.content_type }}.</p>
                      }
                    </div>
                    <div class="row" style="margin-bottom: 0.75rem">
                      <div class="field" style="margin: 0; width: 130px">
                        <label [for]="'el-min-' + lesson.id">Minutes</label>
                        <input
                          [id]="'el-min-' + lesson.id"
                          name="elMinutes"
                          type="number"
                          min="1"
                          [(ngModel)]="lessonDraft.estimated_minutes"
                        />
                      </div>
                      <div class="field" style="margin: 0; width: 150px; margin-left: auto">
                        <label [for]="'el-status-' + lesson.id">Status</label>
                        <select
                          [id]="'el-status-' + lesson.id"
                          name="elStatus"
                          [(ngModel)]="lessonDraft.status"
                        >
                          <option value="draft">draft</option>
                          <option value="published">published</option>
                          <option value="archived">archived</option>
                        </select>
                      </div>
                    </div>
                    <div class="row">
                      <button class="primary small" type="submit">Save</button>
                      <button class="small" type="button" (click)="cancelEdits()">Cancel</button>
                    </div>
                  </form>
                } @else {
                  <div class="lesson">
                    <span class="grow trunc">
                      {{ lesson.title }}
                      <span class="badge" style="margin-left: 0.4rem">{{
                        lesson.content_type
                      }}</span>
                      @if (lesson.video_status && lesson.video_status !== 'ready') {
                        <span class="badge warn" style="margin-left: 0.3rem">
                          video {{ lesson.video_status }}
                        </span>
                      }
                      <span
                        class="badge"
                        style="margin-left: 0.3rem"
                        [class.ok]="lesson.status === 'published'"
                        [class.warn]="lesson.status === 'draft'"
                      >
                        {{ lesson.status }}
                      </span>
                    </span>
                    <span class="row" style="flex-wrap: nowrap; gap: 0.25rem">
                      <button
                        class="icon-btn"
                        type="button"
                        title="Move up"
                        [disabled]="li === 0"
                        (click)="moveLesson(module, lesson, -1)"
                      >
                        <app-icon
                          name="chevron-down"
                          [size]="13"
                          style="transform: rotate(180deg)"
                        />
                      </button>
                      <button
                        class="icon-btn"
                        type="button"
                        title="Move down"
                        [disabled]="li === module.lessons.length - 1"
                        (click)="moveLesson(module, lesson, 1)"
                      >
                        <app-icon name="chevron-down" [size]="13" />
                      </button>
                      <button class="small" type="button" (click)="editLesson(lesson)">Edit</button>
                      <button
                        class="small danger-outline"
                        type="button"
                        (click)="removeLesson(lesson)"
                      >
                        Delete
                      </button>
                    </span>
                  </div>
                }
              }

              <!-- Alta de lección de texto en este módulo -->
              @if (addingLessonModuleId() === module.id) {
                <form
                  class="editor"
                  style="margin-top: 0.6rem"
                  (ngSubmit)="createTextLesson(module)"
                >
                  <div class="field">
                    <label [for]="'nl-title-' + module.id">Lesson title</label>
                    <input
                      [id]="'nl-title-' + module.id"
                      name="nlTitle"
                      [(ngModel)]="lessonDraft.title"
                      required
                    />
                  </div>
                  <div class="field">
                    <label [for]="'nl-body-' + module.id">Body (text lesson)</label>
                    <textarea
                      [id]="'nl-body-' + module.id"
                      name="nlBody"
                      [(ngModel)]="lessonDraft.body"
                      style="min-height: 120px"
                      required
                    ></textarea>
                    <p class="hint">
                      Video lessons are created from the upload panel on the right, once the video
                      is ready.
                    </p>
                  </div>
                  <div class="row" style="margin-bottom: 0.75rem">
                    <div class="field" style="margin: 0; width: 130px">
                      <label [for]="'nl-min-' + module.id">Minutes</label>
                      <input
                        [id]="'nl-min-' + module.id"
                        name="nlMinutes"
                        type="number"
                        min="1"
                        [(ngModel)]="lessonDraft.estimated_minutes"
                      />
                    </div>
                    <div class="field" style="margin: 0; width: 150px; margin-left: auto">
                      <label [for]="'nl-status-' + module.id">Status</label>
                      <select
                        [id]="'nl-status-' + module.id"
                        name="nlStatus"
                        [(ngModel)]="lessonDraft.status"
                      >
                        <option value="draft">draft</option>
                        <option value="published">published</option>
                      </select>
                    </div>
                  </div>
                  <div class="row">
                    <button
                      class="primary small"
                      type="submit"
                      [disabled]="!lessonDraft.title.trim() || !lessonDraft.body?.trim()"
                    >
                      Create lesson
                    </button>
                    <button class="small" type="button" (click)="cancelEdits()">Cancel</button>
                  </div>
                </form>
              }
            </div>
          }
        </section>

        <!-- ==================== Video + vista previa ==================== -->
        <div class="stack" style="gap: 1rem">
          <section class="card">
            <h2>Upload video</h2>
            <p class="hint" style="margin-top:-0.4rem">
              The file goes <strong>straight to storage</strong> with a presigned URL, without
              passing through the API. A worker then transcodes it to HLS at several qualities.
            </p>

            @if (machineId) {
              <p class="hint">
                Uploads are assigned to <strong>{{ machineCode() }}</strong
                >, so they show up filtered in the library and in the lesson picker.
              </p>
            }

            <app-file-drop
              accept="video/*"
              label="Drop an MP4 here"
              hint="Any video file · assigned to the selected machine"
              [disabled]="!machineId"
              [busy]="uploading()"
              [progress]="uploadProgress()"
              [fileName]="uploadFileName()"
              (picked)="onFilePicked($event)"
              (cancel)="cancelUpload()"
            />
            @if (!machineId) {
              <p class="hint" style="color: var(--warn)">Pick a machine above to upload a video.</p>
            }

            @if (asset(); as videoAsset) {
              <div class="field">
                <label>Processing status</label>
                @if (videoAsset.status === 'queued' || videoAsset.status === 'processing') {
                  <p class="hint">
                    Transcoding takes about a minute per minute of footage. You can leave this page:
                    the video will appear as <strong>ready</strong> in the library below.
                  </p>
                }
                <div class="row">
                  <span
                    class="badge"
                    [class.ok]="videoAsset.status === 'ready'"
                    [class.warn]="
                      videoAsset.status === 'queued' || videoAsset.status === 'processing'
                    "
                    [class.danger]="videoAsset.status === 'failed'"
                  >
                    {{ videoAsset.status }}
                  </span>
                  @if (videoAsset.duration_seconds) {
                    <span class="badge">{{ videoAsset.duration_seconds.toFixed(0) }} s</span>
                  }
                  @for (rendition of videoAsset.renditions; track rendition.name) {
                    <span class="badge ok">{{ rendition.name }}</span>
                  }
                  @if (videoAsset.status === 'failed') {
                    <button class="small" type="button" (click)="retryProcessing(videoAsset.id)">
                      Retry processing
                    </button>
                  }
                </div>
                @if (videoAsset.error_message) {
                  <p class="hint" style="color: var(--danger)">{{ videoAsset.error_message }}</p>
                }
              </div>

              @if (videoAsset.status === 'ready') {
                <form (ngSubmit)="createVideoLesson()">
                  <div class="field">
                    <label for="lessonModule">Module</label>
                    <select
                      id="lessonModule"
                      name="lessonModule"
                      [(ngModel)]="videoLessonDraft.moduleId"
                    >
                      @for (module of tree()?.modules ?? []; track module.id) {
                        <option [ngValue]="module.id">{{ module.title }}</option>
                      }
                    </select>
                    @if ((tree()?.modules ?? []).length === 0) {
                      <p class="hint" style="color: var(--warn)">
                        This machine has no modules: create one first (button above) or the video
                        cannot be published.
                      </p>
                    }
                  </div>
                  <div class="field">
                    <label for="lessonTitle">Lesson title</label>
                    <input
                      id="lessonTitle"
                      name="lessonTitle"
                      [(ngModel)]="videoLessonDraft.title"
                    />
                  </div>
                  <button
                    class="primary"
                    type="submit"
                    [disabled]="!videoLessonDraft.title || !videoLessonDraft.moduleId"
                  >
                    Create published lesson
                  </button>
                </form>
              }
            }
          </section>

          <app-video-library
            [videos]="library()"
            [machines]="machines()"
            [machineId]="machineId"
            [scope]="libraryScope()"
            [unassignedCount]="unassignedCount()"
            (scopeChange)="setLibraryScope($event)"
            (refresh)="loadLibrary()"
            (use)="useFromLibrary($event)"
            (process)="processFromLibrary($event)"
            (remove)="removeVideo($event)"
            (assign)="assignToMachine($event)"
          />

          <section class="card">
            <div class="card-head">
              <h2>Trainee preview</h2>
              <button class="small" type="button" (click)="loadPreview()">Refresh</button>
            </div>
            <p class="hint" style="margin-top:-0.4rem">
              The same API response the mobile app renders — including which modules are locked.
            </p>
            @if (!preview()) {
              <div class="empty compact">Press Refresh to load the trainee view.</div>
            } @else {
              <div class="row" style="margin-bottom: 0.6rem">
                <span class="badge">{{ preview()!.total_lessons }} lessons</span>
                <span class="badge ok">{{ preview()!.progress_percent }}% complete</span>
              </div>
              @for (module of preview()!.modules; track module.id) {
                <div class="lesson" style="border: none; padding: 0.2rem 0">
                  <span class="grow trunc">
                    {{ module.order_index + 1 }}. {{ module.title }}
                    @if (module.locked) {
                      <span class="badge warn" style="margin-left: 0.4rem">locked</span>
                    }
                  </span>
                  <span class="badge"
                    >{{ module.completed_lessons }}/{{ module.total_lessons }}</span
                  >
                </div>
              }
              @if (preview()!.modules.length === 0) {
                <div class="empty compact">
                  Nothing published: the trainee sees an empty training for this machine.
                </div>
              }
            }
          </section>
        </div>
      </div>
    </div>
  `,
  styles: `
    .module {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.7rem 0.85rem;
      margin-bottom: 0.7rem;
      background: var(--surface-2);
    }
    .lesson {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
      padding: 0.35rem 0;
      border-top: 1px solid var(--border);
      margin-top: 0.45rem;
      font-size: 0.88rem;
    }
    .editor {
      border: 1px dashed var(--accent-line);
      border-radius: var(--radius);
      padding: 0.8rem;
      margin: 0.5rem 0 0.8rem;
      background: var(--accent-soft);
    }
    .check {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      text-transform: none;
      letter-spacing: normal;
      font-size: 0.85rem;
      color: var(--text);
      font-weight: 400;
      margin: 0;
    }
    .progress {
      height: 8px;
      background: var(--surface-2);
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    .progress span {
      display: block;
      height: 100%;
      background: var(--accent);
      transition: width 0.2s;
    }
  `,
})
export class LmsComponent implements OnDestroy {
  private readonly lms = inject(LmsService);
  private readonly machinesService = inject(MachinesService);

  readonly machines = signal<Machine[]>([]);
  readonly tree = signal<AuthoringTree | null>(null);
  readonly preview = signal<LearningPath | null>(null);
  readonly asset = signal<VideoAsset | null>(null);
  readonly uploading = signal(false);
  readonly uploadProgress = signal<number | null>(null);
  readonly uploadFileName = signal<string | null>(null);
  private upload: Subscription | null = null;
  /** Id del ticket: permite borrar el asset huérfano si se cancela a mitad de subida. */
  private pendingAssetId: string | null = null;
  readonly message = signal<string | null>(null);
  readonly messageIsError = signal(false);

  readonly library = signal<VideoAssetListItem[]>([]);
  readonly libraryScope = signal<LibraryScope>('machine');
  readonly unassignedCount = signal(0);
  readonly creatingModule = signal(false);
  readonly editingModuleId = signal<string | null>(null);
  readonly editingLessonId = signal<string | null>(null);
  readonly addingLessonModuleId = signal<string | null>(null);

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  machineId: string | null = null;

  moduleDraft = {
    title: '',
    description: '' as string | null,
    requires_previous: true,
    status: 'draft' as PublishStatus,
  };
  lessonDraft = {
    title: '',
    body: '' as string | null,
    estimated_minutes: null as number | null,
    status: 'draft' as PublishStatus,
    video_asset_id: null as string | null,
  };
  videoLessonDraft = { moduleId: null as string | null, title: '' };

  constructor() {
    this.machinesService.list().subscribe((list) => {
      this.machines.set(list);
      this.machineId = list[0]?.id ?? null;
      this.reload();
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  reload(): void {
    if (!this.machineId) {
      return;
    }
    this.cancelEdits();
    this.preview.set(null);
    this.lms.authoring(this.machineId).subscribe({
      next: (tree) => {
        this.tree.set(tree);
        this.videoLessonDraft.moduleId = tree.modules[0]?.id ?? null;
      },
      error: (err) => this.notify(`Could not load the authoring tree (${err?.status}).`, true),
    });
    this.loadLibrary();
  }

  loadLibrary(): void {
    const scope = this.libraryScope();
    const machine = this.machineId;
    const params =
      scope === 'machine' && machine
        ? { machineModelId: machine }
        : scope === 'unassigned'
          ? { unassigned: true }
          : undefined;

    this.lms.listVideos(params).subscribe({
      next: (videos) => this.library.set(videos),
      error: () => this.notify('Could not load the video library.', true),
    });

    // El recuento de "sin asignar" se pide aparte y sin filtrar: tiene que ser visible desde
    // cualquier ámbito, o los videos antiguos parecerían haber desaparecido.
    this.lms.listVideos({ unassigned: true }).subscribe({
      next: (videos) => this.unassignedCount.set(videos.length),
      error: () => this.unassignedCount.set(0),
    });
  }

  setLibraryScope(scope: LibraryScope): void {
    this.libraryScope.set(scope);
    this.loadLibrary();
  }

  /** Asigna al equipo activo un video que estaba huérfano. Vía de migración de los antiguos. */
  assignToMachine(video: VideoAssetListItem): void {
    const machine = this.machineId;
    if (!machine) return;
    this.lms.assignVideo(video.id, machine).subscribe({
      next: () => {
        this.notify(`"${video.original_filename}" assigned to ${this.machineCode()}.`, false);
        this.loadLibrary();
      },
      error: (err) => this.notifyHttp('Could not assign the video', err),
    });
  }

  /** Listos y de este equipo. */
  videosForMachine(): VideoAssetListItem[] {
    const machine = this.machineId;
    return this.library().filter((v) => v.status === 'ready' && v.machine_model_id === machine);
  }

  /** Listos y todavía sin equipo: se pueden usar y quedan adoptados por el módulo (D-060). */
  videosUnassigned(): VideoAssetListItem[] {
    return this.library().filter((v) => v.status === 'ready' && !v.machine_model_id);
  }

  /**
   * El video que la lección ya tiene, cuando pertenece a OTRO equipo.
   *
   * Sin esta opción en la lista, el `<select>` no encontraría su valor, se pintaría vacío, y el
   * primer guardado dejaría la lección sin video sin que nadie lo pidiera.
   */
  foreignSelected(): VideoAssetListItem | null {
    const current = this.lessonDraft.video_asset_id;
    if (!current) return null;
    const machine = this.machineId;
    const video = this.library().find((v) => v.id === current);
    if (!video || !video.machine_model_id || video.machine_model_id === machine) return null;
    return video;
  }

  removeVideo(video: VideoAssetListItem): void {
    if (!confirm(`Delete "${video.original_filename}" and its transcoded files?`)) {
      return;
    }
    this.lms.deleteVideo(video.id).subscribe({
      next: () => {
        this.notify('Video deleted.', false);
        this.loadLibrary();
      },
      error: (err) => this.notifyHttp('Could not delete the video', err),
    });
  }

  processFromLibrary(video: VideoAssetListItem): void {
    this.lms.processVideo(video.id).subscribe({
      next: (asset) => {
        this.asset.set(asset);
        this.startPolling(asset.id);
        this.loadLibrary();
      },
      error: (err) => this.notifyHttp('Could not queue the processing', err),
    });
  }

  /** Precarga el formulario de publicación con un video ya listo de la biblioteca. */
  useFromLibrary(video: VideoAssetListItem): void {
    this.lms.videoAsset(video.id).subscribe({
      next: (asset) => {
        this.asset.set(asset);
        this.videoLessonDraft.title = video.original_filename.replace(/\.[^.]+$/, '');
      },
      error: (err) => this.notifyHttp('Could not load the video', err),
    });
  }

  loadPreview(): void {
    if (!this.machineId) {
      return;
    }
    this.lms.learningPath(this.machineId).subscribe({
      next: (path) => this.preview.set(path),
      error: () => this.notify('Could not load the trainee preview.', true),
    });
  }

  // --------------------------------------------------------------------------
  //  Módulos
  // --------------------------------------------------------------------------
  toggleNewModule(): void {
    this.cancelEdits();
    this.creatingModule.update((open) => !open);
  }

  createModule(): void {
    if (!this.machineId) {
      return;
    }
    this.lms
      .createModule({
        machine_model_id: this.machineId,
        title: this.moduleDraft.title.trim(),
        description: this.moduleDraft.description?.trim() || null,
        requires_previous: this.moduleDraft.requires_previous,
        status: this.moduleDraft.status,
        order_index: this.nextModuleIndex(),
      })
      .subscribe({
        next: () => {
          this.notify('Module created.', false);
          this.reload();
        },
        error: (err) => this.notifyHttp('Could not create the module', err),
      });
  }

  editModule(module: ModuleAuthoring): void {
    this.cancelEdits();
    this.editingModuleId.set(module.id);
    this.moduleDraft = {
      title: module.title,
      description: module.description ?? '',
      requires_previous: module.requires_previous,
      status: module.status,
    };
  }

  saveModule(module: ModuleAuthoring): void {
    this.lms
      .updateModule(module.id, {
        title: this.moduleDraft.title.trim(),
        description: this.moduleDraft.description?.trim() || null,
        requires_previous: this.moduleDraft.requires_previous,
        status: this.moduleDraft.status,
      })
      .subscribe({
        next: () => {
          this.notify('Module saved.', false);
          this.reload();
        },
        error: (err) => this.notifyHttp('Could not save the module', err),
      });
  }

  removeModule(module: ModuleAuthoring): void {
    const lessons = module.lessons.length;
    const warning =
      `Delete "${module.title}"` +
      (lessons ? ` and its ${lessons} lesson(s)? Trainee progress on those lessons is lost.` : '?');
    if (!confirm(warning)) {
      return;
    }
    this.lms.deleteModule(module.id).subscribe({
      next: () => {
        this.notify('Module deleted.', false);
        this.reload();
      },
      error: (err) => this.notifyHttp('Could not delete the module', err),
    });
  }

  /**
   * Intercambia `order_index` con el vecino, en tres pasos por la restricción única:
   * A -> índice temporal, B -> índice de A, A -> índice de B. Dos PATCH directos chocarían.
   */
  moveModule(module: ModuleAuthoring, delta: number): void {
    const modules = this.tree()?.modules ?? [];
    const index = modules.findIndex((m) => m.id === module.id);
    const neighbour = modules[index + delta];
    if (!neighbour) {
      return;
    }
    const temp = 9000 + module.order_index;
    this.lms.updateModule(module.id, { order_index: temp }).subscribe({
      next: () =>
        forkJoin([
          this.lms.updateModule(neighbour.id, { order_index: module.order_index }),
        ]).subscribe({
          next: () =>
            this.lms.updateModule(module.id, { order_index: neighbour.order_index }).subscribe({
              next: () => this.reload(),
              error: (e) => this.notifyHttp('Reorder failed', e),
            }),
          error: (e) => this.notifyHttp('Reorder failed', e),
        }),
      error: (e) => this.notifyHttp('Reorder failed', e),
    });
  }

  // --------------------------------------------------------------------------
  //  Lecciones
  // --------------------------------------------------------------------------
  startLesson(module: ModuleAuthoring): void {
    this.cancelEdits();
    this.addingLessonModuleId.set(module.id);
    this.lessonDraft = {
      title: '',
      body: '',
      estimated_minutes: null,
      status: 'draft',
      video_asset_id: null,
    };
  }

  createTextLesson(module: ModuleAuthoring): void {
    this.lms
      .createLesson({
        training_module_id: module.id,
        title: this.lessonDraft.title.trim(),
        content_type: 'text',
        body: this.lessonDraft.body,
        estimated_minutes: this.lessonDraft.estimated_minutes || null,
        status: this.lessonDraft.status,
        order_index: this.nextLessonIndex(module),
      })
      .subscribe({
        next: () => {
          this.notify('Lesson created.', false);
          this.reload();
        },
        error: (err) => this.notifyHttp('Could not create the lesson', err),
      });
  }

  editLesson(lesson: LessonAuthoring): void {
    this.cancelEdits();
    this.editingLessonId.set(lesson.id);
    this.lessonDraft = {
      title: lesson.title,
      body: lesson.body ?? '',
      estimated_minutes: lesson.estimated_minutes,
      status: lesson.status,
      video_asset_id: lesson.video_asset_id,
    };
  }

  saveLesson(lesson: LessonAuthoring): void {
    this.lms
      .updateLesson(lesson.id, {
        title: this.lessonDraft.title.trim(),
        estimated_minutes: this.lessonDraft.estimated_minutes || null,
        status: this.lessonDraft.status,
        // `body` viaja para todos los tipos: en una lección de video es la descripción que la
        // app muestra bajo el reproductor. En una de texto, vacío no es válido (422 del backend).
        body: this.lessonDraft.body || null,
        ...(lesson.content_type === 'video'
          ? { video_asset_id: this.lessonDraft.video_asset_id }
          : {}),
      })
      .subscribe({
        next: () => {
          this.notify('Lesson saved.', false);
          this.reload();
        },
        error: (err) => this.notifyHttp('Could not save the lesson', err),
      });
  }

  removeLesson(lesson: LessonAuthoring): void {
    if (!confirm(`Delete "${lesson.title}"? Trainee progress on it is lost.`)) {
      return;
    }
    this.lms.deleteLesson(lesson.id).subscribe({
      next: () => {
        this.notify('Lesson deleted.', false);
        this.reload();
      },
      error: (err) => this.notifyHttp('Could not delete the lesson', err),
    });
  }

  moveLesson(module: ModuleAuthoring, lesson: LessonAuthoring, delta: number): void {
    const index = module.lessons.findIndex((l) => l.id === lesson.id);
    const neighbour = module.lessons[index + delta];
    if (!neighbour) {
      return;
    }
    const temp = 9000 + lesson.order_index;
    this.lms.updateLesson(lesson.id, { order_index: temp }).subscribe({
      next: () =>
        this.lms.updateLesson(neighbour.id, { order_index: lesson.order_index }).subscribe({
          next: () =>
            this.lms.updateLesson(lesson.id, { order_index: neighbour.order_index }).subscribe({
              next: () => this.reload(),
              error: (e) => this.notifyHttp('Reorder failed', e),
            }),
          error: (e) => this.notifyHttp('Reorder failed', e),
        }),
      error: (e) => this.notifyHttp('Reorder failed', e),
    });
  }

  // --------------------------------------------------------------------------
  //  Video
  // --------------------------------------------------------------------------
  onFilePicked(files: File[]): void {
    const file = files[0];
    if (!file || !this.machineId) {
      return;
    }

    this.uploading.set(true);
    this.uploadProgress.set(0);
    this.uploadFileName.set(file.name);
    this.asset.set(null);
    this.pendingAssetId = null;

    this.upload = this.lms.uploadVideo(file, this.machineId).subscribe({
      next: (state) => {
        if (state.videoAssetId) {
          this.pendingAssetId = state.videoAssetId;
        }
        if (state.progress >= 0) {
          this.uploadProgress.set(state.progress);
        }
        // `done`, y NO la presencia de `videoAssetId`: ese llega al emitirse el ticket, antes de
        // subir un solo byte, y encolar entonces procesaría un objeto que aún no está en MinIO.
        if (state.done && state.videoAssetId) {
          this.uploading.set(false);
          this.uploadFileName.set(null);
          this.upload = null;
          // Subido no es procesado: hay que encolar la transcodificación explícitamente, lo que
          // permite reintentarla sin volver a subir el fichero.
          this.lms.processVideo(state.videoAssetId).subscribe({
            next: (asset) => {
              this.asset.set(asset);
              this.videoLessonDraft.title = file.name.replace(/\.[^.]+$/, '');
              this.startPolling(asset.id);
              this.loadLibrary();
            },
            error: (err) =>
              this.notifyHttp('The file uploaded but processing could not be queued', err),
          });
        }
      },
      error: (err) => {
        this.resetUpload();
        this.notifyHttp('The video could not be uploaded', err);
      },
    });
  }

  /** Aborta el XHR y borra el asset que el ticket ya había creado. */
  cancelUpload(): void {
    this.upload?.unsubscribe();
    if (this.pendingAssetId) {
      this.lms.deleteVideo(this.pendingAssetId).subscribe({
        next: () => this.loadLibrary(),
        error: () => this.loadLibrary(),
      });
    }
    this.resetUpload();
  }

  private resetUpload(): void {
    this.uploading.set(false);
    this.uploadProgress.set(null);
    this.uploadFileName.set(null);
    this.upload = null;
    this.pendingAssetId = null;
  }

  machineCode(): string {
    return this.machines().find((m) => m.id === this.machineId)?.code ?? '';
  }

  retryProcessing(assetId: string): void {
    this.lms.processVideo(assetId).subscribe({
      next: (asset) => {
        this.asset.set(asset);
        this.startPolling(asset.id);
      },
      error: (err) => this.notifyHttp('Could not queue the processing', err),
    });
  }

  createVideoLesson(): void {
    const asset = this.asset();
    const moduleId = this.videoLessonDraft.moduleId;
    if (!asset || !moduleId) {
      return;
    }
    const module = this.tree()?.modules.find((m) => m.id === moduleId);
    this.lms
      .createLesson({
        training_module_id: moduleId,
        title: this.videoLessonDraft.title,
        content_type: 'video',
        // max + 1, no length + 1: el seed usa índices 0-based y `length + 1` dejaba huecos (y
        // con datos no contiguos, colisiones).
        order_index: module ? this.nextLessonIndex(module) : 0,
        video_asset_id: asset.id,
        status: 'published',
      })
      .subscribe({
        next: () => {
          this.notify('Lesson created and published.', false);
          this.asset.set(null);
          this.reload();
        },
        error: (err) => this.notifyHttp('Could not create the lesson', err),
      });
  }

  private startPolling(assetId: string): void {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      this.lms.videoAsset(assetId).subscribe((asset) => {
        this.asset.set(asset);
        if (asset.status === 'ready' || asset.status === 'failed') {
          this.stopPolling();
          this.loadLibrary();
        }
      });
    }, 3000);
  }

  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  // --------------------------------------------------------------------------
  //  Helpers
  // --------------------------------------------------------------------------
  cancelEdits(): void {
    this.creatingModule.set(false);
    this.editingModuleId.set(null);
    this.editingLessonId.set(null);
    this.addingLessonModuleId.set(null);
    this.moduleDraft = { title: '', description: '', requires_previous: true, status: 'draft' };
    this.lessonDraft = {
      title: '',
      body: '',
      estimated_minutes: null,
      status: 'draft',
      video_asset_id: null,
    };
  }

  private nextModuleIndex(): number {
    const modules = this.tree()?.modules ?? [];
    return modules.length ? Math.max(...modules.map((m) => m.order_index)) + 1 : 0;
  }

  private nextLessonIndex(module: ModuleAuthoring): number {
    return module.lessons.length ? Math.max(...module.lessons.map((l) => l.order_index)) + 1 : 0;
  }

  private notify(text: string, isError: boolean): void {
    this.message.set(text);
    this.messageIsError.set(isError);
  }

  private notifyHttp(prefix: string, err: { status?: number; error?: { detail?: unknown } }): void {
    const detail = typeof err?.error?.detail === 'string' ? ` — ${err.error.detail}` : '';
    const status = err?.status ? ` (HTTP ${err.status})` : ' (network error)';
    this.notify(`${prefix}${status}${detail}`, true);
  }
}
