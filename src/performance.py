"""
Performance-Optimierungen für Alexandria-MIVP.

Bietet:
* LRU-Cache für rekonstruierte Node-Zustände (``NodeCache``)
* Query-Result-Cache mit TTL (``QueryCache``)
* Batch-Patch-Verarbeitung mit paralleler Ausführung (``BatchProcessor``)
* Statistiken & Metriken (``PerformanceMonitor``)

Verwendung::

    from performance import NodeCache, QueryCache, BatchProcessor, PerformanceMonitor

    # Node-Cache
    cache = NodeCache(max_size=1000)
    nodes = cache.get_or_compute("main", lambda: store.reconstruct("main"))

    # Batch-Verarbeitung
    processor = BatchProcessor(store, max_workers=4)
    results = processor.submit_batch(patches)

    # Monitor
    monitor = PerformanceMonitor()
    with monitor.measure("reconstruct"):
        nodes = store.reconstruct("main")
    monitor.report()
"""

from __future__ import annotations

import time
import threading
import hashlib
import json
import contextlib
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, Generic, List, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# LRU-Cache für Node-Zustände
# ---------------------------------------------------------------------------

class NodeCache:
    """
    Thread-sicherer LRU-Cache für rekonstruierte Node-Dicts.

    Vermeidet wiederholtes ``store.reconstruct(branch_id)`` bei identischem
    Branch-Stand.  Der Cache-Key ist ``(branch_id, last_patch_id)``.

    Parameters
    ----------
    max_size:
        Maximale Anzahl gecachter Einträge.
    """

    def __init__(self, max_size: int = 256) -> None:
        self._max_size = max(1, max_size)
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #

    def _make_key(self, branch_id: str, last_patch_id: Optional[str]) -> str:
        return f"{branch_id}::{last_patch_id or '__empty__'}"

    def get(self, branch_id: str, last_patch_id: Optional[str]) -> Optional[Any]:
        key = self._make_key(branch_id, last_patch_id)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, branch_id: str, last_patch_id: Optional[str], nodes: Any) -> None:
        key = self._make_key(branch_id, last_patch_id)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)  # evict LRU
            self._cache[key] = nodes

    def get_or_compute(
        self,
        branch_id: str,
        last_patch_id: Optional[str],
        compute_fn: Callable[[], Any],
    ) -> Any:
        """Get from cache or call compute_fn and cache the result."""
        result = self.get(branch_id, last_patch_id)
        if result is None:
            result = compute_fn()
            self.put(branch_id, last_patch_id, result)
        return result

    def invalidate(self, branch_id: str) -> int:
        """Alle Einträge für einen Branch invalidieren."""
        prefix = f"{branch_id}::"
        with self._lock:
            keys = [k for k in self._cache if k.startswith(prefix)]
            for k in keys:
                del self._cache[k]
        return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self._cache)

    def stats(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


# ---------------------------------------------------------------------------
# Query-Result-Cache mit TTL
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class QueryCache(Generic[T]):
    """
    Thread-sicherer Cache für Query-Ergebnisse mit TTL.

    Parameters
    ----------
    ttl:
        Time-to-live in Sekunden (Default: 60 s).
    max_size:
        Maximale Anzahl gecachter Einträge.
    """

    def __init__(self, ttl: float = 60.0, max_size: int = 512) -> None:
        self._ttl = ttl
        self._max_size = max(1, max_size)
        self._cache: Dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        raw = json.dumps({"args": list(args), "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() > entry.expires_at:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            return entry.value

    def put(self, key: str, value: T) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size and key not in self._cache:
                # Evict oldest (simple strategy)
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = _CacheEntry(value=value, expires_at=time.monotonic() + self._ttl)

    def cached(self, fn: Callable[..., T]) -> Callable[..., T]:
        """Decorator: cache the result of fn based on its arguments."""
        def wrapper(*args: Any, **kwargs: Any) -> T:
            key = self._make_key(*args, **kwargs)
            result = self.get(key)
            if result is None:
                result = fn(*args, **kwargs)
                self.put(key, result)
            return result
        return wrapper

    def invalidate_all(self) -> None:
        with self._lock:
            self._cache.clear()

    def evict_expired(self) -> int:
        now = time.monotonic()
        with self._lock:
            expired = [k for k, v in self._cache.items() if now > v.expires_at]
            for k in expired:
                del self._cache[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "max_size": self._max_size,
            "ttl": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


# ---------------------------------------------------------------------------
# Batch-Verarbeitung
# ---------------------------------------------------------------------------

@dataclass
class BatchResult:
    """Ergebnis der Verarbeitung eines einzelnen Patches im Batch."""
    patch_id: str
    success: bool
    commit_hash: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class BatchReport:
    """Zusammenfassung einer Batch-Verarbeitung."""
    total: int
    succeeded: int
    failed: int
    results: List[BatchResult]
    total_duration_ms: float
    patches_per_second: float


class BatchProcessor:
    """
    Verarbeitet mehrere Patches parallel und sammelt die Ergebnisse.

    Parameters
    ----------
    store:
        AlexandriaMIVPStore oder kompatibles Store-Objekt.
    max_workers:
        Anzahl paralleler Threads (Default: 4).
    """

    def __init__(self, store: Any, max_workers: int = 4) -> None:
        self._store = store
        self._max_workers = max(1, max_workers)

    def submit_batch(
        self,
        patches: List[Any],
        method: str = "submit_with_identity",
    ) -> BatchReport:
        """
        Patches parallel einreichen.

        Parameters
        ----------
        patches:
            Liste von Patch-Objekten.
        method:
            Name der Submit-Methode auf dem Store.

        Returns
        -------
        BatchReport
        """
        submit_fn = getattr(self._store, method)
        results: List[BatchResult] = []
        start_all = time.monotonic()

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(self._submit_one, submit_fn, patch): patch
                for patch in patches
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        total_ms = (time.monotonic() - start_all) * 1000
        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded
        pps = (len(patches) / (total_ms / 1000)) if total_ms > 0 else 0.0

        return BatchReport(
            total=len(patches),
            succeeded=succeeded,
            failed=failed,
            results=results,
            total_duration_ms=total_ms,
            patches_per_second=pps,
        )

    @staticmethod
    def _submit_one(submit_fn: Callable, patch: Any) -> BatchResult:
        t0 = time.monotonic()
        try:
            commit_hash = submit_fn(patch)
            return BatchResult(
                patch_id=patch.patch_id,
                success=True,
                commit_hash=commit_hash,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            return BatchResult(
                patch_id=getattr(patch, "patch_id", "unknown"),
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )

    def submit_batch_sequential(
        self,
        patches: List[Any],
        method: str = "submit_with_identity",
    ) -> BatchReport:
        """Sequentielle Variante für Store-Implementierungen, die nicht thread-safe sind."""
        submit_fn = getattr(self._store, method)
        results: List[BatchResult] = []
        start_all = time.monotonic()

        for patch in patches:
            result = self._submit_one(submit_fn, patch)
            results.append(result)

        total_ms = (time.monotonic() - start_all) * 1000
        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded
        pps = (len(patches) / (total_ms / 1000)) if total_ms > 0 else 0.0

        return BatchReport(
            total=len(patches),
            succeeded=succeeded,
            failed=failed,
            results=results,
            total_duration_ms=total_ms,
            patches_per_second=pps,
        )


# ---------------------------------------------------------------------------
# Performance-Monitor
# ---------------------------------------------------------------------------

@dataclass
class _Measurement:
    name: str
    duration_ms: float
    timestamp: float = field(default_factory=time.monotonic)


class PerformanceMonitor:
    """
    Einfacher Performance-Monitor mit Context-Manager.

    Misst Ausführungszeiten für benannte Operationen und stellt
    Statistiken bereit.
    """

    def __init__(self) -> None:
        self._measurements: List[_Measurement] = []
        self._lock = threading.Lock()

    @contextlib.contextmanager
    def measure(self, name: str) -> Generator[None, None, None]:
        """Context-Manager: misst die Ausführungszeit des Blocks."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            duration_ms = (time.monotonic() - t0) * 1000
            with self._lock:
                self._measurements.append(_Measurement(name=name, duration_ms=duration_ms))

    def record(self, name: str, duration_ms: float) -> None:
        """Messung manuell eintragen."""
        with self._lock:
            self._measurements.append(_Measurement(name=name, duration_ms=duration_ms))

    def stats_for(self, name: str) -> Dict[str, Any]:
        """Statistiken für eine benannte Operation."""
        with self._lock:
            values = [m.duration_ms for m in self._measurements if m.name == name]
        if not values:
            return {"name": name, "count": 0}
        return {
            "name": name,
            "count": len(values),
            "min_ms": min(values),
            "max_ms": max(values),
            "mean_ms": sum(values) / len(values),
            "total_ms": sum(values),
        }

    def all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Statistiken für alle gemessenen Operationen."""
        with self._lock:
            names = {m.name for m in self._measurements}
        return {name: self.stats_for(name) for name in names}

    def report(self) -> str:
        """Formatierter Report als String."""
        stats = self.all_stats()
        if not stats:
            return "PerformanceMonitor: no measurements recorded."
        lines = ["PerformanceMonitor report:"]
        for name, s in sorted(stats.items()):
            if s["count"] == 0:
                continue
            lines.append(
                f"  {name}: count={s['count']}, "
                f"mean={s['mean_ms']:.2f}ms, "
                f"min={s['min_ms']:.2f}ms, "
                f"max={s['max_ms']:.2f}ms"
            )
        return "\n".join(lines)

    def reset(self) -> None:
        with self._lock:
            self._measurements.clear()

    @property
    def measurement_count(self) -> int:
        return len(self._measurements)
