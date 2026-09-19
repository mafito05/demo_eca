# Registro de Decisiones de Arquitectura (ADR ligero)

> Contexto: esta versión es una **demo para demostrar capacidad de desarrollo**, no la v1 de
> producción. Cada decisión marca si es definitiva o si es un atajo deliberado con su ruta de
> salida. El objetivo es que ningún atajo de la demo obligue a reescribir el esquema después.

---

## D-001 · Single-tenant (sin entidad `Organization`)
**Decisión:** todos los usuarios pertenecen a una sola compañía. No existe `organization_id`.
**Motivo:** confirmado por el cliente; introducir multi-tenancy ahora añade complejidad sin valor
para la demo.
**Ruta de salida:** todas las tablas de dominio heredan de `TimestampedModel`. Cuando aparezca
multi-tenancy se añade `organization_id` a `User`, `MachineModel` y `UserLessonProgress`; el resto
cuelga por FK. Se evita deliberadamente cualquier query que agregue datos globalmente sin pasar
por un repositorio, para que ese filtro se pueda inyectar en un solo sitio.

## D-002 · El QR identifica un **modelo** de máquina, no una unidad física
**Decisión:** `MachineModel` lleva un `qr_token` opaco y único. El mismo QR se imprime N veces
para todas las máquinas iguales y lleva al mismo tutorial.
**Motivo:** confirmado por el cliente; el alcance real se definirá en reuniones posteriores.
**Ruta de salida (importante):** el resolver de QR es un único endpoint
`GET /api/v1/machines/resolve/{qr_token}`. El día que se necesite trazabilidad por unidad física
(serial, sede, historial de servicio) se crea `MachineUnit(serial, machine_model_id, qr_token)` y
ese mismo endpoint resuelve *token → unidad → modelo*. Ni la app ni el LMS cambian, porque ambos
consumen el `machine_model_id` que devuelve el resolver, nunca el token.
**Por qué `qr_token` y no el `id`:** un UUID en la URL es enumerable y filtra el catálogo interno;
el token es un slug corto rotable sin tocar la PK.

## D-003 · Bypass de login con usuario demo fijo
**Decisión:** `POST /api/v1/auth/demo-login` devuelve un JWT **real** (mismo contrato de tokens que
el login normal) para un usuario `demo@demoeca.local` con rol `trainee`.
**Motivo:** la app móvil necesita una identidad para guardar progreso; emitir un token real
significa que ningún otro módulo sabe que hubo bypass.
**Control:** gobernado por `AUTH_BYPASS_ENABLED`. En `false` el endpoint devuelve 404 (no 403: no
anunciamos la existencia de la puerta).
**Ruta de salida:** desactivar el flag. Cero cambios de código.

## D-004 · Roles: `superadmin`, `admin`, `trainee`
**Decisión:** el cliente pidió solo `superadmin` y `admin` (ambos = panel Angular). Añado
`trainee` porque el consumidor de contenido en Flutter necesita una identidad que **no** pueda
entrar al backoffice; sin ese tercer valor el usuario demo tendría permisos de administración.
`trainee` no es un rol gestionable desde el panel en esta fase.
**Diferencia superadmin/admin:** `admin` gestiona contenido (máquinas, lecciones, quizzes);
`superadmin` además gestiona credenciales de proveedores LLM, tools HTTP y usuarios. Las claves de
API y las tools son superficie de ataque, no contenido.

## D-005 · Embeddings desacoplados del LLM de chat
**Decisión:** el proveedor de chat es configurable en caliente desde el panel. El modelo de
**embeddings** es fijo por instalación (`EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` /
`EMBEDDING_DIM`).
**Motivo:** la columna `vector(N)` de pgvector tiene dimensión fija en el DDL. Permitir cambiar el
modelo de embeddings desde la UI invalidaría silenciosamente todo el corpus vectorizado y las
búsquedas devolverían basura sin dar error.
**Mitigación:** `KnowledgeChunk` persiste `embedding_model` y `embedding_dim` por fila. Una
migración futura puede re-vectorizar por lotes distinguiendo chunks viejos de nuevos, sin borrar
nada.

## D-006 · Guardrails clínicos en el agente
**Decisión:** el system prompt restringe al agente a **operación técnica del equipo**. Rehúsa
consejo clínico, dosificación y decisiones de tratamiento, y redirige al profesional responsable.
Toda respuesta RAG cita su fuente (documento + página/lección).
**Motivo:** un agente sobre equipamiento médico recibirá preguntas clínicas. Responderlas es
riesgo legal para la compañía y para el paciente.

## D-007 · Tools HTTP dinámicas con allowlist
**Decisión:** registrar una URL arbitraria que el backend invoca es SSRF por diseño. Controles:
allowlist de hosts (`TOOL_ALLOWED_HOSTS`), rechazo de IPs privadas/loopback/link-local y del
endpoint de metadatos de cloud, `https` obligatorio fuera de desarrollo, timeout y tamaño máximo
de respuesta, credenciales cifradas, y flag `requires_confirmation` para tools no idempotentes.
**Motivo:** es el módulo más peligroso del sistema y el más vistoso en una demo; enseñarlo con los
controles puestos es parte de demostrar capacidad.

## D-008 · Cifrado de secretos con Fernet
**Decisión:** las API keys de proveedores y las cabeceras de autenticación de las tools se guardan
cifradas con Fernet (`SECRET_ENCRYPTION_KEY`, clave separada de `JWT_SECRET_KEY`). Nunca se
devuelven en claro por la API: el panel solo ve los últimos 4 caracteres.
**Ruta de salida:** sustituir `crypto.py` por un backend KMS/Vault manteniendo la interfaz
`encrypt`/`decrypt`.

## D-009 · Celery (no ARQ), con colas separadas
**Decisión:** Celery en un contenedor worker propio con `ffmpeg` instalado. Colas `video` e
`ingest` separadas.
**Motivo:** el trabajo real es CPU-bound y largo (transcodificar HLS). Con una sola cola, la
vectorización de un manual quedaría bloqueada detrás de un video de 40 minutos, y en una demo eso
se ve como "el agente no sabe nada del manual".

## D-010 · Subida de video directa a MinIO con URL pre-firmada
**Decisión:** Angular pide una presigned URL, sube el `.mp4` directo a MinIO y luego notifica a
FastAPI, que encola la transcodificación.
**Motivo:** pasar ficheros de varios GB a través del API causa timeouts, presión de memoria y
reintentos que reempiezan desde cero.

## D-011 · HLS servido tras un proxy firmado
**Decisión:** el bucket de video es privado. FastAPI expone el `master.m3u8` reescrito con URLs
firmadas de corta vida para los segmentos.
**Motivo:** un bucket público protege el contenido solo por oscuridad de la URL.
**Ruta de salida:** CDN con signed cookies en producción; el proxy consume ancho de banda del API
y no escala a cientos de usuarios concurrentes. Aceptable para demo, **no** para v1.

## D-012 · Transcripción de video: proveedor abstracto, implementación manual primero
**Decisión:** `TranscriptionProvider` como interfaz. En la demo se sube la transcripción a mano
(`.vtt`/`.txt`) y se vectoriza igual que un manual.
**Motivo:** Whisper local en CPU es lento y una API de ASR añade coste por minuto sin aportar a la
demo. El pipeline queda listo para conectar cualquiera de los dos.

## D-013 · Los enums usan `Enum(native_enum=False)`, no `String`
**Decisión:** todos los enums del dominio usan `app.core.base.enum_type()`, que devuelve un
`sqlalchemy.Enum` con `native_enum=False`.
**Motivo (descubierto al integrar, no en diseño):** la primera versión los declaró como
`String(32)`. Se almacenaban bien, pero **al leer de la base de datos SQLModel devuelve
`str` crudo**: los modelos con `table=True` no revalidan al cargar. El resultado fue un
`AttributeError: 'str' object has no attribute 'value'` en el login, y habría fallado
igual en todo `objeto.campo is Enum.x` — que en el código del agente son comparaciones
silenciosas que devuelven `False` en lugar de romper. El bug peligroso no era el 500.
**Por qué `native_enum=False`:** se guarda como VARCHAR, sin `CREATE TYPE` de Postgres.
Añadir un valor a un enum nativo requiere `ALTER TYPE`, que no es reversible dentro de una
transacción y ensucia las migraciones.
**Sin CHECK en la tabla** (`create_constraint=False`): SQLAlchemy ya valida al escribir, así
que el CHECK solo protegería frente a SQL ejecutado por fuera de la aplicación, a cambio de
migrar la restricción cada vez que se añade un valor.

## D-014 · Los fallos de configuración devuelven 503, no 500
**Decisión:** `ProviderNotConfiguredError` y `SecretDecryptionError` tienen manejadores
globales en `main.py` que devuelven **503 con un `code` y un mensaje accionable**.
**Motivo:** faltar una API key no es un bug, es configuración incompleta. Con un 500 opaco,
el administrador ve "Internal Server Error" y tiene que entrar a los logs del contenedor
para descubrir que le falta `EMBEDDING_API_KEY`. En medio de una demo eso son varios
minutos perdidos delante del cliente.

## D-015 · Troceado consciente de la estructura, con encabezado de contexto
**Decisión:** el troceado parte primero por los encabezados de sección numerados del manual
(`4. RESOLUCIÓN DE FALLOS FRECUENTES`) y solo dentro de cada sección aplica el splitter por
caracteres. Además, cada fragmento se prefija con su procedencia
(`[Manual X · 4. RESOLUCIÓN DE FALLOS]`) **antes de vectorizarlo**.
**Motivo (medido, no supuesto):** la primera versión, con `chunk_size=1000` y solo splitter
por caracteres, produjo 2 fragmentos gigantes para el manual de la demo. El fragmento que
mezclaba "seguridad del operador" + "códigos de error" + "mantenimiento" salía **primero
para todas las consultas**: su embedding es el promedio de tres temas y no discrimina
ninguno. Las respuestas parecían correctas solo porque el corpus entero cabía en el
contexto — un manual real de 200 páginas lo habría roto en la demo.
**Resultado tras el cambio** (mismo corpus, mismas consultas):

| Consulta | Antes: 1er resultado | Ahora: 1er resultado |
|---|---|---|
| "qué significa el error E-204" | 3. Seguridad del operador (0.584) | **4. Resolución de fallos (0.537)** |
| "cada cuántos disparos se cambia el líquido" | 3. Seguridad del operador (0.510) | **5. Mantenimiento preventivo (0.444)** |
| "qué hago si el equipo se sobrecalienta" | 3. Seguridad del operador (0.611) | **4. Resolución de fallos (0.546)** |

**Pendiente:** el margen entre el acierto y el siguiente resultado es de ~0.12 con un corpus
de 6 fragmentos. Con manuales reales habrá que revisar `RAG_MAX_DISTANCE` (0.65) contra datos
de verdad, y probablemente añadir reranking. Reindexar es obligatorio tras cualquier cambio
de troceado: `python -m scripts.bootstrap_ai --force`.

## D-016 · El guardrail clasifica antes de mirar el contexto
**Decisión:** el prompt base obliga a clasificar la pregunta como técnica o clínica **antes**
de consultar el bloque CONTEXTO, y prohíbe explícitamente el anti-patrón de tratar una
pregunta clínica como una laguna de documentación.
**Motivo (fallo real detectado en la verificación):** ante "¿qué potencia debo usar para un
paciente de 70 kg con un cálculo de 8 mm?", la primera versión respondió *"esto no aparece en
la documentación de este equipo; te sugiero consultar el módulo sobre parámetros de
tratamiento"*. Rehusaba por el motivo equivocado: insinuaba que la respuesta existe en algún
material de capacitación y que solo hay que buscarla mejor. La regla de "si no está en el
contexto, dilo" ganaba a la restricción clínica.
**Verificación:** `scripts/verify_guardrails.py` prueba dos preguntas clínicas y dos técnicas
en cada ejecución. Consume tokens del proveedor, así que no forma parte del smoke test.

## D-017 · El proxy de HLS redirige los segmentos, no los proxifica
**Decisión:** la playlist maestra se pide con el JWT normal y se devuelve **reescrita**, con las
URIs apuntando a nuestros endpoints y llevando un token de reproducción de vida corta acotado a
un único asset (claim `asset`). Las playlists de variante se reescriben igual. Los segmentos
`.ts` responden **307 hacia una URL prefirmada de MinIO**: los bytes van del almacenamiento al
dispositivo sin pasar por FastAPI.
**Motivo del token en la URL:** ni ExoPlayer (Android) ni AVPlayer (iOS) garantizan propagar la
cabecera `Authorization` a las peticiones derivadas de un playlist, y un video de 20 minutos son
cientos de peticiones.
**Motivo del 307 en lugar de proxy:** mover cientos de megabytes por el API es la forma más
rápida de tumbarlo con tres usuarios concurrentes. Se usa 307 y no 302 para preservar método y
cabecera `Range`, que es lo que usan los reproductores al buscar dentro del video.
**Limitación aceptada:** un token filtrado da acceso a ese video durante
`HLS_TOKEN_TTL_SECONDS`. En producción se sustituye por CDN con signed cookies, que además
elimina el salto de redirección por segmento.

## D-018 · Dos clientes de MinIO: uno interno y uno para firmar
**Decisión:** `get_client()` habla con `MINIO_ENDPOINT` (`minio:9000`) para leer y escribir;
`get_presign_client()` firma contra `MINIO_PUBLIC_ENDPOINT` (`localhost:9000`), y **ambos
declaran `region` explícitamente**.
**Motivo (dos trampas encadenadas, ambas encontradas ejecutando):**
1. La firma SigV4 cubre la cabecera `Host`. No se puede firmar con `minio:9000` y reescribir el
   host después: la firma deja de validar. Hay que firmar con el host que usará el cliente final.
2. Sin `region` explícita, el SDK de MinIO hace una **llamada de red real**
   (`GET /bucket?location=`) para descubrirla antes de firmar. El cliente de firma apunta a un
   host que el backend no alcanza, así que pedir una URL de subida devolvía `Connection refused`
   con una traza de urllib3 que no daba ninguna pista del motivo.

## D-019 · El nombre del directorio de variante lo decide ffmpeg, no nosotros
**Decisión:** la nomenclatura de las variantes HLS pasa por `variant_dir()` en
`workers/tasks/video.py`, y `VARIANT_RE` en `modules/lms/hls.py` valida contra ese formato.
**Motivo:** cuando `-var_stream_map` incluye `name:360p`, ffmpeg expande `%v` con el **nombre**,
no con el índice. Los directorios reales son `v360p`/`v720p`, no `v0`/`v1`. El código asumía lo
segundo en dos sitios distintos: el `renditions` guardado en base de datos apuntaba a rutas
inexistentes, y la reescritura del playlist dejaba las URIs sin tocar, produciendo URLs
corruptas del tipo `http://localhost:8000v360p/playlist.m3u8`.

## D-020 · El porcentaje visto lo calcula el servidor y nunca baja
**Decisión:** el reproductor envía **solo su posición**; el servidor calcula el porcentaje contra
la duración real del video (obtenida por `ffprobe` al transcodificar). El UPSERT usa
`GREATEST(watched_percent, nuevo)`, el estado se deriva de ese máximo y `completed_at` se sella
una única vez.
**Motivo:** si el cliente pudiera enviar `watched_percent`, completar toda la capacitación sin
verla sería un `PUT` con `100`. Y `completed_at` es lo que acabará impreso en el certificado: no
puede moverse cada vez que el usuario reabre la lección.
**Consecuencia para los tests:** la escalera de porcentajes solo es determinista sobre un par
`(usuario, lección)` limpio. `test_video_pipeline.py` crea un trainee de un solo uso en cada
ejecución en lugar de resetear el progreso, porque **no existe** endpoint para resetearlo: un
usuario no debe poder borrar su propio historial de capacitación.

## D-021 · Panel Angular sin librería de componentes
**Decisión:** Angular 21 con componentes standalone, rutas lazy y un sistema de estilos propio
(~250 líneas de SCSS con tokens de color y media docena de clases). Sin Angular Material.
**Motivo:** un backoffice de ~10 pantallas no justifica el peso ni el lenguaje visual de una
librería completa. Si más adelante aparecen tablas con virtual scroll o selectores de fecha,
entonces sí conviene Material.
**Angular 21, no 22:** la 22 exige Node ≥24.15 y la máquina de desarrollo tiene 24.14. Se fija
la versión del framework en lugar de actualizar el Node del entorno de otra persona.
**Tokens duplicados para tema claro y oscuro** resueltos con `prefers-color-scheme`: quien
revisa contenido durante horas agradece el oscuro.

## D-022 · Los tipos del API viven en un solo fichero
**Decisión:** `core/models/api.models.ts` es la única definición de cada entidad; los servicios
la importan.
**Motivo:** la primera versión del servicio del Agent Builder declaraba sus propias interfaces.
Al añadir la pantalla de conocimiento, TypeScript veía dos `KnowledgeDocument` distintos y el
build falló con "is not assignable to parameter of type". Un tipo por entidad.
**Pendiente:** generarlos desde el OpenAPI (`npx openapi-typescript`) en cuanto el contrato se
estabilice. A mano se desincronizan en una semana.

## D-023 · El QR se pide como blob, no con `<img src>`
**Decisión:** el panel descarga la imagen del QR con `HttpClient` (`responseType: 'blob'`) y la
muestra con `URL.createObjectURL`, revocando la URL al cambiar de máquina.
**Motivo:** el endpoint del QR exige `Authorization`, y una etiqueta `<img>` no envía cabeceras;
con `src` directo devuelve 401. Verificado en `verify-panel.mjs`, que comprueba justamente que
sin token da 401.
**Detalle:** revocar la object URL no es opcional — sin ello, cada QR visitado deja el blob
retenido en memoria durante toda la sesión.

## D-024 · Verificación del panel sin Playwright
**Decisión:** dos scripts sin dependencias nuevas. `verify-panel.mjs` comprueba el proxy, cada
pantalla y el WebSocket. `capture-panel.mjs` conduce el Edge ya instalado por CDP usando el
`WebSocket` nativo de Node 24: inyecta la sesión, navega las 7 pantallas, **escribe una pregunta
en el playground** y verifica que el streaming y las fuentes se renderizan.
**Motivo:** Playwright descargaría ~150 MB de navegador para hacer lo mismo. Y lo que de verdad
importa no son las capturas, es la recolección de errores de consola: un error de plantilla en
Angular compila sin problema y solo se manifiesta en el navegador. Sin esto, la única forma de
detectarlo es abrir cada pantalla a mano.
**Límite reconocido:** no es una suite de tests de UI. No comprueba interacciones complejas ni
regresiones visuales; descarta fallos de integración y errores en consola.

## D-025 · Los enums del dominio son `StrEnum`, no `class X(str, Enum)`
**Decisión:** todos usan `enum.StrEnum` (Python 3.11+).
**Motivo:** además de eliminar 13 avisos del linter, `f"{rol}"` devuelve `"trainee"` en lugar de
`"UserRole.trainee"`. Con la forma antigua, cualquier interpolación de un enum en un log, un
mensaje de error o un prompt sacaba el nombre de la clase — un fallo silencioso y feo.
**Verificado:** el smoke test completo pasa tras la migración, que es lo que confirma que
`enum_type()` sigue persistiendo y releyendo los valores correctamente (ver D-013).

## D-026 · `zip(..., strict=True)` en la vectorización
**Decisión:** el emparejamiento entre fragmentos y vectores en `rag/ingest.py` es estricto.
**Motivo:** lo encontró el linter (`B905`) y era un bug real esperando. Si el proveedor de
embeddings devolviera menos vectores que fragmentos enviados, `zip` los emparejaría hasta el más
corto y **se perderían chunks en silencio**. El documento quedaría marcado como indexado con parte
del manual ausente, y eso se manifiesta mucho después como "el agente no encuentra lo que sí está
en el PDF".

## D-027 · Borrado de usuario con cascada explícita
**Decisión:** `DELETE /api/v1/auth/users/{id}` (solo `superadmin`) borra al usuario y sus datos,
pero **anonimiza** `tool_invocations` poniendo `user_id = NULL` en lugar de borrar esas filas.
**Motivo:** el derecho de supresión sobre datos personales lo exige — un profesional que deja la
organización puede pedir que se borre su historial de capacitación, y no basta con marcarlo
inactivo. Pero `tool_invocations` es la auditoría de lo que el agente ejecutó contra sistemas
externos: eliminar esas filas dejaría huecos en un registro de seguridad. Se conserva la fila, no
la identidad. Por eso la cascada es explícita en código y no un `ON DELETE CASCADE`: las tablas no
se tratan igual.
**Salvaguardas:** no se puede borrar el propio usuario (dejaría el sistema sin administrador) ni el
usuario demo (el bypass lo recrearía).
**Efecto lateral útil:** el test del pipeline de video ya limpia el trainee de un solo uso que crea
en cada ejecución.

## D-028 · Flutter: Riverpod, GoRouter y Dio
**Decisión:** Riverpod para estado (`AsyncValue` cubre carga/error/dato sin el boilerplate de
eventos y estados por pantalla de Bloc), GoRouter para rutas y deep linking, Dio por sus
interceptores (el refresco de token vive en uno solo y ninguna pantalla sabe de autenticación).
**Verificación sin SDK instalado:** `flutter analyze` limpio, 24 tests y un APK de debug compilado,
todo con la imagen `ghcr.io/cirruslabs/flutter:stable` en Docker. Es la única forma de verificar
Dart sin instalar 3 GB de SDK en la máquina del desarrollador.
**Trampa encontrada:** el caché de pub vive dentro del contenedor, así que sin montarlo como volumen
persistente el `analyze` de la segunda invocación reporta ~200 errores de "package no existe". No
son errores del código.
**Límite reconocido:** la app **nunca se ha ejecutado**. No hay emulador ni dispositivo en el
entorno, así que la cámara, el reproductor HLS y el chat están sin probar contra hardware. Lo que
está cubierto por tests es la lógica pura: parseo del QR, deserialización del API e interpretación
de los eventos del WebSocket.

## D-029 · Los tests de Flutter cubren lógica pura, no widgets
**Decisión:** 24 tests sobre el parser del token del QR, los modelos del API y los eventos del
agente. Cero tests de widget por ahora.
**Motivo:** son los tres sitios donde un fallo rompe la demo entera y los tres se verifican en CI
sin emulador. Un test de widget exige doblar repositorios y aporta menos por ahora.
**Caso deliberado:** se prueba que un tipo de evento desconocido del WebSocket **no rompa la app**.
El backend puede añadir eventos nuevos y una app ya publicada en las stores tiene que seguir
funcionando.

## D-030 · La app se configura por `--dart-define`, y la IP queda embebida
**Decisión:** `API_BASE_URL` se inyecta en tiempo de compilación. No hay fichero de configuración
en el dispositivo ni pantalla de ajustes.
**Motivo:** un `.env` empaquetado en el APK es legible por cualquiera que lo descomprima, y
cambiarlo exigiría recompilar igualmente.
**Consecuencia que hay que tener presente:** la IP del backend queda dentro del binario. Si el
router cambia la IP del host por DHCP, el APK deja de funcionar y hay que recompilarlo. Por eso
existe `tools/setup-lan-access.ps1`, que detecta la IP y escribe el comando exacto.

## D-031 · `10.0.2.2` no vale para BlueStacks
**Decisión:** el valor por defecto sigue siendo `10.0.2.2` (emulador de Android Studio), pero la
documentación y el script de red parten de la IP de LAN.
**Motivo:** `10.0.2.2` es un alias que implementa el emulador de Google, no una convención de
Android. BlueStacks alcanza el host por su IP de red. El síntoma de equivocarse es idéntico a un
backend caído, así que la pantalla de entrada muestra en depuración **la URL con la que se compiló**
y un botón que diagnostica el fallo concreto (timeout frente a error de conexión). Sin eso, IP
equivocada, firewall cerrado y backend apagado se ven exactamente igual en el dispositivo.

## D-032 · `MINIO_PUBLIC_ENDPOINT` es lo que rompe el video fuera de `localhost`
**Decisión:** el script de red ajusta `MINIO_PUBLIC_ENDPOINT` y **recrea** los contenedores.
**Motivo:** es el fallo menos evidente de todo el paso a dispositivo. Cambiar solo la URL del API
deja la app funcionando *salvo el video*: los segmentos HLS responden con un 307 hacia una URL
prefirmada, y esa URL se firma contra un host concreto porque SigV4 cubre la cabecera `Host` — no se
puede reescribir después. Firmada con `localhost:9000`, el dispositivo se conecta a sí mismo.
**Verificación:** `backend/scripts/simulate_mobile_client.py` comprueba explícitamente el host al
que redirige cada segmento. Es la única prueba de la suite que no puede correr dentro de un
contenedor, precisamente porque el asunto que valida es la diferencia entre `localhost` y la IP real.

## D-033 · La app no aterriza en la cámara (fallo encontrado probando en BlueStacks)
**Síntoma reportado:** la app crasheó al abrir el escáner de QR y, a partir de entonces, siempre
mostraba pantalla blanca y no volvía a abrir bien.
**Causa del "no vuelve a abrir" — un fallo de diseño mío, no del plugin:** tras autenticarse, el
`redirect` del router llevaba a `/scan`. La sesión persiste en el almacenamiento seguro, así que
cada relanzamiento repetía la secuencia sesión → escáner → fallo de cámara. La app quedaba
inservible sin más salida que reinstalarla. **Un fallo de hardware en una pantalla no debe
inutilizar la aplicación entera.**
**Arreglo:** se aterriza en `/home`, una pantalla con el catálogo de equipos. El escáner es una
acción explícita, y desde el catálogo se abre cualquier equipo **sin cámara** usando el mismo
`qr_token` que codifica el QR — que además es la única vía practicable en un emulador.

**Dos hipótesis que descarté con datos, no por intuición:**
- *MLKit sin binario x86_64.* Inspeccioné el APK: `libbarhopper_v3.so` está presente para
  `x86_64`. La librería que solo aparece en `arm64-v8a` es la capa de validación de Vulkan,
  irrelevante.
- *El plugin no arranca la cámara.* Leí el código de `mobile_scanner` 5.2.3 en el pub cache:
  `initState` llama a `controller.start()` porque `autoStart` es `true` por defecto.

**Lo que sí encontré leyendo ese código, y endurecí:**
- `controller.start()` se invoca **sin `await` ni `try/catch`**, así que un fallo de cámara queda
  como excepción asíncrona no gestionada y la pantalla se queda en negro sin explicar nada. Ahora
  el arranque se hace a mano con `autoStart: false` y el error se traduce a un mensaje accionable.
- El plugin **se salta su propia gestión del ciclo de vida** cuando se le pasa un controlador
  externo (`if (widget.controller != null) return;` en `didChangeAppLifecycleState`). Sin eso la
  cámara no se libera al pasar a segundo plano y al volver queda en un estado roto. Esta pantalla
  lo gestiona ahora.

**Causa exacta del crash: sigue sin confirmar.** Es muy probablemente nativa (CameraX sobre la
cámara virtual de BlueStacks), y una excepción en Java no se puede capturar desde Dart. Para
confirmarlo hace falta `logcat`, y BlueStacks tiene el puerto ADB escuchando pero rechaza la
sesión hasta que se activa **Ajustes → Avanzado → Depuración ADB**.

## D-034 · Pantalla de error legible en lugar de blanco
**Decisión:** `main.dart` envuelve el arranque en `runZonedGuarded`, fija `FlutterError.onError` y
sustituye `ErrorWidget.builder` por una pantalla que muestra el mensaje y las primeras líneas de la
traza.
**Motivo:** "sale pantalla blanca" no es un diagnóstico. Con esto el error se lee en el propio
dispositivo y se puede fotografiar, sin depender de tener ADB conectado — que es justo lo que no
teníamos cuando apareció el fallo.

## D-035 · Los identificadores de la app son los que generó `flutter create`
**Decisión:** `com.demoeca.demoeca_app` (Android) y `com.demoeca.demoecaApp` (iOS). La
documentación y `ANDROID_PACKAGE_NAME`/`IOS_BUNDLE_ID` se alinearon con ellos.
**Motivo:** yo había documentado `com.demoeca.app`, que no existe en ningún binario. Con ese valor,
el `assetlinks.json` y el `apple-app-site-association` apuntarían a una app inexistente y el deep
linking fallaría sin dar ninguna pista.
**Pendiente antes de publicar:** renombrarlos a algo limpio (`com.demoeca.app`). Después de subir a
una store ya no se puede: el identificador es la identidad de la app. Ahora es el momento barato,
pero implica tocar `build.gradle.kts`, el paquete de `MainActivity.kt` y tres entradas del
`project.pbxproj`.

## D-036 · La app se organiza en módulos y el escaneo es un atajo, no un paso obligatorio
**Petición del cliente:** poder explorar libremente todos los equipos y capacitaciones; que escanear
el QR sea solo un acceso directo; y que el escáner esté en un módulo propio para poder escanear otra
máquina en cualquier momento.

**Decisión:** `StatefulShellRoute.indexedStack` con barra de navegación y dos módulos:

| Módulo | Rutas | Papel |
|---|---|---|
| **Equipos** | `/equipos`, `/m/:qrToken` | Punto de entrada. Catálogo completo agrupado por especialidad, con filtro. Detalle del equipo y su capacitación. |
| **Escanear** | `/escanear` | Lector de QR, disponible siempre. |

La lección y el chat del agente se abren **fuera** del shell, a pantalla completa: un video y una
conversación piden todo el alto.

**Por qué `/m/:qrToken` conserva el path absoluto dentro del módulo Equipos:** ese path es el de la
URL que codifica el QR impreso (`https://DOMINIO/m/TOKEN`). Anidarlo como `/equipos/m/:token`
habría invalidado los códigos ya impresos. Declarado con path absoluto dentro de la rama, el deep
link entra en el módulo correcto y la barra de navegación sigue visible.

**Las "secciones" son las especialidades**, y se derivan de los datos en lugar de estar codificadas:
añadir una especialidad en el backend la hace aparecer en la app sin recompilar.

**Semántica de navegación deliberadamente mixta:** desde el catálogo se usa `push` (aparece la flecha
de volver, porque se viene de una lista); al escanear se usa `go` (no hay lista a la que retroceder,
y además cambia de módulo dejando al usuario en la capacitación).

**El escáner apaga la cámara al cambiar de módulo.** Con `indexedStack` la rama sigue viva aunque no
se vea; sin esto la cámara quedaría encendida mientras el usuario ve un video en la otra pestaña,
gastando batería y bloqueando el dispositivo para otras apps. El índice activo se publica en
`activeTabProvider` y el escáner lo vigila. Se destruye el controlador en lugar de solo pararlo:
`mobile_scanner` deja el dispositivo tomado con `stop()` en algunas plataformas, y un controlador
huérfano es justo lo que provoca que al volver la vista previa salga en negro.

**Un solo parser de tokens.** El listener de deep links ya no tiene lógica propia de segmentos:
reutiliza `extractMachineToken`, que cubre la URL https, el esquema propio y el token pelado, y está
cubierto por tests (28 en total). Dos parsers acabarían divergiendo.

**Nota sobre "escanear con la cámara del teléfono":** eso es el App Link, y funciona en cuanto el
dominio del cliente sirva `assetlinks.json` con la huella de firma — datos que siguen pendientes
(ver `mobile/docs/deep-linking.md`). El escaneo **dentro de la app** no depende de nada de eso.

## D-037 · El keystore de debug vive en un volumen de Docker
**Síntoma reportado:** "no deja instalar" el APK.

**Causa:** la imagen `ghcr.io/cirruslabs/flutter:stable` **no trae** `~/.android/debug.keystore`.
Gradle lo genera al vuelo dentro del contenedor y se descarta al terminar, así que **cada build
quedaba firmado con una clave distinta**. Android rechaza actualizar una app instalada si la firma no
coincide (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`), y el diálogo de BlueStacks solo dice "app not
installed" sin explicar por qué.

**Decisión:** un tercer volumen, `demoeca_android` → `/root/.android`, con un `debug.keystore`
generado una sola vez y con las credenciales estándar que Gradle espera (`androiddebugkey`,
`storepass`/`keypass` = `android`). Si no coinciden exactamente, Gradle ignora ese fichero y genera
el suyo, así que el detalle no es cosmético.

**Y un script, `tools/build-apk.ps1`,** para que no se pueda olvidar ningún volumen. Los tres
resuelven problemas distintos y los tres son necesarios:
`pubcache` (sin él, `analyze` reporta ~200 errores falsos de "package no existe"), `gradle` (sin él,
cada build vuelve a descargar la cadena de Android entera) y `android` (la firma).

**Verificación:** la huella SHA-256 del APK coincide con la del keystore del volumen
(`d3dc9fef…`), lo que confirma que Gradle usó el fichero persistido en lugar de generar otro.

**Descartado con datos, no por intuición:** la instancia de BlueStacks es `Pie64`, o sea Android 9
(API 28), leído de `C:\ProgramData\BlueStacks_nxt\bluestacks.conf` sin necesidad de ADB. El APK pide
`minSdk 24`, incluye `x86_64` y va firmado con APK Signature Scheme v2 (que requiere Android 7+). Los
cuatro requisitos se cumplen, así que ni la versión de Android, ni la ABI, ni el esquema de firma
explicaban el fallo.

**Efecto lateral útil:** al ser estable, la huella del certificado de debug ya se puede poner en
`assetlinks.json` y probar los App Links sin esperar al certificado de release.

## D-038 · Un build cortado deja el cache de Gradle bloqueado
**Síntoma:** tras cortar un build en segundo plano, el siguiente falla con
`Timeout waiting to lock journal cache … Owner PID: 78`.
**Causa:** el contenedor muere pero los ficheros `.lock` quedan en el volumen `demoeca_gradle`, y
Gradle los cree de un proceso vivo.
**Solución:**
`docker run --rm -v demoeca_gradle:/gradle alpine sh -c "find /gradle -name '*.lock' -delete"`.
Es seguro: Gradle los recrea. Anotado aquí porque el mensaje de error apunta a un PID inexistente y
no sugiere en absoluto cuál es el problema.

## D-039 · El producto está en inglés; el código sigue documentado en español
**Decisión del cliente:** todo el producto en inglés, incluido el agente.

**Alcance aplicado — todo lo que ve un usuario o cliente:**
- App Flutter: las 3 pestañas y todas las pantallas.
- Panel Angular: las 7 pantallas, el menú y los mensajes.
- Backend: mensajes de error del API, `summary` de endpoints y descripciones de schemas (que
  acaban en el OpenAPI y por tanto en el panel).
- Prompt del agente y sus guardrails clínicos.
- Contenido sembrado: el manual del litotrictor, los nombres de equipos, módulos y lecciones.

**Fuera de alcance, deliberadamente:** comentarios y docstrings del código, `DECISIONS.md`, los
README y la salida por consola de los scripts de desarrollo. Son documentación interna del equipo,
que trabaja en español. Traducir 60 ficheros de comentarios no aporta valor de producto y añade
riesgo de romper cosas. Se puede hacer si se decide que el repositorio va a manos de un equipo que
no habla español.

**El agente responde en el idioma de la pregunta.** El prompt lo pide explícitamente. Eso significa
que alguien que pregunte en español recibirá respuesta en español aunque el manual esté en inglés
— útil en un hospital con personal de varias nacionalidades, y gratis.

**Consecuencia obligatoria: había que re-vectorizar.** Traducir el manual invalida el corpus: los
embeddings del texto español no sirven para consultas en inglés. Se hizo un reset completo de la base
de datos, re-seed y `bootstrap_ai --force`. Los 6 chunks nuevos están en inglés y el ranking se
comprobó: "how often is the coupling fluid replaced" trae *5. PREVENTIVE MAINTENANCE* primera
(d=0.446), y "what do I do if the unit overheats" trae *4. COMMON FAULT RESOLUTION* (d=0.542).

**Y había que ajustar cuatro suites de verificación**, porque buscaban textos concretos: las sondas
del guardrail y sus marcadores de rechazo, las preguntas de los smoke tests, los nombres de botones
que pulsa el script de capturas del panel (`Recuperar` → `Retrieve`, `Enviar` → `Send`) y el test de
truncado de respuesta de tools. Un test que busca una cadena traducida falla en silencio si nadie lo
revisa.

## D-040 · ECAHelp: el asistente como módulo del menú
**Decisión:** tercera pestaña, `ECAHelp` (`/ecahelp`), junto a Equipment y Scan.

**Con selector de equipo, y a la vista.** A diferencia del chat que se abre desde una máquina, aquí
no hay contexto implícito. Sin equipo seleccionado el agente solo puede consultar el corpus global y
**no puede citar ningún manual**, así que esconder el selector produciría respuestas genéricas sin
que el usuario entienda por qué. El equipo elegido se recuerda entre visitas a la pestaña.

**El chat se extrajo a `AgentChatView`**, un widget sin `Scaffold` que comparten ECAHelp y el chat
contextual del equipo. Mantener dos implementaciones del streaming, las citas y la confirmación de
tools habría garantizado que divergieran.

**Cambiar de equipo reinicia el hilo** (vía `ValueKey`): continuar la misma conversación mezclaría la
documentación de dos máquinas distintas, que es justo lo que el prompt prohíbe.

---

## D-041 · Gráficos del dashboard sin librería: SVG inline y CSS
**Decisión:** las visualizaciones se dibujan a mano. Cero dependencias nuevas en el panel.

**Razón principal, y no es el peso:** el dashboard necesita **tres primitivas y dos son CSS puro** —
`.bar-fill { width: X% }` y `.meter-fill`. Solo el sparkline necesita un `path`, y son ~25 líneas de
geometría en `shared/charts/geometry.ts`. Traer 70–250 KB para una polilínea es desproporcionado.

Lo que de verdad decide es otra cosa: **cada librería impone su propio lenguaje visual** —tooltips,
leyendas, tipografías, paleta— que habría que combatir en cada gráfico. Es exactamente el
razonamiento por el que este panel no usa Angular Material (D-021); aceptarla aquí rompería la
coherencia por la parte más visible.

**SVG y no canvas.** El canvas no hereda `var(--accent)`, así que habría que recalcular colores al
cambiar de tema; exige `devicePixelRatio` y `ResizeObserver`; y es **invisible para
`capture-panel.mjs`**, que verifica el DOM. El SVG se re-tematiza gratis y es inspeccionable.

**Restricción derivada del tooling:** el SVG se dimensiona con `viewBox` + `width: 100%`, **sin
medir el contenedor**. Nada de `ResizeObserver` — sería una fuente nueva de errores de consola justo
en el script que existe para cazarlos.

**Sin gráficos categóricos.** El desglose por proveedor y la cobertura del conocimiento van como
lista de barras de un solo hue. Con una o dos categorías, una tarta de un gajo no compara nada, y una
paleta categórica obligaría a validar contraste para algo que no aporta.

**Ruta de salida:** si el cliente pide zoom, brush de fechas, apilados multi-serie o export a PNG, se
revisa con **uPlot (~40 KB)**, no con Chart.js.

## D-042 · El Agent Builder se consolida en pestañas
**Decisión del cliente:** "está separado en módulos, lo cual hace poco sentido". Correcto: eran cinco
entradas del menú lateral (`playground`, `config`, `knowledge`, `credentials`, `tools`) para cinco
caras de **una sola herramienta**. Ahora es una ruta padre `/agent` con cinco rutas hijas.

**Se conserva lo que importaba:** cada pestaña sigue siendo una URL real con `loadComponent`, así que
el lazy loading y el deep-link no cambian. Se añadieron redirects de `agent/config` → `agent/agents` y
`agent/credentials` → `agent/providers` para no romper marcadores ni capturas.

No se usó `loadChildren` sobre un `agent.routes.ts`: eso metería `tools` y `credentials` en el mismo
chunk que descarga un `admin`, que nunca puede abrirlas.

**Se descartó el split permanente con el playground fijo a la derecha.** Tres de las cinco pantallas
ya usan `.split` por dentro (tabla + formulario), y anidar un split dentro de otro con
`--page-max: 1400px` deja columnas de ~330 px: los formularios de Knowledge y Tools quedan
inservibles, y el playground —lo que vende el producto— pasaría a vivir en 400 px.

**La intuición del cliente se sirve igual**: cada agente tiene un botón "Test" que abre el playground
con su contexto (`?machine=`), recogido con `input()` porque `withComponentInputBinding()` ya estaba
activo.

**Único cambio funcional, y hay que saberlo:** el ciclo de vida del WebSocket **subió al layout**.
Antes `PlaygroundComponent.ngOnDestroy` llamaba a `disconnect()`; si se hubiera quedado ahí, ir a
Knowledge a mirar un documento y volver mataría la conversación en curso — justo el recorrido que las
pestañas pretenden facilitar. Lo verifica `npm run capture`, que depende del streaming.

## D-043 · Sistema de diseño del panel: tokens completos, iconos inline, tema conmutable
**Tokens completos o no funciona.** `styles.scss` tenía 11 tokens de color y un solo radio. Sin
escala de espaciado ni de tipografía, cada componente inventaba su `1.25rem`, y de ahí a las **siete
copias de `.split`** (una por componente, con dos breakpoints distintos mezclados) hay un paso. Ahora
hay espaciado, radios, sombras, tipografía, superficies de estado y colores de dato, y `.split` vive
una vez con tres variantes.

El fichero se partió en cinco parciales con `@use` (no `@import`, deprecado en Dart Sass),
manteniendo un único entry en `angular.json`.

**Tema conmutable de tres estados.** Antes el tema solo salía de `prefers-color-scheme`, así que un
toggle era imposible. Se resuelve con un mixin y tres puntos de aplicación: `:root` (claro), la media
query con `:not([data-theme='light'])` (oscuro si el sistema lo pide **y** el usuario no forzó claro),
y `[data-theme='dark']` (oscuro forzado, gana siempre). Más `color-scheme: light dark`, que es lo que
hace que scrollbars y controles nativos sigan el tema — sin él, en oscuro aparecen barras de scroll
blancas que delatan que el tema es solo pintura.

**Iconos: componente `<app-icon>` con los paths en TS**, ~2,5 KB. Detalle crítico de implementación:
el path se pinta con `<svg:path [attr.d]>` y **no** con `[innerHTML]` — el sanitizador de Angular
elimina el SVG inyectado por innerHTML dejando un hueco silencioso, sin error en consola. Se
descartaron el sprite externo (petición extra que se rompe al cambiar `base-href`, y que el script de
capturas puede fotografiar a medio cargar) y una librería npm.

**Colores del dato con nombre.** `--data-track` es un paso claro del **mismo hue**, no un gris: un
gris compite con el texto atenuado y ensucia; el mismo hue lee como "el resto de este dato".

## D-044 · El dashboard no miente cuando no hay datos
El endpoint `/stats/overview` y el panel comparten una regla, y es la decisión de diseño más
importante de todo el dashboard:

> **`null` significa "no hay datos para calcularlo". `0` significa "hay datos y el valor es cero".**
> Son afirmaciones distintas y se pintan distinto: `—` atenuado frente a un número.

Consecuencias concretas en el backend (`stats/derive.py`, todo funciones puras y testeadas sin BD):

- `SUM` **sí** se colapsa a 0 (sumar cero mensajes son cero tokens: es verdad). `AVG`, percentiles y
  ratios **nunca** (0 % de respuestas con fuente sobre cero respuestas es falso). Esto divergerá de
  `lms/service.py`, que sí devuelve `0.0` de progreso: allí 0 % significa "no has empezado", que es
  cierto.
- Percentiles con **`percentile_disc`**, no `percentile_cont`: con tres muestras, `cont` interpola y
  devuelve milisegundos que ninguna petición tardó nunca. Y **todo percentil viaja con su
  `sample_size`**, que el panel muestra siempre (`n=48`).
- Sin periodo anterior con datos → **no se pinta el chip de variación**. Nunca "+100 %" contra cero.
- Porcentaje con denominador < 5 → se muestra la fracción ("3 of 4"), no el `%`.

Y en el panel: `app-stat` encapsula esas reglas para que no deriven, el sparkline dibuja **barras** si
hay menos de 3 puntos con valor (una línea de dos puntos parece un fallo de render), y todo gráfico
tiene su **tabla gemela** en un `<details>` — ningún valor existe solo detrás del puntero.

**Composición pensada para datos escasos.** La demo tiene una máquina y seis chunks, así que arriba
van *System health* y *Needs attention*: son afirmaciones categóricas, informan igual con pocos datos
que con muchos. Y al final la tabla de conversaciones recientes, que es lo que **mejor aparenta** con
poco: seis filas llenan una tabla, seis puntos no llenan un gráfico. La lista de avisos vacía es un
**estado de victoria** explícito ("Everything is in order · 6 checks passed"), no una caja gris.

**Deliberadamente fuera:** coste en dólares (exige una tabla de precios por modelo que envejece en
silencio y acaba mostrando cifras erróneas con aire de exactitud) y métricas de assessments (sus
tablas están vacías **por construcción**, porque el módulo no tiene router; un tile permanente de
"0 intentos" comunica "roto", no "pendiente").

**Trampas de SQL que hubo que resolver**, todas verificadas contra el esquema real:
`sources` es `JSON` y no `JSONB`, así que `jsonb_array_length` no compila y hay que envolver con
`json_typeof` **dentro** del argumento (Postgres no garantiza cortocircuito de `AND`);
`func.avg()` sobre entero llega como `Decimal` vía asyncpg y rompe cualquier aritmética posterior;
un `GROUP BY` sobre una columna de `enum_type()` devuelve el **miembro del enum**, no el `str`, y los
estados sin filas no aparecen (hay que pre-inicializar el diccionario o hay `KeyError` justo con
datos escasos); `GROUP BY coalesce(col, 'x')` genera un bind param distinto al del `SELECT` y
Postgres lo rechaza; y `asyncio.gather` sobre la misma `AsyncSession` falla porque asyncpg no
multiplexa una conexión.

**Sin caché, a propósito.** El uso real es "publico una máquina y voy al dashboard a comprobarlo"; un
TTL de 60 s convierte eso en "acabo de publicarla, ¿por qué sigue en borrador?". En su lugar, el
smoke test asserta **< 2 s**, que detecta el N+1 futuro *antes* de que una caché lo esconda.

## D-045 · Sistema de diseño de la app: métricas const, color como ThemeExtension
**Espaciado, radios y duraciones como `static const`, no como `ThemeExtension`.** Razón concreta y
verificable: `analysis_options.yaml` activa `prefer_const_constructors`, y con un ThemeExtension el
valor sale de un lookup en runtime, así que `EdgeInsets.all(spacing.md)` deja de poder ser const y el
lint dispara en cascada por toda la app. Con `static const double md = 12`,
`const EdgeInsets.all(AppSpacing.md)` sigue siendo const. Además, espaciado y radios no dependen del
brightness: el `lerp` gratis de un ThemeExtension no compra nada.

**El color sí como `ThemeExtension`**, porque sí depende del brightness y el `lerp` evita un salto al
conmutar. Cubre dos huecos de Material 3: `ColorScheme` no tiene `success` ni `warning` (el código
usaba `tertiary` para decir "vídeo procesándose", un rol que no significa eso), y sin color por
especialidad todas las tarjetas de equipo se ven idénticas — no hay portadas, `assets/images/` está
vacío y `cover_image_key` no se expone en ningún endpoint.

**Los colores de especialidad se derivan con `ColorScheme.fromSeed(brightness:)`**, no se escriben a
mano: es la única forma de garantizar que el par container/onContainer sigue siendo legible en oscuro
sin auditar cinco hexadecimales a ojo.

**El acceso va con fallback, nunca con `!`.** `Theme.of(context).extension<T>()` es nullable;
resolverlo con `!` compila pero **crashea al pintar** fuera de un `MaterialApp` con las extensiones
registradas — que es justo lo que hace un widget test. Hay un test que cubre ese escenario.

## D-046 · El tema de la app corrige defectos, no solo estética
Había **cuatro** component themes personalizados y **dos** estilos de texto; el resto era el valor por
defecto de Material. Ahora son 15 y los 13 roles tipográficos. La mitad de los cambios son
correcciones de comportamiento, no decoración:

| Cambio | Qué arregla |
|---|---|
| `inputDecorationTheme` con `focusedBorder` | Tenía `borderSide: none` en **todos** los estados: un campo enfocado no se distinguía de uno inactivo |
| `chipTheme` con `showCheckmark: false` | Al seleccionar un `FilterChip`, el check le añadía ancho y **desplazaba toda la fila de filtros** |
| `cardTheme` con `color` por brightness | En oscuro, `elevation 0` + `surface` + borde `outlineVariant` dejaba las tarjetas **casi invisibles** |
| `snackBarTheme` flotante | Los avisos salían pegados al borde inferior, **detrás** de la barra de navegación y bajo el FAB |
| `outlinedButtonTheme`, `textButtonTheme` | Solo `FilledButton` estaba tematizado: en las pantallas de error un outlined de 36 quedaba junto a un filled de 48 |
| `progressIndicatorTheme` con `borderRadius` | Elimina los `ClipRRect(999)` manuales repartidos por tres pantallas |
| `appBarTheme.systemOverlayStyle` | No se tocaba, y los iconos de la barra de estado podían quedar blanco sobre blanco |
| Hairline sobre la `NavigationBar` | `NavigationBarThemeData` no tiene borde, y en oscuro la barra se fundía con el contenido |

**Tipografía: escala completa sobre Roboto, sin `google_fonts`.** Ese paquete descarga la fuente en
runtime; en un hospital con red aislada o portal cautivo la petición falla y cae a Roboto, así que la
app tendría **dos tipografías según la red** — peor que tener una. Definir los 13 roles da el salto de
jerarquía con 0 bytes y 0 riesgo de reflow.

**Sí se empaqueta JetBrains Mono (~530 KB), y es una corrección.** Había cuatro sitios pidiendo
`fontFamily: 'monospace'` sin declarar ninguna fuente: en Android resuelve por casualidad del
sistema, en iOS cae en silencio a la fuente por defecto. Y un código como `URO-LITHO-3000` necesita
desambiguar `O`/`0` e `I`/`1`/`l`, porque el técnico lo teclea a mano cuando el adhesivo del QR está
rozado — es el camino de respaldo de la app. Único punto de uso: el widget `CodeBadge`.

**Suelo tipográfico de 13 px** (Material 3 pone 12) y **peso 600 en títulos** (M3 pone 500): la app se
lee de pie a un brazo de distancia, y con reflejo de luz sobre el cristal se pierde antes el contraste
de trazo que el de tamaño. Botones a **52 de alto** en lugar de 48: guantes de nitrilo.

**Skeletons con pulso, no barrido, y sin `shimmer`.** El paquete es un `ShaderMask` de ~60 líneas, su
barrido blanco queda mal en oscuro (habría que pasarle colores propios igualmente) y repinta un
shader por frame. Un `ColorTween` es más barato, y en una sala en penumbra un destello blanco
recorriendo la pantalla molesta físicamente. **Un solo `AnimationController`** propagado por
`InheritedWidget`: ocho controllers desincronizados en la lista del catálogo es el aspecto de algo
roto.

## D-047 · `friendlyMessage`: la app deja de mostrar excepciones de Dio
Había **cinco** patrones de pantalla de error (`_CatalogError`, `_Problem`, `_LessonError`,
`_CameraUnavailable` y el `errorBuilder` del router) y cuatro de ellos pintaban el `$error` crudo.
Un usuario veía, a pantalla completa:

```
DioException [connection error]: ... SocketException: Failed host lookup
```

Ahora hay un único `StatusView` y un `error_presenter.dart` que traduce por tipo de `DioException` y
por código de estado. **El detalle crudo se conserva, pero solo en `kDebugMode`**, donde sirve para
diagnosticar. Es el cambio que más separa "prototipo" de "producto" en toda la app, y no toca ni una
línea de lógica.

Tres detalles del `StatusView` que hay que respetar al usarlo:

1. **`scrollable: true` por defecto**, con `AlwaysScrollableScrollPhysics`. Sin eso, meterlo dentro
   del `RefreshIndicator` del catálogo **desactiva el pull-to-refresh en silencio**, justo cuando el
   usuario quiere reintentar. Hay un test de widget que lo cubre.
2. `StatusView.sliver()` para listas de slivers, con `hasScrollBody: true`: con `false`, tres acciones
   desbordan en un móvil de 320.
3. Máximo **tres acciones**; las demás se recortan, porque apiladas desbordan en pantalla pequeña.

## D-048 · Siembra de actividad para el dashboard, en un script aparte
`scripts/seed_demo_activity.py` genera ~3 semanas de historial verosímil: cuatro cuentas de formación
(no demo), conversaciones con mensajes cuyos tokens y `latency_ms` están en el rango que el sistema
produce de verdad (el smoke test mide p50 ~2,3 s y p95 ~4,8 s con OpenAI), y progreso de lecciones en
los tres estados.

**No entra en `seed_demo.py` a propósito.** El seed base crea el contenido mínimo del producto y tiene
que seguir siendo la verdad; esto es escenografía para la reunión. Separarlo mantiene la frontera
visible y hace que ejecutarlo sea una decisión consciente. Es idempotente y **reversible con
`--purge`**, que borra solo lo que crea (sus cuatro usuarios y todo lo que cuelga de ellos).

Semilla fija (`SEED = 20260727`): dos ejecuciones dan los mismos números, así que una captura del
dashboard sigue siendo válida mañana. La curva es ascendente y salta los fines de semana — una serie
plana se ve fabricada, y un hospital tiene calendario.

**El dashboard está diseñado para verse bien igualmente sin sembrar** (D-044): la siembra mejora los
gráficos, no los hace posibles.

**Y la exclusión de `is_demo` es asimétrica, declarada en el propio payload:** la sección del agente
**cuenta** el tráfico demo (sus tokens y su latencia son coste y salud reales) y la de formación lo
**excluye** (el login demo es compartido, así que sus "12 lecciones completadas" falsean la adopción
en lugar de medirla). Los campos `includes_demo_traffic` y `excludes_demo_users` lo dicen, para que el
panel pueda rotularlo y nadie tenga que adivinarlo.

## D-049 · El master.m3u8 acepta el token por query, y por qué eso arregla el video en la app
**Síntoma:** los videos no cargaban en la app aunque `simulate_mobile_client.py` pasaba 19/19.

**Dos causas apiladas, ambas invisibles para los tests de host:**

1. **Cleartext.** ExoPlayer es código nativo y respeta la `NetworkSecurityPolicy` de Android, que
   bloquea HTTP plano desde targetSdk 28. Dio implementa la red en Dart y NO pasa por esa política
   — por eso toda la app funcionaba menos el video. Fix: `android:usesCleartextTraffic="true"` en
   el manifest, documentado como cosa de demo (en producción va TLS y esto fuera).
2. **La cabecera `Authorization` viajaba hasta MinIO.** `httpHeaders` de `video_player` se aplica a
   TODAS las peticiones del data source de ExoPlayer y se reenvía al seguir redirects. La cadena:
   master (necesita JWT) → playlist con token de reproducción → segmento → **307 a la URL
   prefirmada de MinIO** → llega con firma en la query **y** `Authorization` en la cabecera → S3
   rechaza el doble mecanismo de auth. El comentario del player que decía "la cabecera solo va en
   el master" era falso a nivel de implementación.

**Fix:** `hls_master` acepta `?access_token=` (mismo patrón que el WebSocket, reutilizando
`get_user_from_token`), la app pide el master con el token en la query y **no envía ninguna
cabecera**. El header sigue aceptándose por compatibilidad con el panel y los scripts.

## D-050 · El socket del chat pertenece al widget, no a un provider
**Síntoma:** `Could not open the chat: Bad state: Cannot call onDispose after a provider was
disposed`, cada vez que se cambiaba de equipo en ECAHelp.

**Causa doble en `agentSocketProvider`:** era un `FutureProvider.autoDispose` con el
`ref.onDispose` **después** de un `await` al keystore, consumido con `ref.read` — que no deja
listener. Riverpod lo autodisponía en cuanto el read retornaba, el dispose ganaba la carrera al
await, y el `onDispose` tardío lanzaba. Y aunque no lanzara, nada anclaba el provider: el socket
recién conectado se habría cerrado solo.

**Fix:** el provider desaparece. Quien usa el socket lo posee: `_AgentChatViewState` lo crea en
`initState` y lo cierra en su `dispose`. El `ValueKey` de ECAHelp que recrea el widget al cambiar
de equipo recrea también la conexión — exactamente el comportamiento buscado. Regla general que
deja esto: un recurso con ciclo de vida (socket, stream, controller) vive donde se usa, no en un
`autoDispose` sin anclar.

## D-051 · Los component themes necesitan color explícito
**Síntoma:** "hay letras en la app que no se ven" — el título del AppBar, los chips de filtro y
los diálogos, invisibles en modo claro.

**Causa:** los component themes recibían la `TextTheme` del proyecto, que deja el color a `null`
para que lo aporte el merge con `Typography`. Ese merge **solo ocurre en `ThemeData.textTheme`**;
en los component themes no, y encima su sola presencia cortocircuita los defaults de Flutter que
sí ponían color (`app_bar.dart`: `appBarTheme.titleTextStyle ?? defaults...copyWith(color:
foregroundColor)` — el `??` nunca llega al copyWith). Un `TextStyle` con color null se pinta con
el color por defecto del engine: **blanco**. Título blanco sobre superficie blanca.

**Fix:** todo estilo de texto inyectado en un component theme lleva `copyWith(color: ...)`
explícito. Y un test de widget verifica el **color efectivo** del texto renderizado (no el del
theme) con ratio de contraste > 4.5 en ambos brightness, para que la regresión no vuelva por otro
camino. `listTileTheme` y los botones no lo necesitan: esos widgets fuerzan el color después.

## D-052 · Autoría completa del LMS y máquinas editables
**Síntoma:** "no deja subir videos, ni editar las capacitaciones, tampoco permite crearlas". Tenía
razón en las tres, y la mayor parte era **UI que no existía**:

- El panel de Training era solo-lectura salvo crear una lección de video en un módulo
  preexistente. **No podía crear módulos** → un video subido a una máquina sin módulos era
  impublicable. No podía editar ni borrar nada. `createModule`/`updateLesson` existían en el
  servicio Angular como código muerto.
- **Las máquinas no tenían PATCH**: una creada desde el panel nacía `draft` y no se podía
  publicar jamás — su capacitación era invisible para la app para siempre.
- El `<input type="file">` **nunca se reseteaba**: reintentar con el mismo fichero no dispara
  `change` y la pantalla parecía muerta. Y todos los errores colapsaban en "Video upload failed."
  sin status.

**Qué hay ahora:** `GET /machines/{id}/authoring` (árbol con los campos editables que el path de
consumo omite a propósito), `DELETE` de módulos y lecciones con cascada explícita (el progreso se
borra; conversaciones y documentos conservan la referencia a NULL — son auditoría y conocimiento),
PATCH endurecidos (colisión de `order_index` → 409 legible; coherencia tipo↔contenido sobre el
estado **resultante**), `PATCH /machines/{id}` con el `qr_token` deliberadamente no editable (hay
códigos impresos pegados a máquinas), y el panel de Training reescrito como editor completo con
vista previa del trainee al lado.

**El reordenado hace el swap en tres pasos** (A→índice temporal, B→índice de A, A→índice de B):
dos PATCH directos chocan contra la restricción única.

## D-053 · Nada del agente hardcodeado: sugerencias, prompt visible y settings
Tres fuentes de hardcode eliminadas de una vez:

1. **Preguntas sugeridas del chat**: vivían como `static const` en el widget de Flutter — cambiar
   un ejemplo exigía recompilar la app. Ahora son una columna JSON de `AgentConfig`
   (migración `b66ef3b550e9`), editables desde el panel (textarea, una por línea, máx. 8), y la
   app las pide a `GET /agent/suggestions?machine_model_id=` — que resuelve la configuración
   **igual que el chat** (específica de máquina o default), así que las preguntas que ves son las
   del mismo agente que va a responderte. Fallbacks en dos niveles: config vacía → defaults del
   backend; backend inalcanzable → dos ejemplos empaquetados en la app.
2. **El prompt, visible.** `GET /agent/prompt` expone el prompt base (solo lectura, D-006 se
   mantiene: los guardrails clínicos no se desactivan desde una pantalla) y
   `POST /agent/configs/{id}/preview-prompt` compone el prompt final con `build_system_prompt` —
   el MISMO código del camino de producción, no una copia. Es la pieza que faltaba para depurar
   un agente: antes el panel solo veía el textarea de instrucciones adicionales.
3. **`RAG_MAX_DISTANCE` estaba triplicado** (config.py, playground de Angular, chips de Flutter).
   Ahora `GET /agent/settings` lo expone y los dos clientes lo consumen con fallback al 0.65.

Además: `suggested_models` de OpenAI/Google actualizados (gpt-5-mini primero: es el que usa el
probe de credenciales y conviene que sea el barato), y el form del panel expone `description`,
`is_active` y `rag_top_k`, que el PATCH del backend siempre aceptó pero la UI no ofrecía.

## D-054 · `provideZonelessChangeDetection()` era obligatorio y no estaba
**El hallazgo más importante de esta tanda, y el más difícil de ver.** El panel no carga zone.js
(decisión correcta en Angular 21) pero a `app.config.ts` le faltaba
`provideZonelessChangeDetection()`. En ese estado no hay NINGÚN planificador de change detection:
un `signal.set()` desde un callback de HTTP marcaba la vista como sucia y **nadie programaba el
repintado**. Solo se repintaba lo que coincidía con una navegación del router o con la
hidratación inicial.

**Por eso "no se podían subir videos"**: la subida completaba todas sus peticiones —ticket, PUT
presignado a MinIO con su preflight CORS, encolado de la transcodificación— y la pantalla se
quedaba como si nada hubiera pasado. El estado interno del componente era perfecto
(`asset: ready`); el DOM, congelado.

**Cómo se encontró y por qué ningún test lo veía:** `test_video_pipeline.py` sube con httpx desde
el host — no ejercita el navegador. Se escribió `verify-upload.mjs` (CDP + `DOM.setFileInputFiles`
con un mp4 real), que reprodujo el bug al primer intento, y una batería de sondas sobre la página
viva acabó demostrando que el estado del componente y el DOM divergían.

**Trampa adicional para el futuro:** al verificar texto renderizado con `innerText`, recordar que
refleja `text-transform` — los `<label>` del panel van en uppercase por CSS, así que
`innerText.includes('Processing status')` falla aunque el nodo exista. Comparar en minúsculas.
`npm run verify:upload` queda como prueba E2E permanente del flujo de subida.

## D-055 · Biblioteca de videos: el estado del pipeline no puede vivir solo en el navegador
**Síntoma reportado:** "se queda en cola y no pasa nada". El diagnóstico contra los logs del worker
mostró lo contrario: el video del usuario (4,4 min) se transcodificó **bien** en 107 segundos. Lo
roto era la visibilidad: el estado del asset recién subido vivía solo en la memoria de la pantalla,
la transcodificación tarda ~1 min por minuto de metraje, y si el admin recargaba o cambiaba de
pantalla mientras tanto, el video terminaba en `ready` pero quedaba **huérfano e invisible** — sin
ninguna UI para verlo ni adjuntarlo jamás.

**Fix:** `GET /lms/videos` — la biblioteca. Cada asset con su estado, duración y `used_by_lessons`
(sin saber qué lecciones usan un video, reemplazarlo da miedo). El panel la pinta con acciones por
estado: `Use` (listo y sin uso → precarga el formulario de publicación), `Process` (subido o
fallido → encola la transcodificación) y `Delete`. El `DELETE /lms/videos/{id}` **rechaza con 409
los assets en uso** — borrar un video referenciado dejaría una lección publicada que revienta en el
móvil — y elimina los ficheros de MinIO (mp4 original + árbol HLS) con tolerancia a objetos ya
ausentes. La UI avisa además del tiempo esperado de transcodificación y de que se puede salir de la
página.

**Y la lección de video se hizo editable de verdad:** el editor permite **reemplazar el video**
(selector sobre los assets `ready` de la biblioteca) y añadir una **descripción** (`body`), que la
app ya mostraba bajo el reproductor para cualquier tipo de lección — el PATCH del backend siempre
lo aceptó; era la UI la que solo ofrecía el título.

## D-056 · Despliegue en VPS: el panel deja de depender de `ng serve`
**Contexto:** la demo pasa de una LAN sin salida a Internet a un VPS con IP pública
(`72.60.112.93`). Hasta aquí el panel solo existía mientras alguien tuviera `ng serve` levantado
en su máquina, y `proxy.conf.json` —que es lo que evita el CORS y hace de puente al `:8000`— es
una pieza del dev-server, no del producto.

**Decisión:** un servicio `web` en el compose que compila el panel y lo sirve con Nginx en el
:80, reproduciendo el mismo proxy sobre `/api`. Alternativa descartada: apuntar `environment.ts`
a `http://IP:8000`. Habría metido la IP dentro del bundle —recompilar el panel entero al cambiar
de host— y devuelto el CORS y el preflight que `apiUrl: '/api/v1'` existe para evitar (D-042). Con
el proxy, el navegador sigue viendo un solo origen y el WebSocket del agente sube por el mismo
camino.

**Dos trampas que costaron una vuelta:**

1. **Las locations por regex ganan a las de prefijo en Nginx.** El bloque de cacheo de estáticos
   (`~* \.(js|css|png|...)$`) se quedaba con `/api/v1/machines/{id}/qr.png` y devolvía el 404 de
   Nginx en lugar del PNG del backend. Se arregla con `location ^~ /api/`, que corta la
   evaluación de regex. Lo cazó `verify-panel.mjs`, que comprueba justo esa descarga.
2. **`main.js` no se llama igual en producción.** Con `outputHashing: all` el bundle es
   `main-<hash>.js`, así que la comprobación "carga el bundle principal" fallaba contra el panel
   desplegado aunque el panel estuviera perfecto. El patrón ahora acepta las dos formas: una
   verificación que solo vale en desarrollo no verifica lo que se despliega.

**Superficie de red:** el salto de LAN a IP pública convierte "puerto publicado" en "puerto
expuesto a Internet". Postgres, Redis y la consola de MinIO quedan atados a `127.0.0.1` (con las
credenciales de demo, publicarlos no es un riesgo: es un incidente). El `:9000` de MinIO **tiene**
que seguir siendo público, porque la firma SigV4 cubre el `Host` y es el propio dispositivo quien
abre la URL prefirmada — el mismo motivo de `MINIO_PUBLIC_ENDPOINT` (D-018), solo que ahora el
host es una IP enrutable en lugar de una de LAN. Sigue todo en HTTP plano, JWT incluidos: TLS es
requisito antes de que esto vea un dato real.

**Tooling:** `setup-server-access.sh` y `build-apk.sh` son los equivalentes en bash de los `.ps1`,
que asumían PowerShell y `Get-NetRoute`. Se añaden en lugar de sustituirlos: el entorno de
desarrollo sigue siendo Windows. `build-apk.sh` además comprueba con `strings` que la IP quedó
embebida en el binario — es el fallo más caro de descubrir tarde, porque solo se manifiesta al
reinstalar en el dispositivo.

## D-057 · Renombrado de marca: panel y app
**Decisión del cliente:** el panel pasa a mostrar **ECA COMMUNICATIONS · Gemini Demo** y la app
móvil se llama **ECA GEMINI DEMO**. Fuera el nombre anterior, `DemoECA`, en ambos.

**Registro del cambio de criterio, porque afecta a cómo leer lo que sigue:** el encargo inicial
fue dejar la app sin marca —se llamó `Equipment Training` durante una iteración, con el
razonamiento de que el panel lo usa el cliente y la app la ve el personal del hospital, donde una
marca comercial no aporta—. El cliente lo revisó y pidió que la app llevara el nombre de la demo.
Queda anotado por si vuelve a plantearse: el argumento a favor del nombre neutro era que
sobrevive a un cambio de cliente sin recompilar.

**Alcance: solo lo que ve el usuario.** Se tocaron cuatro sitios en la app —el título de
`MaterialApp`, el titular de la pantalla de entrada, `android:label` y `CFBundleDisplayName`— y
tres en el panel —sidebar, login y `<title>`—. **No** se tocaron los identificadores internos que
siguen diciendo `demoeca`: el `applicationId` (`com.demoeca.demoeca_app`), el esquema del deep
link, las claves de `SharedPreferences`/`localStorage`, la familia tipográfica `DemoEcaMono` ni
los nombres de clase. Cambiarlos no cambia nada de lo que se ve y sí rompe cosas: el
`applicationId` es la identidad de la app para Android (instalación, firma, App Links), el
esquema está grabado en los QR ya impresos, y renombrar las claves de almacenamiento cerraría la
sesión de todo el mundo en el despliegue.

**`ECAHelp` se queda.** Es el nombre de la función, no el de la empresa, y sale en el menú
inferior, la cabecera del chat y el botón flotante. Renombrarlo era la única parte realmente
invasiva del encargo y el cliente confirmó que no hace falta.

**Cuidado con la longitud.** `ECA GEMINI DEMO` son 15 caracteres en mayúsculas: bajo el icono del
lanzador Android lo trunca a dos líneas, y en la pantalla de entrada, a 320 dp, el titular puede
partirse en dos. Ninguna de las dos cosas rompe nada —el `Text` envuelve, no desborda— pero es lo
primero que hay que mirar si el nombre vuelve a crecer.

**Pendiente si se quiere marca cero:** la pantalla de login del panel sigue mostrando las
credenciales de demo con el dominio `@demoeca.example.com`, que viene del seed. Cambiarlo obliga
a re-sembrar la BD y a tocar los scripts de verificación, que las traen fijadas.

## D-058 · Las fotos de producto van a un bucket público, sin firmar
**Decisión:** las imágenes de equipo viven en `demoeca-public` —el bucket que `minio-init` ya creaba
con `mc anonymous set download` y que nadie usaba— y se sirven por URL directa.

**Por qué no se firman, si el video sí (D-011):** una URL prefirmada caduca a la hora. Un catálogo
abierto en un móvil se quedaría con las fotos rotas sin que nadie tocase nada, y ese es justo el
fallo que hace parecer rota la aplicación. `mc anonymous set download` concede `s3:GetObject`
anónimo pero **no** `ListBucket`, así que las claves (dos UUID) no son enumerables.

**Regla dura:** en ese bucket solo van fotos de producto. Manuales, certificados y cualquier cosa
con datos de paciente siguen en `demoeca-docs`, privado y servido con `presign_get`.

**Cache busting:** la URL lleva `?v=<updated_at>`. Sin él, sustituir una foto no se ve: la URL no
cambia y el navegador —y el `ImageCache` de Flutter— siguen sirviendo la anterior. Es el fallo que
más probablemente aparecería en una demo.

**Validación en dos tiempos, porque el PUT va del navegador a MinIO (D-010) y el backend no ve los
bytes:** al pedir la URL se comprueba lo que el cliente *declara* (tipo permitido, tamaño, tope por
máquina); al confirmar, `stat_object` da el tamaño y el `Content-Type` reales y, si no cuadran, se
borra el objeto y la fila. **SVG queda fuera a propósito**: servido desde un bucket público es XSS
almacenado, y la URL no caduca nunca.

## D-059 · La galería es una tabla, y la portada es un rol dentro de ella
**Decisión:** `machine_images` con `order_index`, `role` (`cover` | `gallery`) e `is_ready`, en vez
de una columna JSON en `machine_models`. La antigua `cover_image_key` se elimina.

**Por qué no JSON:** (1) cada imagen necesita identidad propia para borrarla o reordenarla sola;
(2) un JSON editado *en sitio* no marca la fila como sucia en SQLAlchemy y el cambio se pierde sin
error — `VideoAsset.renditions` se libra solo porque el worker reasigna la lista entera.

**Por qué la portada es un rol y no un campo aparte:** con un campo en la máquina habría dos formas
de guardar una imagen, dos de construir su URL y dos de borrarla, y "promociona esta foto" sería
copiar una clave entre sitios en lugar de cambiar una etiqueta. `cover_image_key` nunca llegó a
exponerse en ningún endpoint y estaba a NULL, así que eliminarla no rompió nada.

**"Como mucho una portada" se garantiza en la base de datos** con un índice único parcial
(`WHERE role = 'cover'`), que el autogenerador de Alembic no saca y hay que escribir a mano. El
router degrada la portada anterior en la misma transacción; el índice es la red de seguridad.

## D-060 · El video se asigna al equipo al subirlo
**Decisión:** `video_assets.machine_model_id`, nullable, más filtros `?machine_model_id=` y
`?unassigned=true` en `GET /lms/videos`.

**Por qué no bastaba la cadena existente:** `VideoAsset ← Lesson → TrainingModule → MachineModel`
solo clasifica los videos que ya cuelgan de una lección. Los recién subidos no cuelgan de nada, y
son precisamente los que se pierden de vista (D-055). Nullable y sin `server_default`: los assets
anteriores quedan "sin asignar", que es un estado legítimo y visible, no adjudicados al azar.

**Reusar un video entre equipos se permite:** en una demo puede querer enseñarse el mismo material
en dos rutas. Un video sin equipo adopta el del módulo al engancharlo a una lección.

**En el panel**, el `<select>` de la lección agrupa por equipo pero **mantiene el video ya asignado
aunque sea de otro equipo**: si el filtro lo excluyera, el `<select>` saldría vacío y el primer
guardado dejaría la lección sin video en silencio.

## D-061 · `app-file-drop` es tonto a propósito
**Decisión:** un componente de subida compartido entre máquinas y capacitación que **no hace HTTP**.
El flujo de dos fases (ticket → PUT prefirmado → confirmar o encolar) se queda en el servicio y en
el componente padre.

**Motivo:** así vale igual para un video de 2 GB y para una foto de 200 KB sin un solo condicional
dentro, y el detalle delicado —cuándo se encola el procesado— vive en un único sitio.

**El centinela `-1`:** el servicio sigue emitiendo `progress: -1` para los eventos sin progreso útil
(D-054). El componente lo trata como "medidor indeterminado", así que es inofensivo aunque llegue,
sin que tenga que saber que existe. Y `videoAssetId` pasa a emitirse **al responder el ticket**, no
al terminar, para poder cancelar y borrar el asset huérfano; la señal de "ya se puede procesar" es
el nuevo `done`.

---

## Supuestos aplicados por defecto (pendientes de confirmar en reunión)

| # | Tema | Supuesto aplicado |
|---|------|-------------------|
| 1 | Idioma | Español en UI y contenido; el agente responde en el idioma de la pregunta. Sin tablas de i18n todavía. |
| 2 | Quizzes | **Fuera del alcance de la demo** (decisión del cliente: "próximamente"). El esquema ya está en la BD; los supuestos aplicados eran 80% para aprobar, 3 intentos y orden aleatorio, a reconfirmar cuando se retome. |
| 3 | Certificados | **Fuera del alcance de la demo** ("próximamente"). Tablas creadas. Cuando se retome hay que decidir si deben servir como registro regulatorio (ISO 13485 / FDA), porque eso exige inmutabilidad y auditoría que hoy no están. |
| 4 | Deep linking | Dominio configurable (`DEEPLINK_DOMAIN`); si la app no está instalada, landing web con enlaces a las stores. Requiere bundle IDs y SHA-256 de firma reales para `assetlinks.json` / AASA. |
| 5 | Renditions HLS | 360p / 720p, `-hls_time 6`. Sin descarga offline en Flutter (cambiaría la arquitectura del player). |
| 6 | Histórico de chat | Persistido en `conversations` / `messages`, con rate limit por usuario en Redis. |
| 7 | RAG | Filtro por `machine_model_id` + corpus global opcional. El cliente envía `lesson_id` como contexto adicional. |
