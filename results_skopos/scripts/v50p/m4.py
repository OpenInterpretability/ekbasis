"""V50P M4 (pre-registered, reported): latent readout (LATENT D1 recipe) on the candidate vs the base, both loaded the
same way (bf16, AutoModelForCausalLM; candidate = base + the pilot's adapter, merged in memory), last token,
layers 32 and 48, the same texts as mission/LATENT/scripts/extract.py.
    python3 m4.py base|cand OUT_DIR"""
import json, os, sys, time
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
which, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
MODEL = "/root/Ekbasis-27B"
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda").eval()
if which == "cand":
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, os.environ.get("ADAPTER", "/root/v50p/run/adapter")).merge_and_unload().eval()
index = json.load(open("/root/lat/index.json"))
rows = {r["id"]: r for r in map(json.loads, open("/root/data.jsonl"))}
texts = {}
for e in index:
    r = rows[e["id"]]
    for t, s in enumerate(r["states"]):
        texts[e["s"][t]] = f"{r['rules']}\n\nCurrent state:\n{s}"
    for t, a in enumerate(r["actions"]):
        texts[e["a"][t]] = f"Action: {a}"
    for t, q in enumerate(r["questions"]):
        for j, o in zip(e["q"][t], q["options"]):
            texts[j] = f"Question: {q['question']}\nAnswer: {o}"
n = max(texts) + 1
order = sorted(texts, key=lambda j: len(texts[j]))
H = {L: torch.zeros((n, model.config.hidden_size if hasattr(model.config, "hidden_size") else model.config.text_config.hidden_size), dtype=torch.float16) for L in (32, 48)}
t0, i = time.time(), 0
with torch.inference_mode():
    while i < len(order):
        lens = [len(tok(texts[j])["input_ids"]) for j in order[i:i + 64]]
        B = max(1, min(64, 12288 // max(lens)))
        ids = order[i:i + B]
        enc = tok([texts[j] for j in ids], return_tensors="pt", padding=True, padding_side="left").to("cuda")
        hs = model(**enc, output_hidden_states=True, logits_to_keep=1).hidden_states
        for L in H:
            H[L][ids] = hs[L][:, -1, :].to(torch.float16).cpu()
        i += B
for L in H:
    torch.save(H[L], f"{out}/h{L}.pt")
print("FIM", which, len(order), f"{time.time() - t0:.0f}s", flush=True)
