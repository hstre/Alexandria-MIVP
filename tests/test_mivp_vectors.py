#!/usr/bin/env python3
"""
Test MIVP v2.1 compliance with Appendix G test vectors.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mivp_impl import run_test_vectors

def test_mivp_compliance():
    """Run all MIVP test vectors and ensure byte-identical compliance."""
    print("Running MIVP v2.1 test vectors (Appendix G)...")
    
    success = run_test_vectors()
    
    if success:
        print("\n✅ All test vectors PASSED. Implementation is MIVP-compliant.")
        return True
    else:
        print("\n❌ Test vectors FAILED. Implementation is non-compliant.")
        return False

if __name__ == "__main__":
    success = test_mivp_compliance()
    sys.exit(0 if success else 1)