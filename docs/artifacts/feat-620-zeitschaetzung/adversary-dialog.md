# Adversary Dialog — feat-620-zeitschaetzung
Spec: docs/specs/feat-620-zeitschaetzung.md
Datum: 2026-11-21 14:03

## Checkliste
- [x] Beim Start nennt Intake eine Spanne, z.B. "Grobe Schätzung: 1 h 10 min–2 h 30 min, Ende ca. 15:40–17:00 (aus 7 Workflows)"; ohne genug Erfahrungswerte "(Startwert)".
- [x] Der Plan-Pane zeigt unter den Schritten `Start`, `Dauer ca.` und `Ende ca.`; das Ende rückt je Runde mit der Uhr und dem Fortschritt nach.
- [x] Mit jeder durchlaufenen Phase wird die Spanne enger; mit jedem archivierten Workflow beruht sie auf mehr Messpunkten.
- [x] Abgeschlossene Workflows zeigen tatsächlichen Start, Ende und Dauer statt einer Prognose.
- [x] **AC-1:** Given archivierte Workflows mit `phase_log`, darunter ein abgebrochener, einer ohne abgeschlossene Einträge und einer mit Wiedereintritt in dieselbe Phase / When `load_archive_phase_durations` läuft / Then zählen abgebrochene und leere Workflows nicht, und die Dauer je Phase ist die Summe aller abgeschlossenen Einträge dieser Phase; eine kaputte Archiv-Datei wird übersprungen, ohne Fehler.
- [x] **AC-2:** Given Vergleichs-Workflows und ein aktueller State in einer Phase mit bereits verstrichener Zeit / When `estimate_remaining(..., now)` läuft / Then ist die Restdauer je Vergleichs-Workflow `max(0, Dauer aktuelle Phase - verstrichen) + Summe der Dauern aller späteren Phasen` (Track-abhängig `PLAN_STEPS` bzw. `PLAN_STEPS_FAST`), Spanne = Quantile 0.25/0.75, Punktwert = Median, und `end_low/end_high` = `now` + Spanne.
- [x] **AC-3:** Given dieselbe Historie / When die Schätzung in einer früheren und in einer späteren Phase berechnet wird / Then ist die Spanne (high - low) in der späteren Phase nicht größer als in der früheren ("wird präziser"), und ein zusätzlicher Archiv-Workflow ändert das Ergebnis ("lernt").
- [x] **AC-4:** Given mindestens `min_samples` Workflows derselben Score-Stufe ("0", "1-3", "4-6") / When geschätzt wird / Then nutzt die Gruppe nur diese; bei weniger gleicher Stufe alle des Typs (`workflow_type`); bei weniger als `min_samples` insgesamt die Startwerte aus `time_estimate.defaults`, skaliert mit dem Anteil offener Plan-Schritte, mit `source == "default"` und `n == 0`.
- [x] **AC-5:** Given ein Schätzungs-Dict / When `render_plan(..., estimate=est)` läuft / Then folgen nach der Schrittliste die Zeilen `Start  HH:MM`, `Dauer  ca. X–Y (aus N Workflows)` bzw. `(Startwert)` und `Ende  ca. HH:MM–HH:MM` (mit Datum, wenn nicht heute); Dauer lesbar ("45 min", "1 h 10 min–2 h 30 min"); ohne `estimate` ist die Ausgabe byte-gleich wie bisher.
- [x] **AC-6:** Given ein abgeschlossener oder archivierter Workflow / When `render_plan` mit Zeitdaten läuft / Then zeigt der Block `Start`, tatsächliches `Ende HH:MM` und tatsächliche `Dauer X` ohne "ca." und ohne Prognose; abgebrochene Workflows und fehlende Zeitstempel ergeben keinen Block.
- [x] **AC-7:** Given `plan --watch` über mehrere Runden / When das Archiv unverändert bleibt / Then wird es nur einmal geladen (Cache über mtime und Dateizahl), bei Änderung des Archivordners neu; die Schätzung wird je Runde mit aktuellem `now` neu berechnet, sodass sich das Ende ändert.
- [x] **AC-8:** Given `workflow.py start <name> --score N` / When N im Bereich 0-6 liegt / Then stehen `intake_score` und `estimate_initial` (`low`, `mid`, `high`, `n`, `source`, `at`) im State; ein ungültiger Wert (z.B. 9, "x") ergibt Exit 1 mit Usage; ohne `--score` bleibt `start` unverändert und bricht nie wegen der Schätzung ab.
- [x] **AC-9:** Given ein aktiver Workflow / When `workflow.py estimate` läuft / Then gibt es `ESTIMATE=on`, `ESTIMATE_LOW_MIN`, `ESTIMATE_HIGH_MIN`, `ESTIMATE_START`, `ESTIMATE_END_LOW`, `ESTIMATE_END_HIGH`, `ESTIMATE_BASIS` (Zahl oder `default`) und `LINE=` aus, Exit 0; bei `enabled: false` oder Fehler nur `ESTIMATE=off`, ebenfalls Exit 0.
- [x] **AC-10:** Given ein archivierter Workflow mit `estimate_initial` / When `workflow.py retro <name>` läuft / Then enthält die Ausgabe eine Zeile "Schätzung vs. Ist" mit geschätzter Spanne und tatsächlicher Dauer; ohne `estimate_initial` ist die Retro-Ausgabe unverändert.
- [x] **AC-11:** Given `time_estimate.enabled: false` oder ein Fehler (kaputtes Archiv, ungültiges `created`, fehlende Felder, ungültige Konfiguration) / When `plan`, `plan --watch`, `start` und `estimate` laufen / Then entstehen keine Zeit-Zeilen und kein Abbruch (Exit 0 bei `plan`/`estimate`).
- [x] **AC-12:** Given `core/commands/00-intake.md`, `skills/00-intake/SKILL.md` und `config.yaml` / When gelesen / Then nennen die Befehlstexte `--score` und `workflow.py estimate`, `config.yaml` enthält `time_estimate` mit `enabled`, `min_samples`, `quantiles` und `defaults`, und `scripts/sync_skills.py --check` meldet keine Drift.

## Dialog

### Runde 1
**Adversary:** Angriff auf Schaetzlogik, Archiv-Laden, Score-Parsing, Kill-Switch (Probelaeufe: probe-1/out.txt, probe-2, probe-3/out.txt).
- Mitternacht: Start 20.11. 23:50, now 00:10 -> `Start  20.11. 23:50`, Ende ohne Datum; Datumslogik greift (workflow.py:1005).
- Fast Track, Phase nicht im Plan (phase1/5/6b/0): `_estimate_steps` (workflow.py:~900) faellt auf letzten Plan-Schritt <= pos zurueck, kein Absturz; unbekannte Phase -> None -> fail-open.
- `--score` 9, x, -1, 05, 3.0, leer, fehlend: alle Exit 1 mit Usage (workflow.py START_USAGE, cmd_start). 0-6 ok; `estimate_initial` und `intake_score` im State.
- Ohne `--score`: kein `intake_score`/`estimate_initial`, Start unveraendert.
- Archiv: abandoned, leer, kaputt (garbage), Liste, NaN, Strings als Dauer, unhashable workflow_type -> kein Absturz, nur gueltige Eintraege; Wiedereintritte summiert (10+5=15).
- Gruppenwahl: 3x gleiche Stufe -> nur Stufe; 2x Stufe + 5 Typ -> 7 Typ; 2 gesamt oder anderer Typ -> Startwerte, skaliert (60/240 * 4/9 in Phase 6 = 26.7/106.7), source=default, n=0.
- Kill-Switch per CLI: `enabled: false`, YAML-`no`, `time_estimate: false`, Liste, min_samples 'x', Quantile verkehrt -> `ESTIMATE=off`, 0 Zeit-Zeilen, Exit 0; fehlender Abschnitt -> an (Defaults); `enabled: "no"` (String) -> bleibt an (siehe F003).
- Byte-gleiche Ausgabe ohne estimate: `render_plan(d)==render_plan(d, estimate=None)` True.
**Implementierer:** Tests: 116 passed (tests/test_zeitschaetzung_620.py, test_plan_*, test_herdr_plan_pane_476, test_intake_two_tracks_254); sync_skills --check synchron; ci_spec_gate/config_loader-Tests 27 passed.

### Runde 2
**Adversary:** Zweite Runde gegen Grenzen und fail-open (kein Early Agreement).
- Negative `duration_min` im Archiv wird akzeptiert -> negative Restdauer (-100 min) (F001).
- NaN-Dauer im Archiv: Plan/estimate fallen auf "keine Zeilen"/`ESTIMATE=off` zurueck, `start --score` wuerde NaN stempeln (F004).
- Fertiger Workflow mit `last_updated` < `created`: `Dauer 0 min`, Ende vor Start (F002).
- Retro: `estimate_initial` + Ist -60 min -> "darunter"; ohne `estimate_initial` Ausgabe unveraendert (nur `_retro_estimate_line` -> None).
- Wiedereintritt: `_minutes_in_phase` nimmt den offenen Eintrag (letzter, exited_at None); Rest = max(0, Dauer - verstrichen) + spaetere Phasen (workflow.py:930-946).
- Cache: `_archive_cache_key` (mtime_ns, Dateizahl); Schaetzung je Runde mit neuem now (current_estimate:980).
- plan --watch: current_estimate faengt alle Fehler; Aufruf liegt in der bestehenden Schleife; Tests (Test 7) belegen 1 bzw. 2 Ladevorgaenge.
- Spanne enger in spaeterer Phase: durch Konstruktion (weniger Summanden); bei low==high zeigt Anzeige "35 min–35 min" (kosmetisch, F002).
**Implementierer:** Keine spec-widrigen Defekte; nur LOW-Anmerkungen.

## Findings

Finding:
  ID: F001
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/workflow.py:813
  Description: `_archive_phase_entry` akzeptiert jede numerische `duration_min`, auch negative; Restdauer und Spanne koennen negativ werden ("-100 min").
  Spec requirement: AC-1 — nur abgeschlossene Eintraege mit `duration_min` zaehlen
  Conflict: Spec schweigt zu negativen Werten; reale Archive erzeugen sie nur bei Uhrspruengen. Keine Spec-Verletzung.
  Remediation: `dur >= 0` und `math.isfinite` pruefen.

Finding:
  ID: F002
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/workflow.py:1021
  Description: `_finished_span`/`_plan_time_lines` rendern bei `last_updated` < `created` "Dauer 0 min" mit Ende vor Start; bei low==high steht "35 min–35 min".
  Spec requirement: AC-5/AC-6 — Anzeigeformat
  Conflict: Nur kosmetisch.
  Remediation: Ende auf mindestens Start klemmen; gleiche Grenzen zu einem Wert zusammenfassen.

Finding:
  ID: F003
  Severity: LOW
  Category: spec_violation
  Code reference: core/hooks/config_loader.py:50
  Description: `enabled: "no"` (String) schaltet nicht ab; nur `false` (und YAML-`no`) -> `_valid_estimate_config` (workflow.py:851). Gewollt laut config.yaml-Kommentar und Spec ("enabled: false"); config_loader/ci_spec_gate nur um den Schluessel ergaenzt (scripts/ci_spec_gate.py:97).
  Spec requirement: AC-11 — Kill-Switch `enabled: false`
  Conflict: Keiner; als Hinweis aufgefuehrt.
  Remediation: Optional Strings "false"/"no"/"off" ebenfalls als aus werten.

Finding:
  ID: F004
  Severity: LOW
  Category: edge_case
  Code reference: core/hooks/workflow.py:2818
  Description: `_stamp_intake_estimate` stempelt NaN/Inf, falls das Archiv NaN-Dauern enthaelt (JSON-NaN wird gelesen); Anzeige faellt dann auf "keine Zeilen" zurueck, start bricht nicht ab.
  Spec requirement: AC-8/AC-11 — fail-open
  Conflict: Keiner (fail-open haelt), nur unsauberer State-Wert.
  Remediation: In `_archive_phase_entry` nicht-endliche Werte verwerfen.

## Confirmations

Confirmation:
  AC: AC-1
  Code reference: core/hooks/workflow.py:831
  Evidence: probe-3: abandoned/leer/kaputt/Liste uebersprungen, Wiedereintritte summiert (15.0).
  Status: CONFIRMED

Confirmation:
  AC: AC-2
  Code reference: core/hooks/workflow.py:949
  Evidence: Rest = max(0, Dauer - verstrichen) + spaetere Phasen (930-946), Quantile 0.25/0.5/0.75, end = now + Spanne; Mitternachtsprobe.
  Status: CONFIRMED

Confirmation:
  AC: AC-3
  Code reference: core/hooks/workflow.py:930
  Evidence: weniger spaetere Summanden -> Spanne nicht groesser; weiterer Archiv-Workflow aendert Gruppe (n). Tests gruen.
  Status: CONFIRMED

Confirmation:
  AC: AC-4
  Code reference: core/hooks/workflow.py:918
  Evidence: probe-3: Stufe (3) > Typ (7) > Startwerte; default 26.7/106.7 bei Phase 6, source=default, n=0.
  Status: CONFIRMED

Confirmation:
  AC: AC-5
  Code reference: core/hooks/workflow.py:1032
  Evidence: CLI-Plan zeigt Start/Dauer ca./Ende ca. nach der Schrittliste; Datum bei anderem Tag; ohne estimate byte-gleich.
  Status: CONFIRMED

Confirmation:
  AC: AC-6
  Code reference: core/hooks/workflow.py:1021
  Evidence: actual-Block ohne "ca."; abandoned -> []; kaputtes created -> [] (probe-3).
  Status: CONFIRMED

Confirmation:
  AC: AC-7
  Code reference: core/hooks/workflow.py:3034
  Evidence: est_cache + `_archive_cache_key`; now je Runde neu (current_estimate:980); Test 7 gruen.
  Status: CONFIRMED

Confirmation:
  AC: AC-8
  Code reference: core/hooks/workflow.py:2818
  Evidence: CLI-Probe: 9, x, -1, 05, 3.0, leer, fehlend -> Exit 1 Usage; 5 -> intake_score 5 und estimate_initial im State; ohne --score keine Felder.
  Status: CONFIRMED

Confirmation:
  AC: AC-9
  Code reference: core/hooks/workflow.py:4850
  Evidence: CLI: ESTIMATE=on + 7 Keys + LINE, Exit 0; Kill-Switch/Fehlkonfig -> nur ESTIMATE=off, Exit 0.
  Status: CONFIRMED

Confirmation:
  AC: AC-10
  Code reference: core/hooks/workflow.py:4868
  Evidence: Zeile "Schätzung vs. Ist" mit estimate_initial, sonst None -> Ausgabe unveraendert.
  Status: CONFIRMED

Confirmation:
  AC: AC-11
  Code reference: core/hooks/workflow.py:980
  Evidence: current_estimate faengt alle Exceptions; Kill-Switch-Varianten per CLI (0 Zeit-Zeilen, Exit 0); kaputtes created -> keine Zeilen.
  Status: CONFIRMED

Confirmation:
  AC: AC-12
  Code reference: core/hooks/config_loader.py:50
  Evidence: time_estimate in PLUGIN_CONFIG_KEYS (config_loader.py:50, ci_spec_gate.py:97); 00-intake.md nennt --score/estimate; sync_skills --check synchron; config.yaml-Abschnitt vollstaendig.
  Status: CONFIRMED

Confirmation:
  AC: Expected Behavior (4 Punkte)
  Code reference: scripts/ci_spec_gate.py:97
  Evidence: Intake-LINE, Plan-Block, engere Spanne, Ist-Block bei fertigen Workflows per Probe belegt; ci_spec_gate-Schluesselliste synchron zu config_loader.
  Status: CONFIRMED

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict

VERDICT: VERIFIED
Tests: 116 passed, 0 failed, 0 uebersprungen (Ziel-Tests); Gesamtsuite gruen laut full-suite.txt
Edge cases: geprueft, keine Spec-Verletzung (4 LOW-Anmerkungen F001-F004)
Regressions: None found
Checklist: 16/16 points proven

## Geprüfte Dateien

- sha256:a070fd118e6d7a65c2b98f699ab02308708fe4dd902b540d801e654e9ee08f6b  core/hooks/config_loader.py
- sha256:963782da7ee775cbf9d5e40c0ff648646363ce82ec6141a37dc103111429928b  core/hooks/workflow.py
- sha256:62cd0e9c4a5716b98e7bcbc91dd8de03c810c0aecaf8db586f4c0461b6581169  scripts/ci_spec_gate.py

## Prüfbasis

- base: 5e31cde2d2abc6d29b506f8d5606e14e3cc601cb
- blob:d971752d04c353db9066b8ecb58e70a498c06b48  core/hooks/config_loader.py
- blob:2a243293cc839d450bd50d55fbb9186c00d3575a  core/hooks/workflow.py
- blob:28822229f2c85b5b57d62c85e0748f60159a7c9e  scripts/ci_spec_gate.py

## Geprüfte Dateien

- sha256:a070fd118e6d7a65c2b98f699ab02308708fe4dd902b540d801e654e9ee08f6b  core/hooks/config_loader.py
- sha256:963782da7ee775cbf9d5e40c0ff648646363ce82ec6141a37dc103111429928b  core/hooks/workflow.py
- sha256:62cd0e9c4a5716b98e7bcbc91dd8de03c810c0aecaf8db586f4c0461b6581169  scripts/ci_spec_gate.py

## Prüfbasis

- base: 5e31cde2d2abc6d29b506f8d5606e14e3cc601cb
- blob:d971752d04c353db9066b8ecb58e70a498c06b48  core/hooks/config_loader.py
- blob:2a243293cc839d450bd50d55fbb9186c00d3575a  core/hooks/workflow.py
- blob:28822229f2c85b5b57d62c85e0748f60159a7c9e  scripts/ci_spec_gate.py
