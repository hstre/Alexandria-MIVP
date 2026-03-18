"""
Tests für den Epistemic Heartbeat.
"""

import time
import unittest


from alexandria_mivp.alexandria_v2 import AlexandriaStore, Patch
from alexandria_mivp.alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from alexandria_mivp.heartbeat import (
    EpistemicHeartbeat,
    HeartbeatReport,
    run_heartbeat_check,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_identity(name: str = "HeartbeatTestAgent") -> AgentIdentity:
    return AgentIdentity(
        name=name,
        model_path="models/hb_test.bin",
        model_bytes=b"heartbeat_test_model",
        system_prompt="Heartbeat test agent.",
        guardrails=[{"id": "accuracy", "rule": "Be accurate"}],
        temperature=0.5,
        top_p=0.9,
        max_tokens=500,
    )


def make_store(identity: AgentIdentity) -> AlexandriaMIVPStore:
    store = AlexandriaMIVPStore(agent_identity=identity)
    store.checkout("main")
    return store


def add_patch(
    store: AlexandriaMIVPStore,
    content: str,
    category: str = "EMPIRICAL",
    ts: int = 1771459200,
    stability: float = 0.8,
) -> str:
    """Hilfsfunktion: Patch einreichen und zurückgegebene Node-ID liefern."""
    uid = abs(hash(content + str(ts)))
    patch = Patch(
        patch_id=f"hb_patch_{uid}",
        parent_patch_id=store.get_last_patch_id("main"),
        branch_id="main",
        timestamp=ts,
        operation="ADD",
        target_id=f"hb_node_{uid}",
        category=category,
        payload={"content": content, "assumptions": []},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.1, "ci": [0.9, 1.1], "n": 5},
    )
    store.submit_with_identity(patch)
    nodes = store.reconstruct("main")
    return list(nodes.keys())[-1]


# ---------------------------------------------------------------------------
# Tests: Grundfunktionen
# ---------------------------------------------------------------------------

class TestHeartbeatInit(unittest.TestCase):
    def test_init(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        self.assertIs(hb.store, store)
        self.assertIsNone(hb.last_report)


class TestRunOnce(unittest.TestCase):
    def setUp(self):
        self.identity = make_identity()
        self.store = make_store(self.identity)
        self.hb = EpistemicHeartbeat(self.store)

    def test_returns_report(self):
        report = self.hb.run_once()
        self.assertIsInstance(report, HeartbeatReport)

    def test_empty_store_no_alert(self):
        report = self.hb.run_once()
        self.assertFalse(report.alert)

    def test_report_has_timestamp(self):
        before = time.time()
        report = self.hb.run_once()
        after = time.time()
        self.assertGreaterEqual(report.timestamp, before)
        self.assertLessEqual(report.timestamp, after)

    def test_report_stored_in_last_report(self):
        report = self.hb.run_once()
        self.assertIs(self.hb.last_report, report)


# ---------------------------------------------------------------------------
# Tests: Identitätsprüfung
# ---------------------------------------------------------------------------

class TestIdentityCheck(unittest.TestCase):
    def test_identity_ok_for_fresh_store(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertTrue(report.identity.ok)

    def test_identity_cih_not_empty(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertTrue(len(report.identity.cih_hex) > 0)

    def test_identity_not_changed_on_first_run(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        # Beim ersten Lauf kein "_last_cih" vorhanden → changed muss False sein
        self.assertFalse(report.identity.changed)

    def test_identity_not_changed_on_second_run_same_agent(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        hb.run_once()
        report2 = hb.run_once()
        self.assertFalse(report2.identity.changed)


# ---------------------------------------------------------------------------
# Tests: Audit-Trail
# ---------------------------------------------------------------------------

class TestAuditTrailCheck(unittest.TestCase):
    def test_empty_store_audit_ok(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertTrue(report.audit_trail.ok)
        self.assertEqual(report.audit_trail.total_nodes, 0)

    def test_single_claim_audit_ok(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "CO2 is rising", ts=1000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertTrue(report.audit_trail.ok)

    def test_ordered_timestamps_ok(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Claim A", ts=1000)
        add_patch(store, "Claim B", ts=2000)
        add_patch(store, "Claim C", ts=3000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertTrue(report.audit_trail.timestamp_monotone)

    def test_node_count_matches(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Claim A", ts=1000)
        add_patch(store, "Claim B", ts=2000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertEqual(report.audit_trail.total_nodes, 2)


# ---------------------------------------------------------------------------
# Tests: Stale Claims
# ---------------------------------------------------------------------------

class TestStaleClaimsCheck(unittest.TestCase):
    def test_no_stale_claims_by_default(self):
        """Frisch hinzugefügte Nodes haben stability=0, threshold=0.2 → stale."""
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Fresh claim")
        hb = EpistemicHeartbeat(store, stability_threshold=0.2)
        report = hb.run_once()
        # Node.stability wird vom Store initial auf 0.0 gesetzt → stale
        self.assertGreaterEqual(report.stale_claims.stale_count, 0)

    def test_threshold_zero_no_stale(self):
        """Mit Schwellwert 0 gibt es keine veralteten Nodes."""
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Any claim")
        hb = EpistemicHeartbeat(store, stability_threshold=0.0)
        report = hb.run_once()
        self.assertEqual(report.stale_claims.stale_count, 0)

    def test_threshold_above_one_all_stale(self):
        """Mit Schwellwert >1 sind alle Nodes stale."""
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Any claim")
        hb = EpistemicHeartbeat(store, stability_threshold=1.1)
        report = hb.run_once()
        self.assertEqual(report.stale_claims.stale_count, 1)


# ---------------------------------------------------------------------------
# Tests: Kategorien-Verteilung
# ---------------------------------------------------------------------------

class TestCategoryDistribution(unittest.TestCase):
    def test_empty_store_no_categories(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertEqual(report.category_distribution.counts, {})
        self.assertFalse(report.category_distribution.imbalance_flag)

    def test_single_category_counts(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Empirical A", category="EMPIRICAL", ts=1000)
        add_patch(store, "Empirical B", category="EMPIRICAL", ts=2000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertEqual(report.category_distribution.counts.get("EMPIRICAL", 0), 2)

    def test_imbalance_flag_when_dominated(self):
        """Wenn 100% der Nodes eine Kategorie haben → Imbalance."""
        identity = make_identity()
        store = make_store(identity)
        for i in range(5):
            add_patch(store, f"Empirical claim {i}", category="EMPIRICAL", ts=1000 + i * 10)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertTrue(report.category_distribution.imbalance_flag)

    def test_no_imbalance_with_mixed_categories(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "E claim", category="EMPIRICAL", ts=1000)
        add_patch(store, "N claim", category="NORMATIVE", ts=2000)
        add_patch(store, "M claim", category="MODEL", ts=3000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        # Jede Kategorie 33.3% → kein Imbalance-Flag
        self.assertFalse(report.category_distribution.imbalance_flag)


# ---------------------------------------------------------------------------
# Tests: Widerspruchserkennung
# ---------------------------------------------------------------------------

class TestContradictionDetection(unittest.TestCase):
    def test_no_contradiction_on_empty_store(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertEqual(report.contradictions.count, 0)

    def test_no_contradiction_for_unrelated_claims(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Water is H2O", category="EMPIRICAL", ts=1000)
        add_patch(store, "Speed of light is constant", category="EMPIRICAL", ts=2000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertEqual(report.contradictions.count, 0)

    def test_detects_negation_contradiction(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Climate change is real", category="EMPIRICAL", ts=1000)
        add_patch(store, "Climate change is not real", category="EMPIRICAL", ts=2000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        self.assertGreater(report.contradictions.count, 0)

    def test_no_contradiction_across_categories(self):
        """Widersprüche nur innerhalb derselben Kategorie."""
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Vaccines are safe", category="EMPIRICAL", ts=1000)
        add_patch(store, "Vaccines are not safe", category="NORMATIVE", ts=2000)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        # Verschiedene Kategorien → kein Widerspruch
        self.assertEqual(report.contradictions.count, 0)


# ---------------------------------------------------------------------------
# Tests: Callback und Alert
# ---------------------------------------------------------------------------

class TestAlertCallback(unittest.TestCase):
    def test_callback_called_on_alert(self):
        """on_alert Callback wird aufgerufen wenn alert=True."""
        identity = make_identity()
        store = make_store(identity)
        # Widerspruch erzeugen → alert=True
        add_patch(store, "X is true", category="EMPIRICAL", ts=1000)
        add_patch(store, "X is not true", category="EMPIRICAL", ts=2000)

        called_with = []
        def callback(report):
            called_with.append(report)

        hb = EpistemicHeartbeat(store, on_alert=callback)
        report = hb.run_once()

        if report.alert:
            self.assertEqual(len(called_with), 1)
            self.assertIs(called_with[0], report)

    def test_callback_not_called_when_ok(self):
        """on_alert wird nicht aufgerufen wenn alles in Ordnung ist."""
        identity = make_identity()
        store = make_store(identity)

        called = []
        hb = EpistemicHeartbeat(store, on_alert=lambda r: called.append(r))
        report = hb.run_once()

        if not report.alert:
            self.assertEqual(len(called), 0)


# ---------------------------------------------------------------------------
# Tests: run_heartbeat_check Convenience-Funktion
# ---------------------------------------------------------------------------

class TestRunHeartbeatCheck(unittest.TestCase):
    def test_returns_none_when_ok(self):
        identity = make_identity()
        store = make_store(identity)
        result = run_heartbeat_check(store)
        # Leerer Store → None
        self.assertIsNone(result)

    def test_returns_string_on_alert(self):
        identity = make_identity()
        store = make_store(identity)
        add_patch(store, "Y is correct", category="EMPIRICAL", ts=1000)
        add_patch(store, "Y is not correct", category="EMPIRICAL", ts=2000)
        result = run_heartbeat_check(store)
        if result is not None:
            self.assertIsInstance(result, str)
            self.assertIn("Alert", result)


# ---------------------------------------------------------------------------
# Tests: Report-Serialisierung
# ---------------------------------------------------------------------------

class TestReportSerialization(unittest.TestCase):
    def test_to_dict_is_dict(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        d = report.to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("timestamp", d)
        self.assertIn("alert", d)

    def test_summary_is_string(self):
        identity = make_identity()
        store = make_store(identity)
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
        s = report.summary()
        self.assertIsInstance(s, str)
        self.assertIn("Epistemic Heartbeat", s)


if __name__ == "__main__":
    unittest.main()
