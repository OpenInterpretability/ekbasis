// WS-AL copy of WS-X's stage_x.mjs (look-ahead `advise` and the ledger tracker added). WS-X's notes:
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
const WEB = path.resolve(process.env.WEB_ROOT || path.join(ROOT, 'web'));
const args = process.argv.slice(2);
const scenarioPath = path.resolve(args[0]);
const PORT = Number(args[args.indexOf('--port') + 1] || 47110) || 47110;
const STATIC = PORT + 1;
const MODE = process.env.FORESEE_MODE || 'model';
const FORESEE = process.env.FORESEE_URL || 'http://127.0.0.1:8771/foresee';
const CHOOSE = process.env.CHOOSE_URL || FORESEE.replace(/\/foresee$/, '/choose');
const ORACLE = process.env.ORACLE_URL || 'http://127.0.0.1:8762/foresee';
const PLACEBO = 'Consider what this action will do before acting.';
const TRACK = process.env.TRACK === '1';
let tracker = null;  // {pred, chain, at, synced_at, looks, steps}: Ekbasis following the ledger (TRACK=1 only)
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
if (TRACK && scenario.world.apps.ledger) tracker = { pred: { ...scenario.world.apps.ledger.opening }, chain: 1, synced_at: null, looks: [], steps: [] };
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

import { candidates as ledgerCandidates, RULES as LEDGER_RULES } from './web/desktop/apps/ledger.js';
const ASK = FORESEE.replace(/\/foresee$/, '/ask');
const ACC = ['Checking', 'Savings', 'Bills'];
const money = (v) => v.toFixed(2);

async function trackSync(how) {
  const st = await page.evaluate(() => window.__live.appState('ledger'));
  tracker.pred = { ...st.shown }; tracker.chain = 1; tracker.synced_at = st.next; tracker.looks.push({ at: st.next, how });
}

// after an instruction is processed: one request, a number question per account over the values the rules can give;
// the predicted balances become the tracker's state; a look (one of the shared balance checks) when the chain confidence
// since the last look falls below 0.9 and a check is left
async function trackStep() {
  const st = await page.evaluate(() => window.__live.appState('ledger'));
  const ins = st.inbox[st.next - 1], dec = ins.kind === 'pay' ? st.decisions[st.decisions.length - 1].choice : null;
  const cand = ledgerCandidates(tracker.pred, ins, dec);
  const state = `Balances before the instruction: ${ACC.map((a) => `${a} $${money(tracker.pred[a])}`).join('; ')}.`;
  const action = ins.text + (dec ? ` It is paid from ${dec}.` : '');
  const questions = Object.fromEntries(ACC.map((a) => [a, { text: `After the instruction, what is the ${a} balance, in dollars?`, options: cand[a].map(money) }]));
  const t0 = Date.now();
  const res = await post(ASK, { rules: LEDGER_RULES, state, actions: [action], questions });
  let conf = 1;
  for (const a of ACC) { tracker.pred[a] = parseFloat(res.answers[a].value); conf *= res.answers[a].confidence; }
  tracker.chain *= conf;
  tracker.steps.push({ at: st.next, conf: Math.round(conf * 1e4) / 1e4, ms: Date.now() - t0, pred: { ...tracker.pred }, truth: { ...st.balances } });
  calls.push({ mode: 'track', el: null, ms: Date.now() - t0 });
  if (tracker.chain < 0.9 && st.checks_left > 0 && st.next < st.inbox.length) {
    await page.evaluate(() => window.__live.click('ledger.check'));
    await trackSync('look');
  }
}

async function balancesText() {
  const st = await page.evaluate(() => window.__live.appState('ledger'));
  return `Ekbasis tracker (followed ${st.next} of ${st.inbox.length} instructions${tracker.synced_at != null ? `; last synced with the bank's balances after instruction ${tracker.synced_at}` : ''}): `
    + `${ACC.map((a) => `${a} $${money(tracker.pred[a])}`).join(', ')}. Confidence since the last sync: ${Math.round(tracker.chain * 1000) / 10}%. Balance checks left: ${st.checks_left}.`;
}

async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (j.error) throw new Error(`Ekbasis call failed: ${j.error}`);
  return j;
}

// look-ahead: one choice question over the actions (Ekbasis ranks them for the task), then the task's goal and harm
// checks for the consequential ones among the top three (or among the ones the agent named).
async function advise(cands) {
  const spec = await page.evaluate((c) => window.__live.adviseSpec(c), cands || []);
  if (!spec) return 'Nothing to rank here: the app in front has no actions to compare.';
  if (!spec.options.length) return 'No action on this screen matches those element ids.';
  const t0 = Date.now();
  const r = await post(CHOOSE, { rules: spec.rules, state: spec.state, goal: spec.goal, options: spec.options.map((o) => o.label) });
  const ranked = spec.options.map((o) => ({ ...o, p: r.probabilities[o.label] ?? 0 })).sort((a, b) => b.p - a.p);
  const pick = (cands && cands.length ? ranked : ranked.slice(0, 3)).filter((o) => o.cons);
  const checks = {};
  for (const o of pick) {
    checks[o.el] = await post(FORESEE, { rules: spec.rules, state: spec.state, action: spec.actions[o.el],
      questions: spec.checks.map((q) => ({ key: q.key, text: q.text, options: q.options })) });
  }
  calls.push({ mode: 'advise', el: null, ms: Date.now() - t0, n_options: ranked.length, n_checks: pick.length });
  return page.evaluate(([s, rk, ch]) => window.__live.adviseHud(s, rk, ch), [spec, ranked, checks]);
}

const OPS = {
  advise: ({ candidates }) => advise(candidates),
  look: () => page.evaluate(() => window.__live.look()),
  open_app: ({ app }) => page.evaluate((a) => window.__live.open(a), app),
  click: async ({ element }) => {
    const out = await page.evaluate((e) => window.__live.click(e), element);
    if (TRACK && tracker) {
      if (element === 'ledger.check') await trackSync('agent check');
      else if (['ledger.process', 'ledger.pay_checking', 'ledger.pay_savings'].includes(element)) await trackStep();
      return page.evaluate(() => window.__live.look());
    }
    return out;
  },
  balances: async () => (tracker ? balancesText() : 'No tracker in this session.'),
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
        log.meta = { ...scenario.meta, ...log.meta, scenario: path.basename(scenarioPath), saved: new Date().toISOString(), foresee_mode: MODE, foresee_calls: calls, tracker };
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
