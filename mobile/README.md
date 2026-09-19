# App Móvil (Flutter)

Cliente para el personal médico y técnico.

**La interfaz está en inglés** (D-039). Los comentarios del código siguen en español: son
documentación interna del equipo.

**Tres módulos** en una barra de navegación:

- **Equipment** — catálogo completo agrupado por especialidad, con filtro. Se entra a cualquier
  equipo y su capacitación: video HLS, progreso y asistente contextual.
- **Scan** — lector de QR, disponible en cualquier momento para saltar directo a otra máquina.
- **ECAHelp** — el asistente, con selector de equipo. Sin equipo seleccionado solo consulta el corpus
  global y no puede citar manuales, de ahí que el selector esté a la vista (D-040).

Escanear es un **atajo, no un requisito**: se puede recorrer todo el catálogo sin pasar por la
cámara. Ver D-036 en [DECISIONS.md](../DECISIONS.md).

## Estado

| Elemento | Estado |
|---|---|
| Análisis estático (`flutter analyze`) | ✅ `No issues found!` |
| Tests | ✅ `71/71` — lógica pura + widget en los dos temas y a 320/411 dp |
| Compilación (`flutter build apk --debug`) | ✅ APK generado |
| Ejecución en dispositivo o emulador | ❌ **sin probar** — ver abajo |

**Lo que no está verificado:** la app compila y su lógica está cubierta por tests, pero **no se
ha ejecutado nunca**. No hay emulador ni dispositivo disponible en el entorno donde se desarrolló,
así que la cámara, el reproductor HLS y el chat por WebSocket están sin probar contra hardware
real. El backend con el que hablan sí está verificado end-to-end desde el panel y desde scripts.

## Arrancar

Con el backend levantado (`docker compose up -d` en la raíz):

```bash
flutter pub get

# Emulador de Android Studio: 10.0.2.2 es un alias de QEMU hacia el localhost del anfitrión.
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000

# Simulador iOS
flutter run --dart-define=API_BASE_URL=http://localhost:8000

# BlueStacks, o un teléfono en la misma red: hace falta la IP real del host.
# `10.0.2.2` NO funciona ahí — es un alias exclusivo del emulador de Google.
flutter run --dart-define=API_BASE_URL=http://192.168.18.33:8000

# Contra el servidor de demo desplegado, desde cualquier red con Internet.
flutter run --dart-define=API_BASE_URL=http://72.60.112.93:8000
```

**Para BlueStacks o un dispositivo físico, ejecuta antes** `.\tools\setup-lan-access.ps1` en la
raíz del repositorio: detecta la IP, ajusta `MINIO_PUBLIC_ENDPOINT` (sin eso el video no carga,
porque las URLs prefirmadas se firman contra un host concreto) y recrea los contenedores. Guía
completa en [docs/bluestacks.md](docs/bluestacks.md).

En el servidor de demo eso ya está hecho (`tools/setup-server-access.sh`), así que un teléfono
con datos móviles apunta directamente a `http://72.60.112.93:8000` sin más preparación. El APK
compilado contra ese servidor se genera con:

```bash
./tools/build-apk.sh 72.60.112.93     # desde la raíz del repo, en el servidor
```

La pantalla de entrada muestra en depuración la URL con la que se compiló y un botón **Comprobar
conexión** que diagnostica el fallo de red concreto. Es lo primero que hay que mirar si la app "no
entra".

La configuración se inyecta con `--dart-define`, no se lee de un `.env`: un fichero empaquetado en
el APK es legible por cualquiera que lo descomprima, y habría que recompilar igualmente para
cambiarlo.

### Sin Flutter instalado en el host

Todo lo de arriba se puede verificar con la imagen oficial en Docker, que es como se hizo:

```bash
docker volume create demoeca_pubcache
docker run --rm -v "${PWD}:/app" -v demoeca_pubcache:/root/.pub-cache -w /app \
  ghcr.io/cirruslabs/flutter:stable \
  bash -lc "flutter pub get && flutter analyze && flutter test"
```

Para compilar el APK hay que montar además un volumen para Gradle
(`-v demoeca_gradle:/root/.gradle`), o cada build vuelve a descargar la cadena entera.

## Estructura

```
lib/
├── main.dart                       # ProviderScope + MaterialApp.router + pantalla de error
├── core/
│   ├── config/app_config.dart      # --dart-define, URLs, cadencia del heartbeat
│   ├── network/api_client.dart      # Dio + Bearer + refresco con cola compartida + diagnose()
│   ├── storage/token_storage.dart   # Keystore / Keychain, no SharedPreferences
│   ├── router/app_router.dart       # Módulos (indexedStack) + deep links en caliente
│   ├── theme/app_theme.dart         # Material 3, claro y oscuro
│   └── providers.dart               # Grafo de dependencias (Riverpod)
└── features/
    ├── shell/presentation/         # Barra de navegación entre módulos
    ├── auth/                       # Entrada por bypass de demo + diagnóstico de red
    ├── machine/
    │   ├── data/                   # Catálogo y resolución del QR
    │   └── presentation/           # Catálogo por especialidad + ficha del equipo
    ├── qr_scanner/
    │   ├── qr_token_parser.dart     # ← lógica pura, con tests; la usa también el deep link
    │   └── presentation/            # Cámara + entrada manual del código
    ├── lms/
    │   ├── data/                   # Ruta, lección, reporte de progreso
    │   └── presentation/player/    # Reproductor HLS con heartbeat
    └── agent/                      # Socket del agente + chat con streaming

shared/                             # Widgets, formato y presentación de errores compartidos
    ├── domain/specialty.dart        # Etiqueta, icono y color por especialidad
    ├── errors/error_presenter.dart  # DioException -> frase legible (D-047)
    └── widgets/                     # StatusView, skeletons, CodeBadge, ProgressRing…

test/                               # 63 tests: lógica pura + widget (sin emulador)
docs/bluestacks.md                  # Cómo probar en el emulador
docs/deep-linking.md                # Lo que falta para cerrar App Links / Universal Links
```

## Diseño

Sistema de tokens en `lib/core/theme/`: métricas como `static const` (`design_tokens.dart`) y color
como `ThemeExtension` (`app_theme_extensions.dart`). El motivo de la asimetría está en D-045: con un
ThemeExtension, `EdgeInsets.all(spacing.md)` deja de poder ser const y `prefer_const_constructors`
dispara en cascada.

Varias decisiones del tema **corrigen defectos** en lugar de decorar (D-046): el foco de un campo no
se distinguía, las tarjetas eran casi invisibles en oscuro, los snackbars salían detrás de la barra de
navegación, y seleccionar un chip de filtro desplazaba toda la fila. La tabla completa está en
DECISIONS.

Contexto de uso que justifica los números: la app se usa **de pie junto a una máquina**, a veces con
guantes de nitrilo y con luz que va de quirófano a sala técnica. De ahí los botones de 52 dp, el suelo
tipográfico de 13 px y el selector manual de tema en el perfil.

## Decisiones que no son obvias

- **El QR codifica una URL https, no `demoeca://`.** Si la app no está instalada, un esquema
  propio no abre nada y el código quedaría muerto pegado al equipo. Ver
  [docs/deep-linking.md](docs/deep-linking.md), que detalla los dos ficheros que debe servir el
  dominio del cliente y los datos que aún faltan (SHA-256 de firma y Team ID de Apple).
- **El JWT viaja en la query del `master.m3u8`, nunca como cabecera** (D-049). ExoPlayer reenvía
  los `httpHeaders` al seguir redirects, así que una cabecera `Authorization` llegaba hasta la URL
  prefirmada de MinIO y rompía la firma. El backend devuelve el playlist con las URIs ya firmadas
  mediante un token de reproducción propio.
- **El manifest lleva `usesCleartextTraffic`** porque la demo habla HTTP plano en LAN y ExoPlayer
  (nativo) respeta la política de Android aunque Dio (Dart) no. En producción: TLS y fuera.
- **El heartbeat de progreso es cada 10 s, no por tick.** Cada llamada es una escritura en base de
  datos; con un heartbeat por segundo, una lección de 20 minutos generaría 1200 escrituras.
- **Solo se envía la posición, nunca el porcentaje.** Lo calcula el servidor contra la duración
  real del video: si lo enviara el cliente, completar la capacitación sin verla sería un `PUT`.
- **El refresco de token usa un `Completer` compartido.** Cinco peticiones que fallan a la vez
  provocarían cinco refrescos concurrentes, cuatro de ellos con un token ya rotado, y el usuario
  acabaría expulsado teniendo sesión válida.
- **Se escuchan los deep links con la app ya abierta.** GoRouter atiende el que arranca la app en
  frío, pero no los siguientes. Sin ese listener, escanear un segundo QR con la app en segundo
  plano no haría nada — que es justo el caso de un técnico recorriendo varias máquinas.
- **El chat rehúsa consejo clínico.** No es lógica de la app: el guardrail vive en el prompt del
  backend (D-006) y la app lo anuncia en la interfaz.

## Qué probar en cuanto haya un dispositivo

1. Permiso de cámara y lectura de un QR impreso de verdad (no en pantalla: el brillo y el reflejo
   cambian el comportamiento).
2. Reproducción HLS con cambio de calidad al degradar la red, y reanudación en la posición
   guardada.
3. Que el progreso cruce el umbral y desbloquee el módulo siguiente.
4. Deep link en frío y en caliente.
5. Chat: streaming de tokens, fuentes citadas y el diálogo de confirmación de herramienta.

## Pendiente

- Visor de PDF integrado (hoy las lecciones de tipo `pdf` muestran un aviso).
- Descarga offline de lecciones — cambiaría la arquitectura del reproductor, así que conviene
  decidirlo antes de avanzar más.
- Tests de widget de pantallas completas con repositorios doblados (ya hay de widgets sueltos).
- Iconos y pantalla de arranque propios.
