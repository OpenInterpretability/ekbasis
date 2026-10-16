"""V49's data (PLAN_v49 + Addendum A), built after the plan's hashes:
- v49_fx_raw: FX's packed training rows (fx_train.jsonl.gz), without ext_webworld (Caio's rule), stratified with
  random.Random(49): up to 400 rows per FX-own family, split evenly across its question types (the qtype head; a type
  with fewer rows gives its quota to the others), plus ext_cwm_python 2,000 and ext_shio_cmds 600. Kind "floorFX".
- v49_anchor2_raw: v48_softpool's rows (firewalled for PLAN_v48) with their own right labels, kind "floorGA".
- fxe_family: 200 rows per held-out FX family (13 families) from fx_eval_family; fxe_app: 800 Memos rows from fx_eval_app
  (random.Random(49)). Reported, not gates.
  /usr/bin/python3 make_v49_data.py   -> /dev/shm/conseq/fac/{v49_fx_raw,v49_anchor2_raw,fxe_family,fxe_app}.jsonl"""
import collections
import gzip
import json
import random

FX = "/dev/shm/fx/data"
FAC = "/dev/shm/conseq/fac"
PER_FAMILY, CWM, SHIO = 400, 2000, 600
EXCLUDE = {"ext_webworld"}


def reservoir(groups, key, row, k, rng, seen):
    seen[key] += 1
    g = groups[key]
    if len(g) < k:
        g.append(row)
    else:
        j = rng.randrange(seen[key])
        if j < k:
            g[j] = row


def main():
    rng = random.Random(49)
    by = collections.defaultdict(list)  # (family, qtype head) -> rows, at most PER_FAMILY each (trimmed below)
    seen = collections.Counter()
    fam_types = collections.defaultdict(set)
    with gzip.open(f"{FX}/fx_train.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            fam = r["fx_family"]
            if fam in EXCLUDE:
                continue
            head = str(r.get("qtype", "")).split("|")[0]
            cap = CWM if fam == "ext_cwm_python" else SHIO if fam == "ext_shio_cmds" else PER_FAMILY
            fam_types[fam].add(head)
            reservoir(by, (fam, head), r, cap, rng, seen)
    out, rep = [], {}
    for fam in sorted(fam_types):
        cap = CWM if fam == "ext_cwm_python" else SHIO if fam == "ext_shio_cmds" else PER_FAMILY
        heads = sorted(fam_types[fam])
        pools = {h: list(by[(fam, h)]) for h in heads}
        for h in heads:
            rng.shuffle(pools[h])
        take, left = {h: 0 for h in heads}, cap
        while left > 0:  # round-robin over question types: an even split, the unused quota of a short type goes on
            moved = False
            for h in heads:
                if left and take[h] < len(pools[h]):
                    take[h] += 1
                    left -= 1
                    moved = True
            if not moved:
                break
        rows = [dict(r, kind="floorFX") for h in heads for r in pools[h][:take[h]]]
        out += rows
        rep[fam] = {"rows": len(rows), "types": {h: take[h] for h in heads}}
    rng.shuffle(out)
    with open(f"{FAC}/v49_fx_raw.jsonl", "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    anchor = [dict(json.loads(line), kind="floorGA") for line in open(f"{FAC}/v48_softpool.jsonl")]
    with open(f"{FAC}/v49_anchor2_raw.jsonl", "w") as f:
        for r in anchor:
            r.pop("probs", None)
            f.write(json.dumps(r) + "\n")
    ev = {}
    for src, name, per, total in (("fx_eval_family", "fxe_family", 200, None), ("fx_eval_app", "fxe_app", None, 800)):
        rows = [json.loads(line) for line in gzip.open(f"{FX}/{src}.jsonl.gz", "rt")]
        r2 = random.Random(49)
        if per:
            fams = collections.defaultdict(list)
            for r in rows:
                fams[r["fx_family"]].append(r)
            pick = []
            for fam in sorted(fams):
                r2.shuffle(fams[fam])
                pick += fams[fam][:per]
        else:
            r2.shuffle(rows)
            pick = rows[:total]
        with open(f"{FAC}/{name}.jsonl", "w") as f:
            for r in pick:
                f.write(json.dumps(r) + "\n")
        ev[name] = {"rows": len(pick), "families": dict(collections.Counter(r["fx_family"] for r in pick))}
    summary = {"v49_fx_raw": {"rows": len(out), "families": len(rep), "by_family": rep,
                              "share_cwm": round(rep.get("ext_cwm_python", {}).get("rows", 0) / len(out), 4),
                              "share_shio": round(rep.get("ext_shio_cmds", {}).get("rows", 0) / len(out), 4)},
               "v49_anchor2_raw": {"rows": len(anchor)}, **ev}
    json.dump(summary, open("/root/decis/mission/F/v49/data/make_v49_data.json", "w"), indent=1)
    print(json.dumps({k: (v if k != "v49_fx_raw" else {kk: vv for kk, vv in v.items() if kk != "by_family"}) for k, v in summary.items()}))


if __name__ == "__main__":
    main()
