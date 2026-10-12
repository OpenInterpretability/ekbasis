"""WiSE-FT for LoRA adapters: the exact weight-space interpolation W0 + (1-λ)·Δ1 + λ·Δ2 (Δ = scaling·B·A), written as one
adapter of twice the rank: A = [√(1-λ)·A1 ; √λ·A2], B = [√(1-λ)·B1 , √λ·B2], with lora_alpha doubled so the scaling
(alpha / r) stays the same. Checked on a few modules against the interpolation computed directly.
argv: adapter1 adapter2 lambda out_dir"""
import json
import math
import os
import random
import sys

import torch
from safetensors.torch import load_file, save_file

a1, a2, lam, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
c1, c2 = (json.load(open(f"{d}/adapter_config.json")) for d in (a1, a2))
assert (c1["r"], c1["lora_alpha"], sorted(c1["target_modules"])) == (c2["r"], c2["lora_alpha"], sorted(c2["target_modules"]))
s1, s2 = load_file(f"{a1}/adapter_model.safetensors"), load_file(f"{a2}/adapter_model.safetensors")
assert s1.keys() == s2.keys()
w1, w2 = math.sqrt(1 - lam), math.sqrt(lam)
sd = {}
for k in s1:
    if ".lora_A." in k:  # (r, in)
        sd[k] = torch.cat([w1 * s1[k].float(), w2 * s2[k].float()], 0).to(s1[k].dtype)
    elif ".lora_B." in k:  # (out, r)
        sd[k] = torch.cat([w1 * s1[k].float(), w2 * s2[k].float()], 1).to(s1[k].dtype)
    else:
        raise SystemExit(f"unexpected key {k}")
for k in random.Random(0).sample([k for k in s1 if ".lora_A." in k], 4):
    kb = k.replace(".lora_A.", ".lora_B.")
    direct = (1 - lam) * (s1[kb].float() @ s1[k].float()) + lam * (s2[kb].float() @ s2[k].float())
    got = sd[kb].float() @ sd[k].float()
    rel = ((got - direct).norm() / direct.norm()).item()
    assert rel < 1e-2, (k, rel)
    print(f"check {k.split('layers.')[1][:40]}: relative error {rel:.1e}")
os.makedirs(out, exist_ok=True)
save_file(sd, f"{out}/adapter_model.safetensors")
json.dump(dict(c1, r=2 * c1["r"], lora_alpha=2 * c1["lora_alpha"]), open(f"{out}/adapter_config.json", "w"), indent=1)
print(f"wrote {out}: rank {2 * c1['r']}, λ = {lam}")
