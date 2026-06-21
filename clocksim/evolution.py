"""The evolutionary loop: selection, elimination, reproduction, tracking."""

import json
import os
import random
import time
from typing import Callable, Dict, List, Optional, Tuple

from .config import Config
from .dna import ClockDNA
from .fitness import score, clock_mass
from .genesis import mutate, random_clock
from .mechanics import Evaluation, evaluate


class Individual:
    __slots__ = ("dna", "evaluation")

    def __init__(self, dna: ClockDNA, config: Config):
        self.dna = dna
        self.evaluation = evaluate(dna, config)
        self.evaluation.score = score(dna, self.evaluation, config)

    @property
    def score(self) -> float:
        return self.evaluation.score


def select_pair(pop: List[Individual], config: Config, rng: random.Random) -> Tuple[int, int]:
    """Return (winner_index, loser_index) according to the selection method."""
    n = len(pop)
    method = config.selection_method
    if method == "random":
        i, j = rng.sample(range(n), 2)
        return (i, j) if pop[i].score >= pop[j].score else (j, i)
    if method == "best":
        winner = max(range(n), key=lambda k: pop[k].score)
        loser = rng.choice([k for k in range(n) if k != winner])
        return winner, loser
    # tournament: winner is the best of one sample, loser the worst of another
    size = min(config.tournament_size, n)
    winner = max(rng.sample(range(n), size), key=lambda k: pop[k].score)
    loser = min(rng.sample(range(n), size), key=lambda k: pop[k].score)
    if loser == winner:
        loser = rng.choice([k for k in range(n) if k != winner])
    return winner, loser


def population_snapshot(generation: int, pop: List[Individual]) -> Dict:
    stage_counts = [0, 0, 0, 0, 0]
    hand_counts = [0, 0, 0, 0]
    pair_errors = []
    best = max(pop, key=lambda ind: ind.score)
    for ind in pop:
        stage_counts[ind.evaluation.stage] += 1
        hand_counts[min(ind.evaluation.rotating_hand_count(), 3)] += 1
        if ind.evaluation.pair_errors:
            pair_errors.append(
                sum(ind.evaluation.pair_errors) / len(ind.evaluation.pair_errors)
            )
    return {
        "generation": generation,
        "best_score": best.score,
        "best_stage": best.evaluation.stage,
        "mean_score": sum(ind.score for ind in pop) / len(pop),
        "stage_counts": stage_counts,
        "hand_counts": hand_counts,
        "mean_pair_error": (sum(pair_errors) / len(pair_errors)) if pair_errors else None,
        "clocks_with_ratios": len(pair_errors),
        "mean_mass": sum(clock_mass(ind.dna) for ind in pop) / len(pop),
        "best_mass": clock_mass(best.dna),
    }


class EvolutionEngine:
    """A resumable, observable evolution run.

    The engine's state (generation counter, snapshot and improvement lists)
    may be read from other threads while ``run`` executes: the lists are
    append-only and their entries are never mutated after creation.
    """

    def __init__(self, config: Config):
        self.config = config
        self.rng = random.Random(config.random_seed)
        self.started = time.time()
        self.elapsed = 0.0
        self.finished = False
        self.generation = 0
        self.success_generation = None

        self.pop = [
            Individual(random_clock(self.rng, config), config)
            for _ in range(config.population_size)
        ]
        best = max(self.pop, key=lambda ind: ind.score)
        self.best_dna = best.dna.clone()
        self.best_eval = best.evaluation
        self.snapshots = [population_snapshot(0, self.pop)]
        self.improvements = [self._improvement_entry(0)]

    def _improvement_entry(self, generation: int) -> Dict:
        return {
            "generation": generation,
            "score": self.best_eval.score,
            "stage": self.best_eval.stage,
            "rotating_hands": self.best_eval.rotating_hand_count(),
            "accurate": self.best_eval.accurate,
            "ratios": list(self.best_eval.ratios),
            "dna": self.best_dna.to_dict(),
        }

    @property
    def success(self) -> bool:
        # A "working clock": three hands turning at the target ratios within tolerance.
        return self.best_eval.accurate

    def run(
        self,
        should_stop: Optional[Callable[[], bool]] = None,
        on_improvement: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        config = self.config
        for generation in range(self.generation + 1, config.generations_per_run + 1):
            if should_stop is not None and should_stop():
                break
            self.generation = generation
            winner_idx, loser_idx = select_pair(self.pop, config, self.rng)
            child = Individual(mutate(self.pop[winner_idx].dna, self.rng, config), config)
            self.pop[loser_idx] = child

            if child.score > self.best_eval.score:
                self.best_dna = child.dna.clone()
                self.best_eval = child.evaluation
                entry = self._improvement_entry(generation)
                self.improvements.append(entry)
                if on_improvement is not None:
                    on_improvement(entry)

            if generation % config.visualization_frequency == 0:
                self.snapshots.append(population_snapshot(generation, self.pop))

            if self.success and config.stop_on_success:
                self.success_generation = generation
                break

        if self.snapshots[-1]["generation"] != self.generation:
            self.snapshots.append(population_snapshot(self.generation, self.pop))
        self.elapsed = time.time() - self.started
        self.finished = True

    def history(self) -> Dict:
        elapsed = self.elapsed if self.finished else time.time() - self.started
        result = {
            "generations_run": self.generation,
            "elapsed_seconds": round(elapsed, 2),
            "success": self.success,
            "success_generation": self.success_generation,
            "best_score": self.best_eval.score,
            "best_stage": self.best_eval.stage,
            "best_summary": self.best_eval.summary(),
        }
        return {
            "config": self.config.to_dict(),
            "result": result,
            "snapshots": list(self.snapshots),
            "improvements": list(self.improvements),
            "best_clock": self.best_dna.to_dict(),
        }


def run_evolution(config: Config, out_dir: str, quiet: bool = False) -> Dict:
    """Run a full evolutionary simulation; write history, best DNA and plots."""
    os.makedirs(out_dir, exist_ok=True)

    def log(message):
        if not quiet:
            print(message, flush=True)

    engine = EvolutionEngine(config)
    log("Initial population: best score %.1f (stage %d)"
        % (engine.best_eval.score, engine.best_eval.stage))

    def announce(entry):
        log("gen %7d: new best score %.1f (stage %d, %d rotating hands, ratios %s)" % (
            entry["generation"], entry["score"], entry["stage"],
            entry["rotating_hands"], ["%.2f" % r for r in entry["ratios"]],
        ))

    engine.run(on_improvement=announce)
    if engine.success:
        log("gen %7d: SUCCESS - three-handed clock with correct ratios evolved"
            % engine.generation)

    history = engine.history()
    with open(os.path.join(out_dir, "history.json"), "w") as fh:
        json.dump(history, fh, indent=1)
    with open(os.path.join(out_dir, "best_clock.json"), "w") as fh:
        json.dump(history["best_clock"], fh, indent=1)

    from .visualization import draw_clock, plot_history
    plot_history(history, out_dir)
    draw_clock(engine.best_dna, config, os.path.join(out_dir, "best_clock.png"))

    log("Done in %.1fs after %d generations. Best: score %.1f, stage %d. Output in %s/"
        % (history["result"]["elapsed_seconds"], engine.generation,
           engine.best_eval.score, engine.best_eval.stage, out_dir))
    return history
