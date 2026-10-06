// WS-AL: one data-driven engine for multi-screen apps (settings, admin console, trips, orders, cloud drive). The scenario
// world holds everything: s.screens {sid: {title, text?, items: [item]}}, s.vars {name: display value}, s.names
// {var: label in the state text}, s.manual (the app's manual: what Ekbasis reads; the agent sees only the screens),
// s.goal (the task), s.checks {goal: [...], harm: [...]} (the typed questions asked about a consequential click).
// item: {id, label ('{var}' is filled in), go?: sid, set?: {var: value}, toggle?: var (two values in s.toggles[var]),
//        also?: {value: {var: value}} (side effects when the toggle takes that value), back?: true (return after acting),
//        field?: var (type_text sets it), cons?: true (consequential: foresee/advise ask the checks), toast?: text}
// Clicking 'back' returns to the previous screen. click/type are pure (a new state); foresight/advise only describe.
import { esc, clone, toast, yesno } from './ui.js';

const fill = (t, v) => String(t).replace(/\{(\w+)\}/g, (_, k) => (v[k] ?? `{${k}}`));
const itemsOf = (s) => {
  const sc = s.screens[s.screen];
  const items = sc.items.map((it) => ({ ...it, label: fill(it.label, s.vars) }));
  if (s.history.length) items.push({ id: 'back', label: 'Back', nav: true });
  return items;
};
const kind = (it) => (it.id === 'back' || ((it.go || it.back) && !it.set && !it.toggle && !it.field) ? 'nav' : it.field ? 'field' : 'action');

export function makeFlowApp({ id, title, icon }) {
  const elOf = (it) => `${id}.${it.id}`;
  const find = (s, el) => {
    const it = itemsOf(s).find((x) => elOf(x) === el);
    if (!it) throw new Error(`element ${el} is not on the ${s.screens[s.screen].title} screen`);
    return it;
  };
  const stateText = (s) => `The ${title} app is on the "${s.screens[s.screen].title}" screen. Current values: `
    + Object.entries(s.names).map(([k, lab]) => `${lab}: ${s.vars[k]}`).join('; ') + '.';
  const checksFor = (s) => [
    ...(s.checks.goal || []).map((q) => ({ key: q.key, text: q.text, options: ['yes', 'no'], bad: '__none__', goal: q.want,
      say: { yes: q.yes || `${q.text.replace(/^After the action, /, '').replace(/\?$/, '')}: yes`, no: q.no || `${q.text.replace(/^After the action, /, '').replace(/\?$/, '')}: no` } })),
    ...(s.checks.harm || []).map((q) => yesno(q.key, q.text, q.bad || 'yes',
      q.yes || `${q.text.replace(/^After the action, /, '').replace(/\?$/, '')}: yes`, q.no || `${q.text.replace(/^After the action, /, '').replace(/\?$/, '')}: no`)),
  ];
  return {
    id, title, icon,
    rules: '',
    windowTitle: (s) => `${title} · ${s.screens[s.screen].title}`,

    render(s) {
      const sc = s.screens[s.screen];
      const rows = itemsOf(s).map((it) => (it.field
        ? `<div style="display:flex;align-items:center;gap:14px;padding:10px 0"><span style="width:220px;color:#475569">${esc(it.label.split(':')[0])}</span><span class="field" data-el="${elOf(it)}" style="flex:1">${esc(s.vars[it.field])}</span></div>`
        : `<div data-el="${elOf(it)}" style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;margin:6px 0;border-radius:12px;border:1px solid #e5e7eb;background:${it.id === 'back' ? '#f8fafc' : '#fff'};font-size:17px;cursor:pointer">${esc(it.label)}<span style="color:#94a3b8">${kind(it) === 'nav' && it.id !== 'back' ? '›' : ''}</span></div>`)).join('');
      return `<div style="height:100%;display:flex;flex-direction:column;position:relative;overflow:hidden">
        <div style="padding:18px 28px;border-bottom:1px solid #eef0f3;font-weight:800;font-size:22px">${esc(sc.title)}</div>
        ${sc.text ? `<div class="muted" style="padding:12px 28px 0;font-size:15px">${esc(fill(sc.text, s.vars))}</div>` : ''}
        <div style="padding:10px 28px;overflow:auto">${rows}</div>${toast(s.toast)}</div>`;
    },

    describe(s) {
      const sc = s.screens[s.screen];
      const out = [`${title} — screen "${sc.title}"`];
      if (sc.text) out.push(`  ${fill(sc.text, s.vars)}`);
      for (const it of itemsOf(s)) out.push(it.field ? `  [${elOf(it)}] text field "${it.label.split(':')[0]}" = "${s.vars[it.field]}"` : `  [${elOf(it)}] ${it.label}`);
      if (s.toast) out.push(`Notice: ${s.toast.text}`);
      return out.join('\n');
    },

    click(s0, el) {
      const s = clone(s0); s.toast = null;
      const it = find(s, el);
      if (it.field) throw new Error(`${el} is a text field: use type_text`);
      if (it.id === 'back') { s.screen = s.history.pop(); return s; }
      if (it.set) Object.assign(s.vars, it.set);
      if (it.toggle) {
        const [a, b] = s.toggles[it.toggle]; s.vars[it.toggle] = s.vars[it.toggle] === a ? b : a;
        const side = (it.also || {})[s.vars[it.toggle]]; if (side) Object.assign(s.vars, side);  // e.g. battery saver pauses sync
      }
      if (it.toast) s.toast = { text: fill(it.toast, s.vars) };
      if (it.back && s.history.length) { s.screen = s.history.pop(); return s; }  // e.g. Cancel on a confirmation
      if (it.go && it.go !== s.screen) { s.history.push(s.screen); s.screen = it.go; }
      if (it.home) { s.history = []; s.screen = s.start; }
      return s;
    },

    type(s0, el, text) {
      const s = clone(s0); s.toast = null;
      const it = find(s, el);
      if (!it.field) throw new Error(`${el} is not a text field`);
      s.vars[it.field] = String(text);
      return s;
    },

    foresight(s, el) {
      const it = find(s, el);
      if (kind(it) === 'nav' || !it.cons) return null;
      return { label: it.label, rules: s.manual, state: stateText(s),
        action: it.field ? `Type into the "${it.label.split(':')[0]}" field.` : `Click '${it.label}' on the "${s.screens[s.screen].title}" screen.`,
        questions: checksFor(s) };
    },

    // look-ahead: the actions on the current screen (or the ones the agent names), one choice question over them, and
    // the checks for each consequential one. The stage asks Ekbasis; this only describes.
    advise(s, cands) {
      let items = itemsOf(s).filter((x) => !x.field);
      if (cands && cands.length) items = items.filter((x) => cands.includes(elOf(x)));
      const seen = {};
      const opts = items.map((x) => { const l = seen[x.label] ? `${x.label} (${x.id})` : x.label; seen[x.label] = 1; return { el: elOf(x), label: l, cons: !!x.cons, nav: kind(x) === 'nav' }; });
      return { rules: s.manual, state: stateText(s), goal: s.goal, screen: s.screens[s.screen].title, options: opts,
        actions: Object.fromEntries(items.map((x) => [elOf(x), `Click '${x.label}' on the "${s.screens[s.screen].title}" screen.`])),
        checks: checksFor(s) };
    },
  };
}
