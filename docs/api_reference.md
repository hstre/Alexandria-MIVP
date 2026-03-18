# API Reference

## Core Modules

### `alexandria_v2`
The core Alexandria Protocol implementation.

#### Classes

##### `AlexandriaStore`
Main store for managing epistemic patches and nodes.

```python
from alexandria_v2 import AlexandriaStore

store = AlexandriaStore()
```

**Methods:**

###### `checkout(branch_id: str) -> None`
Switch to a different branch.

**Parameters:**
- `branch_id`: Name of the branch to checkout

**Raises:**
- `KeyError` if branch doesn't exist

**Example:**
```python
store.checkout("main")
```

###### `create_branch(new_branch_id: str, from_patch_id: Optional[str] = None) -> None`
Create a new branch from current HEAD or specific patch.

**Parameters:**
- `new_branch_id`: Name for new branch
- `from_patch_id`: Optional patch ID to branch from (inclusive)

**Raises:**
- `ValueError` if branch already exists
- `KeyError` if `from_patch_id` not found

**Example:**
```python
store.create_branch("alternative_view")
store.create_branch("forked_view", from_patch_id="patch_123")
```

###### `submit(patch: Patch) -> str`
Submit a patch to the current branch.

**Parameters:**
- `patch`: Patch object to submit

**Returns:**
- `commit_hash`: SHA256 hash of the anchored patch

**Raises:**
- `AuditError` if patch fails validation
- `KeyError` if branch doesn't exist
- `AuditError` for non-monotonic timestamps or parent mismatch

**Example:**
```python
patch = Patch(
    patch_id="my_patch",
    parent_patch_id="previous_patch",
    branch_id="main",
    timestamp=1700000000,
    operation="ADD",
    target_id="claim_001",
    category="EMPIRICAL",
    payload={"content": "Observation", "assumptions": []},
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 0.1}
)
commit_hash = store.submit(patch)
```

###### `reconstruct(branch_id: str) -> Dict[str, Node]`
Rebuild graph state from patch chain with full integrity verification.

**Parameters:**
- `branch_id`: Branch to reconstruct

**Returns:**
- `Dict[str, Node]`: Dictionary of node_id → Node

**Raises:**
- `KeyError` if branch doesn't exist
- `AuditError` for integrity violations

**Example:**
```python
nodes = store.reconstruct("main")
for node_id, node in nodes.items():
    print(f"{node_id}: {node.content[:50]}...")
```

###### `get_node(node_id: str) -> Node`
Get a node by ID from current branch.

**Parameters:**
- `node_id`: Node identifier

**Returns:**
- `Node`: The requested node

**Raises:**
- `KeyError` if node doesn't exist

###### `list_nodes() -> List[str]`
List all node IDs in current branch.

**Returns:**
- `List[str]`: Sorted list of node IDs

###### `status_report() -> Dict[str, Any]`
Generate minimal epistemic status report for current branch.

**Returns:**
```python
{
    "branch": "main",
    "nodes": [
        {
            "id": "claim_001",
            "category": "EMPIRICAL",
            "deprecated": False,
            "stability": 0.85,
            "sigma": 0.05,
            "assumptions": ["temp_constant"],
            "lineage_len": 3
        }
    ]
}
```

##### `Patch`
Immutable state transition.

**Fields:**
- `patch_id: str` - Unique identifier
- `parent_patch_id: Optional[str]` - Previous patch in chain
- `branch_id: str` - Branch name
- `timestamp: int` - Unix timestamp
- `operation: str` - One of: "ADD", "MODIFY", "DEPRECATE", "BRANCH"
- `target_id: str` - Node ID (or patch_id for BRANCH)
- `category: str` - One of: "EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"
- `payload: Dict[str, Any]` - Node fields or operation details
- `audit: Dict[str, Any]` - Audit metadata (results, refs, notes)
- `uncertainty: Optional[Dict[str, Any]]` - Uncertainty metadata
- `chain: Optional[Dict[str, str]]` - commit_hash + previous_commit_hash

**Example:**
```python
from alexandria_v2 import Patch

patch = Patch(
    patch_id="research_001",
    parent_patch_id=None,
    branch_id="main",
    timestamp=1700000000,
    operation="ADD",
    target_id="hypothesis_001",
    category="SPECULATIVE",
    payload={
        "content": "Quantum supremacy within 5 years",
        "assumptions": ["error_correction_improves"]
    },
    audit={"validated": True, "decay": 0.02},
    uncertainty={"sigma": 0.3, "ci": [0.2, 0.8], "n": 50},
    chain=None
)
```

##### `Node`
Epistemic node representing a claim.

**Fields:**
- `node_id: str` - Unique identifier
- `category: str` - Epistemic category
- `content: str` - Claim content
- `assumptions: List[str]` - Underlying assumptions
- `uncertainty: Optional[Uncertainty]` - Uncertainty quantification
- `stability: float` - Stability score [0, 1]
- `deprecated: bool` - Whether node is deprecated
- `lineage: List[str]` - Patch IDs affecting this node

##### `Uncertainty`
Uncertainty quantification for claims.

**Fields:**
- `sigma: float` - Standard deviation
- `ci: Optional[Tuple[float, float]]` - Confidence interval
- `n: Optional[int]` - Sample size

#### Functions

##### `audit_patch(patch: Patch) -> None`
Structural admissibility checks for patches.

**Raises:**
- `AuditError` for invalid operations, categories, timestamps, etc.

##### `sha256_json(obj: Any) -> str`
Stable hash of JSON-serializable object.

##### `now_unix() -> int`
Current Unix timestamp.

##### `clamp01(x: float) -> float`
Clamp float to [0, 1] range.

---

### `mivp_impl`
MIVP v2.1 implementation with Appendix G compliance.

#### Classes

##### `AgentIdentity`
MIVP identity for an epistemic agent.

```python
from mivp_impl import AgentIdentity

identity = AgentIdentity(
    name="ResearchAssistant",
    model_path="models/research_v1.bin",
    model_bytes=b"...",
    system_prompt="You are a research assistant.",
    guardrails=[{"id": "no_harm", "rule": "Do not cause harm"}],
    temperature=0.7,
    top_p=0.9,
    max_tokens=2000,
    tooling_enabled=True,
    routing_mode="direct"
)
```

**Methods:**

###### `compute_mh() -> bytes`
Compute Model Hash (MH).

**Returns:**
- `bytes`: SHA256 hash of model weights via Merkle tree

**Example:**
```python
mh = identity.compute_mh()
print(f"MH: {mh.hex()[:16]}...")
```

###### `compute_ph() -> bytes`
Compute Policy Hash (PH).

**Returns:**
- `bytes`: SHA256 hash of canonical policy JSON

###### `compute_rh() -> bytes`
Compute Runtime Hash (RH).

**Returns:**
- `bytes`: SHA256 hash of canonical runtime configuration

###### `compute_cih(instance_epoch: Optional[int] = None) -> bytes`
Compute Composite Instance Hash (CIH).

**Parameters:**
- `instance_epoch`: Optional epoch for session continuity

**Returns:**
- `bytes`: SHA256(MH || PH || RH [|| instance_epoch])

**Example:**
```python
cih = identity.compute_cih()  # Without epoch
cih_session = identity.compute_cih(1700000000)  # With epoch
```

###### `get_identity_dict() -> Dict[str, Any]`
Get full identity information for inclusion in patches.

**Returns:**
```python
{
    "agent_name": "ResearchAssistant",
    "mh": "4f656b70d087942661166d7a311e3f0afde26c4b21729a8004cac46135480900",
    "ph": "4f081b3563cd5362763879f8b3256a77af438cd0d2ed4c935284f01f248cf86f",
    "rh": "827d100295de8a512a5d9a4138fadcdb5112d73e00dfd3fe163c142141d1faa0",
    "cih": "db1d84656d67f5026fd7271cb3b44cf0814f85cc6031381bd22326ac0af1ca41",
    "timestamp": 1700000000
}
```

#### Functions

##### `model_hash(file_path: str, file_bytes: bytes, chunk_size: int = 4 * 1024 * 1024) -> Tuple[bytes, bytes, int]`
Compute Model Hash for a file.

**Parameters:**
- `file_path`: Path identifier for the file
- `file_bytes`: File content as bytes
- `chunk_size`: Chunk size in bytes (default: 4MB)

**Returns:**
- `Tuple[bytes, bytes, int]`: (MH, merkle_root, total_leaves)

**Example:**
```python
mh, root, leaves = model_hash(
    "models/research_v1.bin",
    model_bytes,
    chunk_size=16
)
```

##### `policy_hash(canonical_policy_json: str) -> bytes`
Compute Policy Hash from canonical JSON.

**Parameters:**
- `canonical_policy_json`: Canonicalized policy JSON string

**Returns:**
- `bytes`: SHA256 hash

##### `canonicalize_policy(system_prompt: str, guardrails: List[Dict[str, str]], moderation_policy_version: str, policy_spec_version: str, attestation_completeness: str) -> str`
Create canonical policy JSON per Appendix B.

**Parameters:**
- `system_prompt`: LLM system prompt
- `guardrails`: List of {"id": "...", "rule": "..."}
- `moderation_policy_version`: Version string
- `policy_spec_version`: Version string
- `attestation_completeness`: "full" or "partial"

**Returns:**
- `str`: Canonical JSON string

##### `runtime_hash(canonical_runtime_json: str) -> bytes`
Compute Runtime Hash from canonical JSON.

##### `canonicalize_runtime(temperature: float, top_p: float, max_tokens: int, tooling_enabled: bool, routing_mode: str, runtime_spec_version: str) -> str`
Create canonical runtime JSON per Appendix D with CFS-1 floats.

##### `composite_instance_hash(mh: bytes, ph: bytes, rh: bytes, instance_epoch: Optional[int] = None) -> bytes`
Compute Composite Instance Hash from component hashes.

**Parameters:**
- `mh`: Model Hash bytes
- `ph`: Policy Hash bytes
- `rh`: Runtime Hash bytes
- `instance_epoch`: Optional epoch integer

**Returns:**
- `bytes`: SHA256(MH || PH || RH [|| u64be(epoch)])

##### `verify(label: str, computed: bytes, expected_hex: str) -> bool`
Verify test vector compliance.

##### `run_test_vectors() -> bool`
Run all Appendix G test vectors.

**Returns:**
- `bool`: True if all vectors pass

---

### `alexandria_mivp`
Integrated Alexandria + MIVP store.

#### Classes

##### `AlexandriaMIVPStore`
Alexandria Store with MIVP identity verification.

```python
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity

identity = AgentIdentity(name="MyAgent", ...)
store = AlexandriaMIVPStore(identity)
```

**Methods:**

###### `submit_with_identity(patch: Patch, instance_epoch: Optional[int] = None) -> str`
Submit a patch with MIVP identity verification.

**Parameters:**
- `patch`: Patch to submit
- `instance_epoch`: Optional epoch for session continuity

**Returns:**
- `commit_hash`: SHA256 hash of anchored patch

**Adds to patch.audit:**
```python
{
    "mivp_identity": {
        "agent_name": "MyAgent",
        "mh": "...",
        "ph": "...",
        "rh": "...",
        "cih": "...",
        "timestamp": 1700000000,
        "instance_epoch": 1700000000  # optional
    }
}
```

###### `verify_patch_identity(patch: Patch) -> bool`
Verify that patch's claimed identity matches computed identity.

**Parameters:**
- `patch`: Patch to verify

**Returns:**
- `bool`: True if identity is valid and matches

**Example:**
```python
if store.verify_patch_identity(patch):
    print("Patch identity verified")
else:
    print("WARNING: Identity mismatch!")
```

###### `reconstruct_with_identity_verification(branch_id: str) -> Dict[str, Node]`
Reconstruct graph while verifying all patch identities.

**Parameters:**
- `branch_id`: Branch to reconstruct

**Returns:**
- `Dict[str, Node]`: Reconstructed nodes

**Raises:**
- `AuditError` if any identity verification fails

**Example:**
```python
try:
    nodes = store.reconstruct_with_identity_verification("main")
    print("All patch identities verified")
except AuditError as e:
    print(f"Identity verification failed: {e}")
```

## Constants

### `CATEGORIES`
Valid epistemic categories:
```python
CATEGORIES = {"EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"}
```

### `OPS`
Valid patch operations:
```python
OPS = {"ADD", "MODIFY", "DEPRECATE", "BRANCH"}
```

## Exceptions

### `AuditError`
Raised for structural admissibility violations.

## Examples

### Basic Usage
```python
from alexandria_v2 import AlexandriaStore, Patch

store = AlexandriaStore()
store.checkout("main")

patch = Patch(
    patch_id="claim_001",
    parent_patch_id=None,
    branch_id="main",
    timestamp=1700000000,
    operation="ADD",
    target_id="observation_001",
    category="EMPIRICAL",
    payload={"content": "Observation", "assumptions": []},
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 0.1}
)

commit_hash = store.submit(patch)
print(f"Patch submitted: {commit_hash}")
```

### MIVP Identity
```python
from mivp_impl import AgentIdentity

identity = AgentIdentity(
    name="EpistemicWilly",
    model_path="models/willy_v1.bin",
    model_bytes=b"...",
    system_prompt="Epistemic consistency architect.",
    guardrails=[{"id": "epistemic_honesty", "rule": "Maintain integrity"}],
    temperature=0.7,
    top_p=0.9,
    max_tokens=4000,
    tooling_enabled=True,
    routing_mode="direct"
)

cih = identity.compute_cih()
print(f"My CIH: {cih.hex()}")
```

### Integrated Usage
```python
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from alexandria_v2 import Patch

# Create identity
identity = AgentIdentity(name="ResearchAgent", ...)

# Create store with identity
store = AlexandriaMIVPStore(identity)
store.checkout("main")

# Submit patch with identity
patch = Patch(...)
commit_hash = store.submit_with_identity(patch)

# Verify reconstruction
nodes = store.reconstruct_with_identity_verification("main")
print(f"Verified {len(nodes)} nodes")
```

## Testing

### Run Compliance Tests
```bash
pytest tests/
```

### Check Implementation
```python
from mivp_impl import run_test_vectors

if run_test_vectors():
    print("MIVP compliant")
else:
    print("MIVP non-compliant")
```

---

## `audit_gate` – Extended Audit Gate

Drei-Schichten-Validierung für Patches: semantisch, Quell-Verifikation, Temporal Reasoning.

### Classes

#### `AuditGateConfig`

Konfigurationsdatenklasse mit allen einstellbaren Schwellwerten.

```python
from audit_gate import AuditGateConfig

cfg = AuditGateConfig(
    min_content_length=10,
    max_content_length=50_000,
    require_sources_for_empirical=True,
    max_future_drift_seconds=300,
)
```

**Key fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `min_content_length` | `5` | Minimum content length |
| `max_content_length` | `100_000` | Maximum content length |
| `require_sources_for_empirical` | `True` | EMPIRICAL patches need sources |
| `min_source_count` | `1` | Minimum number of sources |
| `max_future_drift_seconds` | `600` | Max allowed future timestamp drift |
| `require_monotonic_timestamps` | `True` | Timestamps must not go backwards |

#### `Severity`

```python
class Severity(str, Enum):
    ERROR   = "error"
    WARNING = "warning"
```

#### `AuditViolation`

```python
@dataclass
class AuditViolation:
    code: str       # e.g. "SEM001", "SRC003", "TMP005"
    message: str
    severity: Severity
    field: str      # affected field name
```

#### `AuditReport`

```python
@dataclass
class AuditReport:
    patch_id: str
    passed: bool
    violations: List[AuditViolation]

    def errors(self) -> List[AuditViolation]: ...
    def warnings(self) -> List[AuditViolation]: ...
    def raise_if_failed(self) -> None: ...  # raises AuditError
```

#### `AuditGate`

```python
gate = AuditGate(config=AuditGateConfig())

report = gate.validate(patch)           # returns AuditReport
gate.validate_strict(patch)            # raises AuditError on failure
```

**Methods:**

| Method | Description |
|--------|-------------|
| `validate(patch, branch_last_timestamp)` | Full validation, returns `AuditReport` |
| `validate_strict(patch, ...)` | Like `validate`, raises `AuditError` on failure |

### Factory Functions

```python
from audit_gate import make_default_gate, make_strict_empirical_gate

gate = make_default_gate()           # lenient defaults
gate = make_strict_empirical_gate()  # strict: sources required, short TTL
```

### Violation Codes

| Code | Layer | Meaning |
|------|-------|---------|
| SEM001 | Semantic | Content too short |
| SEM002 | Semantic | Content too long |
| SEM003 | Semantic | Placeholder text detected |
| SEM004 | Semantic | Excessive repetition |
| SEM005 | Semantic | Assumptions missing for MODEL/SPECULATIVE |
| SEM006–009 | Semantic | Category-specific field checks |
| SRC001 | Source | No sources provided |
| SRC002 | Source | Source URL format invalid |
| SRC003 | Source | Duplicate sources |
| SRC004–006 | Source | Source count out of range |
| TMP001 | Temporal | Timestamp implausibly old |
| TMP002 | Temporal | Timestamp in the future |
| TMP003 | Temporal | Non-monotonic timestamp |
| TMP004–008 | Temporal | Scope and anachronism checks |

---

## `uncertainty_propagator` – Uncertainty Propagation

Propagiert Unsicherheit über einen DAG von Claims.

### Classes

#### `PropagationMode`

```python
class PropagationMode(str, Enum):
    SUM_IN_QUADRATURE = "sum_in_quadrature"  # √(σ₁² + σ₂²)
    WEIGHTED_MEAN     = "weighted_mean"
    MAX               = "max"
    MEAN              = "mean"
    LINEAR            = "linear"             # Σ σᵢ
```

#### `PropagationResult`

```python
@dataclass
class PropagationResult:
    node_id: str
    local_sigma: float          # sigma of this node alone
    propagated_sigma: float     # combined sigma from upstream
    combined_sigma: float       # final combined value
    depth: int                  # -1 for cycle nodes
    contributing_nodes: List[str]
    ci: Tuple[float, float]
    n: int
```

#### `PropagationReport`

```python
@dataclass
class PropagationReport:
    results: Dict[str, PropagationResult]
    mode: PropagationMode
    decay_factor: float
    nodes_processed: int
    nodes_skipped_cycle: int
    cycles: List[List[str]]
```

#### `UncertaintyPropagator`

```python
propagator = UncertaintyPropagator()

# Manual registration
propagator.register_dependency(dependent_id="B", dependency_id="A")

# Build from store patches (reads patch.payload["depends_on"])
propagator.build_from_patches(nodes, patches)

# Run propagation
report = propagator.propagate(mode=PropagationMode.SUM_IN_QUADRATURE, decay=0.9)

# Utilities
cycles = propagator.detect_cycles()
depth = propagator.dependency_depth("node_id")
top5 = propagator.most_uncertain_nodes(n=5)
summary = propagator.uncertainty_summary()
```

**Declaring dependencies in patches:**
```python
patch = Patch(..., payload={"content": "...", "depends_on": ["node_a", "node_b"]})
```

---

## `cross_agent_graph` – Cross-Agent Epistemic Graphs

Gemeinsamer epistemischer Graph über mehrere Agenten.

### Classes

#### `EdgeType`

```python
class EdgeType(str, Enum):
    SUPPORTS     = "supports"
    CHALLENGES   = "challenges"
    REFINES      = "refines"
    DEPENDS_ON   = "depends_on"
    DERIVED_FROM = "derived_from"
```

#### `ClaimNode`

```python
@dataclass
class ClaimNode:
    claim_id: str
    agent_name: str
    content: str
    category: str     # EMPIRICAL | NORMATIVE | MODEL | SPECULATIVE
    sigma: float
    timestamp: int
    metadata: Dict[str, Any]
```

#### `GraphEdge`

```python
@dataclass
class GraphEdge:
    source_claim_id: str
    target_claim_id: str
    edge_type: EdgeType
    agent_name: str
    weight: float        # 0.0–1.0
    timestamp: int
    metadata: Dict[str, Any]
```

#### `CrossAgentGraph`

```python
graph = CrossAgentGraph()

# Add claims
graph.add_claim("agent_a", "c1", "CO2 is rising.", "EMPIRICAL", sigma=0.1)
graph.add_claim("agent_b", "c2", "Temperature rising.", "EMPIRICAL", sigma=0.2)

# Add edges
graph.add_edge("agent_a", "c1", "c2", EdgeType.SUPPORTS, weight=0.9)

# Query
neighbors = graph.neighbors("c1")
paths = graph.paths_between("c1", "c3", max_depth=5)
shortest = graph.shortest_path("c1", "c3")

# Conflict detection
conflicts = graph.find_conflicts()
for conflict in conflicts:
    print(conflict.conflict_type, conflict.agent_a, "↔", conflict.agent_b)

# Summary & export
summary = graph.summary()
data = graph.to_dict()
graph2 = CrossAgentGraph.from_dict(data)

# Integration with store
n_added = graph.build_from_store(store, branch_id="main", agent_name="agent_a")
```

**Methods:**

| Method | Description |
|--------|-------------|
| `add_claim(agent, id, content, category, sigma)` | Register a claim node |
| `remove_claim(claim_id)` | Remove node and all adjacent edges |
| `add_edge(agent, src, tgt, type, weight)` | Add directed edge (both nodes must exist) |
| `remove_edges(src, tgt, edge_type)` | Remove matching edges |
| `get_claims_by_agent(agent_name)` | All claims of one agent |
| `get_claims_by_category(category)` | All claims of one category |
| `neighbors(claim_id, edge_type)` | Outgoing neighbors |
| `predecessors(claim_id, edge_type)` | Incoming neighbors |
| `paths_between(start, end, max_depth)` | All simple paths (BFS) |
| `shortest_path(start, end)` | Shortest BFS path |
| `find_conflicts()` | Direct + cross-agent CHALLENGES conflicts |
| `agent_contributions()` | Per-agent claim/edge statistics |
| `summary()` | Aggregated graph statistics |
| `to_dict()` / `from_dict(d)` | JSON export / import |
| `build_from_store(store, branch_id, agent_name)` | Load from AlexandriaMIVPStore |

---

## `performance` – Performance Optimizations

Caching und Batch-Verarbeitung für Alexandria-Stores.

### Classes

#### `NodeCache`

LRU-Cache für rekonstruierte Node-Zustände. Key: `(branch_id, last_patch_id)`.

```python
from performance import NodeCache

cache = NodeCache(max_size=256)

# Direct API
cache.put("main", "patch_id_123", nodes_dict)
nodes = cache.get("main", "patch_id_123")  # None on miss

# Convenience
nodes = cache.get_or_compute(
    "main", store.get_last_patch_id("main"),
    lambda: store.reconstruct("main")
)

# Invalidate on branch change
cache.invalidate("main")

print(cache.stats())   # size, hits, misses, hit_rate
```

#### `QueryCache`

TTL-basierter Cache für beliebige Query-Ergebnisse.

```python
from performance import QueryCache

cache = QueryCache(ttl=60.0, max_size=512)

cache.put("my_key", result)
result = cache.get("my_key")   # None if expired or missing

# Decorator usage
@cache.cached
def expensive_query(branch_id, filter):
    return store.get_patches_by_cih(filter)

# Maintenance
expired = cache.evict_expired()
```

#### `BatchProcessor`

Parallelisierte Patch-Einreichung.

```python
from performance import BatchProcessor

processor = BatchProcessor(store, max_workers=4)

# Parallel (thread-safe stores)
report = processor.submit_batch(patches)

# Sequential (for non-thread-safe stores)
report = processor.submit_batch_sequential(patches)

print(f"{report.succeeded}/{report.total} patches in {report.total_duration_ms:.1f}ms")
print(f"{report.patches_per_second:.0f} patches/s")
```

**`BatchReport` fields:** `total`, `succeeded`, `failed`, `results`, `total_duration_ms`, `patches_per_second`

**`BatchResult` fields:** `patch_id`, `success`, `commit_hash`, `error`, `duration_ms`

#### `PerformanceMonitor`

Zeitmessung für beliebige Operationen.

```python
from performance import PerformanceMonitor

monitor = PerformanceMonitor()

with monitor.measure("reconstruct"):
    nodes = store.reconstruct("main")

monitor.record("manual_op", duration_ms=42.5)

stats = monitor.stats_for("reconstruct")
# {"count": 1, "min_ms": ..., "max_ms": ..., "mean_ms": ..., "total_ms": ...}

print(monitor.report())   # formatted text report
monitor.reset()
```

---

## `distributed_store` – Distributed Storage Backend

Abstraktes Backend-Interface mit mehreren Implementierungen.

### Backend Interface

```python
from distributed_store import DistributedBackend, StoredObject, StorageError

class DistributedBackend(ABC):
    def save(self, key, data, metadata=None) -> StoredObject: ...
    def load(self, key) -> StoredObject: ...       # raises StorageError if missing
    def exists(self, key) -> bool: ...
    def delete(self, key) -> bool: ...
    def list_keys(self, prefix="") -> List[str]: ...
    def health(self) -> BackendHealth: ...
```

### `StoredObject`

```python
@dataclass
class StoredObject:
    key: str
    data: bytes
    content_hash: str    # SHA-256 hex
    timestamp: float
    metadata: Dict[str, str]
```

### `InMemoryBackend`

Thread-sicherer Dict-Speicher (Referenzimplementierung, ideal für Tests).

```python
from distributed_store import InMemoryBackend

backend = InMemoryBackend()
obj = backend.save("patches/p1", data_bytes)
obj = backend.load("patches/p1")
```

### `S3Backend`

AWS S3 / MinIO-kompatibler Object Store. Benötigt `boto3` im Produktionseinsatz.

```python
from distributed_store import S3Backend

# Production
backend = S3Backend(bucket="my-bucket", prefix="alexandria/", region="eu-central-1")

# Mock mode (no boto3 needed)
backend = S3Backend(bucket="test", mock=True)

# Custom endpoint (MinIO)
backend = S3Backend(bucket="test", endpoint_url="http://localhost:9000", mock=False)
```

### `IPFSBackend`

IPFS Content-Addressed Storage. Benötigt einen laufenden IPFS-Node.

```python
from distributed_store import IPFSBackend

backend = IPFSBackend(api_url="http://127.0.0.1:5001")  # production
backend = IPFSBackend(mock=True)                         # mock mode

obj = backend.save("doc1", b"content")
cid = backend.get_cid("doc1")   # returns IPFS Content Identifier
```

> **Hinweis:** IPFS ist immutable – `delete()` entfernt nur den lokalen Index-Eintrag, nicht die Daten aus dem Netzwerk.

### `DistributedLedgerBackend`

Append-Only Log mit kryptographischer Kettenverknüpfung.

```python
from distributed_store import DistributedLedgerBackend, InMemoryBackend

ledger = DistributedLedgerBackend(underlying=InMemoryBackend())
ledger.save("patch/p1", data)
ledger.save("patch/p2", data)

entries = ledger.get_ledger()
# [LedgerEntry(sequence=0, key="patch/p1", content_hash=..., previous_hash="0"*64, ...), ...]

ok, reason = ledger.verify_chain()
# (True, None) if valid
```

### `MultiBackend`

Schreibt in alle Backends, liest vom ersten verfügbaren (Redundanz).

```python
from distributed_store import MultiBackend, InMemoryBackend

multi = MultiBackend(
    backends=[primary_backend, replica_backend],
    read_primary_only=False,  # fallback to replicas on read failure
)

healths = multi.health_all()
```

### `DistributedAlexandriaStore`

High-Level-Wrapper für Patch/Branch-Speicherung über ein Backend.

```python
from distributed_store import DistributedAlexandriaStore, InMemoryBackend

store = DistributedAlexandriaStore(backend=InMemoryBackend(), namespace="myproject/")

store.save_patch(patch)
patch_dict = store.load_patch_dict("patch_id")
store.save_branch_manifest("main", ["p1", "p2", "p3"])
patch_ids = store.load_branch_manifest("main")

# Node snapshots (performance caching)
store.save_node_snapshot("main", "node_id", node_dict)
node_dict = store.load_node_snapshot("main", "node_id")

patches = store.list_patches()
branches = store.list_branches()
health = store.health()
```

---

## `formal_verification` – Formal Verification Framework

Formale Verifikation epistemischer Eigenschaften eines Alexandria-Stores.

### Classes

#### `VerificationStatus`

```python
class VerificationStatus(str, Enum):
    PASSED  = "passed"
    FAILED  = "failed"
    SKIPPED = "skipped"
    ERROR   = "error"
```

#### `PropertyResult`

```python
PropertyResult.ok(message, witnesses=None)
PropertyResult.fail(message, counterexamples=None)
PropertyResult.skip(reason)
PropertyResult.error(message)
```

#### `VerificationReport`

```python
report.passed        # List[VerificationResult] – only PASSED
report.failed        # List[VerificationResult] – only FAILED
report.errors        # List[VerificationResult] – only ERROR
report.is_fully_verified  # bool: no failures and no errors
report.summary()     # Dict with counts and totals
```

#### `EpistemicVerifier`

```python
from formal_verification import EpistemicVerifier

verifier = EpistemicVerifier(store)

# Verify a full branch
report = verifier.verify_branch("main")

# Filter by tag
report = verifier.verify_branch("main", tags=["integrity"])

# Skip specific checks
report = verifier.verify_branch("main", skip=["chain_integrity"])

# Verify all branches at once
reports = verifier.verify_all_branches()

# Quick patch pre-check (invariants only)
results = verifier.verify_patch(patch, nodes)

# List all registered checks
props = verifier.list_properties()
```

### Built-in Invariants

| Name | Description |
|------|-------------|
| `no_dangling_references` | All `parent_patch_id` references must point to existing patches |
| `monotonic_timestamps` | Timestamps must be monotonically non-decreasing |
| `valid_operations` | All operations must be ADD / MODIFY / DEPRECATE |
| `valid_categories` | All categories must be EMPIRICAL / NORMATIVE / MODEL / SPECULATIVE |

### Built-in Properties

| Name | Tags | Description |
|------|------|-------------|
| `chain_integrity` | integrity | Patch chain must be linear and acyclic |
| `unique_patch_ids` | integrity | Patch IDs must be unique within a branch |
| `sigma_in_range` | uncertainty | All sigma values must be in [0, 1] |
| `content_not_empty` | completeness | All active nodes must have non-empty content |
| `no_deprecated_without_add` | consistency | DEPRECATE patches must only target previously ADDed nodes |
| `assumptions_for_speculative` | completeness, epistemics | SPECULATIVE/MODEL nodes must have assumptions |

### Custom Properties

```python
# Functional API
def my_check(nodes, patches) -> PropertyResult:
    if all(n.sigma < 0.5 for n in nodes.values()):
        return PropertyResult.ok("All sigmas below threshold.")
    return PropertyResult.fail("High-uncertainty nodes found.",
                               counterexamples=[nid for nid, n in nodes.items() if n.sigma >= 0.5])

verifier.add_property("low_sigma", "All nodes have sigma < 0.5", my_check, tags=["quality"])

# Decorator API
@verifier.property("always_ok", tags=["custom"])
def always_ok(nodes, patches):
    return PropertyResult.ok()
```

---

## `sqlite_store` – SQLite Persistence with Identity Queries

### `AlexandriaSQLiteMIVPStore`

Persistenter Store mit SQLite-Backend und erweiterten Identity-Abfragen.

```python
from sqlite_store import AlexandriaSQLiteMIVPStore
from alexandria_mivp import AgentIdentity

identity = AgentIdentity(name="MyAgent", ...)
store = AlexandriaSQLiteMIVPStore(":memory:", agent_identity=identity)
store.checkout("main")

# Submit with identity (stores CIH, MH, PH, RH, rh_extended_json)
store.submit_with_identity(patch)
```

**Identity Query Methods:**

| Method | Description |
|--------|-------------|
| `get_all_agents()` | All distinct agent names |
| `count_patches_by_agent(agent_name)` | Patch count for one agent |
| `get_patches_by_cih(cih_hex)` | All patches with given CIH |
| `get_patches_by_mh(mh_hex)` | All patches with given model hash |
| `get_patches_in_epoch_range(start, end)` | Patches within epoch range |
| `get_agent_statistics(agent_name)` | Full stats dict for agent |
| `find_identity_drift(agent_name)` | Detect CIH changes over time |
| `get_identity_timeline(agent_name)` | Ordered identity history |
| `find_unverified_patches()` | Patches with `audit.validated=False` |
| `find_patches_with_extended_rh()` | Patches using Extended Runtime Hash |

**Extended Runtime Hash (three-layer):**

```python
identity = AgentIdentity(
    name="SecureAgent",
    ...,
    use_extended_runtime_hash=True,
    # Environment layer
    container_digest="sha256:abc123",
    python_version="3.11.0",
    dependency_hash="sha256:def456",
    # Attestation layer
    tee_type="sgx",
    tpm_quote="base64_quote_here",
    attestation_spec_version="1.0",
)
# identity.get_identity_dict() includes "rh_extended": {config_h, env_h, attest_h}
```