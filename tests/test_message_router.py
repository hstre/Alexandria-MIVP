"""
Tests für den Message Router.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import Patch
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from message_router import MessageRouter, RouteResult, MiddlewareContext


def make_identity(name="RouterTestAgent"):
    return AgentIdentity(
        name=name,
        model_path="models/rt.bin",
        model_bytes=b"router_test",
        system_prompt="Router test agent.",
        guardrails=[],
        temperature=0.7,
        top_p=0.9,
        max_tokens=500,
    )


def make_store(identity):
    store = AlexandriaMIVPStore(agent_identity=identity)
    store.checkout("main")
    return store


class TestMessageRouterInit(unittest.TestCase):
    def test_init(self):
        identity = make_identity()
        store = make_store(identity)
        router = MessageRouter(store, identity)
        self.assertIs(router.store, store)
        self.assertIs(router.identity, identity)

    def test_builtin_commands_registered(self):
        router = MessageRouter(make_store(make_identity()), make_identity())
        for cmd in ["status", "claim", "verify", "audit", "heartbeat", "help"]:
            self.assertIn(cmd, router.commands)


class TestDispatchParsing(unittest.TestCase):
    def setUp(self):
        identity = make_identity()
        self.router = MessageRouter(make_store(identity), identity)

    def test_with_prefix(self):
        result = self.router.dispatch("/alexandria help")
        self.assertTrue(result.success)
        self.assertEqual(result.command, "help")

    def test_without_prefix(self):
        result = self.router.dispatch("help")
        self.assertTrue(result.success)
        self.assertEqual(result.command, "help")

    def test_case_insensitive_command(self):
        result = self.router.dispatch("HELP")
        self.assertTrue(result.success)

    def test_unknown_command(self):
        result = self.router.dispatch("nonexistent")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "unknown_command")

    def test_empty_message(self):
        result = self.router.dispatch("/alexandria")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "parse_error")

    def test_history_recorded(self):
        self.router.dispatch("help")
        self.router.dispatch("status")
        self.assertEqual(len(self.router.history), 2)


class TestStatusCommand(unittest.TestCase):
    def setUp(self):
        identity = make_identity()
        self.store = make_store(identity)
        self.router = MessageRouter(self.store, identity)

    def test_status_returns_agent_name(self):
        result = self.router.dispatch("status")
        self.assertIn("RouterTestAgent", result.response)

    def test_status_returns_claim_count(self):
        result = self.router.dispatch("status")
        self.assertIn("Claims", result.response)


class TestClaimCommand(unittest.TestCase):
    def setUp(self):
        identity = make_identity()
        self.store = make_store(identity)
        self.router = MessageRouter(self.store, identity)

    def test_create_claim(self):
        result = self.router.dispatch("claim Water is H2O")
        self.assertTrue(result.success)
        self.assertIn("Claim erstellt", result.response)

    def test_create_claim_with_category(self):
        result = self.router.dispatch("claim Sky is blue --category EMPIRICAL")
        self.assertTrue(result.success)
        self.assertIn("EMPIRICAL", result.response)

    def test_create_claim_normative(self):
        result = self.router.dispatch("claim Agents should be honest --category NORMATIVE")
        self.assertTrue(result.success)
        self.assertIn("NORMATIVE", result.response)

    def test_create_claim_adds_to_store(self):
        before = len(self.store.reconstruct("main"))
        self.router.dispatch("claim New epistemic claim")
        after = len(self.store.reconstruct("main"))
        self.assertEqual(after, before + 1)

    def test_claim_invalid_category(self):
        result = self.router.dispatch("claim Some text --category INVALID")
        self.assertFalse(result.success)
        self.assertIn("Ungültige Kategorie", result.response)

    def test_claim_no_text(self):
        result = self.router.dispatch("claim --category EMPIRICAL")
        self.assertFalse(result.success)

    def test_claim_empty(self):
        result = self.router.dispatch("claim")
        self.assertFalse(result.success)


class TestVerifyCommand(unittest.TestCase):
    def test_verify_returns_agent_name(self):
        identity = make_identity()
        router = MessageRouter(make_store(identity), identity)
        result = router.dispatch("verify")
        self.assertTrue(result.success)
        self.assertIn("RouterTestAgent", result.response)

    def test_verify_shows_cih(self):
        identity = make_identity()
        router = MessageRouter(make_store(identity), identity)
        result = router.dispatch("verify")
        self.assertIn("CIH", result.response)


class TestAuditCommand(unittest.TestCase):
    def test_audit_empty_store(self):
        identity = make_identity()
        router = MessageRouter(make_store(identity), identity)
        result = router.dispatch("audit")
        self.assertTrue(result.success)

    def test_audit_with_claims(self):
        identity = make_identity()
        store = make_store(identity)
        router = MessageRouter(store, identity)
        router.dispatch("claim First claim")
        router.dispatch("claim Second claim")
        result = router.dispatch("audit")
        self.assertIn("Gesamt:", result.response)


class TestHelpCommand(unittest.TestCase):
    def test_help_lists_commands(self):
        router = MessageRouter(make_store(make_identity()), make_identity())
        result = router.dispatch("help")
        self.assertTrue(result.success)
        self.assertIn("status", result.response)
        self.assertIn("claim", result.response)
        self.assertIn("verify", result.response)


class TestCustomHandlers(unittest.TestCase):
    def setUp(self):
        identity = make_identity()
        self.router = MessageRouter(make_store(identity), identity)

    def test_register_custom_handler(self):
        self.router.register("ping", lambda args: "pong")
        result = self.router.dispatch("ping")
        self.assertTrue(result.success)
        self.assertEqual(result.response, "pong")

    def test_unregister_handler(self):
        self.router.register("temp", lambda args: "ok")
        removed = self.router.unregister("temp")
        self.assertTrue(removed)
        result = self.router.dispatch("temp")
        self.assertFalse(result.success)

    def test_unregister_nonexistent(self):
        removed = self.router.unregister("does_not_exist")
        self.assertFalse(removed)

    def test_custom_handler_receives_args(self):
        received = []
        def handler(args):
            received.extend(args)
            return "ok"
        self.router.register("echo", handler)
        self.router.dispatch("echo hello world")
        self.assertEqual(received, ["hello", "world"])


class TestMiddleware(unittest.TestCase):
    def setUp(self):
        identity = make_identity()
        self.router = MessageRouter(make_store(identity), identity)

    def test_middleware_called(self):
        called = []
        def mw(ctx, next_fn):
            called.append(ctx.command)
            return next_fn()
        self.router.add_middleware(mw)
        self.router.dispatch("help")
        self.assertIn("help", called)

    def test_middleware_can_modify_response(self):
        def mw(ctx, next_fn):
            original = next_fn()
            return original + "\n[via middleware]"
        self.router.add_middleware(mw)
        result = self.router.dispatch("help")
        self.assertIn("[via middleware]", result.response)

    def test_middleware_receives_context(self):
        contexts = []
        def mw(ctx, next_fn):
            contexts.append(ctx)
            return next_fn()
        self.router.add_middleware(mw)
        self.router.dispatch("status")
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0].command, "status")

    def test_multiple_middleware_called_in_order(self):
        order = []
        def mw1(ctx, next_fn):
            order.append(1)
            return next_fn()
        def mw2(ctx, next_fn):
            order.append(2)
            return next_fn()
        self.router.add_middleware(mw1)
        self.router.add_middleware(mw2)
        self.router.dispatch("help")
        self.assertEqual(order, [1, 2])


class TestRouteResult(unittest.TestCase):
    def test_str_returns_response(self):
        r = RouteResult(success=True, command="x", args=[], response="hello")
        self.assertEqual(str(r), "hello")

    def test_latency_defaults_to_zero(self):
        r = RouteResult(success=True, command="x", args=[], response="ok")
        self.assertEqual(r.latency_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
