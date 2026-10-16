# V50P — results (pre-registered; analysis by `scripts/analyze.py`, paired bootstrap by item, 2,000 resamples)

Training: 600 steps in 61.4 min on one RTX PRO 6000 (6 s/step); final step = candidate (validation fval_git3 0.931).
Base and candidate scored by the same trainer code (bf16, letter readout).

**M1, horizon test (training families, new worlds), accuracy by number of actions**

| actions | 1 | 2 | 3 | 5 | 8 | 12 | 20 |
|---|---|---|---|---|---|---|---|
| base | 0.989 | 0.964 | 0.959 | 0.834 | 0.845 | 0.747 | **0.692** |
| candidate | 0.974 | 0.964 | 0.964 | 0.849 | 0.840 | 0.768 | **0.753** |

Long (8+12+20 pooled, n = 596): **+0.025 [+0.002, +0.047]** — CI above 0, but **below the pre-registered +0.03**.
→ **(a) fails narrowly; verdict by the sealed rule: not promising.** (b) holds: no suite drops.

**M2, LATENT worlds (never trained)**: predictor-worlds k=10 +0.030 [+0.005, +0.057]; held-out k=3 +0.037 [+0.013,
+0.062]; the other cells within ±0.012, CIs across 0 (held-out k=10 −0.004).

**M3, regression suites**: no clear drop. git3 known +0.000, git3 held −0.004 [−0.012, +0.004], guard +0.003,
ftest_family +0.009, m3val **+0.023** [+0.003, +0.047], fval_git3 +0.001, multi +0.005, multi single **+0.013**
[+0.005, +0.020].

## Reading
- The plan-level items move the model in the intended direction and cost nothing elsewhere; the gain grows with the
  horizon and is largest where training never reached (20 actions: 0.692 → 0.753, +6 points), but the pooled long
  gain (+2.5) misses the bar set in advance (+3). Honest label: **a small, real, regression-free gain; not yet the
  long-horizon unlock.**
- Limits: one arm, 600 steps, 15% floorPL, no F factory data / anchors / FX (off the rig); M4 (latent readout) not run.

**M4 (reported), latent readout on true-state last-token latents (LATENT D1 recipe, MLP readout), both loaded the same
way (bf16, AutoModelForCausalLM; candidate = base + adapter merged):** predictor worlds L32 base 0.675 / candidate
0.667, L48 0.672 / 0.654; held-out L32 0.787 / 0.770, L48 0.781 / 0.784. **No change**: 600 steps of plan-level items
with the JEPA term did not make the model hold the state in a question-free vector. The "latent imagination" unlock
is not reached this way.

## Dose arm (ADDENDUM_DOSE: floorPL 0.30, 1,200 steps; same base predictions, same analysis)
- **M1 long (8+12+20): 0.762 → 0.802, +0.040 [+0.012, +0.070] → PASSES the sealed rule (≥ +0.03, CI > 0).**
  By length (base / pilot / dose): 8: 0.845 / 0.840 / 0.855; 12: 0.747 / 0.768 / **0.803**; 20: 0.692 / 0.753 / 0.747.
  The gain grew with the dose (pilot +0.025 → dose +0.040): evidence the effect is real.
- **M3: no clear drop** (rule (b) holds). git3 held **+0.010 [+0.004, +0.017]**, git3 known +0.005, guard 0.000,
  ftest_family −0.003 [−0.016, +0.011], m3val +0.007, fval_git3 +0.003, multi −0.003, multi single +0.008.
- **M2 (worlds never trained):** predictor-worlds k3 +0.023 [+0.007, +0.042]; held-out k3 +0.040 [+0.010, +0.069];
  other cells within ±0.02 with CIs across 0 (k10: +0.012 and +0.006).
- **Calibration watch (not in the rule):** the dose model is more confident; ECE rose on several suites (e.g.
  ftest_family 0.103, fhorizon 0.064 vs the pilot's 0.052). A full V50 must refit temperature on validation
  (PLAN_v50_draft §7) before any release, because look-when-unsure depends on honest confidence.
- **Verdict: promising.** Next: M4 (latent) and M5 (real git, 5–12 commands) are queued on the same machine.
- **M4 (dose):** latent readout L32 0.690 / L48 0.664 (base 0.675 / 0.672); held-out 0.765 / 0.787 (base 0.787 /
  0.781). **No change**, as in the pilot: the long-horizon gain comes without a question-free "held state".

## M5 — real git, 5/8/12 commands (ADDENDUM_M5, sealed before scoring)
| commands | base | pilot | dose |
|---|---|---|---|
| 5 | 0.940 | 0.943 | 0.943 |
| 8 | 0.887 | 0.880 | 0.913 |
| 12 | 0.893 | 0.897 | 0.880 |

dose − base on 8+12: **+0.007 [−0.008, +0.023] → no transfer** by the sealed reading (CI includes 0); pilot −0.002.
"lost": 0.800 / 0.814 / 0.814 (n 140); "fails": 0.934 / 0.940 / 0.940 (n 151). Nothing got worse.
Reading: the long-horizon skill learned on synthetic worlds does not carry over to real git, where the base is
already much stronger on long sequences (0.89–0.94 vs 0.69–0.85 in the worlds). To gain on real domains, the
plan-level items must come from those domains — gitbox3 already generates long real git sequences with exact labels.
