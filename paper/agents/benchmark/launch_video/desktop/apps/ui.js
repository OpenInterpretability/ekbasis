// Small helpers shared by the demo apps (not an app itself).
export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const clone = (o) => JSON.parse(JSON.stringify(o));
export const btn = (el, label, kind = '') => `<span class="btn ${kind}" data-el="${esc(el)}">${label}</span>`;
export const toast = (t) => (t ? `<div class="toast ${t.kind || ''}">${esc(t.text)}</div>` : '');
export const side = (items, active) => `<div style="background:#f8fafc;border-right:1px solid #eef0f3;padding:16px 10px;font-size:15px;height:100%">${
  items.map(([id, label, extra]) => `<div style="padding:9px 12px;border-radius:9px;${id === active ? 'background:#e0e7ff;font-weight:700;color:#3730a3;' : 'color:#475569;'}display:flex;justify-content:space-between">${esc(label)}<span>${extra ?? ''}</span></div>`).join('')}</div>`;
export const yesno = (key, text, bad, yes, no) => ({ key, text, options: ['yes', 'no'], bad, say: { yes, no } });
