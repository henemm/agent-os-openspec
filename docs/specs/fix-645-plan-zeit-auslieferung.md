---
entity_id: fix-645-plan-zeit-auslieferung
type: bugfix
created: 2026-11-24
updated: 2026-11-24
status: draft
version: "1.0"
workflow: fix-645-plan-zeit-auslieferung
tags: [plan-pane, zeitblock, auslieferung, workflow]
---

# Plan-Pane: Zeitblock friert bei Phase 8 ein, Auslieferung zählt nicht (Issue #645)

## Approval

- [ ] Approved

## Purpose

Der Zeitblock im Plan-Pane friert beim Eintritt in `phase8_complete` ein, obwohl die Auslieferung (`ship_status` `open`/`running`) noch läuft. Beispiel: Das Pane zeigt „Start 08:07 · Dauer 56 min · Ende 09:03“ und darunter „▶ Ausliefern (läuft)“, um 12:30 lief die Auslieferung aber noch. Der PO liest „Ende 09:03“ als Fertig-Zeitpunkt. Solange ausgeliefert wird, soll der Block „Ausliefern seit HH:MM“ mit laufender Dauer und „Ende  offen“ zeigen; erst bei `done`/`skipped` stehen die Ist-Werte bis zum Abschluss der Auslieferung. Die Spec ergänzt `fix-642-zeitschaetzung.md` und ändert deren Ist-Block nur für Workflows mit Auslieferungsstand.

## Source

- Issue #645; Kontext und Analyse: `docs/context/fix-645-plan-zeit-auslieferung.md`.
- **File:** `core/hooks/workflow.py`
- **Identifier:** `_plan_time_lines` (geändert), neuer kleiner Helfer für den Auslieferungsbeginn (`_ship_start`); unverändert: `_finished_span`, `_retro_estimate_line`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.py::_format_clock` | function | Uhrzeitformat in der Anzeigezone (#637) |
| `workflow.py::format_duration` | function | Dauer als Text, auch für die laufende Auslieferung |
| `workflow.py::_finished_work_min` | function | Arbeitszeit-/Gesamt-Logik des Ist-Blocks (#628), unverändert |
| `workflow.py::_estimate_now` | function | Testuhr für „jetzt“ |
| `workflow.py::_finished_span` | function | Rückfall für den Auslieferungsbeginn; selbst unverändert |
| `workflow.py::_wrap_time_line` | function | Umbruch des Zeitblocks bei `width` (#642) |
| `workflow.py::_display_time` | function | Anzeigezone (#637) |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | `_plan_time_lines`: Zweig für laufende/fertige Auslieferung; Helfer `_ship_start` |
| `tests/test_plan_zeit_auslieferung_645.py` | CREATE | Tests AC-1 bis AC-6 |
| `CHANGELOG.md` | MODIFY | Eintrag 4.20.1 |
| `.claude-plugin/plugin.json` und die übrigen Versionszeilen | MODIFY | Patch-Bump 4.20.1 (Einzel-Auslieferung) |

### Estimated Changes

- Files: 1 Code-Datei, 1 Testdatei, Versions- und Changelog-Dateien
- LoC: Produktivcode ca. +30/-3, Tests ca. +120
- Keine Gate-Wirkung, keine Änderung an Gate-Config: reine Anzeige, fail-open.

## Implementation Details

**1. Auslieferungsbeginn.** Neuer Helfer `_ship_start(data)`: `entered_at` des letzten `phase8_complete`-Eintrags im `phase_log`; fehlt er, das Ende aus `_finished_span`. `ship_at` taugt nicht, weil `cmd_ship_status` es bei jedem `running` überschreibt und `scripts/ship.py` mehrfach `running` meldet.

**2. Zweig in `_plan_time_lines`** (nur wenn `estimate["actual"]` gesetzt ist):

- `ship_status` in `open`, `running`, `failed` (`SHIP_PENDING_VALUES`): Zeilen `Start  HH:MM`, `Ausliefern  seit HH:MM (<Dauer>)` mit Dauer = jetzt − Auslieferungsbeginn über `format_duration`, und `Ende  offen`. Keine `Dauer  `-Zeile, keine feste Ende-Uhrzeit.
- `ship_status` in `done`, `skipped` mit gültigem `ship_at` ≥ Start: `Ende  ` = `ship_at`, `Dauer  ` bis dahin; Arbeitszeit-/Gesamt-Logik (#628) unverändert.
- Ohne `ship_status` (Altbestand) oder `done`/`skipped` ohne bzw. mit unlesbarem `ship_at`: Ausgabe exakt wie bisher.

**3. Unverändert.** `_finished_span` und die Retro-Zeile „Schätzung vs. Ist“ messen weiter bis Phase 8. `abandoned` und fehlende Zeitstempel ergeben weiterhin keinen Zeitblock.

**4. Anzeige.** Alle Uhrzeiten laufen über `_format_clock` mit der Anzeigezone (#637); die neue Zeile geht durch denselben Umbruch bei `width` (#642) wie die übrigen Zeitzeilen.

**5. Fail-open.** Jede Ausnahme in `_plan_time_lines` ergibt `[]`, nie eine Ausnahme nach außen.

## Expected Behavior

- **Input:** `render_plan(data, archived=…, estimate={"actual": True, "now": …})` mit `ship_status` und `phase_log`.
- **Output:** Während der Auslieferung steht „Ausliefern  seit HH:MM (N min)“ und „Ende  offen“; nach `done`/`skipped` Ende und Dauer bis zum Abschluss der Auslieferung.
- **Side effects:** keine; reine Anzeige.

## Known Limitations

- Die laufende Dauer ist Wanduhrzeit seit Phase-8-Eintritt, keine Arbeitszeit; solange die Auslieferung nicht fertig ist, gibt es keine Arbeitszeit-Aufteilung.
- Ein Workflow, der `done` ohne `ship_at` meldet, zeigt wie bisher das Ende am Phase-8-Eintritt (Altbestand).
- Bei `failed` bleibt das Ende offen, bis ein neuer Lauf `done` meldet.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Das Plan-Pane zeigt während einer laufenden Auslieferung „Ausliefern seit HH:MM“ und „Ende  offen“ statt einer festen Fertig-Uhrzeit
- [ ] Die Tests aus #620, #628, #637 und #642 sind unverändert grün, die gesamte Suite grün
- [ ] CHANGELOG, Versions-Bump 4.20.1, `python3 scripts/release_check.py --no-tests` grün, Version veröffentlicht

## Acceptance Criteria

- **AC-1:** Given ein Workflow in `phase8_complete` mit `ship_status` `open`, `running` oder `failed` und Phase-8-Eintritt um 08:57 bei Start 08:07 / When der Plan mit Testuhr 12:30 gerendert wird / Then zeigt der Zeitblock „Start  08:07“, „Ausliefern  seit 08:57 (<Dauer 3 h 33 min>)“ und „Ende  offen“, ohne „Dauer  “-Zeile und ohne feste Ende-Uhrzeit.
  - Test: tests/test_plan_zeit_auslieferung_645.py::test_laufende_auslieferung_zeigt_seit_und_ende_offen
- **AC-2:** Given ein Workflow mit mehreren `phase8_complete`-Einträgen im `phase_log` und `ship_at` nach mehrfachem `running` / When der Plan rendert / Then ist der Auslieferungsbeginn der `entered_at` des letzten `phase8_complete`-Eintrags und nicht `ship_at`; fehlt der Eintrag, steht das Ende aus `_finished_span`.
  - Test: tests/test_plan_zeit_auslieferung_645.py::test_auslieferungsbeginn_aus_phase_log_nicht_ship_at
- **AC-3:** Given `ship_status` `done` oder `skipped` mit gültigem `ship_at` nicht vor dem Start / When der Plan rendert / Then steht „Ende  “ mit der Uhrzeit von `ship_at` und „Dauer  “ bis dahin, die Arbeitszeit-/Gesamt-Logik aus #628 gilt unverändert.
  - Test: tests/test_plan_zeit_auslieferung_645.py::test_abgeschlossene_auslieferung_ende_ist_ship_at
- **AC-4:** Given ein Workflow ohne `ship_status` oder mit `done`/`skipped` ohne bzw. mit unlesbarem `ship_at` / When der Plan rendert / Then ist die Ausgabe exakt wie vor der Änderung, und die Tests in `test_zeitschaetzung_620.py` (AC-6), `test_arbeitszeit_628.py`, `test_zeitschaetzung_642.py` und `test_anzeige_zeitzone_637.py` bleiben grün.
  - Test: tests/test_plan_zeit_auslieferung_645.py::test_altbestand_ohne_ship_at_unveraendert
- **AC-5:** Given ein abgebrochener Workflow (`abandoned`), fehlende Zeitstempel oder ein kaputter `phase_log` / When der Plan rendert / Then entsteht weiterhin kein Zeitblock bzw. `[]`, und es wird keine Ausnahme ausgelöst; `_finished_span` und die Retro-Zeile „Schätzung vs. Ist“ liefern dasselbe Ergebnis wie vorher.
  - Test: tests/test_plan_zeit_auslieferung_645.py::test_fail_open_und_finished_span_unveraendert
- **AC-6:** Given eine Anzeigezone ungleich UTC (#637) und `render_plan` mit `width=34` / When die Auslieferung läuft / Then zeigt die Zeile „Ausliefern  seit HH:MM (<Dauer>)“ die Uhrzeit in der Anzeigezone, und keine Zeile ist länger als 34 Zeichen (Umbruch statt Kappen, #642).
  - Test: tests/test_plan_zeit_auslieferung_645.py::test_ausliefern_zeile_anzeigezone_und_umbruch

## Test Plan

- `python3 -m pytest tests/test_plan_zeit_auslieferung_645.py -q` (venv): AC-1 bis AC-6.
- `python3 -m pytest tests/test_zeitschaetzung_620.py tests/test_arbeitszeit_628.py tests/test_zeitschaetzung_642.py tests/test_anzeige_zeitzone_637.py -q`: Regression, unverändert grün.
- Gesamte Suite vor der Auslieferung.

### Automated Tests (TDD RED)

- [ ] Test 1: laufende Auslieferung zeigt „seit“ und „Ende  offen“ (AC-1)
- [ ] Test 2: Beginn aus letztem `phase8_complete`, nicht aus `ship_at` (AC-2)
- [ ] Test 3: `done`/`skipped` mit `ship_at` ergibt Ende und Dauer (AC-3)
- [ ] Test 4: Altbestand ohne `ship_status`/`ship_at` unverändert (AC-4)
- [ ] Test 5: fail-open, `_finished_span` und Retro unverändert (AC-5)
- [ ] Test 6: Anzeigezone und Umbruch bei 34 Zeichen (AC-6)

RED-Artefakt: `docs/artifacts/645-red.log`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine neue ADR (kleine Anzeigekorrektur; keine Entscheidungsfläche berührt).
- **Rationale:** Der Phase-8-Eintritt ist derselbe Zeitpunkt wie der Beginn der Auslieferung (Code fertig, `ship_status` `open`); ein bestehender Wert genügt. Alternative: eigenes State-Feld `ship_started_at`, gesetzt beim ersten `running`. Verworfen: es würde eine Zustandserweiterung samt Migration für laufende Workflows bedeuten, ohne einen anderen Zeitpunkt zu liefern; sie fiele für die ADR „Auslieferungsbeginn als eigenes State-Feld“. Ebenfalls verworfen: `ship_at` als „seit“, weil es bei jedem `running` überschrieben wird, und `_finished_span` umzudeuten, weil die Retro-Zeile „Schätzung vs. Ist“ die Arbeit bis Phase 8 misst.

## Changelog

- 1.0 (2026-11-24): Erstfassung zu Issue #645.
