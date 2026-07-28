"""Endpoints de estadísticas para el dashboard del panel.

La dependencia de autorización va **a nivel de router**, no repetida por endpoint. Es una
divergencia deliberada respecto a `lms/router.py` y `agent/router.py`: allí conviven autoría
(backoffice), consumo (cualquier usuario) y streaming de HLS, así que el permiso *tiene* que
verse endpoint por endpoint. Aquí el módulo entero es backoffice al 100 %, y declararlo una vez
consigue que un endpoint futuro no pueda quedar sin proteger por olvido — fail-closed por
construcción. No se pone en `main.py` porque allí el lector espera montaje, no política.

**Sin `try/except` que degrade la respuesta.** La tentación es clara: que la sección que falle
vaya a `null` y el resto se pinte. Hay que rechazarla, porque si una consulta de estadísticas
falla es un bug de código o de esquema, y degradarlo en silencio produce un dashboard que
*miente*, que es el peor resultado posible para un dashboard.

**Sin caché.** El uso real es "publico una máquina y voy al dashboard a comprobarlo"; un TTL de
60 s convierte eso en "acabo de publicarla, ¿por qué sigue en borrador?". Se gastan unos
milisegundos y se gana un bug de percepción. El smoke test asserta que el endpoint responde en
menos de 2 s, que es lo que detecta el N+1 que alguien introducirá algún día — y lo detecta
*antes* de que una caché lo esconda.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import SessionDep, require_backoffice
from app.modules.stats import service
from app.modules.stats.schemas import AgentActivityStats, StatsOverview

router = APIRouter(dependencies=[Depends(require_backoffice)])

# El tope de 90 días acota el coste: sin él, `?days=100000` es un escaneo completo de la tabla
# de mensajes y una lista de 100 000 elementos serializada a JSON.
DaysQuery = Annotated[
    int,
    Query(
        ge=1, le=90, description="Size of the reporting window in days, counted back from today."
    ),
]


@router.get(
    "/overview",
    response_model=StatsOverview,
    summary="Aggregated metrics for the admin dashboard",
)
async def overview(session: SessionDep, days: DaysQuery = 30) -> StatsOverview:
    """Todas las secciones del dashboard en una sola llamada.

    Un único endpoint y no seis porque el panel pinta una sola pantalla: seis endpoints serían
    seis estados de carga y seis manejadores de error para un dashboard que abren una o dos
    personas. Y da **coherencia temporal**: las consultas comparten sesión y ventana, así que dos
    secciones no pueden discrepar por haberse pedido a caballo de la medianoche.
    """
    return await service.build_overview(session, days=days)


@router.get(
    "/agent-activity",
    response_model=AgentActivityStats,
    summary="Agent usage time series and latency percentiles",
)
async def agent_activity(session: SessionDep, days: DaysQuery = 30) -> AgentActivityStats:
    """La serie temporal por separado.

    Única excepción al endpoint monolítico, y está justificada: es el único dato que el usuario
    va a re-pedir con otro rango. Reutiliza el mismo builder, así que cambiar el selector de
    7/30/90 días no relanza las 17 consultas del overview.
    """
    window_start, start_day, today = service.window_bounds(days)
    return await service.build_agent_activity(
        session, days=days, window_start=window_start, start_day=start_day, today=today
    )
