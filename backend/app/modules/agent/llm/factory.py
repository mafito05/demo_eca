"""Fábrica de modelos de chat: `AgentConfig` + credencial -> `BaseChatModel`.

Es la frontera de abstracción del soporte multi-LLM. Todo lo que está por encima
(`service.py`, RAG, tools) trabaja con la interfaz `BaseChatModel` de LangChain y no sabe
qué proveedor hay detrás.

Los imports de los paquetes de proveedor son perezosos a propósito: importar
langchain-google-genai cuando el cliente solo usa Anthropic añade ~1 s al arranque del
API y falla en frío si el paquete no está instalado.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.crypto import decrypt
from app.modules.agent.llm.registry import get_spec
from app.modules.agent.models import AgentConfig, LLMProviderKey, ProviderCredential


class ProviderNotConfiguredError(RuntimeError):
    """No hay credencial activa para el proveedor que pide el agente."""


def build_chat_model(
    config: AgentConfig,
    credential: ProviderCredential,
    *,
    streaming: bool = True,
) -> BaseChatModel:
    api_key = decrypt(credential.encrypted_api_key)
    spec = get_spec(config.provider)
    base_url = credential.base_url or spec.default_base_url

    common = {
        "model": config.model_name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "streaming": streaming,
    }

    if config.provider is LLMProviderKey.anthropic:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(api_key=api_key, base_url=base_url, timeout=60, **common)

    if config.provider is LLMProviderKey.google:
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Gemini no acepta `max_tokens` ni `streaming` con esos nombres.
        return ChatGoogleGenerativeAI(
            model=config.model_name,
            google_api_key=api_key,
            temperature=config.temperature,
            max_output_tokens=config.max_tokens,
            disable_streaming=not streaming,
        )

    if spec.openai_compatible:
        # OpenAI, Grok y DeepSeek. La única diferencia es la base_url.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(api_key=api_key, base_url=base_url, timeout=60, **common)

    raise ValueError(f"Provider not implemented in the factory: {config.provider}")


@lru_cache
def build_embeddings():
    """Modelo de embeddings, fijo por instalación (D-005).

    Cacheado: se instancia una vez por proceso. No depende de la BD a propósito — es
    infraestructura, no configuración editable por el admin.
    """
    from app.core.config import settings

    if not settings.EMBEDDING_API_KEY:
        raise ProviderNotConfiguredError(
            "EMBEDDING_API_KEY is not configured; RAG cannot index or search."
        )

    if settings.EMBEDDING_PROVIDER == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.EMBEDDING_API_KEY,
        )

    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.EMBEDDING_API_KEY,
        # Se fija explícitamente para que un desajuste con la columna vector(N) falle en
        # la llamada al proveedor y no al insertar en Postgres.
        dimensions=settings.EMBEDDING_DIM,
    )
