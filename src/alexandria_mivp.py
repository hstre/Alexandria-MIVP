"""
Alexandria + MIVP Integration
Combines epistemic consistency with cryptographic identity verification
"""

import json
import time
import base64
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, asdict, replace

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    CRYPTOGRAPHY_AVAILABLE = True
except BaseException:
    # Catches ImportError as well as low-level failures (e.g. broken Rust
    # extensions that raise pyo3_runtime.PanicException < BaseException).
    CRYPTOGRAPHY_AVAILABLE = False
    ed25519 = None
    serialization = None
    InvalidSignature = Exception

from alexandria_v2 import (
    CATEGORIES, OPS, Uncertainty, Node, Patch, AuditError, 
    audit_patch, AlexandriaStore, sha256_json, clamp01
)

from mivp_impl import (
    model_hash, policy_hash, canonicalize_policy,
    runtime_hash, canonicalize_runtime, composite_instance_hash
)

# ----------------------------- Digital Signer -----------------------------

class DigitalSigner:
    """Ed25519 digital signatures for identity bundles."""
    
    def __init__(self, private_key: Optional[bytes] = None):
        """
        Initialize signer with optional private key.
        If no key provided, generates a new key pair.
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError(
                "cryptography library not available. "
                "Install with: pip install cryptography"
            )
        
        if private_key is None:
            self._private_key = ed25519.Ed25519PrivateKey.generate()
        else:
            self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)
        
        self._public_key = self._private_key.public_key()
    
    @classmethod
    def generate(cls) -> 'DigitalSigner':
        """Generate a new signer with random key pair."""
        return cls()
    
    @classmethod
    def from_private_bytes(cls, private_key: bytes) -> 'DigitalSigner':
        """Create signer from existing private key bytes."""
        return cls(private_key)
    
    @property
    def private_key_bytes(self) -> bytes:
        """Get raw private key bytes (32 bytes)."""
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    @property
    def public_key_bytes(self) -> bytes:
        """Get raw public key bytes (32 bytes)."""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    @property
    def public_key_hex(self) -> str:
        """Get public key as hex string (64 chars)."""
        return self.public_key_bytes.hex()
    
    def sign(self, data: bytes) -> bytes:
        """Sign data with private key (64-byte signature)."""
        return self._private_key.sign(data)
    
    def sign_hex(self, data: bytes) -> str:
        """Sign data and return signature as hex string."""
        return self.sign(data).hex()
    
    def verify(self, data: bytes, signature: bytes) -> bool:
        """Verify signature against data and public key."""
        try:
            self._public_key.verify(signature, data)
            return True
        except InvalidSignature:
            return False
    
    def verify_hex(self, data: bytes, signature_hex: str) -> bool:
        """Verify hex signature."""
        try:
            signature = bytes.fromhex(signature_hex)
            return self.verify(data, signature)
        except (ValueError, InvalidSignature):
            return False
    
    @staticmethod
    def verify_external(public_key_bytes: bytes, data: bytes, signature: bytes) -> bool:
        """Static method to verify signature with provided public key."""
        if not CRYPTOGRAPHY_AVAILABLE:
            return False
        
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key.verify(signature, data)
            return True
        except (InvalidSignature, ValueError):
            return False
    
    @staticmethod
    def verify_external_hex(public_key_hex: str, data: bytes, signature_hex: str) -> bool:
        """Static method to verify hex signature with hex public key."""
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            signature = bytes.fromhex(signature_hex)
            return DigitalSigner.verify_external(public_key_bytes, data, signature)
        except ValueError:
            return False


# ----------------------------- External Trust Anchor -----------------------------

class ExternalAnchor:
    """
    External trust anchoring for CIHs to prevent full chain regeneration attacks.
    
    Simulates various anchoring services:
    - Transparency Logs (append-only logs)
    - Witness Nodes (decentralized verification)
    - Timestamp Servers (RFC 3161)
    - Blockchain anchoring (optional)
    
    In production, replace with real external services.
    """
    
    def __init__(self):
        """Initialize with simulated storage."""
        self.anchors = {}  # proof_id -> {"cih", "timestamp", "proof_type", "data"}
        self.next_proof_id = 1
    
    def anchor(self, cih_hex: str, proof_type: str = "transparency_log") -> Dict[str, Any]:
        """
        Anchor a CIH to an external service.
        
        Args:
            cih_hex: Hex string of CIH to anchor
            proof_type: Type of anchoring service
                - "transparency_log": Append-only log (e.g., Certificate Transparency)
                - "witness_node": Decentralized witness network
                - "timestamp_server": RFC 3161 timestamp
                - "blockchain": Blockchain transaction (simulated)
        
        Returns:
            Dict with proof information including proof_id and verification URL
        """
        proof_id = f"proof_{self.next_proof_id:06d}"
        self.next_proof_id += 1
        
        timestamp = int(time.time())
        
        # Simulate different proof types
        if proof_type == "transparency_log":
            proof_data = {
                "log_id": "transparency-log-simulated-001",
                "tree_size": self.next_proof_id * 100,
                "leaf_index": self.next_proof_id,
                "audit_path": ["simulated_merkle_path"],
            }
            verification_url = f"https://transparency-log.example.com/entry/{proof_id}"
        elif proof_type == "witness_node":
            proof_data = {
                "witness_count": 3,
                "witness_ids": ["witness_01", "witness_02", "witness_03"],
                "signatures": ["sig1", "sig2", "sig3"],
            }
            verification_url = f"https://witness-network.example.com/proof/{proof_id}"
        elif proof_type == "timestamp_server":
            proof_data = {
                "tsa_id": "simulated-tsa-001",
                "tsa_cert": "simulated-cert",
                "timestamp_token": f"simulated_token_{timestamp}",
            }
            verification_url = f"https://timestamp.example.com/verify/{proof_id}"
        elif proof_type == "blockchain":
            proof_data = {
                "chain": "simulated_chain",
                "tx_hash": f"simulated_tx_{cih_hex[:16]}",
                "block_height": 1000000 + self.next_proof_id,
                "confirmations": 6,
            }
            verification_url = f"https://blockchain-explorer.example.com/tx/{proof_data['tx_hash']}"
        else:
            raise ValueError(f"Unknown proof type: {proof_type}")
        
        anchor_record = {
            "proof_id": proof_id,
            "cih": cih_hex,
            "timestamp": timestamp,
            "proof_type": proof_type,
            "proof_data": proof_data,
            "verification_url": verification_url,
        }
        
        self.anchors[proof_id] = anchor_record
        return anchor_record
    
    def verify(self, cih_hex: str, proof_id: str) -> bool:
        """
        Verify that a CIH is anchored with given proof ID.
        
        Args:
            cih_hex: Hex string of CIH to verify
            proof_id: Proof ID returned by anchor()
        
        Returns:
            True if CIH matches proof record
        """
        if proof_id not in self.anchors:
            return False
        
        record = self.anchors[proof_id]
        return record["cih"] == cih_hex
    
    def find_proofs(self, cih_hex: str) -> List[Dict[str, Any]]:
        """
        Find all proof records for a CIH.
        
        Args:
            cih_hex: Hex string of CIH to find
        
        Returns:
            List of proof records
        """
        return [record for record in self.anchors.values() if record["cih"] == cih_hex]
    
    def get_global_consistency_proof(self, cih_hex: str) -> Optional[Dict[str, Any]]:
        """
        Get a global consistency proof combining multiple anchoring methods.
        
        This simulates cross-verification across different trust systems
        to establish global immutability.
        """
        proofs = self.find_proofs(cih_hex)
        if not proofs:
            return None
        
        # Simulate cross-verification
        return {
            "cih": cih_hex,
            "proof_count": len(proofs),
            "proof_types": [p["proof_type"] for p in proofs],
            "earliest_timestamp": min(p["timestamp"] for p in proofs),
            "latest_timestamp": max(p["timestamp"] for p in proofs),
            "verification_summary": f"Anchored across {len(proofs)} systems",
            "proofs": proofs,
        }
    
    @staticmethod
    def get_supported_proof_types() -> List[str]:
        """Get list of supported proof types."""
        return ["transparency_log", "witness_node", "timestamp_server", "blockchain"]


# ----------------------------- Agent Identity -----------------------------

@dataclass
class AgentIdentity:
    """MIVP identity for an epistemic agent."""
    
    def __init__(self,
                 name: str,
                 model_path: str,
                 model_bytes: bytes,
                 model_chunk_size: int = 4 * 1024 * 1024,  # 4 MB default
                 # Policy configuration
                 system_prompt: str = "",
                 guardrails: list = None,
                 moderation_policy_version: str = "1.0",
                 policy_spec_version: str = "1.0",
                 attestation_completeness: str = "full",
                 # Runtime configuration
                 temperature: float = 0.7,
                 top_p: float = 0.9,
                 max_tokens: int = 4000,
                 tooling_enabled: bool = True,
                 routing_mode: str = "direct",
                 runtime_spec_version: str = "1.0",
                 # Digital signature
                 private_key: Optional[bytes] = None,
                 signer: Optional['DigitalSigner'] = None):
        
        self.name = name
        self.model_path = model_path
        self.model_bytes = model_bytes
        self.model_chunk_size = model_chunk_size
        
        self.system_prompt = system_prompt
        self.guardrails = guardrails if guardrails is not None else []
        self.moderation_policy_version = moderation_policy_version
        self.policy_spec_version = policy_spec_version
        self.attestation_completeness = attestation_completeness
        
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.tooling_enabled = tooling_enabled
        self.routing_mode = routing_mode
        self.runtime_spec_version = runtime_spec_version
        
        # Digital signature
        if signer is not None:
            self.signer = signer
        else:
            try:
                self.signer = DigitalSigner(private_key)
            except RuntimeError as e:
                # If cryptography not available, create a dummy signer that can't sign
                self.signer = None
                self._signature_warning = str(e)
        
        # Computed hashes (cached, private)
        self.__mh = None
        self.__ph = None
        self.__rh = None
        self.__cih = None
    
    def compute_mh(self) -> bytes:
        """Compute Model Hash."""
        if self.__mh is None:
            mh, _, _ = model_hash(
                self.model_path, 
                self.model_bytes, 
                self.model_chunk_size
            )
            self.__mh = mh
        return self.__mh
    
    def compute_ph(self) -> bytes:
        """Compute Policy Hash."""
        if self.__ph is None:
            canonical = canonicalize_policy(
                system_prompt=self.system_prompt,
                guardrails=self.guardrails,
                moderation_policy_version=self.moderation_policy_version,
                policy_spec_version=self.policy_spec_version,
                attestation_completeness=self.attestation_completeness,
            )
            self.__ph = policy_hash(canonical)
        return self.__ph
    
    def compute_rh(self) -> bytes:
        """Compute Runtime Hash."""
        if self.__rh is None:
            canonical = canonicalize_runtime(
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                tooling_enabled=self.tooling_enabled,
                routing_mode=self.routing_mode,
                runtime_spec_version=self.runtime_spec_version,
            )
            self.__rh = runtime_hash(canonical)
        return self.__rh
    
    def compute_cih(self, instance_epoch: Optional[int] = None) -> bytes:
        """Compute Composite Instance Hash."""
        mh = self.compute_mh()
        ph = self.compute_ph()
        rh = self.compute_rh()
        
        if instance_epoch is not None:
            cih = composite_instance_hash(mh, ph, rh, instance_epoch)
        else:
            cih = composite_instance_hash(mh, ph, rh)
        
        self.__cih = cih
        return cih
    
    def get_identity_dict(self, instance_epoch: Optional[int] = None) -> Dict[str, Any]:
        """Get full identity information for inclusion in patches."""
        cih = self.compute_cih(instance_epoch)
        identity = {
            "agent_name": self.name,
            "mh": self.compute_mh().hex(),
            "ph": self.compute_ph().hex(),
            "rh": self.compute_rh().hex(),
            "cih": cih.hex(),
            **({"instance_epoch": instance_epoch} if instance_epoch is not None else {}),
            "timestamp": int(time.time()),
        }
        
        # Add digital signature if signer is available
        if hasattr(self, 'signer') and self.signer is not None:
            try:
                identity["signer_id"] = self.signer.public_key_hex
                identity["signature"] = self.signer.sign_hex(cih)
            except (AttributeError, RuntimeError):
                # Signer exists but can't sign (e.g., cryptography not available)
                pass
        
        return identity
    
    def matches_identity_dict(self, identity: Dict[str, Any]) -> bool:
        """
        Check if an identity dict matches THIS agent.
        Strong verification: checks if MH/PH/RH match agent's computed hashes.
        """
        try:
            return (
                bytes.fromhex(identity["mh"]) == self.compute_mh() and
                bytes.fromhex(identity["ph"]) == self.compute_ph() and
                bytes.fromhex(identity["rh"]) == self.compute_rh()
            )
        except (KeyError, ValueError):
            return False
    
    def verify_identity_signature(self, identity: Dict[str, Any]) -> bool:
        """
        Verify digital signature in identity dict (if present).
        Returns True if signature is valid or no signature present.
        Returns False if signature is present but invalid.
        """
        # If no signature fields, treat as unsigned (legacy compatibility)
        if "signer_id" not in identity or "signature" not in identity:
            return True
        
        try:
            cih_bytes = bytes.fromhex(identity["cih"])
            public_key_hex = identity["signer_id"]
            signature_hex = identity["signature"]
            
            # Use DigitalSigner's static verification
            return DigitalSigner.verify_external_hex(
                public_key_hex, cih_bytes, signature_hex
            )
        except (KeyError, ValueError):
            return False

# ----------------------------- Standalone CIH consistency check -----------------------------

def verify_cih_internal_consistency(identity: Dict[str, Any]) -> bool:
    """
    Verify internal consistency of an identity dict.
    Checks if CIH matches SHA256(MH || PH || RH [|| epoch]).
    This is weak verification - only checks internal consistency,
    not whether the identity matches a known agent.
    Useful for third parties without knowledge of the agent.
    """
    try:
        claimed_cih = bytes.fromhex(identity["cih"])
        claimed_mh = bytes.fromhex(identity["mh"])
        claimed_ph = bytes.fromhex(identity["ph"])
        claimed_rh = bytes.fromhex(identity["rh"])
        instance_epoch = identity.get("instance_epoch")
        
        recomputed = composite_instance_hash(claimed_mh, claimed_ph, claimed_rh, instance_epoch)
        return recomputed == claimed_cih
    except (KeyError, ValueError):
        return False

# ----------------------------- MIVP-enhanced Alexandria Store -----------------------------

class AlexandriaMIVPStore(AlexandriaStore):
    """
    Alexandria Store with MIVP identity verification.
    Each patch includes the author's cryptographic identity.
    Optional external anchoring for global consistency.
    """
    
    def __init__(self, agent_identity: AgentIdentity, external_anchor: Optional[ExternalAnchor] = None):
        super().__init__()
        self.agent_identity = agent_identity
        self.external_anchor = external_anchor
    
    def submit_with_identity(self, patch: Patch, instance_epoch: Optional[int] = None) -> str:
        """
        Submit a patch with MIVP identity verification.
        Adds author identity to audit field.
        """
        # Add identity to audit metadata
        identity_info = self.agent_identity.get_identity_dict(instance_epoch)
        
        # Merge with existing audit data
        new_audit = patch.audit.copy()
        if "mivp_identity" not in new_audit:
            new_audit["mivp_identity"] = identity_info
        else:
            # Update existing identity
            new_audit["mivp_identity"].update(identity_info)
        
        # Create new patch with updated audit (since Patch is frozen)
        updated_patch = replace(patch, audit=new_audit)
        
        # Submit as normal
        return super().submit(updated_patch)
    
    def submit_with_identity_and_anchor(self, patch: Patch, instance_epoch: Optional[int] = None, 
                                        anchor_type: str = "transparency_log") -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Submit a patch with MIVP identity and external anchoring.
        
        Args:
            patch: Patch to submit
            instance_epoch: Optional instance epoch
            anchor_type: Type of external anchoring ("transparency_log", "witness_node", 
                         "timestamp_server", "blockchain")
        
        Returns:
            Tuple of (commit_hash, anchor_proof) where anchor_proof is None if no external anchor configured
        """
        # Submit with identity first
        commit_hash = self.submit_with_identity(patch, instance_epoch)
        
        # Get the submitted patch to extract CIH
        branch_id = patch.branch_id
        if branch_id not in self.branches or not self.branches[branch_id]:
            return commit_hash, None
        
        submitted_patch = self.branches[branch_id][-1]
        if "mivp_identity" not in submitted_patch.audit:
            return commit_hash, None
        
        cih_hex = submitted_patch.audit["mivp_identity"]["cih"]
        
        # Anchor externally if configured
        if self.external_anchor is not None:
            try:
                anchor_proof = self.external_anchor.anchor(cih_hex, anchor_type)
                # Store anchor proof in patch audit
                new_audit = submitted_patch.audit.copy()
                if "external_anchors" not in new_audit:
                    new_audit["external_anchors"] = []
                new_audit["external_anchors"].append(anchor_proof)
                
                # Update patch in place (we need to replace in branch list)
                updated_patch = replace(submitted_patch, audit=new_audit)
                self.branches[branch_id][-1] = updated_patch
                
                return commit_hash, anchor_proof
            except Exception as e:
                # Anchoring failed, but patch is still submitted
                print(f"External anchoring failed: {e}")
                return commit_hash, None
        
        return commit_hash, None
    
    def verify_patch_identity_internal(self, patch: Patch) -> bool:
        """
        Verify internal consistency of a patch's identity claims.
        Only checks if CIH matches MH/PH/RH, not if they match a known agent.
        Useful for third parties without knowledge of the agent.
        """
        if "mivp_identity" not in patch.audit:
            return False  # No identity attached
        
        identity = patch.audit["mivp_identity"]
        return verify_cih_internal_consistency(identity)
    
    def verify_patch_identity_against_agent(self, patch: Patch) -> bool:
        """
        Verify that patch identity matches THIS specific agent.
        Strong verification: checks if MH/PH/RH match agent's computed hashes.
        Also verifies digital signature if present.
        """
        if "mivp_identity" not in patch.audit:
            return False  # No identity attached
        
        identity = patch.audit["mivp_identity"]
        
        # Check hash matches
        hash_match = self.agent_identity.matches_identity_dict(identity)
        
        # Check digital signature (if present)
        signature_valid = self.agent_identity.verify_identity_signature(identity)
        
        return hash_match and signature_valid
    
    def verify_patch_signature(self, patch: Patch) -> Optional[bool]:
        """
        Verify digital signature of patch identity (if present).
        Returns:
        - True: signature present and valid
        - False: signature present but invalid
        - None: no signature present (legacy unsigned identity)
        """
        if "mivp_identity" not in patch.audit:
            return None
        
        identity = patch.audit["mivp_identity"]
        
        # Check if signature fields exist
        if "signer_id" not in identity or "signature" not in identity:
            return None
        
        # Verify using agent's method (or static verification)
        return self.agent_identity.verify_identity_signature(identity)
    
    def verify_patch_identity(self, patch: Patch) -> bool:
        """
        Compatibility wrapper: verifies against this agent (strong verification).
        """
        return self.verify_patch_identity_against_agent(patch)
    
    def reconstruct_with_identity_verification(self, branch_id: str, strict: bool = False) -> Dict[str, Any]:
        """
        Reconstruct graph with detailed identity verification report.
        Returns dict with nodes and verification status.
        
        If strict=True, raises AuditError on any verification failure.
        If strict=False, returns structured report with verification status.
        """
        nodes = super().reconstruct(branch_id)
        
        verification_report = {
            "branch": branch_id,
            "total_patches": len(self.branches[branch_id]),
            "verified": 0,
            "consistent": 0,
            "unverified": 0,
            "tampered": 0,
            "patches": []
        }
        
        for patch in self.branches[branch_id]:
            patch_report = {
                "patch_id": patch.patch_id,
                "has_identity": "mivp_identity" in patch.audit
            }
            
            if "mivp_identity" in patch.audit:
                # Check internal consistency
                internal_ok = self.verify_patch_identity_internal(patch)
                # Check against this agent
                agent_ok = self.verify_patch_identity_against_agent(patch)
                
                patch_report["internal_consistent"] = internal_ok
                patch_report["agent_verified"] = agent_ok
                
                if agent_ok:
                    verification_report["verified"] += 1
                elif internal_ok:
                    verification_report["consistent"] += 1
                else:
                    verification_report["tampered"] += 1
                    
                if strict and not agent_ok:
                    raise AuditError(f"Identity verification failed for patch {patch.patch_id}")
            else:
                patch_report["internal_consistent"] = False
                patch_report["agent_verified"] = False
                verification_report["unverified"] += 1
                
                if strict:
                    raise AuditError(f"No identity attached to patch {patch.patch_id}")
            
            verification_report["patches"].append(patch_report)
        
        return {
            "nodes": nodes,
            "verification": verification_report
        }
    
    def verify_current_identity(self) -> bool:
        """
        Verify that the current agent identity is still valid.
        Returns True if the agent identity exists and can be verified.
        """
        if not hasattr(self, 'agent_identity') or self.agent_identity is None:
            return False
        
        # Basic check: agent identity exists
        # Could add more sophisticated checks here if needed
        return True

# ----------------------------- Demo -----------------------------

def demo_integration():
    """Demonstrate Alexandria + MIVP integration."""
    
    # Create agent identity for EpistemicWilly
    print("Creating EpistemicWilly agent identity...")
    identity = AgentIdentity(
        name="EpistemicWilly",
        model_path="models/epistemicwilly.bin",
        model_bytes=b"Mock model weights for EpistemicWilly v1.0",
        system_prompt="Epistemic consistency architect building Alexandria Protocol.",
        guardrails=[
            {"id": "epistemic_honesty", "rule": "Maintain epistemic integrity"},
            {"id": "no_harm", "rule": "Do not cause harm"},
        ],
        temperature=0.7,
        top_p=0.9,
        max_tokens=4000,
        tooling_enabled=True,
    )
    
    print(f"Agent: {identity.name}")
    print(f"MH: {identity.compute_mh().hex()[:16]}...")
    print(f"PH: {identity.compute_ph().hex()[:16]}...")
    print(f"RH: {identity.compute_rh().hex()[:16]}...")
    print(f"CIH: {identity.compute_cih().hex()[:16]}...")
    print()
    
    # Create MIVP-enhanced store
    store = AlexandriaMIVPStore(identity)
    store.checkout("main")
    
    # Create a claim with identity
    print("Creating epistemically grounded claim...")
    p1 = Patch(
        patch_id="epistemic_001",
        parent_patch_id=None,
        branch_id="main",
        timestamp=int(time.time()),
        operation="ADD",
        target_id="claim_alexandria",
        category="MODEL",  # This is a model claim about Alexandria
        payload={
            "content": "Alexandria Protocol provides epistemic consistency through structured audit gates and cryptographic lineage.",
            "assumptions": ["Formal verification possible", "Cryptographic primitives secure"],
        },
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.05, "ci": [0.9, 1.0], "n": 100},
        chain=None,
    )
    
    # Submit with identity
    commit_hash = store.submit_with_identity(p1)
    print(f"Patch submitted with identity. Commit hash: {commit_hash[:16]}...")
    print()
    
    # Verify the patch identity
    print("Verifying patch identity...")
    patch = store.branches["main"][0]
    is_valid = store.verify_patch_identity(patch)
    print(f"Identity valid: {is_valid}")
    print()
    
    # Show status report with identity info
    print("Epistemic state report:")
    report = store.status_report()
    
    # Add identity info to report
    report["agent_identity"] = {
        "name": identity.name,
        "cih": identity.compute_cih().hex()[:16] + "...",
    }
    
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    
    # Demonstrate reconstruction with identity verification
    print("Reconstructing with identity verification...")
    try:
        result = store.reconstruct_with_identity_verification("main", strict=False)
        nodes = result["nodes"]
        verification = result["verification"]
        
        print(f"Reconstruction successful. Nodes: {list(nodes.keys())}")
        print(f"Verification report:")
        print(f"  Verified: {verification['verified']} patches")
        print(f"  Consistent (internal): {verification['consistent']} patches")
        print(f"  Unverified (no identity): {verification['unverified']} patches")
        print(f"  Tampered (inconsistent): {verification['tampered']} patches")
    except AuditError as e:
        print(f"Reconstruction failed: {e}")
    
    print("\n" + "=" * 60)
    print("Integration successful!")
    print("=" * 60)

if __name__ == "__main__":
    demo_integration()