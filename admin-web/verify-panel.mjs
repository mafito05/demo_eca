/**
 * Verificación del panel servido por `ng serve`.
 *
 * Comprueba lo que un navegador haría: que la SPA se sirve, que el proxy `/api` alcanza el
 * backend, y que las pantallas tienen datos reales que mostrar. No sustituye a una prueba
 * visual, pero descarta la mayoría de los fallos de integración: proxy mal configurado, CORS,
 * rutas equivocadas y contratos que no encajan.
 *
 * Uso (con `ng serve` levantado):
 *   node admin-web/verify-panel.mjs
 */

const PANEL = process.env.PANEL_URL ?? 'http://localhost:4200';
const ADMIN = { email: 'superadmin@demoeca.example.com', password: 'Demo1234!' };

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

const api = (path) => `${PANEL}/api/v1${path}`;

console.log('=== 1. La SPA se sirve ===');
const index = await fetch(PANEL);
const html = await index.text();
check('index.html servido', index.ok, `HTTP ${index.status}`);
check('monta <app-root>', html.includes('<app-root>'));
// El nombre del bundle depende de como se sirva el panel: `ng serve` emite `main.js` y el build
// de produccion que sirve Nginx en el servidor emite `main-<hash>.js` (outputHashing: all). El
// patron acepta las dos formas para que la misma verificacion valga en desarrollo y desplegado.
check('carga el bundle principal', /src="[^"]*main(-[A-Z0-9]+)?\.js"/i.test(html));

console.log('\n=== 2. El proxy /api alcanza el backend ===');
const health = await fetch(`${PANEL}/api/v1/../../health/ready`);
check('readiness a través del proxy', health.ok, `HTTP ${health.status}`);

const login = await fetch(api('/auth/login'), {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(ADMIN),
});
if (!check('login del panel', login.ok, `HTTP ${login.status}`)) {
  process.exit(1);
}
const { access_token: token } = await login.json();
const auth = { Authorization: `Bearer ${token}` };

console.log('\n=== 3. Cada pantalla tiene datos que mostrar ===');
const screens = [
  ['Máquinas y QR', '/machines', (data) => `${data.length} máquinas`],
  ['Playground · proveedores', '/agent/providers', (data) => data.map((p) => p.key).join(', ')],
  ['Agentes', '/agent/configs', (data) => data.map((c) => `${c.provider}/${c.model_name}`).join(', ')],
  ['Conocimiento', '/agent/documents', (data) => `${data.length} documentos, ${data[0]?.chunk_count ?? 0} fragmentos`],
  ['Proveedores LLM', '/agent/credentials', (data) => `${data.length} credenciales`],
  ['Herramientas HTTP', '/agent/tools', (data) => `${data.length} herramientas`],
];

for (const [name, path, describe] of screens) {
  const response = await fetch(api(path), { headers: auth });
  const data = response.ok ? await response.json() : null;
  check(name, response.ok && Array.isArray(data), response.ok ? describe(data) : `HTTP ${response.status}`);
}

const machines = await (await fetch(api('/machines'), { headers: auth })).json();
const machineId = machines[0]?.id;

const path = await fetch(api(`/lms/machines/${machineId}/path`), { headers: auth });
const pathData = path.ok ? await path.json() : null;
check(
  'Capacitación · ruta de aprendizaje',
  path.ok && pathData.modules.length > 0,
  path.ok ? `${pathData.modules.length} módulos, ${pathData.total_lessons} lecciones` : `HTTP ${path.status}`,
);

console.log('\n=== 4. El QR se descarga autenticado (no vale un <img src>) ===');
const png = await fetch(api(`/machines/${machineId}/qr.png`), { headers: auth });
const bytes = new Uint8Array(await png.arrayBuffer());
check(
  'QR en PNG a través del proxy',
  png.ok && bytes[0] === 0x89 && bytes[1] === 0x50,
  `${bytes.length} bytes`,
);
const anonymous = await fetch(api(`/machines/${machineId}/qr.png`));
check('sin token devuelve 401 (por eso se pide como blob)', anonymous.status === 401, `HTTP ${anonymous.status}`);

console.log('\n=== 5. El inspector del RAG responde ===');
const retrieval = await fetch(api('/agent/retrieval-test'), {
  method: 'POST',
  headers: { ...auth, 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: 'what does error E-204 mean', machine_model_id: machineId, top_k: 3 }),
});
const chunks = retrieval.ok ? await retrieval.json() : [];
check(
  'recuperación vectorial desde el panel',
  retrieval.ok && chunks.length > 0,
  chunks[0] ? `${chunks[0].citation} (d=${chunks[0].distance.toFixed(4)})` : `HTTP ${retrieval.status}`,
);

console.log('\n=== 6. El WebSocket del agente pasa por el proxy ===');
const wsResult = await new Promise((resolve) => {
  const socket = new WebSocket(`${PANEL.replace('http', 'ws')}/api/v1/agent/ws?token=${token}`);
  const events = [];
  let answer = '';
  const timer = setTimeout(() => {
    socket.close();
    resolve({ ok: false, reason: 'timeout a los 90 s', events, answer });
  }, 90_000);

  socket.onopen = () =>
    socket.send(
      JSON.stringify({
        type: 'message',
        content: 'What should I do if the unit shows error E-204?',
        machine_model_id: machineId,
      }),
    );

  socket.onmessage = (event) => {
    const parsed = JSON.parse(event.data);
    events.push(parsed.type);
    if (parsed.type === 'token') answer += parsed.data.text;
    if (parsed.type === 'done' || parsed.type === 'error') {
      clearTimeout(timer);
      socket.close();
      resolve({ ok: parsed.type === 'done', events, answer, data: parsed.data });
    }
  };

  socket.onerror = () => {
    clearTimeout(timer);
    resolve({ ok: false, reason: 'error de socket', events, answer });
  };
});

check(
  'handshake WebSocket a través del proxy de ng serve',
  wsResult.events.length > 0,
  wsResult.reason ?? `${wsResult.events.length} eventos`,
);
check(
  'streaming token a token',
  wsResult.ok && wsResult.events.filter((e) => e === 'token').length > 3,
  `${wsResult.events.filter((e) => e === 'token').length} tokens`,
);
check(
  'respuesta con fuentes citadas',
  (wsResult.data?.sources?.length ?? 0) > 0,
  `${wsResult.data?.sources?.length ?? 0} fuentes · ${wsResult.data?.latency_ms ?? '?'} ms`,
);
if (wsResult.answer) {
  console.log(`         respuesta: ${wsResult.answer.slice(0, 160).replace(/\n/g, ' ')}…`);
}

console.log(`\n${'='.repeat(70)}`);
console.log(`PASAN: ${passed}   FALLAN: ${failures.length}`);
failures.forEach((name) => console.log(`  - ${name}`));
console.log('='.repeat(70));
process.exit(failures.length ? 1 : 0);
