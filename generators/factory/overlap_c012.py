"""Overlap of the shell rows in client 0.1.2's guard layout (train + val) with shell_wild (OVERLAP.md, Addendum 3 of
PLAN_v45.md). The guard's listing header was written after shell_wild's, so the two share format words; this check
separates the format from the items:
1. format: word 8-grams of the guard's fixed text (rules as rendered, listing header, line templates, notes, questions,
   the world layout lines; plus every 8-gram in >= 20% of our floors) that also occur in shell_wild's items, listed in full;
2. items: the 8-grams of our floors left after removing that format, shared with shell_wild, counted with examples;
3. identical floors (whitespace-normalized, vs every shell_wild string over 200 characters), verbatim command lines, and
   items with the same command lines on the same set of file names.
python3 overlap_c012.py <c012 jsonl,...> <shell_wild_items.jsonl> <ekbasis package dir> <out.json>"""
import collections
import hashlib
import json
import re
import sys

ours_paths, held_path, pkg, out_path = sys.argv[1].split(","), sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, pkg)
from ekbasis import prompts as P  # noqa: E402
from ekbasis import shell as S  # noqa: E402

W = re.compile(r"[A-Za-z0-9_]+(?:[.\-'][A-Za-z0-9_]+)*")


def words(t):
    return W.findall(t.lower())


def grams(t, n=8):
    ws = words(t)
    return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


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


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


ours = [json.loads(l) for p in ours_paths for l in open(p)]
held = [json.loads(l) for l in open(held_path)]
held_grams = set().union(*[grams(s) for h in held for s in strings(h, [])])

# 1. the guard's fixed text, as the rows show it
rules = ours[0]["floor"].split("\n\nCurrent state:")[0]
fixed = [rules, S.LISTING_HEAD, S.NOTES_LABEL, S.NOTE_NO_CLOBBER_94, S.SHELL_LOST["instructions"], P.WORLD_NOTE,
         "Current state:", "Actions, in order:", "This is the state after all the actions.", "State after the actions:",
         "the starting folder itself (.): folder,", "Not listed:", "Same content elsewhere (not listed above):",
         "What the shell does before running them:", "How the commands' arguments apply here:",
         "Not evaluated by the guard:", "What those parts touch may be missing from the listing."]
fixed += [note for _, note in S.NOTES] + [S.shell_fails(k)["instructions"] for k in (1, 2, 3)]
fixed_grams = set().union(*[grams(t) for t in fixed])
c = collections.Counter()
for r in ours:
    c.update(grams(r["floor"]))
frequent = {g for g, k in c.items() if k >= 0.2 * len(ours)}
q_grams = set().union(*[grams(r["question"]["instructions"]) for r in ours])
layout = fixed_grams | frequent | q_grams
format_shared = sorted(layout & held_grams)

# 2. item text
our_grams = set().union(*[grams(r["floor"]) for r in ours])
item_shared = sorted((our_grams - layout) & held_grams)

# 3. identical floors, command lines, same commands on the same names
held_norm = {hashlib.md5(norm(s).encode()).hexdigest() for h in held for s in strings(h, []) if len(s) > 200}
identical = sum(1 for r in ours if hashlib.md5(norm(r["floor"]).encode()).hexdigest() in held_norm)
our_cmds = collections.Counter(c_.strip() for r in ours for c_ in r["struct"]["cmds"])
held_cmds = {c_.strip() for h in held for c_ in h.get("cmds", [])}
shared_cmds = sorted(set(our_cmds) & held_cmds)
held_items = {(tuple(c_.strip() for c_ in h.get("cmds", [])), frozenset(h.get("state", {}))) for h in held}
same_item = sorted({r["id"] for r in ours if (tuple(c_.strip() for c_ in r["struct"]["cmds"]), frozenset(r["struct"]["tree"]))
                    in held_items})

report = {
    "rows": len(ours), "shell_wild_items": len(held),
    "format_8grams_shared": {"n": len(format_shared), "all": format_shared},
    "item_8grams_shared": {"n": len(item_shared), "of_our_item_8grams": len(our_grams - layout), "examples": item_shared[:20]},
    "identical_floors": identical,
    "command_lines": {"distinct_ours": len(our_cmds), "distinct_shell_wild": len(held_cmds), "shared": len(shared_cmds),
                      "shared_list": shared_cmds},
    "same_commands_on_same_names": {"n": len(same_item), "examples": same_item[:10]},
    "listing_headers": {"guard": S.LISTING_HEAD,
                        "shell_wild": sorted({h["listing"].split("\n")[0] for h in held if h.get("listing")})},
}
json.dump(report, open(out_path, "w"), indent=1)
print(json.dumps({k: (v if k != "format_8grams_shared" else {"n": v["n"], "all": v["all"][:40]}) for k, v in report.items()},
                 indent=1)[:6000])
