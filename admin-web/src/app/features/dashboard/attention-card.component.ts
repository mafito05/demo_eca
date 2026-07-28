import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { PendingAction } from '../../core/models/api.models';
import { IconComponent } from '../../shared/icon/icon.component';
import { IconName } from '../../shared/icon/icons';

/**
 * Lista de lo que hay que arreglar, ordenada por severidad.
 *
 * El backend ya la entrega ordenada y con `resource`, la ruta del panel donde se resuelve cada
 * aviso. Un aviso sin acción detrás es ruido, y en cuanto aparecen tres que nadie puede resolver,
 * el admin deja de mirar la lista entera.
 *
 * **La lista vacía es el estado de victoria, no un hueco.** Se pinta explícitamente "todo en
 * orden" con el número de comprobaciones que pasaron. Una caja gris vacía se lee como "esto no
 * funciona todavía", que es lo contrario de lo que significa.
 */
@Component({
  selector: 'app-attention-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, IconComponent],
  template: `
    <section class="card">
      <div class="card-head">
        <h2>Needs attention</h2>
        @if (actions().length) {
          <span class="badge" [class.danger]="hasCritical()" [class.warn]="!hasCritical()">
            {{ actions().length }}
          </span>
        }
      </div>

      @if (actions().length === 0) {
        <div class="row" style="gap: 0.6rem; color: var(--ok)">
          <app-icon name="check-circle" [size]="20" />
          <span>
            <strong style="color: var(--text)">Everything is in order</strong><br />
            <span class="muted" style="font-size: var(--fs-sm)">
              {{ checksPassed() }} checks passed
            </span>
          </span>
        </div>
      } @else {
        <div class="checklist">
          @for (action of actions(); track action.code) {
            <div class="task" [class]="action.severity">
              <app-icon [name]="iconFor(action.severity)" [size]="17" />
              <span class="task-body">{{ action.message }}</span>
              @if (action.resource) {
                <a class="badge" [routerLink]="'/' + action.resource">Fix</a>
              }
            </div>
          }
        </div>
      }
    </section>
  `,
})
export class AttentionCardComponent {
  readonly actions = input.required<PendingAction[]>();
  /** Total de comprobaciones que hace el backend, para poder decir "N de N pasaron". */
  readonly totalChecks = input(6);

  hasCritical(): boolean {
    return this.actions().some((action) => action.severity === 'critical');
  }

  checksPassed(): number {
    return Math.max(0, this.totalChecks() - this.actions().length);
  }

  iconFor(severity: string): IconName {
    if (severity === 'critical') {
      return 'alert-triangle';
    }
    return severity === 'warning' ? 'clock' : 'info';
  }
}
