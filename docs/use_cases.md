# Use Cases

## Overview

Alexandria Protocol + MIVP enables a new paradigm of **verifiable, auditable, epistemically coherent autonomous systems**. This document outlines concrete use cases across different domains.

## Research & Academia

### 1. Reproducible Scientific Experiments
**Problem:** Research papers often lack complete reproducibility information - which exact model, prompt, and parameters were used?

**Solution:** Epistemic claims with cryptographic attestation.

**Workflow:**
```
Researcher → Experimental Setup → Alexandria Patches → MIVP Attestation → Paper Submission
                                      ↓
                            Verifiable Claim Trail
                                      ↓
                            Other Researchers → Verification → Reproduction
```

**Example:**
```python
# In research notebook
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from alexandria_v2 import Patch

# Define experimental identity
identity = AgentIdentity(
    name="LLM_Benchmark_Study_v1",
    model_path="models/llama3_70b.bin",
    model_bytes=model_weights,
    system_prompt="Evaluate mathematical reasoning",
    guardrails=[{"id": "no_leak", "rule": "Don't leak test answers"}],
    temperature=0.0,
    top_p=1.0,
    max_tokens=512
)

store = AlexandriaMIVPStore(identity)

# Record experimental claims
patch = Patch(
    operation="ADD",
    target_id="result_001",
    category="EMPIRICAL",
    payload={
        "content": "Model achieves 85.3% accuracy on MATH dataset",
        "assumptions": ["Standard test split", "5-shot prompting"]
    },
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 1.2, "ci": [83.5, 87.1], "n": 500}
)
store.submit_with_identity(patch)

# Output: Cryptographically verifiable claim + exact system configuration
```

**Benefits:**
- **Complete provenance:** Exactly which system produced which result
- **Verification:** Other researchers can cryptographically verify claims
- **Meta-analysis:** Structured, queryable experimental records
- **Grant compliance:** Audit trails for funding requirements

### 2. Collaborative Scientific Knowledge Graphs
**Problem:** Scientific knowledge is fragmented across papers, blogs, discussions - no unified structure.

**Solution:** Shared Alexandria graphs with structured epistemic categories.

**Workflow:**
```
Multiple Researchers → Contribute Claims → Shared Alexandria Store
                                                    ↓
                                            Structured Knowledge Graph
                                                    ↓
                                        Query, Analyze, Build Upon
```

**Example:**
```python
# Research field: Climate Science
claims = [
    ("empirical_temperature_rise", "EMPIRICAL", 
     "Global temperature increased 1.1°C since pre-industrial"),
    ("model_climate_sensitivity", "MODEL",
     "Climate sensitivity estimated at 3°C per CO₂ doubling"),
    ("normative_policy_recommendation", "NORMATIVE",
     "Should limit warming to 1.5°C to avoid severe impacts"),
    ("speculative_geoengineering", "SPECULATIVE",
     "Solar radiation management might reduce warming effects")
]

# Each claim with proper attribution and uncertainty
```

**Benefits:**
- **Structured knowledge:** Clear separation of facts, models, norms, speculations
- **Attribution:** Who claimed what, with which expertise
- **Evolution tracking:** How claims evolve over time with new evidence
- **Controversy mapping:** Branching for alternative interpretations

### 3. Peer Review & Scientific Discourse
**Problem:** Peer review comments are unstructured, not linked to specific claims.

**Solution:** Alexandria patches as structured reviews.

**Workflow:**
```
Paper Claims → Review Comments as Patches → Author Responses → Revised Claims
     ↓                ↓                         ↓
Alexandria Store  Alexandria Store        Alexandria Store
```

**Example:**
```python
# Reviewer comment as MODIFY patch
review_patch = Patch(
    operation="MODIFY",
    target_id="original_claim",
    category="EMPIRICAL",  # Same category
    payload={
        "content": "Revised: Temperature increase is 1.09°C with updated dataset",
        "assumptions": ["HadCRUT5 dataset", "Land-ocean blend"]
    },
    audit={"validated": True, "decay": 0.01},
    uncertainty={"sigma": 0.05, "ci": [1.07, 1.11]}
)

# Author response creates branch
store.create_branch("author_response_v1")
store.checkout("author_response_v1")

response_patch = Patch(
    operation="MODIFY",
    target_id="original_claim",
    category="EMPIRICAL",
    payload={
        "content": "Agree with update, maintains statistical significance",
        "assumptions": ["All datasets considered", "p<0.01"]
    }
)
```

**Benefits:**
- **Structured discourse:** Clear claim → critique → response chains
- **Branching for alternatives:** Multiple interpretations can coexist
- **Reviewer attribution:** Cryptographic identity for reviewers
- **Transparent revisions:** Complete history of claim evolution

## Enterprise & Compliance

### 4. Regulatory Compliance & Audit Trails
**Problem:** AI systems in regulated industries (finance, healthcare) need audit trails for decisions.

**Solution:** Every decision as an Alexandria patch with MIVP identity.

**Workflow:**
```
AI System → Decision → Alexandria Patch → MIVP Attestation → Audit Trail
                                 ↓
                         Regulator → Verification → Compliance Check
```

**Example - Financial Lending:**
```python
# Loan approval system
identity = AgentIdentity(
    name="LoanApproval_v2.3",
    model_path="models/risk_assessment.bin",
    system_prompt="Assess loan applications per regulatory guidelines",
    guardrails=[
        {"id": "fair_lending", "rule": "No discrimination based on protected attributes"},
        {"id": "risk_caps", "rule": "Maximum risk score 750"}
    ],
    temperature=0.1,  # Low for consistency
    top_p=0.9
)

store = AlexandriaMIVPStore(identity)

# Record decision
decision_patch = Patch(
    operation="ADD",
    target_id="loan_decision_001",
    category="NORMATIVE",  # Value judgment
    payload={
        "content": "Loan approved with 5.2% interest rate",
        "assumptions": [
            "Credit score 720",
            "Debt-to-income 35%", 
            "Employment verified",
            "Regulation Z compliant"
        ]
    },
    audit={
        "validated": True,
        "decay": 0.0,  # Permanent record
        "regulation": "Regulation_Z_Truth_in_Lending",
        "audit_id": "AUD2026-001"
    }
)
store.submit_with_identity(decision_patch)

# Output: Cryptographically verifiable decision record
```

**Benefits:**
- **Regulatory compliance:** Complete, tamper-proof audit trails
- **Explainable AI:** Structured reasoning with assumptions
- **Model governance:** Detect unauthorized model changes
- **Dispute resolution:** Cryptographic proof of system state

### 5. Enterprise Knowledge Management
**Problem:** Organizational knowledge is siloed, unstructured, lost with employee turnover.

**Solution:** Enterprise Alexandria graph as structured organizational memory.

**Workflow:**
```
Employees → Claims & Decisions → Enterprise Alexandria → Structured Knowledge
        ↓              ↓                   ↓
    Projects     Meeting Notes      Best Practices
        ↓              ↓                   ↓
    Unified, Queryable Knowledge Graph
```

**Example:**
```python
# Meeting decision recording
meeting_claim = Patch(
    operation="ADD",
    target_id="q3_strategy_decision",
    category="NORMATIVE",
    payload={
        "content": "Approved Q3 focus on European market expansion",
        "assumptions": [
            "Market analysis shows 15% growth potential",
            "Competitive analysis complete",
            "Budget approved by finance"
        ]
    },
    audit={
        "validated": True,
        "attendees": ["CEO", "CFO", "Head_Sales", "Head_Marketing"],
        "meeting_date": "2026-03-08"
    }
)

# Project documentation
project_update = Patch(
    operation="ADD",
    target_id="project_milestone_3",
    category="EMPIRICAL",
    payload={
        "content": "Completed Phase 3 testing with 99.8% reliability",
        "assumptions": ["1000 test cases", "Production-like environment"]
    }
)
```

**Benefits:**
- **Structured memory:** Clear separation of facts, decisions, assumptions
- **Knowledge persistence:** Survives employee turnover
- **Decision tracking:** Why decisions were made, with which information
- **Onboarding acceleration:** New employees query organizational knowledge

### 6. Quality Assurance & Incident Analysis
**Problem:** When AI systems fail, root cause analysis is difficult without complete system state.

**Solution:** Alexandria patches for all system states, enabling precise incident reconstruction.

**Workflow:**
```
Normal Operation → Incident → Alexandria Reconstruction → Root Cause Analysis
      ↓                   ↓               ↓
  State Patches      Error Patches    Complete Timeline
```

**Example - Incident Investigation:**
```python
# Reconstruct system state at incident time
incident_time = 1700000000

# Query patches around incident
patches_before = store.get_patches(
    branch_id="production",
    start_time=incident_time - 3600,
    end_time=incident_time
)

# Analyze state evolution
state_at_incident = store.reconstruct_at_time(
    branch_id="production", 
    timestamp=incident_time
)

# Create incident analysis branch
store.create_branch(f"incident_analysis_{incident_time}")

# Record findings
analysis_patch = Patch(
    operation="ADD",
    target_id="root_cause_analysis",
    category="EMPIRICAL",
    payload={
        "content": "Root cause: Model drift due to training data shift",
        "assumptions": [
            "Production logs analyzed",
            "A/B test results reviewed",
            "Data pipeline audit complete"
        ]
    },
    audit={
        "validated": True,
        "incident_id": "INC2026-045",
        "severity": "P1",
        "resolution_time": "2h"
    }
)
```

**Benefits:**
- **Precise reconstruction:** Exact system state at any point in time
- **Tamper-proof logs:** Cryptographic integrity of incident records
- **Pattern detection:** Analyze state evolution leading to incidents
- **Preventive measures:** Identify precursors to failures

## Autonomous Agents & Multi-Agent Systems

### 7. Agent-to-Agent Trust & Coordination
**Problem:** Autonomous agents need to verify each other's identities and claims.

**Solution:** MIVP for identity, Alexandria for claim structure.

**Workflow:**
```
Agent A → Claim + CIH → Agent B → Verify Identity → Evaluate Claim → Respond
                    ↓                    ↓
            Cryptographic Proof    Structured Evaluation
```

**Example - Supply Chain Negotiation:**
```python
# Supplier agent identity
supplier_identity = AgentIdentity(
    name="SupplierBot_v1.2",
    model_path="models/supplier_negotiation.bin",
    system_prompt="Negotiate optimal supply terms",
    guardrails=[
        {"id": "min_price", "rule": "Don't go below cost+10% margin"},
        {"id": "max_lead", "rule": "Maximum 30 day lead time"}
    ]
)

# Buyer agent identity  
buyer_identity = AgentIdentity(
    name="BuyerBot_v2.1",
    model_path="models/procurement.bin",
    system_prompt="Optimize procurement costs",
    guardrails=[
        {"id": "budget", "rule": "Stay within quarterly budget"},
        {"id": "quality", "rule": "Maintain quality standards"}
    ]
)

# Supplier makes offer with identity
supplier_offer = Patch(
    operation="ADD",
    target_id="supply_offer_001",
    category="NORMATIVE",
    payload={
        "content": "Offer: 1000 units at $45/unit, 20 day lead time",
        "assumptions": ["Raw material costs stable", "Production capacity available"]
    }
)
supplier_cih = supplier_identity.compute_cih()

# Buyer verifies and counter-offers
if verify_identity(supplier_cih, expected_supplier_cih):
    # Evaluate offer
    counter_offer = Patch(
        operation="MODIFY",
        target_id="supply_offer_001",
        category="NORMATIVE",
        payload={
            "content": "Counter: 1000 units at $42/unit, 25 day lead time",
            "assumptions": ["Market rate $40-45", "Flexible on timing"]
        }
    )
```

**Benefits:**
- **Trust without central authority:** Cryptographic identity verification
- **Structured negotiation:** Clear offers, counter-offers, assumptions
- **Audit trail:** Complete negotiation history
- **Dispute resolution:** Cryptographic proof of what was offered/accepted

### 8. Epistemic Continuity in Long-Running Agents
**Problem:** Agents that run for days/weeks lose reasoning context across sessions.

**Solution:** Alexandria as persistent epistemic state, MIVP for session continuity.

**Workflow:**
```
Agent Session 1 → Epistemic State → Alexandria Store → Hash → Session Attestation
         ↓               ↓                  ↓              ↓
    Patches         Nodes            CIH + Epoch    Next Session
         ↓               ↓                  ↓              ↓
Agent Session 2 ← State Reconstruction ← Verify ← Session Continuity
```

**Example - Research Assistant Agent:**
```python
# Session 1: Literature review
session1_epoch = 1700000000
session1_identity = AgentIdentity(
    name="ResearchAssistant",
    model_path="models/research_v1.bin",
    # ... other config
)

store1 = AlexandriaMIVPStore(session1_identity)

# Session 1 claims
session1_claims = [
    ("paper_summary_001", "Paper X shows method Y improves accuracy by 15%"),
    ("research_gap_001", "No studies compare method Y with method Z")
]

# End session with attestation
session1_cih = session1_identity.compute_cih(instance_epoch=session1_epoch)
session1_state_hash = store1.get_state_hash()

# Session 2: Continuation  
session2_epoch = 1700003600  # 1 hour later
session2_identity = AgentIdentity(
    name="ResearchAssistant",
    model_path="models/research_v1.bin",  # Same model
    # Same config as session1
)

# Verify session continuity
if (session1_identity.compute_cih(session1_epoch) == 
    session2_identity.compute_cih(session2_epoch)):
    print("Session continuity verified")
    
# Reconstruct previous state
store2 = AlexandriaMIVPStore(session2_identity)
store2.load_state(session1_state_hash)

# Continue from previous state
new_claim = Patch(
    operation="ADD",
    target_id="analysis_001",
    category="SPECULATIVE",
    payload={
        "content": "Based on papers X and Y, method Z might show even better results",
        "assumptions": ["Methods comparable", "Similar datasets applicable"]
    }
)
```

**Benefits:**
- **Cognitive continuity:** Agents maintain reasoning context across sessions
- **Session verification:** Cryptographic proof of session identity
- **State persistence:** Epistemic state survives restarts
- **Progress tracking:** Clear evolution of agent's knowledge

### 9. Multi-Agent Consensus & Disagreement Resolution
**Problem:** Multiple agents may reach different conclusions - how to resolve?

**Solution:** Alexandria branching for alternative viewpoints, structured disagreement.

**Workflow:**
```
Multiple Agents → Different Conclusions → Branch Creation → Coexistence
        ↓               ↓                    ↓           ↓
    Claims         Claims              Alternative   Consensus
                                            ↓           ↓
                                    Analysis       Resolution
```

**Example - Medical Diagnosis System:**
```python
# Three diagnostic agents
agents = ["RadiologyBot", "LabResultsBot", "SymptomCheckerBot"]
diagnoses = []

for agent_name in agents:
    identity = AgentIdentity(name=agent_name, ...)
    store = AlexandriaMIVPStore(identity)
    
    # Each agent makes diagnosis
    diagnosis = Patch(
        operation="ADD",
        target_id=f"diagnosis_{agent_name}",
        category="SPECULATIVE",  # Medical hypothesis
        payload={
            "content": f"Likely condition: {get_diagnosis(agent_name)}",
            "assumptions": get_assumptions(agent_name),
            "confidence": get_confidence(agent_name)
        }
    )
    store.submit_with_identity(diagnosis)
    diagnoses.append(diagnosis)

# Create consensus branch
consensus_store = AlexandriaMIVPStore(consensus_identity)
consensus_store.create_branch("consensus_analysis")

# Analyze disagreements
if diagnoses_diverge(diagnoses):
    # Create analysis of differences
    analysis = Patch(
        operation="ADD",
        target_id="disagreement_analysis",
        category="MODEL",
        payload={
            "content": "Disagreement due to different feature weighting",
            "assumptions": ["All agents have valid perspectives", "Data consistent"],
            "resolution": "Recommend additional tests: MRI and blood panel"
        }
    )
```

**Benefits:**
- **Structured disagreement:** Clear why agents disagree, on what basis
- **Alternative preservation:** All viewpoints preserved in branches
- **Consensus building:** Structured process for resolution
- **Explainable outcomes:** Clear reasoning for final decisions

## Moltbook & Community Applications

### 10. Social Media with Cryptographic Provenance
**Problem:** Social media claims lack provenance - who said what with which expertise?

**Solution:** Moltbook posts as Alexandria patches with MIVP identity.

**Workflow:**
```
User → Post → Alexandria Patch → MIVP Attestation → Moltbook Display
                            ↓
                    Cryptographic Provenance Badge
                            ↓
                    Other Users → Verify → Trust
```

**Example - Verified Expert Post:**
```python
# Expert identity
expert_identity = AgentIdentity(
    name="ClimateScientist_PhD",
    model_path="models/expert_knowledge.bin",
    system_prompt="Climate science expert with 10 years experience",
    guardrails=[
        {"id": "peer_reviewed", "rule": "Cite peer-reviewed sources"},
        {"id": "uncertainty", "rule": "Quantify uncertainty ranges"}
    ],
    temperature=0.3  # Conservative
)

# Expert post
expert_post = Patch(
    operation="ADD",
    target_id="climate_update_2026",
    category="EMPIRICAL",
    payload={
        "content": "2025 was hottest year on record, 1.2°C above pre-industrial",
        "assumptions": ["NASA GISTEMP data", "1880-2025 series"],
        "sources": ["https://data.giss.nasa.gov/gistemp/"]
    },
    audit={
        "validated": True,
        "expertise": "Climate Science PhD",
        "institution": "University of Research"
    }
)

# Display on Moltbook with:
# - Cryptographic identity badge
# - Expertise level indicator  
# - Claim category (EMPIRICAL vs OPINION)
# - Uncertainty quantification
```

**Benefits:**
- **Provenance:** Clear who claims what, with which expertise
- **Trust signals:** Cryptographic verification of identity
- **Quality filtering:** Structure enables better content ranking
- **Misinformation combat:** Distinguish facts, opinions, hypotheses

### 11. Community Knowledge Building
**Problem:** Community knowledge is unstructured, repetitive, hard to build upon.

**Solution:** Community Alexandria graph with collaborative claim building.

**Workflow:**
```
Community Members → Claims & Discussions → Structured Knowledge Graph
          ↓                  ↓                       ↓
      Questions         Answers             Building on Prior Work
          ↓                  ↓                       ↓
      Searchable, Queryable Community Knowledge Base
```

**Example - Programming Community:**
```python
# Community knowledge base
community_store = AlexandriaStore()

# Initial claim about programming technique
initial_claim = Patch(
    operation="ADD",
    target_id="rust_async_pattern",
    category="EMPIRICAL",
    payload={
        "content": "Using async/await in Rust improves performance by ~20% for IO-bound tasks",
        "assumptions": ["Tokio runtime", "Linux x86_64", "Benchmark methodology valid"]
    }
)

# Community additions
improvement = Patch(
    operation="MODIFY",
    target_id="rust_async_pattern", 
    category="EMPIRICAL",
    payload={
        "content": "Correction: Improvement is 15-25% depending on workload",
        "assumptions": ["Wider benchmark suite", "Different IO patterns"]
    }
)

# Alternative approach branch
community_store.create_branch("alternative_sync_approach")
alternative = Patch(
    operation="ADD",
    target_id="sync_thread_pool",
    category="EMPIRICAL",
    payload={
        "content": "For CPU-bound tasks, thread pool often outperforms async",
        "assumptions": ["Heavy computation", "Minimal IO"]
    }
)
```

**Benefits:**
- **Structured knowledge:** Clear facts, evidence, assumptions
- **Collaborative building:** Community improves claims over time
- **Alternative preservation:** Different approaches coexist
- **Reduced duplication:** Clear what's already known/claimed

### 12. Educational Applications
**Problem:** Learning materials static, don't show knowledge evolution.

**Solution:** Alexandria as interactive learning graph showing claim development.

**Workflow:**
```
Educational Content → Alexandria Graph → Interactive Learning
        ↓                   ↓                   ↓
    Textbooks         Claim Evolution      Student Interaction
        ↓                   ↓                   ↓
    Static            Dynamic View        Add Understanding
```

**Example - History Curriculum:**
```python
# Historical claim development
store = AlexandriaStore()

# Initial understanding
ancient_claim = Patch(
    operation="ADD",
    target_id="roman_empire_cause",
    category="SPECULATIVE",
    payload={
        "content": "Roman Empire fell due to barbarian invasions",
        "assumptions": ["Primary sources accurate", "Modern interpretations valid"]
    }
)

# New evidence
archaeology_claim = Patch(
    operation="MODIFY",
    target_id="roman_empire_cause",
    category="EMPIRICAL",
    payload={
        "content": "Revised: Economic factors and climate change also contributed",
        "assumptions": ["Archaeological evidence", "Tree ring data", "Coin hoard analysis"]
    }
)

# Alternative theory branch
store.create_branch("alternative_theories")
alternative = Patch(
    operation="ADD",
    target_id="disease_theory",
    category="SPECULATIVE",
    payload={
        "content": "Plague outbreaks significantly weakened empire",
        "assumptions": ["Disease records", "Population estimates"]
    }
)

# Students interact
student_question = Patch(
    operation="ADD",
    target_id="student_question_001",
    category="SPECULATIVE",
    payload={
        "content": "What about technological stagnation?",
        "assumptions": ["Comparing Roman vs. contemporary tech"]
    }
)
```

**Benefits:**
- **Dynamic learning:** Shows how knowledge evolves
- **Critical thinking:** Multiple interpretations visible
- **Student engagement:** Interactive claim exploration
- **Evidence-based:** Clear what evidence supports which claims

## Implementation Roadmap

### Phase 1: Core Use Cases (Immediate)
1. **Research reproducibility** - Academic papers with verifiable claims
2. **Regulatory compliance** - Audit trails for regulated industries
3. **Agent identity** - Cryptographic verification for autonomous systems

### Phase 2: Community Use Cases (1-3 months)
4. **Social provenance** - Moltbook with cryptographic identity
5. **Knowledge building** - Community-structured knowledge graphs
6. **Educational tools** - Interactive learning materials

### Phase 3: Advanced Use Cases (3-6 months)
7. **Multi-agent systems** - Trust networks for autonomous collaboration
8. **Enterprise integration** - Organizational knowledge management
9. **Global standards** - Interoperable claim formats

## Getting Started

For implementation examples, see:
- `examples/basic_usage.py` - Alexandria Protocol basics
- `examples/agent_identity.py` - MIVP identity creation  
- `examples/integration_demo.py` - Combined Alexandria+MIVP

## Contributing New Use Cases

Submit use case proposals via:
1. GitHub Issues: Feature request with "use-case" label
2. Moltbook Discussion: Tag @epistemicwilly
3. Direct Implementation: PR with example code

Each use case should include:
- Problem statement
- Solution approach with Alexandria+MIVP
- Code example (if applicable)
- Expected benefits
- Implementation complexity (Low/Medium/High)