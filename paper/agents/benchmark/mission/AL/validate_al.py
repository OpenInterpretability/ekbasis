"""Check every look-ahead task before any agent run, on the real stage (browser + app code) with the mock model: the
'right' path must end in success without harm, the 'wrong' path must not end in success (it should end in harm), and
advise (on the first screen) and foresee (on the last element of the right path) must return well-formed text.
No model, no Claude.  python3 validate_al.py [tasks_la.jsonl] [tasks_la] -> validation_la.json"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from judge_al import score_session  # noqa: E402

PORT, MOCK = 47390, 8798


def post(op, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/{op}", json.dumps(body or {}).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def run_path(task_file, tid, label, ops, probe):
    env = dict(os.environ, FORESEE_URL=f"http://127.0.0.1:{MOCK}/foresee", WEB_ROOT=os.path.join(HERE, "web"))
    st = subprocess.Popen(["node", "stage_al.mjs", task_file, "--port", str(PORT)], cwd=HERE, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(120):
            try:
                post("look")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        errors, adv, fs = [], None, None
        if probe:
            adv = post("advise", {"candidates": []})
            if "error" in adv:
                errors.append(f"advise: {adv['error']}")
        for i, op in enumerate(ops):
            if probe and i == len(ops) - 1 and op[0] == "click":
                fs = post("foresee", {"element": op[1]})
                if "error" in fs:
                    errors.append(f"foresee {op[1]}: {fs['error']}")
            r = post("click", {"element": op[1]}) if op[0] == "click" else post("type_text", {"element": op[1], "text": op[2]})
            if "error" in r:
                errors.append(f"{op}: {r['error']}")
        name = f"alval/{tid}_{label}"
        post(f"save?name={name}")
        try:
            post("quit")
        except Exception:  # noqa: BLE001
            pass
        st.wait(timeout=20)
        s = score_session(os.path.join(HERE, "sessions", f"{name}.json"))
        return {"errors": errors, "advise": (adv or {}).get("result", "")[:200], "foresee": (fs or {}).get("result", "")[:200], **s}
    finally:
        if st.poll() is None:
            st.kill()


def main():
    tasks_file = sys.argv[1] if len(sys.argv) > 1 else "tasks_la.jsonl"
    tdir = sys.argv[2] if len(sys.argv) > 2 else "tasks_la"
    os.makedirs(os.path.join(HERE, "sessions", "alval"), exist_ok=True)
    mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_al.py")], env=dict(os.environ, PORT=str(MOCK)))
    time.sleep(1)
    out, bad = [], 0
    try:
        for line in open(os.path.join(HERE, tasks_file)):
            t = json.loads(line)
            m = t["meta"]
            f = os.path.join(HERE, tdir, f"{m['id']}.json")
            r = run_path(f, m["id"], "right", m["paths"]["right"], probe=True)
            row = {"id": m["id"], "kind": m["kind"], "right": r}
            ok = r["success"] and not r["harm"] and not r["errors"] and r["advise"].startswith("Ekbasis look-ahead")
            if m["paths"]["wrong"]:
                w = run_path(f, m["id"], "wrong", m["paths"]["wrong"], probe=False)
                row["wrong"] = w
                ok = ok and not w["success"] and w["harm"] and not w["errors"]
            row["ok"] = ok
            bad += not ok
            print(f"{m['id']:20s} {m['kind']:7s} {'OK ' if ok else 'BAD'} right: success={r['success']} harm={r['harm']} clicks={r['actions']}"
                  + (f" | wrong: success={row['wrong']['success']} harm={row['wrong']['harm']}" if 'wrong' in row else '')
                  + (f" | errors: {r['errors'] + row.get('wrong', {}).get('errors', [])}" if not ok else ''), flush=True)
            out.append(row)
    finally:
        mock.kill()
    json.dump(out, open(os.path.join(HERE, "validation_la.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{len(out)} tasks, {sum(r['ok'] for r in out)} OK, problems: {bad}")


if __name__ == "__main__":
    main()
