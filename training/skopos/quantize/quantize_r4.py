"""Quantized GPU builds of Ekbasis with llm-compressor, in the official Qwen layout (Qwen3_5ForConditionalGeneration),
with the recipes used for Eikos (quantize_llmc.py): only the language model's linear layers are quantized; the vision
tower, lm_head, embeddings, conv1d, Gated DeltaNet parameters and MTP layers stay in bf16.
  fp8  : FP8_DYNAMIC (FP8 weights per channel + FP8 activations computed per token at run time), no calibration.
  int4 : GPTQ W4A16 (groups of 128) calibrated on items of the V42 TRAINING mixture, drawn with the training mix
         weights; single-question items prompted as the server prompts them, multi-question items in the read-once
         layout the model was trained on. NEVER evaluation items.
R4 adaptation (15/10/2026): R4's training mix and file; otherwise unchanged.
usage: /root/lc_venv/bin/python quantize_r4.py <release_dir> <out_dir> <fp8|int4> [n_calib]"""
import glob
import json
import os
import random
import shutil
import sys

import torch

sys.path.insert(0, os.environ.get("EIKOS_SRC", "eikos"))  # decision_core (same prompt code as the trainer and serve.py)
os.environ.setdefault("PROMPT_STYLE", "semif")

SRC, OUT, SCHEME = sys.argv[1:4]
N = int(sys.argv[4]) if len(sys.argv) > 4 else 256
IGNORE = ["re:.*lm_head", "re:.*visual.*", "re:.*vision.*", "re:.*mtp.*", "re:.*embed.*"]
TRAIN = os.environ.get("TRAIN_FILE", "/root/v50p/data/ftrain_r2.jsonl")  # R4's training file (V42 lineage mix + floorPL/PLG/RX)
MIX = {"floorG3": 0.1925, "floorG2": 0.055, "floorG": 0.0275, "multi": 0.0825, "floor": 0.055, "floor3": 0.0385,
       "read": 0.022, "replay": 0.077, "floorPL": 0.15, "floorPLG": 0.15, "floorRX": 0.15}  # run_r4.sh (R4's mix)

from decision_core import messages, options_of, render_followup  # noqa: E402  (after PROMPT_STYLE)
from llmcompressor import oneshot  # noqa: E402
from llmcompressor.modifiers.quantization import GPTQModifier, QuantizationModifier  # noqa: E402
from transformers import AutoModelForImageTextToText, AutoTokenizer  # noqa: E402

tok = AutoTokenizer.from_pretrained(SRC)


def one_question_ids(state, q, opts):
    text = tok.apply_chat_template(messages(state, q, opts), tokenize=False, add_generation_prompt=True,
                                   enable_thinking=False)
    return tok(text, add_special_tokens=False)["input_ids"]


def read_once_ids(state, items):
    """letter_adapter._read_once_ids: the first question as a one-question prompt; each next one in its own user turn,
    answered at the start of the assistant turn; earlier answers hold a "?" placeholder."""
    x = "⁣"
    u = tok.apply_chat_template([{"role": "user", "content": x}], tokenize=False, add_generation_prompt=True,
                                enable_thinking=False)
    user_open, gen = u.split(x)
    a = tok.apply_chat_template([{"role": "user", "content": x}, {"role": "assistant", "content": x}], tokenize=False,
                                add_generation_prompt=False, enable_thinking=False)
    end_assist = a.split(x)[-1]
    ids = one_question_ids(state, *items[0])
    for q, o in items[1:]:
        ids = ids + tok.encode("?" + end_assist + user_open + render_followup(q, o) + gen, add_special_tokens=False)
    return ids + tok.encode("?", add_special_tokens=False)


seqs = []
if SCHEME == "int4":
    rng = random.Random(7)
    by_kind = {k: [] for k in MIX}
    for line in open(TRAIN):
        r = json.loads(line)
        if r.get("kind") in by_kind:
            by_kind[r["kind"]].append(r)
    for rows in by_kind.values():
        rng.shuffle(rows)
    used = {k: 0 for k in MIX}
    while len(seqs) < N:
        k = rng.choices(list(MIX), weights=list(MIX.values()))[0]
        r = by_kind[k][used[k]]
        used[k] += 1
        if k == "multi":
            items = [(q, options_of(q)) for q in r["questions"]]
            if any(len(o) > 26 for _, o in items):
                continue
            ids = read_once_ids(r["floor"], items)
        else:
            o = options_of(r["question"])
            if len(o) > 26:
                continue
            ids = one_question_ids(r["ceiling"] if k == "read" else r["floor"], r["question"], o)
        seqs.append(ids[:2048])
    print(f"calibration: {len(seqs)} training items {used}, {sum(map(len, seqs)) // len(seqs)} tokens on average",
          flush=True)
    if os.environ.get("DRY"):
        print(tok.decode(seqs[0])[:1500])
        sys.exit(0)

model = AutoModelForImageTextToText.from_pretrained(SRC, dtype=torch.bfloat16, device_map="auto")
print("class:", type(model).__name__, flush=True)
if SCHEME == "fp8":
    oneshot(model=model, recipe=QuantizationModifier(targets="Linear", scheme="FP8_DYNAMIC", ignore=IGNORE))
else:
    from datasets import Dataset

    ds = Dataset.from_dict({"input_ids": seqs, "attention_mask": [[1] * len(x) for x in seqs]})
    oneshot(model=model, dataset=ds, processor=tok, recipe=GPTQModifier(targets="Linear", scheme="W4A16", ignore=IGNORE),
            max_seq_length=2048, num_calibration_samples=len(seqs))

model.save_pretrained(OUT, save_compressed=True)
tok.save_pretrained(OUT)
for f in ("calib.json", "decision_config.json", "chat_template.jinja", "preprocessor_config.json",
          "video_preprocessor_config.json", "processor_config.json"):
    if os.path.exists(os.path.join(SRC, f)):
        shutil.copy(os.path.join(SRC, f), os.path.join(OUT, f))
tot = sum(os.path.getsize(p) for p in glob.glob(f"{OUT}/*") if os.path.isfile(p))
print(f"saved {OUT}: {tot / 1e9:.2f} GB ({SCHEME})", flush=True)
