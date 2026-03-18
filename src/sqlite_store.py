"""
SQLite persistence layer for Alexandria Protocol + MIVP integration.
Provides persistent storage with atomic transactions and query optimization.
"""
import sqlite3
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import asdict
import hashlib

from alexandria_v2 import (
    AlexandriaStore, Patch, Node, Uncertainty, AuditError,
    audit_patch, sha256_json, clamp01, CATEGORIES, OPS
)
from alexandria_mivp import AgentIdentity, verify_cih_internal_consistency


class AlexandriaSQLiteStore(AlexandriaStore):
    """
    Alexandria Store with SQLite persistence.
    
    Features:
    - Persistent storage across sessions
    - Atomic transactions for patch submission
    - Query optimization for large stores
    - Efficient reconstruction via SQL joins
    - Migration tools from memory to SQLite
    """
    
    def __init__(self, db_path: str = "alexandria_store.db"):
        """
        Initialize SQLite store.
        
        Args:
            db_path: Path to SQLite database file (created if doesn't exist)
        """
        # Don't call parent __init__ because we replace all storage
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Enable dict-like row access
        
        # Set pragmas for better performance and durability
        self.conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
        self.conn.execute("PRAGMA foreign_keys = ON")   # Foreign key constraints
        self.conn.execute("PRAGMA busy_timeout = 5000") # Timeout for locked DB
        
        self._init_tables()
        
        # Memory caches for performance
        self.current_branch: str = "main"
        self._branches_cache: Dict[str, List[str]] = {}  # branch_id -> list of patch_ids
        self._last_commit_hash: Dict[str, Optional[str]] = {}
        self._last_timestamp: Dict[str, int] = {}
        self._load_branch_metadata()
        
        # Current in-memory nodes for checked-out branch
        self.nodes: Dict[str, Node] = {}
        
    def _init_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Patches table (immutable)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patches (
                patch_id TEXT PRIMARY KEY,
                parent_patch_id TEXT,
                branch_id TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                operation TEXT NOT NULL,
                target_id TEXT NOT NULL,
                category TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                audit_json TEXT NOT NULL,
                uncertainty_json TEXT,
                previous_commit_hash TEXT,
                commit_hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (parent_patch_id) REFERENCES patches(patch_id),
                CHECK (operation IN ('ADD', 'MODIFY', 'DEPRECATE')),
                CHECK (category IN ('EMPIRICAL', 'NORMATIVE', 'MODEL', 'SPECULATIVE'))
            )
        """)
        
        # Indexes for efficient queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patches_branch ON patches(branch_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patches_parent ON patches(parent_patch_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patches_timestamp ON patches(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_patches_target ON patches(target_id)")
        
        # Nodes table (derived state, can be rebuilt from patches)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                uncertainty_json TEXT,
                stability REAL DEFAULT 0.0,
                deprecated INTEGER DEFAULT 0,
                lineage_json TEXT NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                CHECK (category IN ('EMPIRICAL', 'NORMATIVE', 'MODEL', 'SPECULATIVE')),
                CHECK (deprecated IN (0, 1))
            )
        """)
        
        # Branch metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS branches (
                branch_id TEXT PRIMARY KEY,
                last_commit_hash TEXT,
                last_timestamp INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (last_commit_hash) REFERENCES patches(commit_hash)
            )
        """)
        
        # Identity hashes for MIVP integration (optional)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS identity_hashes (
                patch_id TEXT PRIMARY KEY,
                agent_name TEXT,
                mh_hex TEXT,
                ph_hex TEXT,
                rh_hex TEXT,
                cih_hex TEXT,
                instance_epoch INTEGER,
                timestamp INTEGER,
                signer_id_hex TEXT,
                signature_hex TEXT,
                rh_extended_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (patch_id) REFERENCES patches(patch_id)
            )
        """)

        # Migrate: add rh_extended_json column if missing (idempotent)
        try:
            cursor.execute("ALTER TABLE identity_hashes ADD COLUMN rh_extended_json TEXT")
        except Exception:
            pass  # Column already exists

        # Indexes for efficient identity queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_identity_agent ON identity_hashes(agent_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_identity_cih ON identity_hashes(cih_hex)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_identity_mh ON identity_hashes(mh_hex)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_identity_epoch ON identity_hashes(instance_epoch)")
        
        # Insert default 'main' branch if it doesn't exist
        cursor.execute("""
            INSERT OR IGNORE INTO branches (branch_id, last_commit_hash, last_timestamp)
            VALUES ('main', NULL, 0)
        """)
        
        self.conn.commit()
        
    def _load_branch_metadata(self):
        """Load branch metadata from database into memory cache."""
        cursor = self.conn.cursor()
        
        # Load all branches
        cursor.execute("SELECT branch_id, last_commit_hash, last_timestamp FROM branches")
        for row in cursor.fetchall():
            branch_id = row["branch_id"]
            self._last_commit_hash[branch_id] = row["last_commit_hash"]
            self._last_timestamp[branch_id] = row["last_timestamp"] or 0
            
            # Load patch sequence for this branch
            self._branches_cache[branch_id] = self._load_patch_sequence(branch_id)
    
    def _load_patch_sequence(self, branch_id: str) -> List[str]:
        """Load patch IDs in order for a branch."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT patch_id FROM patches 
            WHERE branch_id = ? 
            ORDER BY timestamp ASC
        """, (branch_id,))
        return [row["patch_id"] for row in cursor.fetchall()]
    
    # ---------- Serialization Helpers ----------
    
    @staticmethod
    def _serialize_patch(patch: Patch) -> Dict[str, Any]:
        """Serialize patch for database storage."""
        return {
            "patch_id": patch.patch_id,
            "parent_patch_id": patch.parent_patch_id,
            "branch_id": patch.branch_id,
            "timestamp": patch.timestamp,
            "operation": patch.operation,
            "target_id": patch.target_id,
            "category": patch.category,
            "payload_json": json.dumps(patch.payload, separators=(",", ":"), ensure_ascii=False),
            "audit_json": json.dumps(patch.audit, separators=(",", ":"), ensure_ascii=False),
            "uncertainty_json": json.dumps(patch.uncertainty, separators=(",", ":"), ensure_ascii=False) 
                if patch.uncertainty else None,
            "previous_commit_hash": patch.chain["previous_commit_hash"] if patch.chain else None,
            "commit_hash": patch.chain["commit_hash"] if patch.chain else None,
        }
    
    @staticmethod
    def _deserialize_patch(row: sqlite3.Row) -> Patch:
        """Deserialize patch from database row."""
        return Patch(
            patch_id=row["patch_id"],
            parent_patch_id=row["parent_patch_id"],
            branch_id=row["branch_id"],
            timestamp=row["timestamp"],
            operation=row["operation"],
            target_id=row["target_id"],
            category=row["category"],
            payload=json.loads(row["payload_json"]),
            audit=json.loads(row["audit_json"]),
            uncertainty=json.loads(row["uncertainty_json"]) if row["uncertainty_json"] else None,
            chain={
                "previous_commit_hash": row["previous_commit_hash"],
                "commit_hash": row["commit_hash"],
            } if row["commit_hash"] else None,
        )
    
    @staticmethod
    def _serialize_node(node: Node) -> Dict[str, Any]:
        """Serialize node for database storage."""
        return {
            "node_id": node.node_id,
            "category": node.category,
            "content": node.content,
            "assumptions_json": json.dumps(node.assumptions, separators=(",", ":"), ensure_ascii=False),
            "uncertainty_json": json.dumps({
                "sigma": node.uncertainty.sigma,
                "ci": node.uncertainty.ci,
                "n": node.uncertainty.n,
            }, separators=(",", ":"), ensure_ascii=False) if node.uncertainty else None,
            "stability": node.stability,
            "deprecated": 1 if node.deprecated else 0,
            "lineage_json": json.dumps(node.lineage, separators=(",", ":"), ensure_ascii=False),
        }
    
    @staticmethod
    def _deserialize_node(row: sqlite3.Row) -> Node:
        """Deserialize node from database row."""
        uncertainty_data = json.loads(row["uncertainty_json"]) if row["uncertainty_json"] else None
        uncertainty = None
        if uncertainty_data:
            uncertainty = Uncertainty(
                sigma=uncertainty_data["sigma"],
                ci=tuple(uncertainty_data["ci"]) if uncertainty_data.get("ci") else None,
                n=uncertainty_data.get("n"),
            )
        
        return Node(
            node_id=row["node_id"],
            category=row["category"],
            content=row["content"],
            assumptions=json.loads(row["assumptions_json"]),
            uncertainty=uncertainty,
            stability=row["stability"],
            deprecated=bool(row["deprecated"]),
            lineage=json.loads(row["lineage_json"]),
        )
    
    # ---------- Core Methods (Override AlexandriaStore) ----------
    
    def checkout(self, branch_id: str) -> None:
        """Check out a branch and load its nodes into memory."""
        if branch_id not in self._branches_cache:
            raise KeyError(f"Unknown branch: {branch_id}")
        
        self.current_branch = branch_id
        self.nodes = self.reconstruct(branch_id)
    
    def create_branch(self, new_branch_id: str, from_patch_id: Optional[str] = None) -> None:
        """Create a new branch from current branch or specific patch."""
        if new_branch_id in self._branches_cache:
            raise ValueError("Branch already exists")
        
        current_branch_id = self.current_branch
        current_patches = self._branches_cache[current_branch_id]
        
        cursor = self.conn.cursor()
        
        if from_patch_id is None:
            # Branch from HEAD - copy all patches
            patches_to_copy = current_patches
            if patches_to_copy:
                last_patch_id = patches_to_copy[-1]
                cursor.execute(
                    "SELECT commit_hash, timestamp FROM patches WHERE patch_id = ?",
                    (last_patch_id,)
                )
                last_row = cursor.fetchone()
                last_commit_hash = last_row["commit_hash"] if last_row else None
                last_timestamp = last_row["timestamp"] if last_row else 0
            else:
                last_commit_hash = None
                last_timestamp = 0
        else:
            # Branch from specific patch (inclusive)
            if from_patch_id not in current_patches:
                raise KeyError("from_patch_id not found in current branch")
            
            idx = current_patches.index(from_patch_id)
            patches_to_copy = current_patches[:idx + 1]
            
            cursor.execute(
                "SELECT commit_hash, timestamp FROM patches WHERE patch_id = ?",
                (from_patch_id,)
            )
            last_row = cursor.fetchone()
            last_commit_hash = last_row["commit_hash"]
            last_timestamp = last_row["timestamp"]
        
        # Insert new branch metadata
        cursor.execute("""
            INSERT INTO branches (branch_id, last_commit_hash, last_timestamp)
            VALUES (?, ?, ?)
        """, (new_branch_id, last_commit_hash, last_timestamp))
        
        # Update caches
        self._branches_cache[new_branch_id] = patches_to_copy.copy()
        self._last_commit_hash[new_branch_id] = last_commit_hash
        self._last_timestamp[new_branch_id] = last_timestamp
        
        self.conn.commit()
    
    def submit(self, patch: Patch) -> str:
        """Submit patch with atomic transaction."""
        # Audit first
        audit_patch(patch)
        
        b = patch.branch_id
        if b not in self._branches_cache:
            raise KeyError(f"Branch does not exist: {b}")
        
        # Temporal monotonicity
        if patch.timestamp <= self._last_timestamp[b]:
            raise AuditError(
                f"Non-monotonic timestamp for branch {b}: "
                f"{patch.timestamp} <= {self._last_timestamp[b]}"
            )
        
        # Parent linkage check
        patch_sequence = self._branches_cache[b]
        expected_parent = patch_sequence[-1] if patch_sequence else None
        if patch.parent_patch_id != expected_parent:
            raise AuditError(
                f"parent_patch_id mismatch: got {patch.parent_patch_id}, "
                f"expected {expected_parent}"
            )
        
        # Chain anchor
        prev = self._last_commit_hash[b]
        patch_dict = asdict(patch)
        patch_dict["chain"] = {"previous_commit_hash": prev, "commit_hash": None}
        commit_hash = sha256_json(patch_dict)  # includes previous hash
        patch_dict["chain"]["commit_hash"] = commit_hash
        
        anchored = Patch(**{k: patch_dict[k] for k in patch_dict if k in Patch.__annotations__})
        
        # Begin atomic transaction
        cursor = self.conn.cursor()
        try:
            # Insert patch
            patch_data = self._serialize_patch(anchored)
            cursor.execute("""
                INSERT INTO patches (
                    patch_id, parent_patch_id, branch_id, timestamp,
                    operation, target_id, category, payload_json,
                    audit_json, uncertainty_json, previous_commit_hash, commit_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                patch_data["patch_id"],
                patch_data["parent_patch_id"],
                patch_data["branch_id"],
                patch_data["timestamp"],
                patch_data["operation"],
                patch_data["target_id"],
                patch_data["category"],
                patch_data["payload_json"],
                patch_data["audit_json"],
                patch_data["uncertainty_json"],
                patch_data["previous_commit_hash"],
                patch_data["commit_hash"],
            ))
            
            # Update branch metadata
            cursor.execute("""
                UPDATE branches 
                SET last_commit_hash = ?, last_timestamp = ?
                WHERE branch_id = ?
            """, (commit_hash, patch.timestamp, b))
            
            # Apply patch to nodes if this branch is checked out
            if self.current_branch == b:
                self._apply_patch_to_database(anchored, cursor)
            
            # Update MIVP identity if present
            if "mivp_identity" in anchored.audit:
                identity = anchored.audit["mivp_identity"]
                rh_extended = identity.get("rh_extended")
                rh_extended_json = (
                    json.dumps(rh_extended, separators=(",", ":"), ensure_ascii=False)
                    if rh_extended else None
                )
                cursor.execute("""
                    INSERT OR REPLACE INTO identity_hashes (
                        patch_id, agent_name, mh_hex, ph_hex, rh_hex,
                        cih_hex, instance_epoch, timestamp, signer_id_hex,
                        signature_hex, rh_extended_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    anchored.patch_id,
                    identity.get("agent_name"),
                    identity.get("mh"),
                    identity.get("ph"),
                    identity.get("rh"),
                    identity.get("cih"),
                    identity.get("instance_epoch"),
                    identity.get("timestamp"),
                    identity.get("signer_id"),
                    identity.get("signature"),
                    rh_extended_json,
                ))
            
            self.conn.commit()
            
            # Update memory caches
            self._branches_cache[b].append(anchored.patch_id)
            self._last_commit_hash[b] = commit_hash
            self._last_timestamp[b] = patch.timestamp
            
            # Update in-memory nodes if checked out
            if self.current_branch == b:
                self.apply_patch_in_place(anchored)
            
            return commit_hash
            
        except Exception as e:
            self.conn.rollback()
            raise AuditError(f"Failed to submit patch to SQLite store: {e}")
    
    def _apply_patch_to_database(self, patch: Patch, cursor: sqlite3.Cursor):
        """Apply patch to nodes table in database."""
        op = patch.operation
        tid = patch.target_id
        
        if op == "ADD":
            # Check if active node already exists
            cursor.execute(
                "SELECT deprecated FROM nodes WHERE node_id = ?",
                (tid,)
            )
            row = cursor.fetchone()
            if row and not row["deprecated"]:
                raise AuditError(f"ADD to existing active node: {tid}")
            
            # Create new node
            node = self._node_from_patch(patch, existing=None)
            node_data = self._serialize_node(node)
            
            cursor.execute("""
                INSERT OR REPLACE INTO nodes (
                    node_id, category, content, assumptions_json,
                    uncertainty_json, stability, deprecated, lineage_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node_data["node_id"],
                node_data["category"],
                node_data["content"],
                node_data["assumptions_json"],
                node_data["uncertainty_json"],
                node_data["stability"],
                node_data["deprecated"],
                node_data["lineage_json"],
            ))
            
        elif op == "MODIFY":
            # Check if node exists
            cursor.execute(
                "SELECT * FROM nodes WHERE node_id = ?",
                (tid,)
            )
            row = cursor.fetchone()
            if not row:
                raise AuditError(f"MODIFY unknown node: {tid}")
            
            existing_node = self._deserialize_node(row)
            node = self._node_from_patch(patch, existing=existing_node)
            node_data = self._serialize_node(node)
            
            cursor.execute("""
                UPDATE nodes SET
                    category = ?,
                    content = ?,
                    assumptions_json = ?,
                    uncertainty_json = ?,
                    stability = ?,
                    deprecated = ?,
                    lineage_json = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE node_id = ?
            """, (
                node_data["category"],
                node_data["content"],
                node_data["assumptions_json"],
                node_data["uncertainty_json"],
                node_data["stability"],
                node_data["deprecated"],
                node_data["lineage_json"],
                tid,
            ))
            
        elif op == "DEPRECATE":
            # Check if node exists
            cursor.execute(
                "SELECT deprecated FROM nodes WHERE node_id = ?",
                (tid,)
            )
            row = cursor.fetchone()
            if not row:
                raise AuditError(f"DEPRECATE unknown node: {tid}")
            
            # Update node
            cursor.execute("""
                UPDATE nodes SET
                    deprecated = 1,
                    stability = stability * 0.25,
                    lineage_json = json_insert(lineage_json, '$[#]', ?),
                    last_updated = CURRENT_TIMESTAMP
                WHERE node_id = ?
            """, (patch.patch_id, tid))
    
    def reconstruct(self, branch_id: str) -> Dict[str, Node]:
        """Rebuild graph state from database with full integrity verification."""
        if branch_id not in self._branches_cache:
            raise KeyError(f"Unknown branch: {branch_id}")
        
        cursor = self.conn.cursor()
        
        # Get all patches for this branch in order
        cursor.execute("""
            SELECT * FROM patches 
            WHERE branch_id = ? 
            ORDER BY timestamp ASC
        """, (branch_id,))
        
        prev_hash = None
        last_ts = 0
        nodes: Dict[str, Node] = {}
        
        for row in cursor.fetchall():
            patch = self._deserialize_patch(row)
            
            # Temporal monotonicity
            if patch.timestamp <= last_ts:
                raise AuditError("Non-monotonic timestamp detected during reconstruction")
            last_ts = patch.timestamp
            
            # Verify chain hashes
            commit = patch.chain["commit_hash"] if patch.chain else None
            expected_prev = patch.chain["previous_commit_hash"] if patch.chain else None
            
            if expected_prev != prev_hash:
                raise AuditError("Hash-chain discontinuity detected")
            
            # Reapply patch to rebuild state
            self._apply_patch_to_reconstruction(patch, nodes)
            prev_hash = commit
        
        return nodes
    
    def _apply_patch_to_reconstruction(self, patch: Patch, nodes: Dict[str, Node]):
        """Apply patch during reconstruction."""
        op = patch.operation
        tid = patch.target_id
        
        if op == "ADD":
            if tid in nodes and not nodes[tid].deprecated:
                raise AuditError(f"ADD to existing active node during reconstruction: {tid}")
            nodes[tid] = self._node_from_patch(patch, existing=None)
            
        elif op == "MODIFY":
            if tid not in nodes:
                raise AuditError(f"MODIFY unknown node during reconstruction: {tid}")
            nodes[tid] = self._node_from_patch(patch, existing=nodes[tid])
            
        elif op == "DEPRECATE":
            if tid not in nodes:
                raise AuditError(f"DEPRECATE unknown node during reconstruction: {tid}")
            n = nodes[tid]
            n.deprecated = True
            n.lineage.append(patch.patch_id)
            n.stability = clamp01(n.stability * 0.25)
    
    def get_patch(self, patch_id: str) -> Optional[Patch]:
        """Retrieve a patch by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM patches WHERE patch_id = ?", (patch_id,))
        row = cursor.fetchone()
        return self._deserialize_patch(row) if row else None
    
    def get_patches_by_target(self, target_id: str, branch_id: Optional[str] = None) -> List[Patch]:
        """Get all patches affecting a specific target."""
        cursor = self.conn.cursor()
        
        if branch_id:
            cursor.execute("""
                SELECT * FROM patches 
                WHERE target_id = ? AND branch_id = ?
                ORDER BY timestamp ASC
            """, (target_id, branch_id))
        else:
            cursor.execute("""
                SELECT * FROM patches 
                WHERE target_id = ?
                ORDER BY timestamp ASC
            """, (target_id,))
        
        return [self._deserialize_patch(row) for row in cursor.fetchall()]
    
    def get_patches_by_category(self, category: str, branch_id: Optional[str] = None) -> List[Patch]:
        """Get all patches of a specific category."""
        if category not in CATEGORIES:
            raise ValueError(f"Invalid category: {category}")
        
        cursor = self.conn.cursor()
        
        if branch_id:
            cursor.execute("""
                SELECT * FROM patches 
                WHERE category = ? AND branch_id = ?
                ORDER BY timestamp ASC
            """, (category, branch_id))
        else:
            cursor.execute("""
                SELECT * FROM patches 
                WHERE category = ?
                ORDER BY timestamp ASC
            """, (category,))
        
        return [self._deserialize_patch(row) for row in cursor.fetchall()]
    
    def get_nodes(self, branch_id: Optional[str] = None) -> Dict[str, Node]:
        """Get current nodes for a branch (or all nodes)."""
        cursor = self.conn.cursor()
        
        if branch_id:
            # Reconstruct specific branch
            return self.reconstruct(branch_id)
        else:
            # Get all nodes from database (latest state across all branches)
            cursor.execute("SELECT * FROM nodes WHERE deprecated = 0")
            nodes = {}
            for row in cursor.fetchall():
                node = self._deserialize_node(row)
                nodes[node.node_id] = node
            return nodes
    
    def search_patches(self, content_query: str, limit: int = 100) -> List[Patch]:
        """Search patches by content (full-text search)."""
        cursor = self.conn.cursor()
        
        # Simple LIKE search (could be enhanced with FTS5)
        cursor.execute("""
            SELECT * FROM patches 
            WHERE payload_json LIKE ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (f"%{content_query}%", limit))
        
        return [self._deserialize_patch(row) for row in cursor.fetchall()]
    
    def get_branch_stats(self, branch_id: str) -> Dict[str, Any]:
        """Get statistics for a branch."""
        cursor = self.conn.cursor()
        
        # Count patches by category
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM patches 
            WHERE branch_id = ?
            GROUP BY category
        """, (branch_id,))
        
        category_counts = {row["category"]: row["count"] for row in cursor.fetchall()}
        
        # Count nodes by category
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM nodes 
            WHERE node_id IN (
                SELECT DISTINCT target_id FROM patches WHERE branch_id = ?
            )
            GROUP BY category
        """, (branch_id,))
        
        node_category_counts = {row["category"]: row["count"] for row in cursor.fetchall()}
        
        # Total patches and nodes
        cursor.execute("SELECT COUNT(*) as count FROM patches WHERE branch_id = ?", (branch_id,))
        total_patches = cursor.fetchone()["count"]
        
        cursor.execute("""
            SELECT COUNT(DISTINCT target_id) as count 
            FROM patches 
            WHERE branch_id = ?
        """, (branch_id,))
        total_nodes = cursor.fetchone()["count"]
        
        # Latest patch timestamp
        cursor.execute("""
            SELECT MAX(timestamp) as latest_ts 
            FROM patches 
            WHERE branch_id = ?
        """, (branch_id,))
        latest_ts = cursor.fetchone()["latest_ts"] or 0
        
        return {
            "branch_id": branch_id,
            "total_patches": total_patches,
            "total_nodes": total_nodes,
            "category_counts": category_counts,
            "node_category_counts": node_category_counts,
            "latest_timestamp": latest_ts,
            "patches_per_category": category_counts,
            "nodes_per_category": node_category_counts,
        }
    
    def get_store_stats(self) -> Dict[str, Any]:
        """Get overall store statistics."""
        cursor = self.conn.cursor()
        
        stats = {
            "total_patches": 0,
            "total_nodes": 0,
            "total_branches": 0,
            "branches": [],
        }
        
        # Basic counts
        cursor.execute("SELECT COUNT(*) as count FROM patches")
        stats["total_patches"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM nodes WHERE deprecated = 0")
        stats["total_nodes"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM branches")
        stats["total_branches"] = cursor.fetchone()["count"]
        
        # Branch details
        cursor.execute("SELECT branch_id FROM branches ORDER BY branch_id")
        branch_ids = [row["branch_id"] for row in cursor.fetchall()]
        
        stats["branches"] = []
        for branch_id in branch_ids:
            branch_stats = self.get_branch_stats(branch_id)
            stats["branches"].append(branch_stats)
        
        return stats
    
    def export_to_memory_store(self) -> AlexandriaStore:
        """Export SQLite store to in-memory AlexandriaStore."""
        memory_store = AlexandriaStore()
        
        # For each branch, reconstruct and create equivalent patches
        for branch_id in self._branches_cache:
            # Get all patches for this branch
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM patches 
                WHERE branch_id = ? 
                ORDER BY timestamp ASC
            """, (branch_id,))
            
            # Submit each patch to memory store
            memory_store.checkout(branch_id) if branch_id in memory_store.branches else memory_store.create_branch(branch_id)
            for row in cursor.fetchall():
                patch = self._deserialize_patch(row)
                try:
                    memory_store.submit(patch)
                except AuditError as e:
                    print(f"Warning: Could not import patch {patch.patch_id}: {e}")
        
        return memory_store
    
    def vacuum(self):
        """Reclaim unused database space and optimize."""
        self.conn.execute("VACUUM")
        self.conn.execute("ANALYZE")
        
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __del__(self):
        """Ensure connection is closed on destruction."""
        self.close()


class AlexandriaSQLiteMIVPStore(AlexandriaSQLiteStore):
    """
    SQLite store with MIVP identity verification support.
    Extends AlexandriaSQLiteStore with MIVP-specific functionality.
    """
    
    def __init__(self, db_path: str = "alexandria_store.db", agent_identity: Optional[AgentIdentity] = None):
        super().__init__(db_path)
        self.agent_identity = agent_identity
    
    def submit_with_identity(self, patch: Patch, instance_epoch: Optional[int] = None) -> str:
        """Submit patch with MIVP identity (requires agent_identity)."""
        if not self.agent_identity:
            raise ValueError("agent_identity required for submit_with_identity")
        
        # Add identity to audit metadata
        identity_info = self.agent_identity.get_identity_dict(instance_epoch)
        
        # Merge with existing audit data
        new_audit = patch.audit.copy()
        if "mivp_identity" not in new_audit:
            new_audit["mivp_identity"] = identity_info
        else:
            # Update existing identity
            new_audit["mivp_identity"].update(identity_info)
        
        # Create new patch with updated audit
        from dataclasses import replace
        updated_patch = replace(patch, audit=new_audit)
        
        # Submit as normal (parent class will handle identity storage)
        return super().submit(updated_patch)
    
    def get_patches_by_agent(self, agent_name: str) -> List[Patch]:
        """Get all patches submitted by a specific agent."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.* FROM patches p
            JOIN identity_hashes ih ON p.patch_id = ih.patch_id
            WHERE ih.agent_name = ?
            ORDER BY p.timestamp ASC
        """, (agent_name,))
        
        return [self._deserialize_patch(row) for row in cursor.fetchall()]
    
    def get_identity_for_patch(self, patch_id: str) -> Optional[Dict[str, Any]]:
        """Get MIVP identity information for a patch."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM identity_hashes WHERE patch_id = ?", (patch_id,))
        row = cursor.fetchone()
        if not row:
            return None

        result = {
            "agent_name": row["agent_name"],
            "mh": row["mh_hex"],
            "ph": row["ph_hex"],
            "rh": row["rh_hex"],
            "cih": row["cih_hex"],
            "instance_epoch": row["instance_epoch"],
            "timestamp": row["timestamp"],
            "signer_id": row["signer_id_hex"],
            "signature": row["signature_hex"],
        }
        # Include extended runtime hash sub-hashes if stored
        rh_extended_json = row["rh_extended_json"] if "rh_extended_json" in row.keys() else None
        if rh_extended_json:
            result["rh_extended"] = json.loads(rh_extended_json)
        return result

    def verify_patch_identity_internal(self, patch_id: str) -> bool:
        """Verify internal consistency of patch identity (CIH matches MH/PH/RH)."""
        identity = self.get_identity_for_patch(patch_id)
        if not identity:
            return False
        return verify_cih_internal_consistency(identity)

    # ------------------------------------------------------------------ #
    # Extended identity query patterns                                     #
    # ------------------------------------------------------------------ #

    def get_all_agents(self) -> List[str]:
        """Return a sorted list of all distinct agent names that have submitted patches."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT agent_name
            FROM identity_hashes
            WHERE agent_name IS NOT NULL
            ORDER BY agent_name
        """)
        return [row["agent_name"] for row in cursor.fetchall()]

    def count_patches_by_agent(self) -> Dict[str, int]:
        """Return a mapping of agent_name → patch count."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT agent_name, COUNT(*) AS cnt
            FROM identity_hashes
            WHERE agent_name IS NOT NULL
            GROUP BY agent_name
            ORDER BY cnt DESC
        """)
        return {row["agent_name"]: row["cnt"] for row in cursor.fetchall()}

    def get_patches_by_cih(self, cih_hex: str) -> List[Patch]:
        """Get all patches submitted with a specific Composite Instance Hash."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.* FROM patches p
            JOIN identity_hashes ih ON p.patch_id = ih.patch_id
            WHERE ih.cih_hex = ?
            ORDER BY p.timestamp ASC
        """, (cih_hex,))
        return [self._deserialize_patch(row) for row in cursor.fetchall()]

    def get_patches_by_mh(self, mh_hex: str) -> List[Patch]:
        """Get all patches submitted by agents sharing a specific Model Hash."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.* FROM patches p
            JOIN identity_hashes ih ON p.patch_id = ih.patch_id
            WHERE ih.mh_hex = ?
            ORDER BY p.timestamp ASC
        """, (mh_hex,))
        return [self._deserialize_patch(row) for row in cursor.fetchall()]

    def get_patches_in_epoch_range(
        self,
        agent_name: str,
        start_epoch: Optional[int] = None,
        end_epoch: Optional[int] = None,
    ) -> List[Patch]:
        """
        Get patches submitted by an agent within an instance epoch range.
        None means unbounded on that side.
        """
        cursor = self.conn.cursor()
        conditions = ["ih.agent_name = ?"]
        params: list = [agent_name]
        if start_epoch is not None:
            conditions.append("ih.instance_epoch >= ?")
            params.append(start_epoch)
        if end_epoch is not None:
            conditions.append("ih.instance_epoch <= ?")
            params.append(end_epoch)
        where = " AND ".join(conditions)
        cursor.execute(f"""
            SELECT p.* FROM patches p
            JOIN identity_hashes ih ON p.patch_id = ih.patch_id
            WHERE {where}
            ORDER BY p.timestamp ASC
        """, params)
        return [self._deserialize_patch(row) for row in cursor.fetchall()]

    def get_agent_statistics(self, agent_name: str) -> Dict[str, Any]:
        """
        Compute statistics for a single agent's contribution history.

        Returns:
            patch_count, distinct_cih_count, distinct_mh_count,
            first_seen, last_seen, epoch_min, epoch_max,
            category_breakdown, signed_count
        """
        cursor = self.conn.cursor()

        # Patch count and time range
        cursor.execute("""
            SELECT COUNT(*) AS cnt,
                   MIN(p.timestamp) AS first_ts,
                   MAX(p.timestamp) AS last_ts,
                   MIN(ih.instance_epoch) AS ep_min,
                   MAX(ih.instance_epoch) AS ep_max
            FROM patches p
            JOIN identity_hashes ih ON p.patch_id = ih.patch_id
            WHERE ih.agent_name = ?
        """, (agent_name,))
        row = cursor.fetchone()
        if not row or row["cnt"] == 0:
            return {"agent_name": agent_name, "patch_count": 0}

        # Distinct hashes (detect model/policy/runtime drift)
        cursor.execute("""
            SELECT COUNT(DISTINCT cih_hex) AS d_cih,
                   COUNT(DISTINCT mh_hex)  AS d_mh,
                   COUNT(DISTINCT ph_hex)  AS d_ph,
                   COUNT(DISTINCT rh_hex)  AS d_rh
            FROM identity_hashes
            WHERE agent_name = ?
        """, (agent_name,))
        hrow = cursor.fetchone()

        # Category breakdown
        cursor.execute("""
            SELECT p.category, COUNT(*) AS cnt
            FROM patches p
            JOIN identity_hashes ih ON p.patch_id = ih.patch_id
            WHERE ih.agent_name = ?
            GROUP BY p.category
        """, (agent_name,))
        category_breakdown = {r["category"]: r["cnt"] for r in cursor.fetchall()}

        # Signed patches
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM identity_hashes
            WHERE agent_name = ? AND signature_hex IS NOT NULL
        """, (agent_name,))
        signed_count = cursor.fetchone()["cnt"]

        return {
            "agent_name": agent_name,
            "patch_count": row["cnt"],
            "first_seen": row["first_ts"],
            "last_seen": row["last_ts"],
            "epoch_min": row["ep_min"],
            "epoch_max": row["ep_max"],
            "distinct_cih_count": hrow["d_cih"],
            "distinct_mh_count": hrow["d_mh"],
            "distinct_ph_count": hrow["d_ph"],
            "distinct_rh_count": hrow["d_rh"],
            "category_breakdown": category_breakdown,
            "signed_count": signed_count,
        }

    def find_identity_drift(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Detect identity drift for an agent: moments when MH, PH, or RH changed.

        Returns a list of changepoints (each representing a patch where at least
        one hash component changed relative to the previous patch from this agent).
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT ih.patch_id, ih.mh_hex, ih.ph_hex, ih.rh_hex, ih.cih_hex,
                   ih.instance_epoch, p.timestamp
            FROM identity_hashes ih
            JOIN patches p ON ih.patch_id = p.patch_id
            WHERE ih.agent_name = ?
            ORDER BY p.timestamp ASC
        """, (agent_name,))
        rows = cursor.fetchall()

        changepoints = []
        prev = None
        for row in rows:
            if prev is not None:
                changed = []
                if row["mh_hex"] != prev["mh_hex"]:
                    changed.append("mh")
                if row["ph_hex"] != prev["ph_hex"]:
                    changed.append("ph")
                if row["rh_hex"] != prev["rh_hex"]:
                    changed.append("rh")
                if changed:
                    changepoints.append({
                        "patch_id": row["patch_id"],
                        "timestamp": row["timestamp"],
                        "changed_components": changed,
                        "new_cih": row["cih_hex"],
                        "prev_cih": prev["cih_hex"],
                        "instance_epoch": row["instance_epoch"],
                    })
            prev = row

        return changepoints

    def get_identity_timeline(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Return a chronological timeline of identity snapshots for an agent.

        Each entry represents one submitted patch with its full identity state,
        so callers can reconstruct how the agent's identity evolved over time.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT ih.*, p.timestamp AS patch_ts, p.branch_id, p.category
            FROM identity_hashes ih
            JOIN patches p ON ih.patch_id = p.patch_id
            WHERE ih.agent_name = ?
            ORDER BY p.timestamp ASC
        """, (agent_name,))

        timeline = []
        for row in cursor.fetchall():
            entry = {
                "patch_id": row["patch_id"],
                "timestamp": row["patch_ts"],
                "branch_id": row["branch_id"],
                "category": row["category"],
                "mh": row["mh_hex"],
                "ph": row["ph_hex"],
                "rh": row["rh_hex"],
                "cih": row["cih_hex"],
                "instance_epoch": row["instance_epoch"],
                "signed": row["signature_hex"] is not None,
            }
            rh_ext = row["rh_extended_json"] if "rh_extended_json" in row.keys() else None
            if rh_ext:
                entry["rh_extended"] = json.loads(rh_ext)
            timeline.append(entry)
        return timeline

    def find_unverified_patches(self, branch_id: Optional[str] = None) -> List[Patch]:
        """
        Find patches that have no MIVP identity attached.
        Useful for auditing which patches lack cryptographic provenance.
        """
        cursor = self.conn.cursor()
        if branch_id:
            cursor.execute("""
                SELECT p.* FROM patches p
                LEFT JOIN identity_hashes ih ON p.patch_id = ih.patch_id
                WHERE ih.patch_id IS NULL AND p.branch_id = ?
                ORDER BY p.timestamp ASC
            """, (branch_id,))
        else:
            cursor.execute("""
                SELECT p.* FROM patches p
                LEFT JOIN identity_hashes ih ON p.patch_id = ih.patch_id
                WHERE ih.patch_id IS NULL
                ORDER BY p.timestamp ASC
            """)
        return [self._deserialize_patch(row) for row in cursor.fetchall()]

    def find_patches_with_extended_rh(self, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find patches that used the three-layer extended runtime hash.
        Returns lightweight dicts (patch_id, agent_name, rh_extended sub-hashes).
        """
        cursor = self.conn.cursor()
        if agent_name:
            cursor.execute("""
                SELECT patch_id, agent_name, cih_hex, rh_extended_json
                FROM identity_hashes
                WHERE rh_extended_json IS NOT NULL AND agent_name = ?
                ORDER BY timestamp ASC
            """, (agent_name,))
        else:
            cursor.execute("""
                SELECT patch_id, agent_name, cih_hex, rh_extended_json
                FROM identity_hashes
                WHERE rh_extended_json IS NOT NULL
                ORDER BY timestamp ASC
            """)
        results = []
        for row in cursor.fetchall():
            results.append({
                "patch_id": row["patch_id"],
                "agent_name": row["agent_name"],
                "cih": row["cih_hex"],
                "rh_extended": json.loads(row["rh_extended_json"]),
            })
        return results


def migrate_memory_to_sqlite(memory_store: AlexandriaStore, db_path: str) -> AlexandriaSQLiteStore:
    """
    Migrate an in-memory AlexandriaStore to SQLite persistence.
    
    Args:
        memory_store: In-memory store to migrate
        db_path: Path to SQLite database file
        
    Returns:
        New SQLite store with all data migrated
    """
    sqlite_store = AlexandriaSQLiteStore(db_path)
    
    # For each branch in memory store
    for branch_id, patches in memory_store.branches.items():
        if branch_id not in sqlite_store._branches_cache:
            sqlite_store.create_branch(branch_id)
        
        # Submit each patch (will trigger full audit)
        for patch in patches:
            try:
                sqlite_store.submit(patch)
            except Exception as e:
                print(f"Warning: Could not migrate patch {patch.patch_id}: {e}")
    
    return sqlite_store


# Quick test/demo
if __name__ == "__main__":
    print("Testing AlexandriaSQLiteStore...")
    
    # Create a test store
    store = AlexandriaSQLiteStore(":memory:")  # In-memory database for testing
    
    # Test basic operations
    from alexandria_v2 import Patch
    
    test_patch = Patch(
        patch_id="test_001",
        parent_patch_id=None,
        branch_id="main",
        timestamp=1000,
        operation="ADD",
        target_id="test_node",
        category="EMPIRICAL",
        payload={"content": "Test content", "assumptions": ["test"]},
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.1},
        chain=None,
    )
    
    try:
        commit_hash = store.submit(test_patch)
        print(f"[OK] Submitted patch: {commit_hash[:16]}...")
        
        # Reconstruct
        nodes = store.reconstruct("main")
        print(f"[OK] Reconstructed {len(nodes)} nodes")
        
        # Get stats
        stats = store.get_store_stats()
        print(f"[OK] Store stats: {stats['total_patches']} patches, {stats['total_branches']} branches")
        
        # Export to memory
        memory_store = store.export_to_memory_store()
        print(f"[OK] Exported to memory store with {len(memory_store.branches)} branches")
        
        store.close()
        print("[OK] All tests passed!")
        
    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()