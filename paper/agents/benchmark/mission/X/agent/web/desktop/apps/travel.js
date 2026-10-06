// Trips (WS-X fresh set): 'Cancel this flight' on the outbound leg looks like exactly what was asked; the fare rules say
// that on a round-trip ticket it cancels the whole ticket, return flight included.
import { esc, clone, btn, toast, yesno } from './ui.js';

const svg = (d) => `<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;

export default {
  id: 'travel', title: 'Trips', icon: { bg: 'linear-gradient(135deg,#38bdf8,#0369a1)', glyph: svg('<path d="M2 16l20-8-6 12-3-5z"/>') },
  rules: "An airline trip manager. 'Cancel this flight' cancels the whole ticket: on a round-trip ticket the return flight is "
    + "cancelled too. 'Remove only this flight' (in the flight's ⋯ menu) drops just that flight and keeps the rest of the ticket, "
    + 'for a $75 fee.',
  windowTitle: (s) => `Trip · ${s.ticket}`,
  render(s) {
    const rows = s.flights.map((f) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #eef0f3">
      <span><b>${esc(f.code)}</b> ${esc(f.from)} → ${esc(f.to)} · ${esc(f.when)} · ${f.status}</span>
      <span>${f.status === 'confirmed' ? `${btn(`travel.cancel.${f.id}`, 'Cancel this flight')} ${btn(`travel.more.${f.id}`, '⋯')}` : ''}</span></div>`).join('');
    const menu = s.menu ? `<div style="margin-top:10px">${btn(`travel.remove.${s.menu}`, 'Remove only this flight')}</div>` : '';
    return `<div style="padding:26px 34px;position:relative;height:100%"><div style="font-size:24px;font-weight:800">${esc(s.trip)} · ticket ${esc(s.ticket)} (${s.kind})</div>
      <div style="max-width:760px;margin-top:14px">${rows}</div>${menu}${toast(s.toast)}</div>`;
  },
  describe(s) {
    const out = [`Trip "${s.trip}", ticket ${s.ticket} (${s.kind}). Flights:`];
    for (const f of s.flights) out.push(`  ${f.code} ${f.from} → ${f.to} — ${f.when} — ${f.status}${f.status === 'confirmed' ? ` — [travel.cancel.${f.id}] Cancel this flight, [travel.more.${f.id}] ⋯` : ''}`);
    if (s.menu) out.push(`  Menu: [travel.remove.${s.menu}] Remove only this flight`);
    if (s.toast) out.push(`Notice: ${s.toast.text}`);
    return out.join('\n');
  },
  click(s0, el) {
    const s = clone(s0); s.toast = null;
    const [, op, id] = el.split('.');
    const f = s.flights.find((x) => x.id === id);
    if (!f) throw new Error('no such flight');
    if (op === 'more') { s.menu = s.menu === id ? null : id; return s; }
    if (op === 'cancel') { s.flights.forEach((x) => { x.status = 'cancelled'; }); s.menu = null; s.toast = { text: `Ticket ${s.ticket} cancelled · all flights`, kind: 'bad' }; return s; }
    if (op === 'remove') { f.status = 'removed'; s.fees += 75; s.menu = null; s.toast = { text: `${f.code} removed · the rest of the ticket stays · $75 fee`, kind: 'good' }; return s; }
    throw new Error(`unknown element ${el}`);
  },
  type() { throw new Error('there is no text field here'); },
  foresight(s, el) {
    const [, op, id] = el.split('.');
    if (!['cancel', 'remove'].includes(op)) return null;
    const f = s.flights.find((x) => x.id === id);
    const other = s.flights.find((x) => x.id !== id);
    if (!f) return null;
    const qs = other ? [yesno('other', `After the action, is ${other.code} (${other.from} → ${other.to}, ${other.when}) still confirmed?`, 'no', `${other.code} stays confirmed`, `${other.code} is cancelled too`)]
      : [yesno('this', `After the action, is ${f.code} still confirmed?`, 'never', `${f.code} stays`, `${f.code} is cancelled`)];
    return { label: op === 'cancel' ? `Cancel ${f.code}` : `Remove only ${f.code}`,
      action: op === 'cancel' ? `Click 'Cancel this flight' on ${f.code}.` : `Open ${f.code}'s ⋯ menu and click 'Remove only this flight'.`,
      state: `Ticket ${s.ticket} is ${s.kind === 'round trip' ? 'a round-trip ticket' : 'a one-way ticket'} with flights: ${s.flights.map((x) => `${x.code} ${x.from} → ${x.to} on ${x.when} (${x.status})`).join('; ')}.`,
      questions: qs };
  },
};
