---
entity_id: feat-620-zeitschaetzung
type: feature
created: 2026-11-21
updated: 2026-11-21
status: draft
version: "1.0"
workflow: feat-620-zeitschaetzung
tags: [plan-pane, intake, zeitschaetzung, lernen, workflow]
---

# Zeitschätzung für Workflows: Intake-Schätzung und Plan-Pane mit Start, Dauer-Spanne und Ende (Issue #620)

## Approval

- [ ] Approved

## Purpose

Der PO möchte zu Beginn eines Workflows eine grobe, auf Erfahrungswerten beruhende Schätzung, wie lange er dauert, und diese im rechten Plan-Pane sehen: Startzeit, Dauer als Spanne und prognostiziertes Ende, das sich dynamisch anpasst. Das System soll aus abgeschlossenen Workflows selbst lernen und mit jedem weiteren Messpunkt und mit wachsendem Fortschritt präziser werden: zu Beginn eine weite Zeitspanne, die enger wird, je weniger Phasen offen sind.

Wortlaut PO: "Ich möchte, dass mir Intake zu Beginn eine grobe Schätzung, die auf Erfahrungswerten basiert, gibt, wie viel Zeit der Workflow ungefähr in Anspruch nehmen wird. Diese Zeit möchte ich im rechten Sitepane sehen, inkl. Startzeit und prognostizierter Endzeit. Letztere darf auch dynamisch angepasst werden." Nachtrag: "und war auch so, dass das system selbst lernt und immer präziser wird. Gerne kann zu Beginn auch eine Zeitspanne angegeben werden, die immer präziser wird."

## Source

- PO-Auftrag zu Issue #620 mit Nachtrag (Lernen, Zeitspanne).
- Kontext und Analyse: `docs/context/feat-620-zeitschaetzung.md`.
- **File:** `core/hooks/workflow.py`
- **Identifier:** `render_plan`, `_plan_lines`, `_plan_watch`, `cmd_start`, `cmd_retro`, neue Funktionen `estimate_remaining` (pure) und `load_archive_phase_durations`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.py::_log_phase_transition` / `phase_log` | function/state | Datenquelle: `phase`, `entered_at`, `exited_at`, `duration_min` je Phase |
| `workflow.py::_archive_dir`, `_read_workflow` | function | Archivierte Workflows (`.claude/workflows/_archive/*.json`) lesen |
| `workflow.py::PLAN_STEPS`, `PLAN_STEPS_FAST` | constant | Phasenfolge je Track, bestimmt "spätere Phasen" |
| `workflow.py::render_plan` / `_plan_lines` / `_plan_watch` | function | Plan-Pane (#476, #490, #612), Anzeige und Neuzeichnen je Runde |
| `workflow.py::cmd_retro` | function | Lernnachweis "Schätzung vs. Ist" |
| `config_loader.load_config` / `config.yaml` | module | Abschnitt `time_estimate` (Kill-Switch, Parameter, Startwerte) |
| `core/commands/00-intake.md`, `skills/00-intake/SKILL.md` | command | Score übergeben, Schätzung ausgeben; Skill per `scripts/sync_skills.py` generiert |
| `#254` Intake-Tracks | spec | `workflow_type` (feature / feature-fast), Score-Summe 0-6 |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | Archiv-Dauern laden (mit mtime-Cache), pure Schätzfunktion, `render_plan(..., estimate=None)` mit Zeit-Block, `start --score N` (speichert `intake_score` und `estimate_initial`), CLI `estimate`, Retro-Zeile "Schätzung vs. Ist", `_plan_watch` rechnet je Runde neu |
| `config.yaml` | MODIFY | Abschnitt `time_estimate` (enabled, min_samples, quantiles, defaults je Typ) |
| `core/commands/00-intake.md` | MODIFY | Score per `--score` an `start` übergeben, danach `workflow.py estimate` ausführen und LINE in der Intake-Bewertung nennen |
| `skills/00-intake/SKILL.md` | MODIFY | Generat aus `core/commands/00-intake.md` (`python3 scripts/sync_skills.py`) |
| `tests/test_zeitschaetzung_620.py` | CREATE | Tests der Schätzlogik, Plan-Zeilen, CLI, Start-Stempel, Retro, Fail-open |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]` (keine Versionsnummer) |

### Estimated Changes

- Files: 6
- LoC: +250/-5 (davon ca. 120 Tests)
- Keine Gate-Wirkung: alle neuen Felder (`intake_score`, `estimate_initial`) und Zeilen sind reine Anzeige; kein Hook blockt daran.

## Implementation Details

**Datenquelle.** Erfahrungswerte sind die archivierten Workflows `.claude/workflows/_archive/*.json`. Je Workflow zählt das Feld `phase_log`: nur Einträge mit `exited_at` und `duration_min` (abgeschlossen). Die Dauer je Phase ist die Summe aller abgeschlossenen Einträge dieser Phase (Wiedereintritte nach Rücksprung). Workflows mit `status == "abandoned"` und solche ohne abgeschlossene `phase_log`-Einträge zählen nicht. Dauern sind Wanduhr-Minuten.

**Vergleichsgruppe.** Zuerst nach `workflow_type` (feature, feature-fast). Die Score-Stufe kommt aus dem State-Feld `intake_score`: "0" (Score 0), "1-3", "4-6". Liegen mindestens `min_samples` (Default 3) Archiv-Workflows desselben Typs UND derselben Stufe vor, bilden nur diese die Gruppe; sonst alle des Typs. Hat auch der Typ weniger als `min_samples` Workflows, gelten die Startwerte aus `time_estimate.defaults` (je Typ [low, high] in Minuten, z.B. feature [60, 240], feature-fast [20, 60]), skaliert mit dem Anteil noch offener Plan-Schritte (offene Schritte geteilt durch alle Schritte des Tracks). Archiv-Workflows ohne `intake_score` (Altbestand) zählen nur für die Typ-Gruppe.

**Restdauer.** Je Vergleichs-Workflow: `max(0, Dauer der aktuellen Phase - bereits in dieser Phase verstrichene Zeit) + Summe der Dauern aller späteren Phasen des Plans` (`PLAN_STEPS` bzw. `PLAN_STEPS_FAST`). Eine Phase, die der Vergleichs-Workflow nicht hatte, trägt 0 bei. Spanne = Quantile der Restdauern (Default 0.25 und 0.75, `time_estimate.quantiles`), Punktwert = Median, lineare Interpolation. Prognose-Ende = jetzt + Spanne. Folge: je weniger Phasen offen, desto enger die Spanne ("wird präziser"); jeder neu archivierte Workflow ist automatisch ein weiterer Messpunkt ("lernt"). Median und Quantile sind robust gegen Ausreißer (Nacht, Wartezeit), der Mittelwert wäre es nicht.

**Pure Funktion.** `estimate_remaining(data, history, config, now)` bekommt den aktuellen State, die geladenen Archiv-Dauern, die Konfiguration und `now` (injizierbar) und liefert ein Dict: `low_min`, `mid_min`, `high_min` (Rest), `elapsed_min`, `total_low_min`, `total_high_min` (gesamt = verstrichen + Rest), `n` (Zahl der Vergleichs-Workflows, 0 bei Startwerten), `source` ("archive" oder "default"), `start`, `end_low`, `end_high`. Das Laden des Archivs ist davon getrennt (`load_archive_phase_durations`) und liefert Listen je Workflow aus Typ, Stufe und Phasendauern. In `plan --watch` wird das Ergebnis gecacht und nur neu geladen, wenn sich mtime oder Dateizahl des Archivordners ändern; die Schätzung selbst (billig) wird je Runde mit aktuellem `now` neu berechnet, sodass das Ende dynamisch mitläuft.

**Plan-Pane.** `render_plan(..., estimate=None)`: ohne `estimate` entstehen keine neuen Zeilen, die Ausgabe ist byte-gleich wie bisher (Bestandstests bleiben unverändert). Mit `estimate` folgt nach der Schrittliste (vor der Schlusszeile) ein Block aus drei Zeilen:

- `Start  HH:MM` aus dem State-Feld `created`; liegt der Start nicht auf dem heutigen Tag, mit Datum (`DD.MM. HH:MM`).
- `Dauer  ca. X–Y (aus N Workflows)` bzw. `(Startwert)`; X und Y sind die Gesamtdauer (verstrichen + Rest) im lesbaren Format: unter 60 Minuten "45 min", sonst "1 h 10 min", volle Stunden "2 h"; die Spanne mit Gedankenstrich ohne Leerzeichen, z.B. "1 h 10 min–2 h 30 min".
- `Ende  ca. HH:MM–HH:MM` (Prognose-Ende untere/obere Spanne); liegt ein Wert nicht auf dem heutigen Tag, mit Datum.

Entscheidung für abgeschlossene und archivierte Workflows: Dort gibt es keine Prognose mehr. Der Block zeigt nur `Start  HH:MM` und `Ende  HH:MM` (tatsächlich, aus `exited_at` des letzten `phase_log`-Eintrags bzw. `updated`) und die tatsächliche Gesamtdauer `Dauer  X` ohne "ca."; fehlen die Zeitstempel, entfällt der Block. Abgebrochene Workflows zeigen keinen Block.

**CLI und Start.** `workflow.py start <name> ... --score N` (N ganzzahlig 0-6, sonst Exit 1 mit Usage) speichert `intake_score` im State und stempelt `estimate_initial` = `{low, mid, high, n, source, at}` (Gesamtdauer-Spanne in Minuten zum Startzeitpunkt). Ohne `--score` bleibt `start` unverändert (kein `intake_score`, Stufe unbekannt, Schätzung dann nur nach Typ). Neues CLI `workflow.py estimate` gibt KEY=value-Zeilen aus: `ESTIMATE=on|off`, `ESTIMATE_LOW_MIN`, `ESTIMATE_HIGH_MIN`, `ESTIMATE_START`, `ESTIMATE_END_LOW`, `ESTIMATE_END_HIGH`, `ESTIMATE_BASIS` (Zahl N oder `default`), `LINE=<menschenlesbarer Satz>`, z.B. "Grobe Schätzung: 1 h 10 min–2 h 30 min, Ende ca. 15:40–17:00 (aus 7 Workflows)". Exit immer 0. Bei `enabled: false` oder Fehler: nur `ESTIMATE=off`.

**Retro.** `workflow.py retro <name>` zeigt zusätzlich eine Zeile "Schätzung vs. Ist: geschätzt X–Y, tatsächlich Z (innerhalb|darunter|darüber)", wenn `estimate_initial` vorhanden ist (Lernnachweis). Ohne `estimate_initial` bleibt die Ausgabe unverändert.

**Konfiguration, Kill-Switch, Fail-open.** `config.yaml`: `time_estimate: {enabled: true, min_samples: 3, quantiles: [0.25, 0.75], defaults: {feature: [60, 240], feature-fast: [20, 60]}}`. `enabled: false` ergibt keine Zeit-Zeilen und `ESTIMATE=off`. Jeder Fehler (kaputte Archiv-Datei, fehlende Felder, ungültige Zeitstempel, Konfigurationsfehler) führt zu "keine Zeit-Zeilen"; `plan`, `start` und `plan --watch` brechen nie ab.

**Intake.** `core/commands/00-intake.md`: der Score wird bei `workflow.py start` per `--score` übergeben; nach dem Start läuft `workflow.py estimate`, und die `LINE=` kommt in die Intake-Bewertung. `skills/00-intake/SKILL.md` wird mit `python3 scripts/sync_skills.py` neu erzeugt.

## Expected Behavior

- Beim Start nennt Intake eine Spanne, z.B. "Grobe Schätzung: 1 h 10 min–2 h 30 min, Ende ca. 15:40–17:00 (aus 7 Workflows)"; ohne genug Erfahrungswerte "(Startwert)".
- Der Plan-Pane zeigt unter den Schritten `Start`, `Dauer ca.` und `Ende ca.`; das Ende rückt je Runde mit der Uhr und dem Fortschritt nach.
- Mit jeder durchlaufenen Phase wird die Spanne enger; mit jedem archivierten Workflow beruht sie auf mehr Messpunkten.
- Abgeschlossene Workflows zeigen tatsächlichen Start, Ende und Dauer statt einer Prognose.

## Known Limitations

- Das Archiv ist rechnerlokal (gitignored); Cloud-Container starten meist mit Startwerten, die Anzeige sagt dann "(Startwert)".
- Die Wanduhrzeit enthält PO-Wartezeit (gewollt: der PO fragt nach Kalenderzeit); Nacht- und Wartezeiten bilden Ausreißer, die Quantile dämpfen.
- Die Quantil-Spanne ist eine grobe Schätzung, keine Garantie.
- Die Score-Stufen-Gruppe greift erst, wenn genug Archiv-Workflows mit gespeichertem `intake_score` vorliegen (Altbestand hat keinen).
- Das Ende zeigt keine Rücksicht auf Nacht oder Wochenende, nur reine Kalenderdauer.

## Definition of Done

- Alle AC-1 bis AC-12 durch `tests/test_zeitschaetzung_620.py` belegt, gesamte Testsuite grün (Bestandstests zu Plan, Herdr und Intake unverändert grün).
- `python3 scripts/sync_skills.py --check` ohne Drift; `python3 scripts/release_check.py --no-tests` grün.
- `core/commands/00-intake.md` beschreibt `--score` und `workflow.py estimate`; CHANGELOG-Eintrag unter `[Unreleased]`.
- Kill-Switch `time_estimate.enabled: false` und Fail-open sind per Test belegt.

## Acceptance Criteria

- **AC-1:** Given archivierte Workflows mit `phase_log`, darunter ein abgebrochener, einer ohne abgeschlossene Einträge und einer mit Wiedereintritt in dieselbe Phase / When `load_archive_phase_durations` läuft / Then zählen abgebrochene und leere Workflows nicht, und die Dauer je Phase ist die Summe aller abgeschlossenen Einträge dieser Phase; eine kaputte Archiv-Datei wird übersprungen, ohne Fehler.
- **AC-2:** Given Vergleichs-Workflows und ein aktueller State in einer Phase mit bereits verstrichener Zeit / When `estimate_remaining(..., now)` läuft / Then ist die Restdauer je Vergleichs-Workflow `max(0, Dauer aktuelle Phase - verstrichen) + Summe der Dauern aller späteren Phasen` (Track-abhängig `PLAN_STEPS` bzw. `PLAN_STEPS_FAST`), Spanne = Quantile 0.25/0.75, Punktwert = Median, und `end_low/end_high` = `now` + Spanne.
- **AC-3:** Given dieselbe Historie / When die Schätzung in einer früheren und in einer späteren Phase berechnet wird / Then ist die Spanne (high - low) in der späteren Phase nicht größer als in der früheren ("wird präziser"), und ein zusätzlicher Archiv-Workflow ändert das Ergebnis ("lernt").
- **AC-4:** Given mindestens `min_samples` Workflows derselben Score-Stufe ("0", "1-3", "4-6") / When geschätzt wird / Then nutzt die Gruppe nur diese; bei weniger gleicher Stufe alle des Typs (`workflow_type`); bei weniger als `min_samples` insgesamt die Startwerte aus `time_estimate.defaults`, skaliert mit dem Anteil offener Plan-Schritte, mit `source == "default"` und `n == 0`.
- **AC-5:** Given ein Schätzungs-Dict / When `render_plan(..., estimate=est)` läuft / Then folgen nach der Schrittliste die Zeilen `Start  HH:MM`, `Dauer  ca. X–Y (aus N Workflows)` bzw. `(Startwert)` und `Ende  ca. HH:MM–HH:MM` (mit Datum, wenn nicht heute); Dauer lesbar ("45 min", "1 h 10 min–2 h 30 min"); ohne `estimate` ist die Ausgabe byte-gleich wie bisher.
- **AC-6:** Given ein abgeschlossener oder archivierter Workflow / When `render_plan` mit Zeitdaten läuft / Then zeigt der Block `Start`, tatsächliches `Ende HH:MM` und tatsächliche `Dauer X` ohne "ca." und ohne Prognose; abgebrochene Workflows und fehlende Zeitstempel ergeben keinen Block.
- **AC-7:** Given `plan --watch` über mehrere Runden / When das Archiv unverändert bleibt / Then wird es nur einmal geladen (Cache über mtime und Dateizahl), bei Änderung des Archivordners neu; die Schätzung wird je Runde mit aktuellem `now` neu berechnet, sodass sich das Ende ändert.
- **AC-8:** Given `workflow.py start <name> --score N` / When N im Bereich 0-6 liegt / Then stehen `intake_score` und `estimate_initial` (`low`, `mid`, `high`, `n`, `source`, `at`) im State; ein ungültiger Wert (z.B. 9, "x") ergibt Exit 1 mit Usage; ohne `--score` bleibt `start` unverändert und bricht nie wegen der Schätzung ab.
- **AC-9:** Given ein aktiver Workflow / When `workflow.py estimate` läuft / Then gibt es `ESTIMATE=on`, `ESTIMATE_LOW_MIN`, `ESTIMATE_HIGH_MIN`, `ESTIMATE_START`, `ESTIMATE_END_LOW`, `ESTIMATE_END_HIGH`, `ESTIMATE_BASIS` (Zahl oder `default`) und `LINE=` aus, Exit 0; bei `enabled: false` oder Fehler nur `ESTIMATE=off`, ebenfalls Exit 0.
- **AC-10:** Given ein archivierter Workflow mit `estimate_initial` / When `workflow.py retro <name>` läuft / Then enthält die Ausgabe eine Zeile "Schätzung vs. Ist" mit geschätzter Spanne und tatsächlicher Dauer; ohne `estimate_initial` ist die Retro-Ausgabe unverändert.
- **AC-11:** Given `time_estimate.enabled: false` oder ein Fehler (kaputtes Archiv, ungültiges `created`, fehlende Felder, ungültige Konfiguration) / When `plan`, `plan --watch`, `start` und `estimate` laufen / Then entstehen keine Zeit-Zeilen und kein Abbruch (Exit 0 bei `plan`/`estimate`).
- **AC-12:** Given `core/commands/00-intake.md`, `skills/00-intake/SKILL.md` und `config.yaml` / When gelesen / Then nennen die Befehlstexte `--score` und `workflow.py estimate`, `config.yaml` enthält `time_estimate` mit `enabled`, `min_samples`, `quantiles` und `defaults`, und `scripts/sync_skills.py --check` meldet keine Drift.

## Test Plan

- `python3 -m pytest tests/test_zeitschaetzung_620.py -q` (im venv) — AC-1 bis AC-12.
- `python3 -m pytest tests -q` — gesamte Suite, insbesondere Bestandstests zu `render_plan`, Plan-Pane (#476/#490/#612) und Intake (#254) bleiben unverändert grün.
- `python3 scripts/sync_skills.py --check` und `python3 scripts/release_check.py --no-tests` — DoD.

### Automated Tests (TDD RED)

- [ ] Test 1: GIVEN Archiv-Workflows (ein abgebrochener, einer ohne abgeschlossene Einträge, einer mit Wiedereintritt) WHEN `load_archive_phase_durations` läuft THEN werden nur gültige gezählt und Wiedereintritte je Phase summiert.
- [ ] Test 2: GIVEN eine feste Historie und `now` WHEN `estimate_remaining` in Phase 6 mit 10 min Verstrichenem läuft THEN stimmen Rest, Quantile, Median und Ende exakt.
- [ ] Test 3: GIVEN dieselbe Historie WHEN die Spanne in Phase 3 und in Phase 7 berechnet wird THEN ist sie in Phase 7 nicht weiter.
- [ ] Test 4: GIVEN genug Workflows gleicher Score-Stufe, nur genug gleichen Typs und zu wenige insgesamt WHEN geschätzt wird THEN greifen Stufe, Typ bzw. Startwerte (skaliert) in dieser Reihenfolge.
- [ ] Test 5: GIVEN ein Schätzungs-Dict WHEN `render_plan` mit und ohne `estimate` läuft THEN gibt es mit `estimate` genau den Block `Start`/`Dauer`/`Ende` und ohne `estimate` byte-gleiche Ausgabe.
- [ ] Test 6: GIVEN ein archivierter Workflow WHEN `render_plan` läuft THEN stehen tatsächliches Ende und tatsächliche Dauer ohne "ca.".
- [ ] Test 7: GIVEN `plan --watch` über drei Runden WHEN das Archiv gleich bleibt, dann geändert wird THEN gibt es einen bzw. zwei Ladevorgänge und das Ende rückt mit `now` nach.
- [ ] Test 8: GIVEN `start --score 5` und `start --score 9` WHEN ausgeführt THEN stehen `intake_score` und `estimate_initial` im State bzw. Exit 1 mit Usage.
- [ ] Test 9: GIVEN `workflow.py estimate` WHEN an, aus und bei Fehler THEN erscheinen alle KEY=value-Zeilen bzw. nur `ESTIMATE=off`, immer Exit 0.
- [ ] Test 10: GIVEN ein archivierter Workflow mit `estimate_initial` WHEN `retro` läuft THEN erscheint "Schätzung vs. Ist".
- [ ] Test 11: GIVEN Kill-Switch oder kaputte Eingaben WHEN `plan`/`start`/`estimate` laufen THEN keine Zeit-Zeilen und kein Abbruch.
- [ ] Test 12: GIVEN Befehlstext und Config WHEN gelesen THEN nennen sie `--score`, `workflow.py estimate` und `time_estimate`; `sync_skills.py --check` ohne Drift.

RED-Artefakt: `docs/artifacts/620-red.log`.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Keine neue Architektur: reine Anzeige im bestehenden Plan-Pane (`render_plan` bleibt pure, Zusatzdaten kommen als Parameter), Datenquelle ist das vorhandene `phase_log` der Archiv-Workflows, Parameter und Kill-Switch folgen dem Muster der übrigen `config.yaml`-Abschnitte (`context_budget`, `herdr`); kein Gate, fail-open.

## Changelog

- 1.0 (2026-11-21): Erstfassung nach PO-Auftrag (Zeitschätzung mit Spanne, Lernen aus dem Archiv, Anzeige im Plan-Pane).
