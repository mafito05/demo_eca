/**
 * Geometría del sparkline: funciones puras, sin DOM.
 *
 * Aisladas del componente para poder probarlas con vitest, que ya está en devDependencies y no
 * tenía ni un spec. La escala y el path son donde de verdad se rompen los gráficos —serie de un
 * punto, todos los valores iguales, todo ceros— y ninguno de esos casos se ve mirando el gráfico
 * con datos normales.
 *
 * El SVG se dimensiona con `viewBox` + `width: 100%` y NUNCA midiendo el contenedor: un
 * `ResizeObserver` sería una fuente nueva de errores de consola justo en el script de capturas,
 * que existe para cazarlos.
 */

export const VIEW_WIDTH = 300;
export const VIEW_HEIGHT = 64;

export interface SparkPoint {
  x: number;
  y: number;
  value: number;
  index: number;
}

/**
 * Proyecta la serie al espacio del viewBox.
 *
 * Dos casos que hay que tratar aparte o el gráfico sale mal:
 *
 * - **Un solo punto**: dividir por `length - 1` sería dividir por cero. Se coloca centrado.
 * - **Todos los valores iguales** (incluido todo ceros): el rango es cero, así que normalizar
 *   daría `NaN`. Se dibuja una línea plana a media altura, que es la lectura correcta —"constante",
 *   no "sin datos".
 */
export function scalePoints(
  values: number[],
  width = VIEW_WIDTH,
  height = VIEW_HEIGHT,
): SparkPoint[] {
  if (values.length === 0) {
    return [];
  }
  if (values.length === 1) {
    return [{ x: width / 2, y: height / 2, value: values[0], index: 0 }];
  }

  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min;
  const step = width / (values.length - 1);
  // Margen vertical para que el marcador del último punto y el grosor del trazo no se recorten.
  const padding = 6;
  const usable = height - padding * 2;

  return values.map((value, index) => ({
    x: index * step,
    y: range === 0 ? height / 2 : padding + usable - ((value - min) / range) * usable,
    value,
    index,
  }));
}

/** Polilínea. Un solo punto no produce trazo: devuelve cadena vacía en lugar de un path inválido. */
export function linePath(points: SparkPoint[]): string {
  if (points.length < 2) {
    return '';
  }
  return points
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(' ');
}

/** Área bajo la línea, cerrando contra la base del viewBox. */
export function areaPath(points: SparkPoint[], height = VIEW_HEIGHT): string {
  const line = linePath(points);
  if (!line) {
    return '';
  }
  const first = points[0];
  const last = points[points.length - 1];
  return `${line} L${last.x.toFixed(2)} ${height} L${first.x.toFixed(2)} ${height} Z`;
}

export interface SparkBar {
  x: number;
  y: number;
  width: number;
  height: number;
  value: number;
  index: number;
}

/**
 * Barras, para series demasiado cortas para una línea.
 *
 * Una línea de dos puntos parece un fallo de render, no un dato. Por debajo del umbral se dibujan
 * barras, que con un punto siguen leyéndose bien.
 */
export function barGeometry(
  values: number[],
  width = VIEW_WIDTH,
  height = VIEW_HEIGHT,
): SparkBar[] {
  if (values.length === 0) {
    return [];
  }
  const max = Math.max(...values, 1);
  const slot = width / values.length;
  const barWidth = Math.max(2, slot * 0.6);

  return values.map((value, index) => {
    const barHeight = Math.max(value > 0 ? 2 : 0, (value / max) * (height - 4));
    return {
      x: index * slot + (slot - barWidth) / 2,
      y: height - barHeight,
      width: barWidth,
      height: barHeight,
      value,
      index,
    };
  });
}

/**
 * Decide entre línea y barras.
 *
 * El criterio es cuántos puntos tienen valor, no cuántos hay: una serie de 30 días con actividad
 * en dos de ellos es visualmente una serie de dos puntos, aunque el array traiga 30.
 */
export function preferBars(values: number[], minimumNonZero = 3): boolean {
  return values.filter((value) => value > 0).length < minimumNonZero;
}
