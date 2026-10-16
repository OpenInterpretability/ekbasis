"""V49 copy (PLAN_v49 Addendum C): identical to v47/train_conseq_v47.py (sha256 921fbafc…) except MICRO=<n> (default
BS): each step draws its BS items exactly as before (same rng, same order, same option permutations) and runs them
through the model in micro-batches of MICRO, each micro-batch's loss scaled so that the summed gradient is the
batch's (cross-entropy summed / BS; the JEPA term weighted by the micro-batch's share of the step's floor items),
with one clip, optimizer and scheduler step per BS items; each micro-batch's hidden states are freed before the
next forward.
V47 copy (PLAN_v47): identical to /root/decis/conseq/train_conseq.py (sha256 0dbc858a…) except that every kind
whose name starts with "replay" takes the soft-target path ("replayW": w4a5's own option probabilities).
Consequence training on Eikos-4B with LoRA: cross-entropy on the simulator's answer, optionally plus a JEPA
"hindsight" loss. The model reads the floor prompt (state + actions); the frozen Eikos (adapter off) reads the ceiling
prompt (the true outcome) with the same question and the same option order, and the student is trained to reproduce
the teacher's hidden states at the end of the evidence and at the answer position, in the layers listed (cosine).

env: DATA, OUT, MODE=train|eval_base, JEPA (weight; 0 = cross-entropy only), LAYERS="8,16,24,32", BS=16, LR=1e-4,
     STEPS (0 = one epoch), SEED=1, RANK=64, PERM_P=0.3, MODEL
     MODE=eval_adapter with ADAPTER=<dir>; SPLITS (comma-separated test files, default the four Phase 1 splits)
     INIT=<adapter dir>: start training from that adapter; GC=0: no gradient checkpointing; EVAL_BS (48)
     Items of kind "multi" (gen_multi.py) put all their questions in one prompt and read every answer in one pass;
     test splits named multi_* are scored that way and with one prompt per question.
Out: OUT/adapter, OUT/train_log.jsonl, OUT/preds_<split>_<which>.jsonl, OUT/summary.json"""
import contextlib, json, math, os, random, sys, time
os.environ["PROMPT_STYLE"] = "semif"
sys.path.insert(0, os.environ.get("EIKOS_SRC", os.path.join(os.path.dirname(os.path.abspath(__file__)), "eikos")))  # decision_core.py from github.com/caiovicentino/eikos
import torch
import torch.nn.functional as F
import decision_core as dc
from transformers import AutoModelForCausalLM, AutoTokenizer

E = os.environ.get
MODEL = E("MODEL", "caiovicentino1/Eikos-27B")
DATA, OUT, MODE = E("DATA"), E("OUT"), E("MODE", "train")
JEPA = float(E("JEPA", "0"))
LAYERS = [int(x) for x in E("LAYERS", "8,16,24,32").split(",")]
BS, LR, STEPS, SEED = int(E("BS", "16")), float(E("LR", "1e-4")), int(E("STEPS", "0")), int(E("SEED", "1"))
MICRO = int(E("MICRO", "0")) or BS  # PLAN_v49 Addendum C: micro-batch size (gradient accumulation over BS // MICRO)
RANK, PERM_P = int(E("RANK", "64")), float(E("PERM_P", "0.3"))
TRAIN_FILE, VAL_FILE, SAVE_EVERY = E("TRAIN", "train"), E("VAL", ""), int(E("SAVE_EVERY", "500"))
MIX = E("MIX", "")  # e.g. "floor:0.45,read:0.15,replay:0.40": each item of a batch is drawn from that kind
JEPA_POS = E("JEPA_POS", "both")  # both | ev (end of the evidence: question-independent) | last (answer position)
LS, FOCAL = float(E("LS", "0")), float(E("FOCAL", "0"))  # label smoothing of the one-hot targets; focal loss gamma (0: cross-entropy)
SAVE_PROBS = E("SAVE_PROBS", "") == "1"  # evaluation: also save every option's probability
os.makedirs(OUT, exist_ok=True)
torch.manual_seed(SEED)
dev = "cuda"
SPLITS = E("SPLITS", "test_in,test_newq,test_long,test_world").split(",")

tok = AutoTokenizer.from_pretrained(MODEL)
LET = torch.tensor([tok.encode(L, add_special_tokens=False)[0] for L in dc.LABELS], device=dev)
PAD = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
MARK = '", "criterion": '


def load(name):
    return [json.loads(l) for l in open(f"{DATA}/{name}.jsonl")]


def options(q, rng=None):
    opts = dc.options_of(q)
    if rng is not None and q["type"] == "choice" and rng.random() < PERM_P:
        opts = opts[:]
        rng.shuffle(opts)
    return opts


def gold_index(ex, opts):
    lab = ("yes" if ex["gold"] else "no") if ex["question"]["type"] == "noul" else str(ex["gold"])
    return [l for l, _ in opts].index(lab)


def encode(state, q, opts):
    """Token ids of the decision prompt, and the index of the last token of the evidence."""
    text = tok.apply_chat_template(dc.messages(state, q, opts), tokenize=False, add_generation_prompt=True,
                                   enable_thinking=False)
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    cut = text.find(MARK)  # text evidence ends at its closing quote; JSON evidence (replay items) at the comma
    if cut < 0:
        cut = text.find(', "criterion": ')
    ev_end = max(i for i, (a, b) in enumerate(enc["offset_mapping"]) if b <= cut) if cut >= 0 else len(enc["input_ids"]) - 1
    return enc["input_ids"], ev_end


MULTI_SYSTEM = ("Apply each supplied criterion to the supplied evidence. For each question, choose exactly one listed option. "
                "Respond with one line per question: its id, a colon and only the uppercase letter, with no explanation or reasoning.")
SLOT = tok.encode("?\n", add_special_tokens=False)


MULTI_STYLE = E("MULTI_STYLE", "json")  # json: all questions in the user turn, then the slots | turns: one turn each
_X = "\u2063"
_U = tok.apply_chat_template([{"role": "user", "content": _X}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
USER_OPEN, GEN = _U.split(_X)  # what opens a user turn, and what closes it and opens the assistant's answer
_A = tok.apply_chat_template([{"role": "user", "content": _X}, {"role": "assistant", "content": _X}], tokenize=False,
                             add_generation_prompt=False, enable_thinking=False)
END_ASSIST = _A.split(_X)[-1]  # what closes an assistant turn


def encode_multi(state, qs, opts_list):
    """All the questions about one state in one prompt. Returns the token ids and, per question, the position whose
    next-token logits are its letter readout: the answer slots hold a placeholder, so one pass reads every answer.
    MULTI_STYLE=turns: the first question exactly as a one-question prompt, each next one in its own user turn
    (criterion and options only) answered at the start of the assistant turn, like the first."""
    shown = lambda q, lab: {"yes": "true", "no": "false"}.get(lab, lab) if q["type"] in ("noul", "boolean") else lab
    if MULTI_STYLE == "turns":
        ids = tok(tok.apply_chat_template(dc.messages(state, qs[0], opts_list[0]), tokenize=False, add_generation_prompt=True,
                                          enable_thinking=False), add_special_tokens=False)["input_ids"]
        pos = [len(ids) - 1]
        for q, o in zip(qs[1:], opts_list[1:]):
            follow = json.dumps({"criterion": q.get("instructions", ""), "options": [
                {"letter": dc.LABELS[i], "description": f"{shown(q, lab)}: {desc}"} for i, (lab, desc) in enumerate(o)]},
                ensure_ascii=False)
            ids = ids + tok.encode("?" + END_ASSIST + USER_OPEN + follow + GEN, add_special_tokens=False)
            pos.append(len(ids) - 1)
        return ids, pos
    user = json.dumps({"evidence": state, "questions": [
        {"id": f"Q{k + 1}", "criterion": q.get("instructions", ""),
         "options": [{"letter": dc.LABELS[i], "description": f"{shown(q, lab)}: {desc}"} for i, (lab, desc) in enumerate(o)]}
        for k, (q, o) in enumerate(zip(qs, opts_list))]}, ensure_ascii=False)
    text = tok.apply_chat_template([{"role": "system", "content": MULTI_SYSTEM}, {"role": "user", "content": user}],
                                   tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids, pos = tok(text, add_special_tokens=False)["input_ids"], []
    for k in range(len(qs)):
        ids = ids + tok.encode(f"Q{k + 1}:", add_special_tokens=False)
        pos.append(len(ids) - 1)
        ids = ids + SLOT
    return ids, pos


def label_of(q, g):
    return ("yes" if g else "no") if q["type"] == "noul" else str(g)


def batchify(seqs):
    L = max(len(x) for x, _ in seqs)
    ids = torch.full((len(seqs), L), PAD, dtype=torch.long)
    att = torch.zeros((len(seqs), L), dtype=torch.long)
    for i, (x, _) in enumerate(seqs):
        ids[i, :len(x)] = torch.tensor(x)
        att[i, :len(x)] = 1
    last = torch.tensor([len(x) - 1 for x, _ in seqs])
    ev = torch.tensor([e for _, e in seqs])
    return ids.to(dev), att.to(dev), last.to(dev), ev.to(dev)


print(f"loading {MODEL}", flush=True)
base = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to(dev)
from peft import LoraConfig, get_peft_model  # noqa: E402
model = get_peft_model(base, LoraConfig(r=RANK, lora_alpha=2 * RANK, lora_dropout=0.05, bias="none",
                                        target_modules="all-linear", task_type="CAUSAL_LM"))
decoder = model.base_model.model.model
head = model.base_model.model.lm_head
model.print_trainable_parameters()
if E("INIT"):  # continue from a trained adapter (same RANK), e.g. a skill learned first, then a gentler mix
    from safetensors.torch import load_file as _load
    from peft import set_peft_model_state_dict as _set
    _set(model, _load(f"{E('INIT')}/adapter_model.safetensors"))
    print(f"initialized from {E('INIT')}", flush=True)


def run(ids, att, hidden=False):
    return decoder(input_ids=ids, attention_mask=att, output_hidden_states=hidden)


@torch.no_grad()
def evaluate(rows, which, adapter=True, bs=int(E("EVAL_BS", "48"))):
    """Predictions in the order of rows; batches are formed by prompt length (less padding)."""
    model.eval()
    enc = []
    for ex in rows:
        opts = options(ex["question"])
        enc.append((encode(ex[which], ex["question"], opts), opts))
    order = sorted(range(len(rows)), key=lambda i: len(enc[i][0][0]))
    preds = [None] * len(rows)
    ctx = contextlib.nullcontext() if adapter else model.disable_adapter()
    with ctx:
        for b in range(0, len(order), bs):
            idx = order[b:b + bs]
            ids, att, last, _ = batchify([enc[i][0] for i in idx])
            h = run(ids, att).last_hidden_state
            lg = head(h[torch.arange(len(idx), device=dev), last])[:, LET].float()
            for j, i in enumerate(idx):
                ex, opts = rows[i], enc[i][1]
                p = torch.softmax(lg[j, :len(opts)], -1)
                k, gi = int(p.argmax()), gold_index(ex, opts)
                preds[i] = {"world": ex["world"], "qtype": ex["qtype"], "steps": ex["steps"], "ok": k == gi,
                            "conf": float(p[k]), "p_gold": float(p[gi]), "pred": opts[k][0], "gold": opts[gi][0]}
                if SAVE_PROBS:
                    preds[i]["probs"] = [round(float(x), 7) for x in p]
    model.train()
    return preds


@torch.no_grad()
def evaluate_multi(rows, mode, bs=int(E("EVAL_BS", "48"))):
    """Multi-question items: 'multi' = one prompt per item, every answer read in the same pass; 'single' = each
    question in its own prompt (the usual readout). Per-question predictions, and the prompt tokens spent per item."""
    model.eval()
    jobs = []  # (item, question indices, ids, readout positions, options per readout)
    for r, ex in enumerate(rows):
        opts = [options(q) for q in ex["questions"]]
        if mode == "multi":
            ids, pos = encode_multi(ex["floor"], ex["questions"], opts)
            jobs.append((r, list(range(len(opts))), ids, pos, opts))
        else:
            for k, (q, o) in enumerate(zip(ex["questions"], opts)):
                ids, _ = encode(ex["floor"], q, o)
                jobs.append((r, [k], ids, [len(ids) - 1], [o]))
    order = sorted(range(len(jobs)), key=lambda j: len(jobs[j][2]))
    out, tokens = [[None] * len(ex["questions"]) for ex in rows], [0] * len(rows)
    for b in range(0, len(order), bs):
        idx = order[b:b + bs]
        ids, att, _, _ = batchify([(jobs[j][2], 0) for j in idx])
        h = run(ids, att).last_hidden_state
        for jj, j in enumerate(idx):
            r, ks, seq, pos, opts = jobs[j]
            tokens[r] += len(seq)
            lg = head(h[jj, pos])[:, LET].float()
            for t, (k, o) in enumerate(zip(ks, opts)):
                ex, q = rows[r], rows[r]["questions"][k]
                p = torch.softmax(lg[t, :len(o)], -1)
                lab, g0 = label_of(q, ex["golds"][k]), ex["gold0s"][k]
                gi = [l for l, _ in o].index(lab)
                out[r][k] = {"world": ex["world"], "qtype": ex["qtypes"][k], "ok": int(p.argmax()) == gi, "conf": float(p.max()),
                             "changed": bool(ex["known0s"][k] and g0 is not None and label_of(q, g0) != lab)}
    model.train()
    return out, tokens


def ece(preds):
    bins = {}
    for p in preds:
        bins.setdefault(min(int(p["conf"] * 10), 9), []).append(p)
    return sum(len(b) / len(preds) * abs(sum(x["ok"] for x in b) / len(b) - sum(x["conf"] for x in b) / len(b))
               for b in bins.values())


def summarize(preds):
    out = {"n": len(preds), "acc": sum(p["ok"] for p in preds) / len(preds), "conf": sum(p["conf"] for p in preds) / len(preds),
           "ece": ece(preds), "by": {}}
    for key in sorted({(p["world"], p["qtype"]) for p in preds}):
        g = [p for p in preds if (p["world"], p["qtype"]) == key]
        out["by"]["/".join(key)] = {"n": len(g), "acc": sum(p["ok"] for p in g) / len(g), "ece": ece(g)}
    return out


def final_eval(tag_adapter=True, whiches=("floor",)):
    summary = {}
    for split in SPLITS:
        rows = load(split)
        if split.startswith("multi_"):
            for mode in ("multi", "single"):
                res, tokens = evaluate_multi(rows, mode)
                flat = [x for r in res for x in r]
                chg = [x for x in flat if x["changed"]]
                with open(f"{OUT}/preds_{split}_{mode}.jsonl", "w") as f:
                    for x in flat:
                        f.write(json.dumps(x) + "\n")
                summary[f"{split}/{mode}"] = {"n": len(flat), "acc": sum(x["ok"] for x in flat) / len(flat),
                                              "acc_changed": sum(x["ok"] for x in chg) / max(1, len(chg)), "ece": ece(flat),
                                              "tokens_per_item": sum(tokens) / len(rows)}
                print(f"{split} {mode:6s} n={len(flat):5d} acc {100 * summary[f'{split}/{mode}']['acc']:5.1f}%  changed "
                      f"{100 * summary[f'{split}/{mode}']['acc_changed']:5.1f}% (n {len(chg)})  ECE {ece(flat):.3f}  "
                      f"prompt tokens per item {sum(tokens) / len(rows):.0f}", flush=True)
            continue
        for which in whiches:
            preds = evaluate(rows, which, adapter=tag_adapter)
            with open(f"{OUT}/preds_{split}_{which}.jsonl", "w") as f:
                for p in preds:
                    f.write(json.dumps(p) + "\n")
            s = summarize(preds)
            summary[f"{split}/{which}"] = s
            print(f"{split:11s} {which:8s} n={s['n']:5d} acc {100 * s['acc']:5.1f}%  conf {100 * s['conf']:5.1f}  ECE {s['ece']:.3f}", flush=True)
    json.dump(summary, open(f"{OUT}/summary.json", "w"), indent=1)
    return summary


if MODE == "eval_base":
    final_eval(tag_adapter=False, whiches=("floor", "ceiling"))
    sys.exit(0)
if MODE == "eval_adapter":  # a trained adapter (ADAPTER=<dir with adapter_model.safetensors>) on SPLITS, floor prompts
    from safetensors.torch import load_file
    from peft import set_peft_model_state_dict
    set_peft_model_state_dict(model, load_file(f"{E('ADAPTER')}/adapter_model.safetensors"))
    final_eval(tag_adapter=True, whiches=("floor",))
    sys.exit(0)

train = load(TRAIN_FILE)
for _extra in filter(None, E("TRAIN_EXTRA", "").split(",")):  # more training files, e.g. mined items with their own kind
    train += load(_extra)
devset = load(VAL_FILE) if VAL_FILE else load("dev")
best = (-1.0, None)
rng = random.Random(SEED)
order = list(range(len(train)))
rng.shuffle(order)
pools = {}
for i, ex in enumerate(train):
    pools.setdefault(ex.get("kind", "floor"), []).append(i)
mix = [(k, float(v)) for k, v in (x.split(":") for x in MIX.split(","))] if MIX else []


def pick_batch(step):
    if not mix:
        return [train[order[(step * BS + i) % len(order)]] for i in range(BS)]
    kinds_, probs_ = zip(*mix)
    return [train[rng.choice(pools[rng.choices(kinds_, probs_)[0]])] for _ in range(BS)]
steps = STEPS or len(train) // BS
params = [p for p in model.parameters() if p.requires_grad]
opt = torch.optim.AdamW(params, lr=LR, weight_decay=0.0)
warm = 50
sched = torch.optim.lr_scheduler.LambdaLR(
    opt, lambda s: min(1.0, (s + 1) / warm) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / steps)))))
if E("GC", "1") == "1":
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
model.enable_input_require_grads()
model.train()
log = open(f"{OUT}/train_log.jsonl", "a")


def answer_loss(logits, t, is_soft):
    """Cross-entropy on the answer letter; LS smooths one-hot targets (soft replay targets are kept); FOCAL > 0 weights
    each option's term by (1 - p)^gamma (focal loss)."""
    logp = F.log_softmax(logits, -1)
    if LS > 0 and not is_soft:
        t = (1 - LS) * t + LS / t.numel()
    if FOCAL > 0:
        return -(t * (1 - logp.exp()).pow(FOCAL) * logp).sum()
    return -(t * logp).sum()

perm_rng = random.Random(SEED + 7)
t0, acc_ce, acc_j, n_acc = time.time(), 0.0, 0.0, 0
print(f"train {len(train)} items, {steps} steps of {BS} (micro-batch {MICRO}), JEPA={JEPA} ({JEPA_POS}) layers={LAYERS} LR={LR} RANK={RANK} "
      f"LS={LS} FOCAL={FOCAL} MIX={MIX or 'file order'}", flush=True)
for step in range(steps):
    batch = pick_batch(step)
    kinds = [ex.get("kind", "floor") for ex in batch]
    opts_b, seqs, posl, targets, soft = [], [], [], [], []  # per item: options, prompt, readout positions, target per readout
    onehot = lambda gi, n: torch.nn.functional.one_hot(torch.tensor(gi), n).float().to(dev)
    for ex, k in zip(batch, kinds):
        if k == "multi":  # all of an item's questions in one prompt, one readout each
            o = [options(q, perm_rng) for q in ex["questions"]]
            ids_, pos_ = encode_multi(ex["floor"], ex["questions"], o)
            seqs.append((ids_, len(ids_) - 1))
            posl.append(pos_)
            opts_b.append(o)
            targets.append([onehot([l for l, _ in oo].index(label_of(q, g)), len(oo)) for q, g, oo in zip(ex["questions"], ex["golds"], o)])
            soft.append(False)
            continue
        o = options(ex["question"], perm_rng)
        seqs.append(encode(ex["ceiling"] if k == "read" else ex["floor"], ex["question"], o))
        posl.append(None)
        opts_b.append([o])
        if k.startswith("replay"):  # the teacher's soft labels (V47: "replayW" = w4a5's own, PLAN_v47)
            t = torch.tensor([float(ex["probs"].get(l, 0.0)) for l, _ in o], device=dev)
            t = t / t.sum() if t.sum() > 0 else torch.full((len(o),), 1.0 / len(o), device=dev)
        else:
            t = onehot(gold_index(ex, o), len(o))
        targets.append([t])
        soft.append(k.startswith("replay"))
    n_fl = sum(k.startswith("floor") for k in kinds)  # "floor3" etc.: floor items drawn from their own pool
    ce_v, jl_v = 0.0, 0.0
    for c0 in range(0, len(batch), MICRO):  # PLAN_v49 Addendum C: micro-batches, one optimizer step per batch
        cix = list(range(c0, min(c0 + MICRO, len(batch))))
        ids, att, last, ev = batchify([seqs[i] for i in cix])
        fl = [j for j, i in enumerate(cix) if kinds[i].startswith("floor")]
        hs = run(ids, att, hidden=JEPA > 0 and bool(fl))
        ces = []
        for j, i in enumerate(cix):
            lg = head(hs.last_hidden_state[j, posl[i] if posl[i] is not None else [int(last[j])]])[:, LET].float()
            ces.append(torch.stack([answer_loss(lg[q, :len(o)], t, soft[i]) for q, (t, o) in enumerate(zip(targets[i], opts_b[i]))]).mean())
        ce = torch.stack(ces).mean() if len(cix) == len(batch) else torch.stack(ces).sum() / len(batch)
        loss, jl = ce, torch.zeros((), device=dev)
        if JEPA > 0 and fl:
            tseqs = [encode(batch[cix[j]]["ceiling"], batch[cix[j]]["question"], opts_b[cix[j]][0]) for j in fl]
            tids, tatt, tlast, tev = batchify(tseqs)
            with torch.no_grad(), model.disable_adapter():
                ht = run(tids, tatt, hidden=True)
            fi = torch.tensor(fl, device=dev)
            ta = torch.arange(len(fl), device=dev)
            terms = []
            for L in LAYERS:
                s_h = hs.last_hidden_state if L == len(hs.hidden_states) - 1 else hs.hidden_states[L]
                t_h = ht.last_hidden_state if L == len(ht.hidden_states) - 1 else ht.hidden_states[L]
                pairs = {"both": ((last[fi], tlast), (ev[fi], tev)), "ev": ((ev[fi], tev),), "last": ((last[fi], tlast),)}[JEPA_POS]
                for ps, pt in pairs:
                    terms.append(1 - F.cosine_similarity(s_h[fi, ps].float(), t_h[ta, pt].float(), dim=-1).mean())
            jl = torch.stack(terms).mean()
            if len(fl) != n_fl:  # this micro-batch's share of the step's floor items
                jl = jl * (len(fl) / n_fl)
            loss = ce + JEPA * jl
        loss.backward()
        ce_v, jl_v = ce_v + float(ce), jl_v + float(jl)
        hs = ht = s_h = t_h = lg = ces = terms = loss = ce = jl = None  # free this micro-batch's hidden states
    torch.nn.utils.clip_grad_norm_(params, 1.0)
    opt.step()
    sched.step()
    opt.zero_grad(set_to_none=True)
    acc_ce, acc_j, n_acc = acc_ce + ce_v, acc_j + jl_v, n_acc + 1
    if (step + 1) % 25 == 0:
        rec = {"step": step + 1, "ce": acc_ce / n_acc, "jepa": acc_j / n_acc, "lr": sched.get_last_lr()[0],
               "s_per_step": (time.time() - t0) / (step + 1)}
        log.write(json.dumps(rec) + "\n"); log.flush()
        print(json.dumps(rec), flush=True)
        acc_ce, acc_j, n_acc = 0.0, 0.0, 0
    if (step + 1) % SAVE_EVERY == 0 or step + 1 == steps:
        dv = summarize(evaluate(devset, "floor"))
        rec = {"step": step + 1, "dev_acc": dv["acc"], "dev_ece": dv["ece"]}
        log.write(json.dumps(rec) + "\n"); log.flush()
        print(json.dumps(rec), flush=True)
        if VAL_FILE:
            model.save_pretrained(f"{OUT}/ckpt_{step + 1}")
            if dv["acc"] > best[0]:
                best = (dv["acc"], step + 1)
model.save_pretrained(f"{OUT}/adapter")
print(f"trained in {(time.time() - t0) / 60:.1f} min", flush=True)
if VAL_FILE and best[1] and best[1] != steps:  # evaluate the checkpoint that did best on the validation families
    from safetensors.torch import load_file
    from peft import set_peft_model_state_dict
    set_peft_model_state_dict(model, load_file(f"{OUT}/ckpt_{best[1]}/adapter_model.safetensors"))
print(json.dumps({"best_val_step": best[1], "best_val_acc": best[0]}), flush=True)
final_eval(tag_adapter=True, whiches=("floor",))
