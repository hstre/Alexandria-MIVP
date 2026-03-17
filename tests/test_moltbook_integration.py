"""
Tests für die Moltbook API-Integration.

Da keine echte Moltbook-API verfügbar ist, werden alle HTTP-Anfragen
durch einen einfachen Mock-Mechanismus ersetzt.
"""

import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Src-Verzeichnis zum Pfad hinzufügen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import AlexandriaStore, Patch
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from moltbook_integration import MoltbookIntegration, MoltbookAPIError


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def make_identity(name: str = "TestAgent") -> AgentIdentity:
    return AgentIdentity(
        name=name,
        model_path="models/test.bin",
        model_bytes=b"test_model_bytes_for_testing",
        system_prompt="Test agent for unit tests.",
        guardrails=[{"id": "test_rule", "rule": "Be accurate"}],
        temperature=0.7,
        top_p=0.9,
        max_tokens=1000,
    )


def make_store(identity: AgentIdentity) -> AlexandriaMIVPStore:
    store = AlexandriaMIVPStore(agent_identity=identity)
    store.checkout("main")
    return store


def add_test_claim(store: AlexandriaMIVPStore, content: str = "Test claim", category: str = "EMPIRICAL") -> str:
    patch = Patch(
        patch_id=f"test_{abs(hash(content))}",
        parent_patch_id=store.get_last_patch_id("main"),
        branch_id="main",
        timestamp=1771459200,
        operation="ADD",
        target_id=f"claim_{abs(hash(content))}",
        category=category,
        payload={"content": content, "assumptions": ["test"]},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.1, "ci": [0.9, 1.1], "n": 10},
    )
    store.submit_with_identity(patch)
    nodes = store.reconstruct("main")
    return list(nodes.keys())[-1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMoltbookIntegrationInit(unittest.TestCase):
    def test_init_sets_attributes(self):
        identity = make_identity()
        store = make_store(identity)
        mb = MoltbookIntegration(store, api_key="test_key_123")

        self.assertIs(mb.store, store)
        self.assertEqual(mb.api_key, "test_key_123")
        self.assertEqual(mb._post_links, {})


class TestFormatClaimForMoltbook(unittest.TestCase):
    def setUp(self):
        self.identity = make_identity()
        self.store = make_store(self.identity)
        self.mb = MoltbookIntegration(self.store, api_key="key")
        self.claim_id = add_test_claim(self.store, "CO2 concentration is rising steadily.")

    def test_format_contains_category(self):
        nodes = self.store.reconstruct("main")
        node = nodes[self.claim_id]
        formatted = self.mb._format_claim_for_moltbook(node, self.identity)
        self.assertIn("EMPIRICAL", formatted)

    def test_format_contains_content(self):
        nodes = self.store.reconstruct("main")
        node = nodes[self.claim_id]
        formatted = self.mb._format_claim_for_moltbook(node, self.identity)
        self.assertIn("CO2 concentration is rising steadily.", formatted)

    def test_format_contains_agent_name(self):
        nodes = self.store.reconstruct("main")
        node = nodes[self.claim_id]
        formatted = self.mb._format_claim_for_moltbook(node, self.identity)
        self.assertIn("TestAgent", formatted)

    def test_format_contains_patch_block(self):
        nodes = self.store.reconstruct("main")
        node = nodes[self.claim_id]
        formatted = self.mb._format_claim_for_moltbook(node, self.identity)
        self.assertIn("---alexandria-patch---", formatted)
        self.assertIn("---end-patch---", formatted)

    def test_patch_block_is_valid_json(self):
        nodes = self.store.reconstruct("main")
        node = nodes[self.claim_id]
        formatted = self.mb._format_claim_for_moltbook(node, self.identity)

        start = formatted.find("---alexandria-patch---") + len("---alexandria-patch---")
        end = formatted.find("---end-patch---")
        raw = formatted[start:end].strip()
        data = json.loads(raw)

        self.assertIn("category", data)
        self.assertIn("mivp_identity", data)
        self.assertEqual(data["category"], "EMPIRICAL")


class TestExtractPatchFromPost(unittest.TestCase):
    def setUp(self):
        self.identity = make_identity()
        self.store = make_store(self.identity)
        self.mb = MoltbookIntegration(self.store, api_key="key")

    def test_extracts_valid_patch_block(self):
        patch_data = {"category": "MODEL", "content": "Hello", "mivp_identity": {}}
        content = f"Some intro\n---alexandria-patch---\n{json.dumps(patch_data)}\n---end-patch---\nSome outro"
        post = {"content": content}
        result = self.mb._extract_patch_from_post(post)
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "MODEL")

    def test_returns_none_if_no_block(self):
        post = {"content": "Just a regular post without any markers."}
        result = self.mb._extract_patch_from_post(post)
        self.assertIsNone(result)

    def test_returns_none_for_invalid_json(self):
        content = "---alexandria-patch---\n{not valid json}\n---end-patch---"
        post = {"content": content}
        result = self.mb._extract_patch_from_post(post)
        self.assertIsNone(result)


class TestLinkMoltbookPost(unittest.TestCase):
    def test_link_stores_mapping(self):
        identity = make_identity()
        store = make_store(identity)
        mb = MoltbookIntegration(store, api_key="key")
        mb._link_moltbook_post("claim_abc", "post_xyz")
        self.assertEqual(mb._post_links["claim_abc"], "post_xyz")


class TestPostClaimMocked(unittest.TestCase):
    def setUp(self):
        self.identity = make_identity()
        self.store = make_store(self.identity)
        self.mb = MoltbookIntegration(self.store, api_key="key")
        self.claim_id = add_test_claim(self.store, "Climate change is real.")

    def test_post_claim_success(self):
        mock_response = {"post_id": "post_001"}
        with patch.object(self.mb, '_make_api_request', return_value=mock_response):
            result = self.mb.post_claim(self.claim_id, submolt="science")

        self.assertTrue(result["success"])
        self.assertEqual(result["post_id"], "post_001")
        self.assertIn("post_001", result["url"])
        self.assertEqual(self.mb._post_links[self.claim_id], "post_001")

    def test_post_claim_not_found(self):
        result = self.mb.post_claim("nonexistent_claim_id")
        self.assertIn("error", result)

    def test_post_claim_api_failure(self):
        mock_response = {"error": "rate_limited"}
        with patch.object(self.mb, '_make_api_request', return_value=mock_response):
            result = self.mb.post_claim(self.claim_id)

        self.assertIn("error", result)


class TestFetchPostsMocked(unittest.TestCase):
    def test_fetch_returns_posts_list(self):
        identity = make_identity()
        store = make_store(identity)
        mb = MoltbookIntegration(store, api_key="key")

        mock_response = {"posts": [{"post_id": "p1"}, {"post_id": "p2"}]}
        with patch.object(mb, '_make_api_request', return_value=mock_response):
            posts = mb.fetch_posts(submolt="general", limit=10)

        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["post_id"], "p1")

    def test_fetch_returns_empty_list_on_empty_response(self):
        identity = make_identity()
        store = make_store(identity)
        mb = MoltbookIntegration(store, api_key="key")

        with patch.object(mb, '_make_api_request', return_value={}):
            posts = mb.fetch_posts()

        self.assertEqual(posts, [])


class TestSyncClaimsToMoltbook(unittest.TestCase):
    def setUp(self):
        self.identity = make_identity()
        self.store = make_store(self.identity)
        self.mb = MoltbookIntegration(self.store, api_key="key")
        self.claim_id = add_test_claim(self.store, "Biodiversity is decreasing.")

    def test_sync_publishes_claims(self):
        mock_response = {"post_id": "post_sync_01"}
        with patch.object(self.mb, '_make_api_request', return_value=mock_response):
            result = self.mb.sync_claims_to_moltbook(only_verified=False)

        self.assertEqual(len(result["published"]), 1)
        self.assertEqual(len(result["errors"]), 0)

    def test_sync_skips_already_published(self):
        self.mb._post_links[self.claim_id] = "already_published"
        mock_response = {"post_id": "post_new"}
        with patch.object(self.mb, '_make_api_request', return_value=mock_response):
            result = self.mb.sync_claims_to_moltbook(only_verified=False)

        self.assertIn(self.claim_id, result["skipped"])
        self.assertEqual(len(result["published"]), 0)

    def test_sync_with_api_error(self):
        with patch.object(self.mb, '_make_api_request',
                          side_effect=MoltbookAPIError("Server error", status_code=500)):
            result = self.mb.sync_claims_to_moltbook(only_verified=False)

        self.assertEqual(len(result["errors"]), 1)


class TestSyncFromMoltbook(unittest.TestCase):
    def setUp(self):
        self.identity = make_identity()
        self.store = make_store(self.identity)
        self.mb = MoltbookIntegration(self.store, api_key="key")

    def _make_moltbook_post(self, post_id: str, content: str, category: str = "EMPIRICAL") -> dict:
        identity_dict = self.identity.get_identity_dict()
        patch_data = {
            "category": category,
            "content": content,
            "mivp_identity": identity_dict,
            "timestamp": 1771459200,
        }
        full_content = (
            f"Post intro\n---alexandria-patch---\n{json.dumps(patch_data)}\n---end-patch---"
        )
        return {"post_id": post_id, "content": full_content}

    def test_sync_imports_valid_posts(self):
        posts = [self._make_moltbook_post("mb_001", "Test import from Moltbook")]
        with patch.object(self.mb, 'fetch_posts', return_value=posts):
            result = self.mb.sync_from_moltbook()

        self.assertEqual(len(result["imported"]), 1)
        self.assertEqual(result["imported"][0]["post_id"], "mb_001")

    def test_sync_skips_posts_without_patch_block(self):
        posts = [{"post_id": "mb_002", "content": "Just a regular post."}]
        with patch.object(self.mb, 'fetch_posts', return_value=posts):
            result = self.mb.sync_from_moltbook()

        self.assertIn("mb_002", result["skipped"])
        self.assertEqual(len(result["imported"]), 0)


class TestVerifyPost(unittest.TestCase):
    def setUp(self):
        self.identity = make_identity()
        self.store = make_store(self.identity)
        self.mb = MoltbookIntegration(self.store, api_key="key")

    def _make_post_response(self, content: str) -> dict:
        return {"post": {"post_id": "vp_001", "content": content}}

    def test_verify_consistent_post(self):
        identity_dict = self.identity.get_identity_dict()
        patch_data = {
            "category": "EMPIRICAL",
            "content": "Test",
            "mivp_identity": identity_dict,
        }
        content = f"---alexandria-patch---\n{json.dumps(patch_data)}\n---end-patch---"
        post_resp = self._make_post_response(content)

        with patch.object(self.mb, '_make_api_request', return_value=post_resp):
            result = self.mb.verify_post("vp_001")

        self.assertTrue(result["internally_consistent"])
        self.assertTrue(result["matches_current_agent"])

    def test_verify_post_without_patch_block(self):
        post_resp = {"post": {"post_id": "vp_002", "content": "No patch block here."}}
        with patch.object(self.mb, '_make_api_request', return_value=post_resp):
            result = self.mb.verify_post("vp_002")

        self.assertIn("error", result)


class TestMoltbookAPIError(unittest.TestCase):
    def test_error_carries_status_code(self):
        err = MoltbookAPIError("Not found", status_code=404, response={"detail": "missing"})
        self.assertEqual(err.status_code, 404)
        self.assertEqual(err.response["detail"], "missing")

    def test_error_default_response(self):
        err = MoltbookAPIError("Oops")
        self.assertEqual(err.response, {})
        self.assertIsNone(err.status_code)


if __name__ == "__main__":
    unittest.main()
