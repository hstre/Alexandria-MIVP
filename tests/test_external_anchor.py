"""
Tests für External Trust Anchoring.

Netzwerkgebundene Tests (OpenTimestampsAnchor, WebhookAnchor) werden
komplett gemockt – keine echten HTTP-Anfragen.
"""

import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.error


from alexandria_mivp.external_anchor import (
    SimulatedAnchor,
    OpenTimestampsAnchor,
    WebhookAnchor,
    MultiAnchor,
    AnchorError,
    AnchorProof,
    BaseExternalAnchor,
    ExternalAnchor,
)


FAKE_CIH = "a" * 64   # 32-Byte-Hex


# ---------------------------------------------------------------------------
# Tests: SimulatedAnchor
# ---------------------------------------------------------------------------

class TestSimulatedAnchor(unittest.TestCase):
    def setUp(self):
        self.anchor = SimulatedAnchor()

    def test_anchor_returns_dict(self):
        proof = self.anchor.anchor(FAKE_CIH)
        self.assertIsInstance(proof, dict)

    def test_anchor_contains_required_fields(self):
        proof = self.anchor.anchor(FAKE_CIH)
        for key in ("proof_id", "cih", "timestamp", "proof_type", "service"):
            self.assertIn(key, proof)

    def test_anchor_cih_matches(self):
        proof = self.anchor.anchor(FAKE_CIH)
        self.assertEqual(proof["cih"], FAKE_CIH)

    def test_anchor_service_is_simulated(self):
        proof = self.anchor.anchor(FAKE_CIH)
        self.assertEqual(proof["service"], "simulated")

    def test_all_proof_types(self):
        for pt in SimulatedAnchor.get_supported_proof_types():
            proof = self.anchor.anchor(FAKE_CIH, proof_type=pt)
            self.assertEqual(proof["proof_type"], pt)

    def test_invalid_proof_type_raises(self):
        with self.assertRaises(ValueError):
            self.anchor.anchor(FAKE_CIH, proof_type="invalid_type")

    def test_verify_true_for_existing(self):
        proof = self.anchor.anchor(FAKE_CIH)
        self.assertTrue(self.anchor.verify(FAKE_CIH, proof["proof_id"]))

    def test_verify_false_for_wrong_cih(self):
        proof = self.anchor.anchor(FAKE_CIH)
        self.assertFalse(self.anchor.verify("b" * 64, proof["proof_id"]))

    def test_verify_false_for_unknown_id(self):
        self.assertFalse(self.anchor.verify(FAKE_CIH, "nonexistent_proof"))

    def test_find_proofs_returns_all_for_cih(self):
        self.anchor.anchor(FAKE_CIH, proof_type="transparency_log")
        self.anchor.anchor(FAKE_CIH, proof_type="blockchain")
        proofs = self.anchor.find_proofs(FAKE_CIH)
        self.assertEqual(len(proofs), 2)

    def test_find_proofs_empty_for_unknown_cih(self):
        proofs = self.anchor.find_proofs("c" * 64)
        self.assertEqual(proofs, [])

    def test_get_global_consistency_proof(self):
        self.anchor.anchor(FAKE_CIH, "transparency_log")
        self.anchor.anchor(FAKE_CIH, "blockchain")
        gcp = self.anchor.get_global_consistency_proof(FAKE_CIH)
        self.assertIsNotNone(gcp)
        self.assertEqual(gcp["proof_count"], 2)
        self.assertIn("proofs", gcp)

    def test_global_consistency_none_for_unknown(self):
        result = self.anchor.get_global_consistency_proof("d" * 64)
        self.assertIsNone(result)

    def test_unique_proof_ids(self):
        ids = {self.anchor.anchor(FAKE_CIH)["proof_id"] for _ in range(5)}
        self.assertEqual(len(ids), 5)


# ---------------------------------------------------------------------------
# Tests: OpenTimestampsAnchor (gemockt)
# ---------------------------------------------------------------------------

class TestOpenTimestampsAnchor(unittest.TestCase):
    def setUp(self):
        self.ots = OpenTimestampsAnchor(timeout=5)

    def _mock_response(self, data: bytes):
        """Hilfsfunktion: urlopen-Mock der bytes zurückgibt."""
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = data
        mock_resp.status = 200
        return mock_resp

    def test_anchor_success(self):
        fake_ots = b"\x00\x01\x02\x03fake_ots_data"
        with patch("urllib.request.urlopen", return_value=self._mock_response(fake_ots)):
            proof = self.ots.anchor(FAKE_CIH, proof_type="blockchain")

        self.assertEqual(proof["cih"], FAKE_CIH)
        self.assertEqual(proof["service"], "opentimestamps")
        self.assertIn("ots_size_bytes", proof["proof_data"])
        self.assertIn("raw_bytes_b64", proof)

    def test_anchor_stores_proof(self):
        fake_ots = b"ots_data"
        with patch("urllib.request.urlopen", return_value=self._mock_response(fake_ots)):
            proof = self.ots.anchor(FAKE_CIH)

        self.assertTrue(self.ots.verify(FAKE_CIH, proof["proof_id"]))

    def test_anchor_falls_back_to_next_calendar(self):
        """Erster Calendar schlägt fehl, zweiter funktioniert."""
        fake_ots = b"ots_data"
        call_count = [0]

        def side_effect(req, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise urllib.error.URLError("connection refused")
            return self._mock_response(fake_ots)

        with patch("urllib.request.urlopen", side_effect=side_effect):
            proof = self.ots.anchor(FAKE_CIH)

        self.assertEqual(proof["service"], "opentimestamps")
        self.assertEqual(call_count[0], 2)

    def test_anchor_raises_when_all_fail(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("failed")):
            with self.assertRaises(AnchorError):
                self.ots.anchor(FAKE_CIH)

    def test_anchor_invalid_cih_raises(self):
        with self.assertRaises(AnchorError):
            self.ots.anchor("not_valid_hex")

    def test_verify_false_for_unknown_id(self):
        self.assertFalse(self.ots.verify(FAKE_CIH, "unknown"))

    def test_verify_against_calendar_returns_true_on_200(self):
        with patch("urllib.request.urlopen", return_value=self._mock_response(b"")):
            result = self.ots.verify_against_calendar(FAKE_CIH)
        self.assertTrue(result)

    def test_verify_against_calendar_returns_false_on_404(self):
        http_err = urllib.error.HTTPError(
            url="http://x", code=404, msg="Not Found", hdrs={}, fp=None
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            result = self.ots.verify_against_calendar(FAKE_CIH)
        self.assertFalse(result)

    def test_find_proofs(self):
        fake_ots = b"ots"
        with patch("urllib.request.urlopen", return_value=self._mock_response(fake_ots)):
            self.ots.anchor(FAKE_CIH)
        proofs = self.ots.find_proofs(FAKE_CIH)
        self.assertEqual(len(proofs), 1)

    def test_supported_proof_types(self):
        self.assertIn("blockchain", OpenTimestampsAnchor.get_supported_proof_types())


# ---------------------------------------------------------------------------
# Tests: WebhookAnchor (gemockt)
# ---------------------------------------------------------------------------

class TestWebhookAnchor(unittest.TestCase):
    def setUp(self):
        self.wh = WebhookAnchor("https://anchor.example.com/anchor", timeout=5)

    def _mock_json_response(self, data: dict):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(data).encode()
        mock_resp.status = 200
        return mock_resp

    def test_anchor_success(self):
        server_response = {"proof_id": "wh_001", "status": "anchored"}
        with patch("urllib.request.urlopen",
                   return_value=self._mock_json_response(server_response)):
            proof = self.wh.anchor(FAKE_CIH)

        self.assertEqual(proof["proof_id"], "wh_001")
        self.assertEqual(proof["cih"], FAKE_CIH)
        self.assertEqual(proof["service"], "webhook")

    def test_anchor_uses_fallback_proof_id_if_missing(self):
        with patch("urllib.request.urlopen",
                   return_value=self._mock_json_response({"status": "ok"})):
            proof = self.wh.anchor(FAKE_CIH)
        self.assertTrue(proof["proof_id"].startswith("wh_"))

    def test_anchor_http_error_raises(self):
        http_err = urllib.error.HTTPError(
            url="http://x", code=500, msg="Server Error",
            hdrs={}, fp=MagicMock(read=lambda: b"error")
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with self.assertRaises(AnchorError):
                self.wh.anchor(FAKE_CIH)

    def test_anchor_network_error_raises(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("network error")):
            with self.assertRaises(AnchorError):
                self.wh.anchor(FAKE_CIH)

    def test_verify_local(self):
        server_response = {"proof_id": "wh_local_01"}
        with patch("urllib.request.urlopen",
                   return_value=self._mock_json_response(server_response)):
            proof = self.wh.anchor(FAKE_CIH)
        self.assertTrue(self.wh.verify(FAKE_CIH, proof["proof_id"]))

    def test_verify_false_unknown(self):
        self.assertFalse(self.wh.verify(FAKE_CIH, "unknown_id"))

    def test_custom_headers_sent(self):
        wh = WebhookAnchor(
            "https://secure.example.com/anchor",
            headers={"Authorization": "Bearer token123"},
            timeout=5,
        )
        captured_headers = []

        def capture(req, timeout=None):
            captured_headers.append(req.get_header("Authorization"))
            return self._mock_json_response({"proof_id": "x"})

        with patch("urllib.request.urlopen", side_effect=capture):
            wh.anchor(FAKE_CIH)

        self.assertIn("Bearer token123", captured_headers)

    def test_proof_type_override(self):
        server_response = {"proof_id": "wh_type"}
        with patch("urllib.request.urlopen",
                   return_value=self._mock_json_response(server_response)):
            proof = self.wh.anchor(FAKE_CIH, proof_type="witness_node")
        self.assertEqual(proof["proof_type"], "witness_node")


# ---------------------------------------------------------------------------
# Tests: MultiAnchor
# ---------------------------------------------------------------------------

class TestMultiAnchor(unittest.TestCase):
    def test_init_empty_raises(self):
        with self.assertRaises(ValueError):
            MultiAnchor([])

    def test_first_success_mode_returns_first(self):
        a1 = SimulatedAnchor()
        a2 = SimulatedAnchor()
        multi = MultiAnchor([a1, a2], mode=MultiAnchor.MODE_FIRST_SUCCESS)
        proof = multi.anchor(FAKE_CIH)
        self.assertEqual(proof["service"], "simulated")

    def test_fallback_when_first_fails(self):
        """Erster Anchor schlägt fehl → zweiter (SimulatedAnchor) wird genutzt."""

        class FailingAnchor(BaseExternalAnchor):
            def anchor(self, cih_hex, proof_type="x"):
                raise AnchorError("always fails")
            def verify(self, cih_hex, proof_id):
                return False

        multi = MultiAnchor([FailingAnchor(), SimulatedAnchor()])
        proof = multi.anchor(FAKE_CIH)
        self.assertEqual(proof["service"], "simulated")

    def test_all_fail_raises(self):
        class FailingAnchor(BaseExternalAnchor):
            def anchor(self, cih_hex, proof_type="x"):
                raise AnchorError("fail")
            def verify(self, cih_hex, proof_id):
                return False

        multi = MultiAnchor([FailingAnchor(), FailingAnchor()])
        with self.assertRaises(AnchorError):
            multi.anchor(FAKE_CIH)

    def test_all_mode_tries_all(self):
        anchors_called = []

        class CountingAnchor(SimulatedAnchor):
            def anchor(self, cih_hex, proof_type="transparency_log"):
                anchors_called.append(self)
                return super().anchor(cih_hex, proof_type)

        a1, a2, a3 = CountingAnchor(), CountingAnchor(), CountingAnchor()
        multi = MultiAnchor([a1, a2, a3], mode=MultiAnchor.MODE_ALL)
        multi.anchor(FAKE_CIH)
        self.assertEqual(len(anchors_called), 3)

    def test_verify_checks_all_sub_anchors(self):
        a1 = SimulatedAnchor()
        a2 = SimulatedAnchor()
        multi = MultiAnchor([a1, a2])
        proof = a1.anchor(FAKE_CIH)    # direkt im Sub-Anchor, nicht über Multi
        # Multi sollte über a1.verify() fündig werden
        self.assertTrue(multi.verify(FAKE_CIH, proof["proof_id"]))

    def test_find_proofs_aggregates(self):
        a1 = SimulatedAnchor()
        a2 = SimulatedAnchor()
        a1.anchor(FAKE_CIH)
        a2.anchor(FAKE_CIH)
        multi = MultiAnchor([a1, a2])
        proofs = multi.find_proofs(FAKE_CIH)
        self.assertEqual(len(proofs), 2)


# ---------------------------------------------------------------------------
# Tests: Rückwärtskompatibilität
# ---------------------------------------------------------------------------

class TestBackwardCompatibility(unittest.TestCase):
    def test_external_anchor_alias(self):
        """ExternalAnchor ist ein Alias für SimulatedAnchor."""
        anchor = ExternalAnchor()
        self.assertIsInstance(anchor, SimulatedAnchor)

    def test_original_interface_works(self):
        """Altes ExternalAnchor-Interface funktioniert weiterhin."""
        anchor = ExternalAnchor()
        proof = anchor.anchor(FAKE_CIH, "transparency_log")
        self.assertIn("proof_id", proof)
        self.assertTrue(anchor.verify(FAKE_CIH, proof["proof_id"]))
        proofs = anchor.find_proofs(FAKE_CIH)
        self.assertEqual(len(proofs), 1)
        gcp = anchor.get_global_consistency_proof(FAKE_CIH)
        self.assertIsNotNone(gcp)

    def test_alexandria_mivp_store_accepts_new_anchor(self):
        """AlexandriaMIVPStore akzeptiert alle BaseExternalAnchor-Unterklassen."""
        from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity

        identity = AgentIdentity(
            name="AnchorTest",
            model_path="",
            model_bytes=b"test",
            system_prompt=".",
            guardrails=[],
            temperature=0.7,
            top_p=0.9,
            max_tokens=100,
        )
        anchor = SimulatedAnchor()
        store = AlexandriaMIVPStore(agent_identity=identity, external_anchor=anchor)
        self.assertIs(store.external_anchor, anchor)


if __name__ == "__main__":
    unittest.main()
