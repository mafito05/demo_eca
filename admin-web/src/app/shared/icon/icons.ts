/**
 * Registro de iconos: paths de 24x24, estilo stroke.
 *
 * Sin dependencia de iconos (D-043). No es tacañería: una librería npm traería ~2 KB de paths
 * envueltos en su propio componente y su propia convención de tamaños, para el mismo resultado.
 * Y un sprite SVG externo añadiría una petición que se rompe al cambiar `base-href` y que el
 * script de capturas puede fotografiar a medio cargar.
 *
 * Todos los paths asumen `fill="none" stroke="currentColor"`, así que heredan el color del texto
 * y se re-tematizan solos al cambiar de tema claro a oscuro.
 */

export type IconName =
  | 'dashboard'
  | 'qr'
  | 'graduation'
  | 'sparkles'
  | 'chat'
  | 'sliders'
  | 'book'
  | 'key'
  | 'plug'
  | 'clipboard-check'
  | 'award'
  | 'chevron-left'
  | 'chevron-right'
  | 'chevron-down'
  | 'sun'
  | 'moon'
  | 'monitor'
  | 'log-out'
  | 'alert-triangle'
  | 'check-circle'
  | 'info'
  | 'clock'
  | 'refresh'
  | 'external'
  | 'plus'
  | 'trend-up'
  | 'trend-down'
  | 'minus'
  | 'menu'
  | 'user'
  | 'image'
  | 'upload'
  | 'video'
  | 'play'
  | 'trash'
  | 'search'
  | 'star'
  | 'x';

export const ICONS: Record<IconName, string> = {
  image: 'M3 5h18v14H3V5Zm0 11 5-5 4 4 3-3 6 6',
  upload: 'M12 16V4m0 0L8 8m4-4 4 4M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2',
  video: 'M3 6h11v12H3V6Zm11 4 7-4v12l-7-4',
  play: 'M7 4.5v15l13-7.5-13-7.5Z',
  trash: 'M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5.5 12.5L21 21',
  star: 'm12 3 2.9 5.9 6.5.9-4.7 4.6 1.1 6.5L12 17.8 6.2 20.9l1.1-6.5L2.6 9.8l6.5-.9L12 3Z',
  x: 'M6 6l12 12M18 6 6 18',
  dashboard: 'M3 13h8V3H3v10Zm10 8h8V11h-8v10ZM3 21h8v-6H3v6ZM13 9h8V3h-8v6Z',
  qr: 'M4 4h6v6H4V4Zm10 0h6v6h-6V4ZM4 14h6v6H4v-6Zm10 3h3m0 0v3m3-3h.01M17 14h3',
  graduation: 'M22 9 12 5 2 9l10 4 10-4Zm0 0v6M6 11.5V16c0 1.1 2.7 2.5 6 2.5s6-1.4 6-2.5v-4.5',
  sparkles:
    'M12 3v3m0 12v3M4.9 7.05l2.1 2.12m10 10.03 2.1 2.12M3 14h3m12 0h3M4.9 20.95l2.1-2.12m10-10.03 2.1-2.12M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z',
  chat: 'M21 11.5a8.4 8.4 0 0 1-.9 3.8c-1.5 3-4.5 4.7-7.6 4.7a8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7A8.4 8.4 0 0 1 4 11.5c0-3.1 1.7-6.1 4.7-7.6A8.4 8.4 0 0 1 12.5 3h.5a8.4 8.4 0 0 1 8 8v.5Z',
  sliders: 'M4 21v-7M4 10V3m8 18v-9m0-3V3m8 18v-5m0-3V3M1 14h6m2-5h6m2 7h6',
  book: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 1 6.5 22H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15Z',
  key: 'M15.5 7.5a4 4 0 1 1-1.9 3.4L12 12.5l-1.5-1.5-2 2 1.5 1.5-2 2L6.5 15l-2 2 1.5 1.5-1.5 1.5H3v-2.5l8.6-8.6a4 4 0 0 1 3.9-1.4ZM17 8h.01',
  plug: 'M9 2v6m6-6v6M6 8h12v3a6 6 0 0 1-6 6 6 6 0 0 1-6-6V8Zm6 9v5',
  'clipboard-check':
    'M9 4H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2M9 4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1H9V4Zm-.5 9 2 2 4-4',
  award: 'M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12Zm-3.6 3.4L7 22l5-2.5 5 2.5-1.4-3.6',
  'chevron-left': 'm15 18-6-6 6-6',
  'chevron-right': 'm9 18 6-6-6-6',
  'chevron-down': 'm6 9 6 6 6-6',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-14v2m0 18v-2M4.2 4.2l1.4 1.4m12.8 12.8 1.4 1.4M3 12h2m14 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z',
  monitor: 'M3 5h18v11H3V5Zm5 15h8m-4-4v4',
  'log-out': 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9',
  'alert-triangle': 'M12 3 2.5 20h19L12 3Zm0 6v5m0 3h.01',
  'check-circle': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-3.5-9.5 2.5 2.5 4.5-4.5',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13h.01M11 12h1v4h1',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v5l3 2',
  refresh: 'M21 12a9 9 0 1 1-3-6.7M21 4v5h-5',
  external: 'M14 4h6v6m0-6L10 14M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  plus: 'M12 5v14M5 12h14',
  'trend-up': 'm3 17 6-6 4 4 8-8m0 0h-5m5 0v5',
  'trend-down': 'm3 7 6 6 4-4 8 8m0 0h-5m5 0v-5',
  minus: 'M5 12h14',
  menu: 'M4 6h16M4 12h16M4 18h16',
  user: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
};
