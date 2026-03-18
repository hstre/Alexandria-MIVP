"""Tests for CrossAgentGraph (cross_agent_graph.py)."""
import sys
import os
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cross_agent_graph import (
    CrossAgentGraph, ClaimNode, GraphEdge, EdgeType,
    AgentContribution, EpistemicConflict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_graph():
    g = CrossAgentGraph()
    g.add_claim("agent_a", "c1", "CO2 is rising.", "EMPIRICAL", sigma=0.1)
    g.add_claim("agent_a", "c2", "Temperature is rising.", "EMPIRICAL", sigma=0.2)
    g.add_claim("agent_b", "c3", "Ice caps are melting.", "EMPIRICAL", sigma=0.15)
    g.add_claim("agent_b", "c4", "We should act now.", "NORMATIVE", sigma=0.3)
    return g


# ---------------------------------------------------------------------------
# Basic operations
# ---------------------------------------------------------------------------

class TestAddRemoveClaims:
    def test_add_claim_returns_node(self):
        g = CrossAgentGraph()
        node = g.add_claim("agent_a", "x1", "Hello", "EMPIRICAL")
        assert isinstance(node, ClaimNode)
        assert node.claim_id == "x1"
        assert node.agent_name == "agent_a"

    def test_add_multiple_claims(self):
        g = make_graph()
        assert g.node_count == 4

    def test_overwrite_existing_claim(self):
        g = CrossAgentGraph()
        g.add_claim("agent_a", "x1", "Original", "EMPIRICAL", sigma=0.1)
        g.add_claim("agent_a", "x1", "Updated", "EMPIRICAL", sigma=0.2)
        assert g.node_count == 1
        assert g.get_claim("x1").content == "Updated"
        assert g.get_claim("x1").sigma == 0.2

    def test_contains(self):
        g = make_graph()
        assert "c1" in g
        assert "nonexistent" not in g

    def test_remove_claim(self):
        g = make_graph()
        removed = g.remove_claim("c1")
        assert removed is True
        assert g.node_count == 3
        assert "c1" not in g

    def test_remove_nonexistent_claim(self):
        g = make_graph()
        removed = g.remove_claim("nonexistent")
        assert removed is False

    def test_remove_claim_removes_edges(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_b", "c3", "c1", EdgeType.REFINES)
        g.remove_claim("c1")
        assert len(g.get_edges()) == 0

    def test_len(self):
        g = make_graph()
        assert len(g) == 4


# ---------------------------------------------------------------------------
# Edge operations
# ---------------------------------------------------------------------------

class TestEdgeOperations:
    def test_add_edge(self):
        g = make_graph()
        edge = g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        assert isinstance(edge, GraphEdge)
        assert edge.source_claim_id == "c1"
        assert edge.target_claim_id == "c2"
        assert edge.edge_type == EdgeType.SUPPORTS

    def test_edge_weight_clamped(self):
        g = make_graph()
        edge = g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS, weight=1.5)
        assert edge.weight == 1.0
        edge2 = g.add_edge("agent_a", "c1", "c3", EdgeType.SUPPORTS, weight=-0.5)
        assert edge2.weight == 0.0

    def test_add_edge_missing_source(self):
        g = make_graph()
        with pytest.raises(KeyError, match="Source claim"):
            g.add_edge("agent_a", "nonexistent", "c2", EdgeType.SUPPORTS)

    def test_add_edge_missing_target(self):
        g = make_graph()
        with pytest.raises(KeyError, match="Target claim"):
            g.add_edge("agent_a", "c1", "nonexistent", EdgeType.SUPPORTS)

    def test_edge_count(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_b", "c3", "c4", EdgeType.DEPENDS_ON)
        assert g.edge_count == 2

    def test_remove_edges(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c1", "c2", EdgeType.REFINES)
        count = g.remove_edges("c1", "c2")
        assert count == 2
        assert g.edge_count == 0

    def test_remove_edges_by_type(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c1", "c2", EdgeType.REFINES)
        count = g.remove_edges("c1", "c2", edge_type=EdgeType.SUPPORTS)
        assert count == 1
        assert g.edge_count == 1

    def test_multiple_edge_types(self):
        g = make_graph()
        for et in EdgeType:
            g.add_claim("tmp_a", f"src_{et.value}", "src", "EMPIRICAL")
            g.add_claim("tmp_b", f"tgt_{et.value}", "tgt", "EMPIRICAL")
            g.add_edge("tmp_a", f"src_{et.value}", f"tgt_{et.value}", et)
        assert g.edge_count == len(EdgeType)


# ---------------------------------------------------------------------------
# Query methods
# ---------------------------------------------------------------------------

class TestQueries:
    def test_get_claim(self):
        g = make_graph()
        node = g.get_claim("c1")
        assert node is not None
        assert node.content == "CO2 is rising."

    def test_get_claim_nonexistent(self):
        g = CrossAgentGraph()
        assert g.get_claim("nonexistent") is None

    def test_get_claims_by_agent(self):
        g = make_graph()
        claims_a = g.get_claims_by_agent("agent_a")
        assert len(claims_a) == 2
        assert all(c.agent_name == "agent_a" for c in claims_a)

    def test_get_claims_by_category(self):
        g = make_graph()
        empirical = g.get_claims_by_category("EMPIRICAL")
        assert len(empirical) == 3
        normative = g.get_claims_by_category("NORMATIVE")
        assert len(normative) == 1

    def test_get_edges_filtered(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_b", "c3", "c4", EdgeType.CHALLENGES)
        g.add_edge("agent_a", "c2", "c3", EdgeType.SUPPORTS)

        supports = g.get_edges(edge_type=EdgeType.SUPPORTS)
        assert len(supports) == 2

        from_c1 = g.get_edges(source_claim_id="c1")
        assert len(from_c1) == 1

        agent_b_edges = g.get_edges(agent_name="agent_b")
        assert len(agent_b_edges) == 1

    def test_neighbors(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c1", "c3", EdgeType.REFINES)
        neighbors = g.neighbors("c1")
        assert set(neighbors) == {"c2", "c3"}

    def test_neighbors_filtered_by_type(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c1", "c3", EdgeType.CHALLENGES)
        neighbors = g.neighbors("c1", edge_type=EdgeType.SUPPORTS)
        assert neighbors == ["c2"]

    def test_predecessors(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c3", EdgeType.SUPPORTS)
        g.add_edge("agent_b", "c2", "c3", EdgeType.SUPPORTS)
        preds = g.predecessors("c3")
        assert set(preds) == {"c1", "c2"}


# ---------------------------------------------------------------------------
# Path finding
# ---------------------------------------------------------------------------

class TestPathFinding:
    def test_paths_between_direct(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        paths = g.paths_between("c1", "c2")
        assert len(paths) == 1
        assert paths[0] == ["c1", "c2"]

    def test_paths_between_indirect(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c2", "c3", EdgeType.REFINES)
        paths = g.paths_between("c1", "c3")
        assert len(paths) == 1
        assert paths[0] == ["c1", "c2", "c3"]

    def test_paths_between_multiple(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c1", "c3", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c2", "c4", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c3", "c4", EdgeType.SUPPORTS)
        paths = g.paths_between("c1", "c4")
        assert len(paths) == 2

    def test_paths_between_no_path(self):
        g = make_graph()
        paths = g.paths_between("c1", "c4")
        assert paths == []

    def test_paths_max_depth(self):
        g = CrossAgentGraph()
        for i in range(10):
            g.add_claim("agent", f"n{i}", f"node {i}", "EMPIRICAL")
        for i in range(9):
            g.add_edge("agent", f"n{i}", f"n{i+1}", EdgeType.SUPPORTS)
        paths = g.paths_between("n0", "n9", max_depth=5)
        assert paths == []   # chain is 10 deep, exceeds max_depth=5

    def test_shortest_path(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c2", "c3", EdgeType.SUPPORTS)
        g.add_edge("agent_a", "c1", "c3", EdgeType.SUPPORTS)
        path = g.shortest_path("c1", "c3")
        assert path == ["c1", "c3"]

    def test_shortest_path_no_path(self):
        g = make_graph()
        path = g.shortest_path("c1", "c4")
        assert path is None

    def test_paths_nonexistent_node(self):
        g = make_graph()
        paths = g.paths_between("c1", "nonexistent")
        assert paths == []


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

class TestConflicts:
    def test_no_conflicts(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        assert g.find_conflicts() == []

    def test_cross_agent_challenge(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c3", EdgeType.CHALLENGES)
        conflicts = g.find_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "cross_agent_challenge"
        assert conflicts[0].agent_a == "agent_a"

    def test_direct_mutual_challenge(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c3", EdgeType.CHALLENGES)
        g.add_edge("agent_b", "c3", "c1", EdgeType.CHALLENGES)
        conflicts = g.find_conflicts()
        direct = [c for c in conflicts if c.conflict_type == "direct_challenge"]
        assert len(direct) == 1

    def test_same_agent_challenge_not_conflict(self):
        g = CrossAgentGraph()
        g.add_claim("agent_a", "x1", "Claim 1", "EMPIRICAL")
        g.add_claim("agent_a", "x2", "Claim 2", "EMPIRICAL")
        g.add_edge("agent_a", "x1", "x2", EdgeType.CHALLENGES)
        conflicts = g.find_conflicts()
        cross_agent = [c for c in conflicts if c.agent_a != c.agent_b]
        assert len(cross_agent) == 0


# ---------------------------------------------------------------------------
# Summary & Export
# ---------------------------------------------------------------------------

class TestSummaryAndExport:
    def test_summary(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        s = g.summary()
        assert s["node_count"] == 4
        assert s["edge_count"] == 1
        assert s["agent_count"] == 2
        assert "EMPIRICAL" in s["categories"]
        assert "NORMATIVE" in s["categories"]

    def test_agent_contributions(self):
        g = make_graph()
        contribs = g.agent_contributions()
        assert "agent_a" in contribs
        assert contribs["agent_a"].claim_count == 2
        assert "agent_b" in contribs
        assert contribs["agent_b"].claim_count == 2

    def test_to_dict_and_from_dict(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS, weight=0.8)
        d = g.to_dict()
        assert len(d["nodes"]) == 4
        assert len(d["edges"]) == 1

        g2 = CrossAgentGraph.from_dict(d)
        assert g2.node_count == 4
        assert g2.edge_count == 1
        assert g2.get_claim("c1").content == "CO2 is rising."

    def test_from_dict_skips_invalid_edges(self):
        d = {
            "nodes": [{"claim_id": "x", "agent_name": "a", "content": "X",
                       "category": "EMPIRICAL", "sigma": 0.0}],
            "edges": [{"source": "x", "target": "nonexistent", "type": "supports",
                       "agent": "a", "weight": 1.0}],
        }
        g = CrossAgentGraph.from_dict(d)
        assert g.node_count == 1
        assert g.edge_count == 0  # invalid edge skipped

    def test_iter_nodes(self):
        g = make_graph()
        nodes = list(g.iter_nodes())
        assert len(nodes) == 4

    def test_iter_edges(self):
        g = make_graph()
        g.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS)
        edges = list(g.iter_edges())
        assert len(edges) == 1
