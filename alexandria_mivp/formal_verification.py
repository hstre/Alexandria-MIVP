"""
Formal Verification Framework für Alexandria-MIVP.

Bietet ein Framework zur formalen Verifikation epistemischer Eigenschaften
des Alexandria-Protokolls:

* **Invarianten** – strukturelle Bedingungen, die immer gelten müssen
* **Properties** – semantische Eigenschaften über Claims und Branches
* **Proofs**      – Zeugen/Beweise für die Erfüllung von Properties
* **VerificationReport** – Zusammenfassung aller geprüften Properties

Verwendung::

    verifier = EpistemicVerifier(store)
    report = verifier.verify_branch("main")

    for result in report.results:
        print(result.property_name, result.status)

Eigene Properties registrieren::

    @verifier.property("no_empty_content")
    def no_empty(nodes, patches):
        for node in nodes.values():
            if not node.content.strip():
                return PropertyResult.fail("Empty content found")
        return PropertyResult.ok()
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums & Datenklassen
# ---------------------------------------------------------------------------

class VerificationStatus(str, Enum):
    PASSED  = "passed"
    FAILED  = "failed"
    SKIPPED = "skipped"
    ERROR   = "error"


@dataclass
class PropertyResult:
    """Ergebnis der Prüfung einer einzelnen Property."""
    status: VerificationStatus
    message: str = ""
    witnesses: List[str] = field(default_factory=list)   # unterstützende Beweise
    counterexamples: List[str] = field(default_factory=list)  # Gegenbeispiele

    @classmethod
    def ok(cls, message: str = "Property holds.", witnesses: Optional[List[str]] = None) -> "PropertyResult":
        return cls(status=VerificationStatus.PASSED, message=message, witnesses=witnesses or [])

    @classmethod
    def fail(cls, message: str, counterexamples: Optional[List[str]] = None) -> "PropertyResult":
        return cls(status=VerificationStatus.FAILED, message=message, counterexamples=counterexamples or [])

    @classmethod
    def skip(cls, reason: str = "") -> "PropertyResult":
        return cls(status=VerificationStatus.SKIPPED, message=reason)

    @classmethod
    def error(cls, message: str) -> "PropertyResult":
        return cls(status=VerificationStatus.ERROR, message=message)


@dataclass
class VerificationResult:
    """Ergebnis der Prüfung einer benannten Property."""
    property_name: str
    status: VerificationStatus
    message: str
    duration_ms: float
    witnesses: List[str] = field(default_factory=list)
    counterexamples: List[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    """Vollständiger Verifikationsbericht für einen Branch."""
    branch_id: str
    results: List[VerificationResult]
    timestamp: float = field(default_factory=time.time)
    total_duration_ms: float = 0.0

    @property
    def passed(self) -> List[VerificationResult]:
        return [r for r in self.results if r.status == VerificationStatus.PASSED]

    @property
    def failed(self) -> List[VerificationResult]:
        return [r for r in self.results if r.status == VerificationStatus.FAILED]

    @property
    def errors(self) -> List[VerificationResult]:
        return [r for r in self.results if r.status == VerificationStatus.ERROR]

    @property
    def is_fully_verified(self) -> bool:
        return len(self.failed) == 0 and len(self.errors) == 0

    def summary(self) -> Dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "total": len(self.results),
            "passed": len(self.passed),
            "failed": len(self.failed),
            "errors": len(self.errors),
            "skipped": len([r for r in self.results if r.status == VerificationStatus.SKIPPED]),
            "is_fully_verified": self.is_fully_verified,
            "total_duration_ms": self.total_duration_ms,
        }


@dataclass
class Invariant:
    """Eine formale Invariante über das gesamte Alexandria-System."""
    name: str
    description: str
    check_fn: Callable[[Dict[str, Any], List[Any]], PropertyResult]
    critical: bool = True   # Kritische Invarianten müssen immer gelten


@dataclass
class Property:
    """Eine semantische Property über einen Branch-Zustand."""
    name: str
    description: str
    check_fn: Callable[[Dict[str, Any], List[Any]], PropertyResult]
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in Properties & Invarianten
# ---------------------------------------------------------------------------

def _inv_no_dangling_references(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Alle parent_patch_ids müssen auf existierende Patches zeigen."""
    patch_ids = {p.patch_id for p in patches}
    counterexamples = []
    for patch in patches:
        if patch.parent_patch_id and patch.parent_patch_id not in patch_ids:
            counterexamples.append(
                f"Patch '{patch.patch_id}' references non-existent parent '{patch.parent_patch_id}'"
            )
    if counterexamples:
        return PropertyResult.fail("Dangling parent_patch_id references found.", counterexamples)
    return PropertyResult.ok("No dangling references.")


def _inv_monotonic_timestamps(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Timestamps müssen strikt monoton steigen (oder gleich sein)."""
    if len(patches) < 2:
        return PropertyResult.ok("Too few patches to check monotonicity.")
    counterexamples = []
    for i in range(1, len(patches)):
        if patches[i].timestamp < patches[i - 1].timestamp:
            counterexamples.append(
                f"Patch '{patches[i].patch_id}' (ts={patches[i].timestamp}) < "
                f"'{patches[i-1].patch_id}' (ts={patches[i-1].timestamp})"
            )
    if counterexamples:
        return PropertyResult.fail("Non-monotonic timestamps detected.", counterexamples)
    return PropertyResult.ok("Timestamps are monotonically non-decreasing.")


def _inv_valid_operations(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Alle Patch-Operationen müssen gültig sein."""
    valid_ops = {"ADD", "MODIFY", "DEPRECATE"}
    counterexamples = []
    for patch in patches:
        if patch.operation not in valid_ops:
            counterexamples.append(
                f"Patch '{patch.patch_id}' has invalid operation '{patch.operation}'"
            )
    if counterexamples:
        return PropertyResult.fail("Invalid patch operations found.", counterexamples)
    return PropertyResult.ok("All operations are valid.")


def _inv_valid_categories(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Alle Patch-Kategorien müssen gültig sein."""
    valid_cats = {"EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"}
    counterexamples = []
    for patch in patches:
        if patch.category not in valid_cats:
            counterexamples.append(
                f"Patch '{patch.patch_id}' has invalid category '{patch.category}'"
            )
    if counterexamples:
        return PropertyResult.fail("Invalid patch categories found.", counterexamples)
    return PropertyResult.ok("All categories are valid.")


def _prop_no_deprecated_active(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Keine DEPRECATE-Patches sollten auf aktive Nodes zeigen ohne vorheriges ADD."""
    add_targets = {p.target_id for p in patches if p.operation == "ADD"}
    dep_targets = {p.target_id for p in patches if p.operation == "DEPRECATE"}
    never_added = dep_targets - add_targets
    if never_added:
        return PropertyResult.fail(
            "DEPRECATE patches reference targets that were never ADDed.",
            list(never_added),
        )
    return PropertyResult.ok("All deprecated targets were previously added.")


def _prop_sigma_in_range(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Sigma-Werte müssen im Bereich [0, 1] liegen."""
    counterexamples = []
    for node_id, node in nodes.items():
        if node.uncertainty and not (0.0 <= node.uncertainty.sigma <= 1.0):
            counterexamples.append(
                f"Node '{node_id}' has sigma={node.uncertainty.sigma} outside [0,1]"
            )
    if counterexamples:
        return PropertyResult.fail("Sigma values out of range [0,1].", counterexamples)
    return PropertyResult.ok("All sigma values are in [0,1].")


def _prop_content_not_empty(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Kein aktiver Node sollte leeren Content haben."""
    counterexamples = []
    for node_id, node in nodes.items():
        content = getattr(node, "content", None)
        if content is not None and not str(content).strip():
            counterexamples.append(f"Node '{node_id}' has empty content.")
    if counterexamples:
        return PropertyResult.fail("Nodes with empty content found.", counterexamples)
    return PropertyResult.ok("All nodes have non-empty content.")


def _prop_unique_patch_ids(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Patch-IDs müssen innerhalb eines Branches eindeutig sein."""
    seen: Dict[str, int] = {}
    counterexamples = []
    for i, patch in enumerate(patches):
        if patch.patch_id in seen:
            counterexamples.append(
                f"Patch ID '{patch.patch_id}' appears at positions {seen[patch.patch_id]} and {i}"
            )
        else:
            seen[patch.patch_id] = i
    if counterexamples:
        return PropertyResult.fail("Duplicate patch IDs found.", counterexamples)
    return PropertyResult.ok("All patch IDs are unique.")


def _prop_chain_integrity(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Der Patch-Chain (parent_patch_id) muss eine lineare Kette bilden."""
    if not patches:
        return PropertyResult.ok("No patches to verify.")
    # Erster Patch hat parent_patch_id=None
    root_patches = [p for p in patches if p.parent_patch_id is None]
    if len(root_patches) != 1:
        return PropertyResult.fail(
            f"Expected exactly 1 root patch (parent_patch_id=None), found {len(root_patches)}.",
            [p.patch_id for p in root_patches],
        )
    # Kette aufbauen
    patch_map = {p.patch_id: p for p in patches}
    current = root_patches[0]
    visited = set()
    chain = []
    while current is not None:
        if current.patch_id in visited:
            return PropertyResult.fail(
                "Cycle detected in patch chain.",
                [current.patch_id],
            )
        visited.add(current.patch_id)
        chain.append(current.patch_id)
        # Finde Nachfolger (patch mit parent_patch_id == current.patch_id)
        successors = [p for p in patches if p.parent_patch_id == current.patch_id]
        if len(successors) > 1:
            return PropertyResult.fail(
                f"Branching in patch chain at '{current.patch_id}': {len(successors)} successors.",
                [p.patch_id for p in successors],
            )
        current = successors[0] if successors else None

    if len(chain) != len(patches):
        unreachable = set(p.patch_id for p in patches) - set(chain)
        return PropertyResult.fail(
            "Some patches are unreachable from the chain root.",
            list(unreachable),
        )
    return PropertyResult.ok(f"Patch chain is linear with {len(chain)} patches.")


def _prop_assumptions_not_empty(nodes: Dict[str, Any], patches: List[Any]) -> PropertyResult:
    """Nodes mit SPECULATIVE oder MODEL sollten Assumptions haben."""
    counterexamples = []
    for node_id, node in nodes.items():
        category = getattr(node, "category", "EMPIRICAL")
        assumptions = getattr(node, "assumptions", None)
        if category in ("SPECULATIVE", "MODEL"):
            if not assumptions:
                counterexamples.append(
                    f"Node '{node_id}' (category={category}) has no assumptions."
                )
    if counterexamples:
        return PropertyResult.fail(
            "SPECULATIVE/MODEL nodes without assumptions found.", counterexamples
        )
    return PropertyResult.ok("All SPECULATIVE/MODEL nodes have assumptions.")


# ---------------------------------------------------------------------------
# Epistemic Verifier
# ---------------------------------------------------------------------------

_PropertyFn = Callable[[Dict[str, Any], List[Any]], PropertyResult]


class EpistemicVerifier:
    """
    Formaler Verifikator für Alexandria-MIVP-Epistemic-Stores.

    Prüft registrierte Invarianten und Properties gegen einen Branch-Zustand.

    Parameters
    ----------
    store:
        AlexandriaMIVPStore oder AlexandriaStore-kompatibles Objekt.
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self._invariants: List[Invariant] = []
        self._properties: List[Property] = []
        self._register_builtins()

    # ------------------------------------------------------------------ #
    # Registrierung                                                        #
    # ------------------------------------------------------------------ #

    def _register_builtins(self) -> None:
        """Eingebaute Invarianten und Properties registrieren."""
        # Invarianten
        self.add_invariant(
            "no_dangling_references",
            "All parent_patch_id references must point to existing patches.",
            _inv_no_dangling_references,
            critical=True,
        )
        self.add_invariant(
            "monotonic_timestamps",
            "Patch timestamps must be monotonically non-decreasing.",
            _inv_monotonic_timestamps,
            critical=True,
        )
        self.add_invariant(
            "valid_operations",
            "All patch operations must be ADD, MODIFY, or DEPRECATE.",
            _inv_valid_operations,
            critical=True,
        )
        self.add_invariant(
            "valid_categories",
            "All patch categories must be EMPIRICAL, NORMATIVE, MODEL, or SPECULATIVE.",
            _inv_valid_categories,
            critical=True,
        )

        # Properties
        self.add_property(
            "no_deprecated_without_add",
            "DEPRECATE patches must only target previously ADDed nodes.",
            _prop_no_deprecated_active,
            tags=["consistency"],
        )
        self.add_property(
            "sigma_in_range",
            "All node sigma values must be in [0, 1].",
            _prop_sigma_in_range,
            tags=["uncertainty"],
        )
        self.add_property(
            "content_not_empty",
            "All active nodes must have non-empty content.",
            _prop_content_not_empty,
            tags=["completeness"],
        )
        self.add_property(
            "unique_patch_ids",
            "Patch IDs must be unique within a branch.",
            _prop_unique_patch_ids,
            tags=["integrity"],
        )
        self.add_property(
            "chain_integrity",
            "The patch chain must be a linear, acyclic sequence.",
            _prop_chain_integrity,
            tags=["integrity"],
        )
        self.add_property(
            "assumptions_for_speculative",
            "SPECULATIVE and MODEL nodes must have assumptions.",
            _prop_assumptions_not_empty,
            tags=["completeness", "epistemics"],
        )

    def add_invariant(
        self,
        name: str,
        description: str,
        check_fn: _PropertyFn,
        critical: bool = True,
    ) -> None:
        """Eine Invariante registrieren."""
        self._invariants.append(Invariant(
            name=name,
            description=description,
            check_fn=check_fn,
            critical=critical,
        ))

    def add_property(
        self,
        name: str,
        description: str,
        check_fn: _PropertyFn,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Eine Property registrieren."""
        self._properties.append(Property(
            name=name,
            description=description,
            check_fn=check_fn,
            tags=tags or [],
        ))

    def property(self, name: str, tags: Optional[List[str]] = None):
        """Decorator zum Registrieren einer Property."""
        def decorator(fn: _PropertyFn) -> _PropertyFn:
            self.add_property(name, fn.__doc__ or "", fn, tags=tags)
            return fn
        return decorator

    # ------------------------------------------------------------------ #
    # Verifikation                                                         #
    # ------------------------------------------------------------------ #

    def verify_branch(
        self,
        branch_id: str,
        tags: Optional[List[str]] = None,
        skip: Optional[List[str]] = None,
    ) -> VerificationReport:
        """
        Branch vollständig verifizieren.

        Parameters
        ----------
        branch_id:
            Zu verifizierender Branch.
        tags:
            Wenn angegeben: nur Properties mit diesen Tags prüfen.
        skip:
            Liste von Property/Invariant-Namen, die übersprungen werden sollen.

        Returns
        -------
        VerificationReport
        """
        nodes = self._store.reconstruct(branch_id)
        patches = self._store.branches.get(branch_id, [])
        skip_set = set(skip or [])

        results: List[VerificationResult] = []
        t_start = time.monotonic()

        # 1. Invarianten prüfen
        for inv in self._invariants:
            if inv.name in skip_set:
                results.append(VerificationResult(
                    property_name=inv.name,
                    status=VerificationStatus.SKIPPED,
                    message="Skipped by caller.",
                    duration_ms=0.0,
                ))
                continue
            result = self._run_check(inv.name, inv.check_fn, nodes, patches)
            results.append(result)

        # 2. Properties prüfen
        for prop in self._properties:
            if prop.name in skip_set:
                results.append(VerificationResult(
                    property_name=prop.name,
                    status=VerificationStatus.SKIPPED,
                    message="Skipped by caller.",
                    duration_ms=0.0,
                ))
                continue
            if tags is not None and not any(t in prop.tags for t in tags):
                results.append(VerificationResult(
                    property_name=prop.name,
                    status=VerificationStatus.SKIPPED,
                    message=f"Skipped: no matching tag in {tags}.",
                    duration_ms=0.0,
                ))
                continue
            result = self._run_check(prop.name, prop.check_fn, nodes, patches)
            results.append(result)

        total_ms = (time.monotonic() - t_start) * 1000
        return VerificationReport(
            branch_id=branch_id,
            results=results,
            total_duration_ms=total_ms,
        )

    def verify_patch(self, patch: Any, nodes: Dict[str, Any]) -> List[VerificationResult]:
        """
        Einen einzelnen Patch gegen Invarianten prüfen (Schnellcheck).

        Returns:
            Liste von VerificationResults (nur Invarianten).
        """
        patches = [patch]
        results = []
        for inv in self._invariants:
            result = self._run_check(inv.name, inv.check_fn, nodes, patches)
            results.append(result)
        return results

    @staticmethod
    def _run_check(
        name: str,
        check_fn: _PropertyFn,
        nodes: Dict[str, Any],
        patches: List[Any],
    ) -> VerificationResult:
        t0 = time.monotonic()
        try:
            prop_result = check_fn(nodes, patches)
            duration_ms = (time.monotonic() - t0) * 1000
            return VerificationResult(
                property_name=name,
                status=prop_result.status,
                message=prop_result.message,
                duration_ms=duration_ms,
                witnesses=prop_result.witnesses,
                counterexamples=prop_result.counterexamples,
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return VerificationResult(
                property_name=name,
                status=VerificationStatus.ERROR,
                message=f"Check raised exception: {exc}",
                duration_ms=duration_ms,
            )

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #

    def list_properties(self) -> List[Dict[str, Any]]:
        """Alle registrierten Properties und Invarianten auflisten."""
        result = []
        for inv in self._invariants:
            result.append({
                "name": inv.name,
                "type": "invariant",
                "description": inv.description,
                "critical": inv.critical,
                "tags": [],
            })
        for prop in self._properties:
            result.append({
                "name": prop.name,
                "type": "property",
                "description": prop.description,
                "critical": False,
                "tags": prop.tags,
            })
        return result

    def verify_all_branches(
        self,
        skip: Optional[List[str]] = None,
    ) -> Dict[str, VerificationReport]:
        """Alle Branches des Stores verifizieren."""
        reports: Dict[str, VerificationReport] = {}
        for branch_id in self._store.branches:
            reports[branch_id] = self.verify_branch(branch_id, skip=skip)
        return reports
