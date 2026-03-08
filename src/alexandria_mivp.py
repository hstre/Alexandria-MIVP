"""
Alexandria + MIVP Integration
Combines epistemic consistency with cryptographic identity verification
"""

import json
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, replace

from alexandria_v2 import (
    CATEGORIES, OPS, Uncertainty, Node, Patch, AuditError, 
    audit_patch, AlexandriaStore, sha256_json, clamp01
)

from mivp_impl import (
    model_hash, policy_hash, canonicalize_policy,
    runtime_hash, canonicalize_runtime, composite_instance_hash
)

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
                 runtime_spec_version: str = "1.0"):
        
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
        return {
            "agent_name": self.name,
            "mh": self.compute_mh().hex(),
            "ph": self.compute_ph().hex(),
            "rh": self.compute_rh().hex(),
            "cih": self.compute_cih(instance_epoch).hex(),
            **({"instance_epoch": instance_epoch} if instance_epoch is not None else {}),
            "timestamp": int(time.time()),
        }
    
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
    """
    
    def __init__(self, agent_identity: AgentIdentity):
        super().__init__()
        self.agent_identity = agent_identity
    
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
        """
        if "mivp_identity" not in patch.audit:
            return False  # No identity attached
        
        identity = patch.audit["mivp_identity"]
        return self.agent_identity.matches_identity_dict(identity)
    
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