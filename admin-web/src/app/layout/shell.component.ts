import { Component, HostListener, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { LayoutService } from '../core/services/layout.service';
import { SidebarComponent } from './sidebar.component';
import { TopbarComponent } from './topbar.component';

/**
 * Armazón del backoffice: sidebar a altura completa, topbar sobre el contenido.
 *
 * El sidebar ocupa las dos filas del grid y el topbar solo la columna de contenido. Es el patrón
 * de Stripe o Linear, y evita el doble borde en la esquina superior izquierda que aparece cuando
 * la barra superior cruza por encima de la lateral.
 *
 * Este componente ya solo compone: la navegación está en `SidebarComponent`, el contexto y el
 * usuario en `TopbarComponent`, y las clases en `styles/_layout.scss`. Antes tenía 80 líneas de
 * estilos propios que no se podían reutilizar en ninguna otra parte.
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, SidebarComponent, TopbarComponent],
  template: `
    <a class="skip-link" href="#main">Skip to content</a>

    <div
      class="shell"
      [attr.data-sidebar]="layout.mode()"
      [class.drawer-open]="layout.drawerOpen()"
    >
      <app-sidebar />
      <app-topbar />

      @if (layout.mode() === 'drawer' && layout.drawerOpen()) {
        <button
          class="drawer-backdrop"
          type="button"
          aria-label="Close navigation"
          (click)="layout.closeDrawer()"
        ></button>
      }

      <main class="main" id="main" tabindex="-1"><router-outlet /></main>
    </div>
  `,
})
export class ShellComponent {
  readonly layout = inject(LayoutService);

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.layout.closeDrawer();
  }
}
