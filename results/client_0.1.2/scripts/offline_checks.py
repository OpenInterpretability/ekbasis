"""Checks that need no model: (1) the shell guard builds a state for every dev scenario (shell_wild's 408, folders
built for real in throwaway places) without an exception and without any file content in the prompt; which notes and
"cannot judge" parts appear; (2) the fresh dev items for recap and threshold can be built and none equals a published one.
python3 eval/offline_checks.py -> results/offline_checks.json"""
from __future__ import annotations

import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile

from common import CAP, OUT, PKG, VENDOR, read_jsonl

sys.path.insert(0, os.path.join(VENDOR, "shell_wild"))
import shell_wild as SW  # noqa: E402

from ekbasis import shell as S  # noqa: E402


def shell_states() -> dict:
    items = read_jsonl(os.path.join(CAP, "shell_wild", "items.jsonl"))
    tmp = tempfile.mkdtemp(prefix="c012_offline_")
    out = {"scenarios": len(items), "exceptions": [], "leaks": 0, "notes": collections.Counter(),
           "cannot_judge": collections.Counter(), "notes_per_scenario": collections.Counter(), "prompt_chars": []}
    try:
        for it in items:
            work = os.path.join(tmp, it["id"].replace("/", "_").replace("#", "_"))
            SW.materialize(work, it["state"])
            try:
                v = S.inspect(it["cmds"], work, shell="bash", salt=it["id"], where="a Linux machine (offline check)")
                prompt = S.shell_prompt(v)
            except Exception as e:  # noqa: BLE001
                out["exceptions"].append(f"{it['id']}: {type(e).__name__}: {e}")
                continue
            finally:
                pass
            for e in it["state"].values():
                content = e.get("c") if e["t"] == "f" else None
                if content and any(x.strip() and x in prompt for x in content.splitlines()):
                    out["leaks"] += 1
            notes = [k for k, n in S.NOTES if n in prompt]
            out["notes"].update(notes)
            out["notes_per_scenario"][len(notes)] += 1
            out["cannot_judge"].update(u.split(": ", 1)[-1] for u in v.unread)
            out["prompt_chars"].append(len(prompt))
            shutil.rmtree(work, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    pc = sorted(out.pop("prompt_chars"))
    out["prompt_chars_median_max"] = [pc[len(pc) // 2], pc[-1]] if pc else None
    return out


def fresh_items() -> dict:
    res = {}
    code = ("import os, sys, json; sys.path.insert(0, %r); os.environ['ACC_SEED'] = '77012502'; sys.path.insert(0, %r);"
            "import accum as A; items = A.make_items(); pub = {json.dumps([r['rules'], r['actions'], r['state_full']]) "
            "for r in map(json.loads, open(%r))}; fresh = [r for r in items if json.dumps([r['rules'], r['actions'], "
            "r['state_full']]) not in pub]; print(len(items), len(fresh))") % (
        PKG, os.path.join(VENDOR, "accumulation"), os.path.join(CAP, "accumulation", "items.jsonl"))
    n, f = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    res["threshold_items"] = {"built": int(n), "fresh": int(f)}
    sys.argv = sys.argv[:1]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import recap_dev  # noqa: E402
    h = recap_dev.habit_items()
    r = recap_dev.rules_items()
    res["recap_items"] = {"habit": len(h), "rules_stress": len(r),
                          "habit_by_kind": collections.Counter(x["group"] for x in h),
                          "rules_by_level": collections.Counter(x["group"] for x in r)}
    return res


def main():
    report = {"shell": shell_states(), **fresh_items()}
    json.dump(report, open(os.path.join(OUT, "offline_checks.json"), "w"), indent=1, default=dict)
    print(json.dumps(report, indent=1, default=dict)[:3000])


if __name__ == "__main__":
    main()
