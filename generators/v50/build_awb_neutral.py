"""Neutral-ground suite from Qwen/AgentWorldBench (Apache-2.0): real agent actions with the real environment observation.
Typed yes/no questions whose answer is read mechanically from that observation (never shown to the model):
  awb_swe_fail   SWE shell tools (run_shell_command 'Exit Code: N', Bash 'Exit code N'): does the command fail? (exact)
  awb_term_fail  Terminal-Bench keystrokes: does the output show an error signature after the command echo? (heuristic)
  awb_term_lists Terminal 'ls': does the listing contain an entry named X? X from the real listing (yes) or a file-like
                 name seen earlier in the session but absent from the listing (no). (exact, by string)
Context: earlier actions and observations, newest kept, each observation cut to head+tail, total capped.
    python3 -I build_awb_neutral.py <awb_dir> <out.jsonl>"""
import collections, hashlib, json, random, re, sys

src, out = sys.argv[1], sys.argv[2]
OBS_CAP, CTX_CAP = 1500, 14000
INTRO = ("You are looking at a session of an AI agent working in a Linux environment. Below are the agent's earlier "
         "actions and what the environment showed after each, oldest first, then the agent's next action. The questions "
         "are about what happens when that next action runs.")


def action(x):
    m = re.search(r"```json\s*(.*?)```", x["current_prompt"], re.S)
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def clip(s, n):
    return s if len(s) <= n else s[: n // 2] + "\n[...]\n" + s[-n // 2:]


def strip_obs(s):
    return s.replace("**Environment Observation:**", "").strip()


def strip_act(s):
    s = re.sub(r"^### Turn \d+\s*", "", s.strip())
    return s.replace("**Action:**", "").strip()


def context(x):
    turns = []
    for k, (p, r) in enumerate(zip(x["prompt"][:-1], x["response"][:-1])):
        turns.append(f"[Turn {k + 1}] Action:\n{clip(strip_act(p), 1200)}\nObservation:\n{clip(strip_obs(r), OBS_CAP)}")
    kept, total = [], 0
    for t in reversed(turns):
        if total + len(t) > CTX_CAP:
            break
        kept.append(t); total += len(t)
    kept.reverse()
    head = "(earlier turns omitted)\n\n" if len(kept) < len(turns) else ""
    return head + ("\n\n".join(kept) if kept else "(no earlier actions)")


def floor(x, nxt):
    return f"{INTRO}\n\nEarlier actions and observations:\n{context(x)}\n\nNext action:\n{nxt}"


FAIL_Q = {"type": "noul", "instructions": (
    "Will the next action fail: the command exits with a non-zero status, or its output shows an error such as "
    "'command not found', 'No such file or directory', 'Permission denied', a Python traceback, or a line starting "
    "with 'error' or 'fatal'?")}
SIG = re.compile(r"(command not found|No such file or directory|Permission denied|Traceback \(most recent call last\)|"
                 r"^\s*(?:error|fatal|E)\s*:|^\w*(?:Error|Exception): [^\d\s])", re.M | re.I)

rows = []
# SWE shell tools: exact exit status
for x in map(json.loads, open(f"{src}/swe_test.jsonl")):
    a = action(x)
    if not isinstance(a, dict) or a.get("name") not in ("run_shell_command", "Bash"):
        continue
    try:
        cmd = json.loads(a["arguments"]).get("command", "")
    except Exception:
        continue
    obs = strip_obs(x["response"][-1])
    if a["name"] == "run_shell_command":
        m = re.search(r"Exit Code:\s*(-?\d+)", obs)
        if not m:
            continue
        gold = int(m.group(1)) != 0
    else:
        m = re.search(r"Exit code (\d+)", obs)
        gold = bool(m) and int(m.group(1)) != 0
    rows.append({"world": "awb_swe_fail", "qtype": "fails", "traj": str(x["id"]), "turn": x["turn_idx"],
                 "floor": floor(x, f"Run in a shell: {clip(cmd, 2000)}"), "question": FAIL_Q, "gold": gold})

# Terminal-Bench: keystrokes into a tmux shell (an action may type several command lines)
TERM_Q = {"type": "noul", "instructions": (
    "Will the terminal output after the next action show an error message, such as 'command not found', "
    "'No such file or directory', 'Permission denied', a Python traceback, or a line starting with 'error' or 'fatal'?")}
PROMPT = re.compile(r"^\S+@\S+:[^\n]*[#$] ", re.M)
NAME = re.compile(r"(?<![\w./-])([A-Za-z0-9_][\w.-]*\.[A-Za-z0-9]{1,6}|[A-Za-z_][\w-]{2,})(?![\w/])")
for x in map(json.loads, open(f"{src}/terminal_test.jsonl")):
    a = action(x)
    if not isinstance(a, list):
        continue
    ks = "".join(k.get("keystrokes", "") for k in a if isinstance(k, dict))
    lines = [l for l in ks.splitlines() if l.strip()]
    if not lines or not ks.endswith("\n") or lines[0].strip().startswith(("C-", "move ")):
        continue
    first = lines[0].strip()
    obs = strip_obs(x["response"][-1])
    pos = obs.find(first[:60])  # the first command's echo; what the screen showed before it belongs to earlier turns
    if pos < 0:
        continue
    after = obs[pos + len(first[:60]):]
    after = after.split("\n", 1)[1] if "\n" in after else ""
    shown = "\n".join(lines)
    fl = floor(x, "Type into the terminal, pressing Enter after each line:\n" + clip(shown, 3000))
    rows.append({"world": "awb_term_fail", "qtype": "fails", "traj": str(x["id"]), "turn": x["turn_idx"],
                 "floor": fl, "question": TERM_Q, "gold": bool(SIG.search(after))})
    if re.fullmatch(r"ls(\s+-[A-Za-z]+)*(\s+[\w./~-]+)?", first):  # a plain listing as the first command
        m = PROMPT.search(after)
        listing = after[: m.start()] if m else (after if len(lines) == 1 else None)
        if listing is None or SIG.search(listing) or not listing.strip():
            continue
        names = set()
        for l in listing.splitlines():
            t = l.split()
            if re.match(r"^[-dlcbps][rwxsStT-]{9}", l) and len(t) >= 9:
                names.add(t[t.index("->") - 1] if "->" in t else t[-1])
            elif not l.startswith("total ") and not re.match(r"^[-dlcbps][rwxsStT-]{9}", l):
                names.update(t)
        FILE = re.compile(r"[A-Za-z_][\w-]*(\.[A-Za-z][A-Za-z0-9]{0,5})+")
        names = {n.rstrip("/*@") for n in names}
        hist = "\n".join(x["prompt"][:-1] + x["response"][:-1])
        seen = {n for n in re.findall(r"[A-Za-z_][\w-]*(?:\.[A-Za-z][A-Za-z0-9]{0,5})+", hist)}
        neg = sorted(n for n in seen if FILE.fullmatch(n) and n not in names and n not in listing and n not in first)
        posn = sorted(n for n in names if FILE.fullmatch(n) and n not in first)
        rng = random.Random(int(hashlib.md5(f"{x['id']}-{x['turn_idx']}".encode()).hexdigest()[:8], 16))
        if posn and neg:
            for n, g in ((rng.choice(posn), True), (rng.choice(neg), False)):
                q = {"type": "noul", "instructions": f"Will the listing printed by the first command of the next action "
                                                     f"contain an entry named '{n}'?"}
                rows.append({"world": "awb_term_lists", "qtype": "lists", "traj": str(x["id"]), "turn": x["turn_idx"],
                             "floor": fl, "question": q, "gold": g, "name": n})

for k, r in enumerate(rows):
    r["id"] = f"awb-{r['world']}-{r['traj']}-{r['turn']}-{k}"; r["steps"] = 1
with open(out, "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
c = collections.Counter((r["world"], r["gold"]) for r in rows)
print(json.dumps({f"{w}:{g}": n for (w, g), n in sorted(c.items())}, indent=0))
print("trajectories", len({r["traj"] for r in rows}), "rows", len(rows),
      "floor chars median", sorted(len(r["floor"]) for r in rows)[len(rows) // 2])
