"""Frontier test: Qwen-AgentWorld-35B-A3B (a general language world model) answering Ekbasis' typed questions on the
same items (floor prompt: rules + state + actions; the question; lettered options). It may reason first; the last
'Answer: X' line is parsed. vLLM OpenAI server on 127.0.0.1:8100.
    python3 frontier_eval.py SPLIT N_MAX OUT.jsonl"""
import json, os, random, re, sys, time, urllib.request, concurrent.futures as cf
THINK, MAXTOK, CONC = os.environ.get("AW_THINK", "1"), int(os.environ.get("AW_MAX", "4096")), int(os.environ.get("AW_CONC", "32"))
sys.path.insert(0, "/root/decis/serve_v13/eikos")
import decision_core as dc
split, nmax, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
rows = [json.loads(l) for l in open(f"/root/v50p/data/{split}.jsonl")]
idx = list(range(len(rows)))
if len(idx) > nmax:
    idx = sorted(random.Random(20261015).sample(idx, nmax))
LET = [chr(65 + i) for i in range(26)] + [a + b for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
def prompt(ex):
    q = ex["question"]; opts = dc.options_of(q)          # [(answer value, description)]
    lines = "\n".join(f"{LET[k]}. {desc}" for k, (_, desc) in enumerate(opts))
    return (f"{ex['floor']}\n\nQuestion: {q['instructions']}\nOptions:\n{lines}\n\n"
            "Work out the state after the actions, then give the letter of the correct option on the last line as "
            "'Answer: <letter>'."), opts
def gold_letter(ex, opts):
    lab = ("yes" if ex["gold"] in (True, "True", "true") else "no") if ex["question"]["type"] == "noul" else str(ex["gold"])
    vals = [v for v, _ in opts]
    return LET[vals.index(lab)] if lab in vals else None
def ask(i):
    ex = rows[i]; p, opts = prompt(ex)
    body = json.dumps({"model": "aw", "messages": [{"role": "user", "content": p}], "max_tokens": MAXTOK,
                       "temperature": 0.6, "top_p": 0.95, **({"chat_template_kwargs": {"enable_thinking": False}} if THINK == "0" else {})}).encode()
    t, r = time.time(), None
    for _ in range(3):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8100/v1/chat/completions", body,
                         {"Content-Type": "application/json"}), timeout=900))
            break
        except Exception:
            time.sleep(5)
    txt = (r["choices"][0]["message"].get("content") or "") if r else ""
    m = re.findall(r"Answer:\s*\**\s*([A-Z]{1,2})\b", txt)
    pred, gold = (m[-1] if m else None), gold_letter(ex, opts)
    return {"i": i, "steps": ex.get("steps"), "qtype": ex.get("qtype"), "world": ex.get("world"), "pred": pred, "gold": gold,
            "ok": pred is not None and pred == gold, "s": round(time.time() - t, 2),
            "tokens": (r or {}).get("usage", {}).get("completion_tokens"),
            "finish": (r["choices"][0].get("finish_reason") if r else None), "tail": txt[-160:]}
with open(out, "w") as f, cf.ThreadPoolExecutor(CONC) as ex:
    for res in ex.map(ask, idx):
        f.write(json.dumps(res) + "\n")
print(split, "FIM", len(idx))
