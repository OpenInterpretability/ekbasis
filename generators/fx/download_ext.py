"""Download a deterministic sample of the external sources (CWM traces, ShIO-bash) for WS-FX Addendum 3."""
import os
from huggingface_hub import HfApi, hf_hub_download
api = HfApi()
OUT = "/root/decis/mission/FX/ext"
cwm = sorted(s.rfilename for s in api.dataset_info("marin-community/swe-rebench-v2-CodeWorldModeling").siblings if s.rfilename.startswith("data/traces-"))
pick = cwm[::60][:80]
for f in pick:
    hf_hub_download("marin-community/swe-rebench-v2-CodeWorldModeling", f, repo_type="dataset", local_dir=OUT + "/cwm")
print("cwm shards:", len(pick), flush=True)
shio = sorted(s.rfilename for s in api.dataset_info("jragsdale1/ShIO-bash-26.1").siblings if s.rfilename.endswith(".ndjson"))
sel = [f for f in shio if f.startswith("data/GCS/")][::60][:20] + [f for f in shio if f.startswith("data/UCS/")][::50][:10] + \
      [f for f in shio if f.startswith("data/NL2CMD/")][::50][:10] + [f for f in shio if f.startswith("data/eval/")]
for f in sel:
    hf_hub_download("jragsdale1/ShIO-bash-26.1", f, repo_type="dataset", local_dir=OUT + "/shio")
print("shio files:", len(sel), flush=True)
print("DOWNLOAD DONE", flush=True)
