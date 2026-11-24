# Context: fix-645-plan-zeit-auslieferung

## Request Summary
Issue #645: Der Zeitblock im Plan-Pane („Start · Dauer · Ende“) friert beim Eintritt in
`phase8_complete` ein, obwohl die Auslieferung (`ship_status` `open`/`running`) noch läuft.
Der PO liest „Ende 09:03“ als Fertig-Zeitpunkt. Solange ausgeliefert wird, soll der Block
„Ausliefern seit HH:MM“ mit laufender Dauer zeigen; erst bei `done`/`skipped` stehen die
Ist-Werte bis zum Abschluss der Auslieferung.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` `_plan_time_lines` (~Z. 1306) | Ist-Block: nimmt `_finished_span` → Ende = Phase-8-Eintritt bzw. `last_updated` |
| `core/hooks/workflow.py` `_finished_span` (~Z. 1274) | Start/Ende eines fertigen Workflows; auch von `_retro_estimate_line` (Retro „Schätzung vs. Ist“) genutzt |
| `core/hooks/workflow.py` `current_estimate` (~Z. 1206) | liefert `{"actual": True}` für archivierte Workflows und `phase8_complete` |
| `core/hooks/workflow.py` `cmd_ship_status` (~Z. 4298) | setzt `ship_status` + `ship_at` (UTC) bei jedem Aufruf neu |
| `core/hooks/workflow.py` `_plan_ship_line`, `_plan_lines` | Schritt „Ausliefern“ im Plan (#612) |
| `scripts/ship.py` | ruft `ship-status running` mehrfach (Push, PR, CI) → `ship_at` wandert mit |
| `tests/test_zeitschaetzung_620.py` AC-6 | Ist-Block-Tests; `ship_status: done` ohne `ship_at` → Ende = Phase-8-Eintritt |
| `tests/test_arbeitszeit_628.py`, `tests/test_zeitschaetzung_642.py`, `tests/test_anzeige_zeitzone_637.py` | weitere Zeitblock-Tests (Format, Zeitzone, Umbruch) |

## Existing Patterns
- Zeitzeilen: `["", "Start  …", "<Mitte>", …]`, Uhrzeit über `_format_clock(value, today, zone)` (#637 Anzeigezone).
- Dauer über `format_duration`, Arbeitszeit vs. Gesamt „Dauer  X (gesamt Y)“ (#628).
- Fehlerfest: `_plan_time_lines` fängt jede Exception und gibt `[]`.
- `ship_status`-Werte: `open` (von `phase8_complete` gesetzt), `running`, `done`, `failed`, `skipped`;
  `SHIP_PENDING_VALUES = (open, running, failed)`. Alte Archiv-Workflows haben keinen Marker.

## Dependencies
- Upstream: `phase_log`, `created`, `last_updated`, `ship_status`, `ship_at`, `_estimate_now`, `_display_time`.
- Downstream: `render_plan` (Plan-Pane, `plan --watch`, Herdr), Retro-Zeile, Lern-Daten der Schätzung
  (`load_archive_phase_durations` — nutzt `_finished_span` nicht).

## Existing Specs
- `docs/specs/fix-642-zeitschaetzung.md`, Spec zu #620 (Zeitschätzung), #612 (Auslieferung als Schritt).

## Risks & Considerations
- `ship_at` wird bei jedem `running` überschrieben → taugt nicht als „seit“; Beginn der Auslieferung = Phase-8-Eintritt.
- `_finished_span` nicht umdeuten: Retro-Vergleich „geschätzt vs. tatsächlich“ misst die Arbeit bis Phase 8.
- Archivierte Workflows ohne `ship_status`/`ship_at` müssen unverändert bleiben (bestehende AC-6-Tests).
- `failed` ist auch nicht fertig → kein festes Ende.

## Analysis

### Type
Bug (Anzeige): Ist-Block endet am Phase-8-Eintritt, Auslieferung fehlt.

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | `_plan_time_lines`: Zweig für laufende/fertige Auslieferung; kleiner Helfer für Auslieferungs-Beginn |
| `tests/test_plan_zeit_auslieferung_645.py` | CREATE | Tests für open/running/failed/done/skipped und Altbestand |
| `CHANGELOG.md`, `.claude-plugin/plugin.json` (+ Versionszeilen) | MODIFY | Patch-Version 4.20.1 |

### Scope Assessment
- Files: 1 Code-Datei + 1 Testdatei + Versions-/Changelog-Dateien
- Estimated LoC: Code +30/-3, Tests ~+120
- Risk Level: LOW (reine Anzeige, fail-open `[]` bleibt)

### Technical Approach
- Beginn der Auslieferung = `entered_at` des letzten `phase8_complete`-Eintrags im `phase_log`
  (Fallback: Ende aus `_finished_span`). `ship_at` taugt nicht, es wandert bei jedem `running`.
- `ship_status` in `open`/`running`/`failed`: Zeilen `Start  HH:MM`, `Ausliefern  seit HH:MM (N min)`
  (laufende Dauer = jetzt − Beginn), `Ende  offen`. Keine „Dauer“-Zeile, kein festes Ende.
- `ship_status` in `done`/`skipped` mit gültigem `ship_at` ≥ Start: Ende = `ship_at`, Dauer bis dahin
  (Arbeitszeit-Logik #628 unverändert über `_finished_work_min`).
- Ohne `ship_status` oder ohne `ship_at` (Altbestand, bestehende AC-6-Tests): Verhalten unverändert.
- `_finished_span` bleibt unverändert (Retro „Schätzung vs. Ist“ misst weiter bis Phase 8).

### Alternative
Eigenes Feld `ship_started_at`, gesetzt beim ersten `running` (würde ADR-/State-Erweiterung bedeuten).
Verworfen: der Phase-8-Eintritt ist derselbe Zeitpunkt (Code fertig = Auslieferung beginnt, `open`),
kein neues State-Feld, keine Migration für laufende Workflows.

### Dependencies
`_format_clock`, `format_duration`, `_finished_work_min`, `_estimate_now` (Testuhr), Anzeigezone #637.

### Open Questions
- keine (Darstellung folgt dem Wortlaut des Issues; Produktentscheidung nicht nötig)
