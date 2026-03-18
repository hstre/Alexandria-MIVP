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

from alexandria_mivp.alexandria_v2 import Patch, AuditError
from alexandria_mivp.alexandria_mivp import AgentIdentity, AlexandriaMIVPStore
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
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")

    p = make_patch("p001", None, 1000)
    store.submit_with_identity(p)
    patch = store.branches["main"][0]

    assert "mivp_identity" in patch.audit, "mivp_identity fehlt im audit"
    assert store.verify_patch_identity_internal(patch), "interne CIH-Konsistenz fehlgeschlagen"
    assert store.verify_patch_identity_against_agent(patch), "Agenten-Verifikation fehlgeschlagen"


def test_foreign_agent_detection():
    """Patch von Agent A: Store B meldet consistent aber nicht verified."""
    agent_a = make_identity("AgentA", b"agent a weights")
    agent_b = make_identity("AgentB", b"agent b weights")

    store_a = AlexandriaMIVPStore(agent_a)
    store_a.checkout("main")
    store_a.submit_with_identity(make_patch("p001", None, 1000))
    patch = store_a.branches["main"][0]

    store_b = AlexandriaMIVPStore(agent_b)
    assert store_b.verify_patch_identity_internal(patch), "intern nicht konsistent"
    assert not store_b.verify_patch_identity_against_agent(patch), "fälschlicherweise als eigener Agent verifiziert"


def test_tamper_detection():
    """Manipulierter CIH-Wert wird erkannt."""
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

    assert not store.verify_patch_identity_internal(tampered_patch), "manipulierter CIH nicht erkannt"


def test_patch_without_identity():
    """Patch ohne mivp_identity: unverified, strict wirft AuditError."""
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    store.submit(make_patch("p001", None, 1000))  # kein Identity

    patch = store.branches["main"][0]
    assert not store.verify_patch_identity_internal(patch)
    assert not store.verify_patch_identity_against_agent(patch)

    # strict=False: kein Fehler, patch als unverified im Report
    result = store.reconstruct_with_identity_verification("main", strict=False)
    vr = result["verification"]
    assert vr["unverified"] == 1, f"erwartet unverified=1, got {vr['unverified']}"

    # strict=True: AuditError
    try:
        store.reconstruct_with_identity_verification("main", strict=True)
        assert False, "AuditError erwartet, nicht geworfen"
    except AuditError:
        pass


def test_multi_patch_reconstruction():
    """Mehrere Patches mit Identity: alle verified, Report vollständig."""
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

    assert vr["total_patches"] == len(patch_ids), f"erwartet {len(patch_ids)}, got {vr['total_patches']}"
    assert vr["verified"] == len(patch_ids), f"erwartet alle verified, got {vr['verified']}"


def test_instance_epoch():
    """instance_epoch ändert CIH, bleibt aber intern konsistent."""
    identity = make_identity()
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")

    p = make_patch("p001", None, 1000)
    store.submit_with_identity(p, instance_epoch=123456)

    patch = store.branches["main"][0]
    assert "mivp_identity" in patch.audit
    assert patch.audit["mivp_identity"].get("instance_epoch") == 123456
    assert store.verify_patch_identity_internal(patch)
    assert store.verify_patch_identity_against_agent(patch)

    identity_dict_no_epoch = identity.get_identity_dict()
    identity_dict_with_epoch = identity.get_identity_dict(instance_epoch=123456)
    assert identity_dict_no_epoch["cih"] != identity_dict_with_epoch["cih"], \
        "CIH muss sich mit instance_epoch ändern"


# ----------------------------- Manual runner -----------------------------

def run_all_integration_tests():
    """Führt alle Integrationstests aus (für manuellen Aufruf)."""
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
            test()
            results[test.__name__] = True
        except (AssertionError, Exception) as e:
            print(f"FAIL {test.__name__}: {e}")
            results[test.__name__] = False

    all_pass = all(results.values())
    print(f"\n{'All integration tests PASSED.' if all_pass else 'FAILURES detected.'}")
    return all_pass


if __name__ == "__main__":
    sys.exit(0 if run_all_integration_tests() else 1)
