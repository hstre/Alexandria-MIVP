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

## Extension Points

### Pluggable Storage
- **Local Filesystem**: Default (JSON files)
- **Database**: SQL/NoSQL backends
- **Distributed**: IPFS, S3, distributed ledgers
- **In-Memory**: For testing/development

### Additional Audit Rules
- **Semantic Validation**: LLM-based content analysis
- **Source Verification**: Link crawling, fact-checking
- **Consistency Checking**: Logical contradiction detection
- **Temporal Reasoning**: Claim expiration, staleness detection

### Integration Interfaces
- **REST API**: HTTP endpoints for remote access
- **gRPC**: High-performance RPC interface
- **CLI**: Command-line tools for manual operation
- **GUI**: Visual epistemic graph exploration

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