import { Component, OnDestroy, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AgentChatService } from '../../core/services/agent-chat.service';
import { AuthService } from '../../core/services/auth.service';
import { IconComponent } from '../../shared/icon/icon.component';
import { IconName } from '../../shared/icon/icons';

/**
 * Contenedor del Agent Builder: cabecera común y pestañas (D-042).
 *
 * Antes eran cinco entradas del menú lateral. Son cinco caras de una sola herramienta —se
 * configura un agente, se le da conocimiento, se le conectan proveedores y tools, y se prueba— y
 * presentarlas como módulos independientes obligaba a reconstruir mentalmente esa relación.
 *
 * **El ciclo de vida del WebSocket vive aquí, no en el playground.** Es el único cambio funcional
 * de la consolidación, y es necesario: si `disconnect()` siguiera en `ngOnDestroy` del playground,
 * ir a Knowledge a mirar un documento y volver mataría la conversación en curso, que es
 * exactamente el recorrido que las pestañas pretenden facilitar.
 *
 * Se descartó el otro diseño posible —split permanente con el playground fijo a la derecha—
 * porque tres de estas cinco pantallas ya usan `.split` por dentro (tabla + formulario). Anidar
 * un split dentro de otro con `--page-max: 1400px` deja columnas de ~330 px, y los formularios de
 * Knowledge y Tools quedan inservibles.
 */
@Component({
  selector: 'app-agent-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IconComponent],
  template: `
    <div class="page">
      <div class="page-head">
        <h1>Agent Builder</h1>
        <p>
          Configure the assistant, feed it documentation, connect providers and tools, and test the
          result — all in one place.
        </p>
      </div>

      <nav class="tabs" aria-label="Agent Builder sections">
        @for (tab of tabs; track tab.route) {
          @if (!tab.superadminOnly || auth.isSuperadmin()) {
            <a
              class="tab"
              [routerLink]="tab.route"
              routerLinkActive="active"
              ariaCurrentWhenActive="page"
            >
              <app-icon [name]="tab.icon" [size]="16" />
              {{ tab.label }}
            </a>
          }
        }
      </nav>

      <router-outlet />
    </div>
  `,
})
export class AgentLayoutComponent implements OnDestroy {
  readonly auth = inject(AuthService);
  private readonly chat = inject(AgentChatService);

  readonly tabs: { label: string; route: string; icon: IconName; superadminOnly?: boolean }[] = [
    { label: 'Playground', route: 'playground', icon: 'chat' },
    { label: 'Agents', route: 'agents', icon: 'sliders' },
    { label: 'Knowledge', route: 'knowledge', icon: 'book' },
    { label: 'Providers', route: 'providers', icon: 'key', superadminOnly: true },
    { label: 'Tools', route: 'tools', icon: 'plug', superadminOnly: true },
  ];

  constructor() {
    // Se conecta al entrar en cualquier pestaña, no solo en el playground: así el hilo ya existe
    // cuando el usuario llega desde "Test in playground" y no hay una espera de handshake.
    this.chat.connect();
  }

  ngOnDestroy(): void {
    // Se corta al salir del Agent Builder por completo, no al cambiar de pestaña.
    this.chat.disconnect();
  }
}
