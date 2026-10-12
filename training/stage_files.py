"""Writes the training file of each stage of the Ekbasis-27B lineage, and the validation files, from the published
dataset (huggingface.co/datasets/caiovicentino1/ekbasis-data): the `lineage` config marks in which stages each row was
trained (`stages`), and `item` is the row exactly as the trainer read it.

    python3 stage_files.py <data_dir>   ->  <data_dir>/ftrain_<stage>.jsonl, m3val.jsonl, fval_git*.jsonl

The original files held 7,568 repeated rows that the published lineage keeps once (198,721 unique rows against
206,289 lines in the r4a files); a rerun therefore samples each kind from the same rows without the repeats."""
import os
import sys

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

REPO = "caiovicentino1/ekbasis-data"
STAGES = ["27s1", "V35", "V37", "V41", "V42", "r4a"]
VAL = ["m3val", "fval_git", "fval_git2", "fval_git3"]

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
rows = pq.read_table(hf_hub_download(REPO, "data/lineage/train.parquet", repo_type="dataset"),
                     columns=["stages", "item"]).to_pylist()
for st in STAGES:
    n = 0
    with open(os.path.join(out, f"ftrain_{st}.jsonl"), "w") as f:
        for r in rows:
            if st in (r["stages"] or []):
                f.write(r["item"].rstrip("\n") + "\n")
                n += 1
    print(f"ftrain_{st}.jsonl: {n} rows")
for v in VAL:
    src = hf_hub_download(REPO, f"raw/{v}.jsonl", repo_type="dataset")
    with open(src) as a, open(os.path.join(out, f"{v}.jsonl"), "w") as b:
        b.write(a.read())
    print(f"{v}.jsonl")
