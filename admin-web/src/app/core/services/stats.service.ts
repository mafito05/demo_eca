import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';

import { environment } from '../../../environments/environment';
import { StatsOverview } from '../models/api.models';

export type HealthLevel = 'ok' | 'warn' | 'danger' | 'unknown';

/**
 * Estado del dashboard, compartido entre la pantalla y la pastilla de salud del topbar.
 *
 * Es un servicio con signals y no una petición por componente porque los dos consumidores quieren
 * el mismo dato: pedirlo dos veces mostraría dos verdades distintas en la misma pantalla.
 *
 * `loading` distingue la primera carga de un refetch a propósito. En el primer render se pintan
 * skeletons; al recargar se **mantiene el dato anterior atenuado**. Un skeleton que reaparece
 * produce salto de layout y se lee como un fallo, no como una actualización.
 */
@Injectable({ providedIn: 'root' })
export class StatsService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/stats`;

  readonly overview = signal<StatsOverview | null>(null);
  readonly loading = signal(false);
  readonly refetching = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastLoadedAt = signal<Date | null>(null);

  /** Peor estado de las comprobaciones de salud. Alimenta la pastilla del topbar. */
  readonly healthLevel = computed<HealthLevel>(() => {
    const data = this.overview();
    if (!data) {
      return 'unknown';
    }
    const worst = data.pending_actions.reduce<HealthLevel>((level, action) => {
      if (action.severity === 'critical') return 'danger';
      if (action.severity === 'warning' && level !== 'danger') return 'warn';
      return level;
    }, 'ok');
    return worst;
  });

  readonly openIssues = computed(
    () =>
      this.overview()?.pending_actions.filter((action) => action.severity !== 'info').length ?? 0,
  );

  load(days = 30): void {
    const isFirstLoad = this.overview() === null;
    (isFirstLoad ? this.loading : this.refetching).set(true);
    this.error.set(null);

    this.http.get<StatsOverview>(`${this.base}/overview`, { params: { days } }).subscribe({
      next: (data) => {
        this.overview.set(data);
        this.lastLoadedAt.set(new Date());
        this.loading.set(false);
        this.refetching.set(false);
      },
      error: (err) => {
        // Se conserva el último payload bueno: una pantalla con datos de hace un minuto es más
        // útil que una en blanco, siempre que el error se anuncie.
        this.error.set(
          err?.status === 403
            ? 'Your account cannot view dashboard metrics.'
            : `Could not load metrics (${err?.status ?? 'no response'}).`,
        );
        this.loading.set(false);
        this.refetching.set(false);
      },
    });
  }

  /** Carga solo si no hay nada todavía. La usa el topbar para no duplicar la petición. */
  loadOnce(): void {
    if (this.overview() === null && !this.loading()) {
      this.load();
    }
  }
}
