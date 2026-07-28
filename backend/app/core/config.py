"""Configuración central. Única fuente de verdad para variables de entorno.

Regla del proyecto: ningún módulo lee `os.environ` directamente. Todo pasa por
`settings`, para que el conjunto de variables sea auditable en un solo fichero.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Las listas se declaran en .env como CSV (`a,b,c`), que es más legible a mano que JSON.
# `NoDecode` es imprescindible: sin él, pydantic-settings intenta json.loads() sobre el valor
# del entorno ANTES de ejecutar cualquier validador, y arranca con "error parsing value".
CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General -------------------------------------------------------------
    PROJECT_NAME: str = "DemoECA · Plataforma de Capacitación MedTech"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Base de datos -------------------------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://demoeca:demoeca@localhost:5432/demoeca"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis / Celery ------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- MinIO ---------------------------------------------------------------
    MINIO_ENDPOINT: str = "localhost:9000"
    # Endpoint que se usa para FIRMAR URLs destinadas a un cliente externo (app móvil,
    # panel). Dentro de Docker el backend habla con `minio:9000`, pero una URL prefirmada
    # con ese host no la puede resolver ni el navegador ni el móvil: la firma va sobre el
    # host, así que no se puede reescribir después. Vacío = usar MINIO_ENDPOINT.
    MINIO_PUBLIC_ENDPOINT: str = ""
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin"
    MINIO_SECURE: bool = False
    # Debe declararse explícitamente: sin región, el SDK de MinIO consulta la del bucket por
    # red antes de firmar, y el cliente de firma apunta a un host que el backend no alcanza.
    MINIO_REGION: str = "us-east-1"
    MINIO_BUCKET_VIDEO: str = "demoeca-video"
    MINIO_BUCKET_DOCS: str = "demoeca-docs"
    MINIO_BUCKET_PUBLIC: str = "demoeca-public"
    MINIO_PRESIGN_TTL_SECONDS: int = 3600

    # --- Seguridad -----------------------------------------------------------
    JWT_SECRET_KEY: str = "cambiame-en-produccion"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    SECRET_ENCRYPTION_KEY: str = ""

    AUTH_BYPASS_ENABLED: bool = False
    # Dominio bajo `example.com` (reservado por RFC 2606). NO usar un TLD `.local`/`.test`:
    # `email-validator`, que es lo que respalda a `EmailStr`, los rechaza como nombres de
    # uso especial y el login devolvería 422 para todos los usuarios sembrados.
    DEMO_USER_EMAIL: str = "demo@demoeca.example.com"

    CORS_ORIGINS: CsvList = Field(default_factory=lambda: ["http://localhost:4200"])

    # --- Deep linking --------------------------------------------------------
    DEEPLINK_DOMAIN: str = "demoeca.example.com"
    DEEPLINK_SCHEME: str = "demoeca"
    # Identificadores REALES de la app, tal como los generó `flutter create` combinando
    # `--org com.demoeca` con el nombre de proyecto `demoeca_app`. Son feos y conviene renombrarlos
    # antes de publicar en las stores (después ya no se puede: el identificador es la identidad de
    # la app), pero mientras tanto tienen que coincidir con el binario o el `assetlinks.json` y el
    # `apple-app-site-association` apuntarían a una app que no existe.
    #
    # Hoy solo se usan como documentación: nada en el backend los lee todavía. Cuando se genere el
    # `assetlinks.json` desde aquí, serán la fuente de verdad.
    ANDROID_PACKAGE_NAME: str = "com.demoeca.demoeca_app"
    IOS_BUNDLE_ID: str = "com.demoeca.demoecaApp"

    # --- Embeddings (fijos, ver D-005) --------------------------------------
    EMBEDDING_PROVIDER: Literal["openai", "google"] = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536
    EMBEDDING_API_KEY: str = ""

    # --- RAG -----------------------------------------------------------------
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 150
    RAG_TOP_K: int = 5
    RAG_MAX_DISTANCE: float = 0.65

    # --- Agente --------------------------------------------------------------
    AGENT_MAX_HISTORY_MESSAGES: int = 20
    AGENT_MAX_TOOL_ITERATIONS: int = 5
    AGENT_RATE_LIMIT_PER_MINUTE: int = 20

    # --- Tools HTTP dinámicas (D-007) ---------------------------------------
    TOOL_ALLOWED_HOSTS: CsvList = Field(default_factory=list)
    TOOL_TIMEOUT_SECONDS: int = 15
    TOOL_MAX_RESPONSE_BYTES: int = 131_072

    # --- Video / HLS ---------------------------------------------------------
    FFMPEG_BINARY: str = "ffmpeg"
    HLS_SEGMENT_SECONDS: int = 6
    HLS_RENDITIONS: CsvList = Field(default_factory=lambda: ["360p", "720p"])
    # Vida del token de reproducción. Tiene que sobrevivir a la lección más larga: si caduca
    # a mitad del video, el reproductor falla al pedir el siguiente segmento.
    HLS_TOKEN_TTL_SECONDS: int = 7200
    # Porcentaje visto a partir del cual la lección se marca como completada. No es 100%
    # porque casi nadie ve los créditos finales ni el último segundo del video.
    LESSON_COMPLETION_PERCENT: float = 90.0

    @property
    def minio_public_endpoint(self) -> str:
        """Host con el que se firman las URLs que consumirá un cliente externo."""
        return self.MINIO_PUBLIC_ENDPOINT or self.MINIO_ENDPOINT

    @field_validator("CORS_ORIGINS", "TOOL_ALLOWED_HOSTS", "HLS_RENDITIONS", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def sync_database_url(self) -> str:
        """URL con driver sincrono, para Celery y Alembic."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
