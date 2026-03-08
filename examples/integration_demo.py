"""
Alexandria + MIVP Integration Demo
Shows end-to-end verifiable epistemic claims with cryptographic identity
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from alexandria_v2 import Patch
import json
import time

def demonstrate_integration():
    """Show Alexandria + MIVP working together."""
    print("=== Alexandria + MIVP Integration Demo ===\n")
    
    # Create agent identity
    print("1. Creating epistemic agent identity...")
    identity = AgentIdentity(
        name="EpistemicResearcher",
        model_path="models/researcher_v1.bin",
        model_bytes=b"Mock weights for epistemic researcher",
        model_chunk_size=16,
        
        system_prompt="Research assistant specializing in epistemic consistency.",
        guardrails=[
            {"id": "fact_checking", "rule": "Verify claims against sources"},
            {"id": "uncertainty_marking", "rule": "Mark speculative claims"},
        ],
        moderation_policy_version="2026-03-01",
        policy_spec_version="1.0",
        attestation_completeness="full",
        
        temperature=0.5,
        top_p=0.9,
        max_tokens=3000,
        tooling_enabled=True,
        routing_mode="direct",
        runtime_spec_version="1.0",
    )
    
    print(f"   Agent: {identity.name}")
    print(f"   CIH: {identity.compute_cih().hex()[:16]}...\n")
    
    # Create MIVP-enhanced store
    print("2. Creating Alexandria store with MIVP identity...")
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    
    # Create epistemically grounded claim
    print("3. Submitting claim with cryptographic identity...")
    p1 = Patch(
        patch_id="research_001",
        parent_patch_id=None,
        branch_id="main",
        timestamp=int(time.time()),
        operation="ADD",
        target_id="claim_quantum_supremacy",
        category="SPECULATIVE",  # This is a speculative claim
        payload={
            "content": "Quantum supremacy will be achieved for practical optimization problems within 5 years.",
            "assumptions": [
                "Quantum error correction improves",
                "Hardware scaling continues",
                "Algorithm breakthroughs occur"
            ],
        },
        audit={"validated": True, "decay": 0.02},
        uncertainty={"sigma": 0.3, "ci": [0.2, 0.8], "n": 50},
        chain=None,
    )
    
    commit_hash = store.submit_with_identity(p1, instance_epoch=int(time.time()))
    print(f"   Claim submitted. Commit hash: {commit_hash[:16]}...")
    
    # Show status
    print("\n4. Epistemic status report:")
    report = store.status_report()
    
    # Add identity info
    report["agent_identity"] = {
        "name": identity.name,
        "cih": identity.compute_cih().hex()[:16] + "...",
        "mh": identity.compute_mh().hex()[:16] + "...",
        "ph": identity.compute_ph().hex()[:16] + "...",
        "rh": identity.compute_rh().hex()[:16] + "...",
    }
    
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    # Verify identity
    print("\n5. Verifying patch identity...")
    patch = store.branches["main"][0]
    identity_valid = store.verify_patch_identity(patch)
    print(f"   Identity verification: {identity_valid}")
    
    if identity_valid:
        identity_data = patch.audit.get("mivp_identity", {})
        print(f"   Agent: {identity_data.get('agent_name', 'Unknown')}")
        print(f"   CIH: {identity_data.get('cih', 'Unknown')[:16]}...")
        print(f"   Timestamp: {identity_data.get('timestamp', 'Unknown')}")
    else:
        print("   WARNING: Identity verification failed!")
    
    # Demonstrate reconstruction with verification
    print("\n6. Reconstructing with full verification...")
    try:
        nodes = store.reconstruct_with_identity_verification("main")
        print(f"   Reconstruction successful!")
        print(f"   Nodes: {list(nodes.keys())}")
        
        # Show the claim
        claim = nodes["claim_quantum_supremacy"]
        print(f"\n   Claim details:")
        print(f"   • Content: {claim.content[:60]}...")
        print(f"   • Category: {claim.category}")
        print(f"   • Stability: {claim.stability:.3f}")
        print(f"   • Uncertainty (sigma): {claim.uncertainty.sigma if claim.uncertainty else 'None'}")
        print(f"   • Assumptions: {len(claim.assumptions)}")
        print(f"   • Lineage: {len(claim.lineage)} patches")
        
    except Exception as e:
        print(f"   Reconstruction failed: {e}")
    
    # Demonstrate identity change detection
    print("\n7. Demonstrating identity change detection...")
    print("   Changing agent's policy (adding guardrail)...")
    
    identity.guardrails.append(
        {"id": "new_guardrail", "rule": "New rule added"}
    )
    
    new_identity_info = identity.get_identity_dict()
    old_cih = patch.audit.get("mivp_identity", {}).get("cih", "")
    new_cih = new_identity_info["cih"]
    
    print(f"   Old CIH: {old_cih[:16]}..." if old_cih else "   Old CIH: Not available")
    print(f"   New CIH: {new_cih[:16]}...")
    print(f"   CIH changed: {old_cih != new_cih}")
    
    print("\n=== Integration demonstration complete ===")
    print("\nKey takeaways:")
    print("• Epistemic claims cryptographically linked to agent identity")
    print("• Any change to agent identity (model/policy/runtime) detectable")
    print("• Full audit trail from claim content to originating system")
    print("• Deterministic verification enables trust without central authority")

if __name__ == "__main__":
    demonstrate_integration()