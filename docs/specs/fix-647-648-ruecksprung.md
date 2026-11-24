---
entity_id: fix-647-648-ruecksprung
type: bugfix
created: 2026-11-24
updated: 2026-11-24
status: draft
version: "1.0"
workflow: fix-647-648-ruecksprung
tags: [workflow, ruecksprung, po-briefing, auto-approve, endstate]
---

# Rücksprung verwirft alte Freigabe-Grundlage; endstate bevorzugt den aktiven Workflow (Issues #647, #648, Schnitt 2 von Epic #649)

## Approval

- [ ] Approved

## Purpose

Nach einem Rücksprung auf Analyse oder Spec (#647: `phase4_approved` nach `phase3_spec`, #648: `phase6_implement` nach `phase2_analyse`) blieb das alte PO-Briefing stehen. Dadurch meldete `next_step()` die (Auto-)Freigabe statt `/30-write-spec`, und `auto-approve` hätte eine widerlegte, unveränderte Spec erneut freigeben können. Künftig gilt das alte Briefing nach einem Rücksprung als überholt und wird in einer Historie aufbewahrt; der nächste Schritt ist wieder die Spec. Dazu kommt der Nebenbefund: `endstate <N>` soll bei mehreren Treffern derselben Nummer den aktiven Workflow nehmen statt eines abgeschlossenen Vorgängers.

## Source

- **File:** `core/hooks/workflow.py`, `core/commands/30-write-spec.md`
- **Identifier:** `_reset_approvals_on_backstep`, `cmd_phase`, `next_step`, `_auto_approval_pending`, `cmd_auto_approve`, `cmd_set_briefing`, `_apply_spec_approval`, `_SET_FIELD_PROTECTED`, `_deploy_status_target`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow._reset_approvals_on_backstep` (#405, #561) | function | Zentraler Rücksprung-Reset; wird um das Verwerfen des Briefings erweitert |
| `workflow.next_step`, `expected_footer_command` | function | Eine Quelle für Fußzeile, Plan, Herdr-Bericht und `footer_gate` |
| `workflow._auto_approval_pending`, `cmd_auto_approve` | function | Auto-Freigabe im Auto-Modus (#470); entscheiden nach dem Reset von selbst auf `human` |
| `workflow.cmd_set_briefing`, `_apply_spec_approval` | function | Löschen das Flag `spec_rework` |
| `workflow._SET_FIELD_PROTECTED`, `cmd_set_field` (#379) | dict/function | Bestehendes Muster, Gate-Felder per `set-field` zu sperren |
| `workflow._deploy_status_target`, `_read_active`, `cmd_endstate` (#550) | function | Auflösung von `endstate <N>` |
| `core/hooks/footer_gate.py`, `core/hooks/herdr_bridge.py` | hook/utility | Konsumenten von `next_step()`; bleiben unverändert |
| `docs/specs/feat-470-spec-ampel.md`, `docs/specs/fix-550-endzustand.md` | spec | Vorgänger-Verhalten, das erhalten bleibt |
| `tests/test_rueckspruung_405.py`, `test_spec_ampel_470.py`, `test_endzustand_550.py`, `test_nacharbeit_555.py` | tests | Müssen grün bleiben |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | Reset verschiebt `po_briefing` nach `po_briefing_history` und setzt `spec_rework`; `next_step` meldet bei `spec_rework` `/30-write-spec`; `cmd_set_briefing` und `_apply_spec_approval` löschen das Flag; `_SET_FIELD_PROTECTED` sperrt beide neuen Felder; `_deploy_status_target` mit neuer Rangfolge |
| core/commands/30-write-spec.md | MODIFY | Ein Satz: Nach einem Rücksprung ist ein neues Briefing Pflicht |
| skills/*/SKILL.md | REGENERATE | `python3 scripts/sync_skills.py` |
| tests/test_ruecksprung_briefing_647.py | CREATE | Regressionstests zu allen ACs |
| CHANGELOG.md | MODIFY | Eintrag zu #647/#648 in der Fassung 4.20.2 |
| .claude-plugin/plugin.json | MODIFY | Patch-Version 4.20.2 |

### Estimated Changes

- Files: 1 neu, 4 geändert (plus regenerierte Skills)
- LoC: ca. +45/-5 Produktion, +110 Test (höchstens ±250 gesamt)
- Risk Level: HIGH (Freigabe-Gate, kritischer Pfad), Änderung eng begrenzt

## Implementation Details

Entscheidung A + B2 + C (siehe Analyse in `docs/context/fix-647-648-ruecksprung.md`).

**A, Rücksprung verwirft die Grundlage.** In `_reset_approvals_on_backstep` gilt: Liegt das Ziel vor `phase4_approved` und existiert `po_briefing` (auch aus `phase3_spec` heraus nach `set-briefing`), wird es per `pop` entfernt und als letzter Eintrag an `po_briefing_history` gehängt: `{entry, reason: "backstep <von>-><nach>", at}`. Die Historie behält höchstens die letzten 5 Einträge. Nur wenn vorher ein Briefing existierte, wird `spec_rework = True` gesetzt; sonst würde das Flag bei Fast Track oder Kill-Switch ohne Briefing hängen bleiben. `spec_file` bleibt stehen, weil `/30-write-spec` es überschreibt. Vorwärtswechsel und Rücksprünge auf Ziele ab `phase4_approved` lassen `po_briefing` unberührt.

**B2, `next_step` ohne I/O.** In `phase3_spec` liefert `next_step` den Freigabe-Schritt nur bei `spec_file and not spec_rework`, sonst `/30-write-spec`. `expected_footer_command` ergibt damit `/30-write-spec #647`. `cmd_set_briefing` löscht `spec_rework` nach erfolgreicher Registrierung, `_apply_spec_approval` löscht es zur Sicherheit ebenfalls.

**Auto-Freigabe.** Mit verschobenem Briefing liefert `auto-approve` bereits heute `human` („Kein unabhängiges PO-Briefing registriert“), und `_auto_approval_pending` ist False; das wird per Test festgeschrieben, ohne neue Logik.

**Sperre per `set-field`.** Das bestehende Muster ist `_SET_FIELD_PROTECTED` (Feld → Hinweis auf den zuständigen Befehl, `cmd_set_field` blockt mit Exit 1). `po_briefing_history` und `spec_rework` kommen mit Hinweis „wird von workflow.py phase / set-briefing geführt“ hinein. Eine `_FIELD_HINTS`-Tabelle existiert nicht und wird nicht eingeführt.

**C, `endstate`-Rangfolge.** `_deploy_status_target` wählt bei mehreren laufenden Treffern: exakter Name, dann der aktive Workflow (sofern unter den Treffern; `_read_active` in try/except, ein `SystemExit` wegen fehlendem aktiven Workflow bricht nichts ab), dann ein nicht `phase8_complete`er Treffer, dann der jüngste nach mtime. Das Archiv-Verhalten bleibt.

## Expected Behavior

- **Input:** `workflow.py phase <ziel>` mit Ziel vor `phase4_approved` bei vorhandenem Briefing; `next_step`/`expected_footer_command`; `auto-approve`; `set-briefing`; Spec-Freigabe; `set-field`; `endstate <N>`
- **Output:** Nach dem Rücksprung `/30-write-spec` als Pflicht-Befehl, `AUTO_APPROVE=human`; `endstate <N>` löst auf den aktiven Workflow auf
- **Side effects:** neue State-Felder `po_briefing_history` (Liste, höchstens 5) und `spec_rework` (Bool); `po_briefing` verschwindet beim Rücksprung aus dem State

## Known Limitations

- Altfälle, die schon vor dieser Änderung zurückgesprungen sind, haben kein Flag und behalten das bisherige Verhalten (akzeptiert).
- Der Vertrag „`spec_file` ⇒ Freigabe-Schritt“ gilt für den Normalablauf weiter; die allgemeine Regel „Pflicht-Briefing fehlt ⇒ `/30-write-spec`“ (B1) ist bewusst nicht umgesetzt.
- Die Historie dient dem Nachweis, es gibt keinen Befehl, der ein altes Briefing wieder einsetzt.
- Herdr-Auto-/clear wird mit Epic #649 zurückgebaut; der Fix gilt unabhängig davon für `next_step` allgemein (Cloud, Fußzeile, Plan).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Nach einem Rücksprung auf Analyse oder Spec zeigt die Fußzeile `/30-write-spec` statt der Freigabe, und die Auto-Freigabe gibt eine widerlegte Spec nicht mehr frei
- [ ] `endstate <N>` meldet bei Vorgänger und aktivem Workflow derselben Nummer den aktiven Workflow
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün, besonders die Tests zu #405, #470, #550, #555)

## Acceptance Criteria

- **AC-1:** Given ein Workflow ab `phase4_approved` (oder in `phase3_spec` nach `set-briefing`) mit registriertem `po_briefing` / When `workflow.py phase` auf ein Ziel vor `phase4_approved` springt / Then fehlt `po_briefing` im State und der letzte Eintrag von `po_briefing_history` enthält `entry`, `reason` „backstep <von>-><nach>“ und `at`
  - Test: tests/test_ruecksprung_briefing_647.py::test_backstep_moves_briefing_to_history

- **AC-2:** Given ein Workflow, dessen Historie schon 5 Einträge hat / When ein weiterer Rücksprung ein Briefing verwirft / Then hat `po_briefing_history` genau 5 Einträge, der neue steht zuletzt und der älteste ist entfallen
  - Test: tests/test_ruecksprung_briefing_647.py::test_history_keeps_at_most_five

- **AC-3:** Given ein Workflow in `phase3_spec` mit `spec_file` und `spec_rework=true` / When `next_step` und `expected_footer_command` abgefragt werden / Then lautet der Schritt `/30-write-spec` bzw. die Fußzeile `/30-write-spec #647`; ohne das Flag bleibt es beim Freigabe-Schritt (`APPROVAL_STEP` bzw. `AUTO_APPROVAL_STEP`)
  - Test: tests/test_ruecksprung_briefing_647.py::test_next_step_after_backstep_is_write_spec

- **AC-4:** Given ein Rücksprung im Auto-Modus bei unveränderter Spec-Datei und unveränderter alter Briefing-Datei / When `workflow.py auto-approve` läuft / Then ist `AUTO_APPROVE=human`, die Spec bleibt nicht freigegeben und `_auto_approval_pending` ist False
  - Test: tests/test_ruecksprung_briefing_647.py::test_auto_approve_after_backstep_stays_human

- **AC-5:** Given ein Workflow mit gesetztem `spec_rework` / When `set-briefing` erfolgreich ein neues Briefing registriert oder die Spec freigegeben wird (`_apply_spec_approval`) / Then ist `spec_rework` gelöscht und `next_step` meldet wieder den Freigabe-Schritt
  - Test: tests/test_ruecksprung_briefing_647.py::test_set_briefing_and_approval_clear_rework

- **AC-6:** Given ein Rücksprung ohne vorheriges Briefing (Fast Track oder Kill-Switch), ein Vorwärtswechsel und ein Rücksprung auf ein Ziel ab `phase4_approved` / When `workflow.py phase` ausgeführt wird / Then wird `spec_rework` nicht gesetzt und `po_briefing` bleibt unverändert
  - Test: tests/test_ruecksprung_briefing_647.py::test_no_rework_without_briefing_and_no_change_on_forward

- **AC-7:** Given ein aktiver Workflow / When `workflow.py set-field po_briefing_history …` oder `set-field spec_rework …` aufgerufen wird / Then endet der Aufruf mit Exit 1 und der Meldung „per set-field gesperrt“ samt Hinweis auf den zuständigen Befehl, und der State bleibt unverändert
  - Test: tests/test_ruecksprung_briefing_647.py::test_set_field_blocks_new_fields

- **AC-8:** Given mehrere laufende Workflows zur Nummer 647 (ein Vorgänger in `phase8_complete` und der aktive Workflow) / When `workflow.py endstate 647` bzw. `_deploy_status_target` auflöst / Then gilt die Rangfolge exakter Name, aktiver Workflow, nicht `phase8_complete`, jüngster nach mtime; ohne aktiven Workflow (SystemExit) bricht die Auflösung nicht ab, und archivierte Workflows werden wie bisher gefunden
  - Test: tests/test_ruecksprung_briefing_647.py::test_endstate_prefers_active_workflow

- **AC-9:** Given die bestehenden Tests zu Rücksprung-Reset, Spec-Ampel, Endzustand und Nacharbeit / When sie nach der Änderung laufen / Then sind alle grün
  - Test: tests/test_rueckspruung_405.py, tests/test_spec_ampel_470.py, tests/test_endzustand_550.py, tests/test_nacharbeit_555.py (Regressionslauf)

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_ruecksprung_briefing_647.py` (RED zuerst, dann GREEN; Szenarien #647 `phase4_approved` -> `phase3_spec` und #648 `phase6_implement` -> `phase2_analyse`)
- Regression: `pytest tests/test_rueckspruung_405.py tests/test_spec_ampel_470.py tests/test_endzustand_550.py tests/test_nacharbeit_555.py tests/test_skills_sync.py`
- `python3 -m py_compile core/hooks/workflow.py`
- `python3 scripts/sync_skills.py --check` (keine Drift in `skills/`)

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine neue (Alternative B1 verworfen)
- **Rationale:** Gewählt ist A + B2 + C: Das Briefing wird beim Rücksprung nach `po_briefing_history` verschoben (nichts wird still gelöscht), ein Flag `spec_rework` macht `next_step` ohne I/O eindeutig, und `endstate` bevorzugt den aktiven Workflow. **Verworfene Alternative B1:** `next_step` meldet allgemein `/30-write-spec`, sobald ein Pflicht-Briefing fehlt. Grund der Ablehnung: `next_step` läuft in jedem Hook, B1 hieße dort Config, Spec und Briefing zu lesen, und 6 bis 10 bestehende Tests würden kippen. Auswirkung auf bestehende Entscheidungen: Der Vertrag „`spec_file` ⇒ Freigabe-Schritt“ bleibt für den Normalablauf bestehen; Ausnahmen (Kill-Switch, Fast Track) behalten `approved`, weil das Flag nur bei vorherigem Briefing gesetzt wird.

## Changelog

- 2026-11-24: Initial spec created
