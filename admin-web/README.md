# Panel Administrativo (Angular 21)

SPA exclusiva de gestión interna. **No contiene vistas de cliente**: el consumo de la
capacitación ocurre solo en la app Flutter.

## Arrancar

```bash
npm install
npm start      # http://localhost:4200
```

`proxy.conf.json` redirige `/api` al backend en el puerto 8000, incluido el WebSocket. Por eso
`environment.apiUrl` es una ruta relativa: el navegador ve todo en el mismo origen y no hay
preflight de CORS en desarrollo, que es una fuente habitual de fallos que no se reproducen en
producción.

Entrar con `superadmin@demoeca.example.com` / `Demo1234!`.

> **Angular 21, no 22.** La 22 exige Node ≥ 24.15 y la máquina de desarrollo tiene 24.14. Se
> fija la versión del framework en lugar de forzar una actualización del entorno.

## Verificación

```bash
npm run verify    # 18 comprobaciones contra el API real a través del proxy
npm run capture   # capturas de las 7 pantallas + errores de consola
```

- **`verify-panel.mjs`**: comprueba que la SPA se sirve, que el proxy alcanza el backend, que
  cada pantalla tiene datos, que el QR se descarga autenticado (y que sin token da 401) y que el
  WebSocket del agente hace streaming.
- **`capture-panel.mjs`**: conduce el Edge instalado hablando CDP con el `WebSocket` nativo de
  Node, sin descargar navegador. Inyecta la sesión, navega las 7 pantallas, **escribe una
  pregunta en el playground** y verifica que el streaming y las fuentes se renderizan. Deja las
  imágenes en `.captures/`.

Lo valioso del segundo no son las capturas: es que recoge los **errores de consola**. Un error
de plantilla en Angular compila sin problema y solo se manifiesta en el navegador.

Ninguno de los dos es una suite de tests de UI: no cubren interacciones complejas ni
regresiones visuales.

## Estructura

```
src/
├── styles.scss                     # Solo @use de los parciales
├── styles/                         # Tokens, base, layout, componentes, utilidades (D-043)
└── app/
    ├── core/
    │   ├── models/api.models.ts    # Tipos del API. ÚNICA definición por entidad (D-022)
    │   ├── services/               # auth, machines, lms, agent-builder, agent-chat (WS),
    │   │                           #   stats, theme, layout
    │   ├── interceptors/auth.*.ts  # Bearer + refresco de token con cola compartida
    │   └── guards/auth.guard.ts    # authGuard + roleGuard('superadmin')
    ├── shared/
    │   ├── icon/                   # <app-icon>: paths en TS, cero dependencias (D-043)
    │   ├── charts/                 # Sparkline SVG + lista de barras CSS (D-041)
    │   ├── stat/                   # Tile de KPI: encapsula las reglas de "sin datos" (D-044)
    │   └── format.ts               # compact, duration, percentOrFraction, deltaPercent
    ├── layout/                     # shell (grid) + sidebar + topbar + menú de usuario
    └── features/
        ├── auth/login.component.ts
        ├── dashboard/              # ← vista general: KPIs, salud del sistema, avisos
        ├── machines/               # Catálogo + panel de QR (PNG, SVG, export)
        ├── lms/                    # Ruta de aprendizaje + subida de video a MinIO
        └── agent-builder/
            ├── agent-layout.component.ts   # Cabecera + pestañas (D-042)
            ├── playground.component.ts     # ← la pantalla que demuestra el producto
            ├── agent-config.component.ts   # Proveedor, modelo, temperatura, prompt
            ├── knowledge.component.ts      # Documentos + polling de indexación
            ├── credentials.component.ts    # API keys (solo superadmin)
            └── tools.component.ts          # Registro de tools HTTP (solo superadmin)
```

Componentes standalone con plantilla en línea y `loadComponent` por ruta: un chunk lazy por
feature. **Sin librería de componentes ni de gráficos** — ver D-021 y D-041 en
[DECISIONS.md](../DECISIONS.md).

Las cinco pantallas del Agent Builder cuelgan de `/agent` como rutas hijas con pestañas (D-042).
Las URLs anteriores (`/agent/config`, `/agent/credentials`) siguen funcionando por redirect.

## Detalles que no son obvios

- **`provideZonelessChangeDetection()` en `app.config.ts` es OBLIGATORIO** (D-054). El proyecto no
  carga zone.js; sin ese provider no hay planificador de change detection y un `signal.set()`
  desde un callback de HTTP no repinta nada — el bug se manifestó como "la subida de video no hace
  nada" con todas las peticiones completándose por debajo. `npm run verify:upload` es la prueba
  E2E que lo cubre: sube un mp4 real por el navegador con CDP.
- **`innerText` refleja `text-transform`.** Los `<label>` van en uppercase por CSS, así que un
  script que verifique texto renderizado debe comparar en minúsculas.

- **El QR no se puede pintar con `<img src="/api/…">`.** El endpoint exige `Authorization` y una
  etiqueta `img` no envía cabeceras. Se descarga como blob y se revoca la object URL al cambiar
  de máquina, o cada QR visitado queda retenido en memoria (D-023).
- **El WebSocket lleva el token en la query.** El handshake del navegador no admite cabeceras
  personalizadas; no es un atajo, es una limitación de la API.
- **Los guards por rol replican lo que el backend ya aplica.** La UI oculta, el backend prohíbe.
  Ocultar sin comprobar en el servidor no es seguridad.
- **La subida de video no pasa por el API**: se pide una URL prefirmada y el `PUT` va directo a
  MinIO, con `reportProgress` para la barra.
- **Los iconos se pintan con `<svg:path [attr.d]>`, nunca con `[innerHTML]`.** El sanitizador de
  Angular elimina el SVG inyectado por innerHTML y deja un hueco **sin error en consola**, que es la
  peor clase de fallo: invisible para el script de capturas.
- **En el dashboard, `null` y `0` no son lo mismo.** `null` es "no hay datos" y se pinta `—`; `0` es
  un dato. La regla vive en `app-stat` para que no derive por las plantillas (D-044).
- **`capture-panel.mjs` fija el tema y el estado del sidebar** en localStorage antes de capturar: el
  perfil del navegador persiste entre ejecuciones, y una sesión anterior en oscuro cambiaría todas
  las capturas sin que nadie lo pidiera.
- **El ciclo de vida del WebSocket del agente vive en `AgentLayoutComponent`**, no en el playground.
  Si estuviera en el playground, cambiar de pestaña mataría la conversación en curso (D-042).

## Pendiente

- Generar los tipos desde el OpenAPI en cuanto el contrato se estabilice:
  `npx openapi-typescript http://localhost:8000/openapi.json -o src/app/core/models/api.d.ts`
- Pantallas de **Evaluaciones** y **Certificados**: aparecen como *Próximamente* en el menú, y el
  dashboard lo dice explícitamente en lugar de mostrar una fila de ceros.
- Sin build de producción servido por Nginx ni servicio en `docker-compose`: hoy solo
  `ng serve`.
