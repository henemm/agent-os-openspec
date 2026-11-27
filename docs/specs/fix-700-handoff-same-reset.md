---
entity_id: fix-700-handoff-same-reset
type: bugfix
created: 2026-11-27
updated: 2026-11-27
status: draft
version: "1.0"
workflow: fix-700-handoff-same-reset
tags: [workflow, herdr, handoff, phasenwechsel, bugfix, epic-649]
---

# Übergabe am Phasenwechsel: Doppelstart-Vermerk nach Rücksprung zurücksetzen (Issue #700)

## Approval

- [ ] Approved

## Purpose

`workflow.py handoff --same --start` (#696) merkt sich nach erfolgreichem Start den Vermerk `handoff_same` (Phase, Folgebefehl) und meldet bei gleichem Wert `STARTED=already`. Der Vermerk wird nie zurückgesetzt: Kehrt ein Workflow nach einem BROKEN-Urteil in dieselbe Phase mit demselben Folgebefehl zurück, meldet die Übergabe `already`, es läuft aber keine Nachfolgerin, und der Workflow steht. Neu: Der Vermerk wird bei jedem Phasenwechsel und beim Abschluss verworfen, wie schon `waiting_on` (#550).

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `record_transition` (einziger Wechselpfad, #111), `cmd_complete`; Leser des Vermerks: `_handoff_same_start`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.record_transition` | function | Einziger Pfad für Phasenwechsel (Aufrufer: `cmd_phase`, Freigabe-Pfad, `phase_listener.py`); verwirft bereits `waiting_on` (#550) und `spec_rework` (#647) |
| `workflow.cmd_complete` | function | Setzt `phase8_complete` ohne `record_transition`, verwirft `waiting_on` selbst |
| `workflow._handoff_same_start` | function | Einziger Leser von `handoff_same`; Verhalten unverändert |
| State-Feld `handoff_same` | state | Vermerk `{phase, next, at}` aus #696 |
| tests/test_feat_696_handoff_same.py | test | Helfer (Fake-herdr, Fake-`claude`, Test-Env) und AC-12 als Regressionsschutz |
| docs/specs/feat-696-handoff-phasenwechsel.md | spec | Vorarbeit; AC-12 definiert `already` innerhalb einer Phase |
| Issue #700, #696, #550, #111 | issue | Auftrag, Vorarbeit, Muster, einziger Wechselpfad |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `data.pop("handoff_same", None)` in `record_transition` und in `cmd_complete`, je neben dem `waiting_on`-Pop (ca. 4 LoC) |
| tests/test_fix_700_handoff_same_reset.py | CREATE | Tests zu den ACs (Helfer aus tests/test_feat_696_handoff_same.py wiederverwenden bzw. analog) |
| CHANGELOG.md | MODIFY | Eintrag 4.28.1 mit Verweis auf #700 |
| .claude-plugin/plugin.json | MODIFY | Version 4.28.1 |
| CLAUDE.md | MODIFY | Versionszeile 4.28.1 |

Nicht geändert: Befehlstexte und Skills, `herdr_bridge.py`, `hooks/hooks.json`, `_handoff_same_start` (Vergleich über Phase und Folgebefehl bleibt), `cmd_start`.

### Estimated Changes

- Files: 1 Hook, 1 Testdatei, 3 Versions-/Doku-Dateien
- LoC: ca. +90/-0 (Code ca. 4, Tests ca. 80)
- Risk Level: HIGH (Hook-Code in allen Konsumenten, Workflow-State); Adversary mit zwei Runden

### Out of Scope

- Option 2 aus dem Issue (Zeitstempel `at` gegen Phaseneintritt vergleichen): mehr Logik, Format- und Uhrenabhängigkeit, kein Mehrwert
- Änderungen am Befehlstext der Phasenbefehle oder an der Übergabe-Ausgabe

## Implementation Details

1. **`record_transition`.** Neben dem bestehenden Verwerfen von `waiting_on` (#550) kommt `data.pop("handoff_same", None)`. Da `record_transition` der einzige Wechselpfad ist (#111), sind `cmd_phase`, der Freigabe-Pfad (Übergang nach `phase4_approved`) und `phase_listener.py` automatisch abgedeckt.
2. **`cmd_complete`.** Setzt `phase8_complete` ohne `record_transition`; dort kommt derselbe Pop neben den dortigen `waiting_on`-Pop.
3. **Unverändert.** `_handoff_same_start` vergleicht weiter Phase und Folgebefehl. Innerhalb derselben Phase ohne Wechsel bleibt der Vermerk stehen, der Doppelstart-Schutz (AC-12 aus #696) gilt weiter. Nach einem Wechsel fehlt der Vermerk, der Start läuft wieder.
4. **Version.** 4.28.1 (Patch, Fehlerbehebung) in `.claude-plugin/plugin.json` und der CLAUDE.md-Versionszeile; CHANGELOG-Eintrag mit Verweis auf #700.

## Expected Behavior

- **Input:** Workflow mit Vermerk `handoff_same`, anschließend ein Phasenwechsel (auch Rücksprung nach BROKEN) oder `workflow.py complete`
- **Output:** Vermerk ist aus dem Workflow-State entfernt; `handoff --same --start` in derselben Phase mit demselben Folgebefehl meldet danach `STARTED=yes` und startet genau eine Sitzung
- **Side effects:** Keine weiteren; ohne Phasenwechsel bleibt `STARTED=already`

## Known Limitations

- Der Schutz gilt je Phase zwischen zwei Wechseln. Wird innerhalb einer Phase die Übergabe nach einem Start bewusst wiederholt, bleibt es bei `already`.
- Ein Wechsel auf dieselbe Phase (`workflow.py phase <aktuelle Phase>`) verwirft den Vermerk ebenfalls, weil er über `record_transition` läuft.
- Der Echtlauf mit Herdr ist aus der Cloud nicht ausführbar; belegt ist er gegen das Fake-Binary.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Ein Workflow, der nach BROKEN in dieselbe Phase zurückkehrt, kann dort erneut eine frische Sitzung übergeben, statt stehenzubleiben (Beleg: Test AC-2)
- [ ] Der Doppelstart-Schutz innerhalb einer Phase besteht weiter und der bestehende AC-12-Test aus #696 ist grün
- [ ] Regressionslauf `pytest tests/` grün, kein `pytest.skip` zur Entschärfung, Version 4.28.1 veröffentlicht

## Acceptance Criteria

- **AC-1:** Given ein Workflow mit Vermerk `handoff_same` im State / When `workflow.py phase <andere Phase>` läuft / Then enthält der State das Feld `handoff_same` nicht mehr
  - Test: tests/test_fix_700_handoff_same_reset.py::test_phase_change_removes_handoff_same_note

- **AC-2:** Given Rücksprung phase6_implement → phase6b_adversary → phase6_implement mit Vermerk `{phase6_implement, /60-validate #N, ...}`, Fake-herdr und Fake-`claude` wie in tests/test_feat_696_handoff_same.py / When danach `workflow.py handoff --same --start` läuft / Then lautet die Ausgabe `STARTED=yes` und es gibt genau einen `tab create`-Aufruf
  - Test: tests/test_fix_700_handoff_same_reset.py::test_restart_possible_after_return_to_same_phase

- **AC-3:** Given Vermerk für die aktuelle Phase und kein Phasenwechsel / When `workflow.py handoff --same --start` erneut läuft / Then lautet die Ausgabe `STARTED=already` ohne zweiten `tab create`-Aufruf (Doppelstart-Schutz bleibt; der bestehende Test aus #696 bleibt grün)
  - Test: tests/test_fix_700_handoff_same_reset.py::test_second_start_without_phase_change_stays_already (zusätzlich unverändert: tests/test_feat_696_handoff_same.py::test_second_start_same_phase_is_already)

- **AC-4:** Given ein Workflow mit Vermerk `handoff_same` / When der Übergang nach phase4_approved über den Freigabe-Pfad (`record_transition`) läuft oder `workflow.py complete` ausgeführt wird / Then ist der Vermerk in beiden Fällen aus dem State entfernt
  - Test: tests/test_fix_700_handoff_same_reset.py::test_approval_transition_and_complete_remove_note

- **AC-5:** Given die Dateien `CHANGELOG.md`, `.claude-plugin/plugin.json` und `CLAUDE.md` / When sie gelesen werden / Then führt der CHANGELOG Version 4.28.1 mit Verweis auf #700, und plugin.json sowie die CLAUDE.md-Versionszeile nennen 4.28.1
  - Test: tests/test_fix_700_handoff_same_reset.py::test_changelog_and_version_consistent

## Test Plan

Automatische Tests, jeweils an eine AC gebunden, ohne Netzwerk, mit tmp-Projekt, Subprozess-Aufruf von `workflow.py` und einem Fake-herdr-Binary, das Aufrufe protokolliert (Helfer und Test-Env aus tests/test_feat_696_handoff_same.py wiederverwenden bzw. analog aufbauen).

- GIVEN Vermerk im State WHEN `workflow.py phase <andere Phase>` THEN Vermerk entfernt (AC-1)
- GIVEN Rücksprung phase6 → phase6b → phase6 mit Vermerk WHEN `handoff --same --start` THEN `STARTED=yes`, genau ein `tab create` (AC-2)
- GIVEN Vermerk der aktuellen Phase, kein Wechsel WHEN `handoff --same --start` zweimal THEN zweites Mal `STARTED=already`, kein zweiter Tab (AC-3)
- GIVEN Vermerk WHEN Freigabe-Übergang nach phase4_approved bzw. `complete` THEN Vermerk entfernt (AC-4)
- GIVEN CHANGELOG, plugin.json, CLAUDE.md WHEN gelesen THEN 4.28.1 und Verweis auf #700 (AC-5)

Läufe:

- `pytest tests/test_fix_700_handoff_same_reset.py tests/test_feat_696_handoff_same.py` (RED zuerst, dann GREEN)
- Regressionslauf: `pytest tests/`
- `python3 -m py_compile core/hooks/workflow.py`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Fehlerbehebung nach bestehendem Muster (#550: `waiting_on` wird aus demselben Grund bei jedem Wechsel verworfen); keine neue Architekturebene, kein neuer Hook, keine Config. `record_transition` ist der einzige Wechselpfad (#111), daher deckt ein Pop dort alle Aufrufer ab. Alternative Option 2 (Zeitstempelvergleich von `at` mit dem Phaseneintritt) verworfen: mehr Logik, Format- und Uhrenabhängigkeit, gleicher Effekt. Reversibel: Entfernen der zwei Zeilen stellt das alte Verhalten wieder her.

## Changelog

- 2026-11-27: Initial spec created
