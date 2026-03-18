"""
Epistemic Heartbeat – periodische Integritäts- und Konsistenzprüfung.

Kann eigenständig (threading) oder als OpenClaw-Skill-Heartbeat verwendet werden.

Prüft bei jedem Durchlauf:
  1. MIVP-Identitäts-Konsistenz  (hat sich das Agenten-Profil verändert?)
  2. Audit-Trail-Integrität       (Timestamps monoton steigend, Hash-Chain intakt)
  3. Kategorien-Verteilung        (ungewöhnliche Häufungen)
  4. Veraltete Claims             (Stability unterhalb Schwellwert)
  5. Widersprüche                 (semantisch ähnliche Claims in derselben Kategorie)

Ergebnis wird als HeartbeatReport-Objekt zurückgegeben und optional in einer
JSON-Datei persistiert.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    from .alexandria_v2 import AlexandriaStore, Node
    from .alexandria_mivp import AlexandriaMIVPStore, verify_cih_internal_consistency
except ImportError:
    from alexandria_v2 import AlexandriaStore, Node  # type: ignore[no-redef]
    from alexandria_mivp import AlexandriaMIVPStore, verify_cih_internal_consistency  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------

@dataclass
class IdentityCheckResult:
    ok: bool
    cih_hex: str
    changed: bool          # True wenn CIH sich seit letztem Lauf verändert hat
    details: str = ""


@dataclass
class AuditTrailCheckResult:
    ok: bool
    total_nodes: int
    timestamp_monotone: bool
    hash_chain_intact: bool
    details: str = ""


@dataclass
class StaleClaimsResult:
    stale_count: int
    threshold: float
    stale_ids: List[str] = field(default_factory=list)


@dataclass
class ContradictionResult:
    count: int
    pairs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CategoryDistribution:
    counts: Dict[str, int] = field(default_factory=dict)
    dominant_category: str = ""
    imbalance_flag: bool = False   # True wenn eine Kategorie >80 % aller Nodes ausmacht


@dataclass
class HeartbeatReport:
    timestamp: float
    timestamp_iso: str
    branch: str
    identity: IdentityCheckResult
    audit_trail: AuditTrailCheckResult
    stale_claims: StaleClaimsResult
    contradictions: ContradictionResult
    category_distribution: CategoryDistribution
    alert: bool                      # True wenn irgendetwas fehlerhaft ist
    alert_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        """Menschenlesbare Zusammenfassung."""
        lines = [
            f"=== Epistemic Heartbeat [{self.timestamp_iso}] ===",
            f"Branch: {self.branch}",
            f"Identity OK: {'✅' if self.identity.ok else '❌'}",
            f"  CIH: {self.identity.cih_hex[:32]}...",
            f"  Changed since last run: {'yes' if self.identity.changed else 'no'}",
            f"Audit Trail OK: {'✅' if self.audit_trail.ok else '❌'}",
            f"  Nodes: {self.audit_trail.total_nodes}",
            f"  Timestamps monotone: {'✅' if self.audit_trail.timestamp_monotone else '❌'}",
            f"  Hash chain intact: {'✅' if self.audit_trail.hash_chain_intact else '❌'}",
            f"Stale Claims: {self.stale_claims.stale_count} (threshold σ>{self.stale_claims.threshold})",
            f"Contradictions: {self.contradictions.count}",
            f"Category distribution: {self.category_distribution.counts}",
        ]
        if self.alert:
            lines.append("")
            lines.append(f"⚠️  ALERT: {self.alert_message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Kernklasse
# ---------------------------------------------------------------------------

class EpistemicHeartbeat:
    """
    Periodische Prüfung eines AlexandriaMIVPStore auf Integrität und Konsistenz.

    Verwendung (standalone):
        hb = EpistemicHeartbeat(store, interval_seconds=1800)
        hb.start()           # startet Background-Thread
        ...
        report = hb.last_report
        hb.stop()

    Verwendung (einmalig / in OpenClaw):
        hb = EpistemicHeartbeat(store)
        report = hb.run_once()
    """

    def __init__(
        self,
        store: AlexandriaMIVPStore,
        branch: str = "main",
        interval_seconds: int = 1800,
        stability_threshold: float = 0.2,
        state_path: Optional[str] = None,
        on_alert: Optional[Callable[[HeartbeatReport], None]] = None,
    ):
        """
        Args:
            store: Initialisierter AlexandriaMIVPStore.
            branch: Zu prüfender Branch.
            interval_seconds: Pause zwischen zwei Läufen (Standard: 30 Minuten).
            stability_threshold: Nodes mit stability < Schwellwert gelten als veraltet.
            state_path: JSON-Datei zum Persistieren von Zustand und History.
            on_alert: Callback, der bei Alerts aufgerufen wird.
        """
        self.store = store
        self.branch = branch
        self.interval_seconds = interval_seconds
        self.stability_threshold = stability_threshold
        self.state_path = state_path
        self.on_alert = on_alert

        self._last_cih: Optional[str] = None
        self._last_report: Optional[HeartbeatReport] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        if state_path:
            self._load_state()

    # ------------------------------------------------------------------
    # Öffentliche Schnittstelle
    # ------------------------------------------------------------------

    @property
    def last_report(self) -> Optional[HeartbeatReport]:
        return self._last_report

    def run_once(self, branch: Optional[str] = None) -> HeartbeatReport:
        """Einen einzelnen Heartbeat-Lauf durchführen und den Report zurückgeben."""
        branch = branch or self.branch
        report = self._check(branch)
        self._last_report = report

        if report.alert and self.on_alert:
            try:
                self.on_alert(report)
            except Exception as exc:
                logger.error("on_alert callback failed: %s", exc)

        if self.state_path:
            self._save_state(report)

        return report

    def start(self) -> None:
        """Background-Thread starten (nicht-blockierend)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="EpistemicHeartbeat", daemon=True
        )
        self._thread.start()
        logger.info("EpistemicHeartbeat started (interval=%ds)", self.interval_seconds)

    def stop(self) -> None:
        """Background-Thread stoppen."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("EpistemicHeartbeat stopped")

    # ------------------------------------------------------------------
    # Interne Prüfroutinen
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.error("Heartbeat loop error: %s", exc)
            self._stop_event.wait(self.interval_seconds)

    def _check(self, branch: str) -> HeartbeatReport:
        now = time.time()
        nodes: Dict[str, Node] = self.store.reconstruct(branch)

        identity_result = self._check_identity()
        audit_result = self._check_audit_trail(nodes)
        stale_result = self._check_stale_claims(nodes)
        contradiction_result = self._check_contradictions(nodes)
        category_result = self._check_category_distribution(nodes)

        alert = (
            not identity_result.ok
            or not audit_result.ok
            or contradiction_result.count > 0
            or category_result.imbalance_flag
        )

        alert_parts = []
        if not identity_result.ok:
            alert_parts.append("Identity verification failed")
        if identity_result.changed:
            alert_parts.append("Agent CIH changed since last run")
        if not audit_result.timestamp_monotone:
            alert_parts.append("Timestamp ordering violated")
        if not audit_result.hash_chain_intact:
            alert_parts.append("Hash chain integrity broken")
        if contradiction_result.count > 0:
            alert_parts.append(f"{contradiction_result.count} potential contradiction(s) detected")
        if category_result.imbalance_flag:
            alert_parts.append(f"Category imbalance: '{category_result.dominant_category}' dominates")

        return HeartbeatReport(
            timestamp=now,
            timestamp_iso=datetime.utcfromtimestamp(now).strftime("%Y-%m-%dT%H:%M:%SZ"),
            branch=branch,
            identity=identity_result,
            audit_trail=audit_result,
            stale_claims=stale_result,
            contradictions=contradiction_result,
            category_distribution=category_result,
            alert=alert,
            alert_message="; ".join(alert_parts),
        )

    def _check_identity(self) -> IdentityCheckResult:
        """MIVP-Identität des Agenten prüfen."""
        try:
            cih = self.store.agent_identity.compute_cih()
            cih_hex = cih.hex()

            # Identität intern konsistent?
            identity_dict = self.store.agent_identity.get_identity_dict()
            internally_ok = verify_cih_internal_consistency(identity_dict)

            # Hat sich der CIH seit dem letzten Lauf verändert?
            changed = self._last_cih is not None and self._last_cih != cih_hex
            self._last_cih = cih_hex

            return IdentityCheckResult(
                ok=internally_ok,
                cih_hex=cih_hex,
                changed=changed,
                details="" if internally_ok else "CIH recomputation mismatch",
            )
        except Exception as exc:
            return IdentityCheckResult(
                ok=False, cih_hex="", changed=False, details=str(exc)
            )

    def _check_audit_trail(self, nodes: Dict[str, Node]) -> AuditTrailCheckResult:
        """Audit-Trail auf Timestamp-Monotonie und Hash-Chain-Integrität prüfen."""
        if not nodes:
            return AuditTrailCheckResult(
                ok=True, total_nodes=0, timestamp_monotone=True, hash_chain_intact=True
            )

        # Nodes nach lineage-Reihenfolge sortieren (anhand der Patch-Kette im Store)
        branch_patches = self.store.branches.get(self.branch, [])
        timestamps = [p.timestamp for p in branch_patches]
        timestamp_monotone = all(
            timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1)
        )

        # Hash-Chain: jeder Patch außer dem ersten muss einen bekannten parent haben
        patch_ids = {p.patch_id for p in branch_patches}
        hash_chain_intact = True
        for patch in branch_patches:
            if patch.parent_patch_id and patch.parent_patch_id not in patch_ids:
                hash_chain_intact = False
                break

        ok = timestamp_monotone and hash_chain_intact

        details_parts = []
        if not timestamp_monotone:
            details_parts.append("Non-monotone timestamps detected")
        if not hash_chain_intact:
            details_parts.append("Broken parent reference in patch chain")

        return AuditTrailCheckResult(
            ok=ok,
            total_nodes=len(nodes),
            timestamp_monotone=timestamp_monotone,
            hash_chain_intact=hash_chain_intact,
            details="; ".join(details_parts),
        )

    def _check_stale_claims(self, nodes: Dict[str, Node]) -> StaleClaimsResult:
        """Claims mit zu niedriger Stability identifizieren."""
        stale_ids = [
            nid
            for nid, node in nodes.items()
            if not node.deprecated and node.stability < self.stability_threshold
        ]
        return StaleClaimsResult(
            stale_count=len(stale_ids),
            threshold=self.stability_threshold,
            stale_ids=stale_ids,
        )

    def _check_contradictions(self, nodes: Dict[str, Node]) -> ContradictionResult:
        """
        Heuristik zur Widerspruchserkennung.

        Zwei Nodes gelten als potenzielle Widersprüche, wenn:
        - Sie dieselbe Kategorie haben,
        - Keiner der beiden deprecated ist,
        - Ihre Nicht-Stoppwort-Mengen zu ≥ 50 % überlappen (Jaccard-ähnlich), und
        - Genau einer der beiden einen Negationsterm enthält.
        """
        NEGATIONS = {"not", "kein", "keine", "nein", "no", "never", "nie", "falsch", "false"}
        STOPWORDS = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "in", "on", "at", "to", "for", "of", "and", "or", "but", "with",
            "it", "its", "this", "that", "these", "those", "by", "from",
            "der", "die", "das", "ein", "eine", "ist", "sind", "war", "ich",
        }
        pairs: List[Dict[str, Any]] = []

        active_nodes = {nid: n for nid, n in nodes.items() if not n.deprecated}
        node_list = list(active_nodes.items())

        def keywords(text: str) -> set:
            return {w for w in text.lower().split() if w not in STOPWORDS and len(w) > 2}

        for i in range(len(node_list)):
            nid_a, node_a = node_list[i]
            kw_a = keywords(node_a.content)
            all_a = set(node_a.content.lower().split())

            for j in range(i + 1, len(node_list)):
                nid_b, node_b = node_list[j]

                if node_a.category != node_b.category:
                    continue

                kw_b = keywords(node_b.content)
                all_b = set(node_b.content.lower().split())

                # Schlüsselwort-Überlappung: mindestens 50 % der kleineren Menge
                overlap = kw_a & kw_b
                min_kw = min(len(kw_a), len(kw_b))
                if min_kw == 0 or len(overlap) / min_kw < 0.5:
                    continue

                a_negated = bool(all_a & NEGATIONS)
                b_negated = bool(all_b & NEGATIONS)

                if a_negated != b_negated:
                    pairs.append({
                        "node_a": nid_a,
                        "content_a": node_a.content[:80],
                        "node_b": nid_b,
                        "content_b": node_b.content[:80],
                        "category": node_a.category,
                    })

        return ContradictionResult(count=len(pairs), pairs=pairs)

    def _check_category_distribution(self, nodes: Dict[str, Node]) -> CategoryDistribution:
        """Kategorien-Verteilung berechnen und auf Ungleichgewicht prüfen."""
        counts: Dict[str, int] = {}
        for node in nodes.values():
            counts[node.category] = counts.get(node.category, 0) + 1

        total = sum(counts.values())
        dominant = max(counts, key=counts.get) if counts else ""
        imbalance = total > 0 and counts.get(dominant, 0) / total > 0.8

        return CategoryDistribution(
            counts=counts,
            dominant_category=dominant,
            imbalance_flag=imbalance,
        )

    # ------------------------------------------------------------------
    # Zustands-Persistenz
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Gespeicherten Zustand (letzter CIH) aus JSON-Datei laden."""
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                state = json.load(fh)
            self._last_cih = state.get("last_cih")
            logger.debug("Heartbeat state loaded from %s", self.state_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Could not load heartbeat state: %s", exc)

    def _save_state(self, report: HeartbeatReport) -> None:
        """Zustand und letzten Report in JSON-Datei schreiben."""
        state = {
            "last_cih": self._last_cih,
            "last_run": report.timestamp_iso,
            "last_alert": report.alert,
            "last_report": report.to_dict(),
        }
        try:
            with open(self.state_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
        except Exception as exc:
            logger.warning("Could not save heartbeat state: %s", exc)


# ---------------------------------------------------------------------------
# Convenience-Funktion für OpenClaw-Integration
# ---------------------------------------------------------------------------

def run_heartbeat_check(
    store: AlexandriaMIVPStore,
    branch: str = "main",
    stability_threshold: float = 0.2,
) -> Optional[str]:
    """
    Einmaliger Heartbeat-Check – gibt eine Alert-Nachricht zurück oder None.

    Gedacht für den Einsatz als OpenClaw @heartbeat-Funktion:

        @heartbeat(interval_minutes=30)
        def epistemic_heartbeat(self):
            return run_heartbeat_check(self.store)
    """
    hb = EpistemicHeartbeat(
        store=store,
        branch=branch,
        stability_threshold=stability_threshold,
    )
    report = hb.run_once()

    if report.alert:
        return (
            "## Epistemic Heartbeat Alert\n\n"
            + report.alert_message
            + "\n\nDetails:\n"
            + report.summary()
        )
    return None
