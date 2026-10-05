"""Figures of the paper, every value read from numbers.json (python3 reproduce.py first). Writes figures/*.pdf (paper)
and figures/*.png (web)."""
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
N = json.load(open(HERE / "numbers.json"))
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 9.5, "axes.titleweight": "bold", "legend.frameon": False})
BLUE, GRAY, ORANGE, GREEN, RED, PURPLE = "#2563eb", "#9ca3af", "#ea580c", "#16a34a", "#dc2626", "#7c3aed"


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def wilson(k, n, z=1.96):
    if n == 0:
        return 0, 0
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return 100 * (c - h), 100 * (c + h)


# Figure 2: consequence training cut errors and made the remaining ones confident.
ce = N["confident_errors"]
models = (("Eikos-27B (before)", ce["eikos_report"]["groups"], GRAY), ("V42 (after)", ce["report"]["groups"], BLUE))
groups = (("T", "trained\nfamilies"), ("H", "held-out\nquestions"), ("U", "never\ntrained"))
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8))
w = 0.38
for j, (label, G, color) in enumerate(models):
    for i, (g, _) in enumerate(groups):
        a = G[g]["all"]
        x = i + (j - 0.5) * w
        err = a["error_rate"]
        lo, hi = wilson(a["wrong"], a["n"])
        axes[0].bar(x, err, w, color=color, label=label if i == 0 else None)
        axes[0].errorbar(x, err, yerr=[[err - lo], [hi - err]], color="black", lw=0.8, capsize=2)
        axes[0].text(x, hi + 0.8, f"{err:.1f}", ha="center", va="bottom", fontsize=7.5)
        conf = round(a["share_wrong_conf_ge_0.9"] * a["wrong"] / 100)
        share = a["share_wrong_conf_ge_0.9"]
        lo, hi = wilson(conf, a["wrong"])
        axes[1].bar(x, share, w, color=color)
        axes[1].errorbar(x, share, yerr=[[share - lo], [hi - share]], color="black", lw=0.8, capsize=2)
        axes[1].text(x, hi + 1.5, f"{share:.1f}", ha="center", va="bottom", fontsize=7.5)
for ax in axes:
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"{g}: {d}" for g, d in groups], fontsize=7.5)
axes[0].set_ylabel("wrong answers (% of answers)")
axes[0].set_title("(a) errors")
axes[0].set_ylim(0, 48)
axes[1].set_ylabel("errors at confidence ≥ 0.9 (% of errors)")
axes[1].set_title("(b) errors made with confidence")
axes[1].set_ylim(0, 72)
axes[1].legend(*axes[0].get_legend_handles_labels(), loc="upper right", fontsize=7.5)
fig.tight_layout()
save(fig, "fig_confident_errors")

# Figure 3: the loop. (a) the rules on the same 40 chains; (b) training on errors: where the errors were mined matters.
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
ax = axes[0]
rules = N["chains"]["rules_compared"]
names = {"text": "never", "step0.9": "step < 0.9", "conf0.5": "chain < 0.5", "until0.5": "until 0.5", "check0.5": "check 0.5",
         "conf0.9": "chain < 0.9", "until0.9": "until 0.9", "check0.9": "check 0.9 (default)"}
OFF = {"text": (6, 0, "left"), "conf0.5": (-5, 6, "right"), "until0.5": (4, 6, "left"), "step0.9": (6, -9, "left"),
       "check0.5": (6, -3, "left"), "conf0.9": (-6, -4, "right"), "until0.9": (5, 5, "left"), "check0.9": (7, -1, "left")}
for m, lab in names.items():
    a = rules[m]["all"]
    default = m == "check0.9"
    ax.scatter(a["looks_per_100"], a["silent_wrong_per_100"], s=42 if default else 22, color=BLUE, zorder=3,
               edgecolor="black" if default else "none", linewidth=0.8)
    dx, dy, ha = OFF[m]
    ax.annotate(lab, (a["looks_per_100"], a["silent_wrong_per_100"]), xytext=(dx, dy), textcoords="offset points", fontsize=7,
                ha=ha, va="center", color="black" if default else "#374151", fontweight="bold" if default else "normal")
base = N.get("base_loop")
ax.set_yscale("log")
ax.set_xlabel("looks at the real state per 100 actions")
ax.set_ylabel("silent wrong steps per 100 actions")
ax.set_title("(a) when to look (same 40 chains)")
ax.set_xlim(-2, 40)
ax = axes[1]
L = N["loops"]
runs = (("r2err", "r2err", L["r2err"]["pooled"]["check0.9"], "r2err", ORANGE, (-2, 9, "center")),
        ("r3w20", "r3w20", L["r3w20"]["pooled"]["check0.9"], "r3w20", ORANGE, (6, 0, "left")),
        ("r4a", "r4a", L["r4a_confirm"]["pooled"]["check0.9"], "r4a", GREEN, (6, 0, "left")),
        ("r4b", "r4b", L["r4b_confirm"]["pooled"]["check0.9"], "r4b", GREEN, (6, 0, "left")),
        ("r4c", "r4c (chain items only)", L["r4c"]["pooled"]["check0.9"], "r4c", GREEN, (6, 0, "left")))
ax.axhline(0, color="#d1d5db", lw=0.8, zorder=1)
ax.axvline(0, color="#d1d5db", lw=0.8, zorder=1)
ax.scatter(0, 0, s=42, color=BLUE, edgecolor="black", linewidth=0.8, zorder=3)
ax.annotate("V42\n(same chains)", (0, 0), xytext=(-6, -12), textcoords="offset points", fontsize=7, ha="right")
for key, lab, d, b_, color, (dx, dy, ha) in runs:
    a, b = d["v42"], d[b_ if b_ in d else "r2err"]
    x = 100 * (b["looks_per_100"] / a["looks_per_100"] - 1)
    y = 100 * (b["wrong_per_100"] / a["wrong_per_100"] - 1)
    ax.scatter(x, y, s=26, color=color, zorder=3)
    ax.annotate(lab, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=7, ha=ha, va="center", color=color)
w5 = N.get("wise", {}).get("loop_w4a5")
if w5:  # the exact interpolation halfway back to the release model (its own fresh chains)
    a, b = w5["pooled"]["check0.9"]["v42"], w5["pooled"]["check0.9"]["w4a5"]
    x, y = 100 * (b["looks_per_100"] / a["looks_per_100"] - 1), 100 * (b["wrong_per_100"] / a["wrong_per_100"] - 1)
    ax.scatter(x, y, s=34, color=PURPLE, marker="D", zorder=4)
    ax.annotate("w4a5 (halfway back)", (x, y), xytext=(6, 9), textcoords="offset points", fontsize=7, ha="left", color=PURPLE)
ax.scatter([], [], color=ORANGE, s=22, label="mined from true states")
ax.scatter([], [], color=GREEN, s=22, label="mined inside its own chains")
if w5:
    ax.scatter([], [], color=PURPLE, marker="D", s=22, label="weight interpolation")
ax.legend(loc="center right", fontsize=7)
ax.set_xlim(-35, 95)
ax.set_ylim(-110, 45)
ax.set_xlabel("change in looks (%)")
ax.set_ylabel("change in silent wrong steps (%)")
ax.set_title("(b) training on its own errors")
fig.tight_layout()
save(fig, "fig_loop")
# Figure 4 (paper experiment A): the same chains before and after consequence training.
if base:
    modes = (("text", "never"), ("conf0.5", "chain < 0.5"), ("check0.5", "check 0.5"), ("conf0.9", "chain < 0.9"),
             ("check0.9", "check 0.9"))
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.5), gridspec_kw={"width_ratios": [1.15, 1.15, 0.8]})
    w = 0.38
    for j, (who, lab, color) in enumerate((("eikos", "Eikos-27B (before)", GRAY), ("ekbasis", "V42 (after)", BLUE))):
        xs = [i + (j - 0.5) * w for i in range(len(modes))]
        looks = [base["loop"][m][who]["looks_per_100"] for m, _ in modes]
        wrong = [base["loop"][m][who]["silent_wrong_per_100"] for m, _ in modes]
        axes[0].bar(xs, looks, w, color=color, label=lab)
        axes[1].bar(xs, [max(v, 0.005) for v in wrong], w, color=color)
        for x, v in zip(xs, looks):
            axes[0].text(x, v + 1.5, f"{v:.0f}", ha="center", va="bottom", fontsize=6.5)
        for x, v in zip(xs, wrong):
            axes[1].text(x, max(v, 0.005) * 1.15, "0" if v == 0 else (f"{v:.2f}" if v < 10 else f"{v:.0f}"), ha="center", va="bottom", fontsize=5.8)
    for ax in axes[:2]:
        ax.set_xticks(range(len(modes)))
        ax.set_xticklabels([lab for _, lab in modes], rotation=30, ha="right", fontsize=7)
    axes[0].set_ylabel("looks per 100 actions")
    axes[0].set_title("(a) looks")
    axes[0].set_ylim(0, 115)
    handles, labels = axes[0].get_legend_handles_labels()
    axes[1].set_yscale("log")
    axes[1].set_ylabel("silent wrong steps per 100 actions")
    axes[1].set_title("(b) silent wrong steps")
    tr = base["traces"]
    groups = (("trained", "containers\n+ lamps"), ("unseen", "machines\n+ cards"))
    for j, (who, color) in enumerate((("eikos", GRAY), ("ekbasis", BLUE))):
        xs = [i + (j - 0.5) * w for i in range(2)]
        vals = [100 * (tr[g][who]["share_wrong_at_0.9"] or 0) for g, _ in groups]
        axes[2].bar(xs, vals, w, color=color)
        for x, (g, _), v in zip(xs, groups, vals):
            axes[2].text(x, v + 2, f"{tr[g][who]['wrong_at_0.9']}/{tr[g][who]['wrong']}", ha="center", va="bottom", fontsize=6.5)
    axes[2].set_xticks(range(2))
    axes[2].set_xticklabels([lab for _, lab in groups], fontsize=7)
    axes[2].set_ylim(0, 118)
    axes[2].set_ylabel("wrong steps at p >= 0.9 (%)")
    axes[2].set_title("(c) confident wrong steps")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.legend(handles, labels, loc="lower center", ncol=2, fontsize=7.5)
    save(fig, "fig_parent_loop")
print("figures:", sorted(p.name for p in FIG.iterdir()))
