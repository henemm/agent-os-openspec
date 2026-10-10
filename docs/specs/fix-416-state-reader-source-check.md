---
entity_id: fix-416-state-reader-source-check
type: bugfix
created: 2026-10-10
updated: 2026-10-10
status: draft
workflow: fix-416-state-reader-source-check
version: "1.0"
tags: [state-integrity, hook-utils, symlink, hardlink, leser, fail-open]
test_targets: ["tests/test_state_reader_source_416.py"]
---

# State-Leser prüfen an der Quelle: nur eigene normale Datei — #416

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #416 (ausgegliedert aus #410, Teil 3). Schließt Befund F004 aus #410. Die Config-Sperre (#418) und der allgemeine Bash-Schreibzugriff aufs Hauptrepo (#417) sind nicht Teil dieser Spec.

## Purpose

Der Workflow-State (`.claude/workflows/<name>.json`) trägt die Freigaben der Gate-Kette (Phase, Adversary-Verdict, Approval). Heute liest jeder Leser die Datei ungeprüft per `json.loads(path.read_text())`. Ein harter Verweis von außen (`ln <state> docs/x.txt`, dann Schreiben in `docs/x.txt`), ein Symlink anstelle der State-Datei oder ein Symlink anstelle des Ordners `.claude/workflows` lässt einen gefälschten Inhalt (`phase7_validate`, `adversary_verdict: VERIFIED`) als echten State durchgehen; die Textprüfung in `bash_gate` (3a/3b, #407/#410) erfasst nicht jede Befehlsform (F004). Diese Spec verlegt die Prüfung an die Quelle: Der State wird nur gelesen, wenn er nachweislich eine eigene, normale Datei ist (`S_ISREG`, `st_nlink == 1`, kein Symlink in der Pfadkette ab `.claude`). Eine gemeinsame Lesefunktion in `hook_utils` löst das für alle Leser; bei Fund gilt „kein vertrauenswürdiger State = keine Freigabe“ mit klarer Meldung statt stillem Ignorieren. Rein regelbasiert, ohne Modell, ohne neue Abhängigkeit.

Reproduziert (2026-10-10, Wegwerf-Projekte): In allen drei Varianten (harter Verweis, Symlink auf Datei, Symlink auf Ordner) zeigt `workflow.py status` „Phase: Validation“ und `read_active_workflow_fast()` liefert `VERIFIED`, ohne Warnung.

## Source

- **Analyse:** `docs/context/fix-416-state-reader-source-check.md` (Abschnitte „Leser-Liste“, „Reproduktion“, „Technical Approach“, „Alternativen“, „Known Limitations“)
- **Ursprungsanfrage:** GitHub-Issue #416
- **Vorbild der Prüfung:** `core/hooks/qa_gate.py` (#345: `O_NOFOLLOW` + `fstat` + `S_ISREG`/`st_nlink`), erweitert um die Prüfung der Elternkette
- **Quellen der Leser:** `core/hooks/workflow.py` (`_read_workflow`, `_read_active`, `read_active_workflow_fast`), `edit_gate.py`, `bash_gate.py`, `post_bash.py`, `phase_listener.py`, `footer_gate.py`, `adversary_dialog.py`, `session_singleton_guard.py`
- **Recherche:** CERT POS01-C (Verweise beim Öffnen prüfen, `st_nlink > 1` verweigern), CERT POS35-C (TOCTOU: `O_NOFOLLOW` wirkt nur im letzten Pfadglied, Elternkette gesondert prüfen)

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `core/hooks/hook_utils.py` (`find_project_root`, `resolve_active_workflow`, `block`) | Modul | Heimat der neuen gemeinsamen Funktion; Wurzel- und Namensauflösung bleiben unverändert |
| `core/hooks/workflow.py` | Modul | Zentraler Leser (`_read_workflow`) und Schreiber (`_atomic_write`); `tdd_enforcement`, `post_implementation_gate` und `qa_gate` ziehen über `read_active_workflow_fast` mit |
| `core/hooks/tdd_enforcement.py`, `core/hooks/post_implementation_gate.py` | Modul | Ändern sich nicht im Code, übernehmen das Verhalten über `read_active_workflow_fast` (Blocken bzw. fail-open) |
| `core/hooks/qa_gate.py` | Modul | Eigene `O_NOFOLLOW`-Prüfung (#345) bleibt; `write_qa_run_stamp` liest über `read_active_workflow_fast` mit |
| `docs/specs/fix-407-ln-state-integrity.md`, `docs/specs/fix-410-state-integrity-gaps.md` | Spec | Textprüfung als erste Schicht; F004 in der #410-Spec wird aufgelöst |
| `tests/test_bash_gate_state_integrity_410.py` | Test | Bestehender Bestand muss grün bleiben |

## Scope

### Affected Files

| File | Change Type | Description |
|------|-------------|-------------|
| `core/hooks/hook_utils.py` | MODIFY | `read_state_json(path, root)`, `UnsafeStateError(Exception)` (erbt nicht von `OSError`/`ValueError`), `atomic_write_json(path, data)` |
| `core/hooks/workflow.py` | MODIFY | `_read_workflow`, `_read_active`, `read_active_workflow_fast` über die gemeinsame Funktion; CLI-Pfade exit 1 mit Meldung; `_atomic_write` delegiert an `hook_utils.atomic_write_json` |
| `core/hooks/edit_gate.py` | MODIFY | Lesestellen `_read_active_workflow`, `_find_workflow_for_file`, `_find_workflow_by_spec_file` und LoC-Delta (Lesen-Ändern-Schreiben); unsicher: Code-Edit blocken, Always-Allowed unverändert |
| `core/hooks/bash_gate.py` | MODIFY | `_read_active_workflow` und `_write_e2e_scope` (Lesen-Ändern-Schreiben); unsicher: nur state-abhängige Freigaben verweigern |
| `core/hooks/post_bash.py` | MODIFY | `_record_test_run` (Lesen-Ändern-Schreiben) über den sicheren Leser |
| `core/hooks/phase_listener.py` | MODIFY | `_read_active_workflow` fail-open mit Warnung; `_save_workflow` atomar |
| `core/hooks/footer_gate.py` | MODIFY | `_expected_command` fail-open mit Warnung |
| `core/hooks/adversary_dialog.py` | MODIFY | Fast-Track-Check, Metriken, `required-files` |
| `core/hooks/session_singleton_guard.py` | MODIFY | `_read_workflow_phase` über die gemeinsame Funktion, bei Fund `None` |
| `tests/test_state_reader_source_416.py` | CREATE | Je Leser × Richtung plus Normalfall, parametrisiert; Subprozess-Aufrufe der Hooks, wo das Verhalten über den Exit-Code sichtbar ist |
| `docs/specs/fix-410-state-integrity-gaps.md` | MODIFY | Known Limitation F004 verweist auf diese Spec und gilt als aufgelöst |
| `CHANGELOG.md` | MODIFY | Eintrag unter `[Unreleased]`, **kein** Versions-Bump |

`workflow.py` ist der zentrale Leser; weitere Aufrufer (`cmd_list`, `cmd_find`, `cmd_retro_list`, `cmd_retro`, `cmd_cleanup_stale_locks`) laufen über `_read_workflow` und brauchen keine eigene Änderung.

### Estimated Changes

- Files: 12 (davon 9 Code, 1 Test, 2 Doku). Das liegt über der Grenze von 4-5 Dateien.
- LoC: ca. +420/-40 (Code ca. +190/-40, Tests ca. +230), in Summe ca. 460 bei einer Grenze von ±250.
- **Überschreitung ist vom PO bestätigt:** Henning hat am 2026-10-10 im Intake ein Ticket ohne Teilung bestätigt (gemeinsames Ziel „jeder Leser prüft an der Quelle“; eine Teilung ließe Leser ungeprüft und verfehlte die Definition of Done). Spec, Analyse-Kontext und PO-Briefing zählen im LoC-Gate zusätzlich als Code (#294, Fehlalarm); mit laufendem Workflow ab phase6 entfällt der Override für `core/hooks/` (#322).
- Alle Funktionen bleiben unter 50 Zeilen.
- Risiko hoch: Die Lesefunktion läuft bei jedem Werkzeugaufruf in jedem Konsumentenprojekt. Ein Fehlalarm sperrt Code-Edits. Deshalb Gegenproben im Normalfall (AC-5, AC-6, AC-18).

## Implementation Details

**1. Prüfung an der Quelle per `dir_fd`-Walk (TOCTOU-frei).** `read_state_json(path, root)` öffnet `root` mit `O_DIRECTORY`, danach `.claude`, `workflows` (und ggf. `_archive`) jeweils mit `O_NOFOLLOW|O_DIRECTORY` und `dir_fd=` des Vorgängers; die Datei selbst mit `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`. Ein `fstat` auf den geöffneten Deskriptor muss `S_ISREG` und `st_nlink == 1` ergeben; gelesen wird über denselben Deskriptor, sodass zwischen Prüfung und Lesen nichts getauscht werden kann. `ELOOP`/`ENOTDIR` an einem Pfadglied, ein Nicht-Regulärtyp oder `st_nlink != 1` ergeben `UnsafeStateError(pfad, grund)`. Eine fehlende Datei (`ENOENT`) und kaputtes JSON verhalten sich wie heute (`FileNotFoundError` bzw. `json.JSONDecodeError`).

**2. Wurzel.** Die Wurzel, die der Aufrufer ohnehin nutzt (modulweites `_root` bzw. `find_project_root()`), wird per `realpath` aufgelöst und gilt als vertrauenswürdig; das deckt eine Projektwurzel hinter einem Symlink (macOS `/tmp` → `/private/tmp`) ab. Geprüft wird ab `.claude` abwärts; auch `.claude` als Symlink wird abgelehnt.

**3. `UnsafeStateError` erbt von `Exception`, nicht von `OSError`/`ValueError`.** Viele Leser fangen `OSError` oder `ValueError` und werten das als „kein Workflow“ (fail-open). Ein Fund darf dort nicht versehentlich verschluckt werden; jeder Leser behandelt ihn ausdrücklich.

**4. Verhalten bei Fund: „kein vertrauenswürdiger State = keine Freigabe“, nicht „kein Workflow“.**

| Leser | Verhalten bei Fund |
|-------|--------------------|
| `edit_gate`, `tdd_enforcement` (über `read_active_workflow_fast`) | Code-Edit blocken (Exit 2) mit Meldung; Always-Allowed-Dateien bleiben frei |
| `bash_gate` | Nur state-abhängige Freigaben (Commit-Gate) verweigern; übrige Befehle laufen, damit der Zustand bereinigt werden kann (keine Aussperrung) |
| `phase_listener`, `footer_gate`, `post_implementation_gate` | fail-open mit Warnung, nie Exit 2; `phase_listener` schreibt keinen Phasenwechsel und keine Freigabe |
| `workflow.py`-CLI | exit 1 mit Meldung |
| `adversary_dialog` | Fast-Track gewährt keine Freigabe; Metriken Warnung; `required-files` exit 1 |
| `session_singleton_guard` | `None` (informativ) |

**5. Keine Reparatur durch Kopieren.** Das würde die Fälschung legalisieren. Die Meldung nennt Pfad, Grund (symbolischer Verweis, harter Verweis mit Anzahl, keine normale Datei) und den Bereinigungsweg: Verweis bzw. State-Datei entfernen und den Workflow frisch starten.

**6. Writer.** `phase_listener._save_workflow` schreibt künftig atomar (tempfile + `os.rename` über `atomic_write_json`; neuer Inode, bricht harte Verweise und ersetzt einen Symlink durch eine normale Datei). Die Lesen-Ändern-Schreiben-Stellen (`edit_gate` LoC-Delta, `bash_gate._write_e2e_scope`, `post_bash._record_test_run`) lesen zwingend über den sicheren Leser und schreiben bei Fund **nicht** zurück (sonst würde die Fälschung atomar als echte Datei „gewaschen“).

## Expected Behavior

- **Input:** Jeder Lesezugriff auf `.claude/workflows/<name>.json` (und `_archive/`) durch einen der genannten Leser.
- **Output:** Normale eigene Datei: Verhalten wie heute. Verweis hart oder weich (Datei, Ordner `.claude/workflows`, `.claude`): der Leser verweigert gemäß Tabelle in Implementation Details Punkt 4, mit Meldung zu Pfad, Grund und Bereinigungsweg.
- **Side effects:** Keine neuen Subprozesse, keine neuen Abhängigkeiten, keine geänderten Config-Keys, kein neues State-Format. Beim Fund wird nichts zurückgeschrieben und nichts kopiert.

## Known Limitations

- **Link anlegen, schreiben, Link löschen:** `ln state docs/x; echo … > docs/x; rm docs/x` hinterlässt eine normale Datei mit `st_nlink == 1` und gefälschtem Inhalt; die Fälschung ist beim Lesen nicht erkennbar. Eine Inhaltsbindung (Alternative B) würde das schließen, liefert aber ohne Schlüssel außerhalb der Reichweite von Bash nur Scheinsicherheit.
- **Direktes Schreiben ohne Link** (`python3 -c` mit zusammengesetztem Pfad) bleibt Sache der Textprüfung; #416 schließt nur die Link-Klasse.
- **Symlink von außen auf den Ordner** (`ln -s .claude/workflows docs/w`) ist beim Lesen über den echten Pfad nicht erkennbar (Ziel ist eine normale Datei mit `st_nlink == 1`); bleibt Sache der Textprüfung (#407).
- **Fehlalarmquellen (selten):** `cp -l`/`rsync --link-dest` aus dem Live-Ordner, `.claude` als Dotfile-Symlink. APFS-Klone und Time Machine lösen nicht aus. Bereinigungsweg steht in der Meldung.
- Verteilung: wirkt in Konsumentenprojekten erst nach dem Plugin-Update.

## Bewusst nicht im Scope (Folgeticket, gleiche Angriffsfläche)

`migrate_state.py` (Altbestand), die Marker `active_workflow` und `settings.local.json` (wählen nur den Namen; der State wird danach geprüft gelesen), Override-Token, Stop-Lock, Pending-Validation-Lock, Approval-Marker, Footer-State und Session-Locks. Sie werden als gemeinsames Folgeticket „weitere Zustandsdateien an der Quelle prüfen“ angelegt (Bündelungsregel: ein Ticket je Ziel).

## Definition of Done

Fertig ist diese Änderung, wenn:

- [ ] Jede Acceptance Criterion unten ist durch einen automatischen Test belegt, bei den Verweisrichtungen je ein Test pro Richtung (harter Verweis, Symlink auf Datei, Symlink auf Ordner `.claude/workflows`, `.claude` als Symlink)
- [ ] Bei hartem wie weichem Verweis verweigert jeder Leser gemäß seiner Regel; der Fälschungsfall aus der Reproduktion (`VERIFIED` über Verweis) liefert kein Verdict mehr
- [ ] Eine normale State-Datei verhält sich in jedem Leser unverändert; die Vollsuite ist grün
- [ ] Known Limitation F004 in `docs/specs/fix-410-state-integrity-gaps.md` verweist auf diese Spec und gilt als aufgelöst; die verbleibenden Grenzen sind in Spec und CHANGELOG-Eintrag benannt
- [ ] Das Folgeticket für die weiteren Zustandsdateien ist als GitHub-Issue angelegt

## Acceptance Criteria

- **AC-1:** Given eine Projektwurzel, in der `.claude/workflows/<wf>.json` mit einem zweiten Namen hart verlinkt ist (`st_nlink == 2`) / When `read_state_json` die Datei liest / Then wirft sie `UnsafeStateError`, die Meldung nennt Pfad, Grund (harter Verweis, Linkzahl) und Bereinigungsweg, und es wird nichts geschrieben
  - Test: `tests/test_state_reader_source_416.py::test_read_state_json_hartlink_wird_abgelehnt`
- **AC-2:** Given eine Projektwurzel, in der `.claude/workflows/<wf>.json` ein Symlink auf eine andere Datei ist / When `read_state_json` die Datei liest / Then wirft sie `UnsafeStateError` mit Grund „symbolischer Verweis“
  - Test: `tests/test_state_reader_source_416.py::test_read_state_json_symlink_auf_datei_wird_abgelehnt`
- **AC-3:** Given eine Projektwurzel, in der der Ordner `.claude/workflows` ein Symlink auf einen anderen Ordner ist / When `read_state_json` eine State-Datei darin liest / Then wirft sie `UnsafeStateError` (Elternkette wird geprüft, nicht nur das letzte Glied)
  - Test: `tests/test_state_reader_source_416.py::test_read_state_json_symlink_auf_ordner_wird_abgelehnt`
- **AC-4:** Given eine Projektwurzel, in der `.claude` selbst ein Symlink ist / When `read_state_json` eine State-Datei darunter liest / Then wirft sie `UnsafeStateError`
  - Test: `tests/test_state_reader_source_416.py::test_read_state_json_claude_als_symlink_wird_abgelehnt`
- **AC-5:** Given eine normale eigene State-Datei (`S_ISREG`, `st_nlink == 1`, keine Verweise in der Kette), eine fehlende Datei und eine Datei mit kaputtem JSON / When `read_state_json` bzw. jeder Leser sie liest / Then liefert die normale Datei den Inhalt wie heute, die fehlende Datei `FileNotFoundError` bzw. das heutige „kein Workflow“, das kaputte JSON `json.JSONDecodeError` wie heute; es gibt keinen `UnsafeStateError`
  - Test: `tests/test_state_reader_source_416.py::test_normalfall_fehlende_datei_und_kaputtes_json_wie_heute`
- **AC-6:** Given eine Projektwurzel, die selbst hinter einem Symlink liegt (z. B. `/tmp` → `/private/tmp` auf macOS, im Test ein Symlink-Elternordner der Wurzel) / When `read_state_json` eine normale State-Datei liest / Then liefert sie den Inhalt ohne Fehlalarm
  - Test: `tests/test_state_reader_source_416.py::test_wurzel_hinter_symlink_kein_fehlalarm`
- **AC-7:** Given die Klasse `UnsafeStateError` / When ihre Vererbung geprüft wird / Then erbt sie von `Exception`, aber weder von `OSError` noch von `ValueError`, sodass `except (OSError, ValueError)` in Leser-Code sie nicht verschluckt
  - Test: `tests/test_state_reader_source_416.py::test_unsafe_state_error_erbt_nicht_von_oserror_valueerror`
- **AC-8:** Given ein unsicherer State in einer der vier Richtungen / When ein Leser ihn meldet / Then nennt die Meldung Pfad, Grund und den Bereinigungsweg (Verweis bzw. State entfernen, Workflow frisch starten), und es erfolgt keine Reparatur durch Kopieren (die Datei hinter dem Verweis bleibt unverändert, es entsteht keine neue State-Datei)
  - Test: `tests/test_state_reader_source_416.py::test_meldung_nennt_pfad_grund_bereinigung_und_repariert_nicht`
- **AC-9:** Given ein unsicherer State (harter und weicher Verweis) und ein Code-Edit außerhalb der Always-Allowed-Dateien / When `edit_gate` bzw. `tdd_enforcement` als Subprozess läuft / Then enden sie mit Exit 2 und der Meldung aus AC-8; eine Always-Allowed-Datei bleibt frei
  - Test: `tests/test_state_reader_source_416.py::test_edit_gate_und_tdd_enforcement_blocken_code_edit_bei_unsicherem_state`
- **AC-10:** Given ein unsicherer State / When `bash_gate` einen state-abhängigen Befehl (`git commit`) und einen gewöhnlichen Befehl (`ls`) prüft / Then verweigert er nur den Commit (Exit 2 mit Meldung), der gewöhnliche Befehl endet mit Exit 0, damit der Zustand bereinigt werden kann
  - Test: `tests/test_state_reader_source_416.py::test_bash_gate_verweigert_nur_state_abhaengige_freigaben`
- **AC-11:** Given ein unsicherer State / When `phase_listener` (mit Freigabe-Phrase), `footer_gate` und `post_implementation_gate` laufen / Then enden alle mit Exit 0 und einer Warnung (nie Exit 2), und `phase_listener` schreibt weder einen Phasenwechsel noch eine Freigabe in den State
  - Test: `tests/test_state_reader_source_416.py::test_phase_listener_footer_gate_post_implementation_gate_fail_open_mit_warnung`
- **AC-12:** Given ein unsicherer State / When die `workflow.py`-CLI (`status`, `list`) läuft / Then endet sie mit Exit 1 und der Meldung aus AC-8, und `read_active_workflow_fast()` liefert kein Adversary-Verdict
  - Test: `tests/test_state_reader_source_416.py::test_workflow_cli_exit_1_mit_meldung`
- **AC-13:** Given ein unsicherer State / When `adversary_dialog` den Fast-Track-Check, die Metriken und `required-files` ausführt / Then gewährt der Fast-Track keine Freigabe, die Metriken warnen, `required-files` endet mit Exit 1
  - Test: `tests/test_state_reader_source_416.py::test_adversary_dialog_gewaehrt_keine_freigabe_bei_unsicherem_state`
- **AC-14:** Given ein unsicherer State / When `session_singleton_guard._read_workflow_phase` ihn liest / Then liefert die Funktion `None`
  - Test: `tests/test_state_reader_source_416.py::test_session_singleton_guard_liefert_none`
- **AC-15:** Given ein unsicherer State und die Lesen-Ändern-Schreiben-Stellen (`edit_gate` LoC-Delta, `bash_gate._write_e2e_scope`, `post_bash._record_test_run`) / When sie laufen / Then schreiben sie nicht zurück: die Datei hinter dem Verweis ist byte-gleich zum Zustand davor und wird nicht atomar als normale Datei ersetzt
  - Test: `tests/test_state_reader_source_416.py::test_rmw_stellen_schreiben_bei_unsicherem_state_nicht_zurueck`
- **AC-16:** Given ein State, der durch einen harten Verweis erreichbar ist / When `phase_listener._save_workflow` schreibt / Then geschieht das atomar (neuer Inode, kein Schreiben durch den Verweis hindurch): die über den zweiten Namen sichtbare Datei behält den alten Inhalt
  - Test: `tests/test_state_reader_source_416.py::test_phase_listener_save_workflow_schreibt_atomar`
- **AC-17:** Given die Spec `docs/specs/fix-410-state-integrity-gaps.md` / When Known Limitation F004 gelesen wird / Then verweist sie auf `docs/specs/fix-416-state-reader-source-check.md` bzw. #416 und gilt als aufgelöst
  - Test: `tests/test_state_reader_source_416.py::test_f004_in_fix_410_spec_verweist_auf_416`
- **AC-18:** Given der bestehende Testbestand / When die Vollsuite und das Regressionsnetz `tests/test_bash_gate*` laufen / Then bleiben sie grün (Normalfall unverändert)
  - Test: `tests/test_bash_gate_state_integrity_410.py` und `tests/test_bash_gate*` (unverändert, Lauf grün), Vollsuite

> Die Test-Zuordnung wird **bei der Spec-Erstellung** eingetragen, nicht nachträglich:
> Nach der Freigabe ist diese Datei eingefroren (#230) — jede Änderung verschiebt den
> PO-Briefing-Hash und blockt den Workflow-Abschluss. Stimmt der Testname später nicht
> mehr, gehört die Korrektur in die TDD-RED-Artefakte (`workflow.py add-artifact`),
> nicht in diese Datei.

## Test Plan

### Automated Tests (TDD RED)

Datei: `tests/test_state_reader_source_416.py`, parametrisiert je Leser × Richtung (harter Verweis, Symlink auf Datei, Symlink auf Ordner `.claude/workflows`, `.claude` als Symlink) plus Normalfall. Subprozess-Aufrufe der Hooks, wo das Verhalten über den Exit-Code sichtbar ist; Sandbox als Wegwerf-Projekt mit echtem Workflow-State. Abweichungen werden gesammelt und am Ende gemeinsam gemeldet.

- [ ] Test 1 (AC-1 bis AC-4): GIVEN Wegwerf-Projekt mit State-Datei, WHEN sie per hartem Verweis, Symlink auf Datei, Symlink auf Ordner bzw. `.claude` als Symlink ersetzt wird und `read_state_json` liest, THEN jeweils `UnsafeStateError` (RED: heute liefert jeder Leser den gefälschten Inhalt)
- [ ] Test 2 (AC-5, AC-6): GIVEN normale Datei, fehlende Datei, kaputtes JSON und eine Wurzel hinter einem Symlink-Elternordner, WHEN gelesen wird, THEN Verhalten wie heute, kein Fehlalarm (muss vor und nach der Implementierung grün sein)
- [ ] Test 3 (AC-7, AC-8): GIVEN `UnsafeStateError`, WHEN Vererbung und Meldung geprüft werden, THEN weder `OSError` noch `ValueError` als Basis; Meldung mit Pfad, Grund, Bereinigungsweg; keine Kopie
- [ ] Test 4 (AC-9, AC-10): GIVEN unsicherer State je Richtung, WHEN `edit_gate`, `tdd_enforcement` und `bash_gate` (Commit vs. `ls`) als Subprozess laufen, THEN Exit 2 bzw. 0 wie spezifiziert
- [ ] Test 5 (AC-11, AC-12, AC-13, AC-14): GIVEN unsicherer State je Richtung, WHEN `phase_listener`, `footer_gate`, `post_implementation_gate`, `workflow.py`-CLI, `adversary_dialog` und `session_singleton_guard` laufen, THEN fail-open mit Warnung, exit 1 bzw. `None` wie spezifiziert, kein Phasenwechsel und keine Freigabe
- [ ] Test 6 (AC-15, AC-16): GIVEN unsicherer State bzw. ein State mit hartem Verweis, WHEN die Lesen-Ändern-Schreiben-Stellen laufen und `_save_workflow` schreibt, THEN kein Zurückschreiben bzw. atomares Schreiben (neuer Inode)
- [ ] Test 7 (AC-17): GIVEN die #410-Spec, WHEN F004 geprüft wird, THEN Verweis auf #416 vorhanden
- [ ] Test 8 (AC-18): GIVEN der bestehende Bestand, WHEN `pytest tests/test_bash_gate_state_integrity_410.py` und `tests/test_bash_gate*` und die Vollsuite laufen, THEN grün

Die RED-Läufe müssen vor der Implementierung an allen vier Verweisrichtungen die Abweichung zeigen und werden als Artefakte registriert.

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Die Änderung verlegt die Prüfung aus #407/#410 („Gate prüft Befehlstext, Ausweg ist der Override-Token“) zusätzlich an die Quelle, ohne die bestehende Entscheidung zu kippen; sie ergänzt eine zweite Schicht. Kein neues Format, keine neue Abhängigkeit, keine Migration.

**Entscheidung: Prüfung an der Quelle per `dir_fd`-Walk in einer gemeinsamen Lesefunktion.** Regelweg zuerst: `lstat`/`fstat`-Vergleiche sind deterministisch und brauchen kein Modell. „Ohne Modell geht es nicht“ stellt sich nicht; die Prüfung ist reine Dateisystem-Metadatenabfrage.

**Alternativen (bewertet, nicht gewählt):**

- **A — nur zentrale Leser umstellen** (`workflow.py`, `edit_gate`, `bash_gate`; ca. 5 Dateien, im Limit): `post_bash`, `adversary_dialog` und die Lesen-Ändern-Schreiben-Stellen lesen weiter ungeprüft und schreiben die Fälschung atomar als echte Datei zurück; die Definition of Done „jeder Leser“ wäre nicht erfüllt. Verworfen.
- **B — Inhaltsbindung per Prüfsumme oder HMAC:** würde auch „Link löschen“ schließen, doch Schlüssel und Prüfsummen lägen in Reichweite derselben Bash und böten Scheinsicherheit; dazu neues Format und Migration. Würde die #410-Entscheidung „präventiv prüfen, Ausweg Override“ ergänzen statt ersetzen. Verworfen.
- **C — nur atomare Writer:** bricht harte Verweise beim nächsten Hook-Schreibvorgang, aber die Fälschung wird vorher gelesen und zählt. Als Ergänzung übernommen (Punkt 6), nicht als Ersatz.

## Changelog

- 2026-10-10: Initial spec created (#416)
