# Clock Evolution Simulator

A genetic algorithm that evolves working mechanical clocks from random component
specifications, implementing [docs/clock_evolution_simulator_spec.md](docs/clock_evolution_simulator_spec.md).
Starting from a population of randomly wired clocks, it evolves an escapement
(spring + ratchet + pendulum), then a gear train, then three hands turning at the
correct 720 : 12 : 1 (seconds : minutes : hours) ratios — the hour hand turns
once every 12 hours.

With the default configuration a correct three-handed clock typically evolves in
**3,000–20,000 generations (a few seconds of wall time)**.

## Requirements

- Python 3.8+
- matplotlib (for graphs and clock schematics)

No installation step is needed; run everything from this directory.

## Quick start (interactive)

```bash
python3 -m clocksim serve
```

Then open **http://127.0.0.1:8123/** in a browser (in VS Code the port is
forwarded automatically). The UI has:

- **Settings panel** (left) — every evolution parameter, pre-filled from
  `config.json`; change anything and press **Run** to start a fresh
  simulation. **Stop** cancels a run early.
- **Live status and charts** (centre) — generation counter, best score/stage,
  current best ratios, and the three progress graphs updating as the run
  proceeds.
- **Best-clock timeline** (bottom) — a scrollable filmstrip with a small
  schematic of every new best clock as it was discovered, captioned with its
  generation, stage and ratios (stage-4 clocks get a green border). Click any
  thumbnail to enlarge it and download that clock's DNA.

`--port` and `--host` change where it listens; `--config` points the settings
form at a different defaults file. The downloads panel serves the current
run's `history.json` and `best_clock.json`.

## Quick start (command line)

```bash
python3 -m clocksim run --config config.json --output results
```

This prints each fitness improvement as it happens, stops as soon as a correct
three-handed clock evolves (or at the generation limit), and writes everything
to `results/`. A fixed `--seed N` makes a run exactly reproducible.

## Commands

### `serve` — interactive web UI

```bash
python3 -m clocksim serve [--config FILE] [--host ADDR] [--port N]
```

Described above. Uses only the Python standard library; runs entirely
locally and keeps the active run in memory (use the download links to keep
results). One simulation runs at a time; pressing Run while idle starts a
new one with the current form settings.

### `run` — evolve clocks

```bash
python3 -m clocksim run [--config config.json] [--output DIR] [--seed N] [--generations N] [--quiet]
```

`--seed` and `--generations` override the config file. Exit code is 0 on
success (a stage-4 clock evolved), 1 otherwise. Output files:

| File | Contents |
|---|---|
| `history.json` | Config used, result summary, per-interval population snapshots, every best-clock improvement (with full DNA), and the final best DNA |
| `best_clock.json` | DNA of the best clock found, on its own |
| `best_clock.png` | Schematic of the best clock |
| `hands_over_time.png` | Stacked area chart: clocks with 0/1/2/3 rotating hands |
| `accuracy_over_time.png` | Mean ratio error of 2+-hand clocks (log scale) |
| `fitness_over_time.png` | Best and mean fitness curves |

### `visualize` — render any stored DNA

```bash
python3 -m clocksim visualize results/best_clock.json -o clock.png
```

Accepts a bare DNA file or a `history.json` (renders its best clock). The
schematic shows every component, mesh connections labelled by surface
(`O-I` = outer-to-inner, etc.), rotation direction and speed per cog, and
hands labelled Seconds/Minutes/Hours. Unpowered components are drawn grey;
unpowered cogs are parked in a row below the movement.

### `plot` — regenerate graphs from a saved history

```bash
python3 -m clocksim plot results/history.json -o results
```

## Configuration

All keys in [config.json](config.json) (any key may be omitted; defaults shown):

| Key | Default | Meaning |
|---|---|---|
| `min_cog_teeth` / `max_cog_teeth` | 8 / 120 | Bounds for every cog surface's tooth count |
| `min_ratchet_teeth` / `max_ratchet_teeth` | 8 / 60 | Bounds for the ratchet wheel |
| `min_inner_outer_gap` | 4 | A cog's outer rim must have at least this many more teeth than its inner rim |
| `tooth_module` | 1.0 | Tooth pitch constant; radius = teeth × module / 2 |
| `max_cogs` | 12 | Cap on cogs per clock |
| `max_meshes_per_cog` | 2 | Cog-to-cog connections a single cog may have (the spec's limit is 2; raising it allows richer gear graphs but more cycles, hence more rotational deadlocks — which are rejected as invalid) |
| `population_size` | 100 | Clocks in the pool |
| `mutation_rate` | 0.35 | Every child gets one mutation; this is the chance of each *additional* mutation (max 4 extras) |
| `selection_method` | `"tournament"` | `"tournament"`, `"random"`, or `"best"` (see below) |
| `tournament_size` | 4 | Sample size for tournament selection |
| `mutation_weights` | see `clocksim/config.py` | Relative probability of each mutation operator |
| `generations_per_run` | 200000 | Generation limit |
| `visualization_frequency` | 100 | Record a population snapshot every N generations |
| `ratio_tolerance` | 0.01 | Relative error allowed on each hand-pair ratio (60 for seconds:minutes, 12 for minutes:hours) for stage 4 |
| `stop_on_success` | true | Stop as soon as a stage-4 clock exists |
| `random_seed` | null | Fix for reproducible runs |

Selection methods (each turn picks a winner and a loser; the loser is replaced
by a mutated copy of the winner):

- **random** — the spec's basic scheme: two random clocks, lower fitness eliminated.
- **tournament** (default) — winner is the best of one random sample, loser the worst of another; converges faster while preserving diversity.
- **best** — winner is always the population's best clock; fastest exploitation, weakest exploration.

## How it works

### Physical model

- The **pendulum** swings at its natural frequency `sqrt(g/L) / 2π`; each
  oscillation releases one **ratchet** tooth, so the ratchet wheel turns at
  `frequency / teeth` rev/s — the pendulum sets the tempo, the ratchet sets the
  direction, the **spring** supplies unlimited power. All three must be
  connected for the escapement to function (stage 1).
- Each **cog** has two concentric toothed rims (outer and inner) that rotate
  together. The ratchet's output meshes with one cog surface; rotation then
  propagates through the mesh graph. Every mesh reverses direction and scales
  speed by the ratio of the engaged radii, so a cog's small inner rim driving a
  large outer rim is how the train slows down (60:1, then 12:1) over a couple of stages.
- **Hands** turn with whatever cog surface they're attached to. Roles are
  assigned by speed: the fastest rotating hand is Seconds, then Minutes, then Hours.

### Physical validation

- Tooth pitch compatibility is guaranteed by construction: every surface uses
  the same tooth module, so radius is proportional to tooth count.
- A mesh cycle whose gear ratios disagree is a **rotational deadlock**; the
  clock is invalid.
- The powered train is laid out in 2D, with meshing cogs stacked one axial
  depth level apart (as in a real movement). Meshed centres must sit exactly
  one radius-sum apart, cogs at the same depth must not overlap, and a mesh
  that closes a cycle must agree with the already-fixed geometry — otherwise
  the clock is invalid (**collision** / **geometry conflict**).
- Per the spec, a cog can take part in at most two cog-to-cog meshes.

### Fitness

Hierarchical stages dominate: `score = 100 + 2000 × stage + bonus`, with the
bonus capped below 2000 so a higher stage always wins. Stages: 0 non-functional,
1 swinging pendulum, 2 one rotating hand, 3 two+, 4 all three hands within
`ratio_tolerance` of their targets (60 then 12). Invalid clocks score below every valid clock (0–30,
with small credit per escapement connection so they can climb back out).

The within-stage bonus rewards powered cogs, hands present, a wired ratchet
output, each *rotating* hand, and per-pair ratio accuracy `exp(-|ln(ratio/target)|)`
(target 60 for seconds:minutes, 12 for minutes:hours).
Accuracy is **summed per pair rather than averaged** — this matters: with an
average, a perfect two-handed clock is a local optimum that a third hand can
only make worse, and evolution stalls there permanently (observed empirically
before the fix).

### Mutations

One weighted-random operator per child (plus extras per `mutation_rate`):
parametric (tooth counts with mostly-small steps for fine ratio tuning,
pendulum length, hand length), structural (add/remove cog, add/remove hand),
and topological (add/remove/rewire meshes, move a hand, rewire the ratchet
output, toggle the spring and pendulum couplings). All operators preserve the
DNA invariants (tooth bounds, ≤3 hands, ≤2 meshes per cog).

## Tests

```bash
python3 -m unittest discover -s tests -v
```

19 tests cover gear-ratio propagation, deadlock detection, stage
classification, fitness ordering and gradients, mutation invariants over
thousands of random mutations, DNA serialization round-trips, an end-to-end
smoke run, and the web app (run lifecycle, config validation, HTTP endpoints).

## Experiments

The scripts run a parameter-sensitivity study and its write-up,
[docs/PAPER.md](docs/PAPER.md); generated artifacts land in `experiments/`:

```bash
python3 -m clocksim.run_experiments   # ~8 min on 16 cores: 176 evolution runs
python3 -m clocksim.analyze           # summary stats, figures, example clocks
```

Raw per-run records land in `experiments/data/results.jsonl`, aggregates in
`summary.csv`/`summary.json`, figures in `experiments/figures/`, and example
evolved clocks (DNA + schematic) in `experiments/clocks/`.

## Project layout

```
clocksim/
  config.py         configuration loading + defaults
  dna.py            heritable clock specification + JSON serialization
  mechanics.py      rotation propagation, layout, validation, staging
  fitness.py        composite score
  genesis.py        random clocks + mutation operators
  evolution.py      EvolutionEngine (observable, cancellable) + CLI run wrapper
  visualization.py  progress graphs + clock schematics (full and thumbnail)
  webapp.py         stdlib HTTP server for the interactive UI
  static/index.html the single-page UI
  __main__.py       CLI (serve / run / visualize / plot)
  run_experiments.py  parameter sweeps -> experiments/data/
  analyze.py          summary stats, figures + example clocks from sweep data
tests/test_clocksim.py
config.json         default configuration
docs/               specification + experiment write-up (PAPER.md)
results/            sample successful run (seed 42)
experiments/        generated study artifacts (data, figures, clocks)
```

## Interpretations and decisions

The spec left several points open; the choices made here:

- **Config format**: JSON. **Fitness formula, mutation distribution, selection
  details, 1% ratio tolerance**: as described above, all configurable.
- The spring's power path is spring → ratchet → drive cog (the escapement
  releases power into the train); "spring connects to a cog" is realized
  through the ratchet's drive connection.
- Ratio scoring uses absolute rotation speeds; hand pairs may counter-rotate
  (a real build would add idler gears to fix visual direction).
- Absolute tempo is not scored — the spec's targets are ratios only — so the
  pendulum/ratchet set the tick rate but any tick rate can be a perfect clock.
- "Best clock DNA over time" is preserved as the full DNA of every
  best-so-far improvement, stored in `history.json`.
