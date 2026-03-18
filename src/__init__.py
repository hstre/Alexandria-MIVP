"""
Alexandria + MIVP Integration
Epistemic consistency meets cryptographic identity verification for autonomous agents.
"""

from .alexandria_v2 import (
    AlexandriaStore, Patch, Node, Uncertainty,
    CATEGORIES, OPS, AuditError, audit_patch,
    sha256_json, now_unix, clamp01
)

from .mivp_impl import (
    model_hash, policy_hash, canonicalize_policy,
    runtime_hash, canonicalize_runtime, composite_instance_hash,
    leaf_hash, node_hash, merkle_root,
    verify as verify_test_vectors,
    run_test_vectors,
    canonicalize_runtime_environment, runtime_environment_hash,
    canonicalize_runtime_attestation, runtime_attestation_hash,
    runtime_extended_hash,
)

from .alexandria_mivp import (
    AgentIdentity,
    AlexandriaMIVPStore,
    verify_cih_internal_consistency
)

from .sqlite_store import (
    AlexandriaSQLiteStore,
    AlexandriaSQLiteMIVPStore,
    migrate_memory_to_sqlite
)

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

from .audit_gate import (
    AuditGate,
    AuditGateConfig,
    AuditReport,
    AuditViolation,
    Severity,
    make_default_gate,
    make_strict_empirical_gate,
)

from .uncertainty_propagator import (
    UncertaintyPropagator,
    PropagationMode,
    PropagationResult,
    PropagationReport,
)

from .cross_agent_graph import (
    CrossAgentGraph,
    ClaimNode,
    GraphEdge,
    EdgeType,
    GraphQueryResult,
    AgentContribution,
    EpistemicConflict,
)

from .performance import (
    NodeCache,
    QueryCache,
    BatchProcessor,
    BatchResult,
    BatchReport,
    PerformanceMonitor,
)

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

from .formal_verification import (
    EpistemicVerifier,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
    PropertyResult,
    Invariant,
    Property,
)

__version__ = "0.1.0"
__all__ = [
    # Alexandria Protocol
    "AlexandriaStore", "Patch", "Node", "Uncertainty",
    "CATEGORIES", "OPS", "AuditError", "audit_patch",
    "sha256_json", "now_unix", "clamp01",
    
    # MIVP
    "AgentIdentity",
    "model_hash", "policy_hash", "canonicalize_policy",
    "runtime_hash", "canonicalize_runtime", "composite_instance_hash",
    "leaf_hash", "node_hash", "merkle_root",
    "verify_test_vectors", "run_test_vectors",
    # Extended Runtime Hash
    "canonicalize_runtime_environment", "runtime_environment_hash",
    "canonicalize_runtime_attestation", "runtime_attestation_hash",
    "runtime_extended_hash",
    
    # Integration
    "AlexandriaMIVPStore",
    "verify_cih_internal_consistency",

    # External Anchor
    "BaseExternalAnchor",
    "SimulatedAnchor",
    "OpenTimestampsAnchor",
    "WebhookAnchor",
    "MultiAnchor",
    "AnchorError",
    "AnchorProof",
    "ExternalAnchor",

    # Moltbook
    "MoltbookIntegration",
    "MoltbookAPIError",

    # Heartbeat
    "EpistemicHeartbeat",
    "HeartbeatReport",
    "run_heartbeat_check",

    # Message Router
    "MessageRouter",
    "RouteResult",
    "MiddlewareContext",

    # Sub-Agent / Multi-Agent
    "SubAgent",
    "SubAgentConfig",
    "MultiAgentCoordinator",
    "EvaluationResult",
    "ConsensusResult",

    # Extended Audit Gate
    "AuditGate",
    "AuditGateConfig",
    "AuditReport",
    "AuditViolation",
    "Severity",
    "make_default_gate",
    "make_strict_empirical_gate",

    # Uncertainty Propagation
    "UncertaintyPropagator",
    "PropagationMode",
    "PropagationResult",
    "PropagationReport",

    # Cross-Agent Epistemic Graphs
    "CrossAgentGraph",
    "ClaimNode",
    "GraphEdge",
    "EdgeType",
    "GraphQueryResult",
    "AgentContribution",
    "EpistemicConflict",

    # Performance
    "NodeCache",
    "QueryCache",
    "BatchProcessor",
    "BatchResult",
    "BatchReport",
    "PerformanceMonitor",

    # Distributed Storage
    "DistributedBackend",
    "InMemoryBackend",
    "S3Backend",
    "IPFSBackend",
    "DistributedLedgerBackend",
    "MultiBackend",
    "DistributedAlexandriaStore",
    "StoredObject",
    "BackendHealth",
    "StorageError",
    "LedgerEntry",

    # Formal Verification
    "EpistemicVerifier",
    "VerificationReport",
    "VerificationResult",
    "VerificationStatus",
    "PropertyResult",
    "Invariant",
    "Property",
]