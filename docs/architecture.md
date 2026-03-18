# Architecture Overview

## Core Principles

### 1. Separation of Concerns
- **MIVP** handles *identity verification* (which system produced a claim)
- **Alexandria** handles *epistemic structure* (the integrity of the claim itself)
- **Integration** provides end-to-end verifiability

### 2. Immutability & Append-Only
- All patches are immutable once submitted
- State evolves through append-only patch sequences
- Hash chains enable tamper detection

### 3. Deterministic Verification
- MIVP hashes are byte-identical across compliant implementations
- Same inputs → same cryptographic outputs
- Enables trust without central authority

## Component Architecture

### Alexandria Protocol Layer
```
┌─────────────────────────────────────────────────┐
│                 Alexandria Store                │
├─────────────────────────────────────────────────┤
│ • Multiple branches                             │
│ • Append-only patch chains                      │
│ • Hash-chain anchoring                          │
│ • Derived state (graph of nodes)                │
└─────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────┐
│                 Patch DSL                        │
├─────────────────────────────────────────────────┤
│ • ADD     - Create new epistemic node           │
│ • MODIFY  - Update existing node                │
│ • DEPRECATE - Mark node as deprecated           │
│ • BRANCH  - Create alternative interpretation   │
└─────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────┐
│                 Epistemic Nodes                 │
├─────────────────────────────────────────────────┤
│ • EMPIRICAL   - Observable, falsifiable facts   │
│ • NORMATIVE   - Value judgments, prescriptions  │
│ • MODEL       - Model assumptions, simplifications│
│ • SPECULATIVE - Unverified, exploratory claims  │
└─────────────────────────────────────────────────┘
```

### MIVP Identity Layer
```
┌─────────────────────────────────────────────────┐
│           Composite Instance Hash (CIH)         │
│     SHA256(MH || PH || RH [|| instance_epoch])  │
└─────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
┌────────▼──────┐ ┌──────▼──────┐ ┌───────▼──────┐
│  Model Hash   │ │ Policy Hash │ │ Runtime Hash │
│    (MH)       │ │    (PH)     │ │    (RH)      │
├───────────────┤ ├──────────────┤ ├──────────────┤
│ • Merkle tree │ │ • Canonical  │ │ • CFS-1     │
│ • Carry-up    │ │   JSON       │ │   floats    │
│ • Chunk-based │ │ • Field-level│ │ • Determin- │
│ • File paths  │ │   norm.      │ │   istic     │
└───────────────┘ └──────────────┘ └──────────────┘
```

### Integration Layer
```
┌─────────────────────────────────────────────────┐
│         AlexandriaMIVPStore                     │
├─────────────────────────────────────────────────┤
│ • AlexandriaStore with MIVP identity injection  │
│ • Each patch includes author's CIH              │
│ • Identity verification during reconstruction   │
│ • Tamper detection + substitution detection     │
└─────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────┐
│         AgentIdentity                           │
├─────────────────────────────────────────────────┤
│ • Model configuration (weights, path)           │
│ • Policy configuration (guardrails, prompts)    │
│ • Runtime configuration (temperature, tokens)   │
│ • CIH computation & attestation generation      │
└─────────────────────────────────────────────────┘
```

## Data Flow

### 1. Claim Creation
```
Agent Identity → CIH Computation → Patch Creation → Audit Gate → Hash Chain → Store
      │                │               │              │            │          │
      └───────────────┘               └──────────────┘            └──────────┘
```

### 2. Verification Flow
```
Store → Patch Retrieval → CIH Extraction → Identity Verification → Reconstruction → State Validation
                                │                    │                   │
                                └────────────────────┘                   └──────────────┘
```

### 3. Branching & Dissent
```
Main Branch → Controversial Patch → Branch Creation → Alternative Interpretation → Coexistence
      │               │                   │                       │
      └───────────────┘                   └───────────────────────┘
```

## Security Properties

### Cryptographic Guarantees
1. **Integrity**: Hash chains detect any tampering with patch sequences
2. **Provenance**: CIH links claims to specific model/policy/runtime configurations
3. **Non-repudiation**: Signed attestations (when combined with ORK/ASK) prevent denial
4. **Substitution Detection**: Any change to model, policy, or runtime produces different CIH

### Epistemic Guarantees
1. **Category Purity**: Claims cannot smuggle category changes
2. **Temporal Monotonicity**: Patches must be time-ordered within branches
3. **Structural Admissibility**: All patches pass audit gate validation
4. **Dissent Preservation**: Branches preserve alternative interpretations

## Compliance & Interoperability

### MIVP v2.1 Compliance
- **Appendix G Test Vectors**: Byte-identical output required
- **Deterministic Hashing**: No randomness in identity computation
- **Canonical Formats**: JSON normalization, CFS-1 floats
- **Merkle Tree Specification**: Carry-up logic for odd leaf counts

### Alexandria Protocol Compliance
- **Reference Implementation**: Based on `hstre/Alexandria-Protokoll`
- **Patch-DSL**: ADD/MODIFY/DEPRECATE/BRANCH operations
- **Category System**: EMPIRICAL/NORMATIVE/MODEL/SPECULATIVE
- **Audit Gate**: Structural admissibility checks

## Performance Considerations

### Computational Overhead
- **MIVP Hashing**: One-time per agent configuration (cached)
- **Patch Submission**: O(1) for chain anchoring, O(n) for state update
- **Reconstruction**: O(n) for full verification, O(1) for incremental updates
- **Identity Verification**: O(1) per patch (hash comparison)

### Storage Requirements
- **Patches**: Append-only, compressible (delta encoding possible)
- **Nodes**: Derived state, can be recomputed from patches
- **Branches**: Share common prefix, efficient storage
- **Hashes**: Fixed-size (32 bytes each)

## Advanced Components

### Audit Gate (Three-Layer Validation)
```
┌────────────────────────────────────────────────────┐
│                  AuditGate                         │
├──────────────────┬─────────────────┬───────────────┤
│ Semantic Layer   │ Source Layer    │ Temporal Layer│
│ SEM001–009       │ SRC001–006      │ TMP001–008    │
│                  │                 │               │
│ • Length checks  │ • Presence      │ • Plausibility│
│ • Placeholders   │ • URL format    │ • Monotonicity│
│ • Repetition     │ • Duplicates    │ • Scope       │
│ • Assumptions    │ • Count range   │ • Anachronism │
└──────────────────┴─────────────────┴───────────────┘
         │
AuditReport → violations (ERROR|WARNING), raise_if_failed()
```

### Uncertainty Propagation
```
Claim DAG (directed acyclic graph)
  A → B → D
  C → B
       ↓
UncertaintyPropagator (Kahn topological sort)
  • Modes: SUM_IN_QUADRATURE, WEIGHTED_MEAN, MAX, MEAN, LINEAR
  • Decay: reduces contribution of distant sources
  • Cycle detection (DFS): cycle nodes get combined_sigma=inf
       ↓
PropagationReport → per-node combined_sigma, depth, contributing_nodes
```

### Cross-Agent Epistemic Graphs
```
Agent A ──────────────────────────── Agent B
  c1 (EMPIRICAL, σ=0.1)               c3 (EMPIRICAL, σ=0.15)
  c2 (EMPIRICAL, σ=0.2)               c4 (NORMATIVE, σ=0.3)
       │  SUPPORTS ────────────────────►  │
       │  CHALLENGES ◄──────────────────  │
       └──────────────────────────────────┘
                      ↓
            CrossAgentGraph
            • BFS path-finding
            • Conflict detection (direct_challenge, cross_agent_challenge)
            • agent_contributions()
            • to_dict() / from_dict()
```

### Performance Layer
```
AlexandriaMIVPStore
       │
   NodeCache (LRU)           QueryCache (TTL)
   key: (branch, patch_id)   key: SHA256(args)
   thread-safe               thread-safe
       │
   BatchProcessor            PerformanceMonitor
   ThreadPoolExecutor         context-manager timing
   parallel / sequential      per-operation stats
```

### Distributed Storage Layer
```
DistributedAlexandriaStore
       │
DistributedBackend (abstract)
   ├── InMemoryBackend          (dict, thread-safe, tests)
   ├── S3Backend                (boto3, mock mode available)
   ├── IPFSBackend              (content-addressed, mock mode)
   ├── DistributedLedgerBackend (append-only, cryptographic chain)
   └── MultiBackend             (redundancy: write-all, read-first)
```

### Formal Verification Framework
```
EpistemicVerifier(store)
       │
Built-in Invariants          Built-in Properties
• no_dangling_references     • chain_integrity
• monotonic_timestamps       • unique_patch_ids
• valid_operations           • sigma_in_range
• valid_categories           • content_not_empty
                             • no_deprecated_without_add
                             • assumptions_for_speculative
       │
Custom Properties (add_property / @verifier.property decorator)
       │
VerificationReport
• passed / failed / errors / skipped
• is_fully_verified
• tag-based filtering, skip list
• per-result timing (duration_ms)
```

## Extension Points

### Pluggable Storage
- **In-Memory**: For testing/development (`InMemoryBackend`)
- **SQLite**: Persistent local storage (`AlexandriaSQLiteMIVPStore`)
- **S3**: AWS / MinIO object storage (`S3Backend`)
- **IPFS**: Content-addressed distributed storage (`IPFSBackend`)
- **Ledger**: Append-only cryptographic log (`DistributedLedgerBackend`)
- **Multi**: Redundant multi-backend layer (`MultiBackend`)

### Audit Gate Customization
- Register custom thresholds via `AuditGateConfig`
- Three validation layers (semantic, source, temporal) are independently composable
- Factory functions: `make_default_gate()`, `make_strict_empirical_gate()`

### Integration Interfaces
- **REST API**: HTTP endpoints for remote access
- **CLI**: Command-line tools for manual operation
- **GUI**: Visual epistemic graph exploration (CrossAgentGraph export)

## Use Case Scenarios

### Research Collaboration
```
Researcher A → Claim → Alexandria Store → CIH Attestation → Researcher B → Verification → Trust
```

### Regulatory Compliance
```
AI System → Decisions → Epistemic Audit Trail → Regulator → Identity Verification → Compliance Check
```

### Multi-Agent Systems
```
Agent 1 → Claim → Shared Graph → Agent 2 → Counter-Claim → Branch → Coexistence → Consensus
```

### Educational Applications
```
Curriculum → Epistemic Nodes → Student Contributions → Branching Discussions → Knowledge Evolution
```