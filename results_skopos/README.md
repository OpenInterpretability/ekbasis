# Results of Ekbasis-Skopos-27B

Every number in [RELEASE_EVAL_SKOPOS.md](../RELEASE_EVAL_SKOPOS.md) and in the model cards of
[Ekbasis-Skopos-27B](https://huggingface.co/caiovicentino1/Ekbasis-Skopos-27B) is read from a file in this folder.
The top level holds the summaries the documents read; `runs/` holds every per-item prediction behind them, in the
folders the runs wrote them to (the analysis scripts read these names); `scripts/` holds the scripts that produced
them. Ekbasis-27B's own predictions, the reference of every comparison, are in [`../results/`](../results/). The
pre-registrations and their hashes are in [`../prereg_skopos/`](../prereg_skopos/).

**Recomputable.** `python3 scripts/verify_summaries.py <raw dir>` recomputes the summaries from the per-item files and
the dataset's `raw/` files with the scripts that produced them (two of which read their item files from a fixed folder,
pointed at yours in a temporary copy), and compares them with the files here: equal to 1e-9. It covers the selection
reads, the release read of the bf16, INT4 and FP8 builds, the three quantization gates, the fresh confirmation, the
neutral suite, the image check, the calibration fits and T3c. The MLX build's release read (`release_read_mlx.json`)
was assembled by hand from `runs/release_r4_mlx/` and `quant_gate_mlx.json` because the MLX server does not answer
read-once; its values equal what `compare_release.py` computes from those files (checked when this folder was staged;
the read-once fields are left empty).

| Document section | Summary | Per-item files (`runs/`) | Scripts (`scripts/`) | Pre-registration |
|---|---|---|---|---|
| Choice: first Skopos vs R2 vs Ekbasis-27B | `skopos_v49f_vs_r2.json` | `skopos_eval/`, `run_r2/`, `diag_r2/`, `r2_sessval/`, `base_probs/`, `base_facval/`, `base_sessval/`, `diag_base/`, `neutral_*/` | `run_skopos_cmp.sh`, `analyze_skopos.py` | `PREREG_SKOPOS_CMP.md` |
| Choice: R4 vs the first Skopos | `r4_vs_skopos_v49f.json` (= `run_r4/R4_RESULTS.json` before the neutral AUROC was added) | `run_r4/` (with `train_log.jsonl`) | `run_r4.sh`, `analyze_r4.py` | `PREREG_R4.md` |
| Release read, bf16 served | `release_read_bf16.json`, `release_read_bf16_report.json`, `release_read_bf16_report_extra.json`, `release_read_bf16_guard.json` | `release_r4/` | `serve_r4.sh`, `equiv_r4.py`, `release_eval.py`, `release_eval_extra_rtx.py`, `guard_big_served_rtx.py`, `compare_release.py`, `run_release_r4.sh` | `PREREG_R4_RELEASE_READ.md` |
| Fresh never-trained-family confirmation | `confirm_ftest_fresh.json`; builds `ftest_fresh_int4.json`, `ftest_fresh_fp8.json` | `confirm_r4/`, `confirm_rel/` (Ekbasis-27B); the builds' per-item answers were not kept | `run_confirm_ftest.sh`, `analyze_confirm_ftest.py`, `ftest_fresh_served.py`, `run_ftest_builds.sh` | `CONFIRM_FTEST.md` |
| T3c, real-repository scenarios | `t3c_r4.json` (truth corrected for the planted file as in Ekbasis-27B's), `t3c_r4_raw.json` | `t3c/` (log, the pinned commit of the clone) | `T3C_COMMAND.txt` (the command lines), `release_eval_t3c.py`, `git_battery3.py`, `git_battery3_inj.py`, `rescore_inj_truth.py` | `PREREG_ADDENDUM.md` A1 |
| The builds (INT4, FP8, MLX) | `release_read_{int4,fp8,mlx}.json`, `quant_gate_{int4,fp8,mlx}.json` | `release_r4_int4/`, `release_r4_fp8/`, `release_r4_mlx/` | `run_int4_r4.sh`, `run_fp8.sh`, `run_mlx_gate.sh`, `run_mlx_gate2.sh`, `run_mlx_gate3.sh`, `equiv_mlx.py`, `quant_gate.py`; the builds: `../training/skopos/quantize/` | `PREREG_R4_RELEASE_READ.md`; the gate: `../PREREG_quantized.md` |
| Confident errors (15,008 items) | `ce_r4.json` | `confident_errors/` (predictions re-scored and as first scored; the analysis) | `run_addendum_bf16.sh`, `confident_errors_rtx_path.py` (`confident_errors.py` with the research machine's import path, as it ran), `ce_rescore_and_compare.py`, `../paper/analysis/confident_errors_analyze.py`; `confident_errors.py`, `confident_errors_report.py` (Ekbasis-27B's) | `PREREG_ADDENDUM.md` A2 (`../PREREG_confident_errors.md`) |
| Calibration, per build | `calib_fit_skopos_{int4,bf16,fp8,mlx}.json`, `calib_fit_ekbasis_int4.json` | `calibration/` (every option's probability per item) | `../generators/v50/build_calib_items.py`, `score_skopos_int4.py` (INT4), `score_prod.py` (Ekbasis-27B-INT4), `score_calib_build.py` and `run_addendum_builds.sh` (the other builds), `fit_T.py` | `PREREG_ADDENDUM.md` A3 (INT4: fitted before it) |
| Neutral ground: AgentWorldBench turns | `neutral.json` | `neutral_base/`, `neutral_skopos/`, `neutral_r4/`, `neutral_r2/`; `neutral_items.jsonl` (ids, our labels, a hash of each prompt) | `run_neutral.sh`, `run_neutral_ek.sh`, `analyze_neutral.py`; the suite: `../generators/v50/build_awb_neutral.py` | `PREREG_NEUTRAL.md` |
| Images | `image_compare.json` | `image/` (each item's three answers, both models) | `run_image.sh`; the items and the scoring: `../generators/v50/image_served.py` | `PREREG_IMAGE.md` |
| Overlap of identical states | `overlap_audit_r4.json` (its script was not saved; the audit redone over the whole lineage replaces it) | | | |
| Context, not a Skopos read | `frontier_agentworld.json` (Qwen-AgentWorld against Ekbasis-27B and R1 on our typed questions; its per-item answers are not published) | | | `ADDENDUM_FRONTIER.md` |

Names in the files: `skopos` (in `skopos_eval/`, `neutral_skopos/` and the selection files) is the **first Skopos**
(`v49f_w50`), the internal candidate before R4; `r4` is **Ekbasis-Skopos-27B**; `base` and `release` are
**Ekbasis-27B**. `analyze_r4.py` is `analyze_skopos.py` with R4 in R2's place, so the key `r2` in `R4_RESULTS.json`
and `r4_vs_skopos_v49f.json` means R4. Only the `floor` predictions are here (the trainer's readout also scores the
hindsight prompt, which no number uses).

## Scripts

As run, with where each copy comes from. Two lines differ from the copies that ran: the training machine's SSH address
in `git_battery3.py` and `git_battery3_inj.py` (`RIG`, used only by their `model` subcommand, which T3c does not use).
`verify_summaries.py` and `ftest_paired.py` were written for this folder. `r4_vs_ekbasis.py` (R4 against Ekbasis-27B on
the selection suites, descriptive) reads the per-item files from the private research backup they were copied from.

<!-- provenance:start -->
| File | sha256 of the copy that ran | sha256 here | Changed for publication | Research machine's copy |
|---|---|---|---|---|
| `T3C_COMMAND.txt` | `a57c8f2be07c1699…` | the same | nothing | — |
| `analyze_confirm_ftest.py` | `d41558b1bf57b051…` | the same | nothing | identical |
| `analyze_neutral.py` | `d75b62ea4981ac6b…` | the same | nothing | — |
| `analyze_r2.py` | `5187f5a900ec959f…` | the same | nothing | identical |
| `analyze_r4.py` | `e30041775e000202…` | the same | nothing | identical |
| `analyze_skopos.py` | `27525c8371cd756f…` | the same | nothing | identical |
| `ce_rescore_and_compare.py` | `8cebf2a56ddb9e80…` | the same | nothing | — |
| `compare_release.py` | `c4f4b4e05e5c856c…` | the same | nothing | identical |
| `confident_errors.py` | `9950c209a518a4e6…` | the same | nothing | — |
| `confident_errors_report.py` | `08c323351b054aa6…` | the same | nothing | — |
| `confident_errors_rtx_path.py` | `d15da8a4c739f01b…` | the same | nothing | — |
| `equiv_mlx.py` | `08917661a642b11f…` | the same | nothing | identical |
| `equiv_r4.py` | `7b73c9ebf99c0f0e…` | the same | nothing | identical |
| `fit_T.py` | `4f74987e88cfe94c…` | the same | nothing | — |
| `ftest_fresh_served.py` | `5270920b7165f7d7…` | the same | nothing | identical |
| `git_battery3.py` | `0bdc6a3368297b94…` | `8cd23681a46a2283…` | line 8: the training machine's SSH port and address replaced by placeholders | — |
| `git_battery3_inj.py` | `760710f5fe40ff0f…` | `8a7ece82070e5e64…` | line 8: the training machine's SSH port and address replaced by placeholders | — |
| `guard_big_served_rtx.py` | `a1cbdd61652a0bbd…` | the same | nothing | identical |
| `quant_gate.py` | `62353bc4cbe734a7…` | the same | nothing | identical |
| `r4_vs_ekbasis.py` | `d82fc6fe63345c28…` | the same | nothing | — |
| `release_eval.py` | `bc857b14e95f424d…` | the same | nothing | identical |
| `release_eval_extra_rtx.py` | `9904fd09afbdf306…` | the same | nothing | identical |
| `release_eval_t3c.py` | `56660ab6331afa37…` | the same | nothing | — |
| `rescore_inj_truth.py` | `b0c1bce9905dcadb…` | the same | nothing | — |
| `run_addendum_bf16.sh` | `768dd6ac0f22d504…` | the same | nothing | — |
| `run_addendum_builds.sh` | `38b7c5bc830184af…` | the same | nothing | — |
| `run_confirm_ftest.sh` | `2e61f9a25fbee6e3…` | the same | nothing | identical |
| `run_fp8.sh` | `ca6c88db971bd3f2…` | the same | nothing | identical |
| `run_ftest_builds.sh` | `70b5a73fb6843825…` | the same | nothing | identical |
| `run_image.sh` | `301732d87f556b18…` | the same | nothing | identical |
| `run_int4_r4.sh` | `890c5c58ca106638…` | the same | nothing | identical |
| `run_mlx_gate.sh` | `b756134fd0aa400b…` | the same | nothing | identical |
| `run_mlx_gate2.sh` | `a0fdafdb5eee4547…` | the same | nothing | identical |
| `run_mlx_gate3.sh` | `db75e486ff7ec16d…` | the same | nothing | identical |
| `run_neutral.sh` | `b8c0352ad8262d01…` | the same | nothing | identical |
| `run_neutral_ek.sh` | `55726ce3ad2d3037…` | the same | nothing | identical |
| `run_r4.sh` | `18eccdb3b7288cb9…` | the same | nothing | identical |
| `run_release_r4.sh` | `57b54a2eb538f21a…` | the same | nothing | identical |
| `run_skopos_cmp.sh` | `8bdf0ee3299e4108…` | the same | nothing | identical |
| `score_calib_build.py` | `8ccc793418516ca0…` | the same | nothing | — |
| `score_prod.py` | `f05a18c1a7e20be3…` | the same | nothing | — |
| `score_skopos_int4.py` | `02fd31ef8d3e6865…` | the same | nothing | identical |
| `serve_r4.sh` | `53ecdb0ed3e7541d…` | the same | nothing | identical |
<!-- provenance:end -->
