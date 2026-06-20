"""Analysis of the parameter-sweep results.

Reads experiments/data/results.jsonl and produces:
  - experiments/data/summary.csv / summary.json   aggregate statistics
  - experiments/figures/<sweep>.png               per-sweep result figures
  - experiments/clocks/<config>_seed<k>.{json,png} example evolved clocks

Usage:  python3 -m clocksim.analyze
"""

import json
import os
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from clocksim.config import Config
from clocksim.dna import ClockDNA
from clocksim.visualization import draw_clock
from clocksim.run_experiments import BASELINE, BASELINE_LABELS, BUDGET, SWEEPS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERIMENTS_DIR = os.path.join(_ROOT, "experiments")
DATA_DIR = os.path.join(EXPERIMENTS_DIR, "data")
FIG_DIR = os.path.join(EXPERIMENTS_DIR, "figures")
CLOCK_DIR = os.path.join(EXPERIMENTS_DIR, "clocks")

SWEEP_ORDERS = {
    "max_cog_teeth": [16, 24, 40, 60, 120],
    "max_cogs": [5, 6, 8, 12, 16],
    "max_meshes_per_cog": [2, 3, 4, 6, 8],
    "population_size": [10, 25, 50, 100, 250],
    "mutation_rate": [0.0, 0.2, 0.35, 0.6, 0.9],
    "selection": ["random", "best", "tournament-2", "tournament-4",
                  "tournament-8", "tournament-16"],
}
SWEEP_TITLES = {
    "max_cog_teeth": "Maximum cog teeth",
    "max_cogs": "Maximum cogs per clock",
    "max_meshes_per_cog": "Maximum meshes per cog",
    "population_size": "Population size",
    "mutation_rate": "Mutation rate (extra-mutation probability)",
    "selection": "Selection method",
}


def load_rows():
    rows = []
    with open(os.path.join(DATA_DIR, "results.jsonl")) as fh:
        for line in fh:
            rows.append(json.loads(line))
    return rows


def rows_for(sweep, rows):
    """Rows of one sweep, with the shared baseline runs slotted in."""
    out = {}
    for row in rows:
        if row["sweep"] == sweep:
            out.setdefault(row["value"], []).append(row)
        elif row["sweep"] == "baseline":
            out.setdefault(BASELINE_LABELS[sweep], []).append(row)
    return out


def aggregate(group):
    succ = [r for r in group if r["success"]]
    gens = sorted(r["gen_stage4"] for r in succ)
    errs = sorted(r["final_error_pct"] for r in group
                  if r["final_error_pct"] is not None)
    return {
        "runs": len(group),
        "successes": len(succ),
        "success_rate": len(succ) / len(group),
        "median_gen_stage4": statistics.median(gens) if gens else None,
        "min_gen_stage4": gens[0] if gens else None,
        "max_gen_stage4": gens[-1] if gens else None,
        "median_final_error_pct": statistics.median(errs) if errs else None,
        "mean_elapsed_s": round(statistics.mean(r["elapsed_seconds"] for r in group), 1),
        "mean_best_cogs": round(statistics.mean(r["best_cogs"] for r in group), 1),
        "mean_powered_cogs": round(
            statistics.mean(r["best_powered_cogs"] for r in group), 1),
    }


def plot_sweep(sweep, groups, order, path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    xs = range(len(order))
    labels = [str(v) for v in order]

    for x, value in zip(xs, order):
        group = groups.get(value, [])
        succ = [r["gen_stage4"] for r in group if r["success"]]
        fail_count = sum(1 for r in group if not r["success"])
        jitter = [x + (i - len(succ) / 2) * 0.04 for i in range(len(succ))]
        ax1.scatter(jitter, succ, s=22, color="#2c6fad", alpha=0.75, zorder=3)
        if succ:
            ax1.plot([x - 0.22, x + 0.22], [statistics.median(succ)] * 2,
                     color="#c0392b", lw=2, zorder=4)
        if fail_count:
            ax1.scatter([x] * fail_count, [BUDGET] * fail_count, marker="x",
                        s=46, color="#c0392b", zorder=3)

        # clamp to a display floor so a freak exact-60 run doesn't compress the axis
        errs = [max(r["final_error_pct"], 1e-3) for r in group
                if r["final_error_pct"] is not None]
        jitter = [x + (i - len(errs) / 2) * 0.04 for i in range(len(errs))]
        ax2.scatter(jitter, errs, s=22, color="#2c6fad", alpha=0.75, zorder=3)
        if errs:
            ax2.plot([x - 0.22, x + 0.22], [statistics.median(errs)] * 2,
                     color="#c0392b", lw=2, zorder=4)

    rotation = 18 if max(len(l) for l in labels) > 6 else 0
    for ax in (ax1, ax2):
        ax.set_xticks(list(xs))
        ax.set_xticklabels(labels, rotation=rotation,
                           ha="right" if rotation else "center")
        ax.set_xlabel(SWEEP_TITLES[sweep])
        ax.grid(axis="y", lw=0.3, alpha=0.5)
    ax1.set_yscale("log")
    ax1.set_ylabel("Generations to stage 4 (log)")
    ax1.set_title("Time to evolve (x = failed within %d)" % BUDGET)
    ax2.set_yscale("log")
    ax2.set_ylabel("Final mean ratio error % (log)")
    ax2.set_title("Accuracy plateau after %d generations" % BUDGET)
    fig.suptitle(SWEEP_TITLES[sweep], fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def median_seed_row(group):
    """Pick a representative run: median time-to-success, else best score."""
    succ = sorted((r for r in group if r["success"]), key=lambda r: r["gen_stage4"])
    if succ:
        return succ[len(succ) // 2]
    return max(group, key=lambda r: r["final_score"])


def export_example(sweep, value, row, config_overrides):
    config = Config()
    for key, val in BASELINE.items():
        setattr(config, key, val)
    for key, val in config_overrides.items():
        setattr(config, key, val)
    dna = ClockDNA.from_dict(row["best_dna"])
    name = "%s_%s_seed%d" % (sweep, str(value).replace(".", "p"), row["seed"])
    with open(os.path.join(CLOCK_DIR, name + ".json"), "w") as fh:
        json.dump(row["best_dna"], fh, indent=1)
    draw_clock(dna, config, os.path.join(CLOCK_DIR, name + ".png"))
    return name


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    os.makedirs(CLOCK_DIR, exist_ok=True)
    rows = load_rows()
    print("Loaded %d runs" % len(rows))

    summary = {}
    csv_lines = ["sweep,value,runs,successes,success_rate,median_gen_stage4,"
                 "min_gen_stage4,max_gen_stage4,median_final_error_pct,"
                 "mean_elapsed_s,mean_best_cogs,mean_powered_cogs"]
    examples = {}

    overrides_by_sweep_value = {
        (sweep, label): overrides
        for sweep, values in SWEEPS.items()
        for label, overrides in values
    }

    for sweep, order in SWEEP_ORDERS.items():
        groups = rows_for(sweep, rows)
        summary[sweep] = {}
        for value in order:
            group = groups.get(value, [])
            if not group:
                continue
            agg = aggregate(group)
            summary[sweep][str(value)] = agg
            csv_lines.append(
                "%s,%s,%d,%d,%.3f,%s,%s,%s,%s,%.1f,%.1f,%.1f" % (
                    sweep, value, agg["runs"], agg["successes"], agg["success_rate"],
                    agg["median_gen_stage4"], agg["min_gen_stage4"],
                    agg["max_gen_stage4"],
                    ("%.4f" % agg["median_final_error_pct"])
                    if agg["median_final_error_pct"] is not None else "",
                    agg["mean_elapsed_s"], agg["mean_best_cogs"],
                    agg["mean_powered_cogs"],
                )
            )
        plot_sweep(sweep, groups, order, os.path.join(FIG_DIR, sweep + ".png"))

        # Example clocks: extremes + baseline (baseline rendered once).
        for value in (order[0], BASELINE_LABELS[sweep], order[-1]):
            group = groups.get(value)
            if not group:
                continue
            is_baseline = value == BASELINE_LABELS[sweep]
            key = ("baseline", "baseline") if is_baseline else (sweep, value)
            if key in examples:
                continue
            overrides = overrides_by_sweep_value.get((sweep, value), {})
            row = median_seed_row(group)
            examples[key] = export_example(key[0], key[1], row, overrides)

    with open(os.path.join(DATA_DIR, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    with open(os.path.join(DATA_DIR, "summary.csv"), "w") as fh:
        fh.write("\n".join(csv_lines) + "\n")

    print("Wrote summary.csv / summary.json, %d figures, %d example clocks"
          % (len(SWEEP_ORDERS), len(examples)))
    for key, name in sorted(examples.items()):
        print("  example:", name)


if __name__ == "__main__":
    main()
