"""Prueba end-to-end del pipeline de video: subida -> HLS -> reproducción firmada.

Sube un `.mp4` con URL prefirmada exactamente como haría el panel Angular, encola la
transcodificación y valida el resultado imitando lo que hace un reproductor HLS: pedir la
playlist maestra, seguir a la de variante y descargar un segmento. Comprueba además los casos
negativos: sin token, con token de otro video y con rutas de segmento maliciosas.

**Se ejecuta desde el host**, no desde un contenedor. El motivo es el propio asunto que se
está probando: las URLs prefirmadas se firman contra `MINIO_PUBLIC_ENDPOINT`
(`localhost:9000`), que es lo que resuelven el navegador y el móvil pero no un contenedor
—dentro de un contenedor, `localhost` es el contenedor—. Probarlo desde dentro exigiría
falsear ese endpoint y entonces no se estaría probando nada.

    # 1. Generar el mp4 de prueba (ffmpeg vive en el worker):
    docker compose exec worker python -m scripts.test_video_pipeline --make-source
    # 2. Ejecutar la prueba desde el host:
    python backend/scripts/test_video_pipeline.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx

BASE = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")
API = f"{BASE}/api/v1"
ADMIN = ("superadmin@demoeca.example.com", "Demo1234!")

# Directorio compartido por bind mount entre el host y los contenedores (./backend:/app), que
# es cómo el mp4 generado en el worker llega al host sin copiarlo a mano.
SOURCE_PATH = Path(__file__).resolve().parent.parent / ".tmp_media" / "test.mp4"

passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    (passed if condition else failed).append(name)
    print(f"  [{'OK' if condition else 'FALLO'}] {name}" + (f" — {detail}" if detail else ""))
    return condition


def make_test_video(path: Path, seconds: int = 12) -> None:
    """Genera un mp4 sintético: patrón de barras con un contador de tiempo y un tono.

    Se generan 12 segundos para que con `hls_time=6` salgan al menos 2 segmentos y la playlist
    tenga algo que encadenar; con un solo segmento no se probaría nada del troceado.
    """
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={seconds}:size=1280x720:rate=25",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    subprocess.run(command, capture_output=True, check=True, timeout=180)


async def main() -> int:
    source = SOURCE_PATH

    print("=== 1. Fichero de origen ===")
    if not source.exists():
        print(f"  No existe {source}.")
        print("  Generarlo primero (ffmpeg vive en el worker):")
        print("  docker compose exec worker python -m scripts.test_video_pipeline --make-source")
        return 1
    check(
        "mp4 de origen disponible", source.stat().st_size > 10_000, f"{source.stat().st_size} bytes"
    )

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=False) as client:
        login = await client.post(
            f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]}
        )
        if login.status_code != 200:
            print(f"  No se pudo autenticar: HTTP {login.status_code}")
            return 1
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        print("\n=== 2. Subida directa a MinIO con URL prefirmada (D-010) ===")
        ticket = await client.post(
            f"{API}/lms/videos/upload-url",
            headers=headers,
            json={"filename": "leccion-demo.mp4", "size_bytes": source.stat().st_size},
        )
        if not check(
            "ticket de subida emitido",
            ticket.status_code == 200,
            f"HTTP {ticket.status_code} {ticket.text[:160]}",
        ):
            return 1
        ticket_data = ticket.json()
        asset_id = ticket_data["video_asset_id"]
        print(f"         object_key: {ticket_data['object_key']}")

        # La subida NO pasa por el API: va directa al almacenamiento.
        upload = await client.put(
            ticket_data["upload_url"],
            content=source.read_bytes(),
            headers={"Content-Type": "video/mp4"},
        )
        check(
            "subida directa a MinIO", upload.status_code in (200, 204), f"HTTP {upload.status_code}"
        )

        print("\n=== 3. Transcodificación a HLS en el worker ===")
        process = await client.post(f"{API}/lms/videos/{asset_id}/process", headers=headers)
        check(
            "transcodificación encolada",
            process.status_code == 202,
            f"HTTP {process.status_code} {process.text[:200]}",
        )

        asset: dict = {}
        for attempt in range(40):
            await asyncio.sleep(3)
            response = await client.get(f"{API}/lms/videos/{asset_id}", headers=headers)
            asset = response.json()
            print(f"         intento {attempt + 1}: {asset['status']}")
            if asset["status"] in ("ready", "failed"):
                break

        if not check(
            "video en estado ready",
            asset.get("status") == "ready",
            asset.get("error_message") or "",
        ):
            return 1
        check(
            "duración detectada por ffprobe",
            (asset.get("duration_seconds") or 0) > 10,
            f"{asset.get('duration_seconds')} s",
        )
        check(
            "renditions generadas",
            len(asset.get("renditions", [])) == 2,
            ", ".join(r["name"] for r in asset.get("renditions", [])),
        )

        print("\n=== 4. Reproducción: lo que hace un reproductor HLS ===")
        master = await client.get(f"{API}/lms/videos/{asset_id}/hls/master.m3u8", headers=headers)
        if not check(
            "playlist maestra servida", master.status_code == 200, f"HTTP {master.status_code}"
        ):
            return 1
        check(
            "content-type correcto para HLS",
            "mpegurl" in master.headers.get("content-type", ""),
            master.headers.get("content-type", ""),
        )
        check("no cacheable (contiene un token)", master.headers.get("cache-control") == "no-store")

        master_body = master.text
        variant_lines = [ln for ln in master_body.splitlines() if ln and not ln.startswith("#")]
        check(
            "URIs de variante reescritas y firmadas",
            all("token=" in ln and "/hls/" in ln for ln in variant_lines)
            and len(variant_lines) == 2,
            f"{len(variant_lines)} variantes",
        )

        # El reproductor sigue la primera variante tal cual viene en la playlist.
        variant_url = variant_lines[0]
        variant = await client.get(f"{BASE}{variant_url}")
        if not check(
            "playlist de variante accesible con el token",
            variant.status_code == 200,
            f"HTTP {variant.status_code}",
        ):
            return 1

        segment_lines = [ln for ln in variant.text.splitlines() if ln and not ln.startswith("#")]
        check(
            "segmentos reescritos y firmados",
            len(segment_lines) >= 2 and all("token=" in ln for ln in segment_lines),
            f"{len(segment_lines)} segmentos",
        )

        segment_url = segment_lines[0]
        redirect = await client.get(f"{BASE}{segment_url}")
        check(
            "segmento responde 307 hacia MinIO (los bytes no pasan por el API)",
            redirect.status_code == 307,
            f"HTTP {redirect.status_code}",
        )

        location = redirect.headers.get("location", "")
        check(
            "la URL prefirmada apunta al host público, no a `minio:`",
            location.startswith("http") and "minio:9000" not in location,
            location.split("?")[0],
        )

        # Descarga real del segmento: comprueba que la firma valida y que hay bytes de video.
        async with httpx.AsyncClient(timeout=60.0) as plain:
            data = await plain.get(location)
        check(
            "el segmento se descarga y es un TS válido",
            data.status_code == 200 and len(data.content) > 1000 and data.content[0] == 0x47,
            f"HTTP {data.status_code}, {len(data.content)} bytes, sync byte=0x{data.content[0]:02x}"
            if data.status_code == 200
            else f"HTTP {data.status_code}",
        )

        print("\n=== 5. Casos negativos del proxy firmado ===")
        no_token = await client.get(f"{BASE}{variant_url.split('?')[0]}")
        check(
            "playlist de variante sin token -> 422",
            no_token.status_code == 422,
            f"HTTP {no_token.status_code}",
        )

        bad_token = await client.get(f"{BASE}{variant_url.split('?')[0]}?token=noesuntoken")
        check(
            "token inválido -> 403", bad_token.status_code == 403, f"HTTP {bad_token.status_code}"
        )

        # Token válido pero emitido para OTRO asset: el claim `asset` debe acotarlo.
        other_ticket = await client.post(
            f"{API}/lms/videos/upload-url", headers=headers, json={"filename": "otro.mp4"}
        )
        other_id = other_ticket.json()["video_asset_id"]
        real_token = variant_url.split("token=")[1]
        cross = await client.get(
            f"{API}/lms/videos/{other_id}/hls/v0/playlist.m3u8?token={real_token}"
        )
        check(
            "token de un video no sirve para otro",
            cross.status_code == 403,
            f"HTTP {cross.status_code}",
        )

        traversal = await client.get(
            f"{API}/lms/videos/{asset_id}/hls/v0/..%2f..%2f..%2fsource%2ftest.mp4?token={real_token}"
        )
        check(
            "path traversal en el segmento rechazado",
            traversal.status_code in (400, 404),
            f"HTTP {traversal.status_code}",
        )

        fake_variant = await client.get(
            f"{API}/lms/videos/{asset_id}/hls/v1080p/playlist.m3u8?token={real_token}"
        )
        check(
            "calidad no generada -> 404 (no un 500)",
            fake_variant.status_code == 404,
            f"HTTP {fake_variant.status_code}",
        )

        print("\n=== 6. Progreso y bloqueo por prerrequisito ===")
        demo = await client.post(f"{API}/auth/demo-login")
        demo_headers = {"Authorization": f"Bearer {demo.json()['access_token']}"}

        machines = await client.get(f"{API}/machines", headers=demo_headers)
        machine_id = machines.json()[0]["id"]

        path = await client.get(f"{API}/lms/machines/{machine_id}/path", headers=demo_headers)
        if not check(
            "ruta de aprendizaje construida",
            path.status_code == 200,
            f"HTTP {path.status_code} {path.text[:200]}",
        ):
            return 1
        path_data = path.json()
        print(
            f"         {path_data['machine_name']}: {path_data['total_lessons']} lecciones, "
            f"{path_data['progress_percent']}% completado"
        )

        modules = path_data["modules"]
        check(
            "segundo módulo bloqueado por prerrequisito",
            modules[1]["locked"] is True,
            f"módulo 2 locked={modules[1]['locked']}",
        )

        blocked_lesson = modules[1]["lessons"][0]["id"]
        blocked = await client.get(f"{API}/lms/lessons/{blocked_lesson}", headers=demo_headers)
        check(
            "el servidor rechaza la lección bloqueada -> 403",
            blocked.status_code == 403,
            f"HTTP {blocked.status_code}",
        )

        first_lesson = modules[0]["lessons"][0]["id"]
        progress = await client.put(
            f"{API}/lms/lessons/{first_lesson}/progress",
            headers=demo_headers,
            json={"position_seconds": 5.0},
        )
        check(
            "heartbeat de progreso aceptado",
            progress.status_code == 200,
            f"HTTP {progress.status_code} {progress.text[:160]}",
        )

        # Idempotencia: tres heartbeats no deben crear tres filas ni bajar el porcentaje.
        await client.put(
            f"{API}/lms/lessons/{first_lesson}/progress",
            headers=demo_headers,
            json={"position_seconds": 30.0},
        )
        rewind = await client.put(
            f"{API}/lms/lessons/{first_lesson}/progress",
            headers=demo_headers,
            json={"position_seconds": 1.0},
        )
        body = rewind.json()
        check(
            "rebobinar no reduce el progreso conseguido",
            body["watched_percent"] >= 100.0 or body["status"] == "completed",
            f"percent={body['watched_percent']} status={body['status']}",
        )

        print("\n=== 7. Progreso sobre un video real (cálculo de porcentaje) ===")
        # La lección anterior era de texto, que por diseño salta directamente al 100%: no
        # prueba el cálculo. Aquí se engancha el video transcodificado a una lección nueva y se
        # verifica el porcentaje contra la duración real de 12 s.
        module_id = modules[0]["id"]
        title = "Purging the coupling circuit (video)"

        # Idempotente: si el test ya se ejecutó antes, se reutiliza la lección y solo se
        # reapunta al nuevo asset. Crear una nueva en cada ejecución ensuciaría la ruta de
        # capacitación de la demo con lecciones duplicadas.
        already = next((les for les in modules[0]["lessons"] if les["title"] == title), None)
        if already:
            patched = await client.patch(
                f"{API}/lms/lessons/{already['id']}",
                headers=headers,
                json={"video_asset_id": asset_id},
            )
            ok_created = patched.status_code == 200
            video_lesson = already["id"]
            detalle = f"reutilizada (HTTP {patched.status_code})"
        else:
            created = await client.post(
                f"{API}/lms/lessons",
                headers=headers,
                json={
                    "training_module_id": module_id,
                    "title": title,
                    "content_type": "video",
                    "order_index": len(modules[0]["lessons"]) + 10,
                    "video_asset_id": asset_id,
                    "estimated_minutes": 1,
                    "status": "published",
                },
            )
            ok_created = created.status_code == 201
            video_lesson = created.json().get("id") if ok_created else None
            detalle = f"creada (HTTP {created.status_code}) {created.text[:120] if not ok_created else ''}"

        if not check("lección de video lista", ok_created and video_lesson, detalle):
            return 1

        # El progreso es por (usuario, lección) y `watched_percent` nunca baja —es la regla de
        # diseño—, así que la escalera de porcentajes solo es determinista sobre un par limpio.
        # Se crea un trainee de un solo uso en lugar de reutilizar el usuario demo, que ya
        # arrastra progreso de ejecuciones anteriores. Resetear el progreso desde la API no es
        # una opción: un usuario no debe poder borrar su propio historial de capacitación.
        qa_email = f"qa-video-{uuid.uuid4().hex[:8]}@demoeca.example.com"
        qa_user = await client.post(
            f"{API}/auth/users",
            headers=headers,
            json={
                "email": qa_email,
                "full_name": "QA Pipeline de Video",
                "password": "QaDemo1234!",
                "role": "trainee",
            },
        )
        if not check(
            "trainee de un solo uso creado",
            qa_user.status_code == 201,
            f"HTTP {qa_user.status_code} {qa_user.text[:160]}",
        ):
            return 1
        qa_login = await client.post(
            f"{API}/auth/login", json={"email": qa_email, "password": "QaDemo1234!"}
        )
        demo_headers = {"Authorization": f"Bearer {qa_login.json()['access_token']}"}

        detail = await client.get(f"{API}/lms/lessons/{video_lesson}", headers=demo_headers)
        detail_data = detail.json()
        check(
            "la lección expone su URL de HLS y su duración",
            detail.status_code == 200
            and detail_data.get("hls_master_url", "").endswith("master.m3u8")
            and detail_data.get("duration_seconds") == 12.0,
            f"duración={detail_data.get('duration_seconds')}",
        )

        quarter = await client.put(
            f"{API}/lms/lessons/{video_lesson}/progress",
            headers=demo_headers,
            json={"position_seconds": 3.0},
        )
        body = quarter.json()
        check(
            "3 s de 12 s -> 25% y sigue en curso",
            abs(body["watched_percent"] - 25.0) < 0.5 and body["status"] == "in_progress",
            f"percent={body['watched_percent']} status={body['status']}",
        )

        almost = await client.put(
            f"{API}/lms/lessons/{video_lesson}/progress",
            headers=demo_headers,
            json={"position_seconds": 11.5},
        )
        body = almost.json()
        completed_at = body["completed_at"]
        check(
            "11,5 s de 12 s -> supera el umbral y se completa",
            body["watched_percent"] > 90 and body["status"] == "completed" and completed_at,
            f"percent={round(body['watched_percent'], 1)} status={body['status']}",
        )

        back = await client.put(
            f"{API}/lms/lessons/{video_lesson}/progress",
            headers=demo_headers,
            json={"position_seconds": 2.0},
        )
        body = back.json()
        check(
            "rebobinar mantiene el máximo y no reabre la lección",
            body["watched_percent"] > 90 and body["status"] == "completed",
            f"percent={round(body['watched_percent'], 1)} status={body['status']}",
        )
        check(
            "completed_at se sella una sola vez (irá al certificado)",
            body["completed_at"] == completed_at,
            f"{body['completed_at']}",
        )
        check(
            "la posición sí retrocede (para reanudar donde se dejó)",
            body["last_position_seconds"] == 2.0,
            f"posición={body['last_position_seconds']}",
        )

        # El test limpia lo que creó: sin esto, cada ejecución dejaría un usuario más en la
        # base de datos de la demo.
        cleanup = await client.delete(f"{API}/auth/users/{qa_user.json()['id']}", headers=headers)
        check(
            "el trainee de un solo uso se elimina al terminar",
            cleanup.status_code == 204,
            f"HTTP {cleanup.status_code}",
        )

        gone = await client.post(
            f"{API}/auth/login", json={"email": qa_email, "password": "QaDemo1234!"}
        )
        check("y ya no puede autenticarse", gone.status_code == 401, f"HTTP {gone.status_code}")

    print("\n" + "=" * 70)
    print(f"PASAN: {len(passed)}   FALLAN: {len(failed)}")
    for name in failed:
        print(f"  - {name}")
    print("=" * 70)
    return 1 if failed else 0


if __name__ == "__main__":
    # `--make-source` se ejecuta dentro del worker, que es el contenedor que tiene ffmpeg.
    # El fichero cae en un directorio compartido por bind mount, así que aparece en el host.
    if "--make-source" in sys.argv:
        SOURCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        make_test_video(SOURCE_PATH)
        print(f"Generado {SOURCE_PATH} ({SOURCE_PATH.stat().st_size} bytes)")
        sys.exit(0)

    sys.exit(asyncio.run(main()))
