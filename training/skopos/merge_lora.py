"""Merge a PEFT LoRA (trainer's text-model keys) into a full checkpoint's shards: W += (alpha/r) * B @ A in fp32, cast
back to the shard dtype. Vision tower and every other tensor are copied unchanged.
    python3 merge_lora.py BASE_DIR ADAPTER_DIR OUT_DIR"""
import json, os, shutil, sys, time
import torch
from safetensors import safe_open
from safetensors.torch import save_file
base, adir, out = sys.argv[1:4]
cfg = json.load(open(f"{adir}/adapter_config.json")); scale = cfg["lora_alpha"] / cfg["r"]
A, B = {}, {}
with safe_open(f"{adir}/adapter_model.safetensors", "pt") as f:
    for k in f.keys():
        stem = k.replace("base_model.model.model.", "model.language_model.")
        if ".lora_A." in stem:
            A[stem.replace(".lora_A.weight", ".weight")] = f.get_tensor(k)
        elif ".lora_B." in stem:
            B[stem.replace(".lora_B.weight", ".weight")] = f.get_tensor(k)
        else:
            raise SystemExit(f"unexpected adapter key {k}")
assert A.keys() == B.keys(), "unpaired LoRA keys"
idx = json.load(open(f"{base}/model.safetensors.index.json"))
missing = [k for k in A if k not in idx["weight_map"]]
assert not missing, f"adapter targets not in checkpoint: {missing[:5]}"
os.makedirs(out, exist_ok=True)
done, t0 = 0, time.time()
for shard in sorted(set(idx["weight_map"].values())):
    tensors = {}
    with safe_open(f"{base}/{shard}", "pt") as f:
        meta = f.metadata()
        for k in f.keys():
            w = f.get_tensor(k)
            if k in A:
                d = (B[k].float() @ A[k].float()) * scale
                assert d.shape == w.shape, (k, d.shape, w.shape)
                w = (w.float() + d).to(w.dtype); done += 1
            tensors[k] = w.contiguous()
    save_file(tensors, f"{out}/{shard}", metadata=meta or {"format": "pt"})
    print(shard, "ok", round(time.time() - t0), "s", flush=True)
assert done == len(A), f"merged {done} of {len(A)}"
for fn in os.listdir(base):
    if not fn.endswith(".safetensors") and not os.path.exists(f"{out}/{fn}"):
        p = f"{base}/{fn}"
        (shutil.copytree if os.path.isdir(p) else shutil.copy2)(p, f"{out}/{fn}")
print("MERGE_DONE", done, "LoRA pairs, scale", scale)
