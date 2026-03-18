#!/usr/bin/env python3
"""
Test MIVP v2.1 compliance with Appendix G test vectors.
Extended tests:
- canonicalize_runtime() via helper (nicht nur hardcodierter String)
- cfs1_float() edge cases
"""
import sys

from alexandria_mivp.mivp_impl import (
    run_test_vectors,
    cfs1_float,
    canonicalize_runtime,
    runtime_hash,
    hex_to_bytes,
)


def test_canonicalize_runtime_via_helper():
    """
    G4-Testvektor muss auch über canonicalize_runtime() erreichbar sein.
    Das ist die Lücke, die den top_p-als-String-Bug verborgen hat.
    """
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
    assert rh == expected, f"RH-1 mismatch: expected {expected_hex}, got {rh.hex()}"

    canonical = canonicalize_runtime(
        temperature=0.7, top_p=1.0, max_tokens=256,
        tooling_enabled=False, routing_mode="language-aware",
        runtime_spec_version="1.0",
    )
    assert '"temperature":"' not in canonical, "Floats dürfen keine Strings sein"
    assert '"top_p":"' not in canonical, "Floats dürfen keine Strings sein"


def test_cfs1_float_edge_cases():
    """cfs1_float() Korrektheit und Round-trip-Sicherheit."""
    cases = [
        (0.0,    "0",      "zero"),
        (-0.0,   "0",      "negative zero -> 0"),
        (1.0,    "1",      "integer-valued, kein Dezimalpunkt"),
        (0.7,    "0.7",    "einfaches Decimal"),
        (0.9,    "0.9",    "einfaches Decimal"),
        (0.1,    "0.1",    "0.1 round-trip"),
        (0.5,    "0.5",    "0.5"),
        (1.5,    "1.5",    "1.5"),
        (100.0,  "100",    "integer-valued, kein Dezimalpunkt"),
        (0.0001, "0.0001", "untere Grenze 1e-4"),
        (0.25,   "0.25",   "0.25"),
    ]
    for x, expected, desc in cases:
        result = cfs1_float(x)
        assert result == expected, f"cfs1_float({x!r}) == {result!r}, want {expected!r} ({desc})"

    for x in [0.7, 0.9, 0.1, 0.25, 1.0, 100.0, 0.0001, 3.14, 1.5]:
        s = cfs1_float(x)
        assert float(s) == x, f"round-trip failed: float(cfs1_float({x})) = {float(s)}"


def test_mivp_compliance():
    """Vollständige MIVP-Testsuite: Appendix G."""
    assert run_test_vectors(), "MIVP Appendix G test vectors failed"


if __name__ == "__main__":
    sys.exit(0 if run_test_vectors() else 1)
