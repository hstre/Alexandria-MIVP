"""
Uncertainty Propagation over Epistemic Claim Graphs.

Models how uncertainty flows through a directed dependency graph of Node
objects.  When node A explicitly depends on node B, the combined uncertainty
of A must account for the uncertainty already embedded in B.

Usage
-----
::

    from uncertainty_propagator import UncertaintyPropagator, PropagationMode

    propagator = UncertaintyPropagator(store.nodes)
    propagator.build_from_patches(store.branches["main"])
    report = propagator.propagate(mode=PropagationMode.SUM_IN_QUADRATURE)

    result = report.results["my_claim"]
    print(result.combined_sigma)   # total uncertainty including propagated

Dependency declaration
----------------------
Dependencies are expressed in patch payloads via the ``depends_on`` field::

    payload = {
        "content": "...",
        "assumptions": ["..."],
        "depends_on": ["node_id_a", "node_id_b"],
    }

They can also be registered programmatically with
``UncertaintyPropagator.register_dependency()``.

Propagation modes
-----------------
* ``SUM_IN_QUADRATURE`` – σ = √(Σ σᵢ²)  – for independent sources.
* ``WEIGHTED_MEAN``     – σ = 1/√(Σ 1/σᵢ²) – inverse-variance weighting.
* ``MAX``               – σ = max(σᵢ) – conservative upper bound.
* ``MEAN``              – σ = mean(σᵢ) – simple average.
* ``LINEAR``            – σ = Σ σᵢ – for additive quantities.

In every mode the final ``combined_sigma`` is computed as::

    combined_sigma = √(local_sigma² + propagated_sigma²)

so that the node's own measurement uncertainty is never lost.
"""

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .alexandria_v2 import Node, Patch


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------

class PropagationMode(str, Enum):
    SUM_IN_QUADRATURE = "sum_in_quadrature"
    WEIGHTED_MEAN = "weighted_mean"
    MAX = "max"
    MEAN = "mean"
    LINEAR = "linear"


@dataclass
class PropagationResult:
    """Uncertainty information for a single node after propagation."""
    node_id: str
    local_sigma: float                        # σ from this node's own Uncertainty
    propagated_sigma: float                   # σ contributed by dependency chain
    combined_sigma: float                     # √(local² + propagated²)
    depth: int                                # max dependency chain depth (0 = leaf)
    contributing_nodes: List[str] = field(default_factory=list)
    ci: Optional[Tuple[float, float]] = None  # original CI if provided
    n: Optional[int] = None                   # original sample count


@dataclass
class PropagationReport:
    """Full result of a single propagation run."""
    results: Dict[str, PropagationResult]
    mode: PropagationMode
    decay_factor: float
    nodes_processed: int
    nodes_skipped_cycle: List[str] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Combination rules
# ---------------------------------------------------------------------------

def _combine_sigmas(sigmas: List[float], mode: PropagationMode) -> float:
    """Combine a list of sigma values using the chosen mode."""
    if not sigmas:
        return 0.0
    positive = [s for s in sigmas if s > 0.0]
    if not positive:
        return 0.0

    if mode == PropagationMode.SUM_IN_QUADRATURE:
        return math.sqrt(sum(s * s for s in positive))

    if mode == PropagationMode.WEIGHTED_MEAN:
        # Inverse-variance weighting: σ_combined = 1/√(Σ 1/σᵢ²)
        inv_var_sum = sum(1.0 / (s * s) for s in positive)
        return 1.0 / math.sqrt(inv_var_sum)

    if mode == PropagationMode.MAX:
        return max(positive)

    if mode == PropagationMode.MEAN:
        return sum(positive) / len(positive)

    if mode == PropagationMode.LINEAR:
        return sum(positive)

    raise ValueError(f"Unknown propagation mode: {mode}")


def _quadrature(a: float, b: float) -> float:
    """Combine two independent uncertainties in quadrature."""
    return math.sqrt(a * a + b * b)


# ---------------------------------------------------------------------------
# Cycle detection helpers
# ---------------------------------------------------------------------------

def _find_cycles(deps: Dict[str, Set[str]]) -> List[List[str]]:
    """Find all simple cycles using iterative DFS (Johnson-style walk)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = defaultdict(int)
    cycles: List[List[str]] = []
    path: List[str] = []

    def dfs(node: str):
        color[node] = GRAY
        path.append(node)
        for dep in deps.get(node, set()):
            if color[dep] == GRAY:
                # Found cycle – extract from path
                idx = path.index(dep)
                cycles.append(path[idx:] + [dep])
            elif color[dep] == WHITE:
                dfs(dep)
        path.pop()
        color[node] = BLACK

    for node in list(deps.keys()):
        if color[node] == WHITE:
            dfs(node)
    return cycles


# ---------------------------------------------------------------------------
# Main propagator class
# ---------------------------------------------------------------------------

class UncertaintyPropagator:
    """
    Propagates uncertainty from dependency nodes to dependent nodes across
    the claim graph.

    Parameters
    ----------
    nodes:
        Dict of node_id → Node objects.  Typically obtained from
        ``AlexandriaStore.reconstruct(branch_id)``.
    """

    def __init__(self, nodes: Dict[str, Node]):
        self.nodes: Dict[str, Node] = dict(nodes)
        # node_id → list of dependency node_ids (what this node directly depends on)
        self._raw_deps: Dict[str, List[str]] = defaultdict(list)

    # ------------------------------------------------------------------ #
    # Dependency registration                                              #
    # ------------------------------------------------------------------ #

    def register_dependency(self, dependent_id: str, dependency_id: str) -> None:
        """
        Explicitly register that *dependent_id* depends on *dependency_id*.

        Idempotent: registering the same pair twice has no effect.
        """
        if dependency_id not in self._raw_deps[dependent_id]:
            self._raw_deps[dependent_id].append(dependency_id)

    def build_from_patches(self, patches: List[Patch]) -> int:
        """
        Extract dependencies from patch payloads (``payload["depends_on"]``).

        The ``depends_on`` field should be a list of node IDs::

            payload = {"content": "...", "depends_on": ["node_a", "node_b"]}

        Returns the number of dependency edges registered.
        """
        count = 0
        for patch in patches:
            if patch.operation not in ("ADD", "MODIFY"):
                continue
            dep_field = patch.payload.get("depends_on", [])
            if not isinstance(dep_field, list):
                continue
            for dep_id in dep_field:
                if isinstance(dep_id, str) and dep_id:
                    self.register_dependency(patch.target_id, dep_id)
                    count += 1
        return count

    def get_dependencies(self, node_id: str) -> List[str]:
        """Return the direct dependencies of *node_id*."""
        return list(self._raw_deps.get(node_id, []))

    def get_dependents(self, node_id: str) -> List[str]:
        """Return all nodes that directly depend on *node_id*."""
        return [nid for nid, deps in self._raw_deps.items() if node_id in deps]

    # ------------------------------------------------------------------ #
    # Graph analysis                                                       #
    # ------------------------------------------------------------------ #

    def detect_cycles(self) -> List[List[str]]:
        """Return a list of cycles found in the dependency graph."""
        all_ids = set(self.nodes.keys())
        deps: Dict[str, Set[str]] = {
            nid: {d for d in self._raw_deps.get(nid, []) if d in all_ids}
            for nid in all_ids
        }
        return _find_cycles(deps)

    def dependency_depth(self, node_id: str) -> int:
        """
        Return the maximum depth of *node_id* in the dependency graph.
        Returns 0 for leaf nodes (no dependencies).
        """
        visited: Set[str] = set()

        def _depth(nid: str) -> int:
            if nid in visited:
                return 0  # cycle guard
            visited.add(nid)
            deps = [d for d in self._raw_deps.get(nid, []) if d in self.nodes]
            if not deps:
                return 0
            return 1 + max(_depth(d) for d in deps)

        return _depth(node_id)

    # ------------------------------------------------------------------ #
    # Topological sort (Kahn's algorithm)                                  #
    # ------------------------------------------------------------------ #

    def _topological_order(
        self,
        all_ids: Set[str],
    ) -> Tuple[List[str], Set[str]]:
        """
        Compute a valid processing order (leaves first, dependents last).

        Returns (ordered_list, cyclic_nodes) where cyclic_nodes are excluded
        from the ordered list because they participate in a cycle.
        """
        # deps restricted to known nodes
        deps: Dict[str, Set[str]] = {
            nid: {d for d in self._raw_deps.get(nid, []) if d in all_ids}
            for nid in all_ids
        }
        # reverse: dependency → set of dependents
        rev: Dict[str, Set[str]] = defaultdict(set)
        for nid, d_set in deps.items():
            for d in d_set:
                rev[d].add(nid)

        in_degree: Dict[str, int] = {nid: len(d_set) for nid, d_set in deps.items()}
        queue: deque = deque(nid for nid, deg in in_degree.items() if deg == 0)
        order: List[str] = []

        while queue:
            nid = queue.popleft()
            order.append(nid)
            for dependent in rev.get(nid, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Nodes not in order are part of cycles
        cyclic = all_ids - set(order)
        return order, cyclic

    # ------------------------------------------------------------------ #
    # Propagation                                                          #
    # ------------------------------------------------------------------ #

    def propagate(
        self,
        mode: PropagationMode = PropagationMode.SUM_IN_QUADRATURE,
        decay: float = 1.0,
    ) -> PropagationReport:
        """
        Propagate uncertainty through the dependency graph.

        Parameters
        ----------
        mode:
            How to combine multiple dependency uncertainties.
        decay:
            Multiplicative factor applied per dependency hop (0 < decay ≤ 1).
            Values below 1 reduce the contribution of distant sources.
            Default 1.0 means no decay.

        Returns
        -------
        PropagationReport
            Contains per-node results plus metadata (cycles, mode, etc.).
        """
        if not (0.0 < decay <= 1.0):
            raise ValueError(f"decay must be in (0, 1]: got {decay}")

        all_ids = set(self.nodes.keys())
        order, cyclic_ids = self._topological_order(all_ids)
        cycles = _find_cycles({
            nid: {d for d in self._raw_deps.get(nid, []) if d in all_ids}
            for nid in cyclic_ids
        })

        # results accumulates as we process in topological order
        results: Dict[str, PropagationResult] = {}

        for nid in order:
            node = self.nodes[nid]
            local_sigma = node.uncertainty.sigma if node.uncertainty else 0.0
            ci = node.uncertainty.ci if node.uncertainty else None
            n_samples = node.uncertainty.n if node.uncertainty else None

            # Gather direct dependencies (only those already processed)
            direct_deps = [
                d for d in self._raw_deps.get(nid, [])
                if d in all_ids and d in results
            ]

            if not direct_deps:
                results[nid] = PropagationResult(
                    node_id=nid,
                    local_sigma=local_sigma,
                    propagated_sigma=0.0,
                    combined_sigma=local_sigma,
                    depth=0,
                    contributing_nodes=[],
                    ci=ci,
                    n=n_samples,
                )
                continue

            # Collect dependency combined sigmas (with decay per level)
            dep_sigmas: List[float] = []
            contributing: List[str] = []
            max_dep_depth = 0

            for dep_id in direct_deps:
                dep_result = results[dep_id]
                # Apply decay: uncertainty from dep is scaled by decay
                effective_sigma = dep_result.combined_sigma * (decay ** (dep_result.depth + 1))
                dep_sigmas.append(effective_sigma)
                contributing.append(dep_id)
                contributing.extend(dep_result.contributing_nodes)
                max_dep_depth = max(max_dep_depth, dep_result.depth + 1)

            # Remove duplicates in contributing while preserving order
            seen: Set[str] = set()
            unique_contributing: List[str] = []
            for c in contributing:
                if c not in seen:
                    seen.add(c)
                    unique_contributing.append(c)

            propagated_sigma = _combine_sigmas(dep_sigmas, mode)
            combined_sigma = _quadrature(local_sigma, propagated_sigma)

            results[nid] = PropagationResult(
                node_id=nid,
                local_sigma=local_sigma,
                propagated_sigma=propagated_sigma,
                combined_sigma=combined_sigma,
                depth=max_dep_depth,
                contributing_nodes=unique_contributing,
                ci=ci,
                n=n_samples,
            )

        # Nodes in cycles get a special entry (cannot be properly propagated)
        for nid in cyclic_ids:
            node = self.nodes[nid]
            local_sigma = node.uncertainty.sigma if node.uncertainty else 0.0
            results[nid] = PropagationResult(
                node_id=nid,
                local_sigma=local_sigma,
                propagated_sigma=float("inf"),  # undefined due to cycle
                combined_sigma=float("inf"),
                depth=-1,  # sentinel: in cycle
                contributing_nodes=[],
                ci=node.uncertainty.ci if node.uncertainty else None,
                n=node.uncertainty.n if node.uncertainty else None,
            )

        return PropagationReport(
            results=results,
            mode=mode,
            decay_factor=decay,
            nodes_processed=len(order),
            nodes_skipped_cycle=list(cyclic_ids),
            cycles=cycles,
        )

    # ------------------------------------------------------------------ #
    # Convenience queries                                                  #
    # ------------------------------------------------------------------ #

    def most_uncertain_nodes(
        self,
        report: PropagationReport,
        top_n: int = 10,
        include_cyclic: bool = False,
    ) -> List[PropagationResult]:
        """Return the *top_n* nodes with highest combined_sigma."""
        results = list(report.results.values())
        if not include_cyclic:
            results = [r for r in results if r.depth >= 0]
        results.sort(key=lambda r: r.combined_sigma, reverse=True)
        return results[:top_n]

    def uncertainty_summary(self, report: PropagationReport) -> Dict[str, object]:
        """Return a summary dict suitable for logging or display."""
        valid = [r for r in report.results.values() if r.depth >= 0]
        if not valid:
            return {"node_count": 0}

        sigmas = [r.combined_sigma for r in valid]
        return {
            "mode": report.mode.value,
            "decay_factor": report.decay_factor,
            "node_count": len(valid),
            "cyclic_node_count": len(report.nodes_skipped_cycle),
            "cycle_count": len(report.cycles),
            "sigma_min": min(sigmas),
            "sigma_max": max(sigmas),
            "sigma_mean": sum(sigmas) / len(sigmas),
            "max_depth": max(r.depth for r in valid),
            "leaf_count": sum(1 for r in valid if r.depth == 0),
        }
