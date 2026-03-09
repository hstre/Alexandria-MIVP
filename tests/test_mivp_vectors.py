#!/usr/bin/env python3
"""
Test MIVP v2.1 compliance with Appendix G test vectors.
Extended tests:
- canonicalize_runtime() via helper (nicht nur hardcodierter String)
- cfs1_float() edge cases
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mivp_impl import (
    run_test_vectors,
    cfs1_float,
    canonicalize_runtime,
    runtime_hash,
    hex_to_bytes,
)

def test_canonicalize_runtime_via_helper():
    """
    G4-Testvektor muss auch über canonicalize_runtime() erreichbar sein,
    nicht nur über den hardcodierten String.
    Das ist die Lücke, die den top_p-als-String-Bug verborgen hat.
    """
    print("\n[G4 via helper] canonicalize_runtime() round-trip")
    all_pass = True
    
    expected_hex = "827d100295de8a512a5d9a4138fadcdb5112d73e00dfd3fe163c142141d1faa0"
    expected = hex_to_bytes(expected_hex)
    
    rh = runtime_hash(canonicalize_runtime(
        temperature=0.7,
        top_p=1.0,
        max_tokens=256,
        tooling_enabled=False,
        routing_mode="language-aware",
        runtime_spec_version="1.0",
    ))
    ok = rh == expected
    print(f" [{'PASS' if ok else 'FAIL'}] RH-1 via canonicalize_runtime(top_p=1.0)")
    if not ok:
        print(f"  expected: {expected_hex}")
        print(f"  computed: {rh.hex()}")
    all_pass &= ok
    
    # Canonical string darf keine gequoteten Floats enthalten
    canonical = canonicalize_runtime(
        temperature=0.7,
        top_p=1.0,
        max_tokens=256,
        tooling_enabled=False,
        routing_mode="language-aware",
        runtime_spec_version="1.0",
    )
    no_quoted = '"temperature":"' not in canonical and '"top_p":"' not in canonical
    print(f" [{'PASS' if no_quoted else 'FAIL'}] Floats sind JSON-Zahlen, keine Strings")
    if not no_quoted:
        print(f"  canonical: {canonical}")
    all_pass &= no_quoted
    
    return all_pass

def test_cfs1_float_edge_cases():
    """cfs1_float() Korrektheit und Round-trip-Sicherheit."""
    print("\n[cfs1_float] Edge cases")
    all_pass = True
    
    cases = [
        (0.0, "0", "zero"),
        (-0.0, "0", "negative zero -> 0"),
        (1.0, "1", "integer-valued, kein Dezimalpunkt"),
        (0.7, "0.7", "einfaches Decimal"),
        (0.9, "0.9", "einfaches Decimal"),
        (0.1, "0.1", "0.1 round-trip"),
        (0.5, "0.5", "0.5"),
        (1.5, "1.5", "1.5"),
        (100.0, "100", "integer-valued, kein Dezimalpunkt"),
        (0.0001, "0.0001", "untere Grenze 1e-4"),
        (0.25, "0.25", "0.25"),
    ]
    
    for x, expected, desc in cases:
        result = cfs1_float(x)
        ok = result == expected
        print(f" [{'PASS' if ok else 'FAIL'}] cfs1_float({x!r}) == {expected!r} ({desc})")
        if not ok:
            print(f"  got: {result!r}")
        all_pass &= ok
    
    print("\n [round-trip]")
    for x in [0.7, 0.9, 0.1, 0.25, 1.0, 100.0, 0.0001, 3.14, 1.5]:
        s = cfs1_float(x)
        ok = float(s) == x
        print(f" [{'PASS' if ok else 'FAIL'}] float(cfs1_float({x})) == {x} via '{s}'")
        if not ok:
            print(f"  got: {float(s)}")
        all_pass &= ok
    
    return all_pass

def test_mivp_compliance():
    """Vollständige MIVP-Testsuite: Appendix G + erweiterte Tests."""
    print("=" * 60)
    print("MIVP v2.1 — Full Test Suite")
    print("=" * 60)
    
    results = {
        "appendix_g": run_test_vectors(),
        "canonicalize_runtime_helper": test_canonicalize_runtime_via_helper(),
        "cfs1_float_edges": test_cfs1_float_edge_cases(),
    }
    
    print("\n" + "=" * 60)
    print("Summary:")
    all_pass = True
    for name, ok in results.items():
        print(f" [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass &= ok
    
    print(f"\n{'All tests PASSED.' if all_pass else 'FAILURES detected.'}")
    print("=" * 60)
    return all_pass

if __name__ == "__main__":
    sys.exit(0 if test_mivp_compliance() else 1)