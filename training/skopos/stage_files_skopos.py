"""Writes the training file of each Skopos stage (v49f, R4) and the validation and test files their runs read, from the
published dataset (huggingface.co/datasets/caiovicentino1/ekbasis-skopos-data): the `lineage` config marks in which
stages each row was trained (`stages`), and `item` is the row exactly as the trainer read it.

    python3 stage_files_skopos.py <data_dir>   ->  <data_dir>/ftrain_v49f.jsonl, ftrain_R4.jsonl, and the split files

v49f originally read ftrain_mixG3 plus eight TRAIN_EXTRA files and R4 read ftrain_r2; here each stage gets one file with
the same rows. The trainer draws each batch item from a per-kind pool, so a stage's rows are written in their original
order when the dataset carries it (`order`, the row's position in the stage's original files); otherwise in the
dataset's order, and a rerun then samples the same rows in another order.

CHECK (written before the dataset was final): the layout assumed here is ekbasis-data's (config `lineage`, columns
`stages` and `item`; the split files under raw/). The script checks it first and stops, listing what is missing,
rather than write a partial file."""
import json
import os
import sys

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

REPO = os.environ.get("SKOPOS_DATA", "caiovicentino1/ekbasis-skopos-data")
STAGES = {"v49f": 273529, "R4": 256705}  # rows the original files held (README: lineage table)
SPLITS = ["fval_git3", "m3val", "git3_test_known", "git3_test_held", "guard_known", "ftest_family", "fac_val",
          "git_long", "git_long_val", "fhorizon", "latent_test", "sess_val"]  # what the runs validate and read on

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
path = hf_hub_download(REPO, "data/lineage/train.parquet", repo_type="dataset")
cols = set(pq.read_schema(path).names)
need = {"stages", "item"} - cols
if need:
    raise SystemExit(f"{REPO}: data/lineage/train.parquet has no column {sorted(need)}; this script expects "
                     f"ekbasis-data's layout (stages, item)")
rows = pq.read_table(path, columns=["stages", "item"] + (["order"] if "order" in cols else [])).to_pylist()
present = {s for r in rows for s in (r["stages"] or [])}
if set(STAGES) - present:
    raise SystemExit(f"{REPO}: no row is marked with stage {sorted(set(STAGES) - present)} (stages present: "
                     f"{sorted(present)})")
for st, n_orig in STAGES.items():
    mine = [r for r in rows if st in (r["stages"] or [])]
    ordered = "order" in cols and all(r["order"] and st in r["order"] for r in mine)
    if ordered:
        mine.sort(key=lambda r: r["order"][st])
    with open(os.path.join(out, f"ftrain_{st}.jsonl"), "w") as f:
        for r in mine:
            f.write(r["item"].rstrip("\n") + "\n")
    print(f"ftrain_{st}.jsonl: {len(mine)} rows (the original files: {n_orig}){'' if ordered else '; dataset order'}")
missing = []
for sp in SPLITS:
    try:
        src = hf_hub_download(REPO, f"raw/{sp}.jsonl", repo_type="dataset")
    except Exception as e:  # noqa: BLE001
        missing.append(f"raw/{sp}.jsonl ({type(e).__name__})")
        continue
    with open(src) as a, open(os.path.join(out, f"{sp}.jsonl"), "w") as b:
        b.write(a.read())
    print(f"{sp}.jsonl")
if missing:
    raise SystemExit(f"{REPO}: missing " + ", ".join(missing))
