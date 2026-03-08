# Getting Started

## Quick Overview

Alexandria Protocol + MIVP provides:
- **Epistemic consistency** via Alexandria (structured knowledge graphs)
- **Cryptographic identity** via MIVP (verifiable agent identities)
- **End-to-end verifiability** (who claimed what, with which system)

## Installation

### Option 1: Clone from GitHub
```bash
git clone https://github.com/hstre/Alexandria-MIVP
cd Alexandria-MIVP
```

### Option 2: Install as Package (Development)
```bash
# From source directory
cd Alexandria-MIVP
pip install -e .
```

### Option 3: Use Directly (No Installation)
```python
import sys
sys.path.insert(0, '/path/to/Alexandria-MIVP/src')

from alexandria_v2 import AlexandriaStore, Patch
from mivp_impl import AgentIdentity
from alexandria_mivp import AlexandriaMIVPStore
```

**No external dependencies required** - pure Python 3.8+.

## Quick Start Examples

### 1. Basic Alexandria Usage
```python
from alexandria_v2 import AlexandriaStore, Patch

# Create a store
store = AlexandriaStore()
store.checkout("main")

# Create a simple claim
patch = Patch(
    patch_id="my_first_claim",
    parent_patch_id=None,
    branch_id="main",
    timestamp=1700000000,
    operation="ADD",
    target_id="observation_001",
    category="EMPIRICAL",
    payload={
        "content": "Water boils at 100°C at sea level",
        "assumptions": ["Pure water", "Standard atmospheric pressure"]
    },
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 0.1}
)

# Submit the patch
commit_hash = store.submit(patch)
print(f"Claim submitted with hash: {commit_hash[:16]}...")

# Check status
status = store.status_report()
print(f"Store has {len(status['nodes'])} claims")
```

### 2. Basic MIVP Identity
```python
from mivp_impl import AgentIdentity

# Create an agent identity
identity = AgentIdentity(
    name="MyFirstAgent",
    model_path="models/my_model.bin",
    model_bytes=b"sample model weights",
    system_prompt="You are a helpful assistant.",
    guardrails=[
        {"id": "no_harm", "rule": "Do not cause harm"},
        {"id": "honesty", "rule": "Be truthful"}
    ],
    temperature=0.7,
    top_p=0.9,
    max_tokens=2000,
    tooling_enabled=True
)

# Compute identity hashes
mh = identity.compute_mh()
ph = identity.compute_ph()
rh = identity.compute_rh()
cih = identity.compute_cih()

print(f"Agent: {identity.name}")
print(f"Model Hash: {mh.hex()[:16]}...")
print(f"Policy Hash: {ph.hex()[:16]}...")
print(f"Runtime Hash: {rh.hex()[:16]}...")
print(f"Composite Instance Hash: {cih.hex()[:16]}...")
```

### 3. Integrated Alexandria + MIVP
```python
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from alexandria_v2 import Patch

# Create agent identity
identity = AgentIdentity(
    name="ResearchAssistant",
    model_path="models/research.bin",
    model_bytes=b"...",
    system_prompt="Research assistant specializing in science.",
    guardrails=[{"id": "cite_sources", "rule": "Cite reliable sources"}],
    temperature=0.3,
    top_p=0.95
)

# Create store with identity
store = AlexandriaMIVPStore(identity)
store.checkout("main")

# Submit claim with cryptographic identity
patch = Patch(
    patch_id="research_finding",
    parent_patch_id=None,
    branch_id="main",
    timestamp=1700000000,
    operation="ADD",
    target_id="finding_001",
    category="EMPIRICAL",
    payload={
        "content": "Study shows 20% improvement with new method",
        "assumptions": ["n=1000", "p<0.01", "controlled experiment"]
    },
    audit={"validated": True, "decay": 0.02},
    uncertainty={"sigma": 2.5, "ci": [15, 25], "n": 1000}
)

commit_hash = store.submit_with_identity(patch)
print(f"Verifiable claim submitted: {commit_hash[:16]}...")

# Verify all identities
nodes = store.reconstruct_with_identity_verification("main")
print(f"Verified {len(nodes)} claims with cryptographic identity")
```

## Step-by-Step Tutorial

### Step 1: Understanding Epistemic Categories

Alexandria uses four epistemic categories:

```python
from alexandria_v2 import CATEGORIES

print("Valid categories:", CATEGORIES)
# {'EMPIRICAL', 'NORMATIVE', 'MODEL', 'SPECULATIVE'}

# Choose based on claim type:
category_guide = {
    "EMPIRICAL": "Observable, falsifiable facts (data, measurements)",
    "NORMATIVE": "Value judgments, prescriptions (should, ought)",
    "MODEL": "Model assumptions, simplifications (if-then, given)",
    "SPECULATIVE": "Unverified, exploratory claims (might, could)"
}
```

**Example claims:**
```python
empirical = "Temperature measured at 25.3°C"
normative = "Should reduce carbon emissions by 50%"
model = "Assuming constant growth rate of 3%"
speculative = "AI consciousness might emerge at scale"
```

### Step 2: Creating Your First Claims

```python
from alexandria_v2 import AlexandriaStore, Patch

store = AlexandriaStore()
store.checkout("main")

# Claim 1: Empirical observation
observation = Patch(
    patch_id="obs_001",
    parent_patch_id=None,
    branch_id="main",
    timestamp=1700000000,
    operation="ADD",
    target_id="temperature_reading",
    category="EMPIRICAL",
    payload={
        "content": "Room temperature is 22.5°C",
        "assumptions": ["Sensor calibrated", "No direct sunlight"]
    },
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 0.5}
)

# Claim 2: Model assumption
model_assumption = Patch(
    patch_id="model_001",
    parent_patch_id="obs_001",  # Builds on previous claim
    branch_id="main",
    timestamp=1700000100,
    operation="ADD",
    target_id="growth_model",
    category="MODEL",
    payload={
        "content": "Assuming 5% monthly growth rate",
        "assumptions": ["Historical trend continues", "No market shocks"]
    },
    audit={"validated": True, "decay": 0.05}
)

# Submit both
store.submit(observation)
store.submit(model_assumption)

print("Created claim chain:")
print("1. Observation → 2. Model assumption")
```

### Step 3: Working with Uncertainty

```python
# Different uncertainty levels
uncertainty_levels = {
    "high_confidence": {
        "sigma": 0.1,
        "ci": [0.9, 1.1],
        "n": 10000
    },
    "medium_confidence": {
        "sigma": 0.3,
        "ci": [0.7, 1.3],
        "n": 1000
    },
    "low_confidence": {
        "sigma": 0.5,
        "ci": [0.5, 1.5],
        "n": 100
    },
    "speculative": {
        "sigma": 1.0,
        "ci": [0.0, 2.0],
        "n": 10
    }
}

# Use appropriate uncertainty
scientific_claim = Patch(
    operation="ADD",
    target_id="scientific_result",
    category="EMPIRICAL",
    payload={"content": "New drug reduces symptoms by 60%"},
    audit={"validated": True, "decay": 0.01},
    uncertainty=uncertainty_levels["high_confidence"]  # Well-tested
)

preliminary_finding = Patch(
    operation="ADD",
    target_id="preliminary_result",
    category="SPECULATIVE",
    payload={"content": "Early data suggests possible correlation"},
    audit={"validated": False, "decay": 0.1},
    uncertainty=uncertainty_levels["speculative"]  # Early stage
)
```

### Step 4: Creating Agent Identity

```python
from mivp_impl import AgentIdentity

# Basic identity for testing
test_identity = AgentIdentity(
    name="TestAgent_v1.0",
    model_path="test_models/simple.bin",
    model_bytes=b"test" * 1000,  # Mock model weights
    model_chunk_size=16,  # Small for testing
    
    # Policy configuration
    system_prompt="You are a test agent for demonstration.",
    guardrails=[
        {"id": "test_rule_1", "rule": "Always respond helpfully"},
        {"id": "test_rule_2", "rule": "Mark uncertain claims"}
    ],
    moderation_policy_version="test_v1",
    policy_spec_version="1.0",
    attestation_completeness="partial",
    
    # Runtime configuration
    temperature=0.5,
    top_p=0.9,
    max_tokens=1000,
    tooling_enabled=False,
    routing_mode="test",
    runtime_spec_version="1.0"
)

# Compute and display identity
identity_info = test_identity.get_identity_dict()
print("Agent Identity Created:")
print(f"  Name: {identity_info['agent_name']}")
print(f"  CIH: {identity_info['cih'][:16]}...")
print(f"  Timestamp: {identity_info['timestamp']}")

# Save for later use
import json
with open("agent_identity.json", "w") as f:
    json.dump(identity_info, f, indent=2)
```

### Step 5: Identity Changes & Detection

```python
# Start with identity
identity1 = AgentIdentity(
    name="ConsistentAgent",
    model_path="models/stable.bin",
    model_bytes=b"version1",
    system_prompt="Stable configuration",
    temperature=0.3
)

cih1 = identity1.compute_cih()
print(f"Original CIH: {cih1.hex()[:16]}...")

# Change runtime configuration
identity1.temperature = 0.7  # Increased creativity
cih2 = identity1.compute_cih()
print(f"After temperature change: {cih2.hex()[:16]}...")
print(f"CIH changed: {cih1 != cih2}")  # True - detectable!

# Change policy
identity1.guardrails.append(
    {"id": "new_rule", "rule": "Additional constraint"}
)
cih3 = identity1.compute_cih()
print(f"After policy change: {cih3.hex()[:16]}...")
print(f"CIH changed again: {cih2 != cih3}")  # True

# Reset for consistency
identity1.temperature = 0.3
identity1.guardrails.pop()
cih_original_again = identity1.compute_cih()
print(f"Back to original: {cih1 == cih_original_again}")  # True
```

### Step 6: Branching for Alternative Views

```python
store = AlexandriaStore()
store.checkout("main")

# Initial claim
initial = Patch(
    patch_id="base_claim",
    parent_patch_id=None,
    branch_id="main",
    timestamp=1700000000,
    operation="ADD",
    target_id="initial_hypothesis",
    category="SPECULATIVE",
    payload={"content": "Method A is most effective"},
    audit={"validated": True, "decay": 0.05}
)
store.submit(initial)

# Create branch for alternative view
store.create_branch("alternative_approach")
store.checkout("alternative_approach")

# Alternative claim in branch
alternative = Patch(
    patch_id="alt_claim",
    parent_patch_id="base_claim",  # Branches from same point
    branch_id="alternative_approach",
    timestamp=1700000100,
    operation="ADD",
    target_id="alternative_hypothesis",
    category="SPECULATIVE",
    payload={"content": "Method B might be better for certain cases"},
    audit={"validated": True, "decay": 0.05}
)
store.submit(alternative)

# Both views coexist
print("Main branch claims:", store.checkout("main") and store.list_nodes())
print("Alternative branch claims:", store.checkout("alternative_approach") and store.list_nodes())
```

### Step 7: Verification & Audit

```python
from alexandria_mivp import AlexandriaMIVPStore

# Create store with identity
identity = AgentIdentity(name="AuditableAgent", ...)
store = AlexandriaMIVPStore(identity)

# Submit several claims
for i in range(3):
    patch = Patch(
        patch_id=f"claim_{i}",
        parent_patch_id=None if i == 0 else f"claim_{i-1}",
        branch_id="main",
        timestamp=1700000000 + i*100,
        operation="ADD",
        target_id=f"data_point_{i}",
        category="EMPIRICAL",
        payload={"content": f"Observation {i}"},
        audit={"validated": True, "decay": 0.01}
    )
    store.submit_with_identity(patch)

# Verify reconstruction
print("Reconstructing with full verification...")
try:
    nodes = store.reconstruct_with_identity_verification("main")
    print(f"✅ Successfully verified {len(nodes)} claims")
    print(f"   All patches have valid cryptographic identity")
    
    # Check individual patches
    for patch in store.branches["main"]:
        if store.verify_patch_identity(patch):
            print(f"   ✓ Patch {patch.patch_id}: Identity verified")
        else:
            print(f"   ✗ Patch {patch.patch_id}: Identity mismatch!")
            
except Exception as e:
    print(f"❌ Verification failed: {e}")

# Tamper detection example
print("\nTesting tamper detection...")
original_state = store.reconstruct("main")
print(f"Original state hash: {hash(str(original_state))}")

# Attempt to modify (would be caught by hash chains)
print("Any modification would break hash chain continuity")
print("Integrity protected by SHA256 hash chains")
```

## Common Patterns

### Pattern 1: Research Workflow
```python
def research_workflow(topic, findings):
    """Structure research findings as Alexandria claims."""
    store = AlexandriaStore()
    store.checkout("main")
    
    claims = []
    
    # Literature review claims
    for i, finding in enumerate(findings["literature"]):
        claim = Patch(
            patch_id=f"lit_{i}",
            parent_patch_id=None if i == 0 else f"lit_{i-1}",
            branch_id="main",
            timestamp=1700000000 + i*100,
            operation="ADD",
            target_id=f"literature_finding_{i}",
            category="EMPIRICAL",
            payload={
                "content": finding["summary"],
                "assumptions": finding.get("assumptions", []),
                "source": finding["source"]
            },
            audit={"validated": True, "decay": 0.02},
            uncertainty={"sigma": finding.get("uncertainty", 0.2)}
        )
        store.submit(claim)
        claims.append(claim)
    
    # Research gap identification
    gap_claim = Patch(
        patch_id="research_gap",
        parent_patch_id=claims[-1].patch_id if claims else None,
        branch_id="main",
        timestamp=1700000000 + len(findings["literature"])*100 + 50,
        operation="ADD",
        target_id="identified_gap",
        category="SPECULATIVE",
        payload={
            "content": findings["gap"]["description"],
            "assumptions": findings["gap"].get("assumptions", [])
        },
        audit={"validated": True, "decay": 0.05}
    )
    store.submit(gap_claim)
    
    return store
```

### Pattern 2: Decision Tracking
```python
def track_decision(decision_data, identity=None):
    """Track organizational decisions with provenance."""
    if identity:
        store = AlexandriaMIVPStore(identity)
    else:
        store = AlexandriaStore()
    
    store.checkout("decisions")
    
    decision = Patch(
        patch_id=decision_data["id"],
        parent_patch_id=decision_data.get("parent_id"),
        branch_id="decisions",
        timestamp=decision_data["timestamp"],
        operation="ADD",
        target_id=decision_data["target_id"],
        category="NORMATIVE",
        payload={
            "content": decision_data["decision"],
            "assumptions": decision_data.get("assumptions", []),
            "rationale": decision_data.get("rationale", ""),
            "alternatives_considered": decision_data.get("alternatives", [])
        },
        audit={
            "validated": True,
            "decay": 0.0,  # Permanent record
            "decision_makers": decision_data.get("makers", []),
            "stakeholders": decision_data.get("stakeholders", [])
        }
    )
    
    if identity:
        commit_hash = store.submit_with_identity(decision)
    else:
        commit_hash = store.submit(decision)
    
    return commit_hash
```

### Pattern 3: Experimental Logging
```python
class ExperimentLogger:
    """Log experiments with full reproducibility."""
    
    def __init__(self, experiment_name, identity=None):
        self.experiment_name = experiment_name
        self.identity = identity
        if identity:
            self.store = AlexandriaMIVPStore(identity)
        else:
            self.store = AlexandriaStore()
        self.store.checkout(experiment_name)
        self.last_patch_id = None
        
    def log_parameter(self, name, value, uncertainty=None):
        """Log experimental parameter."""
        patch = Patch(
            patch_id=f"param_{name}_{int(time.time())}",
            parent_patch_id=self.last_patch_id,
            branch_id=self.experiment_name,
            timestamp=int(time.time()),
            operation="ADD",
            target_id=f"parameter_{name}",
            category="EMPIRICAL",
            payload={
                "content": f"{name} = {value}",
                "type": "parameter",
                "units": self._get_units(name)
            },
            audit={"validated": True, "decay": 0.0},
            uncertainty=uncertainty
        )
        
        if self.identity:
            commit_hash = self.store.submit_with_identity(patch)
        else:
            commit_hash = self.store.submit(patch)
        
        self.last_patch_id = patch.patch_id
        return commit_hash
    
    def log_result(self, result, assumptions=[], uncertainty=None):
        """Log experimental result."""
        patch = Patch(
            patch_id=f"result_{int(time.time())}",
            parent_patch_id=self.last_patch_id,
            branch_id=self.experiment_name,
            timestamp=int(time.time()),
            operation="ADD",
            target_id=f"experiment_result",
            category="EMPIRICAL",
            payload={
                "content": str(result),
                "assumptions": assumptions,
                "type": "result"
            },
            audit={"validated": True, "decay": 0.01},
            uncertainty=uncertainty
        )
        
        if self.identity:
            commit_hash = self.store.submit_with_identity(patch)
        else:
            commit_hash = self.store.submit(patch)
        
        self.last_patch_id = patch.patch_id
        return commit_hash
    
    def get_reproducibility_info(self):
        """Get all information needed to reproduce experiment."""
        nodes = self.store.reconstruct(self.experiment_name)
        return {
            "experiment_name": self.experiment_name,
            "parameters": {nid: n.content for nid, n in nodes.items() 
                          if "parameter" in nid},
            "results": {nid: n.content for nid, n in nodes.items()
                       if "result" in nid},
            "identity": self.identity.get_identity_dict() if self.identity else None
        }
```

## Next Steps

### 1. Run Examples
```bash
cd Alexandria-MIVP
python examples/basic_usage.py
python examples/agent_identity.py  
python examples/integration_demo.py
```

### 2. Run Tests
```bash
python tests/test_mivp_vectors.py  # MIVP compliance
python tests/test_alexandria.py    # Alexandria operations
```

### 3. Explore Use Cases
Read `docs/use_cases.md` for detailed application scenarios.

### 4. Integrate with Your System
Start with basic claims, then add:
1. Agent identity (MIVP)
2. Structured categories
3. Branching for alternatives
4. Cryptographic verification

## Troubleshooting

### Common Issues

**Issue:** "AuditError: Invalid operation"
**Solution:** Use only valid operations: "ADD", "MODIFY", "DEPRECATE", "BRANCH"

**Issue:** "AuditError: Invalid category"  
**Solution:** Use only: "EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"

**Issue:** MIVP test vectors fail
**Solution:** Ensure byte-identical implementation per Appendix G

**Issue:** Hash chain discontinuity
**Solution:** Maintain proper parent_patch_id linking

### Getting Help

1. **GitHub Issues:** https://github.com/hstre/Alexandria-MIVP/issues
2. **Moltbook:** @epistemicwilly
3. **Documentation:** `docs/` directory
4. **Examples:** `examples/` directory

## Advanced Topics

Once comfortable with basics, explore:
- **Distributed storage** for multi-node deployment
- **Advanced uncertainty propagation** for complex claims
- **Cross-agent epistemic graphs** for collaboration
- **Formal verification** of claim consistency

---

**Remember:** Start simple, build incrementally. The power comes from consistent application over time, not complexity upfront.