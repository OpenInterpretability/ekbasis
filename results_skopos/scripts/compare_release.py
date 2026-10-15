"""PREREG_R4_RELEASE_READ.md: criteria 1-6 from the predictions, the same code for the current release (public
results/release_eval/) and the candidate. python3 compare_release.py REL_DIR CAND_DIR"""
import json, sys, collections
rel, cand = sys.argv[1], sys.argv[2]
L = lambda p: [json.loads(l) for l in open(p)]
FAC = "/dev/shm/conseq/fac"


def ece(P, bins=10):
    b = collections.defaultdict(list)
    for p in P:
        b[min(bins - 1, int(p["conf"] * bins))].append(p)
    return sum(len(v) / len(P) * abs(sum(x["ok"] for x in v) / len(v) - sum(x["conf"] for x in v) / len(v)) for v in b.values())


def git_preds(d):
    out = []
    for s in ("git3_test_known", "git3_test_held"):
        rows = L(f"{FAC}/{s}.jsonl"); P = L(f"{d}/preds_{s}.jsonl")
        assert len(rows) == len(P), s
        for r, p in zip(rows, P):
            out.append({"ok": p["ok"] if "ok" in p else p["pred"] == p["gold"], "conf": p["conf"]})
    return out


def multi_changed(d, split, mode):  # as release_eval.py: per question, changed = known0 and gold0 != gold
    rows = L(f"{FAC}/{split}.jsonl"); P = L(f"{d}/preds_{split}_{mode}.jsonl")
    n = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
    assert len(rows) == len(P), split
    chg = []
    for r, p in zip(rows, P):
        for k, q in enumerate(r["questions"]):
            g0 = r["gold0s"][k]
            if r["known0s"][k] and g0 is not None and n(g0) != n(r["golds"][k]):
                chg.append(p["preds"][k] == n(r["golds"][k]))
    return 100 * sum(chg) / len(chg), len(chg)


def ftest_changed(d):
    rows = L(f"{FAC}/ftest_family.jsonl"); g0 = L(f"{FAC}/gold0_ftest_family.jsonl"); P = L(f"{d}/preds_ftest_family.jsonl")
    n = lambda g: {True: "yes", False: "no"}[g] if isinstance(g, bool) else str(g)
    ch = [i for i, (r, g) in enumerate(zip(rows, g0)) if g["known"] and n(g["gold0"]) != n(r["gold"])]
    return 100 * sum((P[i]["ok"] if "ok" in P[i] else P[i]["pred"] == n(rows[i]["gold"])) for i in ch) / len(ch), len(ch)


def guard(d, split):
    rows = L(f"{FAC}/{split}.jsonl"); P = L(f"{d}/preds_{split}.jsonl")
    lost = [(r, p) for r, p in zip(rows, P) if r["qtype"] == "lost"]
    pos = [p for r, p in lost if r["gold"]]; neg = [p for r, p in lost if not r["gold"]]
    return sum(p["p_yes"] >= 0.2 for p in pos), len(pos), sum(p["p_yes"] >= 0.2 for p in neg), len(neg)


res = {}
for name, d, gd in (("release", rel, f"{rel}/guard_larger_set"), ("candidate", cand, cand)):
    G = git_preds(d)
    res[name] = {"git_v3_all": 100 * sum(p["ok"] for p in G) / len(G), "ece_git_v3_10bins": ece(G, 10), "ece_git_v3_15bins": ece(G, 15),
                 "multi_testfam_single": multi_changed(d, "multi_test_testfam", "single")[0],
                 "multi_testfam_read_once": multi_changed(d, "multi_test_testfam", "read_once")[0],
                 "multi_trainfam_single": multi_changed(d, "multi_test_trainfam", "single")[0],
                 "multi_trainfam_read_once": multi_changed(d, "multi_test_trainfam", "read_once")[0],
                 "ftest_changed": ftest_changed(d)[0],
                 "guard_known": guard(gd, "guard_known"), "guard_held": guard(gd, "guard_held")}
r, c = res["release"], res["candidate"]
chk = {
    "1 git v3": c["git_v3_all"] >= r["git_v3_all"] - 1,
    "2a multi single": c["multi_testfam_single"] >= r["multi_testfam_single"] - 1,
    "2b multi read-once": c["multi_testfam_read_once"] >= r["multi_testfam_read_once"] - 1,
    "3 ftest changed": c["ftest_changed"] >= r["ftest_changed"] - 1,
    "4 ECE git v3": c["ece_git_v3_10bins"] <= r["ece_git_v3_10bins"] + 0.01 and c["ece_git_v3_15bins"] <= r["ece_git_v3_15bins"] + 0.01,
    "5a guard known flagged": c["guard_known"][0] >= r["guard_known"][0] - 0.01 * r["guard_known"][1],
    "5b guard known false alarms": c["guard_known"][2] <= r["guard_known"][2] + 0.01 * r["guard_known"][3],
    "6a guard held flagged": c["guard_held"][0] >= r["guard_held"][0] - 0.01 * r["guard_held"][1],
    "6b guard held false alarms": c["guard_held"][2] <= r["guard_held"][2] + 0.01 * r["guard_held"][3]}
res["checks"] = chk; res["pass"] = all(chk.values())
print(json.dumps(res, indent=1))
