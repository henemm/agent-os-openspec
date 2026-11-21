# Context: feat-620-zeitschaetzung

## Request Summary
Intake soll zu Beginn eine grobe, auf Erfahrungswerten beruhende Dauer-Schätzung des Workflows
nennen; das rechte Plan-Pane zeigt Startzeit, Schätzung und prognostiziertes Ende, das sich
dynamisch anpasst. Nachtrag PO: Das System soll selbst lernen und immer präziser werden; zu
Beginn gern eine Zeitspanne, die mit dem Fortschritt enger wird.

## Related Files
| File | Relevance |
|------|-----------|
| `core/hooks/workflow.py` `_log_phase_transition` (~1585) | schreibt `phase_log` je Phase: `entered_at`, `exited_at`, `duration_min` (Wanduhr) — Datenquelle |
| `core/hooks/workflow.py` `_archive_dir()` (~1206) | `.claude/workflows/_archive/*.json` — abgeschlossene Workflows = Erfahrungswerte |
| `core/hooks/workflow.py` `cmd_retro_list`/`cmd_retro` (~4026) | bestehende Auswertung der Archiv-Dauern (Summe der `duration_min`), Muster zum Lesen |
| `core/hooks/workflow.py` `render_plan` (607) / `_plan_lines` (695) | Plan-Text (pure) — hier kommen Start/Spanne/Ende-Zeilen hinein |
| `core/hooks/workflow.py` `_plan_watch` (2732) | zeichnet je Runde (Default 1 s) neu, nur bei Textänderung — dynamische Prognose ohne Zusatzmechanik |
| `core/hooks/workflow.py` `PLAN_STEPS`/`PLAN_STEPS_FAST` (336) | Phasenfolge je Track — bestimmt „offene Phasen“ |
| `core/commands/00-intake.md` | Intake-Ablauf; Score (Summe 0–6) wird heute NICHT im State gespeichert, nur `workflow_type` |
| `config.yaml` (`herdr.plan_pane`, `context_budget`) | Ort für Kill-Switch/Parameter (`time_estimate:`) |
| `skills/00-intake/SKILL.md` | Generat aus `core/commands/00-intake.md` (`scripts/sync_skills.py`) |
| Tests `tests/test_plan_*`, `tests/test_herdr_plan_pane_476.py`, `tests/test_intake_two_tracks_254.py` | Muster für Plan-/Intake-Tests |

## Existing Patterns
- Plan-Pane-Inhalte entstehen rein aus dem Workflow-State in `render_plan` (pure, testbar); neue Infos (Issue-Titel #490, Brief #612, Ship #612) wurden jeweils als Zeilen im Kopf/Fuß ergänzt.
- Archiv-Auswertung: `phase_log`-Einträge mit `exited_at` und `duration_min` summieren; abgebrochene Workflows (`status == "abandoned"`) gesondert.
- Optionale Features mit Kill-Switch in `config.yaml` und fail-open.
- CLI-Ausgaben als `KEY=value`-Zeilen (`autonomy`, `queue`, `context`) für Befehlstexte.

## Archiv-Befund (dieser Rechner, 9 Workflows, alle `feature`)
Gesamtdauern 36–562 min; Ausreißer (506, 562 min) enthalten Wartezeiten/Nacht. → Robuste
Statistik nötig (Median/Quantile statt Mittelwert), Spanne statt Punktwert.

## Ansatz (Skizze)
- Je archiviertem Workflow desselben Tracks: Restdauer ab aktueller Phase = (Dauer aktuelle Phase − bereits verstrichene, min 0) + Summe der Dauern der späteren Phasen.
- Spanne = unteres/oberes Quantil (z.B. p25–p75) dieser Restdauern, Punkt = Median; Ende = jetzt + Restdauer. Je weniger Phasen offen, desto enger die Spanne → „wird präziser“.
- Lernen: jeder archivierte Workflow ist automatisch ein weiterer Messpunkt; Intake-Score und Start-Schätzung im State ablegen, damit (a) künftig nach Größenklasse (1–3 / 4–6) gefiltert und (b) Schätzung gegen Ist verglichen werden kann.
- Fallback ohne genug Archivdaten (< Mindestanzahl): feste Startwerte je Track aus `config.yaml`.

## Dependencies
- Upstream: `phase_log`, `_archive_dir`, `_read_workflow`, `datetime`.
- Downstream: `render_plan` (Plan-Pane, `workflow.py plan`), `/00-intake`-Befehlstext, Tests zu `render_plan` (Zeilenanzahl/Format dürfen bestehende Assertions nicht brechen).

## Existing Specs
- Plan-Pane: `docs/specs/` zu #476/#490/#612 (Plan-Kopf), Intake-Tracks #254.

## Risks & Considerations
- `render_plan` ist pure → `now` als Parameter injizieren (Testbarkeit), Archiv-Lesen außerhalb.
- `_plan_watch` rendert jede Sekunde: Archiv nicht jede Sekunde neu lesen (cachen/mtime).
- Bestehende Plan-Tests prüfen genaue Zeilen → neue Zeilen nur bei vorhandener Schätzung bzw. an definierter Stelle.
- Wanduhr-Dauern enthalten PO-Wartezeit — gewollt (PO fragt nach Kalenderzeit), aber Ausreißer.
- Archiv ist rechnerlokal (gitignored); Cloud-Container verlieren es → dort meist Startwerte.
- Phase-Rücksprünge erzeugen mehrere `phase_log`-Einträge je Phase → je Phase summieren.

## Analysis

### Type
Feature

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/workflow.py` | MODIFY | Archiv-Dauern laden (gecacht), pure Schätzfunktion (Quantile der Restdauer), `render_plan(..., estimate=None)` Zeit-Block, `start --score N` (speichert `intake_score` + `estimate_initial`), neues CLI `estimate`, Retro-Zeile „Schätzung vs. Ist“, `_plan_watch` übergibt Schätzung |
| `config.yaml` | MODIFY | Abschnitt `time_estimate` (enabled, min_samples, quantiles, defaults je Track) |
| `core/commands/00-intake.md` | MODIFY | Score an `start --score` übergeben, `workflow.py estimate` ausgeben |
| `skills/00-intake/SKILL.md` | MODIFY | Generat (`scripts/sync_skills.py`) |
| `tests/test_zeitschaetzung_620.py` | CREATE | Tests der Schätzlogik, Plan-Zeilen, CLI, Start-Stempel |
| `CHANGELOG.md` | MODIFY | `[Unreleased]` |

### Scope Assessment
- Files: 6
- Estimated LoC: +250/-5 (davon ~120 Tests)
- Risk Level: MEDIUM (zentrale Datei, aber nur Anzeige; kein Gate, fail-open)

### Technical Approach
- Erfahrungswerte: je archiviertem, nicht abgebrochenem Workflow Dauer je Phase (Summe über Wiedereintritte, nur abgeschlossene Einträge).
- Gruppe: gleicher `workflow_type`; liegen ≥ `min_samples` Workflows derselben Score-Stufe (1–3 / 4–6, aus `intake_score`) vor, nur diese; sonst alle des Typs; sonst Startwerte aus Config (skaliert nach Anteil offener Plan-Schritte).
- Restdauer je Vergleichs-Workflow = max(0, Dauer aktuelle Phase − verstrichene Zeit in der Phase) + Summe späterer Phasen. Spanne = Quantile (Default p25/p75), Punkt = Median. Ende = jetzt + Spanne. Je weniger offen, desto enger → „präziser“; jedes neue Archiv-Exemplar → „lernt“.
- `render_plan` bleibt pure: Schätzung wird als fertiges Dict übergeben; ohne Dict keine neuen Zeilen (bestehende Tests unberührt). Block nach Schrittliste: `Start`, `Dauer`, `Ende`.
- `_plan_watch`: Archiv-Laden gecacht über (mtime, Anzahl) des Archivordners; Schätzung je Runde neu (billig) → Ende passt sich dynamisch an.
- Lernnachweis: `estimate_initial` beim Start im State; `retro` zeigt Schätzung vs. Ist.
- Fail-open: jeder Fehler → keine Zeit-Zeilen, nie Abbruch. Kill-Switch `time_estimate.enabled`.

### Dependencies
- Nutzt `_archive_dir`, `_read_workflow`, `phase_log`, `load_config`.
- Analyse ohne zusätzliche Teilagenten: Summe 3 → ein Durchgang (Intake-Regel #254); Kontext deckt Dateien, Muster und Abhängigkeiten ab.

### Open Questions
- keine (Darstellung und Statistik entscheidet der Tech Lead; PO-Wunsch Spanne + Lernen ist aufgenommen)
