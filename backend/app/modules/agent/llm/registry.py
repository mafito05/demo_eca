"""Catálogo de proveedores LLM.

Este fichero es la única pieza que conoce las particularidades de cada proveedor. El
resto del sistema trabaja contra `LLMProviderKey` y contra los objetos `Runnable` de
LangChain, de modo que añadir un proveedor nuevo es añadir una entrada aquí y (si no es
compatible con OpenAI) una rama en `factory.py`.

El catálogo de modelos es una **sugerencia para el panel**, no una restricción: el admin
puede escribir cualquier `model_name`. Los proveedores publican modelos nuevos cada pocas
semanas y una lista cerrada obligaría a desplegar backend para usar uno recién salido.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.agent.models import LLMProviderKey


@dataclass(frozen=True)
class ProviderSpec:
    key: LLMProviderKey
    display_name: str
    # True si su API es compatible con el protocolo de OpenAI (se resuelve con
    # langchain-openai + base_url en lugar de un paquete propio).
    openai_compatible: bool
    default_base_url: str | None
    suggested_models: list[str] = field(default_factory=list)
    supports_tools: bool = True
    supports_streaming: bool = True
    # URL donde el admin obtiene su API key. Se muestra en el panel; ahorra soporte.
    api_key_url: str | None = None


PROVIDERS: dict[LLMProviderKey, ProviderSpec] = {
    LLMProviderKey.openai: ProviderSpec(
        key=LLMProviderKey.openai,
        display_name="OpenAI",
        openai_compatible=True,
        default_base_url=None,  # el SDK usa su endpoint por defecto
        # El primero de la lista es el que usa el test de conectividad de credenciales:
        # conviene que sea el más barato que exista, no el más capaz.
        suggested_models=["gpt-5-mini", "gpt-5", "gpt-4.1", "gpt-4o-mini"],
        api_key_url="https://platform.openai.com/api-keys",
    ),
    LLMProviderKey.anthropic: ProviderSpec(
        key=LLMProviderKey.anthropic,
        display_name="Anthropic (Claude)",
        openai_compatible=False,
        default_base_url=None,
        suggested_models=["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
        api_key_url="https://console.anthropic.com/settings/keys",
    ),
    LLMProviderKey.google: ProviderSpec(
        key=LLMProviderKey.google,
        display_name="Google (Gemini)",
        openai_compatible=False,
        default_base_url=None,
        suggested_models=["gemini-2.5-flash", "gemini-2.5-pro"],
        api_key_url="https://aistudio.google.com/apikey",
    ),
    LLMProviderKey.grok: ProviderSpec(
        key=LLMProviderKey.grok,
        display_name="xAI (Grok)",
        openai_compatible=True,
        default_base_url="https://api.x.ai/v1",
        suggested_models=["grok-3", "grok-2-latest"],
        api_key_url="https://console.x.ai",
    ),
    LLMProviderKey.deepseek: ProviderSpec(
        key=LLMProviderKey.deepseek,
        display_name="DeepSeek",
        openai_compatible=True,
        default_base_url="https://api.deepseek.com/v1",
        suggested_models=["deepseek-chat", "deepseek-reasoner"],
        # El modelo de razonamiento no admite function calling; la UI debe avisar.
        supports_tools=True,
        api_key_url="https://platform.deepseek.com/api_keys",
    ),
}


def get_spec(provider: LLMProviderKey) -> ProviderSpec:
    try:
        return PROVIDERS[provider]
    except KeyError as exc:  # pragma: no cover - defensa ante enum desincronizado
        raise ValueError(f"Proveedor no soportado: {provider}") from exc


def catalog_for_panel() -> list[dict]:
    """Payload que consume el selector de proveedor/modelo del panel Angular."""
    return [
        {
            "key": spec.key.value,
            "display_name": spec.display_name,
            "suggested_models": spec.suggested_models,
            "supports_tools": spec.supports_tools,
            "supports_streaming": spec.supports_streaming,
            "requires_base_url": spec.openai_compatible and spec.default_base_url is not None,
            "default_base_url": spec.default_base_url,
            "api_key_url": spec.api_key_url,
        }
        for spec in PROVIDERS.values()
    ]
