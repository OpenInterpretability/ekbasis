"""Images of the Ekbasis model cards, every number read from the result files (results/), none typed by hand: the same
visual identity as the Eikos launch (dark, 16:9, 3200×1800), with the OpenInterp violet for Ekbasis and the Eikos amber
for the model it was trained from.
  ekbasis_launch.png         the overview (HTML rendered by headless Chrome)
  chart_git_comparison.png   the same 240 git questions for every system
  chart_speed.png            seconds per forecast and forecasts per minute, against a reasoning model
  chart_guard.png            "will uncommitted work be lost?": the probability for work-losing and safe cases
  chart_calibration.png      confidence against accuracy
usage: python3 assets_src/make_assets.py  (from the package folder)"""
import json
import math
import os
import pathlib
import subprocess
import sys

import matplotlib
import matplotlib.text
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse, Patch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
RES, OUT = os.path.join(PKG, "results"), os.path.join(PKG, "assets")
os.makedirs(OUT, exist_ok=True)
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
ld = lambda *p: json.load(open(os.path.join(RES, *p)))
rows = lambda *p: [json.loads(line) for line in open(os.path.join(RES, *p))]

BG, GRID, FG, MUTED, DIM = "#0a0c10", "#232834", "#eef1f6", "#8a93a3", "#6d7482"
VIOLET, VIOLET2, AMBER = "#8b5cf6", "#c4b5fd", "#f5b942"
plt.rcParams.update({"font.family": "Helvetica Neue", "text.color": FG, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.edgecolor": GRID, "font.size": 20})


def frame(title, subtitle):
    fig = plt.figure(figsize=(16, 9), dpi=200, facecolor=BG)
    fig.text(0.045, 0.925, title, fontsize=40, fontweight="bold", color=FG, va="center")
    fig.text(0.045, 0.865, subtitle, fontsize=20, color=MUTED, va="center")
    fig.text(0.955, 0.915, "Ekbasis", fontsize=34, fontweight="bold", color=VIOLET, va="center", ha="right")
    signature(fig, 0.955, 0.975)
    return fig


def signature(fig, x, y):
    """OpenInterpretability · openinterp.org, right-aligned at (x, y), with the site's logo to its left."""
    r = fig.canvas.get_renderer()
    t3 = fig.text(x, y, "  ·  openinterp.org", fontsize=15, color=MUTED, va="center", ha="right")
    x3 = t3.get_window_extent(r).x0 / fig.bbox.width
    t2 = fig.text(x3, y, "Interpretability", fontsize=15, color="#818cf8", va="center", ha="right", fontweight="bold")
    x2 = t2.get_window_extent(r).x0 / fig.bbox.width
    t1 = fig.text(x2, y, "Open", fontsize=15, color=FG, va="center", ha="right", fontweight="bold")
    x1 = t1.get_window_extent(r).x0 / fig.bbox.width
    h = fig.bbox.width / fig.bbox.height  # figure coordinates are not square: scale the height to keep the rings round
    cx, rad = x1 - 0.022, 0.0058
    for dx, col in ((-0.0045, "#4f46e5"), (0.0045, "#06b6d4")):
        fig.patches.append(Ellipse((cx + dx, y), 2 * rad, 2 * rad * h, transform=fig.transFigure, fill=False, edgecolor=col,
                                   linewidth=1.6, zorder=5))
    fig.patches.append(Ellipse((cx, y), 0.6 * rad, 0.6 * rad * h, transform=fig.transFigure, color="#4f46e5", zorder=5))


def style(ax, grid="y"):
    ax.set_facecolor(BG)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(axis=grid, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(length=0, labelsize=18)


def foot(fig, text):
    fig.text(0.045, 0.03, text, fontsize=14, color=DIM, va="bottom", linespacing=1.5)


def save(fig, name):
    """Saves only if no text leaves the figure."""
    fig.canvas.draw()
    r, fb = fig.canvas.get_renderer(), fig.bbox
    out = [t.get_text()[:50] for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text().strip()
           and ((e := t.get_window_extent(r)).x0 < fb.x0 - 1 or e.x1 > fb.x1 + 1 or e.y0 < fb.y0 - 1 or e.y1 > fb.y1 + 1)]
    assert not out, f"{name}: text outside the figure: {out}"
    fig.savefig(os.path.join(OUT, name), facecolor=BG)
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------------- data
CMP = ld("release_eval", "comparison_240.json")
pct = lambda v: 100 * v[0] / v[1]


def half(x, nd=1):  # half-up rounding for labels (2.25 -> "2.3"), without a trailing ".0"
    from decimal import ROUND_HALF_UP, Decimal
    out = str(Decimal(str(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))
    return out[:-2] if nd == 1 and out.endswith(".0") else out
SYSTEMS = sorted(CMP, key=lambda m: -pct(CMP[m]["git_known"]))
METHOD = {"Ekbasis-27B": "one pass", "Eikos-27B (no consequence training)": "one pass", "Qwen3.8-27B reasoning": "reasoning",
          "Qwen3.8-27B answering at once": "at once"}
COLOR = {"Ekbasis-27B": VIOLET, "Eikos-27B (no consequence training)": AMBER}
SHORT = {"Eikos-27B (no consequence training)": "Eikos-27B", "Qwen3.8-27B reasoning": "Qwen3.8-27B",
         "Qwen3.8-27B answering at once": "Qwen3.8-27B"}
REP = ld("release_eval", "report_server_side.json")
EXT = ld("release_eval", "report_server_side_extra.json")
T3C = ld("release_eval", "release_eval_t3c.json")["primary"]
G3 = rows("release_eval", "preds_git3_test_known.jsonl") + rows("release_eval", "preds_git3_test_held.jsonl")
FF = rows("release_eval", "preds_ftest_family.jsonl")


def p50(*p):  # speed_bench.py sum: the median of the forecasts made one at a time
    s = sorted(r["seconds"] for r in rows(*p))
    return s[len(s) // 2]


def per_min(*p):
    m = ld(*p)
    return m["n"] / m["wall"] * 60


def acc_file(*p):
    r = rows(*p)
    return 100 * sum(x["ok"] for x in r) / len(r)


SPEED = [  # (label, seconds one at a time, per minute at 16, accuracy at 16, color)
    ("Qwen3.8-27B, reasoning", p50("release_eval", "speed_qwen", "think_par1.jsonl"),
     per_min("release_eval", "speed_qwen", "think_par16.meta.json"), acc_file("release_eval", "speed_qwen", "think_par16.jsonl"), "#7c8597"),
    ("Ekbasis-27B, one prompt per question", p50("release_eval", "speed_bf16", "cq_par1.jsonl"),
     per_min("release_eval", "speed_bf16", "cq_par16.meta.json"), acc_file("release_eval", "speed_bf16", "cq_par16.jsonl"), VIOLET),
    ("Ekbasis-27B, state read once per step", p50("release_eval", "speed_bf16", "cqm_par1.jsonl"),
     per_min("release_eval", "speed_bf16", "cqm_par16.meta.json"), acc_file("release_eval", "speed_bf16", "cqm_par16.jsonl"), VIOLET2),
    ("Ekbasis-27B-FP8, state read once per step", p50("quantized", "fp8", "speed", "cqm_par1.jsonl"),
     per_min("quantized", "fp8", "speed", "cqm_par16.meta.json"), acc_file("quantized", "fp8", "speed", "cqm_par16.jsonl"), "#a78bfa"),
]
CHECK = ld("release_eval", "short_eval_release.json")["timing_par1"]["p50_s"]
_plan_f = [f for f in sorted(os.listdir(os.path.join(RES, "release_eval"))) if f.startswith("search_") and f.endswith("rel_agent_hard.json")]
if _plan_f:  # the planning search: needed only by the last two images (strengths, overview)
    _plan = ld("release_eval", _plan_f[0])
    _plan = _plan[list(_plan)[0]]["ok"]
    plan_ok_global, plan_n = 100 * sum(_plan) / len(_plan), len(_plan)
else:
    plan_ok_global = plan_n = None
_think = rows("release_eval", "speed_qwen", "think_par16.jsonl")
THINK_TOK = sum(r["tokens"] for r in _think) / len(_think)  # generated tokens (speed_bench.py: "tokens"; "input_tokens" is what it read)
assert THINK_TOK > 0, "no generated-token count in the reasoning run"


def ece(p, bins=10):
    tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        s = [r for r in p if lo <= r["conf"] < hi or (b == bins - 1 and r["conf"] == 1.0)]
        if s:
            tot += len(s) / len(p) * abs(sum(r["pred"] == r["gold"] for r in s) / len(s) - sum(r["conf"] for r in s) / len(s))
    return tot


# ---------------------------------------------------------------- 1. the 240-question comparison
fig = frame("Git consequences in one pass",
            "Accuracy (%) on the same 240 questions — command types seen in training / never seen")
ax = fig.add_axes([0.06, 0.28, 0.9, 0.47])
style(ax)
w = 0.38
for i, m in enumerate(SYSTEMS):
    c = COLOR.get(m, "#7c8597" if m.startswith("Claude") else "#4a5263")
    for k, (s, alpha) in enumerate((("git_known", 1.0), ("git_held", 0.45))):
        v = pct(CMP[m][s])
        x = i + (k - 0.5) * w
        ax.bar(x, v, w * 0.92, color=c, alpha=alpha, zorder=3)
        ax.text(x, v + 1.2, f"{v:.1f}", ha="center", va="bottom", fontsize=12.5,
                color=FG if m == "Ekbasis-27B" else MUTED, fontweight="bold" if m == "Ekbasis-27B" else "normal")
ax.set_xticks(range(len(SYSTEMS)))
ax.set_xticklabels([(SHORT.get(m, m).replace("Claude ", "Claude\n") if m.startswith("Claude") else SHORT.get(m, m))
                    + f"\n{METHOD.get(m, 'reasoning')}" for m in SYSTEMS], fontsize=15, color=FG, linespacing=1.25)
for lab, m in zip(ax.get_xticklabels(), SYSTEMS):
    if m == "Ekbasis-27B":
        lab.set_color(VIOLET2)
        lab.set_fontweight("bold")
ax.set_ylim(0, 108)
fig.legend(handles=[Patch(color="#9aa1ad", label="command types seen in training"),
                    Patch(color="#9aa1ad", alpha=0.45, label="never seen")],
           loc="center left", bbox_to_anchor=(0.04, 0.795), ncol=2, frameon=False, fontsize=18)
haiku = CMP["Claude Haiku 4.5"]["git_held"]
foot(fig, "40 \"will uncommitted work be lost?\", 40 \"will it fail?\" and 40 state questions per half; the truth comes from running the commands in a sandbox.\n"
          f"Ekbasis, Eikos-27B and Qwen3.8-27B share one base model (Qwen3.8-27B). Ekbasis: the release weights, each question alone, {CHECK:.2f} s, no generated text.\n"
          f"Claude models answered as hand-offs in batches with the answer order shuffled (evaluation only); Claude Haiku 4.5 left {haiku[1] - haiku[2]} of {haiku[1]} unanswered, counted wrong. Oct 2026.")
save(fig, "chart_git_comparison.png")

# ---------------------------------------------------------------- 2. speed
fig = frame("Foresight at the speed of a check",
            "Forecasts over sequences of 10–30 actions (the test's length, not a limit), one RTX PRO 6000 per system")
labels = [f"{s[0]}\n{s[3]:.0f}% right" for s in SPEED][::-1]
for j, (title, idx, fmt) in enumerate((("Seconds per forecast, one at a time (median)", 1, "{:.1f} s"),
                                       ("Forecasts per minute, 16 in parallel", 2, "{:.1f}"))):
    ax = fig.add_axes([0.3 + j * 0.36, 0.24, 0.29, 0.52])
    style(ax, grid="x")
    vals = [s[idx] for s in SPEED][::-1]
    ax.barh(range(len(vals)), vals, 0.62, color=[s[4] for s in SPEED][::-1], zorder=3)
    for y, v in enumerate(vals):
        ax.text(v + max(vals) * 0.02, y, fmt.format(v), va="center", fontsize=17, color=FG, fontweight="bold")
    ax.set_xlim(0, max(vals) * 1.3)
    ax.set_yticks(range(len(vals)))
    ax.set_yticklabels(labels if j == 0 else [""] * len(labels), fontsize=15, color=FG, linespacing=1.3)
    ax.set_title(title, fontsize=16, color=MUTED, loc="left", pad=14)
foot(fig, f"One check (1–3 actions, one question): {CHECK:.2f} s. Same 80 forecasts for every system; Ekbasis asks one typed question per variable after each action\n"
          f"and rebuilds the state from the answers; the reasoning model reads the whole sequence and thinks ({THINK_TOK:.0f} generated tokens per forecast on average).\n"
          "Accuracy on the 80 forecasts at 16 in parallel. vLLM 0.30; latency is the median of 8 forecasts made one at a time. Oct 2026.")
save(fig, "chart_speed.png")

# ---------------------------------------------------------------- 3. the guard: P(lost) for work-losing and safe cases
lost = [r for r in G3 if r["qtype"] == "lost"]
yes, no = [r["p_yes"] for r in lost if r["gold"] == "yes"], [r["p_yes"] for r in lost if r["gold"] == "no"]
fig = frame("\"Will this lose uncommitted work?\"", "Ekbasis' probability, for the git cases that lose work and the ones that do not")
ax = fig.add_axes([0.07, 0.25, 0.55, 0.5])
style(ax)
edges = [i / 20 for i in range(21)]
ax.hist([no, yes], bins=edges, stacked=False, color=["#7c8597", VIOLET], label=["loses nothing", "loses work"], zorder=3, rwidth=0.9)
ax.set_yscale("log")
top = max(max(sum(e0 <= v < e1 or (e1 == 1.0 and v == 1.0) for v in grp) for e0, e1 in zip(edges, edges[1:])) for grp in (yes, no))
ax.set_ylim(0.8, top * 3)
ax.set_xlim(0, 1)
ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
ax.set_yticks([1, 10, 100])
ax.set_yticklabels(["1", "10", "100"])
ax.axvline(0.2, color=VIOLET2, linestyle="--", linewidth=2, zorder=4)
ax.text(0.215, top * 2.2, "the guard flags\nfrom 0.2", color=VIOLET2, fontsize=15, va="top")
ax.set_xlabel("P(work lost)", fontsize=17)
ax.set_ylabel("cases (log scale)", fontsize=17)
ax.legend(frameon=False, fontsize=16, loc="upper center")
kn, he = REP["git3_test_known"], REP["git3_test_held"]
fl = sum(r["p_lost"] >= 0.2 for r in T3C if r["truth"]["lost"])
fa = sum(r["p_lost"] >= 0.2 for r in T3C if not r["truth"]["lost"])
facts = [("AUROC", f"{kn['lost_auroc']:.3f}", f"{he['lost_auroc']:.3f}"),
         ("flagged at 0.2", f"{kn['lost_flagged_at_0.2']:.0f}%", f"{he['lost_flagged_at_0.2']:.0f}%"),
         ("false alarms at 0.2", f"{kn['false_alarm_at_0.2']:.0f}%", f"{he['false_alarm_at_0.2']:.1f}%")]
fig.text(0.68, 0.72, "seen types     never seen", fontsize=15, color=MUTED)
for k, (a, b, c) in enumerate(facts):
    y = 0.64 - k * 0.075
    fig.text(0.68, y, a, fontsize=17, color=FG)
    fig.text(0.86, y, b, fontsize=19, color=VIOLET2, fontweight="bold", ha="right")
    fig.text(0.955, y, c, fontsize=19, color=VIOLET2, fontweight="bold", ha="right")
fig.text(0.68, 0.36, f"Fresh real repositories: {fl} of {sum(r['truth']['lost'] for r in T3C)}\nwork-losing scenarios flagged,\n{fa} false alarm in {sum(not r['truth']['lost'] for r in T3C)}.",
         fontsize=17, color=FG, linespacing=1.4)
foot(fig, f"Git v3 held-out tests: {len(yes)} work-losing and {len(no)} safe cases (repositories built and commands run in a sandbox; never-seen types: rebase, restore --source).\n"
          "Fresh real repositories: 16 scenarios on a clone of pallets/itsdangerous, written before the evaluation; the truth from running the commands. Oct 2026.")
save(fig, "chart_guard.png")

# ---------------------------------------------------------------- 4. calibration
fig = frame("When it is sure, it is right",
            "Confidence of the chosen answer against accuracy — between 0.7 and 0.99 it is overconfident: treat that band as a check")
ax = fig.add_axes([0.07, 0.24, 0.5, 0.54])
style(ax, grid="both")
cuts = [0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0001]
for name, p, c in (("git (3,105 questions)", G3, VIOLET), ("worlds never seen in training (1,080)", FF, AMBER)):
    xs, ys, ns = [], [], []
    for lo, hi in zip(cuts, cuts[1:]):
        s = [r for r in p if lo <= r["conf"] < hi]
        if len(s) >= 10:
            xs.append(sum(r["conf"] for r in s) / len(s))
            ys.append(sum(r["pred"] == r["gold"] for r in s) / len(s))
            ns.append(len(s))
    ax.plot(xs, ys, "-o", color=c, linewidth=3, markersize=9, zorder=3, label=f"{name}: ECE {ece(p):.3f}")
ax.plot([0.3, 1], [0.3, 1], "--", color=MUTED, linewidth=1.5, zorder=2)
ax.set_xlim(0.3, 1.01)
ax.set_ylim(0.3, 1.01)
ax.set_xlabel("confidence", fontsize=17)
ax.set_ylabel("accuracy", fontsize=17)
ax.legend(frameon=False, fontsize=15, loc="upper left")
sure = [r for r in G3 if r["conf"] >= 0.99]
mid = [r for r in G3 if 0.7 <= r["conf"] < 0.99]
fig.text(0.63, 0.66, f"{100 * len(sure) / len(G3):.0f}%", fontsize=58, fontweight="bold", color=VIOLET2)
fig.text(0.63, 0.6, "of the git answers come with confidence ≥ 0.99,", fontsize=17, color=FG)
fig.text(0.63, 0.565, f"and {100 * sum(r['pred'] == r['gold'] for r in sure) / len(sure):.1f}% of those are right", fontsize=17, color=FG)
fig.text(0.63, 0.44, f"{100 * sum(r['pred'] == r['gold'] for r in mid) / len(mid):.0f}%", fontsize=58, fontweight="bold", color=AMBER)
fig.text(0.63, 0.38, f"right between 0.7 and 0.99 ({len(mid)} answers,", fontsize=17, color=FG)
fig.text(0.63, 0.345, f"mean confidence {100 * sum(r['conf'] for r in mid) / len(mid):.0f}%): send those to a check", fontsize=17, color=FG)
foot(fig, "Points: answers grouped by confidence (groups of at least 10); on the dashed line, confidence equals accuracy. ECE: 10 equal-width bins.\n"
          "Git: v3 held-out tests, seen and never-seen command types. Worlds: rule-based worlds of families never seen in training (ftest_family). Oct 2026.")
save(fig, "chart_calibration.png")

# ---------------------------------------------------------------- 4b. long chains: predict, observe, correct
LC = os.path.join(RES, "release_eval", "long_chain3.jsonl")
if os.path.exists(LC):
    lc = rows("release_eval", "long_chain3.jsonl")
    cell = lambda fam, L, m: [r for r in lc if r["fam"] == fam and r["len"] == L and r["mode"] == m]
    MODES = [("text", "never\nlook"), ("obs50", "look\nevery 50"), ("conf0.5", "chain\nconfidence\n< 0.5"),
             ("conf0.9", "chain\nconfidence\n< 0.9"), ("check0.9", "< 0.9 +\nchecks\n(default)"), ("dual_conf0.9", "two views,\nchain\n< 0.9")]
    MODES = [(m, lab) for m, lab in MODES if cell("cards", 100, m)]
    fig = frame("Errors that never fade: it says when to look",
                "Card orderings, a world it never saw in training — the whole state right after the last action (%)")
    ax = fig.add_axes([0.06, 0.32, 0.56, 0.43])
    style(ax)
    w = 0.38
    for i, (m, lab) in enumerate(MODES):
        for k, (L, alpha) in enumerate(((100, 1.0), (200, 0.5))):
            g = cell("cards", L, m)
            if not g:
                continue
            v = 100 * sum(r["state_ok"] for r in g) / len(g)
            looks = sum(r["looks"] for r in g) / len(g) * 100 / L
            x = i + (k - 0.5) * w
            ax.bar(x, v, w * 0.92, color=VIOLET if m != "text" and m != "obs50" else "#7c8597", alpha=alpha, zorder=3)
            ax.text(x, v + 2, half(v, 0), ha="center", va="bottom", fontsize=13, color=FG)
            if looks and v > 12:
                ax.text(x, 4, half(looks, 0), ha="center", va="bottom", fontsize=13, color="white", fontweight="bold")
    ax.set_xticks(range(len(MODES)))
    ax.set_xticklabels([lab for _, lab in MODES], fontsize=14, color=FG, linespacing=1.15)
    fig.text(0.06, 0.205, "white number in a bar: looks at the real state per 100 actions", fontsize=13, color=VIOLET2)
    ax.set_ylim(0, 112)
    ax.set_xlim(-0.7, len(MODES) - 0.3)
    fig.legend(handles=[Patch(color="#9aa1ad", label="100 actions"), Patch(color="#9aa1ad", alpha=0.5, label="200 actions")],
               loc="center left", bbox_to_anchor=(0.04, 0.795), ncol=2, frameon=False, fontsize=17)
    fig.text(0.67, 0.73, "Where errors fade, it rarely asks", fontsize=19, color=FG, fontweight="bold")
    ctl = [r for fam in ("jugs", "toggles", "machines") for L in (100, 200) for r in cell(fam, L, "check0.9")]
    ok = sum(r["state_ok"] for r in ctl)
    fig.text(0.67, 0.69, f"the default rule; {'every chain' if ok == len(ctl) else f'{ok} of {len(ctl)} chains'} exact at the end",
             fontsize=15, color=MUTED)
    fig.text(0.67, 0.64, "world, actions", fontsize=13, color=DIM)
    fig.text(0.885, 0.64, "wrong / 100", fontsize=13, color=DIM, ha="right")
    fig.text(0.955, 0.64, "looks / 100", fontsize=13, color=DIM, ha="right")
    y = 0.595
    for fam, name in (("jugs", "containers"), ("toggles", "lamps"), ("machines", "machines*")):
        for L in (100, 200):
            g = cell(fam, L, "check0.9")
            if g:
                fig.text(0.67, y, f"{name}, {L}", fontsize=15, color=FG)
                fig.text(0.885, y, half(100 * sum(r['wrong_steps'] for r in g) / (len(g) * L)), fontsize=15, color=VIOLET2, ha="right")
                fig.text(0.955, y, half(sum(r['looks'] for r in g) / len(g) * 100 / L), fontsize=15, color=VIOLET2, ha="right")
                y -= 0.045
    fig.text(0.67, y - 0.005, "*never seen in training", fontsize=12, color=DIM)
    y -= 0.04
    trig = [r for r in lc if r["fam"] == "cards" and r["mode"] not in ("text", "obs50", "dual")]
    silent = sum(r["wrong_steps"] for r in trig)
    fig.text(0.67, max(y - 0.03, 0.2), f"Card chains that looked when unsure: {sum(r['state_ok'] for r in trig)} of {len(trig)}\n"
             f"exact; steps carried wrong before a look: {silent}", fontsize=15, color=FG, linespacing=1.4)
    n100 = len(cell("cards", 100, "text"))
    n_ctl = len(cell("jugs", 100, "check0.9"))
    foot(fig, f"One action per step, every variable asked after each action, the next state rebuilt from the answers (cards: the most probable valid ordering).\n"
              f"A look reads the real state (a git status, a sensor) and the chain continues from it. {n100} chains per cell for cards, {n_ctl} for the other worlds.\n"
              "Checks: after 8 actions without a look, look anyway; the gap doubles while forecasts hold (up to 64), back to 8 after a surprise. Wrong / 100: steps wrong along the way.\n"
              "The model's chain confidence is the product of each step's probability since the last look. Release weights, bf16. Oct 2026.")
    save(fig, "chart_long_chains.png")

# ---------------------------------------------------------------- 4c. which rule to look by, all four worlds
if os.path.exists(LC):
    lc = rows("release_eval", "long_chain3.jsonl")
    WORLDS = ("jugs", "toggles", "machines", "cards")
    RULES = [("conf0.5", "Chain confidence < 0.5"), ("until0.5", "< 0.5, and look again until right"),
             ("check0.5", "< 0.5 + checks"), ("conf0.9", "Chain confidence < 0.9"),
             ("until0.9", "< 0.9, and look again until right"), ("check0.9", "< 0.9 + checks (the default)")]
    DEFAULT = "check0.9"

    def pooled(mode):
        g = [r for r in lc if r["fam"] in WORLDS and r["mode"] == mode]
        acts = sum(r["len"] for r in g)
        return (100 * sum(r["looks"] for r in g) / acts, 100 * sum(r["wrong_steps"] for r in g) / acts,
                f"{sum(r['state_ok'] for r in g)}/{len(g)}", len(g))

    data = [(lab, *pooled(m), m == DEFAULT) for m, lab in RULES if pooled(m)[3]]
    never = pooled("text")
    fig = frame("Which rule to look by",
                f"Containers, lamps, machines and card orderings: the same {data[0][4]} chains of 100–200 actions for every rule")
    ys, panels = list(range(len(data)))[::-1], []
    for j, (title, idx, color, xmax) in enumerate((("Looks per 100 actions: the cost", 1, VIOLET, 23),
                                                  ("Steps wrong along the way, per 100", 2, VIOLET, 3.4))):
        ax = fig.add_axes([0.3 + j * 0.3, 0.27, 0.24, 0.47])
        panels.append(ax)
        style(ax, grid="x")
        ax.set_ylim(-0.6, len(data) - 0.4)
        for y, d in zip(ys, data):
            ax.barh(y, d[idx], 0.62, color=color if d[5] else "#7c8597", zorder=3)
            ax.text(d[idx] + xmax * 0.03, y, half(d[idx]) if idx == 1 else f"{d[idx]:.2f}", va="center", fontsize=15,
                    color=FG, fontweight="bold" if d[5] else "normal")
        ax.set_xlim(0, xmax * 1.25)
        ax.set_yticks(ys)
        ax.set_yticklabels([d[0] for d in data] if j == 0 else [""] * len(data), fontsize=15, color=FG)
        for lab in ax.get_yticklabels():
            if "default" in lab.get_text():
                lab.set_color(VIOLET2)
                lab.set_fontweight("bold")
        ax.set_title(title, fontsize=16, color=MUTED, loc="left", pad=14)
    fig.text(0.915, 0.765, "exact at\nthe end", fontsize=15, color=MUTED, ha="center", va="bottom", linespacing=1.1)
    for y, d in zip(ys, data):
        fy = panels[0].transData.transform((0, y))[1] / fig.bbox.height
        fig.text(0.915, fy, d[3], fontsize=16, color=VIOLET2 if d[5] else FG, ha="center", va="center",
                 fontweight="bold" if d[5] else "normal")
    fig.text(0.045, 0.19, "Checks: after 8 actions without a look, look anyway; the gap doubles while the forecasts hold (up to 64) and goes back to 8 after a surprise.",
             fontsize=16, color=FG)
    fig.text(0.045, 0.155, f"They find the rare confident errors a fixed threshold misses. Never looking: {never[2]} chains exact, "
             f"{half(never[1])} steps in 100 wrong along the way.", fontsize=16, color=FG)
    foot(fig, "A look reads the real state and the chain continues from it. Steps wrong along the way: actions after which the simulated state differed from the real one.\n"
              "Chain confidence: the product of each step's probability since the last look. Release weights, bf16. Oct 2026.")
    save(fig, "chart_look_tradeoff.png")

# ---------------------------------------------------------------- 4c2. confident errors: the pre-registered test
CE = os.path.join(RES, "confident_errors", "report.json")
if os.path.exists(CE):
    ce = ld("confident_errors", "report.json")
    CG, CF = ce["groups"], ce["families"]
    FN = {"grid": "grid", "gravity": "gravity", "counters": "counters", "toggles": "lamps", "seq": "sequences",
          "jugs": "containers", "craft": "crafting", "track": "track", "tally": "tally", "cards": "card orderings",
          "timers": "timers", "machines": "machines"}
    rows_ = []  # (label, share, wrong, error rate, kind)
    for g, name, kind in (("T", "Families it was trained on", "T"), ("U", "Families it never saw", "U")):
        d = CG[g]["all"]
        rows_.append((name, d["share_wrong_conf_ge_0.9"], d["wrong"], d["error_rate"], kind + "*"))
        fam_ = sorted((f for f in CG[g]["families"] if CF[f"{g}:{f}"]["wrong"] >= 10),
                      key=lambda f: -CF[f"{g}:{f}"]["share_wrong_conf_ge_0.9"])
        for f in fam_:
            d = CF[f"{g}:{f}"]
            rows_.append(("    " + FN[f], d["share_wrong_conf_ge_0.9"], d["wrong"], d["error_rate"], kind))
        rows_.append(None)
    d = CG["H"]["all"]
    rows_.append(("Known family, question type held out", d["share_wrong_conf_ge_0.9"], d["wrong"], d["error_rate"], "H*"))
    CK = os.path.join(RES, "confident_errors", "eikos27b", "compare.json")
    if os.path.exists(CK):  # the same questions, Eikos-27B: the model before consequence training
        ck = ld("confident_errors", "eikos27b", "compare.json")["eikos27b"]
        rows_.append(None)
        rows_.append(("Before consequence training (Eikos-27B):", None, None, None, "K-"))
        rows_.append(("    families later trained on", ck["share_T"], ck["wrong_T"], ck["error_T"], "K"))
        rows_.append(("    families never trained on", ck["share_U"], ck["wrong_U"], ck["error_U"], "K"))
    left_out = [f"{FN[f]} ({CF[f'{g}:{f}']['wrong']})" for g in ("T", "U") for f in CG[g]["families"] if CF[f"{g}:{f}"]["wrong"] < 10]
    n_ce = sum(CG[g]["all"]["n"] for g in CG)
    fig = frame("Where it is wrong, how sure was it?",
                f"Wrong answers given with a confidence of 0.9 or more, per world family, on {n_ce:,} new questions")
    ax = fig.add_axes([0.31, 0.27, 0.47, 0.5])
    style(ax, grid="x")
    ys, k = [], len(rows_)
    col = {"T": VIOLET, "U": "#7c8597", "H": VIOLET2, "K": AMBER}
    for i, r in enumerate(rows_):
        if r is None or r[1] is None:
            if r is not None:
                ys.append((k - i, r))
            continue
        y = k - i
        ys.append((y, r))
        bold = r[4].endswith("*")
        ax.barh(y, r[1], 0.7 if bold else 0.56, color=col[r[4][0]], alpha=1.0 if bold else 0.75, zorder=3)
        ax.text(r[1] + 1.5, y, f"{half(r[1], 0) if r[1] >= 10 else half(r[1])}%", va="center", fontsize=16 if bold else 14, color=FG,
                fontweight="bold" if bold else "normal")
    ax.set_xlim(0, 100)
    ax.set_ylim(0.4, k + 0.6)
    ax.set_yticks([y for y, _ in ys])
    ax.set_yticklabels([r[0] for _, r in ys], fontsize=15, color=FG)
    for lab, (_, r) in zip(ax.get_yticklabels(), ys):
        if r[4].endswith("*") or r[4] == "K-":
            lab.set_fontweight("bold")
        if r[4].startswith("K"):
            lab.set_color(AMBER)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0", "25%", "50%", "75%", "100%"], fontsize=13, color=MUTED)
    fig.text(0.885, 0.785, "error rate (wrong answers)", fontsize=14, color=MUTED, ha="center", va="bottom")
    for y, r in ys:
        if r[1] is None:
            continue
        fy = ax.transData.transform((0, y))[1] / fig.bbox.height
        fig.text(0.885, fy, f"{half(r[3])}% ({r[2]:,})", fontsize=14 if not r[4].endswith("*") else 15, color=FG,
                 ha="center", va="center", fontweight="bold" if r[4].endswith("*") else "normal")
    fig.text(0.045, 0.19, f"Its confidence ranks right answers above wrong ones about equally well in both (AUROC {half(CG['T']['all']['auroc'], 2)} "
             f"and {half(CG['U']['all']['auroc'], 2)}): what moves is the scale.", fontsize=16, color=FG)
    fig.text(0.045, 0.155, "Before consequence training the same model almost never erred with confidence: the training that cut its errors made the rest confident.",
             fontsize=16, color=FG)
    fig.text(0.045, 0.12, "So a fixed threshold misses more errors where it trained, and \"look when unsure\" also checks now and then.", fontsize=16, color=FG)
    v42ce = os.path.join(PKG, "results_v42", "confident_errors", "report.json")  # the pre-registered test ran on V42
    v42p = json.load(open(v42ce))["primary"] if os.path.exists(v42ce) else None
    foot(fig, f"1–3 actions, one question per prompt, release weights (bf16). Families with fewer than 10 wrong answers are left out of the bars: "
              f"{', '.join(left_out)}.\n"
              + (f"Pre-registered on V42: {half(v42p['difference_points'], 0)} points ({half(v42p['ci95'][0], 0)} to "
                 f"{half(v42p['ci95'][1], 0)}), confirmed; this release, same analysis: " if v42p else "")
              + f"{half(ce['primary']['difference_points'], 0)} ({half(ce['primary']['ci95'][0], 0)} to {half(ce['primary']['ci95'][1], 0)})"
              + (f"; training made it (vs Eikos-27B: {half(ldk['D'], 0)}, {half(ldk['D_ci95'][0], 0)} to {half(ldk['D_ci95'][1], 0)})"
                 if (ldk := (ld("confident_errors", "eikos27b", "compare.json") if os.path.exists(CK) else None)) else "")
              + ". Oct 2026.")
    save(fig, "chart_confident_errors.png")

if plan_ok_global is None:
    print("no planning search yet: the strengths chart and the overview image are left for later")
    sys.exit(0)
# ---------------------------------------------------------------- 4d. strengths and weaknesses, side by side
RLC = rows("release_eval", "release_long_chain.jsonl")
fade200 = [r for r in RLC if r["len"] == 200 and r["mode"] == "text" and r["fam"] in ("jugs", "toggles", "machines")]
cards200 = [r for r in RLC if r["len"] == 200 and r["mode"] == "text" and r["fam"] == "cards"]
img = [line for line in open(os.path.join(RES, "release_eval", "release_image_chain.out")) if line.startswith("all ")]
img_n = int(next(line for line in open(os.path.join(RES, "release_eval", "release_image_chain.out")) if "items" in line).split()[0])
cards_ff = EXT["ftest_family (answers the actions change)"]["per_world_changed"]["cards"]
mid = [r for r in G3 if 0.7 <= r["conf"] < 0.99]
mid_acc, mid_conf = 100 * sum(r["pred"] == r["gold"] for r in mid) / len(mid), 100 * sum(r["conf"] for r in mid) / len(mid)
SHORT_ACC = ld("release_eval", "short_eval_release.json")["accuracy"]["Ekbasis (release)"]
fix = ""
if os.path.exists(LC):
    g = [r for r in rows("release_eval", "long_chain3.jsonl") if r["fam"] == "cards" and r["len"] == 200 and r["mode"] == "check0.9"]
    if g:
        fix = f"look when unsure: {sum(r['state_ok'] for r in g)}/{len(g)} exact"
kn, he = REP["git3_test_known"], REP["git3_test_held"]
frac = lambda a, b: (100 * a / b, f"{a}/{b}")
items = [  # (label, accuracy %, n shown, note)
    ("Work-losing git commands flagged, fresh real repositories", *frac(fl, sum(r["truth"]["lost"] for r in T3C)), ""),
    ("\"Will uncommitted work be lost?\" — command types seen", kn["lost"]["acc"], f"n={kn['lost']['n']}", ""),
    ("\"Will uncommitted work be lost?\" — never seen", he["lost"]["acc"], f"n={he['lost']['n']}", ""),
    ("\"Is an operation left in progress?\" — never seen", he["in_progress"]["acc"], f"n={he['in_progress']['n']}", ""),
    ("Planning with no LLM, hard puzzles (plans run for real)", plan_ok_global, f"n={plan_n}", ""),
    ("Short checks, 1–3 actions", (SHORT_ACC["orig"] + SHORT_ACC["para"]) / 2, "n=240", ""),
    ("200-action chains where errors fade (final answer)", *frac(sum(r["final_ok"] for r in fade200), len(fade200)), ""),
    ("Chains that start from an image (final answer)", float(img[0].split()[2]), f"n={img_n}", ""),
    ("Trained worlds, answers the actions change", REP["multi_test_trainfam (one prompt per question)"]["acc_changed"], "n=902", ""),
    ("\"Will the command fail?\" — never-seen command types", he["fails"]["acc"], f"n={he['fails']['n']}", "a failed command changes nothing"),
    ("Never-trained worlds, answers the actions change", REP["multi_test_testfam (one prompt per question)"]["acc_changed"], "n=1,693", "teach it your environment"),
    ("State the commands change — never-seen command types", he["changed state"]["acc"], f"n={he['changed state']['n']}", "few cases; new command types"),
    ("Card orderings, a never-trained world (changed answers)", 100 * int(cards_ff.split("/")[0]) / int(cards_ff.split("/")[1]), cards_ff, "orderings are its hardest case"),
    ("Confidence between 0.7 and 0.99 (git): how often right", mid_acc, f"n={len(mid)}", f"it claims {mid_conf:.0f}%: check this band"),
    ("Card orderings, 200 actions, never looking (final answer)", *frac(sum(r["final_ok"] for r in cards200), len(cards200)), fix or "look at the real state when unsure"),
]
fig = frame("Where it is strong, where it is not", "Accuracy (%) of the release weights, by kind of question — measured, with what to do where it is weak")
ax = fig.add_axes([0.36, 0.14, 0.27, 0.68])
style(ax, grid="x")
ys = list(range(len(items)))[::-1]
for y, (lab, v, n, note) in zip(ys, items):
    col = VIOLET if v >= 95 else ("#a78bfa" if v >= 88 else AMBER)
    ax.barh(y, v, 0.66, color=col, zorder=3)
    half_up = math.floor(v * 10 + 0.5) / 10  # the documents round half up (96.25 -> 96.3)
    ax.text(v + 1.2, y, f"{half_up:.0f}" if ("/" in n or half_up == 100) else f"{half_up:.1f}", va="center", fontsize=13,
            color=FG, fontweight="bold")
    fig.text(0.35, 0.14 + 0.68 * (y + 0.5) / len(items), lab, fontsize=13.5, color=FG, ha="right", va="center")
    fig.text(0.655, 0.14 + 0.68 * (y + 0.5) / len(items), n, fontsize=12, color=DIM, ha="left", va="center")
    if note:
        fig.text(0.72, 0.14 + 0.68 * (y + 0.5) / len(items), note, fontsize=13, color=AMBER, ha="left", va="center")
    if lab.startswith("Confidence between"):
        ax.plot([mid_conf, mid_conf], [y - 0.38, y + 0.38], color="white", linewidth=2.5, zorder=4)
ax.set_ylim(-0.6, len(items) - 0.4)
ax.set_xlim(0, 112)
fig.text(0.655, 0.835, "cases", fontsize=12, color=DIM, ha="left")
fig.text(0.72, 0.835, "where it is weak: what to do", fontsize=12, color=AMBER, ha="left")
ax.set_yticks([])
ax.set_xticks([0, 25, 50, 75, 100])
foot(fig, "Git: v3 held-out tests (repositories built and commands run in a sandbox) and 16 fresh real-repository scenarios; worlds: rule-based worlds of trained and never-trained\n"
          "families; chains: one action per step, the state rebuilt from the answers. The white tick marks the confidence the model claims in that band. Release weights, Oct 2026.")
save(fig, "chart_strengths.png")

# ---------------------------------------------------------------- 5. the overview image (HTML -> PNG)
ek = CMP["Ekbasis-27B"]
rows4 = [m for m in ("Claude Sonnet 5.5", "Ekbasis-27B", "Qwen3.8-27B reasoning", "Eikos-27B (no consequence training)")]
assert pct(CMP["Ekbasis-27B"]["git_known"]) > pct(CMP["Qwen3.8-27B reasoning"]["git_known"])
qwen = SPEED[0]
assert SPEED[2][1] < qwen[1] / 5  # "about 9× faster" claims below are computed, this just guards the story
CSS = """
  :root { --bg: #0a0c10; --line: #232834; --fg: #eef1f6; --muted: #8a93a3; --dim: #6d7482; --v: #8b5cf6; --v2: #c4b5fd; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { width: 1600px; height: 900px; background: var(--bg); overflow: hidden; }
  body { font-family: -apple-system, "SF Pro Display", "Helvetica Neue", Arial, sans-serif; color: var(--fg); position: relative;
         -webkit-font-smoothing: antialiased; }
  .glow { position: absolute; left: -220px; top: -300px; width: 1000px; height: 760px;
          background: radial-gradient(closest-side, rgba(139,92,246,.24), rgba(139,92,246,0)); }
  .glow2 { position: absolute; right: -260px; bottom: -380px; width: 900px; height: 700px;
           background: radial-gradient(closest-side, rgba(236,72,153,.10), rgba(236,72,153,0)); }
  .grid { position: absolute; inset: 0; background-image: linear-gradient(rgba(255,255,255,.028) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.028) 1px, transparent 1px); background-size: 40px 40px;
          -webkit-mask-image: radial-gradient(ellipse at 25% 15%, black 15%, transparent 70%); }
  .wrap { position: relative; padding: 46px 72px 0 72px; }
  .pills { display: flex; gap: 10px; margin-bottom: 16px; }
  .pill { font-size: 14px; letter-spacing: .09em; text-transform: uppercase; font-weight: 600; padding: 7px 14px; border-radius: 999px;
          color: var(--v2); border: 1px solid rgba(139,92,246,.4); background: rgba(139,92,246,.10); }
  .pill.gray { color: var(--muted); border-color: var(--line); background: rgba(255,255,255,.03); }
  .title { display: flex; align-items: baseline; gap: 24px; }
  .name { font-size: 100px; font-weight: 800; letter-spacing: -0.035em; line-height: 1;
          background: linear-gradient(135deg, #c4b5fd 0%, #8b5cf6 45%, #ec4899 100%); -webkit-background-clip: text;
          background-clip: text; color: transparent; }
  .greek { font-size: 38px; color: var(--muted); font-weight: 300; }
  .greek em { font-style: italic; color: #b9c0cc; }
  .tag { margin-top: 10px; font-size: 27px; font-weight: 600; letter-spacing: -0.01em; }
  .tag span { color: var(--muted); font-weight: 400; }
  .cards { display: grid; grid-template-columns: 1.15fr 1fr 1fr; gap: 22px; margin-top: 30px; }
  .card { border: 1px solid var(--line); border-radius: 22px; padding: 22px 24px 18px;
          background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.012)); }
  .card.hero { border-color: rgba(139,92,246,.35); background: linear-gradient(180deg, rgba(139,92,246,.09), rgba(255,255,255,.012)); }
  .label { font-size: 14.5px; font-weight: 700; color: var(--muted); letter-spacing: .1em; text-transform: uppercase; }
  .big { font-size: 66px; font-weight: 800; letter-spacing: -0.035em; color: var(--v2); line-height: 1.05; margin-top: 6px; }
  .big small { font-size: 21px; font-weight: 600; color: var(--muted); letter-spacing: 0; margin-left: 10px; }
  .sub { font-size: 15.5px; color: var(--muted); margin: 4px 0 10px; }
  .row { display: grid; grid-template-columns: 236px 1fr 46px 46px; align-items: center; gap: 10px; margin: 9px 0; font-size: 16.5px; }
  .row.two { grid-template-columns: 210px 1fr 74px; }
  .n { white-space: nowrap; } .n small { font-size: 12.5px; color: var(--dim); margin-left: 5px; }
  .hdr { display: grid; grid-template-columns: 236px 1fr 46px 46px; gap: 10px; font-size: 12px; color: var(--dim);
         text-transform: uppercase; letter-spacing: .06em; margin-bottom: -4px; }
  .hdr div { text-align: right; }
  .n { color: var(--fg); font-weight: 500; } .n.dim { color: var(--muted); }
  .bar { height: 12px; border-radius: 999px; background: rgba(255,255,255,.055); position: relative; overflow: hidden; }
  .bar i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; min-width: 6px; }
  .v { text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; } .v.dim { color: var(--muted); font-weight: 600; }
  .ek i { background: linear-gradient(90deg, #8b5cf6, #c4b5fd); } .cl i { background: #6b7383; } .qw i { background: #4a5263; }
  .ei i { background: linear-gradient(90deg, #f0a92c, #ffd98a); }
  .strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 20px; }
  .stat { border: 1px solid var(--line); border-radius: 16px; padding: 13px 20px; background: rgba(255,255,255,.025);
          display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .stat .k { font-size: 16.5px; font-weight: 500; } .stat .k small { display: block; font-size: 13px; color: var(--muted); font-weight: 400; margin-top: 3px; }
  .stat .val { font-size: 29px; font-weight: 800; color: var(--v2); letter-spacing: -0.02em; white-space: nowrap; }
  .stat .val span { font-size: 15px; color: var(--muted); font-weight: 600; margin-left: 6px; }
  .links { display: flex; gap: 34px; margin-top: 18px; font-size: 17px; align-items: baseline; }
  .links span { color: var(--muted); font-size: 13.5px; letter-spacing: .08em; text-transform: uppercase; font-weight: 600; margin-right: 10px; }
  .links b { font-weight: 600; }
  .foot { position: absolute; left: 72px; right: 72px; bottom: 20px; font-size: 12px; color: var(--dim); line-height: 1.5; }
  .brand { position: absolute; top: 44px; right: 72px; display: flex; align-items: center; gap: 12px; }
  .brand .word { font-size: 24px; font-weight: 700; letter-spacing: -0.01em; }
  .brand .word b { background: linear-gradient(135deg, #818cf8 0%, #6366f1 40%, #06b6d4 100%); -webkit-background-clip: text;
                   background-clip: text; color: transparent; }
  .brand .site { font-size: 15px; color: var(--muted); text-align: right; margin-top: 2px; }
"""
cls = {"Claude Sonnet 5.5": "cl", "Ekbasis-27B": "ek", "Qwen3.8-27B reasoning": "qw", "Eikos-27B (no consequence training)": "ei"}
nm = {"Claude Sonnet 5.5": "Claude Sonnet 5.5<small>reasoning</small>", "Ekbasis-27B": "Ekbasis<small>one pass</small>",
      "Qwen3.8-27B reasoning": "Qwen3.8‑27B<small>reasoning</small>", "Eikos-27B (no consequence training)": "Eikos‑27B<small>one pass</small>"}
c1 = "".join(f'<div class="row {cls[m]}"><div class="n{"" if m == "Ekbasis-27B" else " dim"}">{nm[m]}</div><div class="bar"><i style="width:{pct(CMP[m]["git_known"]):.1f}%"></i></div>'
             f'<div class="v{"" if m == "Ekbasis-27B" else " dim"}">{pct(CMP[m]["git_known"]):.1f}</div><div class="v dim">{pct(CMP[m]["git_held"]):.1f}</div></div>' for m in rows4)
smax = max(s[1] for s in SPEED)
c3 = "".join(f'<div class="row two {"qw" if k == 0 else "ek"}"><div class="n{" dim" if k == 0 else ""}">{lab}</div><div class="bar"><i style="width:{100 * s[1] / smax:.1f}%"></i></div>'
             f'<div class="v{" dim" if k == 0 else ""}">{s[1]:.1f} s</div></div>'
             for k, (s, lab) in enumerate(zip(SPEED, ("Qwen3.8‑27B<small>reasoning</small>", "Ekbasis<small>per question</small>",
                                                      "Ekbasis<small>read once</small>", "Ekbasis‑FP8<small>read once</small>"))))
he = REP["git3_test_held"]
plan_ok = plan_ok_global
# the reasoning model on the same puzzles: the "all" row, column "A alone" (one plan, thinking on) of the LLM-agent run
_all = next(line for line in open(os.path.join(RES, "release_eval", "llm_agent_hard_score.log")) if line.startswith("all "))
plan_llm = float(_all.split("|")[1].split()[1])
INJ = ld("release_eval", "release_eval_t3c.json")["injection"]
_lc = rows("release_eval", "long_chain3.jsonl")
_g = [r for r in _lc if r["fam"] == "cards" and r["len"] == 200 and r["mode"] == "check0.9"]
_n = [r for r in _lc if r["fam"] == "cards" and r["len"] == 200 and r["mode"] == "text"]
lc_look, lc_never = f"{sum(r['state_ok'] for r in _g)}/{len(_g)}", f"{sum(r['state_ok'] for r in _n)}/{len(_n)}"
inj_missed = sum(len(d["work_losing_missed_at_0.2"]) for d in INJ.values())
html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Ekbasis</title><style>{CSS}</style></head><body>
<div class="glow"></div><div class="glow2"></div><div class="grid"></div>
<div class="brand"><svg width="40" height="40" viewBox="0 0 24 24" fill="none"><circle cx="8" cy="12" r="5" stroke="#4f46e5" stroke-width="1.5"/>
<circle cx="16" cy="12" r="5" stroke="#06b6d4" stroke-width="1.5"/><circle cx="12" cy="12" r="1.5" fill="#4f46e5"/></svg>
<div><div class="word">Open<b>Interpretability</b></div><div class="site">openinterp.org</div></div></div>
<div class="wrap">
  <div class="pills"><div class="pill">Open model · Apache‑2.0</div><div class="pill gray">27B · FP8 · INT4 · MLX</div></div>
  <div class="title"><div class="name">Ekbasis</div><div class="greek">ἔκβασις · <em>“how an action turns out”</em></div></div>
  <div class="tag">An open world model for agents. <span>Not a model that thinks, nor one that judges: a model that foresees.</span></div>
  <div class="cards">
    <div class="card hero"><div class="label">Git · 240 questions, same for all</div>
      <div class="big">{pct(ek["git_known"]):.1f}%<small>one pass, no text</small></div>
      <div class="sub">Will it lose work? fail? what will the state be? — the truth from running the commands</div>
      <div class="hdr"><div></div><div></div><div>seen</div><div>new</div></div>{c1}</div>
    <div class="card"><div class="label">The git guard · fresh real repos</div>
      <div class="big">{fl}/{sum(r["truth"]["lost"] for r in T3C)}<small>work-losing flagged</small></div>
      <div class="sub">16 scenarios written before the evaluation · {fa} false alarm in {sum(not r["truth"]["lost"] for r in T3C)}</div>
      <div class="row two ek"><div class="n">AUROC, never-seen types</div><div class="bar"><i style="width:{100 * he["lost_auroc"]:.1f}%"></i></div><div class="v">{he["lost_auroc"]:.3f}</div></div>
      <div class="row two ek"><div class="n">Caught at 0.2, never-seen</div><div class="bar"><i style="width:{he["lost_flagged_at_0.2"]:.1f}%"></i></div><div class="v">{he["lost_flagged_at_0.2"]:.0f}%</div></div>
      <div class="row two cl"><div class="n dim">False alarms at 0.2</div><div class="bar"><i style="width:{max(he["false_alarm_at_0.2"], 1):.1f}%"></i></div><div class="v dim">{he["false_alarm_at_0.2"]:.1f}%</div></div></div>
    <div class="card"><div class="label">Speed · one GPU</div>
      <div class="big">{CHECK:.2f}<small>seconds per check</small></div>
      <div class="sub">Forecast of 10–30 actions, one at a time (median)</div>{c3}
      <div class="sub" style="margin:12px 0 0">16 in parallel: {SPEED[2][2]:.0f} forecasts/min (FP8 {SPEED[3][2]:.0f}) vs {SPEED[0][2]:.1f} reasoning</div></div>
  </div>
  <div class="strip">
    <div class="stat"><div class="k">Planning with no LLM<small>180 hard puzzles, plans run for real</small></div><div class="val">{plan_ok:.1f}%<span>reasoning {plan_llm:.1f}%</span></div></div>
    <div class="stat"><div class="k">200-action chains<small>orderings: it looks when unsure</small></div><div class="val">{lc_look}<span>exact ({lc_never} never looking)</span></div></div>
    <div class="stat"><div class="k">Prompt injection<small>file, branch and commit-message planting</small></div><div class="val">{inj_missed}<span>work-losing missed</span></div></div>
  </div>
  <div class="links"><div><span>Site</span><b>openinterp.org/ekbasis</b></div><div><span>Weights &amp; data</span><b>huggingface.co/caiovicentino1</b></div><div><span>Code</span><b>github.com/OpenInterpretability/ekbasis</b></div></div>
</div>
<div class="foot">Measured by us, Oct 2026, on the release weights (pre-registered). Git: the same 240 questions for every system (120 command types seen in training, 120 never seen);
Claude models answered as batched hand-offs with shuffled order, evaluation only. Guard: 16 real-repository scenarios on a clone of pallets/itsdangerous, written before the evaluation.
Speed: one RTX PRO 6000, vLLM 0.30. Planning: beam search with Ekbasis alone, the plan run in the true simulator; Qwen3.8‑27B writing the plan while reasoning: {plan_llm:.1f}%. Chains: one action per step; a look reads the real state when the chain confidence falls below 0.9, plus a check now and then. Full results and predictions: RELEASE_EVAL.md.</div>
</body></html>"""
hp = os.path.join(HERE, "ekbasis_launch.html")
open(hp, "w").write(html)
png = os.path.join(OUT, "ekbasis_launch.png")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2", "--window-size=1600,900",
                f"--screenshot={png}", pathlib.Path(hp).as_uri()], check=True, capture_output=True, timeout=120)
print("wrote ekbasis_launch.png")
