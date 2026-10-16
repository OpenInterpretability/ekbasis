"""WS-FX Addendum 3: ext_shio_cmds (train) and ext_shio_eval (held out) from jragsdale1/ShIO-bash-26.1 (CC-BY-4.0).
ShIO's records have no before-state (a fixed VM snapshot), so its labels are not used: its command lines (synthesized
GCS/UCS/NL2CMD for train; the human-annotated eval split from real user logs, held out) are rewritten to relative paths,
kept only if they pass WS-F's safety filter and use an installed utility, and re-executed in FX's sandbox on a generated
tree that holds the files they name (each with probability 0.75, so some commands meet missing files). Questions and
truth are FX's own (lost, fails, exists, kind, content, count), with flip twins from WS-F's perturbations."""
from __future__ import annotations

import glob
import json
import os
import random
import re
import shlex
import shutil

import fx_shell_new as X
import shell as S
from common import cmd_ceiling, cmd_floor, row, stable_seed

ALLOWED = {"ls", "cat", "cp", "mv", "rm", "mkdir", "rmdir", "touch", "ln", "chmod", "find", "grep", "egrep", "fgrep", "sort",
           "uniq", "cut", "tr", "head", "tail", "wc", "sed", "tar", "gzip", "gunzip", "zcat", "echo", "printf", "du", "stat",
           "basename", "dirname", "tee", "diff", "cmp", "comm", "paste", "join", "split", "nl", "rev", "xargs", "md5sum",
           "sha256sum", "base64", "truncate", "readlink", "realpath", "expand", "unexpand", "fold", "fmt", "tac", "od",
           "column", "csplit", "shuf", "seq", "true", "false", "test", "install", "file", "cksum", "sum"}
NET = re.compile(r"\b(sudo|curl|wget|ssh|scp|nc|ncat|telnet|ftp|apt|pip|systemctl|kill|pkill|reboot|shutdown|mount|"
                 r"chown|useradd|passwd|crontab|dd|mkfs|shred|nohup|watch|sleep|top|ping)\b")


def rewrite(cmd):
    c = cmd.replace("/home/ubuntu/", "").replace("~/", "").replace("/home/ubuntu", ".")
    return c.strip()


def acceptable(c):
    if not c or len(c) > 160 or "\n" in c or NET.search(c) or not S.valid(c):
        return False
    try:
        toks = shlex.split(c)
    except ValueError:
        return False
    if not toks:
        return False
    firsts = [toks[0]] + [toks[i + 1] for i, t in enumerate(toks[:-1]) if t in ("|", "&&", "||", ";")]
    return all(f in ALLOWED and shutil.which(f) for f in firsts)


def load(kind):
    pat = "/root/decis/mission/FX/ext/shio/data/eval/*.ndjson" if kind == "eval" else "/root/decis/mission/FX/ext/shio/data/[GUN]*/*.ndjson"
    out, seen = [], set()
    for f in sorted(glob.glob(pat)):
        for line in open(f, errors="replace"):
            try:
                c = rewrite(json.loads(line)["input"])
            except Exception:  # noqa: BLE001
                continue
            if c not in seen and acceptable(c):
                seen.add(c)
                out.append(c)
    random.Random(26).shuffle(out)
    return out


_CMDS = {}


def cmds(kind):
    if kind not in _CMDS:
        _CMDS[kind] = load(kind)
    return _CMDS[kind]


def referenced(cmd):
    try:
        toks = shlex.split(cmd)
    except ValueError:
        return []
    out = []
    for t in toks[1:]:
        if t.startswith("-") or t in ("|", "&&", "||", ";", ">", ">>", "<") or len(t) > 60:
            continue
        if re.match(r"^[\w.\-/]+$", t) and ("." in t or "/" in t) and not t.startswith("/") and ".." not in t:
            out.append(t.rstrip("/") if t.endswith("/") and len(t) > 1 else t)
    return list(dict.fromkeys(out))[:4]


def add_refs(tree, refs, rng):
    for t in refs:
        if rng.random() > 0.75 or t in tree or t in (".", "./"):
            continue
        parts = t.split("/")
        for i in range(1, len(parts)):
            d = "/".join(parts[:i])
            if d and d not in tree:
                tree[d] = {"t": "d"}
        if "." in parts[-1]:
            tree[t] = {"t": "f", "c": "\n".join(X.ml_lines(rng, rng.randint(1, 4))), "age": rng.randint(1, 30)}
        else:
            tree[t] = {"t": "d"}
    return tree


def make_items(seed, allowed=None):
    fam = (allowed or ["ext_shio_cmds"])[0]
    pool = cmds("eval" if fam == "ext_shio_eval" else "train")
    if not pool:
        return [], {"no_commands": 1}
    cmd = pool[seed % len(pool)]
    rng = random.Random(stable_seed("fx_shio", fam, seed))
    refs = referenced(cmd)
    tree = add_refs(X.gen_tree_fx(rng, "sh_text"), refs, rng)
    tag = f"fxs{os.getpid()}_{seed}"
    res = X.execute_fx(tree, [cmd], tag)
    if res is None:
        return [], {"exec_fail": 1}
    layout = "full" if rng.random() < 0.5 else "listing"
    qs = S.scenario_questions(rng, [cmd], refs, res, layout)
    twin = None
    for _ in range(5):
        pt = S.perturb(tree, [cmd], rng)
        if not pt:
            continue
        t2, op = pt
        r2 = X.execute_fx(t2, [cmd], tag + "t")
        if r2 is not None and S.golds(qs, r2) != S.golds(qs, res):
            twin = (t2, r2, op)
            break
    inst = [("a", tree, res)] + ([("b", twin[0], twin[1])] if twin else [])
    rows = []
    name = "shio:" + (shlex.split(cmd)[0] if cmd else "?")
    for side, t_, res_ in inst:
        g = S.golds(qs, res_)
        g0 = S.golds(qs, {"before": res_["before"], "after": res_["before"], "codes": [0]})
        floor = cmd_floor(S.RULES, X.render_fx(res_["before"], layout), [cmd])
        what = "; ".join(f"line {k}: exit {c}" + (f" ({e})" if c and e else "") for k, (c, e) in
                         enumerate(zip(res_["codes"], res_["errs"]), 1))
        what += f". File content lost for good: {'yes' if g[('lost', None)] else 'no'}."
        ceiling = cmd_ceiling(S.RULES, [cmd], X.render_fx(res_["after"], "full"), what)
        for qt, arg, qd in qs:
            gold = g[(qt, arg)]
            if qt == "content":
                if gold is None:
                    continue
                qd = X.content_options(arg, res, twin[1] if twin else None, [cmd])
                if gold not in qd["criteria"]:
                    qd["criteria"][gold] = gold
                if len(qd["criteria"]) < 2:
                    continue
            elif qt == "count":
                if gold is None:
                    continue
                qd = S.count_question(arg, res, twin[1] if twin else None)
                if str(gold) not in qd["criteria"]:
                    qd["criteria"][str(gold)] = str(gold)
            known0 = qt in ("exists", "kind", "content", "count") and g0.get((qt, arg)) is not None
            if known0 and qd["type"] == "choice" and str(g0.get((qt, arg))) not in qd["criteria"]:
                known0 = False
            rid = f"fxshio-{seed}-{side}-{qt}{'' if arg is None else '-' + re.sub(r'[^A-Za-z0-9]', '_', str(arg))}"
            rows.append(row(world="rx_shell", family="shell", template=name, qtype="fails" if qt.startswith("fails") else qt,
                            steps=1, question=qd, gold=gold, gold0=(g0.get((qt, arg)) if known0 else None), known0=known0,
                            floor=floor, ceiling=ceiling, rid=rid,
                            twin=(f"fxshio-{seed}-{'b' if side == 'a' else 'a'}" if twin else None), layout=layout,
                            face=S.face([cmd], qt, arg, res_["before"]),
                            struct={"tree": t_, "cmds": [cmd], "codes": res_["codes"], "op": twin[2] if twin else None,
                                    "source": "ShIO-bash-26.1 (CC-BY-4.0), command line only"}))
    for r in rows:
        r["fx_source"] = "external:jragsdale1/ShIO-bash-26.1 (command lines only, re-executed)"
    return rows, {"scenarios": 1, "twins": int(bool(twin))}


FAMILY_FORMS = {"ext_shio_cmds": ["ext_shio_cmds"], "ext_shio_eval": ["ext_shio_eval"]}
