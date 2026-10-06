"""Check this folder against MANIFEST.json.

For every file: its SHA-256 must match the manifest, and no file may be missing or unlisted (outputs the runners write,
node_modules and the generated .env are ignored). For a file copied without changes, its hash is the hash of the file
that ran; where that hash was recorded at a freeze, the freeze file in ../prereg/freeze must contain it. For a file
whose edits are all published in the manifest, the edits are undone and the result must have the original hash (and
match the freeze where there is one). Files with a redacted edit (a machine path, the address of a server, a user
name) cannot be traced back here; they are listed with what was replaced.
    python3 verify_benchmark.py"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FREEZE = os.path.join(HERE, "..", "prereg", "freeze")
IGNORE_DIRS = {"node_modules", "__pycache__", "sessions", "results", "logs", "agent_cwd", "episodes", "ext", ".git"}
IGNORE_FILES = {".DS_Store", ".env", "MANIFEST.json"}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    man = json.load(open(os.path.join(HERE, "MANIFEST.json")))
    have_freeze = os.path.isdir(FREEZE)
    if not have_freeze:
        print("note: ../prereg/freeze is not next to this folder; the freeze check is skipped")
    files = {f["path"]: f for f in man["files"]}
    fails, notes = [], {"unchanged": 0, "unchanged_frozen": 0, "reversed": 0, "reversed_frozen": 0, "redacted": 0, "added": 0}
    on_disk = set()
    for root, dirs, names in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for n in names:
            rel = os.path.relpath(os.path.join(root, n), HERE)
            if n in IGNORE_FILES or n.endswith((".pyc", ".jsonl.tmp")) or n.startswith("runs_") or n.startswith("validation"):
                if rel not in files:
                    continue
            on_disk.add(rel)
    for rel in sorted(on_disk - set(files)):
        fails.append(f"not in the manifest: {rel}")
    for rel, f in sorted(files.items()):
        p = os.path.join(HERE, rel)
        if not os.path.isfile(p):
            fails.append(f"missing: {rel}")
            continue
        b = open(p, "rb").read()
        if sha(b) != f["sha256"]:
            fails.append(f"hash differs from the manifest: {rel}")
            continue
        if f.get("added"):
            notes["added"] += 1
            continue
        edits = f.get("edits", [])
        if any(e["kind"] == "redacted" for e in edits):
            notes["redacted"] += 1
            continue
        orig = b
        for e in reversed(edits):
            old, new = e["old"].encode(), e["new"].encode()
            if orig.count(new) != e["count"]:
                fails.append(f"edit not found {e['count']} times: {rel}")
                break
            orig = orig.replace(new, old)
        else:
            if sha(orig) != f["source_sha256"]:
                fails.append(f"original hash not recovered: {rel}")
                continue
            key = "reversed" if edits else "unchanged"
            notes[key] += 1
            for fr in (f.get("frozen", []) if have_freeze else []):
                text = open(os.path.join(FREEZE, fr["freeze_file"])).read()
                if f["source_sha256"] not in text:
                    fails.append(f"hash not in {fr['freeze_file']}: {rel}")
                    break
            else:
                if f.get("frozen") and have_freeze:
                    notes[key + "_frozen"] += 1
    print(f"{len(files)} files in the manifest")
    print(f"  {notes['unchanged']} unchanged ({notes['unchanged_frozen']} of them with the hash recorded at a freeze)")
    print(f"  {notes['reversed']} with published edits undone to the original ({notes['reversed_frozen']} of them frozen)")
    print(f"  {notes['redacted']} with a redacted edit (listed in MANIFEST.json), {notes['added']} added for this release")
    for x in fails:
        print("FAIL", x)
    print(f"{len(fails)} failures")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
