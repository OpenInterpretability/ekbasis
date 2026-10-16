"""Writes the training files of the Skopos stages, under the names their runs read, and the validation and test files,
from the published dataset (huggingface.co/datasets/caiovicentino1/ekbasis-skopos-data): `raw/` holds each file as the
trainer read it, in its order, without the rows the dataset does not redistribute (its card lists them).

    python3 stage_files_skopos.py <data_dir>   ->  v49f: ftrain_mixG3.jsonl + its eight TRAIN_EXTRA files;
                                                   R4: ftrain_r2.jsonl (= ftrain_mixG3 + floorPL + git_plan_train + fac_rx);
                                                   the split files the runs validate and read on

The trainer draws each batch item from a per-kind pool in file order, so the order matters: it is the original one.
v49f read the 198,276-row ftrain_mixG3 of Ekbasis-27B's lineage; the dataset's (and ekbasis-data's) holds the 190,853
rows that are redistributed, the file R4 read."""
import os
import sys

from huggingface_hub import hf_hub_download

REPO = os.environ.get("SKOPOS_DATA", "caiovicentino1/ekbasis-skopos-data")
V49F = ["ftrain_mixG3", "v45_v44git", "v45rx_shell", "v45rx_git", "v45rx_sql", "mined_chain", "v46_anchor", "v49_anchor2",
        "v49_fx"]  # TRAIN, then TRAIN_EXTRA in the order the run listed them
R4 = ["ftrain_mixG3", "floorPL", "git_plan_train", "fac_rx"]  # ftrain_r2, as it was concatenated
SPLITS = ["fval_git3", "m3val", "git3_test_known", "git3_test_held", "guard_known", "ftest_family", "fac_val", "git_long",
          "git_long_val", "fhorizon", "latent_test", "sess_val"]

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
missing = []


def raw(name):
    try:
        return hf_hub_download(REPO, f"raw/{name}.jsonl", repo_type="dataset")
    except Exception as e:  # noqa: BLE001
        missing.append(f"raw/{name}.jsonl ({type(e).__name__})")


paths = {n: raw(n) for n in dict.fromkeys(V49F + R4 + SPLITS)}
if missing:
    raise SystemExit(f"{REPO}: missing " + ", ".join(missing))
for n in dict.fromkeys(V49F + SPLITS):
    with open(paths[n]) as a, open(os.path.join(out, f"{n}.jsonl"), "w") as b:
        b.write(a.read())
    print(f"{n}.jsonl")
with open(os.path.join(out, "ftrain_r2.jsonl"), "w") as b:
    n = 0
    for part in R4:
        for line in open(paths[part]):
            b.write(line)
            n += 1
print(f"ftrain_r2.jsonl: {n} rows")
