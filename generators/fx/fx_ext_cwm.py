"""WS-FX Addendum 3: ext_cwm_python, converted from marin-community/swe-rebench-v2-CodeWorldModeling (CC-BY-4.0 plus each
source repository's license; only permissively licensed rows). CWM-style next-line prediction in the typed format: the
state is the test source and the trace so far (each line as it ran, values bound shown after '#'), the action is the next
traced line that binds a simple name, and the question asks the value it binds (real value + values the trace shows for
that name or nearby names). The truth is the value recorded by the tracer.
python3 fx_ext_cwm.py <out_train.jsonl.gz> <out_val.jsonl.gz> [cap_train] [cap_val]"""
from __future__ import annotations

import glob
import gzip
import hashlib
import json
import random
import re
import sys

import pyarrow.parquet as pq

sys.path.insert(0, "/root/decis/mission/FX/factory")
from common import choice, row, world_ceiling, world_floor  # noqa: E402

PERMISSIVE = {"mit", "bsd-2-clause", "bsd-3-clause", "bsd", "apache-2.0", "apache 2.0", "isc", "psf-2.0", "python-2.0",
              "unlicense", "cc0-1.0", "zlib", "0bsd", "mit-0"}
RULES = ("A Python test runs under a line tracer. The trace shows each source line as it ran: '# name=value' records the "
         "value a line bound, '# branch=...' which way a condition went, '# ENTER: ...' the arguments of a call and "
         "'# RETURN ...' a frame's return value. The action is the next line that runs.")
ASSIGN = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*(?:[+\-*/%|&^]|//|<<|>>)?=(?!=)\s*(.+?)\s{2,}#\s(.*)$")
STOP = re.compile(r",\s(?:branch|iter|line)=")


def bound_value(name, comment):
    m = re.search(r"(?:^|,\s)" + re.escape(name) + r"=(.*)", comment)
    if not m:
        return None
    v = STOP.split(m.group(1))[0].strip()
    return v if 0 < len(v) <= 60 and "\n" not in v else None


def traces(text):
    """(source, trace lines) pairs: one for a regression row, the post-patch trace for a fix-verifying row."""
    if "# --- post-patch trace ---" in text:
        src = text.split("# --- pre-patch trace ---")[0]
        tr = text.split("# --- post-patch trace ---")[1]
    elif "# --- trace ---" in text:
        src, tr = text.split("# --- trace ---", 1)
    else:
        return []
    return [(src.strip("\n"), tr.strip("\n").splitlines())]


def items_from(rec, rng, k=2):
    out = []
    for src, lines in traces(rec["text"]):
        cands = []
        seen_vals = {}
        for i, ln in enumerate(lines):
            m = ASSIGN.match(ln)
            if not m:
                continue
            name, comment = m.group(2), m.group(4)
            v = bound_value(name, comment)
            if v is None:
                continue
            seen_vals.setdefault(name, []).append((i, v))
            if i >= 6:
                cands.append((i, name, v, m.group(0).split("  #")[0].rstrip()))
        rng.shuffle(cands)
        for i, name, v, code in cands[:k]:
            others = [x for j, x in seen_vals.get(name, []) if j != i and x != v]
            near = []
            for j in range(max(0, i - 25), min(len(lines), i + 10)):
                m2 = ASSIGN.match(lines[j])
                if m2 and j != i:
                    v2 = bound_value(m2.group(2), m2.group(4))
                    if v2 and v2 != v:
                        near.append(v2)
            distract = list(dict.fromkeys(others[::-1] + near))[:4]
            if len(distract) < 2:
                continue
            before = [x for j, x in seen_vals.get(name, []) if j < i]
            window = lines[max(0, i - 30):i]
            src_lines = src.splitlines()
            src_c = "\n".join(src_lines[:40]) + ("\n…" if len(src_lines) > 40 else "")
            state = f"Test source:\n{src_c}\n\nTrace so far (most recent lines):\n" + "\n".join(window)
            if len(state) > 7000:
                continue
            opts = [v] + distract
            rng.shuffle(opts)
            out.append({"state": state, "action": code.strip(), "name": name, "value": v, "options": opts,
                        "gold0": before[-1] if before else None, "after": lines[i]})
    return out


def main():
    """Streams shards from the Hub one at a time (download, convert, delete), spread over the whole dataset, until the caps;
    an instance goes to val when its hash says so (about 5% of instances), so val shares no repository with train."""
    from huggingface_hub import HfApi, hf_hub_download
    import os
    out_tr, out_va = sys.argv[1], sys.argv[2]
    cap_tr = int(sys.argv[3]) if len(sys.argv) > 3 else 30000
    cap_va = int(sys.argv[4]) if len(sys.argv) > 4 else 1500
    files = sorted(s.rfilename for s in HfApi().dataset_info("marin-community/swe-rebench-v2-CodeWorldModeling").siblings
                   if s.rfilename.startswith("data/traces-"))
    off = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    order = (files[::7] + files[3::7]) if off == 0 else (files[1::7] + files[5::7])
    lic_counts, kept_lic, n_tr, n_va, per_instance, shards = {}, {}, 0, 0, {}, 0
    tmp = "/dev/shm/fx/cwm_tmp"
    with gzip.open(out_tr, "wt") as ft, gzip.open(out_va, "wt") as fv:
        for f in order:
            if n_tr >= cap_tr and n_va >= cap_va:
                break
            try:
                path = hf_hub_download("marin-community/swe-rebench-v2-CodeWorldModeling", f, repo_type="dataset", local_dir=tmp)
            except Exception:  # noqa: BLE001
                continue
            shards += 1
            try:
                recs = pq.read_table(path).to_pylist()
            except Exception:  # noqa: BLE001
                recs = []
            finally:
                os.remove(path)
            for rec in recs:
                lic = (rec.get("license") or "").strip().lower()
                lic_counts[lic] = lic_counts.get(lic, 0) + 1
                if lic not in PERMISSIVE:
                    continue
                inst = rec["instance_id"]
                is_val = int(hashlib.md5(inst.encode()).hexdigest()[:2], 16) < 13
                if per_instance.get(inst, 0) >= 60 or (is_val and n_va >= cap_va) or (not is_val and n_tr >= cap_tr):
                    continue
                rng = random.Random(int(hashlib.md5((inst + rec["test_id"]).encode()).hexdigest()[:8], 16))
                for k, it in enumerate(items_from(rec, rng)):
                    qd = choice(f"After this line runs, what is the value of {it['name']}?", it["options"])
                    floor = world_floor(RULES, it["state"], [it["action"]])
                    ceiling = world_ceiling(RULES, it["after"], f"the line bound {it['name']}={it['value']}.")
                    known0 = it["gold0"] is not None and it["gold0"] in qd["criteria"]
                    rid = f"cwm-{hashlib.md5((inst + rec['test_id']).encode()).hexdigest()[:10]}-{k}"
                    r = row(world="ext_cwm", family="python", template="cwm_assign", qtype="value", steps=1, question=qd,
                            gold=it["value"], gold0=it["gold0"] if known0 else None, known0=known0, floor=floor,
                            ceiling=ceiling, rid=rid, struct={"instance_id": inst, "test_id": rec["test_id"], "license": lic})
                    r.update({"fx_family": "ext_cwm_python", "fx_split": "val" if is_val else "train", "fx_seed": None,
                              "fx_source": "external:marin-community/swe-rebench-v2-CodeWorldModeling"})
                    (fv if is_val else ft).write(json.dumps(r, ensure_ascii=False) + "\n")
                    per_instance[inst] = per_instance.get(inst, 0) + 1
                    kept_lic[lic] = kept_lic.get(lic, 0) + 1
                    if is_val:
                        n_va += 1
                    else:
                        n_tr += 1
    stats = {"train_rows": n_tr, "val_rows": n_va, "license_rows_seen": dict(sorted(lic_counts.items(), key=lambda x: -x[1])[:20]),
             "license_rows_kept": kept_lic, "instances": len(per_instance), "shards_read": shards}
    json.dump(stats, open(out_tr.replace(".jsonl.gz", ".stats.json"), "w"), indent=1)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
