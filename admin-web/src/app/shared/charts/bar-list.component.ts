import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface BarRow {
  label: string;
  value: number;
  /** Segunda línea opcional: contexto que evita que una fila con valor 0 sea inútil. */
  foot?: string;
  /** Texto ya formateado a la derecha. Si falta, se pinta `value`. */
  display?: string;
}

/**
 * Lista de barras horizontales, en CSS puro.
 *
 * **Por qué no una tarta.** Con uno o dos proveedores, una tarta de un solo gajo es un
 * anti-patrón: no compara nada y ocupa el mismo espacio. Esta lista se lee bien con una sola fila
 * y escala a cinco sin necesitar paleta categórica ni leyenda, así que sirve igual el día de la
 * demo (un proveedor) y el día que haya cinco.
 *
 * Un solo hue para todas las barras, por lo mismo: si las categorías no se comparan entre sí por
 * color —y aquí no, están una debajo de otra con su etiqueta— darles colores distintos añade
 * ruido y obliga a validar contraste de una paleta que no aporta.
 *
 * **El marcado ES la tabla de datos**: etiqueta, barra y valor están en el DOM, así que no hace
 * falta un `<details>` gemelo como con el sparkline.
 */
@Component({
  selector: 'app-bar-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (rows().length === 0) {
      <div class="empty compact">{{ emptyText() }}</div>
    } @else {
      <div class="bars">
        @for (row of sorted(); track row.label) {
          <div class="bar-row">
            <span class="bar-label" [title]="row.label">{{ row.label }}</span>
            <span class="bar-track">
              <span class="bar-fill" [style.width.%]="width(row.value)"></span>
            </span>
            <span class="bar-value">{{ row.display ?? row.value }}</span>
          </div>
          @if (row.foot) {
            <div class="bar-foot">{{ row.foot }}</div>
          }
        }
      </div>
    }
  `,
})
export class BarListComponent {
  readonly rows = input.required<BarRow[]>();
  readonly emptyText = input('No data yet.');
  /** Máximo explícito, para comparar dos listas con la misma escala. */
  readonly max = input<number | null>(null);

  readonly sorted = computed(() => [...this.rows()].sort((a, b) => b.value - a.value));

  private readonly scale = computed(() => {
    const explicit = this.max();
    if (explicit && explicit > 0) {
      return explicit;
    }
    // Nunca cero: con todas las filas a cero, dividir daría NaN y el ancho quedaría inválido.
    return Math.max(...this.rows().map((row) => row.value), 1);
  });

  width(value: number): number {
    return Math.max(0, (value / this.scale()) * 100);
  }
}
