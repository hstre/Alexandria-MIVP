"""
Tests für das erweiterte Audit Gate.

Prüft alle drei Validierungsschichten:
1. Semantische Validierung
2. Source-Verifizierung
3. Temporal Reasoning
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from alexandria_v2 import Patch, AuditError
from audit_gate import (
    AuditGate,
    AuditGateConfig,
    AuditReport,
    AuditViolation,
    Severity,
    make_default_gate,
    make_strict_empirical_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS_BASE = int(time.time())


def _make_patch(
    content="This is a valid epistemic claim with sufficient length.",
    category="EMPIRICAL",
    operation="ADD",
    sources=None,
    assumptions=None,
    uncertainty=None,
    timestamp=None,
    payload_extra=None,
    target_id="claim_001",
) -> Patch:
    payload = {"content": content, "assumptions": assumptions or []}
    if sources is not None:
        payload["sources"] = sources
    if payload_extra:
        payload.update(payload_extra)
    return Patch(
        patch_id=f"test_{target_id}",
        parent_patch_id=None,
        branch_id="main",
        timestamp=timestamp or _TS_BASE,
        operation=operation,
        target_id=target_id,
        category=category,
        payload=payload,
        audit={"validated": True, "decay": 0.01},
        uncertainty=uncertainty,
        chain=None,
    )


# ---------------------------------------------------------------------------
# Tests: AuditGate instantiation
# ---------------------------------------------------------------------------

class TestAuditGateInit(unittest.TestCase):
    def test_default_gate_created(self):
        gate = make_default_gate()
        self.assertIsInstance(gate, AuditGate)

    def test_strict_empirical_gate_created(self):
        gate = make_strict_empirical_gate()
        self.assertIn("EMPIRICAL", gate.config.require_sources_for)

    def test_custom_config_applied(self):
        cfg = AuditGateConfig(min_content_length=50)
        gate = AuditGate(cfg)
        self.assertEqual(gate.config.min_content_length, 50)

    def test_validate_returns_report(self):
        gate = make_default_gate()
        p = _make_patch()
        report = gate.validate(p, now=_TS_BASE)
        self.assertIsInstance(report, AuditReport)

    def test_valid_patch_passes(self):
        gate = make_default_gate()
        p = _make_patch()
        report = gate.validate(p, now=_TS_BASE)
        self.assertTrue(report.passed)
        self.assertEqual(report.errors(), [])


# ---------------------------------------------------------------------------
# Tests: Semantische Validierung – content length
# ---------------------------------------------------------------------------

class TestSemanticContentLength(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()

    def test_content_too_short(self):
        p = _make_patch(content="abc")
        report = self.gate.validate(p, now=_TS_BASE)
        codes = [v.code for v in report.errors()]
        self.assertIn("SEM001", codes)

    def test_content_minimum_length_ok(self):
        # Exactly 10 chars
        p = _make_patch(content="1234567890")
        report = self.gate.validate(p, now=_TS_BASE)
        sem001 = [v for v in report.violations if v.code == "SEM001"]
        self.assertEqual(sem001, [])

    def test_content_too_long(self):
        p = _make_patch(content="x" * 60_000)
        report = self.gate.validate(p, now=_TS_BASE)
        codes = [v.code for v in report.errors()]
        self.assertIn("SEM002", codes)

    def test_deprecate_skips_content_check(self):
        p = _make_patch(content="", operation="DEPRECATE")
        report = self.gate.validate(p, now=_TS_BASE)
        sem_errors = [v for v in report.violations if v.code.startswith("SEM")]
        self.assertEqual(sem_errors, [])


# ---------------------------------------------------------------------------
# Tests: Semantische Validierung – placeholder detection
# ---------------------------------------------------------------------------

class TestSemanticPlaceholder(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()

    def test_placeholder_test_rejected(self):
        p = _make_patch(content="test")
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SEM003", [v.code for v in report.violations])

    def test_placeholder_lorem_ipsum_rejected(self):
        p = _make_patch(content="Lorem ipsum dolor sit amet")
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SEM003", [v.code for v in report.violations])

    def test_placeholder_todo_rejected(self):
        p = _make_patch(content="TODO")
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SEM003", [v.code for v in report.violations])

    def test_real_content_not_flagged(self):
        p = _make_patch(content="Temperature increases correlate with CO2 levels.")
        report = self.gate.validate(p, now=_TS_BASE)
        placeholder = [v for v in report.violations if v.code == "SEM003"]
        self.assertEqual(placeholder, [])


# ---------------------------------------------------------------------------
# Tests: Semantische Validierung – repetition
# ---------------------------------------------------------------------------

class TestSemanticRepetition(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()

    def test_highly_repetitive_content_warned(self):
        sentence = "This claim is true. "
        p = _make_patch(content=sentence * 10)
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SEM004", [v.code for v in report.violations])

    def test_non_repetitive_content_ok(self):
        content = (
            "Water boils at 100°C at sea level. "
            "Ice melts at 0°C. "
            "Steam condenses at 100°C. "
            "The phase transitions depend on pressure."
        )
        p = _make_patch(content=content)
        report = self.gate.validate(p, now=_TS_BASE)
        sem004 = [v for v in report.violations if v.code == "SEM004"]
        self.assertEqual(sem004, [])


# ---------------------------------------------------------------------------
# Tests: Semantische Validierung – assumptions
# ---------------------------------------------------------------------------

class TestSemanticAssumptions(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()

    def test_too_many_assumptions_warned(self):
        p = _make_patch(assumptions=[f"assumption {i}" for i in range(60)])
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SEM005", [v.code for v in report.violations])

    def test_non_string_assumptions_flagged(self):
        p = _make_patch(assumptions=["valid", 42, {"key": "value"}])
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SEM006", [v.code for v in report.violations])

    def test_valid_assumptions_ok(self):
        p = _make_patch(assumptions=["Ceteris paribus", "Normal atmospheric pressure"])
        report = self.gate.validate(p, now=_TS_BASE)
        asm_errors = [v for v in report.violations if v.code in ("SEM005", "SEM006")]
        self.assertEqual(asm_errors, [])


# ---------------------------------------------------------------------------
# Tests: Semantische Validierung – category fields
# ---------------------------------------------------------------------------

class TestSemanticCategoryFields(unittest.TestCase):
    def setUp(self):
        cfg = AuditGateConfig(require_uncertainty_for={"EMPIRICAL"})
        self.gate = AuditGate(cfg)

    def test_empirical_without_uncertainty_warned(self):
        p = _make_patch(category="EMPIRICAL", uncertainty=None)
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SEM007", [v.code for v in report.violations])

    def test_empirical_with_uncertainty_ok(self):
        p = _make_patch(category="EMPIRICAL", uncertainty={"sigma": 0.1})
        report = self.gate.validate(p, now=_TS_BASE)
        sem007 = [v for v in report.violations if v.code == "SEM007"]
        self.assertEqual(sem007, [])

    def test_normative_without_uncertainty_ok(self):
        p = _make_patch(category="NORMATIVE", uncertainty=None)
        report = self.gate.validate(p, now=_TS_BASE)
        sem007 = [v for v in report.violations if v.code == "SEM007"]
        self.assertEqual(sem007, [])


# ---------------------------------------------------------------------------
# Tests: Source Verification
# ---------------------------------------------------------------------------

class TestSourceVerification(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()
        self.strict_gate = make_strict_empirical_gate()

    def test_empirical_without_sources_warns(self):
        p = _make_patch(category="EMPIRICAL", sources=None)
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SRC002", [v.code for v in report.violations])

    def test_empirical_without_sources_errors_strict(self):
        p = _make_patch(category="EMPIRICAL", sources=None)
        report = self.strict_gate.validate(p, now=_TS_BASE)
        self.assertIn("SRC001", [v.code for v in report.errors()])

    def test_normative_without_sources_ok(self):
        p = _make_patch(category="NORMATIVE", sources=None)
        report = self.gate.validate(p, now=_TS_BASE)
        src_violations = [v for v in report.violations if v.code.startswith("SRC")]
        self.assertEqual(src_violations, [])

    def test_valid_https_source(self):
        p = _make_patch(sources=["https://example.com/paper"])
        report = self.gate.validate(p, now=_TS_BASE)
        src005 = [v for v in report.violations if v.code == "SRC005"]
        self.assertEqual(src005, [])

    def test_valid_doi_source(self):
        p = _make_patch(sources=["10.1000/xyz123"])
        report = self.gate.validate(p, now=_TS_BASE)
        src005 = [v for v in report.violations if v.code == "SRC005"]
        self.assertEqual(src005, [])

    def test_valid_arxiv_source(self):
        p = _make_patch(sources=["2301.00001"])
        report = self.gate.validate(p, now=_TS_BASE)
        src005 = [v for v in report.violations if v.code == "SRC005"]
        self.assertEqual(src005, [])

    def test_valid_structured_source(self):
        p = _make_patch(sources=[{"title": "IPCC Report", "url": "https://ipcc.ch"}])
        report = self.gate.validate(p, now=_TS_BASE)
        src005 = [v for v in report.violations if v.code == "SRC005"]
        self.assertEqual(src005, [])

    def test_invalid_source_flagged(self):
        p = _make_patch(sources=["just a string with no URL"])
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SRC005", [v.code for v in report.violations])

    def test_empty_source_string_flagged(self):
        p = _make_patch(sources=[""])
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SRC005", [v.code for v in report.violations])

    def test_sources_not_list_is_error(self):
        p = _make_patch(sources="https://example.com")
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SRC003", [v.code for v in report.errors()])

    def test_duplicate_sources_warned(self):
        p = _make_patch(sources=[
            "https://example.com",
            "https://example.com",
        ])
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SRC006", [v.code for v in report.violations])

    def test_too_many_sources_warned(self):
        p = _make_patch(sources=[f"https://source{i}.com" for i in range(150)])
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("SRC004", [v.code for v in report.violations])


# ---------------------------------------------------------------------------
# Tests: Temporal Reasoning – timestamp plausibility
# ---------------------------------------------------------------------------

class TestTemporalTimestamp(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()
        self.now = _TS_BASE

    def test_valid_timestamp_ok(self):
        p = _make_patch(timestamp=self.now)
        report = self.gate.validate(p, now=self.now)
        tmp_errors = [v for v in report.errors() if v.code.startswith("TMP")]
        self.assertEqual(tmp_errors, [])

    def test_too_old_timestamp_rejected(self):
        p = _make_patch(timestamp=999_999_999)  # ~2001-09-08
        report = self.gate.validate(p, now=self.now)
        self.assertIn("TMP001", [v.code for v in report.errors()])

    def test_future_timestamp_rejected(self):
        p = _make_patch(timestamp=self.now + 3600)  # 1 hour in future
        report = self.gate.validate(p, now=self.now)
        self.assertIn("TMP002", [v.code for v in report.errors()])

    def test_slight_future_drift_ok(self):
        # within 5 minutes allowed
        p = _make_patch(timestamp=self.now + 60)
        report = self.gate.validate(p, now=self.now)
        tmp002 = [v for v in report.violations if v.code == "TMP002"]
        self.assertEqual(tmp002, [])

    def test_branch_monotonicity_violation(self):
        p = _make_patch(timestamp=self.now)
        report = self.gate.validate(
            p, now=self.now + 100, branch_last_timestamp=self.now + 50
        )
        self.assertIn("TMP005", [v.code for v in report.errors()])

    def test_branch_monotonicity_ok(self):
        p = _make_patch(timestamp=self.now + 100)
        report = self.gate.validate(
            p, now=self.now + 200, branch_last_timestamp=self.now
        )
        tmp005 = [v for v in report.violations if v.code == "TMP005"]
        self.assertEqual(tmp005, [])


# ---------------------------------------------------------------------------
# Tests: Temporal Reasoning – temporal_scope
# ---------------------------------------------------------------------------

class TestTemporalScope(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()

    def test_valid_temporal_scope_dict(self):
        p = _make_patch(payload_extra={"temporal_scope": {"start": 2000, "end": 2020}})
        report = self.gate.validate(p, now=_TS_BASE)
        tmp = [v for v in report.violations if v.code.startswith("TMP0")]
        # Only TMP violations we care about
        tmp_scope = [v for v in tmp if v.code in ("TMP006", "TMP007")]
        self.assertEqual(tmp_scope, [])

    def test_temporal_scope_inverted_range_error(self):
        p = _make_patch(payload_extra={"temporal_scope": {"start": 2025, "end": 2000}})
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("TMP007", [v.code for v in report.violations])

    def test_temporal_scope_string_ok(self):
        p = _make_patch(payload_extra={"temporal_scope": "Holocene"})
        report = self.gate.validate(p, now=_TS_BASE)
        tmp006 = [v for v in report.violations if v.code == "TMP006"]
        self.assertEqual(tmp006, [])

    def test_temporal_scope_invalid_type_warned(self):
        p = _make_patch(payload_extra={"temporal_scope": 42})
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertIn("TMP006", [v.code for v in report.violations])


# ---------------------------------------------------------------------------
# Tests: Temporal Reasoning – year mention anachronism
# ---------------------------------------------------------------------------

class TestTemporalYearMentions(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()
        # Use a fixed "now" in 2024
        self.now = 1_700_000_000  # ~2023-11-14

    def test_far_future_year_warned(self):
        p = _make_patch(
            content="By 2150, climate models predict irreversible changes.",
            timestamp=self.now,
        )
        report = self.gate.validate(p, now=self.now)
        self.assertIn("TMP008", [v.code for v in report.violations])

    def test_near_future_year_ok(self):
        # 4 years ahead – within the 5-year tolerance
        import datetime
        patch_year = datetime.datetime.fromtimestamp(self.now).year
        near_year = patch_year + 3
        p = _make_patch(
            content=f"By {near_year}, the study will conclude.",
            timestamp=self.now,
        )
        report = self.gate.validate(p, now=self.now)
        tmp008 = [v for v in report.violations if v.code == "TMP008"]
        self.assertEqual(tmp008, [])

    def test_past_year_mention_ok(self):
        p = _make_patch(
            content="The IPCC report of 1990 established baseline projections.",
            timestamp=self.now,
        )
        report = self.gate.validate(p, now=self.now)
        tmp008 = [v for v in report.violations if v.code == "TMP008"]
        self.assertEqual(tmp008, [])


# ---------------------------------------------------------------------------
# Tests: Disabled checks
# ---------------------------------------------------------------------------

class TestDisabledChecks(unittest.TestCase):
    def test_semantic_can_be_disabled(self):
        cfg = AuditGateConfig(enable_semantic=False)
        gate = AuditGate(cfg)
        # Content too short – would normally fail
        p = _make_patch(content="x")
        report = gate.validate(p, now=_TS_BASE)
        sem = [v for v in report.violations if v.code.startswith("SEM")]
        self.assertEqual(sem, [])

    def test_source_check_can_be_disabled(self):
        cfg = AuditGateConfig(enable_source_verification=False)
        gate = AuditGate(cfg)
        p = _make_patch(category="EMPIRICAL", sources=None)
        report = gate.validate(p, now=_TS_BASE)
        src = [v for v in report.violations if v.code.startswith("SRC")]
        self.assertEqual(src, [])

    def test_temporal_check_can_be_disabled(self):
        cfg = AuditGateConfig(enable_temporal=False)
        gate = AuditGate(cfg)
        p = _make_patch(timestamp=999_999_999)  # very old
        report = gate.validate(p, now=_TS_BASE)
        tmp = [v for v in report.violations if v.code.startswith("TMP")]
        self.assertEqual(tmp, [])


# ---------------------------------------------------------------------------
# Tests: AuditReport methods
# ---------------------------------------------------------------------------

class TestAuditReport(unittest.TestCase):
    def setUp(self):
        self.gate = make_default_gate()

    def test_errors_method(self):
        p = _make_patch(content="x")  # too short
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertGreater(len(report.errors()), 0)
        for v in report.errors():
            self.assertEqual(v.severity, Severity.ERROR)

    def test_warnings_method(self):
        p = _make_patch(category="EMPIRICAL", sources=None)
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertGreater(len(report.warnings()), 0)
        for v in report.warnings():
            self.assertEqual(v.severity, Severity.WARNING)

    def test_passed_false_when_errors(self):
        p = _make_patch(content="x")
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertFalse(report.passed)

    def test_passed_true_when_only_warnings(self):
        p = _make_patch(category="EMPIRICAL", sources=None, uncertainty={"sigma": 0.1})
        report = self.gate.validate(p, now=_TS_BASE)
        # SRC002 is a WARNING, not an ERROR
        self.assertTrue(report.passed)

    def test_raise_if_failed_raises_on_errors(self):
        p = _make_patch(content="x")
        report = self.gate.validate(p, now=_TS_BASE)
        with self.assertRaises(AuditError):
            report.raise_if_failed()

    def test_raise_if_failed_ok_with_warnings(self):
        p = _make_patch(category="EMPIRICAL", sources=None, uncertainty={"sigma": 0.1})
        report = self.gate.validate(p, now=_TS_BASE)
        report.raise_if_failed()  # must not raise

    def test_validate_strict_raises(self):
        p = _make_patch(content="x")
        with self.assertRaises(AuditError):
            self.gate.validate_strict(p, now=_TS_BASE)

    def test_patch_id_in_report(self):
        p = _make_patch()
        report = self.gate.validate(p, now=_TS_BASE)
        self.assertEqual(report.patch_id, p.patch_id)


# ---------------------------------------------------------------------------
# Tests: Integration – multiple violations collected
# ---------------------------------------------------------------------------

class TestMultipleViolations(unittest.TestCase):
    def test_multiple_violations_all_collected(self):
        gate = make_strict_empirical_gate()
        p = _make_patch(
            content="x",             # SEM001
            category="EMPIRICAL",
            sources=None,            # SRC001 (strict)
            uncertainty=None,        # SEM007
            timestamp=999_000_000,   # TMP001
        )
        report = gate.validate(p, now=_TS_BASE)
        codes = {v.code for v in report.violations}
        self.assertIn("SEM001", codes)
        self.assertIn("SRC001", codes)
        self.assertIn("TMP001", codes)

    def test_clean_patch_has_no_violations(self):
        gate = make_default_gate()
        p = _make_patch(
            content="CO2 concentration has increased by 50% since industrialization.",
            category="EMPIRICAL",
            sources=["https://noaa.gov/data"],
            uncertainty={"sigma": 0.05},
            assumptions=["Pre-industrial baseline: 280 ppm"],
        )
        report = gate.validate(p, now=_TS_BASE)
        self.assertTrue(report.passed)
        errors = report.errors()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
