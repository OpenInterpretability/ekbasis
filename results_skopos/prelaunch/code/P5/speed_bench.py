# PRELAUNCH PORT (P5) of _orig/speed_bench.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""Speed and cost: the consequence model served like production (Eikos-27B with the adapter fused in, vLLM with prefix
cache, serve.py System One API) against an LLM reasoning (Qwen3.8-27B on vLLM, thinking on / off), on the same
forecasting items (a given sequence of 10-30 actions; one question about the final state).

  cq  <out>          consequence model, one action at a time: one /v1/systemone request per step carrying one typed
                     question per state variable; the next state is rebuilt from the answers
  cq1 <out>          consequence model, one pass: the whole sequence and the question in a single request
  cqm <out>          like cq, but the state is read once per step: one prompt carries every variable's question and all
                     the answers are read in the same pass (vLLM prompt logprobs at the answer slots; env VLLM_URL,
                     MODEL_DIR for the tokenizer, MULTI_STYLE json|turns as in training)
  llm <out> <think>  Qwen3.8-27B answers directly (think = 1 / 0)
  sum <dir>          accuracy, latency per item (p50 / p90), throughput, tokens; and the routing rule (use the
                     consequence model when its chain confidence is at least t, otherwise the reasoning LLM)
Each mode runs the items PAR at a time. env: N (80), PAR (16), CQ_URL, LLM_URL."""
import concurrent.futures as cf, json, math, os, random, re, sys, time, urllib.request
sys.path.insert(0, os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))  # PORT
sys.path.insert(0, os.environ["MODEL_DIR"])  # PORT: decision_core.py of the served model folder (it was serve 1.3's)
os.environ.setdefault("PROMPT_STYLE", "semif")
from envs import qchoice
from scipy.optimize import linear_sum_assignment
from worldgen import Cards, Jugs, Machines, Toggles

N, PAR = int(os.environ.get("N", "80")), int(os.environ.get("PAR", "16"))
CQ_URL = os.environ.get("CQ_URL", "http://127.0.0.1:8501/v1/systemone")
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:30110/v1/chat/completions")


def world(kind, rng):
    while True:
        w = {"jugs": Jugs, "machines": Machines, "toggles": Toggles, "cards": Cards}[kind](rng)
        if (kind == "jugs" and len(w.names) == 3) or (kind == "machines" and len(w.devs) >= 4) or \
           (kind == "toggles" and w.n >= 6 and w.three) or (kind == "cards" and w.n >= 6):
            return w


VARS = {"jugs": lambda w: [(x, qchoice(f"How many liters are in {x}?", [(str(k), f"{k} liters") for k in range(w.cap[x] + 1)])) for x in w.names],
        "toggles": lambda w: [(j, qchoice(f"What state is {w.lamp} {j + 1} in?", [(x, x) for x in w.states])) for j in range(w.n)],
        "machines": lambda w: [(d, qchoice(f"In which state is {d}?", [(x, x) for x in w.cycle])) for d in w.devs],
        "cards": lambda w: [(k, qchoice(f"Which card is at position {k + 1}?", [(x, x) for x in w.labels])) for k in range(w.n)]}


def item(i):
    kind = ["jugs", "machines", "toggles", "cards"][i % 4]
    rng = random.Random(5000 + i)
    w = world(kind, rng)
    w.name = kind
    s0 = s = w.sample_state(rng)
    acts = []
    for _ in range(rng.randint(10, 30)):
        a = w.sample_action(rng, s)
        s, _ = w.step(s, a)
        acts.append(a)
    keys_qs = VARS[kind](w)
    if kind == "cards":
        x = rng.choice(w.labels)
        key, q = ("where", x), qchoice(f"At which position is the {x}?", [(str(k), f"position {k}") for k in range(1, w.n + 1)])
    else:
        key, q = keys_qs[rng.randrange(len(keys_qs))]
    return kind, w, s0, acts, s, key, q, keys_qs


def answer_of(kind, w, s, key):
    return {"jugs": lambda: str(s["v"][key]), "toggles": lambda: w.states[s["st"][key]], "machines": lambda: w.cycle[s["st"][key]],
            "cards": lambda: str(s["xs"].index(key[1]) + 1)}[kind]()


def post(url, body, timeout=900):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def run_cq(i):
    kind, w, s0, acts, sT, key, q, keys_qs = item(i)
    t0, S, conf, mins, reqs, tin = time.time(), s0, 1.0, 1.0, 0, 0
    for a in acts:
        text = f"{w.rules}\n\nCurrent state:\n{w.render(S)}\n\nActions, in order:\n1. {w.render_action(a)}\n\n{w.floor_note()}"
        r = post(CQ_URL, {"state": text, "questions": {f"v{j}": qq for j, (_, qq) in enumerate(keys_qs)}})
        reqs, tin = reqs + 1, tin + r["usage"]["input_tokens"]
        D = {k: r["answers"][f"v{j}"]["probabilities"] for j, (k, _) in enumerate(keys_qs)}
        step = math.prod(max(d.values()) for d in D.values())
        conf, mins = conf * step, min(mins, step)
        if kind == "cards":  # the most probable valid order of the cards (assignment on -log p)
            rows, cols = linear_sum_assignment([[-math.log(D[k].get(c, 0.0) + 1e-9) for c in w.labels] for k in range(w.n)])
            S = {"xs": [w.labels[c] for c in cols]}
        elif kind == "jugs":
            S = {"v": {x: int(max(D[x], key=D[x].get)) for x in w.names}}
        elif kind == "toggles":
            S = {"st": [w.states.index(max(D[j], key=D[j].get)) for j in range(w.n)]}
        else:
            S = {"st": {d: w.cycle.index(max(D[d], key=D[d].get)) for d in w.devs}}
    pred = answer_of(kind, w, S, key)
    return {"i": i, "kind": kind, "n_act": len(acts), "ok": pred == answer_of(kind, w, sT, key), "pred": pred,
            "chain_conf": conf, "min_step": mins, "seconds": time.time() - t0, "requests": reqs, "input_tokens": tin}


_TOK = None


def init_tok():
    """The tokenizer and template pieces, loaded once before the worker threads start."""
    global _TOK, LETTERS, USER_OPEN, GEN, END_ASSIST
    import decision_core as dc
    if _TOK is None:
        from transformers import AutoTokenizer
        _TOK = AutoTokenizer.from_pretrained(os.environ["MODEL_DIR"])
        x = "\u2063"
        u = _TOK.apply_chat_template([{"role": "user", "content": x}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        USER_OPEN, GEN = u.split(x)
        a = _TOK.apply_chat_template([{"role": "user", "content": x}, {"role": "assistant", "content": x}], tokenize=False,
                                     add_generation_prompt=False, enable_thinking=False)
        END_ASSIST = a.split(x)[-1]
        LETTERS = [_TOK.encode(L, add_special_tokens=False)[0] for L in dc.LABELS]


def multi_ids(state, qs, opts_list):
    """The training layout of train_conseq.encode_multi (same tokens), for a model served by vLLM."""
    import decision_core as dc
    tok = _TOK
    shown = lambda q, lab: {"yes": "true", "no": "false"}.get(lab, lab) if q["type"] in ("noul", "boolean") else lab
    if os.environ.get("MULTI_STYLE", "json") == "turns":
        ids = tok(tok.apply_chat_template(dc.messages(state, qs[0], opts_list[0]), tokenize=False, add_generation_prompt=True,
                                          enable_thinking=False), add_special_tokens=False)["input_ids"]
        pos = [len(ids) - 1]
        for q, o in zip(qs[1:], opts_list[1:]):
            follow = json.dumps({"criterion": q.get("instructions", ""), "options": [
                {"letter": dc.LABELS[i], "description": f"{shown(q, lab)}: {desc}"} for i, (lab, desc) in enumerate(o)]}, ensure_ascii=False)
            ids = ids + tok.encode("?" + END_ASSIST + USER_OPEN + follow + GEN, add_special_tokens=False)
            pos.append(len(ids) - 1)
        return ids, pos
    system = ("Apply each supplied criterion to the supplied evidence. For each question, choose exactly one listed option. "
              "Respond with one line per question: its id, a colon and only the uppercase letter, with no explanation or reasoning.")
    user = json.dumps({"evidence": state, "questions": [
        {"id": f"Q{k + 1}", "criterion": q.get("instructions", ""),
         "options": [{"letter": dc.LABELS[i], "description": f"{shown(q, lab)}: {desc}"} for i, (lab, desc) in enumerate(o)]}
        for k, (q, o) in enumerate(zip(qs, opts_list))]}, ensure_ascii=False)
    ids, pos = tok(tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}], tokenize=False,
                                           add_generation_prompt=True, enable_thinking=False), add_special_tokens=False)["input_ids"], []
    for k in range(len(qs)):
        ids = ids + tok.encode(f"Q{k + 1}:", add_special_tokens=False)
        pos.append(len(ids) - 1)
        ids = ids + tok.encode("?\n", add_special_tokens=False)
    return ids, pos


def multi_read(state, keys_qs):
    """One vLLM request: every question's distribution over its options, read at the answer slots."""
    import decision_core as dc
    qs = [qq for _, qq in keys_qs]
    opts = [dc.options_of(qq) for qq in qs]
    ids, pos = multi_ids(state, qs, opts)
    if pos[-1] == len(ids) - 1:  # the last answer is read at the end of the prompt: a placeholder after it puts it in the prompt logprobs
        ids = ids + _TOK.encode("?", add_special_tokens=False)
    r = post(os.environ.get("VLLM_URL", "http://127.0.0.1:30130/v1/completions"),
             {"model": "decider", "prompt": ids, "max_tokens": 1, "temperature": 0.0, "prompt_logprobs": int(os.environ.get("PROMPT_LP", "4"))})
    pl = r["choices"][0]["prompt_logprobs"]
    D = {}
    for (k, _), p, o in zip(keys_qs, pos, opts):
        lp = {int(t): v["logprob"] for t, v in (pl[p + 1] or {}).items()}
        pr = [math.exp(lp.get(LETTERS[j], -30.0)) for j in range(len(o))]
        z = sum(pr)
        D[k] = {lab: x / z for (lab, _), x in zip(o, pr)}
    return D, len(ids)


def run_cqm(i):
    kind, w, s0, acts, sT, key, q, keys_qs = item(i)
    t0, S, conf, mins, reqs, tin = time.time(), s0, 1.0, 1.0, 0, 0
    for a in acts:
        text = f"{w.rules}\n\nCurrent state:\n{w.render(S)}\n\nActions, in order:\n1. {w.render_action(a)}\n\n{w.floor_note()}"
        D, n = multi_read(text, keys_qs)
        reqs, tin = reqs + 1, tin + n
        step = math.prod(max(d.values()) for d in D.values())
        conf, mins = conf * step, min(mins, step)
        if kind == "cards":
            rows, cols = linear_sum_assignment([[-math.log(D[k].get(c, 0.0) + 1e-9) for c in w.labels] for k in range(w.n)])
            S = {"xs": [w.labels[c] for c in cols]}
        elif kind == "jugs":
            S = {"v": {x: int(max(D[x], key=D[x].get)) for x in w.names}}
        elif kind == "toggles":
            S = {"st": [w.states.index(max(D[j], key=D[j].get)) for j in range(w.n)]}
        else:
            S = {"st": {d: w.cycle.index(max(D[d], key=D[d].get)) for d in w.devs}}
    pred = answer_of(kind, w, S, key)
    return {"i": i, "kind": kind, "n_act": len(acts), "ok": pred == answer_of(kind, w, sT, key), "pred": pred,
            "chain_conf": conf, "min_step": mins, "seconds": time.time() - t0, "requests": reqs, "input_tokens": tin}


def run_cq1(i):
    kind, w, s0, acts, sT, key, q, keys_qs = item(i)
    text = (f"{w.rules}\n\nCurrent state:\n{w.render(s0)}\n\nActions, in order:\n" + "\n".join(f"{j + 1}. {w.render_action(a)}" for j, a in enumerate(acts))
            + f"\n\n{w.floor_note()}")
    t0 = time.time()
    r = post(CQ_URL, {"state": text, "questions": {"q": q}})
    a = r["answers"]["q"]
    return {"i": i, "kind": kind, "n_act": len(acts), "ok": a["choice"] == answer_of(kind, w, sT, key), "pred": a["choice"],
            "chain_conf": a["confidence"], "seconds": time.time() - t0, "requests": 1, "input_tokens": r["usage"]["input_tokens"]}


def run_llm(i, think):
    kind, w, s0, acts, sT, key, q, keys_qs = item(i)
    prompt = (f"{w.rules}\n\nCurrent state:\n{w.render(s0)}\n\nActions, in order:\n" + "\n".join(f"{j + 1}. {w.render_action(a)}" for j, a in enumerate(acts))
              + f"\n\nQuestion: after all the actions, {q['instructions'][0].lower() + q['instructions'][1:]} Options: {', '.join(q['criteria'])}."
              + ("\nEnd your answer with a line 'ANSWER: <option>'." if think else
                 "\nNo time to work it out: reply at once with only the line 'ANSWER: <option>' and nothing else."))
    body = {"model": "agent", "messages": [{"role": "user", "content": prompt}], "temperature": 0.6 if think else 0.0,
            "top_p": 0.95, "max_tokens": 12000 if think else 30}
    if not think:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    t0 = time.time()
    r = post(LLM_URL, body, timeout=1800)
    out = (r["choices"][0]["message"].get("content") or "").split("</think>")[-1]
    m = re.findall(r"ANSWER:\s*([^\s\n]+)", out)
    pred = m[-1].strip(".*`") if m else ""
    return {"i": i, "kind": kind, "n_act": len(acts), "ok": pred == answer_of(kind, w, sT, key), "pred": pred,
            "tokens": r["usage"]["completion_tokens"], "input_tokens": r["usage"]["prompt_tokens"], "seconds": time.time() - t0}


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "sum":
        for f in sorted(os.listdir(sys.argv[2])):
            if not f.endswith(".jsonl"):
                continue
            rows = [json.loads(l) for l in open(os.path.join(sys.argv[2], f))]
            meta = json.load(open(os.path.join(sys.argv[2], f.replace(".jsonl", ".meta.json"))))
            secs = sorted(r["seconds"] for r in rows)
            acc = {k: f"{100 * sum(r['ok'] for r in rows if r['kind'] == k) / max(1, sum(1 for r in rows if r['kind'] == k)):.0f}%"
                   for k in ("jugs", "machines", "toggles", "cards")}
            tok = f"generated {sum(r.get('tokens', 0) for r in rows) / len(rows):6.0f} tok/item, read {sum(r['input_tokens'] for r in rows) / len(rows):6.0f}"
            print(f"{f:20s} acc {100 * sum(r['ok'] for r in rows) / len(rows):5.1f}% {acc} | latency p50 {secs[len(secs) // 2]:6.1f}s "
                  f"p90 {secs[int(0.9 * len(secs))]:6.1f}s | {60 * len(rows) / meta['wall']:6.1f} items/min at {meta['par']} parallel | {tok}")
        d = sys.argv[2]
        for cq, llm in (("cq_par16.jsonl", "think_par16.jsonl"), ("cq1_par16.jsonl", "think_par16.jsonl"), ("cq_par16.jsonl", "nothink_par16.jsonl")):
            if not (os.path.exists(os.path.join(d, cq)) and os.path.exists(os.path.join(d, llm))):
                continue
            A = {r["i"]: r for r in map(json.loads, open(os.path.join(d, cq)))}
            B = {r["i"]: r for r in map(json.loads, open(os.path.join(d, llm)))}
            ids = sorted(set(A) & set(B))
            print(f"\nrouting: {cq.split('_')[0]} when its confidence >= t, otherwise {llm.split('_')[0]} ({len(ids)} items)")
            print(f"{'t':>6s} {'to LLM':>7s} {'acc':>6s} {'mean s':>7s} {'gen tok':>8s}")
            for t in (0.0, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.01):
                go = [i for i in ids if A[i]["chain_conf"] < t]
                acc = sum((B[i] if i in go else A[i])["ok"] for i in ids) / len(ids)
                sec = sum(A[i]["seconds"] + (B[i]["seconds"] if i in go else 0) for i in ids) / len(ids)
                tok = sum(B[i]["tokens"] for i in go) / len(ids)
                print(f"{t:6.2f} {100 * len(go) / len(ids):6.0f}% {100 * acc:5.1f}% {sec:7.1f} {tok:8.0f}")
            wrong = [A[i]["chain_conf"] for i in ids if not A[i]["ok"]]
            print(f"consequence model wrong on {len(wrong)}; their chain confidences: {sorted(round(c, 3) for c in wrong)}")
        sys.exit()
    out = sys.argv[2]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fn = {"cq": run_cq, "cq1": run_cq1, "cqm": run_cqm}.get(mode) or (lambda i: run_llm(i, sys.argv[3] == "1"))
    if mode == "cqm":
        init_tok()
    t0 = time.time()
    with cf.ThreadPoolExecutor(PAR) as ex:
        rows = list(ex.map(fn, range(N)))
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    json.dump({"wall": time.time() - t0, "par": PAR, "n": N}, open(out.replace(".jsonl", ".meta.json"), "w"))
    print(f"{mode}: {N} items in {time.time() - t0:.0f} s, accuracy {100 * sum(r['ok'] for r in rows) / N:.1f}%")
