"""Creation of random clocks and DNA mutation operators."""

import math
import random
from typing import Optional

from .config import Config
from .dna import ClockDNA, Cog, Hand, Mesh, Pendulum, Ratchet, INNER, OUTER, SURFACES

MAX_HANDS = 3

# Steps used for tooth-count tweaks: mostly fine adjustments, occasionally bold.
TOOTH_STEPS = [1, 1, 1, 2, 2, 3, 5, 8, 13]


def random_cog(dna: ClockDNA, rng: random.Random, config: Config) -> Cog:
    outer = rng.randint(config.min_cog_teeth + config.min_inner_outer_gap, config.max_cog_teeth)
    inner = rng.randint(config.min_cog_teeth, outer - config.min_inner_outer_gap)
    return Cog(id=dna.new_id("c"), outer_teeth=outer, inner_teeth=inner)


def random_hand(dna: ClockDNA, rng: random.Random, config: Config) -> Optional[Hand]:
    if not dna.cogs:
        return None
    cog = rng.choice(dna.cogs)
    surface = rng.choice(SURFACES)
    radius = cog.radius(surface, config.tooth_module)
    return Hand(
        id=dna.new_id("h"),
        length=rng.uniform(0.5, 1.5) * radius,
        cog_id=cog.id,
        surface=surface,
        attachment_radius=rng.uniform(0.0, radius),
    )


def random_clock(rng: random.Random, config: Config) -> ClockDNA:
    dna = ClockDNA(
        ratchet=Ratchet(teeth=rng.randint(config.min_ratchet_teeth, config.max_ratchet_teeth)),
        pendulum=Pendulum(length=rng.uniform(0.1, 2.0)),
        spring_to_ratchet=rng.random() < 0.6,
        pendulum_to_ratchet=rng.random() < 0.6,
    )
    for _ in range(rng.randint(1, 4)):
        dna.cogs.append(random_cog(dna, rng, config))
    # Sparsely mesh later cogs back onto earlier ones.
    for i, cog in enumerate(dna.cogs[1:], start=1):
        if rng.random() < 0.6:
            partner = rng.choice(dna.cogs[:i])
            if dna.cog_mesh_count(partner.id) < config.max_meshes_per_cog:
                dna.meshes.append(
                    Mesh(
                        cog_a=partner.id,
                        surface_a=rng.choice(SURFACES),
                        cog_b=cog.id,
                        surface_b=rng.choice(SURFACES),
                    )
                )
    if rng.random() < 0.7:
        cog = rng.choice(dna.cogs)
        dna.drive_cog = cog.id
        dna.drive_surface = rng.choice(SURFACES)
    for _ in range(rng.randint(0, 2)):
        hand = random_hand(dna, rng, config)
        if hand:
            dna.hands.append(hand)
    return dna


# ---------------------------------------------------------------------------
# Mutation operators. Each returns True if it changed the DNA.
# ---------------------------------------------------------------------------

def _tweak_teeth(value: int, low: int, high: int, rng: random.Random) -> int:
    step = rng.choice(TOOTH_STEPS) * rng.choice((-1, 1))
    return max(low, min(high, value + step))


def mut_cog_teeth(dna, rng, config):
    if not dna.cogs:
        return False
    cog = rng.choice(dna.cogs)
    gap = config.min_inner_outer_gap
    if rng.random() < 0.5:
        cog.outer_teeth = _tweak_teeth(
            cog.outer_teeth, cog.inner_teeth + gap, config.max_cog_teeth, rng
        )
    else:
        cog.inner_teeth = _tweak_teeth(
            cog.inner_teeth, config.min_cog_teeth, cog.outer_teeth - gap, rng
        )
    return True


def mut_pendulum_length(dna, rng, config):
    factor = math.exp(rng.gauss(0.0, 0.2))
    dna.pendulum.length = max(0.01, min(5.0, dna.pendulum.length * factor))
    return True


def mut_ratchet_teeth(dna, rng, config):
    dna.ratchet.teeth = _tweak_teeth(
        dna.ratchet.teeth, config.min_ratchet_teeth, config.max_ratchet_teeth, rng
    )
    return True


def mut_add_cog(dna, rng, config):
    if len(dna.cogs) >= config.max_cogs:
        return False
    cog = random_cog(dna, rng, config)
    dna.cogs.append(cog)
    partners = [c for c in dna.cogs if c.id != cog.id
                and dna.cog_mesh_count(c.id) < config.max_meshes_per_cog]
    if partners and rng.random() < 0.8:
        partner = rng.choice(partners)
        dna.meshes.append(
            Mesh(
                cog_a=partner.id,
                surface_a=rng.choice(SURFACES),
                cog_b=cog.id,
                surface_b=rng.choice(SURFACES),
            )
        )
    return True


def mut_remove_cog(dna, rng, config):
    if len(dna.cogs) <= 1:
        return False
    cog = rng.choice(dna.cogs)
    dna.cogs = [c for c in dna.cogs if c.id != cog.id]
    dna.meshes = [m for m in dna.meshes if not m.involves(cog.id)]
    if dna.drive_cog == cog.id:
        dna.drive_cog = None
        dna.drive_surface = None
    for hand in list(dna.hands):
        if hand.cog_id == cog.id:
            replacement = rng.choice(dna.cogs)
            hand.cog_id = replacement.id
            hand.attachment_radius = min(
                hand.attachment_radius,
                replacement.radius(hand.surface, config.tooth_module),
            )
    return True


def mut_add_hand(dna, rng, config):
    if len(dna.hands) >= MAX_HANDS:
        return False
    hand = random_hand(dna, rng, config)
    if hand is None:
        return False
    dna.hands.append(hand)
    return True


def mut_remove_hand(dna, rng, config):
    if not dna.hands:
        return False
    dna.hands.remove(rng.choice(dna.hands))
    return True


def mut_move_hand(dna, rng, config):
    if not dna.hands or not dna.cogs:
        return False
    hand = rng.choice(dna.hands)
    cog = rng.choice(dna.cogs)
    hand.cog_id = cog.id
    hand.surface = rng.choice(SURFACES)
    hand.attachment_radius = rng.uniform(0.0, cog.radius(hand.surface, config.tooth_module))
    return True


def mut_hand_length(dna, rng, config):
    if not dna.hands:
        return False
    hand = rng.choice(dna.hands)
    hand.length = max(1.0, hand.length * math.exp(rng.gauss(0.0, 0.2)))
    return True


def mut_add_mesh(dna, rng, config):
    candidates = [c for c in dna.cogs if dna.cog_mesh_count(c.id) < config.max_meshes_per_cog]
    if len(candidates) < 2:
        return False
    existing = dna.meshed_pairs()
    rng.shuffle(candidates)
    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            if frozenset((a.id, b.id)) in existing:
                continue
            dna.meshes.append(
                Mesh(
                    cog_a=a.id,
                    surface_a=rng.choice(SURFACES),
                    cog_b=b.id,
                    surface_b=rng.choice(SURFACES),
                )
            )
            return True
    return False


def mut_remove_mesh(dna, rng, config):
    if not dna.meshes:
        return False
    dna.meshes.remove(rng.choice(dna.meshes))
    return True


def mut_rewire_mesh(dna, rng, config):
    removed = mut_remove_mesh(dna, rng, config)
    added = mut_add_mesh(dna, rng, config)
    return removed or added


def mut_toggle_spring(dna, rng, config):
    dna.spring_to_ratchet = not dna.spring_to_ratchet
    return True


def mut_toggle_pendulum(dna, rng, config):
    dna.pendulum_to_ratchet = not dna.pendulum_to_ratchet
    return True


def mut_set_drive(dna, rng, config):
    if not dna.cogs:
        return False
    if dna.drive_cog is not None and rng.random() < 0.1:
        dna.drive_cog = None
        dna.drive_surface = None
        return True
    cog = rng.choice(dna.cogs)
    dna.drive_cog = cog.id
    dna.drive_surface = rng.choice(SURFACES)
    return True


MUTATIONS = {
    "cog_teeth": mut_cog_teeth,
    "pendulum_length": mut_pendulum_length,
    "ratchet_teeth": mut_ratchet_teeth,
    "add_cog": mut_add_cog,
    "remove_cog": mut_remove_cog,
    "add_hand": mut_add_hand,
    "remove_hand": mut_remove_hand,
    "move_hand": mut_move_hand,
    "hand_length": mut_hand_length,
    "add_mesh": mut_add_mesh,
    "remove_mesh": mut_remove_mesh,
    "rewire_mesh": mut_rewire_mesh,
    "toggle_spring": mut_toggle_spring,
    "toggle_pendulum": mut_toggle_pendulum,
    "set_drive": mut_set_drive,
}


def _apply_one(dna: ClockDNA, rng: random.Random, config: Config) -> None:
    names = list(MUTATIONS.keys())
    weights = [config.mutation_weights.get(name, 1.0) for name in names]
    for _ in range(10):  # retry if the chosen operator is not applicable
        name = rng.choices(names, weights=weights, k=1)[0]
        if MUTATIONS[name](dna, rng, config):
            return


def mutate(dna: ClockDNA, rng: random.Random, config: Config) -> ClockDNA:
    """Return a mutated copy: one guaranteed mutation, plus extra mutations
    with probability ``mutation_rate`` each (capped at 4 extras)."""
    child = dna.clone()
    _apply_one(child, rng, config)
    extras = 0
    while extras < 4 and rng.random() < config.mutation_rate:
        _apply_one(child, rng, config)
        extras += 1
    return child
