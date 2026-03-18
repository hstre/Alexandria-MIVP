"""
Alexandria + MIVP Integration
Epistemic consistency meets cryptographic identity verification for autonomous agents.

Package layout
--------------
Core (always available, no optional dependencies):
    Alexandria Protocol     – AlexandriaStore, Patch, Node, Uncertainty, …
    MIVP v2.1               – AgentIdentity, model_hash, policy_hash, …
    SQLite Store            – AlexandriaSQLiteStore, AlexandriaSQLiteMIVPStore
    Audit Gate              – AuditGate, AuditGateConfig, AuditReport, …
    Uncertainty Propagation – UncertaintyPropagator, PropagationMode, …
    Cross-Agent Graphs      – CrossAgentGraph, EdgeType, ClaimNode, …
    Formal Verification     – EpistemicVerifier, VerificationReport, …
    Performance             – NodeCache, QueryCache, BatchProcessor, …

Extensions (may require optional dependencies):
    External Anchor         – SimulatedAnchor, OpenTimestampsAnchor, …  (no deps)
    Heartbeat               – EpistemicHeartbeat  (no deps)
    Message Router          – MessageRouter  (no deps)
    Sub-Agent               – SubAgent, MultiAgentCoordinator  (no deps)
    Moltbook Integration    – MoltbookIntegration  (no deps for mock)
    Distributed Storage     – InMemoryBackend, S3Backend [boto3], IPFSBackend [requests], …

Quick start:
    from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity, Patch
"""

# ---------------------------------------------------------------------------
# Core: Alexandria Protocol
# ---------------------------------------------------------------------------
from .alexandria_v2 import (
    AlexandriaStore,
    Patch,
    Node,
    Uncertainty,
    CATEGORIES,
    OPS,
    AuditError,
    audit_patch,
    sha256_json,
    now_unix,
    clamp01,
)

# ---------------------------------------------------------------------------
# Core: MIVP v2.1
# ---------------------------------------------------------------------------
from .mivp_impl import (
    model_hash,
    policy_hash,
    canonicalize_policy,
    runtime_hash,
    canonicalize_runtime,
    composite_instance_hash,
    leaf_hash,
    node_hash,
    merkle_root,
    verify as verify_test_vectors,
    run_test_vectors,
    # Extended Runtime Hash
    canonicalize_runtime_environment,
    runtime_environment_hash,
    canonicalize_runtime_attestation,
    runtime_attestation_hash,
    runtime_extended_hash,
)

# ---------------------------------------------------------------------------
# Core: Integrated Alexandria+MIVP Store
# ---------------------------------------------------------------------------
from .alexandria_mivp import (
    AgentIdentity,
    AlexandriaMIVPStore,
    verify_cih_internal_consistency,
)

# ---------------------------------------------------------------------------
# Core: SQLite Persistence
# ---------------------------------------------------------------------------
from .sqlite_store import (
    AlexandriaSQLiteStore,
    AlexandriaSQLiteMIVPStore,
    migrate_memory_to_sqlite,
)

# ---------------------------------------------------------------------------
# Core: Audit Gate
# ---------------------------------------------------------------------------
from .audit_gate import (
    AuditGate,
    AuditGateConfig,
    AuditReport,
    AuditViolation,
    Severity,
    make_default_gate,
    make_strict_empirical_gate,
)

# ---------------------------------------------------------------------------
# Core: Uncertainty Propagation
# ---------------------------------------------------------------------------
from .uncertainty_propagator import (
    UncertaintyPropagator,
    PropagationMode,
    PropagationResult,
    PropagationReport,
)

# ---------------------------------------------------------------------------
# Core: Cross-Agent Epistemic Graphs
# ---------------------------------------------------------------------------
from .cross_agent_graph import (
    CrossAgentGraph,
    ClaimNode,
    GraphEdge,
    EdgeType,
    GraphQueryResult,
    AgentContribution,
    EpistemicConflict,
)

# ---------------------------------------------------------------------------
# Core: Performance
# ---------------------------------------------------------------------------
from .performance import (
    NodeCache,
    QueryCache,
    BatchProcessor,
    BatchResult,
    BatchReport,
    PerformanceMonitor,
)

# ---------------------------------------------------------------------------
# Core: Formal Verification
# ---------------------------------------------------------------------------
from .formal_verification import (
    EpistemicVerifier,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
    PropertyResult,
    Invariant,
    Property,
)

# ---------------------------------------------------------------------------
# Extensions: External Anchor, Heartbeat, Message Router, Sub-Agent, Moltbook
# ---------------------------------------------------------------------------
from .external_anchor import (
    BaseExternalAnchor,
    SimulatedAnchor,
    OpenTimestampsAnchor,
    WebhookAnchor,
    MultiAnchor,
    AnchorError,
    AnchorProof,
    ExternalAnchor,
)

from .moltbook_integration import (
    MoltbookIntegration,
    MoltbookAPIError,
)

from .heartbeat import (
    EpistemicHeartbeat,
    HeartbeatReport,
    run_heartbeat_check,
)

from .message_router import (
    MessageRouter,
    RouteResult,
    MiddlewareContext,
)

from .sub_agent import (
    SubAgent,
    SubAgentConfig,
    MultiAgentCoordinator,
    EvaluationResult,
    ConsensusResult,
)

# ---------------------------------------------------------------------------
# Extensions: Distributed Storage (optional deps: boto3, requests)
# ---------------------------------------------------------------------------
from .distributed_store import (
    DistributedBackend,
    InMemoryBackend,
    S3Backend,
    IPFSBackend,
    DistributedLedgerBackend,
    MultiBackend,
    DistributedAlexandriaStore,
    StoredObject,
    BackendHealth,
    StorageError,
    LedgerEntry,
)

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
__version__ = "0.1.0"

__all__ = [
    # ── Core: Alexandria Protocol ──────────────────────────────────────────
    "AlexandriaStore", "Patch", "Node", "Uncertainty",
    "CATEGORIES", "OPS", "AuditError", "audit_patch",
    "sha256_json", "now_unix", "clamp01",

    # ── Core: MIVP v2.1 ───────────────────────────────────────────────────
    "model_hash", "policy_hash", "canonicalize_policy",
    "runtime_hash", "canonicalize_runtime", "composite_instance_hash",
    "leaf_hash", "node_hash", "merkle_root",
    "verify_test_vectors", "run_test_vectors",
    "canonicalize_runtime_environment", "runtime_environment_hash",
    "canonicalize_runtime_attestation", "runtime_attestation_hash",
    "runtime_extended_hash",

    # ── Core: Integrated Store ─────────────────────────────────────────────
    "AgentIdentity", "AlexandriaMIVPStore", "verify_cih_internal_consistency",

    # ── Core: SQLite ───────────────────────────────────────────────────────
    "AlexandriaSQLiteStore", "AlexandriaSQLiteMIVPStore", "migrate_memory_to_sqlite",

    # ── Core: Audit Gate ───────────────────────────────────────────────────
    "AuditGate", "AuditGateConfig", "AuditReport", "AuditViolation",
    "Severity", "make_default_gate", "make_strict_empirical_gate",

    # ── Core: Uncertainty Propagation ──────────────────────────────────────
    "UncertaintyPropagator", "PropagationMode", "PropagationResult", "PropagationReport",

    # ── Core: Cross-Agent Graphs ───────────────────────────────────────────
    "CrossAgentGraph", "ClaimNode", "GraphEdge", "EdgeType",
    "GraphQueryResult", "AgentContribution", "EpistemicConflict",

    # ── Core: Performance ──────────────────────────────────────────────────
    "NodeCache", "QueryCache", "BatchProcessor", "BatchResult",
    "BatchReport", "PerformanceMonitor",

    # ── Core: Formal Verification ──────────────────────────────────────────
    "EpistemicVerifier", "VerificationReport", "VerificationResult",
    "VerificationStatus", "PropertyResult", "Invariant", "Property",

    # ── Extensions: Anchor / Heartbeat / Router / Sub-Agent / Moltbook ─────
    "BaseExternalAnchor", "SimulatedAnchor", "OpenTimestampsAnchor",
    "WebhookAnchor", "MultiAnchor", "AnchorError", "AnchorProof", "ExternalAnchor",
    "MoltbookIntegration", "MoltbookAPIError",
    "EpistemicHeartbeat", "HeartbeatReport", "run_heartbeat_check",
    "MessageRouter", "RouteResult", "MiddlewareContext",
    "SubAgent", "SubAgentConfig", "MultiAgentCoordinator",
    "EvaluationResult", "ConsensusResult",

    # ── Extensions: Distributed Storage ───────────────────────────────────
    "DistributedBackend", "InMemoryBackend", "S3Backend", "IPFSBackend",
    "DistributedLedgerBackend", "MultiBackend", "DistributedAlexandriaStore",
    "StoredObject", "BackendHealth", "StorageError", "LedgerEntry",
]
