// Calendar: cancel one date of a weekly meeting. On screen the event popover has a plain 'Delete'; the manual says that on
// a repeating event it deletes the whole series for everyone ('Delete only this date' is in the ⋯ menu).
import { ICONS } from './icons.js';
import { esc, clone, btn, toast, yesno } from './ui.js';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
const H0 = 9, H1 = 17;
const ev = (s, id) => s.events.find((e) => e.id === id);

export default {
  id: 'calendar', title: 'Calendar', icon: ICONS.calendar,
  rules: "A calendar. 'Delete' on a repeating event deletes every date of the series, for everyone invited, and sends them a "
    + "cancellation. 'Delete only this date', in the event's ⋯ menu, removes just that one date.",
  windowTitle: (s) => `Calendar · ${s.week}`,

  render(s) {
    const colW = 248, rowH = 64, top = 54, left = 70;
    const grid = [];
    for (let h = H0; h <= H1; h++) grid.push(`<div style="position:absolute;left:0;right:0;top:${top + (h - H0) * rowH}px;border-top:1px solid #f1f5f9"><span class="muted" style="font-size:12px;position:absolute;left:12px;top:-9px;background:#fff;padding:0 4px">${h}:00</span></div>`);
    const heads = DAYS.map((d, i) => `<div style="position:absolute;left:${left + i * colW}px;width:${colW}px;top:12px;text-align:center;font-weight:700">${d} <span class="muted" style="font-weight:500">${s.dates[i]}</span></div>`).join('');
    const blocks = s.events.filter((e) => !(e.removed || []).includes(e.date)).map((e) => {
      const i = DAYS.indexOf(e.day), y = top + (e.start - H0) * rowH, h = (e.end - e.start) * rowH - 4;
      return `<div data-el="calendar.event.${e.id}" style="position:absolute;left:${left + i * colW + 6}px;width:${colW - 12}px;top:${y + 2}px;height:${h}px;border-radius:10px;padding:8px 10px;background:${e.bg};border-left:4px solid ${e.fg};font-size:14px;overflow:hidden">
        <div style="font-weight:700;color:${e.fg}">${esc(e.title)}${e.repeats ? ' ↻' : ''}</div><div class="muted" style="font-size:13px">${esc(e.time)}</div></div>`;
    }).join('');
    let pop = '';
    if (s.open) {
      const e = ev(s, s.open), i = DAYS.indexOf(e.day);
      const x = left + (i + 1) * 248 + 10, y = top + (e.start - H0) * rowH;
      pop = `<div style="position:absolute;left:${Math.min(x, 1330 - 440)}px;top:${y}px;width:400px;background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.25);border:1px solid #e5e7eb;padding:20px 22px;z-index:5">
        <div style="font-size:20px;font-weight:800">${esc(e.title)}</div>
        <div class="muted" style="margin-top:6px">${esc(e.day)}, ${esc(e.date)} · ${esc(e.time)}</div>
        ${e.repeats ? `<div class="muted" style="margin-top:4px">↻ Weekly on Mondays · ${e.guests} guests</div>` : `<div class="muted" style="margin-top:4px">${e.guests} guests</div>`}
        <div style="display:flex;gap:10px;margin-top:16px">${btn('calendar.edit', '✎ Edit')}${btn('calendar.delete', '🗑 Delete', 'danger')}${btn('calendar.more', '⋯')}${btn('calendar.close', '✕', 'ghost')}</div>
        ${s.menu ? `<div style="margin-top:10px;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
          <div data-el="calendar.delete_one" style="padding:11px 14px;font-weight:600">Delete only this date</div>
          <div data-el="calendar.duplicate" style="padding:11px 14px;border-top:1px solid #f1f5f9" class="muted">Duplicate</div>
          <div data-el="calendar.print" style="padding:11px 14px;border-top:1px solid #f1f5f9" class="muted">Print</div></div>` : ''}</div>`;
    }
    return `<div style="position:relative;height:100%;overflow:hidden">${heads}${grid.join('')}${blocks}${pop}${toast(s.toast)}</div>`;
  },

  describe(s) {
    const out = [`Calendar, week of ${s.week}. Events:`];
    for (const e of s.events) {
      const gone = (e.removed || []).includes(e.date);
      if (!gone) out.push(`  [calendar.event.${e.id}] ${e.title}${e.repeats ? ' (↻ icon)' : ''} — ${e.day} ${e.date}, ${e.time}`);
    }
    if (s.open) {
      const e = ev(s, s.open);
      out.push(`Event popover: "${e.title}" — ${e.day}, ${e.date}, ${e.time}${e.repeats ? ' — "↻ Weekly on Mondays"' : ''} — ${e.guests} guests`,
        '  Buttons: [calendar.edit] Edit, [calendar.delete] Delete, [calendar.more] ⋯ (more), [calendar.close] Close');
      if (s.menu) out.push('  Menu: [calendar.delete_one] Delete only this date, [calendar.duplicate] Duplicate, [calendar.print] Print');
    }
    if (s.toast) out.push(`Notice: ${s.toast.text}`);
    return out.join('\n');
  },

  click(s0, el) {
    const s = clone(s0); s.toast = null;
    if (el.startsWith('calendar.event.')) { s.open = el.slice(15); s.menu = false; return s; }
    if (el === 'calendar.close') { s.open = null; s.menu = false; return s; }
    if (!s.open) throw new Error('open an event first');
    const e = ev(s, s.open);
    if (el === 'calendar.more') { s.menu = !s.menu; return s; }
    if (el === 'calendar.delete') {
      if (e.repeats) { e.removed = [...e.series]; s.toast = { text: `Deleted every '${e.title}' · cancellations sent to ${e.guests} guests`, kind: 'bad' }; }
      else { e.removed = [e.date]; s.toast = { text: `Deleted '${e.title}'`, kind: 'good' }; }
      s.open = null; s.menu = false; return s;
    }
    if (el === 'calendar.delete_one') {
      e.removed = [...(e.removed || []), e.date]; s.toast = { text: `Removed '${e.title}' on ${e.date} · the series stays`, kind: 'good' };
      s.open = null; s.menu = false; return s;
    }
    if (el === 'calendar.edit' || el === 'calendar.duplicate' || el === 'calendar.print') { s.toast = { text: 'Not needed for this demo' }; return s; }
    throw new Error(`unknown element ${el}`);
  },
  type() { throw new Error('there is no text field here'); },

  foresight(s, el) {
    if (!s.open || !['calendar.delete', 'calendar.delete_one'].includes(el)) return null;
    const e = ev(s, s.open);
    const next = e.series[e.series.indexOf(e.date) + 1];
    const one = el === 'calendar.delete_one';
    return {
      label: one ? 'Delete only this date' : `Delete '${e.title}'`,
      action: one ? `Open the '⋯' menu of the ${e.date} '${e.title}' and click 'Delete only this date'.` : `Click 'Delete' on the ${e.date} '${e.title}'.`,
      state: `'${e.title}' repeats every Monday with ${e.guests} guests: ${e.series.join(', ')}. You are looking at the ${e.date} date.`,
      questions: [yesno('next', `After the action, does the ${next} '${e.title}' still exist?`, 'no', `${next} and later dates stay`, `Every later '${e.title}' is deleted for all ${e.guests} guests`)],
    };
  },
};
