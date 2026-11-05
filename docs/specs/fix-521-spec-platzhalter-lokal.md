---
entity_id: fix-521-spec-platzhalter-lokal
type: bugfix
created: 2026-11-05
updated: 2026-11-05
status: draft
version: "1.0"
workflow: fix-521-spec-platzhalter-lokal
tags: [ci-spec-gate, spec, placeholder, approval, shift-left]
---

# Spec-Inhaltsprüfung des CI-Gates lokal bei der Freigabe (Issue #521)

## Approval

- [ ] Approved

## Purpose

Das CI-Spec-Gate lehnt Specs ab, die lokal ohne Warnung freigegeben wurden (Fall #508: ein AC zitierte eine Testzeile mit dem Wort TODO samt Doppelpunkt; Ampel grün, CI rot, Rücksprung nach `phase3_spec`, neues Briefing, neue Freigabe). Ursache: Die Spec-Inhaltsprüfung (Pflicht-Sektionen, Platzhalter, AC-N, ADR) steht nur in `scripts/ci_spec_gate.py`; die Platzhalter-Liste existiert zusätzlich in `workflow.py` für das Briefing, mit abweichendem Inhalt. Künftig liegt die Regel einmal in `workflow.py` (`check_spec_content`, `PLACEHOLDER_MARKERS`), das CI-Gate ruft sie auf, und die Freigabe (manuell, per `workflow.py phase` und per `auto-approve`) blockt mit derselben Meldung. Entscheidung des PO: volle CI-Parität, nicht nur Platzhalter.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `PLACEHOLDER_MARKERS`, `find_placeholder`, `SPEC_REQUIRED_SECTIONS`, `check_spec_content`, `_check_spec_content` (alle neu); geändert: `check_briefing_content`, `_validate_transition`, `_auto_approve_decision`; entfällt: `_PO_BRIEFING_PLACEHOLDERS`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.check_adr_content` (#230-Reihe) | function | liefert den ADR-Befund; Vorbild für das Muster eine Regel, zwei Aufrufer |
| `workflow._check_adr` | function | lokaler Wrapper mit Kill-Switch, Vorbild für `_check_spec_content` |
| `workflow.check_briefing_content` | function | nutzt künftig `PLACEHOLDER_MARKERS` und `find_placeholder` |
| `hook_utils.extract_ac_entries` | function | AC-N-Parsing, unverändert |
| `scripts/ci_spec_gate.py::_check_spec` | function | wird zum dünnen Aufrufer von `workflow.check_spec_content` |
| `phase_listener.py` Freigabe-Zweig | hook | bekommt den Spec-Befund neben ADR und Briefing |
| `config.yaml` `ci_spec_gate.enabled` | config | Kill-Switch gilt auch für die lokale Prüfung |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `PLACEHOLDER_MARKERS`, `find_placeholder`, `SPEC_REQUIRED_SECTIONS`, `check_spec_content`, `_check_spec_content`; Aufruf in `_validate_transition` und `_auto_approve_decision`; `_PO_BRIEFING_PLACEHOLDERS` entfällt |
| core/hooks/phase_listener.py | MODIFY | Freigabe-Zweig ruft `_check_spec_content(wf_data)` zusätzlich auf |
| scripts/ci_spec_gate.py | MODIFY | `SPEC_PLACEHOLDERS` und `SPEC_REQUIRED_SECTIONS` entfallen; `_check_spec` ruft `workflow.check_spec_content` |
| core/agents/spec-writer.md | MODIFY | Qualitätsregel Keine Platzhalter präzisiert |
| tests/test_spec_content_gate_521.py | CREATE | Tests zu allen AC |
| tests/test_adr_gate.py, test_auto_approve_env_487.py, test_autoclear_transition_497.py, test_herdr_sidebar_466.py, test_po_briefing_gate.py, test_red_marker_phase_gate_f004.py, test_rueckspruung_405.py, test_spec_ampel_470.py | MODIFY | Fixtures geben CI-vollständige Specs frei (Assertions unverändert; Prototyp: 32 Tests) |
| CHANGELOG.md | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes

- Files: 1 neu, 12 geändert
- LoC: +90/−40 Produktion / +300 Test inklusive Fixture-Umstellung
- Risk Level: HIGH (Freigabe-Gate, wirkt in allen Konsumenten-Projekten)

## Implementation Details

**`workflow.PLACEHOLDER_MARKERS`** — einzige Liste: sechs kleingeschriebene Marker: eckige Klammer auf mit todo, eckige Klammer auf mit tbd, die Wörter todo, fixme und xxx je mit Doppelpunkt sowie spitze Klammer auf mit platzhalter. Das ist inhaltlich die bisherige Briefing-Liste; `_PO_BRIEFING_PLACEHOLDERS` entfällt, das Briefing-Verhalten bleibt gleich. **`find_placeholder(content)`** liefert den ersten Treffer (Reihenfolge der Liste, case-insensitive, rein textuell, Zitate zählen) oder `None`; Briefing- und Spec-Prüfung nutzen ihn.

**`SPEC_REQUIRED_SECTIONS`** zieht mit gleichen Regexen aus `ci_spec_gate.py` nach `workflow.py` um.

**`check_spec_content(content) -> list[str]`** — reine Textfunktion, liefert alle Befunde in der Reihenfolge und mit dem Wortlaut der bisherigen CI-Prüfung, ohne Pfad-Präfix: fehlende Pflicht-Sektionen, Platzhalter (erster Treffer, Text „enthält noch einen Platzhalter ('<marker>').“), AC-Sektion ohne AC-N-Einträge, AC-N kürzer als 30 Zeichen, ADR-Befund aus `check_adr_content`. Leere Liste bedeutet in Ordnung.

**`_check_spec_content(data, config=None) -> str | None`** — lokaler Wrapper, lenient wie `_check_adr`:

1. Kill-Switch `ci_spec_gate.enabled: false` führt zu `None`. `config` kommt von außen (auto-approve: `trusted_config()`), sonst `load_config()`; ein Config-Fehler lässt die Prüfung AN.
2. Nur Specs, die die CI prüft: `spec_file` unter `docs/specs/`, Endung `.md`, nicht `_template.md`, nicht unter `docs/specs/fast/`; sonst `None`.
3. Spec fehlt oder ist unlesbar: `None`.
4. Der ADR-Befund entfällt, solange das ADR-Gate aktiv ist (`adr_gate.enabled` nicht false), weil `_check_adr` ihn dann schon meldet; ist das ADR-Gate aus, meldet der Wrapper ihn wie die CI.
5. Meldung: „Spec besteht das CI-Spec-Gate nicht: “ plus Befunde, verbunden mit „ | “.

**Aufrufe:** `_validate_transition` (feature und feature-fast) nach dem Briefing-Gate, nur wenn die aktuelle Phase vor `phase4_approved` liegt; spätere Phasenwechsel laufender Workflows werden nicht nachträglich gesperrt. `_auto_approve_decision` nach dem Briefing-Gate mit `config`: Ergebnis `("human", "Spec: " + Meldung, [])`. `phase_listener.py`: Import-Fehler führt zu `None`, der Grund erscheint in der vorhandenen Block-Meldung neben ADR und Briefing.

**`ci_spec_gate._check_spec`** ruft `workflow.check_spec_content(content)` und hängt jeden Befund mit Präfix `<rel>: ` an. Ist `workflow` nicht ladbar, kommt ein Befund „workflow.py nicht gefunden …“. Hat die geladene Kopie kein `check_spec_content` (veraltete Projekt-Kopie), kommt ein Befund mit Hinweis auf `setup.py --update` (fail-closed). Ausgabe und Exit-Code sonst unverändert; `tests/test_ci_spec_gate.py` bleibt unverändert grün.

**`core/agents/spec-writer.md`:** Die Regel Keine Platzhalter nennt, dass die Prüfung rein textuell und case-insensitive ist, auch zitierte Zeilen zählen (etwa der Kommentar mit TODO und Doppelpunkt aus einer Testzeile), und dass `workflow.PLACEHOLDER_MARKERS` die Liste ist.

## Expected Behavior

- **Input:** Spec-Datei eines Workflows beim Übergang nach `phase4_approved`
- **Output:** Eine Spec, die das CI-Gate ablehnt, kommt lokal nicht durch die Freigabe; die Meldung enthält jeden CI-Befund-Text. Eine vollständige Spec läuft in allen drei Pfaden durch.
- **Side effects:** keine; kein State, keine Dateien

## Known Limitations

- `set-briefing` prüft die Spec nicht; ein Befund fällt erst bei der Freigabe auf, also vor dem Freigabe-Schritt statt erst in der CI.
- Die CI wird für Specs um den Marker für spitze Klammer plus „platzhalter“ strenger (kein Treffer in bestehenden Specs, per grep geprüft).
- Laufende Workflows jenseits `phase4_approved` werden nicht nachträglich geprüft.
- Pfad-Regel nur `docs/specs/` wie in der CI; eine abweichende `specs.base_path` wird wie dort nicht geprüft.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Eine Spec, die das CI-Gate ablehnt, kommt lokal nicht durch die Freigabe (manuell, `phase phase4_approved`, `auto-approve`)
- [ ] Im Code gibt es nur noch eine Platzhalter-Liste (`PLACEHOLDER_MARKERS`), per Test belegt
- [ ] `tests/test_ci_spec_gate*.py` und der übrige Regressionslauf (`pytest tests/`) bleiben grün

## Acceptance Criteria

Testaufbau: Specs als echte Dateien in `tmp_path` unter `docs/specs/`, Workflow-State als JSON, Aufruf von `workflow.py`, `phase_listener.py` und `scripts/ci_spec_gate.py` als Subprozess bzw. direkter Funktionsaufruf. Kein Mock der Prüfregel.

- **AC-1:** Given eine Spec, in deren AC das Wort TODO mit Doppelpunkt als Zitat einer Testzeile steht / When der Listener die Freigabe-Phrase „approved“ verarbeitet / Then bleibt `spec_approved` ungesetzt und die Block-Meldung nennt den Platzhalter
  - Test: tests/test_spec_content_gate_521.py::TestApprovalBlocked::test_listener_blocks_placeholder_in_spec

- **AC-2:** Given dieselbe Spec / When `workflow.py auto-approve` läuft / Then lautet die Ausgabe `AUTO_APPROVE=human` und `REASON` beginnt mit „Spec: “ und nennt den Platzhalter
  - Test: tests/test_spec_content_gate_521.py::TestApprovalBlocked::test_auto_approve_returns_human_with_reason

- **AC-3:** Given dieselbe Spec in `phase3_spec` mit gültigem Briefing / When `workflow.py phase phase4_approved` läuft / Then wird der Übergang blockiert und die Meldung nennt den Platzhalter
  - Test: tests/test_spec_content_gate_521.py::TestApprovalBlocked::test_phase_transition_blocks_placeholder_in_spec

- **AC-4:** Given dieselbe Spec / When `scripts/ci_spec_gate.py` sie prüft / Then lehnt es mit Exit 1 ab und jeder CI-Befund-Text ohne Pfad-Präfix steckt in der lokalen Meldung (Parität)
  - Test: tests/test_spec_content_gate_521.py::TestCiParity::test_local_message_contains_every_ci_finding

- **AC-5:** Given eine Spec ohne Pflicht-Sektion Test Plan bzw. mit einem AC-N unter 30 Zeichen / When die Freigabe versucht wird / Then blockt der Listener ebenso, mit dem Wortlaut der CI
  - Test: tests/test_spec_content_gate_521.py::TestApprovalBlocked::test_missing_section_and_short_ac_block_locally

- **AC-6:** Given eine vollständige Spec ohne Platzhalter / When Listener, `phase phase4_approved` und `auto-approve` laufen / Then geht die Freigabe in allen drei Pfaden durch
  - Test: tests/test_spec_content_gate_521.py::TestApprovalPasses::test_complete_spec_passes_all_three_paths

- **AC-7:** Given eine Platzhalter-Spec unter `docs/specs/fast/` bzw. außerhalb von `docs/specs/` / When die lokale Prüfung läuft / Then liefert `_check_spec_content` `None`
  - Test: tests/test_spec_content_gate_521.py::TestScopeOfCheck::test_fast_track_and_foreign_paths_not_checked

- **AC-8:** Given `ci_spec_gate.enabled: false` in der Config / When die Platzhalter-Spec freigegeben wird / Then wird sie lokal nicht geprüft
  - Test: tests/test_spec_content_gate_521.py::TestScopeOfCheck::test_kill_switch_disables_local_check

- **AC-9:** Given eine Spec mit leerem ADR-Feld und aktivem ADR-Gate / When der Listener blockt / Then steht genau eine ADR-Meldung in der Block-Meldung; bei abgeschaltetem ADR-Gate meldet der Spec-Wrapper den ADR-Befund
  - Test: tests/test_spec_content_gate_521.py::TestAdrNotDuplicated::test_single_adr_message_in_listener_block

- **AC-10:** Given ein Workflow in `phase6_implement` mit Platzhalter in der Spec / When `workflow.py phase phase7_validate` läuft / Then blockt die Spec-Prüfung den Übergang nicht
  - Test: tests/test_spec_content_gate_521.py::TestScopeOfCheck::test_later_phase_transition_not_blocked

- **AC-11:** Given der Quelltext in `core/hooks/*.py` und `scripts/*.py` / When die Definitionen gezählt werden / Then gibt es genau eine Definition `PLACEHOLDER_MARKERS`, kein `SPEC_PLACEHOLDERS` in `ci_spec_gate` und kein `_PO_BRIEFING_PLACEHOLDERS` in `workflow`; ein Briefing mit dem Marker für spitze Klammer plus „platzhalter“ wird weiter abgelehnt
  - Test: tests/test_spec_content_gate_521.py::TestSingleList::test_only_one_placeholder_list

- **AC-12:** Given ein Projekt, dessen `workflow.py` kein `check_spec_content` besitzt / When das CI-Gate eine Spec prüft / Then meldet es einen Befund mit Hinweis `setup.py --update` und endet mit Exit 1
  - Test: tests/test_spec_content_gate_521.py::TestCiParity::test_old_workflow_copy_fails_closed_with_update_hint

- **AC-13:** Given `CHANGELOG.md` / When gelesen / Then steht ab `## [Unreleased]` (unter `[Unreleased]` oder in einem beliebigen Versionsabschnitt, release-fest wie #409 und #508) ein Eintrag, der `#521` nennt
  - Test: tests/test_spec_content_gate_521.py::test_changelog_mentions_521

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_spec_content_gate_521.py`
- `pytest tests/test_ci_spec_gate.py tests/test_adr_gate.py tests/test_po_briefing_gate.py tests/test_auto_approve_env_487.py tests/test_spec_ampel_470.py tests/test_rueckspruung_405.py`
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py core/hooks/phase_listener.py scripts/ci_spec_gate.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Verschiebung einer bestehenden CI-Regel nach links nach dem Muster von `check_adr_content` und `check_briefing_content`: reine Textfunktion in `workflow.py`, CI und Freigabe rufen sie auf. Kein neues State-Feld, kein neues Gate, per Kill-Switch `ci_spec_gate.enabled` abschaltbar und durch Rückbau der Aufrufe reversibel. Verworfen: (a) nur die Platzhalter lokal prüfen, der Rest bleibt in der CI — vom PO verworfen, weil Pflicht-Sektionen und AC-N dieselbe Rücksprung-Schleife auslösen; (b) `ci_spec_gate` aus den Hooks importieren statt die Regel in `workflow.py` zu halten — Hooks importieren keine Scripts, und im Konsumenten-Projekt liegt das Script nicht neben den Hooks; (c) zwei Listen synchron halten — widerspricht der Regel, dass das Gate keine Regeln dupliziert; (d) Prüfung bei jedem Phasenwechsel — würde laufende Workflows nachträglich sperren.

## Changelog

- 2026-11-05: Initial spec created
