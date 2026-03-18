"""Tests for formal_verification.py (EpistemicVerifier, properties, invariants)."""
import sys
import os
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from formal_verification import (
    EpistemicVerifier,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
    PropertyResult,
    Invariant,
    Property,
)


# ---------------------------------------------------------------------------
# Fake store for testing
# ---------------------------------------------------------------------------

class _FakeUncertainty:
    def __init__(self, sigma=0.1, ci=None, n=None):
        self.sigma = sigma
        self.ci = ci
        self.n = n


class _FakeNode:
    def __init__(self, node_id, content="test content", category="EMPIRICAL",
                 sigma=0.1, assumptions=None):
        self.node_id = node_id
        self.content = content
        self.category = category
        self.uncertainty = _FakeUncertainty(sigma=sigma)
        self.assumptions = assumptions or []


class _FakePatch:
    _counter = 0

    def __init__(self, patch_id=None, parent_patch_id=None, branch_id="main",
                 operation="ADD", target_id="node1", category="EMPIRICAL",
                 timestamp=None, payload=None):
        _FakePatch._counter += 1
        self.patch_id = patch_id or f"patch_{_FakePatch._counter}"
        self.parent_patch_id = parent_patch_id
        self.branch_id = branch_id
        self.operation = operation
        self.target_id = target_id
        self.category = category
        self.timestamp = timestamp if timestamp is not None else int(time.time()) + _FakePatch._counter
        self.payload = payload or {"content": "test"}


class _FakeStore:
    def __init__(self):
        self.branches = {}
        self._nodes = {}

    def add_branch(self, branch_id, patches):
        self.branches[branch_id] = patches

    def add_node(self, node):
        self._nodes[node.node_id] = node

    def reconstruct(self, branch_id):
        # Return nodes relevant to this branch
        return dict(self._nodes)


def make_valid_store():
    """Create a valid store with a simple linear patch chain."""
    store = _FakeStore()
    store.add_node(_FakeNode("n1", content="CO2 is rising."))
    store.add_node(_FakeNode("n2", content="Temperature is rising."))

    p1 = _FakePatch(patch_id="p1", parent_patch_id=None, target_id="n1",
                    timestamp=1000)
    p2 = _FakePatch(patch_id="p2", parent_patch_id="p1", target_id="n2",
                    timestamp=1001)
    store.add_branch("main", [p1, p2])
    return store


# ---------------------------------------------------------------------------
# PropertyResult tests
# ---------------------------------------------------------------------------

class TestPropertyResult:
    def test_ok(self):
        r = PropertyResult.ok("All good.")
        assert r.status == VerificationStatus.PASSED
        assert r.message == "All good."

    def test_fail(self):
        r = PropertyResult.fail("Something wrong.", ["counterexample1"])
        assert r.status == VerificationStatus.FAILED
        assert len(r.counterexamples) == 1

    def test_skip(self):
        r = PropertyResult.skip("Not applicable.")
        assert r.status == VerificationStatus.SKIPPED

    def test_error(self):
        r = PropertyResult.error("Exception occurred.")
        assert r.status == VerificationStatus.ERROR


# ---------------------------------------------------------------------------
# VerificationReport tests
# ---------------------------------------------------------------------------

class TestVerificationReport:
    def make_report(self):
        results = [
            VerificationResult("prop1", VerificationStatus.PASSED, "ok", 1.0),
            VerificationResult("prop2", VerificationStatus.FAILED, "fail", 2.0),
            VerificationResult("prop3", VerificationStatus.ERROR, "err", 3.0),
            VerificationResult("prop4", VerificationStatus.SKIPPED, "skip", 0.0),
        ]
        return VerificationReport(branch_id="main", results=results)

    def test_passed_list(self):
        r = self.make_report()
        assert len(r.passed) == 1
        assert r.passed[0].property_name == "prop1"

    def test_failed_list(self):
        r = self.make_report()
        assert len(r.failed) == 1
        assert r.failed[0].property_name == "prop2"

    def test_errors_list(self):
        r = self.make_report()
        assert len(r.errors) == 1

    def test_is_fully_verified_false(self):
        r = self.make_report()
        assert r.is_fully_verified is False

    def test_is_fully_verified_true(self):
        results = [VerificationResult("p", VerificationStatus.PASSED, "ok", 1.0)]
        r = VerificationReport(branch_id="main", results=results)
        assert r.is_fully_verified is True

    def test_summary(self):
        r = self.make_report()
        s = r.summary()
        assert s["total"] == 4
        assert s["passed"] == 1
        assert s["failed"] == 1
        assert s["errors"] == 1
        assert s["skipped"] == 1
        assert s["is_fully_verified"] is False


# ---------------------------------------------------------------------------
# EpistemicVerifier – built-in invariants
# ---------------------------------------------------------------------------

class TestBuiltInInvariants:
    def test_valid_store_passes_all(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        # All invariants and properties should pass on a valid store
        for r in report.results:
            if r.status == VerificationStatus.FAILED:
                pytest.fail(f"Unexpected failure: {r.property_name}: {r.message}")

    def test_invalid_operation_fails(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1"))
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, operation="INVALID_OP",
                        target_id="n1", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "valid_operations" in failed_names

    def test_invalid_category_fails(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1"))
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, category="INVALID_CAT",
                        target_id="n1", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "valid_categories" in failed_names

    def test_non_monotonic_timestamps_fail(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1"))
        store.add_node(_FakeNode("n2"))
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, target_id="n1", timestamp=2000)
        p2 = _FakePatch(patch_id="p2", parent_patch_id="p1", target_id="n2", timestamp=1000)
        store.add_branch("main", [p1, p2])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "monotonic_timestamps" in failed_names

    def test_dangling_reference_fails(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1"))
        p1 = _FakePatch(patch_id="p1", parent_patch_id="nonexistent_parent",
                        target_id="n1", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "no_dangling_references" in failed_names


# ---------------------------------------------------------------------------
# EpistemicVerifier – built-in properties
# ---------------------------------------------------------------------------

class TestBuiltInProperties:
    def test_unique_patch_ids_fail(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1"))
        p1 = _FakePatch(patch_id="dup", parent_patch_id=None, target_id="n1", timestamp=1000)
        p2 = _FakePatch(patch_id="dup", parent_patch_id=None, target_id="n1", timestamp=1001)
        store.add_branch("main", [p1, p2])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "unique_patch_ids" in failed_names

    def test_sigma_out_of_range_fails(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1", sigma=1.5))  # sigma > 1
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, target_id="n1", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "sigma_in_range" in failed_names

    def test_empty_content_fails(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1", content="   "))  # whitespace only
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, target_id="n1", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "content_not_empty" in failed_names

    def test_speculative_without_assumptions_fails(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1", category="SPECULATIVE", assumptions=[]))
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, target_id="n1",
                        category="SPECULATIVE", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "assumptions_for_speculative" in failed_names

    def test_speculative_with_assumptions_passes(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1", category="SPECULATIVE", assumptions=["assume_x"]))
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, target_id="n1",
                        category="SPECULATIVE", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "assumptions_for_speculative" not in failed_names

    def test_chain_integrity_linear(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        by_name = {r.property_name: r for r in report.results}
        assert by_name["chain_integrity"].status == VerificationStatus.PASSED

    def test_chain_integrity_two_roots_fail(self):
        store = _FakeStore()
        store.add_node(_FakeNode("n1"))
        store.add_node(_FakeNode("n2"))
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, target_id="n1", timestamp=1000)
        p2 = _FakePatch(patch_id="p2", parent_patch_id=None, target_id="n2", timestamp=1001)
        store.add_branch("main", [p1, p2])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "chain_integrity" in failed_names

    def test_deprecate_without_prior_add_fails(self):
        store = _FakeStore()
        p1 = _FakePatch(patch_id="p1", parent_patch_id=None, operation="DEPRECATE",
                        target_id="never_added", timestamp=1000)
        store.add_branch("main", [p1])
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        failed_names = [r.property_name for r in report.failed]
        assert "no_deprecated_without_add" in failed_names


# ---------------------------------------------------------------------------
# Skip & tag filtering
# ---------------------------------------------------------------------------

class TestSkipAndTagFiltering:
    def test_skip_property(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main", skip=["chain_integrity"])
        by_name = {r.property_name: r for r in report.results}
        assert by_name["chain_integrity"].status == VerificationStatus.SKIPPED

    def test_tag_filter(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        # Only run properties with tag "integrity"
        report = verifier.verify_branch("main", tags=["integrity"])
        by_name = {r.property_name: r for r in report.results}
        # "chain_integrity" and "unique_patch_ids" have tag "integrity"
        assert by_name["chain_integrity"].status != VerificationStatus.SKIPPED
        assert by_name["unique_patch_ids"].status != VerificationStatus.SKIPPED
        # "sigma_in_range" has tag "uncertainty" – should be skipped
        assert by_name["sigma_in_range"].status == VerificationStatus.SKIPPED


# ---------------------------------------------------------------------------
# Custom properties
# ---------------------------------------------------------------------------

class TestCustomProperties:
    def test_add_custom_property(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)

        def my_check(nodes, patches):
            if len(nodes) >= 1:
                return PropertyResult.ok("Has at least one node.")
            return PropertyResult.fail("No nodes.")

        verifier.add_property("has_nodes", "Must have at least one node.", my_check, tags=["custom"])
        report = verifier.verify_branch("main")
        by_name = {r.property_name: r for r in report.results}
        assert "has_nodes" in by_name
        assert by_name["has_nodes"].status == VerificationStatus.PASSED

    def test_property_decorator(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)

        @verifier.property("always_passes")
        def always_passes(nodes, patches):
            return PropertyResult.ok("Always ok.")

        report = verifier.verify_branch("main")
        by_name = {r.property_name: r for r in report.results}
        assert by_name["always_passes"].status == VerificationStatus.PASSED

    def test_property_that_raises_returns_error(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)

        def broken_check(nodes, patches):
            raise RuntimeError("Something went wrong!")

        verifier.add_property("broken", "Broken check.", broken_check)
        report = verifier.verify_branch("main")
        by_name = {r.property_name: r for r in report.results}
        assert by_name["broken"].status == VerificationStatus.ERROR
        assert "Something went wrong" in by_name["broken"].message

    def test_add_invariant(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)

        def always_ok(nodes, patches):
            return PropertyResult.ok()

        verifier.add_invariant("custom_invariant", "Always passes.", always_ok)
        report = verifier.verify_branch("main")
        by_name = {r.property_name: r for r in report.results}
        assert "custom_invariant" in by_name
        assert by_name["custom_invariant"].status == VerificationStatus.PASSED


# ---------------------------------------------------------------------------
# List properties & verify_patch
# ---------------------------------------------------------------------------

class TestListPropertiesAndVerifyPatch:
    def test_list_properties(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        props = verifier.list_properties()
        names = [p["name"] for p in props]
        assert "no_dangling_references" in names
        assert "chain_integrity" in names
        assert "sigma_in_range" in names

    def test_list_properties_has_type(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        props = verifier.list_properties()
        types = {p["type"] for p in props}
        assert "invariant" in types
        assert "property" in types

    def test_verify_patch(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        patch = _FakePatch(patch_id="new_p", parent_patch_id="p2",
                           operation="ADD", target_id="n3", timestamp=2000)
        nodes = {"n1": _FakeNode("n1"), "n2": _FakeNode("n2")}
        results = verifier.verify_patch(patch, nodes)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_verify_all_branches(self):
        store = make_valid_store()
        # Add second branch
        p3 = _FakePatch(patch_id="q1", parent_patch_id=None, target_id="n1", timestamp=500)
        store.add_branch("feature", [p3])
        verifier = EpistemicVerifier(store)
        reports = verifier.verify_all_branches()
        assert "main" in reports
        assert "feature" in reports


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

class TestTiming:
    def test_duration_recorded(self):
        store = make_valid_store()
        verifier = EpistemicVerifier(store)
        report = verifier.verify_branch("main")
        assert report.total_duration_ms >= 0.0
        for r in report.results:
            assert r.duration_ms >= 0.0
