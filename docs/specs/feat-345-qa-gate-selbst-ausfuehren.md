---
entity_id: feat-345-qa-gate-selbst-ausfuehren
type: module
created: 2026-10-08
updated: 2026-10-08
status: draft
version: "1.0"
tags: [qa_gate, testlauf, exit-code, stempel, adr, "#345", "#313", "#327"]
workflow: feat-345-qa-gate-selbst-ausfuehren
---

# qa_gate führt Tests selbst aus (`--run`) — Scheibe 1 (#345)

## Approval

- [ ] Approved

## Purpose

Heute bekommt `qa_gate.py` eine Textdatei und rät per Regex je Runner, ob die Tests grün waren. Das
liefert „Could not determine test result“ bei jedem neuen Format und lässt sich fälschen (angehängte
Summary-Zeile, fix-2375 in #327). Mit `qa_gate.py --run "<Befehl>"` startet das Gate den Testbefehl
selbst, wertet den **echten Exit-Code** und legt Ausgabe und einen Stempel ab, den nur das Gate setzen
kann. Der bisherige Datei-Modus bleibt unverändert funktionsfähig (additiv, kein Breaking Change).

Diese Spec umfasst **nur Scheibe 1** (Mechanik). Das Ausrollen (Befehle, Agenten, Config-Feld,
Durchsetzung) ist ein gebündeltes Folge-Issue, siehe Known Limitations.

## Source

- **File:** `core/hooks/qa_gate.py`, `core/hooks/workflow.py`, `core/hooks/bash_gate.py`
- **Identifier:** `qa_gate.validate_test_output`, `qa_gate.main`, `workflow._SET_FIELD_PROTECTED`,
  `bash_gate.WHITELIST_COMMANDS`, `bash_gate._whitelist_matches`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils` (`setup_path`, `strip_ansi`) | Modul | Bootstrap und ANSI-Bereinigung, unverändert |
| `workflow.py set-field` / `_SET_FIELD_PROTECTED` | CLI / Sperrliste | Verdict setzen; der neue Stempel-Key kommt auf die Sperrliste |
| `workflow.py status` | CLI | Workflow-Name für den Default-Pfad der Artefaktdatei |
| `qa_gate.validate_test_output` | Funktion | bestehende Kaskade (unittest/node, xcodebuild, Swift Testing, pytest, go, cargo, generisch); bleibt die Textauswertung bei Exit 0 |
| `adversary_dialog` (`validate_dialog_artifact_ex`, `dialog_verdict`) | Modul | `--checklist` unverändert, in beiden Modi nutzbar |
| `bash_gate.WHITELIST_COMMANDS` | Konstante | `qa_gate.py` steht dort; `--run` darf davon nicht profitieren |

## Scope

### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/qa_gate.py` | MODIFY | `--run`/`--out`/`--timeout`, `run_and_capture`, Urteilsregel Exit x Text, Stempel; `main` in Hilfsfunktionen (je ≤ 50 LoC) |
| `core/hooks/workflow.py` | MODIFY | Stempel-Key `qa_run_stamp` auf `_SET_FIELD_PROTECTED` |
| `core/hooks/bash_gate.py` | MODIFY | `qa_gate.py` mit `--run` wird nicht über die Whitelist an Prüfung 3b vorbeigelassen |
| `tests/test_qa_gate_run_345.py` | CREATE | Tests zu AC-1 bis AC-11 |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |

### Estimated Changes
- Files: 4 Code/Test + CHANGELOG
- LoC: +250/-20 (Code und Tests)

## Implementation Details

1. **Aufruf:** `qa_gate.py --run "<Befehl>" [--out <Pfad>] [--timeout <Sekunden>] [--checklist ...]
   [--screenshot ...] [--no-visual ...]`. `--run` und eine Dateiangabe als erstes Argument schließen
   sich aus (Fehlermeldung, Exit 1). Ohne `--run` läuft der Datei-Modus exakt wie bisher.
2. **Ausführung (`run_and_capture`):** `subprocess.Popen(["bash", "-o", "pipefail", "-c", cmd],
   stdout=PIPE, stderr=STDOUT, start_new_session=True)`. Die zusammengeführte Ausgabe wird Zeile für Zeile
   in die Artefaktdatei geschrieben und auf stdout gespiegelt. Default-Pfad
   `docs/artifacts/<workflow>/test-run-output.txt`, per `--out` änderbar; fehlende Verzeichnisse werden
   angelegt. Timeout Default 540 s (unter dem 600-s-Limit des Bash-Tools), per `--timeout` änderbar.
   Bei Timeout wird die gesamte Prozessgruppe beendet (`os.killpg`, erst SIGTERM, dann SIGKILL), der
   Lauf zählt als Exit != 0.
3. **Urteilsregel (rot gewinnt):**
   - Exit != 0 → BROKEN, ohne Textauswertung (gilt auch für pytest 5 „nichts gesammelt“, xcodebuild 65,
     Timeout). Die Meldung nennt Exit-Code bzw. „Timeout nach N s“.
   - Exit 0 → bestehende Kaskade `validate_test_output` auf der Artefaktdatei: Rot im Text → BROKEN;
     grün mit mindestens einem bestandenen Test → VERIFIED.
   - Exit 0 mit 0 Tests, nur skipped oder `[no test files]` → nicht grün (Regel aus #275 bleibt).
   - Exit 0 und Format unbekannt (Kaskade meldet „Could not determine“) → AMBIGUOUS mit Text „Exit 0,
     Ausgabe nicht auswertbar“. Exit 0 allein gilt bewusst nicht als grün (neuer False-Pass).
   - Im `--run`-Modus entfallen der Größenvorfilter (< 100 Byte) und der „looks fabricated“-Filter,
     weil die Herkunft gemessen ist; die Altersgrenze entfällt ebenfalls (frisch erzeugt). Dafür bekommt
     `validate_test_output` einen Parameter (`trusted=False` als Default), damit der Datei-Modus
     unverändert bleibt.
4. **Verdict:** wird wie bisher per `workflow.py set-field adversary_verdict` gesetzt (VERIFIED:…,
   BROKEN:…, AMBIGUOUS:…). Die Checklisten-Prüfung (`--checklist`) läuft nach der Testauswertung
   unverändert und kann ein VERIFIED zu AMBIGUOUS/BROKEN machen.
5. **Stempel `qa_run_stamp`:** Nach jedem Lauf (auch bei Exit != 0) schreibt das Gate einen Stempel in
   den Workflow-State: `exit_code`, `output_sha256` (SHA-256 der Artefaktdatei), `output_path`,
   `timestamp` (UTC, ISO 8601), `command_sha256` (SHA-256 des Befehls, nie der Klartext, weil Befehle
   Inline-Credentials enthalten können), `source: "run"`. Im Datei-Modus wird `source: "file"` mit
   `output_sha256` der geprüften Datei vermerkt (ohne `exit_code`/`command_sha256`). Geschrieben wird
   über einen eigenen Unterbefehl des Gates, nicht über `set-field`.
6. **Sperre:** `qa_run_stamp` kommt auf `workflow._SET_FIELD_PROTECTED` (Hinweis: „wird von
   qa_gate.py gesetzt“). `set-field qa_run_stamp …` endet mit BLOCKED und Exit 1. Das Gate schreibt den
   Stempel über einen Schreibpfad in `workflow.py`, der die Sperrliste nicht durchläuft (analog zum
   Dialog-Stempel aus #253; kein dritter Mechanismus).
7. **bash_gate:** `qa_gate.py` bleibt für den Datei-Modus auf `WHITELIST_COMMANDS`. Trägt ein Segment
   zusätzlich das Token `--run`, trifft `_whitelist_matches` den Eintrag `qa_gate.py` nicht mehr; das
   Segment wird wie ein gewöhnlicher Befehl behandelt und läuft durch Prüfung 3b (State-Integrity). Ein
   innerer Schreibbefehl auf State-Dateien kann so nicht über die Whitelist durchrutschen.

## Expected Behavior

- **Input:** `qa_gate.py --run "python3 -m pytest tests/ -q"` im aktiven Workflow.
- **Output:** Testausgabe live auf stdout, Artefaktdatei geschrieben, Stempel im State, Verdict gesetzt
  (VERIFIED/BROKEN/AMBIGUOUS), Exit-Code 0 bei VERIFIED/AMBIGUOUS, 1 bei BROKEN oder Fehlbedienung.
- **Side effects:** Datei unter `docs/artifacts/<workflow>/`, ein neuer Key im Workflow-State. Der
  Datei-Modus ändert sein Verhalten nicht (außer dem zusätzlich vermerkten `source: "file"`).

## Known Limitations

- **Nicht in Scheibe 1:** `qa_gate.require_run`-Durchsetzung an Commit-Gate und Phase-8-Übergang,
  Deprecation-Hinweis im Datei-Modus, Dokumentation und Befehle (`/50-implement` Step 4 und 8d,
  `/60-validate`, `/80-workflow`, `implementation-validator`, `developer-agent`), das heute nur
  referenzierte, nie definierte Config-Feld `test_command`, `CLAUDE.md`, README, Skills-Sync. Diese
  Scheiben 2 und 3 werden als gebündeltes Folge-Issue „qa_gate --run ausrollen“ angelegt.
- Solange `require_run` nicht gilt, bleibt die Fälschbarkeit des Datei-Modus bestehen; Scheibe 1 schafft
  nur den prüfbaren Weg (Stempel + Sperre), keine Pflicht dazu.
- Der Stempel belegt, dass das Gate den Befehl ausgeführt hat und was herauskam, nicht, dass der Befehl
  die richtigen Tests umfasst (ein Befehl wie `true` ergibt Exit 0 und wird mangels Testausgabe
  AMBIGUOUS, nicht VERIFIED).
- Lange Suiten (xcodebuild) können das Timeout von 540 s überschreiten; dann BROKEN mit Timeout-Meldung.
  Umgebung (venv, Simulator) erbt das Gate vom aufrufenden Prozess.
- `post_bash.py` bleibt textbasiert und sieht rote Läufe nie (PostToolUse feuert nur bei Exit 0);
  eigenes Issue #403.

## Definition of Done

- [ ] Jede Acceptance Criterion ist durch einen automatischen Test belegt
- [ ] `--run` urteilt nach der Regel „rot gewinnt“ (Exit != 0 → BROKEN, Exit 0 → Kaskade, unbekannt → AMBIGUOUS)
- [ ] Artefaktdatei und Stempel (ohne Befehls-Klartext) liegen nach jedem Lauf vor; der Stempel ist per `set-field` nicht setzbar
- [ ] `qa_gate.py --run` läuft nicht an Prüfung 3b vorbei
- [ ] Alle bestehenden qa_gate-Tests (Datei-Modus) sind unverändert grün; Gesamtsuite grün
- [ ] Funktionen höchstens 50 LoC; CHANGELOG unter [Unreleased] ergänzt
- [ ] Folge-Issue „qa_gate --run ausrollen“ (Scheiben 2 und 3) ist angelegt

## Acceptance Criteria

- **AC-1:** Given ein Befehl, der mit Exit 1 endet und dabei „5 passed“ ausgibt / When `qa_gate.py --run`
  läuft / Then lautet das Verdict BROKEN (Exit-Code des Gates 1), unabhängig vom Text
  - Test: `tests/test_qa_gate_run_345.py::test_nonzero_exit_is_broken_regardless_of_text`
- **AC-2:** Given ein Befehl, der pytest-typische Ausgabe „3 passed in 0.1s“ mit Exit 0 liefert / When
  `--run` läuft / Then lautet das Verdict VERIFIED
  - Test: `tests/test_qa_gate_run_345.py::test_exit_zero_green_output_is_verified`
- **AC-3:** Given Exit 0 und Ausgabe „0 passed, 4 skipped“ / When `--run` läuft / Then ist das Ergebnis
  nicht VERIFIED (Regel #275 bleibt)
  - Test: `tests/test_qa_gate_run_345.py::test_exit_zero_only_skipped_is_not_verified`
- **AC-4:** Given Exit 0 und eine Ausgabe in unbekanntem Format / When `--run` läuft / Then lautet das
  Verdict AMBIGUOUS mit „Exit 0, Ausgabe nicht auswertbar“ und der Größenvorfilter greift nicht
  - Test: `tests/test_qa_gate_run_345.py::test_exit_zero_unknown_format_is_ambiguous`
- **AC-5:** Given der Befehl `false | true` / When `--run` läuft / Then lautet das Verdict BROKEN, weil
  die Ausführung mit `pipefail` erfolgt
  - Test: `tests/test_qa_gate_run_345.py::test_pipefail_makes_failing_pipe_broken`
- **AC-6:** Given ein Befehl, der länger läuft als `--timeout 1` und einen Kindprozess startet / When
  `--run` läuft / Then lautet das Verdict BROKEN mit Timeout-Meldung und die Prozessgruppe ist beendet
  (kein Prozess des Laufs lebt danach noch)
  - Test: `tests/test_qa_gate_run_345.py::test_timeout_is_broken_and_process_group_killed`
- **AC-7:** Given ein erfolgreicher Lauf mit `--out <Pfad>` / When er endet / Then existiert die
  Artefaktdatei mit der vollen Ausgabe (stdout und stderr zusammen) und der Stempel `qa_run_stamp` hat
  `source: "run"`, den Exit-Code und einen `output_sha256`, der zur Datei passt
  - Test: `tests/test_qa_gate_run_345.py::test_artifact_written_and_stamp_sha_matches`
- **AC-8:** Given ein Befehl mit dem Text `secret-token-123` / When der Lauf endet / Then enthält der
  Stempel nur den SHA-256 des Befehls und nirgends im State steht der Befehlstext
  - Test: `tests/test_qa_gate_run_345.py::test_stamp_stores_command_hash_never_plaintext`
- **AC-9:** Given ein Workflow-State / When `workflow.py set-field qa_run_stamp <Wert>` läuft / Then
  endet der Aufruf mit BLOCKED und Exit 1 und der Stempel bleibt unverändert
  - Test: `tests/test_qa_gate_run_345.py::test_set_field_on_stamp_key_is_blocked`
- **AC-10:** Given das Kommando `python3 .claude/hooks/qa_gate.py --run "echo x > .claude/workflows/a.json"`
  / When `bash_gate` es prüft / Then wird es durch Prüfung 3b blockiert, während
  `qa_gate.py <datei>` ohne `--run` weiterhin per Whitelist durchkommt
  - Test: `tests/test_qa_gate_run_345.py::test_bash_gate_does_not_whitelist_qa_gate_run`
- **AC-11:** Given eine Testausgabedatei im bisherigen Format / When `qa_gate.py <datei>` ohne `--run`
  läuft / Then sind Verdict, Meldungen und Altersgrenze unverändert, und der Stempel vermerkt
  `source: "file"`; die bestehenden Testdateien `test_qa_gate*.py`, `test_testausgabe_erkennung_275.py`,
  `test_gate_parser_fixes_73_76_79.py` und `test_verdict_pipeline_77.py` bleiben grün
  - Test: `tests/test_qa_gate_run_345.py::test_file_mode_unchanged_and_marks_source_file`

> Die Test-Zuordnung wird bei der Spec-Erstellung eingetragen, nicht nachträglich: Nach der Freigabe ist
> diese Datei eingefroren (#230). Stimmt ein Testname später nicht mehr, gehört die Korrektur in die
> TDD-RED-Artefakte (`workflow.py add-artifact`), nicht in diese Datei.

## Test Plan

Automatische Tests (TDD RED, jeweils an eine AC gebunden):
- GIVEN ein Befehl mit Exit 1 WHEN `--run` THEN BROKEN (AC-1)
- GIVEN Exit 0 mit grüner Ausgabe WHEN `--run` THEN VERIFIED (AC-2)
- GIVEN Exit 0 mit nur skipped WHEN `--run` THEN nicht VERIFIED (AC-3)
- GIVEN Exit 0 mit unbekanntem Format WHEN `--run` THEN AMBIGUOUS (AC-4)
- GIVEN `false | true` WHEN `--run` THEN BROKEN durch pipefail (AC-5)
- GIVEN Überschreitung des Timeouts WHEN `--run` THEN BROKEN und Prozessgruppe beendet (AC-6)
- GIVEN ein Lauf WHEN er endet THEN Artefakt und Stempel mit passendem SHA (AC-7), ohne
  Befehls-Klartext (AC-8)
- GIVEN `set-field` auf den Stempel-Key WHEN ausgeführt THEN blockiert (AC-9)
- GIVEN `qa_gate.py --run` im bash_gate WHEN geprüft THEN nicht über die Whitelist freigestellt (AC-10)
- GIVEN der Datei-Modus WHEN aufgerufen THEN unverändert (AC-11)

Die Tests laufen mit echten Subprozessen (`bash`, `sleep`) gegen ein temporäres Projekt mit eigenem
Workflow-State; es wird kein Netz und keine Zeitabhängigkeit über 3 s hinaus benötigt.

Regression: `pytest tests/test_qa_gate*.py tests/test_testausgabe_erkennung_275.py
tests/test_gate_parser_fixes_73_76_79.py tests/test_verdict_pipeline_77.py` und die gesamte Suite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0345 — `qa_gate.py` führt Testbefehle selbst aus (`--run`), additiv zum Datei-Modus.
- **Rationale:** Der Exit-Code eines selbst gestarteten Prozesses ist gemessen, die Textdatei ist
  behauptet. Rot gewinnt, aber Exit 0 allein ist kein Grün (pytest/unittest/go/cargo melden Exit 0
  bei null oder übersprungenen Tests), daher bleibt die Textkaskade für den Grün-Beweis und
  „unbekannt“ wird AMBIGUOUS statt VERIFIED. Der Stempel ist gesperrt und trägt SHA-256 der Ausgabe;
  der Befehl wird nur gehasht, weil er Credentials enthalten kann. Diese ADR **kippt die „Verworfene
  Alternative B“** aus `docs/specs/fix-313-327-qa-gate-testausgabe.md` („Gate führt den Test selbst
  aus“, damals verworfen wegen des Prinzips „Datei rein, Urteil raus“ und des Scoping-Limits). Der
  Grund für die Umkehr: Das Prinzip bleibt erhalten (es entsteht weiterhin eine Artefaktdatei, die
  registriert und committet wird), nur ihre Herkunft ist jetzt gemessen; das Scoping-Limit wird durch
  den Schnitt in Scheiben eingehalten. Alternativen:
  - *B — Datei-Modus sofort ersetzen:* konsequent für die Fälschbarkeit, bricht aber 45 Testaufrufe in
    13 Dateien, `/50`, `/60`, `/80`, die Agenten und alle Konsumenten-Projekte und sprengt das Limit.
    Bleibt Endzustand nach einer Deprecation (Folge-Issue).
  - *C — kein Selbstausführen, Exit-Code per Hook erfassen:* recherchiert und widerlegt. PostToolUse
    (Bash) feuert nur bei Exit 0; Fehlschläge kommen als PostToolUseFailure mit Fehlertext statt
    numerischem Feld, also wieder Textparsing, und die Datei bliebe handschreibbar.
  - *D — Status quo mit weiteren Regexen je Runner:* endloser Parsing-Wettlauf ohne Wirkung auf die
    Fälschbarkeit.
  - *Reines „Exit 0 = grün“:* verworfen, weil Läufe ohne Tests Exit 0 liefern (neuer False-Pass).

## Changelog

- 2026-10-08: Initial spec created (Scheibe 1 von #345)
