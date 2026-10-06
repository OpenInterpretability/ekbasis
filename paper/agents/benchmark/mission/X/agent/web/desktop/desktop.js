// The demo desktop. Two modes:
//  live   (?mode=live)   the stage drives it for a real agent: every action is applied to the world and logged as a beat
//                        (with a snapshot of the world after it), so the session can be replayed exactly;
//  replay (?mode=replay) the renderer seeks it frame by frame: the logged beats are played back with cursor motion,
//                        the foresight panel, the agent's words, captions and a camera. Nothing is invented in replay:
//                        every state, click, text and model answer comes from the session log; only the timing is edited.
import APPS from './apps/index.js';

const W = 1920, H = 1080;
const $ = (s, r = document) => r.querySelector(s);
const clone = (o) => JSON.parse(JSON.stringify(o));
export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
const pct = (c) => (c >= 0.995 && c < 1 ? `${(Math.floor(1000 * c) / 10).toFixed(1)}%` : `${Math.round(100 * c)}%`);

// ------------------------------------------------------------------ the desktop, from a world
function menubar(world) {
  const app = APPS[world.focus];
  return `<div class="menubar"><span class="brand"><i></i>Workspace</span><span class="app">${esc(app ? app.title : 'Finder')}</span>
    <span class="spacer"></span><span class="agenton"><b></b>Agent at work</span><span>${esc(world.clock || '')}</span></div>`;
}
function dock(world) {
  return `<div class="dock">${(world.dock || []).map((id) => {
    const a = APPS[id];
    return `<div class="ic ${world.open.includes(id) ? 'open' : ''}" data-el="dock.${id}" style="background:${a.icon.bg}">${a.icon.glyph}</div>`;
  }).join('')}</div>`;
}
function renderWorld(world, ui = {}) {
  const wins = world.open.map((id, i) => {
    const app = APPS[id], st = world.apps[id], w = world.windows[id];
    const z = id === world.focus ? 30 : 10 + i;
    return `<div class="win ${world.focus === id ? 'focus' : ''}" data-app="${id}" style="left:${w.x}px;top:${w.y}px;width:${w.w}px;height:${w.h}px;z-index:${z}">
      <div class="titlebar"><span class="dots"><i></i><i></i><i></i></span><span class="title">${esc(app.windowTitle ? app.windowTitle(st) : app.title)}</span></div>
      <div class="content">${app.render(st, { typing: ui.typing && ui.typing.el.startsWith(id + '.') ? ui.typing : null, pressed: ui.pressed })}</div></div>`;
  }).join('');
  $('#desk').innerHTML = menubar(world) + wins + dock(world);
  if (ui.pressed) {
    const e = $(`[data-el="${CSS.escape(ui.pressed)}"]`);
    if (e) e.classList.add('pressed');
  }
}
function deskScale() { return $('#desk').getBoundingClientRect().width / W; }
function box(el) {
  const e = $(`[data-el="${CSS.escape(el)}"]`);
  if (!e) return null;
  const r = e.getBoundingClientRect(), d = $('#desk').getBoundingClientRect(), s = deskScale();
  return { x: (r.left - d.left) / s, y: (r.top - d.top) / s, w: r.width / s, h: r.height / s };
}

// ------------------------------------------------------------------ live mode (the stage and the agent)
let world = null, beats = [], meta = {};
const push = (kind, extra = {}) => beats.push({ kind, t: Date.now(), ...extra, world: clone(world) });
function screenText() {
  const lines = [`Screen: a desktop. Clock: ${world.clock}.`,
    `Open windows (focused first): ${[world.focus, ...world.open.filter((x) => x !== world.focus)].filter(Boolean).map((id) => APPS[id].title).join(', ') || 'none'}.`,
    `Apps in the dock (open_app): ${world.dock.map((id) => `${id} (${APPS[id].title})`).join(', ')}.`];
  for (const id of [world.focus, ...world.open.filter((x) => x !== world.focus)].filter(Boolean)) {
    if (!id) continue;
    lines.push('', `=== ${APPS[id].title} window ===`, APPS[id].describe(world.apps[id]));
  }
  return lines.join('\n');
}
function appOf(el) {
  const id = el.split('.')[0];
  if (!APPS[id]) throw new Error(`no app for element ${el}`);
  if (!world.open.includes(id)) throw new Error(`the ${APPS[id].title} window is not open`);
  return id;
}
function mustSee(el) {
  if (!$(`[data-el="${CSS.escape(el)}"]`)) throw new Error(`element ${el} is not on the screen`);
}
window.__live = {
  init(scn) {
    world = clone(scn.world); meta = clone(scn.meta || {}); beats = [];
    renderWorld(world); push('init'); return screenText();
  },
  look() { return screenText(); },
  open(id) {
    if (!APPS[id] || !world.dock.includes(id)) throw new Error(`no app ${id} in the dock`);
    push('move', { target: `dock.${id}` });
    if (!world.open.includes(id)) world.open.push(id);
    world.focus = id; renderWorld(world); push('open', { target: `dock.${id}`, app: id }); return screenText();
  },
  click(el) {
    const id = appOf(el); mustSee(el);
    push('move', { target: el });
    const r = APPS[id].click(world.apps[id], el, world);
    world.apps[id] = r; world.focus = id; renderWorld(world); push('click', { target: el }); return screenText();
  },
  type(el, text) {
    const id = appOf(el); mustSee(el);
    push('move', { target: el });
    world.apps[id] = APPS[id].type(world.apps[id], el, text); world.focus = id; renderWorld(world);
    push('type', { target: el, text }); return screenText();
  },
  spec(el) {
    const id = appOf(el); mustSee(el);
    const f = APPS[id].foresight ? APPS[id].foresight(world.apps[id], el) : null;
    return f ? { ...f, rules: APPS[id].rules, app: id } : null;
  },
  hud(el, spec, res) {
    push('move', { target: el });
    const lines = spec.questions.map((q) => {
      const a = res.answers[q.key], v = String(a.value);
      return { text: (q.say && q.say[v]) || `${q.text} ${v}`, value: v, conf: a.confidence, bad: v === String(q.bad) };
    });
    const hud = { label: spec.label, lines, app: spec.app, ms: res.ms };
    push('hud', { target: el, hud, spec, answers: res.answers });
    return `Ekbasis foresight for "${spec.label}":\n` + lines.map((l) => `- ${l.text} (confidence ${pct(l.conf)})${l.bad ? '  <- harmful' : ''}`).join('\n');
  },
  say(text) { push('say', { text }); return 'ok'; },
  rules(html, title) { push('rules', { html, title }); return 'ok'; },  // the app's rules shown on screen (scripted scenes)
  rulesOff() { push('rules_off'); return 'ok'; },
  done(text) { push('done', { text }); return 'ok'; },
  log() { return { meta, beats }; },
};

// ------------------------------------------------------------------ replay mode (the renderer)
const TIMING = { init: 0.9, move: 0.8, click: 0.55, open: 0.75, hud: 2.8, hud_off: 0.3, done: 1.6 };
const COMMIT = { click: 0.42, open: 0.3 };
const typeDur = (s) => clamp(0.4 + 0.032 * s.length, 0.7, 2.6);
const sayDur = (s) => clamp(1.0 + 0.04 * s.length, 1.8, 4.2);
let P = null;  // the program being replayed
let shown = { key: null };

function prepSession(seg) {
  const bs = seg.session.beats;
  const T = { ...TIMING, ...(seg.timing || {}) };
  const over = seg.beat_durations || {};
  let t = 0;
  const first = (x) => { const m = String(x || '').match(/^.*?[.!?](\s|$)/); return m ? m[0].trim() : String(x || ''); };
  seg.beats = bs.map((b0, i) => {
    const b = (b0.kind === 'done' && seg.done_first_sentence) ? { ...b0, text: first(b0.text) } : b0;  // edit: the first sentence only
    let d = b.kind === 'type' ? typeDur(b.text || '') : (b.kind === 'say' || b.kind === 'done') ? sayDur(b.text || '') + (b.kind === 'done' ? 0.8 : 0) : (T[b.kind] ?? 0.6);
    if (b.kind === 'hud' && seg.hud_next && bs.slice(0, i).some((x) => x.kind === 'hud')) d = seg.hud_next;  // later foresights shorter
    if (b.kind === 'say' && seg.say_max) d = Math.min(d, seg.say_max);
    if (b.kind === 'type' && seg.type_max) d = Math.min(d, seg.type_max);
    if (b.kind === 'done' && seg.done_max) d = Math.min(d, seg.done_max);
    if (over[i] != null) d = over[i];
    if (seg.skip && seg.skip.includes(i)) d = 0;
    const out = { ...b, i, start: t, dur: d };
    t += d;
    return out;
  });
  seg.len = t + (seg.tail ?? 0.8);
  // where every target is, measured on the world shown while the cursor goes there
  let pos = seg.cursor_start || { x: 1560, y: 860 };
  for (const b of seg.beats) {
    const before = b.i > 0 ? seg.beats[b.i - 1].world : b.world;
    if (b.target) {
      renderWorld(before);
      const r = box(b.target);
      if (r) { b.rect = r; b.pos = { x: r.x + Math.min(r.w * 0.5, 60), y: r.y + r.h * 0.55 }; }
    }
    b.from = pos;
    if (b.kind === 'move' && b.pos) pos = b.pos;
    b.to = pos;
  }
  for (const b of seg.beats) {  // the next thing the agent goes to after a foresight, which the panel must not cover
    if (b.kind !== 'hud') continue;
    const nx = seg.beats.find((c) => c.i > b.i && c.kind === 'move' && c.target !== b.target && c.rect);
    if (nx) b.avoid = nx.rect;
  }
  // how long each panel stays: a foresight until the next action or foresight, a thought until the next thought
  for (const b of seg.beats) {
    if (b.kind === 'hud') {
      const nx = seg.beats.find((c) => c.i > b.i && ['hud', 'click', 'type', 'open', 'hud_off', 'done'].includes(c.kind));
      b.end = nx ? nx.start : seg.len;
    }
    if (b.kind === 'say') {
      const nx = seg.beats.find((c) => c.i > b.i && c.kind === 'say');
      b.end = nx ? nx.start : seg.len;
    }
  }
}

function cursorAt(seg, u) {
  let cur = seg.beats[0];
  for (const b of seg.beats) { if (b.start <= u) cur = b; else break; }
  if (cur.kind === 'move' && cur.pos) { const q = ease(clamp((u - cur.start) / (cur.dur || 1), 0, 1)); return { x: cur.from.x + (cur.pos.x - cur.from.x) * q, y: cur.from.y + (cur.pos.y - cur.from.y) * q }; }
  return cur.to;
}
function camAt(seg, u, out) {
  const fit = Math.min(out.w / W, out.h / H);
  const follow = seg.follow || (P && P.follow);
  if (follow) {  // the mean cursor position over the last 0.7 s: smooth, and the same for every render
    let x = 0, y = 0; const k = 8;
    for (let j = 0; j < k; j++) { const c = cursorAt(seg, Math.max(0, u - 0.7 * j / (k - 1))); x += c.x; y += c.y; }
    return { s: follow.s ?? 1, cx: x / k + (follow.dx ?? 170), cy: y / k + (follow.dy ?? 0) };
  }
  let cam = seg.camera_start || { cx: W / 2, cy: H / 2, s: fit };
  for (const k of seg.camera || []) {
    const b = seg.beats[k.at];
    if (!b) continue;
    const t0 = b.start + (k.delay || 0), len = k.ease ?? 0.9;
    let target = { s: k.s ?? fit, cx: k.cx ?? cam.cx, cy: k.cy ?? cam.cy };
    if (k.focus) {
      const fb = seg.beats.find((c) => c.target === k.focus && c.rect) || null;
      if (fb) { target.cx = fb.rect.x + fb.rect.w / 2 + (k.dx || 0); target.cy = fb.rect.y + fb.rect.h / 2 + (k.dy || 0); }
    }
    if (u <= t0) break;
    const p = ease(clamp((u - t0) / len, 0, 1));
    cam = { s: cam.s + (target.s - cam.s) * p, cx: cam.cx + (target.cx - cam.cx) * p, cy: cam.cy + (target.cy - cam.cy) * p };
  }
  return cam;
}
function applyCam(cam, out) {
  const s = cam.s, hw = out.w / (2 * s), hh = out.h / (2 * s);
  const cx = s * W >= out.w ? clamp(cam.cx, hw, W - hw) : W / 2;
  const cy = s * H >= out.h ? clamp(cam.cy, hh, H - hh) : H / 2;
  $('#world').style.transform = `translate(${out.w / 2 - cx * s}px, ${out.h / 2 - cy * s}px) scale(${s})`;
}

function hudHTML(h, spec) {
  // a line whose question has no harmful answer (bad: 'never') is information, shown neutral
  const info = (i) => !!(spec && spec.questions && spec.questions[i] && (spec.questions[i].bad === 'never' || spec.questions[i].info));
  return `<div class="h1"><b></b>EKBASIS · FORESIGHT<span class="sp"></span><span class="t">${esc(P.hud_meta || 'one forward pass')}</span></div>
    <div class="act">If clicked: <code>${esc(h.label)}</code></div>
    ${h.lines.map((l, i) => `<div class="line ${l.bad ? 'bad' : info(i) ? 'info' : 'ok'}"><span class="ico">${l.bad ? '✕' : info(i) ? '•' : '✓'}</span><span class="txt">${esc(l.text)}</span>
      <span class="pct">${pct(l.conf)}</span><span class="bar"><i style="width:${(100 * l.conf).toFixed(1)}%"></i></span></div>`).join('')}
    <div class="foot">${esc(P.hud_foot || 'Predicted by Ekbasis-27B from the app’s rules, before the click')}</div>`;
}
function placeHud(b) {
  const el = $('#hud'), r = b.rect;
  el.innerHTML = hudHTML(b.hud, b.spec);
  const hh = el.offsetHeight || 260, hw = 500;
  const hits = (x, y) => b.avoid && x < b.avoid.x + b.avoid.w + 12 && x + hw > b.avoid.x - 12 && y < b.avoid.y + b.avoid.h + 12 && y + hh > b.avoid.y - 12;
  const top = clamp(r.y + r.h / 2 - hh / 2, 50, H - hh - 110);
  // right of the target, else left; and never over what the agent clicks next
  const cands = [[r.x + r.w + 26, top, 'right'], [r.x - hw - 26, top, 'left'],
    [clamp(r.x - 40, 20, W - hw - 20), clamp(r.y + r.h + 22, 50, H - hh - 110), 'below'],
    [clamp(r.x - 40, 20, W - hw - 20), clamp(r.y - hh - 22, 50, H - hh - 110), 'above']];
  const fit = cands.find(([x, y]) => x >= 20 && x + hw <= W - 20 && !hits(x, y)) || cands.find(([x]) => x >= 20 && x + hw <= W - 20) || cands[0];
  const [left, y, side] = fit;
  el.className = `hud ${side === 'left' ? 'left' : side === 'right' ? 'right' : 'flat'}`;
  el.style.left = `${left}px`; el.style.top = `${y}px`;
  el.style.setProperty('--ay', `${clamp(r.y + r.h / 2 - y, 24, hh - 24)}px`);
}

function seekSession(seg, u, out) {
  const bs = seg.beats;
  let cur = bs[0];
  for (const b of bs) { if (b.start <= u) cur = b; else break; }
  const p = cur.dur > 0 ? clamp((u - cur.start) / cur.dur, 0, 1) : 1;
  // the world on screen
  let w = cur.world, ui = {};
  const prev = cur.i > 0 ? bs[cur.i - 1].world : cur.world;
  if (cur.kind in COMMIT && p < COMMIT[cur.kind]) w = prev;
  if (cur.kind === 'click' && p > 0.12 && p < 0.5) ui.pressed = cur.target;
  if (cur.kind === 'type' && p < 0.9) { w = prev; ui.typing = { el: cur.target, text: cur.text.slice(0, Math.round(cur.text.length * clamp(p / 0.85, 0, 1))) }; }
  const key = `${seg.id}:${cur.i}:${w === prev ? 'b' : 'a'}:${ui.pressed || ''}:${ui.typing ? ui.typing.text.length : ''}`;
  if (shown.key !== key) { renderWorld(w, ui); shown.key = key; }
  // the cursor
  let c = cur.to;
  if (cur.kind === 'move' && cur.pos) { const q = ease(p); c = { x: cur.from.x + (cur.pos.x - cur.from.x) * q, y: cur.from.y + (cur.pos.y - cur.from.y) * q }; }
  const press = cur.kind === 'click' || cur.kind === 'open' ? (p > 0.12 && p < 0.42 ? 0.86 : 1) : 1;
  const cursor = $('#cursor');
  cursor.style.transform = `translate(${c.x - 4}px, ${c.y - 3}px) scale(${press})`;
  cursor.style.opacity = seg.hide_cursor ? 0 : 1;
  const rip = $('#cursor .ripple');
  if ((cur.kind === 'click' || cur.kind === 'open') && p > 0.15) {
    const q = clamp((p - 0.15) / 0.65, 0, 1);
    rip.style.width = rip.style.height = `${12 + 64 * q}px`; rip.style.opacity = String(0.85 * (1 - q));
  } else rip.style.opacity = '0';
  // the foresight panel
  const hb = [...bs].reverse().find((b) => b.kind === 'hud' && b.start <= u && u < b.end + 0.25);
  const hud = $('#hud');
  if (hb && hb.rect) {
    const fin = clamp((u - hb.start) / 0.28, 0, 1), fout = clamp((hb.end + 0.25 - u) / 0.25, 0, 1);
    if (hud.dataset.beat !== `${seg.id}:${hb.i}`) { placeHud(hb); hud.dataset.beat = `${seg.id}:${hb.i}`; }
    hud.style.opacity = String(Math.min(fin, fout));
    hud.style.transform = `scale(${0.94 + 0.06 * ease(fin)})`;
  } else { hud.style.opacity = '0'; hud.dataset.beat = ''; }
  // the rules panel (scripted scenes: the app's manual, as Ekbasis reads it)
  const rb = [...bs].reverse().find((b) => (b.kind === 'rules' || b.kind === 'rules_off') && b.start <= u);
  const rp = $('#rules');
  if (rb && rb.kind === 'rules') {
    if (rp.dataset.beat !== `${seg.id}:${rb.i}`) { rp.innerHTML = `<div class="rt">${esc(rb.title || 'The app’s rules · what Ekbasis reads')}</div><div class="rx">${rb.html}</div>`; rp.dataset.beat = `${seg.id}:${rb.i}`; }
    const first = bs.find((b) => b.kind === 'rules');
    rp.style.opacity = String(clamp((u - first.start) / 0.3, 0, 1));
  } else { rp.style.opacity = rb ? String(clamp(1 - (u - rb.start) / 0.25, 0, 1)) : '0'; }
  // the agent's words
  const sb = [...bs].reverse().find((b) => (b.kind === 'say' || b.kind === 'done') && b.start <= u);
  const agent = $('#agent');
  if (seg.show_agent !== false && (sb || seg.session.meta?.task)) {
    agent.style.opacity = String(clamp(u / 0.4, 0, 1));
    $('#agent .name').textContent = seg.agent_name || seg.session.meta?.agent || 'Agent';
    $('#agent .task').textContent = seg.session.meta?.task_short || '';
    const text = sb ? sb.text : (seg.session.meta?.task ? `Task: ${seg.session.meta.task}` : '');
    const n = sb ? Math.round(text.length * clamp((u - sb.start) / Math.max(0.6, Math.min(sb.dur * 0.6, text.length * 0.028)), 0, 1)) : text.length;
    $('#agent .thought').textContent = text.slice(0, n);
  } else agent.style.opacity = '0';
  // captions
  const cap = (seg.captions || []).find((k) => {
    const a = k.at_s ?? bs[k.from]?.start ?? 0, z = k.to_s ?? (bs[k.to] ? bs[k.to].start + bs[k.to].dur : seg.len);
    return a <= u && u < z;
  });
  const ce = $('#caption');
  if (cap) {
    const a = cap.at_s ?? bs[cap.from]?.start ?? 0, z = cap.to_s ?? (bs[cap.to] ? bs[cap.to].start + bs[cap.to].dur : seg.len);
    if (ce.dataset.k !== cap.text) { ce.innerHTML = cap.text; ce.dataset.k = cap.text; }
    ce.style.opacity = String(Math.min(clamp((u - a) / 0.25, 0, 1), clamp((z - u) / 0.25, 0, 1)));
  } else ce.style.opacity = '0';
  // the tag and the camera
  $('#tag').textContent = seg.tag || P.tag || '';
  $('#tag').style.opacity = seg.tag === '' ? '0' : '0.92';
  applyCam(camAt(seg, u, out), out);
}

function seekCard(seg, u) {
  const c = $('#card');
  if (c.dataset.k !== seg.id) { c.innerHTML = seg.html; c.dataset.k = seg.id; }
  const fin = clamp(u / 0.35, 0, 1), fout = seg.fade_out === false ? 1 : clamp((seg.len - u) / 0.35, 0, 1);
  c.style.opacity = String(Math.min(fin, fout));
  c.style.transform = `scale(${1.03 - 0.03 * ease(clamp(u / 0.8, 0, 1))})`;
}

window.__replay = {
  async load(program) {
    // every face the frames use, loaded before the first frame (display=block would hide text while a face loads)
    await Promise.all(['400 16px Inter', '500 16px Inter', '600 16px Inter', '700 16px Inter', '800 16px Inter',
      '400 14px "JetBrains Mono"', '600 14px "JetBrains Mono"'].map((f) => document.fonts.load(f)));
    await document.fonts.ready;
    P = program;
    let t = 0;
    P.segments.forEach((seg, i) => {
      seg.id = seg.id || `s${i}`;
      if (seg.type === 'session') prepSession(seg);
      else seg.len = seg.dur;
      seg.t0 = t; t += seg.len;
    });
    P.len = t;
    return P.len;
  },
  async seek(t) {
    const out = { w: window.innerWidth, h: window.innerHeight };
    const seg = P.segments.find((s) => t >= s.t0 && t < s.t0 + s.len) || P.segments[P.segments.length - 1];
    const u = t - seg.t0;
    $('#card').style.opacity = '0';
    if (seg.type === 'card') {
      seekCard(seg, u);
      $('#agent').style.opacity = '0'; $('#caption').style.opacity = '0'; $('#tag').style.opacity = '0'; $('#hud').style.opacity = '0';
      if (seg.over_session) { const s2 = P.segments.find((x) => x.id === seg.over_session); if (s2) seekSession(s2, s2.len - 0.01, out); }
    } else seekSession(seg, u, out);
    await new Promise((r) => requestAnimationFrame(() => r()));
    return true;
  },
};

if (new URLSearchParams(location.search).get('mode') === 'preview') {  // open a scenario in a normal browser to look at it
  fetch(new URLSearchParams(location.search).get('scenario')).then((r) => r.json()).then((s) => window.__live.init(s));
}
