"""Estimated input tokens Ekbasis bills per check on every set of the full-set extension (no request sent): the System
One prompt as decision_core.py builds it (semif: system line + JSON {evidence, criterion, options}; a yes/no question's
options are "true: <criteria.true or yes>" and "false: <criteria.false or no>") in the Qwen chat format, counted with the
Eikos-4B tokenizer (same Qwen tokenizer family as Ekbasis-27B, whose own tokenizer file is not on this disk).
python3 ekbasis_tokens_full.py   (needs the `tokenizers` package; writes ekbasis_tokens_full.json)"""
import json, os, statistics
from pathlib import Path
from tokenizers import Tokenizer

HERE = Path(__file__).parent
tok = Tokenizer.from_file(os.environ["EIKOS4B_TOKENIZER"])
SYSTEM = ("Apply the supplied criterion to the supplied evidence. Choose exactly one listed option. "
          "Respond with only its uppercase letter, with no explanation or reasoning.")
LABELS = [chr(ord("A") + i) for i in range(26)]


def user(state, q):
    crit = q.get("criteria") or {}
    if q["type"] == "noul":
        opts, shown = [("yes", crit.get("true") or "yes"), ("no", crit.get("false") or "no")], {"yes": "true", "no": "false"}
    else:
        opts, shown = [(k, k if v is None else str(v)) for k, v in crit.items()], {}
    return json.dumps({"evidence": state, "criterion": q["instructions"],
                       "options": [{"letter": LABELS[i], "description": f"{shown.get(l, l)}: {d}"} for i, (l, d) in enumerate(opts)]},
                      ensure_ascii=False)


items = {json.loads(l)["key"]: json.loads(l) for l in open(HERE / "pool_items.jsonl")}
n = {k: len(tok.encode(f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user(r['state'], r['ekbasis_question'])}<|im_end|>\n<|im_start|>assistant\n").ids)
     for k, r in items.items()}
sets = json.load(open(HERE / "sets_full.json"))
out = {s: {"mean": statistics.mean(n[k] for k in keys), "median": statistics.median(n[k] for k in keys)} for s, keys in sets.items()}
print(json.dumps(out, indent=1))
json.dump(out, open(HERE / "ekbasis_tokens_full.json", "w"), indent=1)
