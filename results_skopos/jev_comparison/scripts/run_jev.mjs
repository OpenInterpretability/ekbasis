// Runs Jev (typesafe-ai/jev, Vercel AI Gateway, zero data retention) on a bench item file, one evaluate() per item.
// node run_jev.mjs ITEMS OUT [--dry] [--key-file PATH | --key env] [--cap USD] [--conc 12] [--limit N] [--ids 1,2]
//                            [--state string|object] [--order orig|shuffle|reverse] [--tag x]
// --dry: builds every request through the real SDK call path against a local mock model (no network, no key) and
//        writes the exact evaluate() arguments the model received to OUT.
// Live: the key comes from --key-file (default: the memory note) or, only when authorised, --key env. Resumable (rows
// answered in OUT are skipped). Spend is kept in spent.json from the reported input tokens, checked against the
// gateway balance before and after, and nothing is sent once the US$1 cap would be passed.
import { experimental_evaluate as evaluate } from 'ai';
import fs from 'node:fs';
import path from 'node:path';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const argv = process.argv.slice(2);
const [ITEMS, OUT] = argv;
const opt = (k, d) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : d; };
const DRY = argv.includes('--dry');
const CONC = +opt('conc', 12), LIMIT = +opt('limit', 1e9), STATE = opt('state', 'string'), ORDER = opt('order', 'orig');
const TAG = opt('tag', ''), IDS = opt('ids', null)?.split(',').map(Number);
const KEYFILE = opt('key-file', process.env.JEV_KEY_FILE);

const PRICE = 0.042 / 1e6;   // US$ per input token; output is free
const CAP = +opt('cap', 1.00);  // hard cap on the ledger total for the whole bench, US$
const LEDGER = path.join(HERE, 'spent.json');

let model = 'typesafe-ai/jev';
if (DRY) {
  // the SDK validates the call and hands the model exactly what the gateway provider would get
  model = {
    specificationVersion: 'v4', provider: 'dry', modelId: 'dry-jev', supportedQuestionTypes: ['boolean', 'choice', 'score'],
    async doEvaluate(o) {
      const answers = Object.fromEntries(Object.entries(o.questions).map(([k, q]) => [k, q.type === 'boolean'
        ? { type: 'boolean', probability: 0.5 }
        : { type: 'choice', choice: Object.keys(q.criteria)[0] }]));
      return { answers, warnings: [], usage: { inputTokens: 0 }, providerMetadata: { dry: { request: { state: o.state, questions: o.questions, providerOptions: o.providerOptions } } } };
    },
  };
} else if (opt('key', 'file') === 'env') {
  if (!process.env.AI_GATEWAY_API_KEY) throw new Error('--key env but AI_GATEWAY_API_KEY is not set');
} else {
  const keys = fs.readFileSync(KEYFILE, 'utf8').match(/vck_[A-Za-z0-9_\-]+/g) || [];
  if (keys.length !== 1) throw new Error(`expected one gateway key in ${KEYFILE}, found ${keys.length}`);
  process.env.AI_GATEWAY_API_KEY = keys[0];
}

async function balance() {  // gateway credit balance, the independent check of the spend
  try {
    const r = await fetch('https://ai-gateway.vercel.sh/v1/credits', { headers: { Authorization: `Bearer ${process.env.AI_GATEWAY_API_KEY}` } });
    if (!r.ok) return { error: `HTTP ${r.status}` };
    const j = await r.json();
    return { balance: +j.balance, total_used: +j.total_used };
  } catch (e) { return { error: String(e?.message ?? e).slice(0, 200) }; }
}

let items = fs.readFileSync(ITEMS, 'utf8').trim().split('\n').map(JSON.parse);
if (IDS) items = items.filter(r => IDS.includes(r.idx));
items = items.slice(0, LIMIT);
const done = new Set();
if (!DRY && fs.existsSync(OUT)) for (const l of fs.readFileSync(OUT, 'utf8').trim().split('\n').filter(Boolean)) {
  const r = JSON.parse(l); if (!r.error && (r.tag ?? '') === TAG) done.add(r.idx);
}
const todo = items.filter(r => !done.has(r.idx));
const ledger = fs.existsSync(LEDGER) ? JSON.parse(fs.readFileSync(LEDGER, 'utf8')) : { input_tokens: 0, usd: 0, calls: 0, content_chars: 0 };
const chars = todo.reduce((s, r) => s + r.state.length + JSON.stringify(r.question).length, 0);
// before the first measured call: 1 token per 2 content chars plus 2,000 tokens of the provider's own prompt per call;
// afterwards: the measured tokens per content char of the calls already made, with a 50% margin
const perChar = ledger.calls ? 1.5 * ledger.input_tokens / ledger.content_chars : null;
const estUsd = (perChar ? perChar * chars : chars / 2 + 2000 * todo.length) * PRICE;
console.log(`${todo.length} to ${DRY ? 'build' : 'run'} (${done.size} already done); spent so far US$${ledger.usd.toFixed(4)}; this run estimated <= US$${estUsd.toFixed(4)}`);
if (!DRY && ledger.usd + estUsd > CAP) { console.log(`would pass the US$${CAP} cap: not sending`); process.exit(2); }
const before = DRY ? null : await balance();
if (before?.error) console.log(`gateway balance check failed: ${before.error}`);

// seeded shuffle (mulberry32) so a reorder run is reproducible
const rng = seed => () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
function question(r) {
  const q = r.question;
  if (q.type !== 'choice' || ORDER === 'orig') return q;
  let ks = Object.keys(q.criteria);
  if (ORDER === 'reverse') ks = ks.reverse();
  else { const g = rng(20261016 + r.idx); for (let i = ks.length - 1; i > 0; i--) { const j = Math.floor(g() * (i + 1)); [ks[i], ks[j]] = [ks[j], ks[i]]; } }
  return { ...q, criteria: Object.fromEntries(ks.map(k => [k, q.criteria[k]])) };
}

const out = fs.createWriteStream(OUT, { flags: DRY ? 'w' : 'a' });
let next = 0, stop = false, nOk = 0, nErr = 0;
async function worker() {
  while (!stop && next < todo.length) {
    const r = todo[next++];
    if (!DRY && ledger.usd > CAP * 0.95) { stop = true; console.log('cost cap reached, stopping'); break; }
    const q = question(r);
    const t0 = performance.now();
    try {
      const res = await evaluate({
        model, state: STATE === 'object' ? { situation: r.state } : r.state, questions: { q },
        providerOptions: { gateway: { zeroDataRetention: true } }, maxRetries: 2,
      });
      const ms = performance.now() - t0, a = res.answers.q, it = res.usage?.inputTokens;
      if (DRY) { out.write(JSON.stringify({ set: r.set, idx: r.idx, ...res.providerMetadata.dry.request }) + '\n'); nOk++; continue; }
      if (it === undefined) { console.log('no input token count in the response: stopping so the spend stays known'); stop = true; }
      ledger.input_tokens += it ?? 0; ledger.usd += (it ?? 0) * PRICE; ledger.calls += 1;
      ledger.content_chars += r.state.length + JSON.stringify(q).length;
      out.write(JSON.stringify({ set: r.set, idx: r.idx, qtype: r.qtype, gold: r.gold, tag: TAG, state_form: STATE, order: ORDER,
        options_sent: q.criteria ? Object.keys(q.criteria) : null, answer: a, usage: res.usage, latency_ms: Math.round(ms),
        model: res.response?.modelId, warnings: res.warnings, gateway: res.providerMetadata?.gateway ?? null }) + '\n');
      nOk++;
    } catch (e) {
      nErr++;
      out.write(JSON.stringify({ set: r.set, idx: r.idx, tag: TAG, error: String(e?.message ?? e).slice(0, 500), latency_ms: Math.round(performance.now() - t0) }) + '\n');
      if (nErr >= 5 && nOk === 0) { console.log('5 errors and no answer: stopping'); stop = true; }
    }
    if (!DRY && (nOk + nErr) % 50 === 0) { console.log(`${nOk + nErr}/${todo.length} ok=${nOk} err=${nErr} US$${ledger.usd.toFixed(4)}`); fs.writeFileSync(LEDGER, JSON.stringify(ledger)); }
  }
}
await Promise.all(Array.from({ length: CONC }, worker));
await new Promise(res => out.end(res));
if (DRY) { console.log(`dry: built ${nOk} requests, ${nErr} rejected by the SDK; written to ${OUT}`); process.exit(nErr ? 1 : 0); }
fs.writeFileSync(LEDGER, JSON.stringify(ledger));
const after = await balance();
const delta = before?.balance !== undefined && after?.balance !== undefined ? before.balance - after.balance : null;
console.log(`done ok=${nOk} err=${nErr}; ledger: ${ledger.calls} calls, ${ledger.input_tokens} input tokens, US$${ledger.usd.toFixed(4)}; gateway balance delta this run: ${delta === null ? 'n/a' : 'US$' + delta.toFixed(4)}`);
fs.appendFileSync(path.join(HERE, 'balance_log.jsonl'), JSON.stringify({ tag: TAG, items: ITEMS, n_ok: nOk, n_err: nErr, before, after, delta, ledger_usd: ledger.usd, at: new Date().toISOString() }) + '\n');
