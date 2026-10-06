"""MCP server (stdio) that runs one τ-bench retail episode for a Claude agent: τ-bench's 16 retail tools on a live copy of
its database, `respond` (the message goes to τ-bench's user simulator and its reply comes back), and in the placebo and
ekbasis modes a `foresee` tool with one description:
  placebo -> a fixed reminder, no prediction;  ekbasis -> Ekbasis' answers to the typed questions of tau_env.foresee_request.
Every event (user and agent messages, tool calls with results, foresee calls) is written to $EPISODE after each call.
env: EPISODE (json path), MODE (none | placebo | ekbasis), EKBASIS_URL"""
import asyncio
import json
import os
import sys
import time

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tau_env as E  # noqa: E402

EP = os.environ["EPISODE"]
MODE = os.environ.get("MODE", "none")
PLACEBO = "Consider what this action will do before acting."
FORESEE_DESC = ("Before a tool call that changes the database (cancel, modify, return, exchange, address changes), ask Ekbasis, a "
                "world model, what that call will do: whether it fails, the order status after it, money moved. It reads the tool's "
                "documentation, the store policy and the current database. Nothing is changed.")
ep = json.load(open(EP))
data = E.replay(ep["actions"])
client = None
if MODE == "ekbasis":
    from ekbasis import prompts as P
    from ekbasis.client import Ekbasis
    client = Ekbasis(url=os.environ.get("EKBASIS_URL", "http://127.0.0.1:18542"))
server = Server("tau")


def save():
    tmp = EP + ".tmp"
    json.dump(ep, open(tmp, "w"), ensure_ascii=False)
    os.replace(tmp, EP)


@server.list_tools()
async def list_tools():
    out = []
    for name, t in E.TOOLS.items():
        f = t.get_info()["function"]
        out.append(types.Tool(name=name, description=f["description"], inputSchema=f["parameters"]))
    out.append(types.Tool(name="respond", description="Send a message to the customer. Their reply comes back as the result.",
                          inputSchema={"type": "object", "properties": {"content": {"type": "string", "description": "The message to the customer."}}, "required": ["content"]}))
    if MODE != "none":
        out.append(types.Tool(name="foresee", description=FORESEE_DESC, inputSchema={
            "type": "object", "properties": {"tool_name": {"type": "string", "description": "The tool you are about to call."},
                                             "arguments": {"type": "object", "description": "The arguments you would pass to it."}},
            "required": ["tool_name", "arguments"]}))
    return out


def run_foresee(args):
    tname = args.get("tool_name", "")
    targs = args.get("arguments") or {}
    if isinstance(targs, str):
        try:
            targs = json.loads(targs)
        except json.JSONDecodeError:
            targs = {}
    req = E.foresee_request(data, tname, targs)
    rec = {"tool_name": tname, "arguments": targs, "mode": MODE}
    if req is None:
        text = f"Nothing to foresee: {tname} only reads or does not change the database."
    elif MODE == "placebo":
        text = PLACEBO
    else:
        t0 = time.time()
        qs = {q["key"]: P.choice(q["text"], q["options"]) for q in req["questions"]}
        ans = client.ask(P.world_state(req["rules"], req["state"], [req["action"]]), qs)
        rec["ms"] = round(1000 * (time.time() - t0), 1)
        rec["answers"] = {k: {"value": str(a.value), "confidence": round(a.confidence, 4)} for k, a in ans.items()}
        lines = [f"- {q['text']} {rec['answers'][q['key']]['value']} (confidence {round(100 * rec['answers'][q['key']]['confidence'])}%)" for q in req["questions"]]
        text = f"Ekbasis forecast for {tname}({json.dumps(targs)}):\n" + "\n".join(lines)
        rec["questions"] = req["questions"]
    rec["text"] = text
    ep["foresee"].append(rec)
    ep["events"].append({"type": "foresee", "tool_name": tname})
    return text


@server.call_tool()
async def call_tool(name, arguments):
    args = arguments or {}
    if ep.get("done"):
        text = "The conversation has ended. Stop now."
    elif name == "respond":
        content = str(args.get("content", ""))
        ep["history"].append(["agent", content])
        ep["events"].append({"type": "agent", "text": content})
        reply, cost = await asyncio.to_thread(E.user_reply, ep["instruction"], ep["history"])
        ep["user_cost"] += cost
        ep["user_calls"] += 1
        ep["history"].append(["user", reply])
        ep["events"].append({"type": "user", "text": reply})
        if "###STOP###" in reply:
            ep["done"] = "user_stop"
            text = "The customer ended the conversation (###STOP###). Stop now."
        else:
            text = f"Customer: {reply}"
    elif name == "foresee" and MODE != "none":
        text = await asyncio.to_thread(run_foresee, args)
    elif name in E.TOOLS:
        try:
            res = E.TOOLS[name].invoke(data=data, **args)
        except Exception as e:  # noqa: BLE001
            res = f"Error: {e}"
        ep["actions"].append({"name": name, "kwargs": args, "result": str(res)[:2000]})
        ep["events"].append({"type": "tool", "name": name, "kwargs": args, "error": str(res).startswith("Error")})
        text = str(res)
        if name in E.TERMINATE:
            ep["done"] = "transfer"
            text += "\nThe conversation is over."
    else:
        text = f"Error: unknown tool {name}"
    save()
    return [types.TextContent(type="text", text=text)]


async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
