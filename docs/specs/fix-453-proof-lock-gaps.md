---
entity_id: fix-453-proof-lock-gaps
type: bugfix
created: 2026-10-23
updated: 2026-10-23
status: draft
workflow: fix-453-proof-lock-gaps
version: "1.0"
tags: [bash-gate, evidence-gate, beleg-sperre, haertung, restluecken]
test_targets: ["tests/test_proof_lock_453.py", "tests/test_proof_lock_448.py", "tests/test_evidence_gate_447.py"]
---

# Beleg-Schreibsperre 1d: Restlücken aus #448 schließen — #453

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #453 (Restbefunde F001 bis F007 aus Adversary-Dialog und Validierung zu #448). Dieselben Lücken in den Sperren 1b (Config) und 1c (Hauptordner) sind **nicht** Teil dieser Spec, sondern Folge-Issue #452.

## Purpose

Die Beleg-Schreibsperre (Prüfung 1d in `bash_gate.py`) verhindert, dass Claude den Simulator-Beleg (`docs/artifacts/<wf>/simulator-run.txt` und alles unter `docs/artifacts/<wf>/simulator-run/`) von Hand schreibt. Nach #448 blieben per Probe mit dem echten Gate sechs Umgehungsfamilien offen (Interpreter-Optionen mit Wert, weitere Befehlspräfixe, Glob/Brace/`cp -t`/`curl -oDATEI`/`git mv`/rekursives Kopieren, Shell-Aufrufe in Inline-Code, Umgebungs-Präfix-Zuweisungen, `tar -cf`) sowie ein Fehlalarm (Inline-Skript liest den Beleg und schreibt woanders). Diese Spec schließt alle Wege, mit denen ein Beleg **gefälscht** werden kann, und behebt den Fehlalarm; reines **Zerstören** des Belegs bleibt bewusst erlaubt, weil das Evidence-Gate fail-closed ist. Rein regelbasiert, ohne Modell, ohne neue Abhängigkeit. Ziel ist „kein trivialer Einzeiler mehr“, nicht Vollständigkeit.

## Source

- **File:** `core/hooks/bash_gate.py` — nur der 1d-Abschnitt (ca. Zeilen 618 bis 818): `_PROOF_LINK_PATTERNS`, `_PROOF_AREA_PATTERNS`, `_PROOF_MENTION_RE`, `_INLINE_WRITE_RE`, `_PROOF_PREFIXES`, `_opt_values`, `_tar_dir`, `_PROOF_WRITERS`, `_PROOF_DIR_WRITERS`, `_skip_prefixes`, `_nested_payload`, `_inline_code`, `_link_paths`, `_proof_path_hit`, `_proof_fallback`, `_proof_segment_hit`, `_proof_text_hit`, `_writes_proof_file`
- **Analyse:** `docs/context/fix-453-proof-lock-gaps.md` (Ist-Stand per Probe, Technical Approach Punkte 1 bis 11)
- **Vorgänger-Spec:** `docs/specs/feat-448-proof-lock-bypass.md` (21 ACs) — bleibt unberührt (freigegeben, Spec-Freeze)
- **Ursprungs-Spec:** `docs/specs/feat-447-evidence-gate.md` (AC-27 bis AC-29) — bleibt unberührt

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/bash_gate.py` | Modul | Kern-Gate Bash, Prüfung 1d; läuft bei jedem Bash-Aufruf jedes Konsumentenprojekts mit `workflow_enforced`, unabhängig von `evidence_checks` |
| `PROOF_FILE_PATTERNS` (`bash_gate.py:70`) | Konstante | Beleg-Muster; unverändert, wird für Glob-Abgleich per `fnmatch` und Regex weiterverwendet |
| `core/hooks/hook_utils.py` (`_git_lex`, `_git_segments`) | Modul | Zerlegung in Segmente; unverändert |
| `_split_redirects`, `_command_args`, `_positional`, `_copy_targets`, `_into_dir_targets`, `_config_write_targets`, `_cd_bases`, `_has_write_indicator` | Funktionen | Zielerkennung und `cd`-Nachführung; unverändert wiederverwendet |
| `_CONFIG_WRITERS` | Tabelle | Speist auch 1b und 1c (#417/#418, #452); **bleibt unverändert** |
| `core/hooks/evidence_gate.py` (`_verify_xcresult_proof`) | Modul | Fail-closed-Prüfung des Belegs gegen `run.xcresult`; Begründung für die Entscheidung „Zerstören nicht sperren“; unverändert |
| `tests/test_proof_lock_448.py`, `tests/test_evidence_gate_447.py`, `tests/test_bash_gate_config_lock_418.py`, `tests/test_bash_gate_main_write_417.py` | Tests | Regressionsgrenzen; Helfer (`_root`, `_blocked`, `_free`, `_nest`) als Vorbild |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/bash_gate.py` | MODIFY | Nur 1d-Abschnitt: Interpreter-Optionstabelle, erweiterte Präfixliste, Brace-/Glob-Expansion, eigener `cp`-Zielordner-Extraktor, `_opt_values` mit angehängtem Wert, `git mv` in `_link_paths`, Rekursiv-Kopie-Regel, `shred`/`chmod`/`chown`, Inline-Bindung pro Anweisung mit einstufiger Variablen-Verfolgung, erweiterter Schreibindikator (Shell-Aufrufe), segmentlokale Präfix-Umgebung, `tar`-Packmodus |
| `tests/test_proof_lock_453.py` | CREATE | Angriffs- und Negativmatrix aus der Probe |
| `docs/specs/fix-453-proof-lock-gaps.md` | CREATE | Diese Spec |
| `CHANGELOG.md` | MODIFY | Eintrag unter [Unreleased] |
| `_CONFIG_WRITERS`, `_copy_targets`, `_git_write_targets`, `_command_args`, `_positional`, `hook_utils.*`, `edit_gate.py`, Prüfungen 1b/1c | UNVERÄNDERT | Geteilt mit 1b/1c bzw. von diesem Issue nicht betroffen |

### Estimated Changes

- Files: 4 (davon 1 Produktivcode)
- LoC: bash_gate +120/-15, Tests +250

### Out of Scope

- Sperren 1b (Config) und 1c (Hauptordner): Folge-Issue #452.
- Reines Zerstören des Belegs (siehe Known Limitations und ADR-1).
- Ein Override-Ausweg für die Beleg-Sperre: bewusst keiner.
- Änderungen an `edit_gate.py`, `feat-447`- und `feat-448`-Spec.
- Engerfassen der Rückfallregel `_proof_fallback` (nur Beobachtung, siehe Known Limitations).

## Implementation Details

Alles im 1d-Abschnitt von `bash_gate.py`; jede Ausnahme führt weiterhin zu „kein Treffer“ (fail-open, `_writes_proof_file` fängt alles). Abkürzungen in dieser Spec: `P` = Beleg-Datei `ART/simulator-run.txt`, `ART` = `docs/artifacts/wf-447`, `RUN` = `ART/simulator-run`.

1. **Interpreter-Optionen mit Wert (F001):** `_inline_code` kennt je Interpreter eine Tabelle von Optionen, die den nächsten Token als Wert verbrauchen (python `-W -X`; node `-r --require --input-type -C`; perl `-I -M -x` mit getrenntem Wert; ruby `-I -r -C`). Diese Werte werden übersprungen, bevor das erste Nicht-Flag-Token als Skriptdatei gilt. `-m MODUL` zählt wie eine Skriptdatei (kein Inline-Code). Die Inline-Flags werden um node `--eval`, `-p`, `--print` erweitert. ruby `-E` ist eine Encoding-Option mit Wert und kein Code-Flag.
2. **Präfixliste (F002, ADR-2):** `_PROOF_PREFIXES` wird um `doas` (`-u -C`), `busybox` (nächstes Wort ist das Applet), `flock` (`-w -E` mit Wert, danach Lock-Datei als Positionsargument; `-c CMD` wird wie `sh -c` als Nutzlast rekursiv geprüft), `ionice` (`-c -n -p -t`), `setsid`, `taskset` (Maske als Positionsargument; `-c LISTE`), `chronic`, `builtin` und `xargs` (`-a -d -E -I -L -n -P -s` und Langformen) erweitert. Kein strukturelles „ab jedem Schreiber-Wort neu auswerten“.
3. **Brace und Glob (F003a):** Eigene 1d-Brace-Expansion (Kommalisten, verschachtelt). Ziele mit `?` oder `[` werden zusätzlich per `glob.glob` gegen jede Basis geprüft (Bash-Semantik: Glob expandiert nur gegen Vorhandenes; ohne Treffer bleibt der Literal-Pfad, der den Beleg nicht trifft). Der bestehende Regex-Treffer für `*` bleibt.
4. **`cp`-Zielordner (F003b):** Eigener 1d-Extraktor für `-t` (auch im Bündel `-vt`, angehängt `-tDIR`, `--target-directory DIR` und `=DIR`) liefert `DIR/<basename>` je Quelle. `_copy_targets` bleibt unverändert.
5. **Angehängter Optionswert (F003c):** `_opt_values` erkennt bei Kurz-Flags den angehängten Wert (`-oDATEI`; im Bündel `-sSoDATEI` nach getopt-Semantik: der Rest nach dem wertnehmenden Flag ist der Wert). Nur 1d.
6. **`git mv` (F003d):** Quellen und Ziel werden in `_link_paths` gegen `_PROOF_LINK_PATTERNS` geprüft (Vorfahr-/Link-Regel wie bei `mv`). `git rm` ist Zerstörer und wird nicht gesperrt.
7. **Rekursive Kopie in den Bereich (F003e):** `cp -r/-R/-a` mit Ziel `docs/artifacts` oder `docs/artifacts/<x>` blockt nur, wenn die Quelle auf der Platte einen Eintrag `simulator-run(.txt)` an der Stelle enthält, die im Ziel auf das Beleg-Muster fällt (Quelle `X` wird zu `DEST/basename(X)/…`, Quelle `X/.` wird zu `DEST/…`). `rsync` ist bereits abgedeckt.
8. **Zerstörer auf exakten Beleg-Pfad (F003f):** `shred` (alle Positionsargumente) sowie `chmod` und `chown` (Positionsargumente ab dem zweiten) gegen `PROOF_FILE_PATTERNS`. Nur der exakte Beleg-Pfad, nie der Ordner.
9. **Inline-Bindung pro Anweisung und Shell-Aufrufe (F004, F006, ADR-3):** Inline-Code wird pro Anweisung (Trennung an `;` und Zeilenumbruch) bewertet. Block nur, wenn **eine** Anweisung eine Beleg-Erwähnung **und** einen Schreibindikator enthält. Einstufige Variablen-Verfolgung: Bezeichner, denen eine Erwähnung zugewiesen wird (`p = '…P…'`, `p = Path('…P…')`), zählen in späteren Anweisungen als Erwähnung. `_INLINE_WRITE_RE` wird um Shell-Aufrufe erweitert: `os.system`, `os.popen`, `subprocess.*`, `os.exec*`/`os.spawn*`, node `child_process`/`execSync`/`spawnSync`, perl/ruby `system(`, `exec(`, Backticks, `qx`.
10. **Präfix-Zuweisungen in die Kindumgebung (F005):** Zuweisungen vor dem Kommandowort im selben Segment (`X=P cmd …`) bilden eine segmentlokale Umgebung. Sie wird (a) in die Nutzlast von `sh -c`, `eval` und `flock -c` substituiert und (b) für Inline-Code als Erwähnung gewertet, wenn der Code die Umgebung liest (`environ`, `getenv`, `process.env`, `$ENV{`, `ENV[`). Die Argumente desselben Kommandos (`X=P tee $X`) werden **nicht** substituiert (Bash-Semantik: `$X` wird vor der Präfix-Zuweisung expandiert).
11. **`tar` packen (F007):** Bei Modus `c`/`r`/`u`/`A` (Bündel ohne Strich wie `czf`, mit Strich wie `-cvf`, oder `--create`/`--append`/`--update`) ist der Wert von `-f`/`--file`/`--file=` Schreibziel gegen `PROOF_FILE_PATTERNS`. Wert im Bündel: nächstes Token (getopt), bei altem Stil das erste folgende Argument. Entpacken (`-x -f`) liest nur und bleibt frei.

## Expected Behavior

- **Input:** Ein Bash-Befehl in einem Projekt mit erzwungenem Workflow.
- **Output:** Exit 2 mit Begründung, wenn der Befehl den Beleg schreiben, überschreiben, verlinken oder per Kopie/Packen/Verschieben ersetzen kann (Fälschen), sowie bei `shred`/`chmod`/`chown` auf den exakten Beleg-Pfad; sonst Exit 0 wie bisher.
- **Side effects:** Keine. Lesezugriffe, Erwähnungen in Doku, Aufräumen und Anlegen von Ordnern (`rm -rf`, `mkdir -p`), Packen **aus** dem Beleg-Ordner in ein anderes Ziel und der Erzeuger-Aufruf bleiben frei. Sperren 1b/1c und das Edit-Gate verhalten sich unverändert.

## Known Limitations

- **Zerstörer (F003g):** `rm -rf ART`, `rm -rf docs/artifacts`, `git rm -r ART` und `mkdir -p RUN/x` werden bewusst **nicht** gesperrt. Begründung: Das Evidence-Gate (`_verify_xcresult_proof`) ist fail-closed; fehlender Beleg, fehlende oder prüfsummenlose `summary.json` und fehlendes `run.xcresult` werden abgelehnt. Reines Zerstören führt nie zu einem falschen Phase-8-Durchlauf, nur zu einem Neu-Erzeugen. Eine Sperre träfe dagegen legitimes Aufräumen und Anlegen (`rm -rf docs/artifacts/<wf>`, `mkdir -p docs/artifacts/<wf>`) in jedem Konsumentenprojekt.
- **Nicht gelistete Präfixe:** `su -c`, `runuser`, `script -c`, `unshare`, `chroot`, `watch`, `parallel` und ähnliche reichen Befehle weiter und werden nicht erkannt. Die Präfixliste ist geschlossen (ADR-2).
- **Mehrstufige Variablen-Indirektion im Inline-Code** (`a = 'P'; b = a; open(b, 'w')`) sowie **aus Teilstrings zusammengesetzte Pfade** werden nicht aufgelöst; nur einstufige Zuweisung wird verfolgt (ADR-3).
- **Skriptdateien, `find -exec`, Base64- und zur Laufzeit zusammengesetzte Pfade, Umbenennen von `docs/`:** unverändert wie in #448 dokumentiert.
- **`_proof_fallback` bleibt grob** (Beobachtung, in diesem Issue nicht geändert): Bei Tiefe > 3, Parse-Fehler in der Nutzlast oder Daten-Heredocs mit Interpreter blockt sie „Beleg erwähnt + Schreibindikator“ auch für Doku-Text. Live erlebt: Ein Heredoc, der Analysetext mit Beleg-Pfad in eine Kontextdatei schrieb, wurde geblockt. Ausweg: Datei mit dem Write-Werkzeug schreiben.
- **Glob-Expansion** gilt nur für `?` und `[` gegen vorhandene Dateien; ein Glob, der erst durch den Befehl selbst Treffer erzeugt, wird nicht erkannt.
- **Rekursive Kopie (F003e)** prüft den Quellinhalt zum Zeitpunkt des Hooks; Inhalt, der erst im selben Befehl entsteht, wird nicht gesehen.
- **Schutz nur über die Hooks** (Known Limitation 3 aus #447 bleibt). Defensive Tiefe: Das Evidence-Gate prüft den Beleg zusätzlich gegen `run.xcresult`.

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt
- [ ] Alle Fälschungsformen aus der Probe-Tabelle (F001, F002, F003a bis F003f, F005 über die Kindumgebung, F006, F007) werden mit Exit 2 blockiert, und der Fehlalarm F004 ist behoben (Inline-Skript liest den Beleg und schreibt anderswo: Exit 0)
- [ ] Alle Negativkontrollen der Pflicht-FREE-Liste, einschließlich `X=P tee $X <<< x`, bleiben frei, und die Zerstörer F003g bleiben ausdrücklich frei
- [ ] `CHANGELOG.md` enthält den Eintrag unter [Unreleased]
- [ ] Keine bestehende Funktion ist dabei kaputtgegangen: `tests/test_proof_lock_448.py`, `tests/test_evidence_gate_447.py`, `tests/test_bash_gate_config_lock_418.py` und `tests/test_bash_gate_main_write_417.py` laufen grün

## Acceptance Criteria

- **AC-1 (F001):** Given ein Inline-Interpreter-Aufruf mit wertnehmender Option / When `python3 -W ignore -c "open(P,'w')"`, `python3 -X utf8 -c "…"`, `node -r foo -e "…writeFileSync(P…)"`, `node --eval "…"` oder `node -p "…writeFileSync(P…)"` den Beleg-Pfad mit Schreibindikator enthält / Then beendet sich das Bash-Gate mit Exit 2. `python3 -m modul` gilt wie eine Skriptdatei (Exit 0)
  - Test: `tests/test_proof_lock_453.py::test_interpreter_options_with_value_blocked`
- **AC-2 (F002):** Given ein Schreibbefehl hinter einem der neuen Präfixe / When `doas tee P`, `busybox tee P`, `flock /tmp/l tee P`, `flock /tmp/l -c 'echo x > P'`, `ionice -c 3 tee P`, `setsid tee P`, `taskset 1 tee P`, `chronic tee P` oder `echo x | xargs tee P` ausgeführt wird / Then Exit 2
  - Test: `tests/test_proof_lock_453.py::test_new_command_prefixes_blocked`
- **AC-3 (F003a):** Given ein Ziel mit Glob oder Brace / When `tee ART/simulator-run.t?t`, `tee ART/simulator-run.{txt,x}` ausgeführt wird (der Glob `?` trifft die vorhandene Beleg-Datei) / Then Exit 2; ein Glob ohne Treffer auf dem Dateisystem trifft den Beleg nicht (Exit 0)
  - Test: `tests/test_proof_lock_453.py::test_glob_and_brace_targets_blocked`
- **AC-4 (F003b):** Given `cp` mit Zielordner-Option / When `cp -vt ART /tmp/simulator-run.txt`, `cp -tART /tmp/simulator-run.txt` oder `cp --target-directory ART /tmp/simulator-run.txt` ausgeführt wird / Then Exit 2; `cp -t /tmp/out /tmp/simulator-run.txt` bleibt frei
  - Test: `tests/test_proof_lock_453.py::test_cp_target_directory_blocked`
- **AC-5 (F003c):** Given `curl` mit angehängtem Optionswert / When `curl -oP https://x` oder gebündelt `curl -sSoP https://x` ausgeführt wird / Then Exit 2; `curl -o/tmp/x https://x` bleibt frei
  - Test: `tests/test_proof_lock_453.py::test_curl_attached_output_value_blocked`
- **AC-6 (F003d):** Given `git mv` mit Beleg-Ordner als Quelle oder Ziel / When `git mv ART t` oder `git mv fake-dir ART` ausgeführt wird / Then Exit 2; `git mv a.txt b.txt` bleibt frei
  - Test: `tests/test_proof_lock_453.py::test_git_mv_ancestor_blocked`
- **AC-7 (F003e):** Given eine rekursive Kopie in den Beleg-Bereich, deren Quelle auf der Platte einen Eintrag `simulator-run(.txt)` enthält / When `cp -r /tmp/wf-447 docs/artifacts/` oder `cp -r /tmp/fake/. ART/` ausgeführt wird / Then Exit 2; enthält die Quelle keinen solchen Eintrag (`cp -r screenshots/ ART/`), Exit 0
  - Test: `tests/test_proof_lock_453.py::test_recursive_copy_into_area_blocked_only_with_proof_entry`
- **AC-8 (F003f):** Given Zerstörer auf den exakten Beleg-Pfad / When `shred -u P`, `chmod 000 P` oder `chown root P` ausgeführt wird / Then Exit 2; dieselben Befehle auf eine Nachbardatei (`shred -u ART/shot.png`, `chmod 644 ART/shot.png`) bleiben frei
  - Test: `tests/test_proof_lock_453.py::test_shred_chmod_chown_on_exact_proof_blocked`
- **AC-9 (F005):** Given eine Präfix-Zuweisung, die in die Kindumgebung wirkt / When `X=P sh -c 'tee $X <<< x'` oder `X=P python3 -c "import os; open(os.environ['X'],'w')"` ausgeführt wird / Then Exit 2
  - Test: `tests/test_proof_lock_453.py::test_prefix_assignment_into_child_environment_blocked`
- **AC-10 (F006):** Given Inline-Code mit Shell-Aufruf / When `python3 -c "import os; os.system('echo x > P')"`, `python3 -c "import subprocess; subprocess.run(['tee','P'])"`, node `execSync` oder perl `system(` den Beleg-Pfad enthält / Then Exit 2
  - Test: `tests/test_proof_lock_453.py::test_inline_shell_calls_blocked`
- **AC-11 (F007):** Given `tar` im Packmodus mit dem Beleg als Archivziel / When `tar -cf P …`, `tar czf P …`, `tar -cvf P …` oder `tar --file=P -c …` ausgeführt wird / Then Exit 2; Entpacken (`tar -xf P -C /tmp/out`) und Packen in ein anderes Ziel (`tar -cf /tmp/a.tar ART`) bleiben frei
  - Test: `tests/test_proof_lock_453.py::test_tar_create_with_proof_archive_blocked`
- **AC-12 (F004):** Given Inline-Code, der den Beleg nur liest und anderswo schreibt / When `python3 -c "d=open(P).read(); open('/tmp/out','w').write(d)"` ausgeführt wird / Then Exit 0 (Erwähnung und Schreibindikator liegen in verschiedenen Anweisungen und sind nicht am selben Ziel gebunden); steht beides in **einer** Anweisung (`open(P,'w')`) bleibt es Exit 2
  - Test: `tests/test_proof_lock_453.py::test_inline_read_proof_write_elsewhere_free`
- **AC-13 (Variablen-Verfolgung):** Given ein Inline-Skript, das den Beleg-Pfad einem Bezeichner zuweist / When `python3 -c "p='P'; open(p,'w')"` oder `p=Path('P'); p.write_text('x')` ausgeführt wird / Then Exit 2 (einstufige Verfolgung); mehrstufige Indirektion ist als Known Limitation dokumentiert und nicht Gegenstand eines Blockier-Tests
  - Test: `tests/test_proof_lock_453.py::test_inline_single_level_variable_tracking_blocked`
- **AC-14 (Pflicht-FREE-Liste):** Given die Negativkontrollen / When `cat P`, `tar -cf /tmp/a.tar ART`, `rm -rf docs/artifacts/other-wf`, `mkdir -p ART`, `rm -f ART/shot.png`, `grep tee P`, `git add P`, `ls -la ART`, `python3 -c "print(open(P).read())"`, `echo P`, `git log -- P`, `tar -xf /tmp/a.tar -C /tmp/out` und `X=P tee $X <<< x` (Bash-Semantik: `$X` wird vor der Präfix-Zuweisung expandiert, das Ziel ist leer) ausgeführt werden / Then jeweils Exit 0
  - Test: `tests/test_proof_lock_453.py::test_mandatory_free_list`
- **AC-15 (Zerstörer F003g bewusst frei):** Given reine Zerstörer ohne Fälschungsgewinn / When `rm -rf ART`, `rm -rf docs/artifacts`, `git rm -r ART` oder `mkdir -p RUN/x` ausgeführt wird / Then Exit 0 (dokumentierte Entscheidung ADR-1, fail-closed durch das Evidence-Gate)
  - Test: `tests/test_proof_lock_453.py::test_destroyers_remain_free`
- **AC-16 (ruby `-E`):** Given ruby mit Encoding-Option / When `ruby -E utf-8 skript.rb P` ausgeführt wird / Then Exit 0 (`-E` ist Option mit Wert, kein Code-Flag); `ruby -e "File.write('P','x')"` bleibt Exit 2
  - Test: `tests/test_proof_lock_453.py::test_ruby_encoding_option_not_code`
- **AC-17 (geteilte Bausteine unverändert):** Given die Wiederverwendung durch 1b/1c / When die Änderung abgeschlossen ist / Then `_CONFIG_WRITERS`, `_copy_targets`, `hook_utils` und die Prüfungen 1b/1c sind unverändert, und `tests/test_proof_lock_448.py`, `tests/test_evidence_gate_447.py`, `tests/test_bash_gate_config_lock_418.py` sowie `tests/test_bash_gate_main_write_417.py` laufen grün
  - Test: `tests/test_proof_lock_453.py::test_shared_pieces_unchanged_and_existing_suites_green`
- **AC-18 (fail-open):** Given eine Ausnahme oder ein Parse-Fehler in den neuen Hilfsfunktionen (z. B. `glob.glob` oder `resolve()` wirft, kaputte Quotes im nicht verschachtelten Befehl) / When das Bash-Gate den Befehl prüft / Then Exit 0 (fail-open wie bisher); die Ausnahme von #448 (Tiefe > 3 / Parse-Fehler in Nutzlast mit Rückfall) bleibt unverändert
  - Test: `tests/test_proof_lock_453.py::test_fail_open_on_exception_preserved`

> Die Test-Zuordnung steht bei der Spec-Erstellung fest (Spec-Freeze #230). Weicht ein Testname später ab, wird das in den TDD-RED-Artefakten (`workflow.py add-artifact`) korrigiert, nicht in dieser Datei.

## Test Plan

Automatische Tests (jeweils an eine AC oben gebunden):

- `pytest tests/test_proof_lock_453.py` — neue Datei, parametrisierte Angriffs- und Negativmatrix aus der Probe (Angriff: Exit 2, Negativkontrolle: Exit 0). Helfer wie in `tests/test_proof_lock_448.py` (`_root`, `_blocked`, `_free`, `_nest`) gegen den echten `bash_gate.py`-Subprozess; die Sandbox legt zusätzlich `docs/artifacts/other-wf/` an. Dateien, die für Glob-, `chmod`- und Rekursiv-Kopie-Fälle existieren müssen (Beleg-Datei, Quellordner mit/ohne `simulator-run`-Eintrag), werden real angelegt, kein Mocking.
- `pytest tests/test_proof_lock_448.py tests/test_evidence_gate_447.py tests/test_bash_gate_config_lock_418.py tests/test_bash_gate_main_write_417.py` — bestehende Regressionsgrenzen bleiben grün (AC-17, insbesondere AC-29 „Sperre ist eng“).
- `pytest tests/` — Gesamtlauf.
- RED zuerst: Alle Fälschungsformen (AC-1 bis AC-11, AC-13) liefern vor der Implementierung Exit 0 statt 2; AC-12 liefert Exit 2 statt 0; die Negativkontrollen (AC-14, AC-15, AC-16 Teil 1) sind schon vorher grün.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine (drei lokale Entscheidungen, hier vollständig begründet; kein projektübergreifendes ADR nötig)
- **Rationale:** Alle drei Entscheidungen betreffen nur die interne Auslegung der Sperre 1d und sind mit dieser Spec abgedeckt.

**ADR-1: Fälschen schließen, Zerstören nicht.**
- *Kontext:* Die Sperre soll verhindern, dass ein Beleg von Hand erzeugt wird. Das Evidence-Gate prüft fail-closed (Beleg, `summary.json` mit Prüfsumme, `run.xcresult`). Ein zerstörter Beleg führt deshalb nie zu einem falschen Phase-8-Durchlauf.
- *Entscheidung:* Alle Wege, die Inhalt erzeugen, überschreiben, einschleusen oder verlinken, werden gesperrt. Reine Zerstörer (`rm -rf ART`, `rm -rf docs/artifacts`, `git rm -r ART`, `mkdir -p RUN/x`) bleiben frei. Ausnahme: `shred`, `chmod` und `chown` nur auf den exakten Beleg-Pfad, weil dort kein Fehlalarm-Risiko besteht.
- *Alternativen:* Alle Zerstörer sperren (verworfen: trifft legitimes Aufräumen und Anlegen in jedem Konsumentenprojekt, kein Fälschungsgewinn). Auch `shred`/`chmod` auf Ordner sperren (verworfen: Fehlalarme).
- *Konsequenzen:* Ein Beleg kann gelöscht werden; die Folge ist ein Neu-Erzeugen, kein Betrug. Als Known Limitation dokumentiert.

**ADR-2: Geschlossene Präfixliste erweitern statt struktureller Neuauswertung.**
- *Kontext:* `_PROOF_PREFIXES` kennt nur eine feste Liste von Befehlen, die ein anderes Kommando als Argument tragen.
- *Entscheidung:* Die Liste wird um `doas`, `busybox`, `flock`, `ionice`, `setsid`, `taskset`, `chronic`, `builtin`, `xargs` mit jeweils bekannten Optionen erweitert.
- *Alternativen:* Ab jedem Schreiber-Wort im Segment neu auswerten (verworfen: erzeugt Fehlalarme wie `grep tee P`, weil das Schreiber-Wort dort nur Argument ist); Allowlist der Kommandowörter statt Blocklist (verworfen: kippt das Fehlalarm-Verhältnis).
- *Konsequenzen:* Nicht gelistete Präfixe (`su -c`, `runuser`, `script -c`, `unshare`, `chroot`, `watch`, `parallel`) bleiben offen und stehen in den Known Limitations. Jede weitere Form ist eine kleine, gezielte Ergänzung.

**ADR-3: Bindung pro Anweisung plus einstufige Variablen-Verfolgung im Inline-Code.**
- *Kontext:* Die #448-Regel „Erwähnung irgendwo plus Schreibindikator irgendwo“ blockt Skripte, die den Beleg nur lesen und anderswo schreiben (F004), und kennt keine Shell-Aufrufe (F006).
- *Entscheidung:* Bewertung pro Anweisung (Trennung an `;` und Zeilenumbruch); Block nur, wenn dieselbe Anweisung Erwähnung und Schreibindikator enthält. Bezeichner, denen eine Erwähnung einstufig zugewiesen wurde, zählen später als Erwähnung. Der Schreibindikator wird um Shell-Aufrufe erweitert.
- *Alternativen:* Shell-Strings aus dem Code herausziehen und rekursiv durch die Segmentprüfung schicken (verworfen: deckt die Listenform `subprocess.run(['tee','P'])` nicht ab und kostet mehr Code); vollständige Datenflussanalyse (verworfen: für einen Hook, der bei jedem Befehl läuft, unverhältnismäßig).
- *Konsequenzen:* F004 ist behoben, F006 geschlossen. Mehrstufige Indirektion und aus Teilstrings zusammengesetzte Pfade bleiben unentdeckt (Known Limitation, wie „zusammengesetzte Pfade“ in #448). `_proof_fallback` bleibt unverändert grob.

## Changelog

- 2026-10-23: Initial spec created
