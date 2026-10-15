"""REPORT.md of the confident-errors test, every number from report.json and exploratory.json. argv: results dir"""
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

R = Path(sys.argv[1])
rep, exp = json.load(open(R / "report.json")), json.load(open(R / "exploratory.json"))
NAMES = {"grid": "grid", "gravity": "gravity", "counters": "counters", "toggles": "lamps (toggles)", "seq": "sequences",
         "jugs": "containers (jugs)", "craft": "crafting", "track": "track", "tally": "tally", "cards": "card orderings",
         "timers": "timers", "machines": "machines"}


def h(x, nd=1):
    return str(Decimal(str(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


P, C, G = rep["primary"], rep["secondary_changed"], rep["groups"]
GN = {"T": "Trained families, trained question types", "H": "Trained families, the question type held out of training",
      "U": "Families never seen in training"}
row = lambda name, d: (f"| {name} | {d['n']:,} | {d['wrong']} | {h(d['error_rate'])}% | {h(d['share_wrong_conf_ge_0.9'])}% | "
                       f"{h(d['share_wrong_below_0.7'])}% | {h(d['median_conf_wrong'], 2)} | {h(d['auroc'], 2)} |")
head = ("| | Answers | Wrong | Error rate | Wrong answers at confidence ≥ 0.9 | Wrong answers below 0.7 | Median confidence of "
        "wrong answers | AUROC (right vs wrong) |\n|---|---|---|---|---|---|---|---|")
fam_rows = []
for g in ("T", "U", "H"):
    for f in G[g]["families"]:
        d = rep["families"][f"{g}:{f}"]
        fam_rows.append((g, f, d))
fam_rows.sort(key=lambda t: ("TUH".index(t[0]), -t[2]["share_wrong_conf_ge_0.9"] if t[2]["wrong"] else 1))
fam_tab = "\n".join(row(f"{g} · {NAMES[f]}" + (" (fewer than 10 wrong)" if d["wrong"] < 10 else ""), d) for g, f, d in fam_rows)
L, F, D = exp["logistic"], exp["format"], exp["difficulty"]
lo1 = exp["leave_one_family_out"]
text = f"""# Confident errors in familiar worlds: a pre-registered test

Pre-registration: [`PREREG_confident_errors.md`](../../PREREG_confident_errors.md), written on 2026-10-03 before any
item was generated or answered (its SHA-256 is in `PREREG_sha256.txt`). The release weights (Ekbasis-27B, bf16) answered
{sum(G[g]['all']['n'] for g in G):,} new questions, one prompt per question, about the state after 1 to 3 actions, in
12 world families: 7 it was trained on and 5 it never saw.

## Result: {P['verdict']}

Among wrong answers, the share given with a confidence of 0.9 or more is **{h(P['share_T'])}%** in the families it was
trained on and **{h(P['share_U'])}%** in the families it never saw: {h(P['difference_points'])} points apart (95% interval
{h(P['ci95'][0])} to {h(P['ci95'][1])}, items resampled within each family). The family medians agree ({h(P['family_median_T'])}%
against {h(P['family_median_U'])}%, families with at least 10 wrong answers). On the answers the actions change:
{h(C['share_T'])}% against {h(C['share_U'])}% ({h(C['difference_points'])} points, interval {h(C['ci95'][0])} to {h(C['ci95'][1])}).

{head}
{row(GN['T'], G['T']['all'])}
{row(GN['H'], G['H']['all'])}
{row(GN['U'], G['U']['all'])}

## What it means

- In the worlds it knows, Ekbasis errs rarely, but more than half of its errors come with high confidence; in worlds it
  never saw it errs more often, and most errors come flagged. Its confidence still ranks right answers above wrong ones
  about equally well in both (AUROC {h(G['T']['all']['auroc'], 2)} and {h(G['U']['all']['auroc'], 2)}): what moves with
  familiarity is the scale, not the ranking.
- So a fixed threshold misses more errors in the worlds it knows. This is why "look when unsure" also checks the
  forecast now and then (the checks find the errors a fixed threshold misses), and why a threshold tuned on one world does not
  transfer to another.
- A known family asked a question type it was never trained on falls in between ({h(G['H']['all']['share_wrong_conf_ge_0.9'])}%):
  the familiarity of the question counts too.

## Per family

{head}
{fam_tab}

## Robustness (exploratory, not pre-registered)

- **Answer format.** Yes/no questions: {h(F['yes/no']['T']['share'])}% against {h(F['yes/no']['U']['share'])}%; questions
  with options: {h(F['choice']['T']['share'])}% against {h(F['choice']['U']['share'])}%.
- **Difficulty.** Grouping the (family, question type, actions) cells by error rate, the familiar side has more confident
  errors in every band: under 5% errors {h(D['under 5%']['T']['share'])}% against {h(D['under 5%']['U']['share'])}%
  ({D['under 5%']['U']['wrong']} wrong answers on the unfamiliar side), 5–15% {h(D['5-15%']['T']['share'])}% against
  {h(D['5-15%']['U']['share'])}%, 15% or more {h(D['15% or more']['T']['share'])}% against {h(D['15% or more']['U']['share'])}%.
- **One family at a time.** Leaving any one family out, the difference stays between {h(lo1['min'])} and {h(lo1['max'])} points.
- **Families as the unit.** A logistic regression of "confident" among the {L['n_wrong']:,} wrong answers on familiarity,
  the cell's error rate and the answer format gives odds {h(L['odds_ratio'])} times higher in familiar worlds; resampling
  whole families (12 of them), the 95% interval of that coefficient is {h(L['familiar_family_cluster_ci95'][0], 2)} to
  {h(L['familiar_family_cluster_ci95'][1], 2)} and includes zero. Two families go against the pattern (timers, never
  seen, {h(rep['families']['U:timers']['share_wrong_conf_ge_0.9'])}%; counters, trained, {h(rep['families']['T:counters']['share_wrong_conf_ge_0.9'])}%).
  It is a strong tendency of this model over these families, not yet a law across world families.

## Deviations from the plan

- Nine cells could not reach 120 items (96 to 112): grid "moved", gravity "full" and timers "n_done" (allowed by the plan).
- A pipeline test of 251 items (2 per cell, same generator) ran before the main run; its answers are not used.

## Files

`items.jsonl` (the questions), `preds.jsonl` (every answer, its confidence, right or wrong, changed or not),
`report.json` (the pre-registered analysis), `exploratory.json` (the checks above).
"""
(R / "REPORT.md").write_text(text)
print(text[:1500])
