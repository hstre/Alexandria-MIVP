"""
Basic Alexandria Protocol Usage Example
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alexandria_v2 import AlexandriaStore, Patch
import json

def demonstrate_basic_operations():
    """Show basic Alexandria operations."""
    print("=== Alexandria Protocol Basic Usage ===\n")
    
    # Create a store
    store = AlexandriaStore()
    store.checkout("main")
    
    print("1. Creating empirical claim...")
    p1 = Patch(
        patch_id="patch_001",
        parent_patch_id=None,
        branch_id="main",
        timestamp=1771459200,
        operation="ADD",
        target_id="claim_temp",
        category="EMPIRICAL",
        payload={
            "content": "Water freezes at 0°C at standard atmospheric pressure.",
            "assumptions": ["Pure water", "Standard pressure 1 atm"],
        },
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.01, "ci": [-0.1, 0.1], "n": 1000},
        chain=None,
    )
    
    store.submit(p1)
    print("   Claim added with ID: claim_temp")
    
    print("\n2. Modifying claim with new data...")
    p2 = Patch(
        patch_id="patch_002",
        parent_patch_id="patch_001",
        branch_id="main",
        timestamp=1771460000,
        operation="MODIFY",
        target_id="claim_temp",
        category="EMPIRICAL",
        payload={
            "content": "Water freezes at 0°C at standard atmospheric pressure, but can supercool.",
            "assumptions": ["Pure water", "Standard pressure", "No nucleation sites"],
        },
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.02, "ci": [-0.2, 0.2], "n": 5000},
        chain=None,
    )
    
    store.submit(p2)
    print("   Claim modified")
    
    print("\n3. Creating a branch for alternative interpretation...")
    store.create_branch("b_alt_interpretation")
    store.checkout("b_alt_interpretation")
    
    p3 = Patch(
        patch_id="patch_003",
        parent_patch_id="patch_002",
        branch_id="b_alt_interpretation",
        timestamp=1771465000,
        operation="MODIFY",
        target_id="claim_temp",
        category="EMPIRICAL",
        payload={
            "content": "Freezing point depends on isotopic composition of water.",
            "assumptions": ["Natural isotopic distribution", "Standard pressure"],
        },
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.05, "ci": [-0.3, 0.3], "n": 200},
        chain=None,
    )
    
    store.submit(p3)
    print("   Alternative interpretation added in branch")
    
    print("\n4. Showing epistemic status...")
    report = store.status_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    
    print("\n5. Verifying reconstruction integrity...")
    try:
        reconstructed = store.reconstruct("b_alt_interpretation")
        print("   Reconstruction successful - all patches verify")
        print(f"   Node stability: {reconstructed['claim_temp'].stability:.3f}")
        print(f"   Node deprecated: {reconstructed['claim_temp'].deprecated}")
    except Exception as e:
        print(f"   Reconstruction failed: {e}")
    
    print("\n=== Basic operations complete ===")

if __name__ == "__main__":
    demonstrate_basic_operations()