"""Build a client-side render model for a clock: geometry plus kinematics.

This is what the web UI animates. It reuses the simulator's own layout and
rotation solution (`evaluate`), so the gears turn at the real evolved ratios.
Pure Python (no matplotlib) so it is cheap to serve and easy to test.
"""

from .config import Config
from .dna import ClockDNA, INNER, OUTER
from .mechanics import evaluate, pendulum_frequency

ROLES = ["Seconds", "Minutes", "Hours"]


def render_model(dna: ClockDNA, config: Config) -> dict:
    module = config.tooth_module
    ev = evaluate(dna, config)

    placed = dict(ev.positions)  # cog ids (and "ratchet") that the layout placed
    # Park unpowered cogs in a row below the movement, mirroring the schematic.
    parked = [c for c in dna.cogs if c.id not in placed]
    if dna.cogs:
        min_y = min((p[1] for p in placed.values()), default=0.0)
        radii = [c.radius(OUTER, module) for c in dna.cogs] + [dna.ratchet.radius(module)]
        park_y = min_y - 2.5 * max(radii)
        x = 0.0
        for c in parked:
            r = c.radius(OUTER, module)
            x += r
            placed[c.id] = (x, park_y)
            x += r + module * 4

    rx, ry = placed.get("ratchet", (0.0, 0.0))
    rr = dna.ratchet.radius(module)
    freq = pendulum_frequency(dna.pendulum.length)
    ratchet_omega = (freq / dna.ratchet.teeth) if ev.escapement else 0.0

    # Spring + pendulum world geometry (mirrors the schematic layout) so the
    # client can draw them in-scale and they fall inside the fitted view.
    spring_x, spring_y = rx - 2.2 * rr, ry + 1.2 * rr
    spring_hw, spring_hh = 0.7 * rr, 0.45 * rr
    pivot_x, pivot_y = rx - 1.8 * rr, ry - 0.5 * rr
    pend_len = 10.0 + dna.pendulum.length * 15.0

    cogs = []
    for c in dna.cogs:
        pos = placed.get(c.id)
        if pos is None:
            continue
        cogs.append({
            "id": c.id, "x": pos[0], "y": pos[1],
            "outer_teeth": c.outer_teeth, "inner_teeth": c.inner_teeth,
            "r_out": c.radius(OUTER, module), "r_in": c.radius(INNER, module),
            "omega": ev.omegas.get(c.id, 0.0),
            "powered": c.id in ev.omegas,
            "is_drive": c.id == dna.drive_cog,
        })

    role_by_hand = {hid: ROLES[i] for i, (hid, _) in enumerate(ev.hand_speeds)}
    hands = []
    for i, h in enumerate(dna.hands):
        pos = placed.get(h.cog_id)
        if pos is None:
            continue
        hands.append({
            "cog_id": h.cog_id, "x": pos[0], "y": pos[1],
            "length": h.length, "index": i,
            "role": role_by_hand.get(h.id),
            "omega": ev.omegas.get(h.cog_id, 0.0),
        })

    meshes = [
        {"a": m.cog_a, "b": m.cog_b}
        for m in dna.meshes if m.cog_a in placed and m.cog_b in placed
    ]

    xs, ys = [rx - rr, rx + rr], [ry - rr, ry + rr]
    for c in cogs:
        xs += [c["x"] - c["r_out"], c["x"] + c["r_out"]]
        ys += [c["y"] - c["r_out"], c["y"] + c["r_out"]]
    for h in hands:
        xs += [h["x"] - h["length"], h["x"] + h["length"]]
        ys += [h["y"] - h["length"], h["y"] + h["length"]]
    # include spring box and the pendulum's full swing/length
    xs += [spring_x - spring_hw, spring_x + spring_hw, pivot_x - pend_len, pivot_x + pend_len]
    ys += [spring_y + spring_hh, pivot_y - pend_len]

    return {
        "valid": ev.valid, "reason": ev.reason,
        "stage": ev.stage, "accurate": ev.accurate,
        "module": module,
        "ratchet": {"x": rx, "y": ry, "teeth": dna.ratchet.teeth,
                    "radius": rr, "omega": ratchet_omega},
        "spring": {"connected": dna.spring_to_ratchet, "x": spring_x, "y": spring_y,
                   "hw": spring_hw, "hh": spring_hh},
        "pendulum": {"length": dna.pendulum.length,
                     "connected": dna.pendulum_to_ratchet, "freq": freq,
                     "pivot_x": pivot_x, "pivot_y": pivot_y,
                     "len": pend_len, "bob": 0.28 * rr},
        "drive_cog": dna.drive_cog,
        "cogs": cogs, "hands": hands, "meshes": meshes,
        "bounds": {"minx": min(xs), "maxx": max(xs),
                   "miny": min(ys), "maxy": max(ys)},
    }
