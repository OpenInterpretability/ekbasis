"""V46 data (PLAN_v45 Addendum 4): the anchor into the trainer's folder, and the overlap checks Addendum 4 asks for.
1. data/v46_anchor_raw.jsonl (gen_anchor.py) -> /dev/shm/conseq/fac/v46_anchor.jsonl, slimmed to the trainer's fields,
   kind floorGA (written to a temporary name and renamed);
2. anchor overlap: identical floors against every evaluation split with git items (must be 0), command lines and word
   8-grams shared with git_wild and the client 0.1.1 confirmation set (layout 8-grams removed);
3. hs_wild / hs_confirm overlap with the factory's shell training rows (v45rx_shell): identical floors, shared command
   lines, shared item 8-grams after removing the guard's layout 8-grams.
/usr/bin/python3 prepare_v46.py   -> report in v46/hs/overlap_v46.json"""
import collections
import json
import os
import re
import sys

FAC = "/dev/shm/conseq/fac"
F = "/root/decis/mission/F"
KEEP = ("kind", "world", "family", "template", "qtype", "steps", "question", "gold", "gold0", "known0", "floor", "ceiling", "id")
GIT_EVAL = ["guard_known", "guard_held", "git3_test_known", "git3_test_held", "ho_gitwild", "ho_gitconf0", "ho_gitconf1",
            "hq_guard_known", "hq_guard_held", "v44val_git", "v45val_git", "ftest_family", "ce_items", "multi_test_testfam"]
W = re.compile(r"[A-Za-z0-9_]+(?:[.\-'][A-Za-z0-9_]+)*")


def words(t):
    return W.findall(t.lower())


def grams(t, n=8):
    ws = words(t)
    return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def load(p):
    return [json.loads(l) for l in open(p)]


def floors(split):
    p = f"{FAC}/{split}.jsonl"
    return {r["floor"] for r in load(p) if isinstance(r.get("floor"), str)} if os.path.exists(p) else set()


def cmd_lines(floor, head):
    """Numbered action lines after the given header ('Commands, in order:' or 'Actions, in order:')."""
    if head not in floor:
        return []
    block = floor.split(head, 1)[1].strip().split("\n\n")[0]
    return [re.sub(r"^\d+\.\s*", "", l).strip() for l in block.splitlines() if re.match(r"^\d+\.", l.strip())]


def held_cmds(path):
    out = []
    for r in load(path):
        for k in ("cmds", "commands"):
            v = r.get(k)
            if isinstance(v, list):
                out += [x.strip() for x in v if isinstance(x, str)]
    return out


def layout_grams(rows, share=0.2):
    c = collections.Counter()
    sample = rows[:: max(1, len(rows) // 3000)]
    for r in sample:
        c.update(grams(r["floor"]))
    return {g for g, k in c.items() if k >= share * len(sample)} | set().union(*[grams(r["question"]["instructions"]) for r in sample])


def main():
    rep = {}
    raw = load(f"{F}/data/v46_anchor_raw.jsonl")
    tmp = f"{FAC}/v46_anchor.jsonl.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        for r in raw:
            f.write(json.dumps({k: r[k] for k in KEEP if k in r} | {"kind": "floorGA"}, ensure_ascii=False) + "\n")
    os.replace(tmp, f"{FAC}/v46_anchor.jsonl")
    fl = {r["floor"] for r in raw}
    rep["anchor"] = {"rows": len(raw), "distinct_floors": len(fl),
                     "by_qtype_gold": dict(collections.Counter(f"{r['qtype']}:{r['gold']}" for r in raw)),
                     "identical_floors": {s: len(fl & floors(s)) for s in GIT_EVAL}}
    ours = collections.Counter(c for r in raw for c in cmd_lines(r["floor"], "Commands, in order:"))
    lay = layout_grams(raw)
    our_g = set().union(*[grams(r["floor"]) for r in raw]) - lay
    for name, path in (("git_wild", f"{F}/heldout/git_wild_items.jsonl"), ("client011_confirm", f"{F}/heldout/confirm_items.jsonl")):
        theirs = set(held_cmds(path))
        their_g = set().union(*[grams(" ".join(x for x in r.values() if isinstance(x, str))) for r in load(path)])
        shared = sorted(set(ours) & theirs)
        rep["anchor"][f"vs_{name}"] = {"command_lines_ours": len(ours), "command_lines_theirs": len(theirs),
                                       "shared_command_lines": len(shared), "examples": shared[:12],
                                       "shared_item_8grams": len(our_g & their_g), "gram_examples": sorted(our_g & their_g)[:5]}
    shell = load(f"{FAC}/v45rx_shell.jsonl")
    sfl = {r["floor"] for r in shell}
    scmd = collections.Counter(c for r in shell for c in cmd_lines(r["floor"], "Actions, in order:"))
    slay = layout_grams(shell)
    s_g = set().union(*[grams(r["floor"]) for r in shell]) - slay
    for split in ("hs_wild", "hs_confirm"):
        rows = load(f"{FAC}/{split}.jsonl")
        hcmd = {c for r in rows for c in cmd_lines(r["floor"], "Actions, in order:")}
        h_g = set().union(*[grams(r["floor"]) for r in rows]) - slay - layout_grams(rows)
        shared = sorted(hcmd & set(scmd))
        rep[split] = {"rows": len(rows), "identical_floors_with_shell_training": len({r["floor"] for r in rows} & sfl),
                      "command_lines": len(hcmd), "shared_command_lines": len(shared), "examples": shared[:12],
                      "shared_item_8grams": len(h_g & s_g), "gram_examples": sorted(h_g & s_g)[:8]}
    json.dump(rep, open(f"{F}/v46/hs/overlap_v46.json", "w"), indent=1)
    print(json.dumps(rep, indent=1)[:5000])
    bad = sum(rep["anchor"]["identical_floors"].values()) + sum(rep[s]["identical_floors_with_shell_training"] for s in ("hs_wild", "hs_confirm"))
    if bad:
        sys.exit(f"identical floors found: {bad}")


if __name__ == "__main__":
    main()
