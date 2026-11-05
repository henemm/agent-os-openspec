# Context: fix-521-spec-platzhalter-lokal

## Request Summary
Issue #521: Die Spec-Inhaltsprüfung des CI-Gates (Platzhalter u. a.) läuft lokal bei der
Freigabe nicht. Ergebnis bei #508: lokal auto-freigegeben, CI lehnt ab → Rücksprung nach
phase3_spec. Ziel: eine gemeinsame Prüfung in `workflow.py`, die Freigabe und CI-Gate
aufrufen; eine Platzhalter-Liste für Spec und Briefing.

## Related Files
| File | Relevance |
|------|-----------|
| `scripts/ci_spec_gate.py:60` | `SPEC_PLACEHOLDERS` (ohne `<platzhalter`) |
| `scripts/ci_spec_gate.py:238` | `_check_spec`: Pflicht-Sektionen, Platzhalter, AC-N (≥30 Zeichen), ADR |
| `core/hooks/workflow.py:1272` | `_PO_BRIEFING_PLACEHOLDERS` (mit `<platzhalter`) — zweite Liste |
| `core/hooks/workflow.py:1199` | `check_adr_content` — Vorbild "eine Regel, zwei Aufrufer" |
| `core/hooks/workflow.py:1336` | `check_briefing_content` — nutzt Briefing-Liste |
| `core/hooks/workflow.py:1640ff` | `_validate_transition`: ADR- und Briefing-Gate ab phase4_approved (feature + feature-fast) |
| `core/hooks/workflow.py:3370ff` | `_auto_approve_decision`: ADR/Briefing mit `trusted_config()` |
| `core/hooks/phase_listener.py:548ff` | Freigabe-Phrase: ADR- und Briefing-Gate, blockt mit Meldung |
| `tests/test_ci_spec_gate.py` | muss grün bleiben |

## Existing Patterns
- Inhaltsregeln als reine Text-Funktion in `workflow.py` (`check_adr_content`,
  `check_briefing_content`), lokale Wrapper `_check_adr(data, config)` mit Kill-Switch und
  lenientem Verhalten (Spec fehlt/unlesbar → None).
- CI lädt `workflow` per `_load_hook_module` und ruft die Funktionen auf; bei älteren Kopien
  `getattr`-Fallback (`po_briefing_max_words`).
- CI prüft nur Specs unter `docs/specs/` (ohne `_template.md`), Fast-Track-Specs
  (`docs/specs/fast/`) gar nicht.

## Dependencies / Dependents
- `hook_utils.extract_ac_entries` (AC-N-Parsing) — CI nutzt es bereits.
- Konsumenten-Projekte: `setup.py` installiert `ci_spec_gate.py` und Hooks zusammen.
- Viele Tests legen Minimal-Specs an und geben sie frei (ADR-/Briefing-/Auto-Approve-Tests).

## Risiken
- Volle CI-Prüfung lokal (Pflicht-Sektionen, AC-N) trifft Test-Fixtures mit Minimal-Specs.
- Gemeinsame Platzhalter-Liste macht CI für Specs um `<platzhalter` strenger (kein
  bestehender Spec-Treffer, geprüft per grep).
- Kill-Switch: lokale Prüfung ist Shift-left des CI-Gates → folgt `ci_spec_gate.enabled`.

## Analysis

### Type
Bug (Shift-left einer CI-Regel, Regel-Duplikat entfernen)

### Entscheidung PO (2026-11-05)
Volle CI-Parität: die komplette Spec-Inhaltsprüfung des CI-Gates (Pflicht-Sektionen,
Platzhalter, AC-N ≥ 30 Zeichen, ADR) läuft lokal bei der Freigabe. Prototyp-Messung:
32 bestehende Tests in 8 Dateien geben Minimal-Specs frei und brauchen vollständige
Spec-Fixtures (ohne Prüfung: 0 Brüche).

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `PLACEHOLDER_MARKERS` (eine Liste), `SPEC_REQUIRED_SECTIONS`, `check_spec_content`, `_check_spec_content` (Wrapper: Pfad-Regel wie CI, Kill-Switch `ci_spec_gate.enabled`); Aufruf in `_validate_transition` (nur beim Überschreiten der Freigabe-Grenze) und `_auto_approve_decision` |
| core/hooks/phase_listener.py | MODIFY | Freigabe-Phrase ruft `_check_spec_content` zusätzlich auf |
| scripts/ci_spec_gate.py | MODIFY | `_check_spec` ruft `workflow.check_spec_content`; eigene Liste/Sektionen entfallen |
| core/agents/spec-writer.md | MODIFY | Hinweis: Platzhalter-Prüfung ist rein textuell, auch Zitate zählen |
| tests/test_spec_content_gate_521.py | CREATE | neue Tests |
| tests/(8 Dateien) | MODIFY | Fixtures auf vollständige Specs |
| CHANGELOG.md | MODIFY | [Unreleased] |

### Scope Assessment
- Files: 3 Produktion, 1 Agent-Doku, 1 neu + 8 Test-Fixtures, CHANGELOG
- Estimated LoC: +90/−40 Produktion
- Risk Level: HIGH (Freigabe-Gate, alle Konsumenten)

### Technical Approach
Muster `check_adr_content`: reine Textfunktion in workflow.py, CI ruft sie auf, lokaler
Wrapper lenient (Spec fehlt/unlesbar → None). Lokal nur Specs, die die CI prüft
(`docs/specs/**.md`, nicht `_template.md`, nicht `docs/specs/fast/`). ADR-Befund im Wrapper
nur, wenn das ADR-Gate selbst abgeschaltet ist (sonst doppelte Meldung). Prüfung nur beim
Übergang über die Freigabe-Grenze, nicht bei späteren Phasenwechseln (laufende Workflows
nicht nachträglich sperren). Ältere workflow.py-Kopie ohne `check_spec_content` → CI meldet
Problem mit Update-Hinweis (fail-closed wie fehlendes workflow.py beim Briefing).

### Open Questions
- keine
