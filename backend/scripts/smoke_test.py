"""Smoke test del flujo completo: QR -> capacitación -> agente.

Se ejecuta DENTRO del contenedor del backend (tiene httpx y websockets instalados):

    docker compose exec backend python -m scripts.smoke_test

Verifica el camino crítico end-to-end, incluidos los casos negativos (RBAC, tokens
inválidos, tools bloqueadas). Los pasos que dependen de una API key de proveedor se marcan
como OMITIDO en lugar de fallar, de modo que el test sea útil también sin claves.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from itertools import pairwise

import httpx
import websockets

BASE = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")
API = f"{BASE}/api/v1"
WS = BASE.replace("http://", "ws://").replace("https://", "wss://") + "/api/v1/agent/ws"

SUPERADMIN = ("superadmin@demoeca.example.com", "Demo1234!")

# Equipo contra el que se ejecuta el recorrido. Se fija por código porque el seed siembra más de
# una máquina y los probes del RAG dependen de un manual concreto (el del litotriptor).
SEED_MACHINE_CODE = "URO-LITHO-3000"

passed: list[str] = []
failed: list[str] = []
skipped: list[str] = []


def ok(name: str, detail: str = "") -> None:
    passed.append(name)
    print(f"  [OK]   {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str) -> None:
    failed.append(name)
    print(f"  [FALLO] {name} — {detail}")


def skip(name: str, detail: str) -> None:
    skipped.append(name)
    print(f"  [OMIT] {name} — {detail}")


def check(name: str, condition: bool, detail: str = "") -> bool:
    (ok if condition else fail)(name, detail)
    return condition


async def main() -> int:
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n=== 1. Infraestructura ===")
        health = await client.get(f"{BASE}/health/ready")
        check(
            "readiness probe (Postgres accesible)", health.status_code == 200, health.text.strip()
        )

        print("\n=== 2. Autenticación ===")
        response = await client.post(
            f"{API}/auth/login", json={"email": SUPERADMIN[0], "password": SUPERADMIN[1]}
        )
        if not check(
            "login superadmin",
            response.status_code == 200,
            f"HTTP {response.status_code} {response.text[:160]}",
        ):
            return 1
        admin_token = response.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        bad = await client.post(
            f"{API}/auth/login", json={"email": SUPERADMIN[0], "password": "incorrecta"}
        )
        check("contraseña incorrecta -> 401", bad.status_code == 401, f"HTTP {bad.status_code}")

        response = await client.post(f"{API}/auth/demo-login")
        if not check(
            "bypass demo (D-003)",
            response.status_code == 200,
            f"HTTP {response.status_code} {response.text[:160]}",
        ):
            return 1
        demo_token = response.json()["access_token"]
        demo_headers = {"Authorization": f"Bearer {demo_token}"}

        me = await client.get(f"{API}/auth/me", headers=demo_headers)
        body = me.json() if me.status_code == 200 else {}
        check(
            "usuario demo con rol trainee",
            me.status_code == 200 and body.get("role") == "trainee" and body.get("is_demo") is True,
            f"HTTP {me.status_code} {json.dumps(body)[:160]}",
        )

        garbage = await client.get(
            f"{API}/auth/me", headers={"Authorization": "Bearer no-es-un-jwt"}
        )
        check("token basura -> 401", garbage.status_code == 401, f"HTTP {garbage.status_code}")

        print("\n=== 3. RBAC ===")
        forbidden = await client.get(f"{API}/agent/credentials", headers=demo_headers)
        check(
            "trainee no accede a credenciales -> 403",
            forbidden.status_code == 403,
            f"HTTP {forbidden.status_code}",
        )

        allowed = await client.get(f"{API}/agent/credentials", headers=admin_headers)
        check(
            "superadmin sí accede a credenciales",
            allowed.status_code == 200,
            f"HTTP {allowed.status_code}",
        )

        print("\n=== 4. Flujo del QR (D-002) ===")
        machines = await client.get(f"{API}/machines", headers=demo_headers)
        items = machines.json() if machines.status_code == 200 else []
        if not check(
            "catálogo visible para el trainee",
            machines.status_code == 200 and bool(items),
            f"HTTP {machines.status_code} {len(items)} máquinas",
        ):
            return 1
        # Por código y no `items[0]`: el catálogo va ordenado por nombre, y desde que hay un
        # segundo equipo sembrado ("Uro-Flow 2000") la primera posición depende de la colación
        # del cluster. Las secciones 7 y 10 preguntan por el error E-204, que solo está en el
        # manual del litotriptor: contra otra máquina fallarían con pinta de regresión del RAG.
        machine = next((m for m in items if m["code"] == SEED_MACHINE_CODE), items[0])
        qr_token = machine["qr_token"]
        print(f"         máquina: {machine['code']} · qr_token={qr_token}")

        resolved = await client.get(f"{API}/machines/resolve/{qr_token}", headers=demo_headers)
        data = resolved.json() if resolved.status_code == 200 else {}
        machine_id = data.get("machine_model_id")
        check(
            "ESCANEO DE QR -> ruta de capacitación",
            resolved.status_code == 200 and data.get("modules_count", 0) > 0,
            f"HTTP {resolved.status_code} · {data.get('name')} · {data.get('modules_count')} módulos",
        )

        missing = await client.get(f"{API}/machines/resolve/tokenquenoexiste", headers=demo_headers)
        check("QR desconocido -> 404", missing.status_code == 404, f"HTTP {missing.status_code}")

        png = await client.get(f"{API}/machines/{machine['id']}/qr.png", headers=admin_headers)
        check(
            "QR en PNG descargable",
            png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n",
            f"HTTP {png.status_code} · {len(png.content)} bytes",
        )

        svg = await client.get(f"{API}/machines/{machine['id']}/qr.svg", headers=admin_headers)
        check(
            "QR en SVG vectorial",
            svg.status_code == 200 and b"<svg" in svg.content,
            f"HTTP {svg.status_code} · {len(svg.content)} bytes",
        )

        export = await client.get(f"{API}/machines/{machine['id']}/qr-data", headers=admin_headers)
        payload = export.json() if export.status_code == 200 else {}
        check(
            "export del QR en texto plano",
            export.status_code == 200 and payload.get("qr_url", "").startswith("https://"),
            payload.get("qr_url", ""),
        )

        print("\n=== 5. Agent Builder (configuración) ===")
        providers = await client.get(f"{API}/agent/providers", headers=admin_headers)
        specs = providers.json() if providers.status_code == 200 else []
        check(
            "catálogo multi-LLM",
            providers.status_code == 200 and len(specs) == 5,
            ", ".join(spec["key"] for spec in specs),
        )

        configs = await client.get(f"{API}/agent/configs", headers=admin_headers)
        agent_configs = configs.json() if configs.status_code == 200 else []
        default = next((c for c in agent_configs if c["is_default"]), None)
        check(
            "agente por defecto configurado",
            default is not None,
            f"{default['provider']}/{default['model_name']}" if default else "no hay is_default",
        )

        documents = await client.get(f"{API}/agent/documents", headers=admin_headers)
        docs = documents.json() if documents.status_code == 200 else []
        check(
            "documento de conocimiento sembrado",
            bool(docs),
            docs[0]["title"] if docs else "ninguno",
        )

        print("\n=== 6. Seguridad de tools (D-007) ===")
        blocked = await client.post(
            f"{API}/agent/tools",
            headers=admin_headers,
            json={
                "name": "ssrf_probe",
                "description": "Intento de alcanzar el endpoint de metadatos de cloud.",
                "http_method": "GET",
                "url_template": "http://169.254.169.254/latest/meta-data/",
                "parameters_schema": {},
            },
        )
        check(
            "tool hacia IP interna rechazada (fail-closed)",
            blocked.status_code == 422,
            f"HTTP {blocked.status_code} · {blocked.json().get('detail', '')[:90] if blocked.status_code == 422 else ''}",
        )

        print("\n=== 7. RAG ===")
        retrieval = await client.post(
            f"{API}/agent/retrieval-test",
            headers=admin_headers,
            json={
                "query": "what does error E-204 mean",
                "machine_model_id": machine_id,
                "top_k": 3,
            },
        )
        if retrieval.status_code == 200:
            chunks = retrieval.json()
            check(
                "recuperación vectorial devuelve contexto",
                bool(chunks),
                f"{len(chunks)} chunks · mejor distancia={chunks[0]['distance'] if chunks else 'n/a'}",
            )
            if chunks:
                print(f"         cita: {chunks[0]['citation']}")
                print(f"         texto: {chunks[0]['content'][:110].replace(chr(10), ' ')}...")
        elif (
            retrieval.status_code == 503
            and retrieval.json().get("code") == "provider_not_configured"
        ):
            skip("recuperación vectorial", retrieval.json()["detail"][:100])
            ok("falta de configuración reportada como 503 accionable, no como 500 opaco")
        else:
            fail("recuperación vectorial", f"HTTP {retrieval.status_code} {retrieval.text[:200]}")

        print("\n=== 8. WebSocket del agente ===")
        try:
            async with websockets.connect(f"{WS}?token=token-invalido") as socket:
                raw = await asyncio.wait_for(socket.recv(), timeout=10)
                event = json.loads(raw)
                check(
                    "WS con token inválido -> evento de error y cierre",
                    event.get("type") == "error" and event["data"].get("code") == "unauthorized",
                    json.dumps(event)[:120],
                )
        except Exception as exc:  # noqa: BLE001
            fail("WS con token inválido", f"{type(exc).__name__}: {exc}")

        try:
            async with websockets.connect(f"{WS}?token={demo_token}") as socket:
                await socket.send(json.dumps({"type": "ping"}))
                raw = await asyncio.wait_for(socket.recv(), timeout=10)
                check(
                    "WS handshake + keepalive (pong)",
                    json.loads(raw).get("type") == "pong",
                    raw[:80],
                )

                await socket.send(
                    json.dumps(
                        {
                            "type": "message",
                            "content": "What should I do if the unit shows error E-204?",
                            "machine_model_id": machine_id,
                        }
                    )
                )

                tokens: list[str] = []
                sources_event = None
                terminal = None
                while True:
                    raw = await asyncio.wait_for(socket.recv(), timeout=90)
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "conversation":
                        print(f"         conversación: {event['data']['conversation_id']}")
                    elif kind == "start":
                        print(
                            f"         proveedor: {event['data']['provider']}/{event['data']['model']}"
                        )
                    elif kind == "sources":
                        sources_event = event
                    elif kind == "token":
                        tokens.append(event["data"]["text"])
                    elif kind in ("done", "error"):
                        terminal = event
                        break

                if terminal and terminal["type"] == "error":
                    code = terminal["data"].get("code")
                    if code in ("provider_not_configured", "provider_error"):
                        skip(
                            "streaming de la respuesta del LLM",
                            f"{terminal['data'].get('message', '')[:120]}",
                        )
                        ok("el WS degrada con un error tipado en vez de romperse")
                    else:
                        fail("streaming del agente", json.dumps(terminal)[:200])
                else:
                    answer = "".join(tokens)
                    check(
                        "streaming token a token",
                        len(tokens) > 3,
                        f"{len(tokens)} chunks, {len(answer)} caracteres",
                    )
                    print(f"         respuesta: {answer[:200]}...")
                    if sources_event:
                        citations = sources_event["data"].get("sources", [])
                        check(
                            "respuesta con fuentes citadas",
                            bool(citations),
                            f"{len(citations)} fuentes",
                        )
        except Exception as exc:  # noqa: BLE001
            fail("WS del agente", f"{type(exc).__name__}: {exc}")

        # =====================================================================
        #  9. Dashboard de estadísticas
        # =====================================================================
        # Va al final a propósito: las secciones anteriores han generado tráfico real
        # (conversaciones, mensajes, progreso), así que aquí se puede comprobar que el
        # dashboard **cuenta lo que este mismo test acaba de producir**. Es lo único que
        # demuestra que el lazo está cerrado, y ningún test unitario puede demostrarlo.
        print("\n=== 9. Dashboard de estadísticas ===")

        forbidden_stats = await client.get(f"{API}/stats/overview", headers=demo_headers)
        check(
            "el trainee no accede al dashboard",
            forbidden_stats.status_code == 403,
            f"HTTP {forbidden_stats.status_code}",
        )

        started = time.perf_counter()
        overview_response = await client.get(
            f"{API}/stats/overview", params={"days": 14}, headers=admin_headers
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        if check(
            "overview responde",
            overview_response.status_code == 200,
            f"HTTP {overview_response.status_code}",
        ):
            overview = overview_response.json()
            expected_sections = [
                "content",
                "knowledge",
                "agent",
                "health",
                "training",
                "pending_actions",
                "recent_conversations",
            ]
            missing_sections = [name for name in expected_sections if name not in overview]
            check(
                "las 7 secciones están presentes",
                not missing_sections,
                f"faltan: {missing_sections}" if missing_sections else "completas",
            )

            content = overview["content"]
            check(
                "coherente con el catálogo de la sección 4",
                content["machines"]["total"] >= len(items),
                f"{content['machines']['total']} máquinas · {content['lessons']['total']} lecciones",
            )

            agent_stats = overview["agent"]
            daily = agent_stats["daily"]
            days_are_contiguous = all(
                (date.fromisoformat(later["day"]) - date.fromisoformat(earlier["day"])).days == 1
                for earlier, later in pairwise(daily)
            )
            check(
                "serie diaria completa y sin huecos",
                len(daily) == 14 and days_are_contiguous,
                f"{len(daily)} días · contigua={days_are_contiguous}",
            )
            check(
                "la serie termina hoy en UTC",
                bool(daily) and daily[-1]["day"] == datetime.now(UTC).date().isoformat(),
                daily[-1]["day"] if daily else "vacía",
            )

            # El corazón del requisito: con datos escasos el dashboard debe decir "no sé", no
            # inventarse un cero. Un `0 %` de respuestas con fuente sobre cero respuestas es
            # falso, y un p50 de cero muestras no existe.
            if agent_stats["assistant_messages_in_window"] == 0:
                check(
                    "sin datos, no inventa métricas",
                    agent_stats["grounded_answer_percent"] is None
                    and agent_stats["latency"]["p50_ms"] is None
                    and agent_stats["latency"]["sample_size"] == 0,
                    "porcentaje y percentiles a null",
                )
            else:
                check(
                    "métricas del agente coherentes",
                    agent_stats["latency"]["sample_size"] > 0
                    and 0 <= (agent_stats["grounded_answer_percent"] or 0) <= 100,
                    f"n={agent_stats['latency']['sample_size']} · "
                    f"p50={agent_stats['latency']['p50_ms']} ms · "
                    f"p95={agent_stats['latency']['p95_ms']} ms · "
                    f"{agent_stats['grounded_answer_percent']}% con fuente",
                )

            # Ningún porcentaje puede llegar como NaN o Infinity: JSON no los admite, así que
            # aparecerían como string y el panel pintaría "NaN%".
            percentages = [
                overview["agent"]["grounded_answer_percent"],
                overview["health"]["tool_error_percent"],
                overview["training"]["average_watched_percent"],
                overview["training"]["completion_percent"],
            ]
            check(
                "los porcentajes son número o null, nunca NaN",
                all(
                    value is None or (isinstance(value, int | float) and 0 <= value <= 100)
                    for value in percentages
                ),
                f"{percentages}",
            )

            check(
                "el dashboard responde en menos de 2 s",
                elapsed_ms < 2000,
                f"{elapsed_ms:.0f} ms",
            )

            actions = overview["pending_actions"]
            check(
                "cada aviso pendiente es accionable",
                all(action.get("resource") and action.get("message") for action in actions),
                f"{len(actions)} avisos" if actions else "ninguno: todo en orden",
            )
            for action in actions:
                print(f"         [{action['severity']}] {action['code']}")

            # Cierre del lazo: el WebSocket de la sección 8 generó una conversación con sus
            # mensajes. Si esa sección se omitió por falta de API key, esto se omite también.
            if any("WS" in name or "agente" in name for name in skipped):
                skip("el dashboard refleja el tráfico del test", "la sección 8 se omitió")
            else:
                check(
                    "el dashboard refleja el tráfico que generó este test",
                    agent_stats["conversations_total"] >= 1 and agent_stats["messages_total"] >= 2,
                    f"{agent_stats['conversations_total']} conversaciones · "
                    f"{agent_stats['messages_total']} mensajes · "
                    f"{agent_stats['tokens_total']} tokens",
                )

        activity = await client.get(
            f"{API}/stats/agent-activity", params={"days": 3}, headers=admin_headers
        )
        check(
            "la serie se puede pedir con otro rango",
            activity.status_code == 200 and len(activity.json()["daily"]) == 3,
            f"HTTP {activity.status_code}",
        )

        invalid_range = await client.get(
            f"{API}/stats/overview", params={"days": 0}, headers=admin_headers
        )
        check(
            "rechaza un rango inválido",
            invalid_range.status_code == 422,
            f"HTTP {invalid_range.status_code}",
        )

        # =====================================================================
        #  10. Editabilidad: máquinas, autoría del LMS y agente (D-049..D-053)
        # =====================================================================
        print("\n=== 10. Editabilidad ===")

        # --- PATCH de máquina: el campo que desbloquea publicar -------------
        same_desc = await client.patch(
            f"{API}/machines/{machine['id']}",
            json={"description": machine.get("description")},
            headers=admin_headers,
        )
        check(
            "PATCH de máquina",
            same_desc.status_code == 200,
            f"HTTP {same_desc.status_code}",
        )
        dup_code = await client.patch(
            f"{API}/machines/{machine['id']}",
            json={"code": machine["code"]},
            headers=admin_headers,
        )
        # Mismo código sobre sí misma no es conflicto; un código ajeno sí lo sería.
        check(
            "PATCH con su propio código no es conflicto",
            dup_code.status_code == 200,
            f"HTTP {dup_code.status_code}",
        )

        # --- Árbol de autoría: los campos que el path de consumo omite ------
        authoring = await client.get(
            f"{API}/lms/machines/{machine_id}/authoring", headers=admin_headers
        )
        tree = authoring.json() if authoring.status_code == 200 else {}
        first_lessons = tree.get("modules", [{}])[0].get("lessons", [])
        check(
            "árbol de autoría con campos editables",
            authoring.status_code == 200
            and bool(first_lessons)
            and "body" in first_lessons[0]
            and "status" in first_lessons[0],
            f"HTTP {authoring.status_code} · {len(tree.get('modules', []))} módulos",
        )
        forbidden_authoring = await client.get(
            f"{API}/lms/machines/{machine_id}/authoring", headers=demo_headers
        )
        check(
            "la autoría es solo backoffice",
            forbidden_authoring.status_code == 403,
            f"HTTP {forbidden_authoring.status_code}",
        )

        # --- Ciclo completo: crear módulo -> lección de texto -> borrar -----
        qa_module = await client.post(
            f"{API}/lms/modules",
            json={
                "machine_model_id": str(machine_id),
                "title": "QA smoke module (safe to delete)",
                "order_index": 90,
                "status": "draft",
            },
            headers=admin_headers,
        )
        if check("crear módulo", qa_module.status_code == 201, f"HTTP {qa_module.status_code}"):
            module_id = qa_module.json()["id"]

            qa_lesson = await client.post(
                f"{API}/lms/lessons",
                json={
                    "training_module_id": module_id,
                    "title": "QA text lesson",
                    "content_type": "text",
                    "order_index": 0,
                    "body": "Temporary body for the smoke test.",
                    "status": "draft",
                },
                headers=admin_headers,
            )
            check(
                "crear lección de texto",
                qa_lesson.status_code == 201,
                f"HTTP {qa_lesson.status_code}",
            )

            if qa_lesson.status_code == 201:
                lesson_id = qa_lesson.json()["id"]
                # El PATCH ahora valida el estado RESULTANTE: convertir la lección a video sin
                # asset debe rechazarse, no guardarse y fallar después en el móvil.
                bad_patch = await client.patch(
                    f"{API}/lms/lessons/{lesson_id}",
                    json={"content_type": "video"},
                    headers=admin_headers,
                )
                check(
                    "PATCH incoherente rechazado (video sin asset)",
                    bad_patch.status_code == 422,
                    f"HTTP {bad_patch.status_code}",
                )

                renamed = await client.patch(
                    f"{API}/lms/lessons/{lesson_id}",
                    json={"title": "QA text lesson (renamed)"},
                    headers=admin_headers,
                )
                check(
                    "PATCH de lección",
                    renamed.status_code == 200 and renamed.json()["title"].endswith("(renamed)"),
                    f"HTTP {renamed.status_code}",
                )

            deleted = await client.delete(f"{API}/lms/modules/{module_id}", headers=admin_headers)
            check(
                "borrar módulo (cascada sobre lecciones)",
                deleted.status_code == 204,
                f"HTTP {deleted.status_code}",
            )
            gone = await client.get(
                f"{API}/lms/machines/{machine_id}/authoring", headers=admin_headers
            )
            still_there = any(m["id"] == module_id for m in gone.json().get("modules", []))
            check("el módulo borrado ya no existe", not still_there)

        # --- Biblioteca de videos (D-055) -------------------------------------
        library = await client.get(f"{API}/lms/videos", headers=admin_headers)
        library_items = library.json() if library.status_code == 200 else []
        check(
            "biblioteca de videos con uso por lección",
            library.status_code == 200 and all("used_by_lessons" in item for item in library_items),
            f"{len(library_items)} assets",
        )
        in_use = next((item for item in library_items if item["used_by_lessons"]), None)
        if in_use:
            protected = await client.delete(
                f"{API}/lms/videos/{in_use['id']}", headers=admin_headers
            )
            check(
                "un video en uso no se puede borrar -> 409",
                protected.status_code == 409,
                f"HTTP {protected.status_code}",
            )
        else:
            skip("protección de borrado de video en uso", "no hay assets en uso")

        # --- Introspección del agente ----------------------------------------
        agent_settings = await client.get(f"{API}/agent/settings", headers=demo_headers)
        check(
            "settings del RAG expuestos (fin del 0.65 triplicado)",
            agent_settings.status_code == 200
            and 0 < agent_settings.json().get("rag_max_distance", 0) <= 2,
            f"max_distance={agent_settings.json().get('rag_max_distance')}"
            if agent_settings.status_code == 200
            else f"HTTP {agent_settings.status_code}",
        )

        suggestions = await client.get(
            f"{API}/agent/suggestions",
            params={"machine_model_id": str(machine_id)},
            headers=demo_headers,
        )
        check(
            "preguntas sugeridas para la app",
            suggestions.status_code == 200 and len(suggestions.json().get("questions", [])) > 0,
            f"{len(suggestions.json().get('questions', []))} preguntas "
            f"(source={suggestions.json().get('source')})"
            if suggestions.status_code == 200
            else f"HTTP {suggestions.status_code}",
        )

        base_prompt = await client.get(f"{API}/agent/prompt", headers=admin_headers)
        check(
            "prompt base visible (solo lectura, D-006)",
            base_prompt.status_code == 200
            and "STEP 1" in base_prompt.json().get("base_prompt", ""),
            f"{len(base_prompt.json().get('base_prompt', ''))} caracteres"
            if base_prompt.status_code == 200
            else f"HTTP {base_prompt.status_code}",
        )

        configs_response = await client.get(f"{API}/agent/configs", headers=admin_headers)
        agent_config_id = (
            configs_response.json()[0]["id"] if configs_response.status_code == 200 else None
        )
        if agent_config_id:
            preview = await client.post(
                f"{API}/agent/configs/{agent_config_id}/preview-prompt",
                json={"machine_model_id": str(machine_id)},
                headers=admin_headers,
            )
            check(
                "vista previa del prompt compuesto",
                preview.status_code == 200
                and "STEP 1" in preview.json().get("prompt", "")
                and preview.json().get("includes_machine_context") is True,
                f"{len(preview.json().get('prompt', ''))} caracteres"
                if preview.status_code == 200
                else f"HTTP {preview.status_code}",
            )

        # --- master.m3u8 con el token en la query (D-049) --------------------
        video_lessons = [
            lesson
            for module in tree.get("modules", [])
            for lesson in module.get("lessons", [])
            if lesson.get("video_asset_id") and lesson.get("video_status") == "ready"
        ]
        if video_lessons:
            asset_id = video_lessons[0]["video_asset_id"]
            demo_token = demo_headers["Authorization"].removeprefix("Bearer ")
            by_query = await client.get(
                f"{API}/lms/videos/{asset_id}/hls/master.m3u8",
                params={"access_token": demo_token},
            )
            check(
                "master.m3u8 con access_token por query (para ExoPlayer)",
                by_query.status_code == 200 and "#EXTM3U" in by_query.text,
                f"HTTP {by_query.status_code}",
            )
            no_auth = await client.get(f"{API}/lms/videos/{asset_id}/hls/master.m3u8")
            check(
                "master.m3u8 sin credenciales -> 401",
                no_auth.status_code == 401,
                f"HTTP {no_auth.status_code}",
            )
        else:
            skip("master.m3u8 por query", "no hay video listo en el árbol de autoría")

    print("\n" + "=" * 70)
    print(f"PASAN: {len(passed)}   FALLAN: {len(failed)}   OMITIDOS: {len(skipped)}")
    if failed:
        print("\nFallos:")
        for name in failed:
            print(f"  - {name}")
    if skipped:
        print("\nOmitidos (requieren API key de proveedor):")
        for name in skipped:
            print(f"  - {name}")
    print("=" * 70)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
