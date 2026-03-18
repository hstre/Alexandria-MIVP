"""
Extended Audit Gate for Alexandria Protocol.

Adds three additional validation layers on top of the structural checks
already performed by ``audit_patch()``:

1. **Semantic Validation** – content quality, category-appropriate fields,
   repetition, obvious placeholder detection.
2. **Source Verification** – presence and basic well-formedness of citations
   for empirical claims; structured-reference format checks.
3. **Temporal Reasoning** – anachronism detection, timestamp plausibility,
   in-content date consistency.

All three layers are composable: each can be enabled/disabled independently
via ``AuditGateConfig``.  Results are returned as ``AuditReport`` objects
rather than exceptions, which lets callers distinguish *warnings* from hard
*violations* and decide their own policy.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum

from .alexandria_v2 import Patch, CATEGORIES, AuditError


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "error"     # Hard violation – patch should be rejected
    WARNING = "warning" # Soft issue – patch can be accepted but flagged


@dataclass
class AuditViolation:
    code: str
    message: str
    severity: Severity
    field: Optional[str] = None  # e.g. "payload.content", "payload.sources"


@dataclass
class AuditReport:
    """Result of running the extended audit gate on a single patch."""
    patch_id: str
    passed: bool                             # True ↔ no ERROR violations
    violations: List[AuditViolation] = field(default_factory=list)

    def errors(self) -> List[AuditViolation]:
        return [v for v in self.violations if v.severity == Severity.ERROR]

    def warnings(self) -> List[AuditViolation]:
        return [v for v in self.violations if v.severity == Severity.WARNING]

    def raise_if_failed(self) -> None:
        """Raise AuditError if any ERROR violations are present."""
        errs = self.errors()
        if errs:
            messages = "; ".join(e.message for e in errs)
            raise AuditError(f"Audit gate failed for {self.patch_id}: {messages}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class AuditGateConfig:
    """Tunable parameters for the extended audit gate.

    All boolean ``enable_*`` flags default to True so that the gate is as
    strict as possible by default.  Individual checks can be relaxed per
    deployment.
    """

    # ---- Semantic validation ----
    enable_semantic: bool = True
    min_content_length: int = 10
    max_content_length: int = 50_000
    max_assumption_count: int = 50
    placeholder_patterns: List[str] = field(default_factory=lambda: [
        r"^\s*test\s*$", r"^\s*placeholder\s*$", r"^\s*todo\s*$",
        r"^\s*lorem ipsum\b", r"^\s*foo\s*$", r"^\s*bar\s*$",
        r"^\s*xxx+\s*$",
    ])
    max_repetition_ratio: float = 0.6   # max fraction of duplicate sentences
    require_uncertainty_for: Set[str] = field(
        default_factory=lambda: {"EMPIRICAL"}
    )
    require_assumptions_for: Set[str] = field(
        default_factory=lambda: set()   # optional by default
    )

    # ---- Source verification ----
    enable_source_verification: bool = True
    require_sources_for: Set[str] = field(
        default_factory=lambda: set()   # warn (not error) if missing for EMPIRICAL
    )
    warn_missing_sources_for: Set[str] = field(
        default_factory=lambda: {"EMPIRICAL"}
    )
    valid_source_schemes: Set[str] = field(
        default_factory=lambda: {"http", "https", "doi", "isbn", "arxiv", "urn"}
    )
    max_sources: int = 100

    # ---- Temporal reasoning ----
    enable_temporal: bool = True
    max_future_drift_seconds: int = 300     # allow up to 5 min clock skew
    min_timestamp: int = 1_000_000_000      # ~2001-09-09 (pre-this is suspicious)
    max_timestamp_year: int = 2100
    flag_anachronistic_year_mentions: bool = True
    temporal_scope_field: str = "temporal_scope"  # optional payload key


# ---------------------------------------------------------------------------
# Semantic Validation
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|2[0-9]{3})\b")


def _check_semantic(patch: Patch, cfg: AuditGateConfig) -> List[AuditViolation]:
    violations: List[AuditViolation] = []

    if patch.operation not in ("ADD", "MODIFY"):
        return violations  # DEPRECATE has no content to validate

    content = patch.payload.get("content", "")
    assumptions = patch.payload.get("assumptions", [])

    # --- Length ---
    if len(content) < cfg.min_content_length:
        violations.append(AuditViolation(
            code="SEM001",
            message=f"Content too short: {len(content)} chars (min {cfg.min_content_length})",
            severity=Severity.ERROR,
            field="payload.content",
        ))

    if len(content) > cfg.max_content_length:
        violations.append(AuditViolation(
            code="SEM002",
            message=f"Content too long: {len(content)} chars (max {cfg.max_content_length})",
            severity=Severity.ERROR,
            field="payload.content",
        ))

    # --- Placeholder detection ---
    for pattern in cfg.placeholder_patterns:
        if re.match(pattern, content, re.IGNORECASE):
            violations.append(AuditViolation(
                code="SEM003",
                message=f"Content appears to be a placeholder: {content[:60]!r}",
                severity=Severity.ERROR,
                field="payload.content",
            ))
            break

    # --- Repetition ---
    if content:
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(content) if s.strip()]
        if len(sentences) >= 3:
            unique = set(sentences)
            rep_ratio = 1.0 - (len(unique) / len(sentences))
            if rep_ratio > cfg.max_repetition_ratio:
                violations.append(AuditViolation(
                    code="SEM004",
                    message=f"Excessive sentence repetition: {rep_ratio:.0%} duplicates",
                    severity=Severity.WARNING,
                    field="payload.content",
                ))

    # --- Assumption count ---
    if len(assumptions) > cfg.max_assumption_count:
        violations.append(AuditViolation(
            code="SEM005",
            message=f"Too many assumptions: {len(assumptions)} (max {cfg.max_assumption_count})",
            severity=Severity.WARNING,
            field="payload.assumptions",
        ))

    # --- Non-string assumptions ---
    if assumptions:
        bad = [a for a in assumptions if not isinstance(a, str)]
        if bad:
            violations.append(AuditViolation(
                code="SEM006",
                message=f"Assumptions must be strings; found non-string entries: {bad[:3]}",
                severity=Severity.ERROR,
                field="payload.assumptions",
            ))

    # --- Category-appropriate fields ---
    cat = patch.category

    if cat in cfg.require_uncertainty_for and patch.uncertainty is None:
        violations.append(AuditViolation(
            code="SEM007",
            message=f"Category {cat} requires uncertainty quantification",
            severity=Severity.WARNING,
            field="uncertainty",
        ))

    if cat in cfg.require_assumptions_for and not assumptions:
        violations.append(AuditViolation(
            code="SEM008",
            message=f"Category {cat} requires explicit assumptions",
            severity=Severity.WARNING,
            field="payload.assumptions",
        ))

    # --- Duplicate content key check (extra fields are OK, but 'content' must be str) ---
    if not isinstance(content, str):
        violations.append(AuditViolation(
            code="SEM009",
            message="payload.content must be a string",
            severity=Severity.ERROR,
            field="payload.content",
        ))

    return violations


# ---------------------------------------------------------------------------
# Source Verification
# ---------------------------------------------------------------------------

_URL_RE = re.compile(
    r"^(https?|doi|isbn|arxiv|urn)://\S+",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"^10\.\d{4,}/\S+")
_ARXIV_RE = re.compile(r"^\d{4}\.\d{4,}(v\d+)?$")


def _is_valid_source(src: Any, valid_schemes: Set[str]) -> Tuple[bool, str]:
    """Return (is_valid, reason)."""
    if not isinstance(src, (str, dict)):
        return False, "source must be a string or dict"

    if isinstance(src, dict):
        # Structured reference: must have at least "title" or "url"
        if not src.get("title") and not src.get("url"):
            return False, "structured source must have 'title' or 'url'"
        return True, ""

    # String source: must look like a URL or known ID scheme
    s = src.strip()
    if not s:
        return False, "source is empty string"

    scheme = s.split("://")[0].lower() if "://" in s else ""
    if scheme in valid_schemes:
        return True, ""
    if _DOI_RE.match(s):
        return True, ""
    if _ARXIV_RE.match(s):
        return True, ""
    # Bare URL without scheme
    if s.startswith("www."):
        return True, ""

    return False, f"unrecognized source format: {s[:60]!r}"


def _check_sources(patch: Patch, cfg: AuditGateConfig) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    cat = patch.category
    sources = patch.payload.get("sources", None)

    # Presence requirements
    if sources is None:
        if cat in cfg.require_sources_for:
            violations.append(AuditViolation(
                code="SRC001",
                message=f"Category {cat} requires sources (payload.sources)",
                severity=Severity.ERROR,
                field="payload.sources",
            ))
        elif cat in cfg.warn_missing_sources_for:
            violations.append(AuditViolation(
                code="SRC002",
                message=f"Category {cat} should include sources for reproducibility",
                severity=Severity.WARNING,
                field="payload.sources",
            ))
        return violations

    # Type check
    if not isinstance(sources, list):
        violations.append(AuditViolation(
            code="SRC003",
            message="payload.sources must be a list",
            severity=Severity.ERROR,
            field="payload.sources",
        ))
        return violations

    # Count limit
    if len(sources) > cfg.max_sources:
        violations.append(AuditViolation(
            code="SRC004",
            message=f"Too many sources: {len(sources)} (max {cfg.max_sources})",
            severity=Severity.WARNING,
            field="payload.sources",
        ))

    # Per-source validation
    for i, src in enumerate(sources):
        ok, reason = _is_valid_source(src, cfg.valid_source_schemes)
        if not ok:
            violations.append(AuditViolation(
                code="SRC005",
                message=f"Invalid source at index {i}: {reason}",
                severity=Severity.WARNING,
                field=f"payload.sources[{i}]",
            ))

    # Duplicate sources
    str_sources = [s for s in sources if isinstance(s, str)]
    if len(str_sources) != len(set(str_sources)):
        violations.append(AuditViolation(
            code="SRC006",
            message="Duplicate sources detected",
            severity=Severity.WARNING,
            field="payload.sources",
        ))

    return violations


# ---------------------------------------------------------------------------
# Temporal Reasoning
# ---------------------------------------------------------------------------

def _extract_years_from_text(text: str) -> List[int]:
    return [int(m) for m in _YEAR_RE.findall(text)]


def _check_temporal(
    patch: Patch,
    cfg: AuditGateConfig,
    now: Optional[int] = None,
    branch_last_timestamp: Optional[int] = None,
) -> List[AuditViolation]:
    violations: List[AuditViolation] = []
    ts = patch.timestamp

    if now is None:
        now = int(time.time())

    # --- Timestamp plausibility ---
    if ts < cfg.min_timestamp:
        violations.append(AuditViolation(
            code="TMP001",
            message=f"Suspiciously old timestamp: {ts} (before {cfg.min_timestamp})",
            severity=Severity.ERROR,
            field="timestamp",
        ))

    if ts > now + cfg.max_future_drift_seconds:
        drift = ts - now
        violations.append(AuditViolation(
            code="TMP002",
            message=f"Timestamp is {drift}s in the future (max allowed: {cfg.max_future_drift_seconds}s)",
            severity=Severity.ERROR,
            field="timestamp",
        ))

    import datetime
    try:
        patch_year = datetime.datetime.fromtimestamp(ts).year
        if patch_year > cfg.max_timestamp_year:
            violations.append(AuditViolation(
                code="TMP003",
                message=f"Timestamp year {patch_year} exceeds max {cfg.max_timestamp_year}",
                severity=Severity.ERROR,
                field="timestamp",
            ))
    except (OSError, OverflowError, ValueError):
        violations.append(AuditViolation(
            code="TMP004",
            message=f"Timestamp {ts} cannot be converted to a date",
            severity=Severity.ERROR,
            field="timestamp",
        ))
        patch_year = None

    # --- Monotonicity hint (if branch context provided) ---
    if branch_last_timestamp is not None and ts <= branch_last_timestamp:
        violations.append(AuditViolation(
            code="TMP005",
            message=(
                f"Non-monotonic timestamp: {ts} <= branch last timestamp "
                f"{branch_last_timestamp}"
            ),
            severity=Severity.ERROR,
            field="timestamp",
        ))

    # --- temporal_scope field consistency ---
    temporal_scope = patch.payload.get(cfg.temporal_scope_field)
    if temporal_scope is not None:
        if not isinstance(temporal_scope, (str, dict)):
            violations.append(AuditViolation(
                code="TMP006",
                message=f"payload.{cfg.temporal_scope_field} must be a string or dict",
                severity=Severity.WARNING,
                field=f"payload.{cfg.temporal_scope_field}",
            ))
        elif isinstance(temporal_scope, dict):
            # Validate start/end if present
            start = temporal_scope.get("start")
            end = temporal_scope.get("end")
            if start is not None and end is not None:
                try:
                    if int(start) > int(end):
                        violations.append(AuditViolation(
                            code="TMP007",
                            message="temporal_scope.start > temporal_scope.end",
                            severity=Severity.ERROR,
                            field=f"payload.{cfg.temporal_scope_field}",
                        ))
                except (TypeError, ValueError):
                    pass

    # --- Year mentions in content ---
    if cfg.flag_anachronistic_year_mentions and patch_year is not None:
        content = patch.payload.get("content", "")
        if content:
            mentioned_years = _extract_years_from_text(content)
            future_years = [y for y in mentioned_years if y > patch_year + 5]
            if future_years:
                violations.append(AuditViolation(
                    code="TMP008",
                    message=(
                        f"Content mentions future year(s) {future_years} "
                        f"(patch year: {patch_year})"
                    ),
                    severity=Severity.WARNING,
                    field="payload.content",
                ))

    return violations


# ---------------------------------------------------------------------------
# Audit Gate (main entry point)
# ---------------------------------------------------------------------------

class AuditGate:
    """
    Composable extended audit gate for Alexandria patches.

    Runs up to three additional validation layers beyond the structural
    ``audit_patch()`` checks already performed by ``AlexandriaStore``.
    """

    def __init__(self, config: Optional[AuditGateConfig] = None):
        self.config = config or AuditGateConfig()

    def validate(
        self,
        patch: Patch,
        *,
        now: Optional[int] = None,
        branch_last_timestamp: Optional[int] = None,
    ) -> AuditReport:
        """
        Run all enabled checks and return an AuditReport.

        Args:
            patch: The patch to validate.
            now: Override for current Unix timestamp (useful in tests).
            branch_last_timestamp: Last committed timestamp on the branch,
                used for monotonicity checks.

        Returns:
            AuditReport with all violations and warnings collected.
        """
        cfg = self.config
        violations: List[AuditViolation] = []

        if cfg.enable_semantic:
            violations.extend(_check_semantic(patch, cfg))

        if cfg.enable_source_verification:
            violations.extend(_check_sources(patch, cfg))

        if cfg.enable_temporal:
            violations.extend(
                _check_temporal(patch, cfg, now=now,
                                branch_last_timestamp=branch_last_timestamp)
            )

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        return AuditReport(
            patch_id=patch.patch_id,
            passed=not has_errors,
            violations=violations,
        )

    def validate_strict(
        self,
        patch: Patch,
        *,
        now: Optional[int] = None,
        branch_last_timestamp: Optional[int] = None,
    ) -> AuditReport:
        """
        Validate and raise AuditError immediately if any error-level
        violations are found.
        """
        report = self.validate(patch, now=now,
                               branch_last_timestamp=branch_last_timestamp)
        report.raise_if_failed()
        return report


# ---------------------------------------------------------------------------
# Convenience: extend AlexandriaMIVPStore with gate validation
# ---------------------------------------------------------------------------

def make_default_gate() -> AuditGate:
    """Create an AuditGate with sensible defaults."""
    return AuditGate(AuditGateConfig())


def make_strict_empirical_gate() -> AuditGate:
    """
    Create an AuditGate that requires sources for EMPIRICAL claims
    and enforces uncertainty quantification.
    """
    cfg = AuditGateConfig(
        require_sources_for={"EMPIRICAL"},
        require_uncertainty_for={"EMPIRICAL"},
    )
    return AuditGate(cfg)
