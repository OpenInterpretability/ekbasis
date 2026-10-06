"""WS-U confirmatory test: the policy's extra calls on every kept fresh CONFIDENT row (confidence ≥ 0.9), same evidence:
  request 1: WS-P's two perturbations in one request (options in reverse order; the fixed prefix), infer_baselines.py;
  request 2: the self-check question with part2_run.py's wording: 'Consider this question: "<q>" Is "<answer>" the
             correct answer?', options yes/no.
Rows are rebuilt from their prompt and byte-checked first (infer_baselines.rebuild).
python3 extra_calls.py primary|planning   (EKBASIS_URL must be :8544; 16 in flight; resumable)  ->  extra.jsonl"""
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/root/decis/mission/P")
sys.path.insert(0, os.path.dirname(HERE))
_argv, sys.argv = sys.argv, sys.argv[:1]
import infer_baselines as IB  # noqa: E402
sys.argv = _argv
import part2_run as P2  # noqa: E402  (parse(), answer_text(): the self-check wording of parts 2–4)
from ekbasis.client import Ekbasis  # noqa: E402

URL = os.environ["EKBASIS_URL"].rstrip("/")
assert URL.endswith(":8544"), URL
OUT = os.path.join(HERE, "extra.jsonl")
PRIMARY = ["rules_stress", "sql_wild", "shell_wild", "git_wild", "accumulation"]
client = Ekbasis(url=URL, timeout=900)


def ask_verify(state, text):
    body = {"state": state, "questions": {"q": {"type": "choice", "instructions": text, "criteria": {"yes": "yes", "no": "no"}}}}
    req = urllib.request.Request(URL + "/v1/systemone", json.dumps(body).encode(), {"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=900))["answers"]["q"]
    return {"choice": d.get("choice"), "probabilities": d.get("probabilities")}


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
            v = ask_verify(u["evidence"], vtext)
            break
        except Exception as e:  # noqa: BLE001
            err = str(e)
            time.sleep(3 * (attempt + 1))
    else:
        return {"rid": r["rid"], "error": err[:200]}
    out = {"rid": r["rid"]}
    for name, a_ in ans.items():
        probs = {str(k): float(x) for k, x in (a_.probabilities or {}).items()}
        if r["qtype"] in ("noul", "boolean") and name == "para":
            probs = {"yes": a_.p_yes, "no": 1 - a_.p_yes}
        out[name] = {"answer": max(probs, key=probs.get), "p_original": probs.get(r["answer"], 0.0)}
    out["verify"] = v
    return out


def main():
    which = sys.argv[1]
    suites = PRIMARY if which == "primary" else ["planning_probe"]
    rows = [json.loads(l) for l in open(os.path.join(HERE, "fresh_rows.jsonl"))]
    rows = [r for r in rows if r["exclude"] is None and r["suite"] in suites and (r["conf"] or 0) >= 0.9]
    done = set()
    if os.path.exists(OUT):
        done = {j["rid"] for j in map(json.loads, open(OUT)) if "error" not in j}
    todo = [r for r in rows if r["rid"] not in done]
    print(f"{which}: {len(rows)} confident rows, {len(done)} done, {len(todo)} to ask on {URL}", flush=True)
    IB.B.tok()  # deviation 1: load the tokenizer once here; its lazy first import is not thread-safe (crashed at 12:53)
    with cf.ThreadPoolExecutor(16) as ex, open(OUT, "a") as f:  # each worker has one request in flight at a time
        for n, res in enumerate(ex.map(one, todo), 1):
            f.write(json.dumps(res) + "\n")
            if n % 500 == 0:
                f.flush()
                print(f"{n}/{len(todo)}", flush=True)
    print(f"EXTRA {which} DONE", flush=True)


if __name__ == "__main__":
    main()
