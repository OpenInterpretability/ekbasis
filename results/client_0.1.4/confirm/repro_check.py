"""WS-U confirmatory test: the patched generators with their DEFAULT settings (the dev seeds) must make exactly the dev
items. Run in a scratch copy; no fresh item is made and no model is called.
python3 repro_check.py <scratch dir with make_fresh.py copies>   ->  prints one verdict per suite, exit 1 on any mismatch"""
import hashlib
import json
import os
import subprocess
import sys

CAP = "/root/decis/capability"
PY = "/opt/sglang/bin/python"


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def jl(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def run(cmd, cwd, env=None):
    e = dict(os.environ, PYTHONPATH=f"{CAP}/client", **(env or {}))
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    assert p.returncode == 0, (cmd, p.stdout[-800:], p.stderr[-800:])
    return p.stdout


def main():
    d = os.path.abspath(sys.argv[1])
    ok = True
    tok = {"TOK": "/dev/shm/conseq/merged_w4a5"}
    # rules_stress (main + addendum), accumulation, sql_wild: byte-identical items files
    run([PY, "make_items.py"], f"{d}/rules_stress", tok)
    run([PY, "make_addendum.py"], f"{d}/rules_stress", tok)
    run([PY, "accum.py"], f"{d}/accumulation")
    run([PY, "sql_wild.py", f"{d}/sql_wild/items.jsonl"], f"{d}/sql_wild")
    for suite, fn in (("rules_stress", "items.jsonl"), ("rules_stress", "items_addendum.jsonl"),
                      ("accumulation", "items.jsonl"), ("sql_wild", "items.jsonl")):
        same = sha(f"{d}/{suite}/{fn}") == sha(f"{CAP}/{suite}/{fn}")
        ok &= same
        print(f"{suite:13s} {fn:22s} identical to dev: {same}")
    # shell_wild: the scenario list before execution (the dev file also carries the run's truths)
    code = ("import sys, json; sys.path.insert(0, '.'); import shell_wild as S; "
            "print(json.dumps([{k: g[k] for k in ('id','family','variant','state','cmds','exists','content')} for g in S.build_items()]))")
    mine = json.loads(run([PY, "-c", code], f"{d}/shell_wild"))
    dev = [{k: g[k] for k in ("id", "family", "variant", "state", "cmds", "exists", "content")} for g in jl(f"{CAP}/shell_wild/items.jsonl")]
    same = mine == dev
    ok &= same
    print(f"shell_wild    scenarios ({len(mine)} vs {len(dev)}) identical to dev: {same}")
    # git_wild: items (setup and commands) as listed by make_items()
    code = ("import sys, json; sys.path.insert(0, '.'); import git_wild as G; "
            "print(json.dumps([{k: i[k] for k in ('id','setup','commands')} for i in G.make_items()]))")
    mine = json.loads(run([PY, "-c", code], f"{d}/git_wild"))
    dev = [{k: i[k] for k in ("id", "setup", "commands")} for i in jl(f"{CAP}/git_wild/items.jsonl")]
    same = sorted(mine, key=lambda x: x["id"]) == sorted(dev, key=lambda x: x["id"])
    ok &= same
    print(f"git_wild      items ({len(mine)} vs {len(dev)}) identical to dev: {same}")
    print("ALL IDENTICAL" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
