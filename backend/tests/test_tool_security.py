"""Tests de la defensa SSRF de las tools HTTP dinámicas (D-007).

Es el módulo más peligroso del sistema: el admin registra URLs arbitrarias y el que decide
cuándo invocarlas es un LLM influenciable por el texto del usuario. Estos casos son los que
un atacante probaría primero.

Compatible con pytest, y ejecutable sin él:

    docker compose exec backend python -m tests.test_tool_security
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.modules.agent.tools.security import ToolSecurityError, truncate_response, validate_url

# Casos que DEBEN bloquearse, incluso con el host en la allowlist.
BLOCKED_CASES = [
    ("http://localhost:8000/admin", "loopback, aunque 'localhost' esté autorizado"),
    ("http://127.0.0.1/admin", "loopback por IP"),
    ("http://169.254.169.254/latest/meta-data/", "endpoint de metadatos de cloud"),
    ("https://metadata.google.internal/computeMetadata/v1/", "metadatos de GCP por nombre"),
    ("http://10.0.0.5/internal", "rango privado 10/8"),
    ("http://192.168.1.1/router", "rango privado 192.168/16"),
    ("file:///etc/passwd", "esquema no HTTP"),
    ("gopher://api.github.com/x", "esquema exótico"),
    ("https://api.github.com.attacker.net/x", "sufijo engañoso sobre un host autorizado"),
    ("https://notgithub.com/x", "host fuera de la allowlist"),
]

ALLOWED_CASES = [
    "https://api.github.com/repos/demo/demo",
    "https://api.github.com/",
]


@pytest.fixture(autouse=True)
def _allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allowlist deliberadamente permisiva, incluido `localhost`.

    Autorizar `localhost` es justo lo que un administrador despistado haría, y el test
    comprueba que la resolución de IP lo bloquea de todas formas: la allowlist es la primera
    capa, no la única.
    """
    monkeypatch.setattr(
        settings,
        "TOOL_ALLOWED_HOSTS",
        [
            "api.github.com",
            "localhost",
            "metadata.google.internal",
            "10.0.0.5",
            "192.168.1.1",
            "169.254.169.254",
        ],
    )


@pytest.mark.parametrize(("url", "reason"), BLOCKED_CASES)
def test_blocked(url: str, reason: str) -> None:
    with pytest.raises(ToolSecurityError):
        validate_url(url)


@pytest.mark.parametrize("url", ALLOWED_CASES)
def test_allowed(url: str) -> None:
    assert validate_url(url) == "api.github.com"


def test_empty_allowlist_blocks_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed: sin allowlist configurada no se ejecuta ninguna tool."""
    monkeypatch.setattr(settings, "TOOL_ALLOWED_HOSTS", [])
    with pytest.raises(ToolSecurityError):
        validate_url("https://api.github.com/x")


def test_response_truncation() -> None:
    """Una tool no debe poder inundar la ventana de contexto del LLM."""
    original = settings.TOOL_MAX_RESPONSE_BYTES
    try:
        settings.TOOL_MAX_RESPONSE_BYTES = 100
        result = truncate_response("x" * 5000)
        assert "truncated" in result
        assert len(result) < 300
        assert truncate_response("corto") == "corto"
    finally:
        settings.TOOL_MAX_RESPONSE_BYTES = original


# --- Ejecución sin pytest ----------------------------------------------------
if __name__ == "__main__":
    settings.TOOL_ALLOWED_HOSTS = [
        "api.github.com",
        "localhost",
        "metadata.google.internal",
        "10.0.0.5",
        "192.168.1.1",
        "169.254.169.254",
    ]
    problems = 0

    print("Casos que deben BLOQUEARSE (con el host en la allowlist):")
    for url, reason in BLOCKED_CASES:
        try:
            host = validate_url(url)
            print(f"  [FALLO] PERMITIÓ {reason}  ->  host={host}  url={url}")
            problems += 1
        except ToolSecurityError as exc:
            print(f"  [OK]    bloqueó {reason}: {str(exc)[:64]}")

    print("\nCasos que deben PERMITIRSE:")
    for url in ALLOWED_CASES:
        try:
            print(f"  [OK]    permitió {url} -> {validate_url(url)}")
        except ToolSecurityError as exc:
            print(f"  [FALLO] BLOQUEÓ un destino legítimo {url}: {exc}")
            problems += 1

    print("\nFail-closed con allowlist vacía:")
    settings.TOOL_ALLOWED_HOSTS = []
    try:
        validate_url("https://api.github.com/x")
        print("  [FALLO] permitió una tool sin allowlist configurada")
        problems += 1
    except ToolSecurityError:
        print("  [OK]    ninguna tool se ejecuta sin allowlist")

    print("\nTruncado de respuesta:")
    original = settings.TOOL_MAX_RESPONSE_BYTES
    settings.TOOL_MAX_RESPONSE_BYTES = 100
    truncated = truncate_response("x" * 5000)
    if "truncated" in truncated and len(truncated) < 300:
        print(f"  [OK]    5000 caracteres recortados a {len(truncated)}")
    else:
        print("  [FALLO] no truncó la respuesta")
        problems += 1
    settings.TOOL_MAX_RESPONSE_BYTES = original

    print(f"\n{'TODO OK' if problems == 0 else str(problems) + ' PROBLEMAS'}")
    raise SystemExit(1 if problems else 0)
