---
entity_id: feat-250-teil-b-aufwandsbremse
type: module
created: 2026-10-03
updated: 2026-10-03
status: draft
version: "1.0"
tags: [aufwandsbremse, effort-budget, loc, workflow, "#250"]
---

# Aufwandsbremse: Budget je Stufe, Rückfrage statt Blockade, Abschluss-LoC (#250, Teil B)

## Approval

- [ ] Approved

## Purpose

Die Stufen (`feature-fast`, `feature`) werden nach der Wahl nicht mehr spürbar: ein kleiner Fix im
vollen Prozess kostet im Median 3,7 h gegenüber 33 min im Schnellweg (Auswertung über 1.958
Workflows, Repo `gate-audit-data`). Diese Änderung macht Mehraufwand sichtbar, ohne die Prüfung
abzuschneiden: Überschreitet ein Workflow sein Stufen-Budget, **wird der PO gefragt statt still
weitergearbeitet**. Die bestehende 15-Minuten-Bremse wird nach Stufe abgestuft, statt eine zweite
daneben zu stellen. Zusätzlich wird die Änderungsgröße beim Abschluss verlässlich erfasst, weil
`loc_delta_current` bei 661 von 750 `feature`-Workflows `+0` oder leer ist (es misst nur
nicht committete Zeilen beim letzten Edit) und damit „Aufwand im Verhältnis zur Größe" nicht
auswertbar ist.

Entscheidungsgrundlage (PO, 2026-09-26, Issue #250): *Rückfrage bei Überschreitung, protokolliert —
die Gegenprüfung wird nie abgeschnitten; die bestehende 15-Minuten-Bremse wird stufenabhängig
gemacht; eine harte Blockade ist verworfen.*

## Source

- **File:** `core/hooks/workflow.py`, `core/hooks/post_implementation_gate.py`,
  `core/hooks/config_loader.py`, `config.yaml`
- **Identifier:** `record_transition`, `cmd_phase`, `cmd_write_log`, `cmd_complete`,
  `post_implementation_gate._BATCH_WINDOW_S`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `workflow.py::record_transition` | Funktion | einzige Stelle, die einen Phasenwechsel aufzeichnet (#111) — Einhängepunkt für die Budget-Prüfung |
| `workflow.py::_log_phase_transition` / `phase_transitions` | State | liefern Wiedereintritte je Phase; `fix_loop_iterations` liefert die Fix-Loops |
| `hook_utils.log_gate_event` | Funktion | schreibt Überschreitungen ins Gate-Event-Log (#181/#328) |
| `adversary_dialog.py` | Modul | `MIN_ROUNDS`/`MAX_ITERATIONS` bleiben **unverändert**; die Gegenprüfung wird nicht berührt |
| `docs/context/feat-250-prozess-abstufung.md` | Analyse | Befunde F1–F9, Empfehlung „Sichtbarkeit + Rückfrage"; Zählerstände aus dem State, nicht Wanduhrzeit (R1) |
| `scripts/token_report.py` (#332) | Werkzeug | Basislinie für den Meilenstein „Token-Verbrauch senken"; liefert die Vorher/Nachher-Messung, ist hier nicht Teil der Änderung |

## Scope

- **Affected Files:** `core/hooks/workflow.py`, `core/hooks/post_implementation_gate.py`,
  `core/hooks/config_loader.py`, `config.yaml`, `tests/test_effort_budget_250b.py` (neu),
  `CHANGELOG.md`
- **Estimated Changes:** ca. +150 LoC Logik, ca. +200 LoC Tests. 4 Logik-Dateien (Hausregel eingehalten).
- **Nicht enthalten:** Adversary-Runden deckeln oder nur bei Risiko (Meilenstein 2026-10-03). Das
  widerspricht der Entscheidung vom 26.09. („nie abschneiden") und braucht eine eigene
  PO-Entscheidung. Ebenso nicht enthalten: eine harte Blockade, ein Stundenbudget als Sperre, die
  Entfernung des Typs `bug` (A2, #333) und die Auswertung in `gate-audit-data`.

## Implementation Details

1. **`config.yaml` — neuer Block `effort_budget`** mit Kill-Switch `enabled` (nur ein ausdrückliches
   `false` schaltet ab) und Werten je Stufe:
   ```yaml
   effort_budget:
     enabled: true
     feature-fast: {max_fix_loops: 1, max_phase_reentries: 1, batch_window_min: 30}
     feature:      {max_fix_loops: 2, max_phase_reentries: 2, batch_window_min: 15}
   ```
2. **`config_loader.get_effort_budget(workflow_type)`** liefert die Werte der Stufe oder `None`
   (Kill-Switch aus, Block fehlt, unbekannter Typ). Unbekannte Typen (Altbestand `bug`, `express`)
   fallen auf die Werte von `feature`.
3. **`workflow.effort_budget_exceeded(data, budget)`** (reine Funktion): zählt `fix_loop_iterations`
   und den höchsten Wiedereintrittszähler je Phase (Einträge in `phase_transitions` mit `to == Phase`
   abzüglich 1) und liefert die überschrittenen Metriken als Liste `{metric, value, limit}`.
4. **`record_transition()`** ruft sie nach dem Aufzeichnen auf. Neue Überschreitungen (je Metrik und Wert
   nur einmal) werden in `data["budget_events"]` abgelegt, per `log_gate_event("effort_budget", …)`
   protokolliert und von `record_transition` **zurückgegeben**. Der Phasenwechsel wird nie verweigert.
5. **`cmd_phase()`** gibt zurückgegebene Überschreitungen als `RÜCKFRAGE AN DEN PO:` aus (Stufe,
   Metrik, Stand/Grenze, Aufforderung, dem PO den Stand vorzulegen und zu fragen, ob weiter, kleiner
   geschnitten oder abgebrochen wird). Es ist eine Anweisung an Claude, keine Sperre.
6. **`post_implementation_gate.py`:** `_BATCH_WINDOW_S` wird zu `_batch_window_s(workflow)`: Fenster aus
   `effort_budget.<Stufe>.batch_window_min`, ohne Config/bei Kill-Switch 15 min (bisheriges Verhalten).
7. **Abschluss-LoC:** `workflow._final_loc(data)` misst hinzugefügte Zeilen (Produktiv/Test getrennt,
   gleiche Ausschlüsse und Test-Muster wie `edit_gate._check_loc_delta`) mit `git diff <base_commit> --numstat`
   im Mess-Root (Worktree vor Hauptrepo). `cmd_write_log` schreibt `scope_loc_delta` daraus (Fallback:
   `loc_delta_current`) und ein neues Feld `effort_budget_exceeded: <Anzahl>`; `cmd_complete` speichert
   `loc_delta_final`/`loc_delta_test_final` im archivierten State. Schlägt die Messung fehl, wird nichts
   gespeichert und der Abschluss **nicht** blockiert.

## Expected Behavior

- **Input:** Ein Workflow wechselt die Phase (`workflow.py phase …`) und hat sein Stufen-Budget überschritten.
- **Output:** Der Wechsel gelingt; die Ausgabe enthält `RÜCKFRAGE AN DEN PO:` mit Metrik und Grenze;
  `budget_events` und das Gate-Event-Log enthalten den Eintrag.
- **Side effects:** Im Schnellweg greift die 15-Minuten-Bremse später (30 min), im vollen Prozess wie bisher.
  Nach dem Abschluss steht die Änderungsgröße im archivierten State.

## Known Limitations

- Die Rückfrage ist eine Anweisung an Claude; sie wird durch Tests auf Ausgabe und Protokoll belegt,
  nicht durch einen Hook erzwungen. Ob Claude sie befolgt, zeigt erst die Workflow-Auswertung.
- Die Zähler erfassen Fix-Loops und Wiedereintritte, nicht den Token-Verbrauch; dafür ist `token_report`
  die Messung (#332). Ein Token-Budget ist eine spätere Stufe.
- `loc_delta_final` gilt erst für Workflows, die nach dieser Änderung abgeschlossen werden; die
  Altbestände (`+0`) bleiben unauswertbar.
- Die Werte in `effort_budget` sind Startwerte aus der Auswertung (Fix-Loops Ø 0,1; Median Umsetzung 33 min),
  keine Optimierung; sie sind in `config.yaml` pro Projekt änderbar.

## Alternativen (und was sie kippen würden)

1. **Stundenbudget als Sperre:** verworfen (Entscheidung 26.09.): 82 % der Wanduhrzeit sind Wartezeit
   auf den PO, und die bestehende 15-Minuten-Bremse zeigt genau diesen Fehler.
2. **Hartes `max_adversary_rounds`:** verworfen (R3): die dritte Runde bei #237 fand die CRITICAL-Lücke.
3. **Nur die 15-Minuten-Bremse abstufen, keine Zähler:** kleinster Schnitt, lässt aber Fix-Loops und
   Wiedereintritte unsichtbar; die Abnahme-Bedingung „PO wird gefragt" wäre nur halb erfüllt.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Überschreitet ein Workflow sein Stufen-Budget, wird der PO gefragt und der Vorgang protokolliert,
      ohne dass ein Phasenwechsel verweigert oder die Gegenprüfung abgeschnitten wird
- [ ] Die 15-Minuten-Bremse gilt je Stufe, ohne `effort_budget` wie bisher
- [ ] `loc_delta_final` zeigt nach einem Commit die tatsächliche Größe statt `+0`
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen (Regressionslauf grün)

## Acceptance Criteria

- **AC-1:** Given `config.yaml` / When geladen / Then enthält sie `effort_budget` mit `enabled` und den
  Werten `max_fix_loops`, `max_phase_reentries`, `batch_window_min` für `feature-fast` und `feature`,
  und `get_effort_budget()` liefert sie je Stufe; ein unbekannter Typ fällt auf `feature`
  - Test: `tests/test_effort_budget_250b.py::test_config_block_and_stage_lookup`
- **AC-2:** Given ein `feature-fast`-Workflow mit 2 Fix-Loops (Grenze 1) / When `record_transition` läuft /
  Then steht ein Eintrag in `budget_events` und im Gate-Event-Log (`hook` = `effort_budget`)
  - Test: `tests/test_effort_budget_250b.py::test_exceeding_fix_loops_is_recorded_and_logged`
- **AC-3:** Given dieselbe Lage über `workflow.py phase` / When die Ausgabe gelesen wird / Then enthält sie
  `RÜCKFRAGE AN DEN PO:` mit Stufe, Metrik, Stand und Grenze
  - Test: `tests/test_effort_budget_250b.py::test_phase_command_prints_question_to_po`
- **AC-4:** Given ein Workflow innerhalb seines Budgets / When ein Phasenwechsel läuft / Then gibt es
  keinen Eintrag und keine Rückfrage (milder Fall)
  - Test: `tests/test_effort_budget_250b.py::test_within_budget_stays_silent`
- **AC-5:** Given ein überschrittenes Budget / When der Wechsel nach `phase6b_adversary` oder
  `phase7_validate` gewünscht wird / Then gelingt er; kein Budget verweigert einen Phasenwechsel
  - Test: `tests/test_effort_budget_250b.py::test_budget_never_blocks_a_transition`
- **AC-6:** Given ein `feature`-Workflow, der `phase6_implement` ein drittes Mal betritt (Grenze 2) /
  When `record_transition` läuft / Then meldet er `phase_reentries`; wiederholt sich derselbe Stand bei
  späteren Wechseln, wird er nicht erneut gemeldet
  - Test: `tests/test_effort_budget_250b.py::test_reentries_counted_and_not_repeated`
- **AC-7:** Given `effort_budget.enabled: false` / When Wechsel und `post_implementation_gate` laufen /
  Then gibt es weder Eintrag noch Rückfrage, und das Fenster beträgt für alle Stufen 15 min
  - Test: `tests/test_effort_budget_250b.py::test_kill_switch_restores_old_behaviour`
- **AC-8:** Given ein Lock der Implementierungsphase, 20 Minuten alt / When ein Edit kommt / Then wird er
  für `feature-fast` erlaubt (Fenster 30 min) und für `feature` blockiert (Fenster 15 min)
  - Test: `tests/test_effort_budget_250b.py::test_batch_window_depends_on_stage`
- **AC-9:** Given ein Workflow mit committeter Änderung (`base_commit` gesetzt, danach Commit) / When
  `write-log` und `complete` laufen / Then steht `loc_delta_final` mit den tatsächlich hinzugefügten
  Produktivzeilen (nicht `+0`) im archivierten State, `write-log` nennt `effort_budget_exceeded`, und
  eine fehlschlagende Messung blockiert den Abschluss nicht
  - Test: `tests/test_effort_budget_250b.py::test_final_loc_survives_commit_and_never_blocks_complete`

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich: Nach der
> Freigabe ist diese Datei eingefroren (#230). Stimmt ein Testname später nicht mehr, gehört die
> Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`), nicht in diese Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):
- `pytest tests/test_effort_budget_250b.py` (AC-1 bis AC-9)
- Regression: `pytest tests/test_post_implementation_gate*.py tests/test_gate_event_log_181.py
  tests/test_gate_event_excerpt_328.py` sowie die gesamte Suite

Nicht automatisch prüfbar: ob Claude die Rückfrage befolgt und ob die Startwerte passen. Das belegt
die Workflow-Auswertung (`workflow_stats.py`, Repo `gate-audit-data`) nach einigen Wochen:
Dauer je Typ, Fix-Loops und `loc_delta_final` je Workflow.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-1 (dieses Dokument)
- **Rationale:** Das Budget misst **Aktivitätszähler** (Fix-Loops, Wiedereintritte) statt Wanduhrzeit,
  und es **fragt** statt zu sperren. Wanduhrzeit enthält zu 82 % Wartezeit auf den PO und bestraft
  genau die Unterbrechung, die der PO gewollt hat; eine Sperre würde die Gegenprüfung abschneiden, die
  bei #237 die Sicherheitslücke bestätigt hat. Gewählt ist die kleinste Mechanik, die die Abnahme-
  Bedingung „PO wird gefragt statt still weitergearbeitet" erfüllt, und sie hängt an der einzigen
  Stelle, die Phasenwechsel aufzeichnet (`record_transition`).

## Changelog

- 2026-10-03: Initial spec created
