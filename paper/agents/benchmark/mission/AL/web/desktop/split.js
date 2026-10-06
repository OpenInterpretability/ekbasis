// Split screen: two recorded sessions replayed side by side (each in its own desktop, an iframe in replay mode), the
// same task, left without a world model and right with Ekbasis. Each side keeps its own timing; `delay` shifts a side so
// the moments that matter line up. The agents' words are copied from each side's own panel into large text below.
const $ = (s) => document.querySelector(s);
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
let P = null;

function frameSize() {
  const W = innerWidth, H = innerHeight;
  if (W / H > 1.3) {  // 16:9: two desktops at half size, labels above, words and outcomes below
    const s = 0.49, w = 1920 * s, h = 1080 * s, gap = (W - 2 * w) / 3, top = 120;
    return { s, iw: 1920, ih: 1080, sides: [{ x: gap, y: top }, { x: 2 * gap + w, y: top }], w, h,
      label: (i) => ({ x: [gap, 2 * gap + w][i], y: 52 }), say: (i) => ({ x: [gap, 2 * gap + w][i] + 6, y: top + h + 26, w: w - 12 }),
      outcome: (i) => ({ x: [gap, 2 * gap + w][i], y: top + h + 126, w }) };
  }
  // square: stacked, each side a cropped desktop that follows its own cursor
  const w = W - 60, h = (H - 200) / 2;
  return { s: 1, iw: w, ih: h, sides: [{ x: 30, y: 70 }, { x: 30, y: 130 + h }], w, h,
    label: (i) => ({ x: 34, y: [18, 78 + h][i] }), say: () => null, outcome: (i) => ({ x: 50, y: [70 + h - 80, 130 + 2 * h - 80][i], w: w - 40 }) };
}

function sideLen(side) { return side.delay || 0; }

window.__replay = {
  async load(program) {
    await Promise.all(['600 16px Inter', '700 16px Inter', '800 16px Inter'].map((f) => document.fonts.load(f)));
    P = program;
    const F = frameSize();
    const ifr = [$('#fl'), $('#fr')];
    await Promise.all(ifr.map((f, i) => new Promise((res) => {
      const box = $(['#sl', '#sr'][i]);
      Object.assign(box.style, { left: `${F.sides[i].x}px`, top: `${F.sides[i].y}px`, width: `${F.w}px`, height: `${F.h}px` });
      f.width = F.iw; f.height = F.ih;
      f.style.transform = `scale(${F.s})`;
      f.onload = res;
      f.src = 'index.html?mode=replay&embed=1';
    })));
    for (const f of ifr) {  // the desktop defines __replay once its apps are loaded (top-level await)
      for (let k = 0; k < 400 && !(f.contentWindow && f.contentWindow.__replay); k++) await new Promise((r) => setTimeout(r, 25));
    }
    const lens = [];
    for (let i = 0; i < 2; i++) {
      const side = P.sides[i], w = ifr[i].contentWindow;
      await w.document.fonts.ready;
      w.document.querySelector('#overlay').style.display = 'none';  // the split page shows words and captions itself
      const prog = { hud_meta: P.hud_meta, hud_foot: P.hud_foot, follow: F.s === 1 ? (side.follow || { s: 0.8, dx: 120 }) : undefined,
        segments: [{ type: 'session', session: side.session, tag: '', show_agent: true, captions: [], camera: side.camera || [],
          beat_durations: side.beat_durations || {}, skip: side.skip || [], timing: side.timing || P.timing || {}, tail: side.tail ?? 2,
          say_max: side.say_max ?? P.say_max, done_max: side.done_max ?? P.done_max, hud_next: side.hud_next ?? P.hud_next,
          type_max: side.type_max ?? P.type_max, done_first_sentence: side.done_first_sentence ?? P.done_first_sentence }] };
      lens.push((await w.__replay.load(prog)) + sideLen(side));
    }
    const L = ['#ll span', '#lr span'];
    P.sides.forEach((side, i) => {
      $(L[i]).textContent = side.label;
      const l = F.label(i); Object.assign($(['#ll', '#lr'][i]).style, { left: `${l.x}px`, top: `${l.y}px` });
      const y = F.say(i);
      if (y) Object.assign($(['#yl', '#yr'][i]).style, { left: `${y.x}px`, top: `${y.y}px`, width: `${y.w}px` });
      else $(['#yl', '#yr'][i]).style.display = 'none';
      const o = F.outcome(i); Object.assign($(['#ol', '#or'][i]).style, { left: `${o.x}px`, top: `${o.y}px`, width: `${o.w}px` });
      $(['#ol', '#or'][i]).className = `outcome ${side.outcome_kind || ''}`;
      $(['#ol', '#or'][i]).innerHTML = side.outcome || '';
    });
    P.body = Math.max(...lens);
    P.intro = P.intro ? { ...P.intro } : null;
    P.len = (P.intro ? P.intro.dur : 0) + P.body + (P.outro ? P.outro.dur : 0);
    return P.len;
  },
  async seek(t) {
    const ifr = [$('#fl'), $('#fr')];
    const i0 = P.intro ? P.intro.dur : 0;
    const card = $('#card');
    const showCard = (c, u, len) => {
      if (card.dataset.k !== c.big) { card.innerHTML = `<div><div class="big">${c.big}</div>${c.sub ? `<div class="sub">${c.sub}</div>` : ''}</div>`; card.dataset.k = c.big; }
      card.style.opacity = String(Math.min(clamp(u / 0.35, 0, 1), clamp((len - u) / 0.35, 0, 1)));
    };
    card.style.opacity = '0';
    if (P.intro && t < i0) showCard(P.intro, t, P.intro.dur);
    if (P.outro && t >= i0 + P.body) showCard(P.outro, t - i0 - P.body, P.outro.dur);
    const u = clamp(t - i0, 0, P.body);
    for (let i = 0; i < 2; i++) {
      const side = P.sides[i], w = ifr[i].contentWindow;
      await w.__replay.seek(Math.max(0, u - (side.delay || 0)));
      const th = w.document.querySelector('#agent .thought').textContent;
      $(['#yl', '#yr'][i]).innerHTML = th ? `<small>${side.agent || 'Agent'}</small>${th.replace(/[&<]/g, (c) => ({ '&': '&amp;', '<': '&lt;' }[c]))}` : '';
      const oa = side.outcome_at ?? P.body - 2.5;
      $(['#ol', '#or'][i]).style.opacity = String(clamp((u - oa) / 0.4, 0, 1));
    }
    const cap = (P.captions || []).find((c) => c.at <= u && u < c.to);
    const ce = $('#caption');
    if (cap) { if (ce.dataset.k !== cap.text) { ce.innerHTML = cap.text; ce.dataset.k = cap.text; }
      ce.style.opacity = String(Math.min(clamp((u - cap.at) / 0.25, 0, 1), clamp((cap.to - u) / 0.25, 0, 1))); } else ce.style.opacity = '0';
    await new Promise((r) => requestAnimationFrame(() => r()));
    return true;
  },
};
