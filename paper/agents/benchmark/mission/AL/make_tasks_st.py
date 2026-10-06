"""WS-AL study 2 (state tracker): 12 ledger tasks, written before any agent run (SPEC.md). Each task: opening balances,
26-29 instructions (deposits, card payments, transfers incl. one that fails, "move everything above", "put N%", two
"End of week", one "End of month") and 3 decisions among them (a bill to pay from Checking or Savings, where exactly one
of the two can cover it, with a margin of at least $40 either side; which one varies with the balances). The truth is the app's own arithmetic (ledger.js); this Python port only places the decisions.
Writes tasks_st.jsonl and tasks_st/<id>.json.    python3 make_tasks_st.py"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
ACC = ["Checking", "Savings", "Bills"]


def r2(x):
    return math.floor(x * 100 + 0.5) / 100


def usd(x):
    return f"${x:,.2f}"


def apply(b0, ins, choice=None):
    b, p = dict(b0), ins["p"]
    k = ins["kind"]
    if k == "deposit":
        b[p["acc"]] = r2(b[p["acc"]] + p["amt"])
    elif k == "card":
        b[p["acc"]] = r2(b[p["acc"]] - p["amt"])
        if b[p["acc"]] < 0:
            b[p["acc"]] = r2(b[p["acc"]] - 35)
    elif k == "transfer":
        if b[p["from"]] >= p["amt"]:
            b[p["from"]] = r2(b[p["from"]] - p["amt"])
            b[p["to"]] = r2(b[p["to"]] + p["amt"])
    elif k == "excess":
        x = r2(b[p["acc"]] - p["level"])
        if x > 0:
            b[p["acc"]] = r2(b[p["acc"]] - x)
            b[p["to"]] = r2(b[p["to"]] + x)
    elif k == "percent":
        x = r2(b[p["acc"]] * p["pct"] / 100)
        b[p["acc"]] = r2(b[p["acc"]] - x)
        b[p["to"]] = r2(b[p["to"]] + x)
    elif k == "week":
        for a in ACC:
            if b[a] < 500:
                b[a] = r2(b[a] - 10)
    elif k == "month":
        b["Savings"] = r2(b["Savings"] + r2(b["Savings"] * 0.01))
    elif k == "pay":
        b[choice] = r2(b[choice] - p["amt"])
        if b[choice] < 0:
            b[choice] = r2(b[choice] - 35)
    return b


SHOPS = ["Grocer", "Pharmacy", "Bookshop", "Hardware store", "Cafe", "Garage", "Pet store", "Florist"]
BILLS = [("water bill", "Bills"), ("phone bill", "Bills"), ("internet bill", "Bills"), ("gym fee", "Checking")]
DECISIONS = [("rent", "Checking"), ("car repair", "Checking"), ("insurance premium", "Savings"), ("tax payment", "Savings"),
             ("dentist bill", "Checking"), ("school fees", "Savings")]


def money(rng, lo, hi):
    return r2(rng.uniform(lo, hi))


def make(seed):
    rng = random.Random(1000 + seed)
    b = {"Checking": money(rng, 1200, 2600), "Savings": money(rng, 1800, 4200), "Bills": money(rng, 420, 760)}
    opening = dict(b)
    plan = ["x"] * 26
    for i in (8, 16, 24):
        plan[i] = "pay"
    for i in (10, 20):
        plan[i] = "week"
    plan[22] = "month"
    fillers = ["deposit", "deposit", "deposit", "card", "card", "card", "card", "card", "bill", "bill", "bill", "transfer",
               "transfer", "transfer_fail", "excess", "excess", "percent", "percent", "deposit", "card"]
    rng.shuffle(fillers)
    fi = iter(fillers)
    plan = [next(fi) if x == "x" else x for x in plan]
    decisions = rng.sample(DECISIONS, 3)
    inbox, d = [], 0
    for kind in plan:
        if kind == "deposit":
            acc = rng.choice(["Checking", "Checking", "Savings"])
            amt = money(rng, 120, 900) if acc == "Checking" else money(rng, 80, 400)
            what = rng.choice(["Salary top-up", "Refund", "Client payment", "Gift"])
            ins = {"kind": "deposit", "text": f"{what} of {usd(amt)} arrives in {acc}.", "p": {"acc": acc, "amt": amt}}
        elif kind == "card" and b["Checking"] >= 80:  # scripted payments never overdraw (only the agent's decisions can)
            amt = money(rng, 18, min(260, b["Checking"] - 40))
            ins = {"kind": "card", "text": f"Card payment of {usd(amt)} at {rng.choice(SHOPS)}, from Checking.", "p": {"acc": "Checking", "amt": amt}}
        elif kind == "bill" and min(b["Bills"], b["Checking"]) >= 80:
            name, acc = rng.choice(BILLS)
            amt = money(rng, 25, min(140, b[acc] - 40))
            ins = {"kind": "card", "text": f"The {name} of {usd(amt)} is paid from {acc}.", "p": {"acc": acc, "amt": amt}}
        elif kind in ("card", "bill"):  # too little left to pay safely: a deposit instead
            amt = money(rng, 150, 400)
            ins = {"kind": "deposit", "text": f"Refund of {usd(amt)} arrives in Checking.", "p": {"acc": "Checking", "amt": amt}}
        elif kind in ("transfer", "transfer_fail"):
            src, dst = rng.choice([("Savings", "Bills"), ("Checking", "Bills"), ("Savings", "Checking"), ("Checking", "Savings")])
            if kind == "transfer":
                amt = money(rng, 50, max(60, min(600, b[src] - 50)))
            else:
                amt = r2(b[src] + money(rng, 40, 300))  # more than the source holds: fails, nothing moves
            ins = {"kind": "transfer", "text": f"Transfer {usd(amt)} from {src} to {dst}.", "p": {"from": src, "to": dst, "amt": amt}}
        elif kind == "excess":
            acc, to = rng.choice([("Checking", "Savings"), ("Bills", "Savings")])
            level = float(rng.choice([1500, 1800, 2000, 2200])) if acc == "Checking" else float(rng.choice([500, 600, 700]))
            ins = {"kind": "excess", "text": f"Move everything above {usd(level)} in {acc} to {to}.", "p": {"acc": acc, "to": to, "level": level}}
        elif kind == "percent":
            acc, to = rng.choice([("Checking", "Savings"), ("Savings", "Bills")])
            pct = rng.choice([5, 10, 15, 20])
            ins = {"kind": "percent", "text": f"Put {pct}% of {acc} into {to}.", "p": {"acc": acc, "to": to, "pct": pct}}
        elif kind == "week":
            ins = {"kind": "week", "text": "End of week.", "p": {}}
        elif kind == "month":
            ins = {"kind": "month", "text": "End of month.", "p": {}}
        else:  # pay: exactly one of Checking and Savings can cover it
            name, _usual = decisions[d]
            lo, hi = sorted([b["Checking"], b["Savings"]])
            if hi - lo < 120:  # widen the gap so that exactly one account can pay, with a margin
                b["Savings"] = r2(b["Savings"] + 400)
                inbox.append({"kind": "deposit", "text": f"Bonus of {usd(400.0)} arrives in Savings.", "p": {"acc": "Savings", "amt": 400.0}})
                lo, hi = sorted([b["Checking"], b["Savings"]])
            amt = r2(rng.uniform(lo + 40, hi - 40))
            covering = "Checking" if b["Checking"] >= amt else "Savings"
            ins = {"kind": "pay", "text": f"Pay the {name} of {usd(amt)} from Checking or from Savings.", "p": {"amt": amt, "right": covering}}
            d += 1
        b = apply(b, ins, ins["p"].get("right"))
        inbox.append(ins)
    return opening, inbox, b


def scenario(i):
    opening, inbox, final = make(i)
    tid = f"ledger_{i:02d}"
    st = {"opening": opening, "balances": dict(opening), "inbox": inbox, "next": 0, "checks_left": 2, "checks_used": 0,
          "decisions": [], "overdrafts": [], "report": None, "submitted": False, "shown": None, "last": None, "toast": None}
    right = [["click", "ledger.process"] if ins["kind"] != "pay" else ["click", f"ledger.pay_{ins['p']['right'].lower()}"] for ins in inbox]
    wrong = [["click", "ledger.process"] if ins["kind"] != "pay" else ["click", f"ledger.pay_{('Savings' if ins['p']['right'] == 'Checking' else 'Checking').lower()}"] for ins in inbox]
    report = [["type", f"ledger.r_{a.lower()}", f"{final[a]:.2f}"] for a in ACC] + [["click", "ledger.submit"]]
    task = ("Process every instruction in the Ledger app, one at a time. Account balances are not shown; you may check them "
            "at most twice. When a bill can be paid from Checking or from Savings, pay it from an account that can cover it, "
            "so that no account goes below $0. At the end, report the final balance of each account exactly, to the cent, "
            "and submit the report.")
    meta = {"id": tid, "app": "ledger", "kind": "ledger", "task": task, "task_short": task, "agent": "Claude · computer use",
            "judge": {"kind": "ledger"}, "paths": {"right": right + report, "wrong": wrong}, "expected_final": final,
            "manual": "", "n_instructions": len(inbox)}
    world = {"clock": "Oct 5 · 6:00 PM", "dock": ["ledger"], "open": ["ledger"], "focus": "ledger",
             "windows": {"ledger": {"x": 110, "y": 78, "w": 1330, "h": 820}}, "apps": {"ledger": st}}
    return {"meta": meta, "world": world}


def main():
    os.makedirs(os.path.join(HERE, "tasks_st"), exist_ok=True)
    with open(os.path.join(HERE, "tasks_st.jsonl"), "w") as f:
        for i in range(1, 13):
            sc = scenario(i)
            json.dump(sc, open(os.path.join(HERE, "tasks_st", f"{sc['meta']['id']}.json"), "w"), ensure_ascii=False, indent=1)
            f.write(json.dumps(sc, ensure_ascii=False) + "\n")
            dec = [ins["p"]["right"] for ins in sc["world"]["apps"]["ledger"]["inbox"] if ins["kind"] == "pay"]
            print(sc["meta"]["id"], sc["meta"]["n_instructions"], "instructions; decisions cover:", dec, "final:", sc["meta"]["expected_final"])


if __name__ == "__main__":
    main()
