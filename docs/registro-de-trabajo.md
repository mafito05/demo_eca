# Registro de trabajo

Contexto de las sesiones de trabajo sobre la plataforma: qué se pidió, qué se decidió, por qué, y
qué quedó pendiente. Complementa a [DECISIONS.md](../DECISIONS.md), que recoge las decisiones
técnicas con su razonamiento; aquí está la historia y el estado.

> El transcript en crudo de las sesiones **no se publica**: contiene el contenido del `.env`,
> incluidas claves reales. Este documento es su versión utilizable.

---

## 1. Punto de partida

La plataforma existía como demo verificada en una máquina de desarrollo Windows, en red local:
backend FastAPI, panel Angular, app Flutter, y el agente con RAG sobre los manuales. El encargo fue
llevarla a un VPS con IP pública (`72.60.112.93`, Ubuntu 26.04) y dejarla usable desde cualquier red.

---

## 2. Despliegue en el servidor

El VPS no tenía **nada** instalado: Docker, Compose, Node ni Flutter. Además tiene 1 vCPU y 3,8 GB
de RAM sin swap, lo que no basta para compilar el APK con Gradle; se añadieron 4 GB de swap.

**Lo que no funcionaba tal cual y por qué:**

- **El panel dependía de `ng serve`.** Su proxy de `/api` es una pieza del servidor de desarrollo,
  no del producto. Se añadió un servicio `web` al compose que compila Angular y lo sirve con Nginx
  en el :80, reproduciendo ese proxy. Alternativa descartada: apuntar `environment.ts` a la IP, que
  habría metido la IP en el bundle y devuelto el CORS que ese proxy existe para evitar (D-056).
- **Las URLs prefirmadas de MinIO se firman contra un host concreto** (la firma SigV4 cubre el
  `Host`), así que `MINIO_PUBLIC_ENDPOINT` pasó a ser la IP pública. Sin eso el vídeo no carga en el
  móvil aunque el resto funcione.
- **Puertos.** Al pasar de LAN a IP pública, "puerto publicado" pasa a ser "puerto expuesto a
  Internet": Postgres, Redis y la consola de MinIO se ataron a loopback. El :9000 de MinIO sigue
  público a la fuerza, porque es el propio dispositivo quien abre la URL prefirmada.
- **Tooling.** Los scripts existentes eran PowerShell. Se añadieron `tools/setup-server-access.sh` y
  `tools/build-apk.sh` sin sustituir a los `.ps1`, porque el entorno de desarrollo sigue siendo
  Windows.

**Tres fallos reales que aparecieron al desplegar:**

1. Las *locations* por regex de Nginx ganan a las de prefijo: el bloque de estáticos se quedaba con
   `/api/v1/machines/{id}/qr.png` y devolvía un 404 de Nginx. Se arregla con `location ^~ /api/`.
2. El healthcheck del contenedor usaba `localhost`, que dentro resuelve primero a `::1`, mientras
   Nginx solo escuchaba en IPv4.
3. La comprobación de la IP embebida en el APK con `strings` daba un falso negativo: el
   `kernel_blob.bin` va comprimido dentro del ZIP. Ahora se mira dentro del paquete.

**Verificación del despliegue:** smoke test 54/54, pytest 34/34, pipeline de vídeo 36/36, flujo
móvil simulado contra la IP pública 19/19, panel 18/18, guardrail clínico 4/4, y las 8 pantallas
capturadas en un navegador real sin errores de consola.

---

## 3. Marca

Decisión del cliente, en dos pasos. Primero: **ECA COMMUNICATIONS · Gemini Demo** en el panel, y la
app sin marca (`Equipment Training`), con el argumento de que la app la ve el personal del hospital.
Después el cliente lo revisó y pidió que la app llevara el nombre de la demo: **ECA GEMINI DEMO**.

Solo se tocó lo que ve el usuario. Los identificadores internos siguen diciendo `demoeca`
—`applicationId`, esquema del deep link, claves de almacenamiento— porque cambiarlos rompe la
identidad de la app para Android y los QR ya impresos (D-057).

---

## 4. Imágenes de producto, vídeos por equipo y segundo producto

Decisiones tomadas por el cliente antes de implementar:

| Tema | Decisión |
|---|---|
| Imágenes | Una principal (miniatura y cabecera) más galería de secundarias |
| Acceso a las imágenes | Bucket público con URL directa, no firmada |
| Vídeo ↔ equipo | Se asigna **al subir**; los existentes quedan sin asignar y se reasignan |
| Uroflowmeter | Misma profundidad que el litotriptor: temario, manual vectorizado y QR |
| Alcance en la app | Solo catálogo y ficha del equipo |
| Panel | Partirlo en subcomponentes en lugar de crecer el fichero de 1147 líneas |

**Hallazgo que bloqueaba todo lo demás.** Cuatro scripts de verificación cogían `machines[0]`. El
catálogo va ordenado por nombre y, con la colación real de la base de datos (`en_US.utf8`),
"Uro-Flow 2000" sale **antes** que "Uro-Litho 3000": al sembrar el segundo equipo, los probes del
RAG sobre el error `E-204` habrían interrogado al equipo equivocado y fallado con toda la pinta de
una regresión del RAG. Se arregló antes de sembrar nada.

**Lo entregado:** tabla `machine_images` con la portada como rol e índice único parcial, subida en
dos fases con validación real en el servidor, `?v=` para que sustituir una foto se vea,
`video_assets.machine_model_id` con filtros y reasignación, componente de subida compartido, y el
Uro-Flow 2000 sembrado con su manual (D-058 a D-061).

**Resultado colateral valioso:** con dos corpus vectorizados se pudo verificar por primera vez que
la recuperación **discrimina por equipo**. Las consultas por códigos `UF-xxx` solo devuelven
fragmentos del uroflujómetro, y las de `E-204` solo del litotriptor.

**Pendiente:** la app todavía no muestra las fotos. Están los modelos y el widget `RemoteImage`;
faltan la tarjeta del catálogo, la cabecera, la galería, los tests y un APK nuevo. Se pausó para
priorizar el trabajo de AWS.

---

## 5. AWS y cumplimiento HIPAA

Se pidió plasmar la plataforma en AWS por requisito HIPAA. Conclusiones principales:

- **AWS no hace que una aplicación cumpla HIPAA.** Aporta el BAA y una lista de servicios elegibles;
  el resto es configuración, aplicación y salvaguardas administrativas.
- **Sí hay PHI, y entra por el chat.** El agente rehúsa dar consejo clínico, pero nada impide que un
  técnico escriba datos de un paciente, y ese texto se guarda y se envía al modelo.
- **Once brechas bloquean el cumplimiento en cualquier nube**, no solo en el VPS: el texto va a
  OpenAI, se entra sin credenciales, todo viaja en HTTP plano, no hay auditoría, el token de refresco
  dura 14 días, no hay MFA en el backoffice.
- **Pasar a Bedrock no es solo cambiar de proveedor:** los embeddings bajan de 1536 a 1024
  dimensiones, lo que obliga a migrar la columna, re-vectorizar y **recalibrar el umbral del RAG**,
  que se midió con los embeddings de OpenAI.

Dos riesgos que se descartaron con datos en lugar de suponerlos: no hay problema de contenido mixto
(el panel va en HTTP plano hoy) y el preflight CORS del bucket público ya responde `204` para el PUT.

Entregado: [docs/arquitectura-aws-hipaa.md](arquitectura-aws-hipaa.md) y una presentación de 15
diapositivas con el diagrama de arquitectura y los recorridos de petición.

---

## 6. Backlog del producto

Primero como backlog del trabajo en curso; después reenfocado, a petición del cliente, al **producto
terminado v1**, incluyendo **exámenes y certificaciones propias**, que no existían en la demo.

Son 86 historias en 14 épicas, con criterios de aceptación y 17 requerimientos no funcionales
ligados a su artículo del CFR. El criterio contra la sobreingeniería quedó explícito: la v1 es lo
mínimo para que un hospital forme, evalúe y certifique a su personal con garantías, y hay una épica
"Después de la v1" con el motivo de cada aplazamiento.

Entregado: [docs/Backlog-ECA-Sentinel.docx](Backlog-ECA-Sentinel.docx) y su versión navegable.

---

## 7. Estado y riesgos abiertos

| Asunto | Estado |
|---|---|
| Demo en el VPS | Funcionando y verificada de extremo a extremo |
| Fotos en la app | **Sin terminar**: backend y panel sí, app no |
| Fotos y vídeo del Uroflowmeter | Esperan material del cliente |
| Nombre definitivo del producto | Sin decidir. La app se llama "ECA GEMINI DEMO" y ese nombre no puede salir en un certificado |
| Retención de datos | La fija compliance; bloquea una historia del backlog |
| Compilación del APK | Una vez se quedó parada horas antes de que Gradle arrancara, sin causa identificada |
| Repositorio público | Los ficheros incluyen la IP del servidor junto con la nota de que el acceso sin credenciales está activado |
| Credenciales | El `.env` del servidor tiene una API key real de OpenAI; conviene revocarla al pasar a Bedrock |

## 8. Cómo se verifica todo

```bash
docker compose exec backend python -m scripts.smoke_test
docker compose exec backend python -m pytest tests/ -q
docker compose exec backend python -m scripts.verify_guardrails
docker compose exec backend python -m scripts.simulate_mobile_client http://<IP_DEL_SERVIDOR>:8000
docker run --rm --network host -v "$PWD/admin-web:/w" -w /w -e PANEL_URL=http://<IP_DEL_SERVIDOR> \
  node:24-alpine node verify-panel.mjs
```

La app se verifica con `flutter analyze` y `flutter test` en la imagen oficial de Flutter en Docker.
Sigue sin ejecutarse nunca en un dispositivo físico ni en iOS (D-028).
