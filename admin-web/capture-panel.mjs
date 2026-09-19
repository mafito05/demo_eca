/**
 * Capturas del panel y recolección de errores de consola, vía CDP.
 *
 * Habla el protocolo DevTools directamente con el Edge instalado, usando el `WebSocket` nativo
 * de Node 24: sin Playwright ni Puppeteer, que descargarían un navegador de ~150 MB para hacer
 * lo mismo.
 *
 * Lo importante no son las capturas, es la lista de errores: un error de plantilla en Angular
 * (una propiedad que no existe, un pipe mal aplicado) compila sin problema y solo se manifiesta
 * en la consola del navegador. Sin esto, la única forma de detectarlo es abrir cada pantalla a
 * mano.
 *
 * Uso (con `ng serve` y el backend levantados):
 *   node admin-web/capture-panel.mjs
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

// Por defecto el dev-server; con PANEL_URL se apunta al panel ya desplegado (Nginx en el :80).
const PANEL = process.env.PANEL_URL ?? 'http://localhost:4200';
const PORT = 9333;
const OUT_DIR = process.env.CAPTURE_DIR ?? join(process.cwd(), 'admin-web', '.captures');
const ADMIN = { email: 'superadmin@demoeca.example.com', password: 'Demo1234!' };

// Cualquier navegador de la familia Chromium sirve: solo se le habla por CDP. Se listan las
// rutas de Windows (donde se desarrolló) y las de Linux (donde se despliega); BROWSER_PATH tiene
// prioridad para no tener que tocar el script si está instalado en otro sitio.
const BROWSER_PATHS = [
  process.env.BROWSER_PATH,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/usr/bin/google-chrome',
  '/usr/bin/microsoft-edge',
].filter(Boolean);

// Las rutas del Agent Builder cambiaron al consolidarse en pestañas (D-042): `config` pasó a
// `agents` y `credentials` a `providers`. Hay redirects de compatibilidad en el router, así que el
// script funcionaría sin tocarlo — pero fotografiaría la URL vieja, que es exactamente el tipo de
// detalle que hace que una captura mienta.
const SCREENS = [
  ['dashboard', '/dashboard', 'Panel general'],
  ['playground', '/agent/playground', 'Playground del agente'],
  ['machines', '/machines', 'Máquinas y QR'],
  ['agent-config', '/agent/agents', 'Configuración de agentes'],
  ['knowledge', '/agent/knowledge', 'Base de conocimiento'],
  ['credentials', '/agent/providers', 'Proveedores LLM'],
  ['tools', '/agent/tools', 'Herramientas HTTP'],
  ['lms', '/lms', 'Capacitación'],
];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Cliente CDP mínimo sobre el WebSocket nativo. */
class Cdp {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = [];
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(message.error.message)) : resolve(message.result);
      } else if (message.method) {
        this.listeners.forEach((fn) => fn(message));
      }
    };
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.delete(id)) {
          reject(new Error(`Sin respuesta de ${method}`));
        }
      }, 30_000);
    });
  }

  on(fn) {
    this.listeners.push(fn);
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
}

const browserPath = BROWSER_PATHS.find(existsSync);
if (!browserPath) {
  console.error('No se encontró ningún navegador Chromium. Indica la ruta con BROWSER_PATH.');
  process.exit(1);
}
mkdirSync(OUT_DIR, { recursive: true });

// Se autentica por API y se inyectan los tokens en localStorage: es exactamente lo que deja el
// formulario de login, pero sin depender de simular la escritura.
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
  browserPath,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`,
    '--remote-allow-origins=*',
    '--window-size=1600,1000',
    '--user-data-dir=' + join(OUT_DIR, 'profile'),
    // Chromium se niega a arrancar como root si no se le quita el sandbox, que es la situación
    // habitual en un servidor o dentro de un contenedor. En Windows es un flag inocuo.
    '--no-sandbox',
    'about:blank',
  ],
  { stdio: 'ignore' },
);

let cdp;
try {
  // Espera a que el puerto de depuración esté escuchando.
  let target = null;
  for (let attempt = 0; attempt < 40 && !target; attempt += 1) {
    await sleep(500);
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      target = list.find((entry) => entry.type === 'page');
    } catch {
      /* el navegador todavía no está listo */
    }
  }
  if (!target) {
    throw new Error('El navegador no expuso el puerto de depuración.');
  }

  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = () => reject(new Error('No se pudo abrir el WebSocket de CDP.'));
  });
  cdp = new Cdp(socket);

  const problems = [];
  cdp.on((message) => {
    if (message.method === 'Runtime.exceptionThrown') {
      const details = message.params.exceptionDetails;
      problems.push(`EXCEPCIÓN: ${details.exception?.description ?? details.text}`);
    }
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
      problems.push(
        `CONSOLE.ERROR: ${message.params.args.map((a) => a.value ?? a.description ?? '').join(' ')}`,
      );
    }
    if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') {
      // Los 404/500 de red también aparecen aquí; se filtran los favicon, que no importan.
      const { text, url } = message.params.entry;
      if (!String(url ?? '').includes('favicon')) {
        problems.push(`LOG: ${text}`);
      }
    }
  });

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');

  // Hay que estar en el origen del panel para poder escribir en su localStorage.
  await cdp.send('Page.navigate', { url: `${PANEL}/login` });
  await sleep(2500);
  await cdp.evaluate(`
    localStorage.setItem('demoeca.access', ${JSON.stringify(tokens.access_token)});
    localStorage.setItem('demoeca.refresh', ${JSON.stringify(tokens.refresh_token)});
    // El perfil del navegador se reutiliza entre ejecuciones (--user-data-dir), así que sin fijar
    // estas dos preferencias una sesión anterior en modo oscuro o con el sidebar colapsado
    // cambiaría TODAS las capturas sin que nadie lo pidiera.
    localStorage.setItem('demoeca.theme', 'light');
    localStorage.setItem('demoeca.sidebar', 'expanded');
    'ok';
  `);

  const captured = [];
  for (const [name, route, label] of SCREENS) {
    const before = problems.length;
    await cdp.send('Page.navigate', { url: `${PANEL}${route}` });
    // Margen para que resuelvan las peticiones de datos de cada pantalla.
    await sleep(3200);

    if (name === 'dashboard') {
      // El dashboard agrega 17 consultas sobre la tabla de mensajes. Con un backend frío puede
      // tardar más que la espera fija, y entonces la captura saldría con los skeletons puestos —
      // que es peor que un fallo, porque parece una pantalla vacía. Se sondea un centinela.
      let ready = false;
      for (let attempt = 0; attempt < 20 && !ready; attempt += 1) {
        ready = await cdp.evaluate(`
          !!document.querySelector('[data-testid="stat-conversations"]')?.textContent.trim()
        `);
        if (!ready) await sleep(500);
      }
      if (!ready) {
        problems.push('DASHBOARD: los KPI no se renderizaron en 10 s');
      }
      // Se comprueba que el sparkline tiene su tabla gemela, pero se deja CERRADA: abierta
      // domina la tarjeta y la captura dejaría de representar cómo se ve el panel en uso.
      const hasTwin = await cdp.evaluate(`!!document.querySelector('details.data-table')`);
      if (!hasTwin) {
        problems.push('DASHBOARD: el sparkline no tiene tabla de datos gemela');
      }

      // Segunda captura del resto de la página: los KPI de inventario, el progreso de formación y
      // la tabla de conversaciones quedan por debajo del pliegue en 1600x1000.
      await cdp.evaluate(`document.querySelector('.main').scrollTop = 2000; 'ok'`);
      await sleep(700);
      const below = await cdp.send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(OUT_DIR, 'dashboard-scrolled.png'), Buffer.from(below.data, 'base64'));
      await cdp.evaluate(`document.querySelector('.main').scrollTop = 0; 'ok'`);
      await sleep(300);
    }

    if (name === 'playground') {
      // Se dispara el inspector del RAG para que la captura muestre fragmentos reales con sus
      // distancias, que es lo que demuestra que la recuperación funciona.
      await cdp.evaluate(`
        (() => {
          const button = [...document.querySelectorAll('button')]
            .find((b) => b.textContent.trim() === 'Retrieve');
          if (button) button.click();
          return !!button;
        })()
      `);
      await sleep(3000);

      // Y se envía una pregunta real por el WebSocket del cliente Angular. Esto es lo que
      // verifica el camino completo desde el navegador: `verify-panel.mjs` prueba el socket
      // desde Node, que no ejercita el servicio del panel ni el renderizado del streaming.
      const sent = await cdp.evaluate(`
        (() => {
          const input = document.querySelector('.composer input');
          if (!input) return 'sin campo de texto';
          input.value = 'What should I do if the unit shows error E-204?';
          // ngModel escucha el evento 'input'; asignar .value a secas no actualiza el modelo.
          input.dispatchEvent(new Event('input', { bubbles: true }));
          const button = [...document.querySelectorAll('button')]
            .find((b) => b.textContent.trim() === 'Send');
          if (!button) return 'sin botón enviar';
          setTimeout(() => button.click(), 60);
          return 'enviado';
        })()
      `);
      console.log(`            chat: ${sent}`);

      // Espera a que el streaming termine: se detecta por la aparición de la línea de métricas
      // del evento `done`, en lugar de dormir un tiempo fijo.
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await sleep(1000);
        const done = await cdp.evaluate(`!!document.querySelector('.msg.assistant .meta')`);
        if (done) break;
      }
      const answer = await cdp.evaluate(
        `(document.querySelector('.msg.assistant .text')?.innerText ?? '').slice(0, 120)`,
      );
      const sources = await cdp.evaluate(`document.querySelectorAll('.msg .source').length`);
      console.log(`            respuesta renderizada: "${answer.replace(/\n/g, ' ')}…"`);
      console.log(`            fuentes en pantalla: ${sources}`);
      if (!answer || sources === 0) {
        problems.push('El chat no renderizó respuesta o fuentes en el navegador.');
      }
    }

    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
    const file = join(OUT_DIR, `${name}.png`);
    writeFileSync(file, Buffer.from(shot.data, 'base64'));

    const newProblems = problems.slice(before);
    captured.push({ name, label, file, problems: newProblems });
    console.log(
      `  ${newProblems.length ? '[AVISO]' : '[OK]   '} ${label.padEnd(28)} -> ${name}.png` +
        (newProblems.length ? ` (${newProblems.length} problemas)` : ''),
    );
    newProblems.forEach((problem) => console.log(`            ${problem.slice(0, 170)}`));
  }

  console.log(`\nCapturas en ${OUT_DIR}`);
  const total = captured.reduce((sum, screen) => sum + screen.problems.length, 0);
  console.log(total === 0 ? 'Ninguna pantalla produjo errores en consola.' : `${total} problemas detectados.`);
  process.exitCode = total === 0 ? 0 : 1;
} catch (error) {
  console.error(`Fallo: ${error.message}`);
  process.exitCode = 1;
} finally {
  browser.kill();
}
