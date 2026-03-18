"""
Message Router – Kommando-Dispatching für den Alexandria+MIVP Skill.

Parst eingehende Textnachrichten der Form "/alexandria <command> [args...]"
und leitet sie an registrierte Handler weiter.

Kann standalone oder als Basis für OpenClaw-Skills verwendet werden.

Beispiel:
    router = MessageRouter(store, identity)
    response = router.dispatch("/alexandria claim CO2 levels are rising --category EMPIRICAL")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .alexandria_v2 import Patch, CATEGORIES
from .alexandria_mivp import AlexandriaMIVPStore, AgentIdentity
from .heartbeat import run_heartbeat_check

logger = logging.getLogger(__name__)

# Typ für Handler-Funktionen
HandlerFn = Callable[[List[str]], str]


# ---------------------------------------------------------------------------
# Routing-Ergebnis
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    """Ergebnis eines Dispatch-Aufrufs."""
    success: bool
    command: str
    args: List[str]
    response: str
    latency_ms: float = 0.0
    error: str = ""

    def __str__(self) -> str:
        return self.response


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

@dataclass
class MiddlewareContext:
    """Kontextobjekt, das durch die Middleware-Kette gereicht wird."""
    command: str
    args: List[str]
    store: AlexandriaMIVPStore
    identity: AgentIdentity
    metadata: Dict[str, Any] = field(default_factory=dict)


MiddlewareFn = Callable[[MiddlewareContext, Callable[[], str]], str]


# ---------------------------------------------------------------------------
# Kern-Router
# ---------------------------------------------------------------------------

class MessageRouter:
    """
    Leichtgewichtiger Kommando-Router für Alexandria+MIVP.

    Registrierung eines Handlers:
        router.register("claim", my_claim_handler)

    Dispatching:
        result = router.dispatch("/alexandria claim Some text --category EMPIRICAL")

    Middleware (z.B. Logging, Auth):
        router.add_middleware(my_middleware)
    """

    PREFIX = "/alexandria"

    def __init__(self, store: AlexandriaMIVPStore, identity: AgentIdentity):
        self.store = store
        self.identity = identity
        self._handlers: Dict[str, HandlerFn] = {}
        self._middleware: List[MiddlewareFn] = []
        self._history: List[RouteResult] = []

        # Standard-Handler registrieren
        self._register_builtin_handlers()

    # ------------------------------------------------------------------
    # Registrierung
    # ------------------------------------------------------------------

    def register(self, command: str, handler: HandlerFn) -> None:
        """Einen Handler für ein Kommando registrieren."""
        self._handlers[command.lower()] = handler
        logger.debug("Handler registered for command '%s'", command)

    def unregister(self, command: str) -> bool:
        """Einen Handler entfernen. Gibt True zurück wenn er existierte."""
        return self._handlers.pop(command.lower(), None) is not None

    def add_middleware(self, fn: MiddlewareFn) -> None:
        """Middleware hinzufügen (wird vor dem Handler ausgeführt)."""
        self._middleware.append(fn)

    @property
    def commands(self) -> List[str]:
        """Alle registrierten Kommando-Namen."""
        return list(self._handlers.keys())

    @property
    def history(self) -> List[RouteResult]:
        """Verlauf der letzten Dispatch-Aufrufe (neueste zuletzt)."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Dispatching
    # ------------------------------------------------------------------

    def dispatch(self, message: str) -> RouteResult:
        """
        Nachricht parsen und an den passenden Handler weiterleiten.

        Akzeptierte Formate:
          /alexandria status
          /alexandria claim Some text --category EMPIRICAL
          status                       (ohne Präfix, wenn als direkte API genutzt)
        """
        t0 = time.monotonic()
        command, args = self._parse(message)

        if command is None:
            result = RouteResult(
                success=False,
                command="",
                args=[],
                response=self._unknown_response(message),
                error="parse_error",
            )
            self._history.append(result)
            return result

        handler = self._handlers.get(command)
        if handler is None:
            result = RouteResult(
                success=False,
                command=command,
                args=args,
                response=self._unknown_command_response(command),
                error="unknown_command",
            )
            self._history.append(result)
            return result

        # Middleware-Kette aufbauen
        ctx = MiddlewareContext(command=command, args=args, store=self.store, identity=self.identity)

        def invoke() -> str:
            return handler(args)

        try:
            response = self._run_through_middleware(ctx, invoke, self._middleware[:])
            success = True
            error = ""
        except Exception as exc:
            logger.error("Handler '%s' raised: %s", command, exc)
            response = f"Fehler beim Ausführen von '{command}': {exc}"
            success = False
            error = str(exc)

        latency_ms = (time.monotonic() - t0) * 1000
        result = RouteResult(
            success=success,
            command=command,
            args=args,
            response=response,
            latency_ms=latency_ms,
            error=error,
        )
        self._history.append(result)
        return result

    # ------------------------------------------------------------------
    # Eingebaute Kommando-Handler
    # ------------------------------------------------------------------

    def _register_builtin_handlers(self) -> None:
        self.register("status", self._handle_status)
        self.register("claim", self._handle_claim)
        self.register("verify", self._handle_verify)
        self.register("audit", self._handle_audit)
        self.register("heartbeat", self._handle_heartbeat)
        self.register("help", self._handle_help)

    def _handle_status(self, args: List[str]) -> str:
        nodes = self.store.reconstruct("main")
        cih = self.identity.compute_cih().hex()[:16]
        lines = [
            "## Alexandria+MIVP Status",
            f"**Agent**: {self.identity.name}",
            f"**CIH**: {cih}...",
            f"**Claims**: {len(nodes)}",
            f"**Branches**: {len(self.store.branches)}",
            f"**Zeitpunkt**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if nodes:
            lines.append("\n### Letzte Claims:")
            for nid, node in list(nodes.items())[-3:]:
                lines.append(f"- [{node.category}] {node.content[:60]}")
        return "\n".join(lines)

    def _handle_claim(self, args: List[str]) -> str:
        if not args:
            raise ValueError("Kein Text angegeben. Verwendung: claim <Text> [--category EMPIRICAL|NORMATIVE|MODEL|SPECULATIVE]")

        # Kategorie aus Argumenten extrahieren
        category = "EMPIRICAL"
        text_parts = []
        i = 0
        while i < len(args):
            if args[i] == "--category" and i + 1 < len(args):
                category = args[i + 1].upper()
                i += 2
            else:
                text_parts.append(args[i])
                i += 1

        text = " ".join(text_parts).strip()
        if not text:
            raise ValueError("Kein Text angegeben.")
        if category not in CATEGORIES:
            raise ValueError(f"Ungültige Kategorie: {category}. Erlaubt: {', '.join(sorted(CATEGORIES))}")

        ts = int(time.time())
        uid = abs(hash(text + str(ts)))
        patch = Patch(
            patch_id=f"router_{uid}",
            parent_patch_id=self.store.get_last_patch_id("main"),
            branch_id="main",
            timestamp=ts,
            operation="ADD",
            target_id=f"claim_{uid}",
            category=category,
            payload={"content": text, "assumptions": [], "source": "message_router"},
            audit={"validated": True, "decay": 0.01, "created_by": "router"},
            uncertainty={"sigma": 0.5, "ci": [0.8, 1.2], "n": 1},
        )
        commit_hash = self.store.submit_with_identity(patch)
        return (
            f"Claim erstellt!\n"
            f"**Kategorie**: {category}\n"
            f"**Inhalt**: {text[:100]}\n"
            f"**Hash**: {commit_hash[:16]}..."
        )

    def _handle_verify(self, args: List[str]) -> str:
        cih = self.identity.compute_cih()
        identity_dict = self.identity.get_identity_dict()

        try:
            from .alexandria_mivp import verify_cih_internal_consistency
        except ImportError:
            from alexandria_mivp import verify_cih_internal_consistency  # type: ignore[no-redef]

        ok = verify_cih_internal_consistency(identity_dict)
        nodes = self.store.reconstruct("main")
        lines = [
            "## Identitäts- und Integritätsprüfung",
            f"**Agent**: {self.identity.name}",
            f"**CIH**: {cih.hex()[:32]}...",
            f"**Intern konsistent**: {'✅' if ok else '❌'}",
            f"**Claims verifiziert**: {len(nodes)}",
        ]
        if not ok:
            lines.append("\n⚠️ Identitätsprüfung fehlgeschlagen – Konfiguration geändert?")
        return "\n".join(lines)

    def _handle_audit(self, args: List[str]) -> str:
        branch = args[0] if args else "main"
        nodes = self.store.reconstruct(branch)
        if not nodes:
            return f"Keine Claims in Branch '{branch}'."

        limit = 10
        lines = [f"## Audit Trail – Branch '{branch}'", ""]
        for nid, node in list(nodes.items())[-limit:]:
            lines.append(f"**[{node.category}]** {node.content[:80]}")
            lines.append(f"*Hash: {nid[:16]}...*")
            lines.append("")
        lines.append(f"Gesamt: {len(nodes)} Claims")
        return "\n".join(lines)

    def _handle_heartbeat(self, args: List[str]) -> str:
        result = run_heartbeat_check(self.store)
        return result if result else "Heartbeat: alles in Ordnung ✅"

    def _handle_help(self, args: List[str]) -> str:
        lines = [
            "## Alexandria+MIVP Kommandos",
            "",
            "| Kommando | Beschreibung |",
            "|---|---|",
            "| `status` | Store-Status anzeigen |",
            "| `claim <Text> [--category X]` | Neuen Claim erstellen |",
            "| `verify` | Identität und Integrität prüfen |",
            "| `audit [branch]` | Audit-Trail anzeigen |",
            "| `heartbeat` | Manuellen Heartbeat-Check auslösen |",
            "| `help` | Diese Hilfe anzeigen |",
        ]
        custom = [c for c in self.commands if c not in {"status", "claim", "verify", "audit", "heartbeat", "help"}]
        if custom:
            lines.append("")
            lines.append("**Benutzerdefinierte Kommandos:** " + ", ".join(f"`{c}`" for c in sorted(custom)))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _parse(self, message: str):
        """Nachricht in (command, args) zerlegen. Gibt (None, []) bei Fehler."""
        text = message.strip()
        if text.lower().startswith(self.PREFIX):
            text = text[len(self.PREFIX):].strip()

        if not text:
            return None, []

        parts = text.split()
        return parts[0].lower(), parts[1:]

    def _unknown_response(self, message: str) -> str:
        return f"Konnte Nachricht nicht verarbeiten: '{message[:80]}'. Verwende `/alexandria help`."

    def _unknown_command_response(self, command: str) -> str:
        similar = [c for c in self.commands if command[:3] in c]
        hint = f" Meintest du: {', '.join(similar)}?" if similar else ""
        return f"Unbekanntes Kommando: '{command}'.{hint} Verwende `help` für eine Übersicht."

    def _run_through_middleware(
        self, ctx: MiddlewareContext, invoke: Callable[[], str], remaining: List[MiddlewareFn]
    ) -> str:
        if not remaining:
            return invoke()
        mw = remaining[0]
        rest = remaining[1:]
        return mw(ctx, lambda: self._run_through_middleware(ctx, invoke, rest))
