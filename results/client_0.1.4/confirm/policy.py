"""The frozen "check when sure" policy (WS-U confirmatory test). Parameters come from policy_params.json, written by
dev_calibrate.py from dev data only. For a confident answer (confidence ≥ 0.9):
  famobs  = error rate of its observable question family so far: (errors + 1) / (answers + 2), counting the dev history
            (WS-P's 29,029 answered questions) and every earlier fresh answer whose outcome is known (online, warm start);
  minpert = 1 − min(P_reordered(answer), P_prefixed(answer))   (one extra request, two prompts);
  verify  = P(no) on the self-check question                   (one extra request);
score = mean of the signals mapped through their dev mid-ECDFs, without the self-check on git_wild and shell_wild;
verify the answer by real execution when score ≥ τ."""
import bisect
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEV_DATASET = "/root/decis/mission/P/data/dataset.jsonl"


def observable(suite, family):
    """The observable family key (WS-U Addendum 2): drops the test-design labels a deployment cannot see."""
    parts = family.split("|")
    if suite in ("apps", "accumulation", "planning_probe"):
        return parts[0]
    if suite == "habit_vs_rule":
        return "|".join(parts[:2])
    if suite == "web":
        return parts[-1]
    return family


def apply_ecdf(t, x):
    k = bisect.bisect_left(t["support"], x)
    if k < len(t["support"]) and t["support"][k] == x:
        b, h = t["below_here"][k]
        return b + 0.5 * h
    if k == 0:
        return 0.0
    b, h = t["below_here"][k - 1]
    return b + h


class FamilyRates:
    def __init__(self, prior=(1, 1)):
        self.a, self.b = prior
        self.n, self.e = collections.Counter(), collections.Counter()

    @classmethod
    def from_dev(cls, prior=(1, 1)):
        fr = cls(prior)
        for l in open(DEV_DATASET):
            r = json.loads(l)
            fr.update((r["suite"], observable(r["suite"], r["family"])), not r["correct"])
        return fr

    def rate(self, key):
        return (self.e[key] + self.a) / (self.n[key] + self.a + self.b)

    def update(self, key, wrong):
        self.n[key] += 1
        self.e[key] += bool(wrong)


class Policy:
    def __init__(self, params=None):
        self.p = params or json.load(open(os.path.join(HERE, "policy_params.json")))
        self.tf = self.p["transforms"]
        self.tau = self.p["tau"]
        self.no_selfcheck = set(self.p["no_selfcheck_suites"])

    def F(self, name, x):
        return apply_ecdf(self.tf[name], x)

    def score(self, suite, famobs, minpert, verify):
        if suite in self.no_selfcheck:
            return (self.F("famobs", famobs) + self.F("minpert", minpert)) / 2
        return (self.F("famobs", famobs) + self.F("minpert", minpert) + self.F("verify", verify)) / 3

    def score_all3(self, famobs, minpert, verify):
        """Exploratory comparison only: the self-check kept everywhere (variant A's formula, same transforms)."""
        return (self.F("famobs", famobs) + self.F("minpert", minpert) + self.F("verify", verify)) / 3

    def check(self, s):
        return s >= self.tau
