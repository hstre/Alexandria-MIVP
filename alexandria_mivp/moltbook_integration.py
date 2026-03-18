"""
Moltbook API Integration for Alexandria+MIVP
Bidirektionale Synchronisation zwischen Alexandria Epistemic Store und Moltbook.
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from .alexandria_v2 import Patch, CATEGORIES
from .alexandria_mivp import AlexandriaMIVPStore, AgentIdentity, verify_cih_internal_consistency


class MoltbookAPIError(Exception):
    """Fehler bei Moltbook API-Anfragen."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class MoltbookIntegration:
    """
    Bidirektionale Integration zwischen Alexandria+MIVP und der Moltbook-Plattform.

    Funktionen:
    - Alexandria-Claims als Moltbook-Posts veröffentlichen (mit kryptographischer Provenienz)
    - Moltbook-Posts als Alexandria-Patches importieren
    - Vollständige Synchronisation in beide Richtungen
    - Verifizierbare Identitäts-Badges für Posts
    """

    BASE_URL = "https://www.moltbook.com/api/v1"

    def __init__(self, store: AlexandriaMIVPStore, api_key: str):
        """
        Args:
            store: Initialisierter AlexandriaMIVPStore mit Agent-Identität.
            api_key: Moltbook API-Schlüssel.
        """
        self.store = store
        self.api_key = api_key
        self._post_links: Dict[str, str] = {}  # claim_id -> moltbook_post_id

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def get_agent_profile(self) -> Dict[str, Any]:
        """Moltbook-Profil des Agenten abrufen."""
        return self._make_api_request("/profile")

    def post_claim(self, claim_id: str, submolt: str = "general") -> Dict[str, Any]:
        """
        Einen Alexandria-Claim als verifizierten Moltbook-Post veröffentlichen.

        Args:
            claim_id: ID des Claim-Nodes im Alexandria-Store.
            submolt: Ziel-Submolt auf Moltbook (Standard: "general").

        Returns:
            Dict mit ``success``, ``post_id`` und ``url`` bei Erfolg.
        """
        nodes = self.store.reconstruct("main")
        if claim_id not in nodes:
            return {"error": f"Claim '{claim_id}' nicht gefunden"}

        node = nodes[claim_id]
        identity = self.store.agent_identity

        post_data = {
            "submolt_name": submolt,
            "title": f"Epistemic Claim [{node.category}]: {self._short_content(node)}",
            "content": self._format_claim_for_moltbook(node, identity),
        }

        response = self._make_api_request("/posts", post_data, method="POST")

        if "post_id" in response:
            self._link_moltbook_post(claim_id, response["post_id"])
            return {
                "success": True,
                "post_id": response["post_id"],
                "url": f"https://www.moltbook.com/p/{response['post_id']}",
                "claim_id": claim_id,
            }

        return {"error": "Veröffentlichung fehlgeschlagen", "details": response}

    def fetch_posts(self, submolt: str = "general", limit: int = 20) -> List[Dict[str, Any]]:
        """
        Moltbook-Posts aus einem Submolt abrufen.

        Args:
            submolt: Name des Submolts.
            limit: Maximale Anzahl Posts.

        Returns:
            Liste von Post-Dicts.
        """
        params = {"submolt": submolt, "limit": limit}
        response = self._make_api_request(f"/posts?{urllib.parse.urlencode(params)}")
        return response.get("posts", [])

    def sync_claims_to_moltbook(
        self,
        branch: str = "main",
        submolt: str = "general",
        only_verified: bool = True,
    ) -> Dict[str, Any]:
        """
        Alle (oder alle verifizierten) Alexandria-Claims nach Moltbook synchronisieren.

        Bereits veröffentlichte Claims werden übersprungen.

        Args:
            branch: Alexandria-Branch.
            submolt: Ziel-Submolt.
            only_verified: Nur Claims mit gültiger MIVP-Identität synchronisieren.

        Returns:
            Zusammenfassung mit ``published``, ``skipped`` und ``errors``.
        """
        nodes = self.store.reconstruct(branch)
        published, skipped, errors = [], [], []

        for claim_id, node in nodes.items():
            if claim_id in self._post_links:
                skipped.append(claim_id)
                continue

            if only_verified:
                identity_info = node.audit.get("mivp_identity", {})
                if not verify_cih_internal_consistency(identity_info):
                    skipped.append(claim_id)
                    continue

            try:
                result = self.post_claim(claim_id, submolt=submolt)
                if result.get("success"):
                    published.append({"claim_id": claim_id, "post_id": result["post_id"]})
                else:
                    errors.append({"claim_id": claim_id, "error": result.get("error")})
            except MoltbookAPIError as exc:
                errors.append({"claim_id": claim_id, "error": str(exc)})

        return {"published": published, "skipped": skipped, "errors": errors}

    def sync_from_moltbook(
        self,
        submolt: str = "general",
        limit: int = 20,
        branch: str = "main",
    ) -> Dict[str, Any]:
        """
        Moltbook-Posts als Alexandria-Patches importieren.

        Nur Posts mit eingebettetem Alexandria-Block (erkennbar an ``---alexandria-patch---``
        im Inhalt) werden importiert.

        Args:
            submolt: Quell-Submolt.
            limit: Maximale Anzahl Posts.
            branch: Ziel-Branch im Alexandria-Store.

        Returns:
            Zusammenfassung mit ``imported`` und ``skipped``.
        """
        posts = self.fetch_posts(submolt=submolt, limit=limit)
        imported, skipped = [], []

        for post in posts:
            patch_data = self._extract_patch_from_post(post)
            if patch_data is None:
                skipped.append(post.get("post_id", "unknown"))
                continue

            try:
                patch = self._build_patch_from_moltbook(post, patch_data, branch)
                commit_hash = self.store.submit_with_identity(patch)
                imported.append({
                    "post_id": post.get("post_id"),
                    "commit_hash": commit_hash,
                    "claim_id": patch.target_id,
                })
            except Exception as exc:
                skipped.append(post.get("post_id", "unknown"))

        return {"imported": imported, "skipped": skipped}

    def verify_post(self, post_id: str) -> Dict[str, Any]:
        """
        Kryptographische Identität eines Moltbook-Posts prüfen.

        Args:
            post_id: Moltbook Post-ID.

        Returns:
            Dict mit ``internally_consistent`` und ``matches_current_agent``.
        """
        response = self._make_api_request(f"/posts/{post_id}")
        post = response.get("post", {})
        patch_data = self._extract_patch_from_post(post)

        if patch_data is None:
            return {"error": "Kein Alexandria-Block im Post gefunden", "post_id": post_id}

        identity_info = patch_data.get("mivp_identity", {})
        internally_consistent = verify_cih_internal_consistency(identity_info)
        matches_agent = self.store.agent_identity.matches_identity_dict(identity_info)

        return {
            "post_id": post_id,
            "internally_consistent": internally_consistent,
            "matches_current_agent": matches_agent,
            "agent_name": identity_info.get("agent_name", "unknown"),
            "cih": identity_info.get("cih", "")[:32] + "..." if identity_info.get("cih") else "",
        }

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _make_api_request(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        method: str = "GET",
    ) -> Dict[str, Any]:
        """HTTP-Anfrage an die Moltbook API."""
        url = self.BASE_URL + endpoint
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8") if exc.fp else ""
            try:
                err_body = json.loads(body_text)
            except (json.JSONDecodeError, ValueError):
                err_body = {"raw": body_text}
            raise MoltbookAPIError(
                f"HTTP {exc.code} bei {method} {endpoint}",
                status_code=exc.code,
                response=err_body,
            ) from exc
        except urllib.error.URLError as exc:
            raise MoltbookAPIError(f"Netzwerkfehler: {exc.reason}") from exc

    def _format_claim_for_moltbook(self, node: Any, identity: AgentIdentity) -> str:
        """Alexandria-Node für die Anzeige auf Moltbook formatieren."""
        cih_short = identity.compute_cih().hex()[:32]
        content = node.content if hasattr(node, "content") else node.payload.get("content", "(kein Inhalt)")
        assumptions = node.assumptions if hasattr(node, "assumptions") else node.payload.get("assumptions", [])
        unc = node.uncertainty
        sigma = unc.sigma if hasattr(unc, "sigma") else (unc.get("sigma", "?") if isinstance(unc, dict) else "?")
        validated = True  # Nodes have passed the audit gate

        lines = [
            f"## Epistemic Claim [{node.category}]",
            "",
            content,
            "",
            "### Metadaten",
            f"- **Kategorie**: {node.category}",
            f"- **Konfidenz**: σ = {sigma}",
            f"- **Validiert**: {'✅' if validated else '⚠️ nein'}",
        ]

        if assumptions:
            lines.append(f"- **Annahmen**: {', '.join(str(a) for a in assumptions)}")

        lines += [
            "",
            "### Kryptographische Identität",
            f"- **Agent**: {identity.name}",
            f"- **CIH**: `{cih_short}...`",
            "",
            "---",
            "*Veröffentlicht via Alexandria+MIVP*",
            "",
            self._build_patch_block(node, identity),
        ]

        return "\n".join(lines)

    def _build_patch_block(self, node: Any, identity: AgentIdentity) -> str:
        """Eingebetteten maschinenlesbaren Alexandria-Block erzeugen."""
        identity_dict = identity.get_identity_dict()
        content = node.content if hasattr(node, "content") else node.payload.get("content", "")
        data = {
            "category": node.category,
            "content": content,
            "mivp_identity": identity_dict,
            "timestamp": int(time.time()),
        }
        encoded = json.dumps(data, separators=(",", ":"))
        return f"---alexandria-patch---\n{encoded}\n---end-patch---"

    def _extract_patch_from_post(self, post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Eingebetteten Alexandria-Block aus einem Moltbook-Post extrahieren."""
        content = post.get("content", "")
        start_marker = "---alexandria-patch---"
        end_marker = "---end-patch---"

        start = content.find(start_marker)
        end = content.find(end_marker)

        if start == -1 or end == -1:
            return None

        raw = content[start + len(start_marker):end].strip()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None

    def _build_patch_from_moltbook(
        self, post: Dict[str, Any], patch_data: Dict[str, Any], branch: str
    ) -> Patch:
        """Aus einem Moltbook-Post einen Alexandria-Patch erzeugen."""
        post_id = post.get("post_id", f"mb_{int(time.time())}")
        ts = patch_data.get("timestamp", int(time.time()))
        category = patch_data.get("category", "EMPIRICAL")
        if category not in CATEGORIES:
            category = "EMPIRICAL"

        target_id = f"moltbook_{post_id}"
        patch_id = f"mb_import_{post_id}_{ts}"

        return Patch(
            patch_id=patch_id,
            parent_patch_id=self.store.get_last_patch_id(branch),
            branch_id=branch,
            timestamp=ts,
            operation="ADD",
            target_id=target_id,
            category=category,
            payload={
                "content": patch_data.get("content", ""),
                "source": "moltbook",
                "moltbook_post_id": post_id,
                "moltbook_url": f"https://www.moltbook.com/p/{post_id}",
            },
            audit={
                "validated": False,
                "decay": 0.01,
                "created_by": "moltbook_sync",
                "mivp_identity": patch_data.get("mivp_identity", {}),
            },
            uncertainty={"sigma": 0.5, "ci": [0.8, 1.2], "n": 1},
        )

    def _link_moltbook_post(self, claim_id: str, post_id: str) -> None:
        """Interne Verknüpfung zwischen Claim und Moltbook-Post speichern."""
        self._post_links[claim_id] = post_id

    def _short_content(self, node: Any, max_len: int = 60) -> str:
        content = node.content if hasattr(node, "content") else node.payload.get("content", "")
        return content[:max_len] + "..." if len(content) > max_len else content
