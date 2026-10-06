"""Every number the paper cites must be present in numbers.json (written by reproduce.py). Reads the LaTeX source (or a
Markdown summary with --md); exits with the number of misses.

    python3 check_numbers.py agents.tex
    python3 check_numbers.py --md summary.md

Checked: fractions k/n (also "k of n"), decimals, percentages and integers >= 13. Skipped: the preamble and the
bibliography, LaTeX commands and their non-text arguments, model and version names, years, DOIs, arXiv IDs and ORCIDs,
the 95% intervals and 10,000 resamples, the thresholds 0.5 and 0.9, the pre-registered 50% bar, the 8,192-token cap and
integers below 13 (counts of conditions, runs per task, apps), software versions and dates."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MINUS = "\u2212"
SKIP = [
    r"Sonnet 5\.5", r"Haiku 4\.5", r"GLM-5\.3-flash", r"GLM-5\.3-Flash", r"Qwen ?3\.5(?:[ -](?:4B|9B))?", r"\b(?:4B|9B|27B|35B)\b",
    r"Qwen-AgentWorld-35B-A3B", r"\b\d+B(?:-A\d+B)?\b", r"Ekbasis-27B", r"Eikos-27B", r"w4a5", r"\bV4\d\w*", r"\br4a\b",
    r"\b\d+\.\d+\.\d+\b", r"serve\.py 1\.3", r"pass\^?1", r"\bp90\b", r"\b20\d\d\b", r"95\s?%", r"10[,.]000", r"\bseed \d\b",
    r"10\.\d{4,9}/[^\s},]+", r"zenodo\.\w+", r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", r"arXiv:\s?\d{4}\.\d{4,5}", r"\b\d{4}\.\d{4,5}\b",
    r"≥ ?0[.,]9", r"\b0[.,]9\b", r"\b0[.,]5\b", r"≥ ?50%", r"\b50%(?= relative)", r"8,192", r"8192", r"\b8-gram\b",
    r"MAX_THINKING_TOKENS=0", r"`[^`]*`", r"\b[A-Z]\d\b", r"\bτ²", r"\bUTC[−+-]\d\b", r"\b[0-9a-f]{8}\b",
    r"\b\d{1,2}:\d{2}(?::\d{2})?\b", r"\b20\d\d-\d\d-\d\d\b", r"\d+\s*(?:--|–)\s*\d+ October", r"SHA-256",
    r"\b(?:Roundcube|Postfix|Dovecot|Playwright|docker-mailserver)\s+\d+(?:\.\d+)?", r"\b\d{1,2} October\b",
]


def latex_to_text(s):
    s = s.split("\\begin{document}", 1)[-1]
    s = s.split("\\begin{thebibliography}", 1)[0]
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = re.sub(r"\\(label|ref|eqref|cite|citep|citet|url|includegraphics|input|vspace|hspace|bibitem)\*?(\[[^\]]*\])?\{[^}]*\}", " ", s)
    s = re.sub(r"\\href\{[^}]*\}", " ", s)
    s = re.sub(r"\\begin\{(tabular|tabularx|longtable)\}(\{[^}]*\})+", " ", s)
    s = re.sub(r"\\\\\[[^\]]*\]", " ", s)
    s = re.sub(r"\\(setlength|addtolength)\{[^}]*\}\{[^}]*\}", " ", s)
    s = re.sub(r"\[(?:width|height|scale|keepaspectratio)[^\]]*\]", " ", s)
    s = re.sub(r"\b[pmb]\{\d+(\.\d+)?(cm|mm|in|pt|em)\}", " ", s)
    s = re.sub(r"\d+(\.\d+)?\\(linewidth|textwidth|columnwidth)", " ", s)
    s = re.sub(r"\d+(\.\d+)?(pt|cm|mm|em|ex)\b", " ", s)
    s = s.replace("\\%", "%").replace("{,}", ",").replace("\\,", " ").replace("~", " ").replace("--", "–")
    s = re.sub(r"\$\s*-\s*", MINUS, s)
    s = re.sub(r"(?<=[\s(\[])-(?=\d)", MINUS, s)
    s = s.replace("$", " ")
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
    return s.replace("{", " ").replace("}", " ")


def allowed(N):
    vals, fracs = set(), set()

    def add(x):
        try:
            v = float(x)
        except (TypeError, ValueError):
            return
        for d in range(5):
            for w in (v, abs(v), 100 * v, abs(100 * v)):
                vals.add(round(w, d))

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, bool) or o is None:
            return
        elif isinstance(o, (int, float)):
            add(o)
        elif isinstance(o, str):
            t = o.replace(MINUS, "-")
            for k, n in re.findall(r"(\d+)/(\d+)", t):
                fracs.add(f"{k}/{n}")
                add(k)
                add(n)
                if int(n):
                    add(int(k) / int(n))
            for x in re.findall(r"-?\d+(?:\.\d+)?", t):
                add(x)
    walk(N)
    return vals, fracs


def tokens(t):
    t = t.replace(MINUS, "-")
    t = re.sub(r"(?m)^#+ ?\d+(?:\.\d+)*", " ", t)
    for p in SKIP:
        t = re.sub(p, " ", t)
    found = [("frac", f"{a}/{b}", m) for a, b, m in ((x.group(1), x.group(2), x.group(0)) for x in re.finditer(r"(\d+) of (\d+)", t))]
    t = re.sub(r"(\d+) of (\d+)", " ", t)
    for x in re.finditer(r"(?<![\w.])(\d+)/(\d+)(?![\w/])", t):
        found.append(("frac", f"{x.group(1)}/{x.group(2)}", x.group(0)))
    t = re.sub(r"(?<![\w.])(\d+)/(\d+)(?![\w/])", " ", t)
    for x in re.finditer(r"(?<![\w.^])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.^])[-+]?\d+(?:\.\d+)?", t):
        raw = x.group(0)
        s = raw.replace(",", "") if re.search(r"\d,\d{3}", raw) else raw
        v = float(s)
        if abs(v) < 13 and v.is_integer() and "." not in s:
            continue
        found.append(("num", v, raw))
    return found


def main(argv):
    md = "--md" in argv
    args = [a for a in argv if a != "--md"]
    path = args[0] if args else "agents.tex"
    text = open(os.path.join(HERE, path) if not os.path.isabs(path) else path).read()
    text = text if md else latex_to_text(text)
    vals, fracs = allowed(json.load(open(os.path.join(HERE, "numbers.json"))))
    misses = []
    for kind, v, raw in tokens(text):
        if kind == "frac":
            if v not in fracs:
                misses.append(raw)
        else:
            d = len(str(v).split(".")[1]) if "." in str(v) else 0
            if round(v, d) not in vals and round(abs(v), d) not in vals:
                misses.append(raw)
    for m in misses:
        print("NOT IN numbers.json:", m)
    print(json.dumps({"checked": path, "misses": len(misses)}))
    return len(misses)


if __name__ == "__main__":
    sys.exit(min(main(sys.argv[1:]), 255))
