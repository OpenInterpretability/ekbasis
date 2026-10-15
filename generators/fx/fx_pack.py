"""WS-FX packer (SPEC.md, Balance): drop the firewall's rows, deduplicate, shuffle choice options per row, and resample
yes/no question types to w4a5's training yes rate where it is known (WS-F v47/balance.json: git lost 50, fails 50,
clean 29.3, in_progress 1.25; shell, SQL and PostgreSQL lost 50, fails 50; other types 50/50), dropping majority rows
without a flip twin first. Held-out splits are only capped at 70/30. Writes fx_train / fx_val / fx_eval_family /
fx_eval_app (.jsonl.gz) and pack.json (counts, rates before and after, 'nothing changes' share per family)."""
from __future__ import annotations

import collections
import glob
import gzip
import hashlib
import json
import random

FX = "/root/decis/mission/FX"
TARGET = {("rx_git", "lost"): 0.50, ("rx_git", "fails"): 0.50, ("rx_git", "clean"): 0.293, ("rx_git", "in_progress"): 0.0125,
          ("rx_shell", "lost"): 0.50, ("rx_shell", "fails"): 0.50, ("rx_sql", "lost"): 0.50, ("rx_sql", "fails"): 0.50,
          ("rx_pg", "fails"): 0.50}
# choice types whose gold is either one named effect or a fixed "nothing" option (Addendum 5): balanced like yes/no
CHOICE_AS_BINARY = {"side_effect_which": "nothing else changes"}


def h(s):
    return hashlib.md5(s.encode()).hexdigest()


def main():
    drop = set()
    for fp in glob.glob(f"{FX}/data/firewall_drop_*.txt"):
        drop |= set(l.strip() for l in open(fp) if l.strip())
    rows_by_split = collections.defaultdict(list)
    seen = set()
    n_in = n_drop = n_dup = 0
    for p in sorted(glob.glob(f"{FX}/data/raw/*.jsonl.gz") + glob.glob("/dev/shm/fx/raw2/*.jsonl.gz")):
        for line in gzip.open(p, "rt"):
            r = json.loads(line)
            n_in += 1
            if r["id"] in drop:
                n_drop += 1
                continue
            key = h(r["floor"] + "\x00" + r["question"]["instructions"] + "\x00" + json.dumps(r["question"].get("criteria")) + "\x00" + str(r["gold"]))
            if key in seen:
                n_dup += 1
                continue
            seen.add(key)
            q = r["question"]
            if q["type"] == "choice":
                items = list(q["criteria"].items())
                random.Random(int(h(r["id"])[:8], 16)).shuffle(items)
                q["criteria"] = dict(items)
            rows_by_split[r["fx_split"]].append(r)
    report = {"rows_in": n_in, "dropped_by_firewall": n_drop, "duplicates": n_dup, "splits": {}, "rates": {}, "nothing_changes": {}}
    for split, rows in rows_by_split.items():
        by_q = collections.defaultdict(list)
        keep = []
        for r in rows:
            if r["question"]["type"] == "noul":
                by_q[(r["world"], r["qtype"])].append(r)
            elif r["qtype"] in CHOICE_AS_BINARY:
                # the side-effect choice is a yes/no in disguise ("nothing else changes" = no): balanced the same way
                rr = dict(r)
                by_q[(r["world"], r["qtype"])].append(rr)
            else:
                keep.append(r)
        for key, rs in sorted(by_q.items()):
            if key[1] in CHOICE_AS_BINARY:
                yes = [r for r in rs if r["gold"] != CHOICE_AS_BINARY[key[1]]]
                no = [r for r in rs if r["gold"] == CHOICE_AS_BINARY[key[1]]]
            else:
                yes = [r for r in rs if r["gold"] is True]
                no = [r for r in rs if r["gold"] is False]
            before = len(yes) / max(1, len(rs))
            if not yes or not no:
                # a yes/no type with one answer only teaches nothing but a prior (V45's failure mode), and in an
                # evaluation split it only rewards that prior: left out of every split
                report.setdefault("dropped_single_class", {}).setdefault(split, {})[f"{key[0]}/{key[1]}"] = len(rs)
                continue
            if split in ("train", "val"):
                t = TARGET.get(key, 0.5)
            else:
                t = min(max(before, 0.3), 0.7)
            # keep as many rows as possible at the target rate: drop from the class in excess, rows without a twin first
            if yes and no:
                n_yes_max = int(round(len(no) * t / (1 - t))) if t < 1 else len(yes)
                n_no_max = int(round(len(yes) * (1 - t) / t)) if t > 0 else len(no)
                if len(yes) > n_yes_max:
                    yes = sorted(yes, key=lambda r: (r.get("twin") is not None, h(r["id"])))[len(yes) - n_yes_max:]
                elif len(no) > n_no_max:
                    no = sorted(no, key=lambda r: (r.get("twin") is not None, h(r["id"])))[len(no) - n_no_max:]
            after = len(yes) / max(1, len(yes) + len(no))
            report["rates"].setdefault(split, {})[f"{key[0]}/{key[1]}"] = {"before": round(before, 3), "after": round(after, 3),
                                                                            "rows_before": len(rs), "rows_after": len(yes) + len(no)}
            keep += yes + no
        keep.sort(key=lambda r: h(r["id"]))
        out = {"train": "fx_train", "val": "fx_val", "eval_family": "fx_eval_family", "eval_app": "fx_eval_app"}[split]
        with gzip.open(f"{FX}/data/{out}.jsonl.gz", "wt") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        fams = collections.Counter(r["fx_family"] for r in keep)
        report["splits"][split] = {"rows": len(keep), "families": len(fams), "per_family": dict(sorted(fams.items()))}
        nc = collections.defaultdict(lambda: [0, 0])
        for r in keep:
            if r.get("known0") and r.get("gold0") is not None:
                nc[r["fx_family"]][0] += int(str(r["gold"]) == str(r["gold0"]))
                nc[r["fx_family"]][1] += 1
        report["nothing_changes"][split] = {f: round(a / b, 3) for f, (a, b) in sorted(nc.items()) if b}
        first = sum(1 for r in keep if r["question"]["type"] == "choice" and list(r["question"]["criteria"])[0] == str(r["gold"]))
        nch = sum(1 for r in keep if r["question"]["type"] == "choice")
        report["splits"][split]["choice_gold_first"] = round(first / max(1, nch), 3)
    report["total_rows"] = sum(v["rows"] for v in report["splits"].values())
    report["total_families"] = len({f for v in report["splits"].values() for f in v["per_family"]})
    json.dump(report, open(f"{FX}/data/pack.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k not in ("rates", "nothing_changes")}, indent=1)[:4000])


if __name__ == "__main__":
    main()
