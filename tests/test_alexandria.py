#!/usr/bin/env python3
"""Tests for Alexandria Protocol basic operations."""
import sys

from alexandria_mivp.alexandria_v2 import AlexandriaStore, Patch


def _make_store():
    store = AlexandriaStore()
    store.checkout("main")
    return store


def test_add_operation():
    store = _make_store()
    p = Patch(
        patch_id="test_001", parent_patch_id=None, branch_id="main",
        timestamp=1000, operation="ADD", target_id="claim_test",
        category="EMPIRICAL",
        payload={"content": "Test claim", "assumptions": ["test_assumption"]},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.1}, chain=None,
    )
    store.submit(p)
    assert "claim_test" in store.reconstruct("main")


def test_modify_operation():
    store = _make_store()
    store.submit(Patch(
        patch_id="test_001", parent_patch_id=None, branch_id="main",
        timestamp=1000, operation="ADD", target_id="claim_test",
        category="EMPIRICAL",
        payload={"content": "Original", "assumptions": []},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.1}, chain=None,
    ))
    store.submit(Patch(
        patch_id="test_002", parent_patch_id="test_001", branch_id="main",
        timestamp=2000, operation="MODIFY", target_id="claim_test",
        category="EMPIRICAL",
        payload={"content": "Modified test claim"},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.05}, chain=None,
    ))
    nodes = store.reconstruct("main")
    assert nodes["claim_test"].content == "Modified test claim"


def test_deprecate_operation():
    store = _make_store()
    for pid, parent, ts, op, content in [
        ("test_001", None,       1000, "ADD",       "Test claim"),
        ("test_002", "test_001", 2000, "MODIFY",    "Modified"),
        ("test_003", "test_002", 3000, "DEPRECATE", "Deprecated"),
    ]:
        store.submit(Patch(
            patch_id=pid, parent_patch_id=parent, branch_id="main",
            timestamp=ts, operation=op, target_id="claim_test",
            category="EMPIRICAL",
            payload={"content": content},
            audit={"validated": True, "decay": 0.01},
            uncertainty={"sigma": 0.05} if op != "DEPRECATE" else None,
            chain=None,
        ))
    nodes = store.reconstruct("main")
    assert nodes["claim_test"].deprecated is True


def test_branch_creation():
    store = _make_store()
    store.create_branch("test_branch")
    store.checkout("test_branch")
    assert store.current_branch == "test_branch"


def test_reconstruction_returns_nodes():
    store = _make_store()
    store.submit(Patch(
        patch_id="p1", parent_patch_id=None, branch_id="main",
        timestamp=1000, operation="ADD", target_id="n1",
        category="EMPIRICAL",
        payload={"content": "A claim", "assumptions": []},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.1}, chain=None,
    ))
    nodes = store.reconstruct("main")
    assert "n1" in nodes
    assert nodes["n1"].stability >= 0.0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
