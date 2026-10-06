// WS-X variant of stage.mjs for the control conditions: the same stage and live API, the page served from WEB_ROOT (a copy
// of desktop/ with the same app logic plus apps/truth.js), and a foresee whose answer source is FORESEE_MODE:
//   model (default)  -> FORESEE_URL (Ekbasis through foresee_x.py), as in stage.mjs
//   placebo          -> a fixed reminder, no prediction
//   oracle_llm       -> ORACLE_URL (Claude Sonnet answering the same questions), same panel
//   oracle_truth     -> the app's own code applied to a copy of the current state (apps/truth.js), same panel
//   node stage_x.mjs <scenario.json> [--port 8771]
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.resolve(process.env.WEB_ROOT || ROOT);
const args = process.argv.slice(2);
const scenarioPath = path.resolve(args[0]);
const PORT = Number(args[args.indexOf('--port') + 1] || 47110) || 47110;
const STATIC = PORT + 1;
const MODE = process.env.FORESEE_MODE || 'model';
const FORESEE = process.env.FORESEE_URL || 'http://127.0.0.1:8761/foresee';
const ORACLE = process.env.ORACLE_URL || 'http://127.0.0.1:8762/foresee';
const PLACEBO = 'Consider what this action will do before acting.';
const scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png' };
http.createServer((req, res) => {
  const p = path.join(WEB, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (!p.startsWith(WEB) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(p)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
  fs.createReadStream(p).pipe(res);
}).listen(STATIC, '127.0.0.1');

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', (e) => console.error('page error:', e.message));
await page.goto(`http://127.0.0.1:${STATIC}/desktop/index.html?mode=live`);
await page.waitForFunction(() => window.__live);
const first = await page.evaluate((s) => window.__live.init(s), scenario);
let busy = Promise.resolve();
const calls = [];  // every foresee call of this session: mode, element, ms, cost (saved with the session)

async function foresee(el) {
  const spec = await page.evaluate((e) => window.__live.spec(e), el);
  if (!spec) return `Nothing to foresee for ${el}: clicking it only navigates or opens something, it changes nothing that matters.`;
  const t0 = Date.now();
  if (MODE === 'placebo') { calls.push({ mode: MODE, el, ms: 0 }); return PLACEBO; }
  let res;
  if (MODE === 'oracle_truth') {
    const t = await page.evaluate(async (e) => (await import('/desktop/apps/truth.js')).truthNow(e), el);
    res = { answers: Object.fromEntries(Object.entries(t.answers).map(([k, v]) => [k, { value: v, confidence: 1, probabilities: { [v]: 1 } }])), ms: Date.now() - t0 };
  } else {
    const url = MODE === 'oracle_llm' ? ORACLE : FORESEE;
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rules: spec.rules, state: spec.state, action: spec.action, questions: spec.questions }) });
    res = await r.json();
    if (res.error) throw new Error(`foresight failed: ${res.error}`);
  }
  calls.push({ mode: MODE, el, ms: Date.now() - t0, cost_usd: res.cost_usd ?? null });
  return page.evaluate(([e, s, x]) => window.__live.hud(e, s, x), [el, spec, res]);
}

const OPS = {
  look: () => page.evaluate(() => window.__live.look()),
  open_app: ({ app }) => page.evaluate((a) => window.__live.open(a), app),
  click: ({ element }) => page.evaluate((e) => window.__live.click(e), element),
  type_text: ({ element, text }) => page.evaluate(([e, t]) => window.__live.type(e, t), [element, text]),
  foresee: ({ element }) => foresee(element),
  say: ({ text }) => page.evaluate((t) => window.__live.say(t), text),
  done: ({ summary }) => page.evaluate((t) => window.__live.done(t), summary),
};

http.createServer(async (req, res) => {
  let body = '';
  req.on('data', (c) => { body += c; });
  req.on('end', async () => {
    const send = (code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
    try {
      const u = new URL(req.url, 'http://x');
      if (u.pathname === '/save') {
        const log = await page.evaluate(() => window.__live.log());
        log.meta = { ...scenario.meta, ...log.meta, scenario: path.basename(scenarioPath), saved: new Date().toISOString(), foresee_mode: MODE, foresee_calls: calls };
        const out = path.join(ROOT, 'sessions', `${u.searchParams.get('name') || path.basename(scenarioPath, '.json')}.json`);
        fs.mkdirSync(path.dirname(out), { recursive: true });
        fs.writeFileSync(out, JSON.stringify(log));
        return send(200, { saved: out, beats: log.beats.length });
      }
      if (u.pathname === '/quit') { send(200, { ok: true }); await browser.close(); process.exit(0); }
      const op = u.pathname.slice(1);
      if (!OPS[op]) return send(404, { error: `no op ${op}` });
      const params = body ? JSON.parse(body) : {};
      const result = await (busy = busy.then(() => OPS[op](params), () => OPS[op](params)));
      send(200, { result });
    } catch (e) {
      send(200, { error: String(e.message || e).replace(/^Error: /, '') });
    }
  });
}).listen(PORT, '127.0.0.1', () => console.log(`stage_x on ${PORT} (page on ${STATIC}, web ${WEB}, foresee ${MODE}); ${path.basename(scenarioPath)}\n${first.split('\n')[0]}`));
