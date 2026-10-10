#!/usr/bin/env python3
"""Keep the Claude Code plugin's copy of the client (plugins/ekbasis/lib/ekbasis/) identical to the package (ekbasis/).

The marketplace installs plugins/ekbasis/ alone, so that users do not copy results/, paper/ and assets/ (~90 MB): the
plugin carries its own copy of the package, which is standard library only.

  python scripts/sync_plugin.py           copy ekbasis/*.py and its package data into the plugin, removing extra files
  python scripts/sync_plugin.py --check   exit 1, listing the differences, if the copy is not identical (CI, tests)

Run it after every change to ekbasis/; the version in plugins/ekbasis/.claude-plugin/plugin.json is checked by CI.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ekbasis")
DST = os.path.join(ROOT, "plugins", "ekbasis", "lib", "ekbasis")
DATA = ("verify_policy.json",)   # pyproject.toml [tool.setuptools.package-data]


def shipped(folder: str) -> set:
    if not os.path.isdir(folder):
        return set()
    return {f for f in os.listdir(folder) if f.endswith(".py") or f in DATA}


def differences() -> list:
    src, dst = shipped(SRC), shipped(DST)
    out = [f"missing in the plugin: {f}" for f in sorted(src - dst)]
    out += [f"not in the package (remove it): {f}" for f in sorted(dst - src)]
    out += [f"differs: {f}" for f in sorted(src & dst)
            if not filecmp.cmp(os.path.join(SRC, f), os.path.join(DST, f), shallow=False)]
    if os.path.isdir(DST):
        out += [f"unexpected entry: {f}" for f in sorted(set(os.listdir(DST)) - shipped(DST) - {"__pycache__"})]
    return out


def sync() -> None:
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)
    for f in sorted(shipped(SRC)):
        shutil.copy2(os.path.join(SRC, f), os.path.join(DST, f))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--check"]:
        diff = differences()
        if diff:
            print("plugins/ekbasis/lib/ekbasis is out of sync with ekbasis/ (run: python scripts/sync_plugin.py):",
                  *diff, sep="\n  ", file=sys.stderr)
            return 1
        print("plugin copy of ekbasis/ is in sync")
        return 0
    if argv:
        print(__doc__, file=sys.stderr)
        return 1
    sync()
    print(f"copied {len(shipped(DST))} files to {os.path.relpath(DST, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
