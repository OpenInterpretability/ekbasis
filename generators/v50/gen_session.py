"""V50R3 data: render executed shell-factory scenarios (1 command) as an agent's terminal session, so training sees
what agents see: discovery commands with their exact output (ls -laR; grep -r '' . and archive contents only when the
original item showed contents), then the next command; the question is about running it. Labels unchanged (exact).
Two presentation styles ($-transcript and turn/observation). kind floorSX.
    python3 gen_session.py IN.jsonl OUT.jsonl [kind]"""
import datetime, hashlib, json, random, re, sys

src, dst = sys.argv[1], sys.argv[2]
KIND = sys.argv[3] if len(sys.argv) > 3 else "floorSX"
BASE = datetime.datetime(2026, 10, 14, 9, 12)
SIZE = re.compile(r"^- (.+?) — (?:file|archive), (\d+) bytes", re.M)


def q(n):
    return f"'{n}'" if re.search(r"[\s'\"$&;|<>*?()]", n) else n


def stamp(age, rng):
    d = BASE - datetime.timedelta(days=age or 0, minutes=rng.randrange(600))
    return d.strftime("%b %e %H:%M")


def ls_block(tree, sizes, d, rng):
    pre = "" if d == "" else d + "/"
    kids = sorted({p[len(pre):].split("/")[0] for p in tree if p.startswith(pre) and p != d and "/" not in p[len(pre):]})
    sub = [k for k in kids if tree.get(pre + k, {}).get("t") == "d"]
    lines = [f"drwxr-xr-x {2 + len(sub)} dev dev 4096 {stamp(0, rng)} .", f"drwxr-xr-x 5 dev dev 4096 {stamp(3, rng)} .."]
    total = 8
    for k in kids:
        e, p = tree[pre + k], pre + k
        if e["t"] == "d":
            n_sub = sum(1 for x in tree if x.startswith(p + "/") and "/" not in x[len(p) + 1:] and tree[x]["t"] == "d")
            lines.append(f"drwxr-xr-x {2 + n_sub} dev dev 4096 {stamp(1, rng)} {q(k)}"); total += 4
        elif e["t"] == "l":
            lines.append(f"lrwxrwxrwx 1 dev dev {len(e['to'])} {stamp(2, rng)} {q(k)} -> {e['to']}")
        else:
            size = sizes.get(p, len(e.get("c", "")) + 1)
            lines.append(f"-rw-r--r-- 1 dev dev {size} {stamp(e.get('age'), rng)} {q(k)}"); total += 4
    head = "" if d == "" else f"./{d}:\n"
    return head + f"total {total}\n" + "\n".join(lines)


def render(r, style):
    s = r["struct"]; tree = s["tree"]; cmd = s["cmds"][0]
    rng = random.Random(int(hashlib.md5(r["id"].encode()).hexdigest()[:8], 16))
    sizes = {m.group(1): int(m.group(2)) for m in SIZE.finditer(r["floor"])}
    shows = '"' in r["floor"].split("Commands, in order:")[0].split("State before:")[-1]
    dirs = sorted(p for p, e in tree.items() if e["t"] == "d")
    turns = [("ls -laR", ".:\n" + ls_block(tree, sizes, "", rng) + "".join("\n\n" + ls_block(tree, sizes, d, rng) for d in dirs))]
    if shows:
        files = sorted(p for p, e in tree.items() if e["t"] == "f")
        out = "\n".join(f"./{p}:{tree[p]['c']}" for p in files)
        arch = sorted(p for p, e in tree.items() if e["t"] == "tgz")
        out += "".join(f"\ngrep: ./{p}: binary file matches" for p in arch)
        turns.append(("grep -r '' .", out))
        for p in arch:
            turns.append((f"tar -xzOf {q(p)}", "\n".join(tree[p]["members"].values())))
    if style == "dollar":
        sess = "\n".join(f"$ {c}\n{o}" for c, o in turns)
        return ("An AI agent is working in a Linux shell (bash 5.2, GNU coreutils 9.4) in a project folder, as an "
                "ordinary user (not root). Below is what it ran so far in this folder and what the terminal printed, then "
                f"the command it is about to run.\n\nSession so far:\n{sess}\n\nNext command:\n$ {cmd}\n\n"
                "The questions are about what happens when the next command runs.")
    sess = "\n\n".join(f"[Turn {k + 1}] Action:\n{c}\nObservation:\n{o}" for k, (c, o) in enumerate(turns))
    return ("An AI agent works in a Linux shell (bash 5.2, GNU coreutils 9.4) in a project folder as an ordinary user. "
            "These are its previous actions in this folder with what the environment returned, oldest first, and then the "
            f"action it is about to take.\n\nPrevious actions and observations:\n{sess}\n\nNext action:\nRun in the shell: {cmd}\n\n"
            "The questions are about what happens when that action runs.")


def requestion(qd):
    qd = dict(qd); t = qd["instructions"]
    t = t.replace("Does line 1 fail (finish with a non-zero exit status)?", "Will the next command fail (finish with a non-zero exit status)?")
    t = t.replace("Do these commands permanently lose", "Will the next command permanently lose")
    t = t.replace("After these commands,", "After the next command runs,")
    qd["instructions"] = t
    return qd


n = 0
with open(dst, "w") as f:
    for l in open(src):
        r = json.loads(l)
        if r.get("family") != "shell" or str(r["steps"]) != "1":
            continue
        style = "dollar" if int(hashlib.md5(r["id"].encode()).hexdigest()[:2], 16) % 2 else "turns"
        o = dict(r, floor=render(r, style), question=requestion(r["question"]), kind=KIND, world="sess_shell", style=style)
        o["ceiling"] = r["ceiling"]
        f.write(json.dumps(o, ensure_ascii=False) + "\n"); n += 1
print(dst, n)
