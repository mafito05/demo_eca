"""Tests del cálculo derivado del dashboard.

Lo que se prueba aquí es una sola cosa, y es la que importa: **el dashboard no miente cuando no
hay datos**. Media de una tabla vacía, percentil de cero filas, porcentaje sin denominador, serie
temporal con huecos. Con datos escasos —que es exactamente el estado de una demo recién
sembrada— esos son los casos que producen un `NaN` en pantalla, un `Infinity%` o una barra
inexistente, y ninguno se detecta mirando el JSON con datos abundantes.

Es lógica pura, sin base de datos. Las consultas quedan cubiertas por `scripts/smoke_test.py`,
que corre contra el Postgres real: un test sobre SQLite no valdría porque `json_typeof`,
`percentile_disc` y `timezone()` no existen allí, así que pasaría en verde sin decir nada sobre
si el SQL compila donde se ejecuta de verdad.

Compatible con pytest, y ejecutable sin él:

    docker compose exec backend python -m tests.test_stats_derivations
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import pairwise

from app.modules.stats.derive import (
    build_pending_actions,
    fill_daily_series,
    ratio_percent,
    to_opt_float,
    to_opt_int,
)
from app.modules.stats.schemas import (
    ActionSeverity,
    ContentStats,
    KnowledgeStats,
    LessonCounters,
    MachineCounters,
    ModuleCounters,
    PendingActionCode,
    SystemHealthStats,
    VideoCounters,
)


# =============================================================================
#  Ratios
# =============================================================================
def test_ratio_percent_sin_denominador_es_none() -> None:
    """El caso que rompería el dashboard: 0 respuestas con fuente sobre 0 respuestas.

    Tiene que ser `None` ("no hay datos"), no `0.0` ("hay datos y el valor es cero"). El panel
    los pinta distinto a propósito.
    """
    assert ratio_percent(0, 0) is None
    assert ratio_percent(5, 0) is None
    assert ratio_percent(0, -1) is None


def test_ratio_percent_calcula_y_redondea() -> None:
    assert ratio_percent(1, 3) == 33.3
    assert ratio_percent(3, 4) == 75.0
    assert ratio_percent(0, 10) == 0.0  # cero genuino: hay denominador
    assert ratio_percent(10, 10) == 100.0


# =============================================================================
#  Normalización de tipos
# =============================================================================
def test_to_opt_float_convierte_decimal_a_float() -> None:
    """Regresión de una trampa real de asyncpg.

    `func.avg()` sobre una columna entera devuelve `numeric`, que llega como `Decimal`. Pydantic
    lo coacciona sin queja, pero cualquier aritmética posterior entre ese `Decimal` y un `float`
    lanza `TypeError`. Por eso se normaliza en el borde.
    """
    result = to_opt_float(Decimal("2844.5"))
    assert result == 2844.5
    assert isinstance(result, float)
    assert not isinstance(result, Decimal)


def test_to_opt_float_propaga_none() -> None:
    assert to_opt_float(None) is None
    assert to_opt_int(None) is None


def test_to_opt_float_redondea_cuando_se_pide() -> None:
    assert to_opt_float(Decimal("2844.567"), digits=0) == 2845.0
    assert to_opt_float(Decimal("2844.567"), digits=1) == 2844.6


def test_to_opt_int_trunca_percentiles() -> None:
    assert to_opt_int(Decimal("2353.0")) == 2353
    assert to_opt_int(2353.9) == 2353


# =============================================================================
#  Serie temporal
# =============================================================================
ANCHOR = date(2026, 7, 27)


def test_fill_daily_series_rellena_huecos() -> None:
    """La serie tiene que ser contigua: un hueco en el gráfico parece un fallo de render."""
    series = fill_daily_series(
        anchor=ANCHOR,
        days=14,
        conversations={date(2026, 7, 20): 3, ANCHOR: 5},
        messages={ANCHOR: 10},
    )

    assert len(series) == 14
    assert series[0].day == date(2026, 7, 14)
    assert series[-1].day == ANCHOR

    # Contigua y ascendente, sin saltos.
    for previous, current in pairwise(series):
        assert (current.day - previous.day).days == 1

    # Los días sin datos van a cero: aquí el cero es verdad, no hubo actividad.
    assert series[6].day == date(2026, 7, 20)
    assert series[6].conversations == 3
    assert series[6].messages == 0
    assert series[-1].conversations == 5
    assert series[-1].messages == 10
    assert series[0].conversations == 0


def test_fill_daily_series_ignora_fuera_de_ventana() -> None:
    series = fill_daily_series(
        anchor=ANCHOR,
        days=3,
        conversations={date(2020, 1, 1): 999, date(2030, 1, 1): 999},
        messages={},
    )
    assert len(series) == 3
    assert sum(entry.conversations for entry in series) == 0


def test_fill_daily_series_con_un_solo_dia() -> None:
    series = fill_daily_series(anchor=ANCHOR, days=1, conversations={ANCHOR: 2}, messages={})
    assert len(series) == 1
    assert series[0].day == ANCHOR
    assert series[0].conversations == 2


def test_fill_daily_series_vacia_sigue_teniendo_longitud() -> None:
    """Sin ninguna actividad, el gráfico debe poder dibujar 30 barras a cero, no una lista vacía."""
    series = fill_daily_series(anchor=ANCHOR, days=30, conversations={}, messages={})
    assert len(series) == 30
    assert all(entry.messages == 0 and entry.conversations == 0 for entry in series)


# =============================================================================
#  Avisos accionables
# =============================================================================
def _content(*, published: int = 1, orphans: int = 0, failed_videos: int = 0) -> ContentStats:
    return ContentStats(
        machines=MachineCounters(
            total=published,
            draft=0,
            published=published,
            archived=0,
            published_without_content=orphans,
            by_specialty=[],
        ),
        modules=ModuleCounters(total=2, draft=0, published=2, archived=0),
        lessons=LessonCounters(
            total=5,
            draft=0,
            published=5,
            archived=0,
            video=1,
            pdf=0,
            text=4,
            video_without_asset=0,
            estimated_minutes_total=33,
        ),
        videos=VideoCounters(
            total=1,
            uploaded=0,
            queued=0,
            processing=0,
            ready=1,
            failed=failed_videos,
            ready_minutes=0.2,
            total_size_mb=0.6,
        ),
    )


def _knowledge(*, failed: int = 0, pending: int = 0) -> KnowledgeStats:
    return KnowledgeStats(
        documents_total=1 + failed + pending,
        documents_pending=pending,
        documents_processing=0,
        documents_indexed=1,
        documents_failed=failed,
        documents_global=0,
        documents_by_source_type=[],
        chunks_total=6,
        chunks_global=0,
        declared_chunk_count_total=6,
        embedding_models=["text-embedding-3-small"],
        average_chunks_per_indexed_document=6.0,
        last_indexed_at=None,
    )


def _health(
    *,
    credentials_active: int = 1,
    failing: int = 0,
    never_checked: int = 0,
    has_default: bool = True,
    configs_active: int = 1,
    tools_total: int = 0,
    tools_active: int = 0,
    stuck_documents: int = 0,
    stuck_videos: int = 0,
    failed_videos: int = 0,
    failed_documents: int = 0,
) -> SystemHealthStats:
    return SystemHealthStats(
        provider_credentials_total=max(credentials_active, 1),
        provider_credentials_active=credentials_active,
        provider_credentials_failing_check=failing,
        provider_credentials_never_checked=never_checked,
        agent_configs_total=1,
        agent_configs_active=configs_active,
        has_default_agent_config=has_default,
        tools_total=tools_total,
        tools_active=tools_active,
        tool_invocations_in_window=0,
        tool_invocation_errors_in_window=0,
        tool_error_percent=None,
        videos_failed=failed_videos,
        videos_stuck_processing=stuck_videos,
        documents_failed=failed_documents,
        documents_stuck_processing=stuck_documents,
    )


def test_sistema_sano_no_produce_avisos() -> None:
    """Estado de victoria: la lista vacía es lo que permite al panel decir "todo en orden".

    Si aquí apareciera un aviso fantasma, el admin aprendería a ignorar la lista entera.
    """
    actions = build_pending_actions(content=_content(), knowledge=_knowledge(), health=_health())
    assert actions == []


def test_instalacion_recien_hecha_avisa_de_lo_critico() -> None:
    actions = build_pending_actions(
        content=_content(published=0),
        knowledge=_knowledge(),
        health=_health(credentials_active=0, has_default=False, configs_active=0),
    )
    codes = {action.code for action in actions}
    assert PendingActionCode.no_provider_credential in codes
    assert PendingActionCode.no_active_agent_config in codes
    assert PendingActionCode.no_published_machine in codes

    critical = next(a for a in actions if a.code == PendingActionCode.no_provider_credential)
    assert critical.severity == ActionSeverity.critical
    assert critical.resource == "agent/providers"


def test_avisos_ordenados_por_severidad_descendente() -> None:
    """Lo crítico primero: el orden de la lista es la única priorización que ve el admin."""
    actions = build_pending_actions(
        content=_content(orphans=2),
        knowledge=_knowledge(failed=1),
        health=_health(never_checked=1, failed_documents=1, tools_total=2, tools_active=0),
    )
    severities = [action.severity for action in actions]
    order = {ActionSeverity.critical: 0, ActionSeverity.warning: 1, ActionSeverity.info: 2}
    assert severities == sorted(severities, key=lambda s: order[s])
    assert severities[0] == ActionSeverity.critical


def test_documento_encallado_gana_al_simplemente_pendiente() -> None:
    """Un documento colgado 30 minutos es un worker caído; uno pendiente es solo una cola.

    Reportar los dos a la vez para el mismo documento duplicaría el aviso.
    """
    stuck = build_pending_actions(
        content=_content(),
        knowledge=_knowledge(pending=1),
        health=_health(stuck_documents=1),
    )
    codes = {action.code for action in stuck}
    assert PendingActionCode.knowledge_documents_stuck in codes
    assert PendingActionCode.knowledge_documents_pending not in codes


def test_cada_aviso_lleva_ruta_para_arreglarlo() -> None:
    """Un aviso sin acción detrás es ruido. Todos deben apuntar a una pantalla del panel."""
    actions = build_pending_actions(
        content=_content(published=0, orphans=1, failed_videos=1),
        knowledge=_knowledge(failed=1, pending=1),
        health=_health(
            credentials_active=0,
            has_default=False,
            configs_active=0,
            never_checked=1,
            tools_total=1,
            stuck_videos=1,
            stuck_documents=1,
            failed_videos=1,
            failed_documents=1,
        ),
    )
    assert actions, "el escenario debería producir avisos"
    assert all(action.resource for action in actions)
    assert all(action.message.strip() for action in actions)


if __name__ == "__main__":
    import sys

    failures = 0
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            try:
                function()
                print(f"  [OK] {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  [FALLO] {name}: {exc}")
    print(f"\n{'TODO OK' if not failures else f'{failures} fallos'}")
    sys.exit(1 if failures else 0)
