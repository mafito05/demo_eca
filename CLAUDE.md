# Contexto para agentes

Instrucciones y contexto para un agente que trabaje en este repositorio. Lo que está aquí es lo
que **no** se deduce leyendo el código: el estado real, las reglas duras y hacia dónde va el
proyecto.

**Idioma:** el producto está en inglés (interfaz, mensajes del API, prompt del agente, contenido
sembrado). La documentación interna, los comentarios del código y los mensajes de commit están en
español. No traduzcas comentarios ni documentación interna. Ver D-039.

## Documentos que hay que leer antes de tocar algo

| Documento | Para qué |
|---|---|
| [DECISIONS.md](DECISIONS.md) | 61 decisiones (D-001…D-061) con su motivo y su ruta de salida. **Obligatorio antes de tocar el esquema de la base de datos, el RAG, el pipeline de video o el tema de la app.** Casi todo lo que parece raro está explicado ahí. |
| [README.md](README.md) | Arranque, verificación, despliegue, puertos. |
| [docs/registro-de-trabajo.md](docs/registro-de-trabajo.md) | Historia de las sesiones: qué se pidió, qué se decidió y qué quedó a medias. |
| [docs/arquitectura-aws-hipaa.md](docs/arquitectura-aws-hipaa.md) | **El plan AWS vigente**, con las brechas de cumplimiento, el coste estimado, el orden de trabajo y la ruta de crecimiento. El resumen de abajo no lo sustituye. |
| [mobile/README.md](mobile/README.md), [admin-web/README.md](admin-web/README.md) | Detalles de cada cliente. |
| [guia.md](guia.md) | El encargo original del cliente. Histórico. |

Cuando tomes una decisión de arquitectura o descubras una trampa no evidente, **añade una entrada
D-0xx a DECISIONS.md**. Es la convención del repositorio y la razón de que el proyecto sea
retomable.

## Qué es el proyecto

Plataforma B2B de capacitación técnica sobre equipos médicos. Un QR pegado a la máquina física
abre su ruta de formación en la app móvil (videos HLS, manuales, progreso) con un agente de IA que
responde sobre ese equipo concreto citando la sección del manual.

Es una **demo para demostrar capacidad de desarrollo**, no la v1 de producción. Varios atajos son
deliberados y están documentados con su ruta de salida. El criterio es que ningún atajo obligue a
rehacer el esquema después.

- **Backend:** FastAPI modular, Postgres + pgvector, Redis, Celery (colas `video` e `ingest`
  separadas), MinIO, LangChain multi-LLM, WebSocket con streaming.
- **Panel:** Angular 21 standalone, 8 pantallas, sin librería de componentes ni de gráficos.
- **App:** Flutter con Riverpod, GoRouter y Dio. Tres módulos: Equipment, Scan y ECAHelp.
- **Infra:** `docker-compose.yml` en una sola máquina.

## Estado real

| Pieza | Estado |
|---|---|
| Backend, panel, agente, RAG, video HLS, progreso | ✅ Verificados de extremo a extremo con el stack levantado |
| Desplegado en un VPS Ubuntu con IP pública `72.60.112.93` | ✅ Revalidado ahí |
| App Flutter | ✅ Compila, `analyze` limpio, 71 tests — ⚠️ **nunca ejecutada en un dispositivo real ni en iOS** (D-028) |
| Exámenes y certificados | 🔜 Fuera del alcance de la demo. Las tablas existen, no hay router |
| Fotos de producto en la app | ⚠️ **A medias.** Ver abajo |

**Nunca afirmes que algo funciona sin haberlo ejecutado.** Este repositorio distingue en todas sus
tablas lo verificado de lo que solo compila, y esa distinción es lo que lo hace fiable.

### Lo que quedó a medias: las fotos en la app (US-305)

El backend y el panel están terminados (D-058 a D-061). El backend ya envía `cover_image_url` e
`images` en el catálogo y en el resolver del QR. En la app existen `MachineImage`, los campos en
los modelos y el widget [`RemoteImage`](mobile/lib/shared/widgets/remote_image.dart), **sin
conectar a ninguna pantalla**. Falta:

1. Miniatura en [`machine_card.dart`](mobile/lib/features/machine/presentation/widgets/machine_card.dart).
2. Foto de cabecera en [`machine_header.dart`](mobile/lib/features/machine/presentation/widgets/machine_header.dart).
3. Galería y visor a pantalla completa (ya hay tokens: `AppSizes.galleryStrip`, `AppOverlays.mediaBackdrop`).
4. Tests. El comentario de `RemoteImage` menciona un helper `useFakeImages()` en `test/support/`
   **que todavía no existe**: hay que crearlo, y debe restaurar `providerFactory` con
   `addTearDown` o contamina el resto del fichero.
5. APK nuevo.

Las fotos y el video del Uroflowmeter esperan material del cliente.

## Reglas duras

- **No se lee `os.environ` fuera de `backend/app/core/config.py`.** El conjunto de variables tiene
  que ser auditable en un solo fichero.
- **Ningún endpoint devuelve un secreto en claro**, ni al superadmin. Solo `key_hint`.
- **El prompt base del agente no es editable** desde el panel. Los guardrails clínicos no se
  desactivan desde una pantalla (D-006). El admin añade instrucciones encima.
- **Las tools HTTP son fail-closed:** con `TOOL_ALLOWED_HOSTS` vacío no se ejecuta ninguna.
- **Los tipos del API del panel viven solo en `core/models/api.models.ts`** (D-022).
- **Los enums usan `enum_type()` / `StrEnum`**, nunca `String` (D-013, D-025).
- **El cliente nunca envía porcentajes de progreso**, solo su posición. Lo calcula el servidor y
  nunca baja (D-020).
- **Tras cambiar el troceado o el modelo de embeddings hay que reindexar** con
  `bootstrap_ai --force`, o los chunks viejos contaminan las respuestas (D-005, D-015).
- **`qr_token` no es editable:** hay códigos impresos pegados a máquinas (D-052).
- **Los identificadores internos siguen diciendo `demoeca`** (`applicationId`, esquema del deep
  link, claves de almacenamiento) aunque la marca visible sea otra. Cambiarlos rompe la identidad
  de la app en Android y los QR impresos (D-057).

## Verificación

Todo pasa por scripts; no hay CI. Ejecuta los que toque antes de dar nada por bueno.

```bash
docker compose exec backend python -m scripts.smoke_test        # flujo completo, 54 pasos
docker compose exec backend python -m pytest tests/ -q
docker compose exec backend python -m scripts.verify_guardrails # CONSUME TOKENS del proveedor
docker compose exec backend ruff check . && ruff format .

# Pipeline de video: DESDE EL HOST, no desde un contenedor (D-018).
python backend/scripts/test_video_pipeline.py

# Flujo de la app simulado contra la IP real (la única prueba que no puede correr en contenedor).
python backend/scripts/simulate_mobile_client.py http://<IP>:8000
```

```bash
cd admin-web
npm run verify           # 18 comprobaciones contra el API
npm run verify:upload    # E2E real por navegador (D-054)
npm run capture          # 8 pantallas + errores de consola
```

La app se verifica con la imagen oficial de Flutter en Docker (`flutter analyze && flutter test`),
montando `demoeca_pubcache` como volumen o el `analyze` reporta ~200 errores falsos.

El smoke test marca como OMITIDO, no como fallo, lo que requiere API key.

## Entornos

| Entorno | Notas |
|---|---|
| **Mac o Linux de desarrollo** | Los scripts `.sh` de `tools/` sirven. Los `.ps1` son para Windows y no se eliminan. |
| **Windows** | El entorno original. `tools/setup-lan-access.ps1` y `tools/build-apk.ps1`. |
| **Servidor de demo** | VPS Ubuntu, repositorio en `/root/demo_eca`. Es donde se hizo la mayor parte del trabajo reciente; por eso `.claude/settings.json` tiene rutas de ese servidor. |

Para probar en un dispositivo hay que ejecutar antes el script de red
(`tools/setup-server-access.sh` o el `.ps1`): ajusta `MINIO_PUBLIC_ENDPOINT` y recrea los
contenedores. Sin eso todo funciona **menos el video**, porque la firma SigV4 cubre la cabecera
`Host` y no se puede reescribir después (D-018, D-032).

Compila el APK con `tools/build-apk.sh` o `.ps1`, **nunca con `docker run` a mano**: montan tres
volúmenes y los tres importan, en especial el del `debug.keystore`, sin el cual cada build va
firmado con una clave distinta y Android no deja instalar encima (D-037).

## Plan AWS (decidido en octubre de 2026)

El cliente necesita la plataforma en AWS, respetando la privacidad y **al mínimo coste**,
conservando todo lo posible de la arquitectura actual.

**Volumen real:** unas 200 personas al mes y 10 máquinas. El catálogo es visible para todo el
mundo (no hace falta separar por cliente ni multi-tenancy; D-001 sigue vigente). **Hay dominio
propio** para el HTTPS. La alta disponibilidad **no** es prioritaria: se acepta levantar el
servicio si cae, siempre que no ocurra a menudo ni dure mucho, pero hace falta monitorización que
avise.

**Decisión: Docker en una sola EC2, NO Fargate.** La primera propuesta (Multi-AZ, ALB, NAT, Fargate,
RDS, ElastiCache, VPC endpoints, Config, Security Hub) costaba del orden de 400–800 USD al mes, un
orden de magnitud más que el servicio que sostiene. Quedó descartada y vive ahora como la ruta de
crecimiento por tramos, en la §9 del documento de arquitectura.

Lo que se conserva tal cual: `docker-compose.yml`, FastAPI, Celery con ffmpeg, Postgres+pgvector
en contenedor sobre disco EBS cifrado, Redis, el nginx del servicio `web`, y el proxy de HLS con
redirección 307 a URLs firmadas.

Lo que cambia:

| Pieza | Cambio |
|---|---|
| MinIO | **S3**, cifrado con KMS y sin acceso público. El SDK de MinIO habla S3; conviene pasar a credenciales por rol IAM de la instancia. Desaparece el puerto 9000 abierto a Internet. |
| Bucket público de fotos | S3 privado + CloudFront con OAC (entra en el nivel gratuito). |
| OpenAI | **Amazon Bedrock**, cubierto por el BAA de AWS. Claude para el chat, Titan o Cohere para los embeddings. Hace falta `langchain-aws`. |
| TLS | Certificado de Let's Encrypt en el nginx que ya existe, con el dominio del cliente. |
| Acceso al servidor | SSM Session Manager, sin puerto 22 abierto. |
| Monitorización | Auto-recover de EC2, `restart: unless-stopped`, comprobación de salud de Route 53 con aviso por email, CloudWatch Agent para disco y memoria. |
| Copias de seguridad | Instantánea diaria del disco y volcado de la base de datos a S3, **con la restauración probada y documentada** (sin prueba no hay plan de contingencia). |

**Coste estimado: unos 45–60 USD al mes** más el consumo de Bedrock, que a este volumen son pocos
dólares. Instancia prevista: t4g.medium (ARM, 4 GB); si alguna imagen de Docker da problemas en
ARM, t3a.medium. El tráfico de video estimado son unos 140 GB al mes, de los que AWS da 100 GB
gratis.

**Trampa del paso a Bedrock:** los embeddings bajan de 1536 a 1024 dimensiones. Eso obliga a una
migración de Alembic sobre `knowledge_chunks.embedding`, reconstruir el índice HNSW, volver a
vectorizar todo con `bootstrap_ai --force` y **medir de nuevo `RAG_MAX_DISTANCE`**: el 0.65 actual
se calibró con los embeddings de OpenAI y no es trasladable (D-005, D-015).

### Cambios de aplicación obligatorios antes de meter un dato real

Son independientes de la infraestructura: mover la demo tal cual a AWS no aporta cumplimiento.
El análisis completo de las 11 brechas (B1…B11) está en el documento de arquitectura.

1. **Login real y `AUTH_BYPASS_ENABLED=false`.** Hoy todos entran con el mismo usuario demo
   compartido, así que **el progreso de 200 personas se acumularía sobre una sola cuenta**. El
   cliente pide registrar el progreso de cada usuario, así que esto es lo primero.
2. **Pantalla de progreso por usuario en el panel.** No existe: hoy solo hay totales en el
   dashboard, y tampoco hay pantalla de usuarios. El dato ya está en la base de datos
   (`user_lesson_progress`, por usuario y lección) y hace falta el endpoint y la UI. Es además la
   base de los exámenes y certificados cuando se retomen.
3. **Registro de auditoría**: tabla de solo inserción con quién, qué recurso, qué acción y cuándo,
   para lecturas y escrituras de conversaciones, usuarios y progreso. **Sin el contenido de los
   mensajes en el log.**
4. **Sesiones más cortas:** acceso de 15 minutos, renovación de 12 horas como máximo, cierre por
   inactividad y revocación al cerrar sesión. Hoy la renovación dura 14 días.
5. **MFA con TOTP para el backoffice** (no hace falta Cognito, que encarece y añade integración).
6. **Sin datos de paciente en los logs** y tools HTTP desactivadas en producción.
7. **App:** `API_BASE_URL` con HTTPS y el dominio real, quitar `usesCleartextTraffic`, publicar
   `assetlinks.json` y `apple-app-site-association` (falta el SHA-256 de firma y el Team ID de
   Apple; ver `mobile/docs/deep-linking.md`).

**Hay datos de salud, y entran por el chat.** El guardrail impide que el agente dé consejo
clínico, pero nada impide que un técnico escriba datos de un paciente, y ese texto se guarda y se
envía al modelo. Amazon Comprehend Medical puede enmascararlos antes de guardar; es una decisión
de producto por su coste por mensaje.

### Decisiones abiertas

- **Cómo se crean las cuentas de los técnicos:** las crea el administrador desde el panel
  (recomendado, lo más barato y controlado), registro propio con verificación por email (exige
  SES), o SSO del hospital (exige Cognito). **Sin decidir: bloquea el diseño del login.**
- **Alcance del MFA:** solo el panel (recomendado) o también los técnicos en el móvil.
- Retención de las conversaciones: la fija compliance.
- Nombre definitivo del producto. La app se llama "ECA GEMINI DEMO" y ese nombre no puede
  aparecer en un certificado.
- Identificadores de la app: renombrar `com.demoeca.demoeca_app` a algo limpio solo es posible
  antes de publicar en una store (D-035).

## Riesgos abiertos del estado actual

- Todo va en **HTTP plano**, JWT incluidos, y el acceso sin credenciales está activado.
- El repositorio es público e incluye la IP del servidor junto con esa nota.
- El `.env` del servidor tiene una **API key real de OpenAI**: conviene revocarla al pasar a
  Bedrock.
- Las credenciales de Postgres y MinIO son las de demo.
- Una vez la compilación del APK se quedó parada horas antes de que Gradle arrancara, sin causa
  identificada. Si vuelve a pasar, mira los `.lock` del volumen de Gradle (D-038).

## Commits

Mensajes en español, con el prefijo del área (`Backend:`, `Panel:`, `App:`, `Seed:`,
`Documentacion:`) y el cuerpo explicando **por qué**, incluidas las alternativas descartadas.
Citan la decisión que aplican (`D-0xx`). Mira `git log` antes de escribir el primero.
