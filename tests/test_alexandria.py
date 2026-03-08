#!/usr/bin/env python3
"""
Test Alexandria Protocol basic operations.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import AlexandriaStore, Patch

def test_alexandria_basic():
    """Test basic Alexandria operations."""
    print("Testing Alexandria Protocol basic operations...")
    
    store = AlexandriaStore()
    store.checkout("main")
    
    # Test ADD
    p1 = Patch(
        patch_id="test_001",
        parent_patch_id=None,
        branch_id="main",
        timestamp=1000,
        operation="ADD",
        target_id="claim_test",
        category="EMPIRICAL",
        payload={
            "content": "Test claim",
            "assumptions": ["test_assumption"],
        },
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.1},
        chain=None,
    )
    
    try:
        store.submit(p1)
        print("✅ ADD operation successful")
    except Exception as e:
        print(f"❌ ADD operation failed: {e}")
        return False
    
    # Test MODIFY
    p2 = Patch(
        patch_id="test_002",
        parent_patch_id="test_001",
        branch_id="main",
        timestamp=2000,
        operation="MODIFY",
        target_id="claim_test",
        category="EMPIRICAL",
        payload={
            "content": "Modified test claim",
        },
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.05},
        chain=None,
    )
    
    try:
        store.submit(p2)
        print("✅ MODIFY operation successful")
    except Exception as e:
        print(f"❌ MODIFY operation failed: {e}")
        return False
    
    # Test DEPRECATE
    p3 = Patch(
        patch_id="test_003",
        parent_patch_id="test_002",
        branch_id="main",
        timestamp=3000,
        operation="DEPRECATE",
        target_id="claim_test",
        category="EMPIRICAL",
        payload={"content": "Deprecated for testing"},
        audit={"validated": True, "decay": 0.0},
        uncertainty=None,
        chain=None,
    )
    
    try:
        store.submit(p3)
        print("✅ DEPRECATE operation successful")
    except Exception as e:
        print(f"❌ DEPRECATE operation failed: {e}")
        return False
    
    # Test reconstruction
    try:
        nodes = store.reconstruct("main")
        print("✅ Reconstruction successful")
        if "claim_test" in nodes:
            node = nodes["claim_test"]
            print(f"   Node stability: {node.stability:.3f}")
            print(f"   Node deprecated: {node.deprecated}")
    except Exception as e:
        print(f"❌ Reconstruction failed: {e}")
        return False
    
    # Test branch creation
    try:
        store.create_branch("test_branch")
        print("✅ Branch creation successful")
    except Exception as e:
        print(f"❌ Branch creation failed: {e}")
        return False
    
    print("\n✅ All Alexandria basic tests PASSED.")
    return True

if __name__ == "__main__":
    success = test_alexandria_basic()
    sys.exit(0 if success else 1)