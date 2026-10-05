# Pre-registration: Ekbasis quantized builds

Written on 2026-10-03 at 15:08 BRT (18:08 UTC), **before any quantized build exists**. Everything below is fixed now;
any later change is reported as a deviation.

## Builds (the recipes used for Eikos)

- **Ekbasis-27B-FP8**: llm-compressor `FP8_DYNAMIC` (FP8 weights per channel, FP8 activations computed per token at run
  time), no calibration data.
- **Ekbasis-27B-INT4**: llm-compressor GPTQ `W4A16` (groups of 128, static activation order, dampening 0.01),
  calibrated on 256 items drawn from the V42 **training** mixture with the training mix weights (single-question items
  as the server prompts them, multi-question items in the read-once layout); never on evaluation items.
- **Ekbasis-27B-MLX-4bit**: mlx-lm affine 4-bit, groups of 64, for Apple Silicon; text only.

In both GPU builds the vision tower, `lm_head`, embeddings and MTP layers stay in bf16; the MLX build keeps what mlx-lm
keeps. All three start from the exact release weights (the fused checkpoint evaluated in RELEASE_EVAL.md).

## How each build is evaluated

Served like the release: the GPU builds with vLLM (the release settings of `serve_vllm.sh`: GPU memory fraction 0.85,
64 sequences, prefix caching) behind `serve.py`; the MLX build behind an MLX server that answers the same API (prefix
cache per state; every answer the same as one prompt per question; read-once requests are answered that way). The MLX
build is evaluated with MLX on a Linux GPU, as the Eikos MLX builds were. Sets and scripts are those of the release
evaluation:

- `git3_test_known` + `git3_test_held` (3,105 questions), with `release_eval.py`;
- the answers the actions change in `multi_test_testfam` (one prompt per question and read-once) and
  `multi_test_trainfam`, with `release_eval.py`;
- the answers the actions change in `ftest_family`, and the 240-question comparison, with `release_eval_extra.py`;
- T3c, the 16 real-repository scenarios, through the `ekbasis` client, with `release_eval_t3c.py`;
- speed of the GPU builds on one RTX 6000 Pro with the release harness (reported, not gated).

## Gate

The reference is the bf16 release (RELEASE_EVAL.md). A build **passes** when all of these hold:

1. **Accuracy within one point**: Δ ≥ −1.0 point against bf16 on git3 (known + held pooled, all questions; bf16
   96.39%), on the changed answers of `multi_test_testfam` (one prompt per question; bf16 81.16%; GPU builds also
   read-once, bf16 78.20%) and on the changed answers of `ftest_family` (bf16 81.72%).
2. **The guard**: T3c work-losing scenarios flagged 3 of 3; on git3, work-losing questions flagged at P(lost) ≥ 0.2 no
   more than 1 point below bf16, and false alarms at 0.2 no more than 1 point above, for known and held types.
3. **Calibration**: ECE (10 equal-width bins on the confidence of the chosen answer, git3 pooled) at most bf16 + 0.01.
4. **Agreement with bf16** (same answer): at least 97% over git3, the `multi_test_testfam` answers and `ftest_family`;
   and at least 99% on the answers bf16 gives with confidence ≥ 0.9 (git3 and `ftest_family`, which keep confidences).

A build that misses a criterion may still be released with a note that names the criterion and the numbers, as was done
for Eikos; that decision is the maintainer's. All results are reported. vLLM with batching and prefix caching is not
bit-for-bit deterministic between runs (1–2 near-tie answers per set can change), which the tolerances absorb.
