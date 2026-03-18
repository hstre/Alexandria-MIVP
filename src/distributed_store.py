"""
Distributed Storage Backend für Alexandria-MIVP.

Abstrahiert unterschiedliche Storage-Backends hinter einem einheitlichen Interface.
Unterstützte Backends:
* ``InMemoryBackend``   – lokaler Dict-Speicher (zum Testen)
* ``S3Backend``         – AWS S3 / kompatible Objektspeicher
* ``IPFSBackend``       – IPFS Content-Adressed Storage
* ``DistributedLedgerBackend`` – einfaches Ledger (append-only log)
* ``MultiBackend``      – Redundanzschicht über mehrere Backends

Verwendung::

    backend = S3Backend(bucket="my-bucket", prefix="alexandria/")
    store = DistributedAlexandriaStore(backend)
    store.save_patch(patch)
    retrieved = store.load_patch("patch-123")
"""

from __future__ import annotations

import abc
import hashlib
import json
import logging
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------

@dataclass
class StoredObject:
    """Ein im Backend gespeichertes Objekt."""
    key: str
    data: bytes
    content_hash: str          # SHA-256 des Dateninhalts
    timestamp: float
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class BackendHealth:
    """Health-Status eines Storage-Backends."""
    backend_name: str
    available: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class StorageError(Exception):
    """Fehler beim Zugriff auf ein Storage-Backend."""


# ---------------------------------------------------------------------------
# Abstraktes Backend-Interface
# ---------------------------------------------------------------------------

class DistributedBackend(abc.ABC):
    """Abstraktes Interface für Storage-Backends."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Menschenlesbarer Name des Backends."""

    @abc.abstractmethod
    def save(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> StoredObject:
        """Daten unter key speichern; gibt das gespeicherte Objekt zurück."""

    @abc.abstractmethod
    def load(self, key: str) -> StoredObject:
        """Objekt laden; wirft StorageError wenn nicht vorhanden."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        """Prüfen ob key vorhanden ist."""

    @abc.abstractmethod
    def delete(self, key: str) -> bool:
        """key löschen; gibt True zurück wenn existiert."""

    @abc.abstractmethod
    def list_keys(self, prefix: str = "") -> List[str]:
        """Alle keys mit gegebenen Prefix auflisten."""

    def health(self) -> BackendHealth:
        """Health-Check ausführen."""
        t0 = time.monotonic()
        try:
            test_key = f"__health__{int(time.time())}"
            self.save(test_key, b"ok")
            obj = self.load(test_key)
            self.delete(test_key)
            latency_ms = (time.monotonic() - t0) * 1000
            return BackendHealth(
                backend_name=self.name,
                available=True,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            return BackendHealth(
                backend_name=self.name,
                available=False,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# In-Memory Backend (Referenz-Implementierung / Tests)
# ---------------------------------------------------------------------------

class InMemoryBackend(DistributedBackend):
    """
    Lokaler dict-basierter Storage (für Tests und Entwicklung).
    Thread-sicher.
    """

    def __init__(self) -> None:
        self._store: Dict[str, StoredObject] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "InMemoryBackend"

    def save(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> StoredObject:
        obj = StoredObject(
            key=key,
            data=data,
            content_hash=hashlib.sha256(data).hexdigest(),
            timestamp=time.time(),
            metadata=metadata or {},
        )
        with self._lock:
            self._store[key] = obj
        return obj

    def load(self, key: str) -> StoredObject:
        with self._lock:
            obj = self._store.get(key)
        if obj is None:
            raise StorageError(f"Key not found: {key}")
        return obj

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def delete(self, key: str) -> bool:
        with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
        return existed

    def list_keys(self, prefix: str = "") -> List[str]:
        with self._lock:
            return [k for k in self._store if k.startswith(prefix)]

    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# S3 Backend (Stub – benötigt boto3 im Produktionseinsatz)
# ---------------------------------------------------------------------------

class S3Backend(DistributedBackend):
    """
    AWS S3-kompatibler Object Store.

    Benötigt ``boto3`` (nicht in der Basis-Abhängigkeit).  Im Test-Modus
    (``mock=True``) fällt es auf InMemoryBackend zurück.

    Parameters
    ----------
    bucket:
        S3-Bucket-Name.
    prefix:
        Schlüssel-Prefix (z.B. ``"alexandria/"``).
    region:
        AWS-Region.
    endpoint_url:
        Optionaler Custom-Endpoint (z.B. für MinIO).
    mock:
        Falls True: kein echter S3-Zugriff, InMemory-Fallback.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        mock: bool = False,
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix
        self._region = region
        self._endpoint_url = endpoint_url
        self._mock = mock
        self._mock_backend: Optional[InMemoryBackend] = InMemoryBackend() if mock else None
        self._client: Any = None

        if not mock:
            self._client = self._create_client()

    def _create_client(self) -> Any:
        try:
            import boto3
            kwargs: Dict[str, Any] = {"region_name": self._region}
            if self._endpoint_url:
                kwargs["endpoint_url"] = self._endpoint_url
            return boto3.client("s3", **kwargs)
        except ImportError:
            raise StorageError(
                "boto3 is required for S3Backend. Install it with: pip install boto3"
            )

    @property
    def name(self) -> str:
        return f"S3Backend(bucket={self._bucket})"

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}" if self._prefix else key

    def save(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> StoredObject:
        if self._mock:
            return self._mock_backend.save(self._full_key(key), data, metadata)
        try:
            full_key = self._full_key(key)
            extra_args: Dict[str, Any] = {}
            if metadata:
                extra_args["Metadata"] = metadata
            self._client.put_object(
                Bucket=self._bucket,
                Key=full_key,
                Body=data,
                **extra_args,
            )
            return StoredObject(
                key=key,
                data=data,
                content_hash=hashlib.sha256(data).hexdigest(),
                timestamp=time.time(),
                metadata=metadata or {},
            )
        except Exception as exc:
            raise StorageError(f"S3 save failed for key '{key}': {exc}") from exc

    def load(self, key: str) -> StoredObject:
        if self._mock:
            return self._mock_backend.load(self._full_key(key))
        try:
            full_key = self._full_key(key)
            resp = self._client.get_object(Bucket=self._bucket, Key=full_key)
            data = resp["Body"].read()
            metadata = resp.get("Metadata", {})
            return StoredObject(
                key=key,
                data=data,
                content_hash=hashlib.sha256(data).hexdigest(),
                timestamp=time.time(),
                metadata=metadata,
            )
        except Exception as exc:
            raise StorageError(f"S3 load failed for key '{key}': {exc}") from exc

    def exists(self, key: str) -> bool:
        if self._mock:
            return self._mock_backend.exists(self._full_key(key))
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._full_key(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if self._mock:
            return self._mock_backend.delete(self._full_key(key))
        try:
            existed = self.exists(key)
            self._client.delete_object(Bucket=self._bucket, Key=self._full_key(key))
            return existed
        except Exception as exc:
            raise StorageError(f"S3 delete failed for key '{key}': {exc}") from exc

    def list_keys(self, prefix: str = "") -> List[str]:
        if self._mock:
            full_prefix = self._full_key(prefix)
            keys = self._mock_backend.list_keys(full_prefix)
            strip_len = len(self._prefix)
            return [k[strip_len:] for k in keys]
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            full_prefix = self._full_key(prefix)
            keys: List[str] = []
            for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
                for obj in page.get("Contents", []):
                    k = obj["Key"]
                    if self._prefix:
                        k = k[len(self._prefix):]
                    keys.append(k)
            return keys
        except Exception as exc:
            raise StorageError(f"S3 list_keys failed: {exc}") from exc


# ---------------------------------------------------------------------------
# IPFS Backend (Stub)
# ---------------------------------------------------------------------------

class IPFSBackend(DistributedBackend):
    """
    IPFS Content-Addressed Storage.

    Benötigt einen laufenden IPFS-Node (HTTP API auf localhost:5001 per Default).
    Im Mock-Modus fällt es auf InMemoryBackend zurück.

    Hinweis: IPFS ist immutable – ``delete()`` entfernt nur den lokalen Index-Eintrag,
    nicht die Daten aus dem IPFS-Netzwerk.

    Parameters
    ----------
    api_url:
        IPFS HTTP API URL.
    mock:
        Falls True: kein echter IPFS-Zugriff.
    """

    def __init__(self, api_url: str = "http://127.0.0.1:5001", mock: bool = False) -> None:
        self._api_url = api_url
        self._mock = mock
        self._mock_backend: Optional[InMemoryBackend] = InMemoryBackend() if mock else None
        # key → CID mapping (lokaler Index)
        self._index: Dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return f"IPFSBackend(api={self._api_url})"

    def _add_to_ipfs(self, data: bytes) -> str:
        """Daten zu IPFS hinzufügen, CID zurückgeben."""
        try:
            import requests
            resp = requests.post(
                f"{self._api_url}/api/v0/add",
                files={"file": data},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["Hash"]
        except ImportError:
            raise StorageError("requests is required for IPFSBackend. pip install requests")
        except Exception as exc:
            raise StorageError(f"IPFS add failed: {exc}") from exc

    def _get_from_ipfs(self, cid: str) -> bytes:
        try:
            import requests
            resp = requests.post(
                f"{self._api_url}/api/v0/cat",
                params={"arg": cid},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.content
        except ImportError:
            raise StorageError("requests is required for IPFSBackend.")
        except Exception as exc:
            raise StorageError(f"IPFS cat failed for CID '{cid}': {exc}") from exc

    def save(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> StoredObject:
        if self._mock:
            obj = self._mock_backend.save(key, data, metadata)
            with self._lock:
                self._index[key] = obj.content_hash
            return obj
        cid = self._add_to_ipfs(data)
        obj = StoredObject(
            key=key,
            data=data,
            content_hash=cid,
            timestamp=time.time(),
            metadata={**(metadata or {}), "ipfs_cid": cid},
        )
        with self._lock:
            self._index[key] = cid
        return obj

    def load(self, key: str) -> StoredObject:
        if self._mock:
            return self._mock_backend.load(key)
        with self._lock:
            cid = self._index.get(key)
        if cid is None:
            raise StorageError(f"Key not found in IPFS index: {key}")
        data = self._get_from_ipfs(cid)
        return StoredObject(
            key=key,
            data=data,
            content_hash=cid,
            timestamp=time.time(),
            metadata={"ipfs_cid": cid},
        )

    def exists(self, key: str) -> bool:
        if self._mock:
            return self._mock_backend.exists(key)
        with self._lock:
            return key in self._index

    def delete(self, key: str) -> bool:
        """Entfernt nur den lokalen Index-Eintrag (IPFS-Daten bleiben im Netzwerk)."""
        if self._mock:
            return self._mock_backend.delete(key)
        with self._lock:
            existed = key in self._index
            self._index.pop(key, None)
        return existed

    def list_keys(self, prefix: str = "") -> List[str]:
        if self._mock:
            return self._mock_backend.list_keys(prefix)
        with self._lock:
            return [k for k in self._index if k.startswith(prefix)]

    def get_cid(self, key: str) -> Optional[str]:
        """CID (Content Identifier) für einen key zurückgeben."""
        with self._lock:
            return self._index.get(key)


# ---------------------------------------------------------------------------
# Distributed Ledger Backend (Append-Only Log)
# ---------------------------------------------------------------------------

@dataclass
class LedgerEntry:
    """Ein Eintrag im Distributed Ledger."""
    sequence: int
    key: str
    content_hash: str
    timestamp: float
    previous_hash: str            # Hash des vorherigen Eintrags (Kettenverknüpfung)
    entry_hash: str               # Hash dieses Eintrags


class DistributedLedgerBackend(DistributedBackend):
    """
    Append-Only Ledger Backend.

    Speichert Daten in einem kryptographisch verketteten Log.
    Jeder Eintrag enthält den Hash des vorherigen Eintrags
    (ähnlich einer Blockchain ohne Konsens-Mechanismus).

    Parameters
    ----------
    underlying:
        Darunterliegendes Backend für die eigentliche Datenspeicherung.
    """

    def __init__(self, underlying: DistributedBackend) -> None:
        self._underlying = underlying
        self._ledger: List[LedgerEntry] = []
        self._key_seq: Dict[str, int] = {}   # key → latest sequence
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return f"DistributedLedgerBackend(over={self._underlying.name})"

    def _compute_entry_hash(self, seq: int, key: str, content_hash: str,
                             timestamp: float, previous_hash: str) -> str:
        raw = f"{seq}:{key}:{content_hash}:{timestamp:.6f}:{previous_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def save(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> StoredObject:
        obj = self._underlying.save(key, data, metadata)
        with self._lock:
            seq = len(self._ledger)
            prev_hash = self._ledger[-1].entry_hash if self._ledger else "0" * 64
            entry_hash = self._compute_entry_hash(
                seq, key, obj.content_hash, obj.timestamp, prev_hash
            )
            entry = LedgerEntry(
                sequence=seq,
                key=key,
                content_hash=obj.content_hash,
                timestamp=obj.timestamp,
                previous_hash=prev_hash,
                entry_hash=entry_hash,
            )
            self._ledger.append(entry)
            self._key_seq[key] = seq
        return obj

    def load(self, key: str) -> StoredObject:
        return self._underlying.load(key)

    def exists(self, key: str) -> bool:
        return self._underlying.exists(key)

    def delete(self, key: str) -> bool:
        # Ledger ist append-only; wir können Daten nur aus dem Underlying löschen
        # und einen Tombstone-Eintrag hinzufügen
        existed = self._underlying.delete(key)
        if existed:
            tombstone = f"__deleted__{key}".encode()
            self._underlying.save(f"__tombstone__{key}", tombstone)
        return existed

    def list_keys(self, prefix: str = "") -> List[str]:
        return self._underlying.list_keys(prefix)

    def get_ledger(self) -> List[LedgerEntry]:
        """Den kompletten Ledger zurückgeben."""
        with self._lock:
            return list(self._ledger)

    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        """
        Ledger-Kette kryptographisch verifizieren.

        Returns:
            (True, None) wenn valide; (False, reason) bei Fehler.
        """
        with self._lock:
            entries = list(self._ledger)

        if not entries:
            return True, None

        for i, entry in enumerate(entries):
            expected_prev = entries[i - 1].entry_hash if i > 0 else "0" * 64
            if entry.previous_hash != expected_prev:
                return False, f"Chain broken at sequence {i}: previous_hash mismatch."
            expected_hash = self._compute_entry_hash(
                entry.sequence, entry.key, entry.content_hash,
                entry.timestamp, entry.previous_hash,
            )
            if entry.entry_hash != expected_hash:
                return False, f"Entry hash invalid at sequence {i}."

        return True, None


# ---------------------------------------------------------------------------
# Multi-Backend (Redundanzschicht)
# ---------------------------------------------------------------------------

class MultiBackend(DistributedBackend):
    """
    Redundanzschicht: Schreibt in alle Backends, liest vom ersten verfügbaren.

    Parameters
    ----------
    backends:
        Liste von DistributedBackend-Instanzen.
    read_primary_only:
        Wenn True: Lesen nur vom ersten Backend (schneller).
    """

    def __init__(
        self,
        backends: List[DistributedBackend],
        read_primary_only: bool = False,
    ) -> None:
        if not backends:
            raise ValueError("MultiBackend requires at least one backend.")
        self._backends = backends
        self._read_primary_only = read_primary_only

    @property
    def name(self) -> str:
        names = ", ".join(b.name for b in self._backends)
        return f"MultiBackend([{names}])"

    def save(self, key: str, data: bytes, metadata: Optional[Dict[str, str]] = None) -> StoredObject:
        last_error: Optional[Exception] = None
        result: Optional[StoredObject] = None
        for backend in self._backends:
            try:
                result = backend.save(key, data, metadata)
            except StorageError as exc:
                logger.warning("MultiBackend: save failed on %s: %s", backend.name, exc)
                last_error = exc
        if result is None:
            raise StorageError(f"All backends failed for save('{key}'): {last_error}")
        return result

    def load(self, key: str) -> StoredObject:
        backends = self._backends[:1] if self._read_primary_only else self._backends
        last_error: Optional[Exception] = None
        for backend in backends:
            try:
                return backend.load(key)
            except StorageError as exc:
                last_error = exc
        raise StorageError(f"All backends failed for load('{key}'): {last_error}")

    def exists(self, key: str) -> bool:
        for backend in self._backends:
            try:
                if backend.exists(key):
                    return True
            except StorageError:
                pass
        return False

    def delete(self, key: str) -> bool:
        existed = False
        for backend in self._backends:
            try:
                existed = backend.delete(key) or existed
            except StorageError as exc:
                logger.warning("MultiBackend: delete failed on %s: %s", backend.name, exc)
        return existed

    def list_keys(self, prefix: str = "") -> List[str]:
        all_keys: set = set()
        for backend in self._backends:
            try:
                all_keys.update(backend.list_keys(prefix))
            except StorageError as exc:
                logger.warning("MultiBackend: list_keys failed on %s: %s", backend.name, exc)
        return sorted(all_keys)

    def health_all(self) -> List[BackendHealth]:
        return [b.health() for b in self._backends]


# ---------------------------------------------------------------------------
# Distributed Alexandria Store
# ---------------------------------------------------------------------------

class DistributedAlexandriaStore:
    """
    Alexandria Store mit Distributed Backend.

    Serialisiert Patches und Nodes als JSON und speichert sie im Backend.

    Parameters
    ----------
    backend:
        DistributedBackend-Instanz.
    namespace:
        Prefix für alle Keys (z.B. ``"my_project/"``).
    """

    def __init__(self, backend: DistributedBackend, namespace: str = "") -> None:
        self._backend = backend
        self._ns = namespace

    def _key(self, kind: str, obj_id: str) -> str:
        return f"{self._ns}{kind}/{obj_id}"

    def save_patch(self, patch: Any) -> StoredObject:
        """Patch als JSON im Backend speichern."""
        key = self._key("patches", patch.patch_id)
        payload: Dict[str, Any] = {
            "patch_id": patch.patch_id,
            "parent_patch_id": patch.parent_patch_id,
            "branch_id": patch.branch_id,
            "timestamp": patch.timestamp,
            "operation": patch.operation,
            "target_id": patch.target_id,
            "category": patch.category,
            "payload": patch.payload,
            "audit": patch.audit,
            "uncertainty": patch.uncertainty,
        }
        data = json.dumps(payload, default=str).encode()
        return self._backend.save(key, data, {"type": "patch"})

    def load_patch_dict(self, patch_id: str) -> Dict[str, Any]:
        """Patch aus dem Backend laden (als Dict)."""
        key = self._key("patches", patch_id)
        obj = self._backend.load(key)
        return json.loads(obj.data.decode())

    def patch_exists(self, patch_id: str) -> bool:
        return self._backend.exists(self._key("patches", patch_id))

    def save_branch_manifest(self, branch_id: str, patch_ids: List[str]) -> StoredObject:
        """Branch-Manifest (geordnete Patch-ID-Liste) speichern."""
        key = self._key("branches", branch_id)
        data = json.dumps({"branch_id": branch_id, "patch_ids": patch_ids}).encode()
        return self._backend.save(key, data, {"type": "branch_manifest"})

    def load_branch_manifest(self, branch_id: str) -> List[str]:
        """Branch-Manifest laden; gibt patch_ids-Liste zurück."""
        key = self._key("branches", branch_id)
        obj = self._backend.load(key)
        return json.loads(obj.data.decode())["patch_ids"]

    def list_patches(self) -> List[str]:
        """Alle Patch-IDs im Backend auflisten."""
        prefix = f"{self._ns}patches/"
        keys = self._backend.list_keys(prefix)
        return [k[len(prefix):] for k in keys]

    def list_branches(self) -> List[str]:
        """Alle Branch-IDs im Backend auflisten."""
        prefix = f"{self._ns}branches/"
        keys = self._backend.list_keys(prefix)
        return [k[len(prefix):] for k in keys]

    def save_node_snapshot(self, branch_id: str, node_id: str, node_dict: Dict[str, Any]) -> StoredObject:
        """Node-Snapshot speichern (für Performance-Caching)."""
        key = self._key(f"snapshots/{branch_id}", node_id)
        data = json.dumps(node_dict, default=str).encode()
        return self._backend.save(key, data, {"type": "node_snapshot"})

    def load_node_snapshot(self, branch_id: str, node_id: str) -> Dict[str, Any]:
        """Node-Snapshot laden."""
        key = self._key(f"snapshots/{branch_id}", node_id)
        obj = self._backend.load(key)
        return json.loads(obj.data.decode())

    @property
    def backend(self) -> DistributedBackend:
        return self._backend

    def health(self) -> BackendHealth:
        return self._backend.health()
