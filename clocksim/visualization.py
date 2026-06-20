"""Plots of evolutionary progress and schematic rendering of clock DNA.

Every chart is available both as a saved file (CLI) and as in-memory PNG
bytes (web UI). Schematics have a ``compact`` mode used for the timeline
thumbnails in the web UI.
"""

import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrow, Rectangle

from .config import Config
from .dna import ClockDNA, INNER, OUTER
from .mechanics import evaluate

HAND_ROLES = ["Seconds", "Minutes", "Hours"]
STAGE_LABELS = ["0 hands", "1 hand", "2 hands", "3 hands"]
HAND_COLORS = ["#bbbbbb", "#7fb2e5", "#4d8fd1", "#1f5fa8"]
CHART_NAMES = ("hands", "accuracy", "fitness")


def figure_png_bytes(fig, dpi=120) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Progress charts
# ---------------------------------------------------------------------------

def history_figure(name: str, history) -> "plt.Figure":
    snapshots = history["snapshots"]
    generations = [s["generation"] for s in snapshots]
    fig, ax = plt.subplots(figsize=(8, 4))

    if name == "hands":
        series = [[s["hand_counts"][i] for s in snapshots] for i in range(4)]
        ax.stackplot(generations, series, labels=STAGE_LABELS, colors=HAND_COLORS)
        ax.set_ylabel("Clocks in population")
        ax.set_title("Population by number of rotating hands")
        ax.legend(loc="center left", fontsize=8)
    elif name == "accuracy":
        pts = [(s["generation"], s["mean_pair_error"]) for s in snapshots
               if s["mean_pair_error"] is not None]
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#c0392b")
            ax.set_yscale("log")
        ax.set_ylabel("Mean |ln(ratio / 60)| (log scale)")
        ax.set_title("Ratio accuracy of clocks with 2+ rotating hands")
    elif name == "fitness":
        ax.plot(generations, [s["best_score"] for s in snapshots], label="Best score")
        ax.plot(generations, [s["mean_score"] for s in snapshots], label="Mean score")
        ax.set_ylabel("Fitness score")
        ax.set_title("Fitness over time")
        ax.legend(fontsize=8)
    else:
        raise ValueError("Unknown chart: %r" % name)

    ax.set_xlabel("Generation")
    fig.tight_layout()
    return fig


def plot_history(history, out_dir):
    """Write the progress graphs required by the spec."""
    file_names = {
        "hands": "hands_over_time.png",
        "accuracy": "accuracy_over_time.png",
        "fitness": "fitness_over_time.png",
    }
    for name, file_name in file_names.items():
        fig = history_figure(name, history)
        fig.savefig("%s/%s" % (out_dir, file_name), dpi=120)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Clock schematics
# ---------------------------------------------------------------------------

def _draw_cog(ax, cog, center, module, color="#444444", alpha=1.0, compact=False):
    r_out = cog.radius(OUTER, module)
    r_in = cog.radius(INNER, module)
    ax.add_patch(Circle(center, r_out, fill=False, color=color, lw=1.2, alpha=alpha))
    ax.add_patch(Circle(center, r_in, fill=False, color=color, lw=0.8,
                        linestyle="--", alpha=alpha))
    if compact:
        return
    for k in range(cog.outer_teeth):
        a = 2 * math.pi * k / cog.outer_teeth
        ax.plot(
            [center[0] + r_out * math.cos(a), center[0] + (r_out + module * 0.4) * math.cos(a)],
            [center[1] + r_out * math.sin(a), center[1] + (r_out + module * 0.4) * math.sin(a)],
            color=color, lw=0.4, alpha=alpha * 0.6,
        )
    ax.annotate(
        "%s\n%d/%d" % (cog.id, cog.outer_teeth, cog.inner_teeth),
        center, ha="center", va="center", fontsize=8, color=color, alpha=alpha,
    )


def clock_figure(dna: ClockDNA, config: Config, compact: bool = False) -> "plt.Figure":
    """Build a schematic figure of one clock DNA: components, connections, hands."""
    module = config.tooth_module
    ev = evaluate(dna, config)
    fig, ax = plt.subplots(figsize=(3.0, 2.4) if compact else (12, 10))

    placed = dict(ev.positions)  # includes "ratchet"
    # Park unpowered cogs in a row below the movement.
    parked = [c for c in dna.cogs if c.id not in placed]
    if placed or parked:
        min_y = min((p[1] for p in placed.values()), default=0.0)
        park_y = min_y - 2.5 * max(
            [c.radius(OUTER, module) for c in dna.cogs] + [dna.ratchet.radius(module)]
        )
        x_cursor = 0.0
        for cog in parked:
            r = cog.radius(OUTER, module)
            x_cursor += r
            placed[cog.id] = (x_cursor, park_y)
            x_cursor += r + module * 4

    # Mesh connections.
    for mesh in dna.meshes:
        if mesh.cog_a in placed and mesh.cog_b in placed:
            (x1, y1), (x2, y2) = placed[mesh.cog_a], placed[mesh.cog_b]
            ax.plot([x1, x2], [y1, y2], color="#999999", lw=0.8, linestyle=":")
            if not compact:
                ax.annotate(
                    "%s-%s" % (mesh.surface_a[0].upper(), mesh.surface_b[0].upper()),
                    ((x1 + x2) / 2, (y1 + y2) / 2), fontsize=7, color="#999999",
                )

    # Ratchet, spring, pendulum.
    r_ratchet = dna.ratchet.radius(module)
    rx, ry = placed["ratchet"]
    ax.add_patch(Circle((rx, ry), r_ratchet, fill=False, color="#8e44ad",
                        lw=1.5, hatch="///"))
    if not compact:
        ax.annotate("Ratchet\n%d teeth" % dna.ratchet.teeth, (rx, ry),
                    ha="center", va="center", fontsize=8, color="#8e44ad")

    spring_pos = (rx - r_ratchet * 2.2, ry + r_ratchet * 1.2)
    spring_color = "#27ae60" if dna.spring_to_ratchet else "#bbbbbb"
    ax.add_patch(Rectangle((spring_pos[0] - 6, spring_pos[1] - 4), 12, 8,
                           fill=False, color=spring_color, lw=1.5))
    if not compact:
        ax.annotate("Spring", spring_pos, ha="center", va="center",
                    fontsize=8, color=spring_color)
    if dna.spring_to_ratchet:
        ax.plot([spring_pos[0] + 6, rx - r_ratchet * 0.7],
                [spring_pos[1], ry + r_ratchet * 0.7], color=spring_color, lw=1.0)

    pend_color = "#e67e22" if dna.pendulum_to_ratchet else "#bbbbbb"
    pend_len = 10 + dna.pendulum.length * 15
    px, py = rx - r_ratchet * 1.8, ry - r_ratchet * 0.5
    ax.plot([px, px], [py, py - pend_len], color=pend_color, lw=1.2)
    ax.add_patch(Circle((px, py - pend_len), 3, color=pend_color))
    if not compact:
        ax.annotate("Pendulum\n%.2f m" % dna.pendulum.length, (px, py - pend_len - 8),
                    ha="center", va="top", fontsize=8, color=pend_color)
    if dna.pendulum_to_ratchet:
        ax.plot([px, rx - r_ratchet * 0.5], [py, ry - r_ratchet * 0.5],
                color=pend_color, lw=1.0, linestyle="--")

    if dna.drive_cog and dna.drive_cog in placed:
        (dx, dy) = placed[dna.drive_cog]
        ax.plot([rx, dx], [ry, dy], color="#8e44ad", lw=1.0, linestyle=":")

    # Cogs with rotation annotations.
    for cog in dna.cogs:
        pos = placed.get(cog.id)
        if pos is None:
            continue
        omega = ev.omegas.get(cog.id)
        alpha = 1.0 if omega else 0.45
        _draw_cog(ax, cog, pos, module, alpha=alpha, compact=compact)
        if omega and not compact:
            direction = "CCW" if omega > 0 else "CW"
            ax.annotate(
                "%s %.3g rev/s" % (direction, abs(omega)),
                (pos[0], pos[1] - cog.radius(OUTER, module) - module * 1.5),
                ha="center", fontsize=7, color="#2c3e50",
            )

    # Hands, labelled by role (fastest rotating hand = seconds).
    role_by_hand = {hand_id: HAND_ROLES[i] for i, (hand_id, _) in enumerate(ev.hand_speeds)}
    for index, hand in enumerate(dna.hands):
        pos = placed.get(hand.cog_id)
        if pos is None:
            continue
        angle = math.pi / 2 - index * math.pi / 4
        tip = (pos[0] + hand.length * math.cos(angle), pos[1] + hand.length * math.sin(angle))
        role = role_by_hand.get(hand.id)
        color = "#c0392b" if role else "#bbbbbb"
        ax.add_patch(FancyArrow(
            pos[0], pos[1], tip[0] - pos[0], tip[1] - pos[1],
            width=0.4, head_width=2.0, color=color, length_includes_head=True,
        ))
        if not compact:
            ax.annotate(role or "%s (idle)" % hand.id, tip, fontsize=8, color=color)

    if not compact:
        ratio_text = ", ".join("%.2f" % r for r in ev.ratios) or "n/a"
        status = "VALID" if ev.valid else "INVALID (%s)" % ev.reason
        ax.set_title(
            "Clock schematic - stage %d, %s\nhand speed ratios (target 60, 12): %s"
            % (ev.stage, status, ratio_text)
        )
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.margins(0.05 if compact else 0.1)
    ax.axis("off")
    fig.tight_layout(pad=0.2 if compact else 1.08)
    return fig


def draw_clock(dna: ClockDNA, config: Config, path: str):
    fig = clock_figure(dna, config)
    fig.savefig(path, dpi=120)
    plt.close(fig)
