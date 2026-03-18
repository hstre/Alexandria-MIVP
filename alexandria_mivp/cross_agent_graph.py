"""
Cross-Agent Epistemic Graphs für Multi-Agent-Szenarien.

Modelliert einen gemeinsamen epistemischen Graphen, in dem mehrere Agenten
Claims beisteuern und miteinander verknüpfen.  Kanten repräsentieren
semantische Beziehungen zwischen Claims verschiedener Agenten.

Verwendung::

    graph = CrossAgentGraph()
    graph.add_claim("agent_a", "claim_1", "CO2 is rising.", "EMPIRICAL")
    graph.add_claim("agent_b", "claim_2", "Temperature is rising.", "EMPIRICAL")
    graph.add_edge("agent_a", "claim_1", "agent_b", "claim_2", EdgeType.SUPPORTS)

    paths = graph.paths_between("claim_1", "claim_2")
    summary = graph.summary()

Kantentypen
-----------
* ``SUPPORTS``   – Quelle unterstützt Ziel epistemic
* ``CHALLENGES`` – Quelle widerspricht Ziel
* ``REFINES``    – Quelle verfeinert oder präzisiert Ziel
* ``DEPENDS_ON`` – Quelle setzt Ziel voraus (analog zu Uncertainty Propagation)
* ``DERIVED_FROM`` – Quelle ist abgeleitet von Ziel
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Enums & Datenklassen
# ---------------------------------------------------------------------------

class EdgeType(str, Enum):
    SUPPORTS    = "supports"
    CHALLENGES  = "challenges"
    REFINES     = "refines"
    DEPENDS_ON  = "depends_on"
    DERIVED_FROM = "derived_from"


@dataclass
class ClaimNode:
    """Ein Claim-Knoten im Cross-Agent-Graphen."""
    claim_id: str
    agent_name: str
    content: str
    category: str                         # EMPIRICAL | NORMATIVE | MODEL | SPECULATIVE
    sigma: float = 0.0                    # lokale Unsicherheit
    timestamp: int = field(default_factory=lambda: int(time.time()))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """Gerichtete Kante zwischen zwei Claims."""
    source_claim_id: str
    target_claim_id: str
    edge_type: EdgeType
    agent_name: str                       # welcher Agent hat die Kante hinzugefügt?
    weight: float = 1.0                   # Stärke der Beziehung (0–1)
    timestamp: int = field(default_factory=lambda: int(time.time()))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphQueryResult:
    """Ergebnis einer Graph-Abfrage."""
    nodes: List[ClaimNode]
    edges: List[GraphEdge]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContribution:
    """Zusammenfassung der Beiträge eines einzelnen Agenten."""
    agent_name: str
    claim_count: int
    edge_count: int
    categories: Dict[str, int]           # category → count
    avg_sigma: float
    claim_ids: List[str]


@dataclass
class EpistemicConflict:
    """Ein erkannter epistemischer Konflikt zwischen zwei Agenten."""
    claim_a_id: str
    agent_a: str
    claim_b_id: str
    agent_b: str
    conflict_type: str                   # "direct_challenge" | "indirect_cycle"
    description: str


# ---------------------------------------------------------------------------
# Cross-Agent Epistemic Graph
# ---------------------------------------------------------------------------

class CrossAgentGraph:
    """
    Gemeinsamer epistemischer Graph über mehrere Agenten hinweg.

    Knoten repräsentieren Claims (von verschiedenen Agenten),
    Kanten repräsentieren semantische Beziehungen zwischen Claims.
    """

    def __init__(self) -> None:
        # claim_id → ClaimNode
        self._nodes: Dict[str, ClaimNode] = {}
        # (src_id, tgt_id) → GraphEdge (wir erlauben mehrere Kanten per Paar)
        self._edges: List[GraphEdge] = []
        # agent_name → set of claim_ids
        self._agent_claims: Dict[str, Set[str]] = defaultdict(set)

    # ------------------------------------------------------------------ #
    # Claims hinzufügen / entfernen                                       #
    # ------------------------------------------------------------------ #

    def add_claim(
        self,
        agent_name: str,
        claim_id: str,
        content: str,
        category: str = "EMPIRICAL",
        sigma: float = 0.0,
        timestamp: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ClaimNode:
        """
        Einen Claim im Graphen registrieren.

        Idempotent: erneutes Hinzufügen mit gleicher claim_id überschreibt den Knoten.
        """
        node = ClaimNode(
            claim_id=claim_id,
            agent_name=agent_name,
            content=content,
            category=category,
            sigma=sigma,
            timestamp=timestamp or int(time.time()),
            metadata=metadata or {},
        )
        self._nodes[claim_id] = node
        self._agent_claims[agent_name].add(claim_id)
        return node

    def remove_claim(self, claim_id: str) -> bool:
        """Einen Claim und alle anliegenden Kanten entfernen."""
        if claim_id not in self._nodes:
            return False
        node = self._nodes.pop(claim_id)
        self._agent_claims[node.agent_name].discard(claim_id)
        self._edges = [
            e for e in self._edges
            if e.source_claim_id != claim_id and e.target_claim_id != claim_id
        ]
        return True

    # ------------------------------------------------------------------ #
    # Kanten hinzufügen / entfernen                                       #
    # ------------------------------------------------------------------ #

    def add_edge(
        self,
        agent_name: str,
        source_claim_id: str,
        target_claim_id: str,
        edge_type: EdgeType,
        weight: float = 1.0,
        timestamp: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        """
        Eine gerichtete Kante zwischen zwei Claims hinzufügen.

        Beide Claims müssen bereits im Graphen vorhanden sein.

        Raises:
            KeyError: wenn source oder target nicht existieren.
        """
        if source_claim_id not in self._nodes:
            raise KeyError(f"Source claim '{source_claim_id}' not found in graph.")
        if target_claim_id not in self._nodes:
            raise KeyError(f"Target claim '{target_claim_id}' not found in graph.")

        edge = GraphEdge(
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            edge_type=edge_type,
            agent_name=agent_name,
            weight=max(0.0, min(1.0, weight)),
            timestamp=timestamp or int(time.time()),
            metadata=metadata or {},
        )
        self._edges.append(edge)
        return edge

    def remove_edges(
        self,
        source_claim_id: str,
        target_claim_id: str,
        edge_type: Optional[EdgeType] = None,
    ) -> int:
        """Kanten zwischen source und target entfernen. Gibt Anzahl zurück."""
        before = len(self._edges)
        self._edges = [
            e for e in self._edges
            if not (
                e.source_claim_id == source_claim_id
                and e.target_claim_id == target_claim_id
                and (edge_type is None or e.edge_type == edge_type)
            )
        ]
        return before - len(self._edges)

    # ------------------------------------------------------------------ #
    # Abfragen                                                             #
    # ------------------------------------------------------------------ #

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def get_claim(self, claim_id: str) -> Optional[ClaimNode]:
        return self._nodes.get(claim_id)

    def get_claims_by_agent(self, agent_name: str) -> List[ClaimNode]:
        """Alle Claims eines bestimmten Agenten."""
        return [self._nodes[cid] for cid in self._agent_claims.get(agent_name, set())
                if cid in self._nodes]

    def get_claims_by_category(self, category: str) -> List[ClaimNode]:
        return [n for n in self._nodes.values() if n.category == category]

    def get_edges(
        self,
        source_claim_id: Optional[str] = None,
        target_claim_id: Optional[str] = None,
        edge_type: Optional[EdgeType] = None,
        agent_name: Optional[str] = None,
    ) -> List[GraphEdge]:
        """Kanten mit optionalen Filtern abrufen."""
        result = self._edges
        if source_claim_id is not None:
            result = [e for e in result if e.source_claim_id == source_claim_id]
        if target_claim_id is not None:
            result = [e for e in result if e.target_claim_id == target_claim_id]
        if edge_type is not None:
            result = [e for e in result if e.edge_type == edge_type]
        if agent_name is not None:
            result = [e for e in result if e.agent_name == agent_name]
        return result

    def neighbors(self, claim_id: str, edge_type: Optional[EdgeType] = None) -> List[str]:
        """Direkte Nachbarn (Ziel-Claims der ausgehenden Kanten)."""
        return [
            e.target_claim_id
            for e in self._edges
            if e.source_claim_id == claim_id
            and (edge_type is None or e.edge_type == edge_type)
        ]

    def predecessors(self, claim_id: str, edge_type: Optional[EdgeType] = None) -> List[str]:
        """Claims, die eine Kante zu claim_id haben."""
        return [
            e.source_claim_id
            for e in self._edges
            if e.target_claim_id == claim_id
            and (edge_type is None or e.edge_type == edge_type)
        ]

    # ------------------------------------------------------------------ #
    # Pfadsuche (BFS)                                                     #
    # ------------------------------------------------------------------ #

    def paths_between(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 10,
        edge_types: Optional[Set[EdgeType]] = None,
    ) -> List[List[str]]:
        """
        Alle einfachen Pfade von start_id zu end_id (BFS, begrenzte Tiefe).

        Returns:
            Liste von Pfaden; jeder Pfad ist eine Liste von claim_ids.
        """
        if start_id not in self._nodes or end_id not in self._nodes:
            return []

        all_paths: List[List[str]] = []
        queue: deque = deque([[start_id]])
        visited_paths: Set[Tuple[str, ...]] = set()

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == end_id and len(path) > 1:
                all_paths.append(path)
                continue

            if len(path) > max_depth:
                continue

            for edge in self._edges:
                if edge.source_claim_id != current:
                    continue
                if edge_types and edge.edge_type not in edge_types:
                    continue
                next_id = edge.target_claim_id
                if next_id in path:  # Zyklus vermeiden
                    continue
                new_path = path + [next_id]
                key = tuple(new_path)
                if key not in visited_paths:
                    visited_paths.add(key)
                    queue.append(new_path)

        return all_paths

    def shortest_path(
        self,
        start_id: str,
        end_id: str,
        edge_types: Optional[Set[EdgeType]] = None,
    ) -> Optional[List[str]]:
        """BFS-Kürzester-Pfad von start zu end."""
        paths = self.paths_between(start_id, end_id, max_depth=20, edge_types=edge_types)
        if not paths:
            return None
        return min(paths, key=len)

    # ------------------------------------------------------------------ #
    # Konflikte erkennen                                                   #
    # ------------------------------------------------------------------ #

    def find_conflicts(self) -> List[EpistemicConflict]:
        """
        Erkenne direkte CHALLENGES-Kanten und wechselseitige Konflikte.

        Ein direkter Konflikt liegt vor, wenn agent_a claim_x anficht und
        agent_b (via claim_y) claim_x stützt – oder wenn es wechselseitige
        CHALLENGES-Kanten gibt.
        """
        conflicts: List[EpistemicConflict] = []
        challenge_edges = [e for e in self._edges if e.edge_type == EdgeType.CHALLENGES]

        # Direkte Konflikte: bidirektionale CHALLENGES-Kanten
        challenge_pairs: Set[Tuple[str, str]] = {
            (e.source_claim_id, e.target_claim_id) for e in challenge_edges
        }
        reported_pairs: Set[Tuple[str, str]] = set()
        for src, tgt in challenge_pairs:
            if (tgt, src) in challenge_pairs:
                canonical = tuple(sorted([src, tgt]))
                if canonical in reported_pairs:
                    continue
                reported_pairs.add(canonical)
                node_src = self._nodes.get(src)
                node_tgt = self._nodes.get(tgt)
                if node_src and node_tgt and node_src.agent_name != node_tgt.agent_name:
                    conflicts.append(EpistemicConflict(
                        claim_a_id=src,
                        agent_a=node_src.agent_name,
                        claim_b_id=tgt,
                        agent_b=node_tgt.agent_name,
                        conflict_type="direct_challenge",
                        description=(
                            f"'{src}' and '{tgt}' mutually challenge each other "
                            f"(agents: {node_src.agent_name} ↔ {node_tgt.agent_name})."
                        ),
                    ))

        # Cross-agent CHALLENGES: claim von agent A fordert claim von agent B heraus
        for edge in challenge_edges:
            src_node = self._nodes.get(edge.source_claim_id)
            tgt_node = self._nodes.get(edge.target_claim_id)
            if not src_node or not tgt_node:
                continue
            if src_node.agent_name == tgt_node.agent_name:
                continue
            # Bereits in bidirektionalen Konflikten?
            key = (edge.source_claim_id, edge.target_claim_id)
            rev_key = (edge.target_claim_id, edge.source_claim_id)
            if rev_key in challenge_pairs:
                continue  # already reported as direct_challenge
            conflicts.append(EpistemicConflict(
                claim_a_id=edge.source_claim_id,
                agent_a=src_node.agent_name,
                claim_b_id=edge.target_claim_id,
                agent_b=tgt_node.agent_name,
                conflict_type="cross_agent_challenge",
                description=(
                    f"Agent '{src_node.agent_name}' (claim '{edge.source_claim_id}') "
                    f"challenges agent '{tgt_node.agent_name}' (claim '{edge.target_claim_id}')."
                ),
            ))

        return conflicts

    # ------------------------------------------------------------------ #
    # Zusammenfassung / Export                                             #
    # ------------------------------------------------------------------ #

    def agent_contributions(self) -> Dict[str, AgentContribution]:
        """Beiträge pro Agent berechnen."""
        result: Dict[str, AgentContribution] = {}
        for agent_name, claim_ids in self._agent_claims.items():
            nodes = [self._nodes[cid] for cid in claim_ids if cid in self._nodes]
            edges = [e for e in self._edges if e.agent_name == agent_name]
            categories: Dict[str, int] = defaultdict(int)
            sigma_sum = 0.0
            for node in nodes:
                categories[node.category] += 1
                sigma_sum += node.sigma
            avg_sigma = sigma_sum / len(nodes) if nodes else 0.0
            result[agent_name] = AgentContribution(
                agent_name=agent_name,
                claim_count=len(nodes),
                edge_count=len(edges),
                categories=dict(categories),
                avg_sigma=avg_sigma,
                claim_ids=list(claim_ids),
            )
        return result

    def summary(self) -> Dict[str, Any]:
        """Kompakte Zusammenfassung des Graphen."""
        agents = list(self._agent_claims.keys())
        categories: Dict[str, int] = defaultdict(int)
        sigmas = []
        for node in self._nodes.values():
            categories[node.category] += 1
            sigmas.append(node.sigma)

        edge_types: Dict[str, int] = defaultdict(int)
        for edge in self._edges:
            edge_types[edge.edge_type.value] += 1

        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "agent_count": len(agents),
            "agents": agents,
            "categories": dict(categories),
            "edge_types": dict(edge_types),
            "sigma_min": min(sigmas) if sigmas else 0.0,
            "sigma_max": max(sigmas) if sigmas else 0.0,
            "sigma_mean": sum(sigmas) / len(sigmas) if sigmas else 0.0,
            "conflict_count": len(self.find_conflicts()),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Vollständiger Export als JSON-serialisierbares Dict."""
        return {
            "nodes": [
                {
                    "claim_id": n.claim_id,
                    "agent_name": n.agent_name,
                    "content": n.content,
                    "category": n.category,
                    "sigma": n.sigma,
                    "timestamp": n.timestamp,
                    "metadata": n.metadata,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_claim_id,
                    "target": e.target_claim_id,
                    "type": e.edge_type.value,
                    "agent": e.agent_name,
                    "weight": e.weight,
                    "timestamp": e.timestamp,
                    "metadata": e.metadata,
                }
                for e in self._edges
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossAgentGraph":
        """Graphen aus einem exportierten Dict wiederherstellen."""
        graph = cls()
        for nd in data.get("nodes", []):
            graph.add_claim(
                agent_name=nd["agent_name"],
                claim_id=nd["claim_id"],
                content=nd["content"],
                category=nd.get("category", "EMPIRICAL"),
                sigma=nd.get("sigma", 0.0),
                timestamp=nd.get("timestamp"),
                metadata=nd.get("metadata", {}),
            )
        for ed in data.get("edges", []):
            try:
                graph.add_edge(
                    agent_name=ed["agent"],
                    source_claim_id=ed["source"],
                    target_claim_id=ed["target"],
                    edge_type=EdgeType(ed["type"]),
                    weight=ed.get("weight", 1.0),
                    timestamp=ed.get("timestamp"),
                    metadata=ed.get("metadata", {}),
                )
            except (KeyError, ValueError):
                pass  # Skip malformed edges
        return graph

    # ------------------------------------------------------------------ #
    # Integration mit AlexandriaMIVPStore                                  #
    # ------------------------------------------------------------------ #

    def build_from_store(
        self,
        store: Any,  # AlexandriaMIVPStore | AlexandriaStore
        branch_id: str,
        agent_name: str,
    ) -> int:
        """
        Claims aus einem AlexandriaMIVPStore-Branch in den Graphen laden.

        Erkennt automatisch ``depends_on``-Felder in den Patch-Payloads und
        legt entsprechende DEPENDS_ON-Kanten an.

        Returns:
            Anzahl der hinzugefügten Knoten.
        """
        nodes = store.reconstruct(branch_id)
        count = 0
        for node_id, node in nodes.items():
            self.add_claim(
                agent_name=agent_name,
                claim_id=node_id,
                content=getattr(node, "content", str(node_id)),
                category=getattr(node, "category", "EMPIRICAL"),
                sigma=node.uncertainty.sigma if node.uncertainty else 0.0,
            )
            count += 1

        # DEPENDS_ON-Kanten aus Branch-Patches extrahieren
        branch_patches = store.branches.get(branch_id, [])
        for patch in branch_patches:
            dep_field = getattr(patch, "payload", {}).get("depends_on", [])
            if not isinstance(dep_field, list):
                continue
            for dep_id in dep_field:
                if dep_id in self._nodes and patch.target_id in self._nodes:
                    try:
                        self.add_edge(
                            agent_name=agent_name,
                            source_claim_id=patch.target_id,
                            target_claim_id=dep_id,
                            edge_type=EdgeType.DEPENDS_ON,
                        )
                    except KeyError:
                        pass

        return count

    # ------------------------------------------------------------------ #
    # Iteratoren                                                           #
    # ------------------------------------------------------------------ #

    def iter_nodes(self) -> Iterator[ClaimNode]:
        yield from self._nodes.values()

    def iter_edges(self) -> Iterator[GraphEdge]:
        yield from self._edges

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, claim_id: str) -> bool:
        return claim_id in self._nodes
