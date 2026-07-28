import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { NO_DATA } from '../format';
import { IconComponent } from '../icon/icon.component';

/**
 * Tile de KPI.
 *
 * Existe para que las reglas de "qué se pinta cuando no hay datos" vivan en UN sitio. Repartidas
 * por las plantillas derivan en una semana: aparece un tile que muestra `0 %` donde otro muestra
 * `—` para el mismo caso, y el dashboard empieza a afirmar cosas falsas.
 *
 * Las reglas que aplica:
 *
 * 1. `value === null` -> guion largo atenuado. Es "no lo sé", no "es cero".
 * 2. `delta === null` -> no se pinta el chip. Sin periodo previo con datos no existe variación, y
 *    un "+100 %" contra cero es un número inventado.
 * 3. El pie (`foot`) es obligatorio en la práctica: es donde va el tamaño de muestra, el
 *    denominador o la explicación de un cero ("0 failed — nothing to fix"). Un cero sin contexto
 *    se lee como un fallo del sistema.
 *
 * `data-testid` en el valor: el script de capturas necesita un centinela para saber que los datos
 * ya llegaron, en lugar de fotografiar el skeleton tras un tiempo fijo.
 */
@Component({
  selector: 'app-stat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [IconComponent],
  template: `
    <div class="stat">
      <p class="stat-label">
        {{ label() }}
        @if (hint()) {
          <span [title]="hint()" style="cursor: help; display: inline-flex">
            <app-icon name="info" [size]="13" />
          </span>
        }
      </p>

      @if (loading()) {
        <div class="skeleton skeleton-value"></div>
        <div class="skeleton skeleton-line" style="width: 40%"></div>
      } @else {
        <div class="row" style="gap: 0.5rem; align-items: baseline">
          <span
            class="stat-value"
            [class.undefined-value]="value() === null"
            [attr.data-testid]="testId() || null"
          >
            {{ value() === null ? NO_DATA : value() }}
          </span>

          @if (delta() !== null) {
            <span
              class="stat-delta"
              [class.up]="direction() === 'up'"
              [class.down]="direction() === 'down'"
              [class.flat]="direction() === 'flat'"
            >
              <app-icon
                [name]="
                  direction() === 'up'
                    ? 'trend-up'
                    : direction() === 'down'
                      ? 'trend-down'
                      : 'minus'
                "
                [size]="13"
              />
              {{ delta()! > 0 ? '+' : '' }}{{ delta() }}%
            </span>
          }
        </div>

        @if (foot()) {
          <p class="stat-foot">{{ foot() }}</p>
        }
      }
    </div>
  `,
})
export class StatTileComponent {
  readonly label = input.required<string>();
  /** Ya formateado. `null` significa "no hay datos" y se pinta como guion. */
  readonly value = input.required<string | number | null>();
  readonly foot = input('');
  /** Variación contra el periodo anterior. `null` oculta el chip por completo. */
  readonly delta = input<number | null>(null);
  /** Si es true, un delta negativo es BUENO (errores, latencia). */
  readonly invertDelta = input(false);
  readonly loading = input(false);
  readonly hint = input('');
  readonly testId = input('');

  readonly NO_DATA = NO_DATA;

  readonly direction = computed<'up' | 'down' | 'flat'>(() => {
    const value = this.delta();
    if (value === null || value === 0) {
      return 'flat';
    }
    const rising = value > 0;
    // Con `invertDelta`, bajar es mejorar: menos errores y menos latencia van en verde.
    return rising === !this.invertDelta() ? 'up' : 'down';
  });
}
