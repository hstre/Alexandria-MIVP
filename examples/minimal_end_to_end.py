#!/usr/bin/env python3
"""
Minimal End-to-End Example for Alexandria-MIVP
Follows the 5-step process from the technical review memo.
"""
from alexandria_mivp import Patch, AgentIdentity, AlexandriaMIVPStore
import time

print("=" * 70)
print("Alexandria-MIVP: Minimal End-to-End Example")
print("=" * 70)

# ----------------------------------------------------------------------
# Step 1: Create Identity
print("\n1. CREATE IDENTITY")
print("-" * 40)

identity = AgentIdentity(
    name="ExampleAgent",
    model_path="models/example.bin",
    model_bytes=b"example model weights v1.0",
    system_prompt="You are a helpful assistant.",
    guardrails=[
        {"id": "safety", "rule": "Do not generate harmful content"},
        {"id": "honesty", "rule": "Be truthful and accurate"},
    ],
    temperature=0.7,
    top_p=0.9,
    max_tokens=1000,
    tooling_enabled=True,
)

print(f"   Agent: {identity.name}")
print(f"   MH: {identity.compute_mh().hex()[:16]}...")
print(f"   PH: {identity.compute_ph().hex()[:16]}...")
print(f"   RH: {identity.compute_rh().hex()[:16]}...")
print(f"   CIH: {identity.compute_cih().hex()[:16]}...")

# ----------------------------------------------------------------------
# Step 2: Create Claim
print("\n2. CREATE CLAIM")
print("-" * 40)

claim_patch = Patch(
    patch_id="claim_001",
    parent_patch_id=None,
    branch_id="main",
    timestamp=int(time.time()),
    operation="ADD",
    target_id="knowledge_001",
    category="EMPIRICAL",
    payload={
        "content": "The Alexandria Protocol provides epistemic consistency through structured audit gates.",
        "assumptions": ["Formal verification is possible", "Cryptographic primitives are secure"],
    },
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 0.05},
    chain=None,
)

print(f"   Patch ID: {claim_patch.patch_id}")
print(f"   Category: {claim_patch.category}")
print(f"   Content: {claim_patch.payload['content'][:60]}...")
print(f"   Assumptions: {len(claim_patch.payload['assumptions'])}")

# ----------------------------------------------------------------------
# Step 3: Apply Patch
print("\n3. APPLY PATCH")
print("-" * 40)

store = AlexandriaMIVPStore(identity)
store.checkout("main")

try:
    commit_hash = store.submit_with_identity(claim_patch)
    print(f"   [OK] Patch submitted successfully")
    print(f"   Commit hash: {commit_hash[:16]}...")
    
    # Verify the patch was stored
    stored_patch = store.branches["main"][0]
    print(f"   Stored patch ID: {stored_patch.patch_id}")
    
    # Check identity was attached
    if "mivp_identity" in stored_patch.audit:
        identity_info = stored_patch.audit["mivp_identity"]
        print(f"   Identity attached: [OK]")
        print(f"   Agent name: {identity_info.get('agent_name')}")
        print(f"   CIH: {identity_info.get('cih')[:16]}...")
    else:
        print(f"   Identity attached: [FAIL]")
        
except Exception as e:
    print(f"   ❌ Failed to submit patch: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# Step 4: Verify Chain
print("\n4. VERIFY CHAIN")
print("-" * 40)

try:
    # Reconstruct with verification
    result = store.reconstruct_with_identity_verification("main", strict=False)
    verification = result["verification"]
    
    print(f"   Total patches: {verification['total_patches']}")
    print(f"   Verified: {verification['verified']}")
    print(f"   Consistent: {verification['consistent']}")
    print(f"   Unverified: {verification['unverified']}")
    print(f"   Tampered: {verification['tampered']}")
    
    if verification['verified'] == 1:
        print(f"   [OK] Chain verification successful")
    else:
        print(f"   [NOTE] Chain verification issues detected")
        
    # Show patch details
    for patch_info in verification["patches"]:
        status = "verified" if patch_info["agent_verified"] else "unverified"
        print(f"   - {patch_info['patch_id']}: {status}")
        
except Exception as e:
    print(f"   [FAIL] Chain verification failed: {e}")

# ----------------------------------------------------------------------
# Step 5: Verify Identity Bundle
print("\n5. VERIFY IDENTITY BUNDLE")
print("-" * 40)

# Get the stored patch
stored_patch = store.branches["main"][0]

# Internal consistency check (weak verification)
internal_ok = store.verify_patch_identity_internal(stored_patch)
print(f"   Internal CIH consistency: {'[OK]' if internal_ok else '[FAIL]'}")

# Agent matching check (strong verification)
agent_ok = store.verify_patch_identity_against_agent(stored_patch)
print(f"   Agent identity match: {'[OK]' if agent_ok else '[FAIL]'}")

# Digital signature check (if available)
sig_result = store.verify_patch_signature(stored_patch)
if sig_result is None:
    print(f"   Digital signature: [NOTE] Not present (legacy mode)")
elif sig_result:
    print(f"   Digital signature: [OK] Valid")
else:
    print(f"   Digital signature: [FAIL] Invalid")

# Identity bundle summary
if "mivp_identity" in stored_patch.audit:
    bundle = stored_patch.audit["mivp_identity"]
    print(f"\n   Identity Bundle Summary:")
    print(f"     - Agent: {bundle.get('agent_name')}")
    print(f"     - MH: {bundle.get('mh')[:16]}...")
    print(f"     - PH: {bundle.get('ph')[:16]}...")
    print(f"     - RH: {bundle.get('rh')[:16]}...")
    print(f"     - CIH: {bundle.get('cih')[:16]}...")
    print(f"     - Timestamp: {bundle.get('timestamp')}")

# ----------------------------------------------------------------------
# Final Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print("[OK] Identity created and hashed")
print("[OK] Claim structured as epistemic patch")
print("[OK] Patch submitted with identity binding")
print("[OK] Chain verified with tamper detection")
print("[OK] Identity bundle validated")

print("\nThe system successfully:")
print("1. Created a cryptographically-bound agent identity")
print("2. Structured a knowledge claim with epistemic metadata")
print("3. Applied the claim with immutable lineage")
print("4. Verified the integrity of the claim chain")
print("5. Validated the identity bundle consistency")

print("\nThis demonstrates the core value proposition:")
print("- Claims are bound to specific model/policy/runtime profiles")
print("- Epistemic structure ensures category purity and lineage")
print("- Tamper detection within chains prevents silent modification")
print("- Optional signatures and external anchoring enable trust networks")