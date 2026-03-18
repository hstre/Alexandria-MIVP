"""
Tests für SQLite identity_hashes Query-Patterns.

Prüft alle neuen Query-Methoden in AlexandriaSQLiteMIVPStore sowie
die korrekte Persistenz von rh_extended_json.
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import Patch, AuditError
from alexandria_mivp import AgentIdentity
from sqlite_store import AlexandriaSQLiteMIVPStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = 1_000_000  # base timestamp, incremented per patch


def _ts():
    global _TS
    _TS += 2  # step by 2 to avoid monotonicity issues when two calls happen in same setUp
    return _TS


def _make_identity(name="Agent", model_bytes=b"model", temp=0.7, **kwargs):
    defaults = dict(system_prompt="test", guardrails=[])
    defaults.update(kwargs)
    return AgentIdentity(
        name=name,
        model_path="",
        model_bytes=model_bytes,
        temperature=temp,
        top_p=0.9,
        max_tokens=100,
        **defaults,
    )


class _StoreHelper:
    """Wraps AlexandriaSQLiteMIVPStore and tracks last patch IDs per branch."""

    def __init__(self, db_path=":memory:"):
        self._store = AlexandriaSQLiteMIVPStore(db_path)
        self._last_patch_id: dict = {}  # branch_id → last patch_id

    def __getattr__(self, name):
        return getattr(self._store, name)

    def _next_patch(self, target_id, branch_id="main", operation="ADD", category="EMPIRICAL") -> Patch:
        parent = self._last_patch_id.get(branch_id)
        pid = f"p_{target_id}_{_ts()}"
        ts = _ts()
        patch = Patch(
            patch_id=pid,
            parent_patch_id=parent,
            branch_id=branch_id,
            timestamp=ts,
            operation=operation,
            target_id=target_id,
            category=category,
            payload={"content": f"Content of {target_id}", "assumptions": []},
            audit={"validated": True, "decay": 0.01},
            uncertainty={"sigma": 0.1},
            chain=None,
        )
        return patch

    def submit_patch(self, target_id, branch_id="main", operation="ADD", category="EMPIRICAL",
                     instance_epoch=None) -> Patch:
        p = self._next_patch(target_id, branch_id, operation, category)
        if self._store.agent_identity is not None:
            self._store.submit_with_identity(p, instance_epoch=instance_epoch)
        else:
            self._store.submit(p)
        self._last_patch_id[branch_id] = p.patch_id
        return p


# ---------------------------------------------------------------------------
# Tests: Schema and rh_extended_json persistence
# ---------------------------------------------------------------------------

class TestSchemaAndPersistence(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")
        self.h._store.agent_identity = _make_identity("Alpha", b"model_alpha")

    def test_identity_hashes_table_exists(self):
        cursor = self.h.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='identity_hashes'")
        self.assertIsNotNone(cursor.fetchone())

    def test_rh_extended_json_column_exists(self):
        cursor = self.h.conn.cursor()
        cursor.execute("PRAGMA table_info(identity_hashes)")
        cols = [row["name"] for row in cursor.fetchall()]
        self.assertIn("rh_extended_json", cols)

    def test_indexes_exist(self):
        cursor = self.h.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='identity_hashes'")
        idx_names = {row["name"] for row in cursor.fetchall()}
        self.assertIn("idx_identity_agent", idx_names)
        self.assertIn("idx_identity_cih", idx_names)
        self.assertIn("idx_identity_mh", idx_names)

    def test_submit_stores_identity(self):
        p = self.h.submit_patch("node_a")
        identity = self.h.get_identity_for_patch(p.patch_id)
        self.assertIsNotNone(identity)
        self.assertEqual(identity["agent_name"], "Alpha")

    def test_standard_rh_no_extended_column(self):
        p = self.h.submit_patch("node_b")
        identity = self.h.get_identity_for_patch(p.patch_id)
        self.assertNotIn("rh_extended", identity)

    def test_extended_rh_stored_in_column(self):
        h = _StoreHelper()
        h._store.checkout("main")
        h._store.agent_identity = _make_identity(
            "Extended",
            use_extended_runtime_hash=True,
            container_digest="sha256:abc",
            tee_type="SGX",
        )
        p = h.submit_patch("node_ext")
        identity = h.get_identity_for_patch(p.patch_id)
        self.assertIn("rh_extended", identity)
        rhe = identity["rh_extended"]
        self.assertIn("config_h", rhe)
        self.assertIn("env_h", rhe)
        self.assertIn("attest_h", rhe)


# ---------------------------------------------------------------------------
# Tests: get_all_agents
# ---------------------------------------------------------------------------

class TestGetAllAgents(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")

    def test_empty_store_returns_empty(self):
        self.assertEqual(self.h.get_all_agents(), [])

    def test_single_agent_returned(self):
        self.h._store.agent_identity = _make_identity("Alpha", b"ma")
        self.h.submit_patch("n1")
        agents = self.h.get_all_agents()
        self.assertEqual(agents, ["Alpha"])

    def test_multiple_agents_returned_sorted(self):
        for name, mb in [("Zeta", b"mz"), ("Alpha", b"ma"), ("Beta", b"mb")]:
            self.h._store.agent_identity = _make_identity(name, mb)
            self.h.submit_patch(f"node_{name.lower()}")
        agents = self.h.get_all_agents()
        self.assertEqual(agents, ["Alpha", "Beta", "Zeta"])

    def test_duplicate_agent_appears_once(self):
        self.h._store.agent_identity = _make_identity("Alpha", b"ma")
        for i in range(3):
            self.h.submit_patch(f"n{i}")
        agents = self.h.get_all_agents()
        self.assertEqual(agents.count("Alpha"), 1)


# ---------------------------------------------------------------------------
# Tests: count_patches_by_agent
# ---------------------------------------------------------------------------

class TestCountPatchesByAgent(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")

    def test_empty_store(self):
        self.assertEqual(self.h.count_patches_by_agent(), {})

    def test_counts_correct(self):
        self.h._store.agent_identity = _make_identity("Alpha", b"ma")
        for i in range(3):
            self.h.submit_patch(f"n_alpha_{i}")

        self.h._store.agent_identity = _make_identity("Beta", b"mb")
        for i in range(2):
            self.h.submit_patch(f"n_beta_{i}")

        counts = self.h.count_patches_by_agent()
        self.assertEqual(counts["Alpha"], 3)
        self.assertEqual(counts["Beta"], 2)


# ---------------------------------------------------------------------------
# Tests: get_patches_by_cih / get_patches_by_mh
# ---------------------------------------------------------------------------

class TestGetPatchesByHash(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")
        self.h._store.agent_identity = _make_identity("Agent", b"model_hash_test")
        for i in range(3):
            self.h.submit_patch(f"node_{i}")
        self.cih = self.h._store.agent_identity.compute_cih().hex()
        self.mh = self.h._store.agent_identity.compute_mh().hex()

    def test_get_patches_by_cih(self):
        patches = self.h.get_patches_by_cih(self.cih)
        self.assertEqual(len(patches), 3)

    def test_get_patches_by_cih_unknown(self):
        patches = self.h.get_patches_by_cih("0" * 64)
        self.assertEqual(patches, [])

    def test_get_patches_by_mh(self):
        patches = self.h.get_patches_by_mh(self.mh)
        self.assertEqual(len(patches), 3)

    def test_get_patches_by_mh_different_model(self):
        self.h._store.agent_identity = _make_identity("Beta", b"different_model_bytes")
        self.h.submit_patch("node_beta_0")
        patches = self.h.get_patches_by_mh(self.mh)
        self.assertEqual(len(patches), 3)


# ---------------------------------------------------------------------------
# Tests: get_patches_in_epoch_range
# ---------------------------------------------------------------------------

class TestGetPatchesInEpochRange(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")
        self.h._store.agent_identity = _make_identity("EpochAgent", b"model")
        for i, epoch in enumerate([100, 200, 300, 400, 500]):
            self.h.submit_patch(f"n_{i}", instance_epoch=epoch)

    def test_no_bounds_returns_all(self):
        patches = self.h.get_patches_in_epoch_range("EpochAgent")
        self.assertEqual(len(patches), 5)

    def test_start_bound(self):
        patches = self.h.get_patches_in_epoch_range("EpochAgent", start_epoch=300)
        self.assertEqual(len(patches), 3)

    def test_end_bound(self):
        patches = self.h.get_patches_in_epoch_range("EpochAgent", end_epoch=200)
        self.assertEqual(len(patches), 2)

    def test_both_bounds(self):
        patches = self.h.get_patches_in_epoch_range("EpochAgent", start_epoch=200, end_epoch=400)
        self.assertEqual(len(patches), 3)

    def test_unknown_agent(self):
        patches = self.h.get_patches_in_epoch_range("NoSuchAgent")
        self.assertEqual(patches, [])


# ---------------------------------------------------------------------------
# Tests: get_agent_statistics
# ---------------------------------------------------------------------------

class TestGetAgentStatistics(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")
        self.h._store.agent_identity = _make_identity("Stats", b"model")
        for i, cat in enumerate(["EMPIRICAL", "EMPIRICAL", "NORMATIVE", "MODEL"]):
            self.h.submit_patch(f"n_{i}", category=cat, instance_epoch=i + 1)

    def test_returns_correct_patch_count(self):
        stats = self.h.get_agent_statistics("Stats")
        self.assertEqual(stats["patch_count"], 4)

    def test_unknown_agent(self):
        stats = self.h.get_agent_statistics("Nobody")
        self.assertEqual(stats["patch_count"], 0)

    def test_category_breakdown(self):
        stats = self.h.get_agent_statistics("Stats")
        breakdown = stats["category_breakdown"]
        self.assertEqual(breakdown.get("EMPIRICAL", 0), 2)
        self.assertEqual(breakdown.get("NORMATIVE", 0), 1)
        self.assertEqual(breakdown.get("MODEL", 0), 1)

    def test_epoch_range(self):
        stats = self.h.get_agent_statistics("Stats")
        self.assertEqual(stats["epoch_min"], 1)
        self.assertEqual(stats["epoch_max"], 4)

    def test_distinct_cih_count(self):
        stats = self.h.get_agent_statistics("Stats")
        # Patches were submitted with different instance_epochs → different CIHs
        self.assertGreaterEqual(stats["distinct_cih_count"], 1)

    def test_signed_count_present(self):
        stats = self.h.get_agent_statistics("Stats")
        self.assertIn("signed_count", stats)


# ---------------------------------------------------------------------------
# Tests: find_identity_drift
# ---------------------------------------------------------------------------

class TestFindIdentityDrift(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")

    def test_no_drift_single_agent(self):
        self.h._store.agent_identity = _make_identity("Stable", b"model")
        for i in range(3):
            self.h.submit_patch(f"n_{i}")
        drift = self.h.find_identity_drift("Stable")
        self.assertEqual(drift, [])

    def test_drift_detected_on_model_change(self):
        self.h._store.agent_identity = _make_identity("Drifter", b"model_v1")
        self.h.submit_patch("n_1")
        self.h._store.agent_identity = _make_identity("Drifter", b"model_v2")
        self.h.submit_patch("n_2")
        drift = self.h.find_identity_drift("Drifter")
        self.assertEqual(len(drift), 1)
        self.assertIn("mh", drift[0]["changed_components"])

    def test_drift_detected_on_policy_change(self):
        self.h._store.agent_identity = _make_identity("PolicyChanger", b"model", system_prompt="old")
        self.h.submit_patch("n_1")
        self.h._store.agent_identity = _make_identity("PolicyChanger", b"model", system_prompt="new")
        self.h.submit_patch("n_2")
        drift = self.h.find_identity_drift("PolicyChanger")
        self.assertEqual(len(drift), 1)
        self.assertIn("ph", drift[0]["changed_components"])

    def test_drift_includes_cih(self):
        self.h._store.agent_identity = _make_identity("Drifter2", b"m1")
        self.h.submit_patch("n1")
        self.h._store.agent_identity = _make_identity("Drifter2", b"m2")
        self.h.submit_patch("n2")
        drift = self.h.find_identity_drift("Drifter2")
        self.assertIn("new_cih", drift[0])
        self.assertIn("prev_cih", drift[0])

    def test_unknown_agent_no_drift(self):
        drift = self.h.find_identity_drift("Ghost")
        self.assertEqual(drift, [])


# ---------------------------------------------------------------------------
# Tests: get_identity_timeline
# ---------------------------------------------------------------------------

class TestGetIdentityTimeline(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")
        self.h._store.agent_identity = _make_identity("Timeline", b"model")
        for cat in ["EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"]:
            self.h.submit_patch(f"n_{cat}", category=cat)

    def test_timeline_length(self):
        tl = self.h.get_identity_timeline("Timeline")
        self.assertEqual(len(tl), 4)

    def test_timeline_sorted_by_time(self):
        tl = self.h.get_identity_timeline("Timeline")
        timestamps = [e["timestamp"] for e in tl]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_timeline_entry_fields(self):
        tl = self.h.get_identity_timeline("Timeline")
        for entry in tl:
            for key in ("patch_id", "timestamp", "branch_id", "category", "mh", "ph", "rh", "cih"):
                self.assertIn(key, entry)

    def test_unknown_agent_empty_timeline(self):
        tl = self.h.get_identity_timeline("Nobody")
        self.assertEqual(tl, [])

    def test_extended_rh_in_timeline(self):
        h = _StoreHelper()
        h._store.checkout("main")
        h._store.agent_identity = _make_identity(
            "ExtTimeline", b"m",
            use_extended_runtime_hash=True,
            container_digest="sha256:x",
        )
        h.submit_patch("en_0")
        tl = h.get_identity_timeline("ExtTimeline")
        self.assertIn("rh_extended", tl[0])


# ---------------------------------------------------------------------------
# Tests: find_unverified_patches
# ---------------------------------------------------------------------------

class TestFindUnverifiedPatches(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")
        self.h._store.agent_identity = _make_identity("V", b"m")

    def test_no_unverified_when_all_have_identity(self):
        self.h.submit_patch("n1")
        self.assertEqual(self.h.find_unverified_patches(), [])

    def test_unverified_patch_found(self):
        # Submit without identity
        self.h._store.agent_identity = None
        p = self.h.submit_patch("plain")
        self.h._store.agent_identity = _make_identity("V", b"m")
        unverified = self.h.find_unverified_patches()
        self.assertEqual(len(unverified), 1)
        self.assertEqual(unverified[0].patch_id, p.patch_id)

    def test_mix_of_verified_and_unverified(self):
        pv = self.h.submit_patch("verified")
        self.h._store.agent_identity = None
        pu = self.h.submit_patch("unverified")
        self.h._store.agent_identity = _make_identity("V", b"m")
        unverified = self.h.find_unverified_patches()
        ids = [p.patch_id for p in unverified]
        self.assertIn(pu.patch_id, ids)
        self.assertNotIn(pv.patch_id, ids)

    def test_branch_filter(self):
        self.h._store.create_branch("other")
        self.h._store.checkout("other")
        self.h._store.agent_identity = None
        pu_other = self.h.submit_patch("other_node", branch_id="other")
        self.h._store.checkout("main")
        unverified_main = self.h.find_unverified_patches("main")
        ids = [p.patch_id for p in unverified_main]
        self.assertNotIn(pu_other.patch_id, ids)


# ---------------------------------------------------------------------------
# Tests: find_patches_with_extended_rh
# ---------------------------------------------------------------------------

class TestFindPatchesWithExtendedRH(unittest.TestCase):
    def setUp(self):
        self.h = _StoreHelper()
        self.h._store.checkout("main")

    def test_no_extended_rh_patches(self):
        self.h._store.agent_identity = _make_identity("Plain", b"m")
        self.h.submit_patch("n1")
        self.assertEqual(self.h.find_patches_with_extended_rh(), [])

    def test_finds_extended_rh_patches(self):
        self.h._store.agent_identity = _make_identity(
            "Ext", b"m",
            use_extended_runtime_hash=True,
            container_digest="sha256:abc",
        )
        p = self.h.submit_patch("ext_n1")
        results = self.h.find_patches_with_extended_rh()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["patch_id"], p.patch_id)
        self.assertIn("rh_extended", results[0])

    def test_agent_filter(self):
        self.h._store.agent_identity = _make_identity(
            "A", b"ma",
            use_extended_runtime_hash=True,
            container_digest="sha256:x",
        )
        self.h.submit_patch("n_A")
        self.h._store.agent_identity = _make_identity("B", b"mb")
        self.h.submit_patch("n_B")
        self.assertEqual(len(self.h.find_patches_with_extended_rh("A")), 1)
        self.assertEqual(self.h.find_patches_with_extended_rh("B"), [])


if __name__ == "__main__":
    unittest.main()
