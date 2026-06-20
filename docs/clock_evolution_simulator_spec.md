# Clock Evolution Simulator - Specification

## Overview

The Clock Evolution Simulator is a genetic algorithm that evolves working mechanical clocks from random component specifications. The simulator begins with a population of randomly configured clocks and iteratively selects, reproduces, and mutates them toward a fully functional three-handed clock with correct time ratios.

## Objectives

1. Evolve a working escapement mechanism (spring-driven power regulated by pendulum-ratchet interaction)
2. Evolve a gear train that produces the correct rotation ratios for seconds, minutes, and hours hands
3. Track evolutionary progress: number of functional hands, accuracy of ratios, fitness scores
4. Preserve and visualize the DNA of evolved clocks and their performance metrics over time

## Components

### Spring
- **Role**: Power source for the entire clock mechanism; provides unlimited energy (treated as infinite power drive)
- **DNA Parameters**: None (spring is a constant, unlimited power source)
- **Connections**: Must connect to at least one cog to initiate rotational motion; the cog train and escapement mechanism then regulate and distribute this power

### Ratchet
- **Role**: Controls direction of rotation and prevents backslash; acts as the mechanical pivot point for the escapement mechanism that regulates power release from the spring
- **DNA Parameters**: 
  - Tooth count (integer, within configured min/max bounds)
  - Radius (derived from tooth count via tooth spacing constant)
- **Escapement Function**: Works in conjunction with the pendulum; the pendulum's oscillation controls the tempo at which the ratchet allows the spring's stored energy to be released into the gear train

### Pendulum
- **Role**: Controls the tempo (pace) of the clock; oscillates to regulate how fast the ratchet releases the spring's energy
- **DNA Parameters**:
  - Length (determines swing frequency, which controls clock tempo)
- **Escapement Function**: Mechanically coupled to the ratchet; its swing frequency determines the rate at which energy is released, setting the base timing of the entire clock mechanism

### Cog
- **Role**: Transmits and transforms rotational motion through meshing; enables gear ratio conversion
- **DNA Parameters**:
  - Outer radius and outer tooth count (defines the outer gear surface)
  - Inner radius and inner tooth count (defines the inner gear surface)
  - All tooth counts are integers within configured min/max bounds
- **Geometry**: Each cog has two distinct meshing surfaces—one outer (larger) and one inner (smaller). Cogs can mesh with either surface of another cog.
- **Gear Ratios**: When the outer surface of Cog A meshes with another cog's surface, the rotation speed of the connected cog is determined by the ratio of their respective radii (or tooth counts). A cog's inner surface produces a different ratio than its outer surface, allowing a single cog to participate in two different gear stages.
- **Connections**: Can connect to another cog's outer or inner surface at the same time (up to two simultaneous connections per cog); connection type determines the gear ratio and relative rotational direction

### Hand
- **Role**: Displays time by rotating in sync with the cog it's attached to; three hands are required for a complete clock (seconds, minutes, hours)
- **DNA Parameters**:
  - Length (visual/aesthetic length of the hand)
  - Attachment surface (which cog's outer or inner surface it is attached to)
  - Attachment radius (the specific radius on that surface where the hand is anchored)
- **Connection**: Each hand is attached to exactly one cog surface (outer or inner); the hand rotates with that surface at the same angular velocity

## Clock Specification (DNA)

A clock's DNA encodes:

1. **Component List**: All components in the clock (spring, ratchet, pendulum, cogs, hands)
   - Each component has an ID and its parameter set
2. **Connection Graph**: Which components connect to which
   - For cog-to-cog: specifies outer-to-outer, outer-to-inner, inner-to-outer, or inner-to-inner
   - For spring/ratchet/pendulum: specifies connection partner(s)
3. **Hand Assignments**: Which hands are attached to which cogs and at which radii

## Fitness Evaluation

### Physical Validation
Before a clock can be evaluated, its DNA must specify a configuration that is physically realizable in 2D space:
- All components must fit without collision when laid out according to their connections
- Meshed cogs must have compatible geometry (radii and tooth counts align correctly)
- No mechanical deadlock or conflict in rotational direction

### Functional Stages (Hierarchical Fitness)

Fitness is evaluated in stages, with higher stages always scoring better than lower stages:

1. **Stage 0 - Non-functional**: Clock does not meet the criteria for Stage 1
2. **Stage 1 - Swinging Pendulum**: Pendulum oscillates (escapement mechanism is working); spring drives the system, ratchet controls direction, pendulum controls tempo
3. **Stage 2 - One-Handed Clock**: At least one hand rotates on a cog at any rate
4. **Stage 3 - Two-Handed Clock**: At least two hands rotate on cogs
5. **Stage 4 - Three-Handed Clock**: All three hands (seconds, minutes, hours) rotate on cogs with correct ratios

### Accuracy Scoring Within Stages

Within each stage, clocks are scored by how close their hand rotation ratios are to the ideal mechanical clock:

- **Target ratios**: 
  - Seconds : Minutes = 60 : 1 (for every 60 revolutions of seconds hand, minutes hand revolves once)
  - Minutes : Hours = 12 : 1 (for every 12 revolutions of minutes hand, hours hand revolves once — the hour hand completes one turn every 12 hours)
  - Overall: Seconds : Minutes : Hours = 720 : 12 : 1
- **Ratio accuracy**: Measure the error between actual and target ratios for each hand pair
- **Composite score**: Stage bonus (higher stages score higher) + accuracy bonus (closeness to target ratios)

Clocks with more hands at correct ratios always score higher than clocks with fewer hands or incorrect ratios.

## Evolution Process

### Population Management
- **Pool size**: Configurable (specified in configuration file or application parameter)
- **Initial population**: Generated randomly from component and connection distributions

### Selection and Reproduction
Each generation (turn):
1. **Selection**: Two clocks are selected from the population (selection method TBD)
2. **Evaluation**: Both clocks are evaluated for fitness
3. **Elimination**: The clock with lower fitness is eliminated from the population
4. **Duplication & Mutation**: The surviving (higher fitness) clock is duplicated; the copy undergoes a mutation in its DNA
5. **Insertion**: The mutated copy is added back to the population, restoring pool size

The process repeats each turn until a fully functional three-handed clock evolves or a generation limit is reached.

### Mutations

Applied to the surviving clock's DNA, mutations may include:
- **Structural**: Add a new cog, add a new hand, remove a component
- **Parametric**: Modify tooth count, radius, pendulum length
- **Topological**: Rewire connections (change which cogs mesh with which)

Mutation rate and type distribution are configurable.

## Configuration File

The application reads configuration parameters from a config file (format TBD—JSON, YAML, or INI):

```
# Component Bounds
min_cog_teeth: 8
max_cog_teeth: 120

# Evolution Parameters
population_size: 100
mutation_rate: 0.1
selection_method: "tournament"  # or "random", "best"

# Simulation Parameters
generations_per_run: 10000
visualization_frequency: 100  # Log data every N generations
```

## Output and Tracking

### Primary Metrics (Graphed Over Time)
1. **Hand Count Evolution**: Number of clocks at each stage (0-handed, 1-handed, 2-handed, 3-handed) plotted as a time series or stacked area chart
2. **Accuracy Over Time**: Average accuracy (error from the target hand-pair ratios, 60 then 12) for clocks with 2+ hands, plotted over generations

### Data Tracked Per Generation
- **Best clock in population**: Its fitness score and stage
- **Population distribution**: Histogram of clocks at each functional stage
- **Accuracy metrics**: For clocks with 2+ hands, average ratio error; for 3-handed clocks, individual error on seconds-to-minutes and minutes-to-hours ratios
- **DNA of notable clocks**: Preserved DNA of the best clock found so far and best clock of each generation (for visualization and analysis)

### Clock Visualization
Given a stored DNA, render the clock showing:
- All components (spring, ratchet, pendulum, cogs, hands)
- All connections (meshing relationships, attachment points)
- Hand positions and labels (seconds, minutes, hours)
- Rotational direction annotations if applicable

Format: Schematic diagram (node-and-edge or mechanical diagram representation)

## Success Criteria

The simulation succeeds when:
1. A three-handed clock (seconds, minutes, hours) evolves
2. The three hands rotate at the correct ratios (or within acceptable error margin)
3. The evolved clock's DNA can be used to build a real mechanical clock

## Open Questions for Implementation

- Exact formula for composite fitness score (stage weight + accuracy scaling)
- Spatial layout algorithm for validating physical realizability
- Mutation type distribution and probabilities
- Selection strategy (tournament size, elitism, etc.)
- Acceptable error margin for "correct" ratios
- Visual representation format for clock diagrams
