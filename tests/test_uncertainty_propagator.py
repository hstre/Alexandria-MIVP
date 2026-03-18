"""
Tests für Uncertainty Propagation über Claim-Graphen.
"""

import sys
import os
import math
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import Node, Patch, Uncertainty, AlexandriaStore
from uncertainty_propagator import (
    UncertaintyPropagator,
    PropagationMode,
    PropagationResult,
    PropagationReport,
    _combine_sigmas,
    _quadrature,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(node_id: str, sigma: float = 0.1, n: int = None) -> Node:
    unc = Uncertainty(sigma=sigma, n=n) if sigma > 0 else None
    return Node(
        node_id=node_id,
        category="EMPIRICAL",
        content=f"Content of {node_id}",
        assumptions=[],
        uncertainty=unc,
        stability=0.8,
    )


def _node_no_unc(node_id: str) -> Node:
    return Node(
        node_id=node_id,
        category="MODEL",
        content=f"Content of {node_id}",
        assumptions=[],
        uncertainty=None,
    )


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) < tol


# ---------------------------------------------------------------------------
# Tests: _combine_sigmas
# ---------------------------------------------------------------------------

class TestCombineSigmas(unittest.TestCase):
    def test_empty_list_returns_zero(self):
        self.assertEqual(_combine_sigmas([], PropagationMode.SUM_IN_QUADRATURE), 0.0)

    def test_sum_in_quadrature(self):
        result = _combine_sigmas([3.0, 4.0], PropagationMode.SUM_IN_QUADRATURE)
        self.assertAlmostEqual(result, 5.0, places=9)

    def test_weighted_mean(self):
        # σ = 0.1, both equal → combined = 1/√(1/0.01 + 1/0.01) = 1/√200 ≈ 0.0707
        result = _combine_sigmas([0.1, 0.1], PropagationMode.WEIGHTED_MEAN)
        self.assertAlmostEqual(result, 1.0 / math.sqrt(200), places=9)

    def test_max(self):
        result = _combine_sigmas([0.1, 0.5, 0.3], PropagationMode.MAX)
        self.assertAlmostEqual(result, 0.5, places=9)

    def test_mean(self):
        result = _combine_sigmas([0.1, 0.3], PropagationMode.MEAN)
        self.assertAlmostEqual(result, 0.2, places=9)

    def test_linear(self):
        result = _combine_sigmas([0.1, 0.2, 0.3], PropagationMode.LINEAR)
        self.assertAlmostEqual(result, 0.6, places=9)

    def test_zeros_excluded(self):
        result = _combine_sigmas([0.0, 0.2, 0.0], PropagationMode.MAX)
        self.assertAlmostEqual(result, 0.2, places=9)

    def test_all_zeros_returns_zero(self):
        result = _combine_sigmas([0.0, 0.0], PropagationMode.SUM_IN_QUADRATURE)
        self.assertEqual(result, 0.0)


# ---------------------------------------------------------------------------
# Tests: _quadrature
# ---------------------------------------------------------------------------

class TestQuadrature(unittest.TestCase):
    def test_3_4_gives_5(self):
        self.assertAlmostEqual(_quadrature(3.0, 4.0), 5.0, places=9)

    def test_zero_a(self):
        self.assertAlmostEqual(_quadrature(0.0, 0.5), 0.5, places=9)

    def test_zero_b(self):
        self.assertAlmostEqual(_quadrature(0.3, 0.0), 0.3, places=9)


# ---------------------------------------------------------------------------
# Tests: UncertaintyPropagator – basic setup
# ---------------------------------------------------------------------------

class TestPropagatorSetup(unittest.TestCase):
    def test_empty_nodes(self):
        p = UncertaintyPropagator({})
        report = p.propagate()
        self.assertEqual(len(report.results), 0)

    def test_single_node_no_deps(self):
        nodes = {"A": _node("A", 0.2)}
        p = UncertaintyPropagator(nodes)
        report = p.propagate()
        r = report.results["A"]
        self.assertAlmostEqual(r.local_sigma, 0.2, places=9)
        self.assertAlmostEqual(r.propagated_sigma, 0.0, places=9)
        self.assertAlmostEqual(r.combined_sigma, 0.2, places=9)
        self.assertEqual(r.depth, 0)
        self.assertEqual(r.contributing_nodes, [])

    def test_node_without_uncertainty_sigma_zero(self):
        nodes = {"X": _node_no_unc("X")}
        p = UncertaintyPropagator(nodes)
        report = p.propagate()
        r = report.results["X"]
        self.assertEqual(r.local_sigma, 0.0)
        self.assertEqual(r.combined_sigma, 0.0)


# ---------------------------------------------------------------------------
# Tests: Dependency registration
# ---------------------------------------------------------------------------

class TestDependencyRegistration(unittest.TestCase):
    def setUp(self):
        self.nodes = {"A": _node("A"), "B": _node("B")}
        self.p = UncertaintyPropagator(self.nodes)

    def test_register_dependency(self):
        self.p.register_dependency("A", "B")
        self.assertEqual(self.p.get_dependencies("A"), ["B"])

    def test_idempotent_registration(self):
        self.p.register_dependency("A", "B")
        self.p.register_dependency("A", "B")
        self.assertEqual(len(self.p.get_dependencies("A")), 1)

    def test_get_dependents(self):
        self.p.register_dependency("A", "B")
        self.assertEqual(self.p.get_dependents("B"), ["A"])

    def test_no_deps_returns_empty(self):
        self.assertEqual(self.p.get_dependencies("A"), [])


# ---------------------------------------------------------------------------
# Tests: build_from_patches
# ---------------------------------------------------------------------------

class TestBuildFromPatches(unittest.TestCase):
    def _make_patch(self, target_id, depends_on=None):
        payload = {"content": "test content here", "assumptions": []}
        if depends_on:
            payload["depends_on"] = depends_on
        return Patch(
            patch_id=f"p_{target_id}",
            parent_patch_id=None,
            branch_id="main",
            timestamp=int(time.time()),
            operation="ADD",
            target_id=target_id,
            category="EMPIRICAL",
            payload=payload,
            audit={"validated": True, "decay": 0.01},
            uncertainty=None,
            chain=None,
        )

    def test_extracts_dependencies(self):
        patches = [
            self._make_patch("A"),
            self._make_patch("B", depends_on=["A"]),
        ]
        nodes = {"A": _node("A"), "B": _node("B")}
        p = UncertaintyPropagator(nodes)
        count = p.build_from_patches(patches)
        self.assertEqual(count, 1)
        self.assertEqual(p.get_dependencies("B"), ["A"])

    def test_multiple_deps_extracted(self):
        patches = [
            self._make_patch("A"),
            self._make_patch("B"),
            self._make_patch("C", depends_on=["A", "B"]),
        ]
        nodes = {"A": _node("A"), "B": _node("B"), "C": _node("C")}
        p = UncertaintyPropagator(nodes)
        count = p.build_from_patches(patches)
        self.assertEqual(count, 2)
        self.assertIn("A", p.get_dependencies("C"))
        self.assertIn("B", p.get_dependencies("C"))

    def test_deprecate_patches_ignored(self):
        patch = Patch(
            patch_id="p_dep",
            parent_patch_id=None,
            branch_id="main",
            timestamp=int(time.time()),
            operation="DEPRECATE",
            target_id="D",
            category="EMPIRICAL",
            payload={"depends_on": ["A"]},
            audit={},
            uncertainty=None,
            chain=None,
        )
        p = UncertaintyPropagator({"A": _node("A"), "D": _node("D")})
        count = p.build_from_patches([patch])
        self.assertEqual(count, 0)


# ---------------------------------------------------------------------------
# Tests: Propagation – simple chain A → B → C
# ---------------------------------------------------------------------------

class TestSimpleChain(unittest.TestCase):
    """
    A is a leaf (sigma=0.1).
    B depends on A (sigma=0.2).
    C depends on B (sigma=0.3).
    """
    def setUp(self):
        self.nodes = {
            "A": _node("A", 0.1),
            "B": _node("B", 0.2),
            "C": _node("C", 0.3),
        }
        self.p = UncertaintyPropagator(self.nodes)
        self.p.register_dependency("B", "A")
        self.p.register_dependency("C", "B")

    def _run(self, mode=PropagationMode.SUM_IN_QUADRATURE, decay=1.0):
        return self.p.propagate(mode=mode, decay=decay)

    def test_A_is_leaf(self):
        report = self._run()
        r = report.results["A"]
        self.assertEqual(r.depth, 0)
        self.assertAlmostEqual(r.combined_sigma, 0.1, places=9)

    def test_B_propagates_from_A(self):
        report = self._run()
        r = report.results["B"]
        self.assertEqual(r.depth, 1)
        # propagated = 0.1 (from A), local = 0.2
        # combined = sqrt(0.2² + 0.1²) = sqrt(0.05)
        expected = math.sqrt(0.2**2 + 0.1**2)
        self.assertAlmostEqual(r.combined_sigma, expected, places=9)

    def test_C_propagates_from_B(self):
        report = self._run()
        r = report.results["C"]
        self.assertEqual(r.depth, 2)
        b_combined = report.results["B"].combined_sigma
        # propagated from B's combined; combined_C = sqrt(0.3² + b_combined²)
        expected = math.sqrt(0.3**2 + b_combined**2)
        self.assertAlmostEqual(r.combined_sigma, expected, places=9)

    def test_C_contributing_nodes_include_A_and_B(self):
        report = self._run()
        r = report.results["C"]
        self.assertIn("B", r.contributing_nodes)
        self.assertIn("A", r.contributing_nodes)

    def test_A_no_contributing_nodes(self):
        report = self._run()
        self.assertEqual(report.results["A"].contributing_nodes, [])

    def test_decay_reduces_propagated_sigma(self):
        report_no_decay = self._run(decay=1.0)
        report_with_decay = self._run(decay=0.5)
        # B with decay: propagated = A.combined * 0.5^1 = 0.1 * 0.5 = 0.05
        r_decay = report_with_decay.results["B"]
        self.assertLess(r_decay.propagated_sigma, 0.1)
        self.assertLess(r_decay.combined_sigma, report_no_decay.results["B"].combined_sigma)


# ---------------------------------------------------------------------------
# Tests: Propagation modes
# ---------------------------------------------------------------------------

class TestPropagationModes(unittest.TestCase):
    """
    Fan-in: C depends on A (σ=0.3) and B (σ=0.4), C has σ=0.1.
    """
    def setUp(self):
        self.nodes = {
            "A": _node("A", 0.3),
            "B": _node("B", 0.4),
            "C": _node("C", 0.1),
        }
        self.p = UncertaintyPropagator(self.nodes)
        self.p.register_dependency("C", "A")
        self.p.register_dependency("C", "B")

    def _propagated(self, mode):
        return self.p.propagate(mode=mode).results["C"].propagated_sigma

    def test_sum_in_quadrature(self):
        result = self._propagated(PropagationMode.SUM_IN_QUADRATURE)
        expected = math.sqrt(0.3**2 + 0.4**2)  # = 0.5
        self.assertAlmostEqual(result, expected, places=9)

    def test_max(self):
        result = self._propagated(PropagationMode.MAX)
        self.assertAlmostEqual(result, 0.4, places=9)

    def test_mean(self):
        result = self._propagated(PropagationMode.MEAN)
        self.assertAlmostEqual(result, 0.35, places=9)

    def test_linear(self):
        result = self._propagated(PropagationMode.LINEAR)
        self.assertAlmostEqual(result, 0.7, places=9)

    def test_combined_adds_local_in_quadrature(self):
        # combined = sqrt(local² + propagated²)
        report = self.p.propagate(mode=PropagationMode.SUM_IN_QUADRATURE)
        r = report.results["C"]
        expected = math.sqrt(0.1**2 + r.propagated_sigma**2)
        self.assertAlmostEqual(r.combined_sigma, expected, places=9)


# ---------------------------------------------------------------------------
# Tests: Node without uncertainty as dependency
# ---------------------------------------------------------------------------

class TestNoDependencyUncertainty(unittest.TestCase):
    def test_dep_without_sigma_contributes_zero(self):
        nodes = {
            "A": _node_no_unc("A"),
            "B": _node("B", 0.2),
        }
        p = UncertaintyPropagator(nodes)
        p.register_dependency("B", "A")
        report = p.propagate()
        r_b = report.results["B"]
        # A contributes 0.0, so propagated = 0, combined = local = 0.2
        self.assertAlmostEqual(r_b.propagated_sigma, 0.0, places=9)
        self.assertAlmostEqual(r_b.combined_sigma, 0.2, places=9)


# ---------------------------------------------------------------------------
# Tests: Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection(unittest.TestCase):
    def setUp(self):
        self.nodes = {
            "A": _node("A", 0.1),
            "B": _node("B", 0.2),
            "C": _node("C", 0.3),
        }

    def test_no_cycle(self):
        p = UncertaintyPropagator(self.nodes)
        p.register_dependency("B", "A")
        p.register_dependency("C", "B")
        cycles = p.detect_cycles()
        self.assertEqual(cycles, [])

    def test_simple_cycle(self):
        p = UncertaintyPropagator(self.nodes)
        p.register_dependency("A", "B")
        p.register_dependency("B", "A")
        cycles = p.detect_cycles()
        self.assertGreater(len(cycles), 0)

    def test_cycle_nodes_get_inf_sigma(self):
        p = UncertaintyPropagator(self.nodes)
        p.register_dependency("A", "B")
        p.register_dependency("B", "A")
        report = p.propagate()
        # A and B are in cycles → combined_sigma = inf
        for nid in ("A", "B"):
            self.assertEqual(report.results[nid].combined_sigma, float("inf"))

    def test_cycle_depth_sentinel(self):
        p = UncertaintyPropagator(self.nodes)
        p.register_dependency("A", "B")
        p.register_dependency("B", "A")
        report = p.propagate()
        for nid in ("A", "B"):
            self.assertEqual(report.results[nid].depth, -1)

    def test_non_cycle_node_unaffected(self):
        p = UncertaintyPropagator(self.nodes)
        p.register_dependency("A", "B")
        p.register_dependency("B", "A")
        # C has no dependencies → clean
        report = p.propagate()
        self.assertAlmostEqual(report.results["C"].combined_sigma, 0.3, places=9)
        self.assertEqual(report.results["C"].depth, 0)

    def test_cycles_in_report(self):
        p = UncertaintyPropagator(self.nodes)
        p.register_dependency("A", "B")
        p.register_dependency("B", "A")
        report = p.propagate()
        self.assertGreater(len(report.cycles), 0)


# ---------------------------------------------------------------------------
# Tests: dependency_depth
# ---------------------------------------------------------------------------

class TestDependencyDepth(unittest.TestCase):
    def test_leaf_depth_zero(self):
        p = UncertaintyPropagator({"A": _node("A")})
        self.assertEqual(p.dependency_depth("A"), 0)

    def test_one_hop_depth_one(self):
        p = UncertaintyPropagator({"A": _node("A"), "B": _node("B")})
        p.register_dependency("B", "A")
        self.assertEqual(p.dependency_depth("B"), 1)

    def test_chain_depth(self):
        nodes = {str(i): _node(str(i)) for i in range(5)}
        p = UncertaintyPropagator(nodes)
        for i in range(1, 5):
            p.register_dependency(str(i), str(i - 1))
        self.assertEqual(p.dependency_depth("4"), 4)


# ---------------------------------------------------------------------------
# Tests: most_uncertain_nodes and uncertainty_summary
# ---------------------------------------------------------------------------

class TestConvenienceMethods(unittest.TestCase):
    def setUp(self):
        nodes = {
            "low": _node("low", 0.05),
            "mid": _node("mid", 0.2),
            "high": _node("high", 0.5),
        }
        self.p = UncertaintyPropagator(nodes)
        self.report = self.p.propagate()

    def test_most_uncertain_sorted(self):
        top = self.p.most_uncertain_nodes(self.report, top_n=3)
        sigmas = [r.combined_sigma for r in top]
        self.assertEqual(sigmas, sorted(sigmas, reverse=True))

    def test_most_uncertain_top_n(self):
        top = self.p.most_uncertain_nodes(self.report, top_n=2)
        self.assertEqual(len(top), 2)

    def test_summary_fields(self):
        summary = self.p.uncertainty_summary(self.report)
        for key in ("node_count", "sigma_min", "sigma_max", "sigma_mean", "max_depth"):
            self.assertIn(key, summary)

    def test_summary_node_count(self):
        summary = self.p.uncertainty_summary(self.report)
        self.assertEqual(summary["node_count"], 3)

    def test_summary_mode(self):
        summary = self.p.uncertainty_summary(self.report)
        self.assertEqual(summary["mode"], PropagationMode.SUM_IN_QUADRATURE.value)


# ---------------------------------------------------------------------------
# Tests: Integration with AlexandriaStore
# ---------------------------------------------------------------------------

class TestIntegrationWithStore(unittest.TestCase):
    def test_build_from_real_store(self):
        store = AlexandriaStore()
        ts = int(time.time())

        def _p(pid, target, parent, depends_on=None, ts_offset=0):
            payload = {"content": f"Content for {target}", "assumptions": []}
            if depends_on:
                payload["depends_on"] = depends_on
            return Patch(
                patch_id=pid,
                parent_patch_id=parent,
                branch_id="main",
                timestamp=ts + ts_offset,
                operation="ADD",
                target_id=target,
                category="EMPIRICAL",
                payload=payload,
                audit={"validated": True, "decay": 0.01},
                uncertainty={"sigma": 0.1 * (1 + ts_offset)},
                chain=None,
            )

        store.checkout("main")
        store.submit(_p("p1", "fact_a", None, ts_offset=1))
        store.submit(_p("p2", "fact_b", "p1", depends_on=["fact_a"], ts_offset=2))
        store.submit(_p("p3", "conclusion", "p2", depends_on=["fact_a", "fact_b"], ts_offset=3))

        nodes = store.reconstruct("main")
        propagator = UncertaintyPropagator(nodes)
        propagator.build_from_patches(store.branches["main"])

        report = propagator.propagate()
        self.assertIn("fact_a", report.results)
        self.assertIn("fact_b", report.results)
        self.assertIn("conclusion", report.results)

        # fact_a is a leaf
        self.assertEqual(report.results["fact_a"].depth, 0)
        # conclusion depends on both → depth ≥ 1
        self.assertGreaterEqual(report.results["conclusion"].depth, 1)
        # conclusion has higher combined_sigma than fact_a
        self.assertGreater(
            report.results["conclusion"].combined_sigma,
            report.results["fact_a"].combined_sigma,
        )

    def test_unknown_dependency_ignored(self):
        """Dependency on a node not in the graph is silently ignored."""
        nodes = {"A": _node("A", 0.1)}
        p = UncertaintyPropagator(nodes)
        p.register_dependency("A", "UNKNOWN_NODE")
        report = p.propagate()
        # A treated as leaf (unknown dep has no sigma to propagate)
        self.assertEqual(report.results["A"].depth, 0)
        self.assertAlmostEqual(report.results["A"].combined_sigma, 0.1, places=9)


if __name__ == "__main__":
    unittest.main()
