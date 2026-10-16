"""LLM agent + consequence model, phase 1: puzzles and the LLM's answers.

Puzzles: a new world (jugs, toggles: trained families; machines: never trained), an initial state and a goal of one or
two conditions taken from where a random H-action plan ends (so a plan exists), that does not hold at the start and that
at most 3 of 8 random plans reach. The agent LLM (Qwen3.8-27B, served by vLLM, thinking on) gets the rules, the state, the
goal and the list of valid actions, and is asked (a) for ONE plan, (b) for 8 different candidate plans, (c) which of its
8 plans most likely works. Saves the puzzles (pickle) and every answer with its token counts.
argv: out dir. env: AGENT_URL (default http://127.0.0.1:30110/v1/chat/completions), N (puzzles per family and H), HS."""
import concurrent.futures as cf, json, os, pickle, random, re, sys, time, urllib.request
sys.path.insert(0, "/root/decis/conseq")
from worldgen import Jugs, Machines, Toggles
from llm_agent_gen_lib import GET, KEYS, SAY, all_actions, holds, run_plan

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
URL = os.environ.get("AGENT_URL", "http://127.0.0.1:30110/v1/chat/completions")
N = int(os.environ.get("N", "30"))
HS = [int(x) for x in os.environ.get("HS", "3,5").split(",")]


rng = random.Random(202)
puzzles = []
for F in (Jugs, Toggles, Machines):
    fam = F.family
    for H in HS:
        made = 0
        while made < N:
            w = F(rng)
            w.name = fam
            s0 = w.sample_state(rng)
            plans = [[w.sample_action(rng, s0) for _ in range(H)] for _ in range(8)]  # actions don't depend on state here
            finals = [run_plan(w, s0, p) for p in plans]
            keys = KEYS[fam](w)
            ref = finals[0]
            goal = [(k, GET[fam](w, ref, k)) for k in rng.sample(keys, min(len(keys), 1 if fam == "jugs" else 2))]
            if holds(fam, w, s0, goal) or sum(holds(fam, w, f, goal) for f in finals) > 3:
                continue
            made += 1
            puzzles.append({"fam": fam, "H": H, "w": w, "s0": s0, "goal": goal,
                            "goal_text": " and ".join(SAY[fam](w, k, v) for k, v in goal)})
pickle.dump(puzzles, open(f"{OUT}/puzzles.pkl", "wb"))
print(f"{len(puzzles)} puzzles", flush=True)


def head(p):
    w = p["w"]
    acts = ", ".join(all_actions(p["fam"], w))
    return (f"{w.rules}\n\nCurrent state:\n{w.render(p['s0'])}\n\nGoal: after the last action, {p['goal_text']}.\n\n"
            f"Available actions (write them exactly like this): {acts}\n\n")


def ask(prompt, max_tokens=8000, think=True):
    body = {"model": "agent", "messages": [{"role": "user", "content": prompt}], "temperature": 0.6, "top_p": 0.95,
            "max_tokens": max_tokens}
    if not think:  # one pass, no reasoning: the same regime as the consequence model
        body["chat_template_kwargs"] = {"enable_thinking": False}
        body["temperature"] = 0.0
    t0 = time.time()
    for attempt in range(3):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=900))
            m = r["choices"][0]["message"]
            return {"content": m.get("content") or "", "reasoning": m.get("reasoning_content") or m.get("reasoning") or "",
                    "tokens": r["usage"]["completion_tokens"], "seconds": time.time() - t0}
        except Exception as e:  # retry transient errors
            err = str(e)
            time.sleep(5)
    return {"content": "", "reasoning": "", "tokens": 0, "seconds": time.time() - t0, "error": err}


def one(i):
    p = puzzles[i]
    H = p["H"]
    single = ask(head(p) + f"Find a plan of at most {H} actions (actions may repeat) that makes the goal true after the last "
                 f"action. End your answer with a line 'PLAN:' followed by the actions, one per line, numbered.")
    nothink = ask(head(p) + f"Find a plan of at most {H} actions (actions may repeat) that makes the goal true after the last "
                  f"action. Answer only with a line 'PLAN:' followed by the actions, one per line, numbered.", max_tokens=400, think=False)
    eight = ask(head(p) + f"Propose 8 different plans of at most {H} actions each (actions may repeat) that you think make "
                f"the goal true after the last action. End your answer with 8 lines of the form 'Plan k: action; action; ...' "
                f"for k = 1 to 8.")
    plans = re.findall(r"Plan\s*(\d+)\s*:\s*(.+)", eight["content"])
    listing = "\n".join(f"Plan {k}: {t.strip()}" for k, t in plans[:8]) or "(no plans)"
    pick = ask(head(p) + f"Here are candidate plans:\n{listing}\n\nWhich plan is most likely to make the goal true after its "
               f"last action? Check them carefully. End your answer with a line 'Best: k'.")
    return {"i": i, "single": single, "nothink": nothink, "eight": eight, "pick": pick}


t0 = time.time()
with cf.ThreadPoolExecutor(int(os.environ.get("PAR", "24"))) as ex:
    res = list(ex.map(one, range(len(puzzles))))
json.dump(res, open(f"{OUT}/answers.json", "w"))
print(f"answers saved, {time.time() - t0:.0f} s, tokens {sum(r[k]['tokens'] for r in res for k in ('single', 'nothink', 'eight', 'pick'))}", flush=True)
