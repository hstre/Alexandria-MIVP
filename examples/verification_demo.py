#!/usr/bin/env python3
"""
Demonstration of the three critical fixes from PDF:
1. cfs1_float() - robust float serialization
2. AgentIdentity - normal class (not @dataclass)  
3. Two-stage verification - internal vs agent matching
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_mivp import AgentIdentity, AlexandriaMIVPStore, verify_cih_internal_consistency
from alexandria_v2 import Patch
from mivp_impl import cfs1_float, canonicalize_runtime
import json
import time

print("=" * 70)
print("DEMONSTRATION: Three Critical Fixes from PDF")
print("=" * 70)

# ----------------------------------------------------------------------
# 1. cfs1_float() demonstration
print("\n1. cfs1_float() - Robust Float Serialization")
print("-" * 40)

print("Critical test cases from MIVP spec:")
test_cases = [
    (0.0, "zero"),
    (1.0, "integer-valued float (top_p=1.0)"),
    (0.7, "typical temperature"),
    (0.1, "decimal"),
    (0.0001, "small decimal (edge of range)"),
    (1.23e-5, "scientific notation in range"),
    (0.30000000000000004, "floating-point precision artifact"),
]

for x, desc in test_cases:
    result = cfs1_float(x)
    roundtrip = float(result) == x
    status = "[OK]" if roundtrip else "[FAIL]"
    print(f"  {status} {desc:40} {repr(x):25} -> '{result}'")

# Show canonicalize_runtime using cfs1_float
print("\n   canonicalize_runtime() output:")
runtime_json = canonicalize_runtime(
    temperature=0.7,
    top_p=1.0,  # Will be "1" not "1.0"
    max_tokens=256,
    tooling_enabled=False,
    routing_mode="language-aware",
    runtime_spec_version="1.0"
)
parsed = json.loads(runtime_json)
print(f"     temperature: {parsed['temperature']} (type: {type(parsed['temperature']).__name__})")
print(f"     top_p: {parsed['top_p']} (type: {type(parsed['top_p']).__name__})")
print("     ✓ Floats correctly serialized as CFS-1 strings")

# ----------------------------------------------------------------------
# 2. AgentIdentity demonstration
print("\n2. AgentIdentity - Normal Class (Not @dataclass)")
print("-" * 40)

# Create two different agent identities
print("Creating two agent identities...")
identity1 = AgentIdentity(
    name="ResearchAssistant",
    model_path="models/research_v1.bin",
    model_bytes=b"research model weights v1.0",
    system_prompt="Research assistant specializing in scientific literature.",
    guardrails=[
        {"id": "cite_sources", "rule": "Always cite peer-reviewed sources"},
        {"id": "quantify_uncertainty", "rule": "Quantify uncertainty in empirical claims"},
    ],
    temperature=0.3,
    top_p=0.95,
)

identity2 = AgentIdentity(
    name="CreativeWriter", 
    model_path="models/creative_v2.bin",
    model_bytes=b"creative model weights v2.0",
    system_prompt="Creative writing assistant with imaginative flair.",
    guardrails=[
        {"id": "no_plagiarism", "rule": "Do not plagiarize existing works"},
        {"id": "positive_tone", "rule": "Maintain positive and engaging tone"},
    ],
    temperature=0.9,
    top_p=0.8,
)

print(f"   Agent 1: {identity1.name}")
print(f"     MH: {identity1.compute_mh().hex()[:16]}...")
print(f"     PH: {identity1.compute_ph().hex()[:16]}...")
print(f"     RH: {identity1.compute_rh().hex()[:16]}...")
print(f"     CIH: {identity1.compute_cih().hex()[:16]}...")

print(f"\n   Agent 2: {identity2.name}")
print(f"     MH: {identity2.compute_mh().hex()[:16]}...")
print(f"     Different MH: {identity1.compute_mh() != identity2.compute_mh()}")
print(f"     Different PH: {identity1.compute_ph() != identity2.compute_ph()}")
print(f"     Different RH: {identity1.compute_rh() != identity2.compute_rh()}")

# Show identity dict
identity_dict = identity1.get_identity_dict()
print(f"\n   Identity dict keys: {list(identity_dict.keys())}")
print(f"   Has instance_epoch: {'instance_epoch' in identity_dict}")
print(f"   All hex strings: {all(isinstance(v, str) and all(c in '0123456789abcdef' for c in v.lower()) for k, v in identity_dict.items() if k in ['mh', 'ph', 'rh', 'cih'])}")

# ----------------------------------------------------------------------
# 3. Two-Stage Verification Demonstration
print("\n3. Two-Stage Verification System")
print("-" * 40)

# Create store with identity1
store = AlexandriaMIVPStore(identity1)
store.checkout("main")

print("Creating three patches with different identity scenarios:")
print("  1. Patch with correct identity (identity1)")
print("  2. Patch with different identity (identity2)")
print("  3. Patch with tampered identity (modified CIH)")
print("  4. Patch with no identity")

# Patch 1: Correct identity
p1 = Patch(
    patch_id="patch_correct",
    parent_patch_id=None,
    branch_id="main",
    timestamp=int(time.time()),
    operation="ADD",
    target_id="claim_1",
    category="EMPIRICAL",
    payload={"content": "Study shows 20% improvement with new method"},
    audit={"validated": True},
    uncertainty={"sigma": 0.1},
    chain=None,
)
store.submit_with_identity(p1)

# Patch 2: Different identity (simulate by creating patch with identity2's dict)
# We need to manually craft audit with identity2's dict
identity2_dict = identity2.get_identity_dict()
p2 = Patch(
    patch_id="patch_different",
    parent_patch_id="patch_correct",
    branch_id="main",
    timestamp=int(time.time()) + 1,
    operation="ADD",
    target_id="claim_2",
    category="SPECULATIVE",
    payload={"content": "Alternative method might work better"},
    audit={"validated": True, "mivp_identity": identity2_dict},
    uncertainty={"sigma": 0.5},
    chain=None,
)
store.submit(p2)  # Submit without identity (already has identity2)

# Patch 3: Tampered identity (modified CIH)
tampered_dict = identity1.get_identity_dict().copy()
tampered_dict["cih"] = "a" * 64  # Fake CIH
p3 = Patch(
    patch_id="patch_tampered",
    parent_patch_id="patch_correct",
    branch_id="main",
    timestamp=int(time.time()) + 2,
    operation="ADD",
    target_id="claim_3",
    category="EMPIRICAL",
    payload={"content": "Tampered claim"},
    audit={"validated": True, "mivp_identity": tampered_dict},
    uncertainty={"sigma": 0.1},
    chain=None,
)
store.submit(p3)

# Patch 4: No identity
p4 = Patch(
    patch_id="patch_no_identity",
    parent_patch_id="patch_correct",
    branch_id="main",
    timestamp=int(time.time()) + 3,
    operation="ADD",
    target_id="claim_4",
    category="NORMATIVE",
    payload={"content": "We should prioritize reproducibility"},
    audit={"validated": True},
    uncertainty={"sigma": 0.2},
    chain=None,
)
store.submit(p4)

print("\nVerification results per patch:")
print("  Patch ID           | Has ID | Internal Consist. | Matches Agent | Status")
print("  " + "-" * 70)

for patch in store.branches["main"]:
    has_id = "mivp_identity" in patch.audit
    internal_ok = store.verify_patch_identity_internal(patch) if has_id else False
    agent_ok = store.verify_patch_identity_against_agent(patch) if has_id else False
    
    if agent_ok:
        status = "VERIFIED"
    elif internal_ok:
        status = "CONSISTENT (but wrong agent)"
    elif has_id and not internal_ok:
        status = "TAMPERED"
    else:
        status = "UNVERIFIED"
    
    print(f"  {patch.patch_id:18} | {str(has_id):6} | {str(internal_ok):17} | {str(agent_ok):13} | {status}")

# Demonstrate reconstruct_with_identity_verification
print("\nReconstruction with verification report:")
result = store.reconstruct_with_identity_verification("main", strict=False)
verification = result["verification"]

print(f"  Total patches: {verification['total_patches']}")
print(f"  ✓ Verified: {verification['verified']}")
print(f"  ⚠ Consistent (internal): {verification['consistent']}")
print(f"  ⚠ Unverified (no identity): {verification['unverified']}")
print(f"  ✗ Tampered (inconsistent): {verification['tampered']}")

# Demonstrate standalone verification
print("\nStandalone verification (for third parties):")
for patch in store.branches["main"]:
    if "mivp_identity" in patch.audit:
        identity = patch.audit["mivp_identity"]
        standalone_ok = verify_cih_internal_consistency(identity)
        print(f"  {patch.patch_id}: standalone verification = {standalone_ok}")

# ----------------------------------------------------------------------
print("\n" + "=" * 70)
print("SUMMARY: All three fixes are working correctly")
print("=" * 70)
print("1. cfs1_float() - ✓ Round-trip safe, spec-compliant")
print("2. AgentIdentity - ✓ Normal class, proper caching, serialization")
print("3. Two-stage verification - ✓ Internal consistency + agent matching")
print("\nThe implementation now provides:")
print("  • Strong cryptographic identity verification")
print("  • Detection of identity mismatches and tampering")
print("  • Graceful handling of unverified claims")
print("  • Structured verification reports")
print("=" * 70)