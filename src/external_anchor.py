"""
External Trust Anchoring für Alexandria+MIVP.

Ersetzt die simulierten Implementierungen durch echte externe Services:

- SimulatedAnchor   Offline/Tests – bisheriges ExternalAnchor-Verhalten
- OpenTimestampsAnchor  Bitcoin-Timestamping via OpenTimestamps Calendar API
                        (kein Account, keine Gebühren, pure stdlib)
- WebhookAnchor     Konfigurierbarer HTTP-Webhook für eigene Services
- MultiAnchor       Kombiniert mehrere Dienste mit Fallback

Alle Klassen erfüllen das BaseExternalAnchor-Interface und sind damit als
drop-in-Ersatz für das originale ExternalAnchor in alexandria_mivp.py nutzbar.

Beispiel:
    from external_anchor import OpenTimestampsAnchor, MultiAnchor, SimulatedAnchor

    anchor = MultiAnchor([
        OpenTimestampsAnchor(),
        SimulatedAnchor(),     # Fallback bei Netzwerkfehler
    ])
    store = AlexandriaMIVPStore(identity, external_anchor=anchor)
    commit, proof = store.submit_with_identity_and_anchor(patch)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------

@dataclass
class AnchorProof:
    """Ergebnis eines Anchor-Aufrufs."""
    proof_id: str
    cih: str
    timestamp: int
    proof_type: str
    service: str                        # z.B. "opentimestamps", "webhook", "simulated"
    proof_data: Dict[str, Any] = field(default_factory=dict)
    verification_url: str = ""
    raw_bytes: Optional[bytes] = None   # z.B. binäres OTS-File

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "proof_id": self.proof_id,
            "cih": self.cih,
            "timestamp": self.timestamp,
            "proof_type": self.proof_type,
            "service": self.service,
            "proof_data": self.proof_data,
            "verification_url": self.verification_url,
        }
        if self.raw_bytes is not None:
            d["raw_bytes_b64"] = base64.b64encode(self.raw_bytes).decode()
        return d


class AnchorError(Exception):
    """Fehler beim Anchoring."""


# ---------------------------------------------------------------------------
# Abstrakte Basisklasse
# ---------------------------------------------------------------------------

class BaseExternalAnchor(ABC):
    """
    Gemeinsames Interface für alle External-Anchor-Implementierungen.

    Alle Unterklassen müssen anchor() und verify() implementieren.
    """

    @abstractmethod
    def anchor(self, cih_hex: str, proof_type: str = "transparency_log") -> Dict[str, Any]:
        """CIH bei einem externen Dienst registrieren. Gibt AnchorProof-Dict zurück."""

    @abstractmethod
    def verify(self, cih_hex: str, proof_id: str) -> bool:
        """Prüfen ob ein CIH unter der gegebenen proof_id verankert ist."""

    def find_proofs(self, cih_hex: str) -> List[Dict[str, Any]]:
        """Alle gespeicherten Proofs für einen CIH."""
        return []

    def get_global_consistency_proof(self, cih_hex: str) -> Optional[Dict[str, Any]]:
        """Kombinierten Konsistenz-Proof aller gespeicherten Proofs erzeugen."""
        proofs = self.find_proofs(cih_hex)
        if not proofs:
            return None
        return {
            "cih": cih_hex,
            "proof_count": len(proofs),
            "proof_types": [p.get("proof_type") for p in proofs],
            "earliest_timestamp": min(p.get("timestamp", 0) for p in proofs),
            "latest_timestamp": max(p.get("timestamp", 0) for p in proofs),
            "verification_summary": f"Verankert in {len(proofs)} Dienst(en)",
            "proofs": proofs,
        }

    @staticmethod
    def get_supported_proof_types() -> List[str]:
        return ["transparency_log", "witness_node", "timestamp_server", "blockchain"]


# ---------------------------------------------------------------------------
# 1. SimulatedAnchor – offline, vollständig deterministisch
# ---------------------------------------------------------------------------

class SimulatedAnchor(BaseExternalAnchor):
    """
    Vollständig simulierter Anchor für Tests und Offline-Betrieb.

    Verhält sich identisch zum bisherigen ExternalAnchor in alexandria_mivp.py,
    speichert aber nichts extern – nur im Arbeitsspeicher.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._counter = 1
        # Kurze Instanz-Kennung damit mehrere Instanzen nicht dieselben IDs erzeugen
        self._instance_tag = f"{id(self) & 0xFFFF:04x}"

    def anchor(self, cih_hex: str, proof_type: str = "transparency_log") -> Dict[str, Any]:
        proof_id = f"sim_{self._instance_tag}_{self._counter:06d}"
        self._counter += 1
        ts = int(time.time())

        if proof_type == "transparency_log":
            proof_data = {
                "log_id": "simulated-transparency-log-001",
                "tree_size": self._counter * 100,
                "leaf_index": self._counter,
                "audit_path": ["simulated_merkle_path"],
            }
            verification_url = f"https://transparency-log.example.com/entry/{proof_id}"
        elif proof_type == "witness_node":
            proof_data = {
                "witness_count": 3,
                "witness_ids": ["witness_01", "witness_02", "witness_03"],
                "signatures": ["sig1", "sig2", "sig3"],
            }
            verification_url = f"https://witness-network.example.com/proof/{proof_id}"
        elif proof_type == "timestamp_server":
            proof_data = {
                "tsa_id": "simulated-tsa-001",
                "timestamp_token": f"simulated_token_{ts}",
            }
            verification_url = f"https://timestamp.example.com/verify/{proof_id}"
        elif proof_type == "blockchain":
            proof_data = {
                "chain": "simulated_chain",
                "tx_hash": f"simulated_tx_{cih_hex[:16]}",
                "block_height": 1_000_000 + self._counter,
                "confirmations": 6,
            }
            verification_url = f"https://blockchain-explorer.example.com/tx/{proof_data['tx_hash']}"
        else:
            raise ValueError(f"Unbekannter proof_type: {proof_type}")

        record = {
            "proof_id": proof_id,
            "cih": cih_hex,
            "timestamp": ts,
            "proof_type": proof_type,
            "service": "simulated",
            "proof_data": proof_data,
            "verification_url": verification_url,
        }
        self._store[proof_id] = record
        return record

    def verify(self, cih_hex: str, proof_id: str) -> bool:
        record = self._store.get(proof_id)
        return record is not None and record["cih"] == cih_hex

    def find_proofs(self, cih_hex: str) -> List[Dict[str, Any]]:
        return [r for r in self._store.values() if r["cih"] == cih_hex]


# ---------------------------------------------------------------------------
# 2. OpenTimestampsAnchor – Bitcoin-Timestamping
# ---------------------------------------------------------------------------

class OpenTimestampsAnchor(BaseExternalAnchor):
    """
    Bitcoin-Timestamping via OpenTimestamps Calendar API.

    Kein Account, keine Gebühren. Nutzt ausschließlich Python-stdlib.

    Funktionsweise:
    - anchor(): POST des CIH-Hashes an einen OTS-Calendar-Server.
      Antwortet mit einem partiellen .ots-Proof (binary), der die Existenz
      des Hashes zum Einreichungszeitpunkt beweist.
      Nach einigen Stunden/Tagen wird der Proof gegen einen Bitcoin-Block geankert.
    - verify(): GET des gespeicherten Proof-Tokens vom Calendar-Server.
      Gibt True zurück wenn der Server den Hash kennt.

    Docs: https://opentimestamps.org
    """

    # Mehrere redundante Calendar-Server
    DEFAULT_CALENDARS = [
        "https://alice.btc.calendar.opentimestamps.org",
        "https://bob.btc.calendar.opentimestamps.org",
        "https://finney.calendar.eternitywall.com",
    ]

    def __init__(
        self,
        calendars: Optional[List[str]] = None,
        timeout: int = 15,
    ) -> None:
        self._calendars = calendars or self.DEFAULT_CALENDARS
        self._timeout = timeout
        self._store: Dict[str, Dict[str, Any]] = {}

    def anchor(self, cih_hex: str, proof_type: str = "blockchain") -> Dict[str, Any]:
        """CIH als SHA-256-Hash an OTS-Calendar posten."""
        try:
            hash_bytes = bytes.fromhex(cih_hex)
        except ValueError as exc:
            raise AnchorError(f"Ungültiger CIH-Hex-String: {cih_hex}") from exc

        last_error: Optional[Exception] = None
        for calendar_url in self._calendars:
            try:
                ots_data, used_url = self._post_to_calendar(hash_bytes, calendar_url)
                proof = self._build_proof(cih_hex, ots_data, used_url)
                self._store[proof["proof_id"]] = proof
                logger.info("OTS Anchor erfolgreich: %s → %s", cih_hex[:16], used_url)
                return proof
            except Exception as exc:
                logger.warning("OTS Calendar %s fehlgeschlagen: %s", calendar_url, exc)
                last_error = exc

        raise AnchorError(
            f"Alle OTS-Calendar-Server fehlgeschlagen. Letzter Fehler: {last_error}"
        )

    def verify(self, cih_hex: str, proof_id: str) -> bool:
        """Prüfen ob ein CIH im lokalen Store unter proof_id bekannt ist."""
        record = self._store.get(proof_id)
        if record is None:
            return False
        return record["cih"] == cih_hex

    def verify_against_calendar(self, cih_hex: str) -> bool:
        """
        CIH direkt beim Calendar-Server nachschlagen.
        Gibt True zurück wenn mindestens ein Calendar den Hash kennt.
        """
        try:
            hash_bytes = bytes.fromhex(cih_hex)
        except ValueError:
            return False

        for calendar_url in self._calendars:
            try:
                token_hex = cih_hex
                url = f"{calendar_url}/timestamp/{token_hex}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    if resp.status == 200:
                        logger.debug("OTS Calendar kennt Hash %s", cih_hex[:16])
                        return True
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                logger.debug("OTS verify HTTP %s: %s", exc.code, calendar_url)
            except Exception as exc:
                logger.debug("OTS verify Fehler (%s): %s", calendar_url, exc)

        return False

    def find_proofs(self, cih_hex: str) -> List[Dict[str, Any]]:
        return [r for r in self._store.values() if r["cih"] == cih_hex]

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------

    def _post_to_calendar(self, hash_bytes: bytes, calendar_url: str):
        url = f"{calendar_url}/digest"
        req = urllib.request.Request(
            url,
            data=hash_bytes,
            method="POST",
        )
        req.add_header("Content-Type", "application/octet-stream")
        req.add_header("Accept", "application/vnd.opentimestamps.v1")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            ots_data = resp.read()
        return ots_data, calendar_url

    def _build_proof(self, cih_hex: str, ots_data: bytes, calendar_url: str) -> Dict[str, Any]:
        proof_id = f"ots_{cih_hex[:16]}_{int(time.time())}"
        return {
            "proof_id": proof_id,
            "cih": cih_hex,
            "timestamp": int(time.time()),
            "proof_type": "blockchain",
            "service": "opentimestamps",
            "proof_data": {
                "calendar_url": calendar_url,
                "ots_size_bytes": len(ots_data),
                "hash_algorithm": "sha256",
                "status": "pending_bitcoin_confirmation",
            },
            "verification_url": f"{calendar_url}/timestamp/{cih_hex}",
            "raw_bytes_b64": base64.b64encode(ots_data).decode(),
        }

    @staticmethod
    def get_supported_proof_types() -> List[str]:
        return ["blockchain"]


# ---------------------------------------------------------------------------
# 3. WebhookAnchor – generischer HTTP-Webhook
# ---------------------------------------------------------------------------

class WebhookAnchor(BaseExternalAnchor):
    """
    Generischer HTTP-Webhook-Anchor für eigene Anchoring-Services.

    Sendet POST-Request an eine konfigurierbare URL mit:
        {"cih": "<hex>", "timestamp": <unix>, "proof_type": "<type>"}

    Erwartet JSON-Response mit mindestens {"proof_id": "..."}

    Beispiel (lokaler Test-Server):
        anchor = WebhookAnchor("https://my-anchor-service.example.com/anchor")
    """

    def __init__(
        self,
        url: str,
        verify_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        proof_type: str = "transparency_log",
    ) -> None:
        """
        Args:
            url: Endpoint für POST-Anfragen.
            verify_url: Optionaler GET-Endpoint für Verifikation (url + "/{proof_id}" wenn None).
            headers: Zusätzliche HTTP-Header (z.B. Authorization).
            timeout: Anfrage-Timeout in Sekunden.
            proof_type: Standard-proof_type für alle Anchors.
        """
        self._url = url
        self._verify_url = verify_url
        self._headers = headers or {}
        self._timeout = timeout
        self._default_proof_type = proof_type
        self._store: Dict[str, Dict[str, Any]] = {}

    def anchor(self, cih_hex: str, proof_type: str = "") -> Dict[str, Any]:
        effective_type = proof_type or self._default_proof_type
        payload = {
            "cih": cih_hex,
            "timestamp": int(time.time()),
            "proof_type": effective_type,
        }
        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(self._url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        for k, v in self._headers.items():
            req.add_header(k, v)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode() if exc.fp else ""
            raise AnchorError(
                f"Webhook HTTP {exc.code}: {body_text[:200]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise AnchorError(f"Webhook Netzwerkfehler: {exc.reason}") from exc

        proof_id = response_data.get("proof_id", f"wh_{cih_hex[:16]}_{int(time.time())}")
        record = {
            "proof_id": proof_id,
            "cih": cih_hex,
            "timestamp": int(time.time()),
            "proof_type": effective_type,
            "service": "webhook",
            "proof_data": response_data,
            "verification_url": (self._verify_url or self._url) + f"/{proof_id}",
        }
        self._store[proof_id] = record
        return record

    def verify(self, cih_hex: str, proof_id: str) -> bool:
        """Lokale Prüfung des Stores; für Remote-Prüfung verify_remote() nutzen."""
        record = self._store.get(proof_id)
        return record is not None and record["cih"] == cih_hex

    def verify_remote(self, proof_id: str) -> Optional[Dict[str, Any]]:
        """GET-Request zum Verify-Endpoint des Webhooks."""
        verify_base = self._verify_url or self._url
        url = f"{verify_base}/{proof_id}"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        for k, v in self._headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise AnchorError(f"Webhook verify HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise AnchorError(f"Webhook verify Netzwerkfehler: {exc.reason}") from exc

    def find_proofs(self, cih_hex: str) -> List[Dict[str, Any]]:
        return [r for r in self._store.values() if r["cih"] == cih_hex]


# ---------------------------------------------------------------------------
# 4. MultiAnchor – kombiniert mehrere Dienste mit Fallback
# ---------------------------------------------------------------------------

class MultiAnchor(BaseExternalAnchor):
    """
    Kombiniert mehrere Anchor-Dienste mit automatischem Fallback.

    Alle Dienste werden der Reihe nach versucht; der erste erfolgreiche
    Proof wird zurückgegeben. Optional kann auf Redundanz-Modus
    (alle Dienste versuchen) umgeschaltet werden.

    Beispiel:
        anchor = MultiAnchor([
            OpenTimestampsAnchor(),
            WebhookAnchor("https://my-service/anchor"),
            SimulatedAnchor(),
        ], mode="first_success")
    """

    MODE_FIRST_SUCCESS = "first_success"   # Erster erfolgreicher Proof reicht
    MODE_ALL = "all"                        # Alle Dienste werden versucht

    def __init__(
        self,
        anchors: List[BaseExternalAnchor],
        mode: str = MODE_FIRST_SUCCESS,
    ) -> None:
        if not anchors:
            raise ValueError("Mindestens ein Anchor-Dienst erforderlich.")
        self._anchors = anchors
        self._mode = mode
        self._store: Dict[str, Dict[str, Any]] = {}

    def anchor(self, cih_hex: str, proof_type: str = "transparency_log") -> Dict[str, Any]:
        errors = []
        results = []

        for anchor in self._anchors:
            try:
                proof = anchor.anchor(cih_hex, proof_type)
                results.append(proof)
                self._store[proof["proof_id"]] = proof
                if self._mode == self.MODE_FIRST_SUCCESS:
                    return proof
            except Exception as exc:
                logger.warning("Anchor %s fehlgeschlagen: %s", type(anchor).__name__, exc)
                errors.append(str(exc))

        if results:
            # Im ALL-Modus: zusammenfassenden Proof zurückgeben
            return {
                "proof_id": f"multi_{cih_hex[:16]}_{int(time.time())}",
                "cih": cih_hex,
                "timestamp": int(time.time()),
                "proof_type": proof_type,
                "service": "multi",
                "proof_data": {
                    "sub_proofs": results,
                    "successful_anchors": len(results),
                    "total_anchors": len(self._anchors),
                },
                "verification_url": "",
            }

        raise AnchorError(
            f"Alle {len(self._anchors)} Anchor-Dienste fehlgeschlagen: {'; '.join(errors)}"
        )

    def verify(self, cih_hex: str, proof_id: str) -> bool:
        # Lokaler Store
        if proof_id in self._store:
            return self._store[proof_id]["cih"] == cih_hex
        # Alle Sub-Anchor versuchen
        return any(a.verify(cih_hex, proof_id) for a in self._anchors)

    def find_proofs(self, cih_hex: str) -> List[Dict[str, Any]]:
        seen_ids = set()
        proofs = []
        for anchor in self._anchors:
            for proof in anchor.find_proofs(cih_hex):
                pid = proof.get("proof_id")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    proofs.append(proof)
        return proofs

    @staticmethod
    def get_supported_proof_types() -> List[str]:
        return BaseExternalAnchor.get_supported_proof_types()


# ---------------------------------------------------------------------------
# Rückwärtskompatibles Alias – ExternalAnchor bleibt nutzbar
# ---------------------------------------------------------------------------

ExternalAnchor = SimulatedAnchor
