"""Unit tests for the Clock Evolution Simulator (run with: python3 -m unittest)."""

import json
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clocksim.config import Config
from clocksim.dna import ClockDNA, Cog, Hand, Mesh, Pendulum, Ratchet, INNER, OUTER
from clocksim.fitness import score, VALID_BASE, STAGE_WEIGHT
from clocksim.genesis import (MAX_HANDS, mutate, random_clock)
from clocksim.mechanics import evaluate


def perfect_clock():
    """A hand-built stage-4 clock: 60:1 seconds->minutes, 12:1 minutes->hours.

    ratchet -> C1.outer; seconds hand on C1
    C1.inner(8)  -> C2.outer(120)  (1/15)
    C2.inner(30) -> C3.outer(120)  (1/4)   => minutes on C3 at 1/60
    C3.inner(10) -> C4.outer(120)  (1/12)
    C4.inner(20) -> C5.outer(20)   (1/1)   => hours on C5 at 1/720
    """
    dna = ClockDNA(
        ratchet=Ratchet(teeth=30),
        pendulum=Pendulum(length=1.0),
        spring_to_ratchet=True,
        pendulum_to_ratchet=True,
        drive_cog="c1",
        drive_surface=OUTER,
        next_id=100,
    )
    dna.cogs = [
        Cog("c1", outer_teeth=60, inner_teeth=8),
        Cog("c2", outer_teeth=120, inner_teeth=30),
        Cog("c3", outer_teeth=120, inner_teeth=10),
        Cog("c4", outer_teeth=120, inner_teeth=20),
        Cog("c5", outer_teeth=20, inner_teeth=8),
    ]
    dna.meshes = [
        Mesh("c1", INNER, "c2", OUTER),
        Mesh("c2", INNER, "c3", OUTER),
        Mesh("c3", INNER, "c4", OUTER),
        Mesh("c4", INNER, "c5", OUTER),
    ]
    dna.hands = [
        Hand("h1", length=20.0, cog_id="c1", surface=OUTER, attachment_radius=5.0),
        Hand("h2", length=40.0, cog_id="c3", surface=OUTER, attachment_radius=5.0),
        Hand("h3", length=30.0, cog_id="c5", surface=OUTER, attachment_radius=5.0),
    ]
    return dna


class TestMechanics(unittest.TestCase):
    def setUp(self):
        self.config = Config()

    def test_perfect_clock_is_stage_4(self):
        ev = evaluate(perfect_clock(), self.config)
        self.assertTrue(ev.valid, ev.reason)
        self.assertEqual(ev.stage, 4)
        self.assertTrue(ev.accurate)
        self.assertEqual(len(ev.ratios), 2)
        self.assertAlmostEqual(ev.ratios[0], 60.0, places=6)   # seconds : minutes
        self.assertAlmostEqual(ev.ratios[1], 12.0, places=6)   # minutes : hours

    def test_gear_ratio_propagation(self):
        ev = evaluate(perfect_clock(), self.config)
        w1, w3, w5 = ev.omegas["c1"], ev.omegas["c3"], ev.omegas["c5"]
        self.assertAlmostEqual(abs(w1) / abs(w3), 60.0, places=6)    # seconds : minutes
        self.assertAlmostEqual(abs(w1) / abs(w5), 720.0, places=4)   # seconds : hours

    def test_mesh_reverses_direction(self):
        ev = evaluate(perfect_clock(), self.config)
        self.assertLess(ev.omegas["c1"] * ev.omegas["c2"], 0)

    def test_no_escapement_is_stage_0(self):
        dna = perfect_clock()
        dna.pendulum_to_ratchet = False
        ev = evaluate(dna, self.config)
        self.assertEqual(ev.stage, 0)
        self.assertEqual(ev.omegas, {})

    def test_hand_counts_set_stage(self):
        dna = perfect_clock()
        dna.hands = dna.hands[:1]
        self.assertEqual(evaluate(dna, self.config).stage, 2)
        dna = perfect_clock()
        dna.hands = dna.hands[:2]
        self.assertEqual(evaluate(dna, self.config).stage, 3)
        dna = perfect_clock()
        dna.hands = []
        self.assertEqual(evaluate(dna, self.config).stage, 1)

    def test_wrong_ratio_is_stage_4_but_inaccurate(self):
        # Three hands still turn, so it reaches the top *structural* stage (4),
        # but the ratios are off, so it is not a working clock. Accuracy is a
        # continuous reward, not a stage gate.
        dna = perfect_clock()
        dna.cogs[1].inner_teeth = 40  # 60:1 becomes 45:1
        ev = evaluate(dna, self.config)
        self.assertTrue(ev.valid)
        self.assertEqual(ev.stage, 4)
        self.assertFalse(ev.accurate)

    def test_inconsistent_cycle_is_deadlock(self):
        dna = ClockDNA(
            ratchet=Ratchet(teeth=30),
            pendulum=Pendulum(length=1.0),
            spring_to_ratchet=True,
            pendulum_to_ratchet=True,
            drive_cog="a",
            drive_surface=OUTER,
        )
        dna.cogs = [
            Cog("a", outer_teeth=60, inner_teeth=8),
            Cog("b", outer_teeth=120, inner_teeth=30),
            Cog("c", outer_teeth=100, inner_teeth=12),
        ]
        dna.meshes = [
            Mesh("a", OUTER, "b", OUTER),
            Mesh("b", INNER, "c", OUTER),
            Mesh("c", INNER, "a", INNER),
        ]
        ev = evaluate(dna, self.config)
        self.assertFalse(ev.valid)
        self.assertIn("deadlock", ev.reason)
        self.assertEqual(ev.stage, 0)

    def test_directional_lock_is_invalid(self):
        # Three identical cogs meshed outer-outer in a triangle: every gear
        # ratio is 1, so the only conflict is direction. Going round the odd
        # cycle flips the sign three times, demanding a cog turn both ways at
        # once - a rotational lock that must be rejected even though the
        # speeds match. (Such topologies become reachable once a cog may hold
        # more than two meshes.)
        dna = ClockDNA(
            ratchet=Ratchet(teeth=30),
            pendulum=Pendulum(length=1.0),
            spring_to_ratchet=True,
            pendulum_to_ratchet=True,
            drive_cog="a",
            drive_surface=OUTER,
        )
        dna.cogs = [
            Cog("a", outer_teeth=40, inner_teeth=8),
            Cog("b", outer_teeth=40, inner_teeth=8),
            Cog("c", outer_teeth=40, inner_teeth=8),
        ]
        dna.meshes = [
            Mesh("a", OUTER, "b", OUTER),
            Mesh("b", OUTER, "c", OUTER),
            Mesh("c", OUTER, "a", OUTER),
        ]
        ev = evaluate(dna, self.config)
        self.assertFalse(ev.valid)
        self.assertIn("deadlock", ev.reason)
        self.assertEqual(ev.stage, 0)
        self.assertLess(score(dna, ev, self.config), VALID_BASE)


class TestFitness(unittest.TestCase):
    def setUp(self):
        self.config = Config()

    def _score(self, dna):
        ev = evaluate(dna, self.config)
        return score(dna, ev, self.config), ev

    def test_stage_dominance(self):
        scores = []
        dna = perfect_clock()           # stage 4, accurate
        scores.append(self._score(dna)[0])
        dna = perfect_clock()           # stage 4, wrong ratio (accuracy lower)
        dna.cogs[1].inner_teeth = 40
        scores.append(self._score(dna)[0])
        dna = perfect_clock()           # stage 2 (one rotating hand)
        dna.hands = dna.hands[:1]
        scores.append(self._score(dna)[0])
        dna = perfect_clock()           # stage 1 (escapement only)
        dna.hands = []
        scores.append(self._score(dna)[0])
        dna = perfect_clock()           # stage 0 (no spring power)
        dna.spring_to_ratchet = False
        scores.append(self._score(dna)[0])
        for higher, lower in zip(scores, scores[1:]):
            self.assertGreater(higher, lower)

    def test_invalid_scores_below_valid(self):
        dna = perfect_clock()
        dna.meshes.append(Mesh("c5", INNER, "c1", OUTER))  # inconsistent cycle
        bad_score, ev = self._score(dna)
        self.assertFalse(ev.valid)
        empty = ClockDNA(ratchet=Ratchet(teeth=20), pendulum=Pendulum(length=1.0))
        empty_score, _ = self._score(empty)
        self.assertLess(bad_score, 100)
        self.assertGreaterEqual(empty_score, 100)

    def test_accuracy_gradient(self):
        # Closer ratios always score higher (continuous, within the top stage).
        near = perfect_clock()
        near.cogs[1].inner_teeth = 29   # ratio 58:1
        far = perfect_clock()
        far.cogs[1].inner_teeth = 15    # ratio 30:1
        self.assertGreater(self._score(near)[0], self._score(far)[0])

    def test_accuracy_has_no_cliff_at_tolerance(self):
        # Crossing ratio_tolerance must not create a stage jump: a barely
        # inaccurate three-handed clock shares stage 4 with the perfect one, so
        # the score gap is only the continuous accuracy term, well under a stage.
        good_s, good_ev = self._score(perfect_clock())
        off = perfect_clock()
        off.cogs[1].inner_teeth = 31     # ~3% off 60 -> not within tolerance
        off_s, off_ev = self._score(off)
        self.assertEqual(good_ev.stage, off_ev.stage)   # both stage 4
        self.assertFalse(off_ev.accurate)               # but not a working clock
        self.assertGreater(good_s, off_s)               # closer still wins
        self.assertLess(good_s - off_s, STAGE_WEIGHT)   # no cliff at the tolerance

    def test_material_prunes_redundant_cog(self):
        # An identical clock carrying an extra unpowered cog is heavier and so
        # scores lower - the gradient that pressures evolution to delete dead cogs.
        base = perfect_clock()
        heavy = perfect_clock()
        heavy.cogs.append(Cog("spare", outer_teeth=120, inner_teeth=8))  # unpowered
        base_s, base_ev = self._score(base)
        heavy_s, heavy_ev = self._score(heavy)
        self.assertTrue(base_ev.accurate and heavy_ev.accurate)  # the cog changes nothing functional
        self.assertEqual(base_ev.stage, heavy_ev.stage)
        self.assertGreater(base_s, heavy_s)                      # but the extra mass costs

    def test_material_weight_zero_disables_penalty(self):
        cfg = Config(material_weight=0.0)
        base = perfect_clock()
        heavy = perfect_clock()
        heavy.cogs.append(Cog("spare", outer_teeth=120, inner_teeth=8))
        s_base = score(base, evaluate(base, cfg), cfg)
        s_heavy = score(heavy, evaluate(heavy, cfg), cfg)
        self.assertAlmostEqual(s_base, s_heavy)  # no material term -> identical


class TestGenesis(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.rng = random.Random(42)

    def check_invariants(self, dna):
        self.assertLessEqual(len(dna.hands), MAX_HANDS)
        cog_ids = {c.id for c in dna.cogs}
        for cog in dna.cogs:
            self.assertGreaterEqual(cog.inner_teeth, self.config.min_cog_teeth)
            self.assertLessEqual(cog.outer_teeth, self.config.max_cog_teeth)
            self.assertLessEqual(
                cog.inner_teeth + self.config.min_inner_outer_gap, cog.outer_teeth
            )
            self.assertLessEqual(dna.cog_mesh_count(cog.id), self.config.max_meshes_per_cog)
        for hand in dna.hands:
            self.assertIn(hand.cog_id, cog_ids)
        for mesh in dna.meshes:
            self.assertIn(mesh.cog_a, cog_ids)
            self.assertIn(mesh.cog_b, cog_ids)
        if dna.drive_cog is not None:
            self.assertIn(dna.drive_cog, cog_ids)

    def test_random_clocks_evaluate(self):
        for _ in range(300):
            dna = random_clock(self.rng, self.config)
            self.check_invariants(dna)
            ev = evaluate(dna, self.config)
            self.assertGreaterEqual(score(dna, ev, self.config), 0.0)

    def test_mutations_preserve_invariants(self):
        dna = random_clock(self.rng, self.config)
        for _ in range(2000):
            dna = mutate(dna, self.rng, self.config)
            self.check_invariants(dna)

    def test_max_meshes_per_cog_is_configurable(self):
        # A raised limit must be honoured by every mesh-adding operator, and a
        # cog must actually be allowed to exceed the spec's default of 2.
        config = Config(max_meshes_per_cog=4)
        dna = random_clock(self.rng, config)
        seen_above_two = False
        for _ in range(3000):
            dna = mutate(dna, self.rng, config)
            for cog in dna.cogs:
                count = dna.cog_mesh_count(cog.id)
                self.assertLessEqual(count, config.max_meshes_per_cog)
                seen_above_two = seen_above_two or count > 2
        self.assertTrue(seen_above_two, "raised limit never produced a 3rd mesh")

    def test_serialization_roundtrip(self):
        dna = perfect_clock()
        data = json.loads(json.dumps(dna.to_dict()))
        self.assertEqual(ClockDNA.from_dict(data).to_dict(), dna.to_dict())


class TestEvolution(unittest.TestCase):
    def test_smoke_run_writes_outputs(self):
        from clocksim.evolution import run_evolution
        config = Config()
        config.population_size = 12
        config.generations_per_run = 300
        config.visualization_frequency = 50
        config.random_seed = 7
        config.stop_on_success = True
        out_dir = tempfile.mkdtemp(prefix="clocksim_test_")
        try:
            history = run_evolution(config, out_dir, quiet=True)
            for name in ("history.json", "best_clock.json", "best_clock.png",
                         "hands_over_time.png", "accuracy_over_time.png",
                         "fitness_over_time.png"):
                self.assertTrue(os.path.exists(os.path.join(out_dir, name)), name)
            self.assertGreaterEqual(history["result"]["best_score"], 0.0)
            self.assertTrue(history["snapshots"])
        finally:
            shutil.rmtree(out_dir)


class TestWebApp(unittest.TestCase):
    def small_overrides(self):
        return {"population_size": 12, "generations_per_run": 400,
                "visualization_frequency": 50, "random_seed": 7}

    def test_app_state_run_and_render(self):
        from clocksim.webapp import AppState
        state = AppState(Config())
        state.start(self.small_overrides())
        state.thread.join(timeout=60)
        self.assertFalse(state.thread.is_alive())
        status = state.status()
        self.assertTrue(status["started"])
        self.assertFalse(status["running"])
        self.assertIsNone(status["error"])
        self.assertGreaterEqual(len(status["improvements"]), 1)
        # All renderable artifacts produce PNG bytes.
        for chart in ("hands", "accuracy", "fitness"):
            self.assertTrue(state.chart_png(chart).startswith(b"\x89PNG"))
        self.assertTrue(state.clock_png(0, "small").startswith(b"\x89PNG"))
        self.assertTrue(state.clock_png(0, "full").startswith(b"\x89PNG"))

    def test_rejects_bad_config_and_double_start(self):
        from clocksim.webapp import AppState, build_config
        state = AppState(Config())
        with self.assertRaises(ValueError):
            build_config(Config(), {"no_such_key": 1})
        with self.assertRaises(ValueError):
            build_config(Config(), {"selection_method": "bogus"})
        overrides = self.small_overrides()
        overrides["generations_per_run"] = 100000
        overrides["stop_on_success"] = False
        state.start(overrides)
        try:
            with self.assertRaises(RuntimeError):
                state.start(overrides)
        finally:
            state.stop()
            state.thread.join(timeout=60)
        self.assertTrue(state.status()["stopped"])

    def test_http_endpoints(self):
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        from clocksim.webapp import AppState, Handler

        Handler.state = AppState(Config())
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % port

        def get(path):
            with urllib.request.urlopen(base + path) as resp:
                return resp.read()

        try:
            self.assertIn(b"Clock Evolution Simulator", get("/"))
            defaults = json.loads(get("/api/defaults"))
            self.assertIn("population_size", defaults["values"])
            body = json.dumps(self.small_overrides()).encode()
            req = urllib.request.Request(base + "/api/run", data=body, method="POST")
            self.assertTrue(json.loads(urllib.request.urlopen(req).read())["ok"])
            Handler.state.thread.join(timeout=60)
            status = json.loads(get("/api/status"))
            self.assertFalse(status["running"])
            self.assertTrue(get("/api/plot/hands.png").startswith(b"\x89PNG"))
            self.assertTrue(get("/api/clock/0.png").startswith(b"\x89PNG"))
            self.assertIn("cogs", json.loads(get("/api/clock/0.json")))
            self.assertIn("snapshots", json.loads(get("/api/history.json")))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
