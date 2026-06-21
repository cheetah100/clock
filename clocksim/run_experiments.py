"""Parameter-sweep experiments for the Clock Evolution Simulator.

One-factor-at-a-time sweeps from a baseline (the spec defaults), 8 seeds per
configuration, fixed 100,000-generation budget with stop_on_success disabled,
so every run measures both time-to-evolve and the accuracy plateau reached
with the remaining budget.

Usage:  python3 -m clocksim.run_experiments [--smoke]
Output: experiments/data/results.jsonl  (one JSON record per run)
"""

import argparse
import json
import multiprocessing
import os
import time

from clocksim.config import Config
from clocksim.evolution import EvolutionEngine
from clocksim.fitness import clock_mass
from clocksim.mechanics import TARGET_RATIOS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_ROOT, "experiments", "data")
BUDGET = 100000   # 5x the baseline median time-to-solve, so a run still failing here is stuck, not timed out
SEEDS = list(range(8))

BASELINE = {
    "max_cog_teeth": 120,
    "max_cogs": 12,
    "max_meshes_per_cog": 2,
    "material_weight": 100.0,
    "population_size": 100,
    "mutation_rate": 0.35,
    "selection_method": "tournament",
    "tournament_size": 4,
    "generations_per_run": BUDGET,
    "visualization_frequency": 250,
    "stop_on_success": False,
}

# sweep name -> list of (value_label, config overrides). The baseline value of
# each sweep is NOT repeated here; analysis reuses the shared baseline runs.
SWEEPS = {
    "max_cog_teeth": [(v, {"max_cog_teeth": v}) for v in (16, 24, 40, 60)],
    "max_cogs": [(v, {"max_cogs": v}) for v in (5, 6, 8, 16)],
    "max_meshes_per_cog": [(v, {"max_meshes_per_cog": v}) for v in (3, 4, 6, 8)],
    "material_weight": [(v, {"material_weight": v}) for v in (0.0, 50.0, 200.0, 400.0)],
    "population_size": [(v, {"population_size": v}) for v in (10, 25, 50, 250)],
    "mutation_rate": [(v, {"mutation_rate": v}) for v in (0.0, 0.2, 0.6, 0.9)],
    "selection": [
        ("random", {"selection_method": "random"}),
        ("best", {"selection_method": "best"}),
        ("tournament-2", {"tournament_size": 2}),
        ("tournament-8", {"tournament_size": 8}),
        ("tournament-16", {"tournament_size": 16}),
    ],
}

# The baseline's label within each sweep, used by the analysis script.
BASELINE_LABELS = {
    "max_cog_teeth": 120,
    "max_cogs": 12,
    "max_meshes_per_cog": 2,
    "material_weight": 100.0,
    "population_size": 100,
    "mutation_rate": 0.35,
    "selection": "tournament-4",
}


def make_config(overrides, seed):
    config = Config()
    for key, value in BASELINE.items():
        setattr(config, key, value)
    for key, value in overrides.items():
        setattr(config, key, value)
    config.random_seed = seed
    config.validate()
    return config


def run_task(task):
    sweep, label, overrides, seed = task
    config = make_config(overrides, seed)
    started = time.time()
    engine = EvolutionEngine(config)
    engine.run()
    elapsed = time.time() - started

    # First generation at which the best clock became a working (accurate) clock.
    gen_success = next(
        (e["generation"] for e in engine.improvements if e.get("accurate")), None
    )

    ratios = list(engine.best_eval.ratios)
    error_pct = [abs(r - TARGET_RATIOS[i]) / TARGET_RATIOS[i] * 100.0
                 for i, r in enumerate(ratios)]
    total_mass = clock_mass(engine.best_dna)
    return {
        "sweep": sweep,
        "value": label,
        "seed": seed,
        "budget": config.generations_per_run,
        "elapsed_seconds": round(elapsed, 2),
        "success": engine.success,
        "gen_success": gen_success,
        "final_score": engine.best_eval.score,
        "final_stage": engine.best_eval.stage,
        "final_ratios": ratios,
        "final_error_pct": (sum(error_pct) / len(error_pct)) if error_pct else None,
        "best_cogs": len(engine.best_dna.cogs),
        "best_powered_cogs": len(engine.best_eval.omegas),
        "best_total_mass": total_mass,
        "improvement_count": len(engine.improvements),
        "best_dna": engine.best_dna.to_dict(),
    }


def build_tasks(smoke=False, only=None):
    tasks = [("baseline", "baseline", {}, seed) for seed in SEEDS]
    for sweep, values in SWEEPS.items():
        if only and sweep not in only:
            continue
        for label, overrides in values:
            for seed in SEEDS:
                tasks.append((sweep, label, overrides, seed))
    if smoke:
        tasks = [t for t in tasks if t[3] == 0][:3]
    return tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="tiny sanity run")
    parser.add_argument("--workers", type=int, default=multiprocessing.cpu_count() - 2)
    parser.add_argument("--sweeps", nargs="+", help="run only these sweeps (plus baseline)")
    parser.add_argument("--out", help="output filename under the data dir")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    default_name = "results_smoke.jsonl" if args.smoke else "results.jsonl"
    out_path = os.path.join(DATA_DIR, args.out or default_name)
    tasks = build_tasks(args.smoke, only=args.sweeps)
    if args.smoke:
        tasks = [(sweep, label, dict(overrides, generations_per_run=2000), seed)
                 for sweep, label, overrides, seed in tasks]
    print("Running %d tasks on %d workers -> %s" % (len(tasks), args.workers, out_path),
          flush=True)

    started = time.time()
    with open(out_path, "w") as fh:
        with multiprocessing.Pool(args.workers) as pool:
            for i, record in enumerate(pool.imap_unordered(run_task, tasks), 1):
                fh.write(json.dumps(record) + "\n")
                fh.flush()
                print("[%3d/%d] %-16s %-12s seed %d: %s%s, err %s, %d cogs, %.0fs" % (
                    i, len(tasks), record["sweep"], str(record["value"]), record["seed"],
                    "OK" if record["success"] else "stage %d" % record["final_stage"],
                    (" @gen %d" % record["gen_success"]) if record["gen_success"] else "",
                    ("%.3f%%" % record["final_error_pct"])
                    if record["final_error_pct"] is not None else "n/a",
                    record["best_cogs"],
                    record["elapsed_seconds"],
                ), flush=True)
    print("All done in %.1f minutes." % ((time.time() - started) / 60.0), flush=True)


if __name__ == "__main__":
    main()
