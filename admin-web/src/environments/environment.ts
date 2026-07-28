/**
 * Configuración de entorno para desarrollo.
 *
 * `apiUrl` es una ruta relativa a propósito: `proxy.conf.json` redirige `/api` al backend en
 * el puerto 8000. Así el navegador ve todo en el mismo origen y no hay preflight de CORS en
 * desarrollo, que es una fuente habitual de fallos que no se reproducen en producción.
 *
 * El WebSocket sí necesita origen absoluto: el proxy de `ng serve` soporta `ws`, pero la URL
 * hay que construirla a partir de `location` para que funcione igual en dev y en el build
 * servido por Nginx.
 */
export const environment = {
  production: false,
  apiUrl: '/api/v1',
  /** Construye la URL del WebSocket del agente a partir del origen actual. */
  agentWsUrl(): string {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${location.host}/api/v1/agent/ws`;
  },
};
