#!/usr/bin/env python3
"""
Integration tests: Alexandria + MIVP

Rückgabestruktur von reconstruct_with_identity_verification():
{
  "nodes": {...},
  "verification": {
    "branch": str,
    "total_patches": int,
    "verified": int,
    "consistent": int,
    "unverified": int,
    "tampered": int,
    "patches": [{"patch_id", "has_identity", "internal_consistent", "agent_verified"}, ...]
  }
}
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import Patch, AuditError
from alexandria_mivp import AgentIdentity, AlexandriaMIVPStore
from dataclasses import replace

# ----------------------------- Fixtures -----------------------------

def make_identity(name="TestAgent", model_bytes=b"test model weights v1"):
    return AgentIdentity(
        name=name,
        model_path=f"models/{name}.bin",
        model_bytes=model_bytes,
        system_prompt=f"Test agent: {name}",
        guardrails=[{"id": "no_harm", "rule": "Do not cause harm"}],
        temperature=0.7,
        top_p=0.9,
        max_tokens=1000,
        tooling_enabled=False,
    )

def make_patch(patch_id, parent_id, ts, branch="main"):
    return Patch(
        patch_id=patch_id,
        parent_patch_id=parent_id,
        branch_id=branch,
        timestamp=ts,
        operation="ADD",
        target_id=f"claim_{patch_id}",
        category="EMPIRICAL",
        payload={"content": f"Claim from {patch_id}", "assumptions": ["assumption_a"]},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.05},
        chain=None,
    )

# ----------------------------- Tests -----------------------------

def test_submit_and_verify():
    """submit_with_identity() erzeugt korrekte Identity, Verifikation besteht."""
    print("\n[1] submit_with_identity + verify")
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    
    p = make_patch("p001", None, 1000)
    store.submit_with_identity(p)
    patch = store.branches["main"][0]
    
    assert "mivp_identity" in patch.audit, "mivp_identity fehlt im audit"
    internal_ok = store.verify_patch_identity_internal(patch)
    agent_ok = store.verify_patch_identity_against_agent(patch)
    
    print(f" [{'PASS' if internal_ok else 'FAIL'}] interne CIH-Konsistenz")
    print(f" [{'PASS' if agent_ok else 'FAIL'}] passt zu diesem Agenten")
    return internal_ok and agent_ok

def test_foreign_agent_detection():
    """Patch von Agent A: Store B meldet consistent aber nicht verified."""
    print("\n[2] Fremder Agent: consistent aber nicht verified")
    agent_a = make_identity("AgentA", b"agent a weights")
    agent_b = make_identity("AgentB", b"agent b weights")
    
    store_a = AlexandriaMIVPStore(agent_a)
    store_a.checkout("main")
    store_a.submit_with_identity(make_patch("p001", None, 1000))
    patch = store_a.branches["main"][0]
    
    store_b = AlexandriaMIVPStore(agent_b)
    internal_ok = store_b.verify_patch_identity_internal(patch)
    agent_ok = store_b.verify_patch_identity_against_agent(patch)
    
    ok = internal_ok and not agent_ok
    print(f" [{'PASS' if internal_ok else 'FAIL'}] intern konsistent")
    print(f" [{'PASS' if not agent_ok else 'FAIL'}] nicht als eigener Agent verifiziert")
    print(f" [{'PASS' if ok else 'FAIL'}] korrekte Unterscheidung consistent vs verified")
    return ok

def test_tamper_detection():
    """Manipulierter CIH-Wert wird erkannt."""
    print("\n[3] Tamper detection: manipulierter CIH")
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    store.submit_with_identity(make_patch("p001", None, 1000))
    
    patch = store.branches["main"][0]
    tampered_audit = dict(patch.audit)
    tampered_identity = dict(tampered_audit["mivp_identity"])
    tampered_identity["cih"] = "deadbeef" * 8
    tampered_audit["mivp_identity"] = tampered_identity
    tampered_patch = replace(patch, audit=tampered_audit)
    
    detected = not store.verify_patch_identity_internal(tampered_patch)
    print(f" [{'PASS' if detected else 'FAIL'}] manipulierter CIH wird erkannt")
    return detected

def test_patch_without_identity():
    """Patch ohne mivp_identity: unverified, strict wirft AuditError."""
    print("\n[4] Patch ohne Identity -> unverified")
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    store.submit(make_patch("p001", None, 1000))  # kein Identity
    
    patch = store.branches["main"][0]
    internal_ok = store.verify_patch_identity_internal(patch)
    agent_ok = store.verify_patch_identity_against_agent(patch)
    both_false = not internal_ok and not agent_ok
    
    print(f" [{'PASS' if both_false else 'FAIL'}] beide verify-Methoden geben False")
    
    # strict=False: kein Fehler, patch als unverified im Report
    result = store.reconstruct_with_identity_verification("main", strict=False)
    vr = result["verification"]
    unverified_count = vr["unverified"] == 1
    print(f" [{'PASS' if unverified_count else 'FAIL'}] reconstruct(strict=False) -> unverified=1")
    
    # strict=True: AuditError
    try:
        store.reconstruct_with_identity_verification("main", strict=True)
        strict_raises = False
    except AuditError:
        strict_raises = True
    print(f" [{'PASS' if strict_raises else 'FAIL'}] reconstruct(strict=True) wirft AuditError")
    
    return both_false and unverified_count and strict_raises

def test_multi_patch_reconstruction():
    """Mehrere Patches mit Identity: alle verified, Report vollständig."""
    print("\n[5] Multi-patch reconstruction")
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    
    ts, parent = 1000, None
    patch_ids = ["p001", "p002", "p003"]
    for pid in patch_ids:
        store.submit_with_identity(make_patch(pid, parent, ts))
        parent, ts = pid, ts + 1000
    
    result = store.reconstruct_with_identity_verification("main", strict=True)
    vr = result["verification"]
    
    correct_count = vr["total_patches"] == len(patch_ids)
    all_verified = vr["verified"] == len(patch_ids)
    
    print(f" [{'PASS' if correct_count else 'FAIL'}] {vr['total_patches']}/{len(patch_ids)} Patches")
    print(f" [{'PASS' if all_verified else 'FAIL'}] alle verified ({vr['verified']})")
    for p in vr["patches"]:
        status = "verified" if p["agent_verified"] else "unverified"
        print(f"   {p['patch_id']}: {status}")
    
    return correct_count and all_verified

def test_instance_epoch():
    """instance_epoch ändert CIH, bleibt aber intern konsistent."""
    print("\n[6] instance_epoch")
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    
    # Patch mit instance_epoch
    p = make_patch("p001", None, 1000)
    store.submit_with_identity(p, instance_epoch=123456)
    
    patch = store.branches["main"][0]
    assert "mivp_identity" in patch.audit
    assert patch.audit["mivp_identity"].get("instance_epoch") == 123456
    
    internal_ok = store.verify_patch_identity_internal(patch)
    agent_ok = store.verify_patch_identity_against_agent(patch)
    
    print(f" [{'PASS' if internal_ok else 'FAIL'}] mit instance_epoch intern konsistent")
    print(f" [{'PASS' if agent_ok else 'FAIL'}] passt trotz instance_epoch")
    
    # CIH mit/ohne epoch muss unterschiedlich sein
    identity_dict_no_epoch = identity.get_identity_dict()
    identity_dict_with_epoch = identity.get_identity_dict(instance_epoch=123456)
    
    cih_differs = identity_dict_no_epoch["cih"] != identity_dict_with_epoch["cih"]
    print(f" [{'PASS' if cih_differs else 'FAIL'}] CIH ändert sich mit instance_epoch")
    
    return internal_ok and agent_ok and cih_differs

def run_all_integration_tests():
    """Führt alle Integrationstests aus."""
    print("=" * 60)
    print("Alexandria + MIVP — Integration Test Suite")
    print("=" * 60)
    
    tests = [
        test_submit_and_verify,
        test_foreign_agent_detection,
        test_tamper_detection,
        test_patch_without_identity,
        test_multi_patch_reconstruction,
        test_instance_epoch,
    ]
    
    results = {}
    for test in tests:
        try:
            results[test.__name__] = test()
        except Exception as e:
            print(f"\n[ERROR] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            results[test.__name__] = False
    
    print("\n" + "=" * 60)
    print("Summary:")
    all_pass = True
    for name, ok in results.items():
        print(f" [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass &= ok
    
    print(f"\n{'All integration tests PASSED.' if all_pass else 'FAILURES detected.'}")
    print("=" * 60)
    return all_pass

if __name__ == "__main__":
    sys.exit(0 if run_all_integration_tests() else 1)