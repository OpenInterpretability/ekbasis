"""WS-U part 2, live: the self-check (verify) and negated (negate) questions on WS-P's 6,000-question sample, same
evidence as the original prompt, one question per request, on the batch API. Resumable (skips done keys)."""
import concurrent.futures as cf
import json
import os
import sys
import urllib.request

API = os.environ.get("EKBASIS_URL", "http://127.0.0.1:8543")
P = "/root/decis/mission/P"
OUT = "results/part2_live.jsonl"


def parse(prompt):
    a = prompt.index("<|im_start|>user\n") + len("<|im_start|>user\n")
    b = prompt.index("<|im_end|>", a)
    return json.loads(prompt[a:b])


def answer_text(row, user):
    lab = row["answer"]
    idx = row["labels"].index(lab)
    desc = user["options"][idx]["description"]
    txt = desc[len(lab) + 2:] if desc.startswith(lab + ": ") else desc
    return lab if txt == lab else f"{lab} ({txt})"


def ask(state, text):
    body = {"state": state, "questions": {"q": {"type": "choice", "instructions": text, "criteria": {"yes": "yes", "no": "no"}}}}
    req = urllib.request.Request(API + "/v1/systemone", json.dumps(body).encode(), {"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=300))["answers"]["q"]
    return {"choice": d.get("choice"), "probabilities": d.get("probabilities")}


def main():
    sample = [json.loads(l) for l in open(f"{P}/results/infer_raw.jsonl")]
    data = {}
    want = {r["qid"] for r in sample}
    for l in open(f"{P}/data/dataset.jsonl"):
        r = json.loads(l)
        if r["qid"] in want:
            data[r["qid"]] = r
    done = set()
    if os.path.exists(OUT):
        done = {(j["qid"], j["kind"]) for j in map(json.loads, open(OUT))}
    jobs = []
    for s in sample:
        r = data[s["qid"]]
        u = parse(r["prompt"])
        q = u["criterion"]
        if (r["qid"], "verify") not in done:
            jobs.append((r["qid"], "verify", u["evidence"],
                         f'Consider this question: "{q}" Is "{answer_text(r, u)}" the correct answer?'))
        if sorted(r["labels"]) == ["no", "yes"] and (r["qid"], "negate") not in done:
            jobs.append((r["qid"], "negate", u["evidence"], f'Consider this question: "{q}" Is the correct answer "no"?'))
    print(f"{len(jobs)} requests to send ({len(done)} already done) -> {API}", flush=True)
    os.makedirs("results", exist_ok=True)
    with open(OUT, "a") as f, cf.ThreadPoolExecutor(16) as ex:
        futs = {ex.submit(ask, st, tx): (qid, kind, tx) for qid, kind, st, tx in jobs}
        for n, fu in enumerate(cf.as_completed(futs), 1):
            qid, kind, tx = futs[fu]
            try:
                a = fu.result()
                f.write(json.dumps({"qid": qid, "kind": kind, "text": tx, **a}) + "\n")
            except Exception as e:  # noqa: BLE001
                f.write(json.dumps({"qid": qid, "kind": kind, "error": str(e)[:200]}) + "\n")
            if n % 500 == 0:
                f.flush()
                print(f"{n}/{len(jobs)}", flush=True)
    print("PART2 LIVE DONE", flush=True)


if __name__ == "__main__":
    main()
