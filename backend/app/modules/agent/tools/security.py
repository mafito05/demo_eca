"""Controles de seguridad para las tools HTTP dinámicas (D-007).

Permitir que un administrador registre una URL arbitraria que el backend invoca es
literalmente SSRF como funcionalidad. Y encima el que decide *cuándo* invocarla es un
LLM, influenciable por el texto que escribe el usuario final.

Capas de defensa:

1. Allowlist de hosts. Vacía = ninguna tool externa puede ejecutarse (fail-closed).
2. HTTPS obligatorio fuera de desarrollo.
3. Resolución DNS previa y rechazo de IPs privadas, loopback, link-local y del endpoint
   de metadatos de cloud (169.254.169.254) — el objetivo clásico para robar credenciales
   de instancia.
4. Sin redirecciones automáticas: un 302 hacia 127.0.0.1 saltaría las validaciones.
5. Timeout y tamaño máximo de respuesta: una tool no debe poder colgar el worker ni
   inundar la ventana de contexto del LLM.

La validación se aplica **en cada invocación**, no solo al registrar la tool: la
allowlist puede cambiar después, y el DNS del host también.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import settings

# Endpoints de metadatos de los principales cloud providers.
BLOCKED_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}
BLOCKED_IPS = {ipaddress.ip_address("169.254.169.254")}


class ToolSecurityError(RuntimeError):
    """La invocación se bloquea por política. El mensaje se devuelve al LLM como
    resultado de la tool, para que reformule o desista, y se registra en auditoría."""


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip in BLOCKED_IPS
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_url(url: str) -> str:
    """Valida una URL de destino. Devuelve el host o lanza `ToolSecurityError`."""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ToolSecurityError(f"Scheme not allowed: '{parsed.scheme}'. Only http/https.")

    if parsed.scheme == "http" and settings.is_production:
        raise ToolSecurityError("Only HTTPS destinations are allowed in production.")

    host = parsed.hostname
    if not host:
        raise ToolSecurityError("The URL has no host.")

    host = host.lower()

    if host in BLOCKED_HOSTS:
        raise ToolSecurityError(f"Host blocked by policy: {host}")

    allowed = {h.lower() for h in settings.TOOL_ALLOWED_HOSTS}
    if not allowed:
        raise ToolSecurityError(
            "No authorised hosts (TOOL_ALLOWED_HOSTS is empty). A superadmin must authorise "
            "the domain before external tools can be used."
        )

    # Coincidencia exacta o subdominio de una entrada autorizada. `.` explícito para que
    # `evil-example.com` no pase por autorizar `example.com`.
    if not any(host == entry or host.endswith(f".{entry}") for entry in allowed):
        raise ToolSecurityError(f"Host not authorised: {host}. Add it to TOOL_ALLOWED_HOSTS.")

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ToolSecurityError(f"Could not resolve host {host}.") from exc

    for *_, sockaddr in resolved:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_disallowed_ip(ip):
            raise ToolSecurityError(
                f"Host {host} resolves to an internal address ({ip}); call blocked."
            )

    return host


def truncate_response(text: str) -> str:
    """Recorta la respuesta al límite configurado.

    Una tool que devuelve 5 MB de JSON reventaría la ventana de contexto y el coste del
    request. Se avisa al LLM del recorte para que no asuma que vio todo.
    """
    limit = settings.TOOL_MAX_RESPONSE_BYTES
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text
    clipped = encoded[:limit].decode("utf-8", errors="ignore")
    return f"{clipped}\n\n[...response truncated at {limit} bytes...]"
