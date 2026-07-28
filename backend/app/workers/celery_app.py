"""Configuración de Celery.

Colas separadas (D-009): `video` para transcodificación (minutos de CPU) e `ingest` para
vectorización (segundos, limitado por la API de embeddings). Con una sola cola, indexar un
manual quedaría esperando detrás de un video largo.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

# Imprescindible, y no es un import decorativo: el worker es un proceso independiente del
# API, así que tiene que registrar TODAS las tablas en el metadata de SQLModel por su cuenta.
# Importar solo los modelos que usa una tarea deja las claves ajenas sin resolver y el primer
# commit falla con `NoReferencedTableError: could not find table 'machine_models'`.
# Regla del proyecto: todo punto de entrada que toque la base de datos importa `app.models`.
from app.models import *  # noqa: F403

celery_app = Celery(
    "demoeca",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks.video", "app.workers.tasks.ingest"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Ack tardío: si el worker muere a mitad de transcodificar, la tarea vuelve a la cola
    # en lugar de perderse silenciosamente.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Un video de 1 h puede tardar bastante; el hard limit evita procesos zombis.
    task_soft_time_limit=60 * 50,
    task_time_limit=60 * 60,
    task_routes={
        "app.workers.tasks.video.*": {"queue": "video"},
        "app.workers.tasks.ingest.*": {"queue": "ingest"},
    },
)
