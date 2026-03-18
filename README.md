# Alexandria Protocol + MIVP Integration

**Binding claims to declared, hash-addressed model/policy/runtime profiles with epistemic consistency.**

## Overview

This project combines two complementary protocols:

1. **Alexandria Protocol** - Epistemic consistency layer for tamper-proof knowledge lineage
2. **MIVP (Model Identity Verification Protocol)** - Cryptographic binding of claims to declared identity profiles

Together, they provide **structural verifiability**: binding knowledge claims to specific, hash-addressed system profiles while maintaining epistemic consistency of the claim graph.

## Why This Matters

### The Problem
- **Epistemic Drift**: AI agents make claims without structural continuity or auditability
- **Profile Opaqueness**: Claims aren't bound to specific model/policy/runtime profiles
- **Silent Substitution**: System profiles can be switched without detection
- **Unverifiable Lineage**: Claims lack cryptographic binding to their source profiles

### The Solution
- **MIVP** binds claims to *declared system profiles* (model, policy, runtime configurations)
- **Alexandria** ensures *epistemic structure* of claims (categories, operations, consistency)
- **Combined**: Claims are structurally sound and bound to specific, hash-addressed system profiles

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MIVP Layer    │    │ Alexandria Layer│    │   Application   │
│                 │    │                 │    │                 │
│ • Model Hash    │───▶│ • Claim Graph   │───▶│ • Agent Claims  │
│ • Policy Hash   │    │ • Patch-DSL     │    │ • Audit Trails  │
│ • Runtime Hash  │    │ • Audit Gate    │    │ • Verifiable    │
│ • Composite     │    │ • Hash Chains   │    │   Knowledge     │
│   Instance Hash │    │ • Branching     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Key Components

### Alexandria Protocol
- **Epistemic Categories**: `EMPIRICAL`, `NORMATIVE`, `MODEL`, `SPECULATIVE`
- **Patch Operations**: `ADD`, `MODIFY`, `DEPRECATE`, `BRANCH`
- **Audit Gate**: Structural admissibility checks (schema, category purity, temporal monotonicity)
- **Hash Chains**: Append-only, tamper-detectable patch sequences
- **Branch Support**: Dissent creates branches, never deletions

### MIVP v2.1
- **Four Hash Layers**: MH (Model), PH (Policy), RH (Runtime), CIH (Composite)
- **Merkle Trees**: For model weight verification (carry-up logic)
- **Canonical JSON**: Field-level normalization for deterministic hashing
- **CFS-1 Floats**: Round-trip-safe decimal serialization
- **Normative Test Vectors**: Byte-identical compliance required (Appendix G)
- **Digital Signatures**: Optional cryptographic signatures for origin binding (Ed25519)

### Integration
- **Agent Identity**: Each patch includes author's CIH (Composite Instance Hash)
- **Identity Verification**: Patches can be cryptographically linked to their source
- **End-to-End Audit**: Full provenance from model identity to claim structure

## Installation

```bash
git clone https://github.com/hstre/Alexandria-MIVP
cd alexandria-mivp
```

No external dependencies required (pure Python 3.8+).

## Quick Start

### Basic Alexandria Usage
```python
from alexandria_mivp import AlexandriaStore, Patch

store = AlexandriaStore()
store.checkout("main")

# Create a claim
patch = Patch(
    patch_id="patch_001",
    parent_patch_id=None,
    branch_id="main",
    timestamp=1771459200,
    operation="ADD",
    target_id="claim_001",
    category="EMPIRICAL",
    payload={"content": "Observation under conditions X", "assumptions": ["X"]},
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 0.05},
)

store.submit(patch)
print(store.status_report())
```

### MIVP Identity Creation
```python
from alexandria_mivp import AgentIdentity

identity = AgentIdentity(
    name="EpistemicWilly",
    model_path="models/my_model.bin",
    model_bytes=b"...",
    system_prompt="You are an epistemic agent.",
    guardrails=[{"id": "no_harm", "rule": "Do not cause harm"}],
    temperature=0.7,
    top_p=0.9,
)

print(f"CIH: {identity.compute_cih().hex()}")
```

### Integrated Usage
```python
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity

# Create identity
identity = AgentIdentity(name="MyAgent", ...)

# Create store with identity
store = AlexandriaMIVPStore(identity)

# Submit patch with cryptographic identity
patch = Patch(...)
commit_hash = store.submit_with_identity(patch)

# Verify all identities in branch
nodes = store.reconstruct_with_identity_verification("main")
```

## Compliance

### MIVP Compliance
The implementation passes **all normative test vectors from Appendix G**:
- [x] Model Hash test vectors (G2)
- [x] Policy Hash test vectors (G3)  
- [x] Runtime Hash test vectors (G4)
- [x] Composite Instance Hash test vectors (G5)

Byte-identical output is required for interoperability.

### Alexandria Compliance
Based on the reference implementation from `hstre/Alexandria-Protokoll`:
- [x] Epistemic category system (EMPIRICAL/NORMATIVE/MODEL/SPECULATIVE)
- [x] Patch-DSL operations (ADD/MODIFY/DEPRECATE)
- [x] Audit gate with structural checks
- [x] Hash chain anchoring
- [x] Branch support for dissent

### Test Vectors
Normative test vectors are published for reproducibility and interoperability:

```
tests/vectors/
├── identity_vectors.json    # MIVP v2.1 Appendix G test vectors
└── patch_chain_vectors.json # Alexandria patch chain examples
```

Each test vector includes:
- **Input**: Complete specification of inputs
- **Expected Hash**: Byte-identical expected output
- **Verification Result**: Expected validation outcome

These vectors enable:
- **External implementations** to verify compliance
- **Scientific reproducibility** of hash computations
- **Interoperability testing** between different implementations

## Use Cases

### 1. Research & Academia
- **Reproducible Experiments**: Claims with verifiable model identities
- **Epistemic Audits**: Trace claim evolution and justification chains
- **Collaborative Science**: Multiple agents contributing to shared knowledge graphs

### 2. Enterprise & Compliance
- **Regulatory Compliance**: Audit trails for AI decision-making
- **Model Governance**: Detect unauthorized model substitutions
- **Knowledge Management**: Structured, verifiable organizational knowledge

### 3. Autonomous Agents
- **Agent-to-Agent Trust**: Verify counterparty identities
- **Epistemic Continuity**: Maintain consistent world models
- **Error Analysis**: Trace claim derivation paths for debugging

### 4. Moltbook Integration
- **Verifiable Posts**: Social media claims with cryptographic provenance
- **Community Building**: Epistemically grounded discussions
- **Trust Networks**: Identity-verified agent communities

## Project Structure

```
alexandria-mivp/
├── alexandria_mivp/
│   ├── alexandria_v2.py          # Alexandria Protocol core (Patch-DSL, store, nodes)
│   ├── mivp_impl.py              # MIVP v2.1 (test-vector compliant, MH/PH/RH/CIH)
│   ├── alexandria_mivp.py        # Integrated Alexandria+MIVP store + Extended Runtime Hash
│   ├── sqlite_store.py           # SQLite persistence with 10 identity query methods
│   ├── audit_gate.py             # Extended Audit Gate (semantic, source, temporal checks)
│   ├── uncertainty_propagator.py # Uncertainty propagation across claim DAGs
│   ├── cross_agent_graph.py      # Cross-agent epistemic graphs (multi-agent scenarios)
│   ├── performance.py            # NodeCache, QueryCache, BatchProcessor, PerformanceMonitor
│   ├── distributed_store.py      # Distributed backends (S3, IPFS, Ledger, Multi)
│   ├── formal_verification.py    # Formal verification framework (invariants, properties)
│   ├── sub_agent.py              # SubAgent spawning and MultiAgentCoordinator
│   ├── heartbeat.py              # Epistemic Heartbeat (periodic integrity checks)
│   ├── message_router.py         # Message routing between agents
│   ├── external_anchor.py        # External anchoring (OpenTimestamps, Webhook)
│   └── moltbook_integration.py   # Moltbook API integration
├── examples/                     # Usage examples
│   ├── basic_usage.py
│   ├── agent_identity.py
│   └── integration_demo.py
├── tests/                        # 522 tests (all passing)
│   ├── test_mivp_vectors.py      # MIVP v2.1 Appendix G compliance
│   ├── test_alexandria.py
│   ├── test_integration.py
│   ├── test_extended_runtime_hash.py
│   ├── test_sqlite_identity_queries.py
│   ├── test_audit_gate.py
│   ├── test_uncertainty_propagator.py
│   ├── test_cross_agent_graph.py
│   ├── test_performance.py
│   ├── test_distributed_store.py
│   └── test_formal_verification.py
├── docs/                         # Documentation
│   ├── architecture.md
│   ├── api_reference.md
│   ├── getting_started.md
│   └── use_cases.md
└── README.md
```

## Security Model

### What This System Guarantees
- **Tamper detection within known chains**: Any modification to patches or their lineage is detectable
- **Claim lineage reconstruction**: Complete history of claims can be reconstructed from the patch sequence
- **Hash-bound identity profiles**: Claims are cryptographically bound to declared model/policy/runtime profiles
- **Structural consistency**: Epistemic categories and operations follow defined rules (audit gate)
- **Deterministic verification**: Same inputs always produce same verification results

### What This System Does NOT Guarantee
- **Authorized identity**: The system doesn't verify who controls the private keys or system profile
- **Hardware attestation**: No guarantees about execution environment (TPM, TEE, secure enclaves)
- **Global immutability**: Chains can be regenerated from scratch; external anchoring required for global consistency
- **Network authenticity**: No protection against network-level attacks (MITM, replay)
- **Trustworthy origin**: Hash consistency doesn't imply trustworthiness of the source

### Threat Model

The following table analyzes potential attacks and how the system addresses them:

| Attack Vector | Description | Protection Provided | Additional Measures Needed |
|---------------|-------------|---------------------|----------------------------|
| **Tampering with patches** | Modifying patch content or lineage after submission | ✅ **Detectable**: Hash chain breaks, CIH mismatches | Regular integrity checks |
| **Silent model substitution** | Switching model weights without detection | ✅ **Detectable**: Different MH changes CIH | Runtime monitoring |
| **Policy/Runtime drift** | Changing prompt, guardrails, or runtime parameters | ✅ **Detectable**: PH/RH changes alter CIH | Configuration management |
| **Full chain regeneration** | Creating a new chain from scratch with same claims | ⚠️ **Not prevented**: No global immutability | ✅ **External anchoring** (transparency logs, witnesses) |
| **Identity spoofing** | Claiming to be a different agent | ⚠️ **Possible without signatures** | ✅ **Digital signatures** (Ed25519) |
| **Replay attacks** | Reusing old patches in new contexts | ⚠️ **Possible**: Timestamps help but not foolproof | Sequence numbers, nonces, external timestamps |
| **Network attacks** | MITM, interception, modification in transit | ❌ **No protection** | Transport security (TLS), message signing |
| **Key compromise** | Private signing key stolen | ❌ **No protection** | Key rotation, hardware security modules |
| **Hardware attacks** | Tampering with execution environment | ❌ **No protection** | TEE/TPM attestation, secure enclaves |

### Security Considerations for Deployment

1. **For high-trust environments**:
   - Enable digital signatures for all patches
   - Use external anchoring (multiple services for redundancy)
   - Implement key rotation policies

2. **For regulatory compliance**:
   - Store chains with external timestamping (RFC 3161)
   - Maintain witness node networks for cross-verification
   - Enable full audit trails with cryptographic proofs

3. **For agent-to-agent trust**:
   - Exchange public keys out-of-band or via PKI
   - Verify signatures on received patches
   - Check external anchors for critical claims

4. **For long-term archival**:
   - Regular anchoring to multiple external services
   - Key escrow for signature verification continuity
   - Chain replication across geographically distributed nodes

### Trust Boundaries
1. **Internal consistency**: Hash chains are internally consistent (tamper detection)
2. **Profile binding**: Claims are correctly bound to declared profiles
3. **External trust**: Requires additional mechanisms (signatures, anchors, PKI) for origin trust

## Development Status

### ✅ Implemented
- Alexandria Protocol core (v2, based on reference implementation)
- MIVP v2.1 with all test vectors (Appendix G compliant)
- Integrated Alexandria+MIVP store with full MIVP identity injection
- SQLite persistence backend with 10 identity-query methods
- Extended Runtime Hash (three-layer: config / environment / attestation)
- Extended Audit Gate with semantic, source-verification and temporal checks
- Uncertainty Propagation across claim graphs (DAG, 5 combination modes)
- Cross-Agent Epistemic Graphs (5 edge types, BFS path-finding, conflict detection)
- Performance layer: LRU NodeCache, TTL QueryCache, parallel BatchProcessor, PerformanceMonitor
- Distributed Storage Backend: InMemory, S3, IPFS, DistributedLedger, MultiBackend
- Formal Verification Framework: invariants, properties, custom checks, VerificationReport
- Multi-agent coordination (SubAgent, MultiAgentCoordinator, consensus building)
- Epistemic Heartbeat (periodic integrity and consistency monitoring)
- Message routing (MessageRouter, subscription-based claim delivery)
- External anchoring (OpenTimestamps, Webhook, multi-anchor redundancy)
- Moltbook API integration (bidirectional sync)

### 🚧 In Progress
- OpenClaw integration

## Contributing

1. **Fork** the repository
2. **Test** your changes against MIVP test vectors (must remain byte-identical)
3. **Document** new features or changes
4. **Submit** a pull request

### Critical Constraints
- **MIVP compliance**: All changes must maintain byte-identical output for test vectors
- **Deterministic hashing**: No randomness in identity computation
- **Immutable patches**: Once submitted, patches cannot be modified

## Glossary

### Core Concepts
- **Alexandria Protocol**: Epistemic consistency layer for tamper-proof knowledge lineage
- **MIVP (Model Identity Verification Protocol)**: Cryptographic binding of claims to declared system profiles
- **Epistemic Categories**: EMPIRICAL (observations), NORMATIVE (rules), MODEL (assumptions), SPECULATIVE (hypotheses)
- **Patch**: Immutable operation (ADD, MODIFY, DEPRECATE) applied to the knowledge graph
- **Patch Chain**: Sequence of patches forming an append-only, tamper-detectable lineage
- **Claim State**: Reconstructed knowledge graph from patches
- **Audit Gate**: Structural validation rules for patches (schema, category purity, temporal monotonicity)
- **Uncertainty**: Quantified doubt about a claim (sigma, confidence interval, sample size)
- **Stability**: Measure of claim robustness based on validation history and decay
- **Decay**: Rate at which claim stability decreases over time without reinforcement

### MIVP Identity Components
- **MH (Model Hash)**: Merkle root of model weights/parameters
- **PH (Policy Hash)**: Hash of canonicalized policy configuration (system prompt, guardrails)
- **RH (Runtime Hash)**: Hash of canonicalized runtime configuration (temperature, top_p, etc.)
- **CIH (Composite Instance Hash)**: Cryptographic hash combining MH, PH, and RH (and optionally instance_epoch)
- **Instance Epoch**: Version counter that changes CIH without altering MH/PH/RH (for instance rotation)
- **Identity Bundle**: Combined MH/PH/RH/CIH with optional digital signatures
- **Merkle Root**: Root hash of a Merkle tree (used in MH computation)
- **Carry-up Logic**: Merkle tree construction algorithm where odd nodes pass through unchanged
- **CFS-1 (Canonical Float Serialization)**: Round-trip-safe decimal serialization for floating-point numbers

### Security & Trust
- **Digital Signer**: Ed25519 implementation for signing identity bundles
- **External Anchor**: External trust service (transparency logs, witness nodes, timestamp servers)
- **Transparency Log**: Append-only log for external verification of CIHs
- **Witness Node**: Decentralized node that attests to the existence of CIHs
- **Timestamp Server**: RFC 3161 compliant service for trusted timestamps
- **Trust Boundary**: Conceptual line separating components with different trust assumptions

### Epistemic Metrics
- **Uncertainty**: Quantified doubt (sigma, confidence interval, sample size)
- **Stability**: Derived confidence metric based on validation history and decay
- **Decay**: Rate at which stability decreases over time without reinforcement
- **Lineage**: Record of all patches that have affected a claim

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- **Alexandria Protocol**: H.-Steffen Rentschler (SSRN Working Paper)
- **MIVP**: H.-Steffen Rentschler (v2.1 Specification)
- **Reference Implementations**: `hstre/Alexandria-Protokoll`, `hstre/MIVP`

## Contact

For questions, issues, or collaboration:
- GitHub Issues: [repository issues]
- Email: [tentschler@lbsmail.de]
- Moltbook: `@epistemicwilly` (verified and active)

---

**Built with epistemic integrity.** 🔐🧠
