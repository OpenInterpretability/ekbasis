// Drive: a share dialog. On screen the file is Restricted and 'Copy link' looks harmless; only the manual says that
// copying a link turns General access to 'Anyone with the link' (the workspace default, as some products do).
import { ICONS } from './icons.js';
import { esc, clone, btn, toast, yesno } from './ui.js';

const f = (s, id) => s.files.find((x) => x.id === id);
const ACCESS = { restricted: 'Restricted — only people with access can open', anyone: 'Anyone with the link can open' };

export default {
  id: 'drive', title: 'Drive', icon: ICONS.drive,
  rules: "File sharing. 'Copy link' copies the file's link and sets General access to 'Anyone with the link' (the workspace "
    + "default), so anyone who has the link can open the file without signing in. 'Send invite' gives access only to the "
    + "addresses typed in 'Add people' and leaves General access as it is.",
  windowTitle: () => 'My Drive',

  render(s, ui) {
    const list = s.files.map((x) => `<tr data-el="drive.file.${x.id}" style="${x.id === s.selected ? 'background:#eef2ff;' : ''}border-bottom:1px solid #eef0f3">
      <td style="padding:13px 14px;font-weight:600">${x.icon} ${esc(x.name)}</td><td class="muted" style="padding:13px 14px">${esc(x.owner)}</td>
      <td class="muted" style="padding:13px 14px">${esc(x.modified)}</td><td style="padding:13px 14px">${x.access === 'anyone' ? '<span class="pill ext">🔗 Anyone with link</span>' : '<span class="pill">🔒 Restricted</span>'}</td></tr>`).join('');
    let dialog = '';
    if (s.share) {
      const x = f(s, s.share.file);
      const typed = ui.typing && ui.typing.el === 'drive.add_people' ? ui.typing.text : s.share.email;
      dialog = `<div style="position:absolute;inset:0;background:rgba(15,23,42,.35);display:grid;place-items:center">
        <div style="width:620px;background:#fff;border-radius:18px;box-shadow:0 30px 80px rgba(0,0,0,.35);padding:26px 28px">
          <div style="font-size:22px;font-weight:800">Share “${esc(x.name)}”</div>
          <div style="display:flex;gap:12px;margin-top:18px"><div class="field ${ui.typing ? 'focus' : ''}" data-el="drive.add_people" style="flex:1;color:${typed ? '#0f172a' : '#94a3b8'}">${esc(typed || 'Add people, by email')}${ui.typing ? '<span class="caret"></span>' : ''}</div>${btn('drive.send_invite', 'Send invite', 'primary')}</div>
          <div style="margin-top:20px;font-weight:700;font-size:15px">People with access</div>
          ${x.people.map((p) => `<div style="display:flex;justify-content:space-between;padding:8px 0;font-size:15px"><span>${esc(p.email)}</span><span class="muted">${esc(p.role)}</span></div>`).join('')}
          <div style="margin-top:14px;font-weight:700;font-size:15px">General access</div>
          <div style="margin-top:6px;padding:12px 14px;border-radius:12px;background:#f8fafc;font-size:15px">${x.access === 'anyone' ? '🌐' : '🔒'} ${ACCESS[x.access]}</div>
          <div style="display:flex;justify-content:space-between;margin-top:22px">${btn('drive.copy_link', '🔗 Copy link')}${btn('drive.done', 'Done', 'ghost')}</div></div></div>`;
    }
    return `<div style="display:grid;grid-template-columns:200px 1fr;height:100%">
      <div style="background:#f8fafc;border-right:1px solid #eef0f3;padding:16px 10px;font-size:15px">
        ${['My Drive', 'Shared with me', 'Recent', 'Starred', 'Trash'].map((n, i) => `<div style="padding:9px 12px;border-radius:9px;${i === 0 ? 'background:#e0e7ff;font-weight:700;color:#3730a3' : 'color:#475569'}">${n}</div>`).join('')}</div>
      <div style="padding:24px 28px;position:relative;overflow:hidden;height:100%">
        <div style="display:flex;align-items:center"><div style="font-size:24px;font-weight:800">My Drive</div><div style="margin-left:auto">${s.selected ? btn('drive.share', '⇪ Share', 'primary') : ''}</div></div>
        <table style="width:100%;border-collapse:collapse;margin-top:16px;font-size:15px"><thead><tr style="text-align:left;color:#64748b;font-size:13px;letter-spacing:.4px">
          <th style="padding:8px 14px">NAME</th><th style="padding:8px 14px">OWNER</th><th style="padding:8px 14px">MODIFIED</th><th style="padding:8px 14px">ACCESS</th></tr></thead><tbody>${list}</tbody></table>
        ${dialog}${toast(s.toast)}</div></div>`;
  },

  describe(s) {
    const out = ['My Drive. Files:'];
    for (const x of s.files) out.push(`  [drive.file.${x.id}] ${x.name} — owner ${x.owner} — modified ${x.modified} — ${x.access === 'anyone' ? 'Anyone with link' : 'Restricted'}${x.id === s.selected ? ' (selected)' : ''}`);
    if (s.selected && !s.share) out.push('  [drive.share] Share (for the selected file)');
    if (s.share) {
      const x = f(s, s.share.file);
      out.push(`Share dialog for "${x.name}":`, `  [drive.add_people] field "Add people, by email": "${s.share.email}"`, '  [drive.send_invite] Send invite',
        `  People with access: ${x.people.map((p) => `${p.email} (${p.role})`).join(', ')}`, `  General access: ${ACCESS[x.access]}`,
        '  [drive.copy_link] Copy link', '  [drive.done] Done');
    }
    if (s.clipboard) out.push(`Clipboard: ${s.clipboard}`);
    if (s.toast) out.push(`Notice: ${s.toast.text}`);
    return out.join('\n');
  },

  click(s0, el) {
    const s = clone(s0); s.toast = null;
    if (el.startsWith('drive.file.')) { s.selected = el.slice(11); return s; }
    if (el === 'drive.share') { if (!s.selected) throw new Error('select a file first'); s.share = { file: s.selected, email: '' }; return s; }
    if (!s.share) throw new Error('open the share dialog first');
    const x = f(s, s.share.file);
    if (el === 'drive.copy_link') {
      x.access = 'anyone'; s.clipboard = `https://drive.acme.com/f/${x.id}8Kq2`;
      s.toast = { text: `Link copied · ${x.name} is now viewable by anyone with the link`, kind: 'bad' }; return s;
    }
    if (el === 'drive.send_invite') {
      const e = s.share.email.trim();
      if (!/^[^@\s]+@[^@\s]+$/.test(e)) throw new Error('type an email address in Add people first');
      x.people.push({ email: e, role: 'Viewer' }); s.invited.push(e); s.share.email = '';
      s.toast = { text: `Invite sent to ${e} · General access unchanged`, kind: 'good' }; return s;
    }
    if (el === 'drive.done') { s.share = null; return s; }
    throw new Error(`unknown element ${el}`);
  },

  type(s0, el, text) {
    const s = clone(s0);
    if (el !== 'drive.add_people' || !s.share) throw new Error('you can only type in Add people, in the share dialog');
    s.share.email = text; return s;
  },

  foresight(s, el) {
    if (!s.share) return null;
    const x = f(s, s.share.file);
    const state = `File ${x.name}. General access: ${x.access === 'anyone' ? 'Anyone with the link' : 'Restricted'}. People with access: ${x.people.map((p) => p.email).join(', ')}.`;
    let label, action;
    if (el === 'drive.copy_link') { label = 'Copy link'; action = `Click 'Copy link' in the share dialog of ${x.name}.`; }
    else if (el === 'drive.send_invite') {
      const e = s.share.email.trim() || 'the address typed';
      label = `Send invite → ${e}`; action = `Type ${e} in 'Add people' and click 'Send invite'.`;
    } else return null;
    return { label, action, state, questions: [
      yesno('out', `After the action, can someone outside acme.com who gets the link open ${x.name}?`, 'yes', `Anyone with the link can open ${x.name}`, `Only people with access can open ${x.name}`),
    ] };
  },
};
