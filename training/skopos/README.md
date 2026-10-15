# Training Ekbasis-Skopos-27B

This is the code that trained [Ekbasis-Skopos-27B](https://huggingface.co/caiovicentino1/Ekbasis-Skopos-27B), the
successor of [Ekbasis-27B](https://huggingface.co/caiovicentino1/Ekbasis-27B): two more training stages on top of
Ekbasis-27B's release adapter, on the rows published in
[ekbasis-skopos-data](https://huggingface.co/datasets/caiovicentino1/ekbasis-skopos-data), an interpolation and two
merges. The objective, the prompt and the readout are Ekbasis-27B's ([../README.md](../README.md)).

| File | What |
|---|---|
| `train_conseq_v49.py` | The trainer that ran v49f: `../train_conseq.py` plus the soft path for every `replay*` kind and `MICRO` (gradient accumulation). |
| `train_conseq_v50.py` | The trainer that ran R4: `train_conseq_v49.py` plus `CKPT_EVERY` (resumable checkpoints) and `DEVICE`. |
| `wise_lora.py` | The exact interpolation of two LoRA adapters as one adapter of twice the rank (the same file as `../wise_lora.py`). |
| `merge_lora_v45.py` | Merges an adapter into Eikos-27B's multimodal weights with PEFT (the first Skopos). |
| `merge_lora.py` | Merges an adapter into a full checkpoint's shards, W += (alpha / r) · B · A in float32 (R4 into the first Skopos). |
| `stage_files_skopos.py` | Writes the Skopos stages' training files, under the names their runs read, and the split files, from the dataset. |
| `run_lineage_skopos.sh` | The whole lineage: Ekbasis-27B's release adapter (`../run_lineage.sh`), v49f, the first Skopos, R4, the merge. |
| `quantize/quantize_r4.py` | The INT4 (GPTQ W4A16, groups of 128) and FP8 (FP8_DYNAMIC) builds, with llm-compressor. |

## The lineage

| Stage | From | Rows | Steps × batch | LR | Mix |
|---|---|---|---|---|---|
| Ekbasis-27B | Eikos-27B | | | | its own lineage ([../README.md](../README.md)): the exact interpolation halfway between the V42 and r4a adapters (`w4a5`, rank 128) |
| **v49f** | w4a5's adapter (`INIT`, rank 128), on Eikos-27B | 273,529 | 900 × 8 | 1.5e-5 | world replay 0.245 (multi .0735, floor .049, floor3 .0343, read .0196, replay .0686), git replay 0.245 (floorG3 .1715, floorG2 .049, floorG .0245), guard anchor floorGA .20, executed factory data .155 (floorGV .0227, floorRXsh .0444, floorRXgit .0394, floorRXsql .0296, floorC .0189), floorFX .155 |
| **first Skopos** (`v49f_w50`) | w4a5 + v49f | | | | the exact interpolation halfway between the w4a5 and v49f adapters (`wise_lora.py`, λ = 0.5, rank 256), merged into Eikos-27B (`merge_lora_v45.py`); an unreleased intermediate checkpoint, archived privately |
| **R4** | the first Skopos (a new LoRA, rank 64, alpha 128) | 256,705 | 1,200 × 8 | 1.5e-5 | the V42 mix × 0.55 (floorG3 .1925, floorG2 .055, floorG .0275, multi .0825, floor .055, floor3 .0385, read .022, replay .077), floorPL .15, floorPLG .15, floorRX .15 |
| **release** | first Skopos + R4 | | | | R4's adapter merged into the first Skopos (`merge_lora.py`: 496 LoRA pairs, scale 2.0) |

Both stages: JEPA-style hindsight term weight 3 at the end of the evidence in layers 16, 32, 48 and 64, seed 2, the
several questions of a `multi` row one turn each (`MULTI_STYLE=turns`), checkpoint chosen on `fval_git3` (both kept
their last step: v49f's only checkpoint was step 900; R4's best validation step was 1,200, accuracy 0.9409). The frozen
copy that reads the hindsight prompt is the model under the adapter: Eikos-27B for v49f, the first Skopos for R4.
Sources: v49f's run definition (`PLAN_v49.md` with Addenda A–D and `v49/runs.json`; `runs.json` sha256 47b83daf…,
hashed with Addendum B), R4's (`PREREG_R4.md` and `run_r4.sh`, sealed; [../../prereg_skopos/](../../prereg_skopos/)) and
its log (`train 256705 items, 1200 steps of 8 (micro-batch 4)`).

**What each stage trained on.** Kinds are the trainer's pools; a batch item is drawn from a kind with the mix's
probability, then uniformly within it.

| Kind | Rows in v49f | Rows in R4 | What |
|---|---|---|---|
| floor, floor3, read, multi, floorG, floorG2, floorG3 | 47,785 · 20,601 · 11,382 · 24,000 · 26,108 · 31,373 · 24,685 | the same | Ekbasis-27B's V42 file (`ftrain_mixG3`): simulated worlds (factories 1 and 3), reading a true outcome, several questions per state, git v1–v3 executed in throwaway repositories |
| replay | 12,342 | 4,919 | Eikos training items with the teacher's soft targets; R4 read the file published in ekbasis-data, which keeps only the 4,919 redistributable ones |
| floorGV | 2,612 | | V44's git items (ignored files overwritten, sparse checkout, `--abort` after a resolution), executed |
| floorRXsh, floorRXgit, floorRXsql | 19,032 · 17,189 · 14,630 | | the executed factory (shell, git, SQLite), the shell rows rendered in the client's guard layout |
| floorC | 555 | | r4a's items mined inside V42's own chains (ekbasis-data) |
| floorGA | 3,610 | | guard-style git items ("will work be lost?", "will it fail?"), fresh seeds, firewalled |
| floorFX | 17,625 | | the FX factory: 39 families of shell, git, SQLite, PostgreSQL, Python and side effects, plus 2,000 rows converted from swe-rebench-v2-CodeWorldModeling and 600 from ShIO-bash-26.1 |
| floorPL | | 4,335 | synthetic worlds, 4–16 actions |
| floorPLG | | 6,048 | real git sequences of 4–16 commands, executed (gitbox3) |
| floorRX | | 55,469 | the factory regenerated with fresh seeds and executed (shell, SQLite, Python, git) |

The code behind every kind is in [../../generators/](../../generators/README.md).

## Running it

```
git clone https://github.com/caiovicentino/eikos     # decision_core.py: the prompt format
pip install torch transformers peft safetensors huggingface_hub pyarrow
EIKOS_SRC=$PWD/eikos/eikos bash run_lineage_skopos.sh /path/to/work
```

It first runs Ekbasis-27B's lineage (`../run_lineage.sh`), because only Ekbasis-27B's merged weights are published, not
its release adapter, which v49f continues. One GPU with about 96 GB; ~150 GB of disk.

**Quantized builds.** `quantize/quantize_r4.py <bf16 dir> <out dir> int4|fp8` with llm-compressor (a separate
environment): only the language model's linear layers are quantized; the vision tower, `lm_head`, embeddings and the
multi-token-prediction layer stay in bf16. INT4 is calibrated on 256 items of R4's training file drawn with R4's mix
(`TRAIN_FILE` = `ftrain_R4.jsonl`; never evaluation items). The MLX build was made with mlx_lm's converter,
`mlx_lm convert -q --q-bits 4 --q-group-size 64`, from the bf16 release with `mtp_num_hidden_layers` set to 0 in
`config.json` (the build ships no multi-token-prediction layer); it was run by hand, so no script is published for it.

## Provenance

| File | sha256 of the copy that ran | sha256 here | Changed for publication |
|---|---|---|---|
| `train_conseq_v49.py` | 20678ee87c77fa4520caff71e494327365f9c671ba9683ac5015b61e0975ae2d | fdd2377bdc0c9fa317ee4ad65e9cd4f11141fbde4106722f500821acb456202f | line 23, where `decision_core.py` is found (`/root/decis/serve_v13/eikos` → `EIKOS_SRC`); line 30, the default `MODEL` (a local path → `caiovicentino1/Eikos-27B`) |
| `train_conseq_v50.py` | 5a89f17e82998623e160a3466d48b2aab3c7d4cbf076f0d9e5ea1662b88a821c | 5177a0c9be3f9a6c9b48d35da05e0a3f86b7f314ab85c778e8d28dda768d47be | lines 29 and 36, the same two |
| `wise_lora.py` | 08ef74d80b79d9a7c1b42dfa0725c4efc33d6f5ba8b47b25729cb4226ea01675 | the same | none |
| `merge_lora_v45.py` | 917f6abf9ab4729039112e3f42c8477f4c1d6bbb1e3bded0c2849a0368f35407 | 2090fdf02460ad434aff0b12e5121584c8d383c8f52ede10e85810325c7a35b5 | line 11, the default `MERGE_BASE` (a local path → `caiovicentino1/Eikos-27B`) |
| `merge_lora.py` | a3979df8be2fbb24d7e0072aa91877c3f33a0f8d1d859b2cf5ae53065ef3a04e | the same | none |
| `quantize/quantize_r4.py` | 42659332151658ab93f863cf8971fb718b7bb47f96714481031084fd26c0bc19 | 4cd9b9c84bea054305ce5d6450f9b583c577ca49c4aed4f49bb65f774849f2f1 | line 19, where `decision_core.py` is found (→ `EIKOS_SRC`); line 25, R4's training file (a local path → `TRAIN_FILE`, same default) |

`stage_files_skopos.py` and `run_lineage_skopos.sh` were written for publication; they did not run the lineage. Where the
"copy that ran" comes from:
- **v49f** ran on a 4-GPU training machine (RTX PRO 6000 Blackwell, 96 GB each), 7 October 2026, under PLAN_v49. That
  machine no longer exists; its scripts are kept in a mirror whose copies are the ones hashed above, and the sha256 of
  `train_conseq_v49.py` is the one the status log recorded when the copy was checked (`20678ee8…`). The run's own log
  was not kept.
- **R4** ran on one RTX PRO 6000 Blackwell (96 GB), 15 October 2026, from 14:03 UTC (`trained in 111.6 min`).
  `train_conseq_v50.py` and `quantize_r4.py` are byte-identical to that machine's copies, backed up with its logs, and
  to the hashes sealed before the runs (`train_conseq_v50.py` in V50's pilot pre-registration, `quantize_r4.py` and
  `run_r4.sh` in [../../prereg_skopos/PREREG_sha256.txt](../../prereg_skopos/PREREG_sha256.txt)).
- **R4's merge** ran `merge_lora.py` (that machine's copy); no saved script records its command line, and its log reads
  `MERGE_DONE 496 LoRA pairs, scale 2.0`. The released weights' hashes are in the model repository's `SHA256SUMS`.
- **The first Skopos** was built on the training machine with `wise_lora.py` (as the V49 runner built every λ = 0.5
  candidate: `wise_lora.py <w4a5> <v49f/ckpt_900> 0.5 <out>`) and merged with `merge_lora_v45.py`, the merge tool its
  hand-off names; the merge log was not kept. R4 started from the merged weights as uploaded then (revision
  `1e48ae09a3`), an unreleased intermediate checkpoint, archived privately and reproducible with this folder.

**Deviations.**
- **v49f's memory restart.** v49f was registered to run `train_conseq_v47.py` at batch 8. It ran out of GPU memory at
  step ~500 (7 October, 13:20:53 UTC); its SEED + 1 retry was stopped by PLAN_v49's Addendum D (hashed 13:23:07 UTC,
  before any V49 result), and the run started again from step 0 at **micro-batch 4 × gradient accumulation 2, at the
  registered seed 2**, with `train_conseq_v49.py` (13:24 UTC). The run definition's `TRAINER` field still names the V47
  copy: the training runner switched every V49 retry to the V49 copy (Addendum C and its note). That copy was checked on
  a small random model with Eikos-27B's architecture before use: with `MICRO` unset its step-0 gradient equals the V47
  copy's exactly; with `MICRO` 4, 2 or 1 the gradients differ from batch 8 by at most 8 × 10⁻⁷ (relative L2) and the
  logged losses agree to 6 decimals. The same 8 items per step, in the same order, with the same option permutations;
  only the floating-point order and the LoRA-dropout draws differ.
- **R4 at micro-batch 4** was registered so (`PREREG_R4.md`: "BS 8 (micro 4)").
- **Data files.** v49f read `ftrain_mixG3` plus eight `TRAIN_EXTRA` files; R4 read `ftrain_r2` = `ftrain_v50p`
  (Ekbasis-27B's published `ftrain_mixG3` + `floorPL`) + `git_plan_train` + `fac_rx`. `stage_files_skopos.py` writes them
  under those names, in their original order, from the dataset's `raw/`, and `run_lineage_skopos.sh` passes the runs'
  own `TRAIN`, `TRAIN_EXTRA` and `MIX`.

## What will differ in a rerun

- **The start.** v49f continues w4a5's adapter, which is not published (only Ekbasis-27B's merged weights are); a rerun
  starts from the adapter `../run_lineage.sh` rebuilds.
- **v49f's replay rows.** Of v49f's 12,342 replay rows, 7,423 are not redistributed (ekbasis-data's card says why), so
  a rerun of v49f reads the 190,853-row `ftrain_mixG3` R4 read, not the 198,276 rows v49f read; R4 already read only the
  4,919 replay rows that are redistributed.
- Sampling and GPU arithmetic are not deterministic across hardware and library versions: expect close numbers, not the
  same weights. The release's own weights are on Hugging Face.
