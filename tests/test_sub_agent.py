"""
Tests für Sub-Agent Spawning und Multi-Agenten-Koordination.
"""

import unittest


from alexandria_mivp.alexandria_mivp import AgentIdentity
from alexandria_mivp.sub_agent import SubAgent, SubAgentConfig, MultiAgentCoordinator, ConsensusResult


def make_coordinator_identity():
    return AgentIdentity(
        name="TestCoordinator",
        model_path="models/coord.bin",
        model_bytes=b"test_coordinator",
        system_prompt="Test coordinator.",
        guardrails=[],
        temperature=0.5,
        top_p=0.9,
        max_tokens=500,
    )


class TestSubAgentConfig(unittest.TestCase):
    def test_config_fields(self):
        cfg = SubAgentConfig(
            name="FactChecker",
            role="Verify facts",
            system_prompt="You verify facts.",
            branch="fact_checking",
        )
        self.assertEqual(cfg.name, "FactChecker")
        self.assertEqual(cfg.branch, "fact_checking")
        self.assertEqual(cfg.guardrails, [])


class TestMultiAgentCoordinatorInit(unittest.TestCase):
    def test_init_without_identity(self):
        coord = MultiAgentCoordinator()
        self.assertIsNotNone(coord.shared_store)
        self.assertEqual(len(coord.agents), 0)

    def test_init_with_identity(self):
        identity = make_coordinator_identity()
        coord = MultiAgentCoordinator(coordinator_identity=identity)
        self.assertIsNotNone(coord.shared_store)


class TestSpawnAndDespawn(unittest.TestCase):
    def setUp(self):
        self.coord = MultiAgentCoordinator()

    def test_spawn_creates_agent(self):
        agent = self.coord.spawn(
            "FactChecker", role="Verify facts",
            system_prompt="You verify facts.", branch="fact"
        )
        self.assertIsInstance(agent, SubAgent)
        self.assertIn("FactChecker", self.coord.agents)

    def test_spawn_multiple_agents(self):
        self.coord.spawn("A", role="Role A", system_prompt="A.", branch="a")
        self.coord.spawn("B", role="Role B", system_prompt="B.", branch="b")
        self.assertEqual(len(self.coord.agents), 2)

    def test_spawn_duplicate_raises(self):
        self.coord.spawn("X", role="Role X", system_prompt="X.", branch="x")
        with self.assertRaises(ValueError):
            self.coord.spawn("X", role="Role X2", system_prompt="X2.", branch="x2")

    def test_despawn_removes_agent(self):
        self.coord.spawn("Temp", role="Temp", system_prompt="Temp.", branch="temp")
        removed = self.coord.despawn("Temp")
        self.assertTrue(removed)
        self.assertNotIn("Temp", self.coord.agents)

    def test_despawn_nonexistent_returns_false(self):
        removed = self.coord.despawn("NonExistent")
        self.assertFalse(removed)


class TestSubAgentEvaluate(unittest.TestCase):
    def setUp(self):
        self.coord = MultiAgentCoordinator()
        self.fact_checker = self.coord.spawn(
            "FactChecker",
            role="Verify empirical claims",
            system_prompt="You verify facts.",
            branch="fact_checking",
        )

    def test_evaluate_returns_result(self):
        result = self.fact_checker.evaluate("Water is H2O")
        self.assertIsNotNone(result)
        self.assertEqual(result.agent_name, "FactChecker")

    def test_evaluate_stores_in_branch(self):
        before = len(self.fact_checker.store.reconstruct("fact_checking"))
        self.fact_checker.evaluate("CO2 is a greenhouse gas")
        after = len(self.fact_checker.store.reconstruct("fact_checking"))
        self.assertEqual(after, before + 1)

    def test_evaluate_has_verdict(self):
        result = self.fact_checker.evaluate("Test claim")
        self.assertIn(result.verdict, {"supports", "challenges", "neutral"})

    def test_evaluate_has_cih(self):
        result = self.fact_checker.evaluate("Test claim")
        self.assertTrue(len(result.cih_hex) > 0)

    def test_evaluate_has_commit_hash(self):
        result = self.fact_checker.evaluate("Test claim")
        self.assertTrue(len(result.commit_hash) > 0)

    def test_evaluate_vague_claim_neutral(self):
        """Vage Formulierungen → neutral bei Fact-Checker."""
        result = self.fact_checker.evaluate("Maybe climate change is real")
        self.assertEqual(result.verdict, "neutral")

    def test_evaluate_precise_claim_supports(self):
        """Präzise Aussage → supports bei Fact-Checker."""
        result = self.fact_checker.evaluate("CO2 concentration is 420 ppm")
        self.assertEqual(result.verdict, "supports")


class TestSubAgentRoleHeuristics(unittest.TestCase):
    def setUp(self):
        self.coord = MultiAgentCoordinator()

    def test_ethics_agent_normative_neutral(self):
        ethics = self.coord.spawn(
            "Ethics", role="Evaluate normative claims",
            system_prompt="Ethics.", branch="ethics"
        )
        result = ethics.evaluate("Agents should be transparent")
        self.assertEqual(result.verdict, "neutral")

    def test_model_validator_assumption_challenges(self):
        validator = self.coord.spawn(
            "Validator", role="Validate model assumptions",
            system_prompt="Validator.", branch="models"
        )
        result = validator.evaluate("Assume all agents are rational")
        self.assertEqual(result.verdict, "challenges")

    def test_unknown_role_neutral(self):
        generic = self.coord.spawn(
            "Generic", role="General purpose",
            system_prompt="Generic.", branch="general"
        )
        result = generic.evaluate("Some claim without keywords")
        self.assertEqual(result.verdict, "neutral")


class TestSubAgentVerifyIdentity(unittest.TestCase):
    def test_verify_identity_ok(self):
        coord = MultiAgentCoordinator()
        agent = coord.spawn(
            "TestAgent", role="Test",
            system_prompt="Test.", branch="test"
        )
        self.assertTrue(agent.verify_identity())


class TestCoordinateConsensus(unittest.TestCase):
    def setUp(self):
        self.coord = MultiAgentCoordinator()
        self.coord.spawn("F", role="Verify facts", system_prompt="F.", branch="f")
        self.coord.spawn("E", role="Evaluate normative claims", system_prompt="E.", branch="e")
        self.coord.spawn("M", role="Validate model assumptions", system_prompt="M.", branch="m")

    def test_coordinate_returns_result(self):
        result = self.coord.coordinate("CO2 is rising")
        self.assertIsInstance(result, ConsensusResult)

    def test_coordinate_has_all_evaluations(self):
        result = self.coord.coordinate("Test claim")
        self.assertEqual(len(result.evaluations), 3)

    def test_coordinate_stores_consensus(self):
        before = len(self.coord.shared_store.reconstruct("consensus"))
        self.coord.coordinate("Another claim")
        after = len(self.coord.shared_store.reconstruct("consensus"))
        self.assertEqual(after, before + 1)

    def test_coordinate_has_commit_hash(self):
        result = self.coord.coordinate("Test")
        self.assertTrue(len(result.commit_hash) > 0)

    def test_consensus_verdict_valid_values(self):
        result = self.coord.coordinate("Test")
        self.assertIn(result.consensus_verdict, {"supported", "challenged", "inconclusive"})

    def test_agreement_ratio_between_zero_and_one(self):
        result = self.coord.coordinate("Test")
        self.assertGreaterEqual(result.agreement_ratio, 0.0)
        self.assertLessEqual(result.agreement_ratio, 1.0)

    def test_coordinate_no_agents_raises(self):
        coord = MultiAgentCoordinator()
        with self.assertRaises(RuntimeError):
            coord.coordinate("Some claim")


class TestConsensusLogic(unittest.TestCase):
    def test_majority_supports_gives_supported(self):
        """3 von 3 supports → supported."""
        coord = MultiAgentCoordinator()
        # Fact-Checker: supports precise claims
        for i in range(3):
            coord.spawn(f"F{i}", role="Verify empirical claims",
                        system_prompt=".", branch=f"f{i}")
        result = coord.coordinate("CO2 is 420 ppm exactly")
        # Alle Fact-Checker: "supports"
        self.assertEqual(result.consensus_verdict, "supported")

    def test_majority_challenges_gives_challenged(self):
        """3 von 3 challenges → challenged."""
        coord = MultiAgentCoordinator()
        for i in range(3):
            coord.spawn(f"V{i}", role="Validate model assumptions",
                        system_prompt=".", branch=f"v{i}")
        result = coord.coordinate("Assume all users are rational actors")
        self.assertEqual(result.consensus_verdict, "challenged")


class TestStatus(unittest.TestCase):
    def test_status_empty(self):
        coord = MultiAgentCoordinator()
        status = coord.status()
        self.assertEqual(status["agent_count"], 0)
        self.assertEqual(status["agents"], [])

    def test_status_with_agents(self):
        coord = MultiAgentCoordinator()
        coord.spawn("A1", role="R1", system_prompt=".", branch="a1")
        coord.spawn("A2", role="R2", system_prompt=".", branch="a2")
        status = coord.status()
        self.assertEqual(status["agent_count"], 2)
        names = [a["name"] for a in status["agents"]]
        self.assertIn("A1", names)
        self.assertIn("A2", names)


class TestVerifyAllIdentities(unittest.TestCase):
    def test_all_identities_valid(self):
        coord = MultiAgentCoordinator()
        coord.spawn("A", role="R", system_prompt=".", branch="a")
        coord.spawn("B", role="R", system_prompt=".", branch="b")
        results = coord.verify_all_identities()
        self.assertTrue(all(results.values()))
        self.assertIn("A", results)
        self.assertIn("B", results)


if __name__ == "__main__":
    unittest.main()
