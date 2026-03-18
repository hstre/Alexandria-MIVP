#!/usr/bin/env python3
"""
Simple demonstration of the three fixes - ASCII only.
"""
from alexandria_mivp import (
    AgentIdentity, AlexandriaMIVPStore, verify_cih_internal_consistency,
    Patch, canonicalize_runtime,
)
from alexandria_mivp.mivp_impl import cfs1_float
import json
import time

print("=" * 70)
print("SIMPLE DEMO: Three Critical Fixes")
print("=" * 70)

# ----------------------------------------------------------------------
# 1. cfs1_float()
print("\n1. cfs1_float() - Float Serialization Fix")
print("-" * 40)

cases = [(0.0, "0"), (1.0, "1"), (0.7, "0.7"), (0.1, "0.1")]
all_ok = True
for x, expected in cases:
    result = cfs1_float(x)
    ok = result == expected
    rt = float(result) == x
    print(f"  {x} -> '{result}' (expected '{expected}') {'PASS' if ok and rt else 'FAIL'}")
    if not ok or not rt:
        all_ok = False

print("\n  canonicalize_runtime test:")
runtime = canonicalize_runtime(temperature=0.7, top_p=1.0, max_tokens=256,
                               tooling_enabled=False, routing_mode="test",
                               runtime_spec_version="1.0")
parsed = json.loads(runtime)
print(f"    temperature: {parsed['temperature']} ({type(parsed['temperature']).__name__})")
print(f"    top_p: {parsed['top_p']} ({type(parsed['top_p']).__name__})")
if isinstance(parsed['temperature'], str) and parsed['temperature'] == '0.7':
    print("    PASS: temperature serialized correctly")
else:
    print("    FAIL: temperature serialization issue")
    all_ok = False

# ----------------------------------------------------------------------
# 2. AgentIdentity
print("\n2. AgentIdentity - Class Fix")
print("-" * 40)

identity = AgentIdentity(
    name="TestAgent",
    model_path="test.bin",
    model_bytes=b"test data",
    system_prompt="test",
    guardrails=[],
    temperature=0.7,
    top_p=0.9,
)

print(f"  Created: {identity.name}")
print(f"  MH: {identity.compute_mh().hex()[:8]}...")
print(f"  PH: {identity.compute_ph().hex()[:8]}...")
print(f"  RH: {identity.compute_rh().hex()[:8]}...")

identity_dict = identity.get_identity_dict()
print(f"  Identity dict has mh/ph/rh/cih: {'mh' in identity_dict and 'ph' in identity_dict and 'rh' in identity_dict and 'cih' in identity_dict}")
print(f"  Matches self: {identity.matches_identity_dict(identity_dict)}")
print(f"  Internal consistency: {verify_cih_internal_consistency(identity_dict)}")

if (identity.matches_identity_dict(identity_dict) and 
    verify_cih_internal_consistency(identity_dict)):
    print("  PASS: AgentIdentity works correctly")
else:
    print("  FAIL: AgentIdentity issue")
    all_ok = False

# ----------------------------------------------------------------------
# 3. Two-Stage Verification
print("\n3. Two-Stage Verification")
print("-" * 40)

store = AlexandriaMIVPStore(identity)
store.checkout("main")

# Create patches with different identity scenarios
p1 = Patch(
    patch_id="p1",
    parent_patch_id=None,
    branch_id="main",
    timestamp=int(time.time()),
    operation="ADD",
    target_id="claim1",
    category="EMPIRICAL",
    payload={"content": "Claim with correct identity"},
    audit={"validated": True},
    uncertainty={"sigma": 0.1},
    chain=None,
)
store.submit_with_identity(p1)

# Different identity (fake)
fake_dict = identity.get_identity_dict().copy()
fake_dict["cih"] = "a" * 64
p2 = Patch(
    patch_id="p2",
    parent_patch_id="p1",
    branch_id="main",
    timestamp=int(time.time()) + 1,
    operation="ADD",
    target_id="claim2",
    category="EMPIRICAL",
    payload={"content": "Claim with tampered identity"},
    audit={"validated": True, "mivp_identity": fake_dict},
    uncertainty={"sigma": 0.1},
    chain=None,
)
store.submit(p2)

# No identity
p3 = Patch(
    patch_id="p3",
    parent_patch_id="p2",
    branch_id="main",
    timestamp=int(time.time()) + 2,
    operation="ADD",
    target_id="claim3",
    category="EMPIRICAL",
    payload={"content": "Claim with no identity"},
    audit={"validated": True},
    uncertainty={"sigma": 0.1},
    chain=None,
)
store.submit(p3)

print("  Verification results:")
print("    Patch   | Has ID | Internal | Matches Agent | Status")
print("    " + "-" * 50)

for patch in store.branches["main"]:
    has_id = "mivp_identity" in patch.audit
    internal = store.verify_patch_identity_internal(patch) if has_id else False
    agent = store.verify_patch_identity_against_agent(patch) if has_id else False
    
    if agent:
        status = "VERIFIED"
    elif internal:
        status = "CONSISTENT (wrong agent)"
    elif has_id and not internal:
        status = "TAMPERED"
    else:
        status = "UNVERIFIED"
    
    print(f"    {patch.patch_id:8} | {str(has_id):6} | {str(internal):8} | {str(agent):12} | {status}")

# Reconstruction report
result = store.reconstruct_with_identity_verification("main", strict=False)
ver = result["verification"]
print(f"\n  Reconstruction report:")
print(f"    Total patches: {ver['total_patches']}")
print(f"    Verified: {ver['verified']}")
print(f"    Consistent (internal): {ver['consistent']}")
print(f"    Unverified (no identity): {ver['unverified']}")
print(f"    Tampered (inconsistent): {ver['tampered']}")

# ----------------------------------------------------------------------
print("\n" + "=" * 70)
if all_ok:
    print("ALL FIXES WORKING CORRECTLY")
else:
    print("SOME TESTS FAILED")
print("=" * 70)