"""The reference rows of the certified-mode carry-over check, each on its stated scenario set and family-rate stream,
computed with analyze_carryover.py's own functions (imported, unchanged). Written for publication, to put the
check's references next to the numbers docs/VERIFY.md publishes for WS-MAC T2:
  - the MLX build on T2's completed scenarios, its family rate streamed over its own rows there (T2 as published);
  - Ekbasis-27B bf16 on T2's scenarios and on all of this check's scenarios, its family rate streamed over confirm-3's
    whole fresh stream (as confirm-3 and T2 score it);
  - the Skopos build on all of its scenarios and on T2's, its family rate streamed over its own rows of that set.
Needs the check's folder with its data files uncompressed (gunzip data/*.gz) and results/<TAG>_raw.jsonl.
    python3 certified_reference_rows.py ../certified_carryover ../certified_carryover_reference_rows.json skopos-int4 skopos-bf16"""
import json
import os
import sys

HERE, OUT, TAGS = os.path.abspath(sys.argv[1]), sys.argv[2], sys.argv[3:]
sys.path.insert(0, HERE)
os.environ.setdefault("TAG", TAGS[0])
import analyze_carryover as A  # noqa: E402

P3 = json.load(open(os.path.join(A.U, "confirm3", "params_confirm3.json")))
pol = A.policy.Policy()
reqs = A.jl(os.path.join(HERE, "data", "subset_requests.jsonl"))
meta = {}
for it in reqs:
    for row in it["rows"]:
        meta[row["rid"]] = {**row, "suite": it["suite"], "req": it["req"]}
keep = {(it["suite"], it["req"]) for it in reqs} - A.EXCLUDED
bf_all = [r for r in A.jl(os.path.join(HERE, "data", "fresh_rows_bf16.jsonl")) if r["exclude"] is None]
bf_extra = {e["rid"]: e for e in A.jl(os.path.join(HERE, "data", "extra_bf16.jsonl")) if "error" not in e}
fam_bf_full = A.famobs_stream(bf_all)
mlx_raw = A.dedupe(A.jl(os.path.join(HERE, "data", "mlx_raw_t2.jsonl")))
_, mlx_units, t2_scen = A.model_units(mlx_raw, meta, pol, keep)


def l2(units):
    b = A.rule_block(units, P3["a02"], 0.02)["L2"]
    return {k: b[k] for k in ("units", "accepted", "errors_among_accepted", "error_rate_among_accepted",
                              "error_rate_among_accepted_weighted", "cp95_upper_overall", "verified_share",
                              "verified_share_weighted", "no_node_significantly_above")}


out = {"definition": __doc__.split("\n")[0], "t2_scenarios": len(t2_scen),
       "mlx_t2_as_published": {"scenarios": len(t2_scen), "family_rate": "streamed over the MLX build's own rows on T2's scenarios",
                               "L2_a02": l2(mlx_units)},
       "ekbasis27b_bf16_t2_scenarios": {"scenarios": len(t2_scen), "family_rate": "streamed over confirm-3's whole fresh stream",
                                        "L2_a02": l2(A.bf16_units(bf_all, bf_extra, meta, t2_scen, pol, fam_bf_full)[1])}}
for tag in TAGS:
    raw = A.dedupe(A.jl(os.path.join(HERE, "results", f"{tag}_raw.jsonl")))
    _, units, done = A.model_units(raw, meta, pol, keep)
    _, units_t2, _ = A.model_units(raw, meta, pol, done & t2_scen)
    out[tag] = {"all_scenarios": {"scenarios": len(done), "family_rate": "streamed over this run's rows", "L2_a02": l2(units)},
                "t2_scenarios": {"scenarios": len(done & t2_scen), "family_rate": "streamed over this run's rows on T2's scenarios",
                                 "L2_a02": l2(units_t2)}}
    out[f"ekbasis27b_bf16_{tag}_scenarios"] = {"scenarios": len(done), "family_rate": "streamed over confirm-3's whole fresh stream",
                                               "L2_a02": l2(A.bf16_units(bf_all, bf_extra, meta, done, pol, fam_bf_full)[1])}
json.dump(out, open(OUT, "w"), indent=1)
print(json.dumps({k: (v["L2_a02"] if "L2_a02" in v else {kk: vv["L2_a02"] for kk, vv in v.items()}) if isinstance(v, dict) else v
                  for k, v in out.items()}, indent=1))
