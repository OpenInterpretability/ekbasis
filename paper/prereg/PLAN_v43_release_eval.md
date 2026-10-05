# The release evaluation of a confirmed V43 candidate

Written on 2026-10-04 before the round-4 confirmation's results were known and before any of this evaluation ran.

A round-4 run confirmed better in the loop (PLAN_v43_round4_confirm.md, _r4a.md) is a V43 candidate only if the rest of
what the release promises holds. It goes through the release evaluation of the quantized builds (the same scripts:
release_eval.py, release_eval_extra.py on the server, release_eval_t3c.py on the fresh real repositories through the
ekbasis client, here with the injection secondary as well), served like the release (merged, 3 replicas, the System One
API), against V42's release evaluation, item by item, with the checks of compare_quant_ekbasis.py (PREREG_quantized.md):

- git3 known and held, all questions: not lower than V42's by more than 1 point;
- multi_test_testfam, answers the actions change (one prompt per question, and read once): not more than 1 point lower;
- ftest_family, answers the actions change: not more than 1 point lower;
- the guard on fresh real repositories (T3c): all 3 work-losing commands flagged at 0.2;
- git3 known and held: work-losing commands flagged at 0.2 not lower by more than 1 point, false alarms at 0.2 not higher
  by more than 1 point;
- calibration: ECE on git3 pooled not higher by more than 0.01.

The two agreement checks of that gate (with the bf16 release) are reported, not required: a new model is meant to answer
differently. Also reported: the injection secondary on T3c, the 240-question comparison, and every number next to V42's.
Speed is not measured (the same architecture and size, the adapter merged into the weights).

Passing makes the run a V43 candidate for Caio's decision, nothing more: no release, card or page changes without him.
