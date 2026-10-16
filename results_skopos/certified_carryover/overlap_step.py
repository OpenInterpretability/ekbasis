"""Step 1 of PREREG_CERTIFIED_CARRYOVER.md, before any request: the overlap of the carry-over items with Skopos' training.
confirm-3's fresh items were firewalled against Ekbasis-27B's lineage (results/client_0.1.5/firewall), not against the
rows Skopos added; this step makes the D8 audit cover them.

    python3 overlap_step.py export            -> data/carryover_audit_items.jsonl
        one row per question of the subset (2,781): {"floor": the text the client sends (state, question, options),
        "rid", "suite", "req"}, the input audit/audit_overlap_skopos.py reads (added to its EVAL list as
        ("certified_carryover", <this file>), rules unchanged).
    python3 overlap_step.py exclude <overlap.json>   -> data/overlap_excluded.json
        every scenario with at least one flagged question (the audit's "flagged" rule: identical or near-duplicate) is
        excluded from the run and the analysis; the file records the rule, the audit's sha256 and the counts.
run_carryover.py refuses to start without data/overlap_excluded.json."""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REQ = os.path.join(HERE, "data", "subset_requests.jsonl")
ITEMS = os.path.join(HERE, "data", "carryover_audit_items.jsonl")
EXCL = os.path.join(HERE, "data", "overlap_excluded.json")
SET = "certified_carryover"


def floor_text(state, q):
    crit = q.get("criteria")
    opts = list(crit) if isinstance(crit, dict) else ["yes", "no"] if q.get("type") in ("noul", "boolean") else [str(c) for c in (crit or [])]
    return f"{state}\n\n{q.get('instructions', '')}\n\nOptions: {', '.join(opts)}"


def export():
    n = 0
    with open(ITEMS, "w") as f:
        for it in map(json.loads, open(REQ)):
            for row in it["rows"]:
                q = it["questions"][row["qk"]]
                f.write(json.dumps({"floor": floor_text(it["state"], q), "rid": row["rid"], "suite": it["suite"],
                                    "req": it["req"]}) + "\n")
                n += 1
    print(f"wrote {os.path.relpath(ITEMS, HERE)}: {n} questions; add (\"{SET}\", this path) to the audit's EVAL list")


def exclude(audit_path):
    a = json.load(open(audit_path))
    if SET not in a.get("flags", {}):
        sys.exit(f"{audit_path} has no '{SET}' set: run the audit with the exported items first")
    rows = [json.loads(l) for l in open(ITEMS)]
    flagged = a["flags"][SET]["flagged"]
    scen = sorted({(rows[i]["suite"], rows[i]["req"]) for i in flagged})
    out = {"source": os.path.relpath(audit_path, os.path.dirname(HERE)), "audit_sha256": hashlib.sha256(open(audit_path, "rb").read()).hexdigest(),
           "rule": a.get("rule"), "questions_flagged": len(flagged), "questions": len(rows), "scenarios": [list(s) for s in scen]}
    json.dump(out, open(EXCL, "w"), indent=1)
    print(f"wrote {os.path.relpath(EXCL, HERE)}: {len(flagged)} of {len(rows)} questions flagged, {len(scen)} scenarios excluded")


if __name__ == "__main__":
    if sys.argv[1:2] == ["export"]:
        export()
    elif sys.argv[1:2] == ["exclude"] and len(sys.argv) == 3:
        exclude(sys.argv[2])
    else:
        sys.exit(__doc__)
