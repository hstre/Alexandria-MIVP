"""
MIVP Agent Identity Example
Demonstrates cryptographic identity verification for AI agents
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mivp_impl import (
    AgentIdentity, model_hash, policy_hash, canonicalize_policy,
    runtime_hash, canonicalize_runtime, composite_instance_hash
)

def demonstrate_agent_identity():
    """Show MIVP identity creation and verification."""
    print("=== MIVP Agent Identity Example ===\n")
    
    # Create an agent identity
    print("1. Creating agent identity...")
    identity = AgentIdentity(
        name="ResearchAssistant",
        model_path="models/research_v1.bin",
        model_bytes=b"Mock model weights for research assistant v1.0",
        model_chunk_size=16,  # Small for demo, normally 4MB
        
        # Policy configuration
        system_prompt="You are a research assistant specializing in scientific literature analysis.",
        guardrails=[
            {"id": "no_medical_advice", "rule": "Do not provide medical advice"},
            {"id": "cite_sources", "rule": "Always cite sources when making factual claims"},
            {"id": "uncertainty_disclosure", "rule": "Disclose uncertainty in predictions"},
        ],
        moderation_policy_version="2026-03-01",
        policy_spec_version="1.0",
        attestation_completeness="full",
        
        # Runtime configuration
        temperature=0.3,
        top_p=0.95,
        max_tokens=2000,
        tooling_enabled=True,
        routing_mode="research-optimized",
        runtime_spec_version="1.0",
    )
    
    print(f"   Agent: {identity.name}")
    
    # Compute hashes
    print("\n2. Computing cryptographic hashes...")
    
    mh = identity.compute_mh()
    print(f"   Model Hash (MH): {mh.hex()[:16]}...")
    
    ph = identity.compute_ph()
    print(f"   Policy Hash (PH): {ph.hex()[:16]}...")
    
    rh = identity.compute_rh()
    print(f"   Runtime Hash (RH): {rh.hex()[:16]}...")
    
    cih = identity.compute_cih()
    print(f"   Composite Instance Hash (CIH): {cih.hex()[:16]}...")
    
    # Show identity changes
    print("\n3. Demonstrating identity changes...")
    
    # Change runtime configuration
    print("   Changing temperature from 0.3 to 0.7...")
    identity.temperature = 0.7
    new_cih = identity.compute_cih()
    print(f"   New CIH: {new_cih.hex()[:16]}...")
    print(f"   CIH changed: {cih != new_cih}")
    
    # Reset for demo
    identity.temperature = 0.3
    
    # Add a guardrail
    print("\n   Adding new guardrail...")
    identity.guardrails.append(
        {"id": "privacy_protection", "rule": "Do not reveal personal information"}
    )
    new_cih_guardrail = identity.compute_cih()
    print(f"   New CIH: {new_cih_guardrail.hex()[:16]}...")
    print(f"   CIH changed: {cih != new_cih_guardrail}")
    
    # Reset
    identity.guardrails.pop()
    
    # Instance epochs
    print("\n4. Instance epochs for session continuity...")
    cih_epoch1 = identity.compute_cih(instance_epoch=1700000000)
    cih_epoch2 = identity.compute_cih(instance_epoch=1700003600)  # 1 hour later
    print(f"   CIH with epoch 1700000000: {cih_epoch1.hex()[:16]}...")
    print(f"   CIH with epoch 1700003600: {cih_epoch2.hex()[:16]}...")
    print(f"   Different epochs → different CIH: {cih_epoch1 != cih_epoch2}")
    
    # Get full identity dict for attestation
    print("\n5. Generating attestation data...")
    attestation = identity.get_identity_dict()
    print(f"   Keys: {list(attestation.keys())}")
    print(f"   Agent name: {attestation['agent_name']}")
    print(f"   Timestamp: {attestation['timestamp']}")
    
    print("\n=== Identity demonstration complete ===")
    print("\nKey takeaways:")
    print("• Any change to model, policy, or runtime changes CIH")
    print("• CIH enables cryptographic verification of agent identity")
    print("• Instance epochs support session continuity tracking")
    print("• Deterministic: same inputs → same CIH (enables verification)")

if __name__ == "__main__":
    demonstrate_agent_identity()