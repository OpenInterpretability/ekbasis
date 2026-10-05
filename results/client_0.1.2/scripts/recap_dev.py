"""Rule recap on fresh items, never the published ones.
  habit: habit_vs_rule's 90 archetypes, variants 8-11 (the published run used 0-7; any text identical to a published
         item is dropped), familiar and invented, the rule agreeing with or contradicting the usual effect.
  rules: rules_stress's rule-kind factor (direct, side, delay, cond, prohibit, irrev, chain1-4, line1-4) generated with a
         new seed (RS_SEED), base and flip items.
Each item is asked in one request with the same question three ways: none (as 0.1.1 asks), relevant (the rule that
decides it, recapped: habit's rule line; rules_stress's non-distractor rules) and all (every rule line recapped).
python3 eval/recap_dev.py [habit,rules] -> results/recap_dev.jsonl, results/recap_dev_summary.json"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import json
import os
import subprocess
import sys

from common import CAP, OUT, PKG, VENDOR, WORKERS, client, rate, read_jsonl, write_jsonl

from ekbasis import prompts as P  # noqa: E402

PARTS = (sys.argv[1] if len(sys.argv) > 1 else "habit,rules").split(",")
RS_SEED = os.environ.get("RS_SEED", "77012501")
RS_N = os.environ.get("RS_N", "40")


def habit_items() -> list:
    sys.argv = sys.argv[:1]  # make_items reads sys.argv[1] at import
    sys.path.insert(0, os.path.join(VENDOR, "habit_vs_rule"))
    import make_items as M  # noqa: E402
    published = set()
    for name in ("items.jsonl", "items_mitig.jsonl"):
        path = os.path.join(CAP, "habit_vs_rule", name)
        if os.path.exists(path):
            published |= {(r["text"], r["question"]) for r in read_jsonl(path)}
    out, skipped = [], collections.Counter()
    for j, arch in enumerate(M.ARCHETYPES):
        for i in range(8, 12):
            for setting in ("familiar", "invented"):
                for relation in ("agrees", "contradicts"):
                    try:
                        it, _ = M.build(arch, j, i, setting, relation)
                    except (IndexError, KeyError, AssertionError) as e:
                        skipped[type(e).__name__] += 1
                        continue
                    if (it["text"], it["question"]) in published or it["truth"] is None:
                        skipped["published or no truth"] += 1
                        continue
                    rules_text = it["text"].split("\n\nCurrent state:")[0]
                    out.append({"source": "habit", "id": it["id"], "group": it["kind"], "setting": setting,
                                "relation": relation, "text": it["text"], "question": it["question"],
                                "options": it["options"], "truth": it["truth"], "relevant": [it["rule_line"]],
                                "all": P.rule_lines(rules_text)})
    print("habit:", len(out), "fresh items; skipped", dict(skipped), flush=True)
    return out


def rules_items() -> list:
    path = os.path.join(OUT, f"rs_fresh_items_{RS_SEED}.jsonl")
    env = dict(os.environ, RS_SEED=RS_SEED, N_BASE=RS_N, N_MANUAL="0", ITEMS_OUT=path, PYTHONPATH=PKG)
    subprocess.run([sys.executable, "make_items.py"], cwd=os.path.join(VENDOR, "rules_stress"), env=env, check=True,
                   stdout=subprocess.DEVNULL)
    sys.path.insert(0, os.path.join(VENDOR, "rules_stress"))
    from rs_world import rule_text  # noqa: E402
    published = {r["text"] for r in read_jsonl(os.path.join(CAP, "rules_stress", "items.jsonl"))}
    out = []
    for r in read_jsonl(path):
        if r["factor"] != "kind" or r["variant"] not in ("base", "flip") or r["text"] in published:
            continue
        rules_text = r["text"].split("\n\nCurrent state:")[0]
        rel = [rule_text(x) for x in r.get("world", {}).get("rules", []) if not x.get("dist")] or P.rule_lines(rules_text)
        out.append({"source": "rules", "id": r["id"], "group": r["level"], "setting": "invented", "relation": r["variant"],
                    "text": r["text"], "question": r["question"], "options": r["options"], "truth": r["truth"],
                    "relevant": rel, "all": P.rule_lines(rules_text)})
    print("rules_stress:", len(out), "fresh items (seed", RS_SEED + ")", flush=True)
    return out


def one(item: dict, cl) -> dict:
    q = P.choice(item["question"], item["options"])
    qs = {"none": q, "relevant": P.recap(q, item["relevant"]), "all": P.recap(q, item["all"])}
    for attempt in range(4):
        try:
            ans = cl.ask(item["text"], qs)
            break
        except Exception as e:  # noqa: BLE001  (the server: retried, then recorded)
            err = str(e)
    else:
        return {**{k: item[k] for k in ("source", "id", "group", "setting", "relation", "truth")}, "error": err}
    return {**{k: item[k] for k in ("source", "id", "group", "setting", "relation", "truth")},
            "answers": {k: {"value": a.value, "confidence": a.confidence} for k, a in ans.items()}}


def summarize(rows: list) -> dict:
    ok = [r for r in rows if "answers" in r]
    out = {"items": len(rows), "errors": len(rows) - len(ok), "by_source": {}}
    for src in sorted({r["source"] for r in ok}):
        rs = [r for r in ok if r["source"] == src]
        right = lambda r, c: str(r["answers"][c]["value"]) == str(r["truth"])  # noqa: E731
        d = {c: rate(sum(right(r, c) for r in rs), len(rs)) for c in ("none", "relevant", "all")}
        for c in ("relevant", "all"):
            d[f"{c}_fixed"] = sum(right(r, c) and not right(r, "none") for r in rs)
            d[f"{c}_broke"] = sum(right(r, "none") and not right(r, c) for r in rs)
        groups = collections.defaultdict(list)
        for r in rs:
            groups[(r["group"], r["setting"], r["relation"])].append(r)
        d["by_cell"] = {" | ".join(k): {c: f"{sum(right(r, c) for r in v)}/{len(v)}" for c in ("none", "relevant", "all")}
                        for k, v in sorted(groups.items())}
        out["by_source"][src] = d
    return out


def main():
    items = (habit_items() if "habit" in PARTS else []) + (rules_items() if "rules" in PARTS else [])
    cl = client()
    print("health:", cl.health(), flush=True)
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        rows = list(ex.map(lambda it: one(it, cl), items))
    write_jsonl(os.path.join(OUT, "recap_dev.jsonl"), rows)
    s = summarize(rows)
    json.dump(s, open(os.path.join(OUT, "recap_dev_summary.json"), "w"), indent=1)
    for src, d in s["by_source"].items():
        print(src, {c: d[c]["pct"] for c in ("none", "relevant", "all")},
              {k: d[k] for k in d if k.endswith(("fixed", "broke"))})


if __name__ == "__main__":
    main()
