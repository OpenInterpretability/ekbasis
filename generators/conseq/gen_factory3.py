"""Factory 3 data. ftrain4 = factory 1 (ftrain.jsonl) + factory-3 worlds at 15% of the forecasting items; ftrain5 = the
same at 30%. Tests: m3test_held (factory-3 worlds whose actions use a held scope x effect pair), m3test_known (new
factory-3 worlds without them), ftest_family2 (the three FRESH hand-made families). argv: data dir."""
import json, random, sys
from pathlib import Path
from worldgen import fbalanced
from worldgen3 import FRESH, m3balanced

D = Path(sys.argv[1])


def write(name, rows):
    with open(D / f"{name}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(name, len(rows))


rng = random.Random(51)
fl = [dict(ex, kind="floor") for s in (1, 2, 3) for ex in m3balanced(s, 6867, rng, "exclude")]
rd = [dict(ex, kind="read") for s in (1, 2, 3) for ex in m3balanced(s, 1134, rng, "exclude")]
random.Random(52).shuffle(fl)
random.Random(53).shuffle(rd)
base = [json.loads(l) for l in open(D / "ftrain.jsonl")]
for name, nf, nr in (("ftrain4", 8600, 1400), ("ftrain5", 20600, 3400)):
    rows = base + fl[:nf] + rd[:nr]
    random.Random(54).shuffle(rows)
    write(name, rows)
rng = random.Random(55)
write("m3test_held", [ex for s in (1, 2, 3) for ex in m3balanced(s, 300, rng, "require")])
write("m3test_known", [ex for s in (1, 2, 3) for ex in m3balanced(s, 300, rng, "exclude")])
rng = random.Random(56)
write("ftest_family2", [ex for fam in FRESH for s in (1, 2, 3) for q in fam.QTYPES for ex in fbalanced(fam, s, q, rng, 40)])
