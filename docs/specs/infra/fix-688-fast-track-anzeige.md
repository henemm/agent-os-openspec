---
entity_id: fix-688-fast-track-anzeige
type: bugfix
created: 2026-11-26
updated: 2026-11-26
status: draft
version: "1.0"
workflow: fix-688-fast-track-anzeige
tags: [fast-track, next-step, endzustand, plan-pane, auto-modus]
---

# Fast Track: Anzeige nennt nach Freigabe /50-implement (Issue #688)

## Approval

- [ ] Approved

## Purpose

Im kleinen Ablauf (Fast Track, `feature-fast`) nennen Seitenleiste, Plan-Anzeige, Hook-Hinweis und Fußzeilen-Prüfung nach der Freigabe (`phase4_approved`) den Testschritt `/40-tdd-red`, den dieser Ablauf überspringt. Danach nennen sie `/50-implement`. Außerdem zeigt die Plan-Anzeige nach einer automatischen Freigabe `❗ Du:`, obwohl Claude selbst weiterarbeitet; dort steht dann `⏳ Läuft noch: Claude führt … selbst aus`.

## Source

- **File:** `core/hooks/workflow.py`
- **Identifier:** `next_step(data)`, `_end_state_open(data, self_driven)`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/workflow.py` `expected_footer_command`, `status_note` | function | lesen `next_step`; erben den Fix ohne eigene Änderung |
| `core/hooks/herdr_bridge.py` `build_report` | hook utility | Token `next` aus `expected_footer_command`, Schlusszeile aus `end_state`; unverändert |
| `core/hooks/footer_gate.py` | hook | prüft den erwarteten Befehl in der Fußzeile; unverändert |
| `workflow.py` `record_approval` / `auto-approve` | function | Auto-Freigabe schreibt `approvals`-Eintrag `{"gate": "spec", "by": "auto"}` |
| `tests/test_endzustand_550.py`, `tests/test_nacharbeit_555.py`, `tests/test_footer_gate_234.py`, `tests/test_status_note_325.py`, `tests/test_spec_ampel_470.py` | test | bestehende Pins, bleiben unverändert grün |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| core/hooks/workflow.py | MODIFY | `next_step`: Fast-Track-Fall in `phase4_approved`; `_end_state_open`: ⏳ nach Auto-Freigabe in `phase4_approved` |
| tests/test_fast_track_anzeige_688.py | CREATE | Tests je Fall |
| CHANGELOG.md | MODIFY | Eintrag `[4.26.6]` |
| .claude-plugin/plugin.json, CLAUDE.md, README.md | MODIFY | Version 4.26.6 |
| skills/*/SKILL.md, .claude/commands/*.md | MODIFY | Versions-Marker 4.26.6 (regeneriert per `python3 scripts/sync_skills.py`) |

### Estimated Changes

- Files: 1 Quelldatei, 1 neuer Test, Versionsdateien
- LoC: Quelltext ca. +15, Test ca. +90
- Risk Level: HIGH (Hook-Code in `workflow.py`, speist das Fußzeilen-Gate; zwei Adversary-Runden)

## Implementation Details

- `next_step`: Vor dem Rückgriff auf `NEXT_STEP[phase]` gilt: `phase == "phase4_approved"` und `data.get("workflow_type") == "feature-fast"` → `"/50-implement"`. `NEXT_STEP` selbst bleibt unverändert (voller Prozess weiter `/40-tdd-red`).
- Neue reine Hilfsfunktion `_auto_approved(data) -> bool`: True, wenn der jüngste Eintrag in `data["approvals"]` (Liste, fehlertolerant) mit `gate == "spec"` `by == "auto"` hat. Kein Config-Zugriff, wirft nie.
- `_end_state_open`: Bei Slash-Schritt und (`self_driven` oder (`current_phase == "phase4_approved"` und `_auto_approved(data)`)) → `_end("waiting", END_WAITING.format(f"Claude führt {cmd} selbst aus"), cmd)`. Der Befehl steht damit weiter in der Zeile, das Fußzeilen-Gate findet ihn.
- `end_state` bleibt rein; `render_plan`, `endstate`-CLI und Seitenleiste nutzen denselben Pfad.

## Expected Behavior

- **Input:** Workflow-State in `phase4_approved` (Typ `feature-fast` oder `feature`, Freigabe durch `auto` oder `po`)
- **Output:** `next_step` = `/50-implement` (Fast Track) bzw. `/40-tdd-red` (voller Prozess); Endzustand ⏳ nach Auto-Freigabe, ❗ nach manueller Freigabe
- **Side effects:** keine; nur Anzeige und erwarteter Fußzeilen-Befehl

## Known Limitations

- Nach einer manuellen Freigabe („approved“ durch den PO) im Auto-Modus bleibt `❗ Du:` im Plan stehen, bis Claude die Phase wechselt (nicht Teil von #688).
- Ältere States ohne `approvals`-Liste gelten als manuell freigegeben (❗ wie bisher).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)
- [ ] CHANGELOG `[4.26.6]`, Version 4.26.6 überall, ausgeliefert

## Acceptance Criteria

- **AC-1:** Given ein `feature-fast`-Workflow in `phase4_approved` / When `next_step` und `expected_footer_command` aufgerufen werden / Then liefern sie `/50-implement` bzw. `/50-implement #<N>`, und `status_note` nennt `Nächster Pflicht-Schritt: /50-implement #<N>`
  - Test: tests/test_fast_track_anzeige_688.py::test_fast_track_phase4_next_is_implement

- **AC-2:** Given ein `feature`-Workflow (voller Prozess) in `phase4_approved` / When `next_step` aufgerufen wird / Then bleibt das Ergebnis `/40-tdd-red`
  - Test: tests/test_fast_track_anzeige_688.py::test_full_process_phase4_unchanged

- **AC-3:** Given ein Workflow in `phase4_approved`, dessen jüngste Spec-Freigabe `by: "auto"` ist / When `end_state` bzw. `render_plan` aufgerufen werden / Then ist der Endzustand `waiting` mit der Zeile `⏳ Läuft noch: Claude führt /50-implement #<N> selbst aus. Du musst nichts tun, ich melde mich.` (Fast Track), kein `❗ Du`, und `cmd` ist gesetzt
  - Test: tests/test_fast_track_anzeige_688.py::test_auto_approved_phase4_is_waiting

- **AC-4:** Given ein Workflow in `phase4_approved` mit manueller Freigabe (`by: "po"`) oder ohne `approvals` / When `end_state` aufgerufen wird / Then bleibt der Endzustand `you` mit `❗ Du:`
  - Test: tests/test_fast_track_anzeige_688.py::test_manual_approval_stays_you

- **AC-5:** Given der Fall aus AC-3 / When das Fußzeilen-Gate die ⏳-Zeile prüft / Then blockt es nicht; und die Seitenleiste (`herdr_bridge.build_report`) meldet Token `next=/50-implement #<N>` und Zustand `läuft`
  - Test: tests/test_fast_track_anzeige_688.py::test_footer_gate_and_sidebar_agree

- **AC-6:** Given die Änderung / When die Gesamtsuite läuft / Then sind alle bestehenden Tests ohne Änderung ihrer Assertions grün
  - Test: tests/ (Gesamtsuite)

## Test Plan

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN `feature-fast` in `phase4_approved` WHEN `next_step` THEN `/50-implement` (heute RED: `/40-tdd-red`)
- [ ] Test 2: GIVEN Auto-Freigabe in `phase4_approved` WHEN `end_state` THEN `waiting` (heute RED: `you`)
- [ ] Test 3: GIVEN voller Prozess bzw. manuelle Freigabe WHEN aufgerufen THEN unverändert (grün vor und nach)
- [ ] Test 4: Gesamtsuite grün ohne `skip`/`xfail`

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Zwei zustandsabhängige Ausnahmen in bestehenden reinen Funktionen nach vorhandenem Muster (`phase3_spec`/`phase5_tdd_red` in `next_step`, `self_driven` in `_end_state_open`); keine neue Architektur.
- **Alternative A, Autonomie-Modus aus der Config in `end_state` lesen:** verworfen, `end_state` ist bewusst rein (keine Config-Zugriffe) und läuft im Fußzeilen-Gate jedes Projekts.
- **Alternative B, `NEXT_STEP` je Workflow-Typ verdoppeln:** verworfen, unnötige Duplikation für einen einzigen abweichenden Eintrag.

## Changelog

- 2026-11-26: Erstfassung
- 2026-11-26: Ausgeliefert als 4.26.7 (4.26.6 war inzwischen durch #691 belegt)
