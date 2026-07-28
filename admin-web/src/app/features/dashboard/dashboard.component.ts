import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { StatsService } from '../../core/services/stats.service';
import { AttentionCardComponent } from './attention-card.component';
import { HealthCardComponent } from './health-card.component';
import { RecentActivityComponent } from './recent-activity.component';
import { BarListComponent, BarRow } from '../../shared/charts/bar-list.component';
import { SparklineComponent } from '../../shared/charts/sparkline.component';
import { IconComponent } from '../../shared/icon/icon.component';
import { StatTileComponent } from '../../shared/stat/stat-tile.component';
import {
  NO_DATA,
  compact,
  duration,
  minutesToHours,
  percent,
  percentOrFraction,
  relativeTime,
  shortDay,
} from '../../shared/format';

/**
 * Vista general del sistema.
 *
 * El orden de los bloques no es estético, responde a qué informa con los datos que hay. Un
 * dashboard de demo tiene una máquina, seis chunks y unas decenas de mensajes, así que:
 *
 * 1. Arriba, **actividad del agente** (la cifra que lidera) junto a **salud** y **avisos**. Las dos
 *    últimas son afirmaciones categóricas, no métricas: informan igual con pocos datos que con
 *    muchos, y son lo que un admin quiere saber al abrir.
 * 2. Después los KPI de uso, con su tamaño de muestra a la vista.
 * 3. Luego el **inventario** (equipos, lecciones, conocimiento, vídeos), que nunca está a cero y
 *    da masa a la página sin fabricar analítica.
 * 4. Al final la **tabla de conversaciones recientes**, que es lo que mejor aparenta con pocos
 *    datos: seis filas llenan una tabla, seis puntos no llenan un gráfico.
 *
 * Rango por defecto de 30 días y no 7: con datos sembrados hace unos días, una ventana de 7 puede
 * salir vacía y el panel parecería roto justo al abrirlo.
 *
 * Deliberadamente fuera: coste en dólares (necesita una tabla de precios por modelo que envejece
 * en silencio y acaba mostrando cifras erróneas con aire de exactitud) y tasa de éxito de tools
 * como tile propio (con cero invocaciones sería un tile muerto; vive como fila de salud).
 */
@Component({
  selector: 'app-dashboard',
  imports: [
    RouterLink,
    IconComponent,
    StatTileComponent,
    SparklineComponent,
    BarListComponent,
    HealthCardComponent,
    AttentionCardComponent,
    RecentActivityComponent,
  ],
  template: `
    <div class="page" [class.refetching]="stats.refetching()">
      <div class="page-head">
        <h1>Overview</h1>
        <p>Content, agent usage and system health, from live data.</p>
      </div>

      @if (stats.error()) {
        <div class="alert error">
          {{ stats.error() }}
          <button class="small" type="button" style="margin-left: 0.5rem" (click)="reload()">
            Retry
          </button>
        </div>
      }

      <!-- Los filtros van SIEMPRE encima de lo que filtran, nunca dentro de una tarjeta: dentro
           sugerirían que solo afectan a esa tarjeta. -->
      <div class="toolbar">
        <div class="segmented" role="group" aria-label="Reporting window">
          @for (option of ranges; track option) {
            <button type="button" [class.active]="days() === option" (click)="setRange(option)">
              {{ option }}d
            </button>
          }
        </div>

        <div class="row" style="gap: 0.75rem">
          <span class="muted" style="font-size: var(--fs-sm)">
            Updated {{ relativeTime(stats.lastLoadedAt()) }}
          </span>
          <button class="small" type="button" (click)="reload()" [disabled]="stats.refetching()">
            <app-icon name="refresh" [size]="14" />
            Refresh
          </button>
        </div>
      </div>

      @if (data(); as overview) {
        <!-- Fila 0: la cifra que lidera, la salud y lo que hay que arreglar -->
        <div class="split wide-left" style="margin-bottom: 1rem">
          <section class="card">
            <div class="card-head">
              <h2>Agent activity</h2>
              <span class="badge accent">{{ overview.agent.window_days }} days</span>
            </div>

            @if (overview.agent.messages_in_window === 0) {
              <div class="hero-figure undefined-value muted">{{ NO_DATA }}</div>
              <div class="empty compact" style="margin-top: 1rem">
                <div class="empty-title">No conversations in this window</div>
                Ask the agent something from the
                <a routerLink="/agent/playground">Playground</a> and it will show up here.
              </div>
            } @else {
              <div class="row" style="align-items: baseline; gap: 0.75rem">
                <span class="hero-figure">{{ compact(overview.agent.messages_in_window) }}</span>
                <span class="muted">messages</span>
              </div>
              <p class="hint" style="margin-bottom: 1rem">
                {{ overview.agent.conversations_in_window }} conversations ·
                {{ compact(overview.agent.tokens_total) }} tokens ·
                {{ overview.agent.distinct_users_in_window }} distinct users
              </p>

              <app-sparkline
                [values]="messageSeries()"
                [labels]="daySeries()"
                ariaLabel="Messages per day"
              />

              <!-- Tabla gemela: ningún valor debe existir solo detrás del puntero. -->
              <details class="data-table">
                <summary>Show data</summary>
                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Day</th>
                        <th class="num">Conversations</th>
                        <th class="num">Messages</th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (row of overview.agent.daily; track row.day) {
                        <tr>
                          <td class="nowrap">{{ shortDay(row.day) }}</td>
                          <td class="num">{{ row.conversations }}</td>
                          <td class="num">{{ row.messages }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              </details>
            }
          </section>

          <div class="stack" style="gap: 1rem">
            <app-health-card
              [health]="overview.health"
              [knowledge]="overview.knowledge"
              [content]="overview.content"
            />
            <app-attention-card [actions]="overview.pending_actions" />
          </div>
        </div>

        <!-- Fila 1: KPI de uso -->
        <div class="stat-grid" style="margin-bottom: 1rem">
          <app-stat
            label="Conversations"
            testId="stat-conversations"
            [value]="overview.agent.conversations_in_window"
            [foot]="overview.agent.conversations_total + ' total, all time'"
          />
          <app-stat
            label="Active users"
            [value]="overview.agent.distinct_users_in_window"
            [foot]="'of ' + overview.training.users_total + ' non-demo accounts'"
            hint="Users who started at least one conversation in the window. Demo traffic is included in agent metrics because its tokens and latency are real."
          />
          <app-stat
            label="Response latency"
            [value]="duration(overview.agent.latency.p50_ms)"
            [foot]="latencyFoot()"
            hint="Median (p50) using percentile_disc: always a value that a real request actually took, never an interpolation."
          />
          <app-stat
            label="Grounded answers"
            [value]="groundedValue()"
            [foot]="groundedFoot()"
            hint="Assistant answers that cited at least one retrieved source from the knowledge base."
          />
        </div>

        <!-- Fila 2: desglose. Lista de barras de un solo hue, no tartas: con uno o dos
             proveedores una tarta de un gajo no compara nada. -->
        <div class="split even" style="margin-bottom: 1rem">
          <section class="card">
            <div class="card-head"><h2>Usage by provider</h2></div>
            <app-bar-list
              [rows]="providerRows()"
              emptyText="No assistant messages in this window."
            />
          </section>

          <section class="card">
            <div class="card-head"><h2>Knowledge coverage</h2></div>
            <app-bar-list [rows]="knowledgeRows()" emptyText="No documents indexed yet." />
            <p class="hint">
              {{ overview.knowledge.chunks_total }} chunks ·
              {{ overview.knowledge.embedding_models.join(', ') || 'no embedding model' }}
              @if (
                overview.knowledge.declared_chunk_count_total !== overview.knowledge.chunks_total
              ) {
                <br />
                <span style="color: var(--warn)">
                  Documents declare
                  {{ overview.knowledge.declared_chunk_count_total }} chunks but the table holds
                  {{ overview.knowledge.chunks_total }}: an ingestion finished halfway.
                </span>
              }
            </p>
          </section>
        </div>

        <!-- Fila 3: inventario. Sin delta ni sparkline: es un recuento, no una tendencia. Y nunca
             está a cero, así que da cuerpo a la página sin inventar analítica. -->
        <div class="stat-grid" style="margin-bottom: 1rem">
          <app-stat
            label="Equipment"
            [value]="overview.content.machines.published"
            [foot]="inventoryFoot(overview.content.machines.draft, 'draft')"
          />
          <app-stat
            label="Modules & lessons"
            [value]="
              overview.content.modules.published + ' / ' + overview.content.lessons.published
            "
            [foot]="
              minutesToHours(overview.content.lessons.estimated_minutes_total) + ' of content'
            "
          />
          <app-stat
            label="Knowledge base"
            [value]="overview.knowledge.documents_indexed"
            [foot]="overview.knowledge.chunks_total + ' vectorised chunks'"
          />
          <app-stat label="Videos" [value]="overview.content.videos.ready" [foot]="videosFoot()" />
        </div>

        <!-- Progreso de formación -->
        <div class="split even" style="margin-bottom: 1rem">
          <section class="card">
            <div class="card-head">
              <h2>Training progress</h2>
              <span class="badge">demo account excluded</span>
            </div>

            @if (overview.training.progress_rows_total === 0) {
              <div class="empty compact">
                No training activity from non-demo accounts yet. The shared demo login is excluded
                on purpose: its completions would misrepresent adoption rather than measure it.
              </div>
            } @else {
              <app-bar-list [rows]="progressRows()" />
              <div style="margin-top: 1.25rem">
                <div class="between" style="margin-bottom: 0.4rem">
                  <span class="muted" style="font-size: var(--fs-sm)">Overall completion</span>
                  <strong>{{ percent(overview.training.completion_percent) }}</strong>
                </div>
                <div class="meter">
                  <div
                    class="meter-fill"
                    [class.ok]="(overview.training.completion_percent ?? 0) >= 60"
                    [style.width.%]="overview.training.completion_percent ?? 0"
                  ></div>
                </div>
                <p class="hint">
                  {{ overview.training.lessons_completed }} of
                  {{ overview.training.progress_rows_total }} started lessons completed · average
                  watched {{ percent(overview.training.average_watched_percent) }}
                </p>
              </div>
            }
          </section>

          <section class="card muted">
            <div class="card-head"><h2>Coming soon</h2></div>
            <p style="margin: 0 0 1rem">
              <strong>Assessments &amp; certificates.</strong> The data model is already in the
              database — quizzes, attempts, scores and issued certificates — but there is no API
              yet, so no metrics are shown rather than a permanent row of zeros.
            </p>
            <div class="row">
              <span class="badge">Quizzes</span>
              <span class="badge">Attempts</span>
              <span class="badge">Certificates</span>
            </div>
          </section>
        </div>

        <app-recent-activity [rows]="overview.recent_conversations" />
      } @else if (stats.loading()) {
        <div class="stat-grid" style="margin-bottom: 1rem">
          @for (placeholder of [1, 2, 3, 4]; track placeholder) {
            <app-stat label="Loading" [value]="null" [loading]="true" />
          }
        </div>
        <div class="card">
          <div class="skeleton skeleton-line" style="width: 30%; height: 20px"></div>
          <div class="skeleton" style="height: 80px; margin-top: 1rem"></div>
        </div>
      }
    </div>
  `,
})
export class DashboardComponent {
  readonly stats = inject(StatsService);

  readonly ranges = [7, 30, 90];
  readonly days = signal(30);

  readonly data = computed(() => this.stats.overview());

  readonly NO_DATA = NO_DATA;
  readonly compact = compact;
  readonly duration = duration;
  readonly percent = percent;
  readonly shortDay = shortDay;
  readonly relativeTime = relativeTime;
  readonly minutesToHours = minutesToHours;

  readonly messageSeries = computed(() => this.data()?.agent.daily.map((d) => d.messages) ?? []);
  readonly daySeries = computed(() => this.data()?.agent.daily.map((d) => d.day) ?? []);

  readonly providerRows = computed<BarRow[]>(
    () =>
      this.data()?.agent.by_provider.map((usage) => ({
        label: usage.provider,
        value: usage.assistant_messages,
        display: `${usage.assistant_messages}`,
        foot:
          `${compact(usage.total_tokens)} tokens · ` +
          `${duration(usage.avg_latency_ms)} average latency`,
      })) ?? [],
  );

  readonly knowledgeRows = computed<BarRow[]>(() => {
    const knowledge = this.data()?.knowledge;
    if (!knowledge) {
      return [];
    }
    return knowledge.documents_by_source_type.map((entry) => ({
      label: this.sourceTypeLabel(entry.source_type),
      value: entry.total,
      display: `${entry.total}`,
    }));
  });

  readonly progressRows = computed<BarRow[]>(() => {
    const training = this.data()?.training;
    if (!training) {
      return [];
    }
    return [
      { label: 'Completed', value: training.lessons_completed },
      { label: 'In progress', value: training.lessons_in_progress },
    ];
  });

  constructor() {
    this.stats.loadOnce();
  }

  setRange(days: number): void {
    this.days.set(days);
    this.stats.load(days);
  }

  reload(): void {
    this.stats.load(this.days());
  }

  latencyFoot(): string {
    const latency = this.data()?.agent.latency;
    if (!latency || latency.sample_size === 0) {
      return 'no messages in this window';
    }
    // El tamaño de muestra va SIEMPRE visible: un p95 sobre 3 respuestas es un dato real pero no
    // es una medición, y quien lo lee tiene derecho a saberlo.
    const prefix = latency.sample_size < 20 ? 'small sample · ' : '';
    return `${prefix}p95 ${duration(latency.p95_ms)} · n=${latency.sample_size}`;
  }

  groundedValue(): string {
    const agent = this.data()?.agent;
    if (!agent) {
      return NO_DATA;
    }
    return percentOrFraction(agent.grounded_assistant_messages, agent.assistant_messages_in_window);
  }

  groundedFoot(): string {
    const agent = this.data()?.agent;
    if (!agent || agent.assistant_messages_in_window === 0) {
      return 'no assistant answers yet';
    }
    return (
      `${agent.grounded_assistant_messages} of ${agent.assistant_messages_in_window} ` +
      `answers cited a source`
    );
  }

  videosFoot(): string {
    const videos = this.data()?.content.videos;
    if (!videos) {
      return '';
    }
    if (videos.total === 0) {
      return 'none uploaded';
    }
    const parts = [`${videos.total} total`];
    if (videos.ready_minutes !== null) {
      parts.push(minutesToHours(videos.ready_minutes));
    }
    if (videos.total_size_mb !== null) {
      parts.push(`${videos.total_size_mb} MB`);
    }
    return parts.join(' · ');
  }

  /** Un cero necesita contexto o se lee como un fallo del sistema. */
  inventoryFoot(count: number, noun: string): string {
    if (count === 0) {
      return `no ${noun} — nothing pending`;
    }
    return `${count} in ${noun}`;
  }

  private sourceTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      manual_pdf: 'Manuals (PDF)',
      video_transcript: 'Video transcripts',
      raw_text: 'Pasted text',
    };
    return labels[type] ?? type;
  }
}
