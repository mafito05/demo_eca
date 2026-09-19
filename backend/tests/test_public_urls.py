"""Tests de la URL pública de las imágenes de producto (D-058).

Esta función es pequeña pero tiene tres formas conocidas de salir mal, y las tres se
manifiestan igual de cara al usuario: una foto rota en el catálogo, sin ningún error en los
logs del backend.

  1. Componer contra `MINIO_ENDPOINT` en lugar del público. Dentro de Docker el backend habla
     con `minio:9000`; esa URL la resuelve él y **no** el navegador ni el móvil. Es el mismo
     fallo que D-018 y D-032, que ya costó una tarde con el video.
  2. Equivocar el esquema. Detrás de un proxy HTTPS, una URL `http://` es contenido mixto y el
     navegador la bloquea en silencio: la imagen no aparece y la consola no dice nada útil.
  3. No escapar la clave, o escapar de más y cargarse las barras de la jerarquía.

Compatible con pytest, y ejecutable sin él:

    docker compose exec backend python -m tests.test_public_urls
"""

from __future__ import annotations

import pytest

from app.core import storage
from app.core.config import settings


@pytest.fixture
def minio_settings():
    """Restaura los settings tocados. `Settings` es un singleton cacheado con `lru_cache`,
    así que se parchea el objeto y no el entorno: cambiar la variable no tendría efecto."""
    original = (
        settings.MINIO_PUBLIC_ENDPOINT,
        settings.MINIO_ENDPOINT,
        settings.MINIO_SECURE,
        settings.MINIO_BUCKET_PUBLIC,
    )
    yield settings
    (
        settings.MINIO_PUBLIC_ENDPOINT,
        settings.MINIO_ENDPOINT,
        settings.MINIO_SECURE,
        settings.MINIO_BUCKET_PUBLIC,
    ) = original


def test_usa_el_endpoint_publico_y_no_el_interno(minio_settings):
    minio_settings.MINIO_ENDPOINT = "minio:9000"
    minio_settings.MINIO_PUBLIC_ENDPOINT = "72.60.112.93:9000"
    minio_settings.MINIO_SECURE = False

    url = storage.public_url("machines/abc/def.png")

    assert url == "http://72.60.112.93:9000/demoeca-public/machines/abc/def.png"
    assert "minio:9000" not in url


def test_cae_al_endpoint_interno_si_no_hay_publico(minio_settings):
    """`minio_public_endpoint` es `MINIO_PUBLIC_ENDPOINT or MINIO_ENDPOINT`. En desarrollo, con
    todo en localhost, esa caída es correcta."""
    minio_settings.MINIO_ENDPOINT = "localhost:9000"
    minio_settings.MINIO_PUBLIC_ENDPOINT = ""

    assert storage.public_url("k.png").startswith("http://localhost:9000/")


def test_esquema_https_cuando_minio_es_seguro(minio_settings):
    minio_settings.MINIO_PUBLIC_ENDPOINT = "media.example.com"
    minio_settings.MINIO_SECURE = True

    assert storage.public_url("k.png").startswith("https://media.example.com/")


def test_conserva_las_barras_y_escapa_lo_demas(minio_settings):
    """La jerarquía de la clave tiene que sobrevivir; un espacio, no.

    Las claves las genera el backend (`machines/{uuid}/{uuid}.ext`), así que hoy nunca traen
    caracteres raros. El escapado está para que siga siendo verdad si mañana alguien decide
    usar el nombre de fichero original en la clave.
    """
    minio_settings.MINIO_PUBLIC_ENDPOINT = "host:9000"
    minio_settings.MINIO_SECURE = False

    url = storage.public_url("machines/a b/c.png")

    assert url.endswith("/demoeca-public/machines/a%20b/c.png")
    assert url.count("/demoeca-public/") == 1


def test_permite_forzar_otro_bucket(minio_settings):
    minio_settings.MINIO_PUBLIC_ENDPOINT = "host:9000"
    minio_settings.MINIO_SECURE = False

    assert storage.public_url("k.png", bucket="otro").endswith("/otro/k.png")


if __name__ == "__main__":  # pragma: no cover
    problems = 0
    saved = (
        settings.MINIO_PUBLIC_ENDPOINT,
        settings.MINIO_ENDPOINT,
        settings.MINIO_SECURE,
    )

    settings.MINIO_ENDPOINT = "minio:9000"
    settings.MINIO_PUBLIC_ENDPOINT = "72.60.112.93:9000"
    settings.MINIO_SECURE = False

    casos = [
        ("host público", storage.public_url("machines/a/b.png"),
         "http://72.60.112.93:9000/demoeca-public/machines/a/b.png"),
        ("barras conservadas", storage.public_url("a/b/c.png"),
         "http://72.60.112.93:9000/demoeca-public/a/b/c.png"),
        ("espacio escapado", storage.public_url("a b.png"),
         "http://72.60.112.93:9000/demoeca-public/a%20b.png"),
    ]
    for nombre, obtenido, esperado in casos:
        if obtenido == esperado:
            print(f"  [OK]    {nombre}")
        else:
            print(f"  [FALLO] {nombre}: {obtenido} != {esperado}")
            problems += 1

    settings.MINIO_SECURE = True
    if storage.public_url("k.png").startswith("https://"):
        print("  [OK]    esquema https con MINIO_SECURE")
    else:
        print("  [FALLO] no cambió a https con MINIO_SECURE")
        problems += 1

    (settings.MINIO_PUBLIC_ENDPOINT, settings.MINIO_ENDPOINT, settings.MINIO_SECURE) = saved
    print(f"\n{'TODO OK' if problems == 0 else str(problems) + ' PROBLEMAS'}")
    raise SystemExit(1 if problems else 0)
