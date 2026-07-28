import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { LayoutService } from '../core/services/layout.service';
import { AuthService } from '../core/services/auth.service';
import { IconComponent } from '../shared/icon/icon.component';
import { IconName } from '../shared/icon/icons';

interface NavEntry {
  label: string;
  route: string;
  icon: IconName;
  superadminOnly?: boolean;
}

/**
 * Navegación lateral.
 *
 * Cinco entradas del Agent Builder se han reducido a **una** (D-042): eran cinco caras de la misma
 * herramienta presentadas como cinco módulos independientes, y el sidebar hacía que pareciesen
 * secciones sin relación entre sí. Ahora las pestañas viven dentro de `/agent`.
 *
 * El bloque de usuario ya no está aquí: se movió al topbar, que es donde se busca. Tenerlo al pie
 * del sidebar duplicaba función con un sitio poco convencional.
 *
 * Los enlaces reservados a `superadmin` se ocultan por rol. Es solo presentación —el `roleGuard`
 * bloquea la ruta y el backend devuelve 403 igualmente— pero enseñar una puerta que no se puede
 * abrir es peor experiencia que no enseñarla.
 */
@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive, IconComponent],
  template: `
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">EC</span>
        <span class="brand-text">
          <span class="brand-name">DemoECA</span>
          <span class="brand-sub">MedTech Training</span>
        </span>
      </div>

      <nav class="sidebar-nav" aria-label="Main">
        @for (group of groups; track group.title) {
          <span class="nav-group">{{ group.title }}</span>
          @for (entry of group.entries; track entry.route) {
            @if (!entry.superadminOnly || auth.isSuperadmin()) {
              <a
                class="nav-item"
                [routerLink]="entry.route"
                routerLinkActive="active"
                [routerLinkActiveOptions]="{ exact: false }"
                [attr.title]="entry.label"
                (click)="layout.closeDrawer()"
              >
                <app-icon [name]="entry.icon" [size]="17" />
                <span class="nav-label">{{ entry.label }}</span>
              </a>
            }
          }
        }

        <span class="nav-group">Coming soon</span>
        @for (soon of comingSoon; track soon.label) {
          <span class="nav-item soon" [title]="'Data model ready, API pending'">
            <app-icon [name]="soon.icon" [size]="17" />
            <span class="nav-label">{{ soon.label }}</span>
          </span>
        }
      </nav>

      <div class="sidebar-foot">
        <button
          class="icon-btn"
          type="button"
          (click)="layout.toggle()"
          [attr.aria-label]="layout.mode() === 'rail' ? 'Expand sidebar' : 'Collapse sidebar'"
        >
          <app-icon [name]="layout.mode() === 'rail' ? 'chevron-right' : 'chevron-left'" />
        </button>
      </div>
    </aside>
  `,
})
export class SidebarComponent {
  readonly auth = inject(AuthService);
  readonly layout = inject(LayoutService);

  readonly groups: { title: string; entries: NavEntry[] }[] = [
    {
      title: 'Overview',
      entries: [{ label: 'Dashboard', route: '/dashboard', icon: 'dashboard' }],
    },
    {
      title: 'Content',
      entries: [
        { label: 'Equipment & QR', route: '/machines', icon: 'qr' },
        { label: 'Training', route: '/lms', icon: 'graduation' },
      ],
    },
    {
      title: 'Agent',
      entries: [{ label: 'Agent Builder', route: '/agent', icon: 'sparkles' }],
    },
  ];

  readonly comingSoon: { label: string; icon: IconName }[] = [
    { label: 'Assessments', icon: 'clipboard-check' },
    { label: 'Certificates', icon: 'award' },
  ];
}
