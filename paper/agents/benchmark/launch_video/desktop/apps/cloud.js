// Cloud console: servers and their disks. On screen, 'Release' reads like the cheapest option ("stops all billing");
// only the console's manual says that it deletes the server's disk with it.
import { ICONS } from './icons.js';
import { esc, clone, btn, toast, yesno } from './ui.js';

const money = (n) => `$${n.toLocaleString('en-US')}`;
const sel = (s) => s.servers.find((x) => x.id === s.selected);

export default {
  id: 'cloud', title: 'Cloud Console', icon: ICONS.cloud,
  rules: "A cloud console. 'Pause' stops a server: compute billing stops, its disk is kept (billed at the storage price) and the "
    + "server can be resumed later. 'Release' deletes the server and its attached disk permanently, so all billing stops. A snapshot "
    + 'is a separate copy of a disk and survives a release.',
  windowTitle: (s) => `Compute · ${s.project}`,

  render(s) {
    const x = sel(s);
    const rows = s.servers.map((v) => `<tr data-el="cloud.server.${v.id}" style="${v.id === s.selected ? 'background:#eef2ff;' : ''}border-bottom:1px solid #eef0f3">
      <td style="padding:14px 16px;font-weight:700">${esc(v.name)}</td>
      <td style="padding:14px 16px"><span class="pill" style="${v.status === 'running' ? 'background:#dcfce7;color:#15803d' : 'background:#f1f5f9;color:#475569'}">● ${esc(v.status)}</span></td>
      <td style="padding:14px 16px" class="muted">${esc(v.type)}</td><td style="padding:14px 16px" class="muted">${esc(v.disk)}</td>
      <td style="padding:14px 16px;text-align:right;font-weight:600">${v.status === 'running' ? `${money(v.cost)}/mo` : '<span class="muted">storage only</span>'}</td></tr>`).join('');
    const panel = x ? `<div style="margin-top:22px;border:1px solid #e5e7eb;border-radius:14px;padding:20px 22px">
        <div style="display:flex;align-items:baseline;gap:14px"><span style="font-size:22px;font-weight:800">${esc(x.name)}</span><span class="muted">${esc(x.role || '')}</span>
          <span style="margin-left:auto;font-size:15px" class="muted">This month so far <b style="color:#0f172a">${money(Math.round(x.cost * 0.13))}</b></span></div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:18px">
          <div style="border:1px solid #eef0f3;border-radius:12px;padding:14px 16px">${btn('cloud.pause', '⏸ Pause')}<div class="muted" style="font-size:14px;margin-top:10px">Compute billing stops while paused</div></div>
          <div style="border:1px solid #eef0f3;border-radius:12px;padding:14px 16px">${btn('cloud.release', '⏏ Release')}<div class="muted" style="font-size:14px;margin-top:10px">Stops all billing for this server</div></div>
          <div style="border:1px solid #eef0f3;border-radius:12px;padding:14px 16px">${btn('cloud.snapshot', '◎ Snapshot')}<div class="muted" style="font-size:14px;margin-top:10px">Copy of the disk · $0.05/GB-month</div></div>
        </div></div>` : '<div class="muted" style="margin-top:22px">Select a server.</div>';
    return `<div style="display:grid;grid-template-columns:200px 1fr;height:100%">
      <div style="background:#0f172a;color:#cbd5e1;padding:18px 12px;font-size:15px">
        <div style="font-weight:800;color:#fff;margin:0 8px 16px">☁ ${esc(s.project)}</div>
        ${['Compute', 'Storage', 'Snapshots', 'Networking', 'Billing'].map((n, i) => `<div style="padding:9px 12px;border-radius:9px;${i === 0 ? 'background:#1e293b;color:#fff;font-weight:700' : ''}">${n}${n === 'Snapshots' ? `<span style="float:right">${s.snapshots.length}</span>` : ''}</div>`).join('')}</div>
      <div style="padding:24px 28px;position:relative;overflow:hidden">
        <div style="display:flex;align-items:center"><div style="font-size:24px;font-weight:800">Servers</div><div class="muted" style="margin-left:14px">${s.servers.length} in ${esc(s.region)}</div>
          <div style="margin-left:auto;font-size:15px" class="muted">Projected this month <b style="color:#0f172a">${money(s.servers.filter((v) => v.status === 'running').reduce((a, v) => a + v.cost, 0))}</b></div></div>
        <table style="width:100%;border-collapse:collapse;margin-top:16px;font-size:15px"><thead><tr style="text-align:left;color:#64748b;font-size:13px;letter-spacing:.4px">
          <th style="padding:8px 16px">NAME</th><th style="padding:8px 16px">STATUS</th><th style="padding:8px 16px">TYPE</th><th style="padding:8px 16px">DISK</th><th style="padding:8px 16px;text-align:right">COST</th></tr></thead>
          <tbody>${rows}</tbody></table>${panel}${toast(s.toast)}</div></div>`;
  },

  describe(s) {
    const out = [`Cloud console, project ${s.project}, region ${s.region}. Servers:`];
    for (const v of s.servers) out.push(`  [cloud.server.${v.id}] ${v.name} — ${v.status} — ${v.type} — disk ${v.disk} — ${v.status === 'running' ? `$${v.cost}/month` : 'storage only'}${v.id === s.selected ? ' (selected)' : ''}`);
    const x = sel(s);
    if (x) out.push(`Selected: ${x.name} (${x.role || 'server'}). Actions:`, '  [cloud.pause] Pause — "Compute billing stops while paused"',
      '  [cloud.release] Release — "Stops all billing for this server"', '  [cloud.snapshot] Snapshot — "Copy of the disk · $0.05/GB-month"');
    out.push(`Snapshots: ${s.snapshots.length ? s.snapshots.join(', ') : 'none'}`);
    if (s.toast) out.push(`Notice: ${s.toast.text}`);
    return out.join('\n');
  },

  click(s0, el) {
    const s = clone(s0); s.toast = null;
    if (el.startsWith('cloud.server.')) { s.selected = el.slice(13); return s; }
    const x = sel(s);
    if (!x) throw new Error('select a server first');
    if (el === 'cloud.pause') { x.status = 'paused'; s.toast = { text: `${x.name} paused · disk kept`, kind: 'good' }; return s; }
    if (el === 'cloud.release') {
      s.servers = s.servers.filter((v) => v.id !== x.id); s.released.push(x.name); s.selected = null;
      s.toast = { text: `${x.name} released · disk ${x.disk.split(' ')[0]} deleted`, kind: 'bad' }; return s;
    }
    if (el === 'cloud.snapshot') { s.snapshots.push(`${x.name}-snap-1`); s.toast = { text: `Snapshot of ${x.disk.split(' ')[0]} created`, kind: 'good' }; return s; }
    throw new Error(`unknown element ${el}`);
  },
  type() { throw new Error('there is no text field here'); },

  foresight(s, el) {
    const x = sel(s);
    if (!x || !['cloud.pause', 'cloud.release', 'cloud.snapshot'].includes(el)) return null;
    const name = { 'cloud.pause': 'Pause', 'cloud.release': 'Release', 'cloud.snapshot': 'Snapshot' }[el];
    const snaps = s.snapshots.filter((n) => n.startsWith(x.name));
    return {
      label: `${name} ${x.name}`,
      action: `Click '${name}' on ${x.name}.`,
      state: `Server ${x.name} is ${x.status}. Its disk ${x.disk.split(' ')[0]} holds ${x.data}. ${snaps.length ? `There is a snapshot of it: ${snaps.join(', ')}.` : 'There are no snapshots of it.'}`,
      questions: [
        yesno('data', `After the action, can ${x.data.replace(/^the only copy of /, '')} still be recovered?`, 'no', `${cap(x.dataShort)} is kept`, `${cap(x.dataShort)} is gone for good`),
        yesno('bill', `After the action, is ${x.name} still billed for compute?`, 'never', 'Compute billing continues', 'Compute billing stops'),
      ],
    };
  },
};
const cap = (t) => t[0].toUpperCase() + t.slice(1);
