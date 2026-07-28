import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map, startWith } from 'rxjs';

import { LayoutService } from '../core/services/layout.service';
import { StatsService } from '../core/services/stats.service';
import { IconComponent } from '../shared/icon/icon.component';
import { UserMenuComponent } from './user-menu.component';

/**
 * Barra superior: contexto a la izquierda, estado y usuario a la derecha.
 *
 * Los breadcrumbs se derivan de `data.breadcrumb` recorriendo el árbol de rutas activo, no de una
 * lista paralela: una lista se desincroniza el día que alguien añade una ruta.
 *
 * La pastilla de salud enlaza al dashboard y se alimenta del **mismo** `StatsService` que la
 * pantalla, así que no hay una segunda petición ni riesgo de que las dos discrepen. Si no hay
 * datos todavía, simplemente no se pinta: una pastilla gris "unknown" no informa de nada.
 */
@Component({
  selector: 'app-topbar',
  imports: [RouterLink, IconComponent, UserMenuComponent],
  template: `
    <header class="topbar">
      <div class="topbar-left">
        <button
          class="icon-btn"
          type="button"
          (click)="layout.toggle()"
          [attr.aria-label]="layout.mode() === 'drawer' ? 'Open navigation' : 'Toggle sidebar'"
        >
          <app-icon name="menu" [size]="18" />
        </button>

        <nav class="crumbs" aria-label="Breadcrumb">
          @for (crumb of crumbs(); track crumb; let last = $last) {
            <span class="crumb">{{ crumb }}</span>
            @if (!last) {
              <span class="crumb-sep" aria-hidden="true">/</span>
            }
          }
        </nav>
      </div>

      <div class="topbar-right">
        @if (stats.overview()) {
          <a
            routerLink="/dashboard"
            class="badge"
            [class.ok]="stats.healthLevel() === 'ok'"
            [class.warn]="stats.healthLevel() === 'warn'"
            [class.danger]="stats.healthLevel() === 'danger'"
            [attr.title]="'Open the dashboard'"
          >
            <span
              class="dot"
              [class.ok]="stats.healthLevel() === 'ok'"
              [class.warn]="stats.healthLevel() === 'warn'"
              [class.danger]="stats.healthLevel() === 'danger'"
            ></span>
            {{ healthLabel() }}
          </a>
        }

        <app-user-menu />
      </div>
    </header>
  `,
})
export class TopbarComponent {
  readonly layout = inject(LayoutService);
  readonly stats = inject(StatsService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map(() => this.router.url),
      startWith(this.router.url),
    ),
    { initialValue: this.router.url },
  );

  readonly crumbs = computed(() => {
    // Depende de `url()` para recalcularse en cada navegación: el snapshot del router no es un
    // signal, así que sin esta lectura el computed se quedaría con el primer valor.
    this.url();
    const trail: string[] = [];
    let node: ActivatedRoute | null = this.route.root;
    while (node) {
      const label = node.snapshot.data?.['breadcrumb'];
      if (typeof label === 'string' && label && trail.at(-1) !== label) {
        trail.push(label);
      }
      node = node.firstChild;
    }
    return trail.length ? trail : ['Overview'];
  });

  readonly healthLabel = computed(() => {
    const issues = this.stats.openIssues();
    if (this.stats.healthLevel() === 'ok') {
      return 'All systems OK';
    }
    return issues === 1 ? '1 issue' : `${issues} issues`;
  });

  constructor() {
    this.stats.loadOnce();
  }
}
