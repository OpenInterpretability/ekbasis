"""Fuses a consequence LoRA (trained on the text-only model) into Eikos-27B multimodal weights, on CPU, so the result
can be served like any Eikos checkpoint (vLLM, prefix cache, images). argv: adapter dir, out dir.
V45 copy: MERGE_BASE sets the model the adapter is fused into (default Eikos-27B)."""
import json
import os, os, shutil, sys
import torch
from peft import LoraConfig, get_peft_model, set_peft_model_state_dict
from safetensors.torch import load_file
from transformers import AutoModelForImageTextToText, AutoProcessor

M = os.environ.get("MERGE_BASE", "caiovicentino1/Eikos-27B")  # V45: the merged base on the merged pathway
A, OUT = sys.argv[1], sys.argv[2]
model = AutoModelForImageTextToText.from_pretrained(M, dtype=torch.bfloat16)
sd = load_file(f"{A}/adapter_model.safetensors")
suffixes = sorted({k.split(".lora_")[0].split(".")[-1] for k in sd})
cfg = json.load(open(f"{A}/adapter_config.json"))
model = get_peft_model(model, LoraConfig(r=cfg["r"], lora_alpha=cfg["lora_alpha"], lora_dropout=0.0,
                                         target_modules=r".*language_model\.layers\.\d+\..*\.(" + "|".join(suffixes) + ")"))
sd = {k.replace("base_model.model.model.layers.", "base_model.model.model.language_model.layers."): v for k, v in sd.items()}
res = set_peft_model_state_dict(model, sd)
assert not res.unexpected_keys, res.unexpected_keys[:3]
model = model.merge_and_unload()
model.save_pretrained(OUT, safe_serialization=True, max_shard_size="5GB")
AutoProcessor.from_pretrained(M).save_pretrained(OUT)
for f in os.listdir(M):  # chat template and any extra file the serving stack reads
    if f.endswith((".jinja", ".json", ".txt", ".model")) and not os.path.exists(os.path.join(OUT, f)):
        shutil.copy(os.path.join(M, f), OUT)
print("merged into", OUT, flush=True)
