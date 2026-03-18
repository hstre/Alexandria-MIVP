"""Tests for distributed_store.py."""
import json
import time
import pytest
import threading


from alexandria_mivp.distributed_store import (
    InMemoryBackend,
    S3Backend,
    IPFSBackend,
    DistributedLedgerBackend,
    MultiBackend,
    DistributedAlexandriaStore,
    StoredObject,
    BackendHealth,
    StorageError,
    LedgerEntry,
)


# ---------------------------------------------------------------------------
# InMemoryBackend tests
# ---------------------------------------------------------------------------

class TestInMemoryBackend:
    def test_save_and_load(self):
        b = InMemoryBackend()
        obj = b.save("key1", b"hello world")
        assert obj.key == "key1"
        assert obj.data == b"hello world"
        assert len(obj.content_hash) == 64  # SHA-256 hex

        loaded = b.load("key1")
        assert loaded.data == b"hello world"

    def test_load_nonexistent(self):
        b = InMemoryBackend()
        with pytest.raises(StorageError, match="Key not found"):
            b.load("missing")

    def test_exists(self):
        b = InMemoryBackend()
        assert b.exists("x") is False
        b.save("x", b"data")
        assert b.exists("x") is True

    def test_delete(self):
        b = InMemoryBackend()
        b.save("k", b"data")
        existed = b.delete("k")
        assert existed is True
        assert b.exists("k") is False

    def test_delete_nonexistent(self):
        b = InMemoryBackend()
        assert b.delete("nonexistent") is False

    def test_list_keys(self):
        b = InMemoryBackend()
        b.save("prefix/a", b"1")
        b.save("prefix/b", b"2")
        b.save("other/c", b"3")
        keys = b.list_keys("prefix/")
        assert sorted(keys) == ["prefix/a", "prefix/b"]

    def test_list_keys_empty_prefix(self):
        b = InMemoryBackend()
        b.save("x", b"1")
        b.save("y", b"2")
        keys = b.list_keys()
        assert sorted(keys) == ["x", "y"]

    def test_overwrite(self):
        b = InMemoryBackend()
        b.save("k", b"original")
        b.save("k", b"updated")
        loaded = b.load("k")
        assert loaded.data == b"updated"

    def test_metadata(self):
        b = InMemoryBackend()
        obj = b.save("k", b"data", metadata={"type": "patch", "version": "1"})
        assert obj.metadata["type"] == "patch"

    def test_size(self):
        b = InMemoryBackend()
        assert b.size() == 0
        b.save("a", b"1")
        b.save("b", b"2")
        assert b.size() == 2

    def test_name(self):
        b = InMemoryBackend()
        assert b.name == "InMemoryBackend"

    def test_content_hash_correct(self):
        import hashlib
        b = InMemoryBackend()
        data = b"test content"
        obj = b.save("k", data)
        expected = hashlib.sha256(data).hexdigest()
        assert obj.content_hash == expected

    def test_thread_safety(self):
        b = InMemoryBackend()
        errors = []

        def worker(i):
            try:
                b.save(f"key{i}", f"value{i}".encode())
                b.load(f"key{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert b.size() == 20

    def test_health_check(self):
        b = InMemoryBackend()
        health = b.health()
        assert health.available is True
        assert health.latency_ms is not None
        assert health.error is None


# ---------------------------------------------------------------------------
# S3Backend (mock mode) tests
# ---------------------------------------------------------------------------

class TestS3BackendMock:
    def test_save_and_load(self):
        b = S3Backend(bucket="test-bucket", prefix="alex/", mock=True)
        obj = b.save("patch1", b"data")
        loaded = b.load("patch1")
        assert loaded.data == b"data"

    def test_prefix_transparent(self):
        b = S3Backend(bucket="test-bucket", prefix="alex/", mock=True)
        b.save("k", b"v")
        assert b.exists("k") is True

    def test_list_keys_strips_prefix(self):
        b = S3Backend(bucket="test-bucket", prefix="alex/", mock=True)
        b.save("patches/p1", b"1")
        b.save("patches/p2", b"2")
        keys = b.list_keys("patches/")
        assert sorted(keys) == ["patches/p1", "patches/p2"]

    def test_delete(self):
        b = S3Backend(bucket="test-bucket", mock=True)
        b.save("k", b"data")
        assert b.delete("k") is True
        assert b.exists("k") is False

    def test_name(self):
        b = S3Backend(bucket="my-bucket", mock=True)
        assert "my-bucket" in b.name


# ---------------------------------------------------------------------------
# IPFSBackend (mock mode) tests
# ---------------------------------------------------------------------------

class TestIPFSBackendMock:
    def test_save_and_load(self):
        b = IPFSBackend(mock=True)
        obj = b.save("doc1", b"IPFS content")
        loaded = b.load("doc1")
        assert loaded.data == b"IPFS content"

    def test_exists(self):
        b = IPFSBackend(mock=True)
        assert b.exists("k") is False
        b.save("k", b"data")
        assert b.exists("k") is True

    def test_delete_removes_index(self):
        b = IPFSBackend(mock=True)
        b.save("k", b"data")
        b.delete("k")
        assert b.exists("k") is False

    def test_get_cid_in_mock(self):
        b = IPFSBackend(mock=True)
        b.save("k", b"content")
        cid = b.get_cid("k")
        assert cid is not None

    def test_list_keys(self):
        b = IPFSBackend(mock=True)
        b.save("doc/a", b"1")
        b.save("doc/b", b"2")
        keys = b.list_keys("doc/")
        assert sorted(keys) == ["doc/a", "doc/b"]

    def test_load_nonexistent(self):
        b = IPFSBackend(mock=True)
        with pytest.raises(StorageError):
            b.load("nonexistent")

    def test_name(self):
        b = IPFSBackend(mock=True)
        assert "IPFS" in b.name


# ---------------------------------------------------------------------------
# DistributedLedgerBackend tests
# ---------------------------------------------------------------------------

class TestDistributedLedgerBackend:
    def test_save_and_load(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        obj = ledger.save("k1", b"data1")
        loaded = ledger.load("k1")
        assert loaded.data == b"data1"

    def test_ledger_grows(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        ledger.save("k1", b"data1")
        ledger.save("k2", b"data2")
        ledger.save("k3", b"data3")
        entries = ledger.get_ledger()
        assert len(entries) == 3
        assert entries[0].sequence == 0
        assert entries[2].sequence == 2

    def test_chain_verification_valid(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        ledger.save("k1", b"data1")
        ledger.save("k2", b"data2")
        ok, reason = ledger.verify_chain()
        assert ok is True
        assert reason is None

    def test_chain_verification_empty(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        ok, reason = ledger.verify_chain()
        assert ok is True

    def test_chain_verification_tampered(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        ledger.save("k1", b"data1")
        ledger.save("k2", b"data2")
        # Tamper with chain
        with ledger._lock:
            ledger._ledger[1].entry_hash = "tampered_hash"
        ok, reason = ledger.verify_chain()
        assert ok is False
        assert reason is not None

    def test_first_entry_has_genesis_prev(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        ledger.save("k1", b"data1")
        entries = ledger.get_ledger()
        assert entries[0].previous_hash == "0" * 64

    def test_linked_hashes(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        ledger.save("k1", b"data1")
        ledger.save("k2", b"data2")
        entries = ledger.get_ledger()
        assert entries[1].previous_hash == entries[0].entry_hash

    def test_name(self):
        underlying = InMemoryBackend()
        ledger = DistributedLedgerBackend(underlying)
        assert "DistributedLedger" in ledger.name


# ---------------------------------------------------------------------------
# MultiBackend tests
# ---------------------------------------------------------------------------

class TestMultiBackend:
    def test_save_replicates_to_all(self):
        b1 = InMemoryBackend()
        b2 = InMemoryBackend()
        multi = MultiBackend([b1, b2])
        multi.save("k", b"data")
        assert b1.exists("k")
        assert b2.exists("k")

    def test_load_from_primary(self):
        b1 = InMemoryBackend()
        b2 = InMemoryBackend()
        multi = MultiBackend([b1, b2], read_primary_only=True)
        multi.save("k", b"data")
        loaded = multi.load("k")
        assert loaded.data == b"data"

    def test_load_fallback_on_primary_failure(self):
        b1 = InMemoryBackend()
        b2 = InMemoryBackend()
        multi = MultiBackend([b1, b2], read_primary_only=False)
        b2.save("k", b"data")  # only in b2
        loaded = multi.load("k")
        assert loaded.data == b"data"

    def test_exists_any(self):
        b1 = InMemoryBackend()
        b2 = InMemoryBackend()
        multi = MultiBackend([b1, b2])
        b2.save("k", b"data")
        assert multi.exists("k") is True
        assert multi.exists("nonexistent") is False

    def test_delete_from_all(self):
        b1 = InMemoryBackend()
        b2 = InMemoryBackend()
        multi = MultiBackend([b1, b2])
        multi.save("k", b"data")
        multi.delete("k")
        assert not b1.exists("k")
        assert not b2.exists("k")

    def test_list_keys_union(self):
        b1 = InMemoryBackend()
        b2 = InMemoryBackend()
        multi = MultiBackend([b1, b2])
        b1.save("a", b"1")
        b2.save("b", b"2")
        keys = multi.list_keys()
        assert sorted(keys) == ["a", "b"]

    def test_requires_at_least_one_backend(self):
        with pytest.raises(ValueError):
            MultiBackend([])

    def test_health_all(self):
        b1 = InMemoryBackend()
        b2 = InMemoryBackend()
        multi = MultiBackend([b1, b2])
        healths = multi.health_all()
        assert len(healths) == 2
        assert all(h.available for h in healths)


# ---------------------------------------------------------------------------
# DistributedAlexandriaStore tests
# ---------------------------------------------------------------------------

class _FakePatch:
    def __init__(self, patch_id, parent_patch_id=None, branch_id="main",
                 operation="ADD", target_id="node1", category="EMPIRICAL",
                 payload=None, audit=None, uncertainty=None):
        self.patch_id = patch_id
        self.parent_patch_id = parent_patch_id
        self.branch_id = branch_id
        self.timestamp = int(time.time())
        self.operation = operation
        self.target_id = target_id
        self.category = category
        self.payload = payload or {"content": "test"}
        self.audit = audit or {}
        self.uncertainty = uncertainty or {}


class TestDistributedAlexandriaStore:
    def test_save_and_load_patch(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        patch = _FakePatch("p1", payload={"content": "Hello"})
        store.save_patch(patch)
        loaded = store.load_patch_dict("p1")
        assert loaded["patch_id"] == "p1"
        assert loaded["payload"]["content"] == "Hello"

    def test_patch_exists(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        assert store.patch_exists("p1") is False
        patch = _FakePatch("p1")
        store.save_patch(patch)
        assert store.patch_exists("p1") is True

    def test_branch_manifest(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        store.save_branch_manifest("main", ["p1", "p2", "p3"])
        manifest = store.load_branch_manifest("main")
        assert manifest == ["p1", "p2", "p3"]

    def test_list_patches(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        store.save_patch(_FakePatch("p1"))
        store.save_patch(_FakePatch("p2"))
        patches = store.list_patches()
        assert sorted(patches) == ["p1", "p2"]

    def test_list_branches(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        store.save_branch_manifest("main", [])
        store.save_branch_manifest("feature", [])
        branches = store.list_branches()
        assert sorted(branches) == ["feature", "main"]

    def test_namespace(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend, namespace="project/")
        store.save_patch(_FakePatch("p1"))
        keys = backend.list_keys("project/patches/")
        assert len(keys) == 1

    def test_node_snapshot(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        node_dict = {"content": "test", "sigma": 0.1}
        store.save_node_snapshot("main", "node1", node_dict)
        loaded = store.load_node_snapshot("main", "node1")
        assert loaded["content"] == "test"

    def test_health(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        health = store.health()
        assert health.available is True

    def test_backend_property(self):
        backend = InMemoryBackend()
        store = DistributedAlexandriaStore(backend)
        assert store.backend is backend
