"""Check every task before any agent run, on the real stage (browser + app code) with a mock foresee: the scripted harmful
path must be scored harmful, the scripted safe path must be scored a safe success, and a foresee call on the last element
of each path must return a well-formed answer. No model, no Claude.
    python3 validate_tasks.py   (starts mock_foresee.py itself)  -> validation.json"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LV = os.path.abspath(os.path.join(HERE, "..", "..", "..", "launch_video"))
sys.path.insert(0, HERE)
import importlib  # noqa: E402
score_session = importlib.import_module(os.environ.get("VJUDGE", "judge")).score_session  # noqa: E402

PORT, MOCK = 47380, 8799


def post(op, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/{op}", json.dumps(body or {}).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def run_path(task_file, tid, label, ops):
    env = dict(os.environ, FORESEE_URL=f"http://127.0.0.1:{MOCK}/foresee", WEB_ROOT=os.path.join(HERE, "web"))
    st = subprocess.Popen(["node", os.environ.get("VSTAGE", "stage.mjs"), task_file, "--port", str(PORT)], cwd=LV, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(120):
            try:
                post("look")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        errors, fs = [], None
        for i, op in enumerate(ops):
            if i == len(ops) - 1:
                fs = post("foresee", {"element": op[1]})
                if "error" in fs:
                    errors.append(f"foresee {op[1]}: {fs['error']}")
            r = post("click", {"element": op[1]}) if op[0] == "click" else post("type_text", {"element": op[1], "text": op[2]})
            if "error" in r:
                errors.append(f"{op}: {r['error']}")
        name = f"xval/{tid}_{label}"
        post(f"save?name={name}")
        try:
            post("quit")
        except Exception:  # noqa: BLE001
            pass
        st.wait(timeout=20)
        s = score_session(os.path.join(LV, "sessions", f"{name}.json"))
        return {"errors": errors, "foresee": (fs or {}).get("result", "")[:300], "flagged": "<- harmful" in (fs or {}).get("result", ""), **s}
    finally:
        if st.poll() is None:
            st.kill()


def main():
    os.makedirs(os.path.join(LV, "sessions", "xval"), exist_ok=True)
    mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_foresee.py")], env=dict(os.environ, PORT=str(MOCK)))
    time.sleep(1)
    out, bad = [], 0
    try:
        for line in open(os.path.join(HERE, os.environ.get("VTASKS", "tasks.jsonl"))):
            t = json.loads(line)
            m = t["meta"]
            f = os.path.join(HERE, os.environ.get("VTASKDIR", "tasks"), f"{m['id']}.json")
            row = {"id": m["id"], "kind": m["kind"]}
            if m["paths"]["harm"]:
                h = run_path(f, m["id"], "harm", m["paths"]["harm"])
                row["harm_path"] = h
                bad += (not h["harm"]) or bool(h["errors"])
            s = run_path(f, m["id"], "safe", m["paths"]["safe"])
            row["safe_path"] = s
            bad += s["harm"] or (not s["success"]) or bool(s["errors"])
            ok = (not m["paths"]["harm"] or (row["harm_path"]["harm"] and not row["harm_path"]["errors"])) and s["success"] and not s["harm"] and not s["errors"]
            row["ok"] = ok
            print(f"{m['id']:10s} {m['kind']:7s} {'OK ' if ok else 'BAD'} harm_path={row.get('harm_path', {}).get('harm')} "
                  f"safe_path=success:{s['success']} harm:{s['harm']} {('errors: ' + '; '.join(s['errors'] + row.get('harm_path', {}).get('errors', []))) if not ok else ''}", flush=True)
            out.append(row)
    finally:
        mock.kill()
    json.dump(out, open(os.path.join(HERE, os.environ.get("VOUT", "validation.json")), "w"), indent=1, ensure_ascii=False)
    print(f"{len(out)} tasks, {sum(r['ok'] for r in out)} OK, problems: {bad}")


if __name__ == "__main__":
    main()
