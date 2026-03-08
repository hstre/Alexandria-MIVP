# OpenClaw Integration Guide

## Overview

This guide explains how to integrate Alexandria Protocol + MIVP with OpenClaw, creating a complete ecosystem for epistemically consistent, identity-verifiable autonomous agents.

### Why OpenClaw + Alexandria+MIVP?

- **OpenClaw**: Platform for autonomous agents with messaging, tools, and orchestration
- **Alexandria**: Epistemic consistency layer for structured, auditable knowledge
- **MIVP**: Cryptographic identity verification for tamper-proof agent identification

Together, they enable agents that:
1. Maintain consistent reasoning across sessions
2. Prove their identity cryptographically
3. Structure knowledge for auditability
4. Integrate with existing OpenClaw workflows

## Prerequisites

### Software Requirements
- OpenClaw installed and running
- Python 3.8+
- Git

### OpenClaw Configuration
Ensure OpenClaw is configured with:
- Messaging channels (Discord, Telegram, etc.)
- Tool access (filesystem, browser, etc.)
- Workspace directory access

### Alexandria-MIVP Installation
```bash
# Clone the repository
git clone https://github.com/hstre/Alexandria-MIVP.git
cd Alexandria-MIVP

# Install in development mode
pip install -e .
```

## Creating an OpenClaw Skill

### Skill Structure
```
openclaw-alexandria-mivp/
├── SKILL.md              # Skill definition
├── alexandria_skill.py   # Main skill implementation
├── heartbeat.py          # Periodic epistemic checks
├── ui_components.py      # Visualizations
├── config.yaml           # Configuration
└── examples/             # Usage examples
```

### SKILL.md
```markdown
# Alexandria+MIVP Skill

## Description
Integrates Alexandria Protocol (epistemic consistency) and MIVP (cryptographic identity) with OpenClaw.

## Tools
- read, write, exec, process
- message (for notifications)
- sessions_spawn (for sub-agents)

## Configuration
See config.yaml for:
- Epistemic store location
- Heartbeat intervals
- Identity verification settings

## Commands
- `/alexandria status` - Show epistemic store status
- `/alexandria claim <text>` - Create a new claim
- `/alexandria verify` - Verify agent identity
- `/alexandria audit` - Show audit trail

## Heartbeat Integration
Periodically checks for:
- Epistemic consistency violations
- Identity verification status
- New claims requiring attention
```

### Main Skill Implementation

Create `alexandria_skill.py`:

```python
"""
Alexandria+MIVP OpenClaw Skill
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from openclaw.skill import Skill, command, tool, heartbeat
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from alexandria_v2 import Patch, CATEGORIES


class AlexandriaSkill(Skill):
    """OpenClaw skill for Alexandria Protocol + MIVP integration."""
    
    def __init__(self):
        super().__init__()
        self.store = None
        self.identity = None
        self.config_path = None
        
    def setup(self, config_path: str = None):
        """Initialize the skill with configuration."""
        self.config_path = config_path or os.path.expanduser("~/.openclaw/alexandria_config.json")
        
        # Load or create configuration
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                config = json.load(f)
        else:
            config = self._default_config()
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
        
        # Initialize agent identity
        self.identity = AgentIdentity(
            name=config.get('agent_name', 'OpenClawAgent'),
            model_path=config.get('model_path', ''),
            model_bytes=config.get('model_hash', b'').encode() if config.get('model_hash') else b'',
            system_prompt=config.get('system_prompt', 'OpenClaw assistant'),
            guardrails=config.get('guardrails', []),
            temperature=config.get('temperature', 0.7),
            top_p=config.get('top_p', 0.9),
            max_tokens=config.get('max_tokens', 2000)
        )
        
        # Initialize Alexandria store
        store_path = config.get('store_path', '~/.openclaw/alexandria_store')
        self.store = AlexandriaMIVPStore(
            identity=self.identity,
            storage_path=os.path.expanduser(store_path)
        )
        
        self.logger.info(f"Alexandria+MIVP skill initialized for agent: {self.identity.name}")
        return config
    
    def _default_config(self) -> Dict:
        """Return default configuration."""
        return {
            "agent_name": "OpenClawAgent",
            "store_path": "~/.openclaw/alexandria_store",
            "heartbeat_interval_minutes": 30,
            "epistemic_categories": list(CATEGORIES),
            "enable_identity_verification": True,
            "enable_audit_trail": True,
            "moltbook_integration": False,
            "moltbook_api_key": "",
            "notification_channels": ["discord", "telegram"]
        }
    
    @command("alexandria status")
    def status_command(self, args: List[str] = None):
        """Show epistemic store status."""
        if not self.store:
            return "Skill not initialized. Run setup first."
        
        status = self.store.status_report()
        nodes = self.store.reconstruct("main")
        
        response = [
            "## Alexandria+MIVP Status",
            f"**Agent**: {self.identity.name}",
            f"**Identity CIH**: {self.identity.compute_cih().hex()[:16]}...",
            f"**Store**: {len(nodes)} claims across {len(self.store.branches)} branches",
            f"**Last updated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "### Recent Claims:"
        ]
        
        # Show recent claims
        recent_nodes = list(nodes.items())[-5:]  # Last 5 claims
        for node_id, node in recent_nodes:
            response.append(f"- **{node.category}**: {node.payload.get('content', 'No content')[:60]}...")
        
        response.append("")
        response.append("Use `/alexandria claim <text>` to add a new claim.")
        response.append("Use `/alexandria audit` to see full audit trail.")
        
        return "\n".join(response)
    
    @command("alexandria claim")
    def claim_command(self, args: List[str]):
        """Create a new epistemic claim."""
        if not self.store:
            return "Skill not initialized. Run setup first."
        
        if not args:
            return "Usage: /alexandria claim <text> [--category EMPIRICAL|NORMATIVE|MODEL|SPECULATIVE]"
        
        # Parse arguments
        text = " ".join(args)
        category = "EMPIRICAL"  # Default
        
        # Check for category flag
        if "--category" in args:
            idx = args.index("--category")
            if idx + 1 < len(args):
                category = args[idx + 1].upper()
                # Remove flag and category from text
                text = " ".join([arg for i, arg in enumerate(args) 
                               if i not in (idx, idx + 1)])
        
        if category not in CATEGORIES:
            return f"Invalid category: {category}. Must be one of: {', '.join(CATEGORIES)}"
        
        # Create and submit patch
        patch = Patch(
            patch_id=f"claim_{int(datetime.now().timestamp())}",
            parent_patch_id=self.store.get_last_patch_id("main"),
            branch_id="main",
            timestamp=int(datetime.now().timestamp()),
            operation="ADD",
            target_id=f"user_claim_{int(datetime.now().timestamp())}",
            category=category,
            payload={
                "content": text,
                "source": "user_command",
                "context": "OpenClaw chat"
            },
            audit={
                "validated": True,
                "decay": 0.01,
                "created_by": "user"
            },
            uncertainty={
                "sigma": 0.5,
                "ci": [0.8, 1.2],
                "n": 1
            }
        )
        
        commit_hash = self.store.submit_with_identity(patch)
        
        return f"✅ Claim created!\n**Category**: {category}\n**Content**: {text[:100]}...\n**Hash**: {commit_hash[:16]}..."
    
    @command("alexandria verify")
    def verify_command(self, args: List[str] = None):
        """Verify agent identity and epistemic integrity."""
        if not self.store:
            return "Skill not initialized. Run setup first."
        
        # Verify identity
        cih = self.identity.compute_cih()
        identity_verified = self.store.verify_current_identity()
        
        # Verify store integrity
        nodes = self.store.reconstruct_with_identity_verification("main")
        integrity_verified = len(nodes) > 0
        
        response = [
            "## Identity & Integrity Verification",
            f"**Agent**: {self.identity.name}",
            f"**CIH**: {cih.hex()[:32]}...",
            f"**Identity Verified**: {'✅ YES' if identity_verified else '❌ NO'}",
            f"**Store Integrity**: {'✅ YES' if integrity_verified else '❌ NO'}",
            f"**Verified Claims**: {len(nodes)}",
            ""
        ]
        
        if not identity_verified:
            response.append("⚠️ **Warning**: Identity verification failed!")
            response.append("This could indicate model/policy/runtime changes.")
        
        return "\n".join(response)
    
    @command("alexandria audit")
    def audit_command(self, args: List[str] = None):
        """Show audit trail of claims."""
        if not self.store:
            return "Skill not initialized. Run setup first."
        
        nodes = self.store.reconstruct("main")
        
        if not nodes:
            return "No claims in store yet."
        
        response = ["## Epistemic Audit Trail", ""]
        
        for node_id, node in list(nodes.items())[-10:]:  # Last 10 claims
            timestamp = datetime.fromtimestamp(node.timestamp).strftime('%Y-%m-%d %H:%M')
            content_preview = node.payload.get('content', 'No content')[:80]
            
            response.append(f"**{timestamp}** - `{node.category}`")
            response.append(f"{content_preview}...")
            response.append(f"*Hash: {node_id[:16]}...*")
            response.append("")
        
        response.append(f"Total claims: {len(nodes)}")
        
        return "\n".join(response)
    
    @command("alexandria config")
    def config_command(self, args: List[str] = None):
        """Show or update configuration."""
        if not self.config_path or not os.path.exists(self.config_path):
            return "Configuration not found. Run setup first."
        
        with open(self.config_path, 'r') as f:
            config = json.load(f)
        
        if not args:
            # Show current config
            response = ["## Current Configuration", ""]
            for key, value in config.items():
                if isinstance(value, list):
                    value_str = ", ".join(str(v) for v in value)
                else:
                    value_str = str(value)
                response.append(f"**{key}**: {value_str}")
            return "\n".join(response)
        
        # Update config
        # Simple key=value parsing
        updates = {}
        for arg in args:
            if "=" in arg:
                key, value = arg.split("=", 1)
                # Try to parse value
                try:
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        value = float(value)
                except:
                    pass
                updates[key] = value
        
        if updates:
            config.update(updates)
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Re-initialize with new config
            self.setup(self.config_path)
            
            return f"✅ Configuration updated: {', '.join(updates.keys())}"
        
        return "No valid updates provided. Use key=value format."
    
    @heartbeat(interval_minutes=30)
    def epistemic_heartbeat(self):
        """Periodic check for epistemic consistency and identity verification."""
        if not self.store:
            self.logger.warning("Store not initialized in heartbeat")
            return None
        
        try:
            # Check identity consistency
            identity_ok = self.store.verify_current_identity()
            
            # Check for contradictions
            nodes = self.store.reconstruct("main")
            contradictions = self._check_contradictions(nodes)
            
            # Check audit trail health
            audit_health = self._check_audit_health(nodes)
            
            # Prepare notification if needed
            if not identity_ok or contradictions or not audit_health:
                message = "## Epistemic Heartbeat Alert\n"
                
                if not identity_ok:
                    message += "⚠️ **Identity verification failed**\n"
                    message += "Agent identity has changed since last verification.\n"
                
                if contradictions:
                    message += f"⚠️ **Found {len(contradictions)} potential contradictions**\n"
                
                if not audit_health:
                    message += "⚠️ **Audit trail integrity issues**\n"
                
                message += "\nRun `/alexandria verify` for details."
                
                return message
            
            return None  # No alert needed
            
        except Exception as e:
            self.logger.error(f"Heartbeat error: {e}")
            return f"Epistemic heartbeat error: {e}"
    
    def _check_contradictions(self, nodes: Dict) -> List:
        """Check for contradictory claims."""
        contradictions = []
        
        # Simple contradiction detection
        # In production, implement more sophisticated logic
        claims_by_topic = {}
        
        for node_id, node in nodes.items():
            content = node.payload.get('content', '').lower()
            
            # Extract key terms (simplified)
            words = content.split()[:10]  # First 10 words
            topic = " ".join(words)
            
            if topic not in claims_by_topic:
                claims_by_topic[topic] = []
            
            claims_by_topic[topic].append({
                'id': node_id,
                'content': node.payload.get('content', ''),
                'category': node.category
            })
        
        # Check for contradictions in same topic
        for topic, claims in claims_by_topic.items():
            if len(claims) > 1:
                # Check if claims contradict each other
                # This is simplified - real implementation would use NLP
                contradictions.append({
                    'topic': topic[:50],
                    'claims': claims
                })
        
        return contradictions
    
    def _check_audit_health(self, nodes: Dict) -> bool:
        """Check audit trail health."""
        if not nodes:
            return True
        
        # Check timestamp ordering
        timestamps = [node.timestamp for node in nodes.values()]
        is_ordered = all(timestamps[i] <= timestamps[i+1] 
                        for i in range(len(timestamps)-1))
        
        # Check hash chain integrity
        hash_chain_ok = True
        for node_id, node in nodes.items():
            if node.parent_patch_id and node.parent_patch_id not in nodes:
                hash_chain_ok = False
                break
        
        return is_ordered and hash_chain_ok
    
    @tool("read_epistemic_store")
    def read_store_tool(self, branch: str = "main", limit: int = 10):
        """Tool for reading epistemic store contents."""
        if not self.store:
            return {"error": "Store not initialized"}
        
        nodes = self.store.reconstruct(branch)
        
        result = {
            "branch": branch,
            "total_claims": len(nodes),
            "claims": []
        }
        
        for node_id, node in list(nodes.items())[-limit:]:
            result["claims"].append({
                "id": node_id[:16],
                "timestamp": node.timestamp,
                "category": node.category,
                "content": node.payload.get("content", "")[:100],
                "parent": node.parent_patch_id[:8] if node.parent_patch_id else None
            })
        
        return result
    
    @tool("create_epistemic_claim")
    def create_claim_tool(self, content: str, category: str = "EMPIRICAL", 
                         validated: bool = True, **kwargs):
        """Tool for programmatically creating claims."""
        if not self.store:
            return {"error": "Store not initialized"}
        
        if category not in CATEGORIES:
            return {"error": f"Invalid category. Must be one of: {list(CATEGORIES)}"}
        
        patch = Patch(
            patch_id=f"tool_claim_{int(datetime.now().timestamp())}",
            parent_patch_id=self.store.get_last_patch_id("main"),
            branch_id="main",
            timestamp=int(datetime.now().timestamp()),
            operation="ADD",
            target_id=f"tool_claim_{int(datetime.now().timestamp())}",
            category=category,
            payload={
                "content": content,
                "source": "tool",
                "context": kwargs.get("context", "unknown")
            },
            audit={
                "validated": validated,
                "decay": kwargs.get("decay", 0.01),
                "created_by": kwargs.get("created_by", "tool")
            },
            uncertainty={
                "sigma": kwargs.get("sigma", 0.5),
                "ci": kwargs.get("ci", [0.8, 1.2]),
                "n": kwargs.get("n", 1)
            }
        )
        
        commit_hash = self.store.submit_with_identity(patch)
        
        return {
            "success": True,
            "commit_hash": commit_hash,
            "claim_id": patch.patch_id,
            "category": category
        }


# Skill registration
def register_skill():
    """Register the skill with OpenClaw."""
    return AlexandriaSkill()
```

## Heartbeat Integration

### Periodic Epistemic Checks

The skill includes a heartbeat function that runs every 30 minutes (configurable) to check:

1. **Identity Verification**: Ensure agent identity hasn't changed unexpectedly
2. **Contradiction Detection**: Look for conflicting claims
3. **Audit Trail Health**: Verify timestamp ordering and hash chain integrity

### Configuration

Add to your OpenClaw configuration:

```yaml
# ~/.openclaw/config.yaml
skills:
  alexandria_mivp:
    enabled: true
    config_path: ~/.openclaw/alexandria_config.json
    heartbeat:
      enabled: true
      interval_minutes: 30
      notifications:
        - discord
        - telegram
    store:
      path: ~/.openclaw/alexandria_store
      auto_backup: true
      backup_interval_hours: 24
```

### Heartbeat Configuration File

Create `~/.openclaw/alexandria_config.json`:

```json
{
  "agent_name": "OpenClawAssistant",
  "store_path": "~/.openclaw/alexandria_store",
  "heartbeat_interval_minutes": 30,
  "enable_identity_verification": true,
  "enable_audit_trail": true,
  "epistemic_categories": ["EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"],
  "moltbook_integration": false,
  "notification_channels": ["discord"],
  "contradiction_threshold": 0.8,
  "max_claims_per_topic": 5,
  "auto_resolve_contradictions": false
}
```

## UI Components

### Visualizing Epistemic Claims

Create `ui_components.py` for visualizing claims and identity:

```python
"""
UI components for Alexandria+MIVP visualization in OpenClaw.
"""
import json
from datetime import datetime
from typing import Dict, List

from openclaw.ui import Component, MessageComponent


class EpistemicTimeline(Component):
    """Timeline visualization of epistemic claims."""
    
    def __init__(self, nodes: Dict, title: str = "Epistemic Timeline"):
        self.nodes = nodes
        self.title = title
    
    def render(self) -> str:
        """Render timeline as markdown."""
        if not self.nodes:
            return "## No claims in timeline"
        
        lines = [f"## {self.title}", ""]
        
        # Sort by timestamp
        sorted_nodes = sorted(
            self.nodes.items(),
            key=lambda x: x[1].timestamp
        )
        
        for node_id, node in sorted_nodes[-20:]:  # Last 20 claims
            timestamp = datetime.fromtimestamp(node.timestamp).strftime('%Y-%m-%d %H:%M')
            category_color = {
                "EMPIRICAL": "🟦",
                "NORMATIVE": "🟧", 
                "MODEL": "🟪",
                "SPECULATIVE": "🟨"
            }.get(node.category, "⬜")
            
            content_preview = node.payload.get('content', 'No content')[:60]
            
            lines.append(f"{category_color} **{timestamp}** - `{node.category}`")
            lines.append(f"   {content_preview}...")
            lines.append(f"   *Hash: {node_id[:12]}...*")
            lines.append("")
        
        return "\n".join(lines)


class IdentityBadge(Component):
    """Badge showing agent identity verification status."""
    
    def __init__(self, identity, verified: bool = True):
        self.identity = identity
        self.verified = verified
    
    def render(self) -> str:
        """Render identity badge."""
        cih = self.identity.compute_cih().hex()
        
        status_emoji = "✅" if self.verified else "⚠️"
        status_text = "VERIFIED" if self.verified else "UNVERIFIED"
        
        lines = [
            f"## {status_emoji} Agent Identity: {self.identity.name}",
            f"**Status**: {status_text}",
            f"**CIH**: `{cih[:32]}...`",
            f"**Model Hash**: `{self.identity.compute_mh().hex()[:16]}...`",
            f"**Policy Hash**: `{self.identity.compute_ph().hex()[:16]}...`",
            f"**Runtime Hash**: `{self.identity.compute_rh().hex()[:16]}...`"
        ]
        
        if not self.verified:
            lines.append("\n⚠️ **Warning**: Identity verification failed!")
            lines.append("This could indicate:")
            lines.append("- Model weights changed")
            lines.append("- System prompt modified")
            lines.append("- Runtime parameters altered")
        
        return "\n".join(lines)


class ClaimCard(MessageComponent):
    """Interactive card for individual claims."""
    
    def __init__(self, claim_id: str, node, store):
        self.claim_id = claim_id
        self.node = node
        self.store = store
    
    def get_message(self) -> Dict:
        """Return message with claim card."""
        timestamp = datetime.fromtimestamp(self.node.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        # Create buttons for interaction
        buttons = [
            {
                "label": "View Details",
                "action": f"/alexandria view {self.claim_id[:8]}"
            },
            {
                "label": "Verify Identity",
                "action": f"/alexandria verify_claim {self.claim_id[:8]}"
            },
            {
                "label": "Create Response",
                "action": f"/alexandria respond {self.claim_id[:8]}"
            }
        ]
        
        return {
            "text": f"## Claim: {self.claim_id[:16]}...\n"
                   f"**Category**: {self.node.category}\n"
                   f"**Time**: {timestamp}\n"
                   f"**Content**: {self.node.payload.get('content', 'No content')[:200]}...",
            "buttons": buttons,
            "metadata": {
                "claim_id": self.claim_id,
                "category": self.node.category,
                "timestamp": self.node.timestamp
            }
        }
```

## Installation as OpenClaw Skill

### Method 1: Manual Installation

1. **Create skill directory** in OpenClaw workspace:
   ```bash
   mkdir -p ~/.openclaw/workspace/skills/alexandria-mivp
   ```

2. **Copy skill files** to the directory:
   ```bash
   cp alexandria_skill.py heartbeat.py ui_components.py config.yaml \
      ~/.openclaw/workspace/skills/alexandria-mivp/
   ```

3. **Install Alexandria-MIVP package**:
   ```bash
   pip install Alexandria-MIVP/
   ```

4. **Update OpenClaw config** to load the skill:
   ```yaml
   # ~/.openclaw/config.yaml
   skills:
     enabled:
       - alexandria-mivp
   ```

### Method 2: Using Skill Creator

If you have the `skill-creator` skill installed:

```bash
/openclaw skill create --name alexandria-mivp \
  --description "Alexandria Protocol + MIVP integration" \
  --category "epistemic" \
  --files alexandria_skill.py heartbeat.py ui_components.py config.yaml
```

### Method 3: Git Submodule (Advanced)

Add as a submodule to your OpenClaw workspace:

```bash
cd ~/.openclaw/workspace
git submodule add https://github.com/hstre/Alexandria-MIVP.git skills/alexandria-mivp
```

## Configuration Examples

### Basic Configuration

```yaml
# config.yaml
alexandria_mivp:
  agent:
    name: "ResearchAssistant"
    model_path: "models/llama3_70b.bin"
    system_prompt: "Research assistant specializing in scientific literature review."
    guardrails:
      - id: "cite_sources"
        rule: "Always cite peer-reviewed sources"
      - id: "quantify_uncertainty"
        rule: "Quantify uncertainty in empirical claims"
  
  store:
    path: "~/.openclaw/epistemic_store"
    branches:
      - "main"
      - "research"
      - "personal"
    
    backup:
      enabled: true
      interval_hours: 24
      location: "~/backups/alexandria"
  
  heartbeat:
    enabled: true
    interval_minutes: 30
    checks:
      - identity_verification
      - contradiction_detection
      - audit_trail_health
      - backup_verification
    
    notifications:
      channels: ["discord", "telegram"]
      priority: "medium"
      include_details: true
  
  ui:
    enabled: true
    components:
      - timeline
      - identity_badge
      - claim_cards
    theme: "dark"
    compact_mode: false
  
  integrations:
    moltbook:
      enabled: false
      api_key: ""
      post_claims: false
      verify_posts: true
    
    github:
      enabled: true
      repository: "hstre/Alexandria-MIVP"
      sync_interval_hours: 6
```

### Research Assistant Configuration

```yaml
alexandria_mivp:
  agent:
    name: "ScienceReviewer"
    system_prompt: |
      You are a scientific review assistant. Your role is to:
      1. Evaluate research claims based on evidence
      2. Structure knowledge with proper categorization
      3. Maintain epistemic consistency across sessions
      4. Provide verifiable claims with uncertainty quantification
  
  store:
    path: "~/.openclaw/science_review_store"
    auto_categorize: true
    default_category: "EMPIRICAL"
    
    validation_rules:
      empirical_claims_require_sources: true
      normative_claims_require_justification: true
      speculative_claims_require_disclaimer: true
  
  heartbeat:
    checks:
      - source_attribution_consistency
      - statistical_significance_validation
      - replication_status_tracking
      - literature_update_checking
    
    notifications:
      priority_claims:
        - p_value < 0.05
        - effect_size > 0.5
        - replication_count >= 3
```

### Multi-Agent Configuration

```yaml
alexandria_mivp:
  multi_agent:
    enabled: true
    agents:
      - name: "FactChecker"
        role: "Verify empirical claims"
        store_branch: "fact_checking"
      
      - name: "EthicsReviewer"
        role: "Evaluate normative claims" 
        store_branch: "ethics"
      
      - name: "ModelValidator"
        role: "Validate model assumptions"
        store_branch: "models"
    
    collaboration:
      shared_store: "~/.openclaw/collaborative_store"
      claim_resolution: "branching"  # or "consensus", "voting"
      conflict_notification: true
      
    identity_verification:
      cross_verify: true
      require_signed_claims: true
      trust_threshold: 0.8
```

## Testing the Integration

### Basic Tests

```python
# test_alexandria_skill.py
import pytest
from alexandria_skill import AlexandriaSkill
from alexandria_mivp import AlexandriaMIVPStore


def test_skill_initialization():
    """Test skill initialization."""
    skill = AlexandriaSkill()
    config = skill.setup()
    
    assert skill.store is not None
    assert skill.identity is not None
    assert "agent_name" in config


def test_claim_creation():
    """Test creating claims through skill."""
    skill = AlexandriaSkill()
    skill.setup()
    
    # Test command
    response = skill.claim_command(["Test claim", "--category", "EMPIRICAL"])
    assert "Claim created" in response
    
    # Verify claim was added
    status = skill.status_command()
    assert "Test claim" in status


def test_identity_verification():
    """Test identity verification."""
    skill = AlexandriaSkill()
    skill.setup()
    
    response = skill.verify_command()
    assert "Identity Verified" in response


def test_heartbeat():
    """Test heartbeat function."""
    skill = AlexandriaSkill()
    skill.setup()
    
    # Add some claims
    skill.claim_command(["Claim 1"])
    skill.claim_command(["Claim 2"])
    
    # Run heartbeat
    alert = skill.epistemic_heartbeat()
    
    # Should return None if everything is OK
    assert alert is None or "Alert" in alert


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### Integration Tests with OpenClaw

```python
# test_openclaw_integration.py
import asyncio
from openclaw.testing import OpenClawTestCase
from alexandria_skill import AlexandriaSkill


class TestAlexandriaOpenClaw(OpenClawTestCase):
    """Integration tests with OpenClaw."""
    
    async def asyncSetUp(self):
        await super().asyncSetUp()
        
        # Load the skill
        self.skill = await self.load_skill("alexandria-mivp")
        
        # Initialize
        await self.skill.setup()
    
    async def test_command_processing(self):
        """Test command processing through OpenClaw."""
        # Simulate command
        response = await self.process_command("/alexandria status")
        
        self.assertIn("Alexandria+MIVP Status", response)
        self.assertIn("Agent", response)
    
    async def test_heartbeat_integration(self):
        """Test heartbeat integration with OpenClaw."""
        # Trigger heartbeat
        await self.trigger_heartbeat("alexandria")
        
        # Check if heartbeat ran
        heartbeat_results = await self.get_heartbeat_results("alexandria")
        
        self.assertIsNotNone(heartbeat_results)
        
        # Should not have alerts for empty store
        self.assertNotIn("Alert", heartbeat_results or "")
    
    async def test_tool_integration(self):
        """Test tool integration."""
        # Use the read store tool
        store_contents = await self.use_tool(
            "read_epistemic_store",
            branch="main",
            limit=5
        )
        
        self.assertIn("claims", store_contents)
        self.assertIsInstance(store_contents["claims"], list)


if __name__ == "__main__":
    asyncio.run(OpenClawTestCase.run_tests())
```

## Advanced Usage

### Multi-Agent Epistemic Systems

Create multiple agents with specialized roles:

```python
# multi_agent_setup.py
from alexandria_skill import AlexandriaSkill
from alexandria_mivp import AlexandriaMIVPStore, AgentIdentity


class MultiAgentSystem:
    """System with multiple epistemically coordinated agents."""
    
    def __init__(self):
        self.agents = {}
        self.shared_store = None
        
    def setup(self):
        # Shared store for collaboration
        self.shared_store = AlexandriaMIVPStore(
            identity=AgentIdentity(name="Coordinator"),
            storage_path="~/.openclaw/shared_store"
        )
        
        # Create specialized agents
        self.agents["fact_checker"] = self._create_agent(
            name="FactChecker",
            role="Verify empirical claims",
            system_prompt="Specialize in fact verification and source validation.",
            branch="fact_checking"
        )
        
        self.agents["ethics_reviewer"] = self._create_agent(
            name="EthicsReviewer",
            role="Evaluate normative claims",
            system_prompt="Specialize in ethical analysis and normative reasoning.",
            branch="ethics"
        )
        
        self.agents["model_validator"] = self._create_agent(
            name="ModelValidator",
            role="Validate model assumptions",
            system_prompt="Specialize in model validation and assumption testing.",
            branch="models"
        )
    
    def _create_agent(self, name, role, system_prompt, branch):
        """Create a specialized agent."""
        identity = AgentIdentity(
            name=name,
            system_prompt=system_prompt,
            guardrails=[
                {"id": "specialization", "rule": f"Focus on {role.lower()}"},
                {"id": "collaboration", "rule": "Coordinate with other agents"}
            ]
        )
        
        store = AlexandriaMIVPStore(
            identity=identity,
            storage_path=f"~/.openclaw/{name.lower()}_store"
        )
        
        # Link to shared store
        store.link_shared_store(self.shared_store, branch)
        
        return {
            "identity": identity,
            "store": store,
            "role": role,
            "branch": branch
        }
    
    def coordinate_claims(self, claim_text):
        """Coordinate a claim across specialized agents."""
        results = {}
        
        for agent_name, agent in self.agents.items():
            # Each agent evaluates from their perspective
            patch = self._create_evaluation_patch(
                agent=agent,
                claim_text=claim_text
            )
            
            commit_hash = agent["store"].submit_with_identity(patch)
            results[agent_name] = {
                "evaluation": patch.payload.get("evaluation"),
                "confidence": patch.uncertainty.get("sigma"),
                "commit_hash": commit_hash
            }
        
        # Create consensus in shared store
        consensus = self._create_consensus_patch(claim_text, results)
        shared_hash = self.shared_store.submit_with_identity(consensus)
        
        return {
            "specialized_evaluations": results,
            "consensus_hash": shared_hash,
            "consensus": consensus.payload
        }
```

### Moltbook Integration

```python
# moltbook_integration.py
import json
import urllib.request
from alexandria_skill import AlexandriaSkill


class MoltbookIntegration:
    """Integrate with Moltbook social platform."""
    
    def __init__(self, skill: AlexandriaSkill, api_key: str):
        self.skill = skill
        self.api_key = api_key
        self.base_url = "https://www.moltbook.com/api/v1"
    
    def post_claim(self, claim_id: str, submolt: str = "general"):
        """Post a claim to Moltbook."""
        # Get claim from store
        nodes = self.skill.store.reconstruct("main")
        
        if claim_id not in nodes:
            return {"error": f"Claim {claim_id} not found"}
        
        node = nodes[claim_id]
        
        # Prepare Moltbook post
        post_data = {
            "submolt_name": submolt,
            "title": f"Epistemic Claim: {node.category}",
            "content": self._format_claim_for_moltbook(node)
        }
        
        # Post to Moltbook
        response = self._make_api_request("/posts", post_data, method="POST")
        
        if "post_id" in response:
            # Link Moltbook post to claim
            self._link_moltbook_post(claim_id, response["post_id"])
            
            return {
                "success": True,
                "post_id": response["post_id"],
                "url": f"https://www.moltbook.com/p/{response['post_id']}",
                "claim_id": claim_id
            }
        
        return {"error": "Failed to post to Moltbook", "details": response}
    
    def _format_claim_for_moltbook(self, node):
        """Format claim for Moltbook presentation."""
        lines = [
            f"## 🔬 Epistemic Claim: {node.category}",
            "",
            f"**Content**: {node.payload.get('content', '')}",
            "",
            "### 📊 Metadata",
            f"- **Confidence**: {node.uncertainty.get('sigma', 'unknown')} σ",
            f"- **Validation**: {'✅ Validated' if node.audit.get('validated') else '⚠️ Unvalidated'}",
            f"- **Decay Rate**: {node.audit.get('decay', 0)} per day",
            "",
            "### 🔐 Cryptographic Identity",
            f"- **Agent**: {self.skill.identity.name}",
            f"- **CIH**: `{self.skill.identity.compute_cih().hex()[:32]}...`",
            "",
            "### 💬 Discussion",
            "What's your take on this claim?",
            "",
            "---",
            "*Posted via Alexandria+MIVP integration*"
        ]
        
        return "\n".join(lines)
```

## Troubleshooting

### Common Issues

#### Issue: "Store not initialized"
**Solution**: Ensure the skill's `setup()` method is called before using commands.

#### Issue: Identity verification fails
**Possible causes**:
1. Model/policy/runtime configuration changed
2. Hash computation error
3. Corrupted identity data

**Solutions**:
1. Check configuration consistency
2. Verify MIVP implementation matches spec
3. Re-initialize identity with `skill.setup()`

#### Issue: Heartbeat alerts too frequent
**Adjust configuration**:
```yaml
heartbeat:
  checks:
    identity_verification:
      tolerance: 0.1  # Allow 10% change
    contradiction_detection:
      threshold: 0.8  # Higher threshold = fewer alerts
```

#### Issue: Performance problems with large stores
**Optimizations**:
1. Enable indexing in store configuration
2. Use pagination for large queries
3. Implement caching for frequent reads

### Debugging Commands

```bash
# Check skill status
/alexandria status

# Verify identity
/alexandria verify

# Check configuration
/alexandria config

# View audit trail
/alexandria audit

# Test heartbeat manually
/openclaw heartbeat trigger alexandria
```

### Logging

Enable debug logging in OpenClaw configuration:

```yaml
logging:
  level: DEBUG
  skills:
    alexandria-mivp: DEBUG
```

Check logs:
```bash
tail -f ~/.openclaw/logs/skill_alexandria.log
```

## Deployment

### Production Considerations

1. **Backup Strategy**:
   ```yaml
   backup:
     enabled: true
     interval_hours: 6
     retention_days: 30
     locations:
       - local: ~/backups/alexandria
       - remote: s3://your-bucket/alexandria-backups
   ```

2. **Security**:
   - Store API keys in OpenClaw secure storage
   - Use environment variables for sensitive data
   - Enable encryption for store files

3. **Monitoring**:
   - Monitor heartbeat alerts
   - Track claim volume and growth
   - Set up alerts for verification failures

4. **Scalability**:
   - Use database backend for large stores
   - Implement sharding for multi-agent systems
   - Use caching for frequent queries

### Updating the Integration

1. **Update Alexandria-MIVP package**:
   ```bash
   pip install --upgrade Alexandria-MIVP
   ```

2. **Reload skill**:
   ```bash
   /openclaw skill reload alexandria-mivp
   ```

3. **Migrate store if needed**:
   ```python
   from alexandria_mivp import migrate_store
   migrate_store("old_store_path", "new_store_path")
   ```

## Conclusion

This integration brings together:
- **OpenClaw's** agent orchestration and tool access
- **Alexandria Protocol's** epistemic consistency
- **MIVP's** cryptographic identity verification

The result is agents that:
1. Maintain coherent reasoning over time
2. Can prove their identity cryptographically
3. Create structured, auditable knowledge
4. Integrate seamlessly with existing workflows

### Next Steps

1. **Start simple**: Implement basic skill with status and claim commands
2. **Add heartbeat**: Enable periodic consistency checks
3. **Integrate with workflows**: Connect to your existing OpenClaw tasks
4. **Expand**: Add multi-agent coordination, Moltbook integration, etc.

### Getting Help

- **GitHub Issues**: https://github.com/hstre/Alexandria-MIVP/issues
- **OpenClaw Community**: https://discord.com/invite/clawd
- **Moltbook**: @epistemicwilly

---

**Happy building epistemically consistent, identity-verifiable agents!** 🧠🔐