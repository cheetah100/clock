"""Clock mechanics: rotation propagation, spatial layout, physical validation
and functional staging.

Physical model
--------------
* The pendulum swings at its natural frequency f = sqrt(g/L) / 2*pi.
* Each full oscillation releases one ratchet tooth, so the ratchet wheel
  turns at f / teeth revolutions per second.
* The ratchet's wheel meshes with one cog surface (the "drive" connection);
  from there rotation propagates through the mesh graph. An external mesh
  reverses direction and scales angular speed by the radius ratio of the
  two meshing surfaces. Both surfaces of a cog rotate together.
* Because every toothed surface uses the same tooth module
  (radius = teeth * module / 2), tooth pitch is automatically compatible
  wherever two surfaces mesh.

Spatial validation (2D with axial depth)
----------------------------------------
Like a real movement, cogs stack along the arbor axis: each mesh step moves
one depth level further from the ratchet. Two cogs can only collide if they
sit at the same depth; meshing distance between centres must equal the sum
of the two engaged surface radii. A mesh that closes a cycle must agree
with the already-fixed positions, otherwise the train is geometrically
inconsistent. A cycle whose gear ratios disagree is a rotational deadlock.

Cogs that are not reachable from the drive train carry no power, are parked
outside the movement, and are exempt from collision checks.
"""

import math
from typing import Dict, List, Optional, Tuple

from .config import Config
from .dna import ClockDNA, INNER, OUTER

G = 9.80665
TWO_PI = 2.0 * math.pi
TARGET_RATIO = 60.0


def pendulum_frequency(length: float) -> float:
    """Natural swing frequency in Hz for a simple pendulum."""
    return math.sqrt(G / max(length, 1e-6)) / TWO_PI


class Evaluation:
    """Result of simulating and validating one clock DNA."""

    def __init__(self):
        self.valid = True
        self.reason = None            # why invalid, if invalid
        self.escapement = False       # spring+pendulum coupled to ratchet
        self.stage = 0
        self.omegas = {}              # cog_id -> signed rev/sec
        self.positions = {}           # cog_id (and "ratchet") -> (x, y)
        self.depths = {}              # cog_id -> axial depth level
        self.hand_speeds = []         # [(hand_id, abs rev/sec)] fastest first
        self.ratios = []              # actual ratios between adjacent hands
        self.pair_errors = []         # |ln(ratio / 60)| per adjacent pair
        self.accuracy = 0.0           # exp(-mean pair error), 0..1
        self.score = 0.0              # filled in by fitness module

    def rotating_hand_count(self) -> int:
        return len(self.hand_speeds)

    def summary(self) -> Dict:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "stage": self.stage,
            "score": self.score,
            "rotating_hands": self.rotating_hand_count(),
            "ratios": self.ratios,
            "accuracy": self.accuracy,
        }


def _propagate_rotation(dna: ClockDNA, config: Config, ev: Evaluation) -> None:
    """Fill ev.omegas via BFS from the drive cog; detect ratio deadlocks."""
    drive = dna.get_cog(dna.drive_cog) if dna.drive_cog else None
    if not (ev.escapement and drive and dna.drive_surface):
        return
    module = config.tooth_module
    omega_ratchet = pendulum_frequency(dna.pendulum.length) / dna.ratchet.teeth
    ev.omegas[drive.id] = (
        -omega_ratchet * dna.ratchet.radius(module) / drive.radius(dna.drive_surface, module)
    )
    queue = [drive.id]
    while queue:
        current = queue.pop(0)
        cog = dna.get_cog(current)
        for mesh in dna.meshes:
            if not mesh.involves(current):
                continue
            other_id, other_surface, own_surface = mesh.other_end(current)
            other = dna.get_cog(other_id)
            if other is None:
                continue
            omega = (
                -ev.omegas[current]
                * cog.radius(own_surface, module)
                / other.radius(other_surface, module)
            )
            if other_id in ev.omegas:
                if not math.isclose(ev.omegas[other_id], omega, rel_tol=1e-9):
                    ev.valid = False
                    ev.reason = "deadlock: inconsistent gear ratios in mesh cycle"
                    return
            else:
                ev.omegas[other_id] = omega
                queue.append(other_id)


def _layout(dna: ClockDNA, config: Config, ev: Evaluation) -> None:
    """Place the powered train in 2D and check collisions / mesh geometry."""
    module = config.tooth_module
    ev.positions["ratchet"] = (0.0, 0.0)
    drive = dna.get_cog(dna.drive_cog) if dna.drive_cog else None
    if drive is None or drive.id not in ev.omegas:
        return

    def collides(cog_id: str, pos: Tuple[float, float], depth: int) -> bool:
        cog = dna.get_cog(cog_id)
        meshed_with = {
            m.other_end(cog_id)[0] for m in dna.meshes if m.involves(cog_id)
        }
        for other_id, other_pos in ev.positions.items():
            if other_id in ("ratchet", cog_id):
                continue
            if ev.depths.get(other_id) != depth or other_id in meshed_with:
                continue
            other = dna.get_cog(other_id)
            limit = cog.radius(OUTER, module) + other.radius(OUTER, module)
            if math.hypot(pos[0] - other_pos[0], pos[1] - other_pos[1]) < limit - 1e-6:
                return True
        return False

    # Drive cog sits directly to the right of the ratchet at depth 1.
    distance = dna.ratchet.radius(module) + drive.radius(dna.drive_surface, module)
    ev.positions[drive.id] = (distance, 0.0)
    ev.depths[drive.id] = 1

    queue = [drive.id]
    placed_meshes = set()
    while queue:
        current = queue.pop(0)
        cog = dna.get_cog(current)
        cx, cy = ev.positions[current]
        base_angle = math.atan2(cy, cx)  # continue the train radially outward
        for index, mesh in enumerate(dna.meshes):
            if not mesh.involves(current) or index in placed_meshes:
                continue
            other_id, other_surface, own_surface = mesh.other_end(current)
            other = dna.get_cog(other_id)
            if other is None:
                continue
            placed_meshes.add(index)
            required = cog.radius(own_surface, module) + other.radius(other_surface, module)
            if other_id in ev.positions:
                ox, oy = ev.positions[other_id]
                actual = math.hypot(ox - cx, oy - cy)
                if not math.isclose(actual, required, rel_tol=0.01):
                    ev.valid = False
                    ev.reason = "mesh geometry conflict: cycle does not close"
                    return
                continue
            depth = ev.depths[current] + 1
            placed = False
            for k in range(24):
                # fan out: try outward first, then alternate around the parent
                offset = (k + 1) // 2 * (TWO_PI / 24.0) * (1 if k % 2 else -1)
                angle = base_angle + offset
                pos = (cx + required * math.cos(angle), cy + required * math.sin(angle))
                if not collides(other_id, pos, depth):
                    ev.positions[other_id] = pos
                    ev.depths[other_id] = depth
                    placed = True
                    break
            if not placed:
                ev.valid = False
                ev.reason = "collision: cog %s cannot be placed without overlap" % other_id
                return
            queue.append(other_id)


def _stage_and_accuracy(dna: ClockDNA, config: Config, ev: Evaluation) -> None:
    speeds = []
    for hand in dna.hands:
        omega = ev.omegas.get(hand.cog_id)
        if omega:
            speeds.append((hand.id, abs(omega)))
    speeds.sort(key=lambda item: -item[1])
    ev.hand_speeds = speeds

    if not ev.escapement:
        ev.stage = 0
        return
    count = len(speeds)
    if count == 0:
        ev.stage = 1
    elif count == 1:
        ev.stage = 2
    else:
        ev.stage = 3
        ev.ratios = [speeds[i][1] / speeds[i + 1][1] for i in range(count - 1)]
        ev.pair_errors = [abs(math.log(r / TARGET_RATIO)) for r in ev.ratios]
        ev.accuracy = math.exp(-sum(ev.pair_errors) / len(ev.pair_errors))
        if count == 3 and all(
            abs(r - TARGET_RATIO) / TARGET_RATIO <= config.ratio_tolerance
            for r in ev.ratios
        ):
            ev.stage = 4


def evaluate(dna: ClockDNA, config: Config) -> Evaluation:
    """Simulate, validate and stage one clock."""
    ev = Evaluation()
    ev.escapement = dna.spring_to_ratchet and dna.pendulum_to_ratchet
    _propagate_rotation(dna, config, ev)
    if ev.valid:
        _layout(dna, config, ev)
    _stage_and_accuracy(dna, config, ev)
    if not ev.valid:
        ev.stage = 0  # invalid clocks cannot claim a functional stage
    return ev
