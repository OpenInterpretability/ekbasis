# PRELAUNCH PORT (P9) of _orig/search_eval.py: every changed line is marked PORT; the full diff is CHANGES.diff in this folder.
"""The consequence model ALONE as an agent: it solves a puzzle from scratch by searching, with no LLM.

From the initial state, every valid action is tried on every state of the beam; the model predicts the next state one
action at a time (one typed question per state variable, as in chain_eval.py) and the beam keeps the most promising
predicted states (more goal conditions met, then higher probability of the goal values, then higher chain confidence;
identical predicted states merged). The search stops as soon as a predicted state meets the goal, or at H actions. The
plan found is then run in the TRUE simulator: success = the goal really holds.

Same puzzles as the LLM-agent experiment (puzzles.pkl of llm_agent_gen.py). Runs the base model (adapter off) and the
adapter. argv: puzzle dirs. env: MODEL, ADAPTER, RANK, BEAM, BS, TAG, ONLY (both | base | trained), BASE_LABEL (the
name of the adapter-off run: with MODEL = the fused release weights, adapter off IS the released model)."""
import contextlib, json, math, os, pickle, sys, time
os.environ["PROMPT_STYLE"] = "semif"
sys.path.insert(0, os.environ["MODEL"])  # PORT: decision_core.py of the model folder (it was serve 1.3's)
sys.path.insert(0, os.environ.get("LIB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))  # PORT
import torch
import decision_core as dc
from transformers import AutoModelForCausalLM, AutoTokenizer
from envs import qchoice
from llm_agent_gen_lib import all_actions, holds, run_plan

E = os.environ.get
MODEL = E("MODEL", "/root/decis/release_final/models/Eikos-4B")
BEAM, BS, RANK, TAG = int(E("BEAM", "6")), int(E("BS", "48")), int(E("RANK", "64")), E("TAG", "4b")
dev = "cuda"
tok = AutoTokenizer.from_pretrained(MODEL)
LET = torch.tensor([tok.encode(L, add_special_tokens=False)[0] for L in dc.LABELS], device=dev)
PAD = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
from peft import LoraConfig, get_peft_model, set_peft_model_state_dict  # noqa: E402
from safetensors.torch import load_file  # noqa: E402
model = get_peft_model(AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to(dev),
                       LoraConfig(r=RANK, lora_alpha=2 * RANK, lora_dropout=0.0, bias="none", target_modules="all-linear",
                                  task_type="CAUSAL_LM"))
if E("ADAPTER"):  # PORT: with ONLY=base the adapter is switched off (disable_adapter) and never used; the rig loaded
    set_peft_model_state_dict(model, load_file(f"{E('ADAPTER')}/adapter_model.safetensors"))  # V42's, rig-only
model.eval()
decoder, head = model.base_model.model.model, model.base_model.model.lm_head


@torch.no_grad()
def answer(items, adapter):
    enc = [tok(tok.apply_chat_template(dc.messages(t, q, dc.options_of(q)), tokenize=False, add_generation_prompt=True,
                                       enable_thinking=False), add_special_tokens=False)["input_ids"] for t, q in items]
    order = sorted(range(len(items)), key=lambda i: len(enc[i]))
    out = [None] * len(items)
    ctx = contextlib.nullcontext() if adapter else model.disable_adapter()
    with ctx:
        for b in range(0, len(order), BS):
            idx = order[b:b + BS]
            L = max(len(enc[i]) for i in idx)
            ids = torch.full((len(idx), L), PAD, dtype=torch.long)
            att = torch.zeros((len(idx), L), dtype=torch.long)
            for j, i in enumerate(idx):
                ids[j, :len(enc[i])] = torch.tensor(enc[i])
                att[j, :len(enc[i])] = 1
            h = decoder(input_ids=ids.to(dev), attention_mask=att.to(dev)).last_hidden_state
            last = torch.tensor([len(enc[i]) - 1 for i in idx], device=dev)
            lg = head(h[torch.arange(len(idx), device=dev), last])[:, LET].float()
            for j, i in enumerate(idx):
                opts = dc.options_of(items[i][1])
                out[i] = (opts, torch.softmax(lg[j, :len(opts)], -1).cpu())
    return out


VARS = {"jugs": lambda w: [(x, qchoice(f"How many liters are in {x}?", [(str(k), f"{k} liters") for k in range(w.cap[x] + 1)])) for x in w.names],
        "toggles": lambda w: [(j, qchoice(f"What state is {w.lamp} {j + 1} in?", [(x, x) for x in w.states])) for j in range(w.n)],
        "machines": lambda w: [(d, qchoice(f"In which state is {d}?", [(x, x) for x in w.cycle])) for d in w.devs]}
BUILD = {"jugs": lambda w, A: {"v": {x: int(A[x]) for x in w.names}},
         "toggles": lambda w, A: {"st": [w.states.index(A[j]) for j in range(w.n)]},
         "machines": lambda w, A: {"st": {d: w.cycle.index(A[d]) for d in w.devs}}}


def floor_text(w, s, acts):
    act = "\n".join(f"{i + 1}. {w.render_action(a)}" for i, a in enumerate(acts))
    return f"{w.rules}\n\nCurrent state:\n{w.render(s)}\n\nActions, in order:\n{act}\n\n{w.floor_note()}"


def search(puzzles, adapter):
    """Beam search for all puzzles at once (one batch of questions per depth). Returns plans and question counts."""
    beams = {i: [((), p["s0"], 1.0)] for i, p in enumerate(puzzles)}  # (plan, predicted state, chain confidence)
    found, asked = {}, {i: 0 for i in range(len(puzzles))}
    for t in range(max(p["H"] for p in puzzles)):
        live = [i for i in beams if i not in found and puzzles[i]["H"] > t]
        if not live:
            break
        qs, owner = [], []
        for i in live:
            p = puzzles[i]
            acts = list(all_actions(p["fam"], p["w"]).values())
            for bi, (plan, s, c) in enumerate(beams[i]):
                for a in acts:
                    text = floor_text(p["w"], s, [a])
                    for key, q in VARS[p["fam"]](p["w"]):
                        qs.append((text, q))
                        owner.append((i, bi, json.dumps(a, sort_keys=True), key))
                        asked[i] += 1
        ans = answer(qs, adapter)
        per = {}
        for (i, bi, a, key), x in zip(owner, ans):
            per.setdefault((i, bi, a), {})[key] = x
        cand = {}
        for (i, bi, a), A in per.items():
            p = puzzles[i]
            plan, s, c = beams[i][bi]
            labs = {k: x[0][int(x[1].argmax())][0] for k, x in A.items()}
            c2 = c * math.prod(float(x[1].max()) for x in A.values())
            met = sum(str(labs[k]) == str(v) for k, v in p["goal"])
            pg = math.prod(float(A[k][1][[l for l, _ in A[k][0]].index(v)]) if v in [l for l, _ in A[k][0]] else 0.0
                           for k, v in p["goal"])
            s2 = BUILD[p["fam"]](p["w"], labs)
            key = json.dumps(s2, sort_keys=True)
            item = (met, pg, c2, plan + (json.loads(a),), s2)
            if key not in cand.setdefault(i, {}) or item[:3] > cand[i][key][:3]:
                cand[i][key] = item
        for i in live:
            ranked = sorted(cand.get(i, {}).values(), key=lambda x: x[:3], reverse=True)
            done = [x for x in ranked if x[0] == len(puzzles[i]["goal"])]
            if done:
                found[i] = list(max(done, key=lambda x: x[2])[3])
            beams[i] = [(x[3], x[4], x[2]) for x in ranked[:BEAM]]
    plans = {i: found.get(i) or (list(beams[i][0][0]) if beams[i] else []) for i in range(len(puzzles))}
    return plans, asked


for d in sys.argv[1:]:
    puzzles = pickle.load(open(f"{d}/puzzles.pkl", "rb"))
    res = {}
    runs = [(E("BASE_LABEL", "Eikos (no training)"), False), (f"trained {TAG}", True)]
    runs = [r for r in runs if E("ONLY", "both") == "both" or (E("ONLY") == "trained") == r[1]]
    for tag, adapter in runs:
        t0 = time.time()
        plans, asked = search(puzzles, adapter)
        ok = [holds(p["fam"], p["w"], run_plan(p["w"], p["s0"], plans[i]), p["goal"]) for i, p in enumerate(puzzles)]
        res[tag] = (ok, asked, time.time() - t0)
    print(f"\n== {d}: {len(puzzles)} puzzles; the model alone searches (beam {BEAM}); success = the plan works in the true simulator")
    print(f"{'family':9s} {'H':>2s} {'n':>3s} | " + " ".join(f"{t:>22s}" for t in res) + f" | questions/puzzle ({runs[-1][0]})")
    groups = sorted({(p["fam"], p["H"]) for p in puzzles}, key=lambda g: (["jugs", "toggles", "machines"].index(g[0]), g[1])) + [("all", None)]
    for f, h in groups:
        idx = [i for i, p in enumerate(puzzles) if f == "all" or (p["fam"] == f and p["H"] == h)]
        cells = " ".join(f"{100 * sum(res[t][0][i] for i in idx) / len(idx):21.1f}%" for t in res)
        qa = sum(res[runs[-1][0]][1][i] for i in idx) / len(idx)
        print(f"{f:9s} {str(h or ''):>2s} {len(idx):3d} | {cells} | {qa:8.0f}")
    print("seconds:", {t: round(v[2]) for t, v in res.items()})
    json.dump({t: {"ok": v[0], "asked": v[1]} for t, v in res.items()}, open(f"{d}/search_{TAG}.json", "w"))
