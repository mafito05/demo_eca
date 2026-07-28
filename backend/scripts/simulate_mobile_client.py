"""Simula al cliente móvil contra el backend, por la IP de la red local.

    python backend/scripts/simulate_mobile_client.py http://192.168.18.33:8000

Recorre exactamente la secuencia que ejecuta la app Flutter —bypass de demo, resolver el QR,
ruta de aprendizaje, lección, reproducción HLS, progreso y chat del agente— pero desde el host y
usando la IP de la LAN en lugar de `localhost`.

Por qué esto no lo cubre el smoke test: el smoke test corre **dentro** del contenedor y habla por
`localhost`, así que nunca detectaría el fallo más probable al usar un emulador o un teléfono —
que las URLs prefirmadas de MinIO se hayan firmado contra `localhost:9000`, un host que en el
dispositivo apunta al propio dispositivo. Aquí se comprueba explícitamente a qué host redirige
cada segmento de video.
"""

from __future__ import annotations

import asyncio
import json
import sys
from urllib.parse import urlparse

import httpx

passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    (passed if condition else failed).append(name)
    print(f"  [{'OK' if condition else 'FALLO'}] {name}" + (f" — {detail}" if detail else ""))
    return condition


async def main(base: str) -> int:
    api = f"{base}/api/v1"
    host = urlparse(base).hostname or ""

    print(f"Simulando la app contra {base}\n")

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        print("=== 1. Entrada por bypass de demo (lo que hace el botón Entrar) ===")
        login = await client.post(f"{api}/auth/demo-login")
        if not check("demo-login", login.status_code == 200, f"HTTP {login.status_code}"):
            return 1
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = await client.get(f"{api}/auth/me", headers=headers)
        check(
            "perfil del usuario demo",
            me.status_code == 200 and me.json()["role"] == "trainee",
            me.json().get("email", "") if me.status_code == 200 else f"HTTP {me.status_code}",
        )

        print("\n=== 2. Escaneo del QR ===")
        machines = await client.get(f"{api}/machines", headers=headers)
        if not check("catálogo accesible", machines.status_code == 200):
            return 1
        qr_token = machines.json()[0]["qr_token"]
        print(f"         token del QR: {qr_token}")

        resolved = await client.get(f"{api}/machines/resolve/{qr_token}", headers=headers)
        if not check("resolver el QR", resolved.status_code == 200, f"HTTP {resolved.status_code}"):
            return 1
        machine_id = resolved.json()["machine_model_id"]
        print(f"         {resolved.json()['name']}")

        print("\n=== 3. Ruta de capacitación ===")
        path = await client.get(f"{api}/lms/machines/{machine_id}/path", headers=headers)
        if not check("ruta de aprendizaje", path.status_code == 200, f"HTTP {path.status_code}"):
            return 1
        data = path.json()
        print(
            f"         {data['total_lessons']} lecciones · "
            f"{data['progress_percent']}% completado · {len(data['modules'])} módulos"
        )
        check(
            "el segundo módulo aparece bloqueado",
            len(data["modules"]) > 1 and data["modules"][1]["locked"],
            f"locked={data['modules'][1]['locked']}" if len(data["modules"]) > 1 else "",
        )

        video_lesson = next(
            (
                lesson
                for module in data["modules"]
                for lesson in module["lessons"]
                if lesson["has_video"] and lesson["video_ready"] and not module["locked"]
            ),
            None,
        )
        if not check("hay una lección de video accesible", video_lesson is not None):
            return 1

        print("\n=== 4. Lección y reproducción HLS ===")
        lesson = await client.get(f"{api}/lms/lessons/{video_lesson['id']}", headers=headers)
        if not check(
            "detalle de la lección", lesson.status_code == 200, f"HTTP {lesson.status_code}"
        ):
            return 1
        detail = lesson.json()
        hls_path = detail.get("hls_master_url")
        check("expone la URL del playlist", bool(hls_path), hls_path or "sin URL")
        check(
            "duración conocida",
            bool(detail.get("duration_seconds")),
            f"{detail.get('duration_seconds')} s",
        )

        # El reproductor pide el master con la cabecera Authorization; a partir de ahí las URIs
        # ya vienen firmadas con un token de reproducción.
        master = await client.get(f"{base}{hls_path}", headers=headers)
        if not check("playlist maestra", master.status_code == 200, f"HTTP {master.status_code}"):
            return 1

        variants = [line for line in master.text.splitlines() if line and not line.startswith("#")]
        check(
            "variantes firmadas",
            len(variants) >= 1 and "token=" in variants[0],
            f"{len(variants)} calidades",
        )

        variant = await client.get(f"{base}{variants[0]}")
        if not check(
            "playlist de variante", variant.status_code == 200, f"HTTP {variant.status_code}"
        ):
            return 1

        segments = [line for line in variant.text.splitlines() if line and not line.startswith("#")]
        check("segmentos firmados", len(segments) >= 1, f"{len(segments)} segmentos")

        redirect = await client.get(f"{base}{segments[0]}")
        if not check(
            "el segmento redirige (307)",
            redirect.status_code == 307,
            f"HTTP {redirect.status_code}",
        ):
            return 1

        location = redirect.headers.get("location", "")
        redirect_host = urlparse(location).hostname or ""
        # ESTA es la comprobación que justifica el script: si el backend firmó con `localhost`,
        # el emulador se conectaría a sí mismo y el video no cargaría nunca.
        check(
            "la URL prefirmada apunta al host correcto (no a localhost ni a `minio`)",
            redirect_host == host,
            f"{redirect_host or '(vacío)'} · esperado {host}",
        )

        async with httpx.AsyncClient(timeout=60.0) as plain:
            segment = await plain.get(location)
        check(
            "el segmento se descarga y es un TS válido",
            segment.status_code == 200
            and len(segment.content) > 1000
            and segment.content[0] == 0x47,
            f"HTTP {segment.status_code} · {len(segment.content)} bytes",
        )

        print("\n=== 5. Progreso del reproductor ===")
        progress = await client.put(
            f"{api}/lms/lessons/{video_lesson['id']}/progress",
            headers=headers,
            json={"position_seconds": 4.0},
        )
        check(
            "heartbeat aceptado",
            progress.status_code == 200,
            f"{progress.json().get('watched_percent')}% · {progress.json().get('status')}"
            if progress.status_code == 200
            else f"HTTP {progress.status_code}",
        )

        print("\n=== 6. Chat del agente ===")
        try:
            import websockets

            ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
            async with websockets.connect(f"{ws_base}/api/v1/agent/ws?token={token}") as socket:
                await socket.send(
                    json.dumps(
                        {
                            "type": "message",
                            "content": "What should I do if the unit shows error E-204?",
                            "machine_model_id": machine_id,
                        }
                    )
                )
                tokens = 0
                sources = 0
                answer = ""
                while True:
                    event = json.loads(await asyncio.wait_for(socket.recv(), timeout=90))
                    if event["type"] == "token":
                        tokens += 1
                        answer += event["data"]["text"]
                    elif event["type"] in ("done", "error"):
                        sources = len(event["data"].get("sources", []))
                        check(
                            "streaming del agente",
                            event["type"] == "done" and tokens > 3,
                            f"{tokens} tokens · {sources} fuentes",
                        )
                        break
                if answer:
                    print(f"         {answer[:150].replace(chr(10), ' ')}…")
        except ImportError:
            print("  [OMIT] chat del agente — falta el paquete `websockets` en el host")
        except Exception as exc:  # noqa: BLE001
            check("chat del agente", False, f"{type(exc).__name__}: {exc}")

    print("\n" + "=" * 70)
    print(f"PASAN: {len(passed)}   FALLAN: {len(failed)}")
    for name in failed:
        print(f"  - {name}")
    print("=" * 70)
    return 1 if failed else 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    sys.exit(asyncio.run(main(target.rstrip("/"))))
