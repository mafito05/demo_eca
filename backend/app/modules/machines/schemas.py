"""Schemas de las imágenes de producto.

Fichero aparte y no inline en el router —a diferencia del resto de schemas de este módulo—
porque `lms/schemas.py` necesita `MachineImageRead` para el árbol de autoría. Importarlo desde
el router arrastraría el `APIRouter` y sus dependencias dentro del módulo de schemas del LMS.
Aquí no hay ciclo: este fichero no importa nada de `lms`.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.machines.models import MachineImageRole


class MachineImageRead(BaseModel):
    id: uuid.UUID
    # URL pública absoluta, ya compuesta. El cliente no debe construirla: el host depende del
    # entorno y el bucket es un detalle del servidor.
    url: str
    role: MachineImageRole
    order_index: int
    alt_text: str | None
    content_type: str
    size_bytes: int | None
    is_ready: bool


class MachineImageUploadRequest(BaseModel):
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=64)
    size_bytes: int | None = Field(default=None, ge=1)
    role: MachineImageRole = MachineImageRole.gallery
    alt_text: str | None = Field(default=None, max_length=255)


class MachineImageUploadTicket(BaseModel):
    image_id: uuid.UUID
    upload_url: str
    object_key: str
    # Se devuelve ya: en cuanto el PUT responde, el panel puede pintar la imagen sin esperar a
    # que el `confirm` le conteste.
    public_url: str
    expires_in_seconds: int
    # El PUT DEBE mandar este `Content-Type`. MinIO guarda el que reciba, y `confirm` compara
    # contra la allowlist usando lo que quedó almacenado, no lo que se declaró al pedir la URL.
    required_content_type: str


class MachineImageUpdate(BaseModel):
    """`extra="forbid"` como el resto de PATCH del repo: un campo mal escrito es un 422, no un
    cambio que se descarta en silencio."""

    model_config = ConfigDict(extra="forbid")

    alt_text: str | None = Field(default=None, max_length=255)
    order_index: int | None = Field(default=None, ge=0)
    role: MachineImageRole | None = None
