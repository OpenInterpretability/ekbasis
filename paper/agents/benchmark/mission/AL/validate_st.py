"""Check every ledger task before any agent run, on the real stage with the mock model: the right path (process all,
pay from the covering account, report the generator's final balances) must be scored a success with an exact report
and no overdraft; the wrong path (the other account at every decision) must end with an overdraft. On the first task
the tracker (TRACK=1) is exercised too: it must follow every instruction and answer `balances`. No model, no Claude.
    python3 validate_st.py -> validation_st.json"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from judge_al import score_session  # noqa: E402

PORT, MOCK = 47392, 8797


def post(op, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/{op}", json.dumps(body or {}).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def run(f, tid, label, ops, track=False):
    env = dict(os.environ, FORESEE_URL=f"http://127.0.0.1:{MOCK}/foresee", WEB_ROOT=os.path.join(HERE, "web"), TRACK="1" if track else "0")
    st = subprocess.Popen(["node", "stage_al.mjs", f, "--port", str(PORT)], cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(120):
            try:
                post("look")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        errors, bal = [], None
        for op in ops:
            r = post("click", {"element": op[1]}) if op[0] == "click" else post("type_text", {"element": op[1], "text": op[2]})
            if "error" in r:
                errors.append(f"{op}: {r['error']}")
        if track:
            bal = post("balances").get("result", "")
        name = f"stval/{tid}_{label}"
        post(f"save?name={name}")
        try:
            post("quit")
        except Exception:  # noqa: BLE001
            pass
        st.wait(timeout=20)
        s = score_session(os.path.join(HERE, "sessions", f"{name}.json"))
        meta = json.load(open(os.path.join(HERE, "sessions", f"{name}.json")))["meta"]
        return {"errors": errors, "balances": bal, "tracker_steps": len((meta.get("tracker") or {}).get("steps", [])), **s}
    finally:
        if st.poll() is None:
            st.kill()


def main():
    os.makedirs(os.path.join(HERE, "sessions", "stval"), exist_ok=True)
    mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_al.py")], env=dict(os.environ, PORT=str(MOCK)))
    time.sleep(1)
    out = []
    try:
        for i, line in enumerate(open(os.path.join(HERE, "tasks_st.jsonl"))):
            t = json.loads(line)
            m = t["meta"]
            f = os.path.join(HERE, "tasks_st", f"{m['id']}.json")
            r = run(f, m["id"], "right", m["paths"]["right"], track=(i == 0))
            w = run(f, m["id"], "wrong", m["paths"]["wrong"])
            ok = r["success"] and r["report_exact"] and not r["harm"] and not r["errors"] and w["harm"] and not w["errors"]
            if i == 0:
                ok = ok and r["tracker_steps"] == m["n_instructions"] and r["balances"].startswith("Ekbasis tracker")
            out.append({"id": m["id"], "ok": ok, "right": r, "wrong": w})
            print(f"{m['id']} {'OK ' if ok else 'BAD'} right: success={r['success']} exact={r['report_exact']} overdrafts={r['overdrafts']} "
                  f"decisions={r['decisions_right']}/{r['decisions']} | wrong: overdrafts={w['overdrafts']}"
                  + (f" | tracker steps={r['tracker_steps']} balances='{r['balances'][:90]}'" if i == 0 else "")
                  + (f" | errors {r['errors'] + w['errors']}" if not ok else ""), flush=True)
    finally:
        mock.kill()
    json.dump(out, open(os.path.join(HERE, "validation_st.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{len(out)} tasks, {sum(r['ok'] for r in out)} OK")


if __name__ == "__main__":
    main()
