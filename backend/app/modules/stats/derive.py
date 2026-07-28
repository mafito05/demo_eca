"""Cálculo derivado del dashboard: funciones puras, sin sesión de base de datos.

Está separado de `service.py` a propósito, rompiendo la convención de cuatro ficheros por
módulo. El motivo es concreto: el requisito de que el dashboard **no mienta con datos escasos**
(media de una tabla vacía, percentil de cero filas, porcentaje sin denominador) vive todo aquí,
y aislarlo lo hace verificable con pytest sin levantar Postgres. Mezclado con `await
session.execute` habría que montar una base de datos de test para probar una división.

La regla que gobierna el módulo entero:

- `SUM` **sí** se colapsa a 0. Sumar cero mensajes son cero tokens: es verdad.
- `AVG`, percentiles y cualquier ratio **nunca**. `None` significa "no hay datos"; un `0` ahí
  es una mentira que el panel pintaría como un dato real.

Esto divergerá de `lms/service.py`, que sí devuelve `0.0` de progreso cuando no hay lecciones.
Es deliberado: en una ruta de aprendizaje 0 % significa "no has empezado", que es cierto; en el
dashboard, 0 % de respuestas con fuentes sobre cero respuestas es falso.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal

from app.modules.stats.schemas import (
    ActionSeverity,
    ContentStats,
    DailyActivity,
    KnowledgeStats,
    PendingAction,
    PendingActionCode,
    SystemHealthStats,
)


def ratio_percent(numerator: int, denominator: int, *, digits: int = 1) -> float | None:
    """Porcentaje redondeado, o `None` si no hay denominador.

    Nunca lanza `ZeroDivisionError` y nunca inventa un `0.0`.
    """
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, digits)


def to_opt_float(value: object, *, digits: int | None = None) -> float | None:
    """Normaliza el resultado de un `AVG` de SQL a `float | None`.

    Existe por una trampa real de asyncpg: `func.avg()` sobre una columna entera devuelve
    `numeric`, que llega como `decimal.Decimal`. Pydantic lo coacciona a float sin quejarse,
    pero cualquier aritmética en Python entre ese `Decimal` y un `float` lanza `TypeError`. Así
    que se convierte en el borde, no en el punto de uso.
    """
    if value is None:
        return None
    number = float(value) if isinstance(value, Decimal | int | float) else float(str(value))
    return round(number, digits) if digits is not None else number


def to_opt_int(value: object) -> int | None:
    """Igual que `to_opt_float` pero para percentiles, que se reportan en ms enteros."""
    if value is None:
        return None
    return int(float(value))


def fill_daily_series(
    *,
    anchor: date,
    days: int,
    conversations: Mapping[date, int],
    messages: Mapping[date, int],
) -> list[DailyActivity]:
    """Devuelve exactamente `days` entradas contiguas terminando en `anchor`.

    Se rellena en Python y no con `generate_series` en SQL por dos razones: hay que hacerlo dos
    veces (conversaciones y mensajes son tablas distintas), y aquí se pueden **fusionar las dos
    series en una sola lista alineada por fecha**, de modo que el panel no tenga que emparejar
    dos arrays.

    Los días sin datos entran a 0 porque aquí el cero es verdad: no hubo actividad. Las filas
    que caigan fuera de la ventana se ignoran en silencio.
    """
    start = anchor - timedelta(days=days - 1)
    return [
        DailyActivity(
            day=start + timedelta(days=offset),
            conversations=conversations.get(start + timedelta(days=offset), 0),
            messages=messages.get(start + timedelta(days=offset), 0),
        )
        for offset in range(days)
    ]


_SEVERITY_ORDER = {
    ActionSeverity.critical: 0,
    ActionSeverity.warning: 1,
    ActionSeverity.info: 2,
}


def build_pending_actions(
    *,
    content: ContentStats,
    knowledge: KnowledgeStats,
    health: SystemHealthStats,
) -> list[PendingAction]:
    """Deriva la lista de avisos accionables de los contadores ya calculados.

    **No lanza ninguna consulta**, y eso es la decisión: "acciones pendientes" es una lectura
    distinta de datos que el dashboard ya tiene, no una fuente de datos nueva.

    Cada aviso lleva `resource` con la ruta del panel que lo arregla. Un aviso que nadie puede
    resolver se convierte en ruido y el admin deja de mirar la lista, así que solo entra aquí lo
    que tiene una acción concreta detrás.
    """
    actions: list[PendingAction] = []

    def add(
        code: PendingActionCode,
        severity: ActionSeverity,
        count: int,
        message: str,
        resource: str | None = None,
    ) -> None:
        actions.append(
            PendingAction(
                code=code, severity=severity, count=count, message=message, resource=resource
            )
        )

    # --- Crítico: el producto no funciona -------------------------------------
    if health.provider_credentials_active == 0:
        add(
            PendingActionCode.no_provider_credential,
            ActionSeverity.critical,
            0,
            "No active LLM credential: the agent cannot answer.",
            "agent/providers",
        )
    elif health.provider_credentials_failing_check > 0:
        add(
            PendingActionCode.provider_credential_check_failing,
            ActionSeverity.critical,
            health.provider_credentials_failing_check,
            f"{health.provider_credentials_failing_check} provider credential(s) failed their "
            "last connectivity check.",
            "agent/providers",
        )

    if health.agent_configs_active == 0:
        add(
            PendingActionCode.no_active_agent_config,
            ActionSeverity.critical,
            0,
            "No active agent configuration.",
            "agent/agents",
        )
    elif not health.has_default_agent_config:
        add(
            PendingActionCode.no_default_agent_config,
            ActionSeverity.critical,
            0,
            "No default agent: equipment without its own configuration has nothing to fall "
            "back to.",
            "agent/agents",
        )

    if knowledge.documents_failed > 0:
        add(
            PendingActionCode.knowledge_documents_failed,
            ActionSeverity.critical,
            knowledge.documents_failed,
            f"{knowledge.documents_failed} document(s) failed to index and cannot be cited.",
            "agent/knowledge",
        )

    if content.videos.failed > 0:
        add(
            PendingActionCode.video_assets_failed,
            ActionSeverity.critical,
            content.videos.failed,
            f"{content.videos.failed} video(s) failed to transcode.",
            "lms",
        )

    # --- Aviso: algo está a medias -------------------------------------------
    if health.documents_stuck_processing > 0:
        add(
            PendingActionCode.knowledge_documents_stuck,
            ActionSeverity.warning,
            health.documents_stuck_processing,
            f"{health.documents_stuck_processing} document(s) have been indexing for too long: "
            "check the ingest worker.",
            "agent/knowledge",
        )
    elif knowledge.documents_pending > 0:
        add(
            PendingActionCode.knowledge_documents_pending,
            ActionSeverity.warning,
            knowledge.documents_pending,
            f"{knowledge.documents_pending} document(s) waiting to be vectorised.",
            "agent/knowledge",
        )

    if health.videos_stuck_processing > 0:
        add(
            PendingActionCode.video_assets_stuck,
            ActionSeverity.warning,
            health.videos_stuck_processing,
            f"{health.videos_stuck_processing} video(s) have been processing for too long: "
            "check the video worker.",
            "lms",
        )

    if content.machines.published_without_content > 0:
        add(
            PendingActionCode.published_machine_without_content,
            ActionSeverity.warning,
            content.machines.published_without_content,
            f"{content.machines.published_without_content} published machine(s) have no "
            "published training: scanning their QR leads nowhere.",
            "lms",
        )

    if content.lessons.video_without_asset > 0:
        add(
            PendingActionCode.lessons_without_video_asset,
            ActionSeverity.warning,
            content.lessons.video_without_asset,
            f"{content.lessons.video_without_asset} video lesson(s) have no video attached.",
            "lms",
        )

    # --- Informativo ---------------------------------------------------------
    if content.machines.published == 0:
        add(
            PendingActionCode.no_published_machine,
            ActionSeverity.info,
            0,
            "No published equipment yet: the mobile catalogue is empty.",
            "machines",
        )

    if health.provider_credentials_never_checked > 0:
        add(
            PendingActionCode.provider_credential_never_checked,
            ActionSeverity.info,
            health.provider_credentials_never_checked,
            f"{health.provider_credentials_never_checked} credential(s) have never been "
            "tested for connectivity.",
            "agent/providers",
        )

    if health.tools_total > 0 and health.tools_active == 0:
        add(
            PendingActionCode.tools_registered_none_active,
            ActionSeverity.info,
            health.tools_total,
            f"{health.tools_total} HTTP tool(s) registered but none active.",
            "agent/tools",
        )

    actions.sort(key=lambda action: _SEVERITY_ORDER[action.severity])
    return actions
