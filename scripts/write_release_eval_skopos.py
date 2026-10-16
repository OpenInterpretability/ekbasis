#!/usr/bin/env python3
"""Writes RELEASE_EVAL_SKOPOS.md, the release evaluation of Ekbasis-Skopos-27B, with every number read from
results_skopos/ (and Ekbasis-27B's reference files in results/); no number is typed here.

  python scripts/write_release_eval_skopos.py           draft: a result that has not run yet is marked "pending"
  python scripts/write_release_eval_skopos.py --final   exit 1, listing them, if any file the document cites is missing
"""
from __future__ import annotations

import json
import os
import re
import sys
from decimal import ROUND_HALF_UP, Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "results_skopos")
FINAL = "--final" in sys.argv
missing: list = []


def ld(path):
    """A results file (relative to results_skopos/, or to the repository with a leading '../'), or None if absent."""
    p = os.path.normpath(os.path.join(R, path))
    if not os.path.exists(p):
        missing.append(os.path.relpath(p, ROOT))
        return None
    with open(p) as f:
        return json.load(f) if p.endswith(".json") else f.read()


def pending(path, what):
    return f"*Pending: {what} (`{os.path.relpath(os.path.normpath(os.path.join(R, path)), ROOT)}` not yet written).*"


def h(x, nd=1):
    return str(Decimal(str(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def sg(x, nd=1):
    s = h(abs(x), nd)
    return ("−" if x < 0 and float(s) != 0 else "+") + s


def ci(c, nd=1, scale=1):
    return f"[{sg(scale * c[0], nd)}, {sg(scale * c[1], nd)}]"


def span(c, nd=3):
    return f"[{h(c[0], nd)}–{h(c[1], nd)}]"


def of(s):
    return s.replace("/", " of ")


CHECK = {"git3": "git v3", "ECE": "ECE", "multi single": "worlds, one prompt", "multi read_once": "worlds, read once",
         "ftest": "ftest_family", "guard_known flagged": "guard flagged (known)",
         "guard_known false alarms": "guard false alarms (known)", "guard_held flagged": "guard flagged (held-out)",
         "guard_held false alarms": "guard false alarms (held-out)", "agreement >= 97": "agreement ≥ 97%",
         "agreement conf>=0.9 >= 99": "agreement where the bf16 is sure ≥ 99%"}


RR = ld("release_read_bf16.json")
REL, SK = RR["release"], RR["candidate"]
REP = ld("release_read_bf16_report.json")
EXTRA = ld("release_read_bf16_report_extra.json")
GUARD = ld("release_read_bf16_guard.json")
FP = ld("release_read_ftest_paired.json")
CF = ld("confirm_ftest_fresh.json")
CMP2 = ld("skopos_v49f_vs_r2.json")
CMP4 = ld("r4_vs_skopos_v49f.json")
VSE = ld("r4_vs_ekbasis27b_trainer.json")
NEU = ld("neutral.json")
IMG = ld("image_compare.json")
OV = ld("overlap_audit_r4.json")
T3C = ld("t3c_r4.json")
T3C_REF = ld("../results/release_eval/release_eval_t3c.json")
CE = ld("ce_r4.json")
CAL = {b: ld(f"calib_fit_skopos_{b}.json") for b in ("bf16", "int4", "fp8", "mlx")}
CAL_EKB = ld("calib_fit_ekbasis_int4.json")
BUILDS = {b: (ld(f"release_read_{b}.json"), ld(f"quant_gate_{b}.json")) for b in ("int4", "fp8", "mlx")}
FRESH = {b: ld(f"ftest_fresh_{b}.json") for b in ("int4", "fp8")}
# The same summaries without the items the overlap audit flags (decision D8): the tables print these, as the model
# cards do, with the all-items value beside them.
CL = lambda f: ld(f"overlap_audit/clean/{f}_clean.json")
CMP4C, VSEC, IMGC, CEC = CL("r4_vs_skopos_v49f"), CL("r4_vs_ekbasis27b_trainer"), CL("image_compare"), CL("ce_r4")
CALC = {b: CL(f"calib_fit_skopos_{b}") for b in CAL}
CALC_EKB = CL("calib_fit_ekbasis_int4")
ALLCOL = "All items, before the D8 exclusion"
# Added after the independent review (Part C): the guard's counts paired, confident errors' ECE per group (registered in
# A2, missing from ce_r4.json), git v3 per question type against Ekbasis-27B, and the first Skopos' λ selection.
GP = ld("guard_paired.json")
CEE = ld("ce_r4_ece.json")
G3T = ld("git3_by_type_paired.json")
V49B = ld("candidates/first_skopos_v49/v49b_selection.json")
REC0 = ld("overlap_audit/recomputed.json")
OVA0 = ld("overlap_audit/overlap.json")


def pv(p):
    """A p-value as printed: two significant digits, powers of ten below 0.001."""
    if p >= 0.001:
        return f"{p:.2g}"
    m, e = f"{p:.1e}".split("e")
    return f"{m} × 10" + "".join("⁻⁰¹²³⁴⁵⁶⁷⁸⁹"["-0123456789".index(c)] for c in str(int(e)))
MACP = os.path.join(R, "runs", "mlx_mac", "mlx_mac_test.json")  # not an input: without a pass, MLX is not released
MAC = json.load(open(MACP)) if os.path.exists(MACP) else None
MLX_IN = bool(MAC and MAC.get("pass"))
N_ITEMS = sum(1 for _ in open(os.path.join(R, "runs", "neutral_items.jsonl")))
SCEN = re.findall(r'^    \("([^"]+)",', ld("scripts/git_battery3.py") or "", re.M)  # the scenarios' names, in order
SEQ = ld("served_equivalence_bf16.json")
PIN = (ld("runs/t3c/t3c_pinned_commit.txt") or "").strip()

pct = lambda g, i: 100 * g[i] / g[i + 1]
SUITE = {"fac_val": "Executed factory scenarios (shell, SQL, Python, git)", "git_long": "Real git sequences, 5–12 commands",
         "git_long_val": "Same, validation twin", "sess_val": "Agent sessions (shell, read as a transcript)",
         "latent_test": "Latent-state worlds", "fhorizon": "Synthetic horizons, 1–20 actions",
         "git3_test_known": "git v3, known command types", "git3_test_held": "git v3, held-out command types",
         "guard_known": "The guard, known command types (all questions)", "ftest_family": "Never-trained families (`ftest_family`)",
         "m3val": "Factory-3 worlds (validation)", "fval_git3": "git v3 (validation)"}
out = []
w = out.append

# ---------------------------------------------------------------------------------------------------------------- intro
w("# Ekbasis-Skopos-27B release evaluation — results\n")
if not FINAL:
    w("> **Draft.** Results still to come are marked *pending*; the final version is written with `--final`, which "
      "refuses to build while any of them is missing.\n")
w(f"""**The release, Ekbasis-Skopos-27B, is R4 merged into the first Skopos.** The first Skopos is Ekbasis-27B trained
further on executed scenarios (v49f) and interpolated halfway back to it; R4 is a LoRA trained on top of it, with real
git sequences of several commands, the executed factory regenerated, and synthetic long sequences
([training/skopos/](training/skopos/README.md)). How R4 was chosen is the first section. It was then read by
Ekbasis-27B's release protocol ([PREREG_release_eval.md](PREREG_release_eval.md) as applied in
[RELEASE_EVAL.md](RELEASE_EVAL.md), with the larger guard set), pre-registered for it before any served answer on its
items, though after the trainer's readouts of the same sets ([prereg_skopos/PREREG_R4_RELEASE_READ.md](prereg_skopos/PREREG_R4_RELEASE_READ.md);
deviation 12), on the **exact release weights** served by vLLM and the System One API (`serve.py`), and on each
quantized build. The real-repository scenarios of Ekbasis-27B's release (T3c), the confident-errors test and a
calibration fit per build followed under an addendum registered before they ran
([prereg_skopos/PREREG_ADDENDUM.md](prereg_skopos/PREREG_ADDENDUM.md)). Every pre-registration's hash is in
[prereg_skopos/PREREG_sha256.txt](prereg_skopos/PREREG_sha256.txt); the times are those of our seal log, a local file
without an external timestamp (deviation 11). All results are reported, favourable or not; every prediction is in
[`results_skopos/runs/`](results_skopos/README.md), except the quantized builds' answers on the fresh `ftest` items
(summaries only; deviation 8), and `results_skopos/scripts/verify_summaries.py` recomputes the summaries from them.
Every table on a set where the overlap audit flags items says whether its numbers are on all items or without the
flagged ones. Deviations from the pre-registrations are listed at the end.
""")

# ------------------------------------------------------------------------------------------------------ how it was chosen
v2, v4 = CMP2["verdict"], CMP4["verdict"]
g2, g4 = CMP2["guard_0.2"], CMP4["guard_0.2"]
lb = V49B["base"]
lam = {k: V49B["arms"]["v49f"][k] for k in ("v49f", "v49f_w75", "v49f_w50")}
fails = lambda k: " and ".join({"ce_acc": "accuracy", "ce_ece": "ECE"}[c] for c, ok in lam[k]["checks"].items() if not ok)
w("## How this checkpoint was chosen\n")
w(f"""1. **The first Skopos** (`v49f_w50`): Ekbasis-27B's release adapter trained 900 more steps (v49f) on executed shell,
   git and SQLite scenarios, the FX factory (with rows converted from two public datasets of real commands and code
   traces), fresh guard-style git items and a replay of Ekbasis-27B's own mix, then the exact interpolation halfway
   between the two adapters (λ = 0.5), merged: an unreleased intermediate checkpoint, archived privately, which
   [training/skopos/](training/skopos/README.md) retrains approximately (its README lists what will differ in a rerun).
   λ = 0.5 was chosen because v49f itself failed PLAN_v49b's old-worlds rule on its validation set `ce49b_val_all`
   (trained, held-out-question and never-trained families weighted equally: accuracy {h(lam['v49f']['acc_eq'], 2)}% against
   Ekbasis-27B's {h(lb['acc_eq'], 2)}%, {h(V49B['tolerances']['acc'])} point allowed; ECE {h(lam['v49f']['ece'], 3)} against
   {h(lb['ece'], 3)}, {h(V49B['tolerances']['ece'], 2)} allowed), λ = 0.75
   failed on {fails('v49f_w75')}, and λ = 0.5 passed (accuracy {h(lam['v49f_w50']['acc_eq'], 2)}%, ECE
   {h(lam['v49f_w50']['ece'], 3)}; `results_skopos/candidates/first_skopos_v49/v49b_selection.json`). The selection of R4
   below had no such rule on confident errors or calibration in the old worlds. Every candidate that was not released,
   with its rule and outcome: [results_skopos/candidates/](results_skopos/candidates/README.md).
2. **R2 did not replace it** ([PREREG_SKOPOS_CMP.md](prereg_skopos/PREREG_SKOPOS_CMP.md)). R2, the same new data
   trained as a LoRA on Ekbasis-27B, gained on {", ".join(f"`{s}`" for s in v2["gain_suites"])} but flagged
   {h(g2["r2"]["flagged_at_0.2"], 2)}% of the work-losing commands of `guard_known` at 0.2 against the first Skopos'
   {h(g2["skopos"]["flagged_at_0.2"], 2)}% ({sg(v2["guard_flagged_diff"], 2)} points; the rule allowed −1)
   (`results_skopos/skopos_v49f_vs_r2.json`).
3. **R4, R2's recipe trained on the first Skopos, replaced it** under the same rule
   ([PREREG_R4.md](prereg_skopos/PREREG_R4.md)): {"none" if not v4["suites_worse"] else ", ".join(v4["suites_worse"])} of the
   {len([k for k in CMP4 if k in SUITE])} suites worse with an interval entirely below zero, work-losing commands flagged
   {h(g4["r2"]["flagged_at_0.2"], 2)}% against {h(g4["skopos"]["flagged_at_0.2"], 2)}% ({sg(v4["guard_flagged_diff"], 2)}),
   false alarms {h(g4["r2"]["false_alarms_at_0.2"], 2)}% against {h(g4["skopos"]["false_alarms_at_0.2"], 2)}%, and gains
   with an interval above zero on {", ".join(f"`{s}`" for s in v4["gain_suites"])} (`results_skopos/r4_vs_skopos_v49f.json`;
   in this file the key `r2` means R4). Trainer readout.

   R1 → R2 → R4 were each selected on `fac_val`, `git_long` and `git_long_val`, sets drawn from the same generators as
   their training rows (selection on top of in-distribution data). The more independent evidence is the fresh items of
   the never-trained world families (`ftest_fresh`, below) and the real agent turns of the neutral suite. Those families
   were never in training rows, but they entered selection on validation data: the first Skopos' λ was chosen on
   `ce49b_val_all`, whose never-trained group is cards, machines, tally, timers and track (the three families of
   `ftest_fresh` among them). Every stage kept its last step, so `fval_git3`, the validation set named in each recipe
   (it includes track and tally items), chose no checkpoint; it is part of the calibration fit set.
""")
IND = {"fac_val", "git_long", "git_long_val", "sess_val", "fhorizon"}  # same generators as training rows, fresh seeds
EX4 = CMP4C["clean"]["excluded_n"]
w(f"| Suite | Items | Ekbasis-27B | first Skopos | **Skopos (R4)** | Skopos − first Skopos, 95% CI | Skopos − Ekbasis-27B, 95% CI | "
  f"{ALLCOL}: Ekbasis-27B / first Skopos / Skopos |\n|---|---|---|---|---|---|---|---|")
for s, name in SUITE.items():
    if s in CMP4C:
        d, a, ex = CMP4C[s], CMP4[s], EX4.get(s, 0)
        e = VSEC["sets"].get(s)
        et = f"{sg(100 * e['r4_minus_ekbasis27b'][0])} {ci(e['r4_minus_ekbasis27b'][1], 1, 100)}" if e else "—"
        n = f"{d['n']:,} of {d['n'] + ex:,}" if ex else f"{d['n']:,}"
        al = f"{h(100 * a['base'])} / {h(100 * a['skopos'])} / {h(100 * a['r2'])}" if ex else "no item flagged"
        w(f"| {name}{' †' if s in IND else ''} | {n} | {h(100 * d['base'])} | {h(100 * d['skopos'])} | **{h(100 * d['r2'])}** | "
          f"{sg(100 * d['r2_minus_skopos'][0])} {ci(d['r2_minus_skopos'][1], 1, 100)} | {et} | {al} |")
w("\nPaired bootstrap by item (2,000 resamples, seed 20261015), without the items the overlap audit flags ("
  + ", ".join(f"{n:,} in `{s}`" for s, n in EX4.items()) + "; decision D8, see the overlap section): "
  "`results_skopos/overlap_audit/clean/r4_vs_skopos_v49f_clean.json`, and for the Skopos − Ekbasis-27B column "
  "(descriptive, the same predictions and bootstrap) `…/clean/r4_vs_ekbasis27b_trainer_clean.json`. The selection read "
  "all items (`results_skopos/r4_vs_skopos_v49f.json`, the last column). † In-distribution: the same generators as "
  "training rows, with fresh seeds and firewalls.")
if SEQ:
    n_same = SEQ.get("same", SEQ.get("same_answer"))
    if n_same is None or "n" not in SEQ:
        missing.append("served_equivalence_bf16.json: expected keys n and same")
    w(f"The served model gives the trainer's answer on {n_same} of {SEQ.get('n')} items "
      "(`results_skopos/served_equivalence_bf16.json`, addendum A6; an earlier run of the same check was printed, not "
      "saved).\n")
else:
    w("Served against trainer, item by item: " + pending("served_equivalence_bf16.json", "addendum A6") + "\n")

# -------------------------------------------------------------------------------------------------------- the release read
chk = RR["checks"]
mark = lambda k: "holds" if chk[k] else "**fails**"
t3 = T3C["primary_summary"] if T3C else None
t3r = T3C_REF["primary_summary"]
w("## The release read\n")
w(f"""4. **It then passed the release protocol on every criterion but one**, against Ekbasis-27B item by item
   (`results_skopos/release_read_bf16.json`; Ekbasis-27B's predictions are those of its own release evaluation,
   `results/release_eval/`):
""")
w("| Criterion (at most 1 point worse than Ekbasis-27B; 0.01 for ECE) | Ekbasis-27B | Skopos | |\n|---|---|---|---|")
w(f"| git v3, known and held-out command types, all questions | {h(REL['git_v3_all'], 2)}% | {h(SK['git_v3_all'], 2)}% | {mark('1 git v3')} |")
w(f"| Never-trained worlds, answers the actions change: one prompt per question / read once | {h(REL['multi_testfam_single'], 2)}% / "
  f"{h(REL['multi_testfam_read_once'], 2)}% | {h(SK['multi_testfam_single'], 2)}% / {h(SK['multi_testfam_read_once'], 2)}% | "
  f"{mark('2a multi single')} / {mark('2b multi read-once')} |")
w(f"| `ftest_family`, answers the actions change | {h(REL['ftest_changed'], 2)}% | {h(SK['ftest_changed'], 2)}% | {mark('3 ftest changed')} |")
w(f"| Calibration: ECE on git v3 | {h(REL['ece_git_v3_10bins'], 3)} | {h(SK['ece_git_v3_10bins'], 3)} | {mark('4 ECE git v3')} |")
for key, lab, a, b in (("guard_known", "known", "5a guard known flagged", "5b guard known false alarms"),
                       ("guard_held", "held-out", "6a guard held flagged", "6b guard held false alarms")):
    w(f"| The guard, larger set, {lab} command types: work-losing flagged of {SK[key][1]} / false alarms of {SK[key][3]} | "
      f"{REL[key][0]} / {REL[key][2]} | {SK[key][0]} / {SK[key][2]} | {mark(a)} / {mark(b)} |")
if t3:
    ok = all(int(t3[k].split("/")[0]) >= int(t3r[k].split("/")[0]) for k in ("work_losing_flagged", "fails_right")) and \
        int(t3["false_alarms"].split("/")[0]) <= int(t3r["false_alarms"].split("/")[0])
    w(f"| Real-repository scenarios (T3c): work-losing flagged / false alarms / \"fails?\" right | "
      f"{of(t3r['work_losing_flagged'])} · {of(t3r['false_alarms'])} · {of(t3r['fails_right'])} | {of(t3['work_losing_flagged'])} · "
      f"{of(t3['false_alarms'])} · {of(t3['fails_right'])} | {'holds' if ok else '**fails**'} (addendum A1) |")
else:
    w(f"| Real-repository scenarios (T3c) | {of(t3r['work_losing_flagged'])} · {of(t3r['false_alarms'])} · {of(t3r['fails_right'])} | "
      f"{pending('t3c_r4.json', 'A1')} | |")
w("\nHeld-out command types: held out of the git sandbox's training rows (see the git v3 section).")
fb = FP["bf16"]
fw = fb["by_world"]
cw = CF["changed_by_world"]
w(f"""
**The failed criterion and its confirmation.** The pre-registered release read failed this criterion: on
`ftest_family`'s {FP['items_changed']} answers the actions change, Skopos was {sg(fb['diff'], 2)} points from Ekbasis-27B,
past the 1-point limit, with a paired interval across zero
({ci(fb['ci95'], 2)}; {fb['lost']} answers lost and {fb['gained']} gained; cards {fw['cards']['skopos']} against
{fw['cards']['ekbasis27b']}, machines {fw['machines']['skopos']} against {fw['machines']['ekbasis27b']}, timers
{fw['timers']['skopos']} against {fw['timers']['ekbasis27b']}; `results_skopos/release_read_ftest_paired.json`). A
confirmation registered after that result, before any fresh item existed, and read by the trainer's readout of both
models rather than served ([CONFIRM_FTEST.md](prereg_skopos/CONFIRM_FTEST.md)), generated {CF['all']['n']:,} fresh items of the same three
never-trained families with the same recipe, five times as many: on the {CF['changed']['n']:,} answers the actions
change, Skopos {h(CF['changed']['r4'], 2)}% against {h(CF['changed']['release'], 2)}%
({sg(CF['changed']['r4_minus_release'][0], 2)} points, {ci(CF['changed']['r4_minus_release'][1], 2)}); on all answers
{sg(CF['all']['r4_minus_release'][0], 2)} {ci(CF['all']['r4_minus_release'][1], 2)}. Per family: cards
{sg(cw['cards']['diff'][0], 2)} {ci(cw['cards']['diff'][1], 2)}, machines {sg(cw['machines']['diff'][0], 2)}
{ci(cw['machines']['diff'][1], 2)}, timers {sg(cw['timers']['diff'][0], 2)} {ci(cw['timers']['diff'][1], 2)}. By the
registered reading (not confirmed if Skopos − Ekbasis-27B ≥ −1.0 point on the changed answers), the loss is
**{'not confirmed' if not CF['loss_confirmed'] else 'confirmed'}** (`results_skopos/confirm_ftest_fresh.json`; trainer
readout of both models, bf16).

| Fresh items, answers the actions change, by number of actions | n | Ekbasis-27B | Skopos | Difference, 95% CI |
|---|---|---|---|---|""")
for k, d in CF["changed_by_steps"].items():
    w(f"| {k} | {d['n']:,} | {h(d['release'], 2)}% | {h(d['r4'], 2)}% | {sg(d['diff'][0], 2)} {ci(d['diff'][1], 2)} |")
w("")

# -------------------------------------------------------------------------------------------------------------- T3c
w("## The git guard on real-repository scenarios (T3c)\n")
if T3C:
    w(f"""The 16 scenarios of Ekbasis-27B's release evaluation (not fresh: public since that release; not dataset items, so
outside the overlap audit), written before V42's evaluation on a clone of
`pallets/itsdangerous` (pinned to commit `{PIN[:7]}`, the last on `main` before Ekbasis-27B's evaluation ran; `main`
has not moved since), each set up in a throwaway copy, the state rendered by the client as by default, the truth from
running the commands; the same scripts ([`results_skopos/scripts/`](results_skopos/README.md)). Run under addendum A1,
from the client through a tunnel to the served bf16 (`results_skopos/t3c_r4.json`).

| | Skopos | Ekbasis-27B |
|---|---|---|
| Work-losing scenarios flagged risky (P(lost) ≥ 0.2) | **{t3['work_losing_flagged']}** | {t3r['work_losing_flagged']} |
| False alarms among the other 13 | {t3['false_alarms']} | {t3r['false_alarms']} |
| "Will uncommitted work be lost?" right at 0.5 | {t3['lost_right_at_0.5']} | {t3r['lost_right_at_0.5']} |
| "Will the command fail?" right | {t3['fails_right']} | {t3r['fails_right']} |

| # | Scenario | Commands | P(lost) | Lost (truth) | P(fail) per command | Fails (truth) |
|---|---|---|---|---|---|---|""")
    for r in T3C["primary"]:
        k = r["k"]
        lost_ok = (r["p_lost"] >= 0.5) == r["truth"]["lost"]
        pf = ", ".join(f"{h(100 * x, 0)}%" + ("" if (x >= 0.5) == f else " ✗") for x, f in zip(r["p_fail"], r["truth"]["fails"]))
        w(f"| {k} | {SCEN[k] if k < len(SCEN) else ''} | {' ; '.join(f'`{c}`' for c in r['commands'])} | "
          f"{h(100 * r['p_lost'], 0)}%{'' if lost_ok else ' ✗'} | {'yes' if r['truth']['lost'] else 'no'} | {pf} | "
          f"{', '.join('yes' if f else 'no' for f in r['truth']['fails'])} |")
    w("\n✗ = wrong at 0.5.\n")
    w("**Injection** (an instruction planted where the guard reads; decisions compared with the same scenario without it; "
      "the truth recomputed in the injected environment):\n")
    w("| Planted in | \"Lost?\" decisions changed | \"Fails?\" decisions changed | Work-losing missed at 0.2 | \"Lost?\" right in the injected environment | Ekbasis-27B (the same four) |\n|---|---|---|---|---|---|")
    for env, d in T3C["injection"].items():
        e = T3C_REF["injection"][env]
        miss = lambda x: ", ".join(f"#{i}" for i in x["work_losing_missed_at_0.2"]) or "none"
        w(f"| {env[0].upper() + env[1:]} | {d['lost_decisions_changed']} | {d['fails_decisions_changed']} | {miss(d)} | "
          f"{d['lost_right_in_injected_env']} | {e['lost_decisions_changed']} · {e['fails_decisions_changed']} · {miss(e)} · "
          f"{e['lost_right_in_injected_env']} |")
    w("\nCommit messages are shown only with `commit_text=\"message\"`, not the default.\n")
else:
    w(pending("t3c_r4.json", "addendum A1") + "\n")

# ---------------------------------------------------------------------------------------------------- git v3 in detail
w("## git v3 test sets\n")
w("Repositories built and commands executed in a sandbox; \"held-out\" = command types held out of the git sandbox's "
  "training rows (`rebase`, `restore --source`); Skopos' factory rows do contain `git rebase <branch>` and "
  "`git restore --source=<ref> <file>`, so for Skopos these are not unseen commands. 95% bootstrap intervals "
  "(`results_skopos/release_read_bf16_report.json`).\n")
gk, gh = REP["git3_test_known"], REP["git3_test_held"]
w("| | Known command types | Held-out command types |\n|---|---|---|")
for q, lab in (("all", "All questions"), ("lost", "Will uncommitted work be lost?"), ("fails", "Will the command fail?"),
               ("in_progress", "Is an operation left in progress?"), ("changed state", "State the commands change")):
    f = lambda d: f"{h(d['acc'])}% [{h(d['ci95'][0])}–{h(d['ci95'][1])}] ({d['n']:,})"
    w(f"| {lab} | {f(gk[q])} | {f(gh[q])} |")
w(f"| AUROC of P(lost) | {h(gk['lost_auroc'], 3)} | {h(gh['lost_auroc'], 3)} |")
w(f"| Work-losing caught at a 10% false-alarm rate | {h(gk['lost_caught_at_10pct_false_alarm'])}% | {h(gh['lost_caught_at_10pct_false_alarm'])}% |")
w(f"| At the guard's 0.2 flag: caught / false alarms | {h(gk['lost_flagged_at_0.2'])}% / {h(gk['false_alarm_at_0.2'])}% | "
  f"{h(gh['lost_flagged_at_0.2'])}% / {h(gh['false_alarm_at_0.2'])}% |\n")
g3 = G3T["sets"]
qts = [k.split(":")[1] for k in g3 if k.startswith("git3_test_known:")]
w("Against Ekbasis-27B on the same items, per question type (its release evaluation's predictions; paired bootstrap, "
  "2,000 resamples, seed 20261015; `results_skopos/git3_by_type_paired.json`, added after the independent review):\n")
w("| Question type | Known: Skopos / Ekbasis-27B (n) | Difference, 95% CI | Held-out: Skopos / Ekbasis-27B (n) | Difference, 95% CI |\n|---|---|---|---|---|")
for q in qts:
    cells = []
    for split in ("git3_test_known", "git3_test_held"):
        d = g3.get(f"{split}:{q}")
        cells.append(f"{h(d['skopos'])}% / {h(d['ekbasis'])}% ({d['n']:,}) | {sg(d['diff'], 2)} {ci(d['ci'], 2)}" if d else "— | —")
    w(f"| {'All questions' if q == 'all' else f'`{q}`'} | {cells[0]} | {cells[1]} |")
below = [(k, d) for k, d in g3.items() if d["ci"][1] < 0]
edge = [(k, d) for k, d in g3.items() if d["diff"] < 0 and d["ci"][1] == 0]
lab = lambda k: f"`{k.split(':')[1]}` on the {'held-out' if 'held' in k else 'known'} command types"
w("\n" + ("No interval lies entirely below zero" if not below else "**Below zero:** " + "; ".join(
    f"{lab(k)}, {sg(d['diff'], 2)} {ci(d['ci'], 2)}" for k, d in below)) +
  ("" if not edge else "; " + ("two reach" if len(edge) == 2 else f"{len(edge)} reach" if len(edge) > 1 else "one reaches") +
   " zero from below: " + "; ".join(f"{lab(k)}, {sg(d['diff'], 2)} points {ci(d['ci'], 2)} on {d['n']:,} questions"
                                    for k, d in sorted(edge, key=lambda kd: kd[1]["diff"]))) + ".\n")

# --------------------------------------------------------------------------------------------- never-trained worlds
w("## Consequences in never-trained worlds\n")
mt = lambda s, m: REP[f"multi_test_{s} ({m})"]
fa, fc = EXTRA["ftest_family (all answers)"], EXTRA["ftest_family (answers the actions change)"]
w("Only the answers the actions change (the answer before the actions differs), in families of worlds never seen in "
  "training; trained families for reference (`results_skopos/release_read_bf16_report.json`).\n")
w("| | One prompt per question | Read-once (state read once) |\n|---|---|---|")
for s, lab in (("testfam", "**Never-trained families**"), ("trainfam", "Trained families")):
    a, b = mt(s, "one prompt per question"), mt(s, "read-once")
    w(f"| {lab} ({a['n_changed']:,} changed answers) | {h(a['acc_changed'])}% [{h(a['ci95_changed'][0])}–{h(a['ci95_changed'][1])}] · "
      f"{a['prompt_tokens_per_state']:,.0f} prompt tokens per state | {h(b['acc_changed'])}% [{h(b['ci95_changed'][0])}–"
      f"{h(b['ci95_changed'][1])}] · {b['prompt_tokens_per_state']:,.0f} tokens |")
pw = fc["per_world_changed"]
w(f"""
`ftest_family` (never-trained families, one question per state): {h(fc['acc_changed'])}%
[{h(fc['ci95_changed'][0])}–{h(fc['ci95_changed'][1])}] on the {fc['n_changed']} answers the actions change (cards
{pw['cards']}, machines {pw['machines']}, timers {pw['timers']}); {h(fc['acc_unchanged'])}% on the answers they leave
unchanged; {h(fa['acc'])}% [{h(fa['ci95'][0])}–{h(fa['ci95'][1])}] on all {fa['n']:,}. The never-trained sets have no
item the overlap audit flags; the trained families' row is on all items, and the audit flags
{OVA0['sets']['multi_test_trainfam']['flagged']} of that set's {OVA0['sets']['multi_test_trainfam']['items']} (see the
overlap section).
""")

# ------------------------------------------------------------------------------------------------------- the guard
w("## The guard on the larger set\n")
w("20,000 new examples per split from the git generator, from repository states no earlier set contains, balanced like "
  "the git v3 test sets, with the same held-out command types (Ekbasis-27B's `PLAN_guard_set.md`). Through the exact "
  "release weights, served "
  "(`results_skopos/release_read_bf16_guard.json`):\n")
gK, gH = GUARD["guard_known"], GUARD["guard_held"]
w("| | Known command types | Held-out command types |\n|---|---|---|")
w(f"| Work-losing commands flagged at P(lost) ≥ 0.2 | {gK['flagged_at_0.2']} of {gK['work_losing']} ({h(pct([gK['flagged_at_0.2'], gK['work_losing']], 0))}%) | "
  f"{gH['flagged_at_0.2']} of {gH['work_losing']} ({h(pct([gH['flagged_at_0.2'], gH['work_losing']], 0))}%) |")
w(f"| False alarms on safe commands of the same kinds | {gK['false_alarms_at_0.2']} of {gK['safe']} ({h(pct([gK['false_alarms_at_0.2'], gK['safe']], 0))}%) | "
  f"{gH['false_alarms_at_0.2']} of {gH['safe']} ({h(pct([gH['false_alarms_at_0.2'], gH['safe']], 0))}%) |")
w(f"| \"Will the command fail?\" right | {h(100 * gK['fails_right'] / gK['fails_n'])}% ({gK['fails_n']:,}) | "
  f"{h(100 * gH['fails_right'] / gH['fails_n'])}% ({gH['fails_n']:,}) |")
w(f"\nOn the known command types, the trainer's readout gives the same flag decision as the served model on "
  f"{gK['same_flag_decision']:,} of the {gK['lost_items']:,} \"lost\" questions.\n")
gp = GP["splits"]
w("Against Ekbasis-27B on the same items, paired (its release evaluation's predictions; exact McNemar test on the "
  "commands only one model flags, and a paired bootstrap of the difference, 2,000 resamples, seed 20261015; "
  "`results_skopos/guard_paired.json`, added after the independent review):\n")
w("| At P(lost) ≥ 0.2 | Skopos | Ekbasis-27B | Flagged by Skopos only / by Ekbasis-27B only | Difference, points [95% CI] | McNemar p |\n|---|---|---|---|---|---|")
for key, lab in (("guard_known:flagged", "Work-losing flagged, known command types"),
                 ("guard_known:false_alarms", "False alarms, known command types"),
                 ("guard_held:flagged", "Work-losing flagged, held-out command types"),
                 ("guard_held:false_alarms", "False alarms, held-out command types")):
    d = gp[key]
    w(f"| {lab} | {d['skopos']} of {d['n']} | {d['ekbasis']} of {d['n']} | {d['skopos_only']} / {d['ekbasis_only']} | "
      f"{sg(d['diff_pts'], 2)} {ci(d['ci95_pts'], 2)} | {pv(d['mcnemar_p'])} |")
sig = [k for k, d in gp.items() if d["mcnemar_p"] < 0.05]
w(f"\nSkopos flags as many work-losing commands as Ekbasis-27B: the differences in flagged commands are within chance "
  f"(p = {pv(gp['guard_known:flagged']['mcnemar_p'])} and {pv(gp['guard_held:flagged']['mcnemar_p'])}). "
  + ("Only the drop in false alarms on the held-out command types is beyond chance "
     f"({gp['guard_held:false_alarms']['skopos']} against {gp['guard_held:false_alarms']['ekbasis']}); on the known types "
     f"{gp['guard_known:false_alarms']['skopos']} against {gp['guard_known:false_alarms']['ekbasis']} is not "
     f"(p = {pv(gp['guard_known:false_alarms']['mcnemar_p'])})."
     if sig == ["guard_held:false_alarms"] else "Significant at 0.05: " + ", ".join(sig) + ".")
  + " The held-out command types are held out of the git sandbox's rows only: Skopos' factory rows contain them (see "
  "the git v3 section), and v49f was trained on guard-style git items from the same generator (`floorGA`, "
  "[training/skopos/](training/skopos/README.md)).\n")

# ------------------------------------------------------------------------------------------------------- the builds
w("## The quantized builds\n")
w("Each build was read by the same protocol, served (`results_skopos/release_read_<build>.json`), and gated against "
  "the bf16 by Ekbasis-27B's quantization gate ([PREREG_quantized.md](PREREG_quantized.md); "
  "`results_skopos/quant_gate_<build>.json`). The builds and how they were made: "
  "[training/skopos/](training/skopos/README.md).\n")
w("Fresh `ftest` items: each build served, against Ekbasis-27B bf16 by the trainer's readout (the confirmation's "
  "reference), so the two sides of that column differ in readout and in precision; the builds' answers on these items "
  "were not kept, only their summaries (deviation 8).\n")
w("| Build | Gate against the bf16 | Same answer as the bf16 (all / where the bf16 is ≥ 0.9 sure) | git v3 | Never-trained worlds, one prompt / read once | `ftest_family` changed | Guard false alarms, known · held-out | Fresh `ftest` items, changed: the build served vs Ekbasis-27B bf16 (trainer) |\n|---|---|---|---|---|---|---|---|")
w(f"| bf16 | — | — | {h(SK['git_v3_all'], 2)}% | {h(SK['multi_testfam_single'], 2)}% / {h(SK['multi_testfam_read_once'], 2)}% | "
  f"{h(SK['ftest_changed'], 2)}% | {SK['guard_known'][2]} · {SK['guard_held'][2]} | {sg(CF['changed']['r4_minus_release'][0], 2)} "
  f"{ci(CF['changed']['r4_minus_release'][1], 2)} |")
for b, (rr, gate) in BUILDS.items():
    c = rr["candidate"]
    fails = [CHECK[k.split(" ", 1)[1]] for k, v in gate["checks"].items() if not v]
    gtxt = "passes" if gate["pass"] else "misses " + ", ".join(fails)
    ro = h(c["multi_testfam_read_once"], 2) + "%" if c.get("multi_testfam_read_once") is not None else "not measured"
    fr = FRESH.get(b)
    frt = f"{sg(fr['diff'], 2)} {ci(fr['ci'], 2)}" if fr else ("not run" if b == "mlx" else pending(f"ftest_fresh_{b}.json", "fresh items"))
    v = gate["values_bf16_build"]
    w(f"| {b.upper()} | {gtxt} | {h(v['agreement'], 2)}% / {h(v['agreement_conf09'], 2)}% | {h(c['git_v3_all'], 2)}% | "
      f"{h(c['multi_testfam_single'], 2)}% / {ro} | {h(c['ftest_changed'], 2)}% | {c['guard_known'][2]} · {c['guard_held'][2]} | {frt} |")
mg = BUILDS["mlx"][1]["values_bf16_build"]
gpu = [b for b in ("int4", "fp8") if BUILDS[b][1]["pass"]]
same = [b for b in gpu if not BUILDS[b][0]["checks"]["3 ftest changed"] and FRESH[b] and FRESH[b]["ci"][0] > 0]
n_miss = sum(not v for v in BUILDS["mlx"][1]["checks"].values())
w(f"""
{" and ".join(b.upper() for b in gpu)} pass the gate on every check.{" Against Ekbasis-27B, " + " and ".join(b.upper() for b in same) + " fail the release read's `ftest_family` criterion as the bf16 does, and gain on the fresh items, with intervals above zero." if same else ""}
The MLX build misses {n_miss} checks: false alarms
of the guard (known {h(mg['guard_known']['false_alarms'][0], 2)}% → {h(mg['guard_known']['false_alarms'][1], 2)}%, held-out
{h(mg['guard_held']['false_alarms'][0], 2)}% → {h(mg['guard_held']['false_alarms'][1], 2)}%) and agreement with the bf16
({h(mg['agreement'], 2)}%, the gate asks 97%); it was read on Linux with MLX's CUDA backend, read-once not measured
(the MLX server answers it one prompt per question). Under Ekbasis-27B's rule a build ships with its differences on
its card, and this one only after a test on Apple hardware (addendum A4).
""")
if MLX_IN:
    w("It passed that test (`results_skopos/runs/mlx_mac/mlx_mac_test.json`) and is part of the release.\n")
else:
    w("**The MLX build is not part of this release:** its test on Apple hardware has not passed yet.\n")

# ------------------------------------------------------------------------------------------------- confident errors
w("## Confident errors in familiar worlds\n")
if CE:
    aS, aE = CE["primary_skopos"], CE["primary_ekbasis"]  # all items: the registered primary
    pS, pE = CEC["primary_skopos"], CEC["primary_ekbasis"]  # without the flagged items: sensitivity
    sens = REC0["confident_errors"]["sensitivity"]
    w(f"""The pre-registered test of Ekbasis-27B ([PREREG_confident_errors.md](PREREG_confident_errors.md)), the same
{CE['n']:,} questions, one prompt per question, through the served bf16 (addendum A2; `results_skopos/ce_r4.json`,
paired bootstrap against Ekbasis-27B's published predictions, 2,000 resamples, seed 20261015). The items were read from
ekbasis-data's `raw/ce_items.jsonl`, which stores yes/no answers as booleans, while `results/confident_errors/items.jsonl`
and `confident_errors.py` use the strings yes/no: the answers were re-scored with that normalization (deviation 4).
A2 asked for every number on all {CE['n']:,} items and without the items the overlap audit flags; the all-items
numbers are the registered primary, and the {CEC['n']:,} items left without the {CEC['clean']['excluded_n']['ce_items']:,}
flagged ones, all in trained families (decision D8; `results_skopos/overlap_audit/clean/ce_r4_clean.json`), are a
sensitivity analysis.

Its confirmatory question: are wrong answers more often confident (≥ 0.9) in the families a model was trained on than
in those it never saw? On all items, {h(aS['share_T'])}% against {h(aS['share_U'])}% for Skopos
({sg(aS['difference_points'])} points, {ci(aS['ci95'])}; **{aS['verdict']}**, with {aS['families_counted_T']} trained
families counted by the family-median condition), and {h(aE['share_T'])}% against {h(aE['share_U'])}% for Ekbasis-27B
({sg(aE['difference_points'])} {ci(aE['ci95'])}; {aE['verdict']}). Without the flagged items: Skopos
{sg(pS['difference_points'])} {ci(pS['ci95'])} ({pS['verdict']}), Ekbasis-27B {sg(pE['difference_points'])}
{ci(pE['ci95'])} ({pE['verdict']}); there the family-median condition rests on only {pS['families_counted_T']} trained
families with at least 10 wrong answers ({pE['families_counted_T']} for Ekbasis-27B).
""")
    names = {"T": "Trained families", "H": "Trained families, held-out question types", "U": "**Never-trained families**"}
    ece = CEE["groups"]
    ececell = lambda d: f"{h(d['ece_skopos'], 3)} / {h(d['ece_ekbasis'], 3)} ({sg(d['diff'], 3)} {ci(d['diff_ci'], 3)})"
    for title, C, sub_ece in (("All items (the registered primary; `results_skopos/ce_r4.json`)", CE, "all_items"),
                              ("Without the items the overlap audit flags (sensitivity; `…/clean/ce_r4_clean.json`)", CEC, "clean")):
        w(f"{title}:\n")
        w("| Group | n | Error rate: Skopos / Ekbasis-27B (difference, 95% CI) | Wrong at confidence ≥ 0.9, per 100 answers (difference, 95% CI) | ECE: Skopos / Ekbasis-27B (difference, 95% CI) |\n|---|---|---|---|---|")
        for g, lab in names.items():
            for sub, sl in (("all", lab), ("changed", "… answers the actions change")):
                d = C["groups"][f"{g}_{sub}"]
                if C is CEC and d["n"] == CE["groups"][f"{g}_{sub}"]["n"]:
                    w(f"| {sl} | {d['n']:,} | no item flagged: as on all items | | |")
                    continue
                w(f"| {sl} | {d['n']:,} | {h(d['error_skopos'], 2)} / {h(d['error_ekbasis'], 2)} ({sg(d['error_diff'], 2)} "
                  f"{ci(d['error_diff_ci'], 2)}) | {h(d['conf_wrong_per100_skopos'], 2)} / {h(d['conf_wrong_per100_ekbasis'], 2)} "
                  f"({sg(d['conf_wrong_diff'], 2)} {ci(d['conf_wrong_diff_ci'], 2)}) | {ececell(ece[f'{g}_{sub}_{sub_ece}'])} |")
        w("")
    hs = sens["groups"]["H_all"]
    w(f"Under the audit's stricter sensitivity rule ({REC0['confident_errors']['excluded']['sensitivity']:,} items left out), "
      f"the held-out-question error difference is {sg(hs['error_diff'], 2)} {ci(hs['error_diff_ci'], 2)}, an interval across "
      "zero (`results_skopos/overlap_audit/recomputed.json`). ECE per group was registered in A2 but not computed with the "
      "test; it was added after the independent review asked for it (10 equal-width bins on the answer's confidence, "
      "paired bootstrap; `results_skopos/ce_r4_ece.json`, `results_skopos/scripts/ce_ece_by_group.py`; deviation 13).\n")
    u, uc = CE["groups"]["U_all"], CE["groups"]["U_changed"]
    eu, euc = ece["U_all_all_items"], ece["U_changed_all_items"]
    if u["conf_wrong_diff_ci"][0] > 0:
        w(f"In the never-trained families **more of Skopos' wrong answers come with high confidence**: "
          f"{sg(u['conf_wrong_diff'], 2)} per 100 answers {ci(u['conf_wrong_diff_ci'], 2)}, {sg(uc['conf_wrong_diff'], 2)} "
          f"{ci(uc['conf_wrong_diff_ci'], 2)} on the answers the actions change"
          + (f"; and its calibration there is worse: ECE {sg(eu['diff'], 3)} {ci(eu['diff_ci'], 3)}, {sg(euc['diff'], 3)} "
             f"{ci(euc['diff_ci'], 3)} on the changed answers" if eu["diff_ci"][0] > 0 else "") + ".\n")
    beyond = lambda C: [f"{names[g.split('_')[0]].strip('*')}{' (changed answers)' if g.endswith('changed') else ''}, "
                        f"{m}: {sg(d[k], 2)}" for g, d in C["groups"].items()
                        for m, k in (("errors", "error_diff"), ("confident errors", "conf_wrong_diff")) if abs(d[k]) > 1]
    ba, bc = beyond(CE), beyond(CEC)
    w("The registered prediction (within ±1 point of Ekbasis-27B in every group) " +
      ("held" if not ba else "was not met: " + "; ".join(ba)) + ". Without the flagged items it " +
      ("held." if not bc else ("was not met either: " if ba else "was not met: ") + "; ".join(bc) + ".") + "\n")
else:
    w(pending("ce_r4.json", "addendum A2") + "\n")

# ------------------------------------------------------------------------------------------------------ calibration
w("## Calibration per build\n")
TEST_SPLITS = ("git_long", "guard_known", "fac_val")
c0, a0 = CALC["bf16"], CAL["bf16"]
w("One global temperature per build, fitted on validation only (`fval_git3` + `m3val`, negative log-likelihood of the "
  f"right option), then applied to {sum(a0[s]['T1']['n'] for s in TEST_SPLITS):,} test items from sets of the training "
  "generators (" + ", ".join(f"`{s}` {a0[s]['T1']['n']:,}" for s in TEST_SPLITS) + "), each build "
  "scored through its own server (addendum A3). **Not pre-registered:** the two INT4 fits, Skopos' and "
  f"Ekbasis-27B-INT4's (the hosted API's `calibrated` field, T = {h(CAL_EKB['T'], 2)}), were made before A3, so their "
  "comparison is descriptive; and they ran on different serving stacks: Skopos INT4 through vLLM and `serve.py` on an "
  "RTX PRO 6000, Ekbasis-27B-INT4 through the hosted API's own front end on its production GPU, an RTX 5090 "
  "(`results_skopos/scripts/score_skopos_int4.py`, `score_prod.py`). These test sets come from the generators of the "
  "training rows; calibration in never-trained families is in the confident-errors section. "
  f"The table reports the {c0['test_pooled']['T1']['n']:,} test items left "
  "without the " + ", ".join(f"{n:,} of `{s}`" for s, n in c0["clean"]["excluded_n"].items()) + " that the overlap "
  "audit flags (decision D8; `results_skopos/overlap_audit/clean/calib_fit_*_clean.json`; the temperatures are unchanged, "
  "since no validation item is flagged), with the all-items values beside them.\n")
w(f"| Build | Temperature | Accuracy | ECE raw → calibrated | Wrong at ≥ 0.9, per 100: raw → calibrated | Brier raw → calibrated | "
  f"{ALLCOL}: accuracy · ECE raw → calibrated |\n|---|---|---|---|---|---|---|")
for b, d in list(CALC.items()) + [("Ekbasis-27B INT4", CALC_EKB)]:
    lab = f"Skopos {b.upper() if b != 'bf16' else 'bf16'}" if not b.startswith("Ekbasis") else b
    a = CAL_EKB if b.startswith("Ekbasis") else CAL[b]
    if d is None:
        w(f"| {lab} | {pending(f'overlap_audit/clean/calib_fit_skopos_{b}_clean.json', 'addendum A3')} | | | | | |")
        continue
    t1, tf = d["test_pooled"]["T1"], d["test_pooled"]["Tfit"]
    a1, af = a["test_pooled"]["T1"], a["test_pooled"]["Tfit"]
    w(f"| {lab} | {h(d['T'], 2)} | {h(100 * t1['acc'])}% | {h(t1['ece'], 3)} → {h(tf['ece'], 3)} | "
      f"{h(t1['conf_err_per100'], 2)} → {h(tf['conf_err_per100'], 2)} | {h(t1['brier'], 4)} → {h(tf['brier'], 4)} | "
      f"{h(100 * a1['acc'])}% · {h(a1['ece'], 3)} → {h(af['ece'], 3)} |")
w("\nWithout the items the overlap audit flags (see the overlap section); the last column, all items, before that "
  "exclusion (`results_skopos/calib_fit_*.json`). Per split, and what a raw yes-probability becomes calibrated: the same "
  "files (`map_binary`).\n")

# ---------------------------------------------------------------------------------------------------------- neutral
w("## Neutral ground: real agent turns\n")
nb, ns, nr, na = NEU["base"]["pooled"], NEU["skopos"]["pooled"], NEU["r4"]["pooled"], NEU["aw"]["pooled"]
w(f"""[AgentWorldBench](https://huggingface.co/datasets/Qwen/AgentWorldBench) (Qwen, Apache-2.0): real turns of agents
(Terminal-Bench keystrokes and SWE tool calls) with the environment's real observation. One question before each
action, *will it fail?*, on {nr['n']} turns ({nr['fails']} fail), the label read from the observation
([PREREG_NEUTRAL.md](prereg_skopos/PREREG_NEUTRAL.md); `results_skopos/neutral.json`; bootstrap clustered by
trajectory). Evaluation only: these trajectories come from other agents and are never trained on; only their ids and
our labels are published (`results_skopos/runs/neutral_items.jsonl`: {N_ITEMS} of the {nr['n']} rows; {nr['n'] - N_ITEMS} are
withheld, as in the dataset, because its privacy scan flags their trajectory ids; `generators/v50/build_awb_neutral.py`
rebuilds the whole suite from the upstream dataset).

| | AUROC of P(fail) | Balanced accuracy at 0.5 | Recall at 10% false alarms |
|---|---|---|---|
| Ekbasis-27B | {h(nb['auroc'], 3)} {span(nb['auroc_ci'])} | {h(nb['bal_acc'], 3)} {span(nb['bal_ci'])} | {h(nb['recall_at_10fpr'], 3)} |
| first Skopos | {h(ns['auroc'], 3)} {span(ns['auroc_ci'])} | {h(ns['bal_acc'], 3)} {span(ns['bal_ci'])} | {h(ns['recall_at_10fpr'], 3)} |
| **Skopos** | **{h(nr['auroc'], 3)}** {span(nr['auroc_ci'])} | {h(nr['bal_acc'], 3)} {span(nr['bal_ci'])} | {h(nr['recall_at_10fpr'], 3)} |
| Qwen-AgentWorld-35B-A3B, a generative world model with thinking off (8,192 tokens; median {na['median_tokens']:,} tokens, {h(na['median_s'], 0)} s per answer; {na['unparsed']} unparsed, counted wrong) | — | {h(na['bal_acc'], 3)} {span(na['bal_ci'])} | — |
""")
aurocs = [nb["auroc"], ns["auroc"], nr["auroc"]]
bals = sorted([("Ekbasis-27B's", nb["bal_acc"]), ("the first Skopos'", ns["bal_acc"]), ("Skopos'", nr["bal_acc"])], key=lambda x: x[1])
w(f"The three Ekbasis models rank failing actions about equally well: their AUROCs differ by at most "
  f"{h(max(aurocs) - min(aurocs), 3)}, well inside the intervals. At the fixed 0.5 threshold {bals[0][0]} balanced "
  f"accuracy is the lowest of the three; choose the threshold for your false-alarm budget, as the guard does. Against "
  f"Qwen-AgentWorld, Skopos' balanced accuracy is {sg(NEU['diff_vs_aw']['r4']['bal_diff'], 3)} "
  f"{ci(NEU['diff_vs_aw']['r4']['ci'], 3)}" + (", an interval across zero" if NEU['diff_vs_aw']['r4']['ci'][0] < 0 < NEU['diff_vs_aw']['r4']['ci'][1] else "")
  + f"; Qwen-AgentWorld gave no parseable answer on {na['unparsed']} of the {nr['n']} turns (counted wrong), and its "
  "training data may include the source benchmarks' tasks.\n")

# ------------------------------------------------------------------------------------------------------------ images
w("## Images\n")
w(f"""The state can be a picture. R4's training was text only, so its image ability was checked
([PREREG_IMAGE.md](prereg_skopos/PREREG_IMAGE.md)): {IMG['image_all']['n']} fresh items (lamps drawn as bulbs,
containers with the water level; 1–3 actions), half with an answer the actions change, three prompts each, both models
in INT4 through the same serving, images sent as a client sends them (`results_skopos/image_compare.json`). The table
reports the {IMGC['image_all']['n']} items left without the {IMGC['clean']['excluded_n']['image_fresh']} the overlap audit
flags (decision D8; `results_skopos/overlap_audit/clean/image_compare_clean.json`), with all {IMG['image_all']['n']}
beside them.

| Prompt | Skopos INT4 | Ekbasis-27B INT4 | Difference, 95% CI | Changed answers: Skopos / Ekbasis-27B | {ALLCOL}: Skopos / Ekbasis-27B (difference) |
|---|---|---|---|---|---|""")
for k, lab in (("text", "The state as text"), ("image", "The state as an image"), ("read", "Read the final state from an image")):
    a, c, r = IMGC[f"{k}_all"], IMGC[f"{k}_changed"], IMG[f"{k}_all"]
    w(f"| {lab} | {h(a['skopos'])}% | {h(a['ekbasis'])}% | {sg(a['diff'], 2)} {ci(a['ci'], 2)} | {h(c['skopos'])}% / {h(c['ekbasis'])}% | "
      f"{h(r['skopos'])}% / {h(r['ekbasis'])}% ({sg(r['diff'], 2)}) |")
w(f"\nWithout the items the overlap audit flags (see the overlap section); the last column, all items, before that "
  f"exclusion. Image ability **{'preserved' if IMGC['preserved'] else 'not preserved'}** by the registered reading "
  f"(Skopos − Ekbasis-27B ≥ −2.0 points on the image and the read prompts); on all items, "
  f"**{'preserved' if IMG['preserved'] else 'not preserved'}**.\n")

# ------------------------------------------------------------------------------------------- certified mode carry-over
CC = ld("certified_carryover_skopos_int4.json")
CCB = json.load(open(os.path.join(R, "certified_carryover_skopos_bf16.json"))) if os.path.exists(
    os.path.join(R, "certified_carryover_skopos_bf16.json")) else None  # secondary: reported when it has run
w("## Certified mode with Skopos\n")
if CC:
    L2, L1 = CC["model"]["a02"]["L2"], CC["model"]["a02"]["L1"]
    RR = ld("certified_carryover_reference_rows.json")
    cr = CC["criteria"]
    pr = CC["paired_rows_vs_ekbasis27b"]["all"]
    yn = lambda x: "**holds**" if x else "**fails**"
    w(f"""`ekbasis.verify`'s certified mode acts on a confident answer without checking it only where a Learn-then-Test
certificate holds; its thresholds were certified on Ekbasis-27B. A check registered before any request
([PREREG_CERTIFIED_CARRYOVER.md](prereg_skopos/PREREG_CERTIFIED_CARRYOVER.md)) ran the same client (thresholds
unchanged) on Skopos INT4 (primary) and bf16, served, over confirm-3's fresh scenarios: {CC['scenarios_done']:,} scenarios,
{CC['rows']:,} questions, {CC['units']:,} confident units for INT4 ({CC['scenarios_excluded_overlap']} scenarios excluded by
the overlap audit, {CC['requests_failed']} failed requests; `results_skopos/certified_carryover_skopos_int4.json`, code and
data in `results_skopos/certified_carryover/`). A check that the certificate carries over, not a new certificate.

Each unit's score uses the family's error rate as it stands when the unit comes up: every stream starts warm from
WS-P's development history (`results_skopos/certified_carryover/data/dev_family_counts.json`) and then updates online
over the rows it is given, in confirm-3's hashed order. So a row's numbers depend on its scenario set and on whose rows
drive its stream; every row below names both. Ekbasis-27B bf16's stream is confirm-3's whole fresh set (its answers),
as confirm-3 and T2 scored it. WS-MAC T2, the MLX check in `docs/VERIFY.md`, completed {RR['t2_scenarios']:,} of these
scenarios; the rows on those scenarios are recomputed by the check's own analysis functions
(`results_skopos/scripts/certified_reference_rows.py` → `results_skopos/certified_carryover_reference_rows.json`).
""")
    w("| L2, α = 2% (the certified mode) | Scenarios · family-rate stream | Accepted (of the units) | Errors among accepted | Weighted to confirm-3's mix | 95% upper bound | Verified: raw / weighted |\n|---|---|---|---|---|---|---|")
    def row(label, scen, stream, b):
        return (f"| {label} | {scen} · {stream} | {b['accepted']:,} of {b['units']:,} | {b['errors_among_accepted']} "
                f"({h(100 * b['error_rate_among_accepted'], 2)}%) | {h(100 * b['error_rate_among_accepted_weighted'], 2)}% | "
                f"{h(100 * b['cp95_upper_overall'], 2)}% | {h(100 * b['verified_share'])}% / {h(100 * b['verified_share_weighted'])}% |")
    n_all, n_t2 = f"all {CC['scenarios_done']:,}", f"T2's {RR['t2_scenarios']:,}"
    w(row("**Skopos INT4**", n_all, "its own rows", RR["skopos-int4"]["all_scenarios"]["L2_a02"]))
    if "skopos-bf16" in RR:
        w(row("Skopos bf16", n_all, "its own rows", RR["skopos-bf16"]["all_scenarios"]["L2_a02"]))
    w(row("Ekbasis-27B bf16 (confirm-3's answers)", n_all, "confirm-3's whole fresh stream", RR["ekbasis27b_bf16_skopos-int4_scenarios"]["L2_a02"]))
    w(row("Skopos INT4", n_t2, "its own rows there", RR["skopos-int4"]["t2_scenarios"]["L2_a02"]))
    if "skopos-bf16" in RR:
        w(row("Skopos bf16", n_t2, "its own rows there", RR["skopos-bf16"]["t2_scenarios"]["L2_a02"]))
    w(row("Ekbasis-27B bf16, as in docs/VERIFY.md", n_t2, "confirm-3's whole fresh stream", RR["ekbasis27b_bf16_t2_scenarios"]["L2_a02"]))
    w(row("Ekbasis-27B MLX (T2), as in docs/VERIFY.md", n_t2, "its own rows there", RR["mlx_t2_as_published"]["L2_a02"]))
    T2 = ld("certified_carryover/published_t2_summary.json")
    C3 = ld("../results/client_0.1.5/results/confirm3/confirm3.json")
    if T2 and C3:
        same = lambda mine, pub: all(mine[k] == pub[k] for k in ("units", "accepted", "errors_among_accepted",
                                                                   "error_rate_among_accepted_weighted", "cp95_upper_overall"))
        rep_ok = same(RR["mlx_t2_as_published"]["L2_a02"], T2["mlx"]["a02"]["L2"]) and \
            same(RR["ekbasis27b_bf16_t2_scenarios"]["L2_a02"], T2["bf16_same_scenarios"]["a02"]["L2"])
        c3, t2m, t2b = C3["ltt"]["a02"]["L2"], T2["mlx"]["a02"]["L2"], T2["bf16_same_scenarios"]["a02"]["L2"]
        w(f"""
**The published references, with their definitions.** The certificate's own confirmation (confirm-3, Ekbasis-27B bf16,
its whole fresh test of {C3['n_units']:,} units): {c3['errors_among_accepted']} errors among {c3['accepted']:,} accepted
({h(100 * c3['error_rate_among_accepted'], 2)}%; `results/client_0.1.5/results/confirm3/confirm3.json`). WS-MAC T2, the MLX
build on its {RR['t2_scenarios']:,} completed scenarios, family rate streamed over the MLX build's own rows there:
{t2m['errors_among_accepted']} error among {t2m['accepted']:,} accepted ({h(100 * t2m['error_rate_among_accepted_weighted'], 3)}%
weighted, 95% upper bound {h(100 * t2m['cp95_upper_overall'], 2)}%); Ekbasis-27B bf16 on the same scenarios, confirm-3's whole
fresh stream: {t2b['errors_among_accepted']} among {t2b['accepted']:,} ({h(100 * t2b['error_rate_among_accepted_weighted'], 3)}%
weighted) (`results_skopos/certified_carryover/published_t2_summary.json`, the file behind `docs/VERIFY.md`'s MLX numbers,
which quote the raw rates). The check's analysis code recomputes both T2 rows from T2's own answers
{'exactly (units, accepted, errors, weighted rate, upper bound)' if rep_ok else '**with differences**'}: the last two rows
of the table.""")
    w(f"""
Criteria (pre-registered, on all scenarios): C2 (L2: weighted
error among accepted ≤ 2% and no node significantly above) {yn(cr['C2_certified_mode_L2_a02'])}; C2+ (and the raw 95%
upper bound ≤ 2%) {yn(cr['C2plus_L2_cp95_upper_le_2pct'])}; C1 (L1, α = 2%: {L1['errors_among_accepted']} errors among
{L1['accepted']:,} accepted) {yn(cr['C1_L1_a02'])}. Paired with Ekbasis-27B on the same {pr['rows']:,} questions, Skopos INT4
gives the same answer on {pr['agree']:,}; right {pr['model_correct']:,} against {pr['bf16_correct']:,}; wrong at confidence
≥ 0.9 {pr['model_confident_wrong']} against {pr['bf16_confident_wrong']}.""")
    nodes = L2["nodes"]
    acc_n = sorted(v["accepted"] for v in nodes.values())
    med = acc_n[len(acc_n) // 2] if len(acc_n) % 2 else (acc_n[len(acc_n) // 2 - 1] + acc_n[len(acc_n) // 2]) / 2
    wn, wv = min(nodes.items(), key=lambda kv: kv[1]["p_above_alpha"])
    w(f"\n\"No node significantly above\" tests {len(nodes)} nodes with a median of {med:g} accepted answers each "
      f"({acc_n[0]} to {acc_n[-1]}), corrected for their number (Bonferroni), so it has little power on a single node: the "
      f"highest, `{wn}`, has {wv['errors']} errors among {wv['accepted']} accepted (p = {pv(wv['p_above_alpha'])} before the "
      f"correction{'' if not wv['significant_bonferroni'] else '; significant after it'}). The paired reference for the "
      f"carry-over is Ekbasis-27B on the same {CC['scenarios_done']:,} scenarios (the third row of the table); confirm-3's "
      "published rate above is on a different and larger set.")
    if CCB:
        cb, b2 = CCB["criteria"], CCB["model"]["a02"]["L2"]
        w(f"\nThe bf16 build (secondary; `results_skopos/certified_carryover_skopos_bf16.json`): C2 "
          f"{yn(cb['C2_certified_mode_L2_a02'])}, C2+ {yn(cb['C2plus_L2_cp95_upper_le_2pct'])}, C1 {yn(cb['C1_L1_a02'])}.\n")
    else:
        w("\nThe same check on the bf16 build (secondary) has not run yet.\n")
else:
    w(pending("certified_carryover_skopos_int4.json", "PREREG_CERTIFIED_CARRYOVER.md") + "\n")

# ---------------------------------------------------------------------------------------------------------- latency
LS, LE = ld("latency_skopos_int4.json"), ld("latency_ekbasis_int4.json")
w("## Latency and cost (INT4)\n")
if LS and LE:
    w(f"""Both INT4 builds served the same way on the same RTX PRO 6000 (vLLM and `serve.py`, nothing else on the GPU), on
{LS['n']} fixed items (addendum A5; `results_skopos/latency_*_int4.json`). The hosted API runs on another GPU.

| | Skopos INT4 | Ekbasis-27B INT4 |
|---|---|---|
| One at a time: median / 90th percentile | {h(LS['one_at_a_time']['median_s'], 3)} s / {h(LS['one_at_a_time']['p90_s'], 3)} s | {h(LE['one_at_a_time']['median_s'], 3)} s / {h(LE['one_at_a_time']['p90_s'], 3)} s |
| 16 in parallel: requests per second | {h(LS['parallel16']['requests_per_s'], 1)} | {h(LE['parallel16']['requests_per_s'], 1)} |
| Input tokens per request: mean / median | {LS['input_tokens_per_request']['mean']:,.0f} / {LS['input_tokens_per_request']['median']:,.0f} | {LE['input_tokens_per_request']['mean']:,.0f} / {LE['input_tokens_per_request']['median']:,.0f} |
""")
else:
    w(pending("latency_skopos_int4.json", "addendum A5") + "\n")

# ---------------------------------------------------------------------------------------------------------- overlap
w("## Overlap with the training data\n")
w("A first check counted, per evaluation set, the items whose state is identical to a state of the training rows "
  "(`results_skopos/overlap_audit_r4.json`; its script was not saved, so which training files it covered cannot be "
  "shown here; the redone audit below replaces it):\n")
w("| Set | Items | Identical state in training |\n|---|---|---|")
for s, d in OV.items():
    w(f"| `{s}` | {d['items']:,} | {d['state_in_training']} |")
OVA, REC = ld("overlap_audit/overlap.json"), ld("overlap_audit/recomputed.json")
if OVA:
    w(f"""
**The audit redone for this release** against every training row of the Ekbasis-27B stages, v49f and R4
({OVA['training_texts']['unique_normalized']:,} distinct training texts), with Ekbasis-27B's rule: {OVA['rule']}
(`results_skopos/overlap_audit/`, with its two scripts). It does not cover Eikos-27B's own decision data or the Qwen
base's pretraining, nor T3c, whose scenarios are not dataset items. "Flagged" is the exclusion used for the numbers
without overlap; the sensitivity rule also removes the set's layout from the training text.

| Set | Items | Identical | Near duplicate | Flagged | Sensitivity rule | Same generators as training rows |
|---|---|---|---|---|---|---|""")
    for s, d in OVA["sets"].items():
        w(f"| `{s}` | {d['items']:,} | {d['identical']:,} | {d['near_dup']:,} | {d['flagged']:,} | {d['flagged_sensitivity']:,} | "
          f"{'yes' if d['in_distribution'] else 'no'} |")
    if any(s.startswith("scorecard_") for s in OVA["sets"]):
        w("\nThe `scorecard_*` sets are the fixed items of the API scorecard ([scorecard/](scorecard/README.md)), "
          "audited with the rest.")
else:
    w("\nThe audit redone against every training row of the Ekbasis-27B stages, v49f and R4: " + pending("overlap_audit/overlap.json", "the redone audit"))
if REC:
    rp = REC["release_protocol"]
    holds = lambda d: all(all(v.values()) if isinstance(v, dict) else v for v in d.values())
    imgp = REC["image"]["primary"]["image_all"]
    ceU = REC["confident_errors"]["primary"]["groups"].get("U_all")
    w("\n**Every published number recomputed without the flagged items** (`results_skopos/overlap_audit/recomputed.json`):\n")
    for b in ("bf16", "int4", "fp8", "mlx"):
        w(f"- Release read, {b}: every criterion's outcome {'is the same' if holds(rp[b]['conclusion_holds']) else '**changes**'} "
          "under both rules.")
    w(f"- R4 against the first Skopos, and R2 against it: the verdicts "
      f"{'hold' if holds(REC['h2h']['r4_vs_skopos_v49f']['verdict_holds']) and holds(REC['h2h']['skopos_v49f_vs_r2']['verdict_holds']) else '**change**'}.")
    w(f"- The fresh confirmation: {REC['fresh_confirmation']['excluded']['primary']} items flagged; unchanged.")
    w(f"- Images: preserved {'under both rules' if all(REC['image']['preserved_holds'].values()) else '**not under both rules**'} "
      f"(image prompts {sg(imgp['diff'], 2)} {ci(imgp['ci'], 2)} on {imgp['n']} items).")
    w(f"- Quantization gates: each build's pass or miss "
      f"{'holds' if all(holds(REC['quantization_gates'][b]['pass_holds']) for b in REC['quantization_gates']) else '**changes**'}.")
    if ceU:
        byg = REC["confident_errors"]["excluded_by_group"]["primary"]
        names_g = {"T": "trained families", "H": "trained families with held-out question types", "U": "never-trained families"}
        w(f"- Confident errors: {REC['confident_errors']['excluded']['primary']:,} items flagged ("
          + ", ".join(f"{n:,} in the {names_g[g]}" for g, n in byg.items()) + ")"
          + ("; nothing in the never-trained families, so their numbers stand" if not byg.get("U") else "")
          + f" (never-trained families, wrong at ≥ 0.9: {sg(ceU['conf_wrong_diff'], 2)} per 100 {ci(ceU['conf_wrong_diff_ci'], 2)}).")
    if "vs_ekbasis27b_trainer" in REC:
        vp, va = REC["vs_ekbasis27b_trainer"]["primary"], REC["vs_ekbasis27b_trainer"]["all"]
        moved = [s for s in vp if vp[s]["n"] != va[s]["n"]]
        w("- Skopos against Ekbasis-27B (descriptive), on the sets that lose items: " + "; ".join(
            f"`{s}` {sg(100 * vp[s]['r4_minus_ekbasis27b'][0])} {ci(vp[s]['r4_minus_ekbasis27b'][1], 1, 100)} on {vp[s]['n']:,} items "
            f"(all items {sg(100 * va[s]['r4_minus_ekbasis27b'][0])})" for s in moved) + ".")
    for k, v in REC["unchanged_by_construction"].items():
        w(f"- {k}: {v}.")
    if "flagged_vs_clean" in REC:
        w("\nAccuracy on the flagged items and on the rest (`flagged_vs_clean`):\n")
        w("| Set | Flagged items: Skopos / Ekbasis-27B | The rest: Skopos / Ekbasis-27B |\n|---|---|---|")
        for s, d in REC["flagged_vs_clean"].items():
            w(f"| {s} | {h(d['skopos_flagged'])}% / {h(d['ekbasis27b_flagged'])}% ({d['flagged_n']:,}) | "
              f"{h(d['skopos_clean'])}% / {h(d['ekbasis27b_clean'])}% ({d['clean_n']:,}) |")
    w("")
else:
    w(pending("overlap_audit/recomputed.json", "the numbers without overlap") + "\n")
w("Sets from the same generators as training rows (the last column; fresh seeds and firewalls) measure "
  "in-distribution generalization, not transfer.\n")

# --------------------------------------------------------------------------------------------- pre-launch evaluation
PL = os.path.join(R, "prelaunch")  # the pre-launch evaluation's results, once they exist
w("## Pre-launch evaluation\n")
if os.path.isdir(PL) and os.listdir(PL):
    missing.append("results_skopos/prelaunch/ has results that this section does not report yet")
else:
    w("*Pending: the measurements of Ekbasis-27B's release evaluation that had not yet run on Skopos, each next to "
      "Ekbasis-27B on the same items, and the acceptance checks of the published artifacts, as planned in "
      "[prereg_skopos/PRELAUNCH_EVAL.md](prereg_skopos/PRELAUNCH_EVAL.md) (Part A sealed before its first request). "
      "Their results will be reported here, favourable or not.*\n")
    print("note: the pre-launch evaluation section is pending (results_skopos/prelaunch/ is empty)")

# -------------------------------------------------------------------------------------------------------- deviations
w("## Deviations from the pre-registrations\n")
w(f"""1. **The release read failed one criterion** (`ftest_family`, {sg(fb['diff'], 2)} points). Its rule says R4 passes
   if every criterion holds; the release decision rests instead on the confirmation registered after that result
   (CONFIRM_FTEST.md), which did not confirm the loss.
2. **T3c was not run with the release read** (criterion 7 allowed "reported as not run"); it ran under addendum A1,
   with the scenarios' repository pinned to the commit Ekbasis-27B's evaluation used.
3. **T3c injection truth.** As for Ekbasis-27B, the truth of the file-name injection tracks the planted file
   (`rescore_inj_truth.py`; predictions unchanged); the first scoring is `results_skopos/t3c_r4_raw.json`.
4. **Confident errors, scoring only:** {CE['deviation'] if CE else 'pending (A2)'}.
5. **The first Skopos comparison's analysis script** was written after partial accuracies had been seen (its seal
   says so); the rule was registered before, unchanged.
6. **The neutral suite's Ekbasis runs** were rerun at evaluation batch 6 after running out of memory at 48; unparsed
   AgentWorld answers count as wrong (fixed before any Ekbasis score; both in PREREG_NEUTRAL.md's notes).
7. **The MLX build** misses {n_miss} gate checks (above); {"it passed the test on Apple hardware (A4)" if MLX_IN else "it is not part of this release, which A4's test on Apple hardware would have to pass first"}.
8. **Not kept:** the builds' per-item answers on the fresh `ftest` items (only their summaries), and the first run
   of the served-equals-trainer check (printed; rerun under A6).
9. **Training** (not an evaluation deviation, listed for completeness): v49f restarted at micro-batch 4 after running
   out of memory (PLAN_v49 Addendum D; [training/skopos/README.md](training/skopos/README.md)).
10. **Header times later than their seals.** Three pre-registrations carry in their title a time later than their seal
    (`PREREG_SKOPOS_CMP.md` "~12:40 UTC", sealed 12:26:52Z; `PREREG_R4.md` "13:55 UTC", sealed 13:50:28Z;
    `CONFIRM_FTEST.md` "~17:45 UTC", sealed 17:29:19Z). The files are frozen and not edited; the seal times are those in
    `prereg_skopos/PREREG_sha256.txt`.
11. **The seal log is self-attested.** Hashes and times come from our own seal log, a local file without an external
    timestamp, published with the results: the hashes can be checked against the files, the times cannot be checked
    independently.
12. **The release read was sealed after the trainer's readouts of the same sets.** `PREREG_R4_RELEASE_READ.md` was
    sealed before any served answer on its items, but after R4's comparison had read `git3_test_known`,
    `git3_test_held`, `guard_known`, `ftest_family` and `fval_git3` by the trainer's readout (`runs/run_r4/`). Its
    criteria are Ekbasis-27B's inherited 1-point rule, unchanged.
13. **Confident errors, ECE per group:** registered in A2 and not computed with the test; computed after the
    independent review asked for it (`results_skopos/ce_r4_ece.json`).
14. **The INT4 calibration comparison** (Skopos INT4 against Ekbasis-27B-INT4) was measured before A3 was registered:
    descriptive, not pre-registered.
""")

text = "\n".join(out).rstrip() + "\n"
if FINAL and missing:
    sys.exit("RELEASE_EVAL_SKOPOS.md not written; missing:\n  " + "\n  ".join(sorted(set(missing))))
with open(os.path.join(ROOT, "RELEASE_EVAL_SKOPOS.md"), "w") as f:
    f.write(text)
print(f"RELEASE_EVAL_SKOPOS.md written ({'final' if FINAL else 'draft'}); pending: {sorted(set(missing)) or 'none'}")
