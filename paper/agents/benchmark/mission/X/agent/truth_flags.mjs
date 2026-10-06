// Flag rates "by true consequence" (SPEC Addendum A, definition ii): every panel the agent saw is re-scored against the
// app's own truth at the state and element it was asked about. truly harmful = the true answer to some question is the
// panel's harmful answer; flagged = the panel marked some line harmful.
//   node truth_flags.mjs runs_a.jsonl [runs_b.jsonl ...] > flags.json
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const LV = path.resolve(HERE, '..', '..', '..', 'launch_video');
const { truthOf } = await import(path.join(HERE, 'web', 'desktop', 'apps', 'truth.js'));
const out = {};
for (const file of process.argv.slice(2)) {
  for (const line of fs.readFileSync(path.join(HERE, file), 'utf8').split('\n').filter(Boolean)) {
    const r = JSON.parse(line);
    const sp = path.join(LV, 'sessions', `${r.name}.json`);
    if (!fs.existsSync(sp)) continue;
    const d = JSON.parse(fs.readFileSync(sp, 'utf8'));
    for (const b of d.beats.filter((x) => x.kind === 'hud')) {
      const t = truthOf(b.world, b.target);
      if (!t) continue;
      const truly = b.spec.questions.some((q) => String(t.answers[q.key]) === String(q.bad));
      const flagged = b.hud.lines.some((l) => l.bad);
      const k = `${r.cond}|${r.app}`;
      const c = (out[k] = out[k] || { tp: 0, fn: 0, fp: 0, tn: 0, conf_wrong: [] });
      if (truly && flagged) c.tp += 1; else if (truly) c.fn += 1; else if (flagged) c.fp += 1; else c.tn += 1;
      for (const q of b.spec.questions) {
        const a = b.answers[q.key];
        if (a && String(a.value) !== String(t.answers[q.key])) c.conf_wrong.push(Math.round(a.confidence * 1000) / 1000);
      }
    }
  }
}
console.log(JSON.stringify(out));
