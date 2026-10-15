"""Copies the packed factory rows into the trainer's data folder for V45, slimmed to the fields the trainer reads, one
kind per family (the MIX draws each kind from its own pool), plus the fresh-seed validation splits for the readouts.
The shell rows must be the ones re-rendered in client 0.1.2's guard layout (rerender_shell.py) unless
--allow-old-shell-layout is given. --dry-run writes into a scratch folder instead and only reports.
Also writes v45_v44git.jsonl: V44's git family (kind floorGV) without its in_progress question, which is always "no" (V44
STATUS note). --only git,sql,python prepares those families now (v45g needs git only) and leaves shell for later.
Every file is written to a temporary name and renamed into place, so a run that is loading the data meanwhile never reads
half a file; v45_v44git is rewritten only when git is prepared (or missing). v45val_rx (300 rows per family) is drawn
from the four families' validation files whenever the shell one is in the guard layout, whatever --only says.
python3 prepare_data.py [--dry-run] [--allow-old-shell-layout] [--only fam,fam]"""
import hashlib
import json
import os
import random
import sys

SRC = "/root/decis/mission/F/data"
FAC = "/dev/shm/conseq/fac" if "--dry-run" not in sys.argv else "/tmp/rxF_v45_dryrun"
KEEP = ("kind", "world", "family", "template", "qtype", "steps", "question", "gold", "gold0", "known0", "floor", "ceiling", "id")
FAMS = {"shell": ("floorRXsh", "v45rx_shell"), "git": ("floorRXgit", "v45rx_git"), "python": ("floorRXpy", "v45rx_py"),
        "sql": ("floorRXsql", "v45rx_sql")}
VAL = {"shell": "val_shell", "git": "val_gitfam", "python": "val_pyfam", "sql": "val_sqlfam"}


def slim(r, kind=None):
    out = {k: r[k] for k in KEEP if k in r}
    if kind:
        out["kind"] = kind
    return out


def write_atomic(path, rows):
    tmp = f"{path}.tmp{os.getpid()}"
    n = 0
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    os.replace(tmp, path)
    return n


def val_source(fam):
    if fam == "shell":
        c012 = f"{SRC}/val_shell_c012.jsonl"
        return c012 if os.path.exists(c012) else (f"{SRC}/val_shell.jsonl" if "--allow-old-shell-layout" in sys.argv else None)
    return f"{SRC}/{VAL[fam]}.jsonl"


def main():
    os.makedirs(FAC, exist_ok=True)
    rep = {}
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else set(FAMS)
    shell_src = f"{SRC}/train_shell_c012.jsonl"
    if "shell" in only and not os.path.exists(shell_src):
        if "--allow-old-shell-layout" not in sys.argv and "--dry-run" not in sys.argv:
            raise SystemExit("train_shell_c012.jsonl missing: run rerender_shell.py after C012 freezes its layout, or use --only")
        shell_src = f"{SRC}/train_shell.jsonl"
    rep["shell_source"] = shell_src if "shell" in only else "(not prepared)"
    if "git" in only or not os.path.exists(f"{FAC}/v45_v44git.jsonl"):
        v44 = [json.loads(l) for l in open("/root/decis/conseq/v44/data/v44train_git.jsonl")]
        n_gv = write_atomic(f"{FAC}/v45_v44git.jsonl", (slim(r, "floorGV") for r in v44 if r["qtype"] != "in_progress"))
        rep["v45_v44git"] = {"rows": n_gv, "dropped_in_progress": len(v44) - n_gv}
    else:
        rep["v45_v44git"] = "(kept as it is)"
    for fam, (kind, name) in FAMS.items():
        if fam not in only:
            continue
        src = shell_src if fam == "shell" else f"{SRC}/train_{fam}.jsonl"
        n = write_atomic(f"{FAC}/{name}.jsonl", (slim(json.loads(l), kind) for l in open(src) if not json.loads(l).get("quarantined")))
        vsrc = val_source(fam) or f"{SRC}/{VAL[fam]}.jsonl"
        nv = write_atomic(f"{FAC}/v45val_{fam}.jsonl", (slim(json.loads(l), "floor") for l in open(vsrc)))
        rep[fam] = {"train_rows": n, "train_source": src, "train_file": f"{FAC}/{name}.jsonl", "val_rows": nv, "val_source": vsrc,
                    "bytes": os.path.getsize(f"{FAC}/{name}.jsonl")}
    srcs = {fam: val_source(fam) for fam in FAMS}
    if not all(srcs.values()):  # the shell validation rows are not in the guard layout yet
        rep["v45val_rx"] = "(not written: no shell validation rows in the guard layout)"
        rep["fac"] = FAC
        print(json.dumps(rep, indent=1))
        return
    val_sample = []
    for fam in FAMS:
        vrows = [slim(json.loads(l), "floor") for l in open(srcs[fam])]
        random.Random(45).shuffle(vrows)
        val_sample += vrows[:300]
    val_sample.sort(key=lambda r: hashlib.md5(r["id"].encode()).hexdigest())
    rep["v45val_rx"] = {"rows": write_atomic(f"{FAC}/v45val_rx.jsonl", val_sample), "sources": srcs}
    rep["fac"] = FAC
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
