// Puzzle: a world from the release's planning set (containers or lamps). Left, the real puzzle (the true simulator).
// Right, what Ekbasis imagines while it plans: every depth of the beam search, how many futures it predicted, the
// states it kept (straight from its answers, with the chain confidence), and the plan it found. Then the plan is clicked
// on the real puzzle and each real state is checked against the imagined one.
import { ICONS } from './icons.js';

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const LIQ = { water: ['#7dd3fc', '#0284c7'], juice: ['#fdba74', '#ea580c'], oil: ['#fde68a', '#d97706'], sand: ['#e7d3a8', '#b08d57'] };
const pct = (c) => `${(100 * c).toFixed(c > 0.995 ? 1 : 1)}%`;
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ---------------------------------------------------------------- the true simulator (same rules as worldgen.py)
function parseAction(text) {
  let m = text.match(/^pour (\S+) into (\S+)$/);
  if (m) return { op: 'pour', x: m[1], y: m[2] };
  m = text.match(/^(fill|empty) (\S+)$/);
  if (m) return { op: m[1], x: m[2] };
  m = text.match(/^press (\S+)$/);
  if (m) return { b: m[1] };
  throw new Error(`unknown action ${text}`);
}
export function step(p, s, text) {
  const a = parseAction(text);
  if (p.fam === 'jugs') {
    const v = { ...s.v }, cap = p.world.cap;
    if (a.op === 'fill') v[a.x] = cap[a.x];
    else if (a.op === 'empty') v[a.x] = 0;
    else { const m = Math.min(v[a.x], cap[a.y] - v[a.y]); v[a.x] -= m; v[a.y] += m; }
    return { v };
  }
  const st = s.st.slice(), w = p.world, n = w.states.length;
  for (const j of w.wiring[a.b]) {
    const k = w.kinds[a.b];
    st[j] = k === 'advance' ? (st[j] + 1) % n : k === 'on' ? n - 1 : 0;
  }
  return { st };
}
function holds(p, s) {
  return p.goal.every(([k, v]) => (p.fam === 'jugs' ? String(s.v[k]) === String(v) : p.world.states[s.st[k]] === v));
}
function goalMet(p, s) {
  return p.goal.map(([k, v]) => (p.fam === 'jugs' ? String(s.v[k]) === String(v) : p.world.states[s.st[k]] === v));
}

// ---------------------------------------------------------------- drawings
function bigJugs(p, s) {
  const names = p.world.names, cap = p.world.cap, maxc = Math.max(...names.map((x) => cap[x]));
  const unit = 250 / maxc, [c1, c2] = LIQ[p.world.liq] || LIQ.water;
  const goal = Object.fromEntries(p.goal);
  return `<div style="display:flex;gap:46px;align-items:flex-end;justify-content:center;height:330px;padding-bottom:6px">${names.map((x) => {
    const h = cap[x] * unit, lv = s.v[x] * unit, w = 128;
    const ticks = Array.from({ length: cap[x] - 1 }, (_, i) => `<line x1="${w - 26}" x2="${w - 8}" y1="${h - (i + 1) * unit + 6}" y2="${h - (i + 1) * unit + 6}" stroke="#94a3b8" stroke-width="2"/>`).join('');
    const g = goal[x] != null ? `<line x1="0" x2="${w + 20}" y1="${h - Number(goal[x]) * unit + 6}" y2="${h - Number(goal[x]) * unit + 6}" stroke="#7c3aed" stroke-width="3" stroke-dasharray="8 6"/>
      <text x="${w + 24}" y="${h - Number(goal[x]) * unit + 11}" font-size="15" font-weight="800" fill="#7c3aed">goal ${goal[x]} L</text>` : '';
    return `<div style="text-align:center">
      <svg width="${w + 90}" height="${h + 12}" style="overflow:visible;display:block;margin:0 auto">
        <defs><linearGradient id="lq${x}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs>
        <rect x="4" y="6" width="${w}" height="${h}" rx="14" fill="#f8fafc" stroke="#cbd5e1" stroke-width="3"/>
        <rect x="7" y="${6 + h - lv}" width="${w - 6}" height="${Math.max(0, lv - 3)}" rx="10" fill="url(#lq${x})"/>
        ${ticks}${g}</svg>
      <div style="margin-top:12px;font-size:30px;font-weight:800">${esc(x)}</div>
      <div class="muted" style="font-size:18px;font-weight:600">${s.v[x]} of ${cap[x]} L</div></div>`;
  }).join('')}</div>`;
}
const LAMP = {
  off: 'background:#27272a;border:3px solid #3f3f46;',
  dim: 'background:radial-gradient(circle at 40% 35%,#fde68a,#f59e0b);border:3px solid #d97706;box-shadow:0 0 22px rgba(245,158,11,.55);',
  bright: 'background:radial-gradient(circle at 40% 35%,#fffbeb,#fde047);border:3px solid #eab308;box-shadow:0 0 46px rgba(253,224,71,.95),0 0 90px rgba(253,224,71,.45);',
  on: 'background:radial-gradient(circle at 40% 35%,#fffbeb,#fde047);border:3px solid #eab308;box-shadow:0 0 46px rgba(253,224,71,.95),0 0 90px rgba(253,224,71,.45);',
};
function bigLamps(p, s) {
  const w = p.world, goal = Object.fromEntries(p.goal.map(([k, v]) => [Number(k), v]));
  return `<div style="display:flex;gap:30px;align-items:center;justify-content:center;height:330px;padding:0 10px;border-radius:18px;background:#0f0f14">${s.st.map((x, j) => {
    const name = w.states[x];
    return `<div style="text-align:center;width:104px">
      <div style="width:92px;height:92px;border-radius:50%;margin:0 auto;${LAMP[name]}"></div>
      <div style="margin-top:14px;font-size:20px;font-weight:800;color:#f4f4f5">${esc(w.lamp)} ${j + 1}</div>
      <div style="font-size:16px;font-weight:600;color:#a1a1aa">${esc(name)}</div>
      ${goal[j] != null ? `<div style="margin-top:8px;display:inline-block;padding:3px 10px;border-radius:999px;border:2px dashed #a78bfa;color:#c4b5fd;font-size:14px;font-weight:800">goal: ${esc(goal[j])}</div>` : '<div style="height:31px"></div>'}</div>`;
  }).join('')}</div>`;
}
function mini(p, s, met) {
  if (p.fam === 'jugs') {
    const names = p.world.names, cap = p.world.cap, maxc = Math.max(...names.map((x) => cap[x]));
    return `<div style="display:flex;gap:10px;align-items:flex-end">${names.map((x) => {
      const h = 10 + 22 * cap[x] / maxc, lv = h * s.v[x] / cap[x], [c1, c2] = LIQ[p.world.liq] || LIQ.water;
      return `<div style="text-align:center"><div style="width:18px;height:${h}px;border:2px solid rgba(196,181,253,.6);border-radius:5px;position:relative;overflow:hidden;margin:0 auto">
        <div style="position:absolute;left:0;right:0;bottom:0;height:${lv}px;background:linear-gradient(${c1},${c2});opacity:.9"></div></div>
        <div style="font-size:11px;font-weight:700;color:#d4d4d8;margin-top:2px;font-family:var(--mono)">${s.v[x]}/${cap[x]}</div></div>`;
    }).join('')}</div>`;
  }
  const w = p.world;
  return `<div style="display:flex;gap:7px">${s.st.map((x) => {
    const name = w.states[x];
    const st = name === 'off' ? 'background:#27272a;border:2px solid #52525b' : name === 'dim' ? 'background:#f59e0b;border:2px solid #fbbf24;box-shadow:0 0 8px rgba(245,158,11,.7)'
      : 'background:#fde047;border:2px solid #fef08a;box-shadow:0 0 12px rgba(253,224,71,.9)';
    return `<div style="width:17px;height:17px;border-radius:50%;${st}"></div>`;
  }).join('')}</div>`;
}

// ---------------------------------------------------------------- the imagination panel
function imagination(p) {
  const S = p.search, shown = S.depths.slice(0, S.shown), cardsUpTo = S.cards ?? S.shown;
  const q = shown.length ? shown[shown.length - 1].q : 0, n = shown.reduce((a, d) => a + d.n, 0);
  const path = p.found ? p.plan : null;
  const cols = shown.map((d) => {
    const dots = Array.from({ length: d.n }, (_, i) => `<i style="display:inline-block;width:9px;height:9px;border-radius:50%;margin:2px;background:${i < d.kept.length ? 'rgba(167,139,250,.95)' : 'rgba(167,139,250,.28)'}"></i>`).join('');
    const cards = d.d > cardsUpTo ? '' : d.kept.map((k) => {
      const onPath = path && same(k.plan, path.slice(0, d.d));
      const checked = onPath && p.exec >= d.d ? p.checks[d.d - 1] : null;
      const met = goalMet(p, k.pred);
      return `<div style="position:relative;margin-top:7px;padding:7px 11px;border-radius:11px;display:flex;align-items:center;gap:10px;height:62px;
          background:${onPath ? 'rgba(139,92,246,.32)' : 'rgba(255,255,255,.05)'};border:1.5px solid ${onPath ? '#a78bfa' : 'rgba(255,255,255,.09)'};
          ${onPath ? 'box-shadow:0 0 26px rgba(139,92,246,.55);' : ''}${path && !onPath ? 'opacity:.36;' : ''}" ${onPath ? `data-path="${d.d}"` : ''}>
        <div style="flex:1;min-width:0"><div style="font-family:var(--mono);font-size:14px;font-weight:600;color:#ede9fe;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(k.plan[k.plan.length - 1])}</div>
          <div style="margin-top:4px;font-size:12.5px;font-variant-numeric:tabular-nums"><b style="color:${met.every(Boolean) ? '#86efac' : '#a1a1aa'}">${met.filter(Boolean).length}/${met.length} goal</b>
            <span style="color:#8b8b95"> · ${pct(k.chain)}</span>${checked != null ? ` <b style="color:${checked ? '#86efac' : '#fda4af'}">${checked ? '· ✓ real' : '· ✕ real'}</b>` : ''}</div></div>
        <div style="flex:none">${mini(p, k.pred)}</div></div>`;
    }).join('');
    return `<div style="flex:1;min-width:0">
      <div style="font-size:13px;font-weight:800;letter-spacing:1.2px;color:#a78bfa">AFTER ${d.d} ACTION${d.d > 1 ? 'S' : ''}</div>
      <div style="margin-top:6px;line-height:0">${dots}</div>
      <div style="margin-top:6px;font-size:13px;color:#a1a1aa">${d.n} futures imagined${d.d <= cardsUpTo ? ` · ${d.kept.length} kept` : ''}</div>${cards}</div>`;
  }).join('');
  return `<div style="height:100%;padding:24px 26px;background:radial-gradient(700px 400px at 70% 0%,rgba(139,92,246,.22),transparent 70%),#0d0a1a;color:#f4f4f5;display:flex;flex-direction:column">
    <div style="display:flex;align-items:baseline;gap:14px"><div style="font-size:15px;font-weight:800;letter-spacing:2px;color:#c4b5fd">EKBASIS IMAGINES</div>
      <div style="font-size:15px;color:#a1a1aa">no LLM · every future is one forward pass</div></div>
    <div style="display:flex;gap:26px;margin-top:14px">
      <div><div style="font-size:34px;font-weight:800;font-variant-numeric:tabular-nums">${n}</div><div style="font-size:13px;color:#a1a1aa">futures imagined</div></div>
      <div><div style="font-size:34px;font-weight:800;font-variant-numeric:tabular-nums">${q}</div><div style="font-size:13px;color:#a1a1aa">questions answered</div></div>
      <div><div style="font-size:34px;font-weight:800">${shown.length}</div><div style="font-size:13px;color:#a1a1aa">actions deep</div></div>
      ${p.found ? `<div style="margin-left:auto;align-self:center;padding:10px 16px;border-radius:12px;background:rgba(34,197,94,.14);border:1.5px solid rgba(74,222,128,.6);color:#bbf7d0;font-weight:800;font-size:17px">Plan found in imagination · ${p.plan.length} actions</div>` : ''}</div>
    <div style="display:flex;gap:18px;margin-top:18px;flex:1;min-height:0;overflow:hidden">${cols || '<div style="color:#71717a;font-size:16px;margin-top:20px">Waiting to imagine…</div>'}</div>
    ${p.found ? `<div style="margin-top:12px;padding:12px 16px;border-radius:12px;background:rgba(255,255,255,.05);font-family:var(--mono);font-size:16px;color:#ede9fe">plan: ${p.plan.map((a, i) => `<span style="color:${p.exec > i ? '#86efac' : '#ede9fe'}">${esc(a)}</span>`).join(' <span style="color:#71717a">→</span> ')}</div>` : ''}
  </div>`;
}

// an agent playing without a world model (no search): the right side lists what it did and what happened
function blindPanel(p) {
  const moves = (p.history || []).map((a, i) => `<div style="display:flex;align-items:center;gap:12px;margin-top:7px;padding:7px 11px;border-radius:11px;background:rgba(255,255,255,.05);border:1.5px solid rgba(255,255,255,.09)">
      <div style="width:30px;font-size:13px;font-weight:800;color:#a1a1aa">${i + 1}</div>
      <div style="flex:1;font-family:var(--mono);font-size:14px;font-weight:600;color:#e4e4e7">${esc(a)}</div>${mini(p, p.trail[i])}</div>`).join('');
  return `<div style="height:100%;padding:24px 26px;background:#111114;color:#f4f4f5;display:flex;flex-direction:column">
    <div style="display:flex;align-items:baseline;gap:14px"><div style="font-size:15px;font-weight:800;letter-spacing:2px;color:#d4d4d8">NO WORLD MODEL</div>
      <div style="font-size:15px;color:#a1a1aa">the agent acts, then sees what happened</div></div>
    <div style="margin-top:14px"><div style="font-size:34px;font-weight:800;font-variant-numeric:tabular-nums">${(p.history || []).length}</div><div style="font-size:13px;color:#a1a1aa">moves made on the real puzzle</div></div>
    <div style="margin-top:12px;flex:1;min-height:0;overflow:hidden;display:grid;grid-template-columns:1fr 1fr;column-gap:18px;align-content:start">${moves}</div></div>`;
}

export default {
  id: 'puzzle', title: 'Puzzle', icon: ICONS.puzzle,
  rules: '',  // each puzzle carries its own rules (state.rules)
  windowTitle: (s) => `Puzzle #${s.pid} — ${s.fam === 'jugs' ? 'containers' : 'lamps'} · goal: ${s.goal_text}`,

  render(s, ui) {
    const real = s.fam === 'jugs' ? bigJugs(s, s.real) : bigLamps(s, s.real);
    const buttons = s.actions.map((a, i) => `<span class="btn" data-el="puzzle.act.${i}" style="font-family:var(--mono);font-size:15px;justify-content:center">${esc(a)}</span>`).join('');
    const steps = s.plan && s.exec ? s.plan.slice(0, s.exec).map((a, i) => `<div style="display:flex;justify-content:space-between;font-size:15px;padding:5px 0;border-top:1px solid #f1f5f9">
        <span style="font-family:var(--mono)">${i + 1}. ${esc(a)}</span><span style="font-weight:700;color:${s.checks[i] ? '#15803d' : '#be123c'}">${s.checks[i] ? '✓ real state = imagined' : '✕ differs'}</span></div>`).join('') : '';
    const solved = `<div style="padding:10px 14px;border-radius:12px;background:#15803d;border:1.5px solid #15803d;color:#fff;font-size:19px;font-weight:800;box-shadow:0 10px 26px rgba(21,128,61,.35)">✓ SOLVED in the real puzzle: ${esc(s.goal_text)}</div>`;
    return `<div style="display:grid;grid-template-columns:640px 1fr;height:100%">
      <div style="padding:20px 24px;position:relative;overflow:hidden;display:flex;flex-direction:column;gap:12px">
        <div style="display:flex;align-items:baseline;gap:12px"><div style="font-size:15px;font-weight:800;letter-spacing:2px;color:#475569">THE REAL PUZZLE</div><div class="muted" style="font-size:14px">true simulator</div></div>
        ${s.solved ? solved : `<div style="padding:10px 14px;border-radius:12px;background:#f5f3ff;border:1.5px solid #c4b5fd;font-size:19px;font-weight:800;color:#5b21b6">Goal: ${esc(s.goal_text)}</div>`}
        ${real}
        <div style="display:grid;grid-template-columns:repeat(${s.actions.length > 4 ? 3 : 4},1fr);gap:10px">${buttons}</div>
        <div style="padding:10px 12px;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;font-size:12.5px;line-height:1.45;color:#334155;max-height:${s.exec ? 64 : 118}px;overflow:hidden;font-variant-ligatures:none;font-feature-settings:'calt' 0,'liga' 0">
          <b style="color:#0f172a">${s.search ? 'The rules (all Ekbasis is told):' : 'The rules (what the agent is told):'}</b> ${esc(s.rules)}</div>
        <div>${steps}</div></div>
      <div style="min-width:0">${s.search ? imagination(s) : blindPanel(s)}</div></div>`;
  },

  describe(s) {
    return [`Puzzle #${s.pid}. Rules: ${s.rules}`, `Current state: ${s.fam === 'jugs' ? s.world.names.map((x) => `${x}: ${s.real.v[x]} of ${s.world.cap[x]} liters`).join(', ')
      : s.real.st.map((x, j) => `${s.world.lamp} ${j + 1}: ${s.world.states[x]}`).join(', ')}.`, `Goal: ${s.goal_text}.${s.solved ? ' (solved)' : ''}`,
    `Buttons: ${s.actions.map((a, i) => `[puzzle.act.${i}] ${a}`).join(', ')}`, `Actions taken so far: ${s.history.length ? s.history.join(', ') : 'none'}`].join('\n');
  },

  click(s0, el) {
    const s = JSON.parse(JSON.stringify(s0));
    const m = el.match(/^puzzle\.act\.(\d+)$/);
    if (!m || !s.actions[Number(m[1])]) throw new Error(`unknown element ${el}`);
    const a = s.actions[Number(m[1])];
    s.real = step(s, s.real, a);
    s.history = [...(s.history || []), a];
    s.trail = [...(s.trail || []), s.real];
    s.solved = holds(s, s.real);
    return s;
  },
  type() { throw new Error('there is nothing to type in the puzzle'); },
  foresight() { return null; },
};
