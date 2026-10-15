"""WS-FX report helper: per-family counts, CPU time from the generation stats, and one example per family (question,
options, answer, the end of the prompt) for RESULTS.md. Writes data/report.json and data/examples.md."""
from __future__ import annotations

import collections
import glob
import gzip
import json
import os

FX = "/root/decis/mission/FX"


def main():
    pack = json.load(open(f"{FX}/data/pack.json"))
    fws = [json.load(open(x)) for x in sorted(glob.glob(f"{FX}/data/firewall_*.json"))]
    fw = {"dropped_total": sum(x["dropped_total"] for x in fws), "near_duplicates_dropped": sum(x["near_duplicates_dropped"] for x in fws),
          "eval": fws[0]["eval"] if fws else {"files": 0, "items": 0}}
    cpu = collections.defaultdict(float)
    for p in (glob.glob(f"{FX}/data/raw/*.stats.json") + glob.glob("/dev/shm/fx/raw2/*.stats.json")):
        s = json.load(open(p))
        cpu[os.path.basename(p).split("__")[0]] += float(s.get("cpu_s_parent_view") or 0)
    examples = []
    seen = set()
    for split in ("train", "eval_family", "eval_app"):
        path = f"{FX}/data/fx_{split}.jsonl.gz"
        if not os.path.exists(path):
            continue
        for line in gzip.open(path, "rt"):
            r = json.loads(line)
            fam = r["fx_family"]
            if fam in seen:
                continue
            seen.add(fam)
            q = r["question"]
            opts = list(q.get("criteria", {})) if q["type"] == "choice" else ["yes", "no"]
            tail = r["floor"][-700:]
            examples.append(f"### {fam} ({split})\n\n```\n…{tail}\n```\n\n**Q:** {q['instructions']}  \n**Options:** "
                            f"{' | '.join(o.replace(chr(10), ' / ')[:60] for o in opts)}  \n**Truth:** {str(r['gold'])[:120]}\n")
    open(f"{FX}/data/examples.md", "w").write("\n".join(examples))
    rep = {"splits": {k: {"rows": v["rows"], "families": v["families"]} for k, v in pack["splits"].items()},
           "total_rows": pack["total_rows"], "total_families": pack["total_families"],
           "firewall": {"dropped_total": fw["dropped_total"], "near_duplicates_dropped": fw["near_duplicates_dropped"],
                        "eval_files": fw["eval"]["files"], "eval_items": fw["eval"]["items"]},
           "cpu_hours_by_family": {k: round(v / 3600, 2) for k, v in sorted(cpu.items())},
           "cpu_hours_total": round(sum(cpu.values()) / 3600, 1)}
    json.dump(rep, open(f"{FX}/data/report.json", "w"), indent=1)
    print(json.dumps(rep, indent=1)[:3000])


if __name__ == "__main__":
    main()
