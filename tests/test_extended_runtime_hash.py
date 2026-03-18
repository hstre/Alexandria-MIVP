"""
Tests für Extended Runtime Hash (Three-layer).

Prüft die Integration der drei Schichten (Config, Environment, Attestation)
in AgentIdentity.compute_rh() und get_identity_dict().
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mivp_impl import (
    canonicalize_runtime_environment,
    runtime_environment_hash,
    canonicalize_runtime_attestation,
    runtime_attestation_hash,
    runtime_extended_hash,
    runtime_hash,
    canonicalize_runtime,
)
from alexandria_mivp import AgentIdentity


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def make_basic_identity(**kwargs) -> AgentIdentity:
    """AgentIdentity mit Minimalparametern erstellen."""
    defaults = dict(
        name="TestAgent",
        model_path="",
        model_bytes=b"test_model",
        system_prompt="test",
        guardrails=[],
        temperature=0.7,
        top_p=0.9,
        max_tokens=100,
    )
    defaults.update(kwargs)
    return AgentIdentity(**defaults)


# ---------------------------------------------------------------------------
# Tests: canonicalize_runtime_environment
# ---------------------------------------------------------------------------

class TestCanonicalizeRuntimeEnvironment(unittest.TestCase):
    def test_empty_produces_empty_json(self):
        result = canonicalize_runtime_environment()
        import json
        obj = json.loads(result)
        self.assertEqual(obj, {})

    def test_fields_included_when_set(self):
        result = canonicalize_runtime_environment(
            container_digest="sha256:abc",
            python_version="3.11.0",
        )
        import json
        obj = json.loads(result)
        self.assertEqual(obj["container_digest"], "sha256:abc")
        self.assertEqual(obj["python_version"], "3.11.0")

    def test_empty_fields_excluded(self):
        result = canonicalize_runtime_environment(
            container_digest="sha256:abc",
            python_version="",
        )
        import json
        obj = json.loads(result)
        self.assertNotIn("python_version", obj)

    def test_system_libraries_sorted(self):
        result = canonicalize_runtime_environment(
            system_libraries=["torch", "numpy", "scipy"]
        )
        import json
        obj = json.loads(result)
        self.assertEqual(obj["system_libraries"], sorted(["torch", "numpy", "scipy"]))

    def test_hardware_info_sorted(self):
        result = canonicalize_runtime_environment(
            hardware_info={"z_key": 1, "a_key": 2}
        )
        import json
        raw = result
        self.assertLess(raw.index('"a_key"'), raw.index('"z_key"'))

    def test_deterministic(self):
        r1 = canonicalize_runtime_environment(container_digest="sha256:x", python_version="3.11")
        r2 = canonicalize_runtime_environment(container_digest="sha256:x", python_version="3.11")
        self.assertEqual(r1, r2)


# ---------------------------------------------------------------------------
# Tests: runtime_environment_hash
# ---------------------------------------------------------------------------

class TestRuntimeEnvironmentHash(unittest.TestCase):
    def test_returns_32_bytes(self):
        h = runtime_environment_hash(canonicalize_runtime_environment())
        self.assertEqual(len(h), 32)

    def test_differs_from_config_hash(self):
        canonical = canonicalize_runtime(
            temperature=0.7, top_p=0.9, max_tokens=100,
            tooling_enabled=True, routing_mode="direct", runtime_spec_version="1.0"
        )
        config_h = runtime_hash(canonical)
        # Use same content in env hash to verify domain separation
        env_h = runtime_environment_hash(canonical)
        self.assertNotEqual(config_h, env_h)

    def test_same_input_same_hash(self):
        j = canonicalize_runtime_environment(container_digest="sha256:abc")
        self.assertEqual(runtime_environment_hash(j), runtime_environment_hash(j))

    def test_different_inputs_different_hashes(self):
        j1 = canonicalize_runtime_environment(container_digest="sha256:aaa")
        j2 = canonicalize_runtime_environment(container_digest="sha256:bbb")
        self.assertNotEqual(runtime_environment_hash(j1), runtime_environment_hash(j2))


# ---------------------------------------------------------------------------
# Tests: canonicalize_runtime_attestation
# ---------------------------------------------------------------------------

class TestCanonicalizeRuntimeAttestation(unittest.TestCase):
    def test_only_spec_version_when_empty(self):
        result = canonicalize_runtime_attestation()
        import json
        obj = json.loads(result)
        self.assertIn("attestation_spec_version", obj)

    def test_tee_type_included(self):
        result = canonicalize_runtime_attestation(tee_type="SGX")
        import json
        obj = json.loads(result)
        self.assertEqual(obj["tee_type"], "SGX")

    def test_measurements_sorted(self):
        result = canonicalize_runtime_attestation(
            secure_enclave_measurements=["meas_z", "meas_a"]
        )
        import json
        obj = json.loads(result)
        self.assertEqual(obj["secure_enclave_measurements"], ["meas_a", "meas_z"])

    def test_empty_fields_excluded(self):
        result = canonicalize_runtime_attestation(tee_type="", tpm_quote="")
        import json
        obj = json.loads(result)
        self.assertNotIn("tee_type", obj)
        self.assertNotIn("tpm_quote", obj)


# ---------------------------------------------------------------------------
# Tests: runtime_attestation_hash
# ---------------------------------------------------------------------------

class TestRuntimeAttestationHash(unittest.TestCase):
    def test_returns_32_bytes(self):
        h = runtime_attestation_hash(canonicalize_runtime_attestation())
        self.assertEqual(len(h), 32)

    def test_differs_from_env_hash(self):
        j = canonicalize_runtime_attestation(tee_type="SGX")
        attest_h = runtime_attestation_hash(j)
        env_h = runtime_environment_hash(j)
        self.assertNotEqual(attest_h, env_h)

    def test_deterministic(self):
        j = canonicalize_runtime_attestation(tee_type="TDX")
        self.assertEqual(runtime_attestation_hash(j), runtime_attestation_hash(j))


# ---------------------------------------------------------------------------
# Tests: runtime_extended_hash
# ---------------------------------------------------------------------------

class TestRuntimeExtendedHash(unittest.TestCase):
    def _make_hashes(self):
        config_h = runtime_hash(
            canonicalize_runtime(
                temperature=0.7, top_p=0.9, max_tokens=100,
                tooling_enabled=True, routing_mode="direct", runtime_spec_version="1.0",
            )
        )
        env_h = runtime_environment_hash(
            canonicalize_runtime_environment(container_digest="sha256:abc")
        )
        attest_h = runtime_attestation_hash(
            canonicalize_runtime_attestation(tee_type="SGX")
        )
        return config_h, env_h, attest_h

    def test_returns_32_bytes(self):
        h = runtime_extended_hash(*self._make_hashes())
        self.assertEqual(len(h), 32)

    def test_deterministic(self):
        args = self._make_hashes()
        self.assertEqual(runtime_extended_hash(*args), runtime_extended_hash(*args))

    def test_differs_from_config_hash(self):
        config_h, env_h, attest_h = self._make_hashes()
        ext_h = runtime_extended_hash(config_h, env_h, attest_h)
        self.assertNotEqual(ext_h, config_h)

    def test_changing_env_changes_result(self):
        config_h, env_h, attest_h = self._make_hashes()
        env_h2 = runtime_environment_hash(
            canonicalize_runtime_environment(container_digest="sha256:xyz")
        )
        h1 = runtime_extended_hash(config_h, env_h, attest_h)
        h2 = runtime_extended_hash(config_h, env_h2, attest_h)
        self.assertNotEqual(h1, h2)

    def test_changing_attestation_changes_result(self):
        config_h, env_h, attest_h = self._make_hashes()
        attest_h2 = runtime_attestation_hash(
            canonicalize_runtime_attestation(tee_type="TDX")
        )
        h1 = runtime_extended_hash(config_h, env_h, attest_h)
        h2 = runtime_extended_hash(config_h, env_h, attest_h2)
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# Tests: AgentIdentity – standard mode (use_extended_runtime_hash=False)
# ---------------------------------------------------------------------------

class TestAgentIdentityStandardRH(unittest.TestCase):
    def setUp(self):
        self.identity = make_basic_identity()

    def test_compute_rh_returns_bytes(self):
        rh = self.identity.compute_rh()
        self.assertIsInstance(rh, bytes)
        self.assertEqual(len(rh), 32)

    def test_rh_same_as_plain_runtime_hash(self):
        rh = self.identity.compute_rh()
        expected = runtime_hash(
            canonicalize_runtime(
                temperature=0.7, top_p=0.9, max_tokens=100,
                tooling_enabled=True, routing_mode="direct", runtime_spec_version="1.0",
            )
        )
        self.assertEqual(rh, expected)

    def test_no_rh_extended_in_identity_dict(self):
        d = self.identity.get_identity_dict()
        self.assertNotIn("rh_extended", d)

    def test_use_extended_false_by_default(self):
        self.assertFalse(self.identity.use_extended_runtime_hash)


# ---------------------------------------------------------------------------
# Tests: AgentIdentity – extended mode (use_extended_runtime_hash=True)
# ---------------------------------------------------------------------------

class TestAgentIdentityExtendedRH(unittest.TestCase):
    def setUp(self):
        self.identity = make_basic_identity(
            use_extended_runtime_hash=True,
            container_digest="sha256:abc123",
            python_version="3.11.0",
            dependency_hash="sha256:dep456",
            model_route="/models/test",
            system_libraries=["numpy", "torch"],
            hardware_info={"cpus": 4, "memory_gb": 16},
            tee_type="SGX",
            tpm_quote="mock_quote",
            attestation_proof="mock_proof",
            secure_enclave_measurements=["meas_a", "meas_b"],
            attestation_spec_version="2.0",
        )

    def test_compute_rh_returns_32_bytes(self):
        rh = self.identity.compute_rh()
        self.assertIsInstance(rh, bytes)
        self.assertEqual(len(rh), 32)

    def test_extended_rh_differs_from_plain_rh(self):
        rh_extended = self.identity.compute_rh()
        rh_plain = runtime_hash(
            canonicalize_runtime(
                temperature=0.7, top_p=0.9, max_tokens=100,
                tooling_enabled=True, routing_mode="direct", runtime_spec_version="1.0",
            )
        )
        self.assertNotEqual(rh_extended, rh_plain)

    def test_identity_dict_contains_rh_extended(self):
        d = self.identity.get_identity_dict()
        self.assertIn("rh_extended", d)

    def test_rh_extended_has_all_sub_hashes(self):
        d = self.identity.get_identity_dict()
        rhe = d["rh_extended"]
        self.assertIn("config_h", rhe)
        self.assertIn("env_h", rhe)
        self.assertIn("attest_h", rhe)

    def test_sub_hashes_are_hex_strings(self):
        d = self.identity.get_identity_dict()
        rhe = d["rh_extended"]
        for key in ("config_h", "env_h", "attest_h"):
            self.assertEqual(len(rhe[key]), 64)  # 32 bytes → 64 hex chars
            bytes.fromhex(rhe[key])  # must not raise

    def test_config_h_matches_standard_rh(self):
        d = self.identity.get_identity_dict()
        rhe = d["rh_extended"]
        expected_config_h = runtime_hash(
            canonicalize_runtime(
                temperature=0.7, top_p=0.9, max_tokens=100,
                tooling_enabled=True, routing_mode="direct", runtime_spec_version="1.0",
            )
        )
        self.assertEqual(bytes.fromhex(rhe["config_h"]), expected_config_h)

    def test_rh_in_dict_matches_extended_combined(self):
        d = self.identity.get_identity_dict()
        rhe = d["rh_extended"]
        expected_ext = runtime_extended_hash(
            bytes.fromhex(rhe["config_h"]),
            bytes.fromhex(rhe["env_h"]),
            bytes.fromhex(rhe["attest_h"]),
        )
        self.assertEqual(bytes.fromhex(d["rh"]), expected_ext)

    def test_cih_uses_extended_rh(self):
        rh = self.identity.compute_rh()
        cih = self.identity.compute_cih()
        d = self.identity.get_identity_dict()
        self.assertEqual(bytes.fromhex(d["rh"]), rh)
        self.assertEqual(bytes.fromhex(d["cih"]), cih)

    def test_extended_rh_deterministic(self):
        rh1 = self.identity.compute_rh()
        # Reset cache to force recomputation
        self.identity._AgentIdentity__rh = None
        self.identity._AgentIdentity__config_h = None
        self.identity._AgentIdentity__env_h = None
        self.identity._AgentIdentity__attest_h = None
        rh2 = self.identity.compute_rh()
        self.assertEqual(rh1, rh2)

    def test_env_change_changes_rh(self):
        rh1 = make_basic_identity(
            use_extended_runtime_hash=True,
            container_digest="sha256:aaa",
        ).compute_rh()
        rh2 = make_basic_identity(
            use_extended_runtime_hash=True,
            container_digest="sha256:bbb",
        ).compute_rh()
        self.assertNotEqual(rh1, rh2)

    def test_attest_change_changes_rh(self):
        rh1 = make_basic_identity(
            use_extended_runtime_hash=True,
            tee_type="SGX",
        ).compute_rh()
        rh2 = make_basic_identity(
            use_extended_runtime_hash=True,
            tee_type="TDX",
        ).compute_rh()
        self.assertNotEqual(rh1, rh2)

    def test_standard_vs_extended_rh_differ_with_env(self):
        std = make_basic_identity(use_extended_runtime_hash=False).compute_rh()
        ext = make_basic_identity(
            use_extended_runtime_hash=True,
            container_digest="sha256:abc",
        ).compute_rh()
        self.assertNotEqual(std, ext)


# ---------------------------------------------------------------------------
# Tests: Backward compatibility – existing AgentIdentity usage still works
# ---------------------------------------------------------------------------

class TestBackwardCompatibility(unittest.TestCase):
    def test_no_extra_params_needed(self):
        identity = AgentIdentity(
            name="Legacy",
            model_path="",
            model_bytes=b"model",
            system_prompt=".",
            guardrails=[],
            temperature=0.5,
            top_p=0.8,
            max_tokens=50,
        )
        rh = identity.compute_rh()
        self.assertEqual(len(rh), 32)

    def test_cih_still_computable(self):
        identity = AgentIdentity(
            name="Legacy",
            model_path="",
            model_bytes=b"model",
            system_prompt=".",
            guardrails=[],
            temperature=0.5,
            top_p=0.8,
            max_tokens=50,
        )
        cih = identity.compute_cih()
        self.assertEqual(len(cih), 32)

    def test_get_identity_dict_still_works(self):
        identity = AgentIdentity(
            name="Legacy",
            model_path="",
            model_bytes=b"model",
            system_prompt=".",
            guardrails=[],
            temperature=0.5,
            top_p=0.8,
            max_tokens=50,
        )
        d = identity.get_identity_dict()
        for key in ("agent_name", "mh", "ph", "rh", "cih"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
