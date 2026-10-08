---
entity_id: feat-345-qa-gate-selbst-ausfuehren
type: module
created: 2026-10-08
updated: 2026-10-08
status: draft
version: "2.0"
tags: [qa_gate, testlauf, exit-code, stempel, adr, "#345", "#313", "#327"]
workflow: feat-345-qa-gate-selbst-ausfuehren
---

# qa_gate führt Tests selbst aus (`--run`) — Scheibe 1 (#345)

## Approval

- [ ] Approved

## Purpose

Heute bekommt `qa_gate.py` eine Textdatei und rät per Regex je Runner, ob die Tests grün waren. Das
liefert „Could not determine test result“ bei jedem neuen Format und lässt sich fälschen (angehängte
Summary-Zeile, fix-2375 in #327). Mit `qa_gate.py --run` startet das Gate den **in der
Projekt-Konfiguration hinterlegten** Testbefehl (`config.yaml` → `qa_gate.test_command`) selbst, wertet
den **echten Exit-Code** und legt Ausgabe und einen Stempel ab, den nur das Gate setzen kann. Die
Kommandozeile nimmt im `--run`-Modus **keinen Befehl** an. Der bisherige Datei-Modus bleibt unverändert
funktionsfähig (additiv, kein Breaking Change).

Diese Spec umfasst **nur Scheibe 1** (Mechanik). Das Ausrollen (Befehle, Agenten, Durchsetzung) ist ein
gebündeltes Folge-Issue, siehe Known Limitations.

## Source

- **File:** `core/hooks/qa_gate.py`, `core/hooks/workflow.py`, `config.yaml`
- **Identifier:** `qa_gate.validate_test_output`, `qa_gate.main`, `config_loader.load_config`,
  `workflow._SET_FIELD_PROTECTED`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `config_loader.load_config` | Modul | liefert `qa_gate.test_command` und `qa_gate.run_timeout` (wie `adversary_dialog` und `bash_gate` ihre Abschnitte lesen) |
| `hook_utils` (`setup_path`, `strip_ansi`) | Modul | Bootstrap und ANSI-Bereinigung, unverändert |
| `workflow.py set-field` / `_SET_FIELD_PROTECTED` | CLI / Sperrliste | Verdict setzen; der neue Stempel-Key kommt auf die Sperrliste |
| `workflow.py status` | CLI | Workflow-Name für den festen Artefaktpfad |
| `qa_gate.validate_test_output` | Funktion | bestehende Kaskade (unittest/node, xcodebuild, Swift Testing, pytest, go, cargo, generisch); bleibt die Textauswertung bei Exit 0 |
| `adversary_dialog` (`validate_dialog_artifact_ex`, `dialog_verdict`) | Modul | `--checklist` unverändert, in beiden Modi nutzbar |
| `bash_gate.WHITELIST_COMMANDS` | Konstante | `qa_gate.py` steht dort; bleibt **unverändert** (siehe Implementation Details 7) |

## Scope

### Affected Files
| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/qa_gate.py` | MODIFY | `--run` ohne Befehlsargument, Optionsprüfung, Config-Lesen, `run_and_capture`, Urteilsregel Exit x Text, Stempel; `main` in Hilfsfunktionen (je ≤ 50 LoC) |
| `core/hooks/workflow.py` | MODIFY | Stempel-Key `qa_run_stamp` auf `_SET_FIELD_PROTECTED` |
| `config.yaml` | MODIFY | neuer Abschnitt `qa_gate:` mit `test_command` (leer, dokumentiert) und `run_timeout` |
| `tests/test_qa_gate_run_345.py` | MODIFY | auf das neue Design umstellen (Befehle aus Sandbox-`config.yaml`), Tests zu AC-1 bis AC-13 |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |

`core/hooks/bash_gate.py` wird **nicht** geändert (Stand von main).

### Estimated Changes
- Files: 4 Code/Test/Config + CHANGELOG
- LoC: +240/-20 netto gegenüber main (Code, Config und Tests; Version 1 hatte zusätzlich Änderungen
  an `bash_gate.py`, die entfallen). Tests nehmen davon rund 150, Code rund 90.

## Implementation Details

1. **Aufruf:** `qa_gate.py --run [--timeout <Sekunden>] [--checklist <Pfad>] [--screenshot <Pfad>]
   [--infra] [--no-visual <Text>]`. Der Testbefehl kommt **nie** von der Kommandozeile. Erlaubt sind
   ausschließlich die genannten Optionen mit ihren Werten. `--infra` ist ein Schalter ohne Wert und
   bleibt zugelassen, weil `/50-implement` Step 8d ihn für Infra-Tickets vorschreibt; er ist auch im
   Datei-Modus für das Urteil wirkungslos (`validate_test_output` nutzt ihn nicht). Jedes weitere
   Argument (Befehlstext, `--out`, unbekannte Option, nicht positive oder nicht ganzzahlige
   `--timeout`-Angabe) ist Fehlbedienung:
   Meldung, Exit 1, **bevor** irgendetwas ausgeführt oder geschrieben wird. `--run` und eine Dateiangabe
   als erstes Argument schließen sich aus. Ohne `--run` läuft der Datei-Modus exakt wie bisher.
2. **Befehl aus der Konfiguration:** `qa_gate.test_command` wird über `config_loader.load_config()`
   gelesen. Fehlt der Wert oder ist er leer, ist das Fehlbedienung (Exit 1, die Meldung nennt den
   Schlüssel `qa_gate.test_command` in `config.yaml`); nichts wird ausgeführt, kein Stempel, kein Verdict.
3. **Ausführung (`run_and_capture`):** `subprocess.Popen(["bash", "-o", "pipefail", "-c", cmd],
   stdout=PIPE, stderr=STDOUT, start_new_session=True)`. Die zusammengeführte Ausgabe wird Zeile für Zeile
   in die Artefaktdatei geschrieben und auf stdout gespiegelt. Der Pfad ist fest
   `docs/artifacts/<workflow>/test-run-output.txt`, relativ zur Wurzel des Arbeitsbaums (Worktree-Wurzel,
   sonst Projektwurzel); fehlende Verzeichnisse werden angelegt. Es gibt keine `--out`-Option, damit das
   Gate keinen frei wählbaren Pfad beschreibt (Version 1 ließ so den Workflow-State überschreiben).
   Timeout: Default 540 s (unter dem 600-s-Limit des Bash-Tools), überschreibbar durch
   `qa_gate.run_timeout` in `config.yaml` und durch `--timeout <s>` (positive Ganzzahl; die
   Kommandozeile gewinnt). Bei Timeout wird die gesamte Prozessgruppe beendet (`os.killpg`, erst SIGTERM,
   dann SIGKILL), der Lauf zählt als Exit != 0.
4. **Urteilsregel (rot gewinnt), unverändert gegenüber Version 1:**
   - Exit != 0 → BROKEN, ohne Textauswertung (gilt auch für pytest 5 „nichts gesammelt“, xcodebuild 65,
     Timeout). Die Meldung nennt Exit-Code bzw. „Timeout nach N s“.
   - Exit 0 → bestehende Kaskade `validate_test_output` auf der Artefaktdatei: Rot im Text → BROKEN;
     grün mit mindestens einem bestandenen Test → VERIFIED.
   - Exit 0 mit 0 Tests, nur skipped oder `[no test files]` → nicht grün (Regel aus #275 bleibt).
   - Exit 0 und Format unbekannt → AMBIGUOUS mit Text „Exit 0, Ausgabe nicht auswertbar“.
   - Im `--run`-Modus entfallen Größenvorfilter (< 100 Byte), „looks fabricated“-Filter und Altersgrenze,
     weil die Herkunft gemessen ist (`validate_test_output(..., trusted=False)` als Default, damit der
     Datei-Modus unverändert bleibt).
5. **Verdict:** wie bisher per `workflow.py set-field adversary_verdict` (VERIFIED:…, BROKEN:…,
   AMBIGUOUS:…). `--checklist` läuft nach der Testauswertung unverändert.
6. **Stempel `qa_run_stamp`:** Nach jedem Lauf (auch bei Exit != 0) schreibt das Gate in den
   Workflow-State: `exit_code`, `output_sha256`, `output_path`, `timestamp` (UTC, ISO 8601),
   `command_sha256` (SHA-256 des konfigurierten Befehls, nie der Klartext, weil Befehle Inline-Credentials
   enthalten können), `source: "run"`. Im Datei-Modus wird `source: "file"` mit `output_sha256` der
   geprüften Datei vermerkt. `qa_run_stamp` steht auf `workflow._SET_FIELD_PROTECTED`; `set-field
   qa_run_stamp …` endet mit BLOCKED und Exit 1. Das Gate schreibt über einen Schreibpfad in
   `workflow.py`, der die Sperrliste nicht durchläuft (analog Dialog-Stempel aus #253).
7. **bash_gate unverändert:** Weil `--run` keinen Befehlstext mehr trägt, gibt es auf der Kommandozeile
   keine verschachtelte Shell, die die Whitelist-Freistellung von `qa_gate.py` umgehen könnte. Die
   Textprüfung in `bash_gate.py` wird nicht angefasst; die Absicherung liegt im Prüftor selbst
   (Optionsprüfung, Punkt 1).
8. **`config.yaml`:** neuer Abschnitt `qa_gate:` mit `test_command: ""` (dokumentiert, projektspezifisch zu
   setzen) und `run_timeout: 540`.

## Expected Behavior

- **Input:** `qa_gate.py --run` im aktiven Workflow, `qa_gate.test_command: "python3 -m pytest tests/ -q"`
  in `config.yaml`.
- **Output:** Testausgabe live auf stdout, Artefaktdatei am festen Pfad, Stempel im State, Verdict gesetzt
  (VERIFIED/BROKEN/AMBIGUOUS), Exit-Code 0 bei VERIFIED/AMBIGUOUS, 1 bei BROKEN oder Fehlbedienung.
- **Fehlbedienung:** Befehlstext als Argument, `--out` oder fehlender `qa_gate.test_command` →
  Exit 1, nichts ausgeführt, State unverändert.
- **Side effects:** Datei unter `docs/artifacts/<workflow>/`, ein neuer Key im Workflow-State. Der
  Datei-Modus ändert sein Verhalten nicht (außer dem zusätzlich vermerkten `source: "file"`).

## Known Limitations

- **Restgrenze Config:** Wer `config.yaml` per Edit ändert, bestimmt den ausgeführten Befehl. Das ist ein
  sichtbarer Datei-Edit im Diff und gehört zur selben Klasse wie jedes andere vom Agenten geschriebene
  Skript, das ein Gate ausführt; es wird hier nicht technisch verhindert.
- Der Stempel lässt sich per Python-Import von `workflow.py` fälschen, ebenso bleiben Secrets- und
  Lese-Thread-Punkte offen; beides ist in #404 erfasst.
- **Nicht in Scheibe 1:** `qa_gate.require_run`-Durchsetzung an Commit-Gate und Phase-8-Übergang,
  Deprecation-Hinweis im Datei-Modus, Dokumentation und Befehle (`/50-implement` Step 4 und 8d,
  `/60-validate`, `/80-workflow`, `implementation-validator`, `developer-agent`; sie referenzieren heute
  `test_command` aus `openspec.yaml`/`pre_commit`, ohne dass es dort definiert wäre), `CLAUDE.md`,
  README, Skills-Sync. Diese Scheiben 2 und 3 werden als gebündeltes Folge-Issue „qa_gate --run
  ausrollen“ angelegt.
- Solange `require_run` nicht gilt, bleibt die Fälschbarkeit des Datei-Modus bestehen; Scheibe 1 schafft
  nur den prüfbaren Weg (Stempel + Sperre), keine Pflicht dazu.
- Der Stempel belegt, dass das Gate den konfigurierten Befehl ausgeführt hat und was herauskam, nicht,
  dass der Befehl die richtigen Tests umfasst (ein Befehl wie `true` ergibt Exit 0 und wird mangels
  Testausgabe AMBIGUOUS, nicht VERIFIED).
- Lange Suiten (xcodebuild) können das Timeout überschreiten; dann BROKEN mit Timeout-Meldung. Umgebung
  (venv, Simulator) erbt das Gate vom aufrufenden Prozess.
- `post_bash.py` bleibt textbasiert und sieht rote Läufe nie (PostToolUse feuert nur bei Exit 0);
  eigenes Issue #403.

## Definition of Done

- [ ] Jede Acceptance Criterion ist durch einen automatischen Test belegt
- [ ] `--run` urteilt nach der Regel „rot gewinnt“ (Exit != 0 → BROKEN, Exit 0 → Kaskade, unbekannt → AMBIGUOUS)
- [ ] `--run` nimmt keinen Befehl und kein `--out` an; fehlender `qa_gate.test_command` wird mit Hinweis auf den Schlüssel abgewiesen
- [ ] Artefaktdatei am festen Pfad und Stempel (ohne Befehls-Klartext) liegen nach jedem Lauf vor; der Stempel ist per `set-field` nicht setzbar
- [ ] `core/hooks/bash_gate.py` ist gegenüber main unverändert; Datei-Modus und `--run` laufen durch bash_gate
- [ ] Alle bestehenden qa_gate-Tests (Datei-Modus) sind unverändert grün; Gesamtsuite grün
- [ ] Funktionen höchstens 50 LoC; CHANGELOG unter [Unreleased] ergänzt; `config.yaml` dokumentiert `qa_gate.test_command` und `qa_gate.run_timeout`
- [ ] Folge-Issue „qa_gate --run ausrollen“ (Scheiben 2 und 3) ist angelegt

## Acceptance Criteria

Alle `--run`-Tests schreiben den Testbefehl in die `config.yaml` der Sandbox (`qa_gate.test_command`).

- **AC-1:** Given ein konfigurierter Befehl, der mit Exit 1 endet und dabei „5 passed“ ausgibt / When `qa_gate.py --run`
  läuft / Then lautet das Verdict BROKEN (Exit-Code des Gates 1), unabhängig vom Text
  - Test: `tests/test_qa_gate_run_345.py::test_nonzero_exit_is_broken_regardless_of_text`
- **AC-2:** Given ein konfigurierter Befehl, der „3 passed in 0.1s“ mit Exit 0 liefert / When `--run` läuft / Then lautet das Verdict VERIFIED
  - Test: `tests/test_qa_gate_run_345.py::test_exit_zero_green_output_is_verified`
- **AC-3:** Given Exit 0 und Ausgabe „0 passed, 4 skipped“ / When `--run` läuft / Then ist das Ergebnis
  nicht VERIFIED (Regel #275 bleibt)
  - Test: `tests/test_qa_gate_run_345.py::test_exit_zero_only_skipped_is_not_verified`
- **AC-4:** Given Exit 0 und eine Ausgabe in unbekanntem Format / When `--run` läuft / Then lautet das
  Verdict AMBIGUOUS mit „Exit 0, Ausgabe nicht auswertbar“ und der Größenvorfilter greift nicht
  - Test: `tests/test_qa_gate_run_345.py::test_exit_zero_unknown_format_is_ambiguous`
- **AC-5:** Given der konfigurierte Befehl `false | true` / When `--run` läuft / Then lautet das Verdict BROKEN, weil
  die Ausführung mit `pipefail` erfolgt
  - Test: `tests/test_qa_gate_run_345.py::test_pipefail_makes_failing_pipe_broken`
- **AC-6:** Given ein konfigurierter Befehl, der länger läuft als `--timeout 1` und einen Kindprozess startet / When
  `--run` läuft / Then lautet das Verdict BROKEN mit Timeout-Meldung und die Prozessgruppe ist beendet
  (kein Prozess des Laufs lebt danach noch)
  - Test: `tests/test_qa_gate_run_345.py::test_timeout_is_broken_and_process_group_killed`
- **AC-7:** Given ein erfolgreicher Lauf / When er endet / Then existiert die Artefaktdatei am festen Pfad
  `docs/artifacts/<workflow>/test-run-output.txt` mit der vollen Ausgabe (stdout und stderr zusammen) und
  der Stempel `qa_run_stamp` hat `source: "run"`, den Exit-Code und einen `output_sha256`, der zur Datei passt
  - Test: `tests/test_qa_gate_run_345.py::test_artifact_written_and_stamp_sha_matches`
- **AC-8:** Given ein konfigurierter Befehl mit dem Text `secret-token-123` / When der Lauf endet / Then enthält der
  Stempel nur den SHA-256 des Befehls und nirgends im State steht der Befehlstext
  - Test: `tests/test_qa_gate_run_345.py::test_stamp_stores_command_hash_never_plaintext`
- **AC-9:** Given ein Workflow-State / When `workflow.py set-field qa_run_stamp <Wert>` läuft / Then
  endet der Aufruf mit BLOCKED und Exit 1 und der Stempel bleibt unverändert
  - Test: `tests/test_qa_gate_run_345.py::test_set_field_on_stamp_key_is_blocked`
- **AC-10:** Given `qa_gate.py --run "echo x > .claude/workflows/a.json"` (Befehlstext als Argument) und
  `qa_gate.py --run --out .claude/workflows/a.json` / When das Prüftor sie aufruft / Then weist es beide
  selbst mit Exit 1 ab (ebenso jedes andere unbekannte Argument), nichts wird ausgeführt, und die
  State-Datei bleibt byte-identisch; `--infra` (mit `--checklist` und `--no-visual`) wird dagegen
  angenommen
  - Test: `tests/test_qa_gate_run_345.py::test_run_rejects_command_argument_and_out_option`
- **AC-11:** Given eine Sandbox ohne `qa_gate.test_command` (fehlt oder leer) / When `qa_gate.py --run`
  läuft / Then endet es mit Exit 1, die Meldung nennt den Schlüssel `qa_gate.test_command`, nichts wird
  ausgeführt und es entsteht weder Artefakt noch Stempel
  - Test: `tests/test_qa_gate_run_345.py::test_missing_test_command_is_usage_error`
- **AC-12:** Given eine Testausgabedatei im bisherigen Format / When `qa_gate.py <datei>` ohne `--run`
  läuft / Then sind Verdict, Meldungen und Altersgrenze unverändert, und der Stempel vermerkt
  `source: "file"`; die bestehenden Testdateien `test_qa_gate*.py`, `test_testausgabe_erkennung_275.py`,
  `test_gate_parser_fixes_73_76_79.py` und `test_verdict_pipeline_77.py` bleiben grün
  - Test: `tests/test_qa_gate_run_345.py::test_file_mode_unchanged_and_marks_source_file`
- **AC-13:** Given `core/hooks/bash_gate.py` / When es mit main verglichen wird und `qa_gate.py <datei>` sowie
  `qa_gate.py --run` durch `bash_gate` geprüft werden / Then ist die Datei gegenüber main unverändert und
  beide Aufrufe enden mit Exit 0 (Ende-zu-Ende-Verhalten, kein Eingriff in die Whitelist)
  - Test: `tests/test_qa_gate_run_345.py::test_bash_gate_unchanged_and_qa_gate_calls_pass`

> Die Test-Zuordnung wird bei der Spec-Erstellung eingetragen, nicht nachträglich: Nach der Freigabe ist
> diese Datei eingefroren (#230). Stimmt ein Testname später nicht mehr, gehört die Korrektur in die
> TDD-RED-Artefakte (`workflow.py add-artifact`), nicht in diese Datei.

## Test Plan

Automatische Tests (TDD RED, jeweils an eine AC gebunden; Befehle stehen in der Sandbox-`config.yaml`):
- GIVEN ein Befehl mit Exit 1 WHEN `--run` THEN BROKEN (AC-1)
- GIVEN Exit 0 mit grüner Ausgabe WHEN `--run` THEN VERIFIED (AC-2)
- GIVEN Exit 0 mit nur skipped WHEN `--run` THEN nicht VERIFIED (AC-3)
- GIVEN Exit 0 mit unbekanntem Format WHEN `--run` THEN AMBIGUOUS (AC-4)
- GIVEN `false | true` WHEN `--run` THEN BROKEN durch pipefail (AC-5)
- GIVEN Überschreitung des Timeouts WHEN `--run` THEN BROKEN und Prozessgruppe beendet (AC-6)
- GIVEN ein Lauf WHEN er endet THEN Artefakt am festen Pfad und Stempel mit passendem SHA (AC-7), ohne
  Befehls-Klartext (AC-8)
- GIVEN `set-field` auf den Stempel-Key WHEN ausgeführt THEN blockiert (AC-9)
- GIVEN Befehlstext, `--out` oder ein unbekanntes Argument WHEN `--run` THEN Exit 1, State unverändert;
  GIVEN `--infra` WHEN `--run` THEN angenommen (AC-10)
- GIVEN kein `qa_gate.test_command` WHEN `--run` THEN Exit 1 mit Schlüsselhinweis (AC-11)
- GIVEN der Datei-Modus WHEN aufgerufen THEN unverändert (AC-12)
- GIVEN bash_gate WHEN `qa_gate.py <datei>` und `qa_gate.py --run` geprüft werden THEN Exit 0, Datei
  gegenüber main unverändert (AC-13)

Die Tests der Version 1 zu `bash_gate` (`test_bash_gate_does_not_whitelist_qa_gate_run` und die
Varianten-Tests) entfallen, weil die Textprüfung nicht mehr Teil des Designs ist. Die Tests laufen mit
echten Subprozessen (`bash`, `sleep`) gegen ein temporäres Projekt mit eigenem Workflow-State und eigener
`config.yaml`; es wird kein Netz und keine Zeitabhängigkeit über 3 s hinaus benötigt.

Regression: `pytest tests/test_qa_gate*.py tests/test_testausgabe_erkennung_275.py
tests/test_gate_parser_fixes_73_76_79.py tests/test_verdict_pipeline_77.py` und die gesamte Suite.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** ADR-0345 — `qa_gate.py` führt den konfigurierten Testbefehl selbst aus (`--run`, Befehl
  aus `config.yaml`), additiv zum Datei-Modus.
- **Rationale:** Der Exit-Code eines selbst gestarteten Prozesses ist gemessen, die Textdatei ist
  behauptet. Rot gewinnt, aber Exit 0 allein ist kein Grün (pytest/unittest/go/cargo melden Exit 0 bei
  null oder übersprungenen Tests), daher bleibt die Textkaskade für den Grün-Beweis und „unbekannt“ wird
  AMBIGUOUS statt VERIFIED. Der Stempel ist gesperrt und trägt SHA-256 der Ausgabe; der Befehl wird nur
  gehasht, weil er Credentials enthalten kann. Diese ADR **kippt die „Verworfene Alternative B“** aus
  `docs/specs/fix-313-327-qa-gate-testausgabe.md` („Gate führt den Test selbst aus“): Das Prinzip „Datei
  rein, Urteil raus“ bleibt (es entsteht weiterhin eine registrierte Artefaktdatei), nur ihre Herkunft
  ist gemessen; das Scoping-Limit wird durch den Schnitt in Scheiben eingehalten.
- **Version 1 verworfen (Befehl auf der Kommandozeile):** `--run "<Befehl>"` machte das gewhitelistete
  Prüftor selbst zur Shell. Die Textprüfung in `bash_gate` war in drei Adversary-Runden, alle BROKEN, nicht
  dicht zu bekommen: Runde A `$'--run'` (Shell-Quoting verdeckt das Token), Runde B `--ru''n` und
  `{--run,"…"}` (weitere Expansionsformen), Runde C Skriptpfad mit Leerzeichen und `--out
  .claude/workflows/<wf>.json` (ungeprüfter Ausgabepfad überschreibt den Workflow-State) sowie ein
  Fehlalarm, weil der Skriptpfad `.claude/hooks/qa_gate.py` selbst auf `PROTECTED_FILE_PATTERNS` passt.
  Jede Runde schloss eine Variante, die nächste fand die folgende: ein Wettlauf, den eine Textprüfung
  gegen die Shell-Grammatik nicht gewinnt.
- **Gewählt: (b) Befehl aus der Config.** Ohne Befehlstext in der Kommandozeile gibt es keine
  verschachtelte Shell; die Whitelist-Freistellung von `qa_gate.py` ist wieder unbedenklich und
  `bash_gate.py` bleibt unverändert. Das Prüftor lehnt alles außer den bekannten Optionen selbst ab; ein
  fester Ausgabepfad schließt den Pfad-Angriff. Restgrenze: Der Befehl steht in `config.yaml`, ein Edit
  dort ist ein sichtbarer Diff.
- **Alternativen:**
  - *(a) `bash_gate` weiter flicken:* verworfen, siehe drei Runden oben; jede Ergänzung vergrößert die
    Textprüfung, ohne die Fehlerklasse zu beseitigen.
  - *(c) Datei-Modus-only / Status quo:* kein Aufwand, aber die Fälschbarkeit (angehängte Summary-Zeile,
    #327) und „Could not determine“ bleiben; bleibt Rückfallposition, falls auch dieses Design scheitert.
  - *B — Datei-Modus sofort ersetzen:* konsequent, bricht aber 45 Testaufrufe in 13 Dateien, `/50`, `/60`,
    `/80`, die Agenten und alle Konsumenten-Projekte. Bleibt Endzustand nach einer Deprecation (Folge-Issue).
  - *C — Exit-Code per Hook erfassen:* widerlegt. PostToolUse (Bash) feuert nur bei Exit 0;
    Fehlschläge kommen als PostToolUseFailure mit Fehlertext statt numerischem Feld, die Datei bliebe
    handschreibbar.
  - *Reines „Exit 0 = grün“:* verworfen, weil Läufe ohne Tests Exit 0 liefern (neuer False-Pass).

## Changelog

- 2026-10-08: Initial spec created (Scheibe 1 von #345)
- 2026-10-08: Version 2.0 — Umbau nach drei BROKEN-Adversary-Runden: `--run` nimmt keinen Befehl mehr
  an, der Testbefehl kommt aus `config.yaml` (`qa_gate.test_command`), `--out` entfällt (fester
  Artefaktpfad), `bash_gate.py` bleibt unverändert; AC-10 bis AC-13 neu gefasst, ADR-0345 fortgeschrieben
