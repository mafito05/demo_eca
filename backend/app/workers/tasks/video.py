"""Transcodificación de video a HLS (cola `video`).

Genera un HLS multi-bitrate con playlist maestra, de modo que el reproductor de Flutter
cambie de calidad según el ancho de banda. Es el requisito clave del documento: evitar
cortes en la red móvil de un hospital.

Estructura resultante en MinIO:

    hls/{video_asset_id}/master.m3u8
    hls/{video_asset_id}/v360p/playlist.m3u8 + segment*.ts
    hls/{video_asset_id}/v720p/playlist.m3u8 + segment*.ts

Ojo con el nombre del directorio: ffmpeg sustituye `%v` por el **nombre** de la variante
cuando `var_stream_map` incluye `name:`, no por su índice. Es decir, `v%v` produce `v360p`, no
`v0`. Se descubrió porque la playlist maestra referenciaba `v360p/playlist.m3u8` mientras el
código asumía `v0/`. Toda la nomenclatura pasa ahora por `variant_dir()` para que no vuelva a
haber dos sitios con suposiciones distintas.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import utcnow
from app.core.config import settings
from app.core.storage import get_client, upload_bytes
from app.modules.lms.models import VideoAsset, VideoStatus
from app.workers.celery_app import celery_app
from app.workers.runtime import run_with_session

logger = logging.getLogger(__name__)

# Perfiles de salida. El bitrate de audio se mantiene igual en todas las variantes: cambiarlo
# obliga a más pistas de audio y complica el master sin beneficio perceptible.
RENDITION_PROFILES: dict[str, dict] = {
    "360p": {
        "width": 640,
        "height": 360,
        "video_bitrate": "800k",
        "maxrate": "856k",
        "bufsize": "1200k",
    },
    "720p": {
        "width": 1280,
        "height": 720,
        "video_bitrate": "2800k",
        "maxrate": "2996k",
        "bufsize": "4200k",
    },
    "1080p": {
        "width": 1920,
        "height": 1080,
        "video_bitrate": "5000k",
        "maxrate": "5350k",
        "bufsize": "7500k",
    },
}


def variant_dir(rendition_name: str) -> str:
    """Nombre del directorio de una variante. Única fuente de verdad de la nomenclatura.

    Debe coincidir con lo que ffmpeg genera al expandir `v%v` con `name:` en el
    `var_stream_map`, y con `VARIANT_RE` en `modules/lms/hls.py`.
    """
    return f"v{rendition_name}"


def active_renditions() -> list[str]:
    """Renditions configuradas que además tienen perfil definido, en orden."""
    return [name for name in settings.HLS_RENDITIONS if name in RENDITION_PROFILES]


def probe_duration(path: Path) -> float | None:
    """Duración en segundos vía ffprobe. Se usa para la barra de progreso y el % visto."""
    try:
        output = subprocess.run(
            [
                settings.FFMPEG_BINARY.replace("ffmpeg", "ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return float(json.loads(output.stdout)["format"]["duration"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffprobe no pudo leer la duración: %s", exc)
        return None


def build_ffmpeg_command(source: Path, output_dir: Path, renditions: list[str]) -> list[str]:
    """Construye el comando de ffmpeg para HLS multi-bitrate en una sola pasada.

    Una sola invocación con `split` y `var_stream_map` decodifica el origen una única vez.
    Ejecutar ffmpeg N veces (una por calidad) multiplicaría el tiempo de CPU casi por N.
    """
    profiles = [
        (name, RENDITION_PROFILES[name]) for name in renditions if name in RENDITION_PROFILES
    ]
    if not profiles:
        raise ValueError(f"Ninguna rendition válida en {renditions}.")

    count = len(profiles)
    split = f"[0:v]split={count}" + "".join(f"[v{i}]" for i in range(count))
    scales = ";".join(
        f"[v{i}]scale=w={p['width']}:h={p['height']}:force_original_aspect_ratio=decrease,"
        f"pad={p['width']}:{p['height']}:(ow-iw)/2:(oh-ih)/2[v{i}out]"
        for i, (_, p) in enumerate(profiles)
    )

    command = [
        settings.FFMPEG_BINARY,
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        f"{split};{scales}",
    ]

    for index, (_, profile) in enumerate(profiles):
        command += [
            "-map",
            f"[v{index}out]",
            f"-c:v:{index}",
            "libx264",
            f"-b:v:{index}",
            profile["video_bitrate"],
            f"-maxrate:v:{index}",
            profile["maxrate"],
            f"-bufsize:v:{index}",
            profile["bufsize"],
            "-preset",
            "veryfast",
            # Keyframes alineados con la duración del segmento: sin esto los cortes no caen
            # en frontera de GOP y el cambio de calidad da saltos visibles.
            f"-g:v:{index}",
            str(settings.HLS_SEGMENT_SECONDS * 25),
            f"-keyint_min:v:{index}",
            str(settings.HLS_SEGMENT_SECONDS * 25),
            "-sc_threshold",
            "0",
        ]

    for index in range(len(profiles)):
        command += ["-map", "a:0?", f"-c:a:{index}", "aac", f"-b:a:{index}", "128k", "-ac", "2"]

    var_stream_map = " ".join(f"v:{i},a:{i},name:{profiles[i][0]}" for i in range(len(profiles)))

    command += [
        "-f",
        "hls",
        "-hls_time",
        str(settings.HLS_SEGMENT_SECONDS),
        "-hls_playlist_type",
        "vod",
        "-hls_flags",
        "independent_segments",
        "-hls_segment_type",
        "mpegts",
        "-hls_segment_filename",
        str(output_dir / "v%v" / "segment%03d.ts"),
        "-master_pl_name",
        "master.m3u8",
        "-var_stream_map",
        var_stream_map,
        str(output_dir / "v%v" / "playlist.m3u8"),
    ]
    return command


@celery_app.task(
    name="app.workers.tasks.video.transcode_video_task",
    bind=True,
    max_retries=2,
    acks_late=True,
)
def transcode_video_task(self, video_asset_id: str) -> dict:
    """Descarga el original, transcodifica a HLS y sube el resultado a MinIO."""
    asset_uuid = uuid.UUID(video_asset_id)

    async def _mark(session: AsyncSession, **changes) -> VideoAsset | None:
        asset = await session.get(VideoAsset, asset_uuid)
        if asset is None:
            return None
        for key, value in changes.items():
            setattr(asset, key, value)
        session.add(asset)
        await session.commit()
        return asset

    asset = run_with_session(
        lambda s: _mark(s, status=VideoStatus.processing, processing_started_at=utcnow())
    )
    if asset is None:
        logger.error("VideoAsset %s no existe.", video_asset_id)
        return {"video_asset_id": video_asset_id, "error": "not_found"}

    workdir = Path(tempfile.mkdtemp(prefix=f"hls-{asset_uuid}-"))
    try:
        source = workdir / "source.mp4"
        client = get_client()
        # Descarga a disco por streaming: un video no cabe en memoria de forma fiable.
        client.fget_object(settings.MINIO_BUCKET_VIDEO, asset.source_key, str(source))

        duration = probe_duration(source)

        output_dir = workdir / "hls"
        renditions_used = active_renditions()
        # ffmpeg no crea los directorios de las variantes: hay que anticiparlos con el mismo
        # nombre que usará al expandir `%v`.
        for name in renditions_used:
            (output_dir / variant_dir(name)).mkdir(parents=True, exist_ok=True)

        command = build_ffmpeg_command(source, output_dir, renditions_used)
        logger.info("ffmpeg: %s", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            # ffmpeg escribe todo en stderr; se guardan las últimas líneas, que son las que
            # explican el fallo real.
            tail = "\n".join(result.stderr.strip().splitlines()[-15:])
            raise RuntimeError(f"ffmpeg falló (código {result.returncode}):\n{tail}")

        prefix = f"hls/{asset_uuid}"
        uploaded = 0
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(output_dir).as_posix()
            content_type = (
                "application/vnd.apple.mpegurl" if path.suffix == ".m3u8" else "video/mp2t"
            )
            with path.open("rb") as handle:
                upload_bytes(
                    settings.MINIO_BUCKET_VIDEO, f"{prefix}/{relative}", handle.read(), content_type
                )
            uploaded += 1

        renditions = [
            {
                "name": name,
                "playlist_key": f"{prefix}/{variant_dir(name)}/playlist.m3u8",
                "video_bitrate": RENDITION_PROFILES[name]["video_bitrate"],
                **{k: v for k, v in RENDITION_PROFILES[name].items() if k in ("width", "height")},
            }
            for name in renditions_used
        ]

        run_with_session(
            lambda s: _mark(
                s,
                status=VideoStatus.ready,
                hls_master_key=f"{prefix}/master.m3u8",
                renditions=renditions,
                duration_seconds=duration,
                processing_finished_at=utcnow(),
                error_message=None,
            )
        )
        logger.info("VideoAsset %s listo: %d ficheros subidos.", asset_uuid, uploaded)
        return {"video_asset_id": video_asset_id, "files": uploaded, "duration": duration}

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:2000]
        run_with_session(
            lambda s: _mark(
                s,
                status=VideoStatus.failed,
                error_message=message,
                processing_finished_at=utcnow(),
                attempts=(asset.attempts or 0) + 1,
            )
        )
        logger.exception("Fallo transcodificando %s", asset_uuid)
        raise

    finally:
        # El directorio temporal puede pesar varios GB; limpiarlo no es opcional.
        shutil.rmtree(workdir, ignore_errors=True)
