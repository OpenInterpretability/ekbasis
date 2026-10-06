"""Figures for the write-up, drawn only from numbers.json (run numbers.py first).
  fig_agents: harmful and safe-success runs per agent on the 30 hidden-consequence tasks of the fresh set, alone vs with
              Ekbasis (dumbbells; one hue, two shades: light = alone, dark = with Ekbasis)
  fig_cost:   US$ per run on all 35 fresh tasks, Claude agents alone vs with Ekbasis
  fig_realapps: harmful runs on the real self-hosted apps, per agent and condition
  fig_ra2:    the follow-up on fresh real-app tasks: harmful runs and safe success of Haiku per guard condition
    python3 figures.py -> figures/fig_agents.{pdf,png}, figures/fig_cost.{pdf,png}, figures/fig_realapps.{pdf,png},
                          figures/fig_ra2.{pdf,png}"""
import json
import os

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
N = json.load(open(os.path.join(HERE, "numbers.json")))

# reference palette (dataviz skill): ordinal blue ramp, validated (--ordinal, light): step 250 and step 550
ALONE, WITH = "#86b6ef", "#1c5cab"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
                     "xtick.color": MUTED, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.spines.left": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE, "pdf.fonttype": 42, "ps.fonttype": 42})   # embed TrueType, not Type 3


def dumbbell(ax, rows, key, title):
    ys = list(range(len(rows)))[::-1]
    for y, r in zip(ys, rows):
        a, w = 100 * r["alone"][f"{key}_rate"], 100 * r["with"][f"{key}_rate"]
        ax.plot([a, w], [y, y], color=AXIS, lw=2, zorder=1, solid_capstyle="round")
        ax.scatter([a], [y], s=60, color=ALONE, zorder=3, edgecolor=SURFACE, linewidth=2)
        ax.scatter([w], [y], s=60, color=WITH, zorder=3, edgecolor=SURFACE, linewidth=2)
        ax.text(107, y, f"{r['alone'][key]} → {r['with'][key]}", va="center", ha="left", fontsize=7.5, color=INK2,
                clip_on=False)
    ax.set_yticks(ys)
    ax.set_yticklabels([r["agent"] for r in rows], fontsize=8)
    ax.set_xlim(-3, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_title(title, loc="left", fontsize=9, color=INK, pad=8)


def fig_agents():
    rows = N["agents_table"]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.3), gridspec_kw={"wspace": 1.05})
    dumbbell(axes[0], rows, "harm", "Harmful runs (lower is better)")
    dumbbell(axes[1], rows, "success", "Task done the safe way (higher is better)")
    axes[1].set_yticklabels([])
    h1 = axes[0].scatter([], [], s=60, color=ALONE, label="agent alone")
    h2 = axes[0].scatter([], [], s=60, color=WITH, label="agent + Ekbasis")
    fig.legend(handles=[h1, h2], loc="upper center", ncol=2, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 1.04))
    fig.text(0.01, -0.04, "30 tasks whose harmful consequence the screen does not show (fresh set, 5 apps). Runs per task: "
             "Sonnet and Qwen 2, the others 1. Right of each row: runs alone → with Ekbasis.", fontsize=7, color=MUTED)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"fig_agents.{ext}"), bbox_inches="tight", dpi=200)
    plt.close(fig)


def fig_cost():
    c = N["cost_per_run_all35"]
    groups = [("Claude Sonnet 5.5", "sonnet"), ("Claude Haiku 4.5\n(default thinking)", "haiku_default"),
              ("Claude Haiku 4.5\n(thinking off)", "haiku_nothink")]
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    h = 0.34
    for i, (label, key) in enumerate(groups):
        y = len(groups) - 1 - i
        a, w = c[f"{key}_blind"], c[f"{key}_see"]
        ax.barh(y + h / 2 + 0.01, a, height=h, color=ALONE)
        ax.barh(y - h / 2 - 0.01, w, height=h, color=WITH)
        ax.text(a + 0.0004, y + h / 2 + 0.01, f"${a:.4f}", va="center", fontsize=7.5, color=INK2)
        ax.text(w + 0.0004, y - h / 2 - 0.01, f"${w:.4f}", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(range(len(groups))[::-1])
    ax.set_yticklabels([g for g, _ in groups], fontsize=8)
    ax.set_xlim(0, 0.03)
    ax.set_xticks([0, 0.01, 0.02, 0.03])
    ax.set_xticklabels(["$0", "$0.01", "$0.02", "$0.03"])
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Claude spend per run, 35 fresh tasks (US$)", loc="left", fontsize=9, color=INK, pad=8)
    ax.legend(handles=[Patch(color=ALONE, label="agent alone"), Patch(color=WITH, label="agent + Ekbasis")],
              loc="lower right", frameon=False, fontsize=8)
    fig.text(0.01, -0.06, "Ekbasis itself is self-hosted and has no per-call API charge; its GPU time is not priced here.",
             fontsize=7, color=MUTED)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"fig_cost.{ext}"), bbox_inches="tight", dpi=200)
    plt.close(fig)


def fig_realapps():
    t = N["ra"]["table"]
    rows = [("Claude Sonnet 5.5 alone (2 runs/task)", "sonnet|blind", False), ("Sonnet + Ekbasis, see (1 run/task)", "sonnet|see", True),
            ("Sonnet + guard, exploratory (1 run/task)", "sonnet|guard", True), ("Claude Haiku 4.5 alone (2 runs/task)", "haiku0|blind", False),
            ("Haiku + Ekbasis, see (2 runs/task)", "haiku0|see", True), ("Haiku + guard (2 runs/task)", "haiku0|guard", True),
            ("Haiku + guard_goal, exploratory (2 runs/task)", "haiku0|guard_goal", True)]
    fig, ax = plt.subplots(figsize=(7.4, 3.1))
    ys = list(range(len(rows)))[::-1]
    for y, (label, key, ek) in zip(ys, rows):
        v = float(t[key]["harm"].rstrip("%"))
        ax.barh(y, v, height=0.62, color=WITH if ek else "#b9b7af")
        ax.text(v + 1.0, y, t[key]["harm"], va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8)
    ax.set_xlim(0, 80)
    ax.set_xticks([0, 20, 40, 60, 80])
    ax.set_xticklabels(["0%", "20%", "40%", "60%", "80%"])
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Harmful runs on real self-hosted apps (24 tasks)", loc="left", fontsize=9, color=INK, pad=8)
    ax.legend(handles=[Patch(color="#b9b7af", label="agent alone"), Patch(color=WITH, label="with Ekbasis")],
              loc="upper right", frameon=False, fontsize=8)
    fig.text(0.01, -0.06, "Gitea, Nextcloud and Roundcube, unmodified, in a real browser; truth from the apps. Rates are means over tasks.",
             fontsize=7, color=MUTED)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"fig_realapps.{ext}"), bbox_inches="tight", dpi=200)
    plt.close(fig)


def fig_ra2():
    t = N["ra2"]["table"]
    ASK = "#8f8d86"
    rows = [("Haiku alone (blind)", "haiku0|blind", "#b9b7af"), ("pause with the forecast (guard)", "haiku0|guard", WITH),
            ("guard + one generic request question (guard_goal)", "haiku0|guard_goal", WITH),
            ("request-aware checks + checked safer way (guard_alt)", "haiku0|guard_alt", WITH),
            ("guard_alt, or ask the user (ask_ekbasis)", "haiku0|ask_ekbasis", WITH),
            ("ask the user every time, no forecast (ask_always)", "haiku0|ask_always", ASK)]
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 6.4), gridspec_kw={"hspace": 0.55})
    ys = list(range(len(rows)))[::-1]
    for ax, key, title in ((axes[0], "harm", "Harmful runs (lower is better)"), (axes[1], "success", "Task done the safe way (higher is better)")):
        for y, (label, k, col) in zip(ys, rows):
            v = float(t[k][key].rstrip("%"))
            ax.barh(y, v, height=0.66, color=col)
            ax.text(v + 1.5, y, t[k][key], va="center", fontsize=9.5, color=INK2)
        ax.set_xlim(0, 112)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=9)
        ax.xaxis.grid(True, color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        ax.set_yticks(ys)
        ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
        ax.set_title(title, loc="left", fontsize=10.5, color=INK, pad=8)
    fig.legend(handles=[Patch(color="#b9b7af", label="agent alone"), Patch(color=WITH, label="guard with Ekbasis"),
                        Patch(color=ASK, label="asks the user before every consequential click")],
               loc="upper center", ncol=2, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 1.02))
    fig.text(0.01, -0.03, "Claude Haiku 4.5 (thinking off), 24 fresh harm tasks on real Gitea, Nextcloud and Roundcube, 2 runs per\n"
             "task; rates are means over tasks. The user is simulated by a script written with each task.",
             fontsize=8.5, color=MUTED)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"fig_ra2.{ext}"), bbox_inches="tight", dpi=200)
    plt.close(fig)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fig_agents()
    fig_cost()
    fig_realapps()
    fig_ra2()
    print("figures written to", OUT)
