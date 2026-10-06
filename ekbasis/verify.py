"""Verify when sure: which of the model's CONFIDENT answers to check by real execution before acting on them.

Ekbasis is right most of the time, and when it is unsure the client already says to look ("look when unsure"). The
remaining risk is the confident error: an answer with confidence >= 0.9 that is wrong. Confidence alone ranks them
poorly: to catch 80% of them you would verify about half of all confident answers. This module adds the policy that
was confirmed on fresh items (results/client_0.1.4/SPEC_confirm.md, 2026-10-06), with three signals:

  family     the error rate of the answer's question family, from outcomes you actually observed:
             (errors + 1) / (observed + 2). A family is an observable key: the command types and the question for git
             and shell (`git_family`, `shell_family`), or a key you choose. No model call.
  stability  1 - the lower probability of the same answer when the options are shown in reverse order and when the
             question gets the prefix "Answer from the rules and the state above." One request.
  self-check P(no) to 'Consider this question: "<question>" Is "<answer>" the correct answer?'. One request. Not used
             for git and shell, where it was misleading (fresh git: AUROC 0.33).

Each signal goes through its fixed reference distribution (the dev answers of the test); the score is their mean, and
the answer should be verified when the score reaches the threshold of its domain (`rule="domain"`, the default):

  domain   rules 0.6056, sql 0.4836, shell 0.6571, git 0.7675, totals 0.7361; any other domain, or none: 0.6414.
           On a second fresh test (confirm-2, 18,615 confident answers, 1,202 wrong): 84.5% of the confident errors
           caught while verifying 22.6% of the confident answers, every domain at 80% or more except shell (79.9%).
  conformal  (option) per family group, alpha 0.15: on confirm-2 86.3% caught, 26.2% verified. Its family groups use the
           evaluation's family labels; any other family of a domain uses the domain's "rest" threshold.
  global   (option) 0.6414 for everything: confirmed first (84.9% / 23.4%) and replicated (83.5% / 23.4%), but it
           caught only 67% of the SQL errors.

Confidence alone, at the same verified share, catches about 65%.

For a question about several actions in a row, `check_steps` compares the direct answer with the step-by-step one
(`simulate`) and asks to verify when they differ by >= 0.0334 on the direct answer's probability. That caught 87.9% of
the confident errors while verifying 22.8%, measured on running totals near a limit (the accumulation suite only).

What these numbers do not cover:
  - the client's own family keys (the test used the evaluation's family labels);
  - a tracker that starts empty (the test started from 29,029 evaluation answers, then learned online). With no
    history a family's rate starts at 0.5, so new families are verified more until outcomes come in;
  - new kinds of questions, and real traffic.

Blocked actions: count only outcomes you actually observed. A guard that blocks a command never learns what it would
have done, so `FamilyTracker.observe` must not be called for it. Call `unobserved` instead: it is reported, never
counted. Because blocked actions are the ones that looked risky, the observed error rate of a family can be lower
than its true one. Label some of them anyway: `audit(rate)` picks a random share to replay in a sandbox (or to verify
when accepted), and only that outcome goes to `observe`. Blocking also changes what an agent proposes next, so rates
learned offline may not hold in a live loop.

Answers below 0.9 confidence are not scored: the client's rule for them stays "look", and `check` says so with no
extra call. If the extra requests fail, `check` says to verify (fail closed).
"""
from __future__ import annotations

import bisect
import json
import os
import tempfile
import threading
from dataclasses import dataclass, field

from .client import Answer, EkbasisError
from .prompts import choice, parse_git, tokens, world_state

PREFIX = "Answer from the rules and the state above. "
SELF_CHECK = 'Consider this question: "{question}" Is "{answer}" the correct answer?'
_POLICY = None


def policy(path: str | None = None) -> dict:
    """The frozen policy (verify_policy.json next to this file, unless a path is given)."""
    global _POLICY
    if path:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if _POLICY is None:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_policy.json"), encoding="utf-8") as f:
            _POLICY = json.load(f)
    return _POLICY


def percentile(pol: dict, signal: str, x: float) -> float:
    """Where x sits among the reference answers (a weighted mid-ECDF: below + half of the ties), 0..1."""
    t = pol["transforms"][signal]
    k = bisect.bisect_left(t["support"], x)
    if k < len(t["support"]) and t["support"][k] == x:
        below, here = t["below_here"][k]
        return below + 0.5 * here
    if k == 0:
        return 0.0
    below, here = t["below_here"][k - 1]
    return below + here


def score(family_rate: float, stability: float, doubt: float | None = None, pol: dict | None = None) -> float:
    """The policy score: the mean reference percentile of the signals, in the order family, stability, self-check (the
    self-check left out when doubt is None, as for git and shell). Verify when it is >= pol["tau"]."""
    pol = pol or policy()
    pcts = [percentile(pol, "famobs", family_rate), percentile(pol, "minpert", stability)]
    if doubt is not None:
        pcts.append(percentile(pol, "verify", doubt))
    return sum(pcts) / len(pcts)


def audit(rate: float = 0.05, rng=None) -> bool:
    """True for a random `rate` of the calls. For a BLOCKED action, that means: replay it in a sandbox (a copy of the
    repository or folder) and record what really happened with FamilyTracker.observe. For an ACCEPTED answer, it means:
    verify it anyway. Without audits, blocked actions never get an outcome and a family's observed error rate is biased.
    rng: a random.Random for reproducible audits."""
    import random
    return (rng or random).random() < rate


RULES = ("domain", "conformal", "global")


def domain_of(domain: str | None, pol: dict | None = None) -> str | None:
    """The policy's name for a domain ("rules", "sql", "shell", "git", "totals"; the evaluation suite names are accepted
    too), or None for any other domain."""
    pol = pol or policy()
    d = (domain or "").strip().lower()
    d = pol.get("domain_aliases", {}).get(d, d)
    return d if d in pol.get("domain_tau", {}) else None


def threshold(domain: str | None = None, family: str | None = None, rule: str = "domain", pol: dict | None = None) -> float:
    """The score at or above which a confident answer should be verified, under `rule`:
      "domain"    (default) the domain's threshold; the global one for any other domain;
      "conformal" the family group's threshold (family = the evaluation's label, e.g. "kind|delay"), else the domain's
                  "rest" group, else the global one;
      "global"    one threshold for everything."""
    pol = pol or policy()
    if rule not in RULES:
        raise ValueError(f"rule must be one of {', '.join(RULES)}")
    d = domain_of(domain, pol)
    if rule == "global" or d is None:
        return pol["tau"]
    if rule == "domain":
        return pol["domain_tau"][d]
    groups = pol["conformal"]["groups"]
    return groups.get(f"{d}|{family}", groups.get(f"{d}|*rest*", pol["tau"]))


class FamilyTracker:
    """Error rates of question families, from outcomes that were actually observed.

    tracker = FamilyTracker("~/.ekbasis/families.json")   # loads it if it exists; saved after every update
    tracker.observe(family, correct=True)                  # the action ran and its real outcome matched the answer
    tracker.unobserved(family)                             # blocked, or the outcome was not read: reported, not counted
    """

    def __init__(self, path: str | None = None, prior=(1, 1)):
        self.path = os.path.expanduser(path) if path else None
        self.prior = (float(prior[0]), float(prior[1]))
        self.families: dict = {}
        self._lock = threading.Lock()
        if self.path and os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.prior = tuple(d.get("prior", self.prior))
            self.families = {k: dict(v) for k, v in d.get("families", {}).items()}

    def counts(self, family: str) -> dict:
        c = self.families.get(family) or {}
        return {"observed": int(c.get("observed", 0)), "errors": int(c.get("errors", 0)),
                "unobserved": int(c.get("unobserved", 0))}

    def rate(self, family: str | None) -> float:
        a, b = self.prior
        c = self.counts(family) if family else {"observed": 0, "errors": 0}
        return (c["errors"] + a) / (c["observed"] + a + b)

    def observe(self, family: str, correct: bool, save: bool = True) -> None:
        with self._lock:
            c = self.families.setdefault(family, {"observed": 0, "errors": 0, "unobserved": 0})
            c["observed"] += 1
            c["errors"] += 0 if correct else 1
            if save:
                self._save()

    def unobserved(self, family: str, save: bool = True) -> None:
        with self._lock:
            c = self.families.setdefault(family, {"observed": 0, "errors": 0, "unobserved": 0})
            c["unobserved"] += 1
            if save:
                self._save()

    def save(self) -> None:
        with self._lock:
            self._save()

    def _save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".", prefix=".families.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "prior": list(self.prior), "families": self.families}, f, indent=1, sort_keys=True)
        os.replace(tmp, self.path)


@dataclass
class Decision:
    verify: bool                       # check this answer by real execution (or by looking) before acting on it
    reasons: list                      # why, in plain words (the strongest signal first)
    answer: str                        # the answer's label ("yes"/"no" for yes/no questions)
    confidence: float
    score: float | None = None         # the policy score (None: not scored, e.g. an unsure answer)
    family: str | None = None
    signals: dict = field(default_factory=dict)   # raw values and their reference percentiles
    requests: int = 0                  # extra requests made
    threshold: float | None = None     # the score at or above which the answer is verified (see `threshold`)
    rule: str | None = None            # "domain" (default), "conformal" or "global"

    def __bool__(self):
        return self.verify


def label_of(question: dict, answer: Answer) -> str:
    if question.get("type") in ("noul", "boolean"):
        if isinstance(answer.value, bool):
            return "yes" if answer.value else "no"
        return str(answer.value)
    return str(answer.value)


def prob_of(question: dict, answer: Answer, label: str) -> float:
    if question.get("type") in ("noul", "boolean") and answer.p_yes is not None:
        return answer.p_yes if label == "yes" else 1.0 - answer.p_yes
    return float((answer.probabilities or {}).get(label, 0.0))


def answer_text(question: dict, label: str) -> str:
    """The answer as the self-check names it: the label, and its description when it has one."""
    desc = label if question.get("type") in ("noul", "boolean") else str((question.get("criteria") or {}).get(label, label))
    return label if desc == label else f"{label} ({desc})"


def perturbed(question: dict) -> dict:
    """The two variants asked in one request: options in reverse order, and the prefixed question."""
    text = question["instructions"]
    if question.get("type") in ("noul", "boolean"):
        reorder = choice(text, ["no", "yes"])
    else:
        reorder = dict(question, criteria=dict(reversed(list(question["criteria"].items()))))
    return {"reorder": reorder, "para": dict(question, instructions=PREFIX + text)}


def stability(client, state: str, question: dict, label: str) -> float:
    """1 - the lower probability of `label` over the two variants (WS-P's construction: the reordered variant is always a
    choice question; the prefixed one keeps the question's type)."""
    ans = client.ask(state, perturbed(question))
    p_reorder = float((ans["reorder"].probabilities or {}).get(label, 0.0))
    p_prefixed = prob_of(question, ans["para"], label)
    return 1.0 - min(p_reorder, p_prefixed)


def self_check(client, state: str, question: dict, label: str) -> float:
    text = SELF_CHECK.format(question=question["instructions"], answer=answer_text(question, label))
    ans = client.ask(state, {"q": choice(text, ["yes", "no"])})
    return float((ans["q"].probabilities or {}).get("no", 0.0))


def check(client, state: str, question: dict, answer: Answer, family: str | None = None, domain: str | None = None,
          tracker: FamilyTracker | None = None, pol: dict | None = None, rule: str = "domain") -> Decision:
    """Should this answer be verified before acting on it? state and question: exactly what was asked; answer: what came
    back (client.ask(state, {"q": question})["q"]). family: an observable key for this kind of question. domain: "rules",
    "sql", "shell", "git" or "totals" sets the threshold (`threshold`), and "git" and "shell" skip the self-check.
    rule: "domain" (default), "conformal" or "global". Unsure answers (confidence < 0.9) get verify=True with no extra
    request."""
    pol = pol or policy()
    tau = threshold(domain, family, rule, pol)
    label, conf = label_of(question, answer), float(answer.confidence)
    if conf < pol["confident"]:
        return Decision(True, [f"the model is unsure (confidence {conf:.2f} < {pol['confident']}): look before acting"],
                        label, conf, family=family, threshold=tau, rule=rule)
    rate = tracker.rate(family) if tracker is not None else (pol["family_prior"][0] / sum(pol["family_prior"]))
    use_self = (domain or "").lower() not in pol["no_selfcheck_domains"]
    requests = 0
    try:
        stab = stability(client, state, question, label)
        requests += 1
        doubt = self_check(client, state, question, label) if use_self else None
        requests += 1 if use_self else 0
    except (EkbasisError, OSError, KeyError, ValueError) as e:
        return Decision(True, [f"the checks could not run ({e}): verify"], label, conf, family=family, requests=requests,
                        threshold=tau, rule=rule)
    sig = {"family": {"value": rate, "pct": percentile(pol, "famobs", rate)},
           "stability": {"value": stab, "pct": percentile(pol, "minpert", stab)}}
    if use_self:
        sig["self_check"] = {"value": doubt, "pct": percentile(pol, "verify", doubt)}
    s = score(rate, stab, doubt if use_self else None, pol)
    verify = s >= tau
    c = tracker.counts(family) if (tracker is not None and family) else None
    words = {
        "family": (f"its question family has been wrong {c['errors']} of {c['observed']} observed times" if c and c["observed"]
                   else "its question family has no observed outcomes yet"),
        "stability": f"the answer's probability drops to {1 - stab:.2f} when the options are reversed or the question reworded",
        "self_check": f"the model's own check doubts it (P(no) = {doubt:.2f})" if use_self else "",
    }
    order = sorted(sig, key=lambda k: -sig[k]["pct"])
    if verify:
        reasons = [f"{words[k]} (higher than {100 * sig[k]['pct']:.0f}% of reference answers)" for k in order if sig[k]["pct"] >= 0.5]
        reasons = reasons or [f"the signals together score {s:.2f} >= {tau:.2f}"]
    else:
        reasons = [f"confident ({conf:.2f}) and the signals score {s:.2f} < {tau:.2f} ({rule} threshold)"]
    if c and c["unobserved"]:
        reasons.append(f"{c['unobserved']} earlier answers of this family were never observed (blocked or not read): "
                       "its observed error rate may be too low")
    return Decision(verify, reasons, label, conf, score=s, family=family, signals=sig, requests=requests, threshold=tau,
                    rule=rule)


class _Recorder:
    """Passes ask() to the client and keeps every answer (simulate only calls ask)."""

    def __init__(self, client):
        self.client, self.log = client, []

    def ask(self, state, questions, read_once=False, images=None):
        ans = self.client.ask(state, questions, read_once=read_once) if read_once else self.client.ask(state, questions)
        self.log.append(ans)
        return ans


def check_steps(client, rules: str, state: dict, actions, questions: dict, render, target: str,
                pol: dict | None = None, **simulate_kw) -> Decision:
    """For a question about several actions: ask it directly about all the actions, then follow them one at a time with
    `simulate` (same rules, state, questions and render as for simulate), and compare the probability the two give the
    direct answer. Verify when they differ by >= 0.0334 (or when the direct answer is unsure). Costs one request per
    action, plus one."""
    from .simulate import simulate
    pol = pol or policy()
    actions = list(actions)
    q = questions[target]
    try:
        direct = client.ask(world_state(rules, render(state), actions), {target: q})[target]
    except (EkbasisError, OSError) as e:
        return Decision(True, [f"the direct question could not be asked ({e}): verify"], "", 0.0)
    label, conf = label_of(q, direct), float(direct.confidence)
    if conf < pol["confident"]:
        return Decision(True, [f"the model is unsure (confidence {conf:.2f} < {pol['confident']}): look before acting"],
                        label, conf, requests=1)
    rec = _Recorder(client)
    try:
        sim = simulate(rec, rules, state, actions, questions, render, **simulate_kw)
    except (EkbasisError, OSError) as e:
        return Decision(True, [f"the step-by-step check could not run ({e}): verify"], label, conf, requests=1 + len(rec.log))
    p_direct, p_steps = prob_of(q, direct, label), prob_of(q, rec.log[-1][target], label)
    gap = abs(p_direct - p_steps)
    verify = gap >= pol["steps_tau"]
    stepwise = str(sim.final.get(target))
    why = (f"step by step the model gives {label!r} probability {p_steps:.2f} (final {stepwise!r}), directly {p_direct:.2f}: "
           f"a gap of {gap:.3f}")
    reasons = [why + (f" >= {pol['steps_tau']:.4f}" if verify else f" < {pol['steps_tau']:.4f}")]
    return Decision(verify, reasons, label, conf, score=gap, signals={"direct": p_direct, "steps": p_steps,
                    "final_steps": stepwise}, requests=1 + len(rec.log))


def git_family(commands, key: str) -> str:
    """Observable family for a git guard question: the git subcommands and the question (lost, in_progress, fails)."""
    subs = sorted({(parse_git(c)[0] or (tokens(c)[:1] or ["?"])[0]) for c in commands})
    return f"git:{'+'.join(subs)}|{key}"


def shell_family(commands, key: str) -> str:
    """Observable family for a shell question: the programs the commands run and the question."""
    progs = sorted({os.path.basename((tokens(c)[:1] or ["?"])[0]) for c in commands})
    return f"shell:{'+'.join(progs)}|{key}"


def git(verdict, client, tracker: FamilyTracker | None = None, pol: dict | None = None, rule: str = "domain") -> dict:
    """Decisions for a git guard verdict (ekbasis.git.check): {"lost": Decision, "in_progress": ..., "fails_1": ...}.
    Self-check is not used for git; the git threshold applies (rule="domain"). Each question costs one extra request
    when its answer is confident."""
    from . import prompts as P
    qs = {"lost": (P.GIT_LOST, verdict.p_lost), "in_progress": (P.GIT_IN_PROGRESS, verdict.p_in_progress)}
    qs.update({f"fails_{k}": (P.git_fails(k), p) for k, p in enumerate(verdict.p_fail, 1)})
    out = {}
    for name, (q, p_yes) in qs.items():
        ans = Answer(value=p_yes >= 0.5, confidence=max(p_yes, 1 - p_yes), probabilities={"yes": p_yes, "no": 1 - p_yes},
                     p_yes=p_yes)
        key = name.split("_")[0] if name.startswith("fails") else name
        cmds = [verdict.commands[int(name.split("_")[1]) - 1]] if name.startswith("fails") else verdict.commands
        out[name] = check(client, verdict.state, q, ans, family=git_family(cmds, key), domain="git", tracker=tracker, pol=pol,
                          rule=rule)
    return out
