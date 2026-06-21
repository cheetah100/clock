"""Interactive web UI: a stdlib HTTP server wrapping the evolution engine.

Run with:  python3 -m clocksim serve [--config config.json] [--port 8123]

Endpoints:
    GET  /                      the single-page UI
    GET  /api/defaults          config defaults shown in the settings form
    POST /api/run               start a run (body: JSON config overrides)
    POST /api/stop              cancel the running simulation
    GET  /api/status            live progress + improvement timeline
    GET  /api/plot/<name>.png   hands | accuracy | fitness | mass chart
    GET  /api/clock/<i>.png     schematic of improvement i (?size=full for large)
    GET  /api/clock/<i>.json    DNA of improvement i
    GET  /api/history.json      full run history (downloadable)
    GET  /api/best_clock.json   best DNA so far (downloadable)
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import Config
from .dna import ClockDNA
from .evolution import EvolutionEngine
from .visualization import CHART_NAMES, clock_figure, figure_png_bytes, history_figure

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# matplotlib is not thread-safe; serialize all rendering.
RENDER_LOCK = threading.Lock()

# Form fields exposed in the UI, in display order (mutation_weights stays
# server-side; edit the config file for that).
FORM_FIELDS = [
    "min_cog_teeth", "max_cog_teeth", "min_ratchet_teeth", "max_ratchet_teeth",
    "min_inner_outer_gap", "max_cogs", "max_meshes_per_cog",
    "population_size", "mutation_rate", "selection_method", "tournament_size",
    "generations_per_run", "visualization_frequency", "ratio_tolerance",
    "material_weight", "stop_on_success", "random_seed",
]


def build_config(base: Config, overrides) -> Config:
    data = base.to_dict()
    for key, value in overrides.items():
        if key not in data:
            raise ValueError("Unknown config key: %r" % key)
        data[key] = value
    config = Config()
    for key, value in data.items():
        if key == "mutation_weights":
            config.mutation_weights.update(value)
        else:
            setattr(config, key, value)
    config.validate()
    return config


class AppState:
    def __init__(self, base_config: Config):
        self.base_config = base_config
        self.lock = threading.Lock()
        self.engine = None
        self.thread = None
        self.stop_requested = False
        self.run_id = 0
        self.error = None
        self.png_cache = {}

    # ---- run control ------------------------------------------------------

    def start(self, overrides) -> None:
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise RuntimeError("A simulation is already running")
            config = build_config(self.base_config, overrides)
            self.stop_requested = False
            self.error = None
            self.run_id += 1
            self.png_cache.clear()
            self.engine = EvolutionEngine(config)
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self):
        try:
            self.engine.run(should_stop=lambda: self.stop_requested)
        except Exception as exc:  # surfaced via /api/status
            self.error = "%s: %s" % (type(exc).__name__, exc)

    def stop(self):
        self.stop_requested = True

    # ---- views ------------------------------------------------------------

    def status(self):
        engine = self.engine
        if engine is None:
            return {"run_id": 0, "running": False, "started": False}
        running = self.thread is not None and self.thread.is_alive()
        improvements = [
            {
                "index": i,
                "generation": entry["generation"],
                "score": entry["score"],
                "stage": entry["stage"],
                "rotating_hands": entry["rotating_hands"],
                "accurate": entry["accurate"],
                "ratios": entry["ratios"],
            }
            for i, entry in enumerate(engine.improvements)
        ]
        return {
            "run_id": self.run_id,
            "started": True,
            "running": running,
            "stopped": self.stop_requested,
            "error": self.error,
            "generation": engine.generation,
            "generation_limit": engine.config.generations_per_run,
            "snapshot_count": len(engine.snapshots),
            "success": engine.success,
            "success_generation": engine.success_generation,
            "best_score": engine.best_eval.score,
            "best_stage": engine.best_eval.stage,
            "best_ratios": list(engine.best_eval.ratios),
            "improvements": improvements,
        }

    def chart_png(self, name: str) -> bytes:
        if self.engine is None:
            raise KeyError("no run yet")
        history = {"snapshots": list(self.engine.snapshots)}
        with RENDER_LOCK:
            return figure_png_bytes(history_figure(name, history))

    def clock_png(self, index: int, size: str) -> bytes:
        if self.engine is None:
            raise KeyError("no run yet")
        key = (self.run_id, index, size)
        cached = self.png_cache.get(key)
        if cached is not None:
            return cached
        entry = self.engine.improvements[index]
        dna = ClockDNA.from_dict(entry["dna"])
        with RENDER_LOCK:
            fig = clock_figure(dna, self.engine.config, compact=(size != "full"))
            png = figure_png_bytes(fig, dpi=70 if size != "full" else 120)
        self.png_cache[key] = png
        return png


class Handler(BaseHTTPRequestHandler):
    state = None  # type: AppState

    def log_message(self, fmt, *args):
        pass  # keep the console quiet

    # ---- helpers ----------------------------------------------------------

    def _send(self, code, content_type, body, download=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", "attachment; filename=%s" % download)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, "application/json", json.dumps(data).encode())

    def _error(self, message, code=400):
        self._json({"error": message}, code)

    # ---- routing ----------------------------------------------------------

    def do_GET(self):
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as fh:
                    self._send(200, "text/html; charset=utf-8", fh.read())
            elif path == "/api/defaults":
                data = self.state.base_config.to_dict()
                self._json({"fields": FORM_FIELDS, "values": data})
            elif path == "/api/status":
                self._json(self.state.status())
            elif path.startswith("/api/plot/") and path.endswith(".png"):
                name = path[len("/api/plot/"):-len(".png")]
                if name not in CHART_NAMES:
                    raise KeyError(name)
                self._send(200, "image/png", self.state.chart_png(name))
            elif path.startswith("/api/clock/") and path.endswith(".png"):
                index = int(path[len("/api/clock/"):-len(".png")])
                size = (query.get("size") or ["small"])[0]
                self._send(200, "image/png", self.state.clock_png(index, size))
            elif path.startswith("/api/clock/") and path.endswith(".json"):
                index = int(path[len("/api/clock/"):-len(".json")])
                entry = self.state.engine.improvements[index]
                self._send(200, "application/json", json.dumps(entry["dna"], indent=1).encode(),
                           download="clock_gen%d.json" % entry["generation"])
            elif path == "/api/history.json":
                body = json.dumps(self.state.engine.history(), indent=1).encode()
                self._send(200, "application/json", body, download="history.json")
            elif path == "/api/best_clock.json":
                body = json.dumps(self.state.engine.best_dna.to_dict(), indent=1).encode()
                self._send(200, "application/json", body, download="best_clock.json")
            else:
                self._error("Not found", 404)
        except (KeyError, IndexError, ValueError, AttributeError):
            self._error("Not found", 404)
        except BrokenPipeError:
            pass

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/run":
                length = int(self.headers.get("Content-Length") or 0)
                overrides = json.loads(self.rfile.read(length) or b"{}")
                try:
                    self.state.start(overrides)
                except (RuntimeError, ValueError, TypeError) as exc:
                    return self._error(str(exc))
                self._json({"ok": True, "run_id": self.state.run_id})
            elif path == "/api/stop":
                self.state.stop()
                self._json({"ok": True})
            else:
                self._error("Not found", 404)
        except BrokenPipeError:
            pass


def serve(config_path=None, host="127.0.0.1", port=8123):
    base_config = Config.load(config_path)
    Handler.state = AppState(base_config)
    server = ThreadingHTTPServer((host, port), Handler)
    print("Clock Evolution Simulator UI: http://%s:%d/  (Ctrl-C to quit)" % (host, port))
    if config_path:
        print("Settings form defaults loaded from %s" % config_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
