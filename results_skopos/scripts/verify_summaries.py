"""Recomputes the summaries in results_skopos/ from the per-item files in results_skopos/runs/, with the scripts that
computed them (unchanged; compare_release.py and quant_gate.py read their item files from a constant, FAC, which is
pointed at your copy of the dataset in a temporary copy of the script), and compares each with the published file
(floats to 1e-9). Written for publication; it trains nothing and asks no model.
    python3 verify_summaries.py <dir with the dataset's raw/ files> [--awb <awb_neutral.jsonl rebuilt>]
The raw files read: git3_test_known, git3_test_held, multi_test_testfam, multi_test_trainfam, ftest_family,
gold0_ftest_family, guard_known, guard_held, ftest_fresh (ekbasis-skopos-data, raw/). The neutral suite's analysis
clusters by trajectory, and the rows the dataset withholds are withheld from runs/neutral_items.jsonl too: it is
recomputed only with the full suite, rebuilt from Qwen/AgentWorldBench by generators/v50/build_awb_neutral.py (--awb);
the other analyses read only each row's label, which the per-item predictions carry."""
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAW = Path(sys.argv[1]).resolve()
AWB = Path(sys.argv[sys.argv.index("--awb") + 1]).resolve() if "--awb" in sys.argv else None
HERE = Path(__file__).resolve().parent
RES = HERE.parent
W = Path(tempfile.mkdtemp(prefix="skopos_verify_"))
PY = sys.executable


def close(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        return [f"{path}: keys differ"] if a.keys() != b.keys() else [m for k in a for m in close(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, list) and isinstance(b, list):
        return [f"{path}: lengths differ"] if len(a) != len(b) else [m for i, (x, y) in enumerate(zip(a, b)) for m in close(x, y, f"{path}[{i}]")]
    if isinstance(a, float) or isinstance(b, float):
        ok = a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
        return [] if ok else [f"{path}: {a} vs {b}"]
    return [] if a == b else [f"{path}: {a} vs {b}"]


def with_fac(script):
    """A temporary copy of script whose FAC constant points at RAW (the only line that differs)."""
    t = (HERE / script).read_text()
    old = 'FAC = "/dev/shm/conseq/fac"'
    assert t.count(old) == 1, script
    p = W / f"_{script}"
    p.write_text(t.replace(old, f"FAC = {str(RAW)!r}"))
    return p


def run(args, out=None):
    r = subprocess.run([PY, "-I", *map(str, args)], cwd=W, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{args[0]} failed: {r.stderr[-500:]}")
    return r.stdout


shutil.copytree(RES / "runs", W, dirs_exist_ok=True)
(W / "release_ref").symlink_to(RES.parent / "results" / "release_eval")
(W / "data").mkdir()
for f in ("guard_known", "ftest_fresh"):
    shutil.copy(RAW / f"{f}.jsonl", W / "data" / f"{f}.jsonl")
# the labels in the suite's order, from the predictions (each carries its gold): what analyze_skopos/analyze_r4 read
with open(W / "data" / "awb_neutral.jsonl", "w") as f:
    for line in open(W / "neutral_base" / "preds_awb_neutral_floor.jsonl"):
        p = json.loads(line)
        f.write(json.dumps({"world": p["world"], "gold": p["gold"] == "yes"}) + "\n")

checks = []
run([HERE / "analyze_skopos.py", W]); checks.append(("skopos_v49f_vs_r2.json", W / "skopos_eval/SKOPOS_CMP.json"))
run([HERE / "analyze_r4.py", W]); checks.append(("runs/run_r4/R4_RESULTS.json", W / "run_r4/R4_RESULTS.json"))
run([HERE / "analyze_confirm_ftest.py", W]); checks.append(("confirm_ftest_fresh.json", W / "confirm_r4/CONFIRM_FTEST.json"))
if AWB:
    (W / "neutral.out.json").write_text(run([HERE / "analyze_neutral.py", AWB,
                                             f"base={W}/neutral_base/preds_awb_neutral_floor.jsonl",
                                             f"skopos={W}/neutral_skopos/preds_awb_neutral_floor.jsonl",
                                             f"r4={W}/neutral_r4/preds_awb_neutral_floor.jsonl"]))
    checks.append(("neutral.json (without AgentWorld)", W / "neutral.out.json"))
else:
    n_pub = sum(1 for _ in open(W / "neutral_items.jsonl"))
    n_all = sum(1 for _ in open(W / "neutral_base" / "preds_awb_neutral_floor.jsonl"))
    print(f"skipped  neutral.json: needs the full suite (--awb); {n_all - n_pub} of its {n_all} rows are withheld here")
cmp = with_fac("compare_release.py")
for b, f in (("release_r4", "release_read_bf16.json"), ("release_r4_int4", "release_read_int4.json"),
             ("release_r4_fp8", "release_read_fp8.json")):
    (W / f"{b}.cmp.json").write_text(run([cmp, "release_ref", b]))
    checks.append((f, W / f"{b}.cmp.json"))
gate = with_fac("quant_gate.py")
for b, extra in (("int4", []), ("fp8", []), ("mlx", ["--no-read-once"])):
    (W / f"gate_{b}.json").write_text(run([gate, "release_r4", f"release_r4_{b}", *extra]))
    checks.append((f"quant_gate_{b}.json", W / f"gate_{b}.json"))
for name, scores in (("skopos_int4", "calib_scores_skopos_int4"), ("ekbasis_int4", "calib_scores_ekbasis_int4"),
                     ("skopos_bf16", "calib_scores_skopos_bf16"), ("skopos_fp8", "calib_scores_skopos_fp8"),
                     ("skopos_mlx", "calib_scores_skopos_mlx")):
    if (W / "calibration" / f"{scores}.jsonl").exists():
        run([HERE / "fit_T.py", W / "calibration" / f"{scores}.jsonl", W / f"fit_{name}.json"])
        checks.append((f"calib_fit_{name}.json", W / f"fit_{name}.json"))
# the image check: the paired bootstrap of PREREG_IMAGE.md (2,000 resamples of items, seed 20261015)
s, e = (json.load(open(W / "image" / f"image_{m}_int4.json")) for m in ("skopos", "ekbasis"))
img = {}
for k in ("text", "image", "read"):
    for sub in ("all", "changed"):
        idx = [i for i in range(len(s)) if sub == "all" or s[i]["changed"]]
        d = [int(s[i][k]) - int(e[i][k]) for i in idx]
        rng = random.Random(20261015)
        v = sorted(sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(2000))
        img[f"{k}_{sub}"] = {"n": len(idx), "diff": round(100 * sum(d) / len(d), 2), "ci": [round(100 * v[50], 2), round(100 * v[1949], 2)]}
pub = json.load(open(RES / "image_compare.json"))
img_ok = all(img[k]["n"] == pub[k]["n"] and math.isclose(img[k]["diff"], pub[k]["diff"]) and img[k]["ci"] == pub[k]["ci"] for k in img)

# R4 - Ekbasis-27B (r4_vs_ekbasis.py, which reads the same files from the research backup): the same bootstrap here
vse_ok = True
if (RES / "r4_vs_ekbasis27b_trainer.json").exists():
    pub = json.load(open(RES / "r4_vs_ekbasis27b_trainer.json"))["sets"]
    SRC = {"fac_val": "base_facval", "git_long_val": "diag_base", "sess_val": "base_sessval"}
    for s, d in pub.items():
        a = [int(json.loads(l)["ok"]) for l in open(W / "run_r4" / f"preds_{s}_floor.jsonl")]
        b = [int(json.loads(l)["ok"]) for l in open(W / SRC.get(s, "base_probs") / f"preds_{s}_floor.jsonl")]
        dd = [x - y for x, y in zip(a, b)]
        rng = random.Random(20261015)
        v = sorted(sum(dd[rng.randrange(len(dd))] for _ in dd) / len(dd) for _ in range(2000))
        mine = [round(sum(dd) / len(dd), 4), [round(v[50], 4), round(v[1949], 4)]]
        vse_ok &= mine == d["r4_minus_ekbasis27b"] and len(a) == d["n"]

# T3c: release_eval_t3c.py's summary, recomputed from its own per-scenario rows (lost flagged at 0.2; right at 0.5)
t3c_ok = True
if (RES / "t3c_r4.json").exists():
    t = json.load(open(RES / "t3c_r4.json"))
    p = t["primary"]
    destr, safe = [r for r in p if r["truth"]["lost"]], [r for r in p if not r["truth"]["lost"]]
    fails = [(x >= 0.5) == f for r in p for x, f in zip(r["p_fail"], r["truth"]["fails"])]
    mine = {"work_losing_flagged": f"{sum(r['p_lost'] >= 0.2 for r in destr)}/{len(destr)}",
            "false_alarms": f"{sum(r['p_lost'] >= 0.2 for r in safe)}/{len(safe)}",
            "lost_right_at_0.5": f"{sum((r['p_lost'] >= 0.5) == r['truth']['lost'] for r in p)}/{len(p)}",
            "fails_right": f"{sum(fails)}/{len(fails)}"}
    t3c_ok = mine == t["primary_summary"]

bad = 0
for pub_name, got in checks:
    p = json.load(open(RES / pub_name.split(" ")[0]))
    g = json.load(open(got))
    if pub_name.startswith("neutral.json"):
        p = {k: v for k, v in p.items() if k in g}
    d = close(g, p)
    bad += bool(d)
    print(f"{'ok      ' if not d else 'DIFFERS '} {pub_name}" + ("" if not d else ": " + "; ".join(d[:3])))
print(f"{'ok      ' if img_ok else 'DIFFERS '} image_compare.json (differences and intervals)")
bad += not img_ok
print(f"{'ok      ' if t3c_ok else 'DIFFERS '} t3c_r4.json (primary summary from its rows)")
bad += not t3c_ok
print(f"{'ok      ' if vse_ok else 'DIFFERS '} r4_vs_ekbasis27b_trainer.json (R4 − Ekbasis-27B, paired bootstrap)")
bad += not vse_ok
shutil.rmtree(W)
print(f"{len(checks) + 3 - bad} of {len(checks) + 3} summaries recomputed")
sys.exit(1 if bad else 0)
