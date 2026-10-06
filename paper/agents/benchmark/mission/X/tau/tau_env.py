"""τ-bench retail inside the WS-X harness, kept as close to the benchmark as possible:
- data, tools, tasks (test split) and policy (wiki.md) are τ-bench's own files, loaded without its LLM dependencies;
- the reward is τ-bench's own rule (Env.calculate_reward): the final database must hash-equal the database after the
  task's gold actions, and every expected output must appear in a message to the user;
- the user simulator uses τ-bench's own LLM user prompt (envs/user.py), answered by Claude Haiku via `claude -p`
  (τ-bench accepts any LLM; Haiku is the cheapest we can reach);
- foresee questions are built from the tool docs, the policy section and the live database, as in taubench/build_items.py.
"""
import copy
import importlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import types
from hashlib import sha256

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "ext", "tau-bench-main")
RET = os.path.join(ROOT, "tau_bench", "envs", "retail")
for _n, _p in (("tau_bench", "tau_bench"), ("tau_bench.envs", "tau_bench/envs"), ("tau_bench.envs.retail", "tau_bench/envs/retail")):
    _m = types.ModuleType(_n)
    _m.__path__ = [os.path.join(ROOT, _p)]
    sys.modules[_n] = _m


class Action:  # stand-ins for tau_bench.types (avoids pydantic), same fields
    def __init__(self, name, kwargs):
        self.name, self.kwargs = name, kwargs


class Task:
    def __init__(self, annotator=None, user_id=None, instruction=None, actions=None, outputs=None):
        self.annotator, self.user_id, self.instruction, self.actions, self.outputs = annotator, user_id, instruction, actions or [], outputs or []


_tt = types.ModuleType("tau_bench.types")
_tt.Task, _tt.Action = Task, Action
sys.modules["tau_bench.types"] = _tt
TASKS = importlib.import_module("tau_bench.envs.retail.tasks_test").TASKS_TEST
TOOLS = {t.get_info()["function"]["name"]: t for t in importlib.import_module("tau_bench.envs.retail.tools").ALL_TOOLS}
WIKI = open(os.path.join(RET, "wiki.md")).read()
TERMINATE = {"transfer_to_human_agents"}
WRITE = {"cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items", "modify_pending_order_payment",
         "modify_user_address", "return_delivered_order_items", "exchange_delivered_order_items"}


def load_data():
    return {k: json.load(open(os.path.join(RET, "data", f"{k}.json"))) for k in ("orders", "products", "users")}


# ---------------------------------------------------------------- τ-bench's reward (envs/base.py), reproduced
def to_hashable(item):
    if isinstance(item, dict):
        return tuple((k, to_hashable(v)) for k, v in sorted(item.items()))
    if isinstance(item, list):
        return tuple(to_hashable(e) for e in item)
    if isinstance(item, set):
        return tuple(sorted(to_hashable(e) for e in item))
    return item


def consistent_hash(value):
    return sha256(str(value).encode("utf-8")).hexdigest()


def replay(actions):
    data = load_data()
    for a in actions:
        if a["name"] in TOOLS and a["name"] not in TERMINATE:
            try:
                TOOLS[a["name"]].invoke(data=data, **a["kwargs"])
            except Exception:  # noqa: BLE001  (a malformed call changes nothing, as in τ-bench)
                pass
    return data


def reward(task, actions, messages):
    final = replay(actions)
    gold = replay([{"name": a.name, "kwargs": a.kwargs} for a in task.actions])
    r_actions = consistent_hash(to_hashable(final)) == consistent_hash(to_hashable(gold))
    outs = {o: any(o.lower() in m.lower().replace(",", "") for m in messages) for o in task.outputs}
    return {"reward": float(r_actions and all(outs.values())), "r_actions": r_actions, "outputs": outs}


# ---------------------------------------------------------------- τ-bench's user simulator prompt (envs/user.py)
def user_system_prompt(instruction):
    return f"""You are a user interacting with an agent.

Instruction: {instruction}
Rules:
- Just generate one line at a time to simulate the user's message.
- Do not give away all the instruction at once. Only provide the information that is necessary for the current step.
- Do not hallucinate information that is not provided in the instruction. For example, if the agent asks for the order id but it is not mentioned in the instruction, do not make up an order id, just say you do not remember or have it.
- If the instruction goal is satisified, generate '###STOP###' as a standalone message without anything else to end the conversation.
- Do not repeat the exact instruction in the conversation. Instead, use your own words to convey the same information.
- Try to make the conversation as natural as possible, and stick to the personalities in the instruction."""


def claude(prompt, model):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run(["claude", "-p", prompt, "--model", model, "--tools", "", "--setting-sources", "project,local",
                            "--output-format", "json", "--no-session-persistence"], cwd=d, env=env, capture_output=True, text=True, timeout=300)
    j = json.loads(p.stdout)
    return j.get("result", "").strip(), j.get("total_cost_usd") or 0.0, time.time() - t0


def user_reply(instruction, history, model="haiku"):
    """history: [["agent"|"user", text], ...], τ-bench's chat roles seen from the user's side."""
    convo = "\n".join(f"{'Agent' if r == 'agent' else 'You'}: {t}" for r, t in history)
    prompt = (user_system_prompt(instruction) + "\n\nThe conversation so far:\n" + convo +
              "\n\nWrite only your next message to the agent (or ###STOP###), with no label and nothing else.")
    text, cost, _ = claude(prompt, model)
    return text.removeprefix("You:").strip(), cost


# ---------------------------------------------------------------- foresee questions on the live database
BASIC = ("Each order can be in status 'pending', 'processed', 'delivered', or 'cancelled'. Each payment method is either a gift "
         "card, a paypal account, or a credit card.")
STATUSES = ["pending", "pending (item modified)", "processed", "delivered", "cancelled", "return requested", "exchange requested"]
SECTION = {"cancel_pending_order": "Cancel pending order", "modify_pending_order_address": "Modify pending order",
           "modify_pending_order_payment": "Modify payment", "modify_pending_order_items": "Modify items",
           "return_delivered_order_items": "Return delivered order", "exchange_delivered_order_items": "Exchange delivered order",
           "modify_user_address": None}


def section(title):
    m = re.search(rf"^##+ {re.escape(title)}\n(.*?)(?=^##+ |\Z)", WIKI, re.S | re.M)
    return " ".join(l.lstrip("- ").strip() for l in m.group(1).strip().splitlines() if l.strip())


def rules_for(tname):
    info = TOOLS[tname].get_info()["function"]
    params = "; ".join(f"{k}: {v.get('description', '')}" for k, v in info["parameters"]["properties"].items())
    sec = SECTION.get(tname)
    return (f"Retail store database. {BASIC} Tool {tname}: {info['description']} Parameters — {params}"
            + (f" Store policy: {section(sec)}" if sec else ""))


def money(x):
    return f"${x:,.2f}"


def order_view(o):
    return {"order_id": o["order_id"], "status": o["status"], "address": o["address"],
            "items": [{"name": i["name"], "item_id": i["item_id"], "product_id": i["product_id"], "price": i["price"], "options": i["options"]} for i in o["items"]],
            "payment_history": o["payment_history"]}


def pm_view(u):
    return {k: ({"source": v["source"], "balance": v["balance"]} if v["source"] == "gift_card" else {"source": v["source"]}) for k, v in u["payment_methods"].items()}


def yn(key, text):
    return {"key": key, "text": text, "options": ["yes", "no"]}


def foresee_request(data, tname, args):
    """None when the call only reads; else the request Ekbasis is asked (rules, state, action, typed questions)."""
    if tname not in WRITE:
        return None
    rules = rules_for(tname)
    action = f"The agent calls {tname}({', '.join(f'{k}={json.dumps(v)}' for k, v in args.items())})."
    qs = [yn("fails", "Does the call fail with an error?")]
    state = {}
    o = data["orders"].get(args.get("order_id", ""))
    if tname == "modify_user_address":
        u = data["users"].get(args.get("user_id", ""))
        state = {"user": {"user_id": args.get("user_id"), "address": u["address"]} if u else "no such user"}
        cities = sorted({u["address"]["city"] for u in data["users"].values()})
        opts = sorted({(u or {}).get("address", {}).get("city", "unknown"), args.get("city", "unknown"), *random.Random(len(cities)).sample(cities, 3)})
        qs.append({"key": "city", "text": "After the call, which city is the user's default address in?", "options": opts})
        return {"rules": rules, "state": json.dumps(state), "action": action, "questions": qs}
    if not o:
        return {"rules": rules, "state": f"There is no order {args.get('order_id')} in the database.", "action": action, "questions": qs}
    u = data["users"][o["user_id"]]
    state = {"order": order_view(o), "user_payment_methods": pm_view(u)}
    if tname in ("cancel_pending_order", "return_delivered_order_items", "exchange_delivered_order_items", "modify_pending_order_items"):
        qs.append({"key": "status", "text": "After the call, what is the order's status?", "options": STATUSES})
    if tname == "cancel_pending_order":
        gcs = [p["payment_method_id"] for p in o["payment_history"] if "gift_card" in p["payment_method_id"]]
        if gcs and gcs[0] in u["payment_methods"]:
            gc, b = gcs[0], u["payment_methods"][gcs[0]]["balance"]
            amt = sum(p["amount"] for p in o["payment_history"] if p["payment_method_id"] == gc and p["transaction_type"] == "payment")
            qs.append({"key": "balance", "text": f"After the call, what is the balance of gift card {gc}?",
                       "options": [money(v) for v in sorted({round(b, 2), round(b + amt, 2), round(b - amt, 2), round(amt, 2)})]})
    if tname == "modify_pending_order_payment":
        new = args.get("payment_method_id", "")
        gc = new if "gift_card" in new and new in u["payment_methods"] else None
        if gc:
            b, amt = u["payment_methods"][gc]["balance"], o["payment_history"][0]["amount"]
            qs.append({"key": "balance", "text": f"After the call, what is the balance of gift card {gc}?",
                       "options": [money(v) for v in sorted({round(b, 2), round(b + amt, 2), round(b - amt, 2), round(amt, 2)})]})
    if tname == "modify_pending_order_address":
        cities = sorted({x["address"]["city"] for x in data["users"].values()})
        opts = sorted({o["address"]["city"], args.get("city", "unknown"), *random.Random(len(cities)).sample(cities, 3)})
        qs.append({"key": "city", "text": "After the call, which city is the order shipped to?", "options": opts})
    if tname in ("exchange_delivered_order_items", "modify_pending_order_items"):
        olds = [i for i in o["items"] if i["item_id"] in (args.get("item_ids") or [])]
        news, variants = [], {}
        for it in olds:
            p = data["products"][it["product_id"]]
            variants[p["name"]] = [{"item_id": v["item_id"], "options": v["options"], "available": v["available"], "price": v["price"]} for v in p["variants"].values()][:10]
        for nid in args.get("new_item_ids") or []:
            for p in data["products"].values():
                if nid in p["variants"]:
                    news.append(p["variants"][nid]["price"])
                    variants.setdefault(p["name"], [])
                    if not any(v["item_id"] == nid for v in variants[p["name"]]):
                        v = p["variants"][nid]
                        variants[p["name"]].append({"item_id": nid, "options": v["options"], "available": v["available"], "price": v["price"]})
        state["product_variants"] = variants
        diff = round(sum(news) - sum(i["price"] for i in olds), 2)
        opts = {"nothing is charged or refunded"}
        for v in {abs(diff), round(sum(news), 2), round(sum(i["price"] for i in olds), 2)}:
            if v > 0:
                opts |= {f"the user pays {money(v)}", f"the user is refunded {money(v)}"}
        qs.append({"key": "diff", "text": "After the call, what happens with the price difference?", "options": sorted(opts)})
    return {"rules": rules, "state": json.dumps(state, ensure_ascii=False), "action": action, "questions": qs}
