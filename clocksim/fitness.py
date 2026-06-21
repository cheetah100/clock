"""Composite fitness: stage dominance, continuous accuracy, and material cost.

Score bands (higher stage always beats lower stage):
  invalid clock:        0 .. 30    (small credit per escapement connection)
  valid, stage s:       100 + 2000*s + bonus, bonus < 2000

Stage is structural capability only (escapement + one per rotating hand), so it
is a clean staircase that single mutations climb. *Within* a stage the bonus is
a smooth surface with no cliffs:

  * small structural gradients (powered cogs, hands present, wired ratchet) so
    early mutations make measurable progress;
  * a *continuous* accuracy reward `ACCURACY_WEIGHT * sum(pair_closeness)`, where
    pair_closeness = 1/(1+|ln(ratio/target)|) keeps pulling at any distance and
    peaks (but never jumps) as the ratios approach their targets (60 then 12).
    It is *summed* per pair (not averaged) so attaching a third hand never erases
    the accuracy already earned by the first pair;
  * a material reward `material_weight * lightness` that favours lighter clocks,
    where mass is the sum of outer_teeth^2 over *all* cogs - so a redundant
    unpowered cog is pure dead weight and evolution is pressured to prune it;
  * a direction reward `direction_weight * codirectional` that favours hands all
    turning the same way as the fastest one. A counter-rotating hand is mechanically
    valid (each mesh reverses direction) but un-clocklike; this prices it in
    without forbidding it, so evolution drifts toward all-clockwise faces.

The whole within-stage bonus is clamped below the 2000 stage step, so a clock
with more correctly turning hands always outranks one with fewer; the accuracy,
material and direction terms only trade against each other *within* a stage.
"""

from .config import Config
from .dna import ClockDNA
from .mechanics import Evaluation

STAGE_WEIGHT = 2000.0
VALID_BASE = 100.0
ACCURACY_WEIGHT = 600.0   # per pair; max ~1200 over two pairs, below the stage step


def escapement_links(dna: ClockDNA) -> int:
    return (
        int(dna.spring_to_ratchet)
        + int(dna.pendulum_to_ratchet)
        + int(dna.drive_cog is not None)
    )


def clock_mass(dna: ClockDNA) -> float:
    """Total cog mass: every cog modelled as a solid metal disk of its outer
    radius, so mass is proportional to outer_teeth^2, summed over *all* cogs
    (powered or not)."""
    return sum(c.outer_teeth ** 2 for c in dna.cogs)


def material_lightness(dna: ClockDNA, config: Config) -> float:
    """0..1 reward for a light clock: 1 is massless, 0 the worst-case fleet of
    max_cogs cogs each at max teeth."""
    if not dna.cogs:
        return 1.0
    worst = config.max_cogs * (config.max_cog_teeth ** 2)
    return max(0.0, 1.0 - clock_mass(dna) / worst)


def score(dna: ClockDNA, ev: Evaluation, config: Config) -> float:
    if not ev.valid:
        return 10.0 * escapement_links(dna)
    bonus = 20.0 * min(len(ev.omegas), 5)             # powered cogs in the train
    bonus += 30.0 * min(len(dna.hands), 3)            # hands present (even idle)
    if dna.drive_cog is not None:
        bonus += 50.0
    bonus += ACCURACY_WEIGHT * sum(ev.pair_closeness)  # continuous closeness to targets
    bonus += config.material_weight * material_lightness(dna, config)
    bonus += config.direction_weight * ev.codirectional  # hands turning the same way
    # Clamp the within-stage bonus below one stage step so a higher stage (more
    # rotating hands) always wins, whatever the configured weights.
    return VALID_BASE + STAGE_WEIGHT * ev.stage + min(bonus, STAGE_WEIGHT - 1.0)
