# Training Ekbasis-27B

This is the code that trained [Ekbasis-27B](https://huggingface.co/caiovicentino1/Ekbasis-27B): consequence training of a
LoRA adapter on [Eikos-27B](https://huggingface.co/caiovicentino1/Eikos-27B), stage by stage, on the rows published in
[ekbasis-data](https://huggingface.co/datasets/caiovicentino1/ekbasis-data), then the interpolation that is the release.

| File | What |
|---|---|
| `train_conseq.py` | The trainer (and the evaluator, `MODE=eval_adapter`). |
| `stage_files.py` | Writes each stage's training file and the validation files from the dataset's `lineage` config. |
| `run_lineage.sh` | The whole lineage, then the release adapter. |
| `wise_lora.py` | The exact weight-space interpolation of two LoRA adapters, as one adapter of twice the rank. |

## The objective

The model reads a *floor* prompt: a state, the actions, and a typed question with lettered options. It answers by
the next-token probabilities of the option letters, in one forward pass.

- **Cross-entropy** on the letter of the right answer, computed by a simulator or by running real git.
- **A JEPA-style hindsight term.** The same model with the adapter off (frozen) reads the *ceiling* prompt: the same
  question, with the true outcome written in the state. The student, reading only the floor prompt, is trained to
  reproduce the teacher's hidden states (cosine distance), at the end of the evidence, in layers 16, 32, 48 and 64.
  Weight 3, on every row whose kind starts with `floor`.
  - What it did, measured: it did not raise accuracy; it gave better calibration out of distribution (ECE better in
    8 of 10 tests in the ablation that removed it). On a 4B prototype it raised accuracy on question types never trained
    by 5.4 points (95% CI 2.4 to 8.2) and on a new world by 2.3 (0.2 to 4.4).
  - At inference it changes nothing: the readout is still one pass.
- Every batch item is drawn from a *kind* with the stage's mix probability (`MIX`): generated worlds (`floor`,
  `floor3`), git in a throwaway repository (`floorG`, `floorG2`, `floorG3`), several questions per state (`multi`),
  reading a state that is written out (`read`), replay of earlier decision data (`replay`), and items mined from the
  model's own errors (`floorM`, `floorC`).

## The lineage

From the dataset's `recipes.json`. LoRA rank 64 (alpha 128) on every linear layer, batch 8.

| Stage | From | Rows | Steps | LR | Mix |
|---|---|---|---|---|---|
| 27s1 | Eikos-27B | 24,003 | 1000 | 5e-5 | floor3 .85, read .15 |
| V35 | 27s1 | 118,218 | 600 | 1.5e-5 | floor .15, floor3 .15, floorG .30, read .05, replay .35 |
| V37 | V35 | 149,591 | 600 | 1.5e-5 | floorG2 .40, floorG .10, floor .10, floor3 .10, read .05, replay .25 |
| V41 | V37 | 173,591 | 400 | 1.5e-5 | multi .40, floorG2 .15, floorG .05, floor .10, floor3 .08, read .04, replay .18 |
| V42 | V41 | 198,276 | 400 | 1.5e-5 | floorG3 .35, floorG2 .10, floorG .05, multi .15, floor .10, floor3 .07, read .04, replay .14 |
| r4a | V42 | 206,289 | 300 | 1e-5 | V42's mix × 0.7, plus floorM .20 (errors and unsure answers mined from single questions) and floorC .10 (mined inside its own chains) |
| **release** | V42 + r4a | | | | the exact interpolation halfway between the two adapters (`wise_lora.py`, λ = 0.5), merged |

V41 onward asks the several questions of a `multi` row one turn each (`MULTI_STYLE=turns`). Why each stage, and how
the release was chosen: the paper [Look When Unsure, Check When Sure](https://doi.org/10.5281/zenodo.23146970) and
[RELEASE_EVAL.md](../RELEASE_EVAL.md).

## Running it

```
git clone https://github.com/caiovicentino/eikos     # decision_core.py: the prompt format
pip install torch transformers peft safetensors huggingface_hub pyarrow
EIKOS_SRC=$PWD/eikos/eikos bash run_lineage.sh /path/to/work
```

One GPU with about 80 GB per stage; each stage took 50 to 120 minutes on an RTX PRO 6000 (Blackwell).

## Provenance

Every stage of the lineage was run with `train_conseq.py` on our training machine (2–4 October 2026), and the release
adapter was written by `wise_lora.py`. The files here are those scripts. In `train_conseq.py` only two lines changed for
publication: where `decision_core.py` is found (`EIKOS_SRC`) and the default model (a local path became the Hugging Face
id). `wise_lora.py` is unchanged. This copy of the trainer was taken between V42 and r4a; V42 and the stages before it
ran with an earlier one, before the options `LS`, `FOCAL`, `SAVE_PROBS` and `TRAIN_EXTRA` were added, whose defaults leave training
as it was. The V42 log, for example, opens with:

```
initialized from .../sw_v41/ckpt_400
train 198276 items, 400 steps of 8, JEPA=3.0 (ev) layers=[16, 32, 48, 64] LR=1.5e-05 RANK=64 MIX=floorG3:0.35,floorG2:0.10,floorG:0.05,multi:0.15,floor:0.10,floor3:0.07,read:0.04,replay:0.14
...
{"step": 400, "dev_acc": 0.9311023622047244, "dev_ece": 0.0391299955331747}
trained in 52.8 min
```

## What will differ in a rerun

- The published lineage keeps each row once; the original files held 7,568 repeated rows, so a rerun samples from the
  same rows without the repeats.
- Sampling and GPU arithmetic are not deterministic across hardware and library versions: expect close numbers, not
  the same weights. The release's own weights are on Hugging Face.
