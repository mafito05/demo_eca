import { Injectable, signal } from '@angular/core';

export type SidebarMode = 'expanded' | 'rail' | 'drawer';

const STORAGE_KEY = 'demoeca.sidebar';
const RAIL_BELOW = 1200;
const DRAWER_BELOW = 900;

/**
 * Estado del armazón: modo del sidebar y si el drawer está abierto.
 *
 * Se hace con un servicio y no solo con media queries de CSS porque el botón de colapso necesita
 * estado explícito: en el tramo ancho el usuario puede querer el rail, y eso una media query no lo
 * sabe. La media query se usa como **valor inicial**, no como única fuente.
 *
 * La preferencia se guarda, pero el modo `drawer` no: es consecuencia del ancho de la ventana, no
 * una elección. Guardarlo dejaría a alguien con el panel en modo cajón en un monitor grande.
 */
@Injectable({ providedIn: 'root' })
export class LayoutService {
  readonly mode = signal<SidebarMode>('expanded');
  readonly drawerOpen = signal(false);

  constructor() {
    this.syncToViewport();
    window.addEventListener('resize', () => this.syncToViewport());
  }

  /** Alterna entre expandido y rail; en móvil abre y cierra el cajón. */
  toggle(): void {
    if (this.mode() === 'drawer') {
      this.drawerOpen.update((open) => !open);
      return;
    }
    const next: SidebarMode = this.mode() === 'expanded' ? 'rail' : 'expanded';
    this.mode.set(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* sin almacenamiento accesible */
    }
  }

  /** Se llama al navegar: en móvil el cajón debe cerrarse solo, o tapa el destino. */
  closeDrawer(): void {
    this.drawerOpen.set(false);
  }

  private syncToViewport(): void {
    const width = window.innerWidth;
    if (width < DRAWER_BELOW) {
      this.mode.set('drawer');
      return;
    }
    this.drawerOpen.set(false);
    if (width < RAIL_BELOW) {
      this.mode.set('rail');
      return;
    }
    this.mode.set(this.stored() ?? 'expanded');
  }

  private stored(): SidebarMode | null {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return value === 'expanded' || value === 'rail' ? value : null;
    } catch {
      return null;
    }
  }
}
