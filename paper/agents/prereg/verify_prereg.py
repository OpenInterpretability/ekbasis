"""Checks the scrubbed pre-registration documents against the hashes recorded at each freeze.
For every file in MANIFEST.json: the copy's SHA-256 must match; undoing the listed substitutions must give back a file
with the original's SHA-256; and every frozen SHA-256 must equal the hash of the whole original or of the byte prefix
it covers (addenda were appended to the plans). Exit code = number of failures.
    python3 verify_prereg.py"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    m = json.load(open(os.path.join(HERE, "MANIFEST.json")))
    subs = [(s["original"].encode(), s["placeholder"].encode()) for s in m["substitutions"]]
    fails = 0
    for d in m["documents"]:
        b = open(os.path.join(HERE, d["file"]), "rb").read()
        ok = sha(b) == d["scrubbed_sha256"]
        for orig, ph in reversed(subs):
            b = b.replace(ph, orig)
        ok &= sha(b) == d["original_sha256"]
        for f in d["frozen"]:
            n = re.match(r"its first (\d+) bytes", f["covers"])
            ok &= sha(b[: int(n.group(1))] if n else b) == f["sha256"]
        print(("ok    " if ok else "FAIL  ") + d["file"] + (f"  ({len(d['frozen'])} frozen hashes)" if d["frozen"] else ""))
        fails += not ok
    print(f"{len(m['documents'])} files, {fails} failures")
    return fails


if __name__ == "__main__":
    sys.exit(main())
