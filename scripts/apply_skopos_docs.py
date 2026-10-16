#!/usr/bin/env python3
"""Introduces Ekbasis-Skopos-27B in README.md, MODEL_CARD.md and CHANGELOG.md as the recommended model, with every
number read from results_skopos/ (Ekbasis-27B stays documented: its sections are not changed). Each insert sits between
<!-- skopos:<name> --> markers, so the script can be run again when the results are final. The wording of the README's
blocks is that of the client-docs patch for this release; the release date is RELEASE_DATE (YYYY-MM-DD), left as a
placeholder that tools/release_github.sh refuses to publish until it is set.

  RELEASE_DATE=2026-10-16 python scripts/apply_skopos_docs.py
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
CEC = ld("overlap_audit/clean/ce_r4_clean.json")  # never-trained families: no item flagged, the same as ce_r4.json
CC = ld("certified_carryover_skopos_int4.json")["model"]["a02"]["L2"]
B = ld("builds.json")
GATE = {b: ld(f"quant_gate_{b}.json") for b in ("fp8", "int4")}
MAC = ld("runs/mlx_mac/mlx_mac_test.json") if has("runs/mlx_mac/mlx_mac_test.json") else None
DATE = os.environ.get("RELEASE_DATE") or "⟨release date⟩"
gb = lambda b: h(B[b]["weights_bytes"] / 1e9)
d_fresh = CF["changed"]["r4_minus_release"]
u = CEC["groups"]["U_all"]
mlx_ok = bool(MAC and MAC.get("pass"))

against = (
    f"false alarms of the git guard {SK['guard_held'][2]}/{SK['guard_held'][3]} instead of "
    f"{REL['guard_held'][2]}/{REL['guard_held'][3]} on the held-out command types (held out of the git sandbox's training "
    f"rows), and {SK['guard_known'][2]} instead of {REL['guard_known'][2]} of {SK['guard_known'][3]} on known types; "
    f"never-trained world families {sg(d_fresh[0])} points [{sg(d_fresh[1][0])}, {sg(d_fresh[1][1])}] on "
    f"{CF['changed']['n']:,} fresh answers the actions change. Its largest gains are in-distribution (the generators it "
    f"was trained on)" + (f", and in world families it never saw more of its errors come with confidence ≥ 0.9 "
                          f"({h(u['conf_wrong_per100_skopos'], 2)} vs {h(u['conf_wrong_per100_ekbasis'], 2)} per 100)"
                          if u["conf_wrong_diff_ci"][0] > 0 else ""))
certified = (f"`ekbasis.verify`'s certified mode, certified on Ekbasis-27B, carried over to Skopos INT4 in a pre-registered "
             f"check ({CC['errors_among_accepted']} errors among {CC['accepted']:,} accepted answers; "
             f"[docs/VERIFY.md](docs/VERIFY.md))")


def runs_on(t, name):
    """Where Ekbasis-27B's build of the same kind runs, read from this README's own table (same architecture and sizes)."""
    m = re.search(r"^\| \[" + re.escape(name) + r"\]\([^)]*\)[^|]*\| [^|]+ \| GPUs with (\d+) GB", t, flags=re.M)
    assert m, name
    return f"GPUs with {m.group(1)} GB"


def wrap(text, width=120):
    """Re-wraps each paragraph (and each list item or block quote) at the width the documents use; tables untouched."""
    out = []
    for para in text.split("\n\n"):
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
> further down this page are Ekbasis-27B's. {certified.replace("(docs/VERIFY.md)", f"({GH}/docs/VERIFY.md)")}.
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
  `serve.py`, or keep Ekbasis-27B. {certified}. Its evaluation, with every prediction and pre-registration:
  [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md), [results_skopos/](results_skopos/README.md),
  [prereg_skopos/](prereg_skopos/PREREG_sha256.txt); its training code: [training/skopos/](training/skopos/README.md);
  the generators behind every training kind and evaluation set, as they ran: [generators/](generators/README.md).
"""),
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

if not DATE.startswith("⟨"):  # docs/VERIFY.md's Skopos section carries the date too
    p = os.path.join(ROOT, "docs", "VERIFY.md")
    text = open(p).read()
    open(p, "w").write(text.replace("⟨release date⟩", DATE))
