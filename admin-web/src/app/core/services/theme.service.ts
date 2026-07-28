import { Injectable, effect, signal } from '@angular/core';

export type ThemePreference = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'demoeca.theme';

/**
 * Preferencia de tema, con tres estados.
 *
 * `system` no es lo mismo que "claro": alguien que trabaja con el sistema en oscuro espera que el
 * panel lo siga sin tener que elegirlo, y quien quiere forzar uno concreto también debe poder.
 * De ahí que sea un ciclo de tres y no un interruptor.
 *
 * La implementación es un atributo `data-theme` en `<html>`, que los tokens leen (ver
 * `styles/_tokens.scss`). Para `system` se **quita** el atributo, dejando que gane la media query.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly preference = signal<ThemePreference>(this.restore());

  constructor() {
    effect(() => this.apply(this.preference()));
  }

  set(preference: ThemePreference): void {
    this.preference.set(preference);
    try {
      localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      /* modo privado o almacenamiento lleno: el tema simplemente no persiste */
    }
  }

  /** Tema efectivo, resolviendo `system` contra el sistema operativo. */
  resolved(): 'light' | 'dark' {
    const preference = this.preference();
    if (preference !== 'system') {
      return preference;
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  private apply(preference: ThemePreference): void {
    const root = document.documentElement;
    if (preference === 'system') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', preference);
    }
  }

  private restore(): ThemePreference {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'light' || stored === 'dark' || stored === 'system') {
        return stored;
      }
    } catch {
      /* sin almacenamiento accesible */
    }
    return 'system';
  }
}
