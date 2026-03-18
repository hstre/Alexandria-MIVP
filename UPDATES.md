# UPDATES.md – Alexandria-MIVP Changelog

---

## 2026-03-18 – Technische Konsolidierung

### Packaging
- `src/` → `alexandria_mivp/` umbenannt (Standard Python-Paket-Konvention)
- `pyproject.toml` hinzugefügt (modernes Build-System, `setuptools.build_meta`)
- `setup.py` auf `find_packages()` ohne `package_dir`-Hack vereinfacht
- `pip install -e .` funktioniert jetzt korrekt → `import alexandria_mivp` verfügbar
- Optional dependencies: `[signatures]`, `[s3]`, `[ipfs]`, `[dev]`, `[all]`

### Import-Bereinigung
- Alle `try: from .X … except ImportError: from X …` Dual-Import-Blöcke entfernt
- Alle Module verwenden ausschließlich relative Imports
- `audit_gate.py`, `uncertainty_propagator.py`: invertierte Fallbacks korrigiert
- `sqlite_store.py`: bare absolute Imports korrigiert

### Tests (526 passing, 0 warnings)
- `sys.path.insert(0, "../src")` aus allen 16 Testdateien entfernt
- Alle `from flat_module import` → `from alexandria_mivp.flat_module import`
- `test_integration.py`, `test_mivp_vectors.py`, `test_alexandria.py`: `return bool` → `assert`
- `conftest.py` im Projekt-Root hinzugefügt
- pytest config in `pyproject.toml`: `testpaths = ["tests"]`

### Dokumentation
- `docs/api_reference.md`: neue Sektionen für alle 7 neuen Module
- `docs/architecture.md`: 6 neue Komponenten-Diagramme
- `README.md`: Projektstruktur und Development Status aktualisiert

---

## 2026-03-17 – Neue Module

### Neue Module
| Modul | Tests | Beschreibung |
|-------|-------|--------------|
| `audit_gate.py` | 59 | Drei-Schichten-Validierung (Semantik, Quellen, Temporal) |
| `uncertainty_propagator.py` | 49 | DAG-basierte Unsicherheitspropagation, 5 Modi |
| `cross_agent_graph.py` | 48 | Cross-Agent-Graph, 5 Kantentypen, BFS, Konflikterkennung |
| `performance.py` | 38 | NodeCache (LRU), QueryCache (TTL), BatchProcessor, Monitor |
| `distributed_store.py` | 55 | S3, IPFS, Ledger, Multi-Backend-Redundanz |
| `formal_verification.py` | 47 | 4 Invarianten, 6 Properties, Custom-Checks |
| `sqlite_store.py` (erweitert) | 44 | rh_extended_json, 4 Indizes, 10 Identity-Abfragen |

### `alexandria_mivp.py` – Extended Runtime Hash
- Drei-Schichten-RH: Config, Environment, Attestation
- `AgentIdentity(use_extended_runtime_hash=True)`
- Sub-Hashes gecacht als `__config_h`, `__env_h`, `__attest_h`

---

## 2026-03-08 – Kritische Fixes und Infrastruktur

### Kritische Korrekturen
- **`cfs1_float()`**: `Decimal(repr(x))` für Round-trip-Sicherheit
- **`AgentIdentity`**: von `@dataclass` auf normale Klasse umgestellt
- **Zwei-Stufen-Verifikation**: `verify_patch_identity_internal()` vs. `verify_patch_identity_against_agent()`

### Neue Module
- `sub_agent.py`: SubAgent, MultiAgentCoordinator, Konsensbildung
- `heartbeat.py`: EpistemicHeartbeat (periodische Integritätsprüfungen)
- `message_router.py`: MessageRouter, Subscription-basiertes Routing
- `external_anchor.py`: SimulatedAnchor, OpenTimestampsAnchor, WebhookAnchor, MultiAnchor
- `moltbook_integration.py`: Moltbook API-Integration
- `sqlite_store.py`: SQLite-Persistenz mit Migrations-Tool

### Infrastruktur
- GitHub Repository: https://github.com/hstre/Alexandria-MIVP (public)
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
- `.github/ISSUE_TEMPLATE/` (bug_report.md, feature_request.md)
- Alle MIVP v2.1 Appendix G Test-Vektoren bestanden (byte-identisch)
