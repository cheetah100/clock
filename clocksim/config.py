"""Configuration loading with defaults; reads JSON config files."""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional

DEFAULT_MUTATION_WEIGHTS = {
    "cog_teeth": 4.0,
    "pendulum_length": 0.5,
    "ratchet_teeth": 0.5,
    "add_cog": 1.5,
    "remove_cog": 0.7,
    "add_hand": 1.5,
    "remove_hand": 0.4,
    "move_hand": 1.5,
    "hand_length": 0.3,
    "add_mesh": 1.5,
    "remove_mesh": 0.5,
    "rewire_mesh": 1.0,
    "toggle_spring": 0.3,
    "toggle_pendulum": 0.3,
    "set_drive": 1.0,
}


@dataclass
class Config:
    # Component bounds
    min_cog_teeth: int = 8
    max_cog_teeth: int = 120
    min_ratchet_teeth: int = 8
    max_ratchet_teeth: int = 60
    min_inner_outer_gap: int = 4   # outer_teeth must exceed inner_teeth by this
    tooth_module: float = 1.0      # radius = teeth * module / 2
    max_cogs: int = 12

    # Evolution parameters
    population_size: int = 100
    mutation_rate: float = 0.35    # probability of each *additional* mutation
    selection_method: str = "tournament"  # "tournament" | "random" | "best"
    tournament_size: int = 4
    mutation_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_MUTATION_WEIGHTS)
    )

    # Simulation parameters
    generations_per_run: int = 200000
    visualization_frequency: int = 100  # snapshot population stats every N generations
    ratio_tolerance: float = 0.01       # relative error allowed on the 60:1 ratios
    stop_on_success: bool = True
    random_seed: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def load(path: Optional[str] = None) -> "Config":
        cfg = Config()
        if path:
            with open(path) as fh:
                data = json.load(fh)
            for key, value in data.items():
                if not hasattr(cfg, key):
                    raise ValueError("Unknown config key: %r" % key)
                if key == "mutation_weights":
                    cfg.mutation_weights.update(value)
                else:
                    setattr(cfg, key, value)
        cfg.validate()
        return cfg

    def validate(self):
        if self.min_cog_teeth + self.min_inner_outer_gap > self.max_cog_teeth:
            raise ValueError("Cog teeth bounds leave no room for inner/outer gap")
        if self.population_size < 2:
            raise ValueError("population_size must be at least 2")
        if self.selection_method not in ("tournament", "random", "best"):
            raise ValueError("selection_method must be tournament, random or best")
