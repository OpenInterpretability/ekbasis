#!/usr/bin/env python3
"""Introduces Ekbasis-Skopos-27B in README.md, MODEL_CARD.md and CHANGELOG.md as the recommended model, with every
number read from results_skopos/ (Ekbasis-27B stays documented: its sections are not changed). Each insert sits between
<!-- skopos:<name> --> markers, so the script can be run again when the results are final.

  python scripts/apply_skopos_docs.py
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
H2H = ld("r4_vs_skopos_v49f.json")
CE = ld("ce_r4.json") if has("ce_r4.json") else None
B = ld("builds.json")
MAC = ld("runs/mlx_mac/mlx_mac_test.json") if has("runs/mlx_mac/mlx_mac_test.json") else None
pct = lambda g: 100 * g[0] / g[1]
gb = lambda b: h(B[b]["weights_bytes"] / 1e9)
d_fresh = CF["changed"]["r4_minus_release"]
u = CE["groups"]["U_all"] if CE else None

headline = (
    f"the git guard, served, raises fewer false alarms on the guard set's held-out command types (held out of the git "
    f"sandbox's training rows; {SK['guard_held'][2]} of "
    f"{SK['guard_held'][3]} instead of {REL['guard_held'][2]}) and catches more lost work ({h(pct(SK['guard_held']))}% instead "
    f"of {h(pct(REL['guard_held']))}%); on {CF['all']['n']:,} fresh items of world families it never saw, "
    f"{sg(d_fresh[0], 2)} points on the answers the actions change (95% CI {sg(d_fresh[1][0], 2)} to {sg(d_fresh[1][1], 2)}); "
    f"executed shell, SQL, Python and git scenarios {h(100 * H2H['fac_val']['r2'])}% instead of "
    f"{h(100 * H2H['fac_val']['base'])}%, real git sequences of 5–12 commands {h(100 * H2H['git_long']['r2'])}% instead of "
    f"{h(100 * H2H['git_long']['base'])}% (these two are in-distribution sets, on which the candidates were selected)")
limit = (f" In world families it never saw, more of its wrong answers come with high confidence ({sg(u['conf_wrong_diff'], 2)} "
         f"per 100 answers)." if u and u["conf_wrong_diff_ci"][0] > 0 else "")
mlx_ok = bool(MAC and MAC.get("pass"))

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


BLOCKS = {
    "README.md": {
        "intro": (r"\[paper/prereg/\]\(https://github\.com/OpenInterpretability/ekbasis/tree/main/paper/prereg/\)\) and the deviations\.\n",
                  f"""
> **Ekbasis-Skopos-27B is the recommended model** ([card]({HF}/Ekbasis-Skopos-27B),
> [RELEASE_EVAL_SKOPOS.md]({GH}/RELEASE_EVAL_SKOPOS.md)): Ekbasis-27B trained further on what real tools did, with the
> same prompt, readout, API and client. Against Ekbasis-27B, on the same items: {headline}.{limit}
> Ekbasis-27B and its builds stay available; the measurements on this page are Ekbasis-27B's unless a section says
> otherwise.
"""),
        "builds": (r"the gate was pre-registered in `PREREG_quantized\.md`\)\.\n",
                   f"""
**Ekbasis-Skopos-27B** (recommended): the same architecture and size as Ekbasis-27B, so each build runs where Ekbasis-27B's
build of the same kind runs; each build's quality against its bf16 and against Ekbasis-27B is in
[RELEASE_EVAL_SKOPOS.md]({GH}/RELEASE_EVAL_SKOPOS.md).

| Build | Size |
|---|---|
| [Ekbasis-Skopos-27B]({HF}/Ekbasis-Skopos-27B) (bf16) | {gb('bf16')} GB |
| [Ekbasis-Skopos-27B-FP8]({HF}/Ekbasis-Skopos-27B-FP8) | {gb('fp8')} GB |
| [Ekbasis-Skopos-27B-INT4]({HF}/Ekbasis-Skopos-27B-INT4) | {gb('int4')} GB |
{f"| [Ekbasis-Skopos-27B-MLX-4bit]({HF}/Ekbasis-Skopos-27B-MLX-4bit) | {gb('mlx')} GB |" if mlx_ok else "| Ekbasis-Skopos-27B-MLX-4bit | released after its test on an Apple-silicon Mac |"}

**Ekbasis-27B**:
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
## [Unreleased] — Ekbasis-Skopos-27B (model)

### Added
- **Ekbasis-Skopos-27B, the recommended model** ([card]({HF}/Ekbasis-Skopos-27B); bf16, FP8 and INT4 builds{", MLX" if mlx_ok else "; MLX after its test on an Apple-silicon Mac"}):
  Ekbasis-27B trained further on what real tools did. Against Ekbasis-27B, on the same items: {headline}.{limit}
  The client, the API and the prompts are unchanged: serve the new weights with their own `serve.py`, or keep
  Ekbasis-27B. Its evaluation, with every prediction and pre-registration: [RELEASE_EVAL_SKOPOS.md](RELEASE_EVAL_SKOPOS.md),
  [results_skopos/](results_skopos/README.md), [prereg_skopos/](prereg_skopos/PREREG_sha256.txt); its training code:
  [training/skopos/](training/skopos/README.md); the generators behind every training kind and evaluation set, as
  they ran: [generators/](generators/README.md).
"""),
    },
}

for fname, blocks in BLOCKS.items():
    path = os.path.join(ROOT, fname)
    t = open(path).read()
    for name, (anchor, body) in blocks.items():
        start, end = f"<!-- skopos:{name} -->", f"<!-- /skopos:{name} -->"
        block = f"{start}\n{wrap(body.strip())}\n\n{end}\n"
        if start in t:
            t = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n", lambda m: block, t, flags=re.S)
        else:
            m = list(re.finditer(anchor, t, flags=re.M))
            assert len(m) == 1, (fname, name, len(m))
            t = t[:m[0].end()] + "\n" + block + t[m[0].end():]
    if fname == "README.md":  # the quick start serves the recommended model; Ekbasis-27B is the same commands with its name
        old = ("   hf download caiovicentino1/Ekbasis-27B --local-dir Ekbasis-27B\n"
               "   bash Ekbasis-27B/serve_vllm.sh Ekbasis-27B 8001             # vLLM on 127.0.0.1:8001\n"
               "   python Ekbasis-27B/serve.py --model Ekbasis-27B --vllm-url http://127.0.0.1:8001 --port 8000\n")
        new = ("   hf download caiovicentino1/Ekbasis-Skopos-27B --local-dir Ekbasis-Skopos-27B   # or Ekbasis-27B, the same way\n"
               "   bash Ekbasis-Skopos-27B/serve_vllm.sh Ekbasis-Skopos-27B 8001             # vLLM on 127.0.0.1:8001\n"
               "   python Ekbasis-Skopos-27B/serve.py --model Ekbasis-Skopos-27B --vllm-url http://127.0.0.1:8001 --port 8000\n")
        if old in t:
            t = t.replace(old, new)
        assert new in t, "README quick start"
    open(path, "w").write(t)
    print(f"{fname}: {', '.join(blocks)}")
