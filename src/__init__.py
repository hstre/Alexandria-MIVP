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
    run_test_vectors
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
    
    # Integration
    "AlexandriaMIVPStore",
    "verify_cih_internal_consistency",
]