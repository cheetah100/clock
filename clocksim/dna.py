"""DNA model: the heritable specification of a clock.

A clock always contains exactly one spring, one ratchet and one pendulum.
The spring has no parameters (it is an infinite power source), so it is
represented implicitly by its connection flag (``spring_to_ratchet``).
"""

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

OUTER = "outer"
INNER = "inner"
SURFACES = (OUTER, INNER)


@dataclass
class Ratchet:
    teeth: int

    def radius(self, module: float) -> float:
        return self.teeth * module / 2.0


@dataclass
class Pendulum:
    length: float  # metres


@dataclass
class Cog:
    """A two-surface gear: a large outer toothed rim and a smaller inner
    (concentric) toothed rim. Both surfaces rotate together."""

    id: str
    outer_teeth: int
    inner_teeth: int

    def teeth(self, surface: str) -> int:
        return self.outer_teeth if surface == OUTER else self.inner_teeth

    def radius(self, surface: str, module: float) -> float:
        return self.teeth(surface) * module / 2.0


@dataclass
class Hand:
    id: str
    length: float
    cog_id: str
    surface: str
    attachment_radius: float


@dataclass
class Mesh:
    """An undirected meshing connection between two cog surfaces."""

    cog_a: str
    surface_a: str
    cog_b: str
    surface_b: str

    def involves(self, cog_id: str) -> bool:
        return cog_id in (self.cog_a, self.cog_b)

    def other_end(self, cog_id: str):
        """Return (other_cog_id, other_surface, own_surface)."""
        if cog_id == self.cog_a:
            return self.cog_b, self.surface_b, self.surface_a
        return self.cog_a, self.surface_a, self.surface_b


@dataclass
class ClockDNA:
    ratchet: Ratchet
    pendulum: Pendulum
    cogs: List[Cog] = field(default_factory=list)
    hands: List[Hand] = field(default_factory=list)
    meshes: List[Mesh] = field(default_factory=list)
    spring_to_ratchet: bool = False
    pendulum_to_ratchet: bool = False
    drive_cog: Optional[str] = None       # cog the ratchet's output meshes with
    drive_surface: Optional[str] = None
    next_id: int = 1

    # ---- identity helpers -------------------------------------------------

    def new_id(self, prefix: str) -> str:
        ident = "%s%d" % (prefix, self.next_id)
        self.next_id += 1
        return ident

    def get_cog(self, cog_id: str) -> Optional[Cog]:
        for cog in self.cogs:
            if cog.id == cog_id:
                return cog
        return None

    def cog_mesh_count(self, cog_id: str) -> int:
        return sum(1 for m in self.meshes if m.involves(cog_id))

    def meshed_pairs(self):
        return {frozenset((m.cog_a, m.cog_b)) for m in self.meshes}

    def clone(self) -> "ClockDNA":
        return copy.deepcopy(self)

    # ---- serialization ----------------------------------------------------

    def to_dict(self) -> Dict:
        return {
            "ratchet": {"teeth": self.ratchet.teeth},
            "pendulum": {"length": self.pendulum.length},
            "cogs": [
                {"id": c.id, "outer_teeth": c.outer_teeth, "inner_teeth": c.inner_teeth}
                for c in self.cogs
            ],
            "hands": [
                {
                    "id": h.id,
                    "length": h.length,
                    "cog_id": h.cog_id,
                    "surface": h.surface,
                    "attachment_radius": h.attachment_radius,
                }
                for h in self.hands
            ],
            "meshes": [
                {
                    "cog_a": m.cog_a,
                    "surface_a": m.surface_a,
                    "cog_b": m.cog_b,
                    "surface_b": m.surface_b,
                }
                for m in self.meshes
            ],
            "spring_to_ratchet": self.spring_to_ratchet,
            "pendulum_to_ratchet": self.pendulum_to_ratchet,
            "drive_cog": self.drive_cog,
            "drive_surface": self.drive_surface,
            "next_id": self.next_id,
        }

    @staticmethod
    def from_dict(data: Dict) -> "ClockDNA":
        return ClockDNA(
            ratchet=Ratchet(teeth=data["ratchet"]["teeth"]),
            pendulum=Pendulum(length=data["pendulum"]["length"]),
            cogs=[
                Cog(id=c["id"], outer_teeth=c["outer_teeth"], inner_teeth=c["inner_teeth"])
                for c in data["cogs"]
            ],
            hands=[
                Hand(
                    id=h["id"],
                    length=h["length"],
                    cog_id=h["cog_id"],
                    surface=h["surface"],
                    attachment_radius=h["attachment_radius"],
                )
                for h in data["hands"]
            ],
            meshes=[
                Mesh(
                    cog_a=m["cog_a"],
                    surface_a=m["surface_a"],
                    cog_b=m["cog_b"],
                    surface_b=m["surface_b"],
                )
                for m in data["meshes"]
            ],
            spring_to_ratchet=data["spring_to_ratchet"],
            pendulum_to_ratchet=data["pendulum_to_ratchet"],
            drive_cog=data["drive_cog"],
            drive_surface=data["drive_surface"],
            next_id=data.get("next_id", 1),
        )
