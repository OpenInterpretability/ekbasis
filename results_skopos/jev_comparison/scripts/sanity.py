"""Sanity checks before the main run, all on the git3_test_held sample.
python3 -I sanity.py ids     -> writes sanity_ids.json (the item ids of each check)
python3 -I sanity.py report  -> reads sanity10.jsonl, order_test.jsonl, state_test.jsonl; prints and writes sanity.json
  sanity10   : the first sampled item of each of the 10 question types, run one at a time (serial latency), read by hand
  order test : 20 choice items whose options are names (branch, content), random.Random(20261016).sample; run with the
               original option order twice (tags order_a, order_b: is Jev deterministic?) and reversed (order_rev).
               Stash options are "0".."3": integer-like keys always come first in ascending order in a JS object, so
               their order cannot be changed through the SDK and they are left out.
  state test : 20 items of any type (random.Random(20261017).sample); state as the bare string (state_str) vs
               {situation: string} (state_obj)"""
import json, random, statistics, sys
from pathlib import Path

HERE = Path(__file__).parent
L = lambda p: [json.loads(l) for l in open(p) if l.strip()]
items = L(HERE / "items_git3_test_held.jsonl")

if sys.argv[1] == "ids":
    first = {}
    for r in items:
        first.setdefault(r["qtype"], r["idx"])
    named = [r["idx"] for r in items if r["qtype"] in ("branch", "content")]
    ids = {"sanity10": sorted(first.values()),
           "order": sorted(random.Random(20261016).sample(named, 20)),
           "state": sorted(random.Random(20261017).sample([r["idx"] for r in items], 20))}
    json.dump(ids, open(HERE / "sanity_ids.json", "w"), indent=1)
    print({k: ",".join(map(str, v)) for k, v in ids.items()})
    sys.exit()

by = {r["idx"]: r for r in items}


def pick(rows, tag):
    return {r["idx"]: r for r in rows if r.get("tag") == tag and not r.get("error")}


def p_of(a, opt):  # probability Jev gives to one option (boolean: "yes"/"no")
    if a["type"] == "boolean":
        return a["probability"] if opt == "yes" else 1 - a["probability"]
    return (a.get("probabilities") or {}).get(opt, float("nan"))


def pred(a):
    return ("yes" if a["probability"] >= 0.5 else "no") if a["type"] == "boolean" else a["choice"]


rep = {}
s10 = pick(L(HERE / "sanity10.jsonl") if (HERE / "sanity10.jsonl").exists() else [], "sanity10")
rep["sanity10"] = []
for i, r in sorted(s10.items()):
    it = by[i]
    row = {"idx": i, "qtype": it["qtype"], "gold": it["gold"], "jev": pred(r["answer"]), "p_gold": p_of(r["answer"], it["gold"]),
           "answer": r["answer"], "ekbasis27b": it["published"]["ekbasis27b"]["pred"], "latency_ms": r["latency_ms"],
           "input_tokens": r["usage"]["inputTokens"], "content_chars": len(it["state"]) + len(json.dumps(it["question"]))}
    rep["sanity10"].append(row)
    print(f"--- idx {i} {it['qtype']} | gold {it['gold']} | Jev {row['jev']} (P(gold)={row['p_gold']:.3f}) | Ekbasis-27B {row['ekbasis27b']} | {r['latency_ms']} ms, {row['input_tokens']} tok")
    if "--full" in sys.argv:
        print(it["state"]); print("Q:", json.dumps(it["question"]))
if rep["sanity10"]:
    rep["sanity10_serial_latency_ms_median"] = statistics.median(x["latency_ms"] for x in rep["sanity10"])
    rep["tokens_per_content_char"] = sum(x["input_tokens"] for x in rep["sanity10"]) / sum(x["content_chars"] for x in rep["sanity10"])

ot = L(HERE / "order_test.jsonl") if (HERE / "order_test.jsonl").exists() else []
A, B, R = pick(ot, "order_a"), pick(ot, "order_b"), pick(ot, "order_rev")
common = sorted(set(A) & set(B) & set(R))
if common:
    g = {i: by[i]["gold"] for i in common}
    dp = lambda X, Y: [abs(p_of(X[i]["answer"], g[i]) - p_of(Y[i]["answer"], g[i])) for i in common]
    rep["order"] = {
        "n": len(common),
        "acc_orig_a": 100 * sum(pred(A[i]["answer"]) == g[i] for i in common) / len(common),
        "acc_orig_b": 100 * sum(pred(B[i]["answer"]) == g[i] for i in common) / len(common),
        "acc_reversed": 100 * sum(pred(R[i]["answer"]) == g[i] for i in common) / len(common),
        "same_choice_orig_a_vs_b": sum(pred(A[i]["answer"]) == pred(B[i]["answer"]) for i in common),
        "same_choice_orig_vs_reversed": sum(pred(A[i]["answer"]) == pred(R[i]["answer"]) for i in common),
        "mean_abs_dP_gold_orig_a_vs_b": statistics.mean(dp(A, B)), "max_abs_dP_gold_orig_a_vs_b": max(dp(A, B)),
        "mean_abs_dP_gold_orig_vs_reversed": statistics.mean(dp(A, R)), "max_abs_dP_gold_orig_vs_reversed": max(dp(A, R)),
        "ekbasis27b_acc": 100 * sum(by[i]["published"]["ekbasis27b"]["pred"] == g[i] for i in common) / len(common),
        # does Jev favour the option in a given position? P of the first-listed option, original vs reversed
        "mean_P_first_listed_orig": statistics.mean(p_of(A[i]["answer"], A[i]["options_sent"][0]) for i in common),
        "mean_P_first_listed_reversed": statistics.mean(p_of(R[i]["answer"], R[i]["options_sent"][0]) for i in common),
    }
    print("order", json.dumps(rep["order"], indent=1))

st = L(HERE / "state_test.jsonl") if (HERE / "state_test.jsonl").exists() else []
S, O = pick(st, "state_str"), pick(st, "state_obj")
common = sorted(set(S) & set(O))
if common:
    g = {i: by[i]["gold"] for i in common}
    rep["state_form"] = {
        "n": len(common),
        "acc_string": 100 * sum(pred(S[i]["answer"]) == g[i] for i in common) / len(common),
        "acc_object": 100 * sum(pred(O[i]["answer"]) == g[i] for i in common) / len(common),
        "same_answer": sum(pred(S[i]["answer"]) == pred(O[i]["answer"]) for i in common),
        "mean_abs_dP_gold": statistics.mean(abs(p_of(S[i]["answer"], g[i]) - p_of(O[i]["answer"], g[i])) for i in common),
        "tokens_string": sum(S[i]["usage"]["inputTokens"] for i in common), "tokens_object": sum(O[i]["usage"]["inputTokens"] for i in common),
    }
    print("state form", json.dumps(rep["state_form"], indent=1))
json.dump(rep, open(HERE / "sanity.json", "w"), indent=1)
