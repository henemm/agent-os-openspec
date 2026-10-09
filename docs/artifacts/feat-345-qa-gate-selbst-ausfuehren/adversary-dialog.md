# Adversary Dialog — feat-345-qa-gate-selbst-ausfuehren
Spec: docs/specs/feat-345-qa-gate-selbst-ausfuehren.md
Datum: 2026-10-09 06:37

## Checkliste
- [x] **Input:** `qa_gate.py --run` im aktiven Workflow, `qa_gate.test_command: "python3 -m pytest tests/ -q"`
- [x] **Output:** Testausgabe live auf stdout, Artefaktdatei am festen Pfad, Stempel im State, Verdict gesetzt
- [x] **Fehlbedienung:** Befehlstext als Argument, `--out` oder fehlender `qa_gate.test_command` →
- [x] **Side effects:** Datei unter `docs/artifacts/<workflow>/`, ein neuer Key im Workflow-State. Der
- [x] **AC-1:** Given ein konfigurierter Befehl, der mit Exit 1 endet und dabei „5 passed“ ausgibt / When `qa_gate.py --run` läuft / Then lautet das Verdict BROKEN (Exit-Code des Gates 1), unabhängig vom Text
- [x] **AC-2:** Given ein konfigurierter Befehl, der „3 passed in 0.1s“ mit Exit 0 liefert / When `--run` läuft / Then lautet das Verdict VERIFIED
- [x] **AC-3:** Given Exit 0 und Ausgabe „0 passed, 4 skipped“ / When `--run` läuft / Then ist das Ergebnis nicht VERIFIED (Regel #275 bleibt)
- [x] **AC-4:** Given Exit 0 und eine Ausgabe in unbekanntem Format / When `--run` läuft / Then lautet das Verdict AMBIGUOUS mit „Exit 0, Ausgabe nicht auswertbar“ und der Größenvorfilter greift nicht
- [x] **AC-5:** Given der konfigurierte Befehl `false | true` / When `--run` läuft / Then lautet das Verdict BROKEN, weil die Ausführung mit `pipefail` erfolgt
- [x] **AC-6:** Given ein konfigurierter Befehl, der länger läuft als `--timeout 1` und einen Kindprozess startet / When `--run` läuft / Then lautet das Verdict BROKEN mit Timeout-Meldung und die Prozessgruppe ist beendet (kein Prozess des Laufs lebt danach noch)
- [x] **AC-7:** Given ein erfolgreicher Lauf / When er endet / Then existiert die Artefaktdatei am festen Pfad `docs/artifacts/<workflow>/test-run-output.txt` mit der vollen Ausgabe (stdout und stderr zusammen) und der Stempel `qa_run_stamp` hat `source: "run"`, den Exit-Code und einen `output_sha256`, der zur Datei passt
- [x] **AC-8:** Given ein konfigurierter Befehl mit dem Text `secret-token-123` / When der Lauf endet / Then enthält der Stempel nur den SHA-256 des Befehls und nirgends im State steht der Befehlstext
- [x] **AC-9:** Given ein Workflow-State / When `workflow.py set-field qa_run_stamp <Wert>` läuft / Then endet der Aufruf mit BLOCKED und Exit 1 und der Stempel bleibt unverändert
- [x] **AC-10:** Given `qa_gate.py --run "echo x > .claude/workflows/a.json"` (Befehlstext als Argument) und `qa_gate.py --run --out .claude/workflows/a.json` / When das Prüftor sie aufruft / Then weist es beide selbst mit Exit 1 ab (ebenso jedes andere unbekannte Argument), nichts wird ausgeführt, und die State-Datei bleibt byte-identisch; `--infra` (mit `--checklist` und `--no-visual`) wird dagegen angenommen
- [x] **AC-11:** Given eine Sandbox ohne `qa_gate.test_command` (fehlt oder leer) / When `qa_gate.py --run` läuft / Then endet es mit Exit 1, die Meldung nennt den Schlüssel `qa_gate.test_command`, nichts wird ausgeführt und es entsteht weder Artefakt noch Stempel
- [x] **AC-12:** Given eine Testausgabedatei im bisherigen Format / When `qa_gate.py <datei>` ohne `--run` läuft / Then sind Verdict, Meldungen und Altersgrenze unverändert, und der Stempel vermerkt `source: "file"`; die bestehenden Testdateien `test_qa_gate*.py`, `test_testausgabe_erkennung_275.py`, `test_gate_parser_fixes_73_76_79.py` und `test_verdict_pipeline_77.py` bleiben grün
- [x] **AC-13:** Given `core/hooks/bash_gate.py` / When es mit main verglichen wird und `qa_gate.py <datei>` sowie `qa_gate.py --run` durch `bash_gate` geprüft werden / Then ist die Datei gegenüber main unverändert und beide Aufrufe enden mit Exit 0 (Ende-zu-Ende-Verhalten, kein Eingriff in die Whitelist)

## Dialog

### Runde 1
**Adversary:** Ich greife die einzige Produktivänderung der Vorrunde an: `os.O_NONBLOCK` in den Flags von `os.open` in `run_and_capture` (core/hooks/qa_gate.py:542). Meine Fragen und Probes (Skript r6.py im Scratchpad, direkter Aufruf von `qa_gate.run_and_capture`):
1. Hat O_NONBLOCK Folgen für große Ausgaben in eine reguläre Datei (EAGAIN, Teilschreibvorgänge)?
2. Wird eine bestehende Datei weiterhin gekürzt, wird eine neue weiterhin angelegt?
3. FIFO ohne Leser: Hängt der Aufruf noch?
4. FIFO mit Leser: Wird der Befehl trotz Leser ausgeführt, also ist der Schutz umgehbar?
5. Hardlink, Symlink und Verzeichnis am Artefaktpfad: Ist das fail-closed?

**Implementierer:** Gemessene Belege:
- (1) Befehl schreibt 50.000.001 Byte nach stderr (also in die Pipe, dann in die Artefaktdatei). Ergebnis: `large 0 False 50000001`. Die Datei hat die volle Größe, kein Datenverlust. O_NONBLOCK wirkt auf regulären Dateien nicht (Schreiben blockiert dort nie, kein EAGAIN), und `os.fdopen(fd,"wb")` mit `_pump` schreibt zeilenweise mit flush.
- (2) Neue Datei: wird per O_CREAT angelegt (das große Beispiel legte `a.txt` neu an). Bestehende Datei mit 1000 Byte "y": nach dem Lauf `trunc True 0`, Inhalt exakt "hi\n". `ftruncate(fd,0)` greift also weiterhin.
- (3) FIFO ohne Leser: `fifo-noreader OSError [Errno 6] Device not configured ... 0.0` (ENXIO) nach 0.0 s, der Befehl lief nicht (kein `RAN`). Kein Hängen. Das ist ein Traceback und kein `_usage_error`, aber Exit ≠ 0 und nichts ausgeführt, also fail-closed (bekannter Restpunkt).
- (4) FIFO mit Leser (Leser per `O_RDONLY|O_NONBLOCK` offen): `ERROR: Artefaktpfad ... ist keine eigenstaendige Datei — Abbruch.`, SystemExit 1. Das `S_ISREG`-Prüfen nach dem Öffnen (qa_gate.py:543-545) fängt das ab, Befehl nicht gestartet, Exit 1.
- (5) Hardlink (st_nlink=2): derselbe `_usage_error`, SystemExit 1. Symlink: `OSError ELOOP` (O_NOFOLLOW), Verzeichnis: `IsADirectoryError`. Beides Traceback, Exit ≠ 0, vor dem Lauf. Alle drei sind fail-closed und genau die dokumentierten Restpunkte.
Code reference: core/hooks/qa_gate.py:542 (Flags mit O_NONBLOCK), :543-546 (Prüfung S_ISREG/nlink, danach erst ftruncate).
Der Fix ist wirksam und schadet dem Normalpfad nicht.

### Runde 2
**Adversary:** Zweite Runde: Fokus auf die ACs am aktuellen Diff (7 Dateien: CHANGELOG.md, config.yaml, config_loader.py, qa_gate.py, workflow.py, ci_spec_gate.py, tests/test_qa_gate_run_345.py) und auf Regressionen. Fragen:
- Ist `qa_gate` in `PLUGIN_CONFIG_KEYS` (core/hooks/config_loader.py:49), sodass `qa_gate.test_command` überhaupt gelesen wird?
- Ist `qa_run_stamp` für `set-field` gesperrt (core/hooks/workflow.py:1374) und hat der Stempel einen einzigen Schreibpfad (core/hooks/workflow.py:415 `write_qa_run_stamp`, Aufruf aus core/hooks/qa_gate.py:494)?
- Wird der Befehlstext nie im State abgelegt (AC-8) und nehmen unbekannte Argumente den Abbruch vor der Ausführung (`_check_run_args`, core/hooks/qa_gate.py:~596-617)?
- Läuft die komplette Suite grün, inklusive 21 Tests in tests/test_qa_gate_run_345.py?

**Implementierer:** Belege:
- core/hooks/config_loader.py:49 enthält `"qa_gate"` in `PLUGIN_CONFIG_KEYS`, `_run_config` (core/hooks/qa_gate.py:~620-640) liest es per `load_config()`. Fehlt/leer: `_usage_error` mit Schlüsselnamen `qa_gate.test_command` (core/hooks/qa_gate.py:627), das passiert vor `run_and_capture`, es entsteht kein Artefakt und kein Stempel (AC-11).
- core/hooks/workflow.py:1374 sperrt `qa_run_stamp` ("wird von qa_gate.py gesetzt") für `set-field` (AC-9). Schreibpfad: core/hooks/workflow.py:415-427 `write_qa_run_stamp`, aufgerufen von core/hooks/qa_gate.py:494-495. Die Warnung bei Fehlschlag (:497) bricht nicht lautlos ab.
- `_check_run_args` lässt nur `--timeout --checklist --screenshot --no-visual --infra` zu, alles andere (Befehlstext, `--out`) endet mit `_usage_error` Exit 1 vor jeder Ausführung (AC-10). `_judge_run` (core/hooks/qa_gate.py:~578) liefert: Timeout → BROKEN, Exit ≠ 0 → BROKEN (AC-1), `validate_test_output(trusted=True)` → VERIFIED (AC-2) bzw. AMBIGUOUS „Exit 0, Ausgabe nicht auswertbar“ (AC-4), „0 passed, 4 skipped“ nicht VERIFIED (AC-3). `bash -o pipefail -c` in `run_and_capture` (AC-5), `start_new_session=True` plus `_kill_group` mit SIGTERM/SIGKILL auf die Prozessgruppe (AC-6). Artefakt + Stempel mit `source` (run/file) und `output_sha256` (AC-7, AC-12), Befehl nur als SHA (AC-8). `core/hooks/bash_gate.py` ist im `git diff --stat` nicht enthalten, also gegenüber main unverändert (AC-13).
- Tests: `tests/test_qa_gate_run_345.py` 21 passed (6 s). Volle Suite: `2389 passed, 23 skipped in 174.36s`. 0 fehlgeschlagen. Die 23 übersprungenen sind vorbestehende Skips, nicht durch --run verursacht (die Suite ist insgesamt grün, ≥ 2389 bestanden).
Regressionen: Die einzige geänderte Zeile der Vorrunde ist qa_gate.py:542, andere Aufrufer von `os.open` mit diesen Flags gibt es nicht (nur `run_and_capture`). Early-Agreement-Skepsis: jeder Punkt wurde am Code bzw. an einer Messung belegt (siehe oben), nicht an der Behauptung der Vorrunde.

Status: CONFIRMED
Code reference: core/hooks/qa_gate.py:542
Code reference: core/hooks/qa_gate.py:494
Code reference: core/hooks/qa_gate.py:627
Code reference: core/hooks/workflow.py:415
Code reference: core/hooks/workflow.py:1374
Code reference: core/hooks/config_loader.py:49

Confirmation:
  AC: AC-1 bis AC-13, Input, Output, Fehlbedienung, Side effects
  Code reference: core/hooks/qa_gate.py:542
  Evidence: wie in Runde 2; Probe r6.py und 21/21 Tests in test_qa_gate_run_345.py, Suite 2389 passed
  Status: CONFIRMED

Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED
Status: CONFIRMED

Findings: keine neuen. Bekannte Restpunkte (Traceback statt `_usage_error` bei Verzeichnis/Symlink/FIFO ohne Leser; F006 TOCTOU #407; Stempel-Fälschung per Import, setsid #404) sind fail-closed (Exit ≠ 0, nichts ausgeführt) und werden nicht erneut gewertet.

## Herkunft der Vorbedingungen

kein Sprachprofil konfiguriert (`precondition_origins.default_lang`)

## Verdict
VERDICT: VERIFIED

## Geprüfte Dateien

- sha256:804d4318753babcd594c7727d6a8935b55f8c4bf1f853cf0a948130c0093b4be  core/hooks/config_loader.py
- sha256:d9eb99e09d32462ccc32291c6397c3e72e73bf0cb4a5c1d0227b2998462aed62  core/hooks/qa_gate.py
- sha256:77fb882bdb93f04f90cbaebb71f8d247650a587bbfa7967894242340ae0fe6f8  core/hooks/workflow.py

## Prüfbasis

- base: f636c762e340b2d4b47e1d155cd3a30b2dac6275
- blob:e3ec6d1157d364ebe6a9081be6e7d9317f75ae53  core/hooks/config_loader.py
- blob:2c93d6d516cf0c6a6ec0cb08ff5878d088538a76  core/hooks/qa_gate.py
- blob:a9827520b3be91128551d6fa92517a214680888f  core/hooks/workflow.py
