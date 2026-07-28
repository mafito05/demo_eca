/**
 * Prueba E2E de la subida de video POR NAVEGADOR, vía CDP.
 *
 * Existe porque `test_video_pipeline.py` sube con httpx desde el host, y eso NO ejercita lo que
 * falló de verdad en manos del usuario: el `<input type="file">` de Angular, el PUT presignado
 * cross-origin desde el navegador (con su preflight CORS contra MinIO), el polling de la UI y el
 * formulario de publicación. "No se pueden subir videos" era invisible para todos los tests
 * porque ninguno pasaba por el navegador.
 *
 * Recorre el flujo completo con la UI nueva de autoría:
 *   1. Sube `backend/.tmp_media/test.mp4` con `DOM.setFileInputFiles` (el mp4 lo genera
 *      `test_video_pipeline --make-source`).
 *   2. Espera a que el asset llegue a `ready` (badge en pantalla).
 *   3. Crea la lección publicada desde el formulario.
 *   4. Verifica que aparece en el árbol de autoría.
 *   5. La borra desde la UI para dejar el estado limpio (auto-acepta el confirm()).
 *
 * Uso (con `ng serve` y el backend levantados):
 *   node admin-web/verify-upload.mjs
 */

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

const PANEL = 'http://localhost:4200';
const PORT = 9334;
const ADMIN = { email: 'superadmin@demoeca.example.com', password: 'Demo1234!' };
const VIDEO = resolve(process.cwd(), 'backend', '.tmp_media', 'test.mp4');
const LESSON_TITLE = 'QA browser upload (safe to delete)';

const EDGE_PATHS = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

let passed = 0;
const failures = [];
function check(name, condition, detail = '') {
  if (condition) {
    passed += 1;
    console.log(`  [OK] ${name}${detail ? ` — ${detail}` : ''}`);
  } else {
    failures.push(name);
    console.log(`  [FALLO] ${name}${detail ? ` — ${detail}` : ''}`);
  }
  return condition;
}

class Cdp {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(message.error.message)) : resolve(message.result);
      }
    };
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.delete(id)) reject(new Error(`Sin respuesta de ${method}`));
      }, 30_000);
    });
  }

  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description ?? 'error al evaluar');
    }
    return result.result.value;
  }

  /** Espera hasta que la expresión devuelva truthy, con timeout. */
  async waitFor(expression, { timeoutMs = 30_000, everyMs = 800, label = expression } = {}) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await this.evaluate(expression)) return true;
      await sleep(everyMs);
    }
    throw new Error(`Timeout esperando: ${label}`);
  }
}

if (!existsSync(VIDEO)) {
  console.error(`No existe ${VIDEO}.`);
  console.error('Generarlo: docker compose exec worker python -m scripts.test_video_pipeline --make-source');
  process.exit(1);
}

const edge = EDGE_PATHS.find(existsSync);
if (!edge) {
  console.error('No se encontró Microsoft Edge.');
  process.exit(1);
}

const login = await fetch(`${PANEL}/api/v1/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(ADMIN),
});
if (!login.ok) {
  console.error(`No se pudo autenticar: HTTP ${login.status}. ¿Está el backend levantado?`);
  process.exit(1);
}
const tokens = await login.json();

const browser = spawn(
  edge,
  [
    '--headless=new',
    '--disable-gpu',
    `--remote-debugging-port=${PORT}`,
    '--remote-allow-origins=*',
    '--window-size=1600,1000',
    '--user-data-dir=' + join(process.cwd(), 'admin-web', '.captures', 'upload-profile'),
    'about:blank',
  ],
  { stdio: 'ignore' },
);

let exitCode = 1;
try {
  let target = null;
  for (let attempt = 0; attempt < 40 && !target; attempt += 1) {
    await sleep(500);
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      target = list.find((entry) => entry.type === 'page');
    } catch {
      /* el navegador aún no está listo */
    }
  }
  if (!target) throw new Error('El navegador no expuso el puerto de depuración.');

  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = () => reject(new Error('No se pudo abrir el WebSocket de CDP.'));
  });
  const cdp = new Cdp(socket);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('DOM.enable');

  // Sesión + auto-aceptar los confirm() de borrado: CDP no tiene UI de diálogos.
  await cdp.send('Page.navigate', { url: `${PANEL}/login` });
  await sleep(2500);
  await cdp.evaluate(`
    localStorage.setItem('demoeca.access', ${JSON.stringify(tokens.access_token)});
    localStorage.setItem('demoeca.refresh', ${JSON.stringify(tokens.refresh_token)});
    localStorage.setItem('demoeca.theme', 'light');
    'ok';
  `);

  console.log('=== 1. Pantalla de Training con árbol de autoría ===');
  await cdp.send('Page.navigate', { url: `${PANEL}/lms` });
  await sleep(3000);
  await cdp.evaluate(`window.confirm = () => true; 'ok'`);
  await cdp.waitFor(
    `!!document.querySelector('input#file') && document.body.innerText.includes('Modules')`,
    { label: 'input de subida y árbol' },
  );
  check('la pantalla de autoría carga', true);

  console.log('=== 2. Subida del fichero por el navegador (PUT presignado + CORS) ===');
  const { root } = await cdp.send('DOM.getDocument');
  const { nodeId } = await cdp.send('DOM.querySelector', {
    nodeId: root.nodeId,
    selector: 'input#file',
  });
  if (!check('el input de fichero existe', nodeId > 0)) throw new Error('sin input');

  await cdp.send('DOM.setFileInputFiles', { files: [VIDEO], nodeId });

  // El PUT es cross-origin hacia MinIO: si CORS o la IP firmada fallan, aquí aparece el error.
  await cdp.waitFor(
    `document.body.innerText.toLowerCase().includes('processing status') ||
     document.body.innerText.toLowerCase().includes('upload failed')`,
    { timeoutMs: 60_000, label: 'resultado de la subida' },
  );
  const uploadFailed = await cdp.evaluate(
    `document.body.innerText.toLowerCase().includes('upload failed')`,
  );
  if (!check('la subida por navegador llega a MinIO', !uploadFailed)) {
    const alert = await cdp.evaluate(
      `document.querySelector('.alert.error')?.innerText ?? '(sin detalle)'`,
    );
    console.log(`         detalle: ${alert}`);
    throw new Error('subida fallida');
  }

  console.log('=== 3. Transcodificación hasta ready ===');
  // Se espera al FORMULARIO de publicación, no a un badge 'ready' suelto: la biblioteca lista
  // otros videos ya listos y un badge genérico daría falso positivo inmediato.
  await cdp.waitFor(`!!document.querySelector('input#lessonTitle')`, {
    timeoutMs: 120_000,
    everyMs: 2000,
    label: 'asset ready (formulario de publicación visible)',
  });
  check('el worker transcodifica y la UI lo refleja', true);

  console.log('=== 4. Publicar la lección desde el formulario ===');
  const created = await cdp.evaluate(`
    (async () => {
      const title = document.querySelector('input#lessonTitle');
      if (!title) return 'sin formulario';
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(title, ${JSON.stringify(LESSON_TITLE)});
      title.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 300));
      const button = [...document.querySelectorAll('button')].find(
        (b) => b.textContent.trim() === 'Create published lesson',
      );
      if (!button) return 'sin botón';
      if (button.disabled) return 'botón deshabilitado';
      button.click();
      return 'ok';
    })()
  `);
  if (!check('formulario de publicación operativo', created === 'ok', created)) {
    throw new Error(created);
  }
  await cdp.waitFor(
    `document.body.innerText.includes(${JSON.stringify(LESSON_TITLE)})`,
    { timeoutMs: 15_000, label: 'lección en el árbol' },
  );
  check('la lección aparece en el árbol de autoría', true);

  console.log('=== 5. Borrado desde la UI (deja el estado limpio) ===');
  const deleted = await cdp.evaluate(`
    (() => {
      const row = [...document.querySelectorAll('.lesson')].find((r) =>
        r.innerText.includes(${JSON.stringify(LESSON_TITLE)}),
      );
      if (!row) return 'fila no encontrada';
      const button = [...row.querySelectorAll('button')].find(
        (b) => b.textContent.trim() === 'Delete',
      );
      if (!button) return 'sin botón Delete';
      button.click();
      return 'ok';
    })()
  `);
  check('borrado lanzado desde la fila', deleted === 'ok', deleted);
  await sleep(2500);
  const stillThere = await cdp.evaluate(
    `document.body.innerText.includes(${JSON.stringify(LESSON_TITLE)})`,
  );
  check('la lección de prueba ya no está', !stillThere);

  // El asset queda huérfano tras borrar la lección: se limpia por API para que las ejecuciones
  // repetidas no acumulen basura en la biblioteca.
  const library = await (
    await fetch(`${PANEL}/api/v1/lms/videos`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    })
  ).json();
  const orphan = library.find(
    (video) => video.original_filename === 'test.mp4' && video.used_by_lessons.length === 0,
  );
  if (orphan) {
    const removed = await fetch(`${PANEL}/api/v1/lms/videos/${orphan.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    check('el asset de prueba se limpia de la biblioteca', removed.status === 204);
  } else {
    check('el asset de prueba se limpia de la biblioteca', false, 'no encontrado en la biblioteca');
  }

  exitCode = failures.length ? 1 : 0;
} catch (error) {
  console.error(`\nERROR: ${error.message}`);
  exitCode = 1;
} finally {
  browser.kill();
  console.log(`\n${'='.repeat(70)}`);
  console.log(`PASAN: ${passed}   FALLAN: ${failures.length}`);
  failures.forEach((name) => console.log(`  - ${name}`));
  console.log('='.repeat(70));
  process.exit(exitCode);
}
