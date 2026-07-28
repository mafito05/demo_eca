import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { KnowledgeStats, ContentStats, SystemHealthStats } from '../../core/models/api.models';
import { IconComponent } from '../../shared/icon/icon.component';
import { percent } from '../../shared/format';

type Level = 'ok' | 'warn' | 'danger' | 'neutral';

interface HealthRow {
  key: string;
  level: Level;
  detail: string;
}

/**
 * Estado del sistema en cuatro afirmaciones.
 *
 * Es la tarjeta que se ve bien **precisamente** cuando hay pocos datos, y por eso está arriba: cada
 * fila es una afirmación categórica ("el proveedor responde", "el índice está al día"), no una
 * métrica que necesite volumen para significar algo. Con una máquina y seis chunks, un gráfico
 * queda plano pero estas cuatro filas informan igual que con mil.
 *
 * El punto de estado va **siempre** con texto. El color solo no comunica a quien no distingue rojo
 * de verde, que es alrededor del 4 % de los hombres.
 *
 * Detalle deliberado: "2 tools activas, ninguna invocación" es un punto **neutro**, no un error.
 * Marcar en rojo algo que nadie ha usado todavía enseña al admin a ignorar los colores.
 */
@Component({
  selector: 'app-health-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [IconComponent],
  template: `
    <section class="card">
      <div class="card-head">
        <h2>System health</h2>
        <app-icon name="check-circle" [size]="18" />
      </div>

      <div class="kv">
        @for (row of rows(); track row.key) {
          <div class="kv-row">
            <span class="dot" [class]="row.level"></span>
            <span class="kv-key">{{ row.key }}</span>
            <span class="kv-val">{{ row.detail }}</span>
          </div>
        }
      </div>
    </section>
  `,
})
export class HealthCardComponent {
  readonly health = input.required<SystemHealthStats>();
  readonly knowledge = input.required<KnowledgeStats>();
  readonly content = input.required<ContentStats>();

  readonly rows = computed<HealthRow[]>(() => {
    const health = this.health();
    const knowledge = this.knowledge();
    const videos = this.content().videos;

    return [
      {
        key: 'LLM provider',
        level: this.providerLevel(),
        detail: this.providerDetail(),
      },
      {
        key: 'Knowledge index',
        level:
          knowledge.documents_failed > 0
            ? 'danger'
            : knowledge.documents_pending + knowledge.documents_processing > 0
              ? 'warn'
              : knowledge.documents_indexed > 0
                ? 'ok'
                : 'neutral',
        detail:
          knowledge.documents_total === 0
            ? 'no documents'
            : `${knowledge.documents_indexed}/${knowledge.documents_total} indexed · ` +
              `${knowledge.chunks_total} chunks`,
      },
      {
        key: 'Video pipeline',
        level:
          videos.failed > 0
            ? 'danger'
            : health.videos_stuck_processing > 0
              ? 'warn'
              : videos.ready > 0
                ? 'ok'
                : 'neutral',
        detail:
          videos.total === 0
            ? 'no videos'
            : `${videos.ready} ready · ${videos.processing + videos.queued} processing` +
              (videos.failed ? ` · ${videos.failed} failed` : ''),
      },
      {
        key: 'HTTP tools',
        level: this.toolsLevel(),
        detail: this.toolsDetail(),
      },
    ];
  });

  private providerLevel(): Level {
    const health = this.health();
    if (health.provider_credentials_active === 0) {
      return 'danger';
    }
    if (health.provider_credentials_failing_check > 0) {
      return 'danger';
    }
    return health.provider_credentials_never_checked > 0 ? 'warn' : 'ok';
  }

  private providerDetail(): string {
    const health = this.health();
    if (health.provider_credentials_active === 0) {
      return 'none active';
    }
    if (health.provider_credentials_failing_check > 0) {
      return `${health.provider_credentials_failing_check} failing check`;
    }
    if (health.provider_credentials_never_checked > 0) {
      return `${health.provider_credentials_active} active · never tested`;
    }
    return `${health.provider_credentials_active} active · verified`;
  }

  private toolsLevel(): Level {
    const health = this.health();
    if (health.tools_total === 0) {
      return 'neutral';
    }
    if (health.tool_error_percent !== null && health.tool_error_percent > 20) {
      return 'danger';
    }
    // Registradas pero sin usar todavía: eso no es un problema, es un dato.
    return health.tool_invocations_in_window === 0 ? 'neutral' : 'ok';
  }

  private toolsDetail(): string {
    const health = this.health();
    if (health.tools_total === 0) {
      return 'none registered';
    }
    if (health.tool_invocations_in_window === 0) {
      return `${health.tools_active} active · no calls yet`;
    }
    return (
      `${health.tool_invocations_in_window} calls · ` +
      `${percent(health.tool_error_percent)} errors`
    );
  }
}
