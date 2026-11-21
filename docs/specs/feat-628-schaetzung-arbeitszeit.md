---
entity_id: feat-628-schaetzung-arbeitszeit
type: feature
created: 2026-11-21
updated: 2026-11-21
status: draft
version: "1.0"
workflow: feat-628-schaetzung-arbeitszeit
tags: [plan-pane, zeitschaetzung, arbeitszeit, heartbeat, workflow]
---

# Zeitschätzung zeigt nur Arbeitszeit: Wartezeit auf den PO und Leerlauf zählen nicht (Issue #628)

## Approval

- [ ] Approved

## Purpose

Die Zeitschätzung aus #620 zeigt Spannen wie „1 h 43 min–8 h 37 min“, weil die Wanduhr auch die Nacht und das Warten auf die Spec-Freigabe mitzählt. Sie soll künftig nur die Arbeitszeit schätzen. Wartezeit auf den PO und Leerlauf zählen nicht. Steht eine menschliche Freigabe tatsächlich aus, erscheint der Zusatz „+ Wartezeit auf dich“.

Entscheidung PO (2026-11-21, #628): Die Anzeige schätzt nur Arbeitszeit; „+ Wartezeit auf dich“ nur, solange eine menschliche Spec-Freigabe aussteht. Diese Spec ergänzt `docs/specs/feat-620-zeitschaetzung.md`, sie löst sie nicht ab.

## Source

- Issue #628, Befund und Analyse: `docs/context/feat-628-schaetzung-arbeitszeit.md` (Variante A gewählt, B und C verworfen).
- **File:** `core/hooks/workflow.py`, `core/hooks/session_singleton_guard.py`
- **Identifier:** `_archive_phase_entry`, `current_estimate`, `estimate_remaining`, `_plan_time_lines`, `_estimate_kv_lines` (workflow.py); `_heartbeat` (session_singleton_guard.py); neu `note_activity`, `po_wait_minutes`, `awaiting_human_approval`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.py::phase_log`, `phase_transitions` | state | `phase_log`-Segmente und Übergänge mit `trigger` (`command`, `auto`, `approval`) für die PO-Wartezeit |
| `workflow.py::po_briefing.created` | state | Beginn der Wartezeit auf die Spec-Freigabe |
| `workflow.py::_auto_approval_pending`, `autonomy_mode` | function | Entscheidet, ob die Freigabe automatisch greifen kann (Ampel grün und Modus auto) |
| `workflow.py::estimate_remaining`, `current_estimate`, `_plan_time_lines`, `_estimate_kv_lines`, `_finished_span` | function | Schätzung, Plan-Pane, CLI `estimate` und Ist-Block aus #620 |
| `session_singleton_guard.py::_heartbeat` | function | Einzige Stelle mit regelmäßigem Aktivitätssignal (alle Tools, Throttle 60 s) |
| `config_loader` / `config.yaml` Abschnitt `time_estimate` | module | Neuer Parameter `idle_gap_min` (Standard 15) |
| `docs/specs/feat-620-zeitschaetzung.md` | spec | Grundspec, bleibt gültig; deren Tests bleiben grün |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | `po_wait_minutes`, `note_activity` (pure plus atomare I/O), `load_activity`, Arbeitszeit in `_archive_phase_entry`/`_minutes_in_phase`/`estimate_remaining`, `awaiting_human_approval`, Zusatz in `_plan_time_lines` und `_estimate_kv_lines` (`ESTIMATE_WAITING=po`), Ist-Block mit Gesamtzeit, Default `idle_gap_min` |
| `core/hooks/session_singleton_guard.py` | MODIFY | Im fälligen Throttle-Zweig von `_heartbeat` fail-open `note_activity` aufrufen |
| `config.yaml` | MODIFY | `time_estimate.idle_gap_min: 15` |
| `tests/test_arbeitszeit_628.py` | CREATE | Tests aller ACs inklusive Archiv-Nachrechnung mit Fixture-Kopien der Ausreißer |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, keine Versionsnummer |

### Estimated Changes

- Files: 5
- LoC: Produktivcode ca. +170/-10 (Grenze ±250), Tests ca. +150
- Keine Gate-Wirkung: reine Anzeige, fail-open. Das Workflow-JSON wird vom Hook nie geschrieben.

## Implementation Details

**1. PO-Wartezeit (rückwirkend, exakt).** `po_wait_minutes(data)` bestimmt die Spanne `[po_briefing.created, at]`, wobei `at` der Zeitpunkt des Übergangs nach `phase4_approved` mit `trigger == "approval"` ist (aus `phase_transitions`). Die Überschneidung dieser Spanne mit jedem `phase_log`-Segment wird von der Segmentdauer abgezogen (nie unter 0), je Phase. Bei `trigger == "auto"`, fehlendem Briefing, fehlendem Übergang oder ungültigen Zeitstempeln wird nichts abgezogen. Ein Leerlauf in `phase4_approved` nach einer automatischen Freigabe (fix-566) wird so bewusst nicht erfasst; dafür sorgt Punkt 2.

**2. Aktivität (vorausschauend).** `note_activity(workflow, phase, now)` schreibt `.claude/workflows/_activity/<workflow>.json` atomar (Temp-Datei, `os.replace`) mit `{"last": ts, "phases": {phase: active_min}}`. Liegt `last` höchstens `idle_gap_min` (Config `time_estimate.idle_gap_min`, Standard 15) zurück, wird die Differenz in Minuten der aktuellen Phase gutgeschrieben, sonst wird nur `last` gesetzt. `_heartbeat` ruft die Funktion nur im fälligen Throttle-Zweig (`due`, höchstens einmal je 60 s) und vollständig fail-open (eigenes try/except, nie Blockade, nie Exit-Code). Workflow und Phase kommen aus dem Kontext, den `_apply_context_fields` schon ermittelt. Das Workflow-JSON bleibt unberührt, damit kein zweiter Schreiber auf den State entsteht. Mehrere Sitzungen am selben Workflow: letzter Schreiber gewinnt, Doppelzählung höchstens eine Minute je Schlag.

**3. Archiv-Eintrag.** Existiert eine lesbare Aktivitätsdatei mit mindestens einer Phase, gelten deren Aktivminuten als Phasendauern. Sonst gelten die `phase_log`-Dauern abzüglich PO-Wartezeit (Punkt 1). Archivdateien werden nicht migriert; die Aktivitätsdatei wird beim Archivieren nicht verschoben und über den Workflow-Namen gefunden.

**4. Laufender Workflow.** Die verstrichene Zeit für „Dauer ca.“ und die laufende Phase ist Arbeitszeit: aus der Aktivitätsdatei, sonst Wanduhr abzüglich PO-Wartezeit. „Ende ca.“ = jetzt + Rest, die Wartezeit auf den PO steckt dort nicht drin.

**5. „+ Wartezeit auf dich“.** `awaiting_human_approval(data)` ist wahr, wenn `current_phase == "phase3_spec"`, ein `po_briefing` registriert ist und die Auto-Freigabe nicht greift (`_auto_approval_pending` falsch: Ampel nicht grün oder Modus manual). Dann hängt `_plan_time_lines` an die Dauer-Zeile „ + Wartezeit auf dich“ an, und `workflow.py estimate` hängt es an `LINE=` und gibt zusätzlich `ESTIMATE_WAITING=po` aus. Sonst entfällt beides.

**6. Ist-Block fertiger Workflows.** „Dauer“ zeigt die Arbeitszeit (Punkt 3), die Gesamtzeit in Klammern, z.B. `Dauer  1 h 10 min (gesamt 9 h 2 min)`. Sind beide gleich (auf die Minute gerundet), steht keine Klammer.

**7. Fail-open.** Kaputte oder fehlende Aktivitätsdatei, ungültige Zeitstempel, Konfigurationsfehler: Rückfall auf den bisherigen Weg aus #620, nie eine Ausnahme nach außen; der Guard blockt nie wegen dieser Funktion. `idle_gap_min` wird geprüft (Zahl größer 0), sonst Standard 15.

**8. Rückwärtsverträglichkeit.** Alle Tests aus #620 bleiben grün; ohne Aktivitätsdatei und ohne PO-Briefing verhält sich die Schätzung wie bisher.

## Expected Behavior

- Die Dauer-Spanne zeigt realistische Arbeitszeit (Stunden statt halber Tage); eine über Nacht wartende Spec verfälscht sie nicht mehr.
- Wartet eine Spec auf die menschliche Freigabe, steht hinter der Dauer „+ Wartezeit auf dich“; bei grüner Ampel im Auto-Modus nicht.
- Fertige Workflows zeigen Arbeitszeit und, wenn abweichend, die Gesamtzeit in Klammern.
- Mit jedem neuen Workflow mit Aktivitätsdatei beruht die Schätzung stärker auf echter Arbeitszeit.

## Known Limitations

- Wartezeit auf „go“ (nur Modus manual; im Auto-Modus setzt `auto-green` die Freigabe sofort): Mit Aktivitätsdatei zählt sie automatisch nicht, weil währenddessen kein Werkzeug läuft. Archiv-Workflows ohne Aktivitätsdatei haben keinen Zeitstempel für eine menschliche GREEN-Freigabe; dort bleibt sie enthalten. Alle 11 vorhandenen Archiv-Workflows haben GREEN automatisch bekommen, betroffen ist also keiner.
- Bestehende Archiv-Workflows haben keine Aktivitätsdatei; dort wird nur die PO-Wartezeit der Freigabe abgezogen. Leerlauf wie in fix-566 (automatische Freigabe, danach Pause) bleibt in diesen Altdaten enthalten; die Quantile dämpfen das.
- Aktivität wird auf eine Minute genau und nur bei Tool-Aufrufen erkannt; reines Nachdenken ohne Tool-Aufruf länger als `idle_gap_min` zählt nicht als Arbeit.
- Ein einzelner Werkzeugaufruf, der länger als `idle_gap_min` läuft (langer Build, Teilagent ohne eigene Werkzeugaufrufe in dieser Sitzung), zählt bis zum nächsten Heartbeat nicht als Arbeit: die Lücke zwischen zwei Schlägen gilt dann als Leerlauf.
- Die Aktivitätsdateien sind rechnerlokal wie das Archiv.

## Definition of Done

- Alle AC-1 bis AC-9 sind durch `tests/test_arbeitszeit_628.py` belegt; die Tests aus #620 und die gesamte Suite sind grün.
- Eine über Nacht wartende Spec und ein Leerlauf zählen in der Anzeige nicht mehr als Arbeitszeit; „+ Wartezeit auf dich“ erscheint nur bei tatsächlich ausstehender menschlicher Freigabe.
- Der Guard bleibt fail-open: eine kaputte Aktivitätsdatei lässt kein Tool blocken.
- CHANGELOG-Eintrag unter `[Unreleased]`; `python3 scripts/release_check.py --no-tests` grün.

## Acceptance Criteria

- **AC-1:** Given ein archivierter Workflow mit `po_briefing.created` und einem Übergang nach `phase4_approved` mit `trigger == "approval"`, dessen `phase3_spec`-Segment die Wartezeit überdeckt / When `po_wait_minutes` und `_archive_phase_entry` laufen / Then wird die Überschneidung der Spanne [Briefing, Freigabe] von den `phase_log`-Segmenten abgezogen (nie unter 0), und bei `trigger == "auto"` oder fehlendem Briefing wird nichts abgezogen.
  - Test: tests/test_arbeitszeit_628.py::test_po_wartezeit_wird_abgezogen_und_auto_nicht
- **AC-2:** Given ein Workflow und ein Heartbeat im fälligen Throttle-Zweig / When `_heartbeat` läuft / Then schreibt der Guard fail-open über `note_activity` die Datei `.claude/workflows/_activity/<workflow>.json` atomar mit `last` und Aktivminuten je Phase, aber nicht bei einem Aufruf außerhalb des Throttle-Fensters, und das Workflow-JSON bleibt unverändert.
  - Test: tests/test_arbeitszeit_628.py::test_heartbeat_schreibt_aktivitaet_nur_im_faelligen_zweig
- **AC-3:** Given eine Aktivitätsdatei mit `last` / When `note_activity` einmal innerhalb und einmal außerhalb von `idle_gap_min` (Standard 15, aus `time_estimate.idle_gap_min`) aufgerufen wird / Then wird innerhalb die Differenz der aktuellen Phase gutgeschrieben und außerhalb nur `last` gesetzt, ohne Gutschrift.
  - Test: tests/test_arbeitszeit_628.py::test_note_activity_idle_gap
- **AC-4:** Given ein Archiv-Workflow einmal mit und einmal ohne Aktivitätsdatei / When `load_archive_phase_durations` läuft / Then gelten mit mindestens einer Phase in der Aktivitätsdatei deren Aktivminuten als Phasendauern, sonst die `phase_log`-Dauern abzüglich PO-Wartezeit; Archivdateien werden dabei nicht verändert.
  - Test: tests/test_arbeitszeit_628.py::test_archiv_nutzt_aktivitaet_sonst_phase_log_minus_wartezeit
- **AC-5:** Given ein laufender Workflow, der seit Stunden in `phase3_spec` auf die Freigabe wartet / When `estimate_remaining` und `current_estimate` laufen / Then zählt die verstrichene Zeit (Dauer ca. und laufende Phase) als Arbeitszeit aus der Aktivitätsdatei bzw. Wanduhr abzüglich PO-Wartezeit, und „Ende ca.“ ist jetzt plus Rest ohne Wartezeit.
  - Test: tests/test_arbeitszeit_628.py::test_laufender_workflow_nutzt_arbeitszeit
- **AC-6:** Given ein Workflow, der auf eine menschliche Freigabe wartet: entweder in `phase3_spec` mit registriertem `po_briefing`, bei Ampel nicht grün oder Modus manual (wartet auf „approved“), oder in `phase6_implement` mit `last_test_run.result == "passed"`, `green_approved` falsch und Modus manual (wartet auf „go“) / When Plan und `workflow.py estimate` laufen / Then endet die Dauer-Zeile im Plan und `LINE=` auf „ + Wartezeit auf dich“ und `ESTIMATE_WAITING=po` steht in der Ausgabe; bei grüner Ampel im Auto-Modus, im Auto-Modus in `phase6_implement` (GREEN kommt per `auto-green`), ohne Briefing oder in einer anderen Phase erscheinen weder der Zusatz noch `ESTIMATE_WAITING`.
  - Test: tests/test_arbeitszeit_628.py::test_wartezeit_zusatz_nur_bei_ausstehender_menschlicher_freigabe
- **AC-7:** Given ein fertiger Workflow, dessen Arbeitszeit 1 h 10 min und dessen Gesamtzeit 9 h 2 min beträgt / When der Plan-Block gerendert wird / Then lautet die Zeile „Dauer  1 h 10 min (gesamt 9 h 2 min)“, und bei gleicher Arbeits- und Gesamtzeit steht sie ohne Klammer.
  - Test: tests/test_arbeitszeit_628.py::test_ist_block_arbeitszeit_mit_gesamtzeit
- **AC-8:** Given eine kaputte oder fehlende Aktivitätsdatei, ungültige Zeitstempel oder ein ungültiges `idle_gap_min` / When `_heartbeat`, `note_activity`, `plan` und `estimate` laufen / Then fällt die Anzeige auf den Weg aus #620 zurück, es entsteht keine Ausnahme nach außen, der Guard blockt nie, und alle bestehenden Tests aus `tests/test_zeitschaetzung_620.py` bleiben grün.
  - Test: tests/test_arbeitszeit_628.py::test_fail_open_und_rueckfall
- **AC-9:** Given die 11 Archivdateien als Fixture-Kopien (mindestens die Ausreißer feat-562, feat-589 und fix-566) / When die Gesamtdauer je Feature-Workflow aus `load_archive_phase_durations` berechnet wird / Then liegt die 75-%-Grenze dieser Gesamtdauern unter 2 h statt bei mehreren Stunden.
  - Test: tests/test_arbeitszeit_628.py::test_archiv_nachrechnung_75_prozent_unter_zwei_stunden

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `python3 -m pytest tests/test_arbeitszeit_628.py -q` (im venv): AC-1 bis AC-9.
- `python3 -m pytest tests/test_zeitschaetzung_620.py -q`: Regression der Grundspec.
- `python3 -m pytest tests -q`: gesamte Suite, insbesondere Tests zu `session_singleton_guard` (Heartbeat) und Plan-Pane.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN ein Archiv-Workflow mit Freigabe-Übergang `approval` über Nacht WHEN `po_wait_minutes` läuft THEN wird die Überschneidung abgezogen; bei `auto` oder ohne Briefing nichts.
- [ ] Test 2: GIVEN ein Heartbeat im Throttle-Fenster und einer außerhalb WHEN `_heartbeat` läuft THEN entsteht die Aktivitätsdatei nur im fälligen Zweig und das Workflow-JSON bleibt gleich.
- [ ] Test 3: GIVEN `last` 5 min bzw. 40 min zurück WHEN `note_activity` läuft THEN 5 min Gutschrift bzw. nur `last` neu.
- [ ] Test 4: GIVEN Archiv mit und ohne Aktivitätsdatei WHEN geladen wird THEN Aktivminuten bzw. `phase_log` minus Wartezeit.
- [ ] Test 5: GIVEN ein wartender Workflow in `phase3_spec` WHEN `estimate_remaining` läuft THEN zählt nur Arbeitszeit als verstrichen.
- [ ] Test 6: GIVEN Ampel rot, manual, grün+auto, kein Briefing, sowie phase6_implement mit grünem Testlauf in manual bzw. auto WHEN Plan und `estimate` laufen THEN Zusatz und `ESTIMATE_WAITING=po` nur bei Ampel rot, manual und phase6_implement+manual.
- [ ] Test 7: GIVEN Arbeitszeit ungleich Gesamtzeit WHEN der Ist-Block rendert THEN „(gesamt …)“ in Klammern, sonst ohne.
- [ ] Test 8: GIVEN kaputte Aktivitätsdatei und ungültige Zeitstempel WHEN Guard, Plan und `estimate` laufen THEN Rückfall ohne Ausnahme.
- [ ] Test 9: GIVEN die Fixture-Kopien der Archivdateien WHEN die Gesamtdauern berechnet werden THEN 75-%-Grenze unter 120 min.

RED-Artefakt: `docs/artifacts/628-red.log`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0628 (Konvention: ADR-Nummer = Issue-Nummer, wie ADR-0597): „Aktivität wird vom Session-Heartbeat in eine eigene Datei je Workflow geschrieben, nie ins Workflow-JSON.“
- **Rationale:** Das Workflow-JSON wird per Read-Modify-Write von `workflow.py` geschrieben; ein zweiter Schreiber im Hook könnte Phasenwechsel überschreiben. Eine eigene Datei je Workflow vermeidet das. Gewählt ist Variante A (Aktivitätssignal aus dem Heartbeat). Alternative B (Lückenkappung ohne neues Signal: jede Phase über X min auf X kappen) wurde verworfen, weil legitim lange Phasen wie iOS-Builds (30 bis 60 min) verfälscht würden und der Grenzwert willkürlich wäre; sie würde die ADR „Schätzung nur aus `phase_log`, kein Aktivitätssignal“ begründen. Alternative C (Aktivität aus dem Claude-Transcript) wurde verworfen, weil Transcripts sitzungsgebunden sind und `/clear` neue erzeugt, die Zuordnung beim Archivieren also nicht verlässlich ist.

## Changelog

- 1.0 (2026-11-21): Erstfassung nach PO-Entscheidung (#628): Schätzung nur Arbeitszeit, „+ Wartezeit auf dich“ nur bei ausstehender menschlicher Freigabe.
