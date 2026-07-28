"""Generación de códigos QR y enlaces profundos.

El QR codifica una **URL https del dominio de la compañía**, no el esquema propio
`demoeca://`. Razón: si el usuario no tiene la app instalada, un esquema propio no abre
nada (queda un QR muerto pegado en una máquina de 200.000 €), mientras que la URL https
cae en una landing web que ofrece descargar la app. Con App Links / Universal Links
correctamente configurados, esa misma URL abre la app directamente cuando sí está
instalada.
"""

from __future__ import annotations

import io

import qrcode
from qrcode.image.svg import SvgPathImage

from app.core.config import settings
from app.modules.machines.models import MachineModel


def deeplink_url(qr_token: str) -> str:
    """URL que se imprime en el QR y que resuelve la app vía App Links / Universal Links."""
    return f"https://{settings.DEEPLINK_DOMAIN}/m/{qr_token}"


def custom_scheme_url(qr_token: str) -> str:
    """Esquema propio, para pruebas y como fallback en Android sin verificación de dominio."""
    return f"{settings.DEEPLINK_SCHEME}://machine/{qr_token}"


def _build(qr_token: str, *, box_size: int, border: int):
    qr = qrcode.QRCode(
        version=None,  # tamaño automático según el contenido
        # Corrección de errores alta: estos códigos se pegan sobre equipos que se limpian
        # con desinfectantes y se rozan. Un QR con nivel L deja de leerse con poco desgaste.
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(deeplink_url(qr_token))
    qr.make(fit=True)
    return qr


def png_bytes(qr_token: str, *, box_size: int = 12, border: int = 4) -> bytes:
    """PNG para imprimir. box_size 12 da ~400 px, suficiente para una etiqueta de 5 cm."""
    buffer = io.BytesIO()
    _build(qr_token, box_size=box_size, border=border).make_image(
        fill_color="black", back_color="white"
    ).save(buffer, format="PNG")
    return buffer.getvalue()


def svg_bytes(qr_token: str, *, box_size: int = 12, border: int = 4) -> bytes:
    """SVG vectorial: es lo que pide una imprenta para etiquetas de cualquier tamaño."""
    buffer = io.BytesIO()
    _build(qr_token, box_size=box_size, border=border).make_image(image_factory=SvgPathImage).save(
        buffer
    )
    return buffer.getvalue()


def export_payload(machine: MachineModel) -> dict:
    """Datos en texto plano para exportar a otros softwares de la compañía.

    Requisito explícito del documento de arquitectura: el QR debe poder integrarse en
    sistemas terceros (etiquetado, ERP, inventario) sin depender de nuestra imagen.
    """
    return {
        "machine_code": machine.code,
        "machine_name": machine.name,
        "specialty": machine.specialty.value,
        "qr_token": machine.qr_token,
        "qr_url": deeplink_url(machine.qr_token),
        "qr_custom_scheme": custom_scheme_url(machine.qr_token),
        "png_endpoint": f"{settings.API_V1_PREFIX}/machines/{machine.id}/qr.png",
        "svg_endpoint": f"{settings.API_V1_PREFIX}/machines/{machine.id}/qr.svg",
    }
