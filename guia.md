# Documento de Arquitectura y Requerimientos: Plataforma B2B EdTech/MedTech + Agente IA

## 1. Visión General del Proyecto
Desarrollo de una plataforma B2B para la capacitación técnica de equipos médicos (ej. máquinas de urología, trauma, cardiología). El sistema vincula el hardware físico con el software a través de códigos QR. Los usuarios escanearán el QR de una máquina física para acceder a su ruta de aprendizaje específica en la app móvil (videos, manuales, quizzes) y contarán con la asistencia de un Agente IA contextual y dinámico.

## 2. Stack Tecnológico
*   **Aplicación Móvil (Clientes):** Flutter (Android e iOS).
*   **Panel Administrativo (Backoffice):** Angular (SPA exclusiva para gestión interna, sin vistas de cliente).
*   **Backend (API & Orquestación):** FastAPI (Python) estructurado modularmente (feature-based).
*   **Base de Datos Relacional y Vectorial:** PostgreSQL con la extensión `pgvector`.
*   **Almacenamiento de Archivos (Object Storage):** MinIO (Compatible con S3).
*   **Caché, Sesiones y Colas asíncronas:** Redis + Celery (o ARQ).
*   **Orquestación de IA:** LangChain (para manejo de LLMs agnósticos, RAG y Function Calling).
*   **Infraestructura:** Docker y `docker-compose`.

## 3. Arquitectura de Módulos Principales

### 3.1. Módulo de Autenticación y Usuarios (Auth)
*   **Seguridad:** Basada en JWT (JSON Web Tokens).
*   **Roles (RBAC):** Separación estricta entre Administradores (acceso a Angular) y Usuarios/Médicos (acceso a Flutter).
*   **Bypass Temporal (App):** Implementar un endpoint temporal de bypass de login para escanear el QR e ingresar directamente para pruebas, escalable a un sistema completo de auth posteriormente.

### 3.2. Módulo de Códigos QR y Deep Linking
*   **Generación (Backend):** FastAPI debe generar los códigos QR al registrar una nueva máquina. El output debe ser versátil: imágenes descargables (PNG/SVG) para imprimir y la data en texto plano/URL para exportar a otros softwares de la compañía.
*   **Consumo (Mobile):** Flutter utilizará *Deep Linking* (App Links/Universal Links). Al escanear el QR, se abre la app y redirige automáticamente al flujo de capacitación de esa máquina específica.

### 3.3. Módulo LMS (Capacitación y Video HLS)
*   **Estructura:** Máquinas -> Módulos/Etapas -> Lecciones (Videos). Seguimiento de progreso del usuario (pendiente, completado).
*   **Procesamiento de Video (Asíncrono):** El panel de Angular subirá archivos `.mp4` (u otros formatos) a FastAPI. El backend usará un *worker* asíncrono (ej. Celery/Redis + FFmpeg) para transcodificar el video a formato **HLS (HTTP Live Streaming)** para evitar cortes o latencia en redes móviles.
*   **Almacenamiento:** Los videos HLS y sus segmentos (`.ts`, `.m3u8`) se alojarán y servirán desde MinIO.

### 3.4. Módulo de Evaluaciones y Certificaciones
*   **Quizzes:** Exámenes dinámicos al finalizar módulos de máquinas.
*   **Certificaciones:** Al aprobar un quiz, FastAPI generará un certificado en PDF al vuelo y lo guardará en MinIO, disponibilizando la URL para su descarga en la app.

### 3.5. Módulo Agent Builder & IA Contextual (Core)
*   **Proveedor Multi-LLM (Agnóstico):** Desde el panel Angular, el administrador puede seleccionar qué LLM usará el agente (OpenAI, Anthropic, Gemini, Grok, DeepSeek). LangChain abstraerá esta conexión en el backend.
*   **Gestor de Integraciones:** Las API Keys de los proveedores se guardarán encriptadas en PostgreSQL.
*   **RAG (Retrieval-Augmented Generation):** Los manuales PDF y transcripciones de video de cada máquina se vectorizarán y guardarán en `pgvector`. El agente usará este contexto para responder.
*   **Gestor de Herramientas (Function Calling):** El panel web debe permitir registrar APIs HTTP externas. LangChain las transformará en *Tools* para que el LLM pueda ejecutar acciones en el sistema a través de FastAPI.
*   **Interfaz de Usuario (Mobile):** El agente vivirá como un "botón flotante de chat" dentro de las vistas de capacitación de la máquina, teniendo el contexto de la máquina actual.
*   **Comunicación:** Se usarán **WebSockets** en FastAPI y Flutter para transmitir las respuestas del LLM en tiempo real (*streaming* de tokens).

## 4. Instrucciones para Claude
Actúa como un Tech Lead y Arquitecto de Software Senior. Basándote estrictamente en este stack y estos requerimientos funcionales:
1.  Diseña la estructura de base de datos inicial (modelos en SQLAlchemy/SQLModel).
2.  Desarrolla el esqueleto de directorios para FastAPI, Angular y Flutter.
3.  Comienza por el código del módulo del Agent Builder en FastAPI (integrando LangChain, WebSockets, pgvector y el soporte multi-LLM dinámico).
4.  Genera el código de forma iterativa, explicando las decisiones de diseño aplicadas.