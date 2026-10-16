#!/usr/bin/env python3
"""Introduces Ekbasis-Skopos-27B in README.md, MODEL_CARD.md and CHANGELOG.md as the recommended model, with every
number read from results_skopos/ (Ekbasis-27B stays documented: its sections are not changed). Each insert sits between
<!-- skopos:<name> --> markers, so the script can be run again when the results are final. The wording of the README's
blocks is that of the client-docs patch for this release; the release date (RELEASE_DATE) and the hosted API's
switch date (SWITCH_DATE), YYYY-MM-DD, and the switch's time (SWITCH_TIME, HH:MM UTC), are left as placeholders until
they are set, and the publishing tools refuse to publish while one remains. A switch on the release day (the owner's
decision, against the 14 days the model-change policy promises) gets its own CHANGELOG entry that says so.

  RELEASE_DATE=2026-10-16 SWITCH_DATE=2026-10-16 SWITCH_TIME=14:30 python scripts/apply_skopos_docs.py
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from decimal import ROUND_HALF_UP, Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "results_skopos")
ld = lambda f: json.load(open(os.path.join(R, f)))
has = lambda f: os.path.exists(os.path.join(R, f))
HF, GH = "https://huggingface.co/caiovicentino1", "https://github.com/OpenInterpretability/ekbasis/blob/main"


def h(x, nd=1):
    return str(Decimal(str(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def sg(x, nd=1):
    s = h(abs(x), nd)
    return ("−" if x < 0 and float(s) != 0 else "+") + s


RR = ld("release_read_bf16.json")
REL, SK = RR["release"], RR["candidate"]
CF = ld("confirm_ftest_fresh.json")
CE = ld("ce_r4.json")  # all items, the registered primary; never-trained families have no flagged item
GP = ld("guard_paired.json")["splits"]
CC = ld("certified_carryover_skopos_int4.json")["model"]["a02"]["L2"]
TEMP = {"skopos": ld("calib_fit_skopos_int4.json")["T"], "ekbasis": ld("calib_fit_ekbasis_int4.json")["T"]}
B = ld("builds.json")
GATE = {b: ld(f"quant_gate_{b}.json") for b in ("fp8", "int4")}
MAC = ld("runs/mlx_mac/mlx_mac_test.json") if has("runs/mlx_mac/mlx_mac_test.json") else None
DATE = os.environ.get("RELEASE_DATE") or "⟨release date⟩"
SWITCH = os.environ.get("SWITCH_DATE") or "⟨switch date⟩"
SWITCH_TIME = os.environ.get("SWITCH_TIME") or "⟨HH:MM⟩"
JEVR = ld("jev_comparison/results.json") if has("jev_comparison/results.json") else None  # added after the release
A7R = has("a7/ce_a7.json")
if A7R:
    _no = {sub: [k for k, x in ld("a7/ce_a7.json")["prediction"][sub].items() if not x["held"]] for sub in ("all_items", "clean")}
    A7_HELD = ("its prediction held in every piece, with and without the flagged items" if not any(_no.values()) else
               "its prediction did not hold in every piece (" + "; ".join(f"{'all items' if k == 'all_items' else 'without the flagged items'}: "
                                                              f"{', '.join(v)}" for k, v in _no.items() if v) + ")")
SAME_DAY = not SWITCH.startswith("⟨") and SWITCH == DATE  # the owner's decision: the hosted switch on the release day
gb = lambda b: h(B[b]["weights_bytes"] / 1e9)
d_fresh = CF["changed"]["r4_minus_release"]
u = CE["groups"]["U_all"]
mlx_ok = bool(MAC and MAC.get("pass"))


def pv(p):
    """A p-value as printed: two significant digits, powers of ten below 0.001."""
    if p >= 0.001:
        return f"{p:.2g}"
    m, e = f"{p:.1e}".split("e")
    return f"{m} × 10" + "".join("⁻⁰¹²³⁴⁵⁶⁷⁸⁹"["-0123456789".index(c)] for c in str(int(e)))


hfa, kfa = GP["guard_held:false_alarms"], GP["guard_known:false_alarms"]
flag_ns = all(GP[k]["mcnemar_p"] >= 0.05 for k in ("guard_known:flagged", "guard_held:flagged"))
against = (
    f"the git guard raises fewer false alarms on the held-out command types, {hfa['skopos']}/{hfa['n']} instead of "
    f"{hfa['ekbasis']}/{hfa['n']} (paired McNemar p = {pv(hfa['mcnemar_p'])}; these command types are held out of the git "
    f"sandbox's training rows but appear in Skopos' factory rows)"
    + (", and flags as many work-losing commands" if flag_ns else "")
    + f"; on the known types, {kfa['skopos']} instead of {kfa['ekbasis']} of {kfa['n']} is "
    + ("within chance" if kfa["mcnemar_p"] >= 0.05 else f"beyond chance (p = {pv(kfa['mcnemar_p'])})")
    + f". On {CF['changed']['n']:,} fresh answers of never-trained world families the actions change, "
    f"{sg(d_fresh[0])} points [{sg(d_fresh[1][0])}, {sg(d_fresh[1][1])}]: the pre-registered release read failed this "
    f"criterion on `ftest_family`, and a confirmation registered after that result (before any fresh item existed), by "
    f"trainer readout, did not confirm the loss. Its largest gains are in-distribution (the generators it was trained "
    f"on)" + (f", and in world families it never saw more of its errors come with confidence ≥ 0.9 "
              f"({h(u['conf_wrong_per100_skopos'], 2)} vs {h(u['conf_wrong_per100_ekbasis'], 2)} per 100)"
              if u["conf_wrong_diff_ci"][0] > 0 else ""))
certified = (f"`ekbasis.verify`'s certified mode, certified on Ekbasis-27B, carried over to Skopos INT4 in a pre-registered "
             f"check ({CC['errors_among_accepted']} errors among {CC['accepted']:,} accepted answers; "
             f"[docs/VERIFY.md](docs/VERIFY.md))")
# The release decision (the owner's record): the pre-launch P8 blocker, declared wherever the results are summarized
blocker = ""
if has("prelaunch/RELEASE_DECISION.md"):
    p8 = next(m for m in ld("prelaunch/compare/P8.json")["measures"] if m["measure"].startswith("para"))
    c8 = ld("prelaunch/compare/P8_context.json")["para_wording_120"]
    s8 = ld("prelaunch/compare/P8_same_machine.json")["ekbasis27b_rerun_identity_vs_published"]
    blocker = (f"A pre-launch release blocker is declared: on paraphrased short checks it is right on {c8['skopos_right']} of "
               f"{p8['n']} against Ekbasis-27B's {c8['ekbasis27b_right']} ({sg(p8['difference'])} points, paired 95% CI "
               f"[{sg(p8['ci95'][0])}, {sg(p8['ci95'][1])}]), so the pre-registered rule fired; the exact test on the "
               f"{c8['discordant']['skopos_only_wrong'] + c8['discordant']['ekbasis27b_only_wrong']} discordant items does "
               f"not reject (p = {h(c8['exact_mcnemar_two_sided_p'], 3)}), and Ekbasis-27B re-run on the same machine "
               f"reproduced its published answers ({s8['same_right_wrong_as_published']}) (DECISION_LINK)")
hosted = (f"Hosted API: as its model-change policy promises, this version and its scorecard are posted at least 14 days "
          f"before the served model changes; the hosted API serves Ekbasis-27B-INT4 until {SWITCH}, then "
          f"Ekbasis-Skopos-27B-INT4 (`calibrated.temperature` {h(TEMP['skopos'], 2)} instead of {h(TEMP['ekbasis'], 2)}); "
          f"the switch gets its own entry here, with its date")
if SAME_DAY:
    hosted = (f"Hosted API: it serves Ekbasis-Skopos-27B-INT4 since {SWITCH}, the release day, with less notice than its "
              f"model-change policy promises (the entry above)")


def runs_on(t, name):
    """Where Ekbasis-27B's build of the same kind runs, read from this README's own table (same architecture and sizes)."""
    m = re.search(r"^\| \[" + re.escape(name) + r"\]\([^)]*\)[^|]*\| [^|]+ \| GPUs with (\d+) GB", t, flags=re.M)
    assert m, name
    return f"GPUs with {m.group(1)} GB"


def wrap(text, width=120):
    """Re-wraps each paragraph (and each list item or block quote) at the width the documents use; tables untouched."""
    out = []
    paras = []
    for para in text.split("\n\n"):  # consecutive list items are wrapped one by one
        lines = para.split("\n")
        if lines[0].startswith("- ") and sum(l.startswith("- ") for l in lines) > 1:
            items = []
            for l in lines:
                (items.append([l]) if l.startswith("- ") or not items else items[-1].append(l))
            paras.append(("\n", ["\n".join(i) for i in items]))
        else:
            paras.append(("", [para]))
    for sep, parts in paras:
        if sep:
            out.append("\n".join(wrap(x, width) for x in parts))
            continue
        para = parts[0]
        lines = para.split("\n")
        heads = []
        while lines and lines[0].startswith("#"):  # headings stay on their own lines
            heads.append(lines.pop(0))
        if heads:
            out.append("\n".join(heads) + ("\n" + wrap("\n".join(lines), width) if lines else ""))
            continue
        if any(l.startswith("|") for l in lines):
            out.append(para)
            continue
        first = lines[0]
        lead = "> " if first.startswith("> ") else ("- " if first.startswith("- ") else "")
        rest = "> " if lead == "> " else ("  " if lead == "- " else "")
        body = " ".join(l[len(lead if i == 0 else rest):] if l.startswith(lead if i == 0 else rest) else l
                        for i, l in enumerate(lines)).strip()
        if first.startswith(("#", "**Ekbasis-27B**")) and len(lines) == 1:
            out.append(first)
            continue
        out.append(textwrap.fill(body, width, initial_indent=lead, subsequent_indent=rest, break_on_hyphens=False,
                                 break_long_words=False))
    return "\n\n".join(out)


T_README = open(os.path.join(ROOT, "README.md")).read()
gate_row = lambda b: (f"quantization gate passed: same answer as bf16 on {h(GATE[b]['values_bf16_build']['agreement'])}%"
                      if GATE[b]["pass"] else "quantization gate missed (its card)")
BLOCKS = {
    "README.md": {
        "intro": (r"\[paper/prereg/\]\(https://github\.com/OpenInterpretability/ekbasis/tree/main/paper/prereg/\)\) and the deviations\.\n",
                  f"""
> **New ({DATE}): [Ekbasis-Skopos-27B]({HF}/Ekbasis-Skopos-27B)**, the next version, trained further on executed shell,
> git, SQLite, PostgreSQL and Python scenarios. Against Ekbasis-27B on the same items: {against}. Same prompt, readout,
> API and client; its evaluation is in [RELEASE_EVAL_SKOPOS.md]({GH}/RELEASE_EVAL_SKOPOS.md) and its card. The numbers
> further down this page are Ekbasis-27B's. {certified.replace("(docs/VERIFY.md)", f"({GH}/docs/VERIFY.md)")}.{(" " + blocker.replace("DECISION_LINK", f"[release decision]({GH}/results_skopos/prelaunch/RELEASE_DECISION.md)") + ".") if blocker else ""}
"""),
        "builds": (r"^## Builds\n",
                   f"""
**Ekbasis-Skopos-27B** (recommended): each build's card shows its quality against bf16 on the same evaluation (the gate
of `PREREG_quantized.md`) and ships its own `calibrated_temperature`. Memory needs are those measured for Ekbasis-27B's
builds, which have the same architecture and sizes.

| Build | Size | Runs on | Against bf16 |
|---|---|---|---|
| [Ekbasis-Skopos-27B]({HF}/Ekbasis-Skopos-27B) (bf16) | {gb('bf16')} GB | {runs_on(T_README, 'Ekbasis-27B')} | the reference |
| [Ekbasis-Skopos-27B-FP8]({HF}/Ekbasis-Skopos-27B-FP8) | {gb('fp8')} GB | {runs_on(T_README, 'Ekbasis-27B-FP8')} | {gate_row('fp8')} |
| [Ekbasis-Skopos-27B-INT4]({HF}/Ekbasis-Skopos-27B-INT4) | {gb('int4')} GB | {runs_on(T_README, 'Ekbasis-27B-INT4')} | {gate_row('int4')} |
{f"| [Ekbasis-Skopos-27B-MLX-4bit]({HF}/Ekbasis-Skopos-27B-MLX-4bit) | {gb('mlx')} GB | Macs with Apple Silicon | passed its test on an Apple-silicon Mac (its card) |" if mlx_ok else ""}

**Ekbasis-27B** (the previous version): every build that works is released, so each machine runs the one that fits;
each build's card shows its quality against bf16 on the same evaluation (the gate was pre-registered in
`PREREG_quantized.md`).
"""),
        "training": (r"\[ekbasis-data\]\(https://huggingface\.co/datasets/caiovicentino1/ekbasis-data\)\.\n",
                     """
Ekbasis-Skopos-27B's two further stages, its interpolation, merges and quantized builds are in
[`training/skopos/`](training/skopos/README.md); the programs that computed the answers of every training row and
evaluation set of its lineage, as they ran, in [`generators/`](generators/README.md); the rows in
[ekbasis-skopos-data](https://huggingface.co/datasets/caiovicentino1/ekbasis-skopos-data).
"""),
    },
    "MODEL_CARD.md": {
        "intro": (r"\*\*Site:\*\* \[openinterp\.org/ekbasis\]\(https://openinterp\.org/ekbasis\)\n",
                  f"""
> **A newer version is recommended: [Ekbasis-Skopos-27B]({HF}/Ekbasis-Skopos-27B)**, the same kind of model trained
> further on what real tools did, with the same API and client ([RELEASE_EVAL_SKOPOS.md]({GH}/RELEASE_EVAL_SKOPOS.md)).
> This card describes Ekbasis-27B as it was released; its weights and builds stay available.
"""),
    },
    "CHANGELOG.md": {
        "entry": (r"^# Changelog\n",
                  f"""
## {"[Unreleased] — Ekbasis-Skopos-27B (model)" if DATE.startswith("⟨") else f"Ekbasis-Skopos-27B (model) — {DATE}"}

### Added
- **Ekbasis-Skopos-27B, the recommended model** ([card]({HF}/Ekbasis-Skopos-27B); bf16, FP8 and INT4 builds{", MLX" if mlx_ok else "; MLX after its test on an Apple-silicon Mac"}):
  Ekbasis-27B trained further on executed shell, git, SQLite, PostgreSQL and Python scenarios. Against Ekbasis-27B on
  the same items: {against}. The client, the API and the prompts are unchanged: serve the new weights with their own
  `serve.py`, or keep Ekbasis-27B. {certified}. {blocker.replace("DECISION_LINK", "[release decision](results_skopos/prelaunch/RELEASE_DECISION.md)") + ". " if blocker else ""}{hosted}. Its evaluation, with its per-item predictions and pre-registrations:
  [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md), [results_skopos/](results_skopos/README.md),
  [prereg_skopos/](prereg_skopos/PREREG_sha256.txt); its training code: [training/skopos/](training/skopos/README.md);
  the generators behind every training kind and evaluation set, as they ran: [generators/](generators/README.md).
"""),
        **({"results": (r"^# Changelog\n", f"""
## Results — {JEVR['meta']['measured']}

### Added
- **Jev against Ekbasis-27B and Ekbasis-Skopos-27B** (not pre-registered, measured {JEVR['meta']['measured']}): TypeSafe AI's
  general-purpose evaluator, zero-shot, on the release protocol and the hosted scorecard's suites, next to the published
  per-item predictions; with every per-item answer and a script that reproduces the numbers
  ([results_skopos/jev_comparison/](results_skopos/jev_comparison/METHOD.md), a section of
  [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md)).
""" + (f"""- **Addendum A7** (registered before any A7 request): confident errors with every option's probability on the {ld('ce_r4.json')['n']:,}
  items, Ekbasis-Skopos-27B INT4 against Ekbasis-27B INT4, raw and at each build's calibrated temperature; {A7_HELD}; the bf16 part
  was not run ([results_skopos/a7/](results_skopos/a7/ce_a7.json), a section of
  [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md)).
""" if A7R else ""))} if JEVR else {}),
        **({"switch": (r"^# Changelog\n", f"""
## Hosted API — {SWITCH}

### Changed
- Served model changed: the hosted API serves `ekbasis-skopos-27b-int4-v1.3` since {SWITCH} {SWITCH_TIME} UTC — on
  release day, with less notice than the 14 days the model-change policy promises (owner decision,
  [results_skopos/prelaunch/RELEASE_DECISION.md](results_skopos/prelaunch/RELEASE_DECISION.md)); Ekbasis-27B's weights
  stay public. The prompt, readout, API, fields and client are the same; `calibrated.temperature` is
  {h(TEMP['skopos'], 2)} instead of {h(TEMP['ekbasis'], 2)}.
""")} if SAME_DAY else {}),
    },
}

# Ekbasis-27B's builds paragraph now closes the builds block ("the previous version"); the quick start serves the
# recommended model, and says the previous version is served the same way.
BUILDS_OLD = ("Every build that works is released, so each machine runs the one that fits; each build's card shows its quality\n"
              "against bf16 on the same evaluation (the gate was pre-registered in `PREREG_quantized.md`).\n\n")
QS = ["   hf download caiovicentino1/{0} --local-dir {0}{1}\n",
      "   bash {0}/serve_vllm.sh {0} 8001             # vLLM on 127.0.0.1:8001\n",
      "   python {0}/serve.py --model {0} --vllm-url http://127.0.0.1:8001 --port 8000\n", "   ```\n"]
qs = lambda name, note="": "".join(QS).format(name, note)
QS_NEW = qs("Ekbasis-Skopos-27B") + "\n   The previous version, `caiovicentino1/Ekbasis-27B`, is served the same way.\n"

for fname, blocks in BLOCKS.items():
    path = os.path.join(ROOT, fname)
    t = open(path).read()
    if fname == "README.md":
        t = t.replace(BUILDS_OLD, "")
        for old in (qs("Ekbasis-27B"), qs("Ekbasis-Skopos-27B", "   # or Ekbasis-27B, the same way")):
            if old in t and QS_NEW not in t:
                t = t.replace(old, QS_NEW)
        assert QS_NEW in t and BUILDS_OLD not in t, "README quick start / builds"
    for name, (anchor, body) in blocks.items():
        start, end = f"<!-- skopos:{name} -->", f"<!-- /skopos:{name} -->"
        block = f"{start}\n{wrap(body.strip())}\n\n{end}\n"
        if start in t:
            t = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n", lambda m: block, t, flags=re.S)
        else:
            m = list(re.finditer(anchor, t, flags=re.M))
            assert len(m) == 1, (fname, name, len(m))
            t = t[:m[0].end()] + "\n" + block + t[m[0].end():]
    open(path, "w").write(t)
    print(f"{fname}: {', '.join(blocks)}")

# The dates outside the blocks (docs/VERIFY.md's Skopos section, and any other document that carries them), once set.
# The pre-registrations and results are never touched.
DOCS = ["README.md", "CHANGELOG.md", "MODEL_CARD.md", "scorecard/README.md"] + \
       sorted(os.path.join("docs", f) for f in os.listdir(os.path.join(ROOT, "docs")) if f.endswith(".md"))
for rel in DOCS:
    p = os.path.join(ROOT, rel)
    text = open(p).read()
    new = text
    if not DATE.startswith("⟨"):
        new = new.replace("⟨release date⟩", DATE)
    if not SWITCH.startswith("⟨"):
        new = new.replace("⟨switch date⟩", SWITCH)
    if not SWITCH_TIME.startswith("⟨"):
        new = new.replace("⟨HH:MM⟩", SWITCH_TIME)
    if new != text:
        open(p, "w").write(new)
        print(f"{rel}: dates")
