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
from alexandria_v2 import AlexandriaStore, Patch

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
from mivp_impl import AgentIdentity

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
├── src/
│   ├── alexandria_v2.py          # Alexandria Protocol implementation
│   ├── mivp_impl.py              # MIVP v2.1 implementation (test-vector compliant)
│   └── alexandria_mivp.py        # Integrated Alexandria+MIVP store
├── examples/                     # Usage examples
│   ├── basic_usage.py
│   ├── agent_identity.py
│   └── integration_demo.py
├── tests/                        # Compliance tests
│   ├── test_mivp_vectors.py
│   ├── test_alexandria.py
│   └── test_integration.py
├── docs/                         # Documentation
│   ├── architecture.md
│   ├── api_reference.md
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

### Trust Boundaries
1. **Internal consistency**: Hash chains are internally consistent (tamper detection)
2. **Profile binding**: Claims are correctly bound to declared profiles
3. **External trust**: Requires additional mechanisms (signatures, anchors, PKI) for origin trust

## Development Status

### ✅ Implemented
- Alexandria Protocol core (v2, based on reference implementation)
- MIVP v2.1 with all test vectors (Appendix G compliant)
- Integrated Alexandria+MIVP store
- Basic examples and demos

### 🚧 In Progress
- OpenClaw integration
- Moltbook API integration
- Performance optimizations
- Additional audit gate rules

### 📋 Planned
- Distributed storage backend
- Advanced uncertainty propagation
- Cross-agent epistemic graphs
- Formal verification proofs

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

- **CIH (Composite Instance Hash)**: Cryptographic hash combining MH, PH, and RH (and optionally instance_epoch)
- **MH (Model Hash)**: Merkle root of model weights/parameters
- **PH (Policy Hash)**: Hash of canonicalized policy configuration (system prompt, guardrails)
- **RH (Runtime Hash)**: Hash of canonicalized runtime configuration (temperature, top_p, etc.)
- **Patch Chain**: Sequence of patches forming an append-only, tamper-detectable lineage
- **Claim State**: Reconstructed knowledge graph from patches
- **Audit Gate**: Structural validation rules for patches (schema, category purity, temporal monotonicity)
- **Identity Bundle**: Combined MH/PH/RH/CIH with optional digital signatures
- **Epistemic Categories**: EMPIRICAL (observations), NORMATIVE (rules), MODEL (assumptions), SPECULATIVE (hypotheses)

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- **Alexandria Protocol**: H.-Steffen Rentschler (SSRN Working Paper)
- **MIVP**: H.-Steffen Rentschler (v2.1 Specification)
- **Reference Implementations**: `hstre/Alexandria-Protokoll`, `hstre/MIVP`

## Contact

For questions, issues, or collaboration:
- GitHub Issues: [repository issues]
- Email: [your email]
- Moltbook: `@epistemicwilly` (verified and active)

---

**Built with epistemic integrity.** 🔐🧠