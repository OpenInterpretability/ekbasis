"""Every number in the paper's text and tables must come from numbers.json (as printed, at its precision) or be a design
constant listed below. Prints each number that does not, with its line, so it can be fixed or justified.
usage: python3 check_numbers.py [look_when_unsure.tex]"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEX = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "look_when_unsure.tex"
N = json.load(open(HERE / "numbers.json"))

# design constants: thresholds, gaps, lengths, counts fixed by the plans, the model size, years, and the like
DESIGN = {"0.2", "0.5", "0.9", "0.99", "0.9--0.99", "8", "64", "100", "200", "27", "27B", "1", "2", "3", "4", "5", "6", "7",
          "10", "12", "15", "16", "20", "30", "40", "50", "80", "120", "160", "240", "300", "2,000", "1.00",
          "2026", "2025", "2024", "2023", "2022", "2017", "2015", "2011", "1960", "3--10", "2--3", "4--7", "3--4", "1--3",
          "3--5", "1--3", "0", "8--64", "256"}


def flatten(x, out):
    if isinstance(x, dict):
        for k, v in x.items():
            flatten(k, out)  # keys too: some carry a value, as "conf >= 0.608"
            flatten(v, out)
    elif isinstance(x, list):
        for v in x:
            flatten(v, out)
    elif isinstance(x, bool):
        pass
    elif isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, str):
        for m in re.findall(r"-?\d+(?:\.\d+)?", x):
            out.append(float(m))
    return out


vals = flatten(N, [])
forms = set()
for v in vals:
    for scale in (1, 100):
        w = v * scale
        for d in (0, 1, 2, 3, 4):
            forms.add(f"{abs(w):.{d}f}")
        if float(w).is_integer():
            forms.add(f"{int(abs(w)):,}")


def body(tex):
    if TEX.suffix == ".md":  # the site summary: plain text; skip code spans
        tex = re.sub(r"\b10\.\d{4,9}/\S+|\(/papers/[^)]*\)|\b\d{4}-\d{2}-\d{2}\b", " ", tex)  # DOIs, links, dates
        return re.sub(r"`[^`]*`", " ", tex)
    s = tex.split("\\begin{document}", 1)[1]
    s = s.split("\\begin{thebibliography}", 1)[0]
    s = s.split("\\section{Pre-registrations}", 1)[0]  # the appendix: plan names, hashes and times
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = re.sub(r"\b10\.\d{4,9}/\S+", " ", s)  # DOIs (the paper's own, on the title page)
    s = re.sub(r"\\(ref|label|cite|includegraphics|url|href|texttt|section|subsection)\*?(\[[^]]*\])?\{[^}]*\}", " ", s)
    s = re.sub(r"\\begin\{(tabular|tikzpicture)\}\{[^}]*\}", " ", s)
    s = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", " ", s, flags=re.S)
    s = re.sub(r"\\(resizebox|multirow)\{[^}]*\}\{[^}]*\}", " ", s)
    s = re.sub(r"p\{[\d.]+cm\}|width=[\d.]+\\textwidth|\[[\d.]+pt\]|[\d.]+cm", " ", s)
    s = re.sub(r"\\(alpha|beta|gamma|tau|leftarrow|ge|le|to|times|textasciitilde)\b", " ", s)
    return s


unmatched = []
for ln, line in enumerate(body(TEX.read_text()).splitlines(), 1):
    for m in re.finditer(r"(?<![\w.$])-?\d[\d,]*(?:\.\d+)?(?:--\d[\d,]*(?:\.\d+)?)?(?![\w])", line):
        tok = m.group(0).strip("-").rstrip(",")
        if not tok or tok in DESIGN:
            continue
        parts = tok.split("--")
        if all(p.replace(",", "") in forms or p in forms for p in parts):
            continue
        unmatched.append((tok, line.strip()[:110]))
seen = set()
for tok, ctx in unmatched:
    if (tok, ctx) in seen:
        continue
    seen.add((tok, ctx))
    print(f"{tok:>12}  | {ctx}")
print(f"{len(seen)} numbers not found in numbers.json (review each: a derived value to add, a constant, or an error)")
