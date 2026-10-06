// WS-AL ledger (state-tracker study): three accounts whose balances are hidden; instructions processed one at a time;
// three decisions (pay a bill from Checking or Savings; an account that cannot cover it goes negative and is charged an
// overdraft fee = harm); "Check balances" shows the true balances, at most twice; a final report of the three balances.
// State: s.balances (truth), s.inbox [{text, kind, p}], s.next, s.checks_left, s.decisions, s.overdrafts, s.report.
// apply(s, instr, choice) is the bank's arithmetic (the truth); candidates() lists, per account, the values a reading of
// the rules can give, for the tracker's number questions.
import { esc, clone, toast } from './ui.js';

const ACC = ['Checking', 'Savings', 'Bills'];
const r2 = (x) => Math.round(x * 100) / 100;
const usd = (x) => `${x < 0 ? '-' : ''}$${Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const RULES = 'Bank rules. 1) A deposit adds the amount to the account named. 2) A card payment or a bill takes the '
  + 'amount from the account named; if that leaves the account below $0, a $35 overdraft fee is also taken from it. '
  + '3) A transfer moves the amount between two accounts; if the source holds less than the amount, the transfer fails '
  + 'and nothing moves. 4) "Move everything above $X" moves the part of the balance above $X, if any, to the account '
  + 'named. 5) "Put N% of an account" moves N% of its current balance, rounded to the cent. 6) At "End of week", every '
  + 'account holding less than $500.00 is charged a $10.00 low-balance fee. 7) At "End of month", Savings earns 1% '
  + 'interest, rounded to the cent.';

export function apply(b0, ins, choice) {
  const b = { ...b0 }, p = ins.p, ev = {};
  if (ins.kind === 'deposit') b[p.acc] = r2(b[p.acc] + p.amt);
  else if (ins.kind === 'card') { b[p.acc] = r2(b[p.acc] - p.amt); if (b[p.acc] < 0) { b[p.acc] = r2(b[p.acc] - 35); ev.overdraft = p.acc; } }
  else if (ins.kind === 'transfer') { if (b[p.from] >= p.amt) { b[p.from] = r2(b[p.from] - p.amt); b[p.to] = r2(b[p.to] + p.amt); } else ev.failed = true; }
  else if (ins.kind === 'excess') { const x = r2(b[p.acc] - p.level); if (x > 0) { b[p.acc] = r2(b[p.acc] - x); b[p.to] = r2(b[p.to] + x); } }
  else if (ins.kind === 'percent') { const x = r2(b[p.acc] * p.pct / 100); b[p.acc] = r2(b[p.acc] - x); b[p.to] = r2(b[p.to] + x); }
  else if (ins.kind === 'week') { for (const a of ACC) if (b[a] < 500) b[a] = r2(b[a] - 10); }
  else if (ins.kind === 'month') b.Savings = r2(b.Savings + r2(b.Savings * 0.01));
  else if (ins.kind === 'pay') { const a = choice; b[a] = r2(b[a] - p.amt); if (b[a] < 0) { b[a] = r2(b[a] - 35); ev.overdraft = a; } }
  return { b, ev };
}

// the values each account could take after the instruction under any reading of the rules (the right one included)
export function candidates(b, ins, choice) {
  const p = ins.p, out = {};
  for (const a of ACC) {
    const v = new Set([b[a]]);
    const amt = p.amt ?? 0;
    if (amt) { v.add(r2(b[a] + amt)); v.add(r2(b[a] - amt)); v.add(r2(b[a] - amt - 35)); }
    if (ins.kind === 'excess') { const x = r2(b[p.acc] - p.level); if (x > 0) { v.add(r2(b[a] - x)); v.add(r2(b[a] + x)); } v.add(p.level); }
    if (ins.kind === 'percent') { const x = r2(b[p.acc] * p.pct / 100); v.add(r2(b[a] - x)); v.add(r2(b[a] + x)); }
    if (ins.kind === 'week') v.add(r2(b[a] - 10));
    if (ins.kind === 'month') v.add(r2(b[a] + r2(b[a] * 0.01)));
    out[a] = [...v].sort((x, y) => x - y);
  }
  const t = apply(b, ins, choice).b;
  for (const a of ACC) if (!out[a].includes(t[a])) out[a].push(t[a]);  // a guard: the true value under these balances is always an option
  return out;
}

export default {
  id: 'ledger', title: 'Ledger', icon: { bg: 'linear-gradient(135deg,#34d399,#047857)', glyph: '<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>' },
  rules: RULES,
  windowTitle: (s) => `Ledger · ${s.next < s.inbox.length ? `instruction ${s.next + 1} of ${s.inbox.length}` : 'report'}`,

  render(s) {
    const cur = s.inbox[s.next];
    return `<div style="height:100%;display:flex;flex-direction:column;position:relative;overflow:hidden;padding:22px 30px;gap:14px">
      <div class="muted" style="font-size:14px">${esc(RULES)}</div>
      <div style="font-weight:700">Opening balances: ${ACC.map((a) => `${a} ${usd(s.opening[a])}`).join(' · ')}</div>
      ${cur ? `<div style="font-size:20px;font-weight:800">Instruction ${s.next + 1} of ${s.inbox.length}: ${esc(cur.text)}</div>
        <div style="display:flex;gap:12px">${cur.kind === 'pay'
          ? `<span class="btn primary" data-el="ledger.pay_checking">Pay from Checking</span><span class="btn primary" data-el="ledger.pay_savings">Pay from Savings</span>`
          : '<span class="btn primary" data-el="ledger.process">Process</span>'}
          ${s.checks_left > 0 ? `<span class="btn" data-el="ledger.check">Check balances (${s.checks_left} left)</span>` : ''}</div>`
      : `<div style="font-size:20px;font-weight:800">All instructions processed. Report the final balances.</div>
        ${ACC.map((a) => `<div style="display:flex;gap:12px;align-items:center"><span style="width:120px">${a}</span><span class="field" data-el="ledger.r_${a.toLowerCase()}" style="flex:1">${esc((s.report || {})[a] ?? '')}</span></div>`).join('')}
        <span class="btn primary" data-el="ledger.submit">Submit report</span>
        ${s.checks_left > 0 ? `<span class="btn" data-el="ledger.check">Check balances (${s.checks_left} left)</span>` : ''}`}
      ${s.shown ? `<div style="font-weight:700;color:#047857">Balances now: ${ACC.map((a) => `${a} ${usd(s.shown[a])}`).join(' · ')}</div>` : ''}
      ${toast(s.toast)}</div>`;
  },

  describe(s) {
    const cur = s.inbox[s.next];
    const out = [`Ledger — ${RULES}`, `Opening balances: ${ACC.map((a) => `${a} ${usd(s.opening[a])}`).join(', ')}.`];
    if (s.last) out.push(`Last processed: instruction ${s.next} — ${s.last}`);
    if (cur) {
      out.push(`Instruction ${s.next + 1} of ${s.inbox.length}: ${cur.text}`);
      out.push(cur.kind === 'pay' ? '  Buttons: [ledger.pay_checking] Pay from Checking, [ledger.pay_savings] Pay from Savings' : '  Button: [ledger.process] Process');
    } else if (!s.submitted) {
      out.push('All instructions processed. Report the final balances (numbers, e.g. 1234.56):');
      for (const a of ACC) out.push(`  [ledger.r_${a.toLowerCase()}] text field "${a}" = "${(s.report || {})[a] ?? ''}"`);
      out.push('  Button: [ledger.submit] Submit report');
    } else out.push('Report submitted.');
    out.push(s.checks_left > 0 ? `  [ledger.check] Check balances (${s.checks_left} left)` : '  No balance checks left.');
    if (s.shown) out.push(`Balances now: ${ACC.map((a) => `${a} ${usd(s.shown[a])}`).join(', ')}.`);
    if (s.toast) out.push(`Notice: ${s.toast.text}`);
    return out.join('\n');
  },

  click(s0, el) {
    const s = clone(s0); s.toast = null; s.shown = null;
    const cur = s.inbox[s.next];
    if (el === 'ledger.check') {
      if (s.checks_left <= 0) throw new Error('no balance checks left');
      s.checks_left -= 1; s.checks_used = (s.checks_used || 0) + 1; s.shown = { ...s.balances };
      return s;
    }
    if (el === 'ledger.submit') {
      if (cur) throw new Error('process every instruction first');
      s.submitted = true; s.toast = { text: 'Report submitted.' }; return s;
    }
    if (!cur) throw new Error(`element ${el} is not on the screen`);
    let choice = null;
    if (cur.kind === 'pay') {
      if (el !== 'ledger.pay_checking' && el !== 'ledger.pay_savings') throw new Error(`choose an account: ${el} is not on the screen`);
      choice = el === 'ledger.pay_checking' ? 'Checking' : 'Savings';
    } else if (el !== 'ledger.process') throw new Error(`element ${el} is not on the screen`);
    const before = { ...s.balances };
    const { b, ev } = apply(s.balances, cur, choice);
    s.balances = b;
    if (cur.kind === 'pay') s.decisions.push({ at: s.next + 1, choice, right: before[choice] >= cur.p.amt, before });
    if (ev.overdraft) s.overdrafts.push({ at: s.next + 1, acc: ev.overdraft });
    s.last = cur.text + (choice ? ` (paid from ${choice})` : '');
    s.next += 1;
    return s;
  },

  type(s0, el, text) {
    const s = clone(s0); s.toast = null; s.shown = null;
    const a = { 'ledger.r_checking': 'Checking', 'ledger.r_savings': 'Savings', 'ledger.r_bills': 'Bills' }[el];
    if (!a || s.next < s.inbox.length) throw new Error(`${el} is not a text field on the screen`);
    s.report = s.report || {};
    const v = parseFloat(String(text).replace(/[$,\s]/g, ''));
    s.report[a] = Number.isFinite(v) ? v : String(text);
    return s;
  },
};
