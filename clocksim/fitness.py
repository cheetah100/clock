"""Composite fitness: stage dominance plus graded bonuses.

Score bands (higher stage always beats lower stage):
  invalid clock:        0 .. 30    (small credit per escapement connection)
  valid, stage s:       100 + 2000*s + bonus, bonus < 2000

The bonuses create a gradient *within* a stage so single mutations can make
measurable progress: growing the powered gear train, adding hands, wiring
the ratchet output, getting more hands rotating, and approaching the 60:1
target ratios. Per-pair accuracy is *summed* (not averaged) so attaching a
third hand never reduces the accuracy bonus already earned by the first
pair - otherwise two perfect hands become an inescapable local optimum.
"""

import math

from .config import Config
from .dna import ClockDNA
from .mechanics import Evaluation

STAGE_WEIGHT = 2000.0
VALID_BASE = 100.0


def escapement_links(dna: ClockDNA) -> int:
    return (
        int(dna.spring_to_ratchet)
        + int(dna.pendulum_to_ratchet)
        + int(dna.drive_cog is not None)
    )


def score(dna: ClockDNA, ev: Evaluation, config: Config) -> float:
    if not ev.valid:
        return 10.0 * escapement_links(dna)
    value = VALID_BASE + STAGE_WEIGHT * ev.stage
    value += 20.0 * min(len(ev.omegas), 5)            # powered cogs in the train
    value += 30.0 * min(len(dna.hands), 3)            # hands present (even idle)
    if dna.drive_cog is not None:
        value += 50.0
    value += 200.0 * ev.rotating_hand_count()         # hands actually turning
    value += 300.0 * sum(math.exp(-e) for e in ev.pair_errors)  # closeness to 60:1
    return value
