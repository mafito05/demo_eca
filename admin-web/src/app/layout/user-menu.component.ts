import { Component, HostListener, inject, signal } from '@angular/core';

import { AuthService } from '../core/services/auth.service';
import { ThemeService, ThemePreference } from '../core/services/theme.service';
import { IconComponent } from '../shared/icon/icon.component';
import { IconName } from '../shared/icon/icons';

/**
 * Menú de usuario del topbar: identidad, rol, tema y salida.
 *
 * El selector de tema vive aquí y no como un botón suelto porque un ciclo de tres estados
 * (sistema/claro/oscuro) en un solo botón obliga a pulsarlo a ciegas hasta acertar. Como lista se
 * ve cuál está activo.
 */
@Component({
  selector: 'app-user-menu',
  imports: [IconComponent],
  template: `
    <div class="menu-wrap">
      <button
        class="who"
        type="button"
        (click)="open.set(!open())"
        [attr.aria-expanded]="open()"
        aria-haspopup="menu"
      >
        <span class="avatar" aria-hidden="true">{{ initials() }}</span>
        <span class="nowrap">{{ auth.currentUser()?.full_name }}</span>
        <app-icon name="chevron-down" [size]="14" />
      </button>

      @if (open()) {
        <div class="menu" role="menu">
          <div class="menu-label">{{ auth.currentUser()?.email }}</div>
          <div style="padding: 0 0.75rem 0.5rem">
            <span class="badge accent">{{ auth.currentUser()?.role }}</span>
          </div>

          <div class="menu-sep"></div>
          <div class="menu-label">Appearance</div>
          @for (option of themes; track option.value) {
            <button
              class="menu-item"
              type="button"
              role="menuitemradio"
              [attr.aria-checked]="theme.preference() === option.value"
              [class.active]="theme.preference() === option.value"
              (click)="theme.set(option.value)"
            >
              <app-icon [name]="option.icon" />
              {{ option.label }}
            </button>
          }

          <div class="menu-sep"></div>
          <button class="menu-item" type="button" role="menuitem" (click)="auth.logout()">
            <app-icon name="log-out" />
            Sign out
          </button>
        </div>
      }
    </div>
  `,
})
export class UserMenuComponent {
  readonly auth = inject(AuthService);
  readonly theme = inject(ThemeService);
  readonly open = signal(false);

  readonly themes: { value: ThemePreference; label: string; icon: IconName }[] = [
    { value: 'system', label: 'System', icon: 'monitor' },
    { value: 'light', label: 'Light', icon: 'sun' },
    { value: 'dark', label: 'Dark', icon: 'moon' },
  ];

  initials(): string {
    const name = this.auth.currentUser()?.full_name ?? '';
    return (
      name
        .split(' ')
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() ?? '')
        .join('') || '?'
    );
  }

  // Un menú que solo se cierra con su propio botón deja al usuario atrapado: hay que poder
  // descartarlo pulsando fuera o con Escape, que es lo que espera cualquiera.
  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (this.open() && !(event.target as HTMLElement).closest('app-user-menu')) {
      this.open.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.open.set(false);
  }
}
