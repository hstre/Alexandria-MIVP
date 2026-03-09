#!/usr/bin/env python3
"""
Demonstration of SQLite persistence for Alexandria-MIVP.
Shows migration from memory store to SQLite and advanced queries.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import Patch, AlexandriaStore
from sqlite_store import AlexandriaSQLiteStore, migrate_memory_to_sqlite
import time
import tempfile
import shutil

print("=" * 70)
print("Alexandria-MIVP: SQLite Persistence Demo")
print("=" * 70)

# ----------------------------------------------------------------------
# 1. Create a memory store with some data
print("\n1. CREATE MEMORY STORE WITH DATA")
print("-" * 40)

memory_store = AlexandriaStore()
memory_store.checkout("main")

# Add some patches
patches_data = [
    {
        "patch_id": "empirical_001",
        "content": "The sky appears blue during the day.",
        "category": "EMPIRICAL",
        "assumptions": ["Clear atmosphere", "Daytime conditions"],
    },
    {
        "patch_id": "normative_001",
        "content": "One should treat others with respect.",
        "category": "NORMATIVE",
        "assumptions": ["Golden rule principle"],
    },
    {
        "patch_id": "model_001",
        "content": "Assume economic agents act rationally.",
        "category": "MODEL",
        "assumptions": ["Rational choice theory"],
    },
    {
        "patch_id": "speculative_001",
        "content": "Quantum gravity might be explained by string theory.",
        "category": "SPECULATIVE",
        "assumptions": ["String theory framework"],
    },
]

for i, data in enumerate(patches_data):
    patch = Patch(
        patch_id=data["patch_id"],
        parent_patch_id=memory_store.branches["main"][-1].patch_id if memory_store.branches["main"] else None,
        branch_id="main",
        timestamp=int(time.time()) + i * 100,
        operation="ADD",
        target_id=f"node_{i+1:03d}",
        category=data["category"],
        payload={
            "content": data["content"],
            "assumptions": data["assumptions"],
        },
        audit={"validated": True, "decay": 0.01},
        uncertainty={"sigma": 0.05},
        chain=None,
    )
    
    try:
        commit_hash = memory_store.submit(patch)
        print(f"   Added {data['category']}: {data['content'][:40]}...")
    except Exception as e:
        print(f"   [ERROR] Failed to add patch: {e}")

print(f"\n   Memory store: {len(memory_store.branches['main'])} patches, {len(memory_store.nodes)} nodes")

# ----------------------------------------------------------------------
# 2. Migrate to SQLite
print("\n2. MIGRATE TO SQLITE")
print("-" * 40)

# Create temporary database
temp_dir = tempfile.mkdtemp()
db_path = os.path.join(temp_dir, "alexandria.db")
print(f"   Database path: {db_path}")

try:
    sqlite_store = migrate_memory_to_sqlite(memory_store, db_path)
    print(f"   [OK] Migration successful")
    
    # Verify data integrity
    stats = sqlite_store.get_store_stats()
    print(f"   SQLite store: {stats['total_patches']} patches, {stats['total_branches']} branches")
    
    # Compare with memory store
    sqlite_nodes = sqlite_store.reconstruct("main")
    print(f"   Reconstructed nodes: {len(sqlite_nodes)}")
    
    if len(sqlite_nodes) == len(memory_store.nodes):
        print(f"   [OK] Node counts match")
    else:
        print(f"   [WARNING] Node count mismatch: memory={len(memory_store.nodes)}, sqlite={len(sqlite_nodes)}")
        
except Exception as e:
    print(f"   [FAIL] Migration failed: {e}")
    import traceback
    traceback.print_exc()

# ----------------------------------------------------------------------
# 3. Demonstrate SQLite Features
print("\n3. SQLITE ADVANCED FEATURES")
print("-" * 40)

if 'sqlite_store' in locals():
    # 3.1 Query patches by category
    print("\n   3.1 Query patches by category:")
    for category in ["EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"]:
        patches = sqlite_store.get_patches_by_category(category, "main")
        print(f"      {category}: {len(patches)} patches")
    
    # 3.2 Search patches
    print("\n   3.2 Search patches by content:")
    search_results = sqlite_store.search_patches("theory", limit=5)
    print(f"      Search for 'theory': {len(search_results)} results")
    for patch in search_results:
        print(f"        - {patch.patch_id}: {patch.payload['content'][:50]}...")
    
    # 3.3 Get branch statistics
    print("\n   3.3 Branch statistics:")
    branch_stats = sqlite_store.get_branch_stats("main")
    print(f"      Total patches: {branch_stats['total_patches']}")
    print(f"      Total nodes: {branch_stats['total_nodes']}")
    print(f"      Categories: {branch_stats['category_counts']}")
    
    # 3.4 Create a new branch
    print("\n   3.4 Create and query new branch:")
    try:
        sqlite_store.create_branch("research_branch", from_patch_id="model_001")
        sqlite_store.checkout("research_branch")
        print(f"      Created 'research_branch' from patch 'model_001'")
        
        # Add a new patch to the branch
        new_patch = Patch(
            patch_id="research_001",
            parent_patch_id="model_001",
            branch_id="research_branch",
            timestamp=int(time.time()) + 1000,
            operation="ADD",
            target_id="node_research_001",
            category="SPECULATIVE",
            payload={
                "content": "Alternative: behavioral economics suggests bounded rationality.",
                "assumptions": ["Cognitive limitations", "Social influences"],
            },
            audit={"validated": True, "decay": 0.02},
            uncertainty={"sigma": 0.1},
            chain=None,
        )
        
        commit_hash = sqlite_store.submit(new_patch)
        print(f"      Added research patch: {new_patch.payload['content'][:50]}...")
        
        # Compare branches
        main_stats = sqlite_store.get_branch_stats("main")
        research_stats = sqlite_store.get_branch_stats("research_branch")
        print(f"      Main branch: {main_stats['total_patches']} patches")
        print(f"      Research branch: {research_stats['total_patches']} patches")
        
    except Exception as e:
        print(f"      [ERROR] Branch operations failed: {e}")
    
    # 3.5 Demonstrate export back to memory
    print("\n   3.5 Export SQLite back to memory:")
    exported_store = sqlite_store.export_to_memory_store()
    print(f"      Exported: {len(exported_store.branches)} branches")
    for branch_id, patches in exported_store.branches.items():
        print(f"        {branch_id}: {len(patches)} patches")
    
    # 3.6 Database maintenance
    print("\n   3.6 Database maintenance:")
    sqlite_store.vacuum()
    print(f"      Database vacuumed and analyzed")

# ----------------------------------------------------------------------
# 4. Performance comparison
print("\n4. PERFORMANCE COMPARISON")
print("-" * 40)

if 'sqlite_store' in locals() and 'memory_store' in locals():
    import timeit
    
    # Time reconstruction
    def time_reconstruction(store, store_name):
        start = time.time()
        nodes = store.reconstruct("main")
        elapsed = time.time() - start
        print(f"      {store_name}: {elapsed:.4f}s for {len(nodes)} nodes")
        return elapsed
    
    print("    Reconstruction time:")
    sqlite_time = time_reconstruction(sqlite_store, "SQLite")
    memory_time = time_reconstruction(memory_store, "Memory")
    
    speedup = memory_time / sqlite_time if sqlite_time > 0 else 0
    print(f"      Speed factor: {speedup:.2f}x")
    
    # Query performance
    print("\n    Query performance (category counts):")
    start = time.time()
    for category in ["EMPIRICAL", "NORMATIVE", "MODEL", "SPECULATIVE"]:
        patches = sqlite_store.get_patches_by_category(category, "main")
    sqlite_query_time = time.time() - start
    print(f"      SQLite: {sqlite_query_time:.4f}s for 4 category queries")

# ----------------------------------------------------------------------
# 5. Cleanup and summary
print("\n5. SUMMARY")
print("-" * 40)

print("SQLite persistence provides:")
print("  1. [OK] Persistent storage across sessions")
print("  2. [OK] Atomic transactions for data integrity")
print("  3. [OK] Efficient queries via SQL indexes")
print("  4. [OK] Branch statistics and analytics")
print("  5. [OK] Migration tools from memory stores")
print("  6. [OK] Export capabilities to memory stores")
print("  7. [OK] Database maintenance (VACUUM, ANALYZE)")

print("\nUse cases:")
print("  - Long-term epistemic archives")
print("  - Enterprise deployments with audit requirements")
print("  - Research projects needing query capabilities")
print("  - Multi-user environments with concurrent access")

# Cleanup
try:
    if 'sqlite_store' in locals():
        sqlite_store.close()
    
    # Remove temporary directory
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"\nCleaned up temporary files.")
    
except Exception as e:
    print(f"\nCleanup warning: {e}")

print("\n" + "=" * 70)
print("Demo completed successfully!")
print("=" * 70)