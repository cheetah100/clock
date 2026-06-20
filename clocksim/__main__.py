"""Command-line interface for the Clock Evolution Simulator.

Usage:
    python3 -m clocksim serve [--config config.json] [--port 8123]
    python3 -m clocksim run [--config config.json] [--output results] [--seed N] [--quiet]
    python3 -m clocksim visualize <clock.json> [--config config.json] [-o out.png]
    python3 -m clocksim plot <history.json> [-o out_dir]
"""

import argparse
import json
import os
import sys

from .config import Config
from .dna import ClockDNA


def cmd_run(args):
    config = Config.load(args.config)
    if args.seed is not None:
        config.random_seed = args.seed
    if args.generations is not None:
        config.generations_per_run = args.generations
    from .evolution import run_evolution
    history = run_evolution(config, args.output, quiet=args.quiet)
    result = history["result"]
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


def cmd_visualize(args):
    config = Config.load(args.config)
    with open(args.clock) as fh:
        data = json.load(fh)
    # Accept either a bare DNA file or a history file.
    dna_dict = data.get("best_clock", data)
    dna = ClockDNA.from_dict(dna_dict)
    from .visualization import draw_clock
    draw_clock(dna, config, args.output)
    print("Wrote %s" % args.output)
    return 0


def cmd_plot(args):
    with open(args.history) as fh:
        history = json.load(fh)
    from .visualization import plot_history
    plot_history(history, args.output)
    print("Wrote plots to %s/" % args.output)
    return 0


def cmd_serve(args):
    config_path = args.config
    if config_path is None and os.path.exists("config.json"):
        config_path = "config.json"
    from .webapp import serve
    serve(config_path, host=args.host, port=args.port)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="clocksim",
                                     description="Clock Evolution Simulator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_srv = sub.add_parser("serve", help="launch the interactive web UI")
    p_srv.add_argument("--config", default=None,
                       help="JSON config providing the form defaults "
                            "(default: ./config.json if present)")
    p_srv.add_argument("--host", default="127.0.0.1", help="bind address")
    p_srv.add_argument("--port", type=int, default=8123, help="port (default 8123)")
    p_srv.set_defaults(func=cmd_serve)

    p_run = sub.add_parser("run", help="run an evolutionary simulation")
    p_run.add_argument("--config", default=None, help="path to JSON config file")
    p_run.add_argument("--output", default="results", help="output directory")
    p_run.add_argument("--seed", type=int, default=None, help="random seed override")
    p_run.add_argument("--generations", type=int, default=None,
                       help="generation limit override")
    p_run.add_argument("--quiet", action="store_true", help="suppress progress output")
    p_run.set_defaults(func=cmd_run)

    p_vis = sub.add_parser("visualize", help="render a stored clock DNA as a schematic")
    p_vis.add_argument("clock", help="clock DNA JSON (or history.json)")
    p_vis.add_argument("--config", default=None, help="path to JSON config file")
    p_vis.add_argument("-o", "--output", default="clock.png", help="output PNG path")
    p_vis.set_defaults(func=cmd_visualize)

    p_plot = sub.add_parser("plot", help="regenerate progress graphs from a history file")
    p_plot.add_argument("history", help="history.json from a previous run")
    p_plot.add_argument("-o", "--output", default=".", help="output directory")
    p_plot.set_defaults(func=cmd_plot)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
