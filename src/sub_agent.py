"""
Sub-Agent Spawning und Multi-Agenten-Koordination.

Ermöglicht das Erstellen spezialisierter Sub-Agenten (z.B. FactChecker,
EthicsReviewer, ModelValidator) und die Koordination von Claims über
mehrere Agenten hinweg mit Konsensbildung.

Beispiel:
    coordinator = MultiAgentCoordinator()
    coordinator.spawn("FactChecker", role="Verify empirical claims",
                      system_prompt="You verify facts.", branch="fact_checking")
    result = coordinator.coordinate("Climate change is real.")
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from .alexandria_v2 import Patch, CATEGORIES
    from .alexandria_mivp import AlexandriaMIVPStore, AgentIdentity, verify_cih_internal_consistency
    from .message_router import MessageRouter
except ImportError:
    from alexandria_v2 import Patch, CATEGORIES  # type: ignore[no-redef]
    from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity, verify_cih_internal_consistency  # type: ignore[no-redef]
    from message_router import MessageRouter  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------

@dataclass
class SubAgentConfig:
    """Konfiguration eines Sub-Agenten."""
    name: str
    role: str
    system_prompt: str
    branch: str
    guardrails: List[Dict[str, str]] = field(default_factory=list)
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2000
    # Optionale Modell-Bytes; in Tests oft leer
    model_bytes: bytes = b""


@dataclass
class EvaluationResult:
    """Ergebnis einer Sub-Agenten-Bewertung."""
    agent_name: str
    branch: str
    claim_text: str
    category: str
    confidence: float          # sigma-Wert (niedrig = hohe Konfidenz)
    verdict: str               # "supports" | "challenges" | "neutral"
    reasoning: str
    commit_hash: str
    cih_hex: str


@dataclass
class ConsensusResult:
    """Ergebnis der Konsensbildung über alle Sub-Agenten."""
    claim_text: str
    evaluations: List[EvaluationResult]
    consensus_verdict: str     # "supported" | "challenged" | "inconclusive"
    confidence: float
    agreement_ratio: float     # Anteil der Agenten, die zum Konsens beitragen
    commit_hash: str           # Hash des Konsens-Patches im Shared Store
    details: str = ""


# ---------------------------------------------------------------------------
# Sub-Agent
# ---------------------------------------------------------------------------

class SubAgent:
    """
    Ein spezialisierter Agent mit eigenem Store und eigener Identität.

    Wird vom MultiAgentCoordinator verwaltet.
    """

    def __init__(self, config: SubAgentConfig, shared_store: AlexandriaMIVPStore):
        self.config = config
        self.shared_store = shared_store

        self.identity = AgentIdentity(
            name=config.name,
            model_path=f"models/{config.name.lower()}.bin",
            model_bytes=config.model_bytes or config.name.encode(),
            system_prompt=config.system_prompt,
            guardrails=config.guardrails or [
                {"id": "specialization", "rule": f"Focus on {config.role.lower()}"},
                {"id": "collaboration", "rule": "Coordinate with other agents"},
            ],
            temperature=config.temperature,
            top_p=config.top_p,
            max_tokens=config.max_tokens,
        )

        self.store = AlexandriaMIVPStore(agent_identity=self.identity)
        if config.branch != "main":
            self.store.create_branch(config.branch)
        self.store.checkout(config.branch)
        self.router = MessageRouter(self.store, self.identity)

    # ------------------------------------------------------------------
    # Bewertung
    # ------------------------------------------------------------------

    def evaluate(self, claim_text: str, category: str = "EMPIRICAL") -> EvaluationResult:
        """
        Claim aus der Perspektive dieses Agenten bewerten.

        Die Bewertungslogik ist heuristisch: In einem echten System würde
        hier ein LLM-Aufruf oder ein spezialisiertes Modell stehen.
        """
        verdict, reasoning, confidence = self._assess(claim_text)

        ts = int(time.time())
        uid = abs(hash(claim_text + self.config.name + str(ts)))
        patch = Patch(
            patch_id=f"eval_{self.config.name}_{uid}",
            parent_patch_id=self.store.get_last_patch_id(self.config.branch),
            branch_id=self.config.branch,
            timestamp=ts,
            operation="ADD",
            target_id=f"eval_{uid}",
            category=category if category in CATEGORIES else "EMPIRICAL",
            payload={
                "content": claim_text,
                "evaluation": verdict,
                "reasoning": reasoning,
                "role": self.config.role,
                "source": "sub_agent_evaluation",
            },
            audit={
                "validated": True,
                "decay": 0.01,
                "created_by": self.config.name,
            },
            uncertainty={"sigma": confidence, "ci": [max(0.0, 1 - confidence), 1.0], "n": 1},
        )
        commit_hash = self.store.submit_with_identity(patch)

        return EvaluationResult(
            agent_name=self.config.name,
            branch=self.config.branch,
            claim_text=claim_text,
            category=category,
            confidence=confidence,
            verdict=verdict,
            reasoning=reasoning,
            commit_hash=commit_hash,
            cih_hex=self.identity.compute_cih().hex(),
        )

    def verify_identity(self) -> bool:
        """Eigene MIVP-Identität intern verifizieren."""
        identity_dict = self.identity.get_identity_dict()
        return verify_cih_internal_consistency(identity_dict)

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _assess(self, claim_text: str):
        """
        Einfache heuristische Bewertung eines Claims.

        Gibt (verdict, reasoning, sigma) zurück.
        In einer echten Implementierung: LLM-Aufruf.
        """
        text_lower = claim_text.lower()
        role_lower = self.config.role.lower()

        # Heuristik: Agenten-Rolle beeinflusst Bewertung
        if "empirical" in role_lower or "fact" in role_lower or "verify" in role_lower:
            # Fact-Checker: skeptisch bei vagen Aussagen
            vague_terms = {"maybe", "perhaps", "might", "could", "possibly", "vielleicht", "möglicherweise"}
            if any(t in text_lower for t in vague_terms):
                return "neutral", f"{self.config.name}: Claim enthält vage Formulierungen.", 0.6
            return "supports", f"{self.config.name}: Claim ist präzise formuliert.", 0.2

        elif "ethic" in role_lower or "normativ" in role_lower:
            # Ethics Reviewer: prüft auf normative Implikationen
            normative_terms = {"should", "must", "ought", "shall", "soll", "muss", "darf"}
            if any(t in text_lower for t in normative_terms):
                return "neutral", f"{self.config.name}: Enthält normative Implikationen – weitere Prüfung nötig.", 0.5
            return "supports", f"{self.config.name}: Keine ethischen Bedenken erkannt.", 0.3

        elif "model" in role_lower or "validat" in role_lower or "assumption" in role_lower:
            # Model Validator: prüft auf Modellannahmen
            assumption_terms = {"assume", "given that", "assuming", "annahme", "vorausgesetzt"}
            if any(t in text_lower for t in assumption_terms):
                return "challenges", f"{self.config.name}: Implizite Annahmen müssen explizit gemacht werden.", 0.4
            return "supports", f"{self.config.name}: Keine versteckten Modellannahmen erkannt.", 0.25

        else:
            return "neutral", f"{self.config.name}: Allgemeine Bewertung ohne spezifische Rolle.", 0.5


# ---------------------------------------------------------------------------
# Multi-Agenten-Koordinator
# ---------------------------------------------------------------------------

class MultiAgentCoordinator:
    """
    Verwaltet mehrere Sub-Agenten und koordiniert Claims über alle Agenten hinweg.

    Verwendung:
        coordinator = MultiAgentCoordinator(coordinator_identity)
        coordinator.spawn("FactChecker", role="Verify empirical claims",
                          system_prompt="You verify facts.", branch="fact_checking")
        result = coordinator.coordinate("CO2 levels are rising.")
        print(result.consensus_verdict)
    """

    def __init__(self, coordinator_identity: Optional[AgentIdentity] = None):
        """
        Args:
            coordinator_identity: Optionale Identität für den Shared Store.
                                  Wenn None, wird eine Standard-Identität erstellt.
        """
        if coordinator_identity is None:
            coordinator_identity = AgentIdentity(
                name="Coordinator",
                model_path="models/coordinator.bin",
                model_bytes=b"coordinator",
                system_prompt="Multi-agent coordinator for epistemic consensus.",
                guardrails=[{"id": "neutrality", "rule": "Remain neutral in consensus building"}],
                temperature=0.5,
                top_p=0.9,
                max_tokens=1000,
            )

        self._identity = coordinator_identity
        self.shared_store = AlexandriaMIVPStore(agent_identity=coordinator_identity)
        self.shared_store.create_branch("consensus")
        self.shared_store.checkout("consensus")

        self._agents: Dict[str, SubAgent] = {}

    # ------------------------------------------------------------------
    # Agenten verwalten
    # ------------------------------------------------------------------

    @property
    def agents(self) -> Dict[str, SubAgent]:
        return dict(self._agents)

    def spawn(
        self,
        name: str,
        role: str,
        system_prompt: str,
        branch: str,
        guardrails: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 2000,
        model_bytes: bytes = b"",
    ) -> SubAgent:
        """
        Einen neuen Sub-Agenten erstellen und registrieren.

        Args:
            name: Eindeutiger Agenten-Name.
            role: Beschreibung der Rolle (für Bewertungs-Heuristik).
            system_prompt: System-Prompt des Agenten.
            branch: Branch im lokalen Store des Agenten.
            guardrails: Optionale Guardrail-Regeln.
            temperature: Temperatur-Parameter.
            top_p: Top-P-Parameter.
            max_tokens: Max-Tokens-Parameter.
            model_bytes: Optionale Modell-Bytes für MIVP-Hash.

        Returns:
            Der erstellte SubAgent.
        """
        if name in self._agents:
            raise ValueError(f"Agent '{name}' ist bereits registriert.")

        config = SubAgentConfig(
            name=name,
            role=role,
            system_prompt=system_prompt,
            branch=branch,
            guardrails=guardrails or [],
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            model_bytes=model_bytes,
        )
        agent = SubAgent(config, self.shared_store)
        self._agents[name] = agent
        logger.info("Sub-Agent '%s' gespawnt (Branch: %s)", name, branch)
        return agent

    def despawn(self, name: str) -> bool:
        """Einen Sub-Agenten entfernen. Gibt True zurück wenn er existierte."""
        existed = name in self._agents
        self._agents.pop(name, None)
        return existed

    # ------------------------------------------------------------------
    # Koordination
    # ------------------------------------------------------------------

    def coordinate(
        self,
        claim_text: str,
        category: str = "EMPIRICAL",
        require_consensus: bool = False,
    ) -> ConsensusResult:
        """
        Claim durch alle registrierten Sub-Agenten bewerten und Konsens bilden.

        Args:
            claim_text: Der zu bewertende Claim-Text.
            category: Epistemische Kategorie.
            require_consensus: Wenn True und kein Konsens erreicht,
                               wird ein SPECULATIVE-Patch angelegt.

        Returns:
            ConsensusResult mit allen Einzelbewertungen und Konsens.
        """
        if not self._agents:
            raise RuntimeError("Keine Sub-Agenten registriert. Erst spawn() aufrufen.")

        # Alle Agenten bewerten
        evaluations: List[EvaluationResult] = []
        for agent in self._agents.values():
            try:
                ev = agent.evaluate(claim_text, category=category)
                evaluations.append(ev)
            except Exception as exc:
                logger.error("Agent '%s' Bewertungsfehler: %s", agent.config.name, exc)

        if not evaluations:
            raise RuntimeError("Keine Bewertungen erhalten.")

        # Konsens berechnen
        consensus_verdict, agreement_ratio, avg_confidence = self._compute_consensus(evaluations)

        # Falls kein Konsens → Kategorie auf SPECULATIVE setzen
        consensus_category = category
        if require_consensus and consensus_verdict == "inconclusive":
            consensus_category = "SPECULATIVE"

        # Konsens-Patch im Shared Store ablegen
        ts = int(time.time())
        uid = abs(hash(claim_text + str(ts)))
        agent_summaries = [
            f"{ev.agent_name}: {ev.verdict} ({ev.reasoning[:60]})"
            for ev in evaluations
        ]
        consensus_patch = Patch(
            patch_id=f"consensus_{uid}",
            parent_patch_id=self.shared_store.get_last_patch_id("consensus"),
            branch_id="consensus",
            timestamp=ts,
            operation="ADD",
            target_id=f"consensus_{uid}",
            category=consensus_category,
            payload={
                "content": claim_text,
                "consensus_verdict": consensus_verdict,
                "agreement_ratio": agreement_ratio,
                "agent_evaluations": agent_summaries,
                "source": "multi_agent_consensus",
            },
            audit={
                "validated": consensus_verdict != "inconclusive",
                "decay": 0.02,
                "created_by": "MultiAgentCoordinator",
                "agent_count": len(evaluations),
            },
            uncertainty={
                "sigma": avg_confidence,
                "ci": [max(0.0, 1 - avg_confidence), 1.0],
                "n": len(evaluations),
            },
        )
        commit_hash = self.shared_store.submit_with_identity(consensus_patch)

        return ConsensusResult(
            claim_text=claim_text,
            evaluations=evaluations,
            consensus_verdict=consensus_verdict,
            confidence=avg_confidence,
            agreement_ratio=agreement_ratio,
            commit_hash=commit_hash,
            details="; ".join(agent_summaries),
        )

    def verify_all_identities(self) -> Dict[str, bool]:
        """Alle Sub-Agenten-Identitäten prüfen. Gibt {name: ok} zurück."""
        return {name: agent.verify_identity() for name, agent in self._agents.items()}

    def status(self) -> Dict[str, Any]:
        """Übersicht über alle Sub-Agenten."""
        return {
            "coordinator": self._identity.name,
            "agent_count": len(self._agents),
            "agents": [
                {
                    "name": name,
                    "role": agent.config.role,
                    "branch": agent.config.branch,
                    "claims": len(agent.store.reconstruct(agent.config.branch)),
                    "identity_ok": agent.verify_identity(),
                }
                for name, agent in self._agents.items()
            ],
            "consensus_claims": len(self.shared_store.reconstruct("consensus")),
        }

    # ------------------------------------------------------------------
    # Konsens-Berechnung
    # ------------------------------------------------------------------

    def _compute_consensus(
        self, evaluations: List[EvaluationResult]
    ):
        """Konsens-Verdict aus Einzelbewertungen berechnen."""
        verdicts = [ev.verdict for ev in evaluations]
        supports = verdicts.count("supports")
        challenges = verdicts.count("challenges")
        total = len(verdicts)

        avg_confidence = sum(ev.confidence for ev in evaluations) / total

        if total == 0:
            return "inconclusive", 0.0, 0.5

        if supports / total >= 0.6:
            return "supported", supports / total, avg_confidence
        elif challenges / total >= 0.6:
            return "challenged", challenges / total, avg_confidence
        else:
            return "inconclusive", max(supports, challenges) / total, avg_confidence
