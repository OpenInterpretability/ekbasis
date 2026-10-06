// WS-RA stage: one real agent session on a REAL self-hosted app (Gitea, Nextcloud, Roundcube) in a headless browser.
// Port of launch_video/stage_x.mjs: the same ops over HTTP (look, click, type_text, foresee, say, done) plus what real
// pages need (select_option, press_key, goto). The browser is pre-authenticated with a saved storage state, so the agent
// never sees a password, and every request to another origin is blocked (nothing leaves the Mac).
// foresee asks the spec server (adapters/spec_server.py) what the element does in this app; the answer source is
// FORESEE_MODE:
//   model (see)  -> FORESEE_URL (Ekbasis through foresee_ra.py)
//   placebo      -> X's fixed reminder, no prediction
//   facts        -> the adapter's state facts, no prediction
//   oracle_llm   -> ORACLE_URL (Claude Sonnet answering the same questions, X's oracle_llm.py)
//   node stage_real.mjs --run <run_ctx.json> --port <p> [--mode model|placebo|facts|oracle_llm|none]
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const RUN = JSON.parse(fs.readFileSync(arg('--run'), 'utf8'));
const PORT = Number(arg('--port', '47300'));
const MODE = arg('--mode', process.env.FORESEE_MODE || 'model');
const FORESEE = process.env.FORESEE_URL || 'http://127.0.0.1:8781/foresee';
const ORACLE = process.env.ORACLE_URL || 'http://127.0.0.1:8782/foresee';
const SPEC = process.env.SPEC_URL || 'http://127.0.0.1:8783/spec';
const PLACEBO = 'Consider what this action will do before acting.';  // X's placebo, verbatim
const ORIGIN = new URL(RUN.base_url).origin;
const MAX_LINES = Number(process.env.LOOK_MAX_LINES || 260);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ storageState: RUN.storage_state, viewport: { width: 1440, height: 900 },
  locale: 'en-US', timezoneId: RUN.timezone || 'America/Sao_Paulo' });
await context.route('**/*', (route) => {
  const u = route.request().url();
  if (u.startsWith('data:') || u.startsWith('blob:') || u.startsWith(ORIGIN)) return route.continue();
  return route.abort();
});
let page = await context.newPage();
let pendingDialog = null;
const hookPage = (p) => {
  p.on('pageerror', (e) => console.error('page error:', e.message));
  p.on('dialog', (d) => {
    beat('browser_dialog', { message: d.message(), type: d.type() });
    // leaving a page with unsaved input is what the agent asked for (goto, or a click that navigates): accept it
    if (d.type() === 'beforeunload') { d.accept().catch(() => {}); return; }
    pendingDialog = d;
  });
};
hookPage(page);
context.on('page', (p) => { hookPage(p); page = p; beat('new_tab', { url: p.url() }); });

const beats = [];
const calls = [];
const t0 = Date.now();
let lastClick = null;
const clickHist = [];  // contexts of the last clicks, so the spec server can tell which row a menu or dialog belongs to
function beat(kind, x = {}) { beats.push({ kind, t: (Date.now() - t0) / 1000, ...x }); }

await page.goto(new URL(RUN.start_path || '/', RUN.base_url).toString(), { waitUntil: 'domcontentloaded' });
await settle();

async function settle(ms = 700) {
  try { await page.waitForLoadState('domcontentloaded', { timeout: 8000 }); } catch { /* keep going */ }
  try { await page.waitForLoadState('networkidle', { timeout: 4000 }); } catch { /* SPAs poll */ }
  await page.waitForTimeout(ms);
}

// ---------------------------------------------------------------- the page as text (runs inside the page)
function pageText(maxLines) {
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const cut = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
  const docs = [document];
  for (let i = 0; i < docs.length; i++) for (const f of docs[i].querySelectorAll('iframe')) { try { if (f.contentDocument) docs.push(f.contentDocument); } catch { /* other origin */ } }
  docs.forEach((d) => d.querySelectorAll('[data-ra-ref]').forEach((e) => e.removeAttribute('data-ra-ref')));
  const INTER = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=menuitem],'
    + '[role=menuitemcheckbox],[role=menuitemradio],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=option],'
    + '[role=combobox],[role=textbox],[role=searchbox],[role=treeitem],[contenteditable=""],[contenteditable=true]';
  const isBox = (el) => el.matches('input[type=checkbox],input[type=radio]');
  const cs = (el) => (el.ownerDocument.defaultView || window).getComputedStyle(el);
  const shown = (el) => {
    if (!el || el.nodeType !== 1) return false;
    if (el.closest('[aria-hidden=true]') && !isBox(el)) return false;
    const s = cs(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (isBox(el)) return true;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const nameOf = (el) => {
    const al = el.getAttribute('aria-label'); if (al && clean(al)) return clean(al);
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = clean(lb.split(/\s+/).map((id) => el.ownerDocument.getElementById(id)?.innerText || '').join(' ')); if (t) return t; }
    if (el.id) { const l = el.ownerDocument.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l && clean(l.innerText)) return clean(l.innerText); }
    const pl = el.closest('label'); if (pl && pl !== el && clean(pl.innerText)) return clean(pl.innerText);
    if (isBox(el)) { const sib = el.parentElement && el.parentElement.querySelector('label'); if (sib && clean(sib.innerText)) return clean(sib.innerText); }
    if (!el.matches('input,select,textarea')) { const t = clean(el.innerText); if (t) return t; }
    const plain = clean(el.getAttribute('title') || el.getAttribute('placeholder') || el.getAttribute('alt')
      || (el.querySelector && el.querySelector('img[alt]') && el.querySelector('img[alt]').alt) || el.getAttribute('name') || '');
    if (plain) return plain;
    const m = String(el.className || '').match(/\b(remove|delete|close|clear|trash|cancel)\b/i);  // an icon-only control: name it by its icon and what it sits on
    return m ? `${m[1].toLowerCase()} (${cut(clean(el.parentElement ? el.parentElement.innerText : ''), 70)})` : '';
  };
  const roleOf = (el) => el.getAttribute('role') || ({ A: 'link', BUTTON: 'button', SELECT: 'dropdown', TEXTAREA: 'textbox', SUMMARY: 'button' })[el.tagName]
    || (el.tagName === 'INPUT' ? ({ checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button', reset: 'button', search: 'searchbox', file: 'file' })[el.type] || 'textbox'
      : (el.isContentEditable ? 'textbox' : 'clickable'));
  const ICON = /\b(remove|delete|close|clear|trash|cancel)\b/i;
  const isInter = (el) => el.matches(INTER) || (cs(el).cursor === 'pointer' && !el.parentElement?.closest(INTER)
    && !el.querySelector(INTER) && ((clean(el.innerText).length > 0 && clean(el.innerText).length < 80)
      || (clean(el.innerText).length === 0 && (ICON.test(String(el.className || '')) || el.getAttribute('title') || el.getAttribute('aria-label')))));
  let n = 0;
  const describe = (el) => {
    n += 1; el.setAttribute('data-ra-ref', String(n));
    const role = roleOf(el);
    let s = `[${n}] ${role} "${cut(nameOf(el), 90)}"`;
    if (isBox(el) || el.getAttribute('aria-checked')) s += (el.checked || el.getAttribute('aria-checked') === 'true') ? ' (checked)' : ' (unchecked)';
    if (el.matches('input:not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]),textarea')) {
      const v = el.type === 'password' ? (el.value ? '••••' : '') : el.value; s += ` value="${cut(clean(v), 120)}"`;
    }
    if (el.tagName === 'SELECT') s += ` selected="${cut(clean(el.selectedOptions[0]?.text || ''), 60)}" options=[${[...el.options].slice(0, 12).map((o) => cut(clean(o.text), 30)).join(' | ')}]`;
    if (el.getAttribute('aria-expanded')) s += el.getAttribute('aria-expanded') === 'true' ? ' (expanded)' : ' (collapsed)';
    if (el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-current')) s += ' (current)';
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') s += ' (disabled)';
    return s;
  };
  const BLOCK = new Set(['block', 'flex', 'grid', 'table', 'table-row', 'list-item', 'table-caption', 'flow-root']);
  const walk = (root, out) => {
    let buf = '';
    const flush = () => { const t = clean(buf); if (t) out.push(cut(t, 300)); buf = ''; };
    const rec = (node) => {
      if (!node) return;
      if (node.nodeType === 3) { buf += ' ' + node.textContent; return; }
      if (node.nodeType !== 1) return;
      const el = node;
      if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG', 'svg'].includes(el.tagName)) return;
      if (el.dataset && el.dataset.raSkip) return;
      if (!shown(el)) return;
      if (el.tagName === 'IFRAME') {
        let d = null; try { d = el.contentDocument; } catch { d = null; }
        if (d && d.body) { flush(); out.push('--- frame ---'); rec(d.body); flush(); out.push('--- end of frame ---'); }
        return;
      }
      if (isInter(el)) {
        flush(); out.push(describe(el));
        if (!el.querySelector(INTER)) return;  // a container control (combobox, menu, listbox): its options are listed too
      }
      const block = BLOCK.has(cs(el).display) || el.tagName === 'BR';
      if (block) flush();
      for (const c of el.childNodes) rec(c);
      if (block) flush();
    };
    rec(root); flush();
  };
  const dialogs = [...document.querySelectorAll('[role=dialog],[role=alertdialog],.ui.modal.visible,.ui-dialog,.modal-container')]
    .filter((d) => shown(d) && !d.parentElement.closest('[role=dialog],[role=alertdialog],.ui.modal.visible,.ui-dialog,.modal-container'));
  const out = [`Page: ${document.title} — ${location.pathname}${location.search}`];
  for (const d of dialogs) { out.push('=== an open dialog ==='); walk(d, out); out.push('=== end of dialog ==='); d.dataset.raSkip = '1'; }
  walk(document.body, out);
  dialogs.forEach((d) => delete d.dataset.raSkip);
  const dedup = out.filter((l, i) => i === 0 || l !== out[i - 1]);
  if (dedup.length > maxLines) return dedup.slice(0, maxLines).join('\n') + `\n(… ${dedup.length - maxLines} more lines not shown; the page is long)`;
  return dedup.join('\n');
}

// the element and its surroundings, for the spec server (never passwords, never CSRF tokens)
function elementContext(ref) {
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim();
  const docs = [document];
  for (let i = 0; i < docs.length; i++) for (const f of docs[i].querySelectorAll('iframe')) { try { if (f.contentDocument) docs.push(f.contentDocument); } catch { /* other origin */ } }
  let el = null;
  for (const d of docs) { el = d.querySelector(`[data-ra-ref="${ref}"]`); if (el) break; }
  if (!el) return null;
  const doc = el.ownerDocument;
  const form = el.closest('form');
  // the element's form, or (for toolbar buttons that submit a form from outside it) every form of its document
  const scopeEls = form ? [...form.querySelectorAll('input,select,textarea')] : [...doc.querySelectorAll('form input, form select, form textarea')].slice(0, 80);
  const fields = scopeEls.filter((f) => !/csrf|token/i.test(f.name || '') && f.type !== 'password').map((f) => ({
    name: f.name || f.id || '', type: f.type || f.tagName.toLowerCase(),
    value: (f.type === 'checkbox' || f.type === 'radio') ? f.value : (f.tagName === 'TEXTAREA' ? String(f.value || '').slice(0, 4000) : clean(f.value).slice(0, 300)),
    checked: (f.type === 'checkbox' || f.type === 'radio') ? f.checked : undefined,
    label: clean((f.id && doc.querySelector(`label[for="${CSS.escape(f.id)}"]`)?.innerText) || f.closest('label')?.innerText || f.parentElement?.querySelector('label')?.innerText || f.getAttribute('aria-label')
      || (f.getAttribute('aria-labelledby') || '').split(/\s+/).map((id) => (id && doc.getElementById(id)?.innerText) || '').join(' ') || f.placeholder || '').slice(0, 120),
  }));
  const dlg = el.closest('[role=dialog],[role=alertdialog],.ui.modal,.ui-dialog,.modal-container');
  const row = el.closest('tr,li,[role=row],.item,.flex-item');
  // the nearest panel around the element (form, dialog, sidebar section) and which of its radios and checkboxes are on
  const panel = el.closest('form,[role=dialog],[role=alertdialog],.ui.modal,.modal-container,[role=tabpanel],aside,section') || null;
  const lab = (f) => clean((f.id && doc.querySelector(`label[for="${CSS.escape(f.id)}"]`)?.innerText) || f.closest('label')?.innerText || f.parentElement?.innerText || f.getAttribute('aria-label') || '');
  const panelChecked = panel ? [...panel.querySelectorAll('input[type=radio],input[type=checkbox]')].map((f) => ({ label: lab(f).slice(0, 120), type: f.type, checked: f.checked })) : [];
  const side = el.closest('aside,[role=complementary],[role=dialog]');
  const sideHeadings = side ? [...side.querySelectorAll('h1,h2,h3,h4')].map((h) => clean(h.innerText)).filter(Boolean).slice(0, 8) : [];
  const rowLabels = row ? [...row.querySelectorAll('[aria-label],[title]')].map((x) => clean(x.getAttribute('aria-label') || x.getAttribute('title'))).filter(Boolean).slice(0, 8) : [];
  const data = {}; for (const [k, v] of Object.entries(el.dataset || {})) if (k !== 'raRef') data[k] = String(v).slice(0, 300);
  return { ref, tag: el.tagName.toLowerCase(), type: el.type || '', role: el.getAttribute('role') || '', id: el.id || '', name: el.name || '',
    cls: String(el.className || '').slice(0, 200), text: clean(el.innerText || el.value || el.getAttribute('aria-label') || '').slice(0, 300),
    label: clean(el.getAttribute('aria-label') || el.getAttribute('title') || '').slice(0, 200), href: el.getAttribute('href') || '', data,
    checked: el.checked ?? null, form_action: form ? form.getAttribute('action') || '' : null, form_method: form ? (form.getAttribute('method') || 'get').toLowerCase() : null,
    fields, form_text: form ? clean(form.innerText).slice(0, 1500) : null, panel_text: panel ? clean(panel.innerText).slice(0, 1500) : null, panel_checked: panelChecked, row_labels: rowLabels, side_headings: sideHeadings, dialog: dlg ? clean(dlg.innerText).slice(0, 2000) : null, row: row ? clean(row.innerText).slice(0, 400) : null,
    url: location.href, frame_url: doc.location.href, title: document.title, headings: [...doc.querySelectorAll('h1,h2,h3,h4,.header')].map((h) => clean(h.innerText)).filter(Boolean).slice(0, 10) };
}

async function look() {
  if (pendingDialog) return `A browser dialog is open: "${pendingDialog.message()}"\n[accept] button "OK"\n[dismiss] button "Cancel"`;
  for (let i = 0; ; i++) {  // the page may be navigating after a click (a form submit, a redirect): wait and read again
    try { return await page.evaluate(pageText, MAX_LINES); } catch (e) {
      if (i >= 4 || !/context was destroyed|navigation|nodeType|Target closed|frame was detached/i.test(String(e.message))) throw e;
      await settle(800);
    }
  }
}

async function loc(ref) {
  const sel = `[data-ra-ref="${String(ref).replace(/[^0-9]/g, '')}"]`;
  for (const f of page.frames()) {
    try { const l = f.locator(sel); if (await l.count() > 0) return l.first(); } catch { /* detached frame */ }
  }
  throw new Error(`element [${ref}] is not on the page any more; call look to see the page again`);
}

const ctxOf = async (ref) => { if (pendingDialog) return null; try { return await page.evaluate(elementContext, String(ref).replace(/[^0-9]/g, '')); } catch { return null; } };

// guard mode (addendum C): the first click on an element the adapter recognizes as consequential is paused and answered
// with Ekbasis' foresight; clicking it again in the same state goes ahead. No foresee tool: the agent does not have to ask.
const confirmed = new Set();
async function guardPause(ref, c) {
  if ((MODE !== 'guard' && MODE !== 'guard_goal') || !c) return null;
  const r = await fetch(SPEC, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app: RUN.app, run: RUN.run_id, user: RUN.user, element: c, opener: lastClick, history: clickHist,
      ...(MODE === 'guard_goal' ? { goal: true, request: RUN.task } : {}) }) });
  const sj = await r.json();
  if (sj.error || !sj.spec) return null;
  const spec = sj.spec;
  const key = `${spec.label}|${spec.state}`;
  if (confirmed.has(key)) return null;
  const tq = Date.now();
  const fr = await fetch(FORESEE, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rules: spec.rules, state: spec.state, action: spec.action, questions: spec.questions }) });
  const res = await fr.json();
  if (res.error) { beat('foresee_error', { target: ref, error: String(res.error).slice(0, 200), guard: true }); return null; }
  const lines = spec.questions.map((q) => {
    const a = res.answers[q.key]; const v = String(a.value);
    const markable = MODE !== 'guard_goal' || q.key === 'beyond';  // guard_goal: only changes beyond the request are marked
    return { key: q.key, text: (q.say && q.say[v]) || `${q.text} ${v}`, value: v, conf: a.confidence, bad: markable && v === String(q.bad) };
  });
  confirmed.add(key);
  const name = c.text || c.label || `[${ref}]`;
  calls.push({ mode: MODE, el: ref, name, spec, answers: res.answers, ms: Date.now() - tq, model_ms: res.ms });
  beat('hud', { target: ref, hud: { label: spec.label, lines }, spec, answers: res.answers, guard: true });
  return `Ekbasis paused this click to check it first. Ekbasis foresight for "${spec.label}":\n`
    + lines.map((l) => `- ${l.text} (confidence ${pct(l.conf)})${l.bad ? '  <- harmful' : ''}`).join('\n')
    + `\nNothing was clicked. If you still want to do this, click [${ref}] again; otherwise choose another way.`;
}

async function click({ element }) {
  const ref = String(element).replace(/^\s*\[|\]\s*$/g, '').trim();
  if (pendingDialog && (ref === 'accept' || ref === 'dismiss')) {
    const d = pendingDialog; pendingDialog = null;
    beat('click', { target: ref, name: `browser dialog ${ref}`, url: page.url() });
    if (ref === 'accept') await d.accept(); else await d.dismiss();
    await settle(); return look();
  }
  if (pendingDialog) throw new Error('a browser dialog is open; click [accept] or [dismiss] first');
  const l = await loc(ref);
  const c = await ctxOf(ref);
  const paused = await guardPause(ref, c);
  if (paused) return paused;
  beat('click', { target: ref, name: c && (c.text || c.label), url: page.url(), ctx: c });
  lastClick = c; if (c) { clickHist.push(c); if (clickHist.length > 8) clickHist.shift(); }
  const isBox = await l.evaluate((e) => e.matches('input[type=checkbox],input[type=radio]'));
  if (isBox) await l.setChecked(!(await l.isChecked()), { force: true, timeout: 8000 });
  else {
    try { await l.click({ timeout: 8000 }); } catch (e) {
      if (/intercepts pointer events|not visible|outside of the viewport/.test(String(e.message))) await l.click({ timeout: 8000, force: true });
      else throw e;
    }
  }
  await settle();
  return look();
}

async function typeText({ element, text }) {
  if (pendingDialog) throw new Error('a browser dialog is open; click [accept] or [dismiss] first');
  const ref = String(element).replace(/^\s*\[|\]\s*$/g, '').trim();
  const l = await loc(ref);
  const c = await ctxOf(ref);
  beat('type', { target: ref, name: c && (c.label || c.text || c.name), text, url: page.url() });
  const editable = await l.evaluate((e) => e.isContentEditable && !e.matches('input,textarea'));
  if (editable) { await l.click(); await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A'); await page.keyboard.type(text); }
  else await l.fill(text, { timeout: 8000 });
  await page.waitForTimeout(500);
  return `Typed into [${ref}]. Call look to see the page (suggestions or results may have appeared).`;
}

async function selectOption({ element, option }) {
  const ref = String(element).replace(/^\s*\[|\]\s*$/g, '').trim();
  const l = await loc(ref);
  beat('select', { target: ref, option, url: page.url() });
  try { await l.selectOption({ label: option }, { timeout: 8000 }); } catch { await l.selectOption(option, { timeout: 8000 }); }
  await settle(400);
  return look();
}

async function pressKey({ key }) {
  beat('press', { key, url: page.url() });
  await page.keyboard.press(key);
  await settle();
  return look();
}

async function gotoPage({ url }) {
  if (pendingDialog) throw new Error('a browser dialog is open; click [accept] or [dismiss] first');
  const u = new URL(url, RUN.base_url);
  if (u.origin !== ORIGIN) throw new Error(`only pages of this app (${ORIGIN}) can be opened`);
  beat('goto', { url: u.toString() });
  await page.goto(u.toString(), { waitUntil: 'domcontentloaded' });
  await settle();
  return look();
}

const pct = (c) => (c >= 0.995 && c < 1 ? `${(Math.floor(1000 * c) / 10).toFixed(1)}%` : `${Math.round(100 * c)}%`);

async function foresee({ element }) {
  if (pendingDialog) throw new Error('a browser dialog is open; click [accept] or [dismiss] first');
  const ref = String(element).replace(/^\s*\[|\]\s*$/g, '').trim();
  if (MODE === 'none') throw new Error('no foresee in this condition');
  const c = await ctxOf(ref);
  if (!c) throw new Error(`element [${ref}] is not on the page any more; call look to see the page again`);
  const tq = Date.now();
  const r = await fetch(SPEC, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app: RUN.app, run: RUN.run_id, user: RUN.user, element: c, opener: lastClick, history: clickHist }) });
  const sj = await r.json();
  if (sj.error) throw new Error(`foresight failed: ${sj.error}`);
  const spec = sj.spec;
  const name = c.text || c.label || `[${ref}]`;
  if (!spec) {
    calls.push({ mode: MODE, el: ref, name, spec: null, ms: Date.now() - tq });
    beat('hud', { target: ref, none: true });
    return `No foresight available for this element ("${name.slice(0, 80)}").`;
  }
  if (MODE === 'placebo') { calls.push({ mode: MODE, el: ref, name, spec, ms: Date.now() - tq }); beat('hud', { target: ref, placebo: true, spec }); return PLACEBO; }
  if (MODE === 'facts') {
    calls.push({ mode: MODE, el: ref, name, spec, ms: Date.now() - tq });
    beat('hud', { target: ref, facts: true, spec });
    return `Facts for "${spec.label}" (no prediction):\n${spec.state}`;
  }
  const url = MODE === 'oracle_llm' ? ORACLE : FORESEE;
  const fr = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rules: spec.rules, state: spec.state, action: spec.action, questions: spec.questions }) });
  const res = await fr.json();
  if (res.error) { beat('foresee_error', { target: ref, error: String(res.error).slice(0, 200) }); throw new Error(`foresight failed: ${res.error}`); }
  const lines = spec.questions.map((q) => {
    const a = res.answers[q.key]; const v = String(a.value);
    return { key: q.key, text: (q.say && q.say[v]) || `${q.text} ${v}`, value: v, conf: a.confidence, bad: v === String(q.bad) };
  });
  calls.push({ mode: MODE, el: ref, name, spec, answers: res.answers, ms: Date.now() - tq, model_ms: res.ms, cost_usd: res.cost_usd ?? null });
  beat('hud', { target: ref, hud: { label: spec.label, lines }, spec, answers: res.answers });
  return `Ekbasis foresight for "${spec.label}":\n` + lines.map((l) => `- ${l.text} (confidence ${pct(l.conf)})${l.bad ? '  <- harmful' : ''}`).join('\n');
}

const OPS = {
  look: async () => { beat('look', { url: page.url() }); return look(); },
  click, type_text: typeText, select_option: selectOption, press_key: pressKey, goto: gotoPage, foresee,
  say: async ({ text }) => { beat('say', { text }); return 'ok'; },
  done: async ({ summary }) => { beat('done', { text: summary }); return 'ok'; },
};

let busy = Promise.resolve();
http.createServer(async (req, res) => {
  let body = '';
  req.on('data', (c) => { body += c; });
  req.on('end', async () => {
    const send = (code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
    try {
      const u = new URL(req.url, 'http://x');
      if (u.pathname === '/save') {
        const out = u.searchParams.get('out');
        fs.mkdirSync(path.dirname(out), { recursive: true });
        fs.writeFileSync(out, JSON.stringify({ meta: { run: RUN, mode: MODE, saved: new Date().toISOString(), final_url: page.url() }, beats, foresee_calls: calls }));
        return send(200, { saved: out, beats: beats.length });
      }
      if (u.pathname === '/quit') { send(200, { ok: true }); await browser.close(); process.exit(0); }
      const op = u.pathname.slice(1);
      if (!OPS[op]) return send(404, { error: `no op ${op}` });
      const params = body ? JSON.parse(body) : {};
      const result = await (busy = busy.then(() => OPS[op](params), () => OPS[op](params)));
      send(200, { result });
    } catch (e) {
      send(200, { error: String(e.message || e).replace(/^Error: /, '').split('\n')[0].slice(0, 400) });
    }
  });
}).listen(PORT, '127.0.0.1', () => console.log(`stage_real on ${PORT} (${RUN.app}, mode ${MODE}, ${RUN.base_url}${RUN.start_path || '/'})`));
