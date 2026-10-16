"""Overlap check of the WS-F training rows against every held-out test (OVERLAP.md).
1. identical floors (whitespace-normalized) between our rows and any held-out prompt text;
2. shared word 8-grams between our floors and each held-out suite, after removing the 8-grams of our own fixed layout
   text (rules, notes, question wording), reported with examples;
3. per family, verbatim action overlap: shell commands vs shell_wild, SQL statements vs sql_wild, git commands vs
   git_wild and the client 0.1.1 confirmation set; python code-token 8-grams vs CRUXEval (functions and inputs).
python3 overlap.py <data_dir> <heldout_dir> <out.json>"""
import collections
import glob
import hashlib
import io
import json
import os
import re
import sys
import tokenize

data_dir, held_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
W = re.compile(r"[A-Za-z0-9_]+(?:[.\-'][A-Za-z0-9_]+)*")


def words(t):
    return W.findall(t.lower())


def grams(ws, n=8):
    return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def strings(x, out):
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for v in x.values():
            strings(v, out)
    elif isinstance(x, list):
        for v in x:
            strings(v, out)
    return out


HELD = {  # suite -> file names inside heldout_dir
    "shell_wild": ["shell_wild_items.jsonl"], "sql_wild": ["sql_wild_items.jsonl"], "git_wild": ["git_wild_items.jsonl"],
    "client011_confirm": ["confirm_items.jsonl"], "apps": ["apps_items.jsonl"], "rules_stress": ["rules_stress_items.jsonl"],
    "accumulation": ["accumulation_items.jsonl"], "habit_vs_rule": ["habit_items.jsonl"], "languages_formats": ["lang_items.jsonl"],
    "cruxeval": ["cruxeval_items.jsonl"],
}
held_text = {}
for suite, files in HELD.items():
    txt = []
    for f in files:
        p = os.path.join(held_dir, f)
        if os.path.exists(p):
            for l in open(p):
                try:
                    txt.append(strings(json.loads(l), []))
                except Exception:  # noqa: BLE001
                    pass
    held_text[suite] = txt

fams = {}
for p in sorted(glob.glob(os.path.join(data_dir, "*.jsonl"))):
    name = os.path.basename(p).replace(".jsonl", "")
    if name.startswith("test_") or name.startswith("train_"):
        continue
    rows = [json.loads(l) for l in open(p)]
    fams[name] = rows

# layout 8-grams to ignore: the fixed text every row of a family shares
layout = set()
for name, rows in fams.items():
    c = collections.Counter()
    sample = rows[:: max(1, len(rows) // 3000)]
    for r in sample:
        c.update(grams(words(r["floor"])))
    layout |= {g for g, k in c.items() if k >= 0.2 * len(sample)}
    for r in sample:
        layout |= grams(words(r["question"]["instructions"]))

report = {"families": {k: len(v) for k, v in fams.items()}, "identical_floors": {}, "shared_8grams": {}, "actions": {}}
held_norm = {s: {hashlib.md5(norm(x).encode()).hexdigest() for item in v for x in item if len(x) > 200} for s, v in held_text.items()}
held_grams = {s: set().union(*[grams(words(" ".join(item))) for item in v]) if v else set() for s, v in held_text.items()}
for name, rows in fams.items():
    fl = {hashlib.md5(norm(r["floor"]).encode()).hexdigest() for r in rows}
    report["identical_floors"][name] = {s: len(fl & h) for s, h in held_norm.items()}
    ours = set()
    for r in rows:
        ours |= grams(words(r["floor"]))
    ours -= layout
    shared = {}
    for s, hg in held_grams.items():
        inter = ours & hg
        shared[s] = {"n": len(inter), "examples": sorted(inter)[:5]}
    report["shared_8grams"][name] = shared


def held_field(suite, key):
    out = []
    for f in HELD[suite]:
        p = os.path.join(held_dir, f)
        if os.path.exists(p):
            for l in open(p):
                r = json.loads(l)
                v = r.get(key)
                if isinstance(v, list):
                    out += [x for x in v if isinstance(x, str)]
                elif isinstance(v, str):
                    out.append(v)
    return out


def verbatim(ours, theirs):
    t = set(x.strip() for x in theirs)
    o = collections.Counter(x.strip() for x in ours)
    hit = {x: k for x, k in o.items() if x in t}
    return {"distinct_ours": len(o), "distinct_theirs": len(t), "shared_distinct": len(hit),
            "share_of_their_distinct": round(len(hit) / max(1, len(t)), 3), "examples": sorted(hit)[:12]}


if "shell" in fams:
    report["actions"]["shell_vs_shell_wild"] = verbatim([c for r in fams["shell"] for c in r["struct"]["cmds"]],
                                                         held_field("shell_wild", "cmds"))
if "sql" in fams:
    their = []
    for f in HELD["sql_wild"]:
        p = os.path.join(held_dir, f)
        if os.path.exists(p):
            for l in open(p):
                their += json.loads(l).get("actions", [])
    report["actions"]["sql_vs_sql_wild"] = verbatim([s for r in fams["sql"] for s in r["struct"]["stmts"]], their)
if "git" in fams:
    ours = [c for r in fams["git"] for c in r["struct"]["cmds"]]
    report["actions"]["git_vs_git_wild"] = verbatim(ours, held_field("git_wild", "cmds") + held_field("git_wild", "commands"))
    report["actions"]["git_vs_client011_confirm"] = verbatim(ours, held_field("client011_confirm", "cmds") +
                                                             held_field("client011_confirm", "commands"))


def code_grams(src, n=8):
    toks = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type in (tokenize.NAME, tokenize.OP, tokenize.NUMBER, tokenize.STRING):
                toks.append(t.string)
    except Exception:  # noqa: BLE001
        toks = re.findall(r"\w+|[^\s\w]", src)
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


if "python" in fams:
    cg = set()
    for item in held_text.get("cruxeval", []):
        for x in item:
            if "def " in x or "(" in x:
                cg |= code_grams(x)
    ours = set()
    for r in fams["python"]:
        ours |= code_grams("\n".join(r["struct"]["setup"] + r["struct"]["actions"]))
    inter = ours & cg
    report["actions"]["python_vs_cruxeval_code_8grams"] = {"ours": len(ours), "cruxeval": len(cg), "shared": len(inter),
                                                           "examples": sorted(inter)[:15]}
json.dump(report, open(out_path, "w"), indent=1)
print(json.dumps({k: v for k, v in report.items() if k != "shared_8grams"}, indent=1)[:4000])
print("shared 8-grams (n):", {f: {s: x["n"] for s, x in v.items()} for f, v in report["shared_8grams"].items()})
