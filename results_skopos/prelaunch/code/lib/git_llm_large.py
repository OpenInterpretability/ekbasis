"""A larger git comparison: the reasoning LLM (Qwen3.8-27B, thinking and answering at once) on the same git v2 test
questions the consequence model answers (gitbox2, real git executions): per split (known command types / held ones,
never trained), 40 'lost' + 40 'fails' (balanced yes/no) + 40 state questions whose answer the commands change.
  run              asks the LLM (both modes), saves /dev/shm/conseq/git2/llm_large.json
  score [runs...]  the same questions for every run with predictions (27B base, V35, sweep runs), side by side"""
import concurrent.futures as cf, json, random, re, sys, urllib.request
from pathlib import Path

D = Path("/dev/shm/conseq")
OUT = D / "git2/llm_large.json"
norm = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)


def pick(split):
    rows = [json.loads(l) for l in open(D / f"fac/{split}.jsonl")]
    rng = random.Random(11)
    out = []
    for q in ("lost", "fails"):
        for want in ("yes", "no"):
            idx = [i for i, r in enumerate(rows) if r["qtype"] == q and norm(r["gold"]) == want]
            out += rng.sample(idx, min(20, len(idx)))
    chg = [i for i, r in enumerate(rows) if r["qtype"] not in ("lost", "fails", "in_progress") and r["known0"] and norm(r["gold0"]) != norm(r["gold"])]
    out += rng.sample(chg, min(40, len(chg)))
    return rows, out


def ask(row, think):
    q = row["question"]
    opts = ["yes", "no"] if q["type"] == "noul" else list(q["criteria"])
    prompt = (f"{row['floor']}\n\nQuestion: {q['instructions']} Options: {', '.join(opts)}."
              + ("\nEnd your answer with a line 'ANSWER: <option>'." if think else
                 "\nNo time to work it out: reply at once with only the line 'ANSWER: <option>' and nothing else."))
    body = {"model": "agent", "messages": [{"role": "user", "content": prompt}], "temperature": 0.6 if think else 0.0,
            "top_p": 0.95, "max_tokens": 12000 if think else 30}
    if not think:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request("http://127.0.0.1:30110/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=3600))
    out = (r["choices"][0]["message"].get("content") or "").split("</think>")[-1]
    m = re.findall(r"ANSWER:\s*([^\s\n]+)", out)
    return (m[-1].strip(".*`").lower() if m else ""), r["usage"]["completion_tokens"]


if __name__ == "__main__" and sys.argv[1] == "run":
    res = {}
    for split in ("git2_test_known", "git2_test_held"):
        rows, idx = pick(split)
        for think in (True, False):
            with cf.ThreadPoolExecutor(32) as ex:
                got = list(ex.map(lambda i: ask(rows[i], think), idx))
            res[f"{split}/{'think' if think else 'once'}"] = {str(i): {"pred": p, "tok": t} for i, (p, t) in zip(idx, got)}
            ok = sum(p == norm(rows[i]["gold"]).lower() for i, (p, t) in zip(idx, got))
            print(f"{split} {'thinking' if think else 'at once'}: {ok}/{len(idx)}, {sum(t for _, t in got) / len(got):.0f} tokens", flush=True)
    json.dump(res, open(OUT, "w"))
elif __name__ == "__main__":
    res = json.load(open(OUT))
    runs = [("27B base", D / "git2/gt_27b"), ("V35", D / "git2/gt_v35")] + [(a.upper(), D / f"sw_{a}") for a in sys.argv[2:]]
    for split in ("git2_test_known", "git2_test_held"):
        rows, idx = pick(split)
        groups = {"lost": [i for i in idx if rows[i]["qtype"] == "lost"], "fails": [i for i in idx if rows[i]["qtype"] == "fails"],
                  "state (chg)": [i for i in idx if rows[i]["qtype"] not in ("lost", "fails")], "all": idx}
        print(f"\n== {split}: {len(idx)} questions")
        print(f"{'system':22s} " + " ".join(f"{g:>12s}" for g in groups) + "   gen tokens")
        for mode in ("think", "once"):
            r = res[f"{split}/{mode}"]
            accs = [100 * sum(r[str(i)]["pred"] == norm(rows[i]["gold"]).lower() for i in g) / len(g) for g in groups.values()]
            print(f"{'Qwen3.8-27B ' + ('thinking' if mode == 'think' else 'at once'):22s} " + " ".join(f"{a:12.1f}" for a in accs)
                  + f"   {sum(r[str(i)]['tok'] for i in idx) / len(idx):8.0f}")
        for name, d in runs:
            p = d / f"preds_{split}_floor.jsonl"
            if not p.exists():
                continue
            pr = [json.loads(l) for l in open(p)]
            accs = [100 * sum(pr[i]["ok"] for i in g) / len(g) for g in groups.values()]
            print(f"{name + ' (one pass)':22s} " + " ".join(f"{a:12.1f}" for a in accs) + f"   {0:8d}")
