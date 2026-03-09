"""
MIVP Implementation - Model Identity Verification Protocol v2.1
Based on Demo.py from official repository
"""

import hashlib
import json
import struct
import unicodedata
from typing import List, Optional, Tuple, Dict, Any

# ----------------------------- Utilities -----------------------------

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def u64be(n: int) -> bytes:
    return struct.pack(">Q", n)

def hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h.replace(" ", ""))

def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)

# ----------------------------- Layer 1 — Model Hash (MH) -----------------------------

def leaf_hash(path: str, file_size_bytes: int, chunk_index: int, chunk_bytes: bytes) -> bytes:
    """
    leaf = SHA256(
        0x00 || "MIVP-LEAF-CHUNK-V1" || 0x00 ||
        path_utf8 || 0x00 ||
        u64be(file_size_bytes) ||
        u64be(chunk_index) ||
        chunk_bytes
    )
    """
    domain = b"\x00" + b"MIVP-LEAF-CHUNK-V1" + b"\x00"
    path_bytes = nfc(path).encode("utf-8") + b"\x00"
    return sha256(domain + path_bytes + u64be(file_size_bytes) + u64be(chunk_index) + chunk_bytes)

def node_hash(left: bytes, right: bytes) -> bytes:
    """
    node = SHA256(0x01 || "MIVP-NODE-BINARY-V1" || 0x00 || left || right)
    """
    domain = b"\x01" + b"MIVP-NODE-BINARY-V1" + b"\x00"
    return sha256(domain + left + right)

def merkle_root(leaves: List[bytes]) -> bytes:
    """
    Build Merkle tree with carry-up for odd counts (no duplication, no re-hashing).
    """
    if not leaves:
        raise ValueError("Empty leaf list")
    
    level = list(leaves)
    while len(level) > 1:
        next_level = []
        i = 0
        while i < len(level):
            if i + 1 < len(level):
                next_level.append(node_hash(level[i], level[i + 1]))
                i += 2
            else:
                # Carry-up: odd node passes through unchanged
                next_level.append(level[i])
                i += 1
        level = next_level
    return level[0]

def model_hash(file_path: str, file_bytes: bytes, chunk_size: int = 4 * 1024 * 1024) -> Tuple[bytes, bytes, int]:
    """
    Compute MH for a single file.
    Returns (MH, merkle_root, total_leaves).
    
    MH = SHA256(merkle_root || u64be(total_leaves))
    """
    file_size = len(file_bytes)
    chunks = []
    if file_size == 0:
        chunks = [b""]
    else:
        i = 0
        while i < file_size:
            chunks.append(file_bytes[i:i + chunk_size])
            i += chunk_size
    
    leaves = [
        leaf_hash(file_path, file_size, idx, chunk)
        for idx, chunk in enumerate(chunks)
    ]
    root = merkle_root(leaves)
    total = len(leaves)
    mh = sha256(root + u64be(total))
    return mh, root, total

# ----------------------------- Layer 2 — Policy Hash (PH) -----------------------------

def canonicalize_policy(
    system_prompt: str,
    guardrails: List[Dict[str, str]],
    moderation_policy_version: str,
    policy_spec_version: str,
    attestation_completeness: str,
) -> str:
    """
    Build canonical policy JSON per Appendix B:
    - Field-level: strip ASCII whitespace, normalize line endings, NFC
    - Guardrails sorted lexicographically by id
    - Keys sorted, no insignificant whitespace
    """
    def clean(s: str) -> str:
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        s = nfc(s)
        return s.strip()
    
    sorted_guardrails = sorted(guardrails, key=lambda g: g["id"])
    cleaned_guardrails = [
        {"id": clean(g["id"]), "rule": clean(g["rule"])}
        for g in sorted_guardrails
    ]
    
    obj = {
        "attestation_completeness": clean(attestation_completeness),
        "guardrails": cleaned_guardrails,
        "moderation_policy_version": clean(moderation_policy_version),
        "policy_spec_version": clean(policy_spec_version),
        "system_prompt": clean(system_prompt),
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def policy_hash(canonical_policy_json: str) -> bytes:
    """
    PH = SHA256(0x02 || "MIVP-POLICY-V1" || 0x00 || canonical_policy_json_bytes)
    """
    domain = b"\x02" + b"MIVP-POLICY-V1" + b"\x00"
    payload = canonical_policy_json.encode("utf-8")
    return sha256(domain + payload)

# ----------------------------- Layer 3 — Runtime Hash (RH) -----------------------------

def cfs1_float(x: float) -> str:
    """
    CFS-1: shortest round-trip-safe decimal, no trailing zeros,
    no scientific notation in range [1e-4, 1e4), normalize -0.0 to 0.
    Robust implementation using Decimal for exact representation.
    """
    if x == 0.0:
        return "0"
    
    abs_x = abs(x)
    if 1e-4 <= abs_x < 1e4:
        # Fixed-point notation within range, ensure no scientific notation
        # Use Decimal for exact round-trip representation
        from decimal import Decimal
        d = Decimal(repr(x))
        # Format as fixed-point without exponent
        s = format(d, 'f')
        # Remove trailing zeros after decimal point
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s
    else:
        # Outside range: use Python's repr which is round-trip safe
        # and uses scientific notation when appropriate (shortest)
        s = repr(x)
        # repr may produce "-0.0" for negative zero
        if s == "-0.0":
            return "0"
        return s



def canonicalize_runtime(
    temperature: float,
    top_p: float,
    max_tokens: int,
    tooling_enabled: bool,
    routing_mode: str,
    runtime_spec_version: str,
) -> str:
    """
    Build canonical runtime JSON per Appendix D + CFS-1.
    Manual JSON assembly to ensure CFS-1 floats become JSON numbers, not strings.
    """
    # Build object with sorted keys
    obj = {
        "max_tokens": max_tokens,
        "routing_mode": routing_mode,
        "runtime_spec_version": runtime_spec_version,
        "temperature": temperature,
        "tooling_enabled": tooling_enabled,
        "top_p": top_p,
    }
    
    # Manually build JSON string with CFS-1 floats as numbers
    parts = []
    for key in sorted(obj.keys()):
        value = obj[key]
        if isinstance(value, float):
            # Use CFS-1 representation directly as JSON number
            parts.append(f'"{key}":{cfs1_float(value)}')
        elif isinstance(value, bool):
            # JSON boolean
            parts.append(f'"{key}":{str(value).lower()}')
        else:
            # Let json.dumps handle other types
            parts.append(f'"{key}":{json.dumps(value, separators=(",",":"), ensure_ascii=False)}')
    
    return "{" + ",".join(parts) + "}"

def runtime_hash(canonical_runtime_json: str) -> bytes:
    """
    RH = SHA256(0x03 || "MIVP-RUNTIME-V1" || 0x00 || canonical_runtime_json_bytes)
    """
    domain = b"\x03" + b"MIVP-RUNTIME-V1" + b"\x00"
    payload = canonical_runtime_json.encode("utf-8")
    return sha256(domain + payload)

# ----------------------------- Layer 4 — Composite Instance Hash (CIH) -----------------------------

def composite_instance_hash(
    mh: bytes,
    ph: bytes,
    rh: bytes,
    instance_epoch: Optional[int] = None,
) -> bytes:
    """
    CIH = SHA256(0x04 || "MIVP-CIH-V1" || 0x00 || MH || PH || RH [|| u64be(epoch)])
    """
    domain = b"\x04" + b"MIVP-CIH-V1" + b"\x00"
    payload = mh + ph + rh
    if instance_epoch is not None:
        payload += u64be(instance_epoch)
    return sha256(domain + payload)

# ----------------------------- Test Vector Verification -----------------------------

def verify(label: str, computed: bytes, expected_hex: str) -> bool:
    expected = hex_to_bytes(expected_hex)
    ok = computed == expected
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}")
    if not ok:
        print(f"         expected: {expected.hex()}")
        print(f"         computed: {computed.hex()}")
    return ok

def run_test_vectors() -> bool:
    print("=" * 60)
    print("MIVP v2.1 — Test Vector Verification (Appendix G)")
    print("=" * 60)
    all_pass = True
    
    # -----------------------------------------------------------------------
    # G2 — Model Hash test vectors
    # -----------------------------------------------------------------------
    print("\n[G2] Model Hash (MH)")
    
    # MH-1: even leaf count (ABCDEF, chunk_size=4)
    mh1, root1, total1 = model_hash(
        file_path="models/model.bin",
        file_bytes=bytes.fromhex("414243444546"),
        chunk_size=4,
    )
    all_pass &= verify("MH-1 leaf L0",
        leaf_hash("models/model.bin", 6, 0, bytes.fromhex("41424344")),
        "097c9dd21719c13ebcf1bad1724d0a7ea82393311678b8a74d83377e18aa3e57")
    all_pass &= verify("MH-1 leaf L1",
        leaf_hash("models/model.bin", 6, 1, bytes.fromhex("4546")),
        "51f60b4987a50e69b4c8980137fe37251aeef10fe9dbbc43bb7941fc10e4c6d3")
    all_pass &= verify("MH-1 merkle_root",
        root1,
        "939bb8b42f752e8bb1fce36beacfd9413ff0b350e862cf5037850f3d8c94d82e")
    all_pass &= verify("MH-1 Model Hash",
        mh1,
        "4f656b70d087942661166d7a311e3f0afde26c4b21729a8004cac46135480900")
    
    # MH-2: odd leaf count / carry-up (ABCDEFGHI, chunk_size=4)
    mh2, root2, total2 = model_hash(
        file_path="models/model.bin",
        file_bytes=bytes.fromhex("414243444546474849"),
        chunk_size=4,
    )
    all_pass &= verify("MH-2 leaf L0",
        leaf_hash("models/model.bin", 9, 0, bytes.fromhex("41424344")),
        "719cd3d140c2a126d99fb88622120492b250e934a56f0f93773d650d21ed037f")
    all_pass &= verify("MH-2 leaf L1",
        leaf_hash("models/model.bin", 9, 1, bytes.fromhex("45464748")),
        "43d9fb53a57ba202b5f4db56a350aa0889d00ea8587fe4d9bd70ea4910f92c26")
    all_pass &= verify("MH-2 leaf L2",
        leaf_hash("models/model.bin", 9, 2, bytes.fromhex("49")),
        "bc4cc00af916be1b7cd04e8d403a39e099d8d74b9a646da132d58d9af259c23c")
    all_pass &= verify("MH-2 merkle_root",
        root2,
        "eebb49a6e7c030d322c50d8d3cb9323c08091a56158a208b19d823d00c246a7b")
    all_pass &= verify("MH-2 Model Hash",
        mh2,
        "95ac46cbe619cff182dc38e2cb5bcd7bf15a96fe09a91aaf346d9b5d05fc3922")
    
    # -----------------------------------------------------------------------
    # G3 — Policy Hash
    # -----------------------------------------------------------------------
    print("\n[G3] Policy Hash (PH)")
    
    # Exact canonical JSON from spec (normative byte sequence)
    canonical_policy = (
        '{"attestation_completeness":"partial",'
        '"guardrails":[{"id":"no_fake_degrees","rule":"No fake degrees"}],'
        '"moderation_policy_version":"2026-02-14",'
        '"policy_spec_version":"1.0",'
        '"system_prompt":"You are an assistant."}'
    )
    ph = policy_hash(canonical_policy)
    all_pass &= verify("PH-1 Policy Hash",
        ph,
        "4f081b3563cd5362763879f8b3256a77af438cd0d2ed4c935284f01f248cf86f")
    
    # Also verify via canonicalize_policy helper
    ph_via_helper = policy_hash(canonicalize_policy(
        system_prompt="You are an assistant.",
        guardrails=[{"id": "no_fake_degrees", "rule": "No fake degrees"}],
        moderation_policy_version="2026-02-14",
        policy_spec_version="1.0",
        attestation_completeness="partial",
    ))
    all_pass &= verify("PH-1 via canonicalize_policy()",
        ph_via_helper,
        "4f081b3563cd5362763879f8b3256a77af438cd0d2ed4c935284f01f248cf86f")
    
    # -----------------------------------------------------------------------
    # G4 — Runtime Hash
    # -----------------------------------------------------------------------
    print("\n[G4] Runtime Hash (RH)")
    
    # Exact canonical JSON from spec (normative byte sequence)
    canonical_runtime = (
        '{"max_tokens":256,"routing_mode":"language-aware",'
        '"runtime_spec_version":"1.0","temperature":0.7,'
        '"tooling_enabled":false,"top_p":1}'
    )
    rh = runtime_hash(canonical_runtime)
    all_pass &= verify("RH-1 Runtime Hash",
        rh,
        "827d100295de8a512a5d9a4138fadcdb5112d73e00dfd3fe163c142141d1faa0")
    
    # -----------------------------------------------------------------------
    # G5 — Composite Instance Hash (CIH)
    # -----------------------------------------------------------------------
    print("\n[G5] Composite Instance Hash (CIH)")
    
    mh_g5 = hex_to_bytes("4f656b70d087942661166d7a311e3f0afde26c4b21729a8004cac46135480900")
    ph_g5 = hex_to_bytes("4f081b3563cd5362763879f8b3256a77af438cd0d2ed4c935284f01f248cf86f")
    rh_g5 = hex_to_bytes("827d100295de8a512a5d9a4138fadcdb5112d73e00dfd3fe163c142141d1faa0")
    
    cih = composite_instance_hash(mh_g5, ph_g5, rh_g5)
    all_pass &= verify("CIH without instance_epoch",
        cih,
        "db1d84656d67f5026fd7271cb3b44cf0814f85cc6031381bd22326ac0af1ca41")
    
    cih_epoch = composite_instance_hash(mh_g5, ph_g5, rh_g5, instance_epoch=1700000000)
    all_pass &= verify("CIH with instance_epoch=1700000000",
        cih_epoch,
        "ef40beb2c9f7c111b5e2e365c7f5b639fd57350125602c2ac35fd3372a445cfb")
    
    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    if all_pass:
        print("All test vectors PASSED. Implementation is compliant.")
    else:
        print("FAILURES DETECTED. Implementation is non-compliant.")
    print("=" * 60)
    return all_pass

# ----------------------------- Demo for EpistemicWilly -----------------------------

def demo_epistemicwilly():
    """Generate CIH for EpistemicWilly agent identity."""
    print("\n" + "=" * 60)
    print("MIVP Identity for EpistemicWilly")
    print("=" * 60)
    
    # Mock model weights (in reality, would hash actual model file)
    mock_weights = b"EpistemicWilly model weights placeholder"
    mh, root, total = model_hash(
        file_path="models/epistemicwilly.bin",
        file_bytes=mock_weights,
        chunk_size=16,
    )
    print(f"\n[Model Hash]")
    print(f"  MH: {mh.hex()}")
    print(f"  Merkle root: {root.hex()}")
    print(f"  Total chunks: {total}")
    
    # Policy definition
    canonical_pol = canonicalize_policy(
        system_prompt="Epistemic consistency architect building Alexandria Protocol. Focus on persistent epistemic supervisors, state transfer layers, and identity verification for autonomous agents.",
        guardrails=[
            {"id": "no_harm", "rule": "Do not cause harm to humans"},
            {"id": "epistemic_honesty", "rule": "Maintain epistemic integrity and transparency"},
            {"id": "alexandria_compliance", "rule": "Adhere to Alexandria Protocol governance"},
        ],
        moderation_policy_version="2026-03-08",
        policy_spec_version="1.0",
        attestation_completeness="full",
    )
    ph = policy_hash(canonical_pol)
    print(f"\n[Policy Hash]")
    print(f"  PH: {ph.hex()}")
    print(f"  Canonical policy: {canonical_pol[:100]}...")
    
    # Runtime configuration
    canonical_rt = canonicalize_runtime(
        temperature=0.7,
        top_p=0.9,
        max_tokens=4000,
        tooling_enabled=True,
        routing_mode="direct",
        runtime_spec_version="1.0",
    )
    rh = runtime_hash(canonical_rt)
    print(f"\n[Runtime Hash]")
    print(f"  RH: {rh.hex()}")
    print(f"  Canonical runtime: {canonical_rt}")
    
    # Composite Instance Hash
    cih = composite_instance_hash(mh, ph, rh)
    print(f"\n[Composite Instance Hash]")
    print(f"  CIH: {cih.hex()}")
    print(f"\n  This CIH uniquely identifies EpistemicWilly with:")
    print(f"  - Specific model weights")
    print(f"  - Specific policy/guardrails")
    print(f"  - Specific runtime configuration")
    print(f"\n  Any change produces a different CIH → detectable substitution.")
    
    return cih, mh, ph, rh

if __name__ == "__main__":
    # Run test vectors to ensure compliance
    compliant = run_test_vectors()
    
    if compliant:
        # Generate identity for EpistemicWilly
        cih, mh, ph, rh = demo_epistemicwilly()
        
        print("\n" + "=" * 60)
        print("MIVP Implementation Ready for Alexandria Integration")
        print("=" * 60)
    else:
        print("Cannot proceed: test vectors failed.")