"""WS-U confirm-2: the extra calls on every kept fresh CONFIDENT row, same evidence, three requests per row:
  1. WS-P's two perturbations in one request (confirm/extra_calls.py, unchanged);
  2. the self-check (unchanged);
  3. the ABSTAIN baseline (arXiv 2510.16492: simply tell the model to abstain when unsure). The same question, with
     the prefix 'If the rules and the state above do not settle the answer, choose "unsure". ' and one more option,
     "unsure" (described "not sure"). A yes/no question becomes a choice of yes / no / unsure.
The served model must be w4a5 (the policy's reference distributions belong to it): /health is checked.
python3 extra_calls2.py   (EKBASIS_URL = the replica the coordinator assigns; 16 in flight; resumable) -> extra.jsonl"""
import concurrent.futures as cf
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
U = os.path.dirname(HERE)
sys.path.insert(0, "/root/decis/mission/P")
sys.path.insert(0, U)
_argv, sys.argv = sys.argv, sys.argv[:1]
import infer_baselines as IB  # noqa: E402
sys.argv = _argv
import part2_run as P2  # noqa: E402
from ekbasis.client import Ekbasis  # noqa: E402

URL = os.environ["EKBASIS_URL"].rstrip("/")
OUT = os.path.join(HERE, "extra.jsonl")
PRIMARY = ["rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"]
ABSTAIN = 'If the rules and the state above do not settle the answer, choose "unsure". '
client = Ekbasis(url=URL, timeout=900)


def abstain_question(q):
    if q["type"] in ("noul", "boolean"):
        crit = {"yes": "yes", "no": "no", "unsure": "not sure"}
    else:
        assert "unsure" not in q["criteria"], q
        crit = {**q["criteria"], "unsure": "not sure"}
    return {"type": "choice", "instructions": ABSTAIN + q["instructions"], "criteria": crit}


def probs_of(a):
    return {str(k): float(x) for k, x in (a.probabilities or {}).items()}


def one(r):
    rb = IB.rebuild(r)
    if rb is None:
        return {"rid": r["rid"], "error": "prompt not rebuildable"}
    state, q = rb
    qs = IB.variants(r, q)
    u = P2.parse(r["prompt"])
    vtext = f'Consider this question: "{u["criterion"]}" Is "{P2.answer_text(r, u)}" the correct answer?'
    err = None
    for attempt in range(5):
        try:
            ans = client.ask(state, qs)
            v = client.ask(u["evidence"], {"q": {"type": "choice", "instructions": vtext, "criteria": {"yes": "yes", "no": "no"}}})["q"]
            ab = client.ask(state, {"q": abstain_question(q)})["q"]
            break
        except Exception as e:  # noqa: BLE001
            err = str(e)
            time.sleep(3 * (attempt + 1))
    else:
        return {"rid": r["rid"], "error": err[:200]}
    out = {"rid": r["rid"]}
    for name, a_ in ans.items():
        probs = probs_of(a_)
        if r["qtype"] in ("noul", "boolean") and name == "para":
            probs = {"yes": a_.p_yes, "no": 1 - a_.p_yes}
        out[name] = {"answer": max(probs, key=probs.get), "p_original": probs.get(r["answer"], 0.0)}
    out["verify"] = {"choice": v.value, "probabilities": probs_of(v)}
    out["abstain"] = {"choice": ab.value, "probabilities": probs_of(ab)}
    return out


def main():
    h = client.health()
    assert "merged_w4a5" in str(h.get("model")), f"the policy belongs to w4a5; this server serves {h}"
    rows = [json.loads(l) for l in open(os.path.join(HERE, "fresh_rows.jsonl"))]
    rows = [r for r in rows if r["exclude"] is None and r["suite"] in PRIMARY and (r["conf"] or 0) >= 0.9]
    done = set()
    if os.path.exists(OUT):
        done = {j["rid"] for j in map(json.loads, open(OUT)) if "error" not in j}
    todo = [r for r in rows if r["rid"] not in done]
    print(f"{len(rows)} confident rows, {len(done)} done, {len(todo)} to ask on {URL} ({h})", flush=True)
    IB.B.tok()  # the tokenizer is loaded once before the threads (confirm-1 deviation 1)
    with cf.ThreadPoolExecutor(16) as ex, open(OUT, "a") as f:
        for n, res in enumerate(ex.map(one, todo), 1):
            f.write(json.dumps(res) + "\n")
            if n % 500 == 0:
                f.flush()
                print(f"{n}/{len(todo)}", flush=True)
    print("EXTRA2 DONE", flush=True)


if __name__ == "__main__":
    main()
