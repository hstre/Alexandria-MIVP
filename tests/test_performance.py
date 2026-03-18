"""Tests for performance.py (NodeCache, QueryCache, BatchProcessor, PerformanceMonitor)."""
import sys
import os
import time
import threading
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from performance import NodeCache, QueryCache, BatchProcessor, BatchReport, PerformanceMonitor


# ---------------------------------------------------------------------------
# NodeCache tests
# ---------------------------------------------------------------------------

class TestNodeCache:
    def test_miss_then_put_then_hit(self):
        cache = NodeCache(max_size=10)
        result = cache.get("main", "patch1")
        assert result is None
        assert cache._misses == 1

        cache.put("main", "patch1", {"node_a": "data"})
        result = cache.get("main", "patch1")
        assert result == {"node_a": "data"}
        assert cache._hits == 1

    def test_get_or_compute_calls_fn_once(self):
        cache = NodeCache(max_size=10)
        calls = []
        def compute():
            calls.append(1)
            return {"nodes": 42}

        r1 = cache.get_or_compute("main", "p1", compute)
        r2 = cache.get_or_compute("main", "p1", compute)
        assert r1 == r2
        assert len(calls) == 1  # only called once

    def test_lru_eviction(self):
        cache = NodeCache(max_size=3)
        cache.put("b", "p1", "v1")
        cache.put("b", "p2", "v2")
        cache.put("b", "p3", "v3")
        # Access p1 to make it recent
        cache.get("b", "p1")
        # Add p4 – should evict p2 (LRU)
        cache.put("b", "p4", "v4")
        assert cache.size == 3
        assert cache.get("b", "p2") is None
        assert cache.get("b", "p1") is not None

    def test_invalidate_by_branch(self):
        cache = NodeCache(max_size=10)
        cache.put("branch_x", "p1", "data1")
        cache.put("branch_x", "p2", "data2")
        cache.put("branch_y", "p3", "data3")
        count = cache.invalidate("branch_x")
        assert count == 2
        assert cache.get("branch_x", "p1") is None
        assert cache.get("branch_y", "p3") == "data3"

    def test_clear(self):
        cache = NodeCache(max_size=10)
        cache.put("b", "p", "v")
        cache.clear()
        assert cache.size == 0
        assert cache._hits == 0
        assert cache._misses == 0

    def test_hit_rate(self):
        cache = NodeCache(max_size=10)
        cache.put("b", "p", "v")
        cache.get("b", "p")
        cache.get("b", "p")
        cache.get("b", "p_missing")
        # 2 hits, 1 miss
        assert abs(cache.hit_rate - 2/3) < 1e-9

    def test_hit_rate_no_accesses(self):
        cache = NodeCache(max_size=10)
        assert cache.hit_rate == 0.0

    def test_stats(self):
        cache = NodeCache(max_size=5)
        s = cache.stats()
        assert "size" in s
        assert "max_size" in s
        assert s["max_size"] == 5

    def test_none_patch_id(self):
        cache = NodeCache(max_size=10)
        cache.put("main", None, {"empty": True})
        result = cache.get("main", None)
        assert result == {"empty": True}


# ---------------------------------------------------------------------------
# QueryCache tests
# ---------------------------------------------------------------------------

class TestQueryCache:
    def test_put_and_get(self):
        cache = QueryCache(ttl=60.0)
        cache.put("key1", [1, 2, 3])
        result = cache.get("key1")
        assert result == [1, 2, 3]

    def test_miss(self):
        cache = QueryCache(ttl=60.0)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        cache = QueryCache(ttl=0.05)  # 50ms TTL
        cache.put("k", "value")
        assert cache.get("k") == "value"
        time.sleep(0.1)
        assert cache.get("k") is None  # expired

    def test_evict_expired(self):
        cache = QueryCache(ttl=0.05, max_size=100)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        time.sleep(0.1)
        evicted = cache.evict_expired()
        assert evicted == 2
        assert cache.size == 0

    def test_max_size_eviction(self):
        cache = QueryCache(ttl=60.0, max_size=3)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")
        cache.put("k4", "v4")  # evicts oldest
        assert cache.size == 3

    def test_cached_decorator(self):
        cache = QueryCache(ttl=60.0)
        calls = []

        @cache.cached
        def expensive(x, y):
            calls.append((x, y))
            return x + y

        r1 = expensive(1, 2)
        r2 = expensive(1, 2)
        r3 = expensive(2, 3)
        assert r1 == 3
        assert r2 == 3
        assert r3 == 5
        assert len(calls) == 2  # only 2 unique calls

    def test_invalidate_all(self):
        cache = QueryCache(ttl=60.0)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.invalidate_all()
        assert cache.size == 0

    def test_hit_rate(self):
        cache = QueryCache(ttl=60.0)
        cache.put("k", "v")
        cache.get("k")
        cache.get("k")
        cache.get("missing")
        assert abs(cache.hit_rate - 2/3) < 1e-9

    def test_stats(self):
        cache = QueryCache(ttl=30.0, max_size=100)
        s = cache.stats()
        assert s["ttl"] == 30.0
        assert s["max_size"] == 100


# ---------------------------------------------------------------------------
# BatchProcessor tests
# ---------------------------------------------------------------------------

class _FakePatch:
    def __init__(self, patch_id, should_fail=False):
        self.patch_id = patch_id
        self._should_fail = should_fail


class _FakeStore:
    def __init__(self):
        self._submitted = []
        self._lock = threading.Lock()

    def submit_with_identity(self, patch):
        if patch._should_fail:
            raise ValueError(f"Simulated failure for {patch.patch_id}")
        with self._lock:
            self._submitted.append(patch.patch_id)
        return f"hash_{patch.patch_id}"


class TestBatchProcessor:
    def test_submit_batch_all_success(self):
        store = _FakeStore()
        processor = BatchProcessor(store, max_workers=2)
        patches = [_FakePatch(f"p{i}") for i in range(5)]
        report = processor.submit_batch(patches)
        assert report.total == 5
        assert report.succeeded == 5
        assert report.failed == 0
        assert report.patches_per_second > 0

    def test_submit_batch_with_failures(self):
        store = _FakeStore()
        processor = BatchProcessor(store, max_workers=2)
        patches = [_FakePatch("ok"), _FakePatch("fail", should_fail=True)]
        report = processor.submit_batch(patches)
        assert report.total == 2
        assert report.succeeded == 1
        assert report.failed == 1

    def test_batch_result_details(self):
        store = _FakeStore()
        processor = BatchProcessor(store, max_workers=1)
        patches = [_FakePatch("p1"), _FakePatch("p2", should_fail=True)]
        report = processor.submit_batch(patches)
        results = {r.patch_id: r for r in report.results}
        assert results["p1"].success is True
        assert results["p1"].commit_hash == "hash_p1"
        assert results["p2"].success is False
        assert "Simulated failure" in results["p2"].error

    def test_submit_batch_sequential(self):
        store = _FakeStore()
        processor = BatchProcessor(store, max_workers=1)
        patches = [_FakePatch(f"p{i}") for i in range(3)]
        report = processor.submit_batch_sequential(patches)
        assert report.total == 3
        assert report.succeeded == 3
        # Sequential submission should preserve order
        assert store._submitted == ["p0", "p1", "p2"]

    def test_empty_batch(self):
        store = _FakeStore()
        processor = BatchProcessor(store)
        report = processor.submit_batch([])
        assert report.total == 0
        assert report.succeeded == 0

    def test_batch_duration_positive(self):
        store = _FakeStore()
        processor = BatchProcessor(store)
        patches = [_FakePatch("p1")]
        report = processor.submit_batch(patches)
        assert report.total_duration_ms >= 0.0


# ---------------------------------------------------------------------------
# PerformanceMonitor tests
# ---------------------------------------------------------------------------

class TestPerformanceMonitor:
    def test_measure_context_manager(self):
        monitor = PerformanceMonitor()
        with monitor.measure("operation_a"):
            time.sleep(0.01)
        assert monitor.measurement_count == 1

    def test_stats_for_named_operation(self):
        monitor = PerformanceMonitor()
        for _ in range(3):
            with monitor.measure("fetch"):
                pass
        s = monitor.stats_for("fetch")
        assert s["count"] == 3
        assert s["min_ms"] >= 0
        assert s["max_ms"] >= s["min_ms"]
        assert s["mean_ms"] >= 0

    def test_stats_for_nonexistent(self):
        monitor = PerformanceMonitor()
        s = monitor.stats_for("nonexistent")
        assert s["count"] == 0

    def test_all_stats(self):
        monitor = PerformanceMonitor()
        with monitor.measure("op_a"):
            pass
        with monitor.measure("op_b"):
            pass
        all_s = monitor.all_stats()
        assert "op_a" in all_s
        assert "op_b" in all_s

    def test_record_manual(self):
        monitor = PerformanceMonitor()
        monitor.record("manual_op", 42.5)
        s = monitor.stats_for("manual_op")
        assert s["count"] == 1
        assert abs(s["mean_ms"] - 42.5) < 1e-9

    def test_report_string(self):
        monitor = PerformanceMonitor()
        with monitor.measure("test_op"):
            pass
        report = monitor.report()
        assert "test_op" in report

    def test_report_no_measurements(self):
        monitor = PerformanceMonitor()
        report = monitor.report()
        assert "no measurements" in report.lower()

    def test_reset(self):
        monitor = PerformanceMonitor()
        with monitor.measure("op"):
            pass
        monitor.reset()
        assert monitor.measurement_count == 0

    def test_thread_safety(self):
        monitor = PerformanceMonitor()
        errors = []

        def worker():
            try:
                for _ in range(50):
                    with monitor.measure("concurrent"):
                        pass
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert monitor.measurement_count == 200
