/**
 * Formateo de valores del dashboard.
 *
 * Funciones puras y en un solo sitio, porque la regla de qué se pinta cuando un valor es `null`
 * es una decisión de producto, no de cada plantilla: si cada componente la resuelve a su manera,
 * en dos semanas hay tiles que muestran `0` donde otros muestran `—` para el mismo caso.
 *
 * LA REGLA: `null` es "no hay datos" y se pinta con guion largo atenuado. `0` es "hay datos y el
 * valor es cero" y se pinta como número. Son afirmaciones distintas.
 */

export const NO_DATA = '—';

/** Miles compactos. Un dashboard con `34310` obliga a contar dígitos; `34.3k` no. */
export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return NO_DATA;
  }
  if (Math.abs(value) < 1000) {
    return String(value);
  }
  if (Math.abs(value) < 1_000_000) {
    return `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}k`;
  }
  return `${(value / 1_000_000).toFixed(1)}M`;
}

/** Milisegundos a la unidad que se lee de un vistazo. */
export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) {
    return NO_DATA;
  }
  if (ms < 1000) {
    return `${Math.round(ms)} ms`;
  }
  return `${(ms / 1000).toFixed(1)} s`;
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) {
    return NO_DATA;
  }
  return `${value.toFixed(digits)}%`;
}

/**
 * Porcentaje o fracción, según lo fiable que sea.
 *
 * Con un denominador pequeño un porcentaje engaña: "67 %" sobre 3 casos suena a medición y es
 * una anécdota. Por debajo del umbral se muestra la fracción, que es honesta.
 */
export function percentOrFraction(
  numerator: number,
  denominator: number,
  minimumSample = 5,
): string {
  if (denominator <= 0) {
    return NO_DATA;
  }
  if (denominator < minimumSample) {
    return `${numerator} of ${denominator}`;
  }
  return `${Math.round((numerator / denominator) * 100)}%`;
}

/**
 * Variación relativa entre dos periodos, o `null` si no se puede calcular.
 *
 * Devuelve `null` cuando el periodo anterior fue cero: no existe "+100 %" respecto a nada, y
 * pintar "+∞" o "+100 %" ahí es inventarse una tendencia. El tile simplemente no muestra el chip.
 */
export function deltaPercent(current: number, previous: number): number | null {
  if (previous <= 0) {
    return null;
  }
  return Math.round(((current - previous) / previous) * 100);
}

/** Fecha `YYYY-MM-DD` a etiqueta corta, sin pasar por `new Date` (ver nota en api.models.ts). */
export function shortDay(isoDay: string): string {
  const [, month, day] = isoDay.split('-');
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  return `${Number(day)} ${months[Number(month) - 1] ?? ''}`.trim();
}

/** "hace 4 min" para el sello de última actualización. */
export function relativeTime(value: Date | string | null | undefined): string {
  if (!value) {
    return NO_DATA;
  }
  const then = typeof value === 'string' ? new Date(value) : value;
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) {
    return 'just now';
  }
  if (seconds < 3600) {
    const minutes = Math.round(seconds / 60);
    return `${minutes} min ago`;
  }
  if (seconds < 86_400) {
    const hours = Math.round(seconds / 3600);
    return `${hours} h ago`;
  }
  const days = Math.round(seconds / 86_400);
  return `${days} d ago`;
}

/** Hora local `HH:MM` de un timestamp ISO con zona. */
export function clockTime(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime())
    ? NO_DATA
    : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function minutesToHours(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) {
    return NO_DATA;
  }
  if (minutes < 60) {
    return `${Math.round(minutes)} min`;
  }
  return `${(minutes / 60).toFixed(1)} h`;
}
