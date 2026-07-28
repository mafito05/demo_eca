import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { RecentConversation } from '../../core/models/api.models';
import { clockTime, duration, relativeTime } from '../../shared/format';

/**
 * Últimas conversaciones del agente.
 *
 * Está aquí por una razón concreta de diseño: **es el elemento que mejor aparenta con datos
 * mínimos**. Seis filas llenan una tabla de forma natural y cada una es un hecho verificable
 * ("Nadia preguntó por el E-204 hace dos horas, dos mensajes, 2,3 s"), mientras que seis puntos
 * dejan un gráfico con aspecto de roto.
 *
 * Las columnas numéricas llevan `.num` (`tabular-nums` + alineadas a la derecha) para poder
 * comparar de un vistazo. El valor grande de un KPI no lo lleva: ahí las cifras proporcionales se
 * leen mejor.
 */
@Component({
  selector: 'app-recent-activity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="card pad-0">
      <div class="card-head">
        <h2>Recent conversations</h2>
        <span class="muted" style="font-size: var(--fs-sm)">last {{ rows().length }}</span>
      </div>

      @if (rows().length === 0) {
        <div style="padding: 0 1.5rem 1.5rem">
          <div class="empty compact">
            No conversations yet. Open the Playground to ask the agent something.
          </div>
        </div>
      } @else {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>User</th>
                <th>Equipment</th>
                <th>Question</th>
                <th class="num">Messages</th>
                <th class="num">Median latency</th>
              </tr>
            </thead>
            <tbody>
              @for (row of rows(); track row.id) {
                <tr>
                  <td class="nowrap" [title]="row.created_at">
                    {{ relativeTime(row.created_at) }}
                    <span class="muted">· {{ clockTime(row.created_at) }}</span>
                  </td>
                  <td class="nowrap">{{ row.user_name }}</td>
                  <td class="nowrap">
                    @if (row.machine_code) {
                      <span class="mono">{{ row.machine_code }}</span>
                    } @else {
                      <span class="muted">no context</span>
                    }
                  </td>
                  <td class="trunc" style="max-width: 280px" [title]="row.title ?? ''">
                    {{ row.title ?? '—' }}
                  </td>
                  <td class="num">{{ row.message_count }}</td>
                  <td class="num">{{ duration(row.p50_ms) }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  `,
})
export class RecentActivityComponent {
  readonly rows = input.required<RecentConversation[]>();

  readonly relativeTime = relativeTime;
  readonly duration = duration;
  readonly clockTime = clockTime;
}
