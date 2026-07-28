# DemoECA — Plataforma B2B de Capacitación MedTech + Agente IA

Plataforma de formación técnica sobre equipamiento médico. El QR pegado en la máquina
física abre la ruta de capacitación en la app móvil (videos HLS, manuales, quizzes,
certificado) con un agente IA contextual que responde sobre ese equipo concreto.

> **El producto está en inglés** (interfaz, mensajes del API, prompt del agente y contenido
> sembrado). **La documentación interna y los comentarios del código siguen en español**, porque son
> para el equipo de desarrollo. Ver D-039.

Las decisiones de arquitectura y los supuestos pendientes de confirmar están en
[DECISIONS.md](DECISIONS.md). Leerlo antes de tocar el esquema.

## Estado actual

Verificado con el stack levantado y una API key real de OpenAI: **`54/54` del smoke test,
`36/36` del pipeline de video, `19/19` del flujo móvil por LAN, `18/18` del panel, `9/9` de la
subida E2E por navegador, `29/29` de pytest y `4/4` del guardrail clínico. La app: `analyze`
limpio y `71/71` tests.** El flujo completo funciona: escanear el QR lleva a la capacitación, el
video se reproduce en HLS con URLs firmadas, el progreso se registra, y el agente responde
sobre el manual del equipo citando la sección exacta — tanto desde el API como desde el panel
en un navegador real.

| Componente | Estado |
|---|---|
| Infraestructura Docker (Postgres+pgvector, Redis, MinIO, worker) | ✅ Levantado y verificado |
| Esquema de BD: 21 tablas + índice HNSW `vector_cosine_ops` | ✅ Migrado y verificado |
| Auth + JWT + RBAC + bypass demo | ✅ Verificado, incluidos casos negativos |
| QR: PNG, SVG, export, resolver del deep link | ✅ Verificado end-to-end |
| Agent Builder: catálogo multi-LLM, configuración, conocimiento | ✅ Verificado |
| Defensa SSRF de las tools HTTP | ✅ 14 tests, incluida IP interna con host autorizado |
| WebSocket: handshake, auth, keepalive, degradación por error | ✅ Verificado |
| Worker Celery con colas `video` e `ingest` separadas | ✅ Vectorizando de verdad |
| RAG: vectorización, recuperación y citación por sección | ✅ Verificado y medido (D-015) |
| Streaming de respuestas del LLM por WebSocket | ✅ Verificado (106 chunks, 4 fuentes citadas) |
| Guardrail clínico: rehúsa consejo sobre pacientes | ✅ Verificado (D-016) |
| Transcodificación HLS multi-bitrate | ✅ Probado con un mp4 real (360p + 720p) |
| Reproducción HLS con proxy firmado | ✅ Verificado, incluidos 5 casos negativos (D-017) |
| LMS: módulos, lecciones, ruta de aprendizaje | ✅ Verificado |
| Progreso: heartbeat idempotente y bloqueo por prerrequisito | ✅ Verificado (D-020) |
| **Dashboard de KPIs** con datos reales | ✅ `/stats/overview` en ~190 ms · gráficos sin librería (D-041, D-044) |
| **Panel Angular** (8 pantallas) | ✅ Sidebar + topbar, tema conmutable, responsive (D-042, D-043) |
| **App Flutter** | ✅ Compila (APK) · `analyze` limpio · 63 tests (incl. widget) — ⚠️ **nunca ejecutada en hardware** (D-028) |
| Sistema de diseño de la app: 15 component themes, 13 roles tipográficos | ✅ Verificado en claro y oscuro a 320 y 411 dp (D-045, D-046) |
| Calidad del backend: `ruff check` + `ruff format` | ✅ Sin hallazgos |
| Evaluaciones y certificados | 🔜 **Próximamente**: fuera del alcance de la demo. Modelos y esquema ya en la BD |

### Verificación automatizada

```bash
docker compose exec backend python -m scripts.smoke_test        # flujo completo, 54 pasos
docker compose exec backend python -m pytest tests/ -q          # SSRF + derivaciones del dashboard
docker compose exec backend python -m scripts.verify_guardrails # guardrail + calidad del RAG

# Pipeline de video (34 pasos). Se ejecuta DESDE EL HOST, no desde un contenedor: las URLs
# prefirmadas se firman contra localhost:9000, que dentro de un contenedor no resuelve (D-018).
docker compose exec worker python -m scripts.test_video_pipeline --make-source
python backend/scripts/test_video_pipeline.py
```

- El smoke test marca como OMITIDO (no como fallo) los pasos que requieren API key, así que
  sirve igual como comprobación de regresión sin claves configuradas.
- `verify_guardrails` **consume tokens** del proveedor: prueba dos preguntas clínicas y dos
  técnicas contra el LLM real, e imprime el ranking de recuperación con distancias. Es la
  herramienta para juzgar si el troceado está bien dimensionado (ver D-015).

### Puesta en marcha de la IA

```bash
# Lee la key del entorno (nunca de un argumento: quedaría en el historial del shell),
# registra la credencial cifrada y vectoriza los documentos pendientes.
docker compose exec backend python -m scripts.bootstrap_ai
docker compose exec backend python -m scripts.bootstrap_ai --force   # reindexa TODO
```

`--force` es **obligatorio** tras cambiar el troceado o el modelo de embeddings: los chunks
antiguos seguirían en la tabla, mezclados con los nuevos, contaminando las respuestas.

### Datos para el dashboard

El dashboard funciona con datos reales, y una instalación recién sembrada tiene una máquina y unos
pocos mensajes: se ve honesto pero plano. Para una demostración:

```bash
docker compose exec backend python -m scripts.seed_demo_activity          # ~3 semanas de historial
docker compose exec backend python -m scripts.seed_demo_activity --purge  # revertirlo
```

Genera cuatro cuentas de formación, conversaciones con tokens y latencias del rango que el sistema
produce de verdad, y progreso de lecciones. **No toca `seed_demo.py`**: el seed base sigue siendo la
verdad del producto y esto es escenografía, reversible y con semilla fija. Ver D-048.

El dashboard está diseñado para verse bien también **sin** sembrar (D-044): la lista de avisos vacía
es un estado de victoria explícito, y las métricas sin datos muestran `—` en lugar de un `0` que sería
una afirmación falsa.

### Panel administrativo

```bash
cd admin-web
npm install
npm start                # http://localhost:4200 (proxy de /api al backend en :8000)

npm run verify           # 18 comprobaciones contra el API a través del proxy
npm run verify:upload    # E2E real: sube un mp4 POR EL NAVEGADOR, publica y borra (D-054)
npm run capture          # capturas de las 8 pantallas + errores de consola
```

Entrar con `superadmin@demoeca.example.com` / `Demo1234!`. `npm run capture` conduce el Edge
instalado por CDP (sin descargar navegador), escribe una pregunta en el playground y comprueba
que el streaming y las fuentes se renderizan; deja las imágenes en `admin-web/.captures/`.

**Requiere Node ≥ 22.22.3 o ≥ 24.15.** Angular CLI está fijado a la 21 porque la 22 exige una
Node más nueva que la instalada en la máquina de desarrollo.

### App móvil

```powershell
# 1. Configurar el backend para la red local (detecta la IP y recrea los contenedores).
#    Imprescindible para BlueStacks o un teléfono: sin esto el video no carga, porque las URLs
#    prefirmadas de MinIO se firman contra un host concreto.
.\tools\setup-lan-access.ps1

# 2. Compilar el APK (detecta la IP y la embebe; usa Flutter en Docker).
.\tools\build-apk.ps1
```

**Usa `build-apk.ps1` y no `docker run` a mano.** Monta tres volúmenes y los tres importan: el caché
de pub, el de Gradle, y el que guarda el `debug.keystore` — sin este último cada build va firmado con
una clave distinta y Android no deja instalarlo sobre el anterior (D-037).

Con Flutter instalado en el host, para desarrollo con hot reload:

```powershell
cd mobile
flutter run --dart-define=API_BASE_URL=http://TU_IP:8000
```

Guía paso a paso para BlueStacks (instalación del APK, ADB, deep links, fallos frecuentes):
[mobile/docs/bluestacks.md](mobile/docs/bluestacks.md).

Verificar el flujo completo del móvil desde el host, contra la IP de LAN:

```bash
python backend/scripts/simulate_mobile_client.py http://TU_IP:8000
```

Recorre la misma secuencia que la app (bypass → QR → ruta → lección → HLS → progreso → chat) y
comprueba explícitamente que los segmentos de video redirigen al host correcto — el fallo más
probable al pasar de `localhost` a un dispositivo.

Sin Flutter instalado, todo se verifica con la imagen oficial en Docker (es como se hizo):

```bash
docker volume create demoeca_pubcache
docker run --rm -v "${PWD}/mobile:/app" -v demoeca_pubcache:/root/.pub-cache -w /app \
  ghcr.io/cirruslabs/flutter:stable \
  bash -lc "flutter pub get && flutter analyze && flutter test"
```

**La app no se ha ejecutado nunca**: no hay emulador ni dispositivo en el entorno de desarrollo.
Compila y su lógica está cubierta por tests, pero la cámara, el reproductor y el chat están sin
probar contra hardware. Ver [mobile/README.md](mobile/README.md) y
[mobile/docs/deep-linking.md](mobile/docs/deep-linking.md), que lista los datos que faltan del
cliente (dominio real, SHA-256 de firma Android, Team ID de Apple).

### Calidad del backend

```bash
docker compose exec backend ruff check .    # linter
docker compose exec backend ruff format .   # formateador
```

## Arranque

```bash
cp .env.example .env
# Generar las dos claves y pegarlas en .env:
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up -d --build
docker compose exec backend alembic revision --autogenerate -m "esquema inicial"
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.seed_demo
```

- API + Swagger: http://localhost:8000/docs
- Consola de MinIO: http://localhost:9001

## Probar el flujo del agente

1. `POST /api/v1/auth/login` con `superadmin@demoeca.example.com` / `Demo1234!`
2. `POST /api/v1/agent/credentials` con la API key del proveedor que se quiera usar.
3. `POST /api/v1/agent/credentials/{id}/test` para confirmar la conectividad.
4. Poner `EMBEDDING_API_KEY` en `.env` y reiniciar el backend y el worker.
5. `POST /api/v1/agent/documents/{id}/reindex` con el documento que crea el seed (el manual
   del litotrictor) para vectorizarlo.
6. `POST /api/v1/agent/retrieval-test` con `{"query": "qué significa el error E-204"}` — debe
   devolver el fragmento del manual con distancia baja. **Este paso verifica el RAG sin
   gastar tokens del LLM.**
7. `POST /api/v1/auth/demo-login` para obtener el token del usuario demo.
8. Conectar a `ws://localhost:8000/api/v1/agent/ws?token=<access_token>` y enviar:
   ```json
   {"type":"message","content":"¿Qué hago si sale el error E-204?","machine_model_id":"<id>"}
   ```
   Debe llegar `start` → `sources` → muchos `token` → `done`.

## Estructura del repositorio

```
demoeca/
├── docker-compose.yml          # Postgres+pgvector, Redis, MinIO, backend, worker
├── DECISIONS.md                # ADR: decisiones, atajos de demo y sus rutas de salida
├── docker/postgres/init.sql    # CREATE EXTENSION vector
├── backend/                    # FastAPI, feature-based
│   ├── alembic/
│   ├── scripts/seed_demo.py
│   └── app/
│       ├── main.py
│       ├── models.py           # Registro único de modelos (Alembic lo necesita)
│       ├── core/               # config, db, security, crypto, storage, deps, ratelimit
│       ├── modules/
│       │   ├── auth/           # JWT, RBAC, bypass demo
│       │   ├── machines/       # catálogo + QR + resolver del deep link
│       │   ├── lms/            # módulos, lecciones, video HLS, progreso
│       │   ├── assessments/    # quizzes, intentos, certificados
│       │   └── agent/          # ← núcleo del producto
│       │       ├── llm/        # registry (catálogo) + factory (multi-LLM)
│       │       ├── rag/        # ingest (troceo/embeddings) + retriever (pgvector)
│       │       ├── tools/      # security (SSRF) + http_tool + registry
│       │       ├── prompts.py  # prompt base con guardrails clínicos
│       │       ├── service.py  # orquestación y bucle de tool calling
│       │       └── ws.py       # WebSocket de streaming
│       └── workers/            # Celery: video (FFmpeg/HLS) e ingest (vectorización)
├── admin-web/                  # Angular (backoffice)
└── mobile/                     # Flutter
```

## Notas para quien continúe

- **No se lee `os.environ` fuera de `core/config.py`.** El conjunto de variables tiene que
  ser auditable en un solo fichero.
- **Ningún endpoint devuelve un secreto en claro**, ni al superadmin. Solo `key_hint`.
- **El prompt base del agente no es editable** desde el panel; el admin añade instrucciones
  encima. Ver D-006.
- **Las tools HTTP son fail-closed**: con `TOOL_ALLOWED_HOSTS` vacío no se ejecuta ninguna.
- Antes de producción: `AUTH_BYPASS_ENABLED=false`, generar claves nuevas, `pip freeze` a un
  lock, y sustituir el proxy de HLS por un CDN con signed cookies (D-011).
