import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ICONS, IconName } from './icons';

/**
 * Icono SVG inline.
 *
 * El detalle que importa: el path se pinta con `<svg:path [attr.d]>`, **no** con `[innerHTML]`.
 * El sanitizador de Angular elimina SVG inyectado por innerHTML (queda un hueco silencioso, sin
 * error en consola), y bindear `d` como atributo esquiva `DomSanitizer` por completo. Los paths
 * son constantes del bundle, nunca datos de usuario, así que no hay superficie de inyección.
 *
 * Por defecto es decorativo (`aria-hidden`), que es el 95 % de los usos: un icono junto a su
 * etiqueta de texto no debe anunciarse dos veces. Pasar `label` lo convierte en `role="img"`.
 *
 * OJO con `capture-panel.mjs`: busca botones comparando `textContent`. Un `<svg aria-hidden>` no
 * aporta textContent, así que es seguro meter iconos dentro de esos botones — lo que NO se puede
 * es añadirles un `<title>` ni un `<span class="sr-only">`.
 */
@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      [attr.stroke-width]="strokeWidth()"
      stroke-linecap="round"
      stroke-linejoin="round"
      [attr.role]="label() ? 'img' : null"
      [attr.aria-label]="label() || null"
      [attr.aria-hidden]="label() ? null : 'true'"
    >
      <svg:path [attr.d]="path()" />
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      flex: 0 0 auto;
    }
  `,
})
export class IconComponent {
  readonly name = input.required<IconName>();
  readonly size = input(16);
  readonly strokeWidth = input(1.6);
  /** Si se pasa, el icono se anuncia. Si no, queda oculto para lectores de pantalla. */
  readonly label = input('');

  readonly path = computed(() => ICONS[this.name()] ?? '');
}
