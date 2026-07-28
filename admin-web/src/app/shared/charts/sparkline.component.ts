import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import {
  VIEW_HEIGHT,
  VIEW_WIDTH,
  areaPath,
  barGeometry,
  linePath,
  preferBars,
  scalePoints,
} from './geometry';
import { shortDay } from '../format';

/**
 * Sparkline en SVG inline, sin librería de gráficos (D-041).
 *
 * El panel necesita tres primitivas de visualización y dos son CSS puro (`.bar-fill` y `.meter`).
 * Solo esta necesita un `path`, y son ~25 líneas de geometría. Traer 70-250 KB de librería para
 * una polilínea sería desproporcionado, y peor: cada librería impone su propio lenguaje visual
 * —tooltips, leyendas, tipografías, paleta— que habría que combatir en cada gráfico. Es el mismo
 * razonamiento por el que el panel no usa Angular Material (D-021).
 *
 * SVG y no canvas: hereda `var(--accent)`, así que se re-tematiza gratis al cambiar de tema claro
 * a oscuro, y es inspeccionable por `capture-panel.mjs`, que verifica el DOM. Un canvas sería
 * invisible para esa verificación y exigiría recalcular colores a mano.
 *
 * **Siempre acompañado de su tabla gemela** (`<details>` en el componente que lo usa): ningún
 * valor debe existir solo detrás de un puntero.
 */
@Component({
  selector: 'app-sparkline',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (hasData()) {
      <svg
        class="spark"
        [attr.viewBox]="'0 0 ' + VIEW_WIDTH + ' ' + VIEW_HEIGHT"
        preserveAspectRatio="none"
        role="img"
        [attr.aria-label]="ariaLabel()"
        (pointermove)="onPointerMove($event)"
        (pointerleave)="hovered.set(null)"
      >
        @if (asBars()) {
          @for (bar of bars(); track bar.index) {
            <svg:rect
              class="spark-bar"
              [attr.x]="bar.x"
              [attr.y]="bar.y"
              [attr.width]="bar.width"
              [attr.height]="bar.height"
              [attr.opacity]="hovered() === null || hovered() === bar.index ? 1 : 0.45"
            />
          }
        } @else {
          <svg:path class="spark-area" [attr.d]="area()" />
          <svg:path class="spark-line" [attr.d]="line()" />
          <!-- El último punto lleva marcador: es el valor que el lector busca primero. -->
          <svg:circle class="spark-last" [attr.cx]="last().x" [attr.cy]="last().y" r="3.5" />
        }
      </svg>

      <p class="hint" style="min-height: 1.2em; margin-top: 0.35rem">
        @if (hovered() !== null) {
          <strong>{{ values()[hovered()!] }}</strong> · {{ hoveredLabel() }}
        } @else {
          {{ summary() }}
        }
      </p>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    svg {
      /* Con preserveAspectRatio none el trazo se estiraría en horizontal; lo compensa la
       * regla vector-effect non-scaling-stroke de .spark-line en _components.scss. */
      height: 64px;
      cursor: crosshair;
    }
  `,
})
export class SparklineComponent {
  readonly values = input.required<number[]>();
  /** Etiquetas por punto, normalmente fechas `YYYY-MM-DD`. */
  readonly labels = input<string[]>([]);
  readonly ariaLabel = input('Activity over time');
  /** `auto` decide barras o línea según cuántos puntos tienen valor. */
  readonly mode = input<'auto' | 'line' | 'bars'>('auto');

  readonly VIEW_WIDTH = VIEW_WIDTH;
  readonly VIEW_HEIGHT = VIEW_HEIGHT;

  readonly hovered = signal<number | null>(null);

  readonly hasData = computed(() => this.values().length > 0);
  readonly asBars = computed(() =>
    this.mode() === 'auto' ? preferBars(this.values()) : this.mode() === 'bars',
  );

  readonly points = computed(() => scalePoints(this.values()));
  readonly bars = computed(() => barGeometry(this.values()));
  readonly line = computed(() => linePath(this.points()));
  readonly area = computed(() => areaPath(this.points()));
  readonly last = computed(
    () => this.points().at(-1) ?? { x: 0, y: VIEW_HEIGHT / 2, value: 0, index: 0 },
  );

  readonly hoveredLabel = computed(() => {
    const index = this.hovered();
    if (index === null) {
      return '';
    }
    const label = this.labels()[index];
    return label ? shortDay(label) : `point ${index + 1}`;
  });

  readonly summary = computed(() => {
    const values = this.values();
    if (!values.length) {
      return '';
    }
    const peak = Math.max(...values);
    const peakIndex = values.indexOf(peak);
    const label = this.labels()[peakIndex];
    return `Peak ${peak}${label ? ` on ${shortDay(label)}` : ''}`;
  });

  /**
   * Punto más cercano al puntero, no banda bajo el puntero.
   *
   * Con 30 puntos en ~300 unidades de viewBox cada banda mide ~10, muy por debajo del mínimo
   * cómodo de área de impacto. Redondear al índice más cercano hace que cualquier posición del
   * ratón siempre seleccione algo, que es lo que el usuario espera.
   */
  onPointerMove(event: PointerEvent): void {
    const target = event.currentTarget as SVGSVGElement;
    const bounds = target.getBoundingClientRect();
    if (bounds.width === 0) {
      return;
    }
    const ratio = (event.clientX - bounds.left) / bounds.width;
    const count = this.values().length;
    const index = Math.round(ratio * (count - 1));
    this.hovered.set(Math.min(count - 1, Math.max(0, index)));
  }
}
